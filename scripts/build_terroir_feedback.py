"""Build / merge the per-record review feedback sidecars
(`raw/terroir-facts-feedback/<slug>.json`, see `_lib/terroir_feedback.py`)
from a quality review's evidence directory.

Reads, from `--evidence DIR` (default: the 2026-09-12 full-corpus review):

  confirmed-misleading.json   one row per verified misleading bullet:
                              id, slug, i, country, subsection, mode,
                              where, en, src, reason, corrected_en
  merged.json                 `record_notes` — per-record MISSING / SIB /
                              WRONG_SOURCE / OTHER reviewer notes

and, per slug, `raw/terroir-facts/<slug>.json` for the source shas the
review graded against. Existing sidecars are MERGED: a do-not-claim entry
whose source bullet is already present (token-set ratio ≥ 90) is kept
once, hints and cautions are deduplicated at ≥ 60 (two review lenses
paraphrase one observation), the review is
appended to `reviews`, and `history` is never touched — so a second
review adds to the trail instead of replacing it.

    .venv/bin/python scripts/build_terroir_feedback.py --dry-run
    .venv/bin/python scripts/build_terroir_feedback.py
    .venv/bin/python scripts/build_terroir_feedback.py --only taurasi --only volnay
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.terroir_feedback import FEEDBACK_DIR, clear_cache  # noqa: E402

DEFAULT_EVIDENCE = ROOT / "tmp" / "terroir-facts-review" / "full-review-2026-09-12"
DEFAULT_REVIEW_ID = "review-2026-09-12"
DEFAULT_REVIEWER = "claude-opus-5 review agents, adversarially verified per record"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"

MERGE_THRESHOLD = 90       # do-not-claim: same source bullet
NOTE_MERGE_THRESHOLD = 60  # hints / cautions: two lenses paraphrase one observation (pairs score 60–74)
NOTE_KIND = {"SIB": "sibling-text", "WRONG_SOURCE": "wrong-source", "OTHER": "other"}
_SKIP_NOTE_PREFIXES = ("Batch-wide", "batch-wide")
_SKIP_NOTE_MARKERS = ("Record header says", "record header says")


def log(msg: str) -> None:
    print(f"[feedback] {msg}", file=sys.stderr)


def _present(text: str, pool: list[str], threshold: int = MERGE_THRESHOLD) -> bool:
    return any(fuzz.token_set_ratio(text, p) >= threshold for p in pool if p)


def _caution_kind(note: str, tag: str) -> str:
    low = note.lower()
    if tag == "WRONG_SOURCE":
        if "wiki" in low:
            return "wrong-wikipedia"
        return "wrong-source"
    if tag == "SIB":
        return "sibling-text"
    if "wiki_url" in low or "wikipedia" in low and "points to" in low:
        return "wrong-wikipedia"
    if "typo" in low or "swapped" in low:
        return "source-typo"
    return "other"


def collect(evidence: Path, review_id: str) -> dict[str, dict]:
    """slug → {do_not_claim, capture_if_present, record_cautions} from the
    evidence directory."""
    misleading = json.loads((evidence / "confirmed-misleading.json").read_text(encoding="utf-8"))
    merged = json.loads((evidence / "merged.json").read_text(encoding="utf-8"))
    per: dict[str, dict] = {}

    def slot(slug: str) -> dict:
        return per.setdefault(slug, {"do_not_claim": [], "capture_if_present": [], "record_cautions": []})

    for row in misleading:
        slot(row["slug"])["do_not_claim"].append({
            "claim_en": row.get("en") or "",
            "claim_src": row.get("src") or "",
            "subsection": row.get("subsection") or "",
            "mode": row.get("mode") or "other",
            "stage": row.get("where") or "extraction",
            "why": row.get("reason") or "",
            "fact_index": row.get("i"),
            "review": review_id,
        })
    for slug, notes in (merged.get("record_notes") or {}).items():
        for _lens, tag, note in notes:
            note = " ".join((note or "").split())
            if not note:
                continue
            if tag == "MISSING":
                s = slot(slug)
                if not _present(note, [h["hint"] for h in s["capture_if_present"]], NOTE_MERGE_THRESHOLD):
                    s["capture_if_present"].append({"hint": note, "review": review_id})
                continue
            if note.startswith(_SKIP_NOTE_PREFIXES) or any(m in note for m in _SKIP_NOTE_MARKERS):
                continue
            s = slot(slug)
            if not _present(note, [c["note"] for c in s["record_cautions"]], NOTE_MERGE_THRESHOLD):
                s["record_cautions"].append({
                    "kind": _caution_kind(note, tag), "note": note, "review": review_id,
                })
    return per


def _graded_against(slug: str) -> dict:
    p = TERROIR_FACTS / f"{slug}.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {
        "country": d.get("country") or "fr",
        "source_lang": d.get("source_lang"),
        "cahier_source_sha": d.get("cahier_source_sha"),
        "wiki_source_revision": d.get("wiki_source_revision"),
        "facts_fetched_at": d.get("fetched_at"),
    }


def merge_into(existing: dict | None, slug: str, new: dict, review: dict) -> tuple[dict, Counter]:
    graded = _graded_against(slug)
    fb = existing or {
        "slug": slug, "country": graded.get("country"), "source_lang": graded.get("source_lang"),
        "graded_against": {}, "reviews": [], "do_not_claim": [], "capture_if_present": [],
        "record_cautions": [], "history": [],
    }
    fb.setdefault("history", [])
    if graded:
        fb["country"] = fb.get("country") or graded.get("country")
        fb["source_lang"] = fb.get("source_lang") or graded.get("source_lang")
        fb["graded_against"] = {
            "cahier_source_sha": graded.get("cahier_source_sha"),
            "wiki_source_revision": graded.get("wiki_source_revision"),
            "facts_fetched_at": graded.get("facts_fetched_at"),
        }
    added = Counter()
    if review["id"] not in {r.get("id") for r in fb["reviews"]}:
        fb["reviews"].append(review)
    pool = [c.get("claim_src") or c.get("claim_en") for c in fb["do_not_claim"]]
    for c in new["do_not_claim"]:
        if not _present(c["claim_src"] or c["claim_en"], pool):
            fb["do_not_claim"].append(c)
            pool.append(c["claim_src"] or c["claim_en"])
            added["do_not_claim"] += 1
    pool = [h["hint"] for h in fb["capture_if_present"]]
    for h in new["capture_if_present"]:
        if not _present(h["hint"], pool, NOTE_MERGE_THRESHOLD):
            fb["capture_if_present"].append(h)
            pool.append(h["hint"])
            added["capture_if_present"] += 1
    pool = [n["note"] for n in fb["record_cautions"]]
    for n in new["record_cautions"]:
        if not _present(n["note"], pool, NOTE_MERGE_THRESHOLD):
            fb["record_cautions"].append(n)
            pool.append(n["note"])
            added["record_cautions"] += 1
    return fb, added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    ap.add_argument("--review-id", default=DEFAULT_REVIEW_ID)
    ap.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    ap.add_argument("--out", type=Path, default=FEEDBACK_DIR)
    ap.add_argument("--only", action="append", default=None, metavar="SLUG")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.evidence / "confirmed-misleading.json").exists():
        log(f"error: {args.evidence} has no confirmed-misleading.json")
        return 1
    review = {
        "id": args.review_id, "date": args.review_id.replace("review-", ""),
        "reviewer": args.reviewer, "evidence": str(args.evidence.relative_to(ROOT)) if args.evidence.is_relative_to(ROOT) else str(args.evidence),
    }
    per = collect(args.evidence, args.review_id)
    if args.only:
        per = {s: v for s, v in per.items() if s in set(args.only)}
    totals = Counter()
    written = 0
    args.out.mkdir(parents=True, exist_ok=True)
    for slug in sorted(per):
        path = args.out / f"{slug}.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        fb, added = merge_into(existing, slug, per[slug], review)
        totals.update(added)
        if added and not args.dry_run:
            path.write_text(json.dumps(fb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            written += 1
    clear_cache()
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "review": review, "records": len(per), "written": written,
        "added": dict(totals),
        "records_with_do_not_claim": sum(1 for v in per.values() if v["do_not_claim"]),
        "records_with_capture_hints": sum(1 for v in per.values() if v["capture_if_present"]),
        "records_with_cautions": sum(1 for v in per.values() if v["record_cautions"]),
    }
    if not args.dry_run:
        (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(("dry-run: " if args.dry_run else "") + json.dumps(manifest["added"]) + f" over {len(per)} records"
        f" ({manifest['records_with_do_not_claim']} with do-not-claim, "
        f"{manifest['records_with_capture_hints']} with hints, {manifest['records_with_cautions']} with cautions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
