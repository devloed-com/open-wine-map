"""The earned `interactions` rule (scripts/_lib/terroir_interactions.py)."""
from __future__ import annotations

import pytest
from _lib.terroir_interactions import (
    CONNECTIVES,
    earn_interactions,
    has_connective,
    quote_has_connective,
    unearned_indices,
)


@pytest.mark.parametrize(
    "lang,text",
    [
        ("fr", "Les sols argilo-calcaires confèrent aux vins une belle structure tannique."),
        ("fr", "Grâce à l'exposition sud, les raisins mûrissent tôt."),
        ("it", "L'escursione termica determina un'elevata concentrazione aromatica."),
        ("es", "Debido a la altitud, los vinos conservan la acidez."),
        ("de", "Die Schieferböden speichern die Wärme, wodurch die Trauben voll ausreifen."),
        ("nl", "Dankzij de zuidhelling rijpen de druiven vroeg."),
        ("en", "The chalk soils give the wines their freshness."),
        ("el", "Λόγω των μελτεμιών το κλίμα είναι ξηρό."),
        ("bg", "Благодарение на почвите виното е плътно."),
        ("hu", "A lösztalajnak köszönhetően a borok testesek."),
        ("cs", "Díky spraši jsou vína plná."),
        ("sk", "Vďaka sprašiam sú vína plné."),
        ("sl", "Zaradi apnenca so vina mineralna."),
        ("hr", "Zahvaljujući buri grožđe je zdravo."),
        ("ro", "Datorită solurilor calcaroase vinurile sunt minerale."),
        ("mt", "Thanks to the sea breeze the grapes ripen slowly."),   # mt → en
        ("gr", "Το ηφαιστειακό έδαφος προσδίδει ορυκτότητα."),         # gr → el
    ],
)
def test_connectives_per_language(lang, text):
    assert has_connective(text, lang)


@pytest.mark.parametrize(
    "lang,text",
    [
        ("fr", "Les sols sont argilo-calcaires et les coteaux exposés au sud."),
        ("it", "Il clima è mediterraneo con estati calde e secche."),
        ("de", "Die Böden bestehen aus Schiefer und Quarzit."),
        ("en", "The vineyards lie on chalk at 200 m."),
        ("xx", "grâce à quelque chose"),        # unknown language → never earned
    ],
)
def test_no_connective(lang, text):
    assert not has_connective(text, lang)


def test_word_initial_anchoring_and_stems():
    assert not has_connective("dankbar", "fr")            # "dank" is German, not in the FR list
    assert has_connective("undankbar dank", "de")         # word-initial "dank" matches; "undankbar" alone would not
    assert not has_connective("undankbar", "de")
    assert has_connective("επιδρούν στο κλίμα", "el")     # stem


def test_every_language_table_compiles_and_is_lowercase():
    for lang, terms in CONNECTIVES.items():
        assert terms and all(t == t.lower() for t in terms), lang
        assert has_connective(f"x {terms[0]} y", lang)


def test_quote_has_connective_follows_provenance():
    f = {"provenance": "wiki", "cahier_quote": "grâce aux sols", "wiki_quote": "les sols sont calcaires"}
    assert not quote_has_connective(f, "fr")
    f["provenance"] = "cahier"
    assert quote_has_connective(f, "fr")
    f = {"provenance": "both", "cahier_quote": "sols calcaires", "wiki_quote": "ce qui explique la fraîcheur"}
    assert quote_has_connective(f, "fr")


FACTS = [
    {"bullet": "Le sol est calcaire.", "subsection": "facteurs_naturels", "provenance": "cahier",
     "cahier_quote": "le sol est calcaire"},
    {"bullet": "Le calcaire confère de la fraîcheur.", "subsection": "interactions", "provenance": "cahier",
     "cahier_quote": "le calcaire confère de la fraîcheur"},
    {"bullet": "Le climat donne de la fraîcheur aux vins.", "subsection": "interactions", "provenance": "cahier",
     "cahier_quote": "le climat est frais"},                                   # link only in the bullet
    {"bullet": "L'exposition permet une maturité précoce.", "subsection": "interactions", "provenance": "cahier",
     "cahier_quote": "l'exposition permet une maturité précoce"},
    {"bullet": "Le vent favorise la santé des raisins.", "subsection": "interactions", "provenance": "cahier",
     "cahier_quote": "le vent favorise la santé des raisins"},               # third earned one: over the cap
]


def test_earn_interactions_drops_unearned_and_caps():
    res = earn_interactions(FACTS, "fr")
    assert [f["bullet"][:12] for f in res.kept] == ["Le sol est c", "Le calcaire ", "L'exposition"]
    assert [f["bullet"][:12] for f in res.dropped] == ["Le climat do", "Le vent favo"]
    assert unearned_indices(FACTS, "fr") == [2, 4]
    assert earn_interactions(FACTS, "fr", max_interactions=3).dropped == [FACTS[2]]
