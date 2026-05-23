#!/usr/bin/env python3
"""Audit — suspicious overlaps between appellation polygons.

Appellations overlap by design, and most overlaps are normal: a regional DOC
contains its village DOCs, a sub-denomination sits inside its parent, style
variants share a footprint, and whole families of Italian DOCs (Chianti /
Chianti Classico, the Abruzzo varietal DOCs) genuinely cover the same ground.

A SUSPICIOUS overlap is the opposite — two appellations that are *otherwise
disjoint*, sitting side by side, that share only a thin sliver (typically one
commune thick). That is a commune-union artifact: a border commune assigned to
both appellations' commune lists (or a same-name collision, or imprecise
source polygons). Two appellations built from disjoint commune lists should
*tile* — touch along borders, not overlap with real 2-D area.

For every pair of appellation polygons whose bounding boxes meet, the audit:

  - skips hierarchy pairs — parent ⊃ sub-denomination, and siblings of one
    appellation — which are expected to overlap;
  - classifies the rest by `share` = overlap area / appellation area, taking
    the LARGER of the two shares:
      NESTED   — max share ≥ --containment: one polygon (near-)contains the
                 other. A regional appellation over a smaller one — normal.
      PARTIAL  — --sliver-max ≤ max share < --containment: a large mutual
                 overlap — genuinely overlapping appellations — normal.
      WIDE     — max share < --sliver-max but the overlap area is large
                 (> --max-sliver-km2): two big appellations (regional IGPs)
                 that genuinely share a wide border zone — normal.
      SLIVER   — max share < --sliver-max AND the overlap is small in
                 absolute terms (≤ --max-sliver-km2, i.e. commune-scale): two
                 appellations otherwise disjoint that share only a thin band,
                 the size of a border commune or two. SUSPICIOUS. (A
                 cross-country overlap is always suspicious, whatever its
                 size — appellations of different countries should not share
                 any ground.)
  - cross-references scripts/_lib/geometry_overlap_overrides.json, so a
    reviewed-legitimate sliver is reported as ACCEPTED rather than re-flagged.

The geojson is streamed (it is large); geometries are reprojected to EPSG:3035
and lightly simplified (overlap is a coarse property — a one-commune sliver is
km-scale and survives a ~100 m simplification, which keeps the pairwise
intersection tractable). Default source is the commune-level villages layer —
the right granularity for a "one commune thick" overlap.

Exit code is non-zero with --strict when unreviewed suspicious slivers remain.

Usage:
  uv run scripts/audit_geometry_overlaps.py
  uv run scripts/audit_geometry_overlaps.py --sliver-max 0.2 --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.prepared import prep
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_geometry_outliers import stream_features  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GEOJSON = ROOT / "wiki" / "map-data" / "appellations-villages.geojson"
OVERRIDES_PATH = ROOT / "scripts" / "_lib" / "geometry_overlap_overrides.json"

_to_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform


class Feat:
    """One appellation: metadata plus its reprojected, simplified geometry."""

    __slots__ = ("slug", "name", "country", "region", "kind", "geom", "area",
                 "parent", "id_app")

    def __init__(self, props: dict, geom: BaseGeometry):
        self.slug = props.get("slug") or ""
        self.name = props.get("name") or self.slug
        self.country = props.get("country") or ""
        self.region = props.get("region") or ""
        self.kind = props.get("kind") or ""
        self.parent = props.get("parent_slug") or ""
        self.id_app = props.get("id_appellation")
        self.geom = geom
        self.area = geom.area


def _hierarchy(a: Feat, b: Feat) -> bool:
    """True when a and b are expected to overlap: one is the other's parent
    appellation, or they are sub-denominations of the same appellation."""
    if a.parent and a.parent == b.slug:
        return True
    if b.parent and b.parent == a.slug:
        return True
    return a.id_app is not None and a.id_app == b.id_app


def load_overrides(path: Path) -> dict[frozenset, str]:
    """Return {frozenset({slug_a, slug_b}): reason} for whitelisted pairs."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[frozenset, str] = {}
    for entry in data.get("whitelist", []) or []:
        pair = entry.get("pair") or []
        if len(pair) == 2:
            out[frozenset(pair)] = entry.get("reason", "")
    return out


class Overlap:
    __slots__ = ("a", "b", "area_km2", "share_a", "share_b", "eff_width_km")

    def __init__(self, a, b, area_km2, share_a, share_b, eff_width_km):
        self.a, self.b = a, b
        self.area_km2 = area_km2
        self.share_a, self.share_b = share_a, share_b
        self.eff_width_km = eff_width_km

    @property
    def max_share(self) -> float:
        return max(self.share_a, self.share_b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    ap.add_argument(
        "--sliver-max", type=float, default=0.10,
        help="overlap counts as a suspicious SLIVER when it is below this "
             "fraction of BOTH appellations' area (default 0.10)",
    )
    ap.add_argument(
        "--containment", type=float, default=0.90,
        help="overlap at or above this fraction of one appellation is NESTED "
             "(a regional appellation over a smaller one) — normal",
    )
    ap.add_argument(
        "--min-overlap-km2", type=float, default=1.0,
        help="ignore overlaps below this area — border touches and precision "
             "slivers, not real double-coverage (default 1.0)",
    )
    ap.add_argument(
        "--max-sliver-km2", type=float, default=50.0,
        help="a small-ratio overlap LARGER than this is a WIDE overlap (two "
             "big appellations sharing a wide zone), not a commune-scale "
             "sliver — raise to widen the net (default 50.0)",
    )
    ap.add_argument(
        "--simplify-m", type=float, default=100.0,
        help="simplification tolerance in metres applied before intersection "
             "(0 disables); a one-commune sliver survives it",
    )
    ap.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when unreviewed suspicious slivers remain",
    )
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    if not args.geojson.exists():
        print(f"error: {args.geojson} missing — run scripts/04_build_maps.py",
              file=sys.stderr)
        return 2

    overrides = load_overrides(OVERRIDES_PATH)

    # ---- load -------------------------------------------------------------
    print(f"loading {args.geojson.relative_to(ROOT)} …", file=sys.stderr)
    feats: list[Feat] = []
    n = 0
    for ft in stream_features(args.geojson):
        g = ft.get("geometry")
        if not g:
            continue
        n += 1
        try:
            geom = shp_transform(_to_3035, shape(g))
            if args.simplify_m > 0:
                geom = geom.simplify(args.simplify_m)
        except Exception:  # noqa: BLE001 — skip an unparseable geometry
            continue
        if geom.is_empty or geom.area <= 0:
            continue
        feats.append(Feat(ft.get("properties", {}), geom))
    print(f"  {n} features, {len(feats)} with usable geometry", file=sys.stderr)

    # ---- pairwise overlap -------------------------------------------------
    print("computing pairwise overlaps …", file=sys.stderr)
    geoms = [f.geom for f in feats]
    prepared = [prep(g) for g in geoms]
    tree = STRtree(geoms)
    nested = partial = touches = wide = 0
    slivers: list[Overlap] = []
    for i, fa in enumerate(feats):
        pa = prepared[i]
        for j in tree.query(geoms[i]):
            j = int(j)
            if j <= i:
                continue
            fb = feats[j]
            if _hierarchy(fa, fb):
                continue
            gb = geoms[j]
            if not pa.intersects(gb):
                continue
            if pa.covers(gb) or prepared[j].covers(geoms[i]):
                nested += 1
                continue
            inter = geoms[i].intersection(gb)
            ia = inter.area
            if ia <= 0:
                touches += 1
                continue
            share_a, share_b = ia / fa.area, ia / fb.area
            mx = max(share_a, share_b)
            if mx >= args.containment:
                nested += 1
                continue
            if mx >= args.sliver_max:
                partial += 1
                continue
            km2 = ia / 1e6
            if km2 < args.min_overlap_km2:
                touches += 1
                continue
            # Small ratio + large absolute area = two big appellations
            # sharing a wide border zone (regional IGPs) — normal, not a
            # commune-scale sliver. Cross-country overlaps stay suspicious
            # at any size.
            if km2 > args.max_sliver_km2 and fa.country == fb.country:
                wide += 1
                continue
            per = inter.length or 1.0
            slivers.append(Overlap(fa, fb, km2, share_a, share_b,
                                   2.0 * ia / per / 1000.0))

    # ---- collapse sub-denomination families -------------------------------
    # One appellation overlapping a parent appellation AND its sub-
    # denominations (which inherit the parent's geometry) is a single
    # finding, not one per sub-denomination — IGP Val de Loire alone has a
    # dozen department sub-denominations. Group each sliver by its family
    # key (a sub-denomination folds into its parent); the largest-area
    # member is the representative.
    def fam(f: Feat) -> str:
        return f.parent or f.slug

    groups: dict[frozenset, list[Overlap]] = {}
    for ov in slivers:
        groups.setdefault(frozenset((fam(ov.a), fam(ov.b))), []).append(ov)

    accepted: list[tuple[Overlap, int, str]] = []
    suspicious: list[tuple[Overlap, int]] = []
    used_keys: set[frozenset] = set()
    for members in groups.values():
        members.sort(key=lambda o: -o.area_km2)
        rep = members[0]
        extra = len(members) - 1
        pair_key = frozenset((rep.a.slug, rep.b.slug))
        used_keys.add(pair_key)
        if pair_key in overrides:
            accepted.append((rep, extra, overrides[pair_key]))
        else:
            suspicious.append((rep, extra))
    suspicious.sort(key=lambda t: -t[0].area_km2)
    stale_wl = [sorted(k) for k in overrides if k not in used_keys]

    def _fmt(ov: Overlap, extra: int) -> str:
        a, b = ov.a, ov.b
        if a.country != b.country:
            tag = f"  [CROSS-COUNTRY {a.country}/{b.country}]"
        elif a.region != b.region:
            tag = f"  [cross-region {a.region or '?'} / {b.region or '?'}]"
        else:
            tag = ""
        more = f"  (+{extra} sub-denomination pair(s))" if extra else ""
        return (f"  ~{ov.area_km2:6.1f} km2  "
                f"{ov.share_a * 100:4.1f}% of {a.name} / "
                f"{ov.share_b * 100:4.1f}% of {b.name}  "
                f"(~{ov.eff_width_km:.1f} km wide){tag}{more}")

    # ---- report -----------------------------------------------------------
    print()
    print("GEOMETRY-OVERLAP AUDIT")
    print("=" * 78)
    print(f"source     : {args.geojson.relative_to(ROOT)} ({len(feats)} appellations)")
    print(f"sliver rule: {args.min_overlap_km2:g}–{args.max_sliver_km2:g} km2 "
          f"overlap, < {args.sliver_max * 100:g}% of BOTH appellations "
          f"(or any cross-country overlap)")
    print(f"context    : {nested} nested, {partial} large partial, {wide} wide "
          f"regional overlaps (all normal); {touches} border touches ignored")
    print()

    print(f"ACCEPTED — reviewed legitimate slivers (whitelisted)  [{len(accepted)}]")
    for ov, extra, reason in sorted(accepted, key=lambda t: -t[0].area_km2):
        print(f"  {ov.a.name} vs {ov.b.name}  (~{ov.area_km2:.0f} km2) — {reason}")
    print()

    cross = [t for t in suspicious if t[0].a.country != t[0].b.country]
    same = [t for t in suspicious if t[0].a.country == t[0].b.country]
    print(f"SUSPICIOUS — sliver overlaps between otherwise-disjoint "
          f"appellations  [{len(suspicious)}]")
    print()
    print(f"  cross-country — appellations of different countries should not "
          f"share ground  [{len(cross)}]")
    for ov, extra in cross:
        print(_fmt(ov, extra))
    print()
    print(f"  same-country — a border commune likely double-assigned  [{len(same)}]")
    for ov, extra in same:
        print(_fmt(ov, extra))

    if stale_wl:
        print()
        print(f"NOTE: {len(stale_wl)} whitelist entr(y/ies) no longer match any "
              f"overlap (data changed?): "
              f"{', '.join('+'.join(p) for p in stale_wl)}")

    print()
    print("SUMMARY")
    print("-" * 78)
    print(f"  suspicious slivers  : {len(suspicious)}  "
          f"({len(cross)} cross-country, {len(same)} same-country)")
    print(f"  accepted (whitelist): {len(accepted)}")
    print(f"  normal overlaps     : {nested} nested + {partial} large partial "
          f"+ {wide} wide")
    print()
    if args.strict and suspicious:
        print("RESULT: FAIL (--strict) — unreviewed suspicious slivers")
        return 1
    print("RESULT: ok" if not suspicious
          else "RESULT: ok — review the suspicious slivers above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
