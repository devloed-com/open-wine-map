"""Grape roles across the colour clauses of a FR section V (`grape_lexicon.parse_grapes`).

The card shows one role per grape. A grape accessory in one of the record's
own colour clauses and principal in another is principal; a DGC's rows and the
convention add-on ("et des variétés … sous réserve de la signature … d'une
convention") never promote, and a convention variety is read as a variety of
interest (observation), never as its clause's principal or accessory. Excerpts follow the cahiers in force: Crozes-Hermitage
(BO du MASAF, 19 décembre 2024), Arbois (15 septembre 2022), Bordeaux, Touraine
(11 septembre 2025).
"""
from __future__ import annotations

from _lib.grape_lexicon import parse_grapes


def _roles(text: str) -> dict[str, str]:
    return {t["slug"]: t["role"] for t in parse_grapes(text)["all"]}


def test_an_unheaded_colour_clause_is_principal():
    # visitor flag 2026-10-30: the white clause had run on in the red's
    # accessory chunk, so marsanne and roussanne read as accessory only
    v = (
        "1°- Encépagement\na) - Les vins rouges sont issus des cépages suivants :\n"
        "- cépage principal : syrah N ;\n- cépages accessoires : marsanne B, roussanne B.\n"
        "b) - Les vins blancs sont issus des cépages marsanne B et roussanne B.\n"
    )
    assert _roles(v) == {"syrah": "principal", "marsanne": "principal", "roussanne": "principal"}


def test_principal_in_a_later_clause_of_the_record_wins():
    v = (
        "a) - Les vins blancs sont issus des cépages suivants : - cépages principaux : "
        "chardonnay B, savagnin B ; - cépages accessoires : pinot noir N, poulsard N, trousseau N. "
        "b) - Les vins rouges et rosés sont issus des cépages suivants : - cépages principaux : "
        "pinot noir N, poulsard N, trousseau N ; - cépages accessoires : chardonnay B, savagnin B."
    )
    roles = _roles(v)
    assert all(roles[g] == "principal" for g in ("chardonnay", "savagnin", "pinot-noir", "poulsard", "trousseau"))


def test_the_convention_add_on_never_promotes():
    # Bordeaux: the climate-adaptation varieties follow "Et des variétés" in
    # the red's accessory list and again in the rosé's "exclusivement" clause
    v = (
        "b) - Les vins rouges sont issus des cépages suivants : - Cépages principaux : merlot N ; "
        "- Cépages accessoires : cot N - Et des variétés suivantes : marselan N, sous réserve de la "
        "signature d'une convention. c) - Les vins rosés sont issus exclusivement des cépages "
        "merlot N, cot N - Et des variétés marselan N, sous réserve de la signature d'une convention."
    )
    roles = _roles(v)
    assert roles["marselan"] == "observation"
    assert roles["cot"] == "principal"


def test_a_convention_variety_after_the_principal_header_is_not_principal():
    # visitor flags on Meursault (2026-11-22, card validator): aligoté, melon
    # and sacy read as principal; the cahier (BO Agri, 11 juin 2026) admits
    # them only under the INAO convention, capped at 10 % and 1 ha
    v = (
        "1°- Encépagement a) - Les vins blancs sont issus des cépages suivants : "
        "- cépages principaux : chardonnay B et pinot blanc B. "
        "- et les variétés aligoté B, melon B, sacy B, sous réserve de la signature entre l’INAO, "
        "l’ODG, l’opérateur habilité concerné et l’opérateur-vinificateur d’une convention conforme "
        "à la convention cadre approuvée par le comité national compétent. "
        "b) - Les vins rouges sont issus des cépages suivants : - cépage principal : pinot noir N ; "
        "- cépages accessoires : chardonnay B, pinot blanc B, pinot gris G, "
        "- et la variété césar N, sous réserve de la signature entre l’INAO, l’ODG, l’opérateur "
        "habilité concerné et l’opérateur-vinificateur d’une convention conforme à la convention "
        "cadre approuvée par le comité national compétent. "
        "2°- Règles de proportion à l’exploitation La proportion d’aligoté B, melon B, sacy B et "
        "césar N est limitée à 10 % de l’encépagement."
    )
    roles = _roles(v)
    assert {roles[g] for g in ("chardonnay", "pinot-blanc", "pinot-noir")} == {"principal"}
    assert roles["pinot-gris"] == "accessory"
    assert {roles[g] for g in ("aligote", "melon", "sacy", "cesar")} == {"observation"}


def test_an_unheaded_list_with_a_convention_add_on():
    # Haut-Médoc: no role header; the four convention varieties had read as
    # principal with the six varieties before them
    v = (
        "1° - Encépagement Les vins sont issus des cépages suivants : - cabernet franc N, "
        "cabernet-sauvignon N, merlot N et petit verdot N. - et des variétés arinarnoa N, castets N, "
        "marselan N et touriga nacional N, sous réserve de la signature entre l’INAO, l’ODG et les "
        "opérateurs habilités concernés, d’une convention conforme à la convention cadre approuvée "
        "par le comité national compétent les 2 et 3 Juin 2021."
    )
    roles = _roles(v)
    assert roles["merlot"] == "principal"
    assert {roles[g] for g in ("arinarnoa", "castets", "marselan", "touriga-nacional")} == {"observation"}


def test_a_table_label_inside_the_add_on_phrase():
    # Languedoc (BO Agri, 20 août 2026): pdftotext sets the row label between
    # "et les" and "variétés"
    v = (
        "- cépages principaux : grenache N, syrah N ; - cépages accessoires : carignan N, cinsaut N, "
        "et les AOC « Languedoc » (Vins rouges) variétés suivantes : agiorgitiko N, marselan N, "
        "sous réserve de la signature entre l’INAO, l’ODG et l’opérateur habilité concerné, d’une "
        "convention conforme à la convention cadre approuvée par le comité national compétent le 6 "
        "septembre 2018."
    )
    roles = _roles(v)
    assert roles["carignan"] == "accessory"
    assert roles["agiorgitiko"] == roles["marselan"] == "observation"


def test_a_singular_variety_without_a_convention_is_read_as_before():
    v = "- cépages principaux : chardonnay B et la variété pinot blanc B."
    assert _roles(v) == {"chardonnay": "principal", "pinot-blanc": "principal"}


def test_a_dgc_row_never_promotes_the_parents_grape():
    # Touraine: chenin is a variété d'intérêt for the AOC's whites, the
    # principal grape of the Amboise DGC's whites further down the table
    v = (
        "AOC « Touraine » - Cépage principal : sauvignon B ; - Cépage accessoire : sauvignon gris G, "
        "variétés « d’intérêt à fin d’adaptation » : chenin B. "
        "Dénomination géographique complémentaire «Mesland» - cépage principal : chenin B ;"
    )
    assert _roles(v)["chenin"] == "observation"


def test_an_unlabelled_row_after_the_convention_sentence_is_the_colours_roster():
    # Alsace (BO Agri, 15 janvier 2026): the white row follows the rosé's
    # adaptation cell, and riesling had been read as a variété d'intérêt
    v = (
        "« Alsace » Vins rosés pinot noir N Vins rosés : variétés d’intérêt à fin d’adaptation "
        "sous réserve de la signature entre l’INAO, l’ODG et les opérateurs habilités concernés, "
        "d’une convention Coliris N, Nebbiolo N conforme à la convention cadre approuvée par le "
        "comité national compétent. « Alsace » ou « Vin d’Alsace » suivie ou non d’un nom de "
        "lieu-dit auxerrois B, chasselas B et chasselas rose Rs, gewurztraminer Rs, pinot gris G, "
        "Vins blancs pinot noir N, riesling B, sylvaner B, et savagnin rose Rs"
    )
    roles = _roles(v)
    assert roles["coliris"] == "observation"
    assert {roles[g] for g in ("riesling", "sylvaner", "gewurztraminer")} == {"principal"}


def test_a_trailing_accessory_label_sets_the_rows_role():
    v = (
        "- variétés d’intérêt à fin d’adaptation (VIFA) : verdejo B sous réserve de la signature "
        "d’une convention entre l’INAO, l’ODG et les opérateurs habilités concernés. Toutefois, les "
        "cépages barbaroux Rs et calitor N sont autorisés en tant que cépages accessoires pour le "
        "vin rosé."
    )
    roles = _roles(v)
    assert roles["verdejo"] == "observation"
    assert roles["barbaroux"] == roles["calitor"] == "accessory"


def test_roles_by_colour_lists_a_grape_whose_role_differs_between_the_colours():
    # the card shows one role; the pill tooltip states the roles per colour
    v = (
        "1°- Encépagement\na) - Les vins rouges sont issus des cépages suivants :\n"
        "- cépage principal : syrah N ;\n- cépages accessoires : marsanne B, roussanne B.\n"
        "b) - Les vins blancs sont issus des cépages marsanne B et roussanne B.\n"
    )
    got = parse_grapes(v)["roles_by_colour"]
    assert got == {
        "marsanne": {"red": "accessory", "white": "principal"},
        "roussanne": {"red": "accessory", "white": "principal"},
    }
    # a grape with one role everywhere is not listed
    assert "syrah" not in got
    assert parse_grapes("Les vins sont issus des cépages chardonnay B et pinot noir N.")["roles_by_colour"] == {}
