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


# ---------------------------------------------------------------- Alsace / Savoie rows (2026-11-07)
# The Alsace cahier (BO Agri du 15 janvier 2026) lists one DGC per table row,
# one blank line apart; the Savoie cahier (BO-AGRI du 6 juillet 2023) wraps a
# row's label over three lines around its value. Until 2026-11-07 no DGC of an
# "X ou Y" parent matched its own row, pooled rows gave every Alsace DGC the
# union of the rows, and the Savoie heading ran into the rows below it.

ALSACE = "Alsace ou Vin d'Alsace"
ALSACE_DGCS = ["Alsace Bergheim", "Alsace Blienschwiller", "Alsace Côtes de Barr",
               "Alsace Klevener de Heiligenstein", "Alsace Ottrott", "Alsace Rodern",
               "Alsace Saint-Hippolyte", "Alsace Wolxheim"]

ALSACE_V = """1°- Règles d’encépagement

a) - Les vins sont issus des cépages suivants :

                                         « Alsace » ou « Vin d’Alsace » suivie ou non d’un nom de lieu-dit

                                                       auxerrois B, chasselas B et chasselas rose Rs,
                                                       gewurztraminer Rs, muscat ottonel B, pinot blanc B, pinot gris G,
Vins blancs                                            pinot noir N, riesling B, sylvaner B, et savagnin rose Rs,
                                                       pour les seules parcelles appartenant à l’aire parcellaire
                                                       délimitée de la dénomination géographique « Klevener de
                                                       Heiligenstein »
Vins rouges                                            pinot noir N

            « Alsace » ou « Vin d’Alsace » suivie d’une dénomination géographique complémentaire


« Bergheim »                                          gewurztraminer Rs

« Blienschwiller », « Côtes de Barr »                 sylvaner B

« Klevener de Heiligenstein »                         savagnin rose Rs

« Ottrott », « Rodern », « Saint Hippolyte »          pinot noir N

« Scherwiller », « Wolxheim »                         riesling B
"""

ALSACE_III = """APPELLATION D’ORIGINE CONTRÔLEE, DENOMINATION
                                                                                  TYPE DE PRODUIT
      GEOGRAPHIQUE COMPLÉMENTAIRE, LIEU-DIT,
                                                                                ET COULEUR DES VINS
         DENOMINATIONS EN USAGE, MENTIONS

 « Alsace » ou « Vin d’Alsace »                                           Vins tranquilles blancs, rouges et rosés

 « Alsace » ou « Vin d’Alsace » suivi d’un nom de lieu- dit               Vins tranquilles blancs et rouges

Dénominations géographiques complémentaires :
- « Bergheim » ;
- « Blienschwiller » ;
- « Côtes de Barr » ;
                                                                            Vins tranquilles blancs
- « Klevener de Heiligenstein » ;
- « Scherwiller » ;
- « Wolxheim »
Dénominations géographiques complémentaires :
- « Rodern » ;
- « Saint Hippolyte » ;                                                     Vins tranquilles rouges
- « Ottrott ».

Dénomination géographique complémentaire « Côte de Rouffach »               Vins tranquilles blancs et rouges

Mentions « vendanges tardives » ou « sélection de grains nobles »           Vins tranquilles blancs
"""


def alsace_keys(name):
    return dgc_keys(name, ALSACE)


def alsace_covered():
    return set().union(*(alsace_keys(n) for n in ALSACE_DGCS)) | {"alsace", "vin d'alsace"}


def test_dgc_keys_strip_every_alias_of_an_x_ou_y_parent():
    assert "klevener de heiligenstein" in alsace_keys("Alsace Klevener de Heiligenstein")
    assert "apremont" in dgc_keys("Vin de Savoie Apremont", "Vin de Savoie ou Savoie")
    # the hyphen SIQO writes where the cahier's row reads « Saint Hippolyte »
    assert {"saint-hippolyte", "saint hippolyte"} <= alsace_keys("Alsace Saint-Hippolyte")


def test_one_dgc_per_row_takes_its_own_row_not_the_pooled_rows():
    rows = {n: slugs(dgc_text(ALSACE_V, alsace_keys(n), alsace_covered())) for n in ALSACE_DGCS}
    assert rows["Alsace Bergheim"] == {"gewurztraminer"}
    assert rows["Alsace Blienschwiller"] == rows["Alsace Côtes de Barr"] == {"sylvaner"}
    assert rows["Alsace Ottrott"] == rows["Alsace Rodern"] == rows["Alsace Saint-Hippolyte"] == {"pinot-noir"}
    assert rows["Alsace Wolxheim"] == {"riesling"}


def test_a_value_cell_naming_the_dgc_yields_to_its_own_row():
    # the parent's white row restricts savagnin rose to the Klevener parcels;
    # the DGC's own row below is its roster
    assert slugs(dgc_text(ALSACE_V, alsace_keys("Alsace Klevener de Heiligenstein"),
                          alsace_covered())) == {"savagnin-rose"}


def test_alsace_dgc_colours_come_from_the_label_block_of_section_iii():
    want = {n: colours(dgc_text(ALSACE_III, alsace_keys(n), alsace_covered(), RESERVATION))
            for n in ALSACE_DGCS}
    assert want["Alsace Bergheim"] == want["Alsace Klevener de Heiligenstein"] == {"white"}
    assert want["Alsace Ottrott"] == want["Alsace Saint-Hippolyte"] == {"red"}


SAVOIE = "Vin de Savoie ou Savoie"
SAVOIE_DGCS = ["Vin de Savoie Apremont", "Vin de Savoie Arbin", "Vin de Savoie Saint-Jean-de-la-Porte",
               "Vin de Savoie Chautagne", "Vin de Savoie Chignin", "Vin de Savoie Chignin-Bergeron",
               "Vin de Savoie Crépy"]

SAVOIE_V = """1°- Encépagement

Les vins sont issus des cépages suivants :

 APPELLATION D’ORIGINE CONTRÔLÉE,
    INDICATION, DENOMINATIONS
                                                                    ENCÉPAGEMENT
 GEOGRAPHIQUES COMPLEMENTAIRES,
     COULEUR ET TYPE DES VINS
                                                - cépage principal : jacquère B ;
                                                - cépages accessoires : aligoté B, altesse B,
                                                chardonnay B, velteliner rouge
                                                précoce Rs, les variétés suivantes bia B, mondeuse
  Dénominations géographiques
                                                grise G, petite sainte-Marie B, pinot gris G, sous
  complémentaires « Apremont », « Cruet »,
                                                réserve de la signature entre l’INAO, l’ODG,
  « Montmélian », « Saint-Jeoire-Prieuré »
                                                l’opérateur habilité concerné et l’opérateur-
                                                vinificateur d’une convention conforme à la
                                                convention cadre approuvée par le comité national
                                                compétent le 11 février 2021
  Dénominations géographiques
  complémentaires « Arbin », « Saint-Jean-de-   mondeuse N exclusivement
  la-Porte »

      Dénominations géographiques complémentaires « Chautagne », « Chignin », « Jongieux »

                                                  - cépage principal : jacquère B ;
  Vins blancs tranquilles                         - cépages accessoires : aligoté B, altesse B
                                                  - cépages principaux : gamay N, mondeuse N,
  Vins rouges tranquilles                         pinot N;
  Dénomination géographique complémentaire
                                                   roussanne B exclusivement
  « Chignin-Bergeron »
                                                   - cépage principal : chasselas B ;
  Dénominations géographiques                      - cépages accessoires : aligoté B, gringet B
  complémentaires « Crépy », « Marignan »
"""


def savoie_keys(name):
    return dgc_keys(name, SAVOIE)


def savoie_covered():
    return set().union(*(savoie_keys(n) for n in SAVOIE_DGCS)) | {"vin de savoie", "savoie"}


def roles(text):
    g = parse_grapes(strip_names(text))
    return {k: {t["slug"] for t in g[k]} for k in ("principal", "accessory")}


def test_a_label_wrapped_around_the_rows_keeps_the_wrapped_grape_whole():
    # "mondeuse / grise G" with the label's line between its halves
    got = roles(dgc_text(SAVOIE_V, savoie_keys("Vin de Savoie Apremont"), savoie_covered()))
    assert got["principal"] == {"jacquere"}
    assert {"mondeuse-grise", "bia", "petite-sainte-marie", "pinot-gris"} <= got["accessory"]


def test_a_quoted_name_wrapping_around_the_value_cell_still_names_the_row():
    for name in ("Vin de Savoie Arbin", "Vin de Savoie Saint-Jean-de-la-Porte"):
        assert slugs(dgc_text(SAVOIE_V, savoie_keys(name), savoie_covered())) == {"mondeuse"}


def test_a_heading_scope_ends_at_the_next_dgc_row():
    got = slugs(dgc_text(SAVOIE_V, savoie_keys("Vin de Savoie Chautagne"), savoie_covered()))
    assert got == {"jacquere", "aligote", "altesse", "gamay", "mondeuse"}
    assert slugs(dgc_text(SAVOIE_V, savoie_keys("Vin de Savoie Chignin-Bergeron"), savoie_covered())) == {"roussanne"}
    assert slugs(dgc_text(SAVOIE_V, savoie_keys("Vin de Savoie Crépy"), savoie_covered())) == {
        "chasselas", "aligote", "gringet"}


# ---- Meursault (BO Agri, 11 juin 2026): a colour row per premier-cru climat

MEURSAULT = "Meursault"
MEURSAULT_III = """APPELLATION D’ORIGINE CONTRÔLÉE,
                                                                          COULEUR ET TYPE DE
       MENTION, NOM DE CLIMAT, DENOMINATION
                                                                               PRODUIT
          GEOGRAPHIQUE COMPLEMENTAIRE
AOC « Meursault »                                                      Vins tranquilles blancs ou rouges

AOC « Meursault » complétée par la mention « premier cru »              Vins tranquilles blancs ou rouges


                                    « Blagny »                          Vins tranquilles blancs
                                    « Charmes »                         Vins tranquilles blancs ou rouges
                                    « La Jeunellotte »                  Vins tranquilles blancs
                                    « Les Santenots du Milieu »         Vins tranquilles blancs
                                    « Perrières »                       Vins tranquilles blancs ou rouges

Dénomination géographique complémentaire « Côte de Beaune »             Vins tranquilles rouges
"""
MEURSAULT_DGCS = [
    "Meursault premier cru", "Meursault premier cru Blagny", "Meursault premier cru Charmes",
    "Meursault premier cru La Jeunellotte", "Meursault premier cru Les Santenots du Milieu",
    "Meursault premier cru Perrières", "Meursault ou Meursault Côte de Beaune",
]


def _meursault_colours(name: str) -> set[str]:
    parent_keys = {"meursault"}
    covered = set().union(*(dgc_keys(n, MEURSAULT) for n in MEURSAULT_DGCS)) | parent_keys
    want = dgc_keys(name, MEURSAULT) - parent_keys  # as stage 02 builds it
    text = dgc_text(MEURSAULT_III, want, covered, RESERVATION)
    return colours(text) if text is not None else set()


def test_a_premier_cru_climat_matches_its_row_by_the_climat_name():
    # visitor flags on Meursault 2026-11-22 (card validator): every climat
    # had shown red and white; ten are white only
    assert "la jeunellotte" in dgc_keys("Meursault premier cru La Jeunellotte", MEURSAULT)
    assert _meursault_colours("Meursault premier cru La Jeunellotte") == {"white"}
    assert _meursault_colours("Meursault premier cru Les Santenots du Milieu") == {"white"}
    assert _meursault_colours("Meursault premier cru Charmes") == {"white", "red"}


def test_an_alias_equal_to_the_parent_name_does_not_take_the_parents_row():
    assert _meursault_colours("Meursault ou Meursault Côte de Beaune") == {"red"}
