"""Post-pass over the stage-02d terroir-fact caches: re-grade every fact's
quotes with the ellipsis-aware coverage rule and rewrite
`cahier_coverage` / `wiki_coverage` / `provenance` in place. No LLM call.

Why: the model legitimately joins two source spans with "[…]" in a quote.
The original single-contiguous-match test then scored such a quote below
the 0.6 threshold, so hundreds of facts whose `cahier_quote` is verbatim
cahier text carried `provenance: wiki` (and the map panel attributed them
to Wikipedia). `_lib.terroir_coverage.fuzzy_coverage` now grades a
multi-span quote span by span; this script applies that rule to the
caches that were graded before it existed.

How: each country's stage-02d module is loaded and asked for the exact
source text it graded against — the lien (for CH/MT/GB the règlement /
spec context) plus the per-sub-section Wikipedia hint — so the result is
precisely what 02d computes today. A cache whose `cahier_source_sha` or
`wiki_source_revision` no longer matches the current sources is skipped
and listed: it is stale for 02d anyway. Nothing is dropped: the new grade
of a previously-kept fact is never lower than its old one, so provenance
only ever moves towards `cahier` / `both`.

The stage-02e translation caches copy each fact's `provenance`; the
aligned ones (same `source_facts_sha`, same length) are updated in the
same pass so the four locales agree with the source cache. Stage 04 reads
provenance from the source cache, so the panel picks the change up at the
next build.

Usage:
  .venv/bin/python scripts/recompute_terroir_provenance.py --dry-run
  .venv/bin/python scripts/recompute_terroir_provenance.py [--country cc …] [--only SLUG …]
      [--report tmp/terroir-facts-review/provenance-recompute.json]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache  # noqa: E402
from _lib.terroir_coverage import SourceMatcher, fuzzy_coverage, provenance_for  # noqa: E402
from _lib.terroir_dedupe import facts_sha  # noqa: E402

TERROIR = ROOT / "raw" / "terroir-facts"
TRANSLATIONS = ROOT / "raw" / "translations" / "terroir-facts"
LANGS = ("en", "fr", "es", "nl")
DEFAULT_REPORT = ROOT / "tmp" / "terroir-facts-review" / "provenance-recompute.json"


def log(msg: str) -> None:
    print(f"[provenance] {msg}", file=sys.stderr)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stage_path(country: str) -> Path:
    if country == "fr":
        return ROOT / "scripts" / "02d_extract_terroir_facts.py"
    return ROOT / "scripts" / country / "02d_extract_terroir_facts.py"


def load_stage(country: str):
    path = stage_path(country)
    spec = importlib.util.spec_from_file_location(f"owm_02d_{country}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Sources:
    cahier: str
    cahier_sha: str
    wiki_revision: object
    hints: dict[str, str]
    _matcher: SourceMatcher | None = None

    @property
    def matcher(self) -> SourceMatcher:
        if self._matcher is None:
            self._matcher = SourceMatcher(self.cahier)
        return self._matcher


def _wiki_record(mod, rec: dict, lang: str) -> dict:
    slug = rec["slug"]
    if hasattr(mod, "_wiki_record_for"):
        params = inspect.signature(mod._wiki_record_for).parameters
        return mod._wiki_record_for(slug, lang) if "lang" in params else mod._wiki_record_for(slug)
    wiki_path = mod.WIKI_AOCS / f"{slug}.json"
    if not wiki_path.exists():
        return {}
    try:
        return json.loads(wiki_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _hints(mod, wiki: dict, lang: str, sub_keys: list[str]) -> dict[str, str]:
    fn = mod._wiki_hint_for_subsection
    if "lang" in inspect.signature(fn).parameters:
        return {k: fn(wiki, lang, k) for k in sub_keys}
    return {k: fn(wiki, k) for k in sub_keys}


def resolve_sources(country: str) -> dict[str, Sources]:
    """slug → the exact cahier text + per-sub-section wiki hints stage 02d
    grades against for this country, built through the stage's own code."""
    mod = load_stage(country)
    out: dict[str, Sources] = {}
    if country == "fr":
        for job in mod.enumerate_aocs():
            out[job["slug"]] = Sources(
                job["lien"], job["lien_sha"],
                job["wiki_meta"]["wiki_source_revision"], dict(job["wiki_hints"]),
            )
        return out
    sub_keys = [s["key"] for s in mod.SUBSECTIONS]
    default_lang = getattr(mod, "SOURCE_LANG", None) or "fr"
    for rec in mod.collect_targets():
        lang = rec.get("source_lang") or default_lang
        if "_cahier_ctx" in rec:
            cahier = rec["_cahier_ctx"] or ""
            wiki = rec.get("_wiki_record") or {}
        else:
            cahier = rec.get("link_to_terroir") or ""
            wiki = _wiki_record(mod, rec, lang)
        out[rec["slug"]] = Sources(
            cahier, _sha(cahier), wiki.get("revision") if wiki else None,
            _hints(mod, wiki, lang, sub_keys),
        )
    return out


@dataclass
class Regrade:
    changed: list[dict]
    coverage_only: int = 0
    ungrounded_now: int = 0


def regrade_facts(facts: list[dict], src: Sources) -> Regrade:
    out = Regrade(changed=[])
    for i, f in enumerate(facts):
        cq = (f.get("cahier_quote") or "").strip()
        wq = (f.get("wiki_quote") or "").strip()
        cc = src.matcher.coverage(cq) if cq else 0.0
        wc = fuzzy_coverage(wq, src.hints.get(f.get("subsection") or "", "")) if wq else 0.0
        prov = provenance_for(cc, wc)
        if prov is None:
            out.ungrounded_now += 1
            continue
        old = (f.get("cahier_coverage"), f.get("wiki_coverage"), f.get("provenance"))
        new = (round(cc, 3), round(wc, 3), prov)
        if new == old:
            continue
        if new[2] == old[2]:
            out.coverage_only += 1
        else:
            out.changed.append({
                "index": i,
                "old_provenance": old[2], "new_provenance": prov,
                "old_cahier_coverage": old[0], "new_cahier_coverage": new[0],
                "old_wiki_coverage": old[1], "new_wiki_coverage": new[1],
                "bullet": f.get("bullet") or "",
                "cahier_quote": cq[:200],
            })
        f["cahier_coverage"], f["wiki_coverage"], f["provenance"] = new
    return out


def sync_translation_provenance(slug: str, facts: list[dict], *, dry_run: bool) -> tuple[int, list[str]]:
    """Copy the source cache's provenance into the aligned bullet-mode
    translation caches. Returns (n_written, misaligned_langs)."""
    sha = facts_sha(facts)
    written = 0
    misaligned: list[str] = []
    for lang in LANGS:
        tp = TRANSLATIONS / lang / f"{slug}.json"
        if not tp.exists():
            continue
        t = cache.read_json_or_none(tp)
        if not t or t.get("mode") == "verbatim" or not t.get("facts"):
            continue
        if t.get("source_facts_sha") != sha or len(t["facts"]) != len(facts):
            misaligned.append(lang)
            continue
        changed = False
        for tf, sf in zip(t["facts"], facts):
            if tf.get("provenance") != sf.get("provenance"):
                tf["provenance"] = sf.get("provenance")
                changed = True
        if changed:
            written += 1
            if not dry_run:
                cache.write_json(tp, t)
    return written, misaligned


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--country", action="append", default=[], help="restrict to a country code (repeatable)")
    ap.add_argument("--only", action="append", default=[], help="restrict to a slug (repeatable)")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="JSON report path")
    args = ap.parse_args()

    by_country: dict[str, list[Path]] = {}
    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if not d or d.get("mode") == "verbatim" or not d.get("facts"):
            continue
        cc = d.get("country") or "fr"
        if args.country and cc not in args.country:
            continue
        if args.only and d.get("slug") not in args.only:
            continue
        by_country.setdefault(cc, []).append(p)

    transitions: Counter = Counter()
    per_country: dict[str, Counter] = {}
    skipped: list[dict] = []
    changes: list[dict] = []
    n_records_written = 0
    n_translations_written = 0
    misaligned_translations: list[dict] = []

    for cc in sorted(by_country):
        paths = by_country[cc]
        log(f"{cc}: resolving sources for {len(paths)} cached records …")
        try:
            sources = resolve_sources(cc)
        except Exception as e:  # noqa: BLE001
            log(f"{cc}: FAILED to load stage 02d sources: {e!r} — skipping country")
            skipped.extend({"slug": p.stem, "country": cc, "reason": f"stage-load-error: {e!r}"} for p in paths)
            continue
        stats = per_country.setdefault(cc, Counter())
        for p in paths:
            d = cache.read_json_or_none(p)
            slug = d.get("slug") or p.stem
            src = sources.get(slug)
            if src is None:
                skipped.append({"slug": slug, "country": cc, "reason": "no-source-today"})
                stats["skipped"] += 1
                continue
            if d.get("cahier_source_sha") != src.cahier_sha:
                skipped.append({"slug": slug, "country": cc, "reason": "cahier-sha-drift"})
                stats["skipped"] += 1
                continue
            if d.get("wiki_source_revision") != src.wiki_revision:
                skipped.append({"slug": slug, "country": cc, "reason": "wiki-revision-drift"})
                stats["skipped"] += 1
                continue
            facts = d["facts"]
            res = regrade_facts(facts, src)
            stats["facts"] += len(facts)
            stats["coverage_only"] += res.coverage_only
            stats["ungrounded_now"] += res.ungrounded_now
            stats["provenance_changed"] += len(res.changed)
            for ch in res.changed:
                transitions[(ch["old_provenance"], ch["new_provenance"])] += 1
                changes.append({"slug": slug, "country": cc, **ch})
            if res.changed or res.coverage_only:
                n_records_written += 1
                if not args.dry_run:
                    cache.write_json(p, d)
            if res.changed:
                n_t, mis = sync_translation_provenance(slug, facts, dry_run=args.dry_run)
                n_translations_written += n_t
                misaligned_translations.extend({"slug": slug, "lang": lang} for lang in mis)

    verb = "would rewrite" if args.dry_run else "rewrote"
    log("")
    log(f"{verb} {n_records_written} source caches; provenance changed on {len(changes)} facts; "
        f"{n_translations_written} translation caches synced; "
        f"{len(misaligned_translations)} translation caches misaligned (left for 02e); "
        f"{len(skipped)} records skipped")
    log("transitions: " + ", ".join(f"{a}→{b}: {n}" for (a, b), n in transitions.most_common()))
    log(f"{'cc':4} {'facts':>6} {'prov-chg':>8} {'cov-only':>8} {'ungrnd':>6} {'skip':>5}")
    for cc, st in sorted(per_country.items()):
        log(f"{cc:4} {st['facts']:6} {st['provenance_changed']:8} {st['coverage_only']:8} "
            f"{st['ungrounded_now']:6} {st['skipped']:5}")
    if skipped:
        reasons = Counter(s["reason"] for s in skipped)
        log("skipped by reason: " + ", ".join(f"{r}: {n}" for r, n in reasons.most_common()))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    cache.write_json(args.report, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": {
            "records_rewritten": n_records_written,
            "facts_provenance_changed": len(changes),
            "translation_caches_synced": n_translations_written,
            "translation_caches_misaligned": len(misaligned_translations),
            "records_skipped": len(skipped),
            "transitions": {f"{a}->{b}": n for (a, b), n in transitions.most_common()},
            "per_country": {cc: dict(st) for cc, st in sorted(per_country.items())},
        },
        "skipped": skipped,
        "misaligned_translations": misaligned_translations,
        "changes": changes,
    })
    log(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
