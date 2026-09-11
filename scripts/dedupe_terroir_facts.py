"""Post-pass over the stage-02d terroir-fact caches: drop facts restated
inside one record. No LLM call.

Why: 02d extracts each record in four sub-section calls over overlapping
source text, so one sentence of the cahier regularly comes back two or
three times ("facteurs naturels", again under "produit", again under
"interactions"). About a tenth of all bullets were such restatements.
The rule (`_lib.terroir_dedupe.dedupe_facts`) collapses near-identical
bullets, and same-quote bullets that overlap substantially, keeping the
more informative one; bullets with different numbers are never merged.

Translations: the stage-02e caches are index-aligned with the source
facts and keyed on `source_facts_sha` (a hash of the source bullets).
Dropping a source fact would misalign them and, at the next 02e run,
re-translate the whole record. Instead this script prunes the same
indices from every aligned bullet-mode translation cache and updates its
`source_facts_sha`, so no translation is lost and no re-translation is
needed. A translation cache that is already out of step (hash or length
mismatch) is left alone and listed — 02e re-translates it.

Usage:
  .venv/bin/python scripts/dedupe_terroir_facts.py --dry-run
  .venv/bin/python scripts/dedupe_terroir_facts.py [--only SLUG …]
      [--report tmp/terroir-facts-review/dedupe.json]
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
from _lib.terroir_dedupe import dedupe_facts, facts_sha  # noqa: E402

TERROIR = ROOT / "raw" / "terroir-facts"
TRANSLATIONS = ROOT / "raw" / "translations" / "terroir-facts"
LANGS = ("en", "fr", "es", "nl")
DEFAULT_REPORT = ROOT / "tmp" / "terroir-facts-review" / "dedupe.json"


def log(msg: str) -> None:
    print(f"[dedupe] {msg}", file=sys.stderr)


def prune_translations(
    slug: str, old_sha: str, n_old: int, kept_indices: list[int], new_sha: str, *, dry_run: bool,
) -> tuple[list[str], list[dict]]:
    """Prune the dropped indices from every aligned translation cache.
    Returns (pruned_langs, stale_entries)."""
    pruned: list[str] = []
    stale: list[dict] = []
    for lang in LANGS:
        tp = TRANSLATIONS / lang / f"{slug}.json"
        if not tp.exists():
            continue
        t = cache.read_json_or_none(tp)
        if not t or t.get("mode") == "verbatim":
            continue
        tfacts = t.get("facts") or []
        if t.get("source_facts_sha") != old_sha or len(tfacts) != n_old:
            stale.append({"slug": slug, "lang": lang, "reason": "already-misaligned"})
            continue
        t["facts"] = [tfacts[i] for i in kept_indices]
        t["source_facts_sha"] = new_sha
        pruned.append(lang)
        if not dry_run:
            cache.write_json(tp, t)
    return pruned, stale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--only", action="append", default=[], help="restrict to a slug (repeatable)")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="JSON report path")
    args = ap.parse_args()

    n_records = n_touched = n_facts_before = n_facts_after = 0
    reasons: Counter = Counter()
    per_country: dict[str, Counter] = {}
    translations_pruned = 0
    stale: list[dict] = []
    records: list[dict] = []

    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if not d or d.get("mode") == "verbatim" or not d.get("facts"):
            continue
        slug = d.get("slug") or p.stem
        if args.only and slug not in args.only:
            continue
        cc = d.get("country") or "fr"
        facts = d["facts"]
        n_records += 1
        n_facts_before += len(facts)
        res = dedupe_facts(facts)
        n_facts_after += len(res.kept)
        stats = per_country.setdefault(cc, Counter())
        stats["records"] += 1
        stats["facts_before"] += len(facts)
        stats["facts_after"] += len(res.kept)
        if not res.changed:
            continue
        n_touched += 1
        stats["records_touched"] += 1
        for drop in res.drops:
            reasons[drop["reason"]] += 1
        old_sha = facts_sha(facts)
        new_sha = facts_sha(res.kept)
        pruned, rec_stale = prune_translations(
            slug, old_sha, len(facts), res.kept_indices, new_sha, dry_run=args.dry_run,
        )
        translations_pruned += len(pruned)
        stale.extend(rec_stale)
        records.append({
            "slug": slug, "country": cc,
            "facts_before": len(facts), "facts_after": len(res.kept),
            "translations_pruned": pruned, "drops": res.drops,
        })
        if not args.dry_run:
            d["facts"] = res.kept
            d["n_deduped"] = int(d.get("n_deduped") or 0) + len(res.drops)
            cache.write_json(p, d)

    verb = "would drop" if args.dry_run else "dropped"
    n_dropped = n_facts_before - n_facts_after
    log("")
    log(f"{verb} {n_dropped} of {n_facts_before} facts ({100 * n_dropped / max(n_facts_before, 1):.1f} %) "
        f"in {n_touched} of {n_records} records; "
        f"{translations_pruned} translation caches pruned in step; "
        f"{len(stale)} translation caches already misaligned (left for 02e)")
    log("by reason: " + ", ".join(f"{r}: {n}" for r, n in reasons.most_common()))
    log(f"{'cc':4} {'records':>7} {'touched':>7} {'before':>6} {'after':>6} {'dropped':>7}")
    for cc, st in sorted(per_country.items()):
        log(f"{cc:4} {st['records']:7} {st['records_touched']:7} {st['facts_before']:6} "
            f"{st['facts_after']:6} {st['facts_before'] - st['facts_after']:7}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    cache.write_json(args.report, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": {
            "records": n_records, "records_touched": n_touched,
            "facts_before": n_facts_before, "facts_after": n_facts_after,
            "dropped_by_reason": dict(reasons),
            "translation_caches_pruned": translations_pruned,
            "translation_caches_stale": len(stale),
            "per_country": {cc: dict(st) for cc, st in sorted(per_country.items())},
        },
        "stale_translations": stale,
        "records": records,
    })
    log(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
