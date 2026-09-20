"""Per-run snapshots of the terroir-fact caches, so any 02d / 02e /
post-pass write can be rolled back.

Every write to `raw/terroir-facts/<slug>.json` or
`raw/translations/terroir-facts/<lang>/<slug>.json` goes through
`terroir_cache.write_source_cache` / `write_translation_cache`, which
call `snapshot_slug(slug)` first. The first time a slug is touched in a
run, its current source cache AND all four translation caches (whatever
exists) are copied to

    raw/terroir-facts-backup/<run>/source/<slug>.json
    raw/terroir-facts-backup/<run>/translations/<lang>/<slug>.json
    raw/terroir-facts-backup/<run>/entries/<slug>.json   (what existed)
    raw/terroir-facts-backup/<run>/run.json              (started_at, argv)

Source and translations are snapshotted together because stage 04
matches them by index and `source_facts_sha`: restoring one without the
other leaves a misaligned pair. The per-slug entry records which files
existed so `scripts/rollback_terroir_facts.py` can also delete files the
run created; one file per slug means several per-country processes can
share a run id without racing on a manifest.

The run id comes from `OWM_TERROIR_RUN` (the orchestrator sets one id
for 02d → gate → 02e so the whole chain is one rollback unit); a script
run on its own gets a timestamp id for its process, printed on stderr.
Never on the map, never in git (raw/ is ignored).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERROIR = ROOT / "raw" / "terroir-facts"
TRANSLATIONS = ROOT / "raw" / "translations" / "terroir-facts"
BACKUP_ROOT = ROOT / "raw" / "terroir-facts-backup"
LANGS = ("en", "fr", "es", "nl")
RUN_ENV = "OWM_TERROIR_RUN"

_lock = threading.Lock()
_run_id: str | None = None
_done: set[str] = set()


def run_id() -> str:
    """The active run id: `OWM_TERROIR_RUN`, else a per-process timestamp."""
    global _run_id
    if _run_id is None:
        _run_id = os.environ.get(RUN_ENV) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    return _run_id


def run_dir(run: str | None = None) -> Path:
    return BACKUP_ROOT / (run or run_id())


def _entries_dir(run: str | None = None) -> Path:
    return run_dir(run) / "entries"


def _run_meta_path(run: str | None = None) -> Path:
    return run_dir(run) / "run.json"


def load_manifest(run: str | None = None) -> dict:
    """{run, started_at, argv, slugs: {slug: entry}} — the per-slug entry
    files aggregated (one file per slug, so concurrent per-country
    processes sharing a run id never race on a single manifest)."""
    run = run or run_id()
    meta: dict = {"run": run, "started_at": None}
    mp = _run_meta_path(run)
    if mp.exists():
        try:
            meta.update(json.loads(mp.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    slugs: dict[str, dict] = {}
    ed = _entries_dir(run)
    if ed.exists():
        for ep in sorted(ed.glob("*.json")):
            try:
                slugs[ep.stem] = json.loads(ep.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    meta["slugs"] = slugs
    return meta


def _write_entry(slug: str, entry: dict, run: str | None = None) -> None:
    ep = _entries_dir(run) / f"{slug}.json"
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_text(json.dumps(entry, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_run_meta(at: str) -> None:
    mp = _run_meta_path()
    if mp.exists():
        return
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({"run": run_id(), "started_at": at, "argv": sys.argv[:6]}, indent=1) + "\n",
                  encoding="utf-8")
    print(f"[terroir-backup] run {run_id()} → {run_dir().relative_to(ROOT)}", file=sys.stderr)


def snapshot_slug(slug: str, *, note: str = "") -> bool:
    """Copy the slug's current source + translation caches into the run dir,
    once per run. Returns True when a snapshot was taken now."""
    with _lock:
        if slug in _done:
            return False
        if (_entries_dir() / f"{slug}.json").exists():
            _done.add(slug)
            return False
        rd = run_dir()
        entry: dict = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": False, "translations": [],
        }
        src = TERROIR / f"{slug}.json"
        if src.exists():
            dst = rd / "source" / f"{slug}.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            entry["source"] = True
        for lang in LANGS:
            tp = TRANSLATIONS / lang / f"{slug}.json"
            if tp.exists():
                dst = rd / "translations" / lang / f"{slug}.json"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tp, dst)
                entry["translations"].append(lang)
        if note:
            entry["note"] = note
        _ensure_run_meta(entry["at"])
        _write_entry(slug, entry)
        _done.add(slug)
        return True


def list_runs() -> list[tuple[str, dict]]:
    """(run id, manifest) for every run dir, newest last."""
    if not BACKUP_ROOT.exists():
        return []
    out = []
    for d in sorted(BACKUP_ROOT.iterdir()):
        if d.is_dir() and (d / "run.json").exists():
            out.append((d.name, load_manifest(d.name)))
    return out


def restore_slug(slug: str, run: str, *, dry_run: bool = False) -> dict:
    """Put the slug's caches back to their state before `run`: restore each
    file the run snapshotted, delete each file the run created. Returns
    {restored: [paths], deleted: [paths], missing: bool}."""
    m = load_manifest(run)
    entry = (m.get("slugs") or {}).get(slug)
    if entry is None:
        return {"restored": [], "deleted": [], "missing": True}
    rd = run_dir(run)
    restored: list[str] = []
    deleted: list[str] = []

    def _apply(existed: bool, backup: Path, live: Path) -> None:
        rel = str(live.relative_to(ROOT))
        if existed:
            if not backup.exists():
                return
            if not dry_run:
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, live)
            restored.append(rel)
        elif live.exists():
            if not dry_run:
                live.unlink()
            deleted.append(rel)

    _apply(bool(entry.get("source")), rd / "source" / f"{slug}.json", TERROIR / f"{slug}.json")
    had = set(entry.get("translations") or [])
    for lang in LANGS:
        _apply(lang in had, rd / "translations" / lang / f"{slug}.json", TRANSLATIONS / lang / f"{slug}.json")
    return {"restored": restored, "deleted": deleted, "missing": False}
