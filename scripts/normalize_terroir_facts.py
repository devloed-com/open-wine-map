"""Post-pass over the terroir-fact caches: apply the deterministic bullet
clean-up of `_lib.terroir_normalize` (regulatory colour codes after grape
names, VT / SGN expansion, terminal period) to the source caches AND the
translation caches, in step. No LLM call.

Stage 04 applies the same normaliser at render time, so this pass is not
needed for the map; it exists so the caches themselves — what the audit
checks and what stage 02e re-translates from — are clean. Rewriting a
source bullet changes `source_facts_sha`; every aligned translation cache
(same hash, same length) is re-keyed to the new hash after its own bullets
are normalised, so nothing is re-translated. A cache already out of step
is left alone and reported.

Usage:
  .venv/bin/python scripts/normalize_terroir_facts.py --dry-run
  .venv/bin/python scripts/normalize_terroir_facts.py [--only SLUG …] [--report PATH]
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
from _lib.terroir_cache import (  # noqa: E402
    LANGS,
    TERROIR,
    TRANSLATIONS,
    rekey_translations,
    write_source_cache,
    write_translation_cache,
)
from _lib.terroir_dedupe import facts_sha  # noqa: E402
from _lib.terroir_normalize import normalize_facts  # noqa: E402

DEFAULT_REPORT = ROOT / "tmp" / "terroir-facts-review" / "normalize.json"


def log(msg: str) -> None:
    print(f"[normalize] {msg}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    per_country: dict[str, Counter] = {}
    n_src_records = n_src_bullets = n_tr_records = n_tr_bullets = 0
    misaligned: list[dict] = []
    changes: list[dict] = []
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
        st = per_country.setdefault(cc, Counter())
        facts = d["facts"]
        old_sha = facts_sha(facts)
        before = [f.get("bullet") for f in facts]
        n = normalize_facts(facts)
        st["source_bullets"] += n
        if n:
            n_src_records += 1
            n_src_bullets += n
            changes.extend({"slug": slug, "lang": d.get("source_lang") or cc, "index": i, "before": b, "after": f["bullet"]}
                           for i, (b, f) in enumerate(zip(before, facts)) if b != f["bullet"])
        new_sha = facts_sha(facts)
        # translation bullets first (they hold their own text), then the re-key
        for lang in LANGS:
            tp = TRANSLATIONS / lang / f"{slug}.json"
            if not tp.exists():
                continue
            t = cache.read_json_or_none(tp)
            if not t or t.get("mode") == "verbatim" or not t.get("facts"):
                continue
            tb = [f.get("bullet") for f in t["facts"]]
            tn = normalize_facts(t["facts"], lang)
            if tn:
                n_tr_records += 1
                n_tr_bullets += tn
                st[f"translated_bullets_{lang}"] += tn
                changes.extend({"slug": slug, "lang": lang, "index": i, "before": b, "after": f["bullet"]}
                               for i, (b, f) in enumerate(zip(tb, t["facts"])) if b != f["bullet"])
                if not args.dry_run:
                    write_translation_cache(tp, t)
        if n:
            if not args.dry_run:
                write_source_cache(p, d)
            _, mis = rekey_translations(slug, old_sha, len(facts), new_sha, dry_run=args.dry_run)
            misaligned.extend({"slug": slug, "lang": lang} for lang in mis)

    verb = "would normalise" if args.dry_run else "normalised"
    log(f"{verb} {n_src_bullets} source bullets in {n_src_records} records and "
        f"{n_tr_bullets} translated bullets in {n_tr_records} caches; "
        f"{len(misaligned)} translation caches misaligned (left for 02e)")
    log(f"{'cc':4} {'src':>5} " + " ".join(f"{lg:>5}" for lg in LANGS))
    for cc, st in sorted(per_country.items()):
        log(f"{cc:4} {st['source_bullets']:5} " + " ".join(f"{st[f'translated_bullets_{lg}']:5}" for lg in LANGS))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    cache.write_json(args.report, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": {"source_records": n_src_records, "source_bullets": n_src_bullets,
                    "translation_caches": n_tr_records, "translated_bullets": n_tr_bullets,
                    "misaligned": len(misaligned), "per_country": {c: dict(s) for c, s in sorted(per_country.items())}},
        "misaligned": misaligned,
        "changes": changes,
    })
    log(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
