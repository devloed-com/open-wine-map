"""Shared --emit-todo / --import argparse plumbing for 02c / 02d / 02e.

Each script's actual emit/import body is per-script (the JSON shapes
differ enough that a single abstraction would cost more than it saves).
This module just normalises the CLI surface and the dispatch validation
so all three stages expose the same flags with the same semantics.
"""

from __future__ import annotations

import argparse
import sys


def add_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the round-trip flags: --emit-todo, --all, --import (dest=import_path),
    --translator-id, --translator-kind."""
    ap.add_argument(
        "--emit-todo", metavar="PATH", default=None,
        help="write a TODO JSON of untreated work and exit (no model calls)",
    )
    ap.add_argument(
        "--all", action="store_true",
        help="with --emit-todo: include AOCs already cached (default: only stale/missing)",
    )
    ap.add_argument(
        "--import", dest="import_path", metavar="PATH", default=None,
        help="read a filled-in TODO JSON and write per-AOC cache files (no model calls)",
    )
    ap.add_argument(
        "--translator-id", default=None,
        help="recorded as `translator` when --import (e.g. 'claude.ai 2026-05-03')",
    )
    ap.add_argument(
        "--translator-kind", default="manual",
        help="recorded as `translator_kind` when --import (default: manual)",
    )


def validate_emit_import(args: argparse.Namespace) -> int | None:
    """Check --emit-todo / --import mutex and the --translator-id requirement.
    Returns an exit code if invalid, else None."""
    if args.emit_todo and args.import_path:
        print("error: --emit-todo and --import are mutually exclusive.", file=sys.stderr)
        return 1
    if args.import_path and not args.translator_id:
        print(
            "error: --import requires --translator-id "
            "(e.g. --translator-id 'claude.ai 2026-05-03').",
            file=sys.stderr,
        )
        return 1
    return None
