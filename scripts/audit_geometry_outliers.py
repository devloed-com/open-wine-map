#!/usr/bin/env python3
"""Audit — detached polygon parts ("outliers") in the resolved appellation map.

Reads the final `wiki/map-data/appellations.geojson` and flags MultiPolygon
appellations with parts detached far from the main body. A detached part is
the symptom of one of three things:

  1. a mis-attributed fragment in upstream geometry data (the Bétard 2022
     `EU_PDO.gpkg`) — e.g. Garda DOP carrying a 29 km² sliver of Piedmont;
  2. a same-name commune-union collision in our own resolvers — e.g. PT Lagoa
     unioning the Algarve concelho *and* the Azores concelho of the same name;
  3. a genuinely disjoint appellation — an archipelago, or a multi-region DO.

Every finding is cross-referenced against
`scripts/_lib/geometry_outlier_overrides.json` and lands in one bucket:

  CONFIRMED       — a clip override is active and still matches a real spurious
                    part in the SOURCE data: the fix is verified, working.
  PENDING-REBUILD — a clip override exists, but the spurious part is still in
                    appellations.geojson — stage 04 has not been re-run.
  STALE           — a clip override no longer matches the source data: upstream
                    drifted, or was fixed. Re-verify the override. (exit != 0)
  ACCEPTED        — slug whitelisted: the detached parts are legitimate.
  UNREVIEWED      — a detached part on the map with no override. Needs review.

Nothing is hidden: a CONFIRMED clip is re-derived against the source on every
run and stays in the report, so an applied fix is always visible.

The geojson is streamed feature-by-feature (it is ~1.7 GB) so the audit runs
in tens of MB of RAM, and stdout is line-buffered so a partial run still shows
its progress — an audit must never fail silently.

Exit code is non-zero when any STALE override exists. With --strict it also
fails on UNREVIEWED findings.

Usage:
  uv run scripts/audit_geometry_outliers.py
  uv run scripts/audit_geometry_outliers.py --geojson wiki/map-data/appellations-villages.geojson
  uv run scripts/audit_geometry_outliers.py --gap-km 40 --strict
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.geometry_overrides import GeometryOverrides  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WGS84 = "EPSG:4326"
EQ_AREA = "EPSG:3035"
DEFAULT_GEOJSON = ROOT / "wiki" / "map-data" / "appellations.geojson"
DEFAULT_FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
DEFAULT_PANEL_DIR = ROOT / "wiki" / "data" / "d" / "en"
DEFAULT_NUTS_LAYERS = (
    ROOT / "raw" / "gr" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_3.geojson",
    ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson",
)

_to_3035 = Transformer.from_crs(WGS84, EQ_AREA, always_xy=True).transform
_to_4326 = Transformer.from_crs(EQ_AREA, WGS84, always_xy=True).transform


def _display(path: Path) -> str:
    """Repo-relative when the file is inside the repo, absolute otherwise —
    ``--geojson`` may point at a snapshot outside the checkout."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)



def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Outlier:
    """One detached part of an appellation polygon. `lat`/`lon` is the part
    centroid (matched against override signatures); `rep_lat`/`rep_lon` is a
    point guaranteed inside the part (used for the overlap signal)."""

    __slots__ = ("area_km2", "gap_km", "frac", "lat", "lon",
                 "rep_lat", "rep_lon", "overlaps")

    def __init__(self, area_km2, gap_km, frac, lat, lon, rep_lat, rep_lon):
        self.area_km2 = area_km2
        self.gap_km = gap_km
        self.frac = frac
        self.lat = lat
        self.lon = lon
        self.rep_lat = rep_lat
        self.rep_lon = rep_lon
        self.overlaps: list[str] = []

    @property
    def severity(self) -> float:
        return self.area_km2 * self.gap_km


def _clusters(parts: list[BaseGeometry], gap_km: float) -> np.ndarray:
    """Label every part with its cluster: the connected components of the
    graph that links two parts no more than `gap_km` apart.

    Each part is queried once, with its envelope widened by the gap, and
    the exact distance is only computed for candidates not yet labelled —
    within 25 km almost every parcel of a parcellaire union is near every
    other, so an all-pairs `dwithin` query would be quadratic."""
    gap_m = gap_km * 1000.0
    tree = STRtree(parts)
    geoms = tree.geometries
    label = np.full(len(parts), -1, dtype=np.int64)
    for seed in range(len(parts)):
        if label[seed] >= 0:
            continue
        label[seed] = seed
        stack = [seed]
        while stack:
            i = stack.pop()
            minx, miny, maxx, maxy = parts[i].bounds
            cand = tree.query(box(minx - gap_m, miny - gap_m, maxx + gap_m, maxy + gap_m))
            cand = cand[label[cand] < 0]
            if cand.size == 0:
                continue
            near = cand[shapely.distance(geoms[cand], parts[i]) <= gap_m]
            label[near] = seed
            stack.extend(near.tolist())
    return label


def detect_outliers(
    geom_3035: BaseGeometry, gap_km: float, area_frac: float
) -> list[Outlier]:
    """Return the detached parts of a MultiPolygon.

    Parts no more than `gap_km` apart belong to one cluster, transitively.
    The main body is the cluster holding the most area; every part outside
    it lies more than `gap_km` from the body, and is an outlier when its
    cluster holds less than `area_frac` of the total: a cluster that large
    is a genuine second lobe, however many parcels it is drawn in.

    Proximity, not area rank: an area-rank body (the largest parts up to
    95% of the total) swallowed a large detached part, and Saale-Unstrut's
    Werderaner Wachtelberg (117 km², 87 km out) went untested. Seeding by
    the largest cluster rather than the largest part matters too — skipping
    parts with no neighbour made the lone 1,207 km² Sevilla body of Los
    Palacios lose to the two touching Navarra parts of its homonym leak,
    and Crémant de Bourgogne's single largest parcel sits in the Yonne
    lobe, not in the lobe that holds 85% of its area."""
    if geom_3035.geom_type != "MultiPolygon":
        return []
    parts = sorted(geom_3035.geoms, key=lambda p: p.area, reverse=True)
    if len(parts) < 2:
        return []
    total = sum(p.area for p in parts)
    if total <= 0:
        return []
    label = _clusters(parts, gap_km)
    cluster_area: dict[int, float] = {}
    for lab, p in zip(label.tolist(), parts):
        cluster_area[lab] = cluster_area.get(lab, 0.0) + p.area
    # Labels are the index of the cluster's largest part, so ties go to the
    # cluster holding the largest part.
    body_label = max(cluster_area, key=lambda lab: (cluster_area[lab], -lab))
    body_tree = STRtree([p for lab, p in zip(label.tolist(), parts) if lab == body_label])
    out: list[Outlier] = []
    for lab, p in zip(label.tolist(), parts):
        if lab == body_label or cluster_area[lab] / total >= area_frac:
            continue
        _, dist = body_tree.query_nearest(p, return_distance=True)
        gap = float(dist.min()) / 1000.0
        c = p.centroid
        clon, clat = _to_4326(c.x, c.y)
        r = p.representative_point()
        rlon, rlat = _to_4326(r.x, r.y)
        out.append(Outlier(p.area / 1e6, gap, p.area / total, clat, clon, rlat, rlon))
    return out


def stream_features(path: Path) -> Iterator[dict]:
    """Yield GeoJSON features one at a time without loading the whole file.

    appellations.geojson is a single compact line ~1.7 GB long. We seek to the
    `features` array, then repeatedly `raw_decode` one feature object — the
    real JSON parser, so strings/nesting are handled correctly — refilling the
    buffer from disk as needed. Peak memory is one feature plus one read chunk.
    """
    dec = json.JSONDecoder()
    chunk = 1 << 20
    with path.open(encoding="utf-8") as fh:
        buf = ""
        n = 0

        def _truncated() -> ValueError:
            return ValueError(
                f"{path} ended after {n} features without the closing ']' — "
                "the GeoJSON is truncated or still being written. Wait for "
                "scripts/04_build_maps.py to finish, then re-run."
            )

        while '"features"' not in buf:
            more = fh.read(chunk)
            if not more:
                raise ValueError(f"{path} has no 'features' key — not a GeoJSON "
                                  "FeatureCollection")
            buf += more
        buf = buf[buf.index('"features"'):]
        while "[" not in buf:
            more = fh.read(chunk)
            if not more:
                raise ValueError(f"{path} has no 'features' array")
            buf += more
        buf = buf[buf.index("[") + 1:]
        while True:
            buf = buf.lstrip()
            while buf.startswith(","):
                buf = buf[1:].lstrip()
            if buf.startswith("]"):
                return
            if not buf:
                more = fh.read(chunk)
                if not more:
                    raise _truncated()
                buf += more
                continue
            try:
                obj, end = dec.raw_decode(buf)
            except json.JSONDecodeError:
                more = fh.read(chunk)
                if not more:
                    raise _truncated() from None
                buf += more
                continue
            yield obj
            n += 1
            buf = buf[end:]


def load_figshare_polygons(path: Path, file_numbers: set[str]) -> dict[str, BaseGeometry]:
    """Load the named PDO polygons from the Bétard gpkg, reprojected to
    EPSG:4326 (so GeometryOverrides.clip can be applied directly)."""
    if not path.exists() or not file_numbers:
        return {}
    import geopandas as gpd

    gdf = gpd.read_file(path)
    gdf = gdf[gdf["PDOid"].astype(str).isin(file_numbers)]
    if gdf.empty:
        return {}
    if gdf.crs is None or gdf.crs.to_string() != WGS84:
        gdf = gdf.to_crs(WGS84)
    return {str(row["PDOid"]): row.geometry for _, row in gdf.iterrows()}


def load_nuts_union_polygons(
    clip_specs: dict[str, dict], panel_dir: Path, nuts_layers: tuple[Path, ...],
) -> dict[str, BaseGeometry]:
    """The pre-clip source geometry of every `gisco-nuts-region` clip: the
    union of the GISCO NUTS polygons the record resolved to. Stage 04
    writes those ids on the record as `geom_nuts_ids` (panel payload
    wiki/data/d/en/<slug>.json), so the audit re-derives the union from the
    same layers the resolver unioned; a slug without the field (a build
    that predates it) stays unverifiable and is reported STALE."""
    slugs = [s for s, spec in clip_specs.items() if spec.get("geom_source") == "gisco-nuts-region"]
    if not slugs:
        return {}
    ids_by_slug: dict[str, list[str]] = {}
    for slug in slugs:
        path = panel_dir / f"{slug}.json"
        if not path.exists():
            continue
        try:
            ids = json.loads(path.read_text(encoding="utf-8")).get("geom_nuts_ids") or []
        except (OSError, ValueError):
            continue
        if ids:
            ids_by_slug[slug] = [str(i) for i in ids]
    wanted = {i for ids in ids_by_slug.values() for i in ids}
    if not wanted:
        return {}
    import geopandas as gpd

    nuts: dict[str, BaseGeometry] = {}
    for layer in nuts_layers:
        if not layer.exists():
            continue
        gdf = gpd.read_file(layer)
        gdf = gdf[gdf["NUTS_ID"].astype(str).isin(wanted)]
        if gdf.empty:
            continue
        if gdf.crs is None or gdf.crs.to_string() != WGS84:
            gdf = gdf.to_crs(WGS84)
        for _, row in gdf.iterrows():
            nuts[str(row["NUTS_ID"])] = row.geometry
    out: dict[str, BaseGeometry] = {}
    for slug, ids in ids_by_slug.items():
        polys = [nuts[i] for i in ids if i in nuts]
        if polys and len(polys) == len(ids):
            out[slug] = shapely.union_all(polys)
    return out


def feature_bbox(ft: dict) -> tuple[float, float, float, float] | None:
    """(minx, miny, maxx, maxy) in lon/lat. Uses the `bbox` property stage 04
    writes per feature; falls back to a walk over the raw coordinates. This
    lets both passes skip the expensive `shape()` / reprojection for features
    that cannot be relevant — no GEOS parsing just to get an extent."""
    bb = ft.get("properties", {}).get("bbox")
    if isinstance(bb, (list, tuple)) and len(bb) == 4:
        return tuple(float(v) for v in bb)
    coords = (ft.get("geometry") or {}).get("coordinates")
    if not coords:
        return None
    xs: list[float] = []
    ys: list[float] = []
    stack = [coords]
    while stack:
        c = stack.pop()
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            stack.extend(c)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def bbox_span_km(bbox: tuple[float, float, float, float]) -> float:
    """Diagonal of a lon/lat bbox in km — an upper bound on the gap between
    any two parts of a polygon with that bbox."""
    minx, miny, maxx, maxy = bbox
    return _haversine_km(miny, minx, maxy, maxx)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    ap.add_argument("--figshare", type=Path, default=DEFAULT_FIGSHARE)
    ap.add_argument(
        "--panel-dir", type=Path, default=DEFAULT_PANEL_DIR,
        help="per-slug panel payloads (geom_nuts_ids of NUTS-union records)",
    )
    ap.add_argument(
        "--gap-km", type=float, default=25.0,
        help="minimum gap from the main body for a part to count as detached",
    )
    ap.add_argument(
        "--area-frac", type=float, default=0.20,
        help="a detached part's cluster must hold less than this fraction of "
             "the total area",
    )
    ap.add_argument(
        "--minor-km2", type=float, default=1.0,
        help="outliers whose largest part is below this area are listed as "
             "minor (likely digitisation slivers)",
    )
    ap.add_argument(
        "--strict", action="store_true",
        help="exit non-zero on UNREVIEWED findings, not only STALE overrides",
    )
    args = ap.parse_args()

    # Line-buffer stdout: even if the run is interrupted, what ran is visible.
    sys.stdout.reconfigure(line_buffering=True)

    if not args.geojson.exists():
        print(f"error: {args.geojson} missing — run scripts/04_build_maps.py",
              file=sys.stderr)
        return 2

    overrides = GeometryOverrides()

    # Pass 1 — stream every feature, detect outliers. A feature can only hold
    # a part detached by more than `gap-km` if its own bbox spans at least
    # that far, so small appellations skip the expensive reprojection
    # entirely. Geometry is dropped as soon as it is scanned.
    print(f"pass 1/2: scanning {_display(args.geojson)} for outliers …",
          file=sys.stderr)
    detected: dict[str, dict] = {}  # slug -> {name, country, geom_source, ...}
    n_features = n_checked = 0
    for ft in stream_features(args.geojson):
        g = ft.get("geometry")
        props = ft.get("properties", {})
        if not g:
            continue
        n_features += 1
        bbox = feature_bbox(ft)
        if bbox is not None and bbox_span_km(bbox) < args.gap_km:
            continue
        n_checked += 1
        try:
            g3035 = shp_transform(_to_3035, shape(g))
        except Exception:  # noqa: BLE001 — skip an unparseable geometry
            continue
        outliers = detect_outliers(g3035, args.gap_km, args.area_frac)
        if outliers:
            slug = props.get("slug") or ""
            n_parts = len(list(g3035.geoms)) if g3035.geom_type == "MultiPolygon" else 1
            detected[slug] = {
                "name": props.get("name") or slug,
                "country": props.get("country") or "",
                "geom_source": props.get("geom_source") or "",
                "n_parts": n_parts,
                "outliers": outliers,
            }
    print(f"  {n_features} features ({n_checked} large enough to check), "
          f"{len(detected)} with detached parts", file=sys.stderr)

    # Pass 2 — overlap signal: which other appellation polygon contains each
    # outlier part? A second stream; for each feature, a bbox pre-filter then a
    # prepared-geometry point-in-polygon test. Containment is projection-
    # independent, so this pass needs no reprojection.
    out_points = [
        (slug, ol)
        for slug, info in detected.items()
        for ol in info["outliers"]
    ]
    if out_points:
        print("pass 2/2: resolving which appellations the outliers sit inside …",
              file=sys.stderr)
        for ft in stream_features(args.geojson):
            g = ft.get("geometry")
            props = ft.get("properties", {})
            if not g:
                continue
            bbox = feature_bbox(ft)
            if bbox is None:
                continue
            fslug = props.get("slug") or ""
            minx, miny, maxx, maxy = bbox
            cands = [
                (s, ol) for s, ol in out_points
                if s != fslug
                and minx <= ol.rep_lon <= maxx and miny <= ol.rep_lat <= maxy
            ]
            if not cands:
                continue
            # Only now is the (potentially huge) geometry actually parsed.
            try:
                pg = prep(shape(g))
            except Exception:  # noqa: BLE001
                continue
            fname = props.get("name") or fslug
            for _s, ol in cands:
                if pg.contains(Point(ol.rep_lon, ol.rep_lat)):
                    ol.overlaps.append(fname)
        for _s, ol in out_points:
            ol.overlaps = sorted(set(ol.overlaps))[:4]

    # Pass 3 — verify clip overrides against the SOURCE figshare data.
    clip_specs = overrides.clip_specs
    file_numbers = {
        s.get("file_number") for s in clip_specs.values()
        if s.get("geom_source", "figshare-pdo") == "figshare-pdo"
    }
    file_numbers.discard(None)
    src_polys = load_figshare_polygons(args.figshare, file_numbers)
    nuts_polys = load_nuts_union_polygons(clip_specs, args.panel_dir, DEFAULT_NUTS_LAYERS)

    confirmed: list[str] = []
    pending: list[str] = []
    stale: list[str] = []
    for slug, spec in sorted(clip_specs.items()):
        fn = spec.get("file_number") or ""
        if spec.get("geom_source") == "gisco-nuts-region":
            src_geom = nuts_polys.get(slug)
            if src_geom is None:
                stale.append(
                    f"  {slug:32s} {fn:14s} SOURCE POLYGON NOT FOUND — no "
                    f"geom_nuts_ids in {_display(args.panel_dir / (slug + '.json'))} "
                    f"(rebuild with scripts/04_build_maps.py) or NUTS layer missing"
                )
                continue
        else:
            src_geom = src_polys.get(fn)
        if src_geom is None:
            stale.append(
                f"  {slug:32s} {fn:14s} SOURCE POLYGON NOT FOUND — cannot "
                f"verify (is {args.figshare.name} present / current?)"
            )
            continue
        src_res = overrides.clip(slug, src_geom)
        gj_outliers = detected.get(slug, {}).get("outliers", [])
        for d in src_res.dropped:
            dlat, dlon = d["centroid_latlon"]
            still_on_map = any(
                _haversine_km(dlat, dlon, ol.lat, ol.lon) <= overrides.match_tol_km
                for ol in gj_outliers
            )
            line = (f"  {slug:32s} {fn:14s} part @({dlat:.4f},{dlon:.4f}) "
                    f"~{d['area_km2']:.1f} km2")
            if still_on_map:
                pending.append(line + "  — still in appellations.geojson; "
                                       "re-run scripts/04_build_maps.py")
            else:
                confirmed.append(line + "  — verified spurious in source, "
                                         "clipped from the map")
        for s in src_res.stale:
            slat, slon = s.get("centroid_latlon", (0.0, 0.0))
            n = s.get("n_matches", 0)
            why = "matches no source part" if n == 0 else f"matches {n} source parts"
            stale.append(
                f"  {slug:32s} {fn:14s} drop spec @({slat:.4f},{slon:.4f}) "
                f"~{s.get('area_km2', 0):.1f} km2 — {why}; RE-VERIFY"
            )

    # Pass 4 — partition detected outliers into ACCEPTED / UNREVIEWED. An
    # outlier of a clip-override slug that matches a drop spec is handled by
    # Pass 3; any that match no drop spec still count as unreviewed.
    accepted: list[tuple[str, dict]] = []
    unreviewed: list[tuple[str, dict, list[Outlier]]] = []
    for slug, info in detected.items():
        if overrides.is_whitelisted(slug):
            accepted.append((slug, info))
            continue
        spec = clip_specs.get(slug)
        leftover = info["outliers"]
        if spec:
            drops = spec.get("drop", [])
            leftover = [
                ol for ol in info["outliers"]
                if not any(
                    _haversine_km(d["centroid_latlon"][0], d["centroid_latlon"][1],
                                  ol.lat, ol.lon) <= overrides.match_tol_km
                    for d in drops
                )
            ]
        if leftover:
            unreviewed.append((slug, info, leftover))

    whitelist_unused = [s for s in overrides.whitelist if s not in detected]

    # ---- report ----------------------------------------------------------
    print()
    print("GEOMETRY-OUTLIER AUDIT")
    print("=" * 72)
    print(f"source     : {_display(args.geojson)} ({n_features} features)")
    print(f"thresholds : gap > {args.gap_km:g} km, detached cluster < "
          f"{args.area_frac * 100:g}% of total area")
    print()

    print(f"CONFIRMED clips — override active, fix verified against source  "
          f"[{len(confirmed)}]")
    for line in confirmed:
        print(line)
    print()

    print(f"PENDING REBUILD — override added, map not yet rebuilt  [{len(pending)}]")
    for line in pending:
        print(line)
    print()

    print(f"STALE overrides — no longer match source, RE-VERIFY  [{len(stale)}]")
    for line in stale:
        print(line)
    print()

    print(f"ACCEPTED — whitelisted, detached parts are legitimate  [{len(accepted)}]")
    for slug, info in sorted(accepted, key=lambda t: t[0]):
        worst = max(info["outliers"], key=lambda o: o.severity)
        print(f"  {info['name']:32s} [{info['country']}] {info['n_parts']} parts; "
              f"{len(info['outliers'])} detached "
              f"(worst ~{worst.area_km2:.1f} km2, {worst.gap_km:.0f} km away) — "
              f"{overrides.whitelist[slug]}")
    print()

    prominent = [u for u in unreviewed
                 if max(o.area_km2 for o in u[2]) >= args.minor_km2]
    minor = [u for u in unreviewed
             if max(o.area_km2 for o in u[2]) < args.minor_km2]
    prominent.sort(key=lambda u: -max(o.severity for o in u[2]))
    minor.sort(key=lambda u: -max(o.severity for o in u[2]))

    print(f"UNREVIEWED outliers — need review  [{len(unreviewed)}]")
    for _slug, info, ols in prominent:
        _print_unreviewed(info, ols)
    if minor:
        print()
        print(f"  -- minor: largest part < {args.minor_km2:g} km2, "
              f"likely digitisation slivers --")
        for _slug, info, ols in minor:
            _print_unreviewed(info, ols, compact=True)
    print()

    if whitelist_unused:
        print(f"NOTE: {len(whitelist_unused)} whitelist entr(y/ies) no longer "
              f"match any detached appellation (data changed?): "
              f"{', '.join(whitelist_unused)}")
        print()

    print("SUMMARY")
    print("-" * 72)
    print(f"  confirmed clips   : {len(confirmed)}")
    print(f"  pending rebuild   : {len(pending)}")
    print(f"  stale overrides   : {len(stale)}")
    print(f"  accepted          : {len(accepted)}")
    print(f"  unreviewed        : {len(unreviewed)}  "
          f"({len(prominent)} prominent, {len(minor)} minor)")
    print()
    if stale:
        print("RESULT: FAIL — stale override(s); re-verify "
              "scripts/_lib/geometry_outlier_overrides.json")
        return 1
    if args.strict and unreviewed:
        print("RESULT: FAIL (--strict) — unreviewed outlier(s) present")
        return 1
    if pending:
        print("RESULT: ok — re-run scripts/04_build_maps.py to apply pending clips")
        return 0
    print("RESULT: ok")
    return 0


_MAX_PARTS_SHOWN = 10


def _print_unreviewed(info: dict, ols: list[Outlier], compact: bool = False) -> None:
    ols = sorted(ols, key=lambda o: -o.severity)
    print(f"  {info['name']}  [{info['country']}]  "
          f"src={info['geom_source']}  ({info['n_parts']} parts)")
    # A detached parcellaire lobe is hundreds of parcels; the worst ones
    # locate it.
    shown = ols[:1] if compact else ols[:_MAX_PARTS_SHOWN]
    for ol in shown:
        ov = "; ".join(ol.overlaps) if ol.overlaps else "no appellation"
        print(f"      part ~{ol.area_km2:8.2f} km2  gap {ol.gap_km:6.1f} km  "
              f"@({ol.lat:.4f},{ol.lon:.4f})  inside: {ov}")
    rest = ols[len(shown):]
    if rest:
        print(f"      … +{len(rest)} more detached part(s), "
              f"~{sum(o.area_km2 for o in rest):.2f} km2")


if __name__ == "__main__":
    raise SystemExit(main())
