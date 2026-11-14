"""French records whose area crosses the border: the checked-in table is
well-formed, every quote is in the record's zone text, every unit is a unit of
the NUTS layers, and stage 02 writes the alias countries on the record."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fr import cross_border  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
LOCALES = {"en", "fr", "es", "nl"}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip()


def test_table_is_well_formed():
    table = cross_border.load()
    assert table
    for slug, entry in table.items():
        assert entry["country_aliases"] and "fr" not in entry["country_aliases"], slug
        assert all(re.fullmatch(r"[a-z]{2}", c) for c in entry["country_aliases"]), slug
        assert entry["quote"].strip() and entry["source"].strip() and entry["verified"], slug
        for unit in entry.get("units", []):
            assert re.fullmatch(r"(?:nuts|country):[A-Za-z0-9]+", unit), (slug, unit)
        if entry.get("disclose"):
            assert set(entry["disclose"]) == LOCALES, slug
        # the units are of the alias countries (Greece is EL, the UK is UK in NUTS)
        for unit in entry.get("units", []):
            kind, _, code = unit.partition(":")
            assert code[:2].lower() in entry["country_aliases"], (slug, unit)


@pytest.mark.skipif(not EXTRACTED.exists(), reason="raw/ not present")
def test_quotes_are_in_the_zone_text_and_the_record_carries_the_aliases():
    for slug, entry in cross_border.load().items():
        rec = json.loads((EXTRACTED / f"{slug}.json").read_text(encoding="utf-8"))
        zone = _flat((rec.get("section_roles") or {}).get("aire") or "")
        assert _flat(entry["quote"]) in zone, slug
        assert rec.get("country_aliases") == entry["country_aliases"], slug


@pytest.mark.skipif(not (ROOT / "raw" / "gr" / "nuts").exists(), reason="raw/ not present")
def test_units_resolve_in_the_nuts_layers():
    from _lib.drinks.geometry import DrinksGeometry

    geometry = DrinksGeometry()
    for slug, entry in cross_border.load().items():
        if not entry.get("units"):
            continue
        res = geometry.resolve_units(entry["units"])
        assert res.geom is not None and not res.unresolved, (slug, res.unresolved)


def test_seam_slivers_are_closed_and_real_holes_kept():
    """The union of IGN communes and NUTS units leaves sliver holes along the
    border; a hole that does not touch the foreign part, or a large one, stays."""
    import importlib

    from shapely.geometry import Polygon, box

    stage04 = importlib.import_module("04_build_maps")
    foreign = box(1.0, 0.0, 2.0, 1.0)
    sliver = [(1.0, 0.40), (0.995, 0.405), (1.0, 0.41), (1.0, 0.40)]          # touches the foreign part
    inland = [(0.30, 0.30), (0.31, 0.30), (0.31, 0.31), (0.30, 0.31), (0.30, 0.30)]  # a commune left out
    enclave = [(1.2, 0.2), (1.6, 0.2), (1.6, 0.6), (1.2, 0.6), (1.2, 0.2)]     # inside the foreign part, large
    geom = Polygon([(0, 0), (2, 0), (2, 1), (0, 1), (0, 0)], [sliver, inland, enclave])
    out = stage04._fill_seam_holes(geom, foreign)
    assert len(out.interiors) == 2
    assert {round(Polygon(r).area, 4) for r in out.interiors} == {0.0001, 0.16}
