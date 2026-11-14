"""The class model and the register index of the drinks pipeline: which
register rows are drinks of the corpus, which pipeline owns them, how they
are named and classed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import product_class as pc  # noqa: E402
from _lib import style_taxonomy  # noqa: E402
from _lib.drinks import index as ix  # noqa: E402


def _row(**kw):
    base = {"status": "Registered", "qualityProductType": "Spirit drink", "productCategory": "9. Fruit spirit",
            "fileName": "PGI-HU-01234", "countryId": "HU", "protectedName": "Szatmári szilvapálinka",
            "geographicalIndicatorTypeCode": "PGI", "id": 1}
    return {**base, **kw}


def test_spirit_category_reads_the_annex_number() -> None:
    assert pc.spirit_category("4. Wine spirit") == "wine-spirit"
    assert pc.spirit_category("6. Grape marc spirit or grape marc") == "grape-marc"
    assert pc.spirit_category("29. Distilled anis") == "aniseed"
    # the first category named decides; an unlisted number is the residual
    assert pc.spirit_category("15. Vodka, 31. Flavoured vodka") == "other-spirit"
    assert pc.spirit_category("") == "other-spirit"


def test_every_drink_category_is_a_style_leaf() -> None:
    under_drinks = style_taxonomy.descendants(style_taxonomy.DRINKS_BUCKET, include_self=False)
    for cat in pc.DRINK_CATEGORIES:
        assert cat in under_drinks, cat


def test_register_row_classes() -> None:
    assert pc.classify_register_row(_row()) == ("spirit", "fruit-spirit")
    wine = _row(qualityProductType="Wine", productCategory="1. Wine")
    assert pc.classify_register_row(wine) == ("", "")
    aromatised = _row(qualityProductType="Aromatised wine", productCategory="Class 2.21. Aromatised wines")
    assert pc.classify_register_row(aromatised) == ("aromatised-wine", "aromatised-wine")
    cider = _row(qualityProductType="Food", productCategory="Class 1.8. Other products", fileName="PDO-ES-0260")
    assert pc.classify_register_row(cider) == ("", "")  # a Food row is a drink only by the checked-in list
    assert pc.classify_register_row(cider, {"PDO-ES-0260"}) == ("cider", "cider")


def test_a_record_without_the_field_is_a_wine() -> None:
    assert pc.product_class({"country": "it", "kind": "DOP"}) == "wine"
    assert pc.is_wine({"country": "it", "kind": "DOP"})
    assert pc.product_class({"product_class": "spirit", "drink_category": "rum"}) == "spirit"
    assert not pc.is_wine({"product_class": "cider"})


def test_owner_is_the_first_corpus_country_of_the_file_number() -> None:
    row = _row(fileName="PGI-NL+BE+DE-01994", countryId="BE,DE,NL")
    assert ix.owner_and_aliases(row) == ("nl", ["be", "de"])
    assert ix.owner_and_aliases(_row(fileName="PGI-US-0001", countryId="US")) == ("", [])


def test_naming_keeps_the_regulators_string_and_its_latin_form() -> None:
    names = ix.naming("Ούζο Μυτιλήνης / Ouzo of Mitilene")
    assert names["name"] == "Ούζο Μυτιλήνης" and names["name_latin"] == "Ouzo of Mitilene"
    assert ix.record_slug(names) == "ouzo-of-mitilene"
    names = ix.naming("Korn / Kornbrand")
    assert names["name"] == "Korn" and names["name_latin"] == "" and names["name_aliases"] == ["Kornbrand"]
    assert ix.record_slug(names) == "korn"


def test_kind_tokens() -> None:
    assert ix.kind_for("spirit", "PGI") == "EDV"
    assert ix.kind_for("cider", "PDO") == "DOP"
    assert ix.kind_for("aromatised-wine", "PGI") == "IGP"


def test_select_leaves_french_and_uk_rows_to_their_pipelines() -> None:
    rows = [
        _row(),
        _row(fileName="PGI-FR-02028", countryId="FR", protectedName="Genièvre Flandre Artois"),
        _row(fileName="PGI-GB-01854", countryId="GB", protectedName="Scotch Whisky"),
        _row(fileName="PGI-FR+IT-01909", countryId="fr,it", protectedName="Génépi des Alpes / Genepì delle Alpi"),
        _row(status="Applied", fileName="PGI-HU-09999"),
        _row(qualityProductType="Wine", productCategory="1. Wine", fileName="PDO-HU-A1234"),
    ]
    rows.append(_row(fileName="PGI-BE+NL+FR+DE-01962", countryId="be,nl,fr,de",
                     protectedName="Genièvre / Jenever / Genever", productCategory="19. Juniper-flavoured spirit drink"))
    entries, skipped = ix.select(
        rows, cider_file_numbers=set(),
        fr_owned_file_numbers={"PGI-FR+IT-01909", "PGI-BE+NL+FR+DE-01962"},
    )
    # a shared GI France filed stays French; one another state filed is a
    # drinks record with France among its aliases, whatever INAO lists
    assert [e["file_number"] for e in entries] == ["PGI-BE+NL+FR+DE-01962", "PGI-HU-01234"]
    assert entries[0]["country"] == "be" and entries[0]["country_aliases"] == ["nl", "fr", "de"]
    assert entries[1]["kind"] == "EDV" and entries[1]["drink_category"] == "fruit-spirit"
    assert {s["file_number"]: s["reason"] for s in skipped} == {
        "PGI-FR-02028": "fr-siqo", "PGI-GB-01854": "uk-register", "PGI-FR+IT-01909": "fr-siqo",
    }


def test_cider_table_is_cited() -> None:
    table = ix.load_cider_gis()
    assert table, "empty cider table"
    for file_number, entry in table.items():
        assert file_number.startswith(("PDO-", "PGI-")), file_number
        assert entry.get("register_name") and entry.get("verified"), file_number


# --- the United Kingdom's register ----------------------------------------------

from _lib.drinks import uk_register as uk  # noqa: E402


def test_uk_category_is_read_by_its_words() -> None:
    # the UK keeps the numbering of Reg. 110/2008: "32" is liqueur there
    assert uk.category_of(["2-whisky-or-whiskey"]) == "whisky"
    assert uk.category_of(["10-cider-spirit-and-perry-spirit"]) == "cider-spirit"
    assert uk.category_of(["32-liqueur"]) == "liqueur"
    assert uk.category_of(["47-other-spirit-drinks"]) == "other-spirit"
    assert uk.category_of(None) == "other-spirit"


def test_uk_titles_split_on_any_slash() -> None:
    names = uk.naming("English Whisky/ English Whiskey")
    assert names["name"] == "English Whisky" and names["name_aliases"] == ["English Whiskey"]
    names = uk.naming("Single Malt Welsh Whisky/Wisgi Cymreig Brag  Sengl")
    assert names["name_aliases"] == ["Wisgi Cymreig Brag Sengl"]
    assert ix.record_slug(uk.naming("Irish Whiskey / Uisce Beatha Eireannach / Irish Whisky")) == "irish-whiskey"


def test_uk_specification_attachment_is_not_a_translation_or_a_notice() -> None:
    def att(url, title=""):
        return {"content_type": "application/pdf", "url": url, "title": title}

    content = {"details": {"attachments": [
        att("https://x/English_Whisky_Decision_Notice.pdf", "English Whisky Decision Notice"),
        att("https://x/English_Whisky_Product_Specification.pdf", "English Whisky Product Specification"),
    ]}}
    assert uk.spec_attachment(content)["url"].endswith("Product_Specification.pdf")
    # a Welsh product's own specification is kept; its Welsh translation is not
    content = {"details": {"attachments": [
        att("https://x/Single_Malt_Welsh_Whisky_UK_GI_product_specification_S0006_final_version-Welsh.pdf"),
        att("https://x/Welsh_Cider_PGI_product_specification_Welsh_translation.pdf"),
        att("https://x/protected-food-name-welsh-cider.pdf", "Traditional Welsh Cider product specification"),
    ]}}
    assert uk.spec_attachment(content)["url"].endswith("protected-food-name-welsh-cider.pdf")
    assert uk.spec_attachment({"details": {"attachments": []}}) is None


def test_uk_names_take_the_eu_file_number_where_the_eu_lists_them() -> None:
    rows = [{"countryId": "gb", "protectedName": "Scotch Whisky", "fileName": "PGI-GB-01854"},
            {"countryId": "ie,uk(ni)", "protectedName": "Irish Poteen / Irish Poitín", "fileName": "PGI-IE+UK(NI)-02080"},
            {"countryId": "fr", "protectedName": "Whisky breton", "fileName": "PGI-FR-01959"}]
    numbers = uk.eu_file_numbers(rows)
    assert numbers["scotch whisky"] == "PGI-GB-01854" and numbers["irish poitin"] == "PGI-IE+UK(NI)-02080"
    assert "whisky breton" not in numbers
