#!/usr/bin/env python3
"""Audit — IT appellation regione labels vs. their actual geography.

Some Italian DOP/IGP records carry the wrong `regione`: the old
text-scan region derivation took the first regione name appearing
anywhere in the area / terroir text, and that text routinely names a
*neighbouring* regione first. This audit is the independent geometric
check.

For every IT appellation it reverse-geocodes the resolved polygon
against Italian administrative regioni — derived from the Eurostat
GISCO LAU comuni the IT pipeline already loads (`GISCO_ID` →
ISTAT province code → regione, see `scripts/_lib/it/province.py`):

  - the polygon's **representative point** gives the primary regione;
  - the comuni the polygon overlaps give the **touched set** (a regione
    is "touched" when ≥ --touch-share of the polygon area sits in it),
    so a genuinely interregional DOP is not flagged for its secondary.

The resolved `regione` (what stages 03/04 render — the extracted
record's `regione`, or the MASAF sidecar's when the record is a
MASAF-augmented stub) is then compared:

  OK         — labelled regione is the primary, or a touched regione;
  MISMATCH   — labelled regione is neither — the misattribution bug;
  UNRESOLVED — no regione resolved at all;
  NO-GEOM    — no polygon (IGTs miss the PDO-only Figshare layer) —
               cannot be geometrically verified here.

Geometry source: Bétard 2022 `EU_PDO.gpkg` (the IT `geom_source` is
`figshare-pdo`), the same polygon stage 04 renders. Exit code is
non-zero with --strict when MISMATCHes remain.

Run: `.venv/bin/python scripts/audit_it_regions.py`
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.it.province import (  # noqa: E402
    load_comune_regione_map, regione_for_gisco_id, resolve_gisco_lau,
)
from _lib.it.region import derive_regione  # noqa: E402

EAMBROSIA = ROOT / "raw" / "it" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "it" / "disciplinari-extracted"
MASAF_EXTRACTED = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_DIR = ROOT / "raw" / "es" / "gisco"
GISCO_LAU = GISCO_DIR / "LAU_RG_01M_2024_3035.shp.zip"


def _load_eambrosia() -> list[dict]:
    if not EAMBROSIA.exists():
        return []
    return json.loads(EAMBROSIA.read_text(encoding="utf-8"))["wines"]


def _load_records(directory: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not directory.exists():
        return out
    for jp in directory.glob("*.json"):
        if jp.name.startswith("_"):
            continue
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if rec.get("slug"):
            out[rec["slug"]] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--touch-share", type=float, default=0.03,
        help="a regione counts as 'touched' when this fraction of the "
             "polygon area sits in it (default 0.03)",
    )
    ap.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when MISMATCHes remain",
    )
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    for needed in (EAMBROSIA, FIGSHARE, GISCO_LAU):
        if not needed.exists():
            print(f"error: {needed} missing — run the fetch stages first",
                  file=sys.stderr)
            return 2

    import geopandas as gpd
    from shapely.strtree import STRtree

    # ---- geometry: GISCO comuni (regione-tagged) + Figshare polygons ----
    print("loading GISCO LAU comuni …", file=sys.stderr)
    lau = gpd.read_file(GISCO_LAU)
    lau = lau[lau["CNTR_CODE"] == "IT"].to_crs("EPSG:3035")
    comune_geoms = []
    comune_regione: list[str] = []
    for gisco_id, geom in zip(lau["GISCO_ID"], lau.geometry):
        if geom is None or geom.is_empty:
            continue
        reg = regione_for_gisco_id(gisco_id or "")
        if not reg:
            continue
        comune_geoms.append(geom)
        comune_regione.append(reg)
    tree = STRtree(comune_geoms)
    print(f"  {len(comune_geoms)} IT comuni indexed", file=sys.stderr)

    print("loading Figshare PDO polygons …", file=sys.stderr)
    figs = gpd.read_file(FIGSHARE)
    figs = figs[figs["PDOid"].str.startswith(("PDO-IT", "PGI-IT"))].to_crs("EPSG:3035")
    poly_by_fn: dict[str, object] = {}
    for fn, geom in zip(figs["PDOid"], figs.geometry):
        if geom is not None and not geom.is_empty:
            poly_by_fn[fn] = geom
    print(f"  {len(poly_by_fn)} IT PDO polygons", file=sys.stderr)

    def ground_truth(geom) -> tuple[str, dict[str, float]]:
        """Return (primary regione by representative point, {regione:
        area share}) for one polygon."""
        shares: dict[str, float] = defaultdict(float)
        total = geom.area or 1.0
        for idx in tree.query(geom):
            cg = comune_geoms[int(idx)]
            if not cg.intersects(geom):
                continue
            inter = cg.intersection(geom).area
            if inter > 0:
                shares[comune_regione[int(idx)]] += inter / total
        rp = geom.representative_point()
        primary = ""
        for idx in tree.query(rp):
            if comune_geoms[int(idx)].contains(rp):
                primary = comune_regione[int(idx)]
                break
        if not primary and shares:
            primary = max(shares.items(), key=lambda kv: kv[1])[0]
        return primary, dict(shares)

    # ---- resolved regione per wine (what stages 03/04 render) ----------
    wines = _load_eambrosia()
    extracted = _load_records(EXTRACTED)
    masaf = _load_records(MASAF_EXTRACTED)

    comune_map = load_comune_regione_map(str(resolve_gisco_lau(GISCO_DIR) or ""))

    def resolved_regione(slug: str, file_number: str) -> str:
        """The regione as stages 03/04 render it: the extracted
        record's value, the MASAF sidecar's (it augments stubs), else
        the stage-04 `derive_regione` fallback (curated file-number
        map for a pure stub)."""
        rec = extracted.get(slug) or {}
        if rec.get("regione"):
            return rec["regione"]
        sidecar = masaf.get(slug) or {}
        if sidecar.get("regione"):
            return sidecar["regione"]
        geo = (rec.get("section_roles") or {}).get("geo_area", "")
        return derive_regione({"file_number": file_number}, geo,
                              rec.get("name", ""), comune_map=comune_map)

    ok = mismatch = unresolved = no_geom = subdenom = 0
    findings: list[tuple[str, str, str, str, dict]] = []

    for w in wines:
        slug = w["slug"]
        fn = w.get("fileNumber") or ""
        rec = extracted.get(slug) or {}
        if rec.get("is_sub_denomination"):
            subdenom += 1
            continue
        geom = poly_by_fn.get(fn)
        labelled = resolved_regione(slug, fn)
        if geom is None:
            no_geom += 1
            continue
        primary, shares = ground_truth(geom)
        touched = {r for r, s in shares.items() if s >= args.touch_share}
        if primary:
            touched.add(primary)
        if not labelled:
            unresolved += 1
            findings.append(("UNRESOLVED", slug, fn, primary, shares))
        elif labelled == primary or labelled in touched:
            ok += 1
        else:
            mismatch += 1
            findings.append(("MISMATCH", slug, fn, primary, shares))

    # ---- report --------------------------------------------------------
    print()
    print("IT REGIONE AUDIT")
    print("=" * 78)
    print("geometry   : Bétard 2022 EU_PDO.gpkg · GISCO LAU 2024 comuni")
    print(f"touch rule : a regione is 'touched' at >= {args.touch_share:.0%} "
          f"of the polygon area")
    print(f"checked    : {ok + mismatch + unresolved} IT appellations with a "
          f"polygon  ({no_geom} without — IGT/no-Figshare, unverifiable; "
          f"{subdenom} sub-denominations skipped)")
    print()

    def _shares_str(shares: dict[str, float]) -> str:
        top = sorted(shares.items(), key=lambda kv: -kv[1])[:3]
        return ", ".join(f"{r} {s:.0%}" for r, s in top) or "(none)"

    bad = [f for f in findings if f[0] == "MISMATCH"]
    print(f"MISMATCH — labelled regione is not where the polygon sits  [{len(bad)}]")
    for _tag, slug, fn, primary, shares in sorted(bad, key=lambda f: f[1]):
        labelled = resolved_regione(slug, fn)
        print(f"  {slug:42s} {fn:14s}")
        print(f"      labelled : {labelled}")
        print(f"      polygon  : {primary or '?'}   "
              f"[{_shares_str(shares)}]")
    print()

    unres = [f for f in findings if f[0] == "UNRESOLVED"]
    if unres:
        print(f"UNRESOLVED — no regione resolved (polygon shown for reference)  "
              f"[{len(unres)}]")
        for _tag, slug, fn, primary, shares in sorted(unres, key=lambda f: f[1]):
            print(f"  {slug:42s} {fn:14s}  polygon: {primary or '?'}")
        print()

    print("SUMMARY")
    print("-" * 78)
    print(f"  ok          : {ok}")
    print(f"  mismatch    : {mismatch}")
    print(f"  unresolved  : {unresolved}")
    print(f"  no-geometry : {no_geom}  (IGT / not in Figshare — not checked)")
    print()
    if args.strict and mismatch:
        print("RESULT: FAIL (--strict) — regione mismatches remain")
        return 1
    print("RESULT: ok" if not mismatch
          else "RESULT: ok — review the mismatches above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
