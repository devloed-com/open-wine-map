#!/usr/bin/env python3
"""Audit the generalised vineyard footprints the map draws below the detail
zoom (scripts/_lib/vineyard_envelope.py) against the parcels they generalise.

Reads the two built GeoJSONs — `wiki/map-data/appellations.geojson` (the
parcels) and `wiki/map-data/appellations-overview.geojson` (what is drawn
below the detail zoom) — and checks, per French parcel-level record:

  parity        the record exists in both zoom bands (else it vanishes on one
                side of the detail zoom, silently);
  containment   the parcels lie inside the footprint (a closing only ever adds
                area; the corner shave of a polygonal buffer is bounded by
                `containment_tolerance_m`) — reported as km² of parcels outside;
  bbox          the footprint's bbox stays within the parcels' bbox + radius;
  inflation     footprint area / parcel area (the corpus maximum at 250 m is
                ~2.4×; more means something wide was bridged);
  bridging      how much of the AREA THE FOOTPRINT ADDS (footprint − parcels)
                lies on another appellation's parcels. Umbrella appellations
                whose parcels contain this record's (Bourgogne over Chablis,
                Haut-Médoc over Pauillac — ≥ 90 % of the record's parcels) and
                the record's own parent / children are not "other": their
                ground is legitimately shared. What remains is a real bridge
                across a neighbour, worst first.
  --water       km² of IGN BD TOPO `surface_hydrographique` (every nature,
                including `Ecoulement naturel` — rivers) inside the added area,
                fetched per record from the Géoplateforme WFS and cached under
                raw/ign/bdtopo-hydro/. The closing bridges any water narrower
                than 2r between parcels on both banks; this is the measurement.

Read-only. `--strict` exits non-zero on a parity / containment / bbox failure
or a bridge above `--bridge-max`. The build already gates parity and bbox
(stage 04); this audit is the full picture, run it after every stage-04 build
that touches the geometry.

    .venv/bin/python scripts/audit_vineyard_envelopes.py
    .venv/bin/python scripts/audit_vineyard_envelopes.py --water --top 30
    .venv/bin/python scripts/audit_vineyard_envelopes.py --strict --json tmp/envelopes.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.vineyard_envelope import (  # noqa: E402
    ENVELOPE_GEOM_SOURCE,
    ENVELOPE_RADIUS_M,
    ENVELOPE_SIMPLIFY_M,
    containment_tolerance_m,
)
from audit_geometry_outliers import stream_features  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DETAIL_GEOJSON = ROOT / "wiki" / "map-data" / "appellations.geojson"
OVERVIEW_GEOJSON = ROOT / "wiki" / "map-data" / "appellations-overview.geojson"
HYDRO_CACHE = ROOT / "raw" / "ign" / "bdtopo-hydro"

WFS = "https://data.geopf.fr/wfs/ows?"
WFS_LAYER = "BDTOPO_V3:surface_hydrographique"
UA = {"User-Agent": "open-wine-map/1.0 (winemap@devloed.com)"}

_to_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform


def _km2(g) -> float:
    return float(g.area) / 1e6 if g is not None and not g.is_empty else 0.0


def _valid(g):
    return g if g.is_valid else shapely.make_valid(g)


def _clip(g, bounds):
    """clip_by_rect can emit self-touching rings; repair before any overlay."""
    return _valid(shapely.clip_by_rect(g, *bounds))


def _inter_km2(a, b) -> float:
    try:
        return _km2(a.intersection(b))
    except shapely.errors.GEOSException:
        return _km2(_valid(a).intersection(_valid(b)))


def _load_fr(path: Path, keep_sources: set[str] | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for feat in stream_features(path):
        p = feat.get("properties") or {}
        if (p.get("country") or "fr") != "fr":
            continue
        if keep_sources is not None and p.get("geom_source") not in keep_sources:
            continue
        out[p["slug"]] = {
            "props": p,
            "geom": _valid(shp_transform(_to_3035, shape(feat["geometry"]))),
        }
    return out


def _water_for_bbox(bounds4326: tuple[float, float, float, float]) -> list[dict]:
    """BD TOPO water surfaces intersecting a WGS84 bbox, cached by bbox digest."""
    key = hashlib.sha1(",".join(f"{v:.4f}" for v in bounds4326).encode()).hexdigest()[:16]
    cache = HYDRO_CACHE / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())["features"]
    minx, miny, maxx, maxy = bounds4326
    feats: list[dict] = []
    start = 0
    while True:
        q = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAME": WFS_LAYER, "OUTPUTFORMAT": "application/json",
            "COUNT": "1000", "STARTINDEX": str(start), "SRSNAME": "EPSG:4326",
            "CQL_FILTER": f"BBOX(geometrie,{minx},{miny},{maxx},{maxy},'EPSG:4326')",
        }
        req = urllib.request.Request(WFS + urllib.parse.urlencode(q), headers=UA)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    d = json.load(resp)
                break
            except Exception as exc:  # network hiccup: back off and retry
                print(f"[water] retry {attempt} {exc!r}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"[water] gave up on bbox {bounds4326}")
        page = d.get("features", [])
        feats += page
        if len(page) < 1000:
            break
        start += 1000
    HYDRO_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return feats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", type=Path, default=DETAIL_GEOJSON)
    ap.add_argument("--overview", type=Path, default=OVERVIEW_GEOJSON)
    ap.add_argument("--water", action="store_true", help="also measure BD TOPO water inside the added area (network, cached)")
    ap.add_argument("--only", action="append", default=[], help="slug substring filter (repeatable)")
    ap.add_argument("--top", type=int, default=15, help="rows per worst-first table")
    ap.add_argument("--bridge-max", type=float, default=0.05, help="--strict fails above this bridge share of the footprint")
    ap.add_argument("--ratio-warn", type=float, default=3.0)
    ap.add_argument("--json", type=Path, help="write every per-record row here")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    for path in (args.detail, args.overview):
        if not path.exists():
            sys.exit(f"missing {path} — run scripts/04_build_maps.py")

    t0 = time.perf_counter()
    detail = _load_fr(args.detail, None)
    overview = _load_fr(args.overview, {ENVELOPE_GEOM_SOURCE})
    print(
        f"[load] {len(detail)} FR detail polygons, {len(overview)} footprints "
        f"({time.perf_counter() - t0:.0f} s)",
        file=sys.stderr,
    )
    only = [s.lower() for s in args.only]
    slugs = [s for s in overview if not only or any(o in s for o in only)]

    # Parity: every French parcel-level record has a footprint and vice versa.
    parcel_level = {s for s, d in detail.items() if d["props"].get("geom_source") in ("parcellaire", "parcellaire-dgc")}
    no_footprint = sorted(parcel_level - set(overview))
    orphan = sorted(set(overview) - set(detail))

    # Bridging index: every FR parcel-level record's parcels.
    idx_slugs = sorted(parcel_level)
    tree = STRtree([detail[s]["geom"] for s in idx_slugs])
    tol = containment_tolerance_m()
    bbox_slack = ENVELOPE_RADIUS_M + ENVELOPE_SIMPLIFY_M + 5.0

    rows: list[dict] = []
    for i, slug in enumerate(slugs):
        env = overview[slug]["geom"]
        parcels = detail[slug]["geom"] if slug in detail else None
        if parcels is None:
            continue
        p = detail[slug]["props"]
        outside = _km2(parcels.difference(_valid(env.buffer(tol))))
        eminx, eminy, emaxx, emaxy = env.bounds
        pminx, pminy, pmaxx, pmaxy = parcels.bounds
        bbox_ok = (
            eminx >= pminx - bbox_slack and eminy >= pminy - bbox_slack
            and emaxx <= pmaxx + bbox_slack and emaxy <= pmaxy + bbox_slack
        )
        added = _valid(env.difference(parcels))
        added_km2 = _km2(added)
        ratio = env.area / parcels.area if parcels.area > 0 else 1.0
        # Bridging onto other appellations' parcels.
        bridges: list[tuple[str, float]] = []
        bridge_km2 = 0.0
        if added_km2 > 0:
            others = []
            for j in tree.query(added, predicate="intersects").tolist():
                other = idx_slugs[j]
                if other == slug:
                    continue
                op = detail[other]["props"]
                if op.get("parent_slug") == slug or p.get("parent_slug") == other:
                    continue
                og = detail[other]["geom"]
                clipped = _clip(og, added.bounds)
                if clipped.is_empty:
                    continue
                # An appellation whose parcels cover at least half of this
                # record's shares its ground (a regional over a village, a
                # VDN over a table-wine AOC on the same slopes) — not a bridge.
                shared = _inter_km2(_clip(og, parcels.bounds), parcels)
                if parcels.area > 0 and shared / _km2(parcels) >= 0.5:
                    continue
                b = _inter_km2(clipped, added)
                if b > 0.005:
                    bridges.append((other, b))
                    others.append(_valid(clipped))
            # The total is the UNION of the neighbours' parcels inside the
            # added area — overlapping neighbours (a climat under its village
            # AOC) must not be summed twice.
            if others:
                bridge_km2 = _inter_km2(_valid(shapely.union_all(others)), added)
        bridges.sort(key=lambda t: -t[1])
        row = {
            "slug": slug,
            "parts": p.get("parts"),
            "parcels_km2": round(_km2(parcels), 3),
            "footprint_km2": round(_km2(env), 3),
            "ratio": round(ratio, 3),
            "outside_km2": round(outside, 4),
            "bbox_ok": bbox_ok,
            "added_km2": round(added_km2, 3),
            "bridge_km2": round(bridge_km2, 3),
            "bridge_share": round(bridge_km2 / _km2(env), 4) if env.area > 0 else 0.0,
            "bridges": [(o, round(b, 3)) for o, b in bridges[:5]],
        }
        if args.water and added_km2 > 0:
            env4326 = shape(json.loads(shapely.to_geojson(shp_transform(
                Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True).transform, env))))
            water_feats = _water_for_bbox(env4326.bounds)
            by_nature: dict[str, float] = {}
            for wf in water_feats:
                try:
                    wg = shp_transform(_to_3035, shape(wf["geometry"]))
                except Exception:
                    continue
                if not wg.intersects(added):
                    continue
                nature = (wf.get("properties") or {}).get("nature") or "?"
                by_nature[nature] = by_nature.get(nature, 0.0) + _inter_km2(_valid(wg), added)
            row["water_km2"] = round(sum(by_nature.values()), 3)
            row["water_by_nature"] = {k: round(v, 3) for k, v in sorted(by_nature.items(), key=lambda kv: -kv[1]) if v > 0.001}
        rows.append(row)
        if (i + 1) % 100 == 0:
            print(f"[audit] {i + 1}/{len(slugs)} ({time.perf_counter() - t0:.0f} s)", file=sys.stderr)

    # ---- report ----
    print(f"\n# Vineyard footprints — r = {ENVELOPE_RADIUS_M} m, {len(rows)} records audited\n")
    print(f"parity: {len(no_footprint)} parcel-level record(s) without a footprint {no_footprint[:10]}; "
          f"{len(orphan)} footprint(s) without a detail record {orphan[:10]}")
    bad_contain = [r for r in rows if r["outside_km2"] > 0.001]
    bad_bbox = [r for r in rows if not r["bbox_ok"]]
    print(f"containment: {len(bad_contain)} record(s) with parcels outside the footprint "
          f"(tolerance {tol:.0f} m)" + (f": {[(r['slug'], r['outside_km2']) for r in bad_contain[:10]]}" if bad_contain else ""))
    print(f"bbox: {len(bad_bbox)} record(s) leave their parcels' bbox + {bbox_slack:.0f} m"
          + (f": {[r['slug'] for r in bad_bbox[:10]]}" if bad_bbox else ""))
    ratios = sorted(r["ratio"] for r in rows)
    if ratios:
        print(f"inflation (footprint / parcels): median {ratios[len(ratios)//2]:.2f}× · "
              f"p90 {ratios[int(len(ratios)*0.9)]:.2f}× · max {ratios[-1]:.2f}× · "
              f"{sum(1 for x in ratios if x > args.ratio_warn)} above {args.ratio_warn}×")

    def table(title: str, key: str, fmt, n: int) -> None:
        print(f"\n## {title}\n")
        print("| slug | parts | parcels km² | footprint km² | ratio | " + fmt[0] + " |")
        print("|---|---:|---:|---:|---:|---|")
        for r in sorted(rows, key=lambda r: -(r.get(key) or 0))[:n]:
            print(f"| {r['slug']} | {r['parts']} | {r['parcels_km2']:.1f} | {r['footprint_km2']:.1f} | {r['ratio']:.2f} | {fmt[1](r)} |")

    table("Largest inflation", "ratio", ("added km²", lambda r: f"{r['added_km2']:.1f}"), args.top)
    table(
        "Worst bridging onto a neighbour's parcels (share of the footprint)",
        "bridge_share",
        ("bridge km² · share · onto", lambda r: f"{r['bridge_km2']:.2f} · {100*r['bridge_share']:.1f} % · " + ", ".join(f"{o} {b:.2f}" for o, b in r["bridges"][:3])),
        args.top,
    )
    if args.water:
        table(
            "Most water in the added area (BD TOPO surface_hydrographique)",
            "water_km2",
            ("water km² · by nature", lambda r: f"{r.get('water_km2', 0):.2f} · " + ", ".join(f"{k} {v:.2f}" for k, v in (r.get("water_by_nature") or {}).items())),
            args.top,
        )
        wtotal = sum(r.get("water_km2", 0.0) for r in rows)
        print(f"\nwater in added area, corpus total: {wtotal:.1f} km² over "
              f"{sum(1 for r in rows if r.get('water_km2', 0) > 0.05)} record(s) with > 0.05 km²")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"\nrows → {args.json}")

    over_bridge = [r for r in rows if r["bridge_share"] > args.bridge_max]
    failed = bool(no_footprint or orphan or bad_contain or bad_bbox or over_bridge)
    if args.strict and failed:
        print(f"\nSTRICT: {len(no_footprint)} missing, {len(orphan)} orphan, {len(bad_contain)} containment, "
              f"{len(bad_bbox)} bbox, {len(over_bridge)} bridge > {args.bridge_max:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
