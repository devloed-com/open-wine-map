"""Extract structured fields from each cached EUR-Lex single-document HTML.

Pipeline stage 02 (be).

For each Belgian wine GI in `raw/be/eambrosia/index.json`:
  - if a cached HTML exists at `raw/be/oj-pages/<slug>.html`, parse the
    "ENIG DOCUMENT" (Dutch) or "DOCUMENT UNIQUE" (French) block into
    numbered sections (the EU wine GI template) and route them by the
    per-record source_lang title keywords
  - else emit a stub record so the wine remains searchable

Output: one JSON per wine under `raw/be/dokumenten-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata.

v1 models the 10 Belgian wine GIs as a flat corpus — no sub-denominations.
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
from _lib.be.document import (  # noqa: E402
    DOC_ANCHOR_RE, SECTION_HEADER_RE, SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS, ROLE_BY_KEYWORD, INLINE_ROLE_RE,
    STYLE_MARKERS, COLOUR_BY_KEYWORD, _GEO_AREA_TITLE_BLOCKLIST,
    _GRAPE_LINE_DROP,
)
from _lib.be.region import derive_region  # noqa: E402
from _lib.be.text_parser import (  # noqa: E402
    pdftotext, parse_enig_document_text, parse_wallex_text,
    parse_wallex_standalone_text,
    WALLEX_CHAPTER_BY_SLUG, WALLEX_CHAPTER_BY_FILE_NUMBER,
    WALLEX_STANDALONE_SLUGS, WALLEX_STANDALONE_FILE_NUMBERS,
)
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "be" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "be" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "be" / "dokumenten-extracted"
INDEX_OUT = OUT_DIR / "_index.json"


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_document(html: str, lang: str) -> str | None:
    m = DOC_ANCHOR_RE[lang].search(html)
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


def _gather_subsections(sections: dict[str, str], parent_num: str) -> str:
    prefix = f"{parent_num}."
    children = sorted(
        (k for k in sections if k.startswith(prefix)),
        key=lambda k: tuple(int(p) if p.isdigit() else 0 for p in k.split(".")),
    )
    return "\n".join(sections[k] for k in children if sections.get(k))


def _match_section_body(
    sections: dict[str, str],
    titles: dict[str, str],
    keywords: tuple[str, ...],
    title_blocklist: tuple[str, ...] = (),
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


def route_sections(
    sections: dict[str, str], titles: dict[str, str], lang: str,
) -> dict[str, str]:
    routed: dict[str, str] = {}
    role_kw = SECTION_ROLE_KEYWORDS[lang]
    blocklist_geo = _GEO_AREA_TITLE_BLOCKLIST[lang]
    for role, keywords in role_kw.items():
        blocklist = blocklist_geo if role == "geo_area" else ()
        body = _match_section_body(sections, titles, keywords, blocklist)
        if body is not None:
            routed[role] = body
    return routed


# Grape-variety section parsing: split on bullets / newlines, then on a
# `Name - synonym` separator. Some BE Dutch templates list one variety per
# line as a bare name (Maasvallei: Acolon / Auxerrois / Chardonnay / …).
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


def parse_grapes(section_text: str, lang: str) -> dict:
    """Parse the grape-variety section body into {principal, accessory,
    observation, details}. The EU single document is usually flat —
    default to `principal`. Unmatched names flow into
    `raw/be/extraction-unknowns.json`."""
    out: dict[str, list] = {
        "principal": [],
        "accessory": [],
        "observation": [],
        "details": [],
    }
    if not section_text:
        return out

    inline_role = INLINE_ROLE_RE[lang]
    role_by_kw = ROLE_BY_KEYWORD[lang]
    line_drop = _GRAPE_LINE_DROP[lang]
    seen_slugs: set[str] = set()
    current_role = "principal"

    for raw_item in _grape_items(section_text):
        item = raw_item.strip()
        if not item:
            continue

        m_role = inline_role.match(item)
        if m_role:
            kw = m_role.group(1).lower()
            for k, v in role_by_kw.items():
                if kw.startswith(k):
                    current_role = v
                    break
            tail = item[m_role.end():].strip()
            if not tail:
                continue
            item = tail

        low = item.lower()
        if any(d in low for d in line_drop) and len(item) < 45:
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
    return out


_GRAPE_COLOUR_TO_STYLE = {
    "blanc": "blanc",
    "noir": "noir",
    "gris": "blanc",
    "rose": "rose",
}


def parse_styles(
    sections: dict[str, str], titles: dict[str, str], lang: str,
    grape_details: list[dict] | None = None,
    wine_name: str = "",
) -> list[str]:
    """Belgium produces still wines + Crémant-de-Wallonie family +
    Vlaamse mousserende kwaliteitswijn. The EU OJ template describes
    wine styles per-variety, not in whole-wine bucket sentences, so the
    section-text colour scan rarely matches; the grape-colour fallback
    (below) covers the still-wine baseline. Sparkling markers still
    come from the section text + the wine name."""
    blob_parts = []
    title_kw_per_lang = {
        "nl": (
            "beschrijving van de wijn", "categorieën", "andere essentiële",
        ),
        "fr": (
            "description du vin", "description des vins", "catégories",
            "autres conditions",
        ),
    }
    for num, body in sections.items():
        title_low = titles.get(num, "").lower()
        if any(kw in title_low for kw in title_kw_per_lang[lang]):
            blob_parts.append(body)
    blob = " ".join(blob_parts) + " " + (wine_name or "")
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD[lang].items():
        if re.search(rf"\b{re.escape(kw)}\b", blob, re.I):
            found.add(colour_slug)
    for pattern, slug in STYLE_MARKERS[lang]:
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
                 oj_meta: dict) -> dict:
    lang = wine.get("source_lang") or "nl"
    routed = route_sections(sections, titles, lang)
    grapes = parse_grapes(routed.get("grape_varieties", ""), lang)
    styles = parse_styles(
        sections, titles, lang,
        grape_details=grapes.get("details") or [],
        wine_name=wine.get("name", ""),
    )
    geo_area = routed.get("geo_area", "")
    region = derive_region(
        {"file_number": wine["fileNumber"]},
        geo_area,
        routed.get("link_to_terroir", ""),
        wine["name"],
    )
    return {
        "country": "be",
        "source_lang": lang,
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
    lang = wine.get("source_lang") or "nl"
    return {
        "country": "be",
        "source_lang": lang,
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "region": derive_region({"file_number": wine["fileNumber"]}),
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": "",
        "sections": {},
        "section_titles": {},
        "section_roles": {},
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


def _extract_from_html(cache: Path, lang: str) -> tuple[dict[str, str], dict[str, str], str]:
    html = cache.read_text(encoding="utf-8")
    doc = slice_document(html, lang)
    if doc is None:
        return {}, {}, f"no-{lang}-document-anchor"
    sections, titles = extract_sections(doc)
    if not sections:
        return {}, {}, "no-sections"
    return sections, titles, ""


def _extract_from_pdf(
    pdf_cache: Path, lang: str, slug: str, file_number: str, name: str = "",
) -> tuple[dict[str, str], dict[str, str], str]:
    """Route a cached PDF through the right text-mode parser:
    - WALLEX single-AOC PDFs (Côtes de Sambre et Meuse) → WALLEX
      standalone parser (one decree, one appellation, no chapters).
    - WALLEX PDFs (the 2 Walloon sparkling PDOs) → WALLEX-specific
      chapter parser (one decree, two PDOs, one chapter each).
    - Flemish PDFs structurally identical to EU enig documents →
      the NL text-mode enig-document parser.
    """
    text = pdftotext(pdf_cache)
    if not text:
        return {}, {}, "pdftotext-empty"
    if slug in WALLEX_STANDALONE_SLUGS or file_number in WALLEX_STANDALONE_FILE_NUMBERS:
        sections, titles = parse_wallex_standalone_text(
            text, slug=slug, file_number=file_number, name=name,
        )
        if not sections:
            return {}, {}, "wallex-standalone-parse-empty"
        return sections, titles, ""
    is_wallex = (
        slug in WALLEX_CHAPTER_BY_SLUG
        or file_number in WALLEX_CHAPTER_BY_FILE_NUMBER
        or "wallex" in pdf_cache.read_bytes()[:2048].decode("latin-1", "ignore").lower()
    )
    if is_wallex:
        sections, titles = parse_wallex_text(
            text, slug=slug, file_number=file_number,
        )
        if not sections:
            return {}, {}, "wallex-parse-empty"
        return sections, titles, ""
    if lang == "nl":
        sections, titles = parse_enig_document_text(text)
        if not sections:
            return {}, {}, "no-flemish-headers-in-pdf"
        return sections, titles, ""
    return {}, {}, f"no-pdf-parser-for-{lang}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/be/00_fetch_data.py first",
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
        lang = w.get("source_lang") or "nl"
        file_number = w.get("fileNumber") or ""
        set_pliego_context(slug)
        oj_meta = oj_manifest.get(slug, {})
        html_cache = OJ_DIR / f"{slug}.html"
        pdf_cache = OJ_DIR / f"{slug}.pdf"

        if html_cache.exists():
            sections, titles, parse_reason = _extract_from_html(html_cache, lang)
        elif pdf_cache.exists():
            sections, titles, parse_reason = _extract_from_pdf(
                pdf_cache, lang, slug, file_number, w.get("name", ""),
            )
        else:
            sections, titles, parse_reason = {}, {}, oj_meta.get("status") or "no-html-cached"

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
            record = build_record(w, sections, titles, oj_meta)
            record["source"]["filename"] = (
                html_cache.name if html_cache.exists() else pdf_cache.name
            )
            extracted += 1

        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "country": "be",
            "source_lang": lang,
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
    unknowns_path = ROOT / "raw" / "be" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )

    print(
        f"[done] extracted={extracted} stubs={stubs} parse_failed={parse_failed} "
        f"→ {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
