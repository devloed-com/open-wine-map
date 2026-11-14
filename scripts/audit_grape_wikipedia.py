#!/usr/bin/env python3
"""Does each grape pill's Wikipedia article describe that grape?

Stage 02b accepts an article when it is about *a* grape (`is_grape_summary`),
not when it is about *this* one. Two ways it goes wrong, both found on
2026-11-14 behind the Palomino question (two pills of one card opening the
same extract):

  STALE-PASSPORT   the article was found through a VIVC passport — its prime
                   name, a synonym, a donor slug of the same number — that is
                   no longer the slug's (a corrected or withdrawn pin).
                   Pugnitello → Montepulciano, Picardan → Bourboulenc. Stage 04
                   withholds these (`_lib/grape_wiki_identity.py`) and the 02b
                   fetcher re-fetches them on its next run for the slug.
  OTHER-CULTIVAR   the article's title is none of the slug's own names (slug,
                   VIVC prime, VIVC synonyms) and IS the name of another corpus
                   slug with a different variety number: a VIVC synonym that
                   Wikipedia redirects to the better-known homonym. Chenanson
                   → "Chenin blanc" (synonym VAALBLAAR STEIN), Raffiat de
                   Moncade → "Gewürztraminer" (ROUSSELET), Gamay de Chaudenay
                   → "Aligoté" (PLANT GRIS).
  UNVERIFIED       the title is none of the slug's own names and no other slug
                   owns it — a local name VIVC does not list (Xarel·lo's
                   "Charelo"), a family article, or another wrong binding.

OTHER-CULTIVAR and UNVERIFIED are a curator queue, not a verdict: Sousão's
"Sezão" and Lledoner pelut's "Grenache" are right. A wrong one is fixed by
pinning the right title (or `null`) in raw/wikipedia/grape_overrides.json and
re-fetching that slug (`02b_fetch_grape_lexicon.py --only SLUG`).

Read-only. `--langs en,fr,es,nl` (default), `--json PATH`, `--all` (list every
slug of a bucket, not the top 40).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.grape_corpus import collect_grape_slugs  # noqa: E402
from _lib.grape_wiki_identity import (  # noqa: E402
    article_is_anothers,
    consulted_vivc_id,
    current_vivc_ids,
    passport_match_is_stale,
    title_is_own,
)

ROOT = Path(__file__).resolve().parents[1]
LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes"


def classify(langs: list[str]) -> dict[str, list[dict]]:
    current = current_vivc_ids()
    corpus = collect_grape_slugs()
    out: dict[str, list[dict]] = defaultdict(list)
    for lang in langs:
        for f in sorted((LEXICON_DIR / lang).glob("*.json")) if (LEXICON_DIR / lang).exists() else ():
            slug = f.stem
            if slug not in corpus:
                continue
            rec = json.loads(f.read_text(encoding="utf-8"))
            if rec.get("missing") or rec.get("error") or not rec.get("extract"):
                continue
            title = rec.get("wikipedia_title") or ""
            row = {
                "slug": slug, "lang": lang, "title": title,
                "matched_via": rec.get("matched_via"), "vivc_now": current.get(slug),
                "vivc_consulted": consulted_vivc_id(rec),
            }
            if passport_match_is_stale(rec, slug):
                out["STALE-PASSPORT"].append(row)
            elif title_is_own(slug, title):
                continue
            elif owners := article_is_anothers(slug, title):
                row["owned_by"] = owners
                out["OTHER-CULTIVAR"].append(row)
            else:
                out["UNVERIFIED"].append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--langs", default="en,fr,es,nl")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    buckets = classify(langs)
    for name in ("STALE-PASSPORT", "OTHER-CULTIVAR", "UNVERIFIED"):
        rows = buckets.get(name, [])
        by_slug: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_slug[row["slug"]].append(row)
        print(f"\n== {name}: {len(rows)} (slug, locale) entries, {len(by_slug)} slugs")
        shown = sorted(by_slug.items())
        for slug, items in shown if args.all else shown[:40]:
            parts = "; ".join(
                f"{r['lang']}: {r['title']!r} via {r['matched_via'] or 'title'}"
                + (f" (owned by {', '.join(r['owned_by'])})" if r.get("owned_by") else "")
                for r in items
            )
            print(f"  {slug:28} #{items[0]['vivc_now'] or '—'}  {parts}")
        if not args.all and len(shown) > 40:
            print(f"  … {len(shown) - 40} more (--all)")
    stale = sorted({r["slug"] for r in buckets.get("STALE-PASSPORT", [])})
    if stale:
        print("\nre-fetch the stale ones (one process; Wikimedia throttles a parallel walk):")
        print("  .venv/bin/python scripts/02b_fetch_grape_lexicon.py " + " ".join(f"--only {s}" for s in stale))
    if args.json:
        args.json.write_text(json.dumps(buckets, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n[json] {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
