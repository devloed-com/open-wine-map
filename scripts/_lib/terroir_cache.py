"""Index-aligned maintenance of the stage-02e translation caches.

`raw/translations/terroir-facts/<lang>/<slug>.json` copies the source
cache's facts by index (`bullet`, `subsection`, `provenance`) and is keyed
on `source_facts_sha` — a hash of the source bullets. Stage 04's overlay
matches translated bullets to source facts by index (checking only the
length), and its sibling filter (commit 24bd059d) is computed on source
indices and applied after the overlay. Any post-pass that drops, reorders
or relabels source facts therefore has to apply the same change to every
aligned translation cache, or a page shows the wrong bullet under the
wrong provenance. These helpers do that; a cache that is already out of
step is left alone and reported so stage 02e re-translates it.
"""

from __future__ import annotations

from pathlib import Path

from _lib import cache
from _lib.terroir_backup import snapshot_slug
from _lib.terroir_dedupe import facts_sha

ROOT = Path(__file__).resolve().parents[2]
TERROIR = ROOT / "raw" / "terroir-facts"
TRANSLATIONS = ROOT / "raw" / "translations" / "terroir-facts"
LANGS = ("en", "fr", "es", "nl")


def write_source_cache(path: Path, payload: dict) -> None:
    """Write a `raw/terroir-facts/<slug>.json` cache, snapshotting the slug's
    current source + translation caches into the run's backup first
    (`terroir_backup`). Every 02d script and post-pass writes through here
    (the wiring lint in tests/test_terroir_backup.py fails otherwise)."""
    snapshot_slug(path.stem)
    cache.write_json(path, payload)


def write_translation_cache(path: Path, payload: dict) -> None:
    """Write a `raw/translations/terroir-facts/<lang>/<slug>.json` cache,
    snapshotting first — the 02e counterpart of `write_source_cache`."""
    snapshot_slug(path.stem)
    cache.write_json(path, payload)


def _aligned(t: dict | None, sha: str, n: int) -> bool:
    return bool(t) and t.get("mode") != "verbatim" and bool(t.get("facts")) \
        and t.get("source_facts_sha") == sha and len(t["facts"]) == n


def prune_translations(
    slug: str, old_sha: str, n_old: int, kept_indices: list[int], new_sha: str, *, dry_run: bool,
) -> tuple[list[str], list[dict]]:
    """Keep only `kept_indices` (in order) in every aligned translation cache
    and re-key it on `new_sha`. Returns (pruned_langs, stale_entries)."""
    pruned: list[str] = []
    stale: list[dict] = []
    for lang in LANGS:
        tp = TRANSLATIONS / lang / f"{slug}.json"
        if not tp.exists():
            continue
        t = cache.read_json_or_none(tp)
        if not t or t.get("mode") == "verbatim":
            continue
        if not _aligned(t, old_sha, n_old):
            stale.append({"slug": slug, "lang": lang, "reason": "already-misaligned"})
            continue
        t["facts"] = [t["facts"][i] for i in kept_indices]
        t["source_facts_sha"] = new_sha
        pruned.append(lang)
        if not dry_run:
            write_translation_cache(tp, t)
    return pruned, stale


def sync_translation_provenance(slug: str, facts: list[dict], *, dry_run: bool) -> tuple[int, list[str]]:
    """Copy each source fact's `provenance` into the aligned translation
    caches. Returns (n_written, misaligned_langs)."""
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
        if not _aligned(t, sha, len(facts)):
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
                write_translation_cache(tp, t)
    return written, misaligned


def sync_translation_meta(slug: str, facts: list[dict], *, dry_run: bool) -> tuple[int, list[str]]:
    """Copy each source fact's `provenance` AND `subsection` into the aligned
    translation caches (the gate moves misfiled facts between sub-sections
    without touching the text). Returns (n_written, misaligned_langs)."""
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
        if not _aligned(t, sha, len(facts)):
            misaligned.append(lang)
            continue
        changed = False
        for tf, sf in zip(t["facts"], facts):
            for key in ("provenance", "subsection"):
                if tf.get(key) != sf.get(key):
                    tf[key] = sf.get(key)
                    changed = True
        if changed:
            written += 1
            if not dry_run:
                write_translation_cache(tp, t)
    return written, misaligned


def rekey_translations(slug: str, old_sha: str, n: int, new_sha: str, *, dry_run: bool) -> tuple[list[str], list[str]]:
    """After an in-place edit of source bullets that keeps count and order
    (the normaliser), move every aligned translation cache to `new_sha`.
    Returns (rekeyed_langs, misaligned_langs)."""
    done: list[str] = []
    misaligned: list[str] = []
    for lang in LANGS:
        tp = TRANSLATIONS / lang / f"{slug}.json"
        if not tp.exists():
            continue
        t = cache.read_json_or_none(tp)
        if not t or t.get("mode") == "verbatim" or not t.get("facts"):
            continue
        if not _aligned(t, old_sha, n):
            misaligned.append(lang)
            continue
        t["source_facts_sha"] = new_sha
        done.append(lang)
        if not dry_run:
            write_translation_cache(tp, t)
    return done, misaligned
