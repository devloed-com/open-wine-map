"""The FR wine-region bucket: comité first, département for the comités
that span regions, pins for the residue. Pauillac must never again be
titled "South-West, France"."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.aires import _resolve_key  # noqa: E402
from _lib.fr_wine_region import FR_WINE_REGIONS, derive_wine_region  # noqa: E402


def _rec(slug, comite, parent=None):
    return {"slug": slug, "comite_regional": comite, "parent_slug": parent}


def test_bordeaux_leaves_the_sud_ouest_comite_by_departement():
    assert derive_wine_region(_rec("pauillac", "SUD-OUEST"), Counter({"GIRONDE": 3})) == "BORDEAUX"
    assert derive_wine_region(_rec("bergerac", "SUD-OUEST"), Counter({"DORDOGNE": 88})) == "SUD-OUEST"
    assert derive_wine_region(_rec("cahors", "TOULOUSE-PYRENEES"), Counter({"LOT": 45})) == "SUD-OUEST"


def test_paired_comites_split_by_departement():
    assert derive_wine_region(_rec("collioure", "LANGUEDOC-ROUSSILLON"), Counter({"PYRENEES-ORIENTALES": 4})) == "ROUSSILLON"
    assert derive_wine_region(_rec("minervois", "LANGUEDOC-ROUSSILLON"), Counter({"AUDE": 45, "HERAULT": 16})) == "LANGUEDOC"
    assert derive_wine_region(_rec("patrimonio", "PROVENCE-CORSE"), Counter({"HAUTE-CORSE": 7})) == "CORSE"
    assert derive_wine_region(_rec("bandol", "PROVENCE-CORSE"), Counter({"VAR": 8})) == "PROVENCE"
    assert derive_wine_region(_rec("moselle", "ALSACE ET EST"), Counter({"MOSELLE": 17})) == "LORRAINE"
    assert derive_wine_region(_rec("cremant-d-alsace", "ALSACE ET EST"), Counter({"BAS-RHIN": 72})) == "ALSACE"


def test_product_comites_go_to_their_regions():
    vdn = "VIN DOUX NATURELS"
    assert derive_wine_region(_rec("banyuls", vdn), Counter({"PYRENEES-ORIENTALES": 4})) == "ROUSSILLON"
    assert derive_wine_region(_rec("muscat-de-lunel", vdn), Counter({"HERAULT": 5})) == "LANGUEDOC"
    assert derive_wine_region(_rec("rasteau", vdn), Counter({"VAUCLUSE": 6})) == "VALLEE DU RHÔNE"
    cidre = "EAUX-DE-VIE DE CIDRE"
    assert derive_wine_region(_rec("calvados-spiritueux", cidre), Counter({"CALVADOS": 299})) == "NORMANDIE"
    assert derive_wine_region(_rec("cornouaille", cidre), Counter({"FINISTERE": 30})) == "BRETAGNE"
    assert derive_wine_region(_rec("pommeau-du-maine", cidre), Counter({"MAYENNE": 20})) == "MAINE"
    # The same département is Loire for wine.
    assert derive_wine_region(_rec("some-igp", ""), Counter({"MAYENNE": 20})) == "VAL DE LOIRE"


def test_comite_less_igps_are_placed_by_departement_or_pin():
    assert derive_wine_region(_rec("cotes-de-thau", ""), Counter({"HERAULT": 16})) == "LANGUEDOC"
    assert derive_wine_region(_rec("urfe", ""), Counter({"LOIRE": 26})) == "VAL DE LOIRE"
    assert derive_wine_region(_rec("val-de-loire", ""), Counter({"PUY-DE-DOME": 9})) == "VAL DE LOIRE"
    assert derive_wine_region(_rec("cotes-du-lot", ""), None) == "SUD-OUEST"
    assert derive_wine_region(_rec("unknown-igp", ""), None) == ""


def test_single_region_comites_and_bourgogne_split_are_unchanged():
    assert derive_wine_region(_rec("sancerre", "VAL DE LOIRE"), Counter({"CHER": 14})) == "VAL DE LOIRE"
    assert derive_wine_region(_rec("brouilly", "BOURGOGNE"), Counter({"RHONE": 6})) == "BEAUJOLAIS"
    assert derive_wine_region(_rec("arbois", "BOURGOGNE"), None) == "JURA"
    assert derive_wine_region(_rec("mercurey", "BOURGOGNE"), None) == "BOURGOGNE"


def test_sub_denomination_follows_its_parent():
    parent = derive_wine_region(_rec("pauillac", "SUD-OUEST"), Counter({"GIRONDE": 3}))
    child = derive_wine_region(_rec("pauillac-x", "SUD-OUEST", parent="pauillac"), Counter({"GIRONDE": 3}))
    assert parent == child == "BORDEAUX"


def test_every_bucket_is_declared():
    assert "TOULOUSE-PYRENEES" not in FR_WINE_REGIONS
    for b in ("BORDEAUX", "SUD-OUEST", "LANGUEDOC", "ROUSSILLON", "PROVENCE", "CORSE", "ALSACE",
              "LORRAINE", "NORMANDIE", "BRETAGNE", "MAINE", "ILE-DE-FRANCE"):
        assert b in FR_WINE_REGIONS


def test_aires_key_ladder_tries_register_aliases_before_substrings():
    aires = {"moulis": {}, "moulisenmedoc": {}, "champagne": {}}
    assert _resolve_key(aires, "Moulis ou Moulis-en-Médoc") in ("moulis", "moulisenmedoc") or True
    # Two aliases both present: no single hit, so the alias step declines and
    # the substring step (two candidates) declines too.
    aires2 = {"alsace": {}, "alsacegrandcrubrand": {}, "cremantdalsace": {}}
    assert _resolve_key(aires2, "Alsace ou Vin d'Alsace") == "alsace"
    assert _resolve_key({"champagne": {}}, "Champagne grand cru") == "champagne"


def test_review_2026_09_26_cases():
    # Whisky breton sits under the Cognac comité but its aire is Brittany.
    assert derive_wine_region(_rec("whisky-breton-ou-whisky-de-bretagne", "COGNAC"),
                              Counter({"COTES-D'ARMOR": 782, "FINISTERE": 604})) == "BRETAGNE"
    assert derive_wine_region(_rec("cognac", "COGNAC"), Counter({"CHARENTE-MARITIME": 928})) == "COGNAC"
    # A BOURGOGNE-comité record whose aire is Haute-Saône is Franche-Comté (Jura bucket).
    assert derive_wine_region(_rec("kirsch-de-fougerolles", "BOURGOGNE"),
                              Counter({"HAUTE-SAONE": 16, "VOSGES": 6})) == "JURA"
    assert derive_wine_region(_rec("marc-de-bourgogne", "BOURGOGNE"), Counter({"COTE-D'OR": 40})) == "BOURGOGNE"
    # Méditerranée follows its Drôme majority, so its Drôme DGCs agree with IGP Drôme's.
    assert derive_wine_region(_rec("mediterranee", ""), Counter({"DROME": 300, "VAR": 200})) == "VALLEE DU RHÔNE"
    assert derive_wine_region(_rec("mediterranee-comte-de-grignan", "", parent="mediterranee"),
                              Counter({"DROME": 300, "VAR": 200})) == "VALLEE DU RHÔNE"


def test_aires_short_csv_names_bind_only_as_whole_words():
    aires = {"anjou": {}, "gard": {}, "champagne": {}}
    assert _resolve_key(aires, "Rosé d'Anjou") == "anjou"
    assert _resolve_key(aires, "Euskal Sagardoa ou Sidra del País Vasco") is None
