"""Write a parcellaire carry-forward extract from a release on disk.

    .venv/bin/python scripts/extract_parcellaire_carry_forward.py --release 2026-05-11 --app "Saint-Sardos"
    .venv/bin/python scripts/extract_parcellaire_carry_forward.py --release 2026-05-11 --id-denom 1313

Reads `raw/inao/parcellaire/<release>_delim-parcellaire-aoc-shp.shp`, selects
the rows and writes them unchanged (EPSG:2154, every attribute, INAO's own
coordinates) as a gzipped GeoJSON under scripts/_lib/parcellaire_carry_forward/,
then prints the row count, area and sha256 to put in
scripts/_lib/parcellaire_carry_forward.json. Nothing is simplified or rounded:
a 1 cm rounding already made one Saint-Sardos polygon invalid.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.parcellaire import CARRY_FORWARD_DIR, SHAPEFILE_DIR, slug_for_extract  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", required=True, help="YYYY-MM-DD of the release on disk")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app", help="the shapefile `app` value (whole appellation)")
    g.add_argument("--id-denom", type=int, help="the shapefile `id_denom` value (one denomination)")
    args = ap.parse_args()

    shp = SHAPEFILE_DIR / f"{args.release}_delim-parcellaire-aoc-shp.shp"
    if not shp.exists():
        sys.exit(f"no release on disk: {shp}")
    where = f"app = '{args.app}'" if args.app else f"id_denom = {args.id_denom}"
    gdf = gpd.read_file(shp, where=where).sort_values(["id_denom", "insee"]).reset_index(drop=True)
    if gdf.empty:
        sys.exit(f"no row matches {where} in {shp.name}")
    label = args.app or str(gdf["denom"].iloc[0])
    out = CARRY_FORWARD_DIR / f"{slug_for_extract(label)}-{args.release}.geojson.gz"
    fc = json.loads(gdf.to_json(na="null", drop_id=True))
    fc["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
    fc["name"] = out.name.split(".")[0]
    raw = json.dumps(fc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    CARRY_FORWARD_DIR.mkdir(exist_ok=True)
    with gzip.GzipFile(out, "wb", compresslevel=9, mtime=0) as fh:
        fh.write(raw)
    print(json.dumps({
        "file": out.name, "rows": len(gdf), "area_km2": round(gdf.geometry.union_all().area / 1e6, 2),
        "id_app": sorted({int(v) for v in gdf["id_app"]}), "id_denom": sorted({int(v) for v in gdf["id_denom"]}),
        "sha256": hashlib.sha256(raw).hexdigest(), "valid": bool(gdf.geometry.is_valid.all()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
