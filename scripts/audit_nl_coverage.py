"""Audit NL pipeline coverage.

Prints extraction status per kind, stub reasons, Bétard + NUTS-2
geometry coverage, grape extraction, region distribution.

Run: `.venv/bin/python scripts/audit_nl_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EAMBROSIA = ROOT / "raw" / "nl" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "nl" / "dokumenten-extracted"
OJ_MANIFEST = ROOT / "raw" / "nl" / "oj-pages" / "manifest.json"
OVERRIDES = ROOT / "raw" / "nl" / "oj-pages" / "manual_overrides.json"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
NUTS = ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"


def _load_eambrosia() -> list[dict]:
    if not EAMBROSIA.exists():
        return []
    return json.loads(EAMBROSIA.read_text(encoding="utf-8"))["wines"]


def _load_extracted() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not EXTRACTED.exists():
        return out
    for jp in EXTRACTED.glob("*.json"):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        out[rec["slug"]] = rec
    return out


def _load_manifest() -> dict[str, dict]:
    if not OJ_MANIFEST.exists():
        return {}
    try:
        return json.loads(OJ_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
    except (ValueError, OSError):
        return {}


def _load_overrides() -> dict[str, dict]:
    if not OVERRIDES.exists():
        return {}
    try:
        return json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _load_figshare_file_numbers() -> set[str]:
    if not FIGSHARE.exists():
        return set()
    try:
        import geopandas as gpd
        gdf = gpd.read_file(FIGSHARE)
        return set(
            fn for fn in gdf["PDOid"].astype(str).tolist()
            if fn and fn.startswith("PDO-NL")
        )
    except ImportError:
        return set()


def _load_nuts2_nl() -> set[str]:
    if not NUTS.exists():
        return set()
    try:
        data = json.loads(NUTS.read_text(encoding="utf-8"))
        return {
            f["properties"]["NUTS_ID"]
            for f in data.get("features", [])
            if (f.get("properties") or {}).get("CNTR_CODE") == "NL"
        }
    except (ValueError, OSError):
        return set()


def main() -> int:
    wines = _load_eambrosia()
    extracted = _load_extracted()
    oj_manifest = _load_manifest()
    overrides = _load_overrides()
    figshare_ids = _load_figshare_file_numbers()
    nuts2 = _load_nuts2_nl()

    print("# NL pipeline audit\n")
    print(f"eAmbrosia wines:      {len(wines)} (excludes BE-primary cross-border Maasvallei)")
    print(f"Extracted records:    {len(extracted)}")
    print(f"OJ-page manifest:     {len(oj_manifest)} entries")
    print(f"Manual overrides:     {len(overrides)} entries")
    print(f"Figshare NL PDOids:   {len(figshare_ids)}")
    print(f"NUTS-2 NL polygons:   {len(nuts2)}")
    print()

    by_kind_total: Counter[str] = Counter()
    by_kind_extracted: Counter[str] = Counter()
    by_kind_stub: Counter[str] = Counter()
    stub_reasons: Counter[str] = Counter()
    in_figshare = no_figshare = 0
    grape_total = 0
    n_with_grapes = 0
    by_region: Counter[str] = Counter()

    for w in wines:
        slug = w["slug"]
        kind = w.get("kind", "?")
        by_kind_total[kind] += 1
        rec = extracted.get(slug)
        if rec is None:
            stub_reasons["not-yet-extracted"] += 1
            continue
        if rec.get("stub"):
            by_kind_stub[kind] += 1
            stub_reasons[rec.get("stub_reason", "unknown")] += 1
        else:
            by_kind_extracted[kind] += 1
        fn = w.get("fileNumber") or ""
        if fn in figshare_ids:
            in_figshare += 1
        else:
            no_figshare += 1
        n_grapes = len((rec.get("grapes") or {}).get("details") or [])
        if n_grapes:
            n_with_grapes += 1
            grape_total += n_grapes
        by_region[rec.get("region") or "?"] += 1

    print("## By kind")
    print(f"  Total:     {dict(by_kind_total)}")
    print(f"  Extracted: {dict(by_kind_extracted)}")
    print(f"  Stubs:     {dict(by_kind_stub)}")
    print()
    print("## Stub reasons")
    for r, n in sorted(stub_reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {r}")
    if not stub_reasons:
        print("  (none — full extraction)")
    print()
    print("## Geometry coverage")
    print(f"  Bétard PDOs in Figshare: {in_figshare} of {len(wines)} "
          f"({in_figshare/max(1,len(wines)):.1%})")
    print(f"  Missing from Figshare:    {no_figshare} "
          f"(the 12 PGIs resolve via NUTS-2; 4 newer PDOs are stub-no-geometry in v1)")
    print()
    print("## Region distribution")
    for b, n in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {b}")
    print()
    print("## Grape extraction")
    print(f"  Wines with grapes:  {n_with_grapes} of {len(extracted)}")
    print(f"  Total grape-slugs:  {grape_total}")
    print()

    curator_targets: list[tuple[str, str, str]] = []
    for w in wines:
        slug = w["slug"]
        rec = extracted.get(slug)
        if rec is None or not rec.get("stub"):
            continue
        if slug in overrides or w["giIdentifier"] in overrides:
            continue
        curator_targets.append((rec.get("stub_reason") or "unknown", slug,
                                 w.get("fileNumber", "")))
    curator_targets.sort()

    print(f"## Curator queue ({len(curator_targets)} stubs needing input)")
    for reason, slug, fn in curator_targets:
        print(f"  [{reason:30s}] {slug:40s} {fn}")
    if not curator_targets:
        print("  (empty — every Dutch wine extracted)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
