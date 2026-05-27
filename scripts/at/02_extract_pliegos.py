"""Extract structured fields from each cached EUR-Lex Einziges-Dokument HTML.

Pipeline stage 02 (at).

For each Austrian wine GI in `raw/at/eambrosia/index.json`:
  - if a cached HTML exists at `raw/at/oj-pages/<slug>.html`, parse the
    "EINZIGES DOKUMENT" block into numbered sections (the EU wine GI
    template — sections 1..9 / 1..10 in the German-language variant)
  - else emit a stub record so the wine remains searchable

Output: one JSON per wine under `raw/at/dokumente-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata.

The 32 Austrian wine GIs are a flat corpus — no DAC sub-denominations
are modelled in v1 (unlike FR DGCs / ES subzonas / IT sottozone). Most
Austrian DACs use ripeness or single-vineyard tiers rather than
geographic sub-areas, and the single document does not enumerate them.
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
from _lib.at.einziges_dokument import (  # noqa: E402
    DOC_ANCHOR_RE, SECTION_HEADER_RE, SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS, ROLE_BY_KEYWORD, INLINE_ROLE_RE,
    STYLE_MARKERS, COLOUR_BY_KEYWORD, _GEO_AREA_TITLE_BLOCKLIST,
)
from _lib.at.region import derive_bundesland  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "at" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "at" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "at" / "dokumente-extracted"
INDEX_OUT = OUT_DIR / "_index.json"


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_einziges_dokument(html: str) -> str | None:
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
    numbered children when the parent body is empty (newer EUR-Lex
    template leaves parent headers blank)."""
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


_GRAPE_LINE_DROP = (
    "haupt", "wichtigste", "empfohlen", "zugelassen", "ergänzend", "erganzend",
    "keltertraubensorte", "keltertraubensorten", "rebsorte", "rebsorten",
    "traubensorte", "weiße sorten", "weisse sorten", "rote sorten",
    "qualitätswein", "qualitatswein",
)

# The German section-7 body lists one variety per line as
# `Offizieller Name - Synonym1, Synonym2, …` (e.g. `Grauer Burgunder -
# Grauburgunder, Pinot Gris, Ruländer`). The first segment before the
# dash is the canonical Austrian name; the rest are synonyms.
_DASH_SPLIT_RE = re.compile(r"\s+[-–—]\s+")


def _line_candidates(line: str) -> list[str]:
    """Variety-name candidates for one section-7 line, canonical name
    first then its synonyms. match_variety is tried on each in order."""
    parts = _DASH_SPLIT_RE.split(line, maxsplit=1)
    head = parts[0]
    syn_blob = parts[1] if len(parts) > 1 else ""
    out: list[str] = []
    for c in [head, *syn_blob.split(",")]:
        c = re.sub(r"\s*\(.*?\)\s*", " ", c).strip()
        if c and c not in out:
            out.append(c)
    return out


def parse_grapes(section_text: str) -> dict:
    """Parse the section-7 body into {principal, accessory, details}.

    The German Einziges Dokument lists varieties one per line without an
    explicit role split — section 7 is a flat list. We default to
    `principal` for every match. Each line is `Name - Synonym, …`;
    `grape_entity.match_variety` is tried on the canonical name then the
    synonyms, so a known synonym still resolves the variety. Unmatched
    names flow into `raw/at/extraction-unknowns.json` for curator review."""
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

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m_role = INLINE_ROLE_RE.match(line)
        if m_role:
            kw = m_role.group(1).lower()
            for k, v in ROLE_BY_KEYWORD.items():
                if kw.startswith(k):
                    current_role = v
                    break
            tail = line[m_role.end():].strip()
            if not tail:
                continue
            line = tail

        low = line.lower()
        if any(d in low for d in _GRAPE_LINE_DROP) and len(line) < 40:
            continue

        for cand in _line_candidates(line):
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
                "name": _DASH_SPLIT_RE.split(line, maxsplit=1)[0].strip(),
                "role": current_role,
                "colour": match.colour,
            })
            break
    return out


def parse_styles(sections: dict[str, str], titles: dict[str, str]) -> list[str]:
    """Detect style tags from the description + additional-conditions
    sections. German colour adjectives + Prädikat / Schaumwein markers."""
    blob_parts = []
    for num, body in sections.items():
        title_low = titles.get(num, "").lower()
        if (
            "beschreibung" in title_low
            or "kategorie" in title_low
            or "weiter" in title_low
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
    bundesland = derive_bundesland(
        {"file_number": wine["fileNumber"]},
        geo_area,
        routed.get("link_to_terroir", ""),
        wine["name"],
    )
    return {
        "country": "at",
        "source_lang": "de",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "bundesland": bundesland,
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
        "country": "at",
        "source_lang": "de",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        # The curated file_number → Bundesland map covers every wine,
        # so even a content-stub keeps its region facet.
        "bundesland": derive_bundesland({"file_number": wine["fileNumber"]}),
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
    doc = slice_einziges_dokument(html)
    if doc is None:
        return {}, {}, "no-einziges-dokument-anchor"
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
        print(f"error: {INDEX_IN} missing — run scripts/at/00_fetch_data.py first",
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

    for w in tqdm(wines, desc="extract-dokumente", leave=False):
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
            "country": "at",
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
    unknowns_path = ROOT / "raw" / "at" / "extraction-unknowns.json"
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
