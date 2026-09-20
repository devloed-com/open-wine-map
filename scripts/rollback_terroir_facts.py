"""Roll a terroir-facts run back from its backup.

Every write to `raw/terroir-facts/` and `raw/translations/terroir-facts/`
(stage 02d, the claim-support gate, stage 02e, the post-passes) first
snapshots the slug's source + translation caches into
`raw/terroir-facts-backup/<run>/` (`_lib/terroir_backup.py`). This script
puts a run's slugs back to their pre-run state: files the run overwrote
are restored, files it created are deleted, so the source cache and its
four index-aligned translation caches stay in step.

  --list                 every run with its slug count and start time
  --run ID               the run to roll back (required unless --list)
  --only SLUG            restrict to these slugs (repeatable)
  --dry-run              print what would change, write nothing

A rollback is itself a write and is snapshotted under a new run id
(`rollback-of-<ID>-<ts>`), so a rollback can be rolled back. After a
rollback, re-run stage 04 to rebuild the map from the restored caches.

Usage:
  .venv/bin/python scripts/rollback_terroir_facts.py --list
  .venv/bin/python scripts/rollback_terroir_facts.py --run 2026-09-13T1200 --dry-run
  .venv/bin/python scripts/rollback_terroir_facts.py --run 2026-09-13T1200 --only chablis
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import terroir_backup as tb  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list the runs that can be rolled back")
    ap.add_argument("--run", default=None, help="run id (a directory under raw/terroir-facts-backup/)")
    ap.add_argument("--only", action="append", default=[], help="restrict to these slugs (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list:
        runs = tb.list_runs()
        if not runs:
            print("[rollback] no backup runs under raw/terroir-facts-backup/", file=sys.stderr)
            return 0
        for run, m in runs:
            slugs = m.get("slugs") or {}
            argv = " ".join(m.get("argv") or [])
            print(f"  {run:32} {len(slugs):5} slugs  started {m.get('started_at') or '?'}  {argv[:70]}")
        return 0

    if not args.run:
        ap.error("--run ID is required (see --list)")
    m = tb.load_manifest(args.run)
    slugs = m.get("slugs") or {}
    if not slugs:
        print(f"error: run {args.run!r} has no manifest under {tb.BACKUP_ROOT}", file=sys.stderr)
        return 1
    wanted = [s for s in sorted(slugs) if not args.only or s in set(args.only)]
    unknown = sorted(set(args.only) - set(slugs))
    for s in unknown:
        print(f"  skip {s}: not in run {args.run}", file=sys.stderr)
    if not wanted:
        print("[rollback] nothing to do.", file=sys.stderr)
        return 0

    # The rollback's own snapshot goes under a fresh run id so it is undoable.
    if not args.dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        os.environ[tb.RUN_ENV] = f"rollback-of-{args.run}-{stamp}"
        tb._run_id = None  # noqa: SLF001 — re-read the env for this process
    n_restored = n_deleted = 0
    for slug in wanted:
        if not args.dry_run:
            tb.snapshot_slug(slug, note=f"before rollback of {args.run}")
        r = tb.restore_slug(slug, args.run, dry_run=args.dry_run)
        n_restored += len(r["restored"])
        n_deleted += len(r["deleted"])
        what = ", ".join([f"restore {p}" for p in r["restored"]] + [f"delete {p}" for p in r["deleted"]])
        print(f"  {slug}: {what or 'no change'}", file=sys.stderr)
    verb = "would restore" if args.dry_run else "restored"
    print(f"[rollback] run {args.run}: {len(wanted)} slugs — {verb} {n_restored} files, "
          f"{'would delete' if args.dry_run else 'deleted'} {n_deleted} files created by the run."
          f"{'' if args.dry_run else ' Re-run scripts/04_build_maps.py to rebuild the map.'}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
