"""The class model (`scripts/_lib/product_class.py`): a record is a wine, a
spirit drink, an aromatised wine or a cider, and a drink has one category —
a leaf of the style tree's `drinks` bucket. France derives both from the SIQO
`categorie`; the EU register countries from the register's `productCategory`."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import product_class as pc  # noqa: E402
from _lib import style_taxonomy as st  # noqa: E402
from _lib.fr import siqo  # noqa: E402


def test_every_category_is_a_leaf_of_the_drinks_bucket() -> None:
    leaves = st.descendants("drinks", include_self=False)
    assert set(pc.DRINK_CATEGORIES) == leaves
    for slug in pc.DRINK_CATEGORIES:
        assert st.simple_buckets(slug) == {"drinks"}
    assert st.BUCKETS[-1] == "drinks" and st.FACET_BUCKET_ORDER[-1] == "drinks"
    assert "drinks" not in st.WINE_BUCKETS


@pytest.mark.parametrize("categorie, expected", [
    ("Vin tranquille", ("wine", "")),
    ('Vin mousseux "Crémant"', ("wine", "")),
    ("Vin de liqueur", ("wine", "")),
    ("Cidre", ("cider", "cider")),
    ("Poiré", ("cider", "cider")),
    ("Eaux-de-vie de vin", ("spirit", "wine-spirit")),
    ("Eaux-de-vie de marc de raisin", ("spirit", "grape-marc")),
    ("Eaux-de-vie de fruits", ("spirit", "fruit-spirit")),
    ("Eaux-de-vie de cidre et de poiré", ("spirit", "cider-spirit")),
    ("Rhum", ("spirit", "rum")),
    ("Whisky ou Whiskey", ("spirit", "whisky")),
    ("Liqueur", ("spirit", "liqueur")),
    ("Crème de cassis", ("spirit", "liqueur")),
    ("Boissons aromatisées baies de genévrier", ("spirit", "juniper")),
    ("Autres boissons spiritueuses", ("spirit", "other-spirit")),
    ("", ("", "")),
    ("Fromage", ("", "")),
])
def test_siqo_categorie_table(categorie: str, expected: tuple[str, str]) -> None:
    assert siqo.classify_categorie(categorie) == expected


def test_category_pins_follow_the_register_not_the_export() -> None:
    # SIQO files Genièvre Flandre-Artois under fruit spirits and Absinthe de
    # Pontarlier under liqueurs; the EU register's Annex I category decides.
    assert siqo.classify_categorie("Eaux-de-vie de fruits", "1030") == ("spirit", "juniper")
    assert siqo.classify_categorie("Liqueur", "746") == ("spirit", "other-spirit")
    # a pin never turns a wine into a drink, and only binds its own id
    assert siqo.classify_categorie("Vin tranquille", "1030") == ("wine", "")
    assert siqo.classify_categorie("Liqueur", "1148") == ("spirit", "liqueur")
    for id_app, (slug, source) in siqo.CATEGORY_PINS.items():
        assert slug in pc.DRINK_CATEGORIES, id_app
        assert "PGI-" in source, id_app


def test_the_corpus_signs_hold_the_ig_only_spirits() -> None:
    assert siqo.CORPUS_SIGNS == {"AOC", "AOP", "IGP", "IG"}
    assert siqo.is_wine_row is siqo.is_corpus_row
    row = {"secteur": "VITICOLE", "lib_etat": "Publié", "signe_fr": "", "signe_ue": "IG"}
    assert siqo.is_corpus_row(row)
    assert not siqo.is_corpus_row({**row, "secteur": "AGROALIMENTAIRE"})
    assert not siqo.is_corpus_row({**row, "signe_ue": "", "signe_fr": "LR"})


def test_record_class_reads_the_field_then_the_fr_categorie() -> None:
    # a record without the field is a wine — the wine pipelines are untouched
    assert pc.product_class({"country": "es", "kind": "DOP"}) == "wine"
    assert pc.drink_category({"country": "es", "kind": "DOP"}) == ""
    assert pc.is_wine({"country": "it"})
    # the drinks pipeline writes both
    rec = {"country": "it", "product_class": "spirit", "drink_category": "grape-marc"}
    assert (pc.product_class(rec), pc.drink_category(rec)) == ("spirit", "grape-marc")
    assert not pc.is_wine(rec)
    # an FR record of before the field: its SIQO categorie, with the manifest
    # gap filled from the `categories` list
    cognac = {"country": "fr", "categorie": "Eaux-de-vie de vin", "kind": "EDV"}
    assert (pc.product_class(cognac), pc.drink_category(cognac)) == ("spirit", "wine-spirit")
    gap = {"country": "fr", "categorie": "", "categories": ["Vin doux naturel"]}
    assert pc.product_class(gap) == "wine"
    marc = {"country": "fr", "categorie": "", "categories": [], "kind": "EDV"}
    assert (pc.product_class(marc), pc.drink_category(marc)) == ("spirit", "other-spirit")
    # nothing known at all is a wine, as before the class model
    assert pc.product_class({"country": "fr", "kind": "STUB"}) == "wine"
    assert pc.product_class({"country": "fr", "id_appellation": "1030",
                             "categorie": "Eaux-de-vie de fruits"}) == "spirit"
    assert pc.drink_category({"country": "fr", "id_appellation": "1030",
                              "categorie": "Eaux-de-vie de fruits"}) == "juniper"


@pytest.mark.parametrize("category, expected", [
    ("4. Wine spirit", "wine-spirit"),
    ("5. Brandy or Weinbrand", "brandy"),
    ("6. Grape marc spirit or grape marc", "grape-marc"),
    ("9. Fruit spirit", "fruit-spirit"),
    ("17. Geist (supplemented by the name of the fruit or the raw materials used)", "fruit-spirit"),
    ("10. Cider spirit, perry spirit and cider and perry spirit", "cider-spirit"),
    ("1. Rum", "rum"),
    ("2. Whisky or whiskey", "whisky"),
    ("3. Grain spirit", "grain-spirit"),
    ("19. Juniper-flavoured spirit drink", "juniper"),
    ("25. Aniseed-flavoured spirit drink", "aniseed"),
    ("29. Distilled anis", "aniseed"),
    ("30. Bitter-tasting spirit drink or bitter", "bitter"),
    ("33. Liqueur", "liqueur"),
    ("34. Crème de (supplemented by the name of a fruit or other raw material used)", "liqueur"),
    ("32. Sloe-aromatised spirit drink or pacharán", "liqueur"),
    ("38. Nocino or orehovec", "liqueur"),
    ("45. Spirit drinks", "other-spirit"),
    ("15. Vodka, 31. Flavoured vodka", "other-spirit"),
    ("18. Gentian", "other-spirit"),
    ("", "other-spirit"),
])
def test_register_category_to_slug(category: str, expected: str) -> None:
    assert pc.spirit_category(category) == expected


def test_register_row_classes() -> None:
    spirit = {"fileName": "PGI-ES-01878", "qualityProductType": "Spirit drink",
              "productCategory": "32. Sloe-aromatised spirit drink or pacharán"}
    assert pc.classify_register_row(spirit) == ("spirit", "liqueur")
    vermut = {"fileName": "PGI-IT-02305", "qualityProductType": "Food",
              "productCategory": "Class 2.21. Aromatised wines"}
    assert pc.classify_register_row(vermut) == ("aromatised-wine", "aromatised-wine")
    gluehwein = {"fileName": "PGI-DE-02344", "qualityProductType": "Food",
                 "productCategory": "Class 2.22. Other alcoholic beverages"}
    assert pc.classify_register_row(gluehwein) == ("aromatised-wine", "aromatised-wine")
    sidra = {"fileName": "PDO-ES-0260", "qualityProductType": "Food",
             "productCategory": "Class 1.8. Other products of Annex I of the Treaty (spices etc.)"}
    assert pc.classify_register_row(sidra) == ("", "")  # class 1.8 says nothing
    assert pc.classify_register_row(sidra, {"PDO-ES-0260"}) == ("cider", "cider")
    wine = {"fileName": "PDO-FR-A0994", "qualityProductType": "Wine", "productCategory": "Wine"}
    assert pc.classify_register_row(wine) == ("", "")


def test_a_shared_gi_another_state_filed_is_no_french_record() -> None:
    """Genièvre / Jenever / Genever is PGI-BE+NL+FR+DE-01962: the drinks
    pipeline builds it for Belgium, France is one of its aliases."""
    row = {"secteur": "VITICOLE", "lib_etat": "Publié", "signe_fr": "", "signe_ue": "IG",
           "id_appellation": "1157"}
    assert not siqo.is_corpus_row(row)
    assert siqo.is_corpus_row({**row, "id_appellation": "1030"})
    for id_app, why in siqo.DRINKS_PIPELINE_IDS.items():
        assert id_app.isdigit() and "PGI-" in why, id_app
