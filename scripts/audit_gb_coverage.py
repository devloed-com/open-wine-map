"""Coverage audit for the United Kingdom corpus.

Reports, per registered UK wine GI: whether its product specification was
fetched, which parser template read it, how many varieties and styles came
out, whether it carries terroir-source text and extracted terroir facts,
and how its geometry resolves.

Unlike the eAmbrosia countries there is no stub tier to chase — every
registered UK wine ships a public specification — so the curator queue
here is short by construction: it lists pending applications (names still
in assessment, which stage 00 filters out of the corpus) and any
registered wine whose specification failed to fetch or parse.

    .venv/bin/python scripts/audit_gb_coverage.py
    .venv/bin/python scripts/audit_gb_coverage.py --strict   # non-zero on gaps
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

INDEX_IN = ROOT / "raw" / "gb" / "gov-uk" / "index.json"
GOVUK_MANIFEST = ROOT / "raw" / "gb" / "gov-uk" / "manifest.json"
SPECS_MANIFEST = ROOT / "raw" / "gb" / "specs" / "manifest.json"
EXTRACTED = ROOT / "raw" / "gb" / "specs-extracted"
TERROIR = ROOT / "raw" / "terroir-facts"


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when a registered wine is missing "
                         "a specification, varieties or terroir text")
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/gb/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = _load(INDEX_IN, {"wines": []})["wines"]
    govuk = _load(GOVUK_MANIFEST, {})
    specs = _load(SPECS_MANIFEST, {}).get("by_slug", {})

    try:
        from _lib.gb.geometry import GBPolygonIndex
        gb_polygons = GBPolygonIndex()
    except Exception as exc:  # noqa: BLE001 - the audit must run without geopandas
        print(f"[warn] geometry index unavailable ({exc}); skipping geom column",
              file=sys.stderr)
        gb_polygons = None

    print(f"United Kingdom — {len(wines)} registered wine GIs\n")
    header = (f"{'slug':24s} {'kind':4s} {'region':8s} {'spec':6s} "
              f"{'template':24s} {'grapes':>6s} {'styles':>6s} {'link':>6s} "
              f"{'facts':>5s}  geom")
    print(header)
    print("-" * len(header))

    problems: list[str] = []
    n_facts_total = 0
    geom_counts: dict[str, int] = {}

    for w in wines:
        slug = w["slug"]
        meta = specs.get(slug, {})
        spec_ok = meta.get("status") == "ok"
        rec = _load(EXTRACTED / f"{slug}.json", {})
        grapes = len(((rec.get("grapes") or {}).get("details")) or [])
        styles = len(rec.get("styles") or [])
        link = len(rec.get("link_to_terroir") or "")
        facts_doc = _load(TERROIR / f"{slug}.json", {})
        n_facts = len(facts_doc.get("facts") or []) if facts_doc.get("country") == "gb" else 0
        n_facts_total += n_facts

        geom = "-"
        if gb_polygons is not None:
            _g, geom, _stats = gb_polygons.resolve(w.get("file_number") or "")
            geom_counts[geom] = geom_counts.get(geom, 0) + 1

        print(f"{slug:24s} {w['kind']:4s} {rec.get('region', '?'):8s} "
              f"{'ok' if spec_ok else 'MISS':6s} "
              f"{rec.get('parser_template', '-'):24s} {grapes:6d} {styles:6d} "
              f"{link:6d} {n_facts:5d}  {geom}")

        if not spec_ok:
            problems.append(f"{slug}: no cached product specification")
        elif not rec:
            problems.append(f"{slug}: specification cached but not extracted")
        else:
            if grapes == 0:
                problems.append(f"{slug}: no varieties resolved")
            if link == 0:
                problems.append(f"{slug}: no terroir source text")

    print("\nGeometry: " + ", ".join(f"{k}={v}" for k, v in sorted(geom_counts.items())))
    n_with_facts = sum(
        1 for w in wines
        if (_load(TERROIR / f"{w['slug']}.json", {}) or {}).get("facts")
    )
    print(f"Terroir facts: {n_facts_total} bullets across "
          f"{n_with_facts}/{len(wines)} wines")

    pending = govuk.get("pending_applications") or []
    print(f"\nCurator queue — {len(pending)} pending application(s), "
          f"{len(problems)} problem(s)")
    for p in pending:
        print(f"  [pending]  {p['name']} ({p['kind']}, applied {p['date_application']}) "
              f"— {p['register_url']}")
    for p in problems:
        print(f"  [problem]  {p}")
    if not pending and not problems:
        print("  (nothing queued)")

    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
