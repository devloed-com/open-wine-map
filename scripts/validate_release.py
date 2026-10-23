#!/usr/bin/env python3
"""Pre-deploy umbrella — runs every deterministic gate the repo has and
prints one table (docs/plan-validators.md § 4, `/validate-release`).

The checks are a registry (`CHECKS`): the `--strict` audits, the data-
quality detectors, the test suite, the About-page date and the stage-04
shell-snapshot staleness. Each runs as a subprocess with a timeout; the
report records the exit code, the duration and the last lines of output.
`--quick` leaves out the geometry audits (minutes each); `--only` / `--skip`
pick by name; `--list` prints the registry. A failed check is a failed
release: exit 1. Nothing is written but the report.

    .venv/bin/python scripts/validate_release.py --quick
    .venv/bin/python scripts/validate_release.py --only empty-grapes --only gi-terms
    .venv/bin/python scripts/validate_release.py --list
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
REPORT_DIR = ROOT / "tmp" / "validation"

# name, command, group (quick | full), timeout seconds, what it gates
CHECKS: list[dict] = [
    {"name": "empty-grapes", "cmd": [PY, "scripts/audit_empty_grapes.py", "--strict"], "group": "quick", "timeout": 300,
     "gate": "no wine card renders without grapes (FLAGGED / INHERIT empty)"},
    {"name": "gi-terms", "cmd": [PY, "scripts/audit_gi_terms.py", "--strict"], "group": "quick", "timeout": 300,
     "gate": "every child's classification equals its parent's; no empty class_label"},
    {"name": "styles", "cmd": [PY, "scripts/audit_styles.py", "--strict"], "group": "quick", "timeout": 300,
     "gate": "style floor and taxonomy consistency"},
    {"name": "vivc-pins", "cmd": [PY, "scripts/audit_vivc_coverage.py", "--strict"], "group": "quick", "timeout": 600,
     "gate": "every VIVC pin matches its passport"},
    {"name": "grape-surfaces", "cmd": [PY, "scripts/audit_grape_surfaces.py", "--strict"], "group": "quick", "timeout": 600,
     "gate": "no banned / colour-word grape surface binds a variety"},
    {"name": "ambiguous-synonyms", "cmd": [PY, "scripts/audit_ambiguous_synonyms.py", "--strict"], "group": "quick", "timeout": 600,
     "gate": "no unpinned ambiguous grape synonym"},
    {"name": "grape-brackets", "cmd": [PY, "scripts/audit_grape_identity.py", "--strict"], "group": "quick", "timeout": 600,
     "gate": "the card's umlaut fold suppresses a bracket only on an umlaut pair (no `review` pair)"},
    {"name": "dup-keys", "cmd": [PY, "scripts/audit_dup_keys.py"], "group": "quick", "timeout": 120,
     "gate": "no silently overriding dict key under scripts/"},
    {"name": "terroir-facts", "cmd": [PY, "scripts/audit_terroir_facts.py", "--strict"], "group": "quick", "timeout": 1200,
     "gate": "no eroded grounding, no feedback recurrence, no gate pending"},
    {"name": "untranslated", "cmd": [PY, "scripts/detect_untranslated_terroir_facts.py", "--strict"], "group": "quick", "timeout": 600,
     "gate": "no non-Latin script, leaked common noun or missing exonym in a translated bullet"},
    {"name": "betard-delta", "cmd": [PY, "scripts/audit_betard_delta.py", "--strict"], "group": "quick", "timeout": 300,
     "gate": "no unreviewed post-snapshot GI drawn from Bétard"},
    {"name": "parcellaire-gaps", "cmd": [PY, "scripts/audit_parcellaire_gaps.py", "--strict"], "group": "quick", "timeout": 900,
     "gate": "no STALE gap-fill pin or carry-forward entry"},
    {"name": "geometry-outliers", "cmd": [PY, "scripts/audit_geometry_outliers.py", "--strict"], "group": "full", "timeout": 3600,
     "gate": "no unreviewed detached part; no STALE clip"},
    {"name": "geometry-overlaps", "cmd": [PY, "scripts/audit_geometry_overlaps.py", "--strict"], "group": "full", "timeout": 3600,
     "gate": "no unreviewed SUSPICIOUS sliver"},
    {"name": "geometry-vs-text", "cmd": [PY, "scripts/audit_geometry_vs_text.py", "--strict"], "group": "full", "timeout": 3600,
     "gate": "the polygon covers the units the text names and no others (unreviewed SUSPECT)"},
    {"name": "vineyard-envelopes", "cmd": [PY, "scripts/audit_vineyard_envelopes.py", "--strict"], "group": "full", "timeout": 3600,
     "gate": "footprint parity, containment, bridging"},
    {"name": "it-regions", "cmd": [PY, "scripts/audit_it_regions.py", "--strict"], "group": "full", "timeout": 1800,
     "gate": "every IT regione label sits on its polygon"},
    {"name": "pytest", "cmd": [PY, "-m", "pytest", "-q", "-x", "--no-header"], "group": "quick", "timeout": 1800,
     "gate": "the test suite"},
]


def about_date_check() -> dict:
    """The homepage's 'Data updated on' date must be today's build (memory:
    rebuild on deploy day)."""
    p = ROOT / "wiki" / "index.html"
    if not p.exists():
        return {"name": "about-date", "status": "fail", "detail": "wiki/index.html missing — build first"}
    html = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Data updated on\s*<[^>]*>?\s*([^<]{4,40})<", html) or re.search(r"Data updated on\s*([^<]{4,40})<", html)
    if not m:
        return {"name": "about-date", "status": "warn", "detail": "no 'Data updated on' line found on the EN homepage"}
    txt = m.group(1).strip()
    today = date.today()
    ok = str(today.year) in txt and (today.strftime("%B") in txt or today.strftime("%-d") in txt)
    return {"name": "about-date", "status": "pass" if ok else "warn",
            "detail": f"homepage says «{txt}»; today is {today.isoformat()} — rebuild on deploy day if stale"}


def snapshot_check() -> dict:
    snap = ROOT / "raw" / "cache" / "stage04-shell-snapshot.pkl"
    if not snap.exists():
        return {"name": "shell-snapshot", "status": "warn", "detail": "no stage-04 shell snapshot (a full build writes it)"}
    # only scripts the build runs or imports count: the audits, the validators,
    # the review tooling and their libraries never change a page
    skip = re.compile(r"^scripts/(audit_|validate_|diff_records|feedback_report|rollback_|rerun_|build_terroir_feedback|"
                      r"detect_|extract_register_fiches|_lib/(freshness/|card_packet|terroir_gate|terroir_backcheck))")
    newer = [str(p.relative_to(ROOT)) for p in (ROOT / "scripts").rglob("*.py")
             if p.stat().st_mtime > snap.stat().st_mtime and not skip.match(str(p.relative_to(ROOT)))]
    return {"name": "shell-snapshot", "status": "pass" if not newer else "warn",
            "detail": "snapshot newer than every script" if not newer else f"{len(newer)} script(s) changed since the last full build: {', '.join(newer[:6])}{' …' if len(newer) > 6 else ''} — a record / geometry change needs a full build"}


def run_check(c: dict) -> dict:
    t0 = time.monotonic()
    try:
        r = subprocess.run(c["cmd"], cwd=ROOT, capture_output=True, text=True, timeout=c["timeout"])
        code, out = r.returncode, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired:
        code, out = 124, f"timeout after {c['timeout']} s"
    except FileNotFoundError as e:
        code, out = 127, str(e)
    tail = "\n".join(line for line in out.strip().splitlines()[-8:])
    return {"name": c["name"], "gate": c["gate"], "status": "pass" if code == 0 else "fail", "exit": code,
            "seconds": round(time.monotonic() - t0, 1), "tail": tail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="skip the geometry audits")
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--skip", action="append", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    if args.list:
        for c in CHECKS:
            print(f"{c['name']:20} [{c['group']}] {c['gate']}")
        return 0
    checks = [c for c in CHECKS if (not args.only or c["name"] in set(args.only)) and c["name"] not in set(args.skip or [])
              and (not args.quick or c["group"] == "quick")]
    results = []
    for c in checks:
        print(f"[release] {c['name']} …", file=sys.stderr, flush=True)
        results.append(run_check(c))
        print(f"[release] {c['name']}: {results[-1]['status']} ({results[-1]['seconds']} s)", file=sys.stderr, flush=True)
    extras = [about_date_check(), snapshot_check()]
    failed = [r for r in results if r["status"] == "fail"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    lines = [f"# validate-release — {stamp}", "", f"{len(results) - len(failed)} / {len(results)} checks pass"
             + ("" if not failed else f"; FAILED: {', '.join(r['name'] for r in failed)}"), "",
             "| check | status | s | gate |", "|---|---|---:|---|"]
    lines += [f"| {r['name']} | {'✅' if r['status'] == 'pass' else '❌'} {r['status']} | {r['seconds']} | {r['gate']} |" for r in results]
    lines += [f"| {e['name']} | {'✅' if e['status'] == 'pass' else '⚠️'} {e['status']} | | {e['detail']} |" for e in extras]
    for r in failed:
        lines += ["", f"## {r['name']} (exit {r['exit']})", "", "```", r["tail"], "```"]
    md = "\n".join(lines) + "\n"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = Path(args.report) if args.report else REPORT_DIR / f"release-{stamp}.md"
    report.write_text(md, encoding="utf-8")
    (report.with_suffix(".json")).write_text(json.dumps({"results": results, "extras": extras}, indent=1) + "\n", encoding="utf-8")
    print(md)
    print(f"[release] report → {report}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
