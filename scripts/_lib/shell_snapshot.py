"""The stage-04 shell snapshot behind `04_build_maps.py --shell-only`.

A template, JS, CSS or catalog change re-renders every page, but nothing the
page emitter consumes has changed: the emitter reads the two feature lists
(their properties only — the geometry is tiled, never rendered into a page)
and a set of runtime caches the record loop, the augmenters and the geometry
resolution fill in main(). A full build pickles exactly those at the emit
boundary; `--shell-only` restores them in place — the augmenters and the
emitter hold the same dict objects — and calls the emitter, skipping the
minutes of loading, augmenting and resolving that produce identical inputs.

The snapshot is a cache under raw/ (gitignored). It is valid for the shell
files below; `stale_inputs` lists what else changed after it was written, so
a run that would need a full build is warned about, not silently served.
"""

from __future__ import annotations

import datetime as dt
import os
import pickle
from pathlib import Path

SNAPSHOT_VERSION = 1

# Changes to these only move the shell: the snapshot stays valid.
SHELL_PATHS = (
    "scripts/_lib/map_template.py",
    "scripts/_lib/content_block.py",
    "scripts/_lib/assets/",
    "scripts/_lib/vendor/",
    "scripts/_lib/i18n.py",
    "scripts/_lib/gi_terms.py",
    "scripts/_lib/traditional_terms.json",
    "scripts/_lib/appellation_urls.py",
    "scripts/_lib/appellation_urls.json",
    "scripts/_lib/appellation_notes.json",
    "scripts/_lib/cancelled_gis.json",
    "scripts/_lib/promoted_gis.json",
    "scripts/_lib/region_exonyms.json",
    "scripts/_lib/region_search_terms.json",
    "scripts/_lib/region_search_terms.py",
    "scripts/_lib/grape_labels.py",
    "scripts/_lib/romanise.py",
    "scripts/_lib/shell_snapshot.py",
    "scripts/compare_build_output.py",
    "scripts/serve.py",
    "scripts/deploy.py",
    "scripts/deploy.sh",
    "scripts/deploy_mcp.py",
    "scripts/snapshot_deployed.py",
)


def _without_geometry(features: list[dict]) -> list[dict]:
    return [{k: v for k, v in f.items() if k != "geometry"} for f in features]


def write_snapshot(
    path: Path,
    *,
    features: list[dict],
    overview_features: list[dict],
    source_type: str,
    use_translations: bool,
    state: dict[str, dict],
) -> int:
    """Pickle the emitter's inputs; returns the file size in bytes."""
    payload = {
        "version": SNAPSHOT_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_type": source_type,
        "use_translations": use_translations,
        "features": _without_geometry(features),
        "overview_features": _without_geometry(overview_features),
        "state": {name: dict(d) for name, d in state.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return path.stat().st_size


def load_snapshot(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as fh:
        payload = pickle.load(fh)  # noqa: S301 — our own cache under raw/
    if payload.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"snapshot version {payload.get('version')!r} != {SNAPSHOT_VERSION}")
    return payload


def restore_state(saved: dict[str, dict], live: dict[str, dict]) -> list[str]:
    """Refill the live caches in place; returns the names the snapshot lacks."""
    missing = []
    for name, target in live.items():
        if name not in saved:
            missing.append(name)
            continue
        target.clear()
        target.update(saved[name])
    return missing


def _is_shell_path(rel: str) -> bool:
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in SHELL_PATHS)


def stale_inputs(snapshot: Path, root: Path) -> list[str]:
    """Files that may change the emitter's inputs and are newer than the
    snapshot: every file under scripts/ outside the shell set, and the
    extracted-corpus indexes under raw/."""
    since = snapshot.stat().st_mtime
    newer: list[str] = []
    scripts = root / "scripts"
    for p in scripts.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if _is_shell_path(rel):
            continue
        if p.stat().st_mtime > since:
            newer.append(rel)
    for p in (root / "raw").glob("*/*/_index.json"):
        if p.stat().st_mtime > since:
            newer.append(p.relative_to(root).as_posix())
    return sorted(newer)
