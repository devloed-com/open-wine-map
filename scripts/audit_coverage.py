"""One-shot audit: which wine AOC/AOPs in SIQO never made it into the
generated wiki, and at which stage they fell out.

For every (id_appellation, id_denomination_geo) wine row in the SIQO
referentiel, classify against:
  - raw/inao/cahiers/manifest.json          (stage 01: PDF resolved & fetched)
  - raw/inao/cahier-extracted/_index.json   (stage 02: cahier text extracted)

Reports per id_appellation:
  status = ok | no-pdf | no-extract
plus a one-liner reason where available.

Run: uv run python scripts/audit_coverage.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIQO_CSV = ROOT / "raw" / "inao" / "siqo-referentiel.csv"
MANIFEST = ROOT / "raw" / "inao" / "cahiers" / "manifest.json"
INDEX = ROOT / "raw" / "inao" / "cahier-extracted" / "_index.json"

WINE_SIGNS = {"AOC", "AOP", "IGP"}


def load_siqo() -> dict[str, dict]:
    """id_appellation → {name, denoms: [(id_denomination_geo, denomination)]}."""
    apps: dict[str, dict] = {}
    with open(SIQO_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["secteur"].strip() != "VITICOLE":
                continue
            if row["lib_etat"].strip() != "Publié":
                continue
            sign = row["signe_fr"].strip() or row["signe_ue"].strip()
            if sign not in WINE_SIGNS:
                continue
            id_app = row["id_appellation"].strip()
            entry = apps.setdefault(
                id_app,
                {
                    "name": row["appellation"].strip(),
                    "comite_regional": row.get("comite_regional", "").strip(),
                    "denoms": set(),
                },
            )
            entry["denoms"].add(
                (row["id_denomination_geo"].strip(), row["denomination"].strip())
            )
    return apps


def main() -> int:
    if not MANIFEST.exists():
        print(f"error: {MANIFEST} missing — run 01_scrape_cahiers.py", file=sys.stderr)
        return 1
    if not INDEX.exists():
        print(f"error: {INDEX} missing — run 02_extract_cahiers.py", file=sys.stderr)
        return 1

    apps = load_siqo()
    manifest = json.loads(MANIFEST.read_text())
    index = json.loads(INDEX.read_text())

    extracted_app_ids: set[str] = set()
    extracted_denom_ids: set[str] = set()
    for entry in index.values():
        extracted_app_ids.add(str(entry.get("id_appellation", "")))
        if entry.get("id_denomination_geo"):
            extracted_denom_ids.add(str(entry["id_denomination_geo"]))

    by_status: dict[str, list[dict]] = defaultdict(list)
    region_misses: Counter[str] = Counter()

    for id_app, entry in apps.items():
        name = entry["name"]
        comite = entry["comite_regional"]
        in_manifest = id_app in manifest
        in_extracted = id_app in extracted_app_ids
        if in_extracted:
            missing_dgcs = [
                (did, dname)
                for did, dname in entry["denoms"]
                if did and did not in extracted_denom_ids
            ]
            if missing_dgcs:
                by_status["dgc-missing"].append(
                    {
                        "id": id_app,
                        "name": name,
                        "comite": comite,
                        "missing_dgcs": missing_dgcs,
                    }
                )
            else:
                by_status["ok"].append({"id": id_app, "name": name, "comite": comite})
        elif in_manifest:
            by_status["no-extract"].append(
                {
                    "id": id_app,
                    "name": name,
                    "comite": comite,
                    "pdf": manifest[id_app].get("filename", "")[:16],
                }
            )
            region_misses[comite] += 1
        else:
            by_status["no-pdf"].append({"id": id_app, "name": name, "comite": comite})
            region_misses[comite] += 1

    total = sum(len(v) for v in by_status.values())
    print(f"SIQO wine appellations (Publié, AOC/AOP/IGP): {total}", file=sys.stderr)
    for status in ("ok", "no-pdf", "no-extract", "dgc-missing"):
        rows = by_status.get(status, [])
        print(f"  {status}: {len(rows)}", file=sys.stderr)

    print()
    print("# no-pdf  (stage 01 didn't resolve a BO Agri URL)")
    for r in sorted(by_status.get("no-pdf", []), key=lambda r: (r["comite"], r["name"])):
        print(f"  [{r['id']:>5}] {r['name']}  ({r['comite']})")

    print()
    print("# no-extract  (PDF fetched but stage 02 found no segment)")
    for r in sorted(
        by_status.get("no-extract", []), key=lambda r: (r["comite"], r["name"])
    ):
        print(f"  [{r['id']:>5}] {r['name']}  ({r['comite']})  pdf={r['pdf']}")

    if by_status.get("dgc-missing"):
        print()
        print("# dgc-missing  (parent extracted, but some DGCs never emitted)")
        for r in sorted(
            by_status["dgc-missing"], key=lambda r: (r["comite"], r["name"])
        ):
            dgcs = ", ".join(f"{d[0]}:{d[1]}" for d in r["missing_dgcs"])
            print(f"  [{r['id']:>5}] {r['name']}  ({r['comite']})  -> {dgcs}")

    if region_misses:
        print()
        print("# misses by comité régional")
        for comite, n in region_misses.most_common():
            print(f"  {n:>3}  {comite or '(unset)'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
