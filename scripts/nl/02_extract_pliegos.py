"""Extract structured fields from each cached EUR-Lex ENIG-DOCUMENT HTML.

Pipeline stage 02 (nl). Mirrors `scripts/sk/02_extract_pliegos.py` for
the NL corpus; the only language-specific bits live in
`scripts/_lib/nl/enig_document.py`.

v1 models the 21 NL wine GIs (12 PGIs + 9 standalone PDOs; the
cross-border Maasvallei Limburg ships on the BE side) as a flat corpus.

English-language fallback: a handful of NL wines have no published Dutch
translation of their single document — EUR-Lex serves the English
"SINGLE DOCUMENT" instead (e.g. Ambt Delden, PDO-NL-02169). Rather than
drop those to a stub, we re-anchor on the English template and route the
sections with the shared English keyword table from `_lib.mt`.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue,
    match_variety,
    set_pliego_context,
)
from _lib.nl.enig_document import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    _GRAPE_LINE_DROP,
    COLOUR_BY_KEYWORD,
    DOC_ANCHOR_RE,
    INLINE_ROLE_RE,
    ROLE_BY_KEYWORD,
    SECTION_HEADER_RE,
    SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS,
    STYLE_MARKERS,
)
from _lib.nl.region import derive_region  # noqa: E402

# English SINGLE-DOCUMENT keyword table for the NL English-fallback path.
# Based on the Malta (post-2019) keyword set but broadened for the older
# 2018-era template (Ambt Delden), whose section titles are shorter —
# "Main wine grapes" (no "variety"), "Demarcated area" (no "geographical").
EN_SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": ("name(s)", "name"),
    "category": (
        "categories of grapevine products", "categories",
        "geographical indication type",
    ),
    "description": ("description of the wine", "description of the product"),
    "viticultural_practices": (
        "wine making practices", "winemaking practices",
        "specific oenological practices", "maximum yields",
    ),
    "geo_area": (
        "demarcated geographical area", "demarcated area",
        "geographical area", "defined geographical area",
    ),
    "grape_varieties": (
        "main wine grapes variety", "main wine grape variety",
        "wine grape variet", "grape variet", "main wine grapes",
        "wine grapes",
    ),
    "link_to_terroir": (
        "description of the link", "link with the geographical area",
        "link to the geographical area", "causal link",
    ),
    "additional_conditions": (
        "essential further conditions", "further conditions",
        "other conditions",
    ),
}
EN_GEO_AREA_TITLE_BLOCKLIST = (
    "geographical indication type",
    "categories of grapevine products",
)

INDEX_IN = ROOT / "raw" / "nl" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "nl" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "nl" / "dokumenten-extracted"
INDEX_OUT = OUT_DIR / "_index.json"

# Tolerant anchor for the English "SINGLE DOCUMENT" slab (older OJ pages
# wrap the heading text in inline tags, newer ones leave it bare).
EN_DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>'
    r'(?:\s*<[^>]+>)*\s*SINGLE\s+DOCUMENT\s*(?:</[^>]+>\s*)*</p>',
    re.I | re.S,
)


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_document(html: str) -> str | None:
    m = DOC_ANCHOR_RE.search(html)
    if not m:
        return None
    return html[m.start():]


def find_section_offsets(html: str) -> list[tuple[str, str, int, int]]:
    out: list[tuple[str, str, int, int]] = []
    for m in SECTION_HEADER_RE.finditer(html):
        plaintext = re.sub(r"\s+", " ", strip_tags(m.group(1))).strip()
        nm = SECTION_NUM_RE.match(plaintext)
        if not nm:
            continue
        out.append((nm.group(1), nm.group(2).strip(), m.start(), m.end()))
    return out


def extract_sections(html: str) -> tuple[dict[str, str], dict[str, str]]:
    headers = find_section_offsets(html)
    if not headers:
        return {}, {}
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, _hstart, hend) in enumerate(headers):
        end = headers[i + 1][2] if i + 1 < len(headers) else len(html)
        bodies[num] = strip_tags(html[hend:end]).strip()
        titles[num] = title
    return bodies, titles


def extract_sections_en(html: str) -> tuple[dict[str, str], dict[str, str]]:
    """Monotonic section extraction for the English SINGLE-DOCUMENT template.

    The older 2018 EU-OJ Implementing-Decision layout (e.g. Ambt Delden)
    nests wine-type and oenological subsections (``5.1``, ``5.2`` and repeated
    "Wine category …" headers) that share the ``ti-grseq-1`` class with real
    top-level headers, and the table-celled numbering occasionally mis-slices.
    Keep only a strictly increasing 1→N top-level run so a nested or duplicate
    header can't stretch a later section's body — the Malta/HU/BG idiom.
    """
    headers = find_section_offsets(html)
    if not headers:
        return {}, {}
    kept: list[tuple[str, str, int, int]] = []
    last_top = 0
    for num, title, hstart, hend in headers:
        if "." in num:
            continue
        n = int(num)
        if n != last_top + 1:
            continue
        last_top = n
        kept.append((num, title, hstart, hend))
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, _hs, hend) in enumerate(kept):
        end = kept[i + 1][2] if i + 1 < len(kept) else len(html)
        bodies[num] = strip_tags(html[hend:end]).strip()
        titles[num] = title
    return bodies, titles


def _gather_subsections(sections: dict[str, str], parent_num: str) -> str:
    prefix = f"{parent_num}."
    children = sorted(
        (k for k in sections if k.startswith(prefix)),
        key=lambda k: tuple(int(p) if p.isdigit() else 0 for p in k.split(".")),
    )
    return "\n".join(sections[k] for k in children if sections.get(k))


def _match_section_body(
    sections: dict[str, str], titles: dict[str, str],
    keywords: tuple[str, ...], title_blocklist: tuple[str, ...] = (),
) -> str | None:
    for kw in keywords:
        for num, title in titles.items():
            tlow = title.lower()
            if kw not in tlow:
                continue
            if any(b in tlow for b in title_blocklist):
                continue
            body = sections.get(num, "")
            if not body.strip():
                body = _gather_subsections(sections, num)
            return body
    return None


def route_sections(sections: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    routed: dict[str, str] = {}
    for role, keywords in SECTION_ROLE_KEYWORDS.items():
        blocklist = _GEO_AREA_TITLE_BLOCKLIST if role == "geo_area" else ()
        body = _match_section_body(sections, titles, keywords, blocklist)
        if body is not None:
            routed[role] = body
    return routed


def route_sections_en(sections: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Route an English SINGLE-DOCUMENT's sections with the EN keyword table."""
    routed: dict[str, str] = {}
    for role, keywords in EN_SECTION_ROLE_KEYWORDS.items():
        blocklist = EN_GEO_AREA_TITLE_BLOCKLIST if role == "geo_area" else ()
        body = _match_section_body(sections, titles, keywords, blocklist)
        if body is not None:
            routed[role] = body
    return routed


_BULLET_SPLIT_RE = re.compile(r"\s*[—•·]\s*|\n")
_NAME_SYN_SPLIT_RE = re.compile(r"\s+[-–]\s+")


def _grape_items(section_text: str) -> list[str]:
    items: list[str] = []
    for chunk in _BULLET_SPLIT_RE.split(section_text or ""):
        chunk = chunk.strip(" \t;,.")
        if chunk:
            items.append(chunk)
    return items


def _item_candidates(item: str) -> list[str]:
    parts = _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)
    head = parts[0]
    syn_blob = parts[1] if len(parts) > 1 else ""
    out: list[str] = []
    for c in [head, *syn_blob.split(",")]:
        c = re.sub(r"\s*\(.*?\)\s*", " ", c).strip()
        if c and c not in out:
            out.append(c)
    return out


_COLOUR_CODE_TOKEN_RE = re.compile(r"^(?:B|N|G|Rs|Rg)$", re.I)


def _merged_cell_matches(item: str) -> list[tuple[str, str, str]]:
    """Recover 2+ varieties packed into one cell (e.g. the Ambt Delden
    EU-OJ section 7 lists ``Solaris Regent`` in a single table cell).

    Splits ONLY when every whitespace token (after dropping a trailing
    colour-code letter) independently resolves to a known variety, so
    genuine multi-word names (Souvignier Gris, Pinot Noir) are never split.
    """
    head = _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)[0]
    tokens = [t for t in head.split() if not _COLOUR_CODE_TOKEN_RE.match(t)]
    if len(tokens) < 2:
        return []
    matches = [match_variety(t) for t in tokens]
    if not all(matches):
        return []
    return [(tok, m.slug, m.colour) for tok, m in zip(tokens, matches)]


def parse_grapes(section_text: str) -> dict:
    out: dict[str, list] = {
        "principal": [], "accessory": [], "observation": [], "details": [],
    }
    if not section_text:
        return out
    seen_slugs: set[str] = set()
    current_role = "principal"
    for raw_item in _grape_items(section_text):
        item = raw_item.strip()
        if not item:
            continue
        m_role = INLINE_ROLE_RE.match(item)
        if m_role:
            kw = m_role.group(1).lower()
            for k, v in ROLE_BY_KEYWORD.items():
                if kw.startswith(k):
                    current_role = v
                    break
            tail = item[m_role.end():].strip()
            if not tail:
                continue
            item = tail
        low = item.lower()
        if any(d in low for d in _GRAPE_LINE_DROP) and len(item) < 45:
            continue
        for cand in _item_candidates(item):
            match = match_variety(cand)
            if match is None:
                continue
            slug = match.slug
            if slug in seen_slugs:
                break
            seen_slugs.add(slug)
            out[current_role].append(slug)
            out["details"].append({
                "slug": slug,
                "name": _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)[0].strip(),
                "role": current_role,
                "colour": match.colour,
            })
            break
        else:
            for name, slug, colour in _merged_cell_matches(item):
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                out[current_role].append(slug)
                out["details"].append({
                    "slug": slug, "name": name,
                    "role": current_role, "colour": colour,
                })
    return out


_GRAPE_COLOUR_TO_STYLE = {"blanc": "blanc", "noir": "noir", "gris": "blanc", "rose": "rose"}


def parse_styles(
    sections: dict[str, str], titles: dict[str, str],
    grape_details: list[dict] | None = None, wine_name: str = "",
) -> list[str]:
    blob_parts = []
    title_kw = ("beschrijving van de wijn", "categorieën", "andere essentiële")
    for num, body in sections.items():
        title_low = titles.get(num, "").lower()
        if any(kw in title_low for kw in title_kw):
            blob_parts.append(body)
    blob = " ".join(blob_parts) + " " + (wine_name or "")
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob, re.I):
            found.add(colour_slug)
    for pattern, slug in STYLE_MARKERS:
        if pattern.search(blob):
            found.add(slug)
    if grape_details:
        for g in grape_details:
            base = _GRAPE_COLOUR_TO_STYLE.get(g.get("colour") or "", "")
            if base:
                found.add(base)
    return sorted(found)


def derive_summary(role_text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", role_text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def build_record(wine: dict, sections: dict[str, str], titles: dict[str, str],
                 oj_meta: dict, routed: dict[str, str] | None = None) -> dict:
    if routed is None:
        routed = route_sections(sections, titles)
    grapes = parse_grapes(routed.get("grape_varieties", ""))
    styles = parse_styles(
        sections, titles, grape_details=grapes.get("details") or [],
        wine_name=wine.get("name", ""),
    )
    geo_area = routed.get("geo_area", "")
    region = derive_region({"file_number": wine["fileNumber"]})
    return {
        "country": "nl",
        "source_lang": "nl",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "region": region,
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": derive_summary(routed.get("description") or geo_area or ""),
        "sections": sections,
        "section_titles": titles,
        "section_roles": routed,
        "grapes": grapes,
        "styles": styles,
        "geo_area_brief": geo_area,
        "link_to_terroir": routed.get("link_to_terroir", ""),
        "producer_group": wine["producer_group"],
        "publications": wine["publications"],
        "source": {
            "filename": f"{wine['slug']}.html",
            "source_url": oj_meta.get("source_url", ""),
            "final_url": oj_meta.get("final_url", ""),
            "bytes": oj_meta.get("bytes", 0),
            "fetched_at": oj_meta.get("fetched_at", ""),
        },
        "stub": False,
    }


def build_stub(wine: dict, oj_meta: dict, reason: str) -> dict:
    return {
        "country": "nl",
        "source_lang": "nl",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "region": derive_region({"file_number": wine["fileNumber"]}),
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": "",
        "sections": {}, "section_titles": {}, "section_roles": {},
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [],
        "geo_area_brief": "",
        "link_to_terroir": "",
        "producer_group": wine["producer_group"],
        "publications": wine["publications"],
        "source": {
            "filename": "",
            "source_url": oj_meta.get("source_url", ""),
            "final_url": oj_meta.get("final_url", ""),
            "bytes": 0,
            "fetched_at": oj_meta.get("fetched_at", ""),
        },
        "stub": True,
        "stub_reason": reason,
    }


def _extract_from_html(
    cache: Path,
) -> tuple[dict[str, str], dict[str, str], str, str]:
    """Return (sections, titles, doc_lang, parse_reason).

    Tries the Dutch ENIG-DOCUMENT template first; falls back to the
    English SINGLE-DOCUMENT template when no Dutch translation was
    published (EUR-Lex then serves the English variant).
    """
    html = cache.read_text(encoding="utf-8")
    doc = slice_document(html)
    if doc is not None:
        sections, titles = extract_sections(doc)
        if sections:
            return sections, titles, "nl", ""
        return {}, {}, "nl", "no-sections"
    m = EN_DOC_ANCHOR_RE.search(html)
    if m is None:
        return {}, {}, "nl", "no-enig-document-anchor"
    sections, titles = extract_sections_en(html[m.start():])
    if not sections:
        return {}, {}, "en", "no-sections"
    return sections, titles, "en", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/nl/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_IN.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        wines = wines[: args.limit]

    oj_manifest: dict = {}
    if OJ_MANIFEST.exists():
        try:
            oj_manifest = json.loads(OJ_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    extracted = stubs = parse_failed = 0
    index: dict[str, dict] = {}

    for w in tqdm(wines, desc="extract-dokumenten", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        oj_meta = oj_manifest.get(slug, {})
        html_cache = OJ_DIR / f"{slug}.html"
        if html_cache.exists():
            sections, titles, doc_lang, parse_reason = _extract_from_html(html_cache)
        else:
            sections, titles, doc_lang, parse_reason = (
                {}, {}, "nl", oj_meta.get("status") or "no-html-cached"
            )
        if parse_reason or not sections:
            record = build_stub(w, oj_meta, parse_reason or "no-sections")
            if parse_reason in (
                "no-html-cached", "no-publication", "fetch-error",
                "not-single-document", "playwright-error",
            ):
                stubs += 1
            else:
                parse_failed += 1
        else:
            routed = route_sections_en(sections, titles) if doc_lang == "en" else None
            record = build_record(w, sections, titles, oj_meta, routed=routed)
            record["source"]["filename"] = html_cache.name
            extracted += 1
        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "country": "nl",
            "source_lang": "nl",
            "id_eambrosia": w["giIdentifier"],
            "file_number": w["fileNumber"],
            "slug": slug,
            "name": w["name"],
            "kind": w["kind"],
            "filename": out_path.name,
            "is_sub_denomination": False,
            "parent_slug": "",
            "stub": record["stub"],
            "stub_reason": record.get("stub_reason", ""),
            "sections_present": sorted(record["sections"]),
            "n_grapes": len(record["grapes"].get("details") or []),
        }

    set_pliego_context(None)
    INDEX_OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    unknowns_path = ROOT / "raw" / "nl" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(f"[entity] {n_unknowns} unknown variety candidates → "
              f"{unknowns_path.relative_to(ROOT)}", file=sys.stderr)
    print(f"[done] extracted={extracted} stubs={stubs} parse_failed={parse_failed} "
          f"→ {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
