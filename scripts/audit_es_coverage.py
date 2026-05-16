"""Audit ES pipeline coverage — what ratio of the 149 ES wine GIs make
it from eAmbrosia to a usable map feature, with breakdowns by stage.

Reads:
  raw/es/eambrosia/index.json — 149 ES wine GIs (spine)
  raw/es/oj-pages/manifest.json — stage 01 pliego fetch outcomes
  raw/es/pliegos-extracted/_index.json — stage 02 extraction outcomes
  raw/translations/summaries/<lang>/*.json — stage 02c translations
  raw/es/figshare/EU_PDO.gpkg — stage 04 polygon source

Writes nothing. Stdout-only summary.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    eamb_idx = ROOT / "raw" / "es" / "eambrosia" / "index.json"
    if not eamb_idx.exists():
        print(f"error: {eamb_idx} missing — run scripts/es/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(eamb_idx.read_text())["wines"]
    n_wines = len(wines)
    by_kind = Counter(w["kind"] for w in wines)

    # Stage 01: oj-pages manifest
    oj_manifest_path = ROOT / "raw" / "es" / "oj-pages" / "manifest.json"
    n_html_cached = 0
    oj_status: Counter[str] = Counter()
    if oj_manifest_path.exists():
        m = json.loads(oj_manifest_path.read_text())
        for slug, info in m.get("by_slug", {}).items():
            oj_status[info.get("status", "unknown")] += 1
            if info.get("status") == "ok":
                n_html_cached += 1

    # Stage 02: pliegos-extracted records
    extracted_dir = ROOT / "raw" / "es" / "pliegos-extracted"
    parents = subzonas = stubs = parse_failed = 0
    extracted_slugs: set[str] = set()
    parents_by_slug: dict[str, dict] = {}
    if extracted_dir.exists():
        for jp in sorted(extracted_dir.glob("*.json")):
            if jp.name.startswith("_"):
                continue
            d = json.loads(jp.read_text())
            extracted_slugs.add(d["slug"])
            if d.get("is_sub_denomination"):
                subzonas += 1
                continue
            if d.get("stub"):
                stubs += 1
                continue
            if d.get("stub_reason"):
                parse_failed += 1
                continue
            parents += 1
            parents_by_slug[d["slug"]] = d

    # Stage 02c: translations cached per locale (only for ES records)
    summary_translations: Counter[str] = Counter()
    for lang in ("en", "fr", "nl"):
        d = ROOT / "raw" / "translations" / "summaries" / lang
        if not d.exists():
            continue
        n = 0
        for jp in d.glob("*.json"):
            try:
                rec = json.loads(jp.read_text())
            except (ValueError, OSError):
                continue
            if rec.get("country") == "es" or rec.get("source_lang") == "es":
                n += 1
        summary_translations[lang] = n

    # Stage 04: how many of the 99 Figshare PDOs cover the parents we extracted
    figshare_path = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
    figshare_covered: list[dict] = []
    figshare_uncovered_parents: list[tuple[str, str, str]] = []
    if figshare_path.exists():
        import geopandas as gpd
        gdf = gpd.read_file(figshare_path)
        es_pdo_ids = set(
            gdf[gdf["PDOid"].str.startswith(("PDO-ES", "PGI-ES"))]["PDOid"]
        )
        figshare_covered = [
            p for p in parents_by_slug.values()
            if p.get("file_number") in es_pdo_ids
        ]
        figshare_uncovered_parents = [
            (p["slug"], p["file_number"], p["kind"])
            for p in parents_by_slug.values()
            if p.get("file_number") not in es_pdo_ids
        ]

    print(f"=== ES pipeline coverage ===")
    print(f"eAmbrosia ES wines (filtered to status=registered + productType=WINE):")
    print(f"  total       : {n_wines}")
    for k, n in by_kind.most_common():
        print(f"  {k:11s} : {n}")
    print()
    print(f"Stage 01 (oj-pages, EUR-Lex single-document HTML):")
    for status, n in oj_status.most_common():
        print(f"  {status:30s}: {n}")
    print(f"  HTML cached (ok)              : {n_html_cached}/{n_wines}"
          f" ({100*n_html_cached//n_wines}%)")
    print()
    print(f"Stage 02 (pliegos-extracted records):")
    print(f"  parents (full extraction)      : {parents}")
    print(f"  subzonas (DGC-equivalent)      : {subzonas}")
    print(f"  stubs (no HTML cached)         : {stubs}")
    print(f"  parse_failed (HTML had no DOCUMENTO ÚNICO): {parse_failed}")
    print()
    print(f"Stage 02c (summary translations into target locales):")
    for lang, n in sorted(summary_translations.items()):
        print(f"  {lang:>4s}: {n}")
    print()
    print(f"Stage 04 (geometry source: Figshare EU_PDO.gpkg):")
    print(f"  parents with Figshare polygon  : {len(figshare_covered)}/{parents}"
          f" ({100*len(figshare_covered)//parents if parents else 0}%)")
    print(f"  parents WITHOUT Figshare polygon (need MAPA fallback or commune-union):")
    for slug, fn, kind in figshare_uncovered_parents[:20]:
        print(f"    {slug:30s}  {fn:18s}  {kind}")
    if len(figshare_uncovered_parents) > 20:
        print(f"    … and {len(figshare_uncovered_parents) - 20} more")

    # Curation queue: wines that need a manual_overrides.json URL.
    overrides_path = ROOT / "raw" / "es" / "oj-pages" / "manual_overrides.json"
    if overrides_path.exists():
        overrides = json.loads(overrides_path.read_text())
        needs_curation = []
        curated = []
        for slug, entry in overrides.items():
            if slug == "__doc__":
                continue
            if entry.get("url"):
                curated.append(entry)
            else:
                needs_curation.append(entry)
        n_total = len(needs_curation) + len(curated)
        print()
        print(f"Curation queue (manual_overrides.json):")
        print(f"  curated (URL filled in)        : {len(curated)}/{n_total}")
        print(f"  still needs URL                : {len(needs_curation)}")
        if needs_curation:
            print(f"  by kind: " + ", ".join(
                f"{k}={sum(1 for e in needs_curation if e.get('kind')==k)}"
                for k in ("DOP", "IGP")
            ))
            print()
            print(f"  -- Top-priority IGPs needing curation (sorted by name) --")
            igps = sorted(
                (e for e in needs_curation if e.get("kind") == "IGP"),
                key=lambda e: e.get("name", "").lower(),
            )
            for e in igps:
                print(
                    f"    [IGP] {e.get('name', '?'):40s}  "
                    f"{e.get('file_number', '?'):16s}  "
                    f"protect={e.get('eu_protect_date', '?')}  "
                    f"reason={e.get('status', '?')}"
                )
            dops = sorted(
                (e for e in needs_curation if e.get("kind") == "DOP"),
                key=lambda e: e.get("name", "").lower(),
            )
            if dops:
                print()
                print(f"  -- DOPs needing curation --")
                for e in dops:
                    print(
                        f"    [DOP] {e.get('name', '?'):40s}  "
                        f"{e.get('file_number', '?'):16s}  "
                        f"protect={e.get('eu_protect_date', '?')}  "
                        f"reason={e.get('status', '?')}"
                    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
