"""Build one record per UK wine GI from its cached product specification.

Pipeline stage 02 (gb).

Every registered UK wine GI ships a public specification (stage 01), so
this stage has **no stub path**: all six records come out fully
extracted. That is unique in the corpus — ES/IT/GR/SI/HR/BG/SK/CZ all
need a national-spec fallback tier for their grandfathered names.

The three document layouts are handled by `scripts/_lib/gb/spec.py`;
this stage is the glue: text extraction (`pdftotext -layout` for the five
PDFs, stdlib zip → `word/document.xml` for Sussex's .docx), grape
matching, style derivation and record assembly.

Grape roles: no UK specification splits principal from accessory — each
lists a flat roster of authorised varieties — so every match resolves as
`principal`, the same convention as PT/IT/HR/BG/SK.

v1 models the 6 wine GIs as a **flat corpus**. Sussex and Darnibole sit
geographically inside the English PDO's territory but are first-class
PDOs on the register rather than sub-denominations of it (Darnibole's
own specification makes the point explicitly), so they are siblings —
the way the CZ podoblasti are siblings of Čechy / Morava.

Reads:  raw/gb/gov-uk/index.json + raw/gb/specs/*.{pdf,docx} + manifest.json
Writes: raw/gb/specs-extracted/*.json + _index.json
        raw/gb/extraction-unknowns.json (unmatched variety candidates)
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.gb.geometry import is_approximate  # noqa: E402
from _lib.gb.region import derive_region  # noqa: E402
from _lib.gb.spec import (  # noqa: E402
    COLOUR_BY_KEYWORD,
    PART_STYLE_MARKERS,
    grape_candidates,
    parse_spec,
)
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue,
    match_variety,
    set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "gb" / "gov-uk" / "index.json"
SPECS_DIR = ROOT / "raw" / "gb" / "specs"
SPECS_MANIFEST = SPECS_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "gb" / "specs-extracted"
INDEX_OUT = OUT_DIR / "_index.json"
UNKNOWNS_OUT = ROOT / "raw" / "gb" / "extraction-unknowns.json"

_GRAPE_COLOUR_TO_STYLE = {"blanc": "white", "noir": "red", "gris": "white", "rose": "rose"}


def pdf_text(path: Path) -> str:
    proc = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout or ""


def docx_text(path: Path) -> str:
    """Plain text from a .docx, via the stdlib (the HR pipeline's route).

    `<w:pPr>` paragraph-property blocks are dropped first so numbering
    and style markup can't leak into the text, and `</w:p>` becomes a
    newline so paragraphs survive as lines.
    """
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"<w:pPr>.*?</w:pPr>", "", xml, flags=re.S)
    xml = re.sub(r"</w:p\s*>", "\n", xml)
    xml = re.sub(r"<w:tab\s*/>", " ", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return html_lib.unescape(xml)


def spec_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    return pdf_text(path)


def parse_grapes(section_text: str) -> dict:
    """Resolve the variety roster to lexicon slugs; all `principal`."""
    out: dict[str, list] = {
        "principal": [], "accessory": [], "observation": [], "details": [],
    }
    seen: set[str] = set()
    for cand in grape_candidates(section_text):
        match = match_variety(cand)
        if match is None or match.slug in seen:
            continue
        seen.add(match.slug)
        out["principal"].append(match.slug)
        out["details"].append({
            "slug": match.slug,
            "name": cand,
            "role": "principal",
            "colour": match.colour,
        })
    return out


def parse_styles(parsed: dict, grape_details: list[dict], wine_name: str) -> list[str]:
    """Derive styles from the specification's own wine-category parts.

    The DEFRA 2011 template names its categories as `PART n: STILL WINE`
    / `PART n: QUALITY SPARKLING WINE`; Sussex names them in section 5
    ("Traditional method quality sparkling wine", "Quality still wine").
    Colour comes from the varieties, since none of the UK specifications
    describes its wines by colour in a keyword form.
    """
    found: set[str] = set()
    blob = " ".join(parsed.get("part_titles") or [])
    roles = parsed.get("roles") or {}
    blob_full = f"{blob} {roles.get('description', '')} {wine_name}"
    for pattern, slug in PART_STYLE_MARKERS:
        if slug and pattern.search(blob):
            found.add(slug)
    for kw, colour in COLOUR_BY_KEYWORD.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob_full, re.I):
            found.add(colour)
    for g in grape_details:
        base = _GRAPE_COLOUR_TO_STYLE.get(g.get("colour") or "", "")
        if base:
            found.add(base)
            if base == "red":
                found.add("rose")
    return sorted(found)


def derive_summary(parsed: dict, wine: dict, max_chars: int = 600) -> str:
    roles = parsed.get("roles") or {}
    text = re.sub(r"\s+", " ", roles.get("description") or roles.get("link_to_terroir") or "")
    # The DEFRA parts prefix their narrative with the category name.
    text = re.sub(r"^(Still Wine|Quality Sparkling Wine)\s+", "", text).strip()
    if not text:
        demarcation = (parsed.get("demarcation") or "").strip()
        kind = "PDO" if wine.get("kind") == "DOP" else "PGI"
        return (f"{wine['name']} is a United Kingdom wine {kind}"
                + (f" demarcated to {demarcation.title()}." if demarcation else "."))
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def build_record(wine: dict, parsed: dict, meta: dict) -> dict:
    roles = dict(parsed.get("roles") or {})
    grapes = parse_grapes(roles.get("grape_varieties", ""))
    styles = parse_styles(parsed, grapes["details"], wine["name"])
    demarcation = (parsed.get("demarcation") or "").strip()
    region = derive_region({"file_number": wine["file_number"],
                            "demarcation": demarcation})
    return {
        "country": "gb",
        "source_lang": "en",
        "file_number": wine["file_number"],
        "id_eambrosia": "",
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "parent_slug": "",
        "region": region,
        "demarcation": demarcation,
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": derive_summary(parsed, wine),
        "sections": {},
        "section_titles": {},
        "section_roles": roles,
        "grapes": grapes,
        "styles": styles,
        "geo_area_brief": roles.get("geo_area", ""),
        "link_to_terroir": roles.get("link_to_terroir", ""),
        "max_yields": roles.get("yields", ""),
        "parser_template": parsed.get("template", ""),
        # Darnibole's boundary is reconstructed from its specification's
        # own plan rather than published as data; the panel discloses it.
        "geom_approximate": is_approximate(wine["file_number"]),
        "date_registration": wine.get("date_registration", ""),
        "date_registration_eu": wine.get("date_registration_eu", ""),
        "reason_for_protection": wine.get("reason_for_protection", ""),
        "publications": [],
        "producer_group": {"name": "", "url": ""},
        "source": {
            "kind": "gov-uk-product-specification",
            "filename": meta.get("filename", ""),
            "format": meta.get("format", ""),
            "source_url": meta.get("source_url", ""),
            "final_url": meta.get("final_url", ""),
            "register_url": wine.get("register_url", ""),
            "sha256": meta.get("sha256", ""),
            "bytes": meta.get("bytes", 0),
            "fetched_at": meta.get("fetched_at", ""),
            "license": "Open Government Licence v3.0 — © Crown copyright, DEFRA / GOV.UK",
        },
        "stub": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/gb/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_IN.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]

    manifest: dict = {}
    if SPECS_MANIFEST.exists():
        manifest = json.loads(SPECS_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    extracted = failed = 0

    for w in tqdm(wines, desc="extract-gb-specs", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        meta = manifest.get(slug, {})
        fname = meta.get("filename") or ""
        path = SPECS_DIR / fname if fname else None
        if path is None or not path.exists():
            print(f"[fail] {slug}: no cached specification "
                  "(run scripts/gb/01_fetch_specs.py)", file=sys.stderr)
            failed += 1
            continue
        text = spec_text(path)
        if not text.strip():
            print(f"[fail] {slug}: empty text from {path.name}", file=sys.stderr)
            failed += 1
            continue
        parsed = parse_spec(text)
        record = build_record(w, parsed, meta)
        if not record["grapes"]["principal"]:
            print(f"[warn] {slug}: no varieties resolved from "
                  f"{record['parser_template']}", file=sys.stderr)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        extracted += 1
        index[slug] = {
            "country": "gb",
            "source_lang": "en",
            "file_number": w["file_number"],
            "slug": slug,
            "name": w["name"],
            "kind": w["kind"],
            "region": record["region"],
            "filename": f"{slug}.json",
            "is_sub_denomination": False,
            "parent_slug": "",
            "stub": False,
            "parser_template": record["parser_template"],
            "n_grapes": len(record["grapes"]["details"]),
            "n_styles": len(record["styles"]),
            "link_chars": len(record["link_to_terroir"]),
        }

    set_pliego_context(None)
    INDEX_OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    n_unknowns = flush_unknowns_queue(UNKNOWNS_OUT)
    if n_unknowns:
        print(f"[entity] {n_unknowns} unknown variety candidates → "
              f"{UNKNOWNS_OUT.relative_to(ROOT)}", file=sys.stderr)
    print(f"[done] extracted={extracted} failed={failed} → {OUT_DIR.relative_to(ROOT)}",
          file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
