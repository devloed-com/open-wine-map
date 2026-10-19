"""`04_build_maps.py --shell-only` re-emits the pages from the last full build's
snapshot of the emitter's inputs (scripts/_lib/shell_snapshot.py): the two
feature lists without their geometry and the runtime caches main() fills.
These pin the round trip, the in-place restore and the staleness check, and
that stage 04 is wired to the helper."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.shell_snapshot import (  # noqa: E402
    SHELL_PATHS,
    load_snapshot,
    restore_state,
    stale_inputs,
    write_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
STAGE04 = (ROOT / "scripts" / "04_build_maps.py").read_text(encoding="utf-8")


def test_round_trip_drops_geometry_and_keeps_properties(tmp_path: Path) -> None:
    snap = tmp_path / "raw" / "cache" / "snap.pkl"
    feats = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
              "properties": {"slug": "pauillac", "bbox": "0,0,1,1"}}]
    size = write_snapshot(snap, features=feats, overview_features=feats, source_type="pmtiles",
                          use_translations=True, state={"_X_BY_SLUG": {"pauillac": [1, 2]}})
    assert size > 0 and snap.exists() and not snap.with_suffix(".pkl.tmp").exists()
    back = load_snapshot(snap)
    assert back["source_type"] == "pmtiles" and back["use_translations"] is True
    assert back["features"] == [{"type": "Feature", "properties": {"slug": "pauillac", "bbox": "0,0,1,1"}}]
    assert back["state"] == {"_X_BY_SLUG": {"pauillac": [1, 2]}}
    assert back["created_at"].endswith("+00:00")


def test_restore_refills_the_live_dicts_in_place() -> None:
    live_a: dict = {"old": 1}
    live_b: dict = {}
    live = {"A": live_a, "B": live_b}
    missing = restore_state({"A": {"new": 2}}, live)
    assert live["A"] is live_a and live_a == {"new": 2}
    assert missing == ["B"] and live_b == {}


def test_stale_inputs_skips_the_shell_files(tmp_path: Path) -> None:
    (tmp_path / "scripts" / "_lib" / "assets").mkdir(parents=True)
    (tmp_path / "raw" / "es" / "pliegos-extracted").mkdir(parents=True)
    snap = tmp_path / "raw" / "snap.pkl"
    snap.write_bytes(b"x")
    then = time.time() - 100
    os.utime(snap, (then, then))
    older = tmp_path / "scripts" / "_lib" / "aires.py"
    older.write_text("x")
    os.utime(older, (then - 10, then - 10))
    for rel in ("scripts/_lib/map_template.py", "scripts/_lib/assets/app.js", "scripts/_lib/geom_chain.py",
                "raw/es/pliegos-extracted/_index.json"):
        (tmp_path / rel).write_text("y")  # now → newer than the snapshot
    assert stale_inputs(snap, tmp_path) == ["raw/es/pliegos-extracted/_index.json", "scripts/_lib/geom_chain.py"]
    assert "scripts/_lib/map_template.py" in SHELL_PATHS and "scripts/_lib/assets/" in SHELL_PATHS


def test_stage04_is_wired_to_the_snapshot() -> None:
    assert '"--shell-only"' in STAGE04
    assert "return _shell_only(args)" in STAGE04
    # Every emission goes through _emit (which writes the snapshot first);
    # emit_html itself is called once, from _emit.
    assert STAGE04.count('_emit(features, overview_features, source_type="') == 4
    assert STAGE04.count("    emit_html(\n") == 1
    assert "def _shell_state() -> dict[str, dict]:" in STAGE04
    # The shared augmenter caches the emitter reads are all in the state map.
    for name in ("_ES_NATIONAL_PLIEGO_BY_SLUG", "_GEOM_UNITS_DISCLOSURE_BY_SLUG", "_LOD_RADIUS_BY_SLUG",
                 "_PARCEL_FILL_BY_SLUG", "_PT_AREA_ACT_BY_SLUG", "_IT_MASAF_BY_SLUG", "_GRAPE_DETAILS_BY_SLUG",
                 "_IT_MENZIONI_BY_SLUG", "_FR_COMITE_BY_SLUG", "_ES_PARROQUIAS_BY_SLUG", "_ES_SIGPAC_BY_SLUG"):
        assert f'"{name}": {name},' in STAGE04, name
