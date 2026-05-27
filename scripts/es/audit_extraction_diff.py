"""Diff two directories of `<slug>.json` extracted records by their
grape slugs (principal + accessory + observation). Used as the
reconciliation gate after rerunning the ES extractors with the new
vocab-anchored matcher.

Writes a per-pliego `lost` / `gained` / `unchanged_count` report and a
short stderr summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GRAPE_CATEGORIES = ("principal", "accessory", "observation")


def _record_slugs(path: Path) -> set[str]:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    grapes = rec.get("grapes") or {}
    out: set[str] = set()
    for cat in GRAPE_CATEGORIES:
        for g in grapes.get(cat) or []:
            if isinstance(g, str):
                out.add(g)
            elif isinstance(g, dict) and isinstance(g.get("slug"), str):
                out.add(g["slug"])
    return out


def _index(dir_: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in sorted(dir_.glob("*.json")):
        if p.name.startswith("_"):
            continue
        out[p.stem] = _record_slugs(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--current", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    baseline = _index(args.baseline)
    current = _index(args.current)

    all_keys = sorted(set(baseline) | set(current))
    lost: dict[str, list[str]] = {}
    gained: dict[str, list[str]] = {}
    unchanged = 0
    total_lost = total_gained = 0
    for slug in all_keys:
        old = baseline.get(slug, set())
        new = current.get(slug, set())
        l = sorted(old - new)
        g = sorted(new - old)
        if l:
            lost[slug] = l
            total_lost += len(l)
        if g:
            gained[slug] = g
            total_gained += len(g)
        if not l and not g:
            unchanged += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline": str(args.baseline),
        "current": str(args.current),
        "pliegos_compared": len(all_keys),
        "totals": {
            "lost": total_lost,
            "gained": total_gained,
            "unchanged_records": unchanged,
            "records_with_lost": len(lost),
            "records_with_gained": len(gained),
        },
        "lost": lost,
        "gained": gained,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[diff] {len(all_keys)} pliegos compared", file=sys.stderr)
    print(
        f"  total lost:    {total_lost} grape rows across {len(lost)} pliegos",
        file=sys.stderr,
    )
    print(
        f"  total gained:  {total_gained} grape rows across {len(gained)} pliegos",
        file=sys.stderr,
    )
    print(f"  net delta:    {total_gained - total_lost:+d}", file=sys.stderr)
    print(f"[diff] full report → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
