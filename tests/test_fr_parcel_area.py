"""A French cahier's own parcel area, told apart from a parcel identification
and from the parcel areas of other appellations (second look at the triage of
2026-11-23: the first cut flagged every «aire parcellaire délimitée»)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.fr.parcel_area import PUBLISHED_APART, parcel_area_note, sets_own_parcel_area  # noqa: E402

CHAMPAGNE = {"IV": (
    "sous réserve des dispositions suivantes: - dans l’arrondissement de Vitry-le-François "
    "(département de la Marne), l’aire parcellaire délimitée est celle approuvée par le comité "
    "national compétent de l’Institut national de l’origine et de la qualité lors de la séance "
    "des 7 et 8 novembre 1990 et dont les plans sont déposés dans les mairies")}
CASSIS = {"IV": (
    "2°- Aire parcellaire délimitée Les vins sont issus exclusivement des vignes situées dans "
    "l’aire parcellaire de production telle qu’approuvée par le comité national compétent de "
    "l’Institut national de l’origine et de la qualité."),
    "VI": "L’apport de terre exogène sur des parcelles de l’aire parcellaire délimitée est interdit"}
CORREZE = {"IV": (
    "2°- Aire parcellaire délimitée Les vins sont issus de raisins récoltés sur des parcelles "
    "ayant fait l’objet d’une procédure d’identification, approuvée par le comité national")}
ARMAGNAC = {"3": (
    "Aire parcellaire délimitée Le raisin est récolté sur des parcelles identifiées selon des "
    "critères relatifs à leur lieu d’implantation, fixés par le comité national compétent de "
    "l’INAO en ses séances des 11 et 12 février 2004, approuvés")}
MARC_DU_JURA = {"3": (
    "2 Aire parcellaire délimitée Les marcs proviennent de raisins récoltés dans des vignes "
    "situées dans les aires parcellaires de production définies dans les cahiers des charges "
    "des appellations d’origine contrôlées « Arbois », « Côtes du Jura », approuvées")}
FINE_BORDEAUX = {"6": (
    "Aire parcellaire délimitée Publié au BO agri du MASA le 17 avril 2025 Les parcelles "
    "plantées en vigne, exclues de l'aire délimitée parcellaire approuvée lors des séances du "
    "comité national compétent, continuent à bénéficier, pour leur récolte, du droit à "
    "l'indication géographique jusqu'à leur arrachage")}


def test_own_parcel_area() -> None:
    assert sets_own_parcel_area(CHAMPAGNE)
    assert sets_own_parcel_area(CASSIS)
    assert parcel_area_note("champagne", CHAMPAGNE) == "unpublished"


def test_identification_is_not_a_delimitation() -> None:
    assert not sets_own_parcel_area(CORREZE)
    assert not sets_own_parcel_area(ARMAGNAC)


def test_other_appellations_parcel_areas_are_not_the_records_own() -> None:
    assert not sets_own_parcel_area(MARC_DU_JURA)
    assert not sets_own_parcel_area(FINE_BORDEAUX)
    assert parcel_area_note("fine-bordeaux", FINE_BORDEAUX) is None


def test_published_apart() -> None:
    assert parcel_area_note("rhum-de-la-martinique", CASSIS) == "apart"
    for slug, entry in PUBLISHED_APART.items():
        assert entry["resource"].startswith("https://static.data.gouv.fr/"), slug
        assert entry["reason"] and entry["verified"], slug
