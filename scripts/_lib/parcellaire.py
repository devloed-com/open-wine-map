"""Loader for the INAO viticole parcel shapefile.

Source: data.gouv.fr/datasets/delimitation-parcellaire-des-aoc-viticoles-de-linao
Distributed by INAO; rows are (AOC × commune × parcel-set) features in
Lambert-93 (EPSG:2154). One AOC like "Côtes du Rhône" spans hundreds of
rows; each row carries an `app` (canonical AOC name) field that we group
on to produce one polygon per appellation.

The raw shapefile has a few documented data-quality bugs (cross-département
INSEE codes, the literal string "ok" in `insee2011`, comma-separated
`nomcom` values, two invalid geometries). We apply the patches catalogued
in `inao-shapefile-patch.csv` — copied verbatim from wine-wiki, which
maintained them — before unioning.

Output is cached to `wiki/map-data/aoc-parcels.geojson` so subsequent
stage-04 runs skip the 30-second load + reproject + union pass.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import geopandas as gpd
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parent.parent.parent
SHAPEFILE = ROOT / "raw" / "inao" / "parcellaire" / "2026-04-13_delim-parcellaire-aoc-shp.shp"
PATCH_CSV = Path(__file__).resolve().parent / "inao-shapefile-patch.csv"
CACHE_GEOJSON = ROOT / "wiki" / "map-data" / "aoc-parcels.geojson"
CACHE_DENOM_GEOJSON = ROOT / "wiki" / "map-data" / "aoc-parcels-denom.geojson"


def apply_patches(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Apply field-level patches and repair invalid geometries.

    Mirrors `apply_inao_patch.py` in wine-wiki — see that file's docstring
    and `inao-shapefile-patch.csv` for the documented bug list.
    """
    if not PATCH_CSV.exists():
        print(f"warn: no patch CSV at {PATCH_CSV}", file=sys.stderr)
        return gdf

    with PATCH_CSV.open() as fh:
        patches = list(csv.DictReader(fh))

    n = 0
    for p in patches:
        field = p["field"]
        mask = (
            (gdf["app"] == p["app"])
            & (gdf["id_denom"] == int(p["id_denom"]))
            & (gdf["insee"] == p["insee"])
            & (gdf[field] == p["current_value"])
            & (gdf["nomcom"] == p["nomcom"])
        )
        matched = int(mask.sum())
        if matched == 0:
            # Patch already applied or row missing — log and skip rather than
            # fail; keeps the pipeline resilient if INAO later fixes the
            # source data themselves.
            print(
                f"  patch skipped: {p['app']}/{p['id_denom']}/{field}={p['current_value']!r} not found",
                file=sys.stderr,
            )
            continue
        if matched > 1:
            raise SystemExit(
                f"expected 1 match for {p['app']}/{p['id_denom']}/{field}={p['current_value']}, got {matched}"
            )
        gdf.loc[mask, field] = p["proposed_value"]
        n += 1
    print(f"  applied {n} field-level patches", file=sys.stderr)

    invalid = ~gdf.geometry.is_valid
    n_invalid = int(invalid.sum())
    if n_invalid:
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].apply(make_valid)
        print(f"  repaired {n_invalid} invalid geometries", file=sys.stderr)
    return gdf


def build_aoc_polygons(force: bool = False) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (by_app, by_denom) parcel polygon caches.

    `by_app` is `{app_name: GeoJSON-Feature}` keyed on the INAO `app`
    field — the parent appellation polygon (unions every DGC it carries).
    `by_denom` is `{id_denom: GeoJSON-Feature}` keyed on the INAO
    `id_denom` field — DGC-precise polygons. The same id_denom that
    matches `app` is the parent's row; DGCs each get their own.

    Reads from cached geojsons when available; (re)builds from the
    shapefile when either is missing or `force=True`. Geometries are
    unioned per group and reprojected to WGS84.
    """
    if not force and CACHE_GEOJSON.exists() and CACHE_DENOM_GEOJSON.exists():
        print(
            f"  using caches {CACHE_GEOJSON.relative_to(ROOT)} + "
            f"{CACHE_DENOM_GEOJSON.relative_to(ROOT)}",
            file=sys.stderr,
        )
        fc_app = json.loads(CACHE_GEOJSON.read_text())
        fc_denom = json.loads(CACHE_DENOM_GEOJSON.read_text())
        by_app = {f["properties"]["app"]: f for f in fc_app["features"]}
        by_denom = {str(f["properties"]["id_denom"]): f for f in fc_denom["features"]}
        return by_app, by_denom

    if not SHAPEFILE.exists():
        print(f"  no shapefile at {SHAPEFILE.relative_to(ROOT)}", file=sys.stderr)
        return {}, {}

    print(f"  loading {SHAPEFILE.relative_to(ROOT)} (~600 MB)…", file=sys.stderr)
    gdf = gpd.read_file(SHAPEFILE)
    gdf = apply_patches(gdf)

    print(f"  unioning {len(gdf)} parcels into AOC polygons…", file=sys.stderr)
    by_app_gdf = gdf.dissolve(by="app", as_index=False)[["app", "geometry"]]
    by_app_gdf = by_app_gdf.to_crs(epsg=4326)
    print(f"  → {len(by_app_gdf)} AOC polygons (reprojected to WGS84)", file=sys.stderr)

    print(f"  unioning {len(gdf)} parcels into denomination polygons…", file=sys.stderr)
    # `id_denom` is unique per (appellation, denomination) — dissolve by it
    # to get DGC-precise polygons. Carry `app` along so consumers can map a
    # denom polygon back to its parent appellation. `denom` (the textual
    # denomination name from the shapefile) is also surfaced so we can
    # spot-check: "Muscadet Sèvre et Maine Clisson" should appear there.
    by_denom_gdf = gdf.dissolve(by="id_denom", as_index=False)[
        ["id_denom", "app", "denom", "geometry"]
    ]
    by_denom_gdf = by_denom_gdf.to_crs(epsg=4326)
    print(f"  → {len(by_denom_gdf)} denomination polygons (reprojected to WGS84)", file=sys.stderr)

    CACHE_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_GEOJSON.exists():
        CACHE_GEOJSON.unlink()
    by_app_gdf.to_file(CACHE_GEOJSON, driver="GeoJSON")
    if CACHE_DENOM_GEOJSON.exists():
        CACHE_DENOM_GEOJSON.unlink()
    by_denom_gdf.to_file(CACHE_DENOM_GEOJSON, driver="GeoJSON")
    print(
        f"  cached → {CACHE_GEOJSON.relative_to(ROOT)} + "
        f"{CACHE_DENOM_GEOJSON.relative_to(ROOT)}",
        file=sys.stderr,
    )

    fc_app = json.loads(CACHE_GEOJSON.read_text())
    fc_denom = json.loads(CACHE_DENOM_GEOJSON.read_text())
    by_app = {f["properties"]["app"]: f for f in fc_app["features"]}
    by_denom = {str(f["properties"]["id_denom"]): f for f in fc_denom["features"]}
    return by_app, by_denom
