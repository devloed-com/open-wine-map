"""Detector for appellations that span several regions of their country's
sidebar hierarchy but are not listed under each — the region level of the
listing rule of 2026-10-25: a record that spans several branches is listed
under each (`country_aliases` for countries, `co_parents` for parent
appellations, `region_aliases` for regions — scripts/_lib/region_aliases.py).

A region's footprint is the union of the drawn polygons of its own PDO / AOC
parents — never a PGI (a region holding PGIs only, Österreich or a German
Bundesland, has no footprint), nor an umbrella PDO (one holding two or more other PDOs:
Delle Venezie, Garda, the Bourgogne regionals), which would feed its whole
area into the footprint of the one region it is filed under. A record spans
region R when at least `--min-km2` of it lies in R's footprint and that is
`--min-share` of the record or `--min-cover` of R's footprint (an umbrella
IGP over a region drawn as parcels). FR's ARMAGNAC bucket is neither source
nor target (region_aliases.FR_EXCLUDED).

Status per candidate: ACCEPTED (the build lists the record under R — its
`region_aliases`, a co-parent's region), REJECTED (the table's `rejected`
section says why it is not a second region) or NEW (the review queue). There
is no reverse check: an alias the table cites from the record's own text
(Jumilla's Albacete municipalities, Cava's Badajoz) need not overlap a PDO of
the alias region, and the FR aliases come from shared aire communes, not
from polygons; tests/test_region_aliases.py checks the quotes.

Usage:
  .venv/bin/python scripts/sweep_region_aliases.py [--country it] [--json PATH] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.region_aliases import FR_EXCLUDED, load_table  # noqa: E402

OVERVIEW = ROOT / "wiki" / "map-data" / "appellations-overview.geojson"
DATA = ROOT / "wiki" / "data"


def built_regions() -> dict[str, set[str]]:
    """slug → the regions the build lists the record under beside its own
    (its `region_aliases`, its co-parents' regions)."""
    blobs = sorted(DATA.glob("aocs.en.*.js"))
    if not blobs:
        return {}
    txt = blobs[-1].read_text(encoding="utf-8")
    aocs = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])["aocs"]
    out: dict[str, set[str]] = defaultdict(set)
    for slug, rec in aocs.items():
        out[slug].update(rec.get("region_aliases") or [])
        for cp in rec.get("co_parents") or []:
            if cp in aocs and aocs[cp].get("region"):
                out[slug].add(aocs[cp]["region"])
        out[slug].discard(rec.get("region") or "")
    return out


def _umbrellas(pdo: gpd.GeoDataFrame, contain: float = 0.8) -> set[str]:
    """PDOs that hold at least two other PDOs (≥ `contain` of each one's area)."""
    from shapely.strtree import STRtree
    geoms = list(pdo.geometry)
    slugs = list(pdo["slug"])
    tree = STRtree(geoms)
    out: set[str] = set()
    for i, g in enumerate(geoms):
        held = 0
        for j in tree.query(g):
            if j == i or geoms[j].area <= 0 or geoms[j].area >= g.area:
                continue
            if g.intersection(geoms[j]).area / geoms[j].area >= contain:
                held += 1
                if held >= 2:
                    out.add(slugs[i])
                    break
    return out


def sweep(countries: set[str] | None, min_share: float, min_km2: float, min_cover: float = 0.25) -> list[dict]:
    gdf = gpd.read_file(OVERVIEW)
    gdf = gdf[gdf["is_sub_denomination"].astype(str) != "1"]
    if countries:
        gdf = gdf[gdf["country"].isin(countries)]
    gdf = gdf.to_crs("EPSG:3035")
    gdf["geometry"] = gdf.geometry.buffer(0).simplify(50)
    rows: list[dict] = []
    for cc, part in gdf.groupby("country"):
        wine = part[(part["is_wine"].astype(str) != "0") & (part["region"] != "")]
        pdo = wine[wine["kind"] != "IGP"]
        umbrellas = _umbrellas(pdo)
        core = pdo[~pdo["slug"].isin(umbrellas)]
        footprints = {r: unary_union(list(g.geometry)) for r, g in core.groupby("region")}
        if cc == "fr":
            footprints = {r: fp for r, fp in footprints.items() if r not in FR_EXCLUDED}
        for _, rec in part.iterrows():
            geom = rec.geometry
            if geom is None or geom.is_empty or geom.area <= 0:
                continue
            if cc == "fr" and rec["region"] in FR_EXCLUDED:
                continue
            for region, fp in footprints.items():
                if region == rec["region"] or not fp.intersects(geom):
                    continue
                inter = fp.intersection(geom).area
                share = inter / geom.area
                covers = inter / fp.area if fp.area else 0.0
                # the record lies partly in R, or covers a good part of R's
                # vineyards (an umbrella IGP over a region drawn as parcels)
                if inter / 1e6 >= min_km2 and (share >= min_share or covers >= min_cover):
                    rows.append({
                        "slug": rec["slug"], "country": cc, "name": rec["name"], "kind": rec["kind"],
                        "region": rec["region"], "spans": region,
                        "share": round(share, 3), "covers": round(covers, 3), "km2": round(inter / 1e6, 1),
                    })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--min-share", type=float, default=0.10)
    ap.add_argument("--min-km2", type=float, default=20.0)
    ap.add_argument("--min-cover", type=float, default=0.25,
                    help="or the record covers at least this share of R's footprint")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--strict", action="store_true", help="exit 1 on a NEW row")
    args = ap.parse_args()

    found = sweep(set(args.country) if args.country else None, args.min_share, args.min_km2, args.min_cover)
    rejected = load_table()["rejected"]
    listed = built_regions()
    for r in found:
        if r["spans"] in listed.get(r["slug"], set()):
            r["status"] = "ACCEPTED"
        elif r["spans"] in (rejected.get(r["slug"]) or {}):
            r["status"] = "REJECTED"
            r["reason"] = rejected[r["slug"]][r["spans"]]
        else:
            r["status"] = "NEW"

    for status in ("NEW", "REJECTED", "ACCEPTED"):
        rows = [r for r in found if r["status"] == status]
        print(f"\n{status} [{len(rows)}]")
        for r in sorted(rows, key=lambda r: (r["country"], r["slug"], -r["share"])):
            print(f"  {r['country']} {r['slug']:42} {r['kind']:4} {r['region'] or '—':28} → {r['spans']:28} "
                  f"{r['share']:6.1%} cov {r['covers']:6.1%} {r['km2']:8.1f} km²")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"rows": found}, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
    n_new = sum(1 for r in found if r["status"] == "NEW")
    if args.strict and n_new:
        print(f"\nSTRICT: {n_new} new", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
