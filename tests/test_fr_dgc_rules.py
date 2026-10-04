"""A DGC's own colours and roster in its appellation's cahier (scripts/_lib/fr/dgc_rules.py).

Excerpts follow the cahiers in force (pdftotext -layout): Touraine (BO du 11
septembre 2025), Côtes du Rhône Villages (28 novembre 2024), Côtes de Bordeaux,
IGP Var (11 décembre 2025), IGP Isère (8 août 2024).
"""
from __future__ import annotations

from _lib.fr.dgc_rules import (
    RESERVATION,
    dgc_keys,
    dgc_text,
    drop_colours,
    strip_names,
)
from _lib.grape_lexicon import parse_grapes, parse_styles

TOURAINE = "Touraine"
TOURAINE_DGCS = ["Touraine Amboise", "Touraine Azay-le-Rideau", "Touraine Chenonceaux",
                 "Touraine Mesland", "Touraine Oisly"]

TOURAINE_III = """APPELLATION D’ORIGINE CONTRÔLÉE,
   MENTION, INDICATION, DÉNOMINATIONS                        COULEUR ET TYPES DE PRODUIT
    GÉOGRAPHIQUES COMPLEMENTAIRES
                                                       Vins tranquilles blancs, rouges et rosés et vins
    AOC « Touraine »
                                                       mousseux blancs et rosés.
    AOC « Touraine » complétée par la mention
                                                       Vins tranquilles rouges
    « primeur » ou « nouveau »
    Indication « gamay »                               Vins tranquilles rouges
    Dénominations géographiques complémentaires
                                                       Vins tranquilles blancs, rouges et rosés
    «Amboise» et «Mesland»
    Dénomination géographique complémentaire
                                                       Vins tranquilles blancs et rosés
    «Azay-le-Rideau»
      Dénomination géographique complémentaire
                                                             Vins tranquilles blancs et rouges
      «Chenonceaux»
      Dénomination géographique complémentaire
                                                             Vins tranquilles blancs
      «Oisly»
"""

TOURAINE_V = """1°- Encépagement

    APPELLATION D’ORIGINE CONTROLÉE,
    DENOMINATIONS     GEOGRAPHIQUES                                  ENCEPAGEMENT
                       AOC « Touraine »

                                                      - Cépage principal : sauvignon B ;
    Vins blancs                                       - Cépage accessoire : sauvignon gris G

                                                      - Cépage principal : cot N ;
    Vins rouges                                       - Cépages accessoires : cabernet-franc N,
                                                      gamay N, pinot noir N

                       Dénomination géographique complémentaire «Chenonceaux»

    Vins blancs                                     sauvignon B

                                                    Cépage principal : cot N
    Vins rouges                                     Cépage complémentaire : cabernet franc N

                       Dénomination géographique complémentaire «Oisly»

    Vins blancs                                     sauvignon B
"""


def keys(name):
    return dgc_keys(name, TOURAINE)


def covered():
    return set().union(*(keys(n) for n in TOURAINE_DGCS)) | {"touraine"}


def colours(text):
    return set(parse_styles(text)) & {"white", "red", "rose"}


def slugs(text):
    return {g["slug"] for g in parse_grapes(strip_names(text))["all"]}


def test_dgc_keys_take_the_part_after_the_parent_name():
    assert keys("Touraine Oisly") == {"touraine oisly", "oisly"}
    assert "montre-cul" in dgc_keys("Bourgogne Montrecul ou Montre-Cul ou En Montre-Cul", "Bourgogne")


def test_table_colour_rows_pair_each_label_with_its_value():
    want = {n: colours(dgc_text(TOURAINE_III, keys(n), covered())) for n in TOURAINE_DGCS}
    assert want["Touraine Oisly"] == {"white"}
    assert want["Touraine Chenonceaux"] == {"white", "red"}
    assert want["Touraine Azay-le-Rideau"] == {"white", "rose"}
    assert want["Touraine Amboise"] == want["Touraine Mesland"] == {"white", "red", "rose"}


def test_a_heading_scopes_the_rows_below_it():
    assert slugs(dgc_text(TOURAINE_V, keys("Touraine Oisly"), covered())) == {"sauvignon"}
    assert slugs(dgc_text(TOURAINE_V, keys("Touraine Chenonceaux"), covered())) == {
        "sauvignon", "cot", "cabernet-franc"
    }
    assert dgc_text(TOURAINE_V, keys("Touraine Mesland"), covered()) is None


CDRV_III = """1°- L'appellation d'origine contrôlée « Côtes du Rhône Villages » est réservée aux vins tranquilles blancs,
rouges ou rosés.

2°- Les dénominations géographiques complémentaires « Roaix », « Rochegude », « Rousset-les-Vignes »,
« Sablet », « Saint-Gervais », « Saint-Maurice », « Séguret », « Valréas », et
« Visan » sont réservées aux vins tranquilles blancs, rouges ou rosés.

3°- La dénomination géographique complémentaire « Chusclan » est réservée aux vins tranquilles rouges ou
rosés.
"""


def test_a_wrapped_prose_list_stays_one_sentence():
    cov = {"roaix", "rochegude", "rousset-les-vignes", "sablet", "saint-gervais", "saint-maurice",
           "seguret", "valreas", "visan", "chusclan", "cotes du rhone villages"}
    got = dgc_text(CDRV_III, {"sablet"}, cov, RESERVATION)
    assert colours(got) == {"white", "red", "rose"}
    assert colours(dgc_text(CDRV_III, {"chusclan"}, cov, RESERVATION)) == {"red", "rose"}


CDB_V = """1°- Encépagement

a)- Les vins rouges sont issus des cépages suivants :
- cépages principaux : cabernet-sauvignon N, cabernet franc N, cot N (ou malbec) et merlot N ;
- cépages accessoires : carmenère N, et petit verdot N.

b)- Les vins blancs sont issus des cépages suivants :
- cépages principaux : sauvignon B, sauvignon gris G, sémillon B et muscadelle B ;
- cépages accessoires : colombard B et ugni blanc B.
"""


def test_a_red_only_dgc_drops_the_white_clause():
    got = slugs(drop_colours(CDB_V, {"red"}, {"cadillac", "castillon", "blaye"}))
    assert got == {"cabernet-sauvignon", "cabernet-franc", "cot", "merlot", "carmenere", "petit-verdot"}


VAR_V = """Les vins bénéficiant de l’indication géographique protégée « Var » complétée ou non par le
 nom d’une des unités géographiques plus petites visées au point 2, hormis ceux complétés par
 le nom de l’unité géographique « Correns », sont produits à partir de l’ensemble des cépages
 classés en tant que variétés de vigne de raisins de cuve figurant dans la liste suivante:

  Agiorgitiko N, alicante henri bouschet N, aligoté B, syrah N, xinomavro N.

 Les vins bénéficiant de l’indication géographique protégée « Var » complétée par la mention
 géographique « Correns » sont produits à partir de l’ensemble des cépages classés en tant
 que variétés de vigne de raisins de cuve figurant dans la liste suivante :

  Floréal B, solaris B, soreli B, souvignier gris B, ugni blanc B, vermentino B, voltis B.
"""


def test_hormis_excepts_and_a_colon_takes_the_following_list():
    cov = {"correns", "argens", "var"}
    got = slugs(dgc_text(VAR_V, {"correns"}, cov))
    assert "syrah" not in got
    assert {"floreal", "solaris", "vermentino", "voltis"} <= got


ISERE_III = """L’indication géographique protégée « Isère » est réservée aux vins tranquilles rouges, rosés et blancs.

Pour l’unité géographique « Coteaux du Grésivaudan », les vins blancs présentent une robe jaune à reflets
verts. Le nez est porté sur les agrumes frais et les fleurs blanches.
"""


def test_a_description_is_not_a_colour_rule():
    assert dgc_text(ISERE_III, {"coteaux du gresivaudan"}, {"coteaux du gresivaudan", "isere"},
                    RESERVATION) is None
