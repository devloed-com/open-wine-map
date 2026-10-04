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

The first corpus-wide review (2026-09-25, 520 slivers) found that premise
holds only for one class of pair, so every sliver is first classified —
listed in full, never hidden — and only the last class is SUSPICIOUS:

  BORDER          — two countries, a band under --thin-km wide: the two
                    national layers digitise the state border differently.
  TIER            — a PGI / IGP (or a spirit-drink GI) over a PDO / AOC of
                    the same country: the broader tier shares ground with
                    the narrower one by design, nothing is double-assigned.
  GENERALISATION  — same country and tier, a band under --thin-km wide,
                    the two records drawn from different geometry sources
                    (Bétard vs a GISCO union, a geoportal zone vs a commune
                    list): a coastline or boundary drawn at two resolutions.
  SOURCE-DRAWN    — same country and tier, both polygons taken from an
                    official zone layer (regional geoportal, MAPA, INAO
                    parcellaire) or Bétard: the overlap is the publisher's
                    own statement (Tuscany's DOCs, Bétard's padded
                    municipalities); a commune list cannot fix it.
  SUSPICIOUS      — what is left: same country and tier, at least one side
                    drawn from a commune list of ours, and either wide or
                    from the same source — the one class where a double-
                    assigned commune is the likely cause.

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


def _display(path: Path) -> str:
    """Repo-relative when the file is inside the repo, absolute otherwise —
    ``--geojson`` may point at a snapshot outside the checkout."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)



class Feat:
    """One appellation: metadata plus its reprojected, simplified geometry."""

    __slots__ = ("slug", "name", "country", "region", "kind", "geom", "area",
                 "parent", "id_app", "geom_source")

    def __init__(self, props: dict, geom: BaseGeometry):
        self.slug = props.get("slug") or ""
        self.name = props.get("name") or self.slug
        self.country = props.get("country") or ""
        self.region = props.get("region") or ""
        self.kind = props.get("kind") or ""
        self.parent = props.get("parent_slug") or ""
        self.id_app = props.get("id_appellation")
        self.geom_source = props.get("geom_source") or ""
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


# GI tiers: a PGI over a PDO is expected to share ground.
_TIER = {"AOC": "pdo", "AOP": "pdo", "DOP": "pdo", "PDO": "pdo",
         "IGP": "pgi", "PGI": "pgi", "EDV": "spirit"}
# Provenances that are a published zone polygon (or Bétard), not a commune
# list of ours. A sub-denomination that inherits its polygon is read through
# its parent (`root_source`).
_ZONE_SOURCE_PREFIXES = (
    "figshare-pdo", "mapa-zone", "geoportal-zone", "geoportal-canton", "sigpac",
    "parcellaire", "cadastre-lieu-dit", "ivv-commune-vineyard", "region-pdo-union",
    "pdo-plan-parcel",
)
_INHERITING_SOURCES = ("parent-appellation", "parent-aoc", "sibling-dgc")
CLASSES = ("border", "tier", "generalisation", "source", "suspicious")


def _tier(kind: str) -> str:
    return _TIER.get(kind or "", kind or "?")


def is_zone_source(src: str) -> bool:
    return any(src.startswith(p) for p in _ZONE_SOURCE_PREFIXES)


def root_source(f: "Feat", by_slug: dict[str, "Feat"]) -> str:
    """The provenance a polygon was drawn with — an inheriting
    sub-denomination reports its parent's."""
    src = f.geom_source
    hops = 0
    while src in _INHERITING_SOURCES and f.parent in by_slug and hops < 4:
        f = by_slug[f.parent]
        src = f.geom_source
        hops += 1
    return src


def classify(ov: "Overlap", src_a: str, src_b: str, thin_km: float) -> str:
    """One of CLASSES for a sliver (see the module docstring)."""
    a, b = ov.a, ov.b
    if a.country != b.country:
        return "border" if ov.eff_width_km < thin_km else "suspicious"
    if _tier(a.kind) != _tier(b.kind):
        return "tier"
    if ov.eff_width_km < thin_km and src_a != src_b:
        return "generalisation"
    if is_zone_source(src_a) and is_zone_source(src_b):
        return "source"
    return "suspicious"


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
    ap.add_argument(
        "--thin-km", type=float, default=0.3,
        help="a sliver narrower than this (2·area/perimeter) between two countries "
             "or two geometry sources is a digitisation band, not a commune",
    )
    ap.add_argument("--json", type=Path, help="write every sliver (all classes + accepted) here")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    if not args.geojson.exists():
        print(f"error: {args.geojson} missing — run scripts/04_build_maps.py",
              file=sys.stderr)
        return 2

    overrides = load_overrides(OVERRIDES_PATH)

    # ---- load -------------------------------------------------------------
    print(f"loading {_display(args.geojson)} …", file=sys.stderr)
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

    # ---- classify: only the last class is an artefact we could fix ------
    by_slug = {f.slug: f for f in feats}
    classes: dict[str, list[tuple[Overlap, int]]] = {c: [] for c in CLASSES}
    class_of: dict[frozenset, str] = {}
    for ov, extra in suspicious:
        cls = classify(ov, root_source(ov.a, by_slug), root_source(ov.b, by_slug), args.thin_km)
        classes[cls].append((ov, extra))
        class_of[frozenset((ov.a.slug, ov.b.slug))] = cls
    suspicious = classes["suspicious"]

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
    print(f"source     : {_display(args.geojson)} ({len(feats)} appellations)")
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

    expected_titles = {
        "border": f"BORDER — two national layers along a state border, < {args.thin_km:g} km wide",
        "tier": "TIER — a PGI / IGP or spirit-drink GI over a PDO / AOC of the same country",
        "generalisation": f"GENERALISATION — same tier, two geometry sources, < {args.thin_km:g} km wide",
        "source": "SOURCE-DRAWN — same tier, both polygons from an official zone layer or Bétard",
    }
    for cls in ("border", "tier", "generalisation", "source"):
        rows_c = classes[cls]
        print(f"{expected_titles[cls]}  [{len(rows_c)}]")
        for ov, extra in rows_c:
            print(_fmt(ov, extra))
        print()

    cross = [t for t in suspicious if t[0].a.country != t[0].b.country]
    same = [t for t in suspicious if t[0].a.country == t[0].b.country]
    print(f"SUSPICIOUS — same tier, a commune list of ours on at least one side  "
          f"[{len(suspicious)}]")
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

    if args.json:
        def _row(ov: Overlap, extra: int, reason: str | None) -> dict:
            return {
                "a": {"slug": ov.a.slug, "name": ov.a.name, "country": ov.a.country,
                      "kind": ov.a.kind, "region": ov.a.region, "geom_source": ov.a.geom_source,
                      "area_km2": round(ov.a.area / 1e6, 2)},
                "b": {"slug": ov.b.slug, "name": ov.b.name, "country": ov.b.country,
                      "kind": ov.b.kind, "region": ov.b.region, "geom_source": ov.b.geom_source,
                      "area_km2": round(ov.b.area / 1e6, 2)},
                "overlap_km2": round(ov.area_km2, 3), "share_a": round(ov.share_a, 4),
                "share_b": round(ov.share_b, 4), "eff_width_km": round(ov.eff_width_km, 3),
                "extra_pairs": extra, "accepted": reason is not None, "reason": reason,
            }
        rows = []
        for cls in CLASSES:
            for ov, extra in classes[cls]:
                rows.append({**_row(ov, extra, None), "class": cls})
        rows += [{**_row(ov, extra, reason), "class": "accepted"} for ov, extra, reason in accepted]
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"\nrows → {_display(args.json)}")

    print()
    print("SUMMARY")
    print("-" * 78)
    print(f"  suspicious slivers  : {len(suspicious)}  "
          f"({len(cross)} cross-country, {len(same)} same-country)")
    print("  expected slivers    : " + ", ".join(
        f"{len(classes[c])} {c}" for c in ("border", "tier", "generalisation", "source")))
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
