"""Audit subzona extraction quality across the ES corpus.

For every extracted ES wine, check whether the pliego text mentions
"subzona" / "subzonas" / "unidad geográfica menor" anywhere (geo,
link-to-terroir, or any other section), and bucket each wine into:

  - extracted   : at least one subzona record was emitted by stage 02
  - mentioned   : pliego text mentions subzona but no records were emitted
                  → parser-tuning queue (add a pattern, or accept that
                  the wine is purely narrative without enumerable subzonas)
  - silent      : no mention of subzona anywhere → probably has none

Reads:  raw/es/pliegos-extracted/_index.json + raw/es/pliegos-extracted/*.json
Writes: nothing — prints a per-bucket report to stderr.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "es" / "pliegos-extracted"

SUBZONA_HINT_RE = re.compile(
    r"\b(?:subzonas?|unidad(?:es)?\s+geográfica(?:s)?\s+menor(?:es)?)\b",
    re.IGNORECASE,
)


def main() -> int:
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/es/02_extract_pliegos.py first",
              file=sys.stderr)
        return 1

    extracted_parents: set[str] = set()
    extracted_subzonas_per_parent: dict[str, list[str]] = {}
    parents: list[dict] = []
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        d = json.loads(jp.read_text())
        if d.get("is_sub_denomination"):
            extracted_subzonas_per_parent.setdefault(d["parent_slug"], []).append(d["name"])
            extracted_parents.add(d["parent_slug"])
            continue
        if d.get("stub"):
            continue
        parents.append(d)

    buckets = Counter()
    mentioned_unextracted: list[tuple[str, int]] = []
    for d in parents:
        slug = d["slug"]
        full = " ".join(d.get("sections", {}).values()) + " " + d.get("link_to_terroir", "")
        n_hits = len(SUBZONA_HINT_RE.findall(full))
        if slug in extracted_parents:
            buckets["extracted"] += 1
        elif n_hits > 0:
            buckets["mentioned-but-not-extracted"] += 1
            mentioned_unextracted.append((slug, n_hits))
        else:
            buckets["silent"] += 1

    n_subzonas = sum(len(v) for v in extracted_subzonas_per_parent.values())
    print(
        f"[audit_subzonas] {len(parents)} extracted parents | "
        f"extracted={buckets['extracted']} subzonas={n_subzonas} | "
        f"mentioned-but-not-extracted={buckets['mentioned-but-not-extracted']} | "
        f"silent={buckets['silent']}",
        file=sys.stderr,
    )
    if extracted_parents:
        print("\n--- extracted (parent → subzonas) ---", file=sys.stderr)
        for parent_slug in sorted(extracted_parents):
            names = extracted_subzonas_per_parent[parent_slug]
            print(f"  {parent_slug:30s} ({len(names)}): {names}", file=sys.stderr)
    if mentioned_unextracted:
        print("\n--- mentioned-but-not-extracted (curator queue) ---", file=sys.stderr)
        mentioned_unextracted.sort(key=lambda kv: -kv[1])
        for slug, n in mentioned_unextracted:
            print(f"  {slug:30s} ({n} subzona-keyword hits in pliego text)",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
