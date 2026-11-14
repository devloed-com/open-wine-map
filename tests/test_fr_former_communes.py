"""Former French communes: what a pre-merger INSEE code of INAO's rows is
drawn as (`scripts/_lib/fr/former_communes.py`), and the commune-name index
that reads a cahier's names (`_lib/geom_chain`)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import geom_chain  # noqa: E402
from _lib.fr import former_communes as fc  # noqa: E402

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
HEADER = ('"MOD","DATE_EFF","TYPECOM_AV","COM_AV","TNCC_AV","NCC_AV","NCCENR_AV","LIBELLE_AV",'
          '"TYPECOM_AP","COM_AP","TNCC_AP","NCC_AP","NCCENR_AP","LIBELLE_AP"\n')


def _row(mod, date, before, name_before, after, name_after, type_before="COM", type_after="COM"):
    return (f'"{mod}","{date}","{type_before}","{before}","0","X","X","{name_before}",'
            f'"{type_after}","{after}","0","Y","Y","{name_after}"\n')


def _load(tmp_path, current):
    former = tmp_path / "former.geojson"
    former.write_text(json.dumps({"type": "FeatureCollection", "features": [
        # a commune déléguée with its own outline
        {"type": "Feature", "properties": {"code": "61003", "nom": "Anceins", "chefLieu": "61167"}, "geometry": SQUARE},
        # the seat's déléguée carries the commune's own code: not a former code
        {"type": "Feature", "properties": {"code": "61167", "nom": "La Ferté-Frênel", "chefLieu": "61167"}, "geometry": SQUARE},
    ]}), encoding="utf-8")
    moves = tmp_path / "moves.csv"
    moves.write_text(
        HEADER
        + _row("32", "2016-01-01", "61003", "Anceins", "61167", "La Ferté-en-Ouche")
        + _row("32", "2016-01-01", "61167", "La Ferté-Frênel", "61167", "La Ferté-en-Ouche")
        # fused without trace into a commune of today
        + _row("31", "1973-01-01", "14999", "Vieux-Bourg", "14001", "Ablon")
        # a change of code for the same ground
        + _row("41", "2018-01-01", "49999", "Freigné", "44225", "Vallons-de-l'Erdre")
        # a commune déléguée row is no succession of communes
        + _row("32", "2016-01-01", "61003", "Anceins", "61003", "Anceins", type_after="COMD"),
        encoding="utf-8",
    )
    return fc.load(current, former, moves, log=False)


def test_load_keeps_outlines_of_former_codes_only_and_follows_successions(tmp_path):
    former = _load(tmp_path, {"61167", "14001", "44225"})
    assert set(former.geoms) == {"61003"}
    assert former.successor == {"61003": "61167", "14999": "14001", "49999": "44225"}
    assert former.predecessors["61167"] == {"61003", "61167"}   # the seat was one of the merged communes
    assert former.predecessors["44225"] == {"49999"}
    assert former.name("14999") == "Vieux-Bourg"


def test_resolve_sorts_the_four_classes(tmp_path):
    current = {"61167", "14001", "44225"}
    former = _load(tmp_path, current)
    # its own outline, drawn exactly
    assert set(fc.resolve({"61003"}, current, former).outlines) == {"61003"}
    # its commune of today is in the aire: nothing to add
    res = fc.resolve({"14999", "14001"}, current, former)
    assert res.covered == ["14999"] and not res.undrawn and not res.whole
    # fused into a commune the aire does not list: no outline anywhere
    assert fc.resolve({"14999"}, current, former).undrawn == ["14999"]
    # a new code for the same ground: the commune of today, whole
    assert fc.resolve({"49999"}, current, former).whole == {"44225": ["49999"]}
    # a code no table knows
    assert fc.resolve({"99999"}, current, former).undrawn == ["99999"]
    # without the layer nothing is resolved and nothing is drawn
    assert fc.resolve({"61003", "14999"}, current, None).undrawn == ["14999", "61003"]


def test_union_from_insee_draws_former_communes_and_names_the_undrawn(tmp_path):
    current = {"61167", "14001", "44225"}
    former = _load(tmp_path, current)
    insee_idx = {code: SQUARE for code in current}
    geom, stats = geom_chain.union_from_insee({"61003", "14999", "49999", "14002"}, insee_idx, former)
    assert geom is not None
    assert stats["matched"] == 2 and stats["former_drawn"] == 2      # Anceins' outline, Vallons-de-l'Erdre whole
    assert stats["unmatched"] == 2 and stats["former_undrawn"] == ["14002", "Vieux-Bourg"]
    # without the layer: as before
    geom, stats = geom_chain.union_from_insee({"61167", "61003"}, insee_idx)
    assert stats == {"matched": 1, "unmatched": 1, "former_drawn": 0, "former_covered": 0, "former_undrawn": ["61003"]}


def test_find_commune_reads_the_name_as_written_before_the_loose_key(tmp_path):
    communes = tmp_path / "communes.geojson"
    communes.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"code": "17464", "nom": "Vergné", "codeDepartement": "17"}, "geometry": SQUARE},
        {"type": "Feature", "properties": {"code": "17465", "nom": "La Vergne", "codeDepartement": "17"}, "geometry": SQUARE},
        {"type": "Feature", "properties": {"code": "17139", "nom": "Dœuil-sur-le-Mignon", "codeDepartement": "17"}, "geometry": SQUARE},
        {"type": "Feature", "properties": {"code": "33069", "nom": "Le Bouscat", "codeDepartement": "33"}, "geometry": SQUARE},
    ]}), encoding="utf-8")
    former = tmp_path / "former.geojson"
    former.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"code": "17040", "nom": "La Benâte", "chefLieu": "17277", "codeDepartement": "17"},
         "geometry": SQUARE},
        # never over a commune of today of the same name
        {"type": "Feature", "properties": {"code": "17999", "nom": "Vergné", "chefLieu": "17464", "codeDepartement": "17"},
         "geometry": SQUARE},
    ]}), encoding="utf-8")
    original_root = geom_chain.ROOT
    geom_chain.ROOT = tmp_path
    try:
        name_idx, insee_idx, _ = geom_chain.load_commune_index(communes, former)
    finally:
        geom_chain.ROOT = original_root
    assert geom_chain.find_commune(name_idx, "17", "Vergné")[1] == "17464"
    assert geom_chain.find_commune(name_idx, "17", "La Vergne")[1] == "17465"
    assert geom_chain.find_commune(name_idx, "17", "Doeuil-sur-le-Mignon")[1] == "17139"   # the ligature
    assert geom_chain.find_commune(name_idx, "33", "Bouscat")[1] == "33069"                # the loose key still serves
    assert geom_chain.find_commune(name_idx, "17", "La Benâte")[1] == "17040"              # a former commune by name
    assert set(insee_idx) == {"17464", "17465", "17139", "33069"}                         # the INSEE index: communes of today


def test_union_for_appellation_draws_a_whole_departement_only_with_the_insee_index():
    record = {"aire": {"aire_geographique": {}, "aire_departements": ["Var"]}}
    insee_idx = {"83001": SQUARE, "83002": SQUARE, "84001": SQUARE}
    geom, stats = geom_chain.union_for_appellation(record, {}, insee_idx)
    assert geom is not None and stats == {"matched": 2, "unmatched": 0}
    geom, stats = geom_chain.union_for_appellation(record, {})
    assert geom is None


def test_a_renamed_commune_is_found_under_the_name_it_had(tmp_path):
    communes = tmp_path / "communes.geojson"
    communes.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"code": "04045", "nom": "Céreste-en-Luberon", "codeDepartement": "04"}, "geometry": SQUARE},
        {"type": "Feature", "properties": {"code": "04999", "nom": "Corbières", "codeDepartement": "04"}, "geometry": SQUARE},
        {"type": "Feature", "properties": {"code": "04063", "nom": "Corbières-en-Provence", "codeDepartement": "04"}, "geometry": SQUARE},
    ]}), encoding="utf-8")
    moves = tmp_path / "moves.csv"
    moves.write_text(
        HEADER
        + _row("10", "2024-01-01", "04045", "Céreste", "04045", "Céreste-en-Luberon")
        # never over a commune of today that carries the old name
        + _row("10", "2018-11-08", "04063", "Corbières", "04063", "Corbières-en-Provence"),
        encoding="utf-8",
    )
    original_root = geom_chain.ROOT
    geom_chain.ROOT = tmp_path
    try:
        name_idx, _, _ = geom_chain.load_commune_index(communes, None, moves)
    finally:
        geom_chain.ROOT = original_root
    assert geom_chain.find_commune(name_idx, "04", "Céreste")[1] == "04045"
    assert geom_chain.find_commune(name_idx, "04", "Corbières")[1] == "04999"
    assert fc.former_names({"04045"}, moves) == [("04045", "Céreste")]


def test_a_pinned_cahier_name_is_read_as_the_commune_it_means():
    slug = "euskal-sagardoa-ou-sidra-del-pais-vasco-ou-cidre-du-pays-basque-ou-cidre-du-pays-basque-eu"
    assert geom_chain._pinned_name({"slug": slug}, "ALCIETTE-BASCASSAN") == "Ahaxe-Alciette-Bascassan"
    assert geom_chain._pinned_name({"slug": "another"}, "ALCIETTE-BASCASSAN") == "ALCIETTE-BASCASSAN"
    pins = json.loads(geom_chain.COMMUNE_NAME_PINS_PATH.read_text(encoding="utf-8"))
    for record_slug, names in pins.items():
        if record_slug.startswith("_"):
            continue
        for written, pin in names.items():
            assert pin["name"].strip() and pin["reason"].strip() and pin["verified"], (record_slug, written)


def _load_moved(tmp_path, current):
    former = tmp_path / "former-moved.geojson"
    former.write_text(json.dumps({"type": "FeatureCollection", "features": [
        # an associated commune of a commune of another département
        {"type": "Feature", "properties": {"code": "52210", "nom": "Frettes", "chefLieu": "70122"}, "geometry": SQUARE},
        # a commune déléguée under the code its change of département gave it
        {"type": "Feature", "properties": {"code": "49382", "nom": "Le Fresne-sur-Loire", "chefLieu": "49160"},
         "geometry": SQUARE},
    ]}), encoding="utf-8")
    moves = tmp_path / "moves-moved.csv"
    moves.write_text(
        HEADER
        # Isère → Rhône, 1967: the commune lives on under a new code
        + _row("41", "1967-12-31", "38088", "Chassieu", "69271", "Chassieu")
        # Haute-Marne → Haute-Saône by a merger, 1974
        + _row("33", "1974-07-01", "52210", "Frettes", "70122", "Champlitte")
        # merged inside its département in 1973, the merged commune left it in 2018
        + _row("33", "1973-05-01", "14507", "Pleines-Œuvres", "14513", "Pont-Farcy")
        + _row("41", "2018-01-01", "14513", "Pont-Farcy", "50649", "Pont-Farcy")
        + _row("32", "2018-01-01", "50649", "Pont-Farcy", "50592", "Tessy-Bocage")
        # changed département, then merged: the outline is under the later code
        + _row("41", "2015-12-31", "44060", "Le Fresne-sur-Loire", "49382", "Le Fresne-sur-Loire")
        + _row("32", "2016-01-01", "49382", "Le Fresne-sur-Loire", "49160", "Ingrandes-Le Fresne sur Loire")
        + _row("32", "2016-01-01", "49160", "Ingrandes", "49160", "Ingrandes-Le Fresne sur Loire"),
        encoding="utf-8",
    )
    return fc.load(current, former, moves, log=False)


def test_a_code_that_left_its_departement_before_the_cahiers_is_not_in_the_aire(tmp_path):
    """IGP Isère is "le département de l'Isère": INAO's rows still carry
    Chassieu under 38088, a commune of the Rhône since 1967. Frettes has an
    outline of its own, in Haute-Saône since 1974, and IGP Haute-Marne is "le
    territoire du département de la Haute-Marne"."""
    current = {"69271", "70122", "50592", "49160"}
    former = _load_moved(tmp_path, current)
    assert former.left_departement["38088"] == "1967-12-31"
    assert former.left_departement["52210"] == "1974-07-01"
    res = fc.resolve({"38088", "52210"}, current, former)
    assert res.elsewhere == ["38088", "52210"]
    assert not res.outlines and not res.whole and not res.undrawn and not res.covered
    insee_idx = {code: SQUARE for code in current}
    geom, stats = geom_chain.union_from_insee({"38088", "52210"}, insee_idx, former)
    assert geom is None
    assert stats["former_elsewhere"] == 2 and stats["former_undrawn"] == [] and stats["unmatched"] == 0


def test_a_code_that_moved_inside_the_aire_is_resolved_as_any_other(tmp_path):
    """Frettes went to Haute-Saône in 1974: outside IGP Haute-Marne, inside an
    aire that holds communes of Haute-Saône too (IGP Franche-Comté's Antorpe,
    Jura → Doubs)."""
    current = {"69271", "70122", "70001", "50592", "49160"}
    former = _load_moved(tmp_path, current)
    # the aire has a commune of today in the département the ground went to
    res = fc.resolve({"52210", "70001"}, current, former)
    assert set(res.outlines) == {"52210"} and not res.elsewhere
    res = fc.resolve({"52210", "70122"}, current, former)
    assert not res.elsewhere and (set(res.outlines) == {"52210"} or res.covered == ["52210"])
    # … and without one the code is outside the aire
    assert fc.resolve({"52210", "50592"}, current, former).elsewhere == ["52210"]


def test_a_commune_that_crossed_a_departement_border_after_the_cahiers_is_resolved_as_any_other(tmp_path):
    current = {"69271", "70122", "50592", "49160"}
    former = _load_moved(tmp_path, current)
    # Pont-Farcy (and Pleines-Œuvres, merged into it in 1973) left the
    # Calvados in 2018: the cahier of the day held them
    assert former.left_departement["14513"] == "2018-01-01"
    assert former.left_departement["14507"] == "2018-01-01"
    res = fc.resolve({"14507", "14513"}, current, former)
    assert res.undrawn == ["14507", "14513"] and not res.elsewhere
    # Le Fresne-sur-Loire: the outline its later code carries is drawn for
    # the code INAO's rows keep
    res = fc.resolve({"44060"}, current, former)
    assert set(res.outlines) == {"44060"} and not res.elsewhere
    assert former.commune_of_today("44060") == "49160"


def test_obsolete_codes_of_inao_s_table(tmp_path):
    """A commune suppressed and shared out, a Corsican commune merged before
    1976 under the 2A code it never bore, and a commune that ceased before
    INSEE's table begins (pinned)."""
    moves = tmp_path / "moves-obsolete.csv"
    moves.write_text(
        HEADER
        + _row("30", "1965-01-01", "45117", "Creusy", "45093", "Chevilly")
        + _row("30", "1965-01-01", "45117", "Creusy", "45313", "Sougy")
        + _row("31", "1965-01-01", "20237", "Poggio-di-Tallano", "20308", "Sainte-Lucie-de-Tallano")
        + _row("41", "1976-01-01", "20308", "Sainte-Lucie-de-Tallano", "2A308", "Sainte-Lucie-de-Tallano"),
        encoding="utf-8",
    )
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({
        "_doc": "…",
        "66131": {"name": "Palalda", "today": "66003"},
    }), encoding="utf-8")
    current = {"45093", "45313", "2A308", "66003"}
    former = fc.load(current, tmp_path / "none.geojson", moves, pins_path=pins, log=False)
    # shared out: covered only when every taker is in the aire
    assert former.split == {"45117": {"45093", "45313"}}
    assert fc.resolve({"45117", "45093", "45313"}, current, former).covered == ["45117"]
    assert fc.resolve({"45117", "45093"}, current, former).undrawn == ["45117"]
    assert former.name("45117") == "Creusy"
    # Corsica: the split of 1976 moved no ground, and 2A237 reads as 20237
    assert former.successor["2A237"] == "2A308" and former.name("2A237") == "Poggio-di-Tallano"
    assert "20237" not in former.left_departement and "2A237" not in former.left_departement
    assert fc.resolve({"2A237", "2A308"}, current, former).covered == ["2A237"]
    # pinned
    assert fc.resolve({"66131", "66003"}, current, former).covered == ["66131"]
    res = fc.resolve({"66131"}, current, former)
    assert res.whole == {} and res.undrawn == ["66131"] and former.name("66131") == "Palalda"


def test_the_pins_file_names_a_source_for_every_code():
    pins = fc.load_pins()
    assert pins
    for code, pin in pins.items():
        assert len(code) == 5 and len(pin["today"]) == 5
        assert pin["name"] and pin["reason"] and pin["source"].startswith("https://") and pin["verified"]


def test_a_departement_is_found_whatever_its_hyphens_and_a_cut_name_is_none():
    """The département lookup every consumer of a cahier's list shares
    (`geom_chain.dept_code_for`): Marc d'Auvergne's 88 communes stand under
    « Puy-deDôme », and until 2026-11-13 none of them resolved — the aire
    audit skipped the record without a word."""
    assert geom_chain.dept_code_for("Puy-de-Dôme") == "63"
    assert geom_chain.dept_code_for("Puy-deDôme") == "63"
    assert geom_chain.dept_code_for("Pyrénées Orientales") == "66"
    assert geom_chain.dept_code_for("Maine-et Loire") == "49"
    assert geom_chain.dept_code_for("Côte-d’Or") == "21" and geom_chain.dept_code_for("Côte-d'Or") == "21"
    assert geom_chain.dept_code_for("Loire") == "42" and geom_chain.dept_code_for("Haute-Loire") == "43"
    for cut in ("Côte", "Côtes", "Ille", "Hautes", "Bouches", "Saône"):
        assert geom_chain.dept_code_for(cut) is None, cut


def test_a_commune_is_known_by_the_name_its_cahier_writes():
    record = {"slug": "marc-d-auvergne"}
    assert geom_chain._pinned_name(record, "Saint-Maurice-ès-Allier") == "Saint-Maurice"
    assert geom_chain.written_names(record, "Saint-Maurice") == ["Saint-Maurice-ès-Allier"]
    assert geom_chain.written_names({"slug": "pauillac"}, "Saint-Maurice") == []
    pins = json.loads(geom_chain.COMMUNE_NAME_PINS_PATH.read_text(encoding="utf-8"))
    for slug, names in pins.items():
        if slug.startswith("_"):
            continue
        for written, pin in names.items():
            assert pin["name"] and pin["reason"] and pin["verified"], (slug, written)
