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

A release can also drop rows that nothing retires — Saint-Sardos vanished
from the 2026-09-28 release with no act behind it, and the DGC Languedoc
Montpeyroux's rows went before its successor's parcels existed. Those rows
are carried forward from the last release that had them: a checked-in
extract per entry of `parcellaire_carry_forward.json`, appended to the
current table by `build_aoc_polygons` and by the coverage index alike, and
reported STALE the moment the current release carries them again.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parent.parent.parent
SHAPEFILE_DIR = ROOT / "raw" / "inao" / "parcellaire"
PATCH_CSV = Path(__file__).resolve().parent / "inao-shapefile-patch.csv"
CARRY_FORWARD_PATH = Path(__file__).resolve().parent / "parcellaire_carry_forward.json"
CARRY_FORWARD_DIR = Path(__file__).resolve().parent / "parcellaire_carry_forward"
EXTRACT_EPSG = 2154
CACHE_GEOJSON = ROOT / "wiki" / "map-data" / "aoc-parcels.geojson"
CACHE_DENOM_GEOJSON = ROOT / "wiki" / "map-data" / "aoc-parcels-denom.geojson"
# What the two caches were built from: the release and the carry-forward
# entries. A cache built from another release, or before an entry was added,
# is rebuilt — a stale cache would silently drop the carried rows.
CACHE_META = ROOT / "wiki" / "map-data" / "aoc-parcels.meta.json"


def resolve_shapefile() -> Path | None:
    """Pick the .shp for the most recent INAO release present in
    SHAPEFILE_DIR. INAO ships the file as
    `<YYYY-MM-DD>_delim-parcellaire-aoc-shp.shp`, so a lexicographic sort
    of any matching filenames yields newest-last. Returns None when no
    matching shapefile is on disk."""
    if not SHAPEFILE_DIR.is_dir():
        return None
    matches = sorted(SHAPEFILE_DIR.glob("*delim-parcellaire-aoc-shp.shp"))
    return matches[-1] if matches else None


def apply_patches(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Apply field-level patches and repair invalid geometries.

    Mirrors `apply_inao_patch.py` in wine-wiki — see that file's docstring
    and `inao-shapefile-patch.csv` for the documented bug list.
    """
    if not PATCH_CSV.exists():
        print(f"warn: no patch CSV at {PATCH_CSV}", file=sys.stderr)
        return gdf

    with PATCH_CSV.open(encoding="utf-8") as fh:
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


# ------------------------------------------------------------ carry-forward
@dataclass
class CarrySpec:
    """One entry of parcellaire_carry_forward.json."""

    match: dict
    label: str
    release: str
    file: Path
    rows: int
    reason: str
    source: str
    verified: str
    id_app: int | None = None
    id_denom: list[int] | None = None

    @property
    def key(self) -> str:
        k, v = next(iter(self.match.items()))
        return f"{k}={v}"


def slug_for_extract(label: str) -> str:
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def load_carry_forward(path: Path = CARRY_FORWARD_PATH) -> list[CarrySpec]:
    """The checked-in entries, validated: one `match` key (`app` or
    `id_denom`), an extract file that exists, a reason, a source and a
    verification date."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[CarrySpec] = []
    for i, e in enumerate(data.get("entries") or []):
        match = e.get("match") or {}
        if set(match) not in ({"app"}, {"id_denom"}):
            raise ValueError(f"{path.name} entry {i}: `match` must be {{'app': …}} or {{'id_denom': …}}")
        for k in ("label", "release", "file", "rows", "reason", "source", "verified"):
            if not e.get(k):
                raise ValueError(f"{path.name} entry {i}: `{k}` is required")
        f = CARRY_FORWARD_DIR / e["file"]
        if not f.exists():
            raise FileNotFoundError(f"{path.name} entry {i}: {f} missing")
        out.append(CarrySpec(
            match=match, label=e["label"], release=e["release"], file=f, rows=int(e["rows"]),
            reason=e["reason"], source=e["source"], verified=e["verified"],
            id_app=e.get("id_app"), id_denom=e.get("id_denom"),
        ))
    return out


def carry_matches(df, match: dict):
    """Boolean mask of the rows of `df` an entry's `match` selects."""
    if "app" in match:
        return df["app"] == match["app"]
    return df["id_denom"].astype(int) == int(match["id_denom"])


def read_carry_extract(spec: CarrySpec, geometry: bool = True, crs=None):
    """The entry's rows, as a GeoDataFrame in `crs` (default EPSG:2154) or,
    without geometry, a DataFrame of the attributes."""
    raw = gzip.decompress(spec.file.read_bytes())
    gdf = gpd.read_file(io.BytesIO(raw))
    gdf = gdf.set_crs(EXTRACT_EPSG, allow_override=True)
    if len(gdf) != spec.rows:
        raise ValueError(f"{spec.file.name}: {len(gdf)} rows, the table says {spec.rows}")
    if not carry_matches(gdf, spec.match).all():
        raise ValueError(f"{spec.file.name}: a row does not match {spec.key}")
    if not geometry:
        return pd.DataFrame(gdf.drop(columns="geometry"))
    if crs is not None and not gdf.crs.equals(crs):
        # the shapefile's WKT names the same Lambert-93 (IGNF LAMB93) without
        # an EPSG code; a reprojection between the two is the identity
        name = str(getattr(crs, "name", crs))
        if "Lambert" in name or "LAMB93" in name or getattr(crs, "to_epsg", lambda: None)() == EXTRACT_EPSG:
            gdf = gdf.set_crs(crs, allow_override=True)
        else:
            gdf = gdf.to_crs(crs)
    return gdf


def carry_forward_frames(current, geometry: bool = True, specs: list[CarrySpec] | None = None):
    """For each entry: the extract to append when the current release has no
    matching row (`APPLIED`), or nothing when it has (`STALE`). Returns
    (frames, states) with states = [(spec, state, n_rows)]."""
    specs = load_carry_forward() if specs is None else specs
    frames: list = []
    states: list[tuple[CarrySpec, str, int]] = []
    for spec in specs:
        present = int(carry_matches(current, spec.match).sum()) if len(current) else 0
        if present:
            states.append((spec, "STALE", present))
            continue
        frame = read_carry_extract(spec, geometry=geometry, crs=getattr(current, "crs", None))
        missing = [c for c in current.columns if c not in frame.columns]
        if missing:
            raise ValueError(f"{spec.file.name}: columns {missing} absent from the extract")
        frames.append(frame[list(current.columns)])
        states.append((spec, "APPLIED", len(frame)))
    return frames, states


def log_carry_forward(states, release: str) -> None:
    for spec, state, n in states:
        if state == "APPLIED":
            print(
                f"[parcellaire] carried forward: {spec.label} — {n} row(s) of the {spec.release} "
                f"release; the {release} release carries none (see parcellaire_carry_forward.json)",
                file=sys.stderr,
            )
        else:
            print(
                f"[parcellaire] STALE carry-forward: {spec.label} — the {release} release carries "
                f"{n} matching row(s); nothing appended, drop the entry",
                file=sys.stderr,
            )


def release_of(shapefile: Path) -> str:
    return shapefile.stem[:10]


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
    shapefile = resolve_shapefile()
    meta = {
        "shapefile": shapefile.name if shapefile else "",
        "carry": [[sp.key, sp.release, sp.rows] for sp in load_carry_forward()],
    }
    cached_meta = json.loads(CACHE_META.read_text(encoding="utf-8")) if CACHE_META.exists() else None
    if not force and CACHE_GEOJSON.exists() and CACHE_DENOM_GEOJSON.exists() and cached_meta != meta:
        print(
            f"  parcel caches were built from {cached_meta} — current source is {meta}; rebuilding",
            file=sys.stderr,
        )
        force = True
    if not force and CACHE_GEOJSON.exists() and CACHE_DENOM_GEOJSON.exists():
        print(
            f"  using caches {CACHE_GEOJSON.relative_to(ROOT)} + "
            f"{CACHE_DENOM_GEOJSON.relative_to(ROOT)}",
            file=sys.stderr,
        )
        fc_app = json.loads(CACHE_GEOJSON.read_text(encoding="utf-8"))
        fc_denom = json.loads(CACHE_DENOM_GEOJSON.read_text(encoding="utf-8"))
        by_app = {f["properties"]["app"]: f for f in fc_app["features"]}
        by_denom = {str(f["properties"]["id_denom"]): f for f in fc_denom["features"]}
        return by_app, by_denom

    if shapefile is None:
        print(
            f"  no shapefile in {SHAPEFILE_DIR.relative_to(ROOT)}/ — "
            f"unzip raw/inao/parcellaire.zip into that directory.",
            file=sys.stderr,
        )
        return {}, {}

    print(f"  loading {shapefile.relative_to(ROOT)} (~600 MB)…", file=sys.stderr)
    gdf = gpd.read_file(shapefile)
    gdf = apply_patches(gdf)
    frames, states = carry_forward_frames(gdf, geometry=True)
    log_carry_forward(states, release_of(shapefile))
    if frames:
        gdf = gpd.GeoDataFrame(
            pd.concat([gdf, *frames], ignore_index=True), geometry="geometry", crs=gdf.crs,
        )

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
    CACHE_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"  cached → {CACHE_GEOJSON.relative_to(ROOT)} + "
        f"{CACHE_DENOM_GEOJSON.relative_to(ROOT)}",
        file=sys.stderr,
    )

    fc_app = json.loads(CACHE_GEOJSON.read_text(encoding="utf-8"))
    fc_denom = json.loads(CACHE_DENOM_GEOJSON.read_text(encoding="utf-8"))
    by_app = {f["properties"]["app"]: f for f in fc_app["features"]}
    by_denom = {str(f["properties"]["id_denom"]): f for f in fc_denom["features"]}
    return by_app, by_denom
