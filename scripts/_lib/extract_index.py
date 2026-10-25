"""The stage-02 `_index.json` write, shared by every country's extractor.

A partial run (`--only` / `--limit`) merges its entries into the index on
disk instead of replacing it. Before 2026-10-22 `it/02 --only piemonte`
left a 7-record index for a 524-record corpus — the French stage's own
footgun of 2026-09-11, present in every sibling. Stage 04 reads the
per-record files and did not notice; stage 03 and the coverage audits read
the index.

Stage 03 has the same shape one level up: every country's generator merges
its entries into the shared `wiki/_index.json`, and until 2026-10-24 it
dropped all of its country's entries before the merge, so `03_generate_wiki.py
--only collioure` left one French entry of ~1,500. Stage 04 does not read that
index; the untranslated detector (its appellation-name exemption) and
`terroir_roster` (the sub-denomination roster of the dedupe pass and the
02d / 02e prompts) do.
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


def wiki_index_kept(existing: dict, country: str, *, partial: bool) -> dict:
    """The entries of `wiki/_index.json` a stage-03 run keeps before laying
    its own over them: the other countries' — and, on a partial run, its own
    country's too, so only the selected records are replaced."""
    if partial:
        return dict(existing)
    return {k: v for k, v in existing.items() if v.get("country") != country}
