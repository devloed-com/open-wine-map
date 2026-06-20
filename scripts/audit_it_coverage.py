"""Audit IT pipeline coverage.

Prints a per-record table of stub status, geometry source, grape count,
sottozona count, and surfaces wines that need curator input
(no-publication, fetch-error). Mirrors `scripts/audit_es_coverage.py`
for the IT corpus.

Run: `.venv/bin/python scripts/audit_it_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
EAMBROSIA = ROOT / "raw" / "it" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "it" / "disciplinari-extracted"
OJ_MANIFEST = ROOT / "raw" / "it" / "oj-pages" / "manifest.json"
OVERRIDES = ROOT / "raw" / "it" / "oj-pages" / "manual_overrides.json"
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
            fn for fn in gdf["PDOid"].tolist()
            if fn and fn.startswith(("PDO-IT", "PGI-IT"))
        )
    except ImportError:
        return set()


def main() -> int:
    wines = _load_eambrosia()
    extracted = _load_extracted()
    oj_manifest = _load_manifest()
    overrides = _load_overrides()
    figshare_ids = _load_figshare_file_numbers()

    print("# IT pipeline audit\n")
    print(f"eAmbrosia wines:      {len(wines)}")
    print(f"Extracted records:    {len(extracted)} (parents + sottozone)")
    print(f"OJ-page manifest:     {len(oj_manifest)} entries")
    print(f"Manual overrides:     {len(overrides)} entries")
    print(f"Figshare IT PDOids:   {len(figshare_ids)}")
    print()

    # Extraction status
    by_kind_total: Counter[str] = Counter()
    by_kind_extracted: Counter[str] = Counter()
    by_kind_stub: Counter[str] = Counter()
    stub_reasons: Counter[str] = Counter()
    in_figshare = no_figshare = 0
    sottozone_count = 0
    menz_total = 0
    grape_total = 0
    n_with_grapes = 0

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
        if fn in figshare_ids:
            in_figshare += 1
        else:
            no_figshare += 1
        n_grapes = len((rec.get("grapes") or {}).get("details") or [])
        if n_grapes:
            n_with_grapes += 1
            grape_total += n_grapes
        menz_total += len(rec.get("menzioni") or [])

    for slug, rec in extracted.items():
        if rec.get("is_sub_denomination"):
            sottozone_count += 1

    print("## By kind")
    print(f"  Total:     {dict(by_kind_total)}")
    print(f"  Extracted: {dict(by_kind_extracted)}")
    print(f"  Stubs:     {dict(by_kind_stub)}")
    print()
    from importlib import import_module
    try:
        cancelled = import_module("it.00_fetch_data").CANCELLED_GIS
    except Exception:
        cancelled = {}
    if cancelled:
        print(f"## Cancelled GIs (filtered at stage 00 — {len(cancelled)})")
        for gi, meta in sorted(cancelled.items(), key=lambda kv: kv[1]["name"]):
            print(f"  {meta['name']:24} {gi}  {meta['regulation']} (eff. {meta['effective']})")
        print()
    print("## Stub reasons")
    for r, n in sorted(stub_reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {r}")
    print()
    print("## Geometry coverage (Bétard 2022)")
    print(f"  In Figshare:    {in_figshare} of {len(wines)} ({in_figshare/max(1,len(wines)):.1%})")
    print(f"  Missing from Figshare: {no_figshare}")
    print("  (Most IGTs miss Figshare — it's PDO-only. Some newer DOPs may also miss.)")
    print()
    print("## Sub-denominations + menzioni")
    print(f"  Sottozone records:      {sottozone_count}")
    print(f"  Wines with menzioni:    "
          f"{sum(1 for r in extracted.values() if r.get('menzioni'))}")
    print(f"  Total menzioni emitted: {menz_total}")
    print()
    print("## Grape extraction")
    print(f"  Wines with grapes:      {n_with_grapes} of {len(extracted)}")
    print(f"  Total grape-slugs:      {grape_total}")
    print()

    # Curator queue — wines with no extraction OR stub + no override yet
    curator_targets: list[tuple[str, str, str, str]] = []
    for w in wines:
        slug = w["slug"]
        rec = extracted.get(slug)
        if rec is None or not rec.get("stub"):
            continue
        if slug in overrides or w["giIdentifier"] in overrides:
            continue
        reason = rec.get("stub_reason") or "unknown"
        # Prioritise: fetch-error (curator URL could rescue) and
        # no-documento-unico-anchor (curator may know an alternate URL)
        # over no-publication (massive bucket — only worth showing
        # well-known DOPs).
        priority = {
            "fetch-error": 0,
            "no-documento-unico-anchor": 1,
            "not-single-document": 2,
            "no-publication": 3,
        }.get(reason, 9)
        curator_targets.append((str(priority), reason, slug, w.get("fileNumber", "")))
    curator_targets.sort()

    print(f"## Curator queue ({len(curator_targets)} stubs needing input)")
    print("Top 20 by priority:")
    for _p, reason, slug, fn in curator_targets[:20]:
        print(f"  [{reason:30s}] {slug:40s} {fn}")
    print()
    # Verbatim-mode terroir-facts records — short-text liens where 02d
    # emits the source text directly (see scripts/_lib/terroir_verbatim.py).
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _lib import terroir_verbatim as _verbatim
        _vb_count, _vb_records = _verbatim.count_verbatim_records(
            Path(__file__).resolve().parent.parent / "raw" / "terroir-facts", "it",
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
