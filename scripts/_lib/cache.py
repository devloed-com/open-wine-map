"""Shared JSON cache I/O helpers for stage 02b / 02c / 02d / 02e.

The narrative-layer scripts each maintain a per-AOC (or per-locale per-AOC)
JSON cache. The structure differs per stage but the I/O conventions are
identical: read with try/except returning None on missing or parse error;
write with `ensure_ascii=False`, `indent=2`, trailing newline.
"""

from __future__ import annotations

import json
from pathlib import Path


def read_json_or_none(path: Path) -> dict | None:
    """Load JSON from `path`, or return None if missing or unparseable."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def write_json(path: Path, payload: dict | list, *, sort_keys: bool = False) -> None:
    """Write `payload` to `path` as JSON: indent=2, ensure_ascii=False,
    trailing newline. Creates parent directories as needed.

    Set `sort_keys=True` for manifest files where alphabetical key order is
    more readable than the author-chosen order. Per-record cache files
    keep `sort_keys=False` so curated key order survives round-trips.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )
