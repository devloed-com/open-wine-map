"""Orchestrate a scoped terroir-facts re-run as ONE rollback unit:

    snapshot + mark stale  →  02d --batch (per country, parallel)
      →  02d_verify --batch  →  02e --batch (per country, parallel)
      →  02e_verify --batch  →  audit_terroir_facts

Every step runs under one `OWM_TERROIR_RUN` id, so every cache the chain
touches is snapshotted into `raw/terroir-facts-backup/<run>/` before its
first write and `scripts/rollback_terroir_facts.py --run <run>` undoes
the whole chain (source caches and translations together).

Scope. The 21 country scripts spell their record filter differently
(`--slug` exact for FR, `--only` substring elsewhere), so the
orchestrator does not pass slugs down. It marks each scoped record's
cache stale instead — `cahier_source_sha` prefixed `stale:` — which every
02d's cache check treats as "re-extract"; the per-country batch then
enumerates exactly those (plus records whose sources changed, which are
due anyway). A stale mark is written through `write_source_cache`, so the
pre-run copy is in the backup before the mark lands.

  --scope FILE        JSON list of slugs (or {"slugs": [...]})
  --slug S            add a slug (repeatable)
  --country CC        restrict the 02d step to these countries (default:
                      the countries of the scoped slugs). The gate, 02e
                      and the back-check always run corpus-wide on
                      whatever is ungated / stale / unchecked.
  --parallel N        per-country batch processes at once (default 6)
  --scoped-02d        pass the scope down to each 02d (--slug / --only) so a
                      country whose sources all changed (IT after the MASAF
                      full-text change) re-extracts only the scope
  --scoped-gate       gate only the scoped slugs (a smoke run right after a
                      GATE_VERSION bump would otherwise re-gate the corpus)
  --scoped-backcheck  back-check only the scoped slugs (same reason, after a
                      BACKCHECK_VERSION bump). A smoke run passes all three
                      --scoped-* flags; a corpus migration passes none.
  --skip-02d / --skip-gate / --skip-02e / --skip-02e-verify / --skip-audit
  --dry-run           print the plan, touch nothing

Logs: /tmp/owm-<run>/<step>-<cc>.log (tee'd, readable while running).

Usage:
  .venv/bin/python scripts/rerun_terroir_facts.py --scope tmp/r1-scope.json
  .venv/bin/python scripts/rerun_terroir_facts.py --slug chablis --slug barolo
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, terroir_backup  # noqa: E402
from _lib.terroir_cache import TERROIR, write_source_cache  # noqa: E402
from _lib.terroir_sources import COUNTRIES  # noqa: E402

PY = ROOT / ".venv" / "bin" / "python"
STALE_PREFIX = "stale:"


def log(msg: str) -> None:
    print(f"[rerun] {datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr)


def stage_script(stage: str, cc: str) -> Path:
    name = {"02d": "02d_extract_terroir_facts.py", "02e": "02e_translate_terroir_facts.py"}[stage]
    return ROOT / "scripts" / name if cc == "fr" else ROOT / "scripts" / cc / name


def load_scope(args) -> list[str]:
    slugs: list[str] = list(args.slug or [])
    if args.scope:
        data = json.loads(Path(args.scope).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("slugs") or data.get("union") or []
        slugs.extend(str(s) for s in data)
    return sorted(set(slugs))


def mark_stale(slugs: list[str], *, dry_run: bool) -> dict[str, list[str]]:
    """Snapshot + mark each scoped cache stale. Returns {country: [slugs]}."""
    by_cc: dict[str, list[str]] = {}
    for slug in slugs:
        p = TERROIR / f"{slug}.json"
        d = cache.read_json_or_none(p)
        if not d:
            log(f"  {slug}: no cache — will be extracted if its country's 02d finds a source")
            continue
        cc = d.get("country") or "fr"
        by_cc.setdefault(cc, []).append(slug)
        sha = d.get("cahier_source_sha") or ""
        if sha.startswith(STALE_PREFIX):
            continue
        if not dry_run:
            d["cahier_source_sha"] = STALE_PREFIX + sha
            write_source_cache(p, d)
    return by_cc


def run_step(cmd: list[str], logfile: Path, env: dict) -> int:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    return proc.returncode


def run_parallel(label: str, jobs: list[tuple[str, list[str]]], logdir: Path, env: dict, parallel: int) -> dict[str, int]:
    rcs: dict[str, int] = {}
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        futs = {ex.submit(run_step, cmd, logdir / f"{label}-{cc}.log", env): cc for cc, cmd in jobs}
        for fut in as_completed(futs):
            cc = futs[fut]
            rcs[cc] = fut.result()
            log(f"  {label} {cc}: exit {rcs[cc]} ({(time.monotonic() - t0) / 60:.1f} min) — {logdir / f'{label}-{cc}.log'}")
    return rcs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scope", default=None)
    ap.add_argument("--slug", action="append", default=[])
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--run", default=None, help="run id (default: timestamp)")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral"))
    ap.add_argument("--model", default=None, help="02d extractor model override (default: STAGE_DEFAULTS['02d']); "
                    "the gate, 02e and the back-check keep their own stage defaults")
    for step in ("02d", "gate", "02e", "02e-verify", "audit"):
        ap.add_argument(f"--skip-{step}", action="store_true")
    ap.add_argument("--scoped-02d", action="store_true",
                    help="pass the scoped slugs down to each 02d (--slug for FR, --only elsewhere) so a "
                         "country whose sources all changed re-extracts only the scope")
    ap.add_argument("--scoped-gate", action="store_true",
                    help="gate only the scoped slugs (default: corpus-wide on whatever is ungated — "
                         "after a GATE_VERSION bump that is the whole corpus)")
    ap.add_argument("--scoped-backcheck", action="store_true",
                    help="back-check only the scoped slugs (default: corpus-wide on whatever is unchecked — "
                         "after a BACKCHECK_VERSION bump that is the whole corpus)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run = args.run or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    os.environ[terroir_backup.RUN_ENV] = run
    env = {**os.environ, terroir_backup.RUN_ENV: run}
    logdir = Path("/tmp") / f"owm-{run}"
    slugs = load_scope(args)
    log(f"run {run}: {len(slugs)} scoped slugs; logs → {logdir}")

    by_cc = mark_stale(slugs, dry_run=args.dry_run)
    countries = sorted(set(args.country) if args.country else set(by_cc))
    unknown = [c for c in countries if c not in COUNTRIES]
    if unknown:
        log(f"unknown countries {unknown}")
        return 1
    for cc in countries:
        log(f"  {cc}: {len(by_cc.get(cc, []))} scoped records")
    if args.dry_run:
        log("dry run — nothing marked, nothing launched.")
        return 0

    model = ["--model", args.model] if args.model else []
    if not args.skip_02d and countries:
        log(f"02d --batch for {len(countries)} countries (parallel {args.parallel}) …")
        jobs = []
        for cc in countries:
            scoped: list[str] = []
            if args.scoped_02d:
                flag = "--slug" if cc == "fr" else "--only"
                scoped = [x for slug in by_cc.get(cc, []) for x in (flag, slug)]
            jobs.append((cc, [str(PY), str(stage_script("02d", cc)), "--batch", "--provider", args.provider,
                              *model, *scoped]))
        rcs = run_parallel("02d", jobs, logdir, env, args.parallel)
        if any(rcs.values()):
            log(f"02d failed for {[c for c, rc in rcs.items() if rc]} — re-run the same command to resume; stopping.")
            return 1

    if not args.skip_gate:
        gate_scope: list[str] = []
        if args.scoped_gate:
            scope_file = logdir / "gate-scope.json"
            scope_file.write_text(json.dumps({"slugs": slugs}), encoding="utf-8")
            gate_scope = ["--only-file", str(scope_file)]
        log(f"02d_verify --batch ({'scoped' if gate_scope else 'corpus-wide, ungated records'}) …")
        rc = run_step([str(PY), str(ROOT / "scripts" / "02d_verify_terroir_facts.py"), "--batch",
                       "--provider", args.provider, "--quiet", *gate_scope], logdir / "gate.log", env)
        log(f"  gate: exit {rc} — {logdir / 'gate.log'}")
        if rc:
            return 1

    if not args.skip_02e:
        # Every country: the gate may have rewritten records outside the scope.
        cc_02e = sorted(COUNTRIES)
        log(f"02e --batch for {len(cc_02e)} countries …")
        jobs = [(cc, [str(PY), str(stage_script("02e", cc)), "--batch", "--provider", args.provider])
                for cc in cc_02e]
        rcs = run_parallel("02e", jobs, logdir, env, args.parallel)
        if any(rcs.values()):
            log(f"02e failed for {[c for c, rc in rcs.items() if rc]} — re-run to resume; continuing to the checks.")

    if not args.skip_02e_verify:
        check_scope: list[str] = []
        if args.scoped_backcheck:
            scope_file = logdir / "backcheck-scope.json"
            scope_file.write_text(json.dumps({"slugs": slugs}), encoding="utf-8")
            check_scope = ["--only-file", str(scope_file)]
        log(f"02e_verify --batch ({'scoped' if check_scope else 'corpus-wide, unchecked translations'}) …")
        rc = run_step([str(PY), str(ROOT / "scripts" / "02e_verify_terroir_facts.py"), "--batch",
                       "--provider", args.provider, "--quiet", *check_scope], logdir / "02e-verify.log", env)
        log(f"  02e-verify: exit {rc} — {logdir / '02e-verify.log'}")

    if not args.skip_audit:
        report = ROOT / "tmp" / "terroir-facts-review" / f"audit-{run}.json"
        rc = run_step([str(PY), str(ROOT / "scripts" / "audit_terroir_facts.py"), "--quiet", "--report", str(report)],
                      logdir / "audit.log", env)
        log(f"  audit: exit {rc} — {report.relative_to(ROOT)}; strict summary in {logdir / 'audit.log'}")

    log(cost_report(run))
    log(f"done. Rollback with: scripts/rollback_terroir_facts.py --run {run}")
    return 0


_STAGE_LABEL = {"02d-verify": "gate", "02e-verify": "backcheck", "llm-audit": "audit"}


def cost_report(run: str) -> str:
    """The run's spend per stage from the batch ledger (`raw/.batch/costs.jsonl`)."""
    if not batch.COSTS_LEDGER.exists():
        return "cost: no batch ledger"
    per_stage: dict[str, float] = {}
    unpriced = 0
    for line in batch.COSTS_LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("run") != run:
            continue
        stage = _STAGE_LABEL.get(row.get("stage") or "", (row.get("stage") or "?").split("-")[0])
        cost = row.get("cost_usd")
        if cost is None:
            unpriced += 1
            continue
        per_stage[stage] = per_stage.get(stage, 0.0) + cost
    if not per_stage and not unpriced:
        return "cost: no batches recorded for this run"
    parts = [f"{k} ${v:,.2f}" for k, v in sorted(per_stage.items())]
    total = sum(per_stage.values())
    return (f"cost (Batch API): {' · '.join(parts)} — total ${total:,.2f}"
            + (f" (+{unpriced} unpriced batches)" if unpriced else ""))


if __name__ == "__main__":
    sys.exit(main())
