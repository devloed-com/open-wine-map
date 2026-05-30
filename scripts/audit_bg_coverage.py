"""Audit BG pipeline coverage.

Prints extraction status per kind, stub reasons, Figshare geometry
coverage, commune-list coverage, grape extraction, region distribution,
and a curator queue for any wine whose single document could not be
fetched. Mirrors `audit_ro_coverage.py` for the Bulgarian corpus.

Run: `.venv/bin/python scripts/audit_bg_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EAMBROSIA = ROOT / "raw" / "bg" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "bg" / "dokumenti-extracted"
OJ_MANIFEST = ROOT / "raw" / "bg" / "oj-pages" / "manifest.json"
OVERRIDES = ROOT / "raw" / "bg" / "oj-pages" / "manual_overrides.json"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
NATIONAL_SPECS = ROOT / "raw" / "bg" / "national-specs-extracted"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"


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
            if fn and (fn.startswith("PDO-BG") or fn.startswith("PGI-BG"))
        )
    except ImportError:
        return set()


def main() -> int:
    wines = _load_eambrosia()
    extracted = _load_extracted()
    oj_manifest = _load_manifest()
    overrides = _load_overrides()
    figshare_ids = _load_figshare_file_numbers()

    print("# BG pipeline audit\n")
    print(f"eAmbrosia wines:      {len(wines)}")
    print(f"Extracted records:    {len(extracted)}")
    print(f"OJ-page manifest:     {len(oj_manifest)} entries")
    print(f"Manual overrides:     {len(overrides)} entries")
    print(f"Figshare BG PDOids:   {len(figshare_ids)}")
    print()

    by_kind_total: Counter[str] = Counter()
    by_kind_extracted: Counter[str] = Counter()
    by_kind_stub: Counter[str] = Counter()
    stub_reasons: Counter[str] = Counter()
    in_figshare = no_figshare = 0
    grape_total = 0
    n_with_grapes = 0
    by_region: Counter[str] = Counter()
    n_communes_total = 0
    n_with_communes = 0

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
        communes = rec.get("geo_communes") or []
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
          f"(expected 2 = the 2 PGIs, resolved via member-PDO union)")
    print()
    print("## Commune-list coverage (defensive fallback)")
    print(f"  Wines with geo_communes: {n_with_communes} of {len(extracted)}")
    print(f"  Total commune-name candidates: {n_communes_total}")
    print()
    print("## Region distribution (5 wine regions + the 2 PGIs)")
    for b, n in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {b}")
    print()
    print("## Grape extraction (on-disk EU-OJ records only)")
    print(f"  Wines with grapes:  {n_with_grapes} of {len(extracted)}")
    print(f"  Total grape-slugs:  {grape_total}")
    print()

    # National-spec augmentation (ИАЛВ / IAVV per-wine продуктова
    # спецификация, stage 01c/02f). On-disk records stay stubs; this layer
    # is merged in-memory by stage 04's augment_bg_records_with_national_specs.
    ns_sidecars = 0
    ns_with_grapes = ns_with_terroir = ns_grape_total = 0
    if NATIONAL_SPECS.exists():
        for jp in NATIONAL_SPECS.glob("*.json"):
            if jp.name.startswith("_") or jp.name == "manifest.json":
                continue
            sc = json.loads(jp.read_text(encoding="utf-8"))
            ns_sidecars += 1
            ng = len((sc.get("grapes") or {}).get("principal") or [])
            if ng:
                ns_with_grapes += 1
                ns_grape_total += ng
            if len((sc.get("link_to_terroir") or "").strip()) >= 200:
                ns_with_terroir += 1
    print("## National-spec augmentation (ИАЛВ / IAVV, stage 02f)")
    print(f"  Sidecars:           {ns_sidecars}")
    print(f"  With grapes:        {ns_with_grapes}")
    print(f"  With terroir ≥200:  {ns_with_terroir}")
    print(f"  Total grape-slugs:  {ns_grape_total}")
    print()

    # Terroir-fact bullets (stage 02d) — across both EU-OJ and spec-grounded.
    tf_records = tf_bullets = 0
    if TERROIR_FACTS.exists():
        for jp in TERROIR_FACTS.glob("*.json"):
            if jp.name.startswith(("_", "manifest")):
                continue
            try:
                tf = json.loads(jp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if tf.get("country") != "bg":
                continue
            bullets = tf.get("facts") or tf.get("bullets") or []
            if bullets:
                tf_records += 1
                tf_bullets += len(bullets)
    print("## Terroir-fact bullets (stage 02d, country=bg)")
    print(f"  Wines with bullets: {tf_records}")
    print(f"  Total bullets:      {tf_bullets}")
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
        print("  (empty — every Bulgarian wine extracted)")
    print()
    # Verbatim-mode terroir-facts records — short-text liens where 02d
    # emits the source text directly (see scripts/_lib/terroir_verbatim.py).
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _lib import terroir_verbatim as _verbatim
        _vb_count, _vb_records = _verbatim.count_verbatim_records(
            Path(__file__).resolve().parent.parent / "raw" / "terroir-facts", "bg",
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
