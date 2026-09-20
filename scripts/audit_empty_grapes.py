#!/usr/bin/env python3
"""List every record of the current build that renders with no grape list.

Reads the stage-04 output (`wiki/data/aocs.en.*.js` for the startup fields,
`wiki/data/d/en/<slug>.json` for `parent_slug` / `is_stub`) and buckets
each grape-less record with `_lib.grape_gaps.classify`:

  FLAGGED   wine parent, not a stub, no grapes, not reviewed — an extraction
            gap (a cahier layout the parser missed, a sidecar that did not
            bind). Sub-denominations of an empty parent are counted on the
            parent's line.
  INHERIT   sub-denomination with no grapes whose parent has grapes — a
            stage-04 inheritance gap.
  REVIEWED  slug in scripts/_lib/empty_grapes_overrides.json — the regulator
            names no variety (curator-verified).
  STUB      no source document (owned by the per-country coverage audits).
  NON-WINE  spirits and ciders, no grape list by design.

Stage 04 prints the one-line summary of the same classification on every
build; this script is the full report and the gate:

    uv run scripts/audit_empty_grapes.py            # report
    uv run scripts/audit_empty_grapes.py --strict   # exit 1 on FLAGGED / INHERIT
    uv run scripts/audit_empty_grapes.py --json PATH

Read-only. A FLAGGED finding is fixed upstream (stage 02 / 02f parser, a
manual override) and a genuine absence is pinned in the overrides file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_gaps import (  # noqa: E402
    BUCKETS,
    classify,
    has_grapes,
    load_overrides,
    summary_line,
)

PANEL_DIR = ROOT / "wiki" / "data" / "d" / "en"


def load_aocs() -> dict[str, dict]:
    files = sorted((ROOT / "wiki" / "data").glob("aocs.en.*.js"))
    if not files:
        sys.exit("error: wiki/data/aocs.en.*.js not found — run stage 04 first")
    txt = files[-1].read_text(encoding="utf-8")
    m = re.match(r"window\.__OWM_DATA=(.*);\s*$", txt, re.S)
    if not m:
        sys.exit(f"error: could not parse {files[-1].name}")
    aocs = json.loads(m.group(1))["aocs"]
    # parent_slug / is_stub are panel-payload fields, not startup fields
    for slug, rec in aocs.items():
        if rec.get("grapes_principal") or rec.get("grapes_accessory") or rec.get("grapes_all"):
            continue
        p = PANEL_DIR / f"{slug}.json"
        if p.exists():
            panel = json.loads(p.read_text(encoding="utf-8"))
            rec["parent_slug"] = panel.get("parent_slug") or ""
            rec["is_stub"] = bool(panel.get("is_stub"))
    return aocs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any FLAGGED or INHERIT record")
    ap.add_argument("--json", default=None, help="also write the buckets to this path")
    ap.add_argument("--all", action="store_true", help="also list STUB and NON-WINE rows")
    args = ap.parse_args()

    aocs = load_aocs()
    buckets = classify(aocs, load_overrides())
    n_wine = sum(1 for r in aocs.values() if r.get("is_wine", True))

    print(f"records: {len(aocs)} ({n_wine} wine); no grape list: "
          f"{sum(1 for r in aocs.values() if not has_grapes(r))}")
    for b in BUCKETS:
        rows = buckets[b]
        if b in ("STUB", "NON-WINE") and not args.all:
            print(f"\n{b}: {len(rows)} (use --all to list)")
            continue
        print(f"\n{b}: {len(rows)}")
        for r in rows:
            extra = ""
            if r.get("children"):
                extra = f"  (+{r['children']} sub-denominations)"
            if r.get("orphan"):
                extra += "  [parent not in build]"
            if r.get("parent") and b == "INHERIT":
                extra = f"  parent={r['parent']}"
            if r.get("reason"):
                extra = f"  — {r['reason']}"
            print(f"  {r['country']:2} {r['kind']:4} {r['slug']}{extra}")
    by_country = Counter(r["country"] for r in buckets["FLAGGED"])
    print("\nsummary:", "  ".join(f"{b}={len(buckets[b])}" for b in BUCKETS),
          "| FLAGGED by country:", dict(sorted(by_country.items())))
    print(summary_line(buckets))

    if args.json:
        Path(args.json).write_text(json.dumps(buckets, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.strict and (buckets["FLAGGED"] or buckets["INHERIT"]):
        print(f"\n--strict: {len(buckets['FLAGGED'])} FLAGGED + {len(buckets['INHERIT'])} INHERIT record(s)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
