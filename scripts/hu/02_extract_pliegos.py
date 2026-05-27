"""Extract structured fields from each cached EUR-Lex Egységes-dokumentum HTML.

Pipeline stage 02 (hu).

For each Hungarian wine GI in `raw/hu/eambrosia/index.json`:
  - if a cached HTML exists at `raw/hu/oj-pages/<slug>.html`, parse the
    "EGYSÉGES DOKUMENTUM" block into numbered sections (the EU wine GI
    template) and route them by Hungarian title keyword
  - else emit a stub record so the wine remains searchable

Output: one JSON per wine under `raw/hu/dokumenti-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata.

v1 models the 41 Hungarian wine GIs as a flat corpus — the regulatory
hierarchy (7 borrégió ⊃ 22 borvidék ⊃ dűlő names) is preserved via the
`region` facet rather than as parent / sub-denomination records.
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
from _lib.hu.egyseges_dokumentum import (  # noqa: E402
    DOC_ANCHOR_RE, SECTION_HEADER_RE, SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS, ROLE_BY_KEYWORD, INLINE_ROLE_RE,
    STYLE_MARKERS, COLOUR_BY_KEYWORD, _GEO_AREA_TITLE_BLOCKLIST,
)
from _lib.hu.region import derive_region  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "hu" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "hu" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "hu" / "dokumentumok-extracted"
INDEX_OUT = OUT_DIR / "_index.json"


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_egyseges_dokumentum(html: str) -> str | None:
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


# Wine-type subsection title prefixes used inside section 4 (description
# of wines). Hungarian docs (Kunság, Eger, Mátra, …) restart numbering at
# 1 for each wine type ("1. Bor – Rozé fajta és küvé", …), and the EUR-Lex
# template reuses `<p class="ti-grseq-1">` for those nested rows. We have
# to filter them by title prefix; treating them as top-level sections
# would shadow the real sections 5–9 that follow.
_NESTED_TITLE_PREFIXES = (
    "bor -", "bor –", "bor —",
    "pezsgő", "pezsgo",
    "likőrbor", "likorbor",
    "szén-dioxid", "szen-dioxid",
    "muszt", "must",
    "gyöngyöző", "gyongyozo",
    "rövid szöveges leírás", "rovid szoveges leiras",
    "classicus", "superior", "grand superior",
    "kötelezően", "kotelezoen",
    "nem engedélyezett", "nem engedelyezett",
    "a szőlőművelés", "a szolomuveles",
    "a szőlő minimális", "a szolo minimalis",
)


def _looks_like_nested_subsection(title: str) -> bool:
    low = title.lower().strip()
    return any(low.startswith(p) for p in _NESTED_TITLE_PREFIXES)


def extract_sections(html: str) -> tuple[dict[str, str], dict[str, str]]:
    """Carve the EGYSÉGES DOKUMENTUM slab into top-level numbered sections.

    Hungarian docs (e.g. Kunság, Eger) re-use `<p class="ti-grseq-1">` for
    wine-type subsections nested inside section 4 (description of wines)
    and section 5.1 / 8.1-8.4 (vinification + link subsections), which
    restart numbering at 1 each. A naive "first-occurrence" dedupe keeps
    those nested subsection bodies and silently drops the real top-level
    5–9 that appear later. The state machine walks headers in document
    order and accepts each one only when:
      - it's the next expected top-level integer AND
      - its title doesn't match a known nested-subsection prefix
        (`Bor -`, `Pezsgő -`, `Classicus`, …)
    or
      - it's a sub-number `top.x` of the most recently accepted top-level.
    """
    headers = find_section_offsets(html)
    if not headers:
        return {}, {}
    accepted: list[tuple[int, str, str, int, int]] = []
    last_top: int = 0
    for i, (num, title, hstart, hend) in enumerate(headers):
        parts = num.split(".")
        if not all(p.isdigit() for p in parts):
            continue
        ip = tuple(int(p) for p in parts)
        if len(ip) == 1:
            if ip[0] != last_top + 1:
                continue
            if _looks_like_nested_subsection(title):
                continue
            accepted.append((i, num, title, hstart, hend))
            last_top = ip[0]
        else:
            if ip[0] == last_top:
                accepted.append((i, num, title, hstart, hend))

    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for j, (_idx, num, title, _hs, hend) in enumerate(accepted):
        end = accepted[j + 1][3] if j + 1 < len(accepted) else len(html)
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
    numbered children when the parent body is empty."""
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


# Hungarian grape-variety sections list one variety per line as
# `Canonical name – Synonym, Synonym, ...` (with an en-dash separator).
# The canonical name is the segment before the dash.
_BULLET_SPLIT_RE = re.compile(r"\s*[—•·]\s*|\n")
_NAME_SYN_SPLIT_RE = re.compile(r"\s+[-–]\s+")

_GRAPE_LINE_DROP = (
    "fontosabb borszőlőfajták", "fontosabb borszolofajtak",
    "borszőlőfajta", "borszolofajta",
    "szőlőfajták", "szolofajtak",
)


def _grape_items(section_text: str) -> list[str]:
    items: list[str] = []
    for chunk in _BULLET_SPLIT_RE.split(section_text or ""):
        chunk = chunk.strip(" \t;,.")
        if chunk:
            items.append(chunk)
    return items


def _item_candidates(item: str) -> list[str]:
    """Variety-name candidates for one item, canonical name first then
    its synonyms (the segment(s) after a plain hyphen)."""
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
    observation, details}. The Hungarian Egységes dokumentum lists
    varieties without an explicit role split — we default to `principal`
    for every match. Unmatched names flow into
    `raw/hu/extraction-unknowns.json`."""
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
    return out


def parse_styles(sections: dict[str, str], titles: dict[str, str]) -> list[str]:
    """Detect style tags from the description + additional-conditions
    sections. Hungarian colour adjectives + Tokaji ladder markers."""
    blob_parts = []
    for num, body in sections.items():
        title_low = titles.get(num, "").lower()
        if (
            "bor(ok) leírása" in title_low
            or "bor leírása" in title_low
            or "borok leírása" in title_low
            or "kategóriái" in title_low
            or "kategoriai" in title_low
            or "további" in title_low
            or "tovabbi" in title_low
            or "feltételek" in title_low
            or "feltetelek" in title_low
        ):
            blob_parts.append(body)
    blob = " ".join(blob_parts)
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob, re.I):
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
    region = derive_region(
        {"file_number": wine["fileNumber"]},
        geo_area,
        routed.get("link_to_terroir", ""),
        wine["name"],
    )
    return {
        "country": "hu",
        "source_lang": "hu",
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
        "country": "hu",
        "source_lang": "hu",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        # The curated file_number → region map covers every wine, so even
        # a content-stub keeps its region facet.
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


def _extract_from_html(cache: Path) -> tuple[dict[str, str], dict[str, str], str]:
    html = cache.read_text(encoding="utf-8")
    doc = slice_egyseges_dokumentum(html)
    if doc is None:
        return {}, {}, "no-egyseges-dokumentum-anchor"
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
        print(f"error: {INDEX_IN} missing — run scripts/hu/00_fetch_data.py first",
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

    for w in tqdm(wines, desc="extract-dokumentumok", leave=False):
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
            "country": "hu",
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
    unknowns_path = ROOT / "raw" / "hu" / "extraction-unknowns.json"
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
