"""One appellation's clauses in a shared cahier (scripts/_lib/fr/shared_cahier.py).

Excerpts follow the cahiers in force: Alsace grand cru (BO du MASA, 17 juillet
2025), Anjou / Cabernet d'Anjou / Rosé d'Anjou (25 janvier 2024),
Pouilly-Fumé / Pouilly-sur-Loire.
"""
from __future__ import annotations

from _lib.fr.shared_cahier import covered_names, is_shared, own_encepagement, own_text
from _lib.grape_lexicon import parse_grapes, parse_styles

AGC_I = (
    "Seuls peuvent prétendre à l’une des appellations d’origine contrôlées «Alsace grand cru "
    "Altenberg de Bergheim »,\n« Alsace grand cru Brand », « Alsace grand cru Hengst », "
    "« Alsace grand cru Kaefferkopf »,\n« Alsace grand cru Kirchberg de Barr», « Alsace grand cru "
    "Vorbourg », « Alsace grand cru Zinnkoepflé », « Alsace grand cru Zotzenberg» initialement "
    "reconnues par les décrets des 20 novembre\n1975, les vins répondant aux dispositions "
    "particulières fixées ci-après.\n"
)

AGC_III = (
    "Les appellations d’origine contrôlées visées par le présent cahier des charges à l’exception "
    "des appellations d’origine\ncontrôlées « Alsace grand cru Hengst », « Alsace grand cru Kirchberg "
    "de Barr » et « Alsace grand cru Vorbourg » sont\nréservées aux vins blancs tranquilles.\n\n"
    "Les appellations d’origine contrôlées « Alsace grand cru Hengst », « Alsace grand cru Kirchberg "
    "de Barr » et « Alsace\ngrand cru Vorbourg » sont réservées aux vins blancs et rouges tranquilles.\n"
)

AGC_V = """1°- Encépagement

a) - Les vins sont issus :

- pour les vins blancs :
     − soit d'un seul des cépages suivants : gewurztraminer Rs, muscat à petits grains blancs B, muscat à petits grains
         roses Rs, muscat ottonel B, pinot gris G, riesling B,
     − soit de l'assemblage des cépages suivants : muscat à petits grains blancs B, muscat à petits grains roses Rs, muscat
         ottonel B

- pour les vins rouges : du cépage pinot noir N

b) - Les vins à appellation d'origine contrôlée « Alsace grand cru Altenberg de Bergheim » sont issus :
- soit d'un seul des cépages suivants : gewurztraminer Rs, pinot gris G, riesling B,
- soit d’un assemblage des cépages suivants :
      − cépage principal : riesling B,
      − cépages complémentaires : gewurztraminer Rs, pinot gris G,
      − cépages accessoires : pour les vignes plantées avant le 26 mars 2005, chasselas B, muscat à petits grains blancs
          B, muscat à petits grains roses Rs, muscat ottonel B, pinot blanc B, pinot noir N.

c) - Les vins à appellation d'origine contrôlée « Alsace grand cru Zotzenberg » sont issus d'un seul des cépages suivants
: gewurztraminer Rs, pinot gris G, riesling B, sylvaner B.

d) – Les vins à appellation d'origine contrôlée « Alsace grand cru Kaefferkopf » sont issus :
- soit d'un seul des cépages suivants : gewurztraminer Rs, pinot gris G, riesling B,
- soit d’un assemblage des cépages suivants :
      − cépage principal : gewurztraminer Rs,
      − cépage complémentaire : riesling B,
      − cépages accessoires : muscat à petits grains blancs B, muscat à petits grains roses Rs, muscat ottonel B, pinot
          gris G.

e) - Les vins susceptibles de bénéficier des mentions « vendanges tardives » ou « sélection de grains nobles » sont issus
des cépages suivants : gewurztraminer Rs, muscat à petits grains blancs B, muscat à petits grains roses Rs, muscat ottonel
B, pinot gris G, riesling B.

2°- Règles de proportion à l'exploitation

b) - Pour les vins élaborés à partir de plusieurs cépages et susceptibles de bénéficier de l'appellation d'origine contrôlée «
Alsace grand cru Kaefferkopf », la proportion du cépage gewurztraminer Rs ne peut être inférieure à 60 % de
l’encépagement. La proportion des cépages muscat à petits grains blancs B, muscat à petits grains roses Rs, muscat ottonel B,
ne peut être supérieure à 10 % de l’encépagement.
"""

MUSCATS = {"muscat-a-petits-grains", "muscat-a-petits-grains-roses", "muscat-ottonel"}
WHITE6 = MUSCATS | {"gewurztraminer", "pinot-gris", "riesling"}


def cru(name: str) -> tuple[set[str], set[str], list[str]]:
    covered = covered_names(AGC_I)
    full = f"Alsace grand cru {name}"
    styles = parse_styles(own_text(AGC_III, full, covered), ["Vin tranquille"])
    grapes = parse_grapes(own_encepagement(AGC_V, full, covered, styles))
    return (
        {g["slug"] for g in grapes["principal"]},
        {g["slug"] for g in grapes["accessory"]},
        styles,
    )


def test_a_general_cru_is_white_with_the_six_varieties():
    principal, accessory, styles = cru("Brand")
    assert principal == WHITE6
    assert accessory == set()
    assert "red" not in styles and "white" in styles


def test_the_three_red_crus_add_pinot_noir():
    for name in ("Hengst", "Kirchberg de Barr", "Vorbourg"):
        principal, accessory, styles = cru(name)
        assert principal == WHITE6 | {"pinot-noir"}, name
        assert {"red", "white"} <= set(styles), name


def test_zotzenberg_takes_sylvaner_and_no_muscat():
    principal, accessory, styles = cru("Zotzenberg")
    assert principal == {"gewurztraminer", "pinot-gris", "riesling", "sylvaner"}
    assert accessory == set()


def test_altenberg_de_bergheim_blend_accessories_stay_white():
    principal, accessory, styles = cru("Altenberg de Bergheim")
    assert principal == {"gewurztraminer", "pinot-gris", "riesling"}
    assert accessory == MUSCATS | {"chasselas", "pinot-blanc", "pinot-noir"}
    assert "red" not in styles


def test_kaefferkopf_muscats_are_accessory_and_the_proportion_rules_are_not_read():
    principal, accessory, _ = cru("Kaefferkopf")
    assert principal == {"gewurztraminer", "pinot-gris", "riesling"}
    assert accessory == MUSCATS


def test_accented_name_in_section_i_matches_the_record():
    assert is_shared(covered_names(AGC_I), "Alsace grand cru Zinnkoepfle")


ANJOU_I = (
    "Seuls peuvent prétendre aux appellations d’origine contrôlées suivantes les vins répondant aux "
    "dispositions\nparticulières fixées ci-après :\n- « Anjou », initialement reconnue par les décrets "
    "du 14 novembre 1936 ;\n- « Cabernet d’Anjou », initialement reconnue par le décret du 9 mai 1964 ;\n"
    "- « Rosé d’Anjou », initialement reconnue par le décret du 31 décembre 1957.\n"
)

ANJOU_III = (
    "1°- L’appellation d’origine contrôlée « Anjou » est réservée aux vins tranquilles blancs et rouges "
    "et aux vins\nmousseux blancs et rosés.\n\n"
    "2°- L’appellation d’origine contrôlée « Anjou » suivie de l’indication « gamay », complétée ou non "
    "par la\nmention « primeur » ou « nouveau », est réservée aux vins tranquilles rouges.\n\n"
    "3°- Les appellations d’origine contrôlées « Cabernet d’Anjou » et « Rosé d’Anjou », complétées ou "
    "non par la\nmention « primeur » ou « nouveau », sont réservées aux vins tranquilles rosés.\n"
)

ANJOU_V = """1°- Encépagement

Les vins sont issus des cépages suivants :

APPELLATION D’ORIGINE
CONTRÔLEE, INDICATION,                                                 CEPAGES
TYPE ET COULEUR DES VINS

« Anjou »

                                          Cépage principal : chenin B (ou pineau de la Loire)
Vins tranquilles blancs
                                          Cépages accessoires : chardonnay B, sauvignon B

                                          Cépages principaux : cabernet franc N, cabernet-sauvignon N
Vins tranquilles rouges
                                          Cépages accessoires : grolleau N, pineau d’Aunis N

Indication « gamay »                      Gamay N

« Cabernet d’Anjou »

Vins tranquilles rosés                    Cabernet franc N, cabernet-sauvignon N

« Rosé d’Anjou »

                                          Cabernet franc N, cabernet-sauvignon N, cot N, gamay N, grolleau N,
Vins tranquilles rosés
                                          grolleau gris G, pineau d’Aunis N

2°- Règles de proportion à l’exploitation
"""


def anjou(name: str) -> tuple[set[str], list[str]]:
    covered = covered_names(ANJOU_I)
    styles = parse_styles(own_text(ANJOU_III, name, covered))
    grapes = parse_grapes(own_encepagement(ANJOU_V, name, covered, styles))
    return {g["slug"] for g in grapes["all"]}, styles


def test_anjou_table_rows_split_by_appellation():
    grapes, styles = anjou("Anjou")
    assert "chenin" in grapes and "cot" not in grapes
    assert {"white", "red"} <= set(styles)
    grapes, styles = anjou("Cabernet d’Anjou")
    assert grapes == {"cabernet-franc", "cabernet-sauvignon"}
    assert "rose" in styles and "red" not in styles and "white" not in styles
    grapes, _ = anjou("Rosé d’Anjou")
    assert "cot" in grapes and "chenin" not in grapes


POUILLY_I = (
    "Seuls peuvent prétendre à l’appellation d’origine contrôlée « Pouilly-Fumé » ou « Blanc Fumé de "
    "Pouilly\n» et à l’appellation d’origine contrôlée « Pouilly-sur-Loire », initialement reconnues "
    "par le décret du 31\njuillet 1937, les vins répondant aux dispositions particulières fixées ci-après.\n"
)

POUILLY_V = """Les vins sont issus des cépages suivants :

    APPELLATION D’ORIGINE CONTRÔLEE                                      CÉPAGES

   «Pouilly-Fumé » ou « Blanc Fumé de Pouilly»        sauvignon B.

   « Pouilly-sur-Loire »                              chasselas B.
"""


def test_register_name_with_alias_matches_its_row():
    covered = covered_names(POUILLY_I)
    for name, want in (
        ("Pouilly-Fumé ou Blanc Fumé de Pouilly", {"sauvignon"}),
        ("Pouilly-sur-Loire", {"chasselas"}),
    ):
        grapes = parse_grapes(own_encepagement(POUILLY_V, name, covered, ["white"]))
        assert {g["slug"] for g in grapes["all"]} == want, name


def test_a_single_appellation_cahier_is_left_alone():
    section_i = "Seuls peuvent prétendre à l’appellation « Pouilly-Fumé » ou « Blanc Fumé de Pouilly »."
    covered = covered_names(section_i)
    assert not is_shared(covered, "Pouilly-Fumé ou Blanc Fumé de Pouilly")
    text = "a) - Les vins sont issus de sauvignon B.\n\nb) - Les vins « Pouilly-Fumé » sont issus de sauvignon B."
    assert own_text(text, "Pouilly-Fumé ou Blanc Fumé de Pouilly", covered) == text
