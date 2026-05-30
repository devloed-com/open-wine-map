"""Audit HU pipeline coverage.

Prints extraction status per kind, stub reasons, Figshare + PGI-union
geometry coverage, grape extraction, and a curator queue for any wine
whose single document could not be fetched. Mirrors
`audit_hr_coverage.py` for the Hungarian corpus.

Run: `.venv/bin/python scripts/audit_hu_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EAMBROSIA = ROOT / "raw" / "hu" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "hu" / "dokumentumok-extracted"
OJ_MANIFEST = ROOT / "raw" / "hu" / "oj-pages" / "manifest.json"
OVERRIDES = ROOT / "raw" / "hu" / "oj-pages" / "manual_overrides.json"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"

sys.path.insert(0, str(ROOT / "scripts"))
from _lib.hu.geometry import HU_PGI_MEMBER_PDOS  # noqa: E402


def _load_eambrosia() -> list[dict]:
    if not EAMBROSIA.exists():
        return []
    return json.loads(EAMBROSIA.read_text(encoding="utf-8"))["wines"]


def _load_extracted() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not EXTRACTED.exists():
        return out
    for jp in EXTRACTED.glob("*.json"):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        out[rec["slug"]] = rec
    return out


def _load_manifest() -> dict[str, dict]:
    if not OJ_MANIFEST.exists():
        return {}
    try:
        return json.loads(OJ_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
    except (ValueError, OSError):
        return {}


def _load_overrides() -> dict[str, dict]:
    if not OVERRIDES.exists():
        return {}
    try:
        return json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _load_figshare_file_numbers() -> set[str]:
    if not FIGSHARE.exists():
        return set()
    try:
        import geopandas as gpd
        gdf = gpd.read_file(FIGSHARE)
        return set(
            fn for fn in gdf["PDOid"].astype(str).tolist()
            if fn and fn.startswith(("PDO-HU", "PGI-HU"))
        )
    except ImportError:
        return set()


# Bétard mis-labels PGI-HU-A1507 (Balaton PGI) as PDO-HU-A1507; we accept
# that bridge in the geometry resolver and in this audit.
_BÉTARD_BRIDGE = {"PGI-HU-A1507": "PDO-HU-A1507"}


def main() -> int:
    wines = _load_eambrosia()
    extracted = _load_extracted()
    oj_manifest = _load_manifest()
    overrides = _load_overrides()
    figshare_ids = _load_figshare_file_numbers()

    print("# HU pipeline audit\n")
    print(f"eAmbrosia wines:      {len(wines)}")
    print(f"Extracted records:    {len(extracted)}")
    print(f"OJ-page manifest:     {len(oj_manifest)} entries")
    print(f"Manual overrides:     {len(overrides)} entries")
    print(f"Figshare HU PDO/PGI ids: {len(figshare_ids)}")
    print()

    by_kind_total: Counter[str] = Counter()
    by_kind_extracted: Counter[str] = Counter()
    by_kind_stub: Counter[str] = Counter()
    stub_reasons: Counter[str] = Counter()
    in_figshare = no_figshare = pgi_union_resolved = pgi_no_geom = 0
    grape_total = 0
    n_with_grapes = 0
    by_region: Counter[str] = Counter()

    for w in wines:
        slug = w["slug"]
        kind = w.get("kind", "?")
        by_kind_total[kind] += 1
        rec = extracted.get(slug)
        if rec is None:
            stub_reasons["not-yet-extracted"] += 1
            continue
        if rec.get("stub"):
            by_kind_stub[kind] += 1
            stub_reasons[rec.get("stub_reason", "unknown")] += 1
        else:
            by_kind_extracted[kind] += 1
        fn = w.get("fileNumber") or ""
        bridged = _BÉTARD_BRIDGE.get(fn, fn)
        if bridged in figshare_ids:
            in_figshare += 1
        elif fn in HU_PGI_MEMBER_PDOS:
            members = HU_PGI_MEMBER_PDOS[fn]
            resolved_members = sum(
                1 for m in members if _BÉTARD_BRIDGE.get(m, m) in figshare_ids
            )
            if resolved_members:
                pgi_union_resolved += 1
            else:
                pgi_no_geom += 1
        else:
            no_figshare += 1
        n_grapes = len((rec.get("grapes") or {}).get("details") or [])
        if n_grapes:
            n_with_grapes += 1
            grape_total += n_grapes
        by_region[rec.get("region") or "?"] += 1

    print("## By kind")
    print(f"  Total:     {dict(by_kind_total)}")
    print(f"  Extracted: {dict(by_kind_extracted)}")
    print(f"  Stubs:     {dict(by_kind_stub)}")
    print()
    print("## Stub reasons")
    for r, n in sorted(stub_reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {r}")
    if not stub_reasons:
        print("  (none — full extraction)")
    print()
    print("## Geometry coverage")
    print(f"  Bétard PDO match:      {in_figshare} of {len(wines)}")
    print(f"  PGI region-union:      {pgi_union_resolved}")
    print(f"  PGI no member geom:    {pgi_no_geom}")
    print(f"  Missing entirely:      {no_figshare}")
    total_mapped = in_figshare + pgi_union_resolved
    print(f"  → on the map:          {total_mapped} of {len(wines)} "
          f"({total_mapped/max(1,len(wines)):.1%})")
    print()
    print("## Region distribution (borrégió)")
    for b, n in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {b}")
    print()
    print("## Grape extraction")
    print(f"  Wines with grapes:  {n_with_grapes} of {len(extracted)}")
    print(f"  Total grape-slugs:  {grape_total}")
    print()

    curator_targets: list[tuple[str, str, str]] = []
    for w in wines:
        slug = w["slug"]
        rec = extracted.get(slug)
        if rec is None or not rec.get("stub"):
            continue
        if slug in overrides or w["giIdentifier"] in overrides:
            continue
        curator_targets.append((rec.get("stub_reason") or "unknown", slug,
                                 w.get("fileNumber", "")))
    curator_targets.sort()

    print(f"## Curator queue ({len(curator_targets)} stubs needing input)")
    for reason, slug, fn in curator_targets:
        print(f"  [{reason:30s}] {slug:40s} {fn}")
    if not curator_targets:
        print("  (empty — every Hungarian wine extracted)")
    print()
    # Verbatim-mode terroir-facts records — short-text liens where 02d
    # emits the source text directly (see scripts/_lib/terroir_verbatim.py).
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _lib import terroir_verbatim as _verbatim
        _vb_count, _vb_records = _verbatim.count_verbatim_records(
            Path(__file__).resolve().parent.parent / "raw" / "terroir-facts", "hu",
        )
        if _vb_count:
            print(f"## Verbatim terroir-facts records ({_vb_count} flagged for validation)")
            for _r in _vb_records:
                print(f"  {_r['slug']:42}  {_r['chars']:>4} chars  flag={_r['flag']}")
            print()
    except Exception as _exc:  # noqa: BLE001
        print(f"[warn] verbatim-records check failed: {_exc}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
