"""A table label printed inside a wrapped variety name (scripts/_lib/fr/roster_table.py).

Excerpts follow the cahiers in force (pdftotext -layout): Coteaux Varois en
Provence, Alsace (BO Agri du 15 janvier 2026).
"""
from __future__ import annotations

from _lib.fr.roster_table import repair_label_interleave
from _lib.grape_lexicon import parse_grapes

VAROIS_V = """1°- Encépagement

 Les vins sont issus des cépages suivants :

                  COULEUR DES VINS                                              CEPAGES

                                                          - cépages principaux : cinsaut N, grenache N,
                                                          mourvèdre N, syrah N ;
   Vins rouges et rosés
                                                          - cépages accessoires : cabernet-sauvignon N,
                                                          carignan N, tibouren N, caladoc N
                                                          - variétés d’intérêt à fin d’adaptation :
                                                          sciaccarello N, vidoc N sous réserve de la
                                                          signature d’une convention entre l’INAO,
                                                          l’ODG et les opérateurs habilités concernés.
                                                          clairette B, grenache blanc B, semillon B, ugni
   Vins blancs
                                                          blanc B, vermentino B.
                                                         - variétés d’intérêt à fin d’adaptation : floreal B,
                                                           marsanne B ; souvignier gris B sous réserve
                                                           de la signature d’une convention entre
                                                           l’INAO, l’ODG et les opérateurs habilités
                                                           concernés.

 2°- Règles de proportion à l’exploitation

                                                                     REGLES DE PROPORTION A
                  COULEUR DES VINS
                                                                         L’EXPLOITATION

                                                           - La proportion de cépages principaux est supérieure
   Vins rouges et rosés                                    ou égale à 80 % de l’encépagement.
"""

ALSACE_V = """1°- Règles d’encépagement

a) - Les vins sont issus des cépages suivants :

                                         « Alsace » ou « Vin d’Alsace » suivie ou non d’un nom de lieu-dit

                                                       auxerrois B, chasselas B et chasselas rose Rs,
                                                       gewurztraminer Rs, muscat ottonel B, pinot blanc B, pinot gris G,
Vins blancs                                            pinot noir N, riesling B, sylvaner B
Vins blancs à l’exception des AOC Alsace suivi d’un
nom de lieu-dit : variétés d’intérêt à fin d’adaptation
sous réserve de la signature entre l’INAO, l’ODG et Voltis B, Opalor B, Selenor B, Souvignier gris G, Johanniter
les opérateurs habilités concernés, d’une convention B, Chenin B, Vermentino B
conforme à la convention cadre approuvée par le
comité national compétent
Vins rouges                                            pinot noir N
"""


def roles(text):
    return {t["slug"]: t["role"] for t in parse_grapes(text)["all"]}


def test_a_label_line_inside_a_wrapped_name_moves_above_it():
    before, after = roles(VAROIS_V), roles(repair_label_interleave(VAROIS_V))
    assert "ugni-blanc" not in before
    assert after["ugni-blanc"] == "principal"
    assert {k: v for k, v in after.items() if k != "ugni-blanc"} == before


def test_a_label_sharing_the_line_with_the_values_is_cut_at_the_column():
    before, after = roles(ALSACE_V), roles(repair_label_interleave(ALSACE_V))
    assert "johanniter" not in before
    assert after["johanniter"] == "observation"
    assert {k: v for k, v in after.items() if k != "johanniter"} == before


def test_a_one_column_section_and_a_complete_entry_are_left_as_printed():
    prose = "a) - Les vins blancs sont issus des cépages marsanne B et roussanne B.\n"
    assert repair_label_interleave(prose) == prose
    # the previous line ends on a colour code: nothing to join
    text = VAROIS_V.replace("semillon B, ugni\n", "semillon B, ugni blanc B\n").replace(
        "blanc B, vermentino B.", "vermentino B.")
    assert repair_label_interleave(text) == text
