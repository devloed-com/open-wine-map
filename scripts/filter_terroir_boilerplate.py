"""Post-pass over the terroir-fact caches: drop boilerplate facts — a
quote shared by ≥ 3 records of one country that matches a tautology
pattern for its language (`_lib.terroir_boilerplate`). No LLM call.

The dropped indices are pruned from the index-aligned stage-02e
translation caches in step (their `source_facts_sha` is updated), the way
`dedupe_terroir_facts.py` does it, so nothing is re-translated.

Usage:
  .venv/bin/python scripts/filter_terroir_boilerplate.py --dry-run
  .venv/bin/python scripts/filter_terroir_boilerplate.py [--only SLUG …] [--report PATH]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache  # noqa: E402
from _lib.terroir_boilerplate import find_boilerplate  # noqa: E402
from _lib.terroir_cache import TERROIR, prune_translations, write_source_cache  # noqa: E402
from _lib.terroir_dedupe import facts_sha  # noqa: E402

DEFAULT_REPORT = ROOT / "tmp" / "terroir-facts-review" / "boilerplate.json"


def log(msg: str) -> None:
    print(f"[boilerplate] {msg}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    caches: dict[str, dict] = {}
    paths: dict[str, Path] = {}
    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if not d or d.get("mode") == "verbatim" or not d.get("facts"):
            continue
        slug = d.get("slug") or p.stem
        caches[slug] = d
        paths[slug] = p
    drops = find_boilerplate(caches)
    if args.only:
        drops = {s: v for s, v in drops.items() if s in args.only}

    per_country: Counter = Counter()
    records: list[dict] = []
    stale: list[dict] = []
    n_pruned = 0
    for slug, idx in sorted(drops.items()):
        d = caches[slug]
        facts = d["facts"]
        cc = d.get("country") or "fr"
        per_country[cc] += len(idx)
        kept_indices = [i for i in range(len(facts)) if i not in set(idx)]
        old_sha = facts_sha(facts)
        kept = [facts[i] for i in kept_indices]
        new_sha = facts_sha(kept)
        records.append({"slug": slug, "country": cc, "dropped": [
            {"index": i, "bullet": facts[i].get("bullet"), "cahier_quote": (facts[i].get("cahier_quote") or "")[:200]} for i in idx
        ]})
        pruned, rec_stale = prune_translations(slug, old_sha, len(facts), kept_indices, new_sha, dry_run=args.dry_run)
        n_pruned += len(pruned)
        stale.extend(rec_stale)
        if not args.dry_run:
            d["facts"] = kept
            d["n_boilerplate"] = int(d.get("n_boilerplate") or 0) + len(idx)
            write_source_cache(paths[slug], d)

    verb = "would drop" if args.dry_run else "dropped"
    total = sum(per_country.values())
    log(f"{verb} {total} boilerplate facts in {len(drops)} records; {n_pruned} translation caches pruned; "
        f"{len(stale)} already misaligned (left for 02e)")
    log("per country: " + ", ".join(f"{c}: {n}" for c, n in sorted(per_country.items())))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    cache.write_json(args.report, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": {"records": len(drops), "facts_dropped": total, "per_country": dict(per_country),
                    "translation_caches_pruned": n_pruned, "translation_caches_stale": len(stale)},
        "stale_translations": stale,
        "records": records,
    })
    log(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
