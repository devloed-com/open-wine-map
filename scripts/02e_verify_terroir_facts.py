"""Translation back-check over the stage-02e terroir-fact caches (every
country, every target locale) — review 2026-09-12 recommendation R6.
Runs after 02e:

    02d --refresh  →  02d_verify  →  02e  →  02e_verify  →  04

Per (record, locale) ONE model request compares every translated bullet
with its source-language bullet (`_lib/terroir_backcheck`): changed
numbers, dropped or upgraded hedges, wrong entities and back-formed
names, watch-list false friends (generoso → generous, tirage →
disgorgement, climat → climate, Lehm → clay), untranslated common nouns
and missing exonyms (the deterministic `exonyms.exonym_hits` detector
feeds the model its hits). Fixes are applied under the gate's guards (no
new numbers, no arrows, sane length); every checked bullet carries
`check` ({verdict, issue[, original]}) and the cache a `backcheck` block
keyed on the source and translated shas, so the pass is incremental —
a re-translated record is re-checked, an unchanged one is not.

Only caches aligned with their source (same `source_facts_sha`, same
length) are checked; a stale one is left for 02e. Writes go through the
per-run backup (`scripts/rollback_terroir_facts.py --run <id>`).

Usage:
  .venv/bin/python scripts/02e_verify_terroir_facts.py --batch --provider anthropic
  .venv/bin/python scripts/02e_verify_terroir_facts.py --lang en --only rueda --provider anthropic
  .venv/bin/python scripts/02e_verify_terroir_facts.py --sample 40 --dry-run --provider anthropic
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, providers, terroir_backup  # noqa: E402
from _lib.exonyms import gi_forms_from_names  # noqa: E402
from _lib.prompt_cache import mark_cached  # noqa: E402
from _lib.terroir_backcheck import (  # noqa: E402
    BACKCHECK_VERSION,
    apply_fixes,
    build_user_message,
    parse_checks,
    system_prompt,
)
from _lib.terroir_cache import LANGS, TERROIR, TRANSLATIONS, write_translation_cache  # noqa: E402
from _lib.terroir_dedupe import facts_sha  # noqa: E402
from _lib.terroir_feedback import append_history, load_feedback  # noqa: E402

MANIFEST = TERROIR / "manifest-backcheck.json"
REPORT_DIR = ROOT / "tmp" / "terroir-facts-review"
BATCH_SIDECAR = ROOT / "raw" / ".batch" / "02e-verify.json"
MAX_TOKENS = 4000


def log(msg: str) -> None:
    print(f"[02e-verify] {msg}", file=sys.stderr)


def _translated_sha(facts: list[dict]) -> str:
    return facts_sha(facts)


def needs_check(t: dict, src: dict, *, refresh: bool) -> str | None:
    """None when the cache is due; else why it is skipped."""
    if t.get("mode") == "verbatim" or not t.get("facts"):
        return "verbatim-or-empty"
    sfacts = src.get("facts") or []
    if not sfacts or t.get("source_facts_sha") != facts_sha(sfacts) or len(t["facts"]) != len(sfacts):
        return "stale"
    if refresh:
        return None
    b = t.get("backcheck") or {}
    if not b:
        return None
    if (
        b.get("version") == BACKCHECK_VERSION
        and b.get("source_facts_sha") == t.get("source_facts_sha")
        and b.get("translated_sha") == _translated_sha(t["facts"])
    ):
        return "checked"
    return None


def select(
    *, langs: list[str], countries: set[str] | None, only: set[str] | None, sample: int, limit: int, refresh: bool,
) -> tuple[list[tuple[str, str, Path, dict, dict]], Counter]:
    """[(slug, lang, path, translation, source)] due for a check."""
    skipped: Counter = Counter()
    out: list[tuple[str, str, Path, dict, dict]] = []
    sources: dict[str, dict | None] = {}
    for lang in langs:
        d = TRANSLATIONS / lang
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            slug = p.stem
            if only and slug not in only:
                continue
            if slug not in sources:
                sources[slug] = cache.read_json_or_none(TERROIR / f"{slug}.json")
            src = sources[slug]
            if not src or src.get("mode") == "verbatim":
                skipped["no-source"] += 1
                continue
            if countries and (src.get("country") or "fr") not in countries:
                continue
            t = cache.read_json_or_none(p)
            if not t:
                skipped["unreadable"] += 1
                continue
            why = needs_check(t, src, refresh=refresh)
            if why:
                skipped[why] += 1
                continue
            out.append((slug, lang, p, t, src))
    if sample and len(out) > sample:
        random.seed(0)
        out = sorted(random.sample(out, sample), key=lambda x: (x[0], x[1]))
    if limit:
        out = out[:limit]
    return out, skipped


def check_one(
    provider, model_id: str, item: tuple[str, str, Path, dict, dict], *, run: str, dry_run: bool,
    gi_forms: frozenset[str],
) -> dict:
    slug, lang, path, t, src = item
    country = src.get("country") or "fr"
    source_lang = src.get("source_lang") or ("fr" if country == "fr" else country)
    sfacts = src.get("facts") or []
    user = build_user_message(
        name=src.get("name") or slug, source_lang=source_lang, target_lang=lang,
        source_facts=sfacts, translated=t["facts"], feedback=load_feedback(slug), gi_forms=gi_forms,
        slug=slug,
    )
    try:
        raw = provider.chat(system=mark_cached(system_prompt()), user=user, max_tokens=MAX_TOKENS, num_ctx=16384)
    except Exception as e:  # noqa: BLE001
        return {"slug": slug, "lang": lang, "country": country, "status": "error", "error": str(e)[:200]}
    checks, err = parse_checks(raw, len(t["facts"]))
    if checks is None:
        return {"slug": slug, "lang": lang, "country": country, "status": "parse_error", "error": err}
    res = apply_fixes(t["facts"], sfacts, checks, lang=lang, run=run, model=model_id)
    row = {
        "slug": slug, "lang": lang, "country": country, "status": "ok", "n": len(t["facts"]),
        "n_fixed": len(res["fixed"]), "n_rejected": len(res["rejected"]),
        "n_missing_fixes": len(res["missing_fixes"]),
        "n_flagged": sum(1 for c in checks if c["verdict"] == "fix"),
        "fixed": res["fixed"], "rejected": res["rejected"],
        "issues": [{"i": i, **c} for i, c in enumerate(checks) if c["verdict"] == "fix"],
    }
    if dry_run:
        return row
    t["facts"] = res["facts"]
    t["backcheck"] = {
        "version": BACKCHECK_VERSION, "run": run, "model": model_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_facts_sha": t.get("source_facts_sha"), "translated_sha": _translated_sha(res["facts"]),
        "n_fixed": len(res["fixed"]), "n_rejected": len(res["rejected"]),
        "n_missing_fixes": len(res["missing_fixes"]),
    }
    write_translation_cache(path, t)
    if res["fixed"]:
        append_history(slug, {
            "run": run, "kind": "backcheck", "lang": lang, "model": model_id,
            "fixed": [{"from": f["from"], "to": f["to"], "issue": f["issue"]} for f in res["fixed"]],
        })
    return row


def _summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    by_lang: dict[str, Counter] = {}
    for r in ok:
        c = by_lang.setdefault(r["lang"], Counter())
        c["caches"] += 1
        for k in ("n", "n_fixed", "n_rejected", "n_flagged", "n_missing_fixes"):
            c[k] += r[k]
    tot = Counter()
    for c in by_lang.values():
        tot.update(c)
    return {
        "caches_selected": len(rows), "caches_ok": len(ok),
        "caches_error": sum(1 for r in rows if r.get("status") == "error"),
        "caches_parse_error": sum(1 for r in rows if r.get("status") == "parse_error"),
        "totals": dict(tot),
        "bullets_fixed_share": round(tot["n_fixed"] / tot["n"], 4) if tot["n"] else 0,
        "by_lang": {k: dict(v) for k, v in sorted(by_lang.items())},
    }


def run_checks(provider, model_id, items, *, run, dry_run, quiet, gi_forms) -> list[dict]:
    rows: list[dict] = []
    for item in tqdm(items, desc="02e-verify", leave=False, disable=quiet):
        row = check_one(provider, model_id, item, run=run, dry_run=dry_run, gi_forms=gi_forms)
        rows.append(row)
        if not quiet:
            if row.get("status") == "ok":
                log(f"{row['slug']:40} {row['lang']} n={row['n']:2} fixed={row['n_fixed']}"
                    + (f" rejected={row['n_rejected']}" if row["n_rejected"] else ""))
            else:
                log(f"{row['slug']:40} {row['lang']} {row.get('status')}: {row.get('error', '')[:120]}")
    return rows


def _gi_forms() -> frozenset[str]:
    names = []
    for p in TERROIR.glob("*.json"):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if d and d.get("name"):
            names.append(d["name"])
    return gi_forms_from_names(names)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral", "ollama"))
    ap.add_argument("--model", default=None, help="default: providers.STAGE_DEFAULTS['backcheck']")
    ap.add_argument("--thinking", default=None, choices=("disabled", "adaptive"))
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--lang", action="append", default=None, help="target locale(s); default all four")
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--only-file", default=None, help="JSON list (or {\"slugs\": [...]}) of slugs to restrict to")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.only_file:
        data = json.loads(Path(args.only_file).read_text(encoding="utf-8"))
        args.only = list(args.only or []) + list(data.get("slugs") if isinstance(data, dict) else data)

    run = terroir_backup.run_id()
    langs = args.lang or list(LANGS)
    items, skipped = select(
        langs=langs, countries=set(args.country) if args.country else None,
        only=set(args.only) if args.only else None, sample=args.sample, limit=args.limit, refresh=args.refresh,
    )
    log(f"{len(items)} translation caches due (skipped: {dict(skipped)})")
    if not items:
        return 0
    gi_forms = _gi_forms()
    t0 = time.monotonic()
    rows: list[dict] = []
    batch_stats: dict | None = None
    if args.batch:
        if not batch.supports(args.provider):
            log("--batch requires --provider anthropic|mistral")
            return 1
        model_id = args.model or batch.default_model(args.provider, stage="backcheck")
        thinking = args.thinking or batch.default_thinking(args.provider, stage="backcheck")
        log(f"batch: {len(items)} caches (provider={args.provider}, model={model_id}, thinking={thinking}, "
            f"dry_run={args.dry_run}, run={run})")

        def run_loop(prov):
            nonlocal rows
            collecting = getattr(prov, "kind", "") == "collecting"
            rows = run_checks(prov, model_id, items, run=run, dry_run=args.dry_run or collecting,
                              quiet=collecting or args.quiet, gi_forms=gi_forms)

        batch_stats = batch.run_two_pass(provider=args.provider, model=model_id, sidecar=BATCH_SIDECAR,
                                         run_loop=run_loop, thinking=thinking)
        kind = f"{args.provider}-api"
    else:
        provider, model_id = providers.make_provider(
            args.provider, model=args.model, ollama_url=args.ollama_url, mistral_url=args.mistral_url,
            stage="backcheck", thinking=args.thinking,
        )
        rows = run_checks(provider, model_id, items, run=run, dry_run=args.dry_run, quiet=args.quiet, gi_forms=gi_forms)
        kind = provider.kind

    summary = _summary(rows)
    if batch_stats:
        summary["batch"] = batch_stats
    summary.update({
        "run": run, "model": model_id, "provider_kind": kind, "dry_run": args.dry_run,
        "version": BACKCHECK_VERSION, "elapsed_seconds": round(time.monotonic() - t0, 1),
        "skipped": dict(skipped),
    })
    report = Path(args.report) if args.report else REPORT_DIR / f"backcheck-{run}{'-dryrun' if args.dry_run else ''}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "caches": rows}, ensure_ascii=False, indent=1, default=str) + "\n",
                      encoding="utf-8")
    if not args.dry_run:
        cache.write_json(MANIFEST, {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **summary},
                         sort_keys=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    log(f"report → {report.relative_to(ROOT) if report.is_relative_to(ROOT) else report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
