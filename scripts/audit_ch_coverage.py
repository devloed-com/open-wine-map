"""Audit CH pipeline coverage.

Reports per-canton règlement fetch status, OFAG-spine record counts
(63 expected = 28 cantonale + 13 régionale + 22 locale), variety
extraction stats, swissBOUNDARIES3D commune-match stats, and SITG GE
geoportal coverage.

Run: `.venv/bin/python scripts/audit_ch_coverage.py`
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFAG_MANIFEST = ROOT / "raw" / "ch" / "ofag" / "manifest.json"
REGLEMENTS_MANIFEST = ROOT / "raw" / "ch" / "reglements" / "manifest.json"
EXTRACTED_DIR = ROOT / "raw" / "ch" / "dokumente-extracted"
EXTRACTED_MANIFEST = ROOT / "raw" / "ch" / "dokumente-extracted-manifest.json"
SITG_GEOJSON = ROOT / "raw" / "ch" / "geoportals" / "sitg-vit-vignoble-ao.geojson"


def _safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def main() -> int:
    ofag = _safe_json(OFAG_MANIFEST)
    reg = _safe_json(REGLEMENTS_MANIFEST)
    extract = _safe_json(EXTRACTED_MANIFEST)

    print("=" * 70)
    print("CH coverage audit")
    print("=" * 70)

    print("\n— OFAG répertoire (spine) —")
    print(f"  source: {ofag.get('source_url', '?')}")
    print(f"  edition: {ofag.get('edition', '?')}")
    print(f"  sha256: {ofag.get('sha256', '?')[:16]}…")

    print("\n— Cantonal règlements (stage 01) —")
    by_canton = reg.get("by_canton", {})
    n_ok = sum(1 for e in by_canton.values() if e.get("status", "").startswith("ok"))
    print(f"  fetched: {n_ok} / {len(by_canton)}")
    fail = [c for c, e in by_canton.items() if not e.get("status", "").startswith("ok")]
    if fail:
        print(f"  failed: {', '.join(fail)}")

    print("\n— Records (stage 02) —")
    n_records = extract.get("n_records", 0)
    print(f"  total: {n_records}")
    by_tier = extract.get("by_tier") or {}
    for tier, n in sorted(by_tier.items()):
        print(f"    {tier:12} {n:4}")
    print(f"  parents: {extract.get('n_parents', 0)}, "
          f"sub-denominations: {extract.get('n_sub_denominations', 0)}")
    geom_status = extract.get("by_geom_status") or {}
    print(f"  with règlement-extracted communes: "
          f"{geom_status.get('with_communes', 0)} / {n_records}")

    print("\n— Variety extraction (stage 02 sample) —")
    by_canton_records = Counter()
    grape_counts: dict[str, int] = {}
    commune_counts: dict[str, int] = {}
    for jp in sorted(EXTRACTED_DIR.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        c = rec.get("canton", "?")
        by_canton_records[c] += 1
        grape_counts.setdefault(c, 0)
        commune_counts.setdefault(c, 0)
        grape_counts[c] = max(grape_counts[c], rec.get("n_grapes", 0))
        commune_counts[c] = max(commune_counts[c], rec.get("n_communes", 0))
    print(f"  {'canton':6} {'records':>8} {'grapes':>8} {'communes':>10}")
    for canton in sorted(by_canton_records):
        print(f"  {canton:6} {by_canton_records[canton]:>8} "
              f"{grape_counts.get(canton, 0):>8} "
              f"{commune_counts.get(canton, 0):>10}")
    grape_total = sum(grape_counts.values())
    no_grapes = [c for c, n in grape_counts.items() if n == 0]
    print(f"\n  total varieties extracted (max per canton): {grape_total}")
    if no_grapes:
        print(f"  cantons with no varieties extracted: {', '.join(sorted(no_grapes))}")

    print("\n— GE SITG geoportal coverage —")
    if SITG_GEOJSON.exists():
        d = json.loads(SITG_GEOJSON.read_text(encoding="utf-8"))
        feats = d.get("features", [])
        appellations = {f["properties"].get("APPELATION", "")
                        for f in feats}
        appellations.discard("")
        appellations.discard("null")
        print(f"  SITG features: {len(feats)} parcels")
        print(f"  distinct AOCs: {len(appellations)}")
    else:
        print("  SITG layer not fetched")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
