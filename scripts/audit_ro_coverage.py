"""Audit RO pipeline coverage.

Prints extraction status per kind, stub reasons, Figshare geometry
coverage, commune-list coverage for IGPs, grape extraction, region
distribution, and a curator queue for any wine whose single document
could not be fetched. Mirrors `audit_hr_coverage.py` for the Romanian
corpus, with the IGP commune-list section added.

Run: `.venv/bin/python scripts/audit_ro_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EAMBROSIA = ROOT / "raw" / "ro" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "ro" / "dokumente-extracted"
OJ_MANIFEST = ROOT / "raw" / "ro" / "oj-pages" / "manifest.json"
OVERRIDES = ROOT / "raw" / "ro" / "oj-pages" / "manual_overrides.json"
NATIONAL_SPECS = ROOT / "raw" / "ro" / "national-specs-extracted"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"


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


def _load_national_specs() -> dict[str, dict]:
    """slug → ONVPV caiet-de-sarcini sidecar (stage 02f). These augment
    the on-disk DOCUMENT UNIC stubs in stage 04."""
    out: dict[str, dict] = {}
    if not NATIONAL_SPECS.exists():
        return out
    for jp in NATIONAL_SPECS.glob("*.json"):
        if jp.name.startswith("_"):
            continue
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
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
            if fn and (fn.startswith("PDO-RO") or fn.startswith("PGI-RO"))
        )
    except ImportError:
        return set()


def main() -> int:
    wines = _load_eambrosia()
    extracted = _load_extracted()
    oj_manifest = _load_manifest()
    overrides = _load_overrides()
    national_specs = _load_national_specs()
    figshare_ids = _load_figshare_file_numbers()

    print("# RO pipeline audit\n")
    print(f"eAmbrosia wines:      {len(wines)}")
    print(f"Extracted records:    {len(extracted)}")
    print(f"OJ-page manifest:     {len(oj_manifest)} entries")
    print(f"Manual overrides:     {len(overrides)} entries")
    print(f"National-spec (caiet) sidecars: {len(national_specs)}")
    print(f"Figshare RO PDOids:   {len(figshare_ids)}")
    print()

    by_kind_total: Counter[str] = Counter()
    by_kind_extracted: Counter[str] = Counter()
    by_kind_stub: Counter[str] = Counter()
    stub_reasons: Counter[str] = Counter()
    in_figshare = no_figshare = 0
    grape_total = 0
    n_with_grapes = 0
    by_region: Counter[str] = Counter()
    # Commune-list coverage: how many non-Figshare wines have a
    # geo_communes list that the resolver will use.
    n_communes_total = 0
    n_with_communes = 0
    n_igp_missing_communes = 0
    n_national_spec = 0

    for w in wines:
        slug = w["slug"]
        kind = w.get("kind", "?")
        by_kind_total[kind] += 1
        rec = extracted.get(slug)
        if rec is None:
            stub_reasons["not-yet-extracted"] += 1
            continue
        # A DOCUMENT UNIC stub augmented by the ONVPV caiet de sarcini
        # (stage 02f) is effectively covered — stage 04 merges its grapes /
        # communes / terroir at load time. Count grapes + communes from the
        # sidecar and keep it out of the stub / curator buckets.
        spec = national_specs.get(slug) if rec.get("stub") else None
        if rec.get("stub") and not spec:
            by_kind_stub[kind] += 1
            stub_reasons[rec.get("stub_reason", "unknown")] += 1
        elif spec:
            n_national_spec += 1
            by_kind_extracted[kind] += 1
        else:
            by_kind_extracted[kind] += 1
        eff = spec or rec
        fn = w.get("fileNumber") or ""
        if fn in figshare_ids:
            in_figshare += 1
        else:
            no_figshare += 1
            if kind == "IGP" and not (eff.get("geo_communes") or []):
                n_igp_missing_communes += 1
        n_grapes = len((eff.get("grapes") or {}).get("details") or [])
        if n_grapes:
            n_with_grapes += 1
            grape_total += n_grapes
        communes = eff.get("geo_communes") or []
        if communes:
            n_with_communes += 1
            n_communes_total += len(communes)
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
    print("## Geometry coverage (Bétard 2022)")
    print(f"  In Figshare:           {in_figshare} of {len(wines)} "
          f"({in_figshare/max(1,len(wines)):.1%})")
    print(f"  Missing from Figshare: {no_figshare} "
          f"(expected: ~16 = 13 IGPs + 3 newer PDOs)")
    print()
    print("## IGP commune-list coverage (gisco-commune-list fallback)")
    print(f"  Wines with geo_communes: {n_with_communes} of {len(extracted)}")
    print(f"  Total commune-name candidates: {n_communes_total}")
    print(f"  IGPs missing Bétard AND geo_communes: {n_igp_missing_communes} "
          f"(stub-no-geometry — need curator URL or commune-list parser tuning)")
    print()
    print("## Region distribution")
    for b, n in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {b}")
    print()
    print("## Grape extraction")
    print(f"  Wines with grapes:  {n_with_grapes} of {len(extracted)}")
    print(f"  Total grape-slugs:  {grape_total}")
    print()
    print("## National-spec coverage (ONVPV caiet de sarcini, stage 02f)")
    print(f"  DOCUMENT UNIC stubs augmented: {n_national_spec} of "
          f"{len(national_specs)} sidecars")
    print("  (these are effectively covered — stage 04 merges grapes / "
          "communes / terroir at load time)")
    print()

    curator_targets: list[tuple[str, str, str]] = []
    for w in wines:
        slug = w["slug"]
        rec = extracted.get(slug)
        if rec is None or not rec.get("stub"):
            continue
        if slug in national_specs:
            continue  # covered by the ONVPV caiet de sarcini
        if slug in overrides or w["giIdentifier"] in overrides:
            continue
        curator_targets.append((rec.get("stub_reason") or "unknown", slug,
                                 w.get("fileNumber", "")))
    curator_targets.sort()

    print(f"## Curator queue ({len(curator_targets)} stubs needing input)")
    for reason, slug, fn in curator_targets:
        print(f"  [{reason:30s}] {slug:40s} {fn}")
    if not curator_targets:
        print("  (empty — every Romanian wine extracted)")
    print()
    # Verbatim-mode terroir-facts records — short-text liens where 02d
    # emits the source text directly (see scripts/_lib/terroir_verbatim.py).
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _lib import terroir_verbatim as _verbatim
        _vb_count, _vb_records = _verbatim.count_verbatim_records(
            Path(__file__).resolve().parent.parent / "raw" / "terroir-facts", "ro",
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
