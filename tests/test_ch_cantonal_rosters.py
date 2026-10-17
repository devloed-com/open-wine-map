"""Swiss cantonal rosters: BL's Anhang 1 table, the AOCs it governs by
reference (Basel-Stadt, Solothurn), and the lone-capital commune rule."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from _lib.ch.canton import CANTON_CAPITAL, CANTON_CODES
from _lib.ch.reglement import annex_roster_block, table_varieties
from _lib.grape_entity import match_variety

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "raw" / "ch" / "dokumente-extracted"

_spec = importlib.util.spec_from_file_location(
    "ch_02", ROOT / "scripts/ch/02_extract_reglements.py")
ch_02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ch_02)

# SGS 516.31, Anhang 1 (Stand 01.05.2025), as pdftotext -layout prints it.
ANNEX = """
1                                                            516.31 – Anhang 1
                                                              Stand 01.05.2025
Anhang 1 – Zugelassene Rebsorten
Die für die Weinherstellung zugelassenen Rebsorten gemäss § 16 Abs. 1 sind:
Bacchus                                Interspezifische weiss
Blauburgunder / Pinot Noir             Kerner
Cabertin, VB 91-26-17                  Mara (RAC 3022, C41)
CAL 1-14                               Riesling-Silvaner
Diolynoir                              Sauvignac (VB CAL 6-04)
Heida, Savagnin blanc                  Zweigelt
Interspezifische rot
"""


def test_annex_is_read_down_each_column():
    rows = table_varieties(annex_roster_block(ANNEX), match_variety)
    assert [r["slug"] for r in rows] == [
        "bacchus", "pinot-noir", "diolinoir", "savagnin",
        "kerner", "mara", "muller-thurgau", "sauvignac", "zweigelt",
    ]


def test_annex_cells_keep_the_regulator_spelling():
    names = {r["slug"]: r["name"] for r in table_varieties(annex_roster_block(ANNEX), match_variety)}
    assert names["pinot-noir"] == "Blauburgunder"
    assert names["savagnin"] == "Heida"
    assert names["diolinoir"] == "Diolynoir"


def test_breeder_codes_and_placeholders_are_not_varieties():
    slugs = {r["slug"] for r in table_varieties(annex_roster_block(ANNEX), match_variety)}
    # "Cabertin" fuzzy-matches Pinot noir at 88; the floor refuses it.
    assert "sylvaner" not in slugs
    assert len(slugs) == 9


def test_no_annex_without_its_heading():
    assert annex_roster_block("§ 16 Rebsorten\nDie Sorten sind im Anhang aufgelistet.") == ""


def test_heida_and_paien_are_savagnin_blanc():
    # VIVC lists both on Savagnin blanc and Gewürztraminer; the Valais OVV
    # writes "Savagnin blanc (Païen ou Heida)".
    assert match_variety("Heida").slug == "savagnin"
    assert match_variety("Païen").slug == "savagnin"
    assert match_variety("Gewürztraminer").slug == "gewurztraminer"


def test_every_canton_has_a_capital():
    assert set(CANTON_CAPITAL) == set(CANTON_CODES)


def test_roster_references_name_known_cantons():
    for canton, (ref, applied_by) in ch_02.ROSTER_BY_REFERENCE.items():
        assert canton in CANTON_CODES and ref in CANTON_CODES and canton != ref
        assert "§" in applied_by


def _records():
    if not EXTRACTED.exists():
        pytest.skip("CH extracts not built")
    return {p.stem: json.loads(p.read_text()) for p in EXTRACTED.glob("*.json")
            if p.name != "_index.json"}


def test_aocs_governed_by_bl_carry_its_roster():
    recs = _records()
    bl = [d["slug"] for d in recs["basel-landschaft"]["grapes"]["details"]]
    for slug in ("basel-stadt", "solothurn"):
        rec = recs[slug]
        assert [d["slug"] for d in rec["grapes"]["details"]] == bl
        roster = [s for s in rec["sources"] if s["kind"] == "cantonal-reglement-roster"]
        assert roster and "516.31" in roster[0]["url"]


def test_no_cantonal_aoc_is_drawn_as_its_capital_alone():
    for slug, rec in _records().items():
        if rec.get("tier") != "cantonale":
            continue
        names = [c["name"] for c in rec.get("geo_communes") or []]
        assert names != [CANTON_CAPITAL[rec["canton"]]], slug
