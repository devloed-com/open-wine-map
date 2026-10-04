"""Generalised vineyard footprint of an INAO parcellaire — the low-zoom
geometry of a French appellation.

Below the detail zoom the map draws not the parcel delimitation itself but a
*morphological closing* of it: dilate by ``ENVELOPE_RADIUS_M``, erode by the
same amount, simplify. Parcels closer than twice the radius merge into one
silhouette, holes narrower than that fill, and the result stays inside the
dilation of the parcels — so it is a generalisation of the regulator's
delimitation, never a different area. It replaces the commune union that the
default view used to draw for these records (5–8× the vineyard, water and
forest included) with a shape ~1.3× the vineyard that follows it.

Cost is kept linear by decomposing the parcellaire into connected components
first: two parts can only interact in a closing when they are within ``2r``
of each other, so grouping parts whose ``r``-dilated bounding boxes touch
(an STRtree query plus union-find) is a conservative, exact decomposition and
each component closes on its own. Languedoc (31,488 parts) goes from 832 s
monolithic to ~20 s.

Results are cached on disk under ``raw/cache/vineyard-envelopes``, keyed by a
digest of the *input* geometry (plus the parameter version), so the cache is a
pure function of the INAO data: a fresh checkout rebuilds it, a new
parcellaire release invalidates exactly the records that changed, and records
sharing one polygon (Banyuls / Banyuls Grand Cru / Collioure) close once.
"""

from __future__ import annotations

import hashlib
import math
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[2]

# Closing radius in metres. 250 m keeps the shape of the vineyard (Saint-Bris'
# three lobes, Sancerre's detached south-western parcels) at a median area
# inflation of 1.33× over the parcels; 500 m already turns Saint-Bris into a
# ring around its village. Rivers narrower than 2r between parcels on both
# banks are bridged — see scripts/audit_vineyard_envelopes.py --water.
ENVELOPE_RADIUS_M = 250
# Douglas-Peucker tolerance applied to the closed shape (metres). The input
# is already tile-simplified (~22 m); 30 m removes the buffer arcs' vertices.
ENVELOPE_SIMPLIFY_M = 30
# Segments per quarter circle for the buffers. 3 is enough for a shape that
# is simplified afterwards; more only adds vertices to erode again.
ENVELOPE_QUAD_SEGS = 3
# Bump whenever radius / simplify / quad_segs / the algorithm change: it is
# part of the cache key, so stale envelopes can never be served.
ENVELOPE_VERSION = 2

# Countries whose parcel-level delimitation gets a footprint. Only France
# publishes one (INAO parcellaire); the rule is on the record's country AND
# its geometry provenance (see `is_envelope_source`).
ENVELOPE_COUNTRIES = frozenset({"fr"})
# Detail-geometry provenances that are parcel-level. A record inheriting one
# of these (parent-appellation / sibling-dgc) is decided by its donor.
ENVELOPE_SOURCES = frozenset({"parcellaire", "parcellaire-dgc"})
# The value written to the overview feature's `geom_source`.
ENVELOPE_GEOM_SOURCE = "parcellaire-envelope"
# Zoom bands, shared with the map template and app.js (through the build
# tokens) so Python and JS never disagree about where the footprint stops.
LOD_DETAIL_MIN_ZOOM = 11     # parcel layers exist from this zoom
LOD_CROSSFADE = (11.0, 11.9)  # parcels fade in / footprint fades out
# The overview layers stop at the end of the crossfade (their maxzoom), so
# what the card says ("footprint") and what is drawn agree to the pixel.
LOD_FOOTPRINT_MAX_ZOOM = LOD_CROSSFADE[1]
# Single-record fits stop here: from this zoom only the parcels are drawn.
LOD_OVERVIEW_MAX_ZOOM = 12

# The closing radius scales with the record below one square kilometre:
# r = ADAPTIVE_FACTOR · √(parcel area), floored at ENVELOPE_MIN_RADIUS_M and
# capped at ENVELOPE_RADIUS_M. A 250 m closing generalises a village AOC or a
# regional appellation the way it should, but on a Burgundy premier-cru climat
# of 0.01–0.1 km² it laps across the neighbouring climat (Les Gaudichots'
# footprint was 65 % La Tâche parcels, 2026-09-24 audit): there the gaps
# worth closing are the row breaks and tracks inside the climat, tens of
# metres, not the 500 m the regional silhouette needs. √area is the
# record's own length scale — 1 km² → 250 m, 0.25 km² → 125 m,
# 0.05 km² → 56 m — so the footprint of a small record follows its parcels.
ADAPTIVE_FACTOR = 0.25
ENVELOPE_MIN_RADIUS_M = 30

CACHE_DIR = ROOT / "raw" / "cache" / "vineyard-envelopes"

_TO_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform
_TO_4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True).transform


def containment_tolerance_m(radius_m: float = ENVELOPE_RADIUS_M) -> float:
    """How far the footprint may fall *inside* its parcels. A polygonal buffer
    under-covers a corner by the chord sagitta r·(1 − cos(π/(4·quad_segs)))
    (≈ 8.5 m at 250 m / 3 segments), and the final simplify may move an edge
    by ENVELOPE_SIMPLIFY_M. Everything else is contained exactly: a closing
    never leaves the r-dilation of its input."""
    sagitta = radius_m * (1.0 - math.cos(math.pi / (4 * ENVELOPE_QUAD_SEGS)))
    return sagitta + ENVELOPE_SIMPLIFY_M


def adaptive_radius(area_m2: float) -> int:
    """Closing radius for a record whose parcels cover `area_m2` (EPSG:3035
    square metres): whole metres, so the cache key and the card agree."""
    if area_m2 <= 0:
        return ENVELOPE_MIN_RADIUS_M
    r = ADAPTIVE_FACTOR * math.sqrt(area_m2)
    return int(round(min(ENVELOPE_RADIUS_M, max(ENVELOPE_MIN_RADIUS_M, r))))


def is_envelope_source(country: str | None, geom_source: str | None) -> bool:
    return (country or "fr") in ENVELOPE_COUNTRIES and geom_source in ENVELOPE_SOURCES


def cache_key(geom: BaseGeometry, radius_m: int = ENVELOPE_RADIUS_M) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(f"v{ENVELOPE_VERSION}-r{radius_m}-s{ENVELOPE_SIMPLIFY_M}-q{ENVELOPE_QUAD_SEGS}|".encode())
    h.update(shapely.to_wkb(geom, flavor="iso"))
    return h.hexdigest()


def _cache_path(key: str, radius_m: int) -> Path:
    return CACHE_DIR / f"v{ENVELOPE_VERSION}-r{radius_m}" / key[:2] / f"{key}.wkb"


def _components(parts: list[BaseGeometry], r: float) -> list[list[int]]:
    """Group parts whose r-grown bounding boxes intersect (union-find over an
    STRtree query). Two parts can only touch in a closing when their
    r-dilations meet, i.e. when they are within 2r; a bbox grown by r on every
    side contains the part's r-dilation (a rounded buffer of the box would
    under-cover the corners), so the grouping is a conservative superset and
    the decomposition is exact for the closing that follows."""
    n = len(parts)
    if n <= 1:
        return [list(range(n))]
    boxes = np.array([shapely.box(b[0] - r, b[1] - r, b[2] + r, b[3] + r) for b in (p.bounds for p in parts)])
    tree = shapely.STRtree(boxes)
    left, right = tree.query(boxes, predicate="intersects")
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in zip(left.tolist(), right.tolist()):
        if a == b:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _close(geom_3035: BaseGeometry, r: float) -> BaseGeometry:
    qs = ENVELOPE_QUAD_SEGS
    out = geom_3035.buffer(r, quad_segs=qs).buffer(-r, quad_segs=qs)
    out = out.simplify(ENVELOPE_SIMPLIFY_M, preserve_topology=True)
    return shapely.make_valid(out)


def envelope_3035(geom_3035: BaseGeometry, radius_m: float = ENVELOPE_RADIUS_M) -> BaseGeometry:
    """Morphological closing of a (multi)polygon already in EPSG:3035."""
    if geom_3035.is_empty:
        return geom_3035
    parts = list(geom_3035.geoms) if geom_3035.geom_type == "MultiPolygon" else [geom_3035]
    pieces = []
    for idx in _components(parts, radius_m):
        comp = shapely.union_all([parts[i] for i in idx]) if len(idx) > 1 else parts[idx[0]]
        closed = _close(comp, radius_m)
        if not closed.is_empty:
            pieces.append(closed)
    if not pieces:
        return geom_3035
    out = shapely.union_all(pieces) if len(pieces) > 1 else pieces[0]
    return shapely.make_valid(out)


def envelope(
    geom_4326: BaseGeometry,
    radius_m: int | None = None,
    *,
    use_cache: bool = True,
    stats: dict | None = None,
) -> BaseGeometry:
    """Footprint of a WGS84 (multi)polygon, cached on disk by input digest.

    `radius_m` defaults to `adaptive_radius` of the polygon's area (see the
    constants); a caller may pin it. `stats`, when given, is incremented in
    place: `hits`, `misses`, `secs`, and `radius_m` is set to the radius
    used. Never returns an empty geometry for a non-empty input: on the
    (theoretical) degenerate case the input itself is returned, so a record
    can never vanish from the overview layer.
    """
    if geom_4326 is None or geom_4326.is_empty:
        return geom_4326
    if radius_m is None:
        radius_m = adaptive_radius(_area_m2(geom_4326))
    if stats is not None:
        stats["radius_m"] = radius_m
    key = cache_key(geom_4326, radius_m)
    path = _cache_path(key, radius_m)
    if use_cache and path.exists():
        try:
            out = shapely.from_wkb(path.read_bytes())
            if not out.is_empty:
                if stats is not None:
                    stats["hits"] = stats.get("hits", 0) + 1
                return out
        except Exception as exc:  # a truncated file is just a miss
            print(f"[envelope] unreadable cache {path.name}: {exc}", file=sys.stderr)
    t0 = time.perf_counter()
    g3035 = shp_transform(_TO_3035, geom_4326)
    closed = envelope_3035(g3035, radius_m)
    out = shp_transform(_TO_4326, closed) if not closed.is_empty else geom_4326
    if out.is_empty:
        out = geom_4326
    if stats is not None:
        stats["misses"] = stats.get("misses", 0) + 1
        stats["secs"] = stats.get("secs", 0.0) + (time.perf_counter() - t0)
    if use_cache:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(shapely.to_wkb(out, flavor="iso"))
            tmp.replace(path)
        except OSError as exc:
            print(f"[envelope] cache write failed {path.name}: {exc}", file=sys.stderr)
    return out


def _area_m2(geom_4326: BaseGeometry) -> float:
    """Equal-area (EPSG:3035) area of a WGS84 polygon. Reprojecting is the
    honest measure and costs a fraction of the closing it sizes."""
    return float(shp_transform(_TO_3035, geom_4326).area)


def shape_metrics(geom_4326: BaseGeometry) -> tuple[int, float]:
    """`(parts, frag)` for the outline paint: the number of polygon parts and
    the perimeter/area ratio in m⁻¹ — ink per fill for a given stroke width.
    An equirectangular rescale at the polygon's latitude is accurate to ~1 %
    across the corpus and avoids reprojecting every polygon."""
    if geom_4326 is None or geom_4326.is_empty:
        return 0, 0.0
    parts = len(geom_4326.geoms) if geom_4326.geom_type == "MultiPolygon" else 1
    lat = float(geom_4326.centroid.y) if not geom_4326.centroid.is_empty else 46.0
    kx = float(np.cos(np.radians(lat)))
    local = shapely.transform(geom_4326, lambda c: c * np.array([kx, 1.0]))
    area_deg2 = float(local.area)
    if area_deg2 <= 0:
        return parts, 0.0
    frag = float(local.length) / (area_deg2 * 111_320.0)
    return parts, frag


def lod_config() -> dict:
    """The LOD constants the client needs (rendered into app.js as one JSON)."""
    return {
        "radius_m": ENVELOPE_RADIUS_M,
        "min_radius_m": ENVELOPE_MIN_RADIUS_M,
        "adaptive_factor": ADAPTIVE_FACTOR,
        "overview_max_zoom": LOD_OVERVIEW_MAX_ZOOM,
        "footprint_max_zoom": LOD_FOOTPRINT_MAX_ZOOM,
        "detail_min_zoom": LOD_DETAIL_MIN_ZOOM,
        "crossfade": list(LOD_CROSSFADE),
        "countries": sorted(ENVELOPE_COUNTRIES),
        "sources": sorted(ENVELOPE_SOURCES),
    }
