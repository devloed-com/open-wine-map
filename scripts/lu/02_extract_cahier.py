"""Extract structured fields from the IVV cahier des charges.

Pipeline stage 02 (lu).

Reads:
  - raw/lu/eambrosia/index.json (1 wine GI)
  - raw/lu/ivv/cahiers/2020-cahier.txt (pdftotext sidecar produced by
    scripts/lu/01_fetch_cahier.py)
  - raw/lu/ivv/manifest.json (cahier provenance)

Writes:
  - raw/lu/cahier-extracted/<slug>.json for the 1 parent
    (Moselle Luxembourgeoise) and 1 per-commune sub-denomination
    (Moselle Luxembourgeoise — <Commune>, 11 modern wine communes).
  - raw/lu/cahier-extracted/_index.json (slug → metadata).
  - raw/lu/extraction-unknowns.json (unmatched grape candidates, if any).

The 11 commune sub-denominations are predicate labels under
Art. 8 / Art. 9 of the labelling règlement (RGD 17-déc-2015), not
separate appellations — but stage 04 renders them as searchable /
filterable records on the map so users can navigate "show me
Wormeldange wines" etc. Each sub-denomination inherits the parent's
varieties + terroir + style list and uses the IVV-parcel-dissolved
polygon for its commune (planted-vineyard precision, far more
honest than the full GISCO admin polygon).

The lieu-dit tier (Art. 10) — named single-vineyard labelling —
needs the IVV `kleinlagen` GeoServer layer (geoportail.lu node
`node_ivv_kleinlagen1`) which is Phase 2. v1 stops at the per-commune
tier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.lu.cahier import (  # noqa: E402
    parse_cahier, iter_variety_canonical_slugs,
)
from _lib.lu.commune import (  # noqa: E402
    extract_communes_from_perimetre, MODERN_TO_HISTORIC, slugify_commune,
)
from _lib.lu.region import derive_region  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

EAMBROSIA_INDEX = ROOT / "raw" / "lu" / "eambrosia" / "index.json"
CAHIER_TXT = ROOT / "raw" / "lu" / "ivv" / "cahiers" / "2020-cahier.txt"
CAHIER_MANIFEST = ROOT / "raw" / "lu" / "ivv" / "manifest.json"
OUT_DIR = ROOT / "raw" / "lu" / "cahier-extracted"
INDEX_OUT = OUT_DIR / "_index.json"
UNKNOWNS_OUT = ROOT / "raw" / "lu" / "extraction-unknowns.json"


def build_grapes(varieties) -> dict:
    """Build the grape-record dict from cahier variety entries. All LU
    varieties are emitted as `principal` (the cahier does not split
    principal/accessory)."""
    out = {"principal": [], "accessory": [], "observation": [], "details": []}
    seen: set[str] = set()
    for variety, _slug_hint in iter_variety_canonical_slugs(varieties):
        match = match_variety(variety.header)
        if match is None or match.slug in seen:
            continue
        seen.add(match.slug)
        out["principal"].append(match.slug)
        out["details"].append({
            "slug": match.slug,
            "name": variety.header,
            "role": "principal",
            "colour": match.colour or variety.colour,
        })
    return out


def derive_styles(wine_descriptions: dict[str, str]) -> list[str]:
    """Derive style slugs from the cahier's wine-type subsections + the
    "mention particulière" body (Crémant / VT / Vin de paille / Vin
    de glace). Each maps to the shared style-taxonomy vocabulary."""
    out: set[str] = set()
    if "blanc" in wine_descriptions:
        out.add("white")
    if "rouge" in wine_descriptions:
        out.add("red")
    if "rose" in wine_descriptions:
        out.add("rose")
    mc = wine_descriptions.get("mousseux-cremant", "").lower()
    if mc:
        out.add("sparkling")
        if "crémant" in mc or "cremant" in mc:
            out.add("sparkling-quality")
            out.add("cremant")
        elif "mousseux" in mc:
            out.add("sparkling-quality")
    mp = wine_descriptions.get("mention-particuliere", "").lower()
    if mp:
        if "vendanges tardives" in mp:
            out.add("late-harvest")
            out.add("vendanges-tardives")
        if "vin de paille" in mp:
            out.add("raisin-wine")
            out.add("vin-de-paille")
        # Vin de glace mentioned but no style slug in shared taxonomy
        # (deferred to a follow-up that also covers DE Eiswein).
    return sorted(out)


def derive_summary(cahier_extract, max_chars: int = 600) -> str:
    """Build a parent summary paragraph from cahier section b (white
    wine description — the canonical "what is this wine" paragraph)."""
    body = (
        cahier_extract.wine_descriptions.get("blanc")
        or cahier_extract.wine_descriptions.get("rouge")
        or cahier_extract.denomination
        or ""
    )
    text = " ".join(body.split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def build_parent_record(
    wine: dict,
    cahier_extract,
    manifest: dict,
    communes: list[str],
) -> dict:
    """Build the 1 parent record (Moselle Luxembourgeoise)."""
    grapes = build_grapes(cahier_extract.varieties)
    styles = derive_styles(cahier_extract.wine_descriptions)
    region = derive_region({"file_number": wine["fileNumber"]})
    cahier_meta = manifest.get("cahier") or {}
    return {
        "country": "lu",
        "source_lang": "fr",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "region": region,
        "categories": [wine["kind"]] if wine.get("kind") else [],
        "summary": derive_summary(cahier_extract),
        "denomination": cahier_extract.denomination,
        "wine_descriptions": cahier_extract.wine_descriptions,
        "yields_text": " ".join(cahier_extract.yields_text.split()),
        "grapes": grapes,
        "styles": styles,
        "geo_area_brief": " ".join(cahier_extract.commune_perimetre_text.split()),
        "communes": communes,
        "link_to_terroir": cahier_extract.lien_au_terroir,
        "autorite_controle": " ".join(cahier_extract.autorite_controle.split()),
        "etiquetage": " ".join(cahier_extract.etiquetage.split()),
        "pratiques_culturales": " ".join(cahier_extract.pratiques_culturales.split()),
        "producer_group": wine["producer_group"],
        "publications": wine["publications"],
        "source": {
            "kind": "ivv-cahier-des-charges",
            "filename": cahier_meta.get("path", ""),
            "source_url": cahier_meta.get("source_url", ""),
            "publisher": cahier_meta.get("publisher", ""),
            "sha256": cahier_meta.get("sha256", ""),
            "bytes": cahier_meta.get("bytes", 0),
            "reglements": cahier_meta.get("reglements", []),
        },
        "stub": False,
    }


def build_sub_record(
    parent_record: dict,
    modern_commune: str,
) -> dict:
    """Build a per-commune sub-denomination record. Inherits parent's
    grapes/styles/terroir; carries the modern commune name + IVV-derived
    planted-vineyard geometry will be resolved in stage 04."""
    commune_slug = slugify_commune(modern_commune)
    sub_slug = f"{parent_record['slug']}-{commune_slug}"
    historic_aliases = MODERN_TO_HISTORIC.get(modern_commune, ())
    name = f"{parent_record['name']} — {modern_commune}"
    return {
        "country": "lu",
        "source_lang": "fr",
        "id_eambrosia": parent_record["id_eambrosia"],
        "file_number": parent_record["file_number"],
        "slug": sub_slug,
        "name": name,
        "kind": parent_record["kind"],
        "is_sub_denomination": True,
        "parent_slug": parent_record["slug"],
        "parent_id_eambrosia": parent_record["id_eambrosia"],
        "parent_name": parent_record["name"],
        "commune": modern_commune,
        "historic_communes": list(historic_aliases),
        "region": parent_record["region"],
        "categories": list(parent_record["categories"]),
        "summary": "",  # Inherits via parent at rendering time
        "grapes": parent_record["grapes"],  # Inherited verbatim
        "styles": list(parent_record["styles"]),
        "geo_area_brief": (
            f"Vignobles plantés de la commune de {modern_commune} "
            "(périmètre viticole AOP-Moselle Luxembourgeoise)."
        ),
        "link_to_terroir": "",  # Inherits via parent at rendering time
        "producer_group": parent_record["producer_group"],
        "publications": parent_record["publications"],
        "source": dict(parent_record["source"]),
        "stub": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[],
                    help="slug substring to filter (repeatable)")
    args = ap.parse_args()

    if not EAMBROSIA_INDEX.exists():
        print(f"error: {EAMBROSIA_INDEX} missing — run scripts/lu/00_fetch_data.py first",
              file=sys.stderr)
        return 1
    if not CAHIER_TXT.exists():
        print(f"error: {CAHIER_TXT} missing — run scripts/lu/01_fetch_cahier.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(EAMBROSIA_INDEX.read_text(encoding="utf-8"))["wines"]
    manifest = json.loads(CAHIER_MANIFEST.read_text(encoding="utf-8")) if CAHIER_MANIFEST.exists() else {}
    cahier_text = CAHIER_TXT.read_text(encoding="utf-8")
    cahier_extract = parse_cahier(cahier_text)
    communes = extract_communes_from_perimetre(cahier_extract.commune_perimetre_text)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    written = 0

    for wine in wines:
        set_pliego_context(wine["slug"])
        parent = build_parent_record(wine, cahier_extract, manifest, communes)
        records = [parent]
        for commune in communes:
            sub = build_sub_record(parent, commune)
            records.append(sub)

        if args.only:
            needles = [s.lower() for s in args.only]
            records = [r for r in records
                       if any(n in r["slug"].lower() for n in needles)]

        for rec in records:
            out_path = OUT_DIR / f"{rec['slug']}.json"
            out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            index[rec["slug"]] = {
                "country": "lu",
                "id_eambrosia": rec["id_eambrosia"],
                "file_number": rec["file_number"],
                "slug": rec["slug"],
                "name": rec["name"],
                "kind": rec["kind"],
                "filename": out_path.name,
                "is_sub_denomination": rec["is_sub_denomination"],
                "parent_slug": rec.get("parent_slug", ""),
                "commune": rec.get("commune", ""),
                "stub": rec["stub"],
                "n_grapes": len(rec["grapes"].get("details") or []),
                "n_styles": len(rec.get("styles") or []),
            }
            written += 1

    set_pliego_context(None)
    INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    n_unknowns = flush_unknowns_queue(UNKNOWNS_OUT)
    if n_unknowns:
        print(f"[entity] {n_unknowns} unknown variety candidates → "
              f"{UNKNOWNS_OUT.relative_to(ROOT)}", file=sys.stderr)

    print(
        f"[done] records_written={written} (1 parent + {len(communes)} sub-denoms) "
        f"→ {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
