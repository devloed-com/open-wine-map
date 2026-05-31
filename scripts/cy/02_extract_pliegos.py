"""Extract structured fields from each cached EUR-Lex ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ HTML.

Pipeline stage 02 (cy).

For each Greek wine GI in `raw/cy/eambrosia/index.json`:
  - if a cached HTML exists at `raw/cy/oj-pages/<slug>.html`, parse the
    "ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ" block into numbered sections (the EU wine GI
    template) and route them by Greek title keyword
  - else emit a content-stub so the wine remains searchable

In addition to the standard role-routed sections, the CY extractor
harvests the **δήμος / κοινότητα list** from the section-6 area body
(`geo_communes`) so stage 04's `GRPolygonIndex.commune_union` can
resolve geometry against the shared GISCO LAU `EL_*` index when
necessary. Mirrors the RO / BG commune-list fallback.

Output: one JSON per wine under `raw/cy/dokumenti-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata.

v1 models the 147 Greek wine GIs as a flat corpus — the 9 macro wine
regions (αμπελουργικές ζώνες) are preserved via the `region` facet
rather than as parent / sub-denomination records.
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
from _lib.cy.eniaio_engrafo import (  # noqa: E402
    DOC_ANCHOR_NORM, SECTION_HEADER_RE, SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS, ROLE_BY_KEYWORD, INLINE_ROLE_RE,
    STYLE_MARKERS, COLOUR_BY_KEYWORD, _GEO_AREA_TITLE_BLOCKLIST,
    greek_norm,
)
from _lib.cy.region import derive_region  # noqa: E402
from _lib.cy.commune import parse_commune_list  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "cy" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "cy" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "cy" / "dokumenti-extracted"
INDEX_OUT = OUT_DIR / "_index.json"


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_document_unic(html: str) -> str | None:
    """Walk every `ti-grseq-1` header and return `html[m.start():]` for
    the first whose `greek_norm(text)` equals the anchor. Robust to
    polytonic vs monotonic diacritics and final-sigma drift, both of
    which break a literal-regex match. The modification-preamble
    template carries an outer header like `ΚΟΙΝΟΠΟΙΗΣΗ ΤΥΠΙΚΗΣ
    ΤΡΟΠΟΠΟΙΗΣΗΣ … ΤΟΥ ΕΝΙΑΙΟΥ ΕΓΓΡΑΦΟΥ` and a separate inner
    `ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ` header — only the inner one matches because
    the outer is inflected (genitive)."""
    for m in SECTION_HEADER_RE.finditer(html):
        inner = strip_tags(m.group(1))
        inner_norm = greek_norm(re.sub(r"\s+", " ", inner).strip())
        if inner_norm == DOC_ANCHOR_NORM:
            return html[m.start():]
    return None


def find_section_offsets(html: str) -> list[tuple[str, str, int, int]]:
    out: list[tuple[str, str, int, int]] = []
    for m in SECTION_HEADER_RE.finditer(html):
        plaintext = re.sub(r"\s+", " ", strip_tags(m.group(1))).strip()
        nm = SECTION_NUM_RE.match(plaintext)
        if not nm:
            continue
        out.append((nm.group(1), nm.group(2).strip(), m.start(), m.end()))
    return out


_TOP_LEVEL_ROLE_TITLE_KEYWORDS_NORM: tuple[str, ...] = tuple(
    greek_norm(kw) for kws in SECTION_ROLE_KEYWORDS.values() for kw in kws
)


def _title_matches_role(title: str) -> bool:
    low = greek_norm(title)
    return any(kw in low for kw in _TOP_LEVEL_ROLE_TITLE_KEYWORDS_NORM)


def extract_sections(html: str) -> tuple[dict[str, str], dict[str, str]]:
    """Walk section headers in document order. Some Greek publications
    nest sub-section headers inside section 4 (Περιγραφή των οίνων) for
    per-style / per-variety entries — those nested `ti-grseq-1` headers
    are numbered `1.` / `2.` / … and would shadow the real sections
    5–9 if we deduped naively. Two filters apply (the BG pattern):
      1. Numeric monotonic: a top-level number must not go backwards.
      2. Title match: a top-level header's title must contain at least
         one known section-role keyword."""
    headers = find_section_offsets(html)
    if not headers:
        return {}, {}
    top_level_seen: set[int] = set()
    kept: list[tuple[str, str, int, int]] = []
    last_top_int = 0
    for h in headers:
        num, title, _hstart, _hend = h
        try:
            top = int(num.split(".")[0])
        except ValueError:
            continue
        if "." in num:
            kept.append(h)
            continue
        if top in top_level_seen or top < last_top_int:
            continue
        if not _title_matches_role(title):
            continue
        top_level_seen.add(top)
        last_top_int = top
        kept.append(h)
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, _hstart, hend) in enumerate(kept):
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
    sections: dict[str, str],
    titles: dict[str, str],
    keywords: tuple[str, ...],
    title_blocklist: tuple[str, ...] = (),
) -> str | None:
    """Keyword-priority match: outer loop on keywords (most specific first),
    inner loop on sections in document order. Falls back to a section's
    numbered children when the parent body is empty. Both the title and
    every keyword run through `greek_norm` (casefold + diacritic-strip
    + final-sigma fold) before substring comparison."""
    norm_keywords = [greek_norm(kw) for kw in keywords]
    norm_blocklist = [greek_norm(b) for b in title_blocklist]
    norm_titles = {num: greek_norm(t) for num, t in titles.items()}
    for kw in norm_keywords:
        for num, tnorm in norm_titles.items():
            if kw not in tnorm:
                continue
            if any(b in tnorm for b in norm_blocklist):
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


# Greek grape-variety sections enumerate varieties separated by em-dash
# bullets, em-dash hyphens, newlines, or numbered lists.
_BULLET_SPLIT_RE = re.compile(r"\s*[—•·]\s*|\n|\s*\d+\.\s+")
# Name — Latin-synonym separator: hyphen-with-spaces.
_NAME_SYN_SPLIT_RE = re.compile(r"\s+[-–]\s+")

_GRAPE_LINE_DROP = (
    "κύρια οινοποιήσιμη ποικιλία ή ποικιλίες σταφυλιού",
    "κύρια οινοποιήσιμη ποικιλία/-ίες σταφυλιού",
    "κύριες οινοποιήσιμες ποικιλίες σταφυλιού",
    "οινοποιήσιμες ποικιλίες σταφυλιού",
    "ποικιλίες σταφυλιού",
    "ποικιλία σταφυλιού",
)


def _grape_items(section_text: str) -> list[str]:
    items: list[str] = []
    for chunk in _BULLET_SPLIT_RE.split(section_text or ""):
        chunk = chunk.strip(" \t;,.-")
        if chunk:
            items.append(chunk)
    return items


def _item_candidates(item: str) -> list[str]:
    """Variety-name candidates: canonical Greek name first, then any
    Latin synonym after a plain hyphen separator."""
    parts = _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)
    head = parts[0]
    syn_blob = parts[1] if len(parts) > 1 else ""
    out: list[str] = []
    for c in [head, *syn_blob.split(",")]:
        c = re.sub(r"\s*\(.*?\)\s*", " ", c).strip()
        if c and c not in out:
            out.append(c)
    return out


def parse_grapes(section_text: str) -> dict:
    """Parse the grape-variety section body into {principal, accessory,
    observation, details}. Greek single documents generally do not split
    principal / accessory; we default to `principal`."""
    out: dict[str, list] = {
        "principal": [],
        "accessory": [],
        "observation": [],
        "details": [],
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

        low = item.casefold()
        if any(d in low for d in _GRAPE_LINE_DROP) and len(item) < 75:
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


def parse_styles(sections: dict[str, str], titles: dict[str, str]) -> list[str]:
    """Detect style tags from the description + additional-conditions
    sections."""
    blob_parts = []
    for num, body in sections.items():
        title_low = titles.get(num, "").casefold()
        if (
            "περιγραφή" in title_low and "οίν" in title_low
            or "κατηγορίες" in title_low
            or "άλλες ουσιώδεις" in title_low
            or "πρόσθετες" in title_low
        ):
            blob_parts.append(body)
    blob = " ".join(blob_parts)
    blob_norm = greek_norm(blob)
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD.items():
        if greek_norm(kw) in blob_norm:
            found.add(colour_slug)
    for pattern, slug in STYLE_MARKERS:
        if pattern.search(blob):
            found.add(slug)
    return sorted(found)


def derive_summary(role_text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", role_text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def build_record(wine: dict, sections: dict[str, str], titles: dict[str, str],
                 oj_meta: dict) -> dict:
    routed = route_sections(sections, titles)
    grapes = parse_grapes(routed.get("grape_varieties", ""))
    styles = parse_styles(sections, titles)
    geo_area = routed.get("geo_area", "")
    geo_communes = parse_commune_list(geo_area) if geo_area else []
    region = derive_region(
        {"file_number": wine["fileNumber"]},
        geo_area,
        routed.get("link_to_terroir", ""),
        wine["name"],
    )
    return {
        "country": "cy",
        "source_lang": "el",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "name_latin": wine.get("name_latin", ""),
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
        "geo_communes": geo_communes,
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
        "country": "cy",
        "source_lang": "el",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "name_latin": wine.get("name_latin", ""),
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
        "geo_communes": [],
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


def _extract_from_html(cache: Path) -> tuple[dict[str, str], dict[str, str], str]:
    html = cache.read_text(encoding="utf-8")
    doc = slice_document_unic(html)
    if doc is None:
        return {}, {}, "no-eniaio-engrafo-anchor"
    sections, titles = extract_sections(doc)
    if not sections:
        return {}, {}, "no-sections"
    return sections, titles, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/cy/00_fetch_data.py first",
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

    for w in tqdm(wines, desc="extract-dokumenti", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        oj_meta = oj_manifest.get(slug, {})
        html_cache = OJ_DIR / f"{slug}.html"

        if html_cache.exists():
            sections, titles, parse_reason = _extract_from_html(html_cache)
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
            record["source"]["filename"] = html_cache.name
            extracted += 1

        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "country": "cy",
            "id_eambrosia": w["giIdentifier"],
            "file_number": w["fileNumber"],
            "slug": slug,
            "name": w["name"],
            "name_latin": record.get("name_latin", ""),
            "kind": w["kind"],
            "filename": out_path.name,
            "is_sub_denomination": False,
            "parent_slug": "",
            "stub": record["stub"],
            "stub_reason": record.get("stub_reason", ""),
            "sections_present": sorted(record["sections"]),
            "n_grapes": len(record["grapes"].get("details") or []),
            "n_communes": len(record.get("geo_communes") or []),
        }

    set_pliego_context(None)
    INDEX_OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    unknowns_path = ROOT / "raw" / "cy" / "extraction-unknowns.json"
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
