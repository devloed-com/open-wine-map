"""The readers of the drinks pipeline: the EU register's technical file in
its two layouts (the Commission's e-form and a member state's own document)
and the Official Journal single document of the drinks registered since.
Fixtures are synthetic files in the layouts `pdftotext -layout` and EUR-Lex
produce."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.drinks import single_document as sd  # noqa: E402
from _lib.drinks import technical_file as tf  # noqa: E402

FIX = ROOT / "tests" / "fixtures"

EFORM_LABELS = frozenset({
    "Title - Product name", "Physical, chemical and/or", "organoleptic characteristics",
    "Specific characteristics", "(compared to spirit drinks", "of the same category)",
    "Title - Type of method", "Method", "Details of the geographical",
    "area or origin relevant to the", "link", "Specific characteristics of the",
    "spirit drink attributable to", "the geographical area", "Title", "Description of the rule",
})


def _eform(labels=frozenset()):
    return tf.parse((FIX / "drinks_eform_plum_spirit.txt").read_text(encoding="utf-8"), labels)


def test_eform_sections_and_nuts_rows() -> None:
    parsed = _eform(EFORM_LABELS)
    assert parsed["layout"] == "eform"
    roles = parsed["roles"]
    assert roles["geo_area"] == (
        "The area is the whole of the province of Northshire and the municipality of Southford."
    )
    assert [r["code"] for r in parsed["geo_nuts"]] == ["ES612", "ES61", "ES6", "ES"]
    assert parsed["geo_nuts"][0]["name"] == "Cádiz"
    assert roles["method"].startswith("Double distillation The plums are picked ripe")
    # section 7 (provisions) is no role, and part II is not read
    assert "Official Gazette" not in " ".join(roles.values())
    assert "Supporting material" not in " ".join(roles.values())


def test_eform_labels_are_cut_from_the_value_cells() -> None:
    roles = _eform(EFORM_LABELS)["roles"]
    for label in ("organoleptic characteristics", "Details of the geographical", "attributable to"):
        assert label not in roles["description"] + roles["link"], label
    assert "Its almond note comes from stones left in the mash during fermentation." in roles["description"]
    assert "so the plums ripen late and sweet." in roles["link"]
    # without learnt labels a label that runs into its value stays: a few
    # words too many, never a value word too few
    loose = _eform()["roles"]
    assert "so the plums ripen late and sweet." in loose["link"]


def test_page_furniture_is_dropped() -> None:
    text = " ".join(_eform(EFORM_LABELS)["roles"].values())
    for furniture in ("Ref. Ares", "PGI-XX-02018", "Generated on", "1/3"):
        assert furniture not in text, furniture


def test_form_contents_page_is_neither_heading_nor_body() -> None:
    parsed = tf.parse((FIX / "drinks_form_anise_spirit.txt").read_text(encoding="utf-8"))
    assert parsed["layout"] == "form"
    roles = parsed["roles"]
    assert roles["geo_area"] == (
        "Harbour Anise is produced within the boundaries of the Municipality of "
        "Harbourtown of the Regional Unit of Seashire."
    )
    assert roles["description"].startswith("Harbour Anise is a colourless spirit")
    assert roles["method"].startswith("Ethyl alcohol is flavoured")
    # "Link …   6 -8" of the contents page opened nothing
    assert roles["link"].startswith("The port traded aniseed")
    assert "3-4" not in " ".join(roles.values()) and "6 -8" not in " ".join(roles.values())


def test_bracketed_cross_reference_opens_no_section() -> None:
    assert tf._is_sentence("(see the section «Link with the geographical environment or origin»).")
    assert not tf._is_sentence("(a) Link with the geographical environment")
    assert not tf._is_sentence("Link with the geographical environment or origin")
    roles = tf.parse((FIX / "drinks_form_anise_spirit.txt").read_text(encoding="utf-8"))["roles"]
    assert "copper stills since 1860" in roles["link"]


def test_heading_words_at_the_end_count_only_for_a_known_heading() -> None:
    de = "Kurzbeschreibung der Abgrenzung des geografischen Gebiets:"
    bg = "Географско указание, за което се подава заявлението (съответен географски район)"
    assert tf._heading_role(de) is None and tf._heading_role(bg) is None
    assert tf._heading_role(de, anywhere=True) == "geo_area"
    assert tf._heading_role(bg, anywhere=True) == "geo_area"
    # the link is tested before the area: "Zusammenhang mit dem geografischen Gebiet"
    assert tf._heading_role("Zusammenhang mit dem geografischen Gebiet:", anywhere=True) == "link"


def test_single_document_numbered_sections() -> None:
    html = (FIX / "drinks_single_document_cider.html").read_text(encoding="utf-8")
    parsed = sd.parse(html, "en")
    assert parsed["layout"] == "single-document"
    roles = parsed["roles"]
    assert roles["geo_area"] == "The Federal State of Hillshire."
    # a numbered step inside a section is body text, not a section
    assert "1. Pressing takes place within a day of picking." in roles["description"]
    assert roles["link"].startswith("Cider has been pressed in the hill orchards")
    assert set(parsed["section_titles"]) == {"description", "geo_area", "link"}


def test_eurlex_language_rewrite() -> None:
    url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv:OJ.C_.2019.200.01.0007.01.ENG"
    assert sd.to_language(url, "de") == (
        "https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=uriserv:OJ.C_.2019.200.01.0007.01.DEU"
    )
    assert sd.to_language("http://data.europa.eu/eli/C/2024/1234/oj", "bg") == (
        "https://eur-lex.europa.eu/eli/C/2024/1234/oj/bul"
    )


def test_a_wrapped_contents_entry_and_a_quoted_reference_open_nothing() -> None:
    """The contents page lists "Link …, with the details bearing" / "out the
    reputation of the drink   6 -8" over two lines, and the body cites the
    section in quotes: neither opens the link, which starts at its heading."""
    roles = tf.parse((FIX / "drinks_form_anise_spirit.txt").read_text(encoding="utf-8"))["roles"]
    assert roles["link"].startswith("The port traded aniseed")
    assert "below gives the history" in roles["description"]
    assert tf._is_sentence("“Link with the geographical environment or origin” below.")


def test_a_table_of_values_is_no_contents_page() -> None:
    """A parameter and a number per line is neither a contents page (no
    section heading among them) nor, inside a prose file, a two-column
    layout to re-order."""
    lines = ["Description of the spirit drink", "Alcoholic strength          40", "Sugar                        5",
             "Esters                      50", "Methanol                   400",
             *[f"The spirit is clear and bright, sentence number {i} of the description." for i in range(9)]]
    assert tf._contents_zone(lines) == set()
    assert tf._decolumn(lines) is None
    roles = tf._parse_form(lines)["roles"]
    assert " ".join(roles["description"].split()).startswith("Alcoholic strength 40 Sugar 5 Esters 50 Methanol 400")


def test_letter_spaced_and_named_headings() -> None:
    assert tf._heading_role("3. D E F I NI T I O N O F T HE GE O GR A P HI C AL A RE A C O NCE RNE D :") == "geo_area"
    assert tf._heading_role("4. T HE M E T H O D F OR O B T A I N I N G T HE S PI RI T DRI N K :") == "method"
    assert tf._heading_role("Description of Scotch Whisky") == "description"
    assert tf._heading_role("Description of the casks used by the distillers of the valley.") is None
    assert tf._heading_role("5. Production method") == "method"
    # the words inside a sentence are no heading
    assert tf._heading_role("Irish Whisky” then the production method for this whiskey must strictly adhere to") is None
    assert tf._heading_role("4.6. Link:") == "link" and tf._heading_role("4.4. Proof of origin:") == "stop"


def test_two_column_table_is_read_row_by_row() -> None:
    parsed = tf.parse((FIX / "drinks_two_column_gluhwein.txt").read_text(encoding="utf-8"))
    roles = parsed["roles"]
    assert roles["geo_area"] == "City of Oldtown Production takes place within the city."
    assert roles["link"].startswith("The link to the area relates to the special reputation.")
    assert "No 251/2014" not in roles["link"] and "Food Inspectorate" not in roles["link"]
    assert roles["description"].startswith("Colour: ruby red, clear.")
    assert "organoleptic characteristics" not in roles["description"]
    assert roles["method"].startswith("Red wine is sweetened")


def test_swiss_cahier_headings() -> None:
    assert tf._heading_role("Article 2           Aire géographique") == "geo_area"
    assert tf._heading_role("Section 2           Description du produit") == "description"
    assert tf._heading_role("3. Abschnitt           Beschreibung der Produktions- und Herstellungsmethode") == "method"
    assert tf._heading_role("8.      Typicité du produit liée au terroir") == "link"
    assert tf._heading_role("7. Geschichtliche Elemente") == "link"
    assert tf._heading_role("Section 4              Etiquetage et certification") == "stop"
