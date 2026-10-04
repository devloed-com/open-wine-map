"""INAO parcellaire rows carried forward from an earlier release
(scripts/_lib/parcellaire_carry_forward.json): the table is well-formed, each
extract is exactly the rows its entry names, the helper appends them only
when the current release lacks them and reports STALE otherwise, and — with
the releases on disk — the extract is a faithful copy of the earlier release
and the current release still lacks the rows."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.parcellaire import (  # noqa: E402
    SHAPEFILE_DIR,
    carry_forward_frames,
    carry_matches,
    load_carry_forward,
    read_carry_extract,
    resolve_shapefile,
)

COLS = ["app", "id_denom", "insee", "insee2011", "nomcom"]


def test_table_is_well_formed():
    specs = load_carry_forward()
    assert {s.label for s in specs} >= {"Saint-Sardos", "Languedoc Montpeyroux"}
    for s in specs:
        date.fromisoformat(s.release)
        date.fromisoformat(s.verified)
        assert s.rows > 0 and s.reason.strip() and s.source.strip(), s.label
        assert s.file.exists() and s.file.name.endswith(".geojson.gz"), s.label
        assert s.release in s.file.name, s.label


def test_each_extract_is_exactly_the_rows_its_entry_names():
    for s in load_carry_forward():
        df = read_carry_extract(s, geometry=False)
        assert len(df) == s.rows, s.label
        assert carry_matches(df, s.match).all(), s.label
        if s.id_app is not None:
            assert set(df["id_app"].astype(int)) == {s.id_app}, s.label
        if s.id_denom:
            assert set(df["id_denom"].astype(int)) == set(s.id_denom), s.label
        assert df["insee"].notna().all() and (df["insee"].str.len() == 5).all(), s.label
        gdf = read_carry_extract(s, geometry=True)
        assert gdf.crs.to_epsg() == 2154 and gdf.geometry.is_valid.all(), s.label


def test_frames_are_appended_only_when_the_release_lacks_the_rows():
    specs = [s for s in load_carry_forward() if s.label == "Saint-Sardos"]
    assert specs
    empty = pd.DataFrame(columns=COLS)
    frames, states = carry_forward_frames(empty, geometry=False, specs=specs)
    assert [(st, n) for _, st, n in states] == [("APPLIED", 23)]
    assert list(frames[0].columns) == COLS and len(frames[0]) == 23

    present = pd.DataFrame([["Saint-Sardos", 1850, "31062", "31062", "BELLESSERRE"]], columns=COLS)
    frames, states = carry_forward_frames(present, geometry=False, specs=specs)
    assert frames == [] and [(st, n) for _, st, n in states] == [("STALE", 1)]


def _release_shp(release: str) -> Path | None:
    p = SHAPEFILE_DIR / f"{release}_delim-parcellaire-aoc-shp.shp"
    return p if p.exists() else None


@pytest.mark.parametrize("spec", load_carry_forward(), ids=lambda s: s.label)
def test_extract_is_a_faithful_copy_of_the_earlier_release(spec):
    shp = _release_shp(spec.release)
    if shp is None:
        pytest.skip(f"release {spec.release} not on disk")
    import pyogrio

    src = pyogrio.read_dataframe(shp, read_geometry=False)
    src = src[carry_matches(src, spec.match)].sort_values(["id_denom", "insee"]).reset_index(drop=True)
    ext = read_carry_extract(spec, geometry=False).sort_values(["id_denom", "insee"]).reset_index(drop=True)
    assert len(src) == len(ext) == spec.rows
    pd.testing.assert_frame_equal(src[ext.columns].astype(str), ext.astype(str))


def test_current_release_still_lacks_every_carried_row():
    shp = resolve_shapefile()
    if shp is None:
        pytest.skip("no parcellaire release on disk")
    import pyogrio

    cur = pyogrio.read_dataframe(shp, read_geometry=False, columns=["app", "id_denom"])
    _frames, states = carry_forward_frames(cur, geometry=False)
    stale = [s.label for s, st, _ in states if st == "STALE"]
    assert not stale, f"rows are back in {shp.name}; drop the entries: {stale}"


def test_card_line_names_both_releases():
    from _lib.content_block import _parcel_fill_line

    lab = {
        "geom_parcel_fill_commune": "whole: {names}", "geom_parcel_fill_donor": "{donor}: {names}",
        "geom_parcel_gaps": "gaps: {names}",
        "geom_parcel_carry": "Parcels of the {release} release; {current} has none.",
    }
    html = _parcel_fill_line({"geom_parcel_carry": {"release": "2026-05-11", "current": "2026-09-28"}}, lab)
    assert "Parcels of the 2026-05-11 release; 2026-09-28 has none." in html
    assert _parcel_fill_line({}, lab) == ""
