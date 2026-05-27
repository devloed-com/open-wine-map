"""Extract structured fields from each cached EUR-Lex documento-unico HTML.

Pipeline stage 02 (it).

For each Italian wine GI in `raw/it/eambrosia/index.json`:
  - if a cached HTML exists at `raw/it/oj-pages/<slug>.html`, parse the
    "DOCUMENTO UNICO" block into numbered sections (the EU 2024 wine GI
    template — sections 1..10 in the Italian-language variant)
  - else emit a stub record so the wine remains searchable
  - run sottozona extraction on the brief geographical-area section and
    emit one child record (`is_sub_denomination=True`) per detected
    sottozona, mirroring the ES subzona + FR DGC pattern
  - harvest Menzioni / Unità Geografiche Aggiuntive into a flat
    `menzioni: []` list on the parent record (no per-MGA polygons in
    v1).

Output: one JSON per wine under `raw/it/disciplinari-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata.

Italian EUR-Lex single-document template (post-2014):

  1. Denominazione/denominazioni             — name
  2. Tipo di indicazione geografica          — kind (DOP / IGP)
  3. Categorie di prodotti vitivinicoli      — category
  4. Descrizione dei vini                    — per wine type
  5. Pratiche di vinificazione               — practices, yields
  6. Zona geografica delimitata              — area
  7. Varietà di uve da vino                  — grape varieties
  8. Descrizione del legame                  — link to terroir
  9. Ulteriori condizioni essenziali         — labelling, packaging
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.it.documento_unico import (  # noqa: E402
    DOC_UNICO_ANCHOR_RE, SECTION_HEADER_RE, SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS, ROLE_BY_KEYWORD, INLINE_ROLE_RE,
    STYLE_MARKERS, COLOUR_BY_KEYWORD,
)
from _lib.it.sottozona import extract_sottozone  # noqa: E402
from _lib.it.menzione import extract_menzioni  # noqa: E402
from _lib.it.region import derive_regione  # noqa: E402
from _lib.it.province import load_comune_regione_map, resolve_gisco_lau  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)
from _lib.grape_lexicon import slugify as _grape_slug  # noqa: E402

INDEX_IN = ROOT / "raw" / "it" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "it" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "it" / "disciplinari-extracted"
INDEX_OUT = OUT_DIR / "_index.json"
GISCO_DIR = ROOT / "raw" / "es" / "gisco"


def strip_tags(html: str) -> str:
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def slice_documento_unico(html: str) -> str | None:
    m = DOC_UNICO_ANCHOR_RE.search(html)
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


# Title-prefixes that disqualify a section from being routed to a given
# role even when the title contains the role keyword. Italian documenti
# unici sometimes name section 3 "Paese cui appartiene la zona
# geografica delimitata" with body "Italia" — that title contains the
# `geo_area` keyword but the body is wrong. Same shape for section 4
# titles that reference "zona geografica" in passing.
_GEO_AREA_TITLE_BLOCKLIST = (
    "paese cui appartiene",
    "tipo di indicazione",
    "classificazione del prodotto",
)


def _match_section_body(
    sections: dict[str, str],
    titles: dict[str, str],
    keywords: tuple[str, ...],
    title_blocklist: tuple[str, ...] = (),
) -> str | None:
    """Keyword-priority match: outer loop on keywords (most specific first),
    inner loop on sections in document order. First keyword that hits a
    non-blocklisted title wins. Falls back to a section's numbered children
    when the parent body is empty (newer EUR-Lex template leaves parent
    headers blank with content in N.1 / N.2 / ...)."""
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


# Grape variety extraction. The Italian documento unico section 7 typically
# lists varieties one per line (with synonyms in parentheses) or as a
# comma-separated list. There may be no role split — Italian
# disciplinari put the full split (principale + complementari) in the
# national disciplinare allegato, which stage 02f handles.

_LINE_SPLIT_RE = re.compile(r"[\n,;]+")

_GRAPE_LINE_DROP = (
    "principal", "principali", "raccomandate", "raccomandato",
    "complementar", "accessori", "autorizzat", "consentit",
    "idoneo", "idonee",
    "varietà", "varieta", "varietà di uve", "uve da vino",
    "vitigni", "vitigno",
    "elencat", "iscritt", "registro nazionale",
    "uvaggio", "uva a bacca",
)


def parse_grapes(section_text: str) -> dict:
    """Parse the section-7 body into {principal, accessory, details}.

    The Italian documento unico typically lists varieties without an
    explicit role split — section 7 is a flat list. We default to
    `principal` for every match. Stage 02f's MASAF parser reclassifies
    to accessory when the national disciplinare has a split.

    Uses `grape_entity.match_variety` for vocabulary-anchored detection
    so unknown tokens flow into `raw/it/extraction-unknowns.json` for
    curator review."""
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

    # Replace " e " conjunctions with commas so the comma-split below
    # handles "Sangiovese e Cabernet" identically to "Sangiovese,
    # Cabernet".
    text = re.sub(r"\s+e\s+", ", ", section_text)

    for line in _LINE_SPLIT_RE.split(text):
        line = line.strip()
        if not line:
            continue

        # Role-marker line — e.g. "principali:" / "complementari:".
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

        # Strip trailing parenthetical annotation (varietal synonyms,
        # colour codes) — but keep the head for grape_entity matching.
        head = re.sub(r"\s*\(.*?\)\s*$", "", line).strip()
        if not head:
            continue

        # Drop role-keyword lines that survived (e.g. "Varietà di uve
        # idonee alla coltivazione:").
        low = head.lower()
        if any(d in low for d in _GRAPE_LINE_DROP) and len(head) < 80:
            continue

        match = match_variety(head)
        if match is None:
            continue
        slug = match.slug
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        out[current_role].append(slug)
        out["details"].append({
            "slug": slug,
            "name": head,
            "role": current_role,
            "colour": match.colour,
        })
    return out


def parse_styles(sections: dict[str, str], titles: dict[str, str]) -> list[str]:
    """Detect style tags from section 4 (description) + section 9 (additional
    conditions). Italian colour adjectives + style markers (spumante,
    frizzante, passito, vin santo, novello, …)."""
    blob_parts = []
    for num, body in sections.items():
        title_low = titles.get(num, "").lower()
        if "descrizione" in title_low or "categori" in title_low or "ulterior" in title_low:
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
                 oj_meta: dict, comune_map: dict) -> dict:
    routed = route_sections(sections, titles)
    grapes = parse_grapes(routed.get("grape_varieties", ""))
    styles = parse_styles(sections, titles)
    regione = derive_regione(
        {"file_number": wine["fileNumber"]},
        routed.get("geo_area", ""),
        routed.get("name", ""),
        comune_map=comune_map,
    )
    geo_area = routed.get("geo_area", "")
    additional = routed.get("additional_conditions", "")
    menzioni = extract_menzioni(geo_area + "\n" + additional, wine["name"])
    return {
        "country": "it",
        "source_lang": "it",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "regione": regione,
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": derive_summary(routed.get("description") or routed.get("geo_area") or ""),
        "sections": sections,
        "section_titles": titles,
        "section_roles": routed,
        "grapes": grapes,
        "styles": styles,
        "geo_area_brief": geo_area,
        "link_to_terroir": routed.get("link_to_terroir", ""),
        "menzioni": menzioni,
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


def build_sottozona_record(parent: dict, sub: dict) -> dict:
    rec = json.loads(json.dumps(parent))
    rec["name"] = sub["name"]
    rec["slug"] = f"{parent['slug']}-{sub['slug']}" if sub["slug"] else parent["slug"]
    rec["is_sub_denomination"] = True
    rec["parent_id_eambrosia"] = parent["id_eambrosia"]
    rec["parent_slug"] = parent["slug"]
    rec["parent_name"] = parent["name"]
    rec["sottozona_communes"] = sub["communes"]
    rec["sottozona_source_pattern"] = sub["source_pattern"]
    rec["geo_area_brief"] = "\n".join(sub["communes"])
    # Sub-denominations don't carry the parent's MGA list — those belong
    # to the parent only.
    rec["menzioni"] = []
    return rec


def build_stub(wine: dict, oj_meta: dict, reason: str) -> dict:
    return {
        "country": "it",
        "source_lang": "it",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "regione": "",
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": "",
        "sections": {},
        "section_titles": {},
        "section_roles": {},
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [],
        "geo_area_brief": "",
        "link_to_terroir": "",
        "menzioni": [],
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
    doc = slice_documento_unico(html)
    if doc is None:
        return {}, {}, "no-documento-unico-anchor"
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
        print(f"error: {INDEX_IN} missing — run scripts/it/00_fetch_data.py first",
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

    gisco_lau = resolve_gisco_lau(GISCO_DIR)
    comune_map = load_comune_regione_map(str(gisco_lau)) if gisco_lau else {}
    if comune_map:
        print(f"[regione] GISCO commune index: {len(comune_map)} names",
              file=sys.stderr)
    else:
        print("[regione] warn: GISCO LAU not found — regione derivation "
              "falls back to province/file-number signals", file=sys.stderr)

    extracted = stubs = parse_failed = sottozone_emitted = 0
    index: dict[str, dict] = {}

    for w in tqdm(wines, desc="extract-pliegos", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        oj_meta = oj_manifest.get(slug, {})
        html_cache = OJ_DIR / f"{slug}.html"
        pdf_cache = OJ_DIR / f"{slug}.pdf"

        if html_cache.exists():
            sections, titles, parse_reason = _extract_from_html(html_cache)
        elif pdf_cache.exists():
            # v1 doesn't ship the IT PDF path. PDF caches come from
            # curator overrides pointing at MASAF / Gazzetta Ufficiale;
            # stage 02f-MASAF will own this in a follow-up. For now,
            # emit a stub.
            sections, titles, parse_reason = {}, {}, "pdf-cache-not-yet-parsed"
        else:
            sections, titles, parse_reason = {}, {}, oj_meta.get("status") or "no-html-cached"

        if parse_reason or not sections:
            record = build_stub(w, oj_meta, parse_reason or "no-sections")
            if parse_reason in (
                "no-html-cached", "no-publication", "fetch-error",
                "not-single-document", "playwright-error",
                "pdf-cache-not-yet-parsed",
            ):
                stubs += 1
            else:
                parse_failed += 1
        else:
            record = build_record(w, sections, titles, oj_meta, comune_map)
            record["source"]["filename"] = html_cache.name
            extracted += 1

        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "country": "it",
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
            "n_menzioni": len(record.get("menzioni") or []),
        }

        # Sottozona child records — same model as ES subzonas / FR DGCs.
        if not record["stub"] and record.get("geo_area_brief"):
            subs = extract_sottozone(record["geo_area_brief"], record["name"])
            for sub in subs:
                child = build_sottozona_record(record, sub)
                child_path = OUT_DIR / f"{child['slug']}.json"
                child_path.write_text(json.dumps(child, ensure_ascii=False, indent=2), encoding="utf-8")
                index[child["slug"]] = {
                    "country": "it",
                    "id_eambrosia": w["giIdentifier"],
                    "file_number": w["fileNumber"],
                    "slug": child["slug"],
                    "name": child["name"],
                    "kind": w["kind"],
                    "filename": child_path.name,
                    "is_sub_denomination": True,
                    "parent_slug": w["slug"],
                    "parent_name": w["name"],
                    "sottozona_source_pattern": sub["source_pattern"],
                    "n_communes": len(sub["communes"]),
                    "stub": False,
                    "stub_reason": "",
                    "sections_present": sorted(record["sections"]),
                    "n_grapes": len(record["grapes"].get("details") or []),
                    "n_menzioni": 0,
                }
                sottozone_emitted += 1

    set_pliego_context(None)
    INDEX_OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    unknowns_path = ROOT / "raw" / "it" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )

    print(
        f"[done] extracted={extracted} stubs={stubs} parse_failed={parse_failed} "
        f"sottozone={sottozone_emitted} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
