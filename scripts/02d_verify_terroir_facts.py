"""Claim-support gate over the stage-02d terroir-fact caches (all
countries) — review 2026-09-12 recommendations R2 (claim-support gate),
R3 (earned `interactions`), R7 (sub-section per fact), R8 (semantic
dedupe). Runs between 02d and 02e:

    02d --refresh  →  02d_verify  →  02e  →  02e_verify  →  04

Per record, ONE model request grades every bullet against the exact
source text stage 02d graded against (`_lib/terroir_sources`, through the
country's own 02d module), the per-sub-section Wikipedia hints and the
record's review feedback (`raw/terroir-facts-feedback/<slug>.json`:
verified-misleading claims become explicit checks, record cautions
disqualify pasted or mis-bound text). Verdicts are applied by
`_lib/terroir_gate.apply_verdicts`: supported bullets stay, over-claiming
bullets are replaced by the model's narrower rewrite (guarded — no new
numbers, no arrows), unsupported / foreign / tautological / restated
bullets are dropped, clearly misfiled bullets move sub-section.

Writes, per gated record (through the per-run backup, so
`scripts/rollback_terroir_facts.py --run <id>` undoes it):
  raw/terroir-facts/<slug>.json      facts (with `support` per fact) +
                                     a `gate` block (counts, dropped
                                     bullets, shas the gate keyed on)
  raw/translations/terroir-facts/…   index-aligned prune for pure drops;
                                     re-keyed `pending:` when a bullet
                                     was rewritten so 02e re-translates
  raw/terroir-facts-feedback/<slug>  a `history` entry (kind "gate")
  raw/terroir-facts/manifest-gate.json + tmp/terroir-facts-review/gate-<run>.json

Incremental: a record is gated when it has no `gate` block or its facts
or source sha changed since (a 02d re-run, a post-pass). `--refresh`
re-gates everything selected; `--dry-run` grades and writes the report
only (with `--sample N` this is the cheap LLM audit of R9).

Providers: anthropic — default `claude-opus-5` with adaptive thinking
(`providers.STAGE_DEFAULTS["gate"]`; `--model` / `--thinking` override) /
mistral / ollama; `--batch` submits every selected record as one
Batch-API job (resumable via raw/.batch/02d-verify.json).

Usage:
  .venv/bin/python scripts/02d_verify_terroir_facts.py --batch --provider anthropic
  .venv/bin/python scripts/02d_verify_terroir_facts.py --country it --only barolo --provider anthropic
  .venv/bin/python scripts/02d_verify_terroir_facts.py --sample 50 --dry-run --provider anthropic
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
from _lib.terroir_cache import (  # noqa: E402
    TERROIR,
    prune_translations,
    sync_translation_meta,
    write_source_cache,
)
from _lib.terroir_dedupe import facts_sha  # noqa: E402
from _lib.terroir_feedback import append_history, load_feedback  # noqa: E402
from _lib.terroir_gate import (  # noqa: E402
    GATE_VERSION,
    SYSTEM,
    apply_verdicts,
    build_user_message,
    parse_verdicts,
)
from _lib.terroir_sources import COUNTRIES, Sources, resolve_sources  # noqa: E402

MANIFEST = TERROIR / "manifest-gate.json"
REPORT_DIR = ROOT / "tmp" / "terroir-facts-review"
BATCH_SIDECAR = ROOT / "raw" / ".batch" / "02d-verify.json"
MAX_TOKENS = 8000  # Opus 5 with adaptive thinking: thinking + the JSON reply


def log(msg: str) -> None:
    print(f"[02d-verify] {msg}", file=sys.stderr)


# ────────────────────────────────────────────────────────── selection ──


def needs_gate(d: dict, *, refresh: bool) -> bool:
    facts = d.get("facts") or []
    if not facts:
        return False
    if refresh:
        return True
    g = d.get("gate") or {}
    if not g:
        return True
    return (
        g.get("facts_sha_after") != facts_sha(facts)
        or g.get("cahier_source_sha") != d.get("cahier_source_sha")
        or g.get("version") != GATE_VERSION
    )


def select_records(
    *, countries: set[str] | None, only: set[str] | None, sample: int, limit: int, refresh: bool,
) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        if only and p.stem not in only:
            continue
        d = cache.read_json_or_none(p)
        if not d or d.get("mode") == "verbatim":
            continue
        if countries and (d.get("country") or "fr") not in countries:
            continue
        if not needs_gate(d, refresh=refresh):
            continue
        d["slug"] = d.get("slug") or p.stem
        out.append((p, d))
    if sample and len(out) > sample:
        random.seed(0)
        out = sorted(random.sample(out, sample), key=lambda t: t[0])
    if limit:
        out = out[:limit]
    return out


class SourceResolver:
    def __init__(self) -> None:
        self._by_country: dict[str, dict[str, Sources] | None] = {}
        self.failed: dict[str, str] = {}

    def get(self, country: str) -> dict[str, Sources] | None:
        if country not in self._by_country:
            if country not in COUNTRIES:
                self.failed[country] = "no stage-02d module"
                self._by_country[country] = None
            else:
                log(f"{country}: resolving stage-02d sources …")
                try:
                    self._by_country[country] = resolve_sources(country)
                except Exception as e:  # noqa: BLE001
                    self.failed[country] = repr(e)
                    log(f"{country}: FAILED to resolve sources: {e!r}")
                    self._by_country[country] = None
        return self._by_country[country]


# ─────────────────────────────────────────────────────────── one record ──


def gate_record(
    provider, model_id: str, path: Path, d: dict, src: Sources, *, run: str, dry_run: bool,
) -> dict:
    """Grade + apply for one record. Returns the report row; writes the
    cache / translations / feedback history unless `dry_run`."""
    slug = d["slug"]
    country = d.get("country") or "fr"
    source_lang = d.get("source_lang") or ("fr" if country == "fr" else country)
    facts = d.get("facts") or []
    fb = load_feedback(slug)
    user = build_user_message(
        name=d.get("name") or slug, country=country, source_lang=source_lang,
        cahier=src.cahier, hints=src.hints, facts=facts, feedback=fb,
    )
    try:
        raw = provider.chat(system=SYSTEM, user=user, max_tokens=MAX_TOKENS, num_ctx=32768)
    except Exception as e:  # noqa: BLE001
        return {"slug": slug, "country": country, "status": "error", "error": str(e)[:200]}
    verdicts, err = parse_verdicts(raw, len(facts))
    if verdicts is None:
        return {"slug": slug, "country": country, "status": "parse_error", "error": err}

    res = apply_verdicts(facts, verdicts, source=src.cahier, source_lang=source_lang, run=run, model=model_id)
    old_sha = facts_sha(facts)
    new_sha = facts_sha(res["facts"])
    row = {
        "slug": slug, "country": country, "status": "ok",
        "n_before": len(facts), "n_after": len(res["facts"]),
        "n_supported": sum(1 for f in res["facts"] if f["support"]["verdict"] == "supported"),
        "n_rewritten": len(res["rewritten"]), "n_dropped": len(res["dropped"]),
        "n_moved": len(res["moved"]), "n_rejected_rewrites": len(res["rejected_rewrites"]),
        "dropped": res["dropped"], "rewritten": res["rewritten"], "moved": res["moved"],
        "rejected_rewrites": res["rejected_rewrites"],
        "verdicts": [{"i": i, **v} for i, v in enumerate(verdicts)],
    }
    if dry_run:
        return row

    d["facts"] = res["facts"]
    d["gate"] = {
        "version": GATE_VERSION, "run": run, "model": model_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "facts_sha_before": old_sha, "facts_sha_after": new_sha,
        "cahier_source_sha": d.get("cahier_source_sha"),
        "wiki_source_revision": d.get("wiki_source_revision"),
        "n_supported": row["n_supported"], "n_rewritten": row["n_rewritten"],
        "n_dropped": row["n_dropped"], "n_moved": row["n_moved"],
        "n_rejected_rewrites": row["n_rejected_rewrites"],
        "dropped": res["dropped"],
    }
    write_source_cache(path, d)
    # Translations: index-aligned prune for drops; a rewrite changes the text,
    # so the caches are re-keyed `pending:` — still length-aligned for the
    # interim render, but stale for 02e, which re-translates the record.
    if res["dropped"] or res["text_changed"]:
        key = new_sha if not res["text_changed"] else f"pending:{new_sha}"
        pruned, stale = prune_translations(slug, old_sha, len(facts), res["kept_indices"], key, dry_run=False)
        row["translations_pruned"] = pruned
        row["translations_stale"] = [s["lang"] for s in stale]
    if res["moved"] and not res["text_changed"]:
        sync_translation_meta(slug, res["facts"], dry_run=False)
    if res["dropped"] or res["rewritten"] or res["moved"]:
        append_history(slug, {
            "run": run, "kind": "gate", "model": model_id,
            "dropped": [{"bullet": x["bullet"], "note": x["note"]} for x in res["dropped"]],
            "rewritten": [{"from": x["from"], "to": x["to"]} for x in res["rewritten"]],
            "moved": [{"from": x["from"], "to": x["to"], "index": x["index"]} for x in res["moved"]],
        })
    return row


# ────────────────────────────────────────────────────────────── main ──


def _summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    by_country: dict[str, Counter] = {}
    for r in ok:
        c = by_country.setdefault(r["country"], Counter())
        c["records"] += 1
        for k in ("n_before", "n_after", "n_supported", "n_rewritten", "n_dropped", "n_moved", "n_rejected_rewrites"):
            c[k] += r[k]
    tot = Counter()
    for c in by_country.values():
        tot.update(c)
    return {
        "records_selected": len(rows), "records_ok": len(ok),
        "records_error": sum(1 for r in rows if r.get("status") == "error"),
        "records_parse_error": sum(1 for r in rows if r.get("status") == "parse_error"),
        "records_no_source": sum(1 for r in rows if r.get("status") == "no_source"),
        "totals": dict(tot),
        "bullets_dropped_share": round(tot["n_dropped"] / tot["n_before"], 4) if tot["n_before"] else 0,
        "bullets_rewritten_share": round(tot["n_rewritten"] / tot["n_before"], 4) if tot["n_before"] else 0,
        "by_country": {k: dict(v) for k, v in sorted(by_country.items())},
    }


def run_gate(provider, model_id: str, selected: list[tuple[Path, dict]], resolver: SourceResolver,
             *, run: str, dry_run: bool, quiet: bool) -> list[dict]:
    rows: list[dict] = []
    for path, d in tqdm(selected, desc="02d-verify", leave=False, disable=quiet):
        country = d.get("country") or "fr"
        sources = resolver.get(country)
        src = sources.get(d["slug"]) if sources else None
        if src is None:
            rows.append({"slug": d["slug"], "country": country, "status": "no_source"})
            continue
        row = gate_record(provider, model_id, path, d, src, run=run, dry_run=dry_run)
        rows.append(row)
        if not quiet and row.get("status") == "ok":
            log(f"{d['slug']:40} {country:2} {row['n_before']:2}→{row['n_after']:2} "
                f"drop={row['n_dropped']} rewrite={row['n_rewritten']} move={row['n_moved']}"
                + (f" rejected={row['n_rejected_rewrites']}" if row['n_rejected_rewrites'] else ""))
        elif not quiet:
            log(f"{d['slug']:40} {country:2} {row.get('status')}: {row.get('error', '')[:120]}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral", "ollama"))
    ap.add_argument("--model", default=None, help="default: providers.STAGE_DEFAULTS['gate']")
    ap.add_argument("--thinking", default=None, choices=("disabled", "adaptive"),
                    help="anthropic thinking mode (default: the stage default, adaptive on Opus 5)")
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--country", action="append", default=None, help="restrict to a country code (repeatable)")
    ap.add_argument("--only", action="append", default=None, help="restrict to these slugs (repeatable)")
    ap.add_argument("--only-file", default=None, help="JSON list (or {\"slugs\": [...]}) of slugs to restrict to")
    ap.add_argument("--sample", type=int, default=0, help="random sample of N records (seed 0)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="re-gate records that already carry a gate block")
    ap.add_argument("--dry-run", action="store_true", help="grade and report only; write no cache")
    ap.add_argument("--batch", action="store_true", help="submit as one provider Batch-API job (resumable)")
    ap.add_argument("--report", default=None, help="report path (default tmp/terroir-facts-review/gate-<run>.json)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.only_file:
        data = json.loads(Path(args.only_file).read_text(encoding="utf-8"))
        args.only = list(args.only or []) + list(data.get("slugs") if isinstance(data, dict) else data)

    run = terroir_backup.run_id()
    selected = select_records(
        countries=set(args.country) if args.country else None,
        only=set(args.only) if args.only else None,
        sample=args.sample, limit=args.limit, refresh=args.refresh,
    )
    if not selected:
        log("nothing to do — every selected record is gated against its current facts.")
        return 0
    resolver = SourceResolver()
    t0 = time.monotonic()
    rows: list[dict] = []

    if args.batch:
        if not batch.supports(args.provider):
            log("--batch requires --provider anthropic|mistral")
            return 1
        model_id = args.model or batch.default_model(args.provider, stage="gate")
        thinking = args.thinking or batch.default_thinking(args.provider, stage="gate")
        log(f"batch: {len(selected)} records (provider={args.provider}, model={model_id}, "
            f"thinking={thinking}, dry_run={args.dry_run}, run={run})")

        def run_loop(prov):
            nonlocal rows
            collecting = getattr(prov, "kind", "") == "collecting"
            rows = run_gate(prov, model_id, selected, resolver, run=run,
                            dry_run=args.dry_run or collecting, quiet=collecting or args.quiet)

        batch.run_two_pass(provider=args.provider, model=model_id, sidecar=BATCH_SIDECAR, run_loop=run_loop,
                           thinking=thinking)
        kind = f"{args.provider}-api"
    else:
        provider, model_id = providers.make_provider(
            args.provider, model=args.model, ollama_url=args.ollama_url, mistral_url=args.mistral_url,
            stage="gate", thinking=args.thinking,
        )
        log(f"{len(selected)} records (provider={args.provider}, model={model_id}, dry_run={args.dry_run}, run={run})")
        rows = run_gate(provider, model_id, selected, resolver, run=run, dry_run=args.dry_run, quiet=args.quiet)
        kind = provider.kind

    summary = _summary(rows)
    summary.update({
        "run": run, "model": model_id, "provider_kind": kind, "dry_run": args.dry_run,
        "gate_version": GATE_VERSION, "elapsed_seconds": round(time.monotonic() - t0, 1),
        "source_unresolved_countries": resolver.failed,
    })
    report = Path(args.report) if args.report else REPORT_DIR / f"gate-{run}{'-dryrun' if args.dry_run else ''}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "records": rows}, ensure_ascii=False, indent=1, default=str) + "\n",
                      encoding="utf-8")
    if not args.dry_run:
        cache.write_json(MANIFEST, {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **summary,
        }, sort_keys=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    log(f"report → {report.relative_to(ROOT) if report.is_relative_to(ROOT) else report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
