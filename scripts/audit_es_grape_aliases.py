"""Surface ES grape tokens that don't resolve via GRAPE_ALIAS or DEFAULT_COLOUR.

For every ES pliego, walk the extracted `grapes.details` list and check
whether each `slug` is already known to the lexicon — either:
  - it's an existing canonical slug shared with FR (cabernet-sauvignon,
    chardonnay, syrah, …), OR
  - it's an ES-only canonical slug registered in DEFAULT_COLOUR, OR
  - the raw name slug maps to one of the above via GRAPE_ALIAS.

Tokens that satisfy none of the above are emitted with a frequency
count so curators can decide whether to fold them via GRAPE_ALIAS,
register them as new canonical slugs in DEFAULT_COLOUR, or drop them
as parse noise. Pliegos written in Spanish national format
(narrative-prose variety sections — Málaga, Bajo Aragón, Yecla, …)
generate the most leakage and are good candidates for hand
overrides.

Usage:
    .venv/bin/python scripts/audit_es_grape_aliases.py
    .venv/bin/python scripts/audit_es_grape_aliases.py --min-count 3
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS  # noqa: E402


PLIEGOS_DIR = ROOT / "raw" / "es" / "pliegos-extracted"


def _known_canonical_slugs() -> set[str]:
    """Slugs that are known landing points: anything in DEFAULT_COLOUR plus
    every alias-map value (the right-hand side of the GRAPE_ALIAS dict)."""
    known: set[str] = set(DEFAULT_COLOUR.keys())
    known.update(GRAPE_ALIAS.values())
    return known


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-count", type=int, default=1,
                        help="Hide tokens that appear in fewer than N pliegos.")
    parser.add_argument("--top", type=int, default=200,
                        help="Show only the top-N most frequent unmapped tokens.")
    args = parser.parse_args()

    known = _known_canonical_slugs()
    token_count: Counter[str] = Counter()
    token_examples: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total_records = 0
    total_tokens = 0

    for p in sorted(PLIEGOS_DIR.glob("*.json")):
        if p.name == "_index.json":
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("is_sub_denomination"):
            continue
        total_records += 1
        for d in (rec.get("grapes", {}).get("details") or []):
            total_tokens += 1
            slug = d.get("slug", "")
            if not slug or slug in known:
                continue
            token_count[slug] += 1
            if len(token_examples[slug]) < 3:
                token_examples[slug].append((rec["slug"], d.get("name", "")))

    eligible = [
        (slug, n) for slug, n in token_count.most_common()
        if n >= args.min_count
    ][: args.top]

    print(f"Audited {total_records} parent records, {total_tokens} grape tokens")
    print(f"  → {len(token_count)} distinct unmapped slugs"
          f" ({sum(token_count.values())} total occurrences)")
    print()
    if not eligible:
        print(f"No unmapped tokens at min-count={args.min_count}.")
        return 0

    width = max(len(s) for s, _ in eligible)
    print(f"{'count':>5}  {'slug':<{width}}  examples (pliego: raw_name)")
    print("-" * (8 + width + 60))
    for slug, n in eligible:
        ex = "; ".join(f"{p}: {nm!r}" for p, nm in token_examples[slug])
        print(f"{n:>5}  {slug:<{width}}  {ex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
