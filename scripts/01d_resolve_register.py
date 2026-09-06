"""Resolve every French appellation to its eAmbrosia register file number.

Pipeline stage 01d.

France is INAO-sourced and carries no `id_eambrosia`, so the register — which
serves the INAO cahier des charges PDF per GI, with none of BO Agri's
hand-curated URLs, Légifrance cookie injection or OCR-over-mirrors — needs a
name-based join key before stage 01 can use it as a fallback source.

Reads the parent appellations from `raw/inao/cahiers/manifest.json` (falling
back to the SIQO referentiel when stage 01 has not run yet) and the register's
own GI listing, and writes:

    raw/inao/register/resolved.json     id_appellation -> register GI binding
    raw/inao/register/unresolved.json   curator queue, with a reason per entry

Pin the residue in `scripts/_lib/fr/register_overrides.json` (checked in) and
re-run; the resolver never fuzzy-matches, so anything it cannot settle on
exact alias keys is a curator decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import eambrosia_register as er  # noqa: E402
from _lib.fr import register_cahier as rc  # noqa: E402
from _lib.fr import register_match as rm  # noqa: E402

MANIFEST_PATH = ROOT / "raw" / "inao" / "cahiers" / "manifest.json"
SIQO_CSV = ROOT / "raw" / "inao" / "siqo-referentiel.csv"
WINE_SIGNS = {"AOC", "AOP", "IGP"}


def appellations_from_manifest() -> list[dict]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [
        {"id_appellation": k, "name": v["name"], "categorie": v.get("categorie", "")}
        for k, v in manifest.items()
    ]


def appellations_from_siqo() -> list[dict]:
    """Stage-01-free fallback: the same VITICOLE / AOC-AOP-IGP / Publié
    filter stage 01 applies, one row per id_appellation."""
    out: dict[str, dict] = {}
    with open(SIQO_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["secteur"].strip() != "VITICOLE" or row["lib_etat"].strip() != "Publié":
                continue
            if (row["signe_fr"].strip() or row["signe_ue"].strip()) not in WINE_SIGNS:
                continue
            id_app = row["id_appellation"].strip()
            out.setdefault(id_app, {
                "id_appellation": id_app,
                "name": row["appellation"].strip(),
                "categorie": row["categorie"].strip(),
            })
    return list(out.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch the register GI listing")
    ap.add_argument("--strict", action="store_true", help="exit 2 when the queue is non-empty")
    args = ap.parse_args()

    if MANIFEST_PATH.exists():
        appellations = appellations_from_manifest()
        origin = MANIFEST_PATH
    elif SIQO_CSV.exists():
        appellations = appellations_from_siqo()
        origin = SIQO_CSV
    else:
        print(f"error: neither {MANIFEST_PATH} nor {SIQO_CSV} — run stage 00/01 first",
              file=sys.stderr)
        return 1

    session = requests.Session()
    rows = rm.fr_rows(er.load_gi_rows(refresh=args.refresh, session=session))
    overrides = rm.load_overrides()
    print(
        f"[plan] {len(appellations)} appellations from {origin.relative_to(ROOT)} "
        f"vs {len(rows)} FR register GIs; {len(overrides)} curator pin(s)",
        file=sys.stderr,
    )

    resolved, unresolved = rm.resolve_all(appellations, rows, overrides)

    rc.REGISTER_DIR.mkdir(parents=True, exist_ok=True)
    rc.RESOLVED_PATH.write_text(
        json.dumps(rm.to_json(resolved), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rc.UNRESOLVED_PATH.write_text(
        json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    by_type = Counter(r.product_type for r in resolved.values())
    by_via = Counter(r.matched_via for r in resolved.values())
    by_status = Counter(r.status for r in resolved.values())
    for u in unresolved:
        print(f"[queue] {u['name']} ({u['id_appellation']}): {u['reason']} — {u['detail']}",
              file=sys.stderr)
    print(
        f"[done] resolved={len(resolved)} ({dict(by_via)}; {dict(by_type)}; "
        f"{dict(by_status)}) "
        f"unresolved={len(unresolved)} "
        f"-> {rc.RESOLVED_PATH.relative_to(ROOT)}, {rc.UNRESOLVED_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 2 if (args.strict and unresolved) else 0


if __name__ == "__main__":
    sys.exit(main())
