"""The stage-02 `_index.json` write, shared by every country's extractor.

A partial run (`--only` / `--limit`) merges its entries into the index on
disk instead of replacing it. Before 2026-10-22 `it/02 --only piemonte`
left a 7-record index for a 524-record corpus — the French stage's own
footgun of 2026-09-11, present in every sibling. Stage 04 reads the
per-record files and did not notice; stage 03 and the coverage audits read
the index.
"""

from __future__ import annotations

import json
from pathlib import Path


def is_partial(args) -> bool:
    """True when the run selected records (`--only` / `--limit`)."""
    return bool(getattr(args, "only", None) or getattr(args, "limit", 0))


def write_index(path: Path, entries: dict, *, partial: bool) -> dict:
    """Write `entries` as the index — merged over the index on disk when the
    run was partial. Returns what was written."""
    merged: dict = {}
    if partial and path.exists():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            prior = {}
        if isinstance(prior, dict):
            merged = prior
    merged.update(entries)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return merged
