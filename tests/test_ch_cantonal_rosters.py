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
        "bacchus", "pinot-noir", "cabertin", "diolinoir", "savagnin",
        "kerner", "mara", "muller-thurgau", "sauvignac", "zweigelt",
    ]


def test_annex_cells_keep_the_regulator_spelling():
    names = {r["slug"]: r["name"] for r in table_varieties(annex_roster_block(ANNEX), match_variety)}
    assert names["pinot-noir"] == "Blauburgunder"
    assert names["savagnin"] == "Heida"
    assert names["diolinoir"] == "Diolynoir"


def test_breeder_codes_and_placeholders_are_not_varieties():
    slugs = {r["slug"] for r in table_varieties(annex_roster_block(ANNEX), match_variety)}
    # Cabertin has its own entry (VIVC #22329, 2026-10-22); before, it
    # fuzzy-matched Pinot noir at 88 and the floor refused it.
    assert "sylvaner" not in slugs
    assert len(slugs) == 10


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


def test_an_intercantonal_aoc_belongs_to_every_canton_it_spans():
    """Vully (FR / VD) and Zürichsee (SZ / ZH): no sub-denomination of the
    primary canton, a co-parent per canton that has a cantonal AOC."""
    OfagEntry = ch_02.OfagEntry if hasattr(ch_02, "OfagEntry") else __import__(
        "_lib.ch.ofag_register", fromlist=["OfagEntry"]).OfagEntry
    parents = {c: OfagEntry(name=n, canton=c, cantons=[c], tier="cantonale")
               for c, n in (("vd", "Vaud"), ("sz", "Schwyz"), ("zh", "Zürich"))}
    vully = OfagEntry(name="Vully", canton="fr", cantons=["fr", "vd"], tier="régionale")
    zsee = OfagEntry(name="Zürichsee", canton="sz", cantons=["sz", "zh"], tier="régionale")
    chablais = OfagEntry(name="Chablais", canton="vd", cantons=["vd"], tier="régionale")
    assert ch_02._co_parents_for(vully, parents) == ["vaud"]
    assert ch_02._co_parents_for(zsee, parents) == ["schwyz", "zurich"]
    assert ch_02._co_parents_for(chablais, parents) == []
    assert ch_02._co_parents_for(parents["vd"], parents) == []


def test_a_record_without_communes_is_drawn_from_every_canton_it_spans():
    from _lib.ch.geometry import resolve

    class FakeIndex:
        _bfs_by_canton = {"sz": [1, 2], "zh": [3]}

        def union_from_bfs_ids(self, ids):
            from shapely.geometry import box
            from shapely.ops import unary_union
            return unary_union([box(i, 0, i + 0.5, 1) for i in ids]) if ids else None

    g, src, _ = resolve({"slug": "zurichsee", "canton": "sz", "cantons": ["sz", "zh"], "geo_communes": []},
                        commune_index=FakeIndex(), ge_sitg=None, parent_geom_by_slug={})
    assert src == "swissboundaries-canton-union" and len(getattr(g, "geoms", [g])) == 3
    g, _, _ = resolve({"slug": "schwyz", "canton": "sz", "cantons": ["sz"], "geo_communes": []},
                      commune_index=FakeIndex(), ge_sitg=None, parent_geom_by_slug={})
    assert len(getattr(g, "geoms", [g])) == 2


GPKG = sorted((ROOT / "raw" / "ch" / "swisstopo").glob("swissboundaries3d_*.gpkg"))


@pytest.mark.skipif(not GPKG, reason="swissBOUNDARIES3D not fetched")
def test_zurichsee_is_the_area_both_cantons_delimit():
    """ZH Verfügung 26.06.2020 Ziff. III (seven districts) + SZ
    Allgemeinverfügung 28.07.2025 Ziff. 2.1 (ten communes of Höfe and March)."""
    from _lib.ch.geometry import CHCommuneIndex
    from _lib.ch.per_aoc_carving import resolve_intercantonal_area
    idx = CHCommuneIndex(GPKG[-1])
    communes, misses = resolve_intercantonal_area("zurichsee", idx)
    assert misses == []
    sz = sorted(c["name"] for c in communes if c["canton"] == "sz")
    assert sz == sorted(["Altendorf", "Feusisberg", "Freienbach", "Galgenen", "Lachen", "Reichenburg",
                         "Schübelbach", "Tuggen", "Wangen (SZ)", "Wollerau"])
    names = {c["name"] for c in communes}
    assert {"Meilen", "Stäfa", "Wädenswil", "Zürich", "Uster", "Affoltern am Albis"} <= names
    assert not names & {"Innerthal", "Vorderthal", "Winterthur", "Andelfingen"}
