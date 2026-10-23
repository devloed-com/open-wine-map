"""Regression tests for the roster and style fixes of 2026-10-23 (validator
findings, phase B): the HU wrapped-name join, the NL / BE rosé rule, the BE
monotonic slicer, the RO yield-table accessories, the BG header strip, the SK
roster-cell colour word, the FR colour-qualified muscat entries, the IT
Article 1 varietal types and the matcher helpers behind them."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.grape_entity import (  # noqa: E402
    exact_match,
    match_roster_cell,
    match_variety,
    set_pliego_context,
)
from _lib.grape_lexicon import parse_grapes as fr_parse_grapes  # noqa: E402
from _lib.hu.termekleiras import parse_grapes as hu_parse_grapes  # noqa: E402
from _lib.it.masaf import article1_varietal_types  # noqa: E402
from _lib.sk.specifikacija import _parse_grapes as sk_parse_grapes  # noqa: E402

nl02 = importlib.import_module("nl.02_extract_pliegos")
be02 = importlib.import_module("be.02_extract_pliegos")
ro02 = importlib.import_module("ro.02_extract_pliegos")
bg02 = importlib.import_module("bg.02_extract_pliegos")


# ---- the matcher helpers ----------------------------------------------------

def test_exact_match_is_silent_and_exact_only():
    assert exact_match("Irsai Olivér").slug == "irsai-oliver"
    assert exact_match("Viognier Alibernet") is None
    # a fuzzy-only surface never passes
    assert match_variety("Mourverdre") is not None
    assert exact_match("Mourverdre") is None


def test_a_colour_word_cultivar_binds_only_as_a_roster_cell():
    assert match_variety("Rosa") is None
    cell = match_roster_cell("Rosa")
    assert cell is not None and cell.slug == "rosa" and cell.method == "exact-roster-cell"
    assert match_roster_cell("Chardonnay").slug == "chardonnay"


def test_a_colour_coded_muscat_takes_its_colours_passport():
    white = match_variety("muscat à petits grains B")
    red = match_variety("muscat à petits grains Rg")
    pink = match_variety("muscat à petits grains Rs")
    assert white.slug == "muscat-a-petits-grains"
    assert red.slug == "muscat-a-petits-grains-rouges" and red.name.endswith("rouges")
    assert pink.slug == "muscat-a-petits-grains-roses" and pink.name.endswith("roses")


def test_fr_reader_emits_one_pill_per_colour_coded_muscat_entry():
    section = (
        "1°- Encépagement\n"
        "Cépages principaux : muscat à petits grains B, muscat à petits grains Rg, "
        "muscat à petits grains Rs, viognier B.\n"
        "2°- Règles de proportion à l'exploitation\n"
    )
    out = fr_parse_grapes(section)
    slugs = {g["slug"]: g for g in out["principal"]}
    assert {"muscat-a-petits-grains", "muscat-a-petits-grains-rouges",
            "muscat-a-petits-grains-roses", "viognier"} <= set(slugs)
    assert slugs["muscat-a-petits-grains-rouges"]["name"] == "muscat à petits grains rouges"
    assert slugs["muscat-a-petits-grains"]["name"] == "muscat à petits grains"


# ---- HU: names wrapped across the PDF's lines -------------------------------

HU_TABLE = """   bortípus   engedélyezett fajták
              Bacchus, Chardonnay, Furmint, Hárslevelű, Irsai
              Olivér, Juhfark, Kéknyelű, Olasz
1. fehér      rizling, Rajnai rizling, Sárga
              muskotály, Zöld veltelíni, Viognier
              Alibernet, Cabernet
              franc, Kékfrankos, Merlot, Pinot
2. rozé
              noir, Zweigelt, Hamburgi
              muskotály, Tannat
"""


def test_hu_wrapped_names_are_joined_and_type_labels_skipped():
    names = [d["name"] for d in hu_parse_grapes(HU_TABLE)["details"]]
    for joined in ("Irsai Olivér", "Olasz rizling", "Rajnai rizling", "Sárga muskotály",
                   "Zöld veltelíni", "Cabernet franc", "Pinot noir", "Hamburgi muskotály"):
        assert joined in names, (joined, names)
    assert "Viognier" in names and "Alibernet" in names and "Tannat" in names
    assert "Kéknyelű" in names
    for half in ("Irsai", "Olivér", "franc", "noir", "muskotály", "rizling"):
        assert half not in names
    slugs = [d["slug"] for d in hu_parse_grapes(HU_TABLE)["details"]]
    assert "plavaie" not in slugs and "keknyelu" in slugs


# ---- NL / BE: rosé comes from the text, never from a berry ------------------

def test_nl_rose_from_the_text_not_the_berry():
    sections = {"4": "Wijncategorie 1 wijn: rosé, volfruitig", "5": "Koude fermentatie"}
    titles = {"4": "Beschrijving van de wijn(en)", "5": "Wijnbereidingsprocedés"}
    gris = [{"slug": "pinot-gris", "colour": "gris"}, {"slug": "regent", "colour": "noir"}]
    assert "rose" in nl02.parse_styles(sections, titles, grape_details=gris)
    assert nl02.parse_styles({"4": "Wijncategorie 1 wijn: wit"}, titles, grape_details=gris) == [
        "blanc", "noir",
    ]


def test_nl_reads_the_compound_rose_words_and_the_section_titles():
    sections = {"5": "WIJNCATEGORIE: 1. Wijn, wijntype: roséwijn", "11": "Koude maceratie"}
    titles = {"5": "Wijnbereidingsprocedés", "11": "WIJNCATEGORIE 9: Parelwijn waaraan"}
    styles = nl02.parse_styles(sections, titles, grape_details=[])
    assert "rose" in styles and "semi-sparkling" in styles


def test_be_rose_bare_word_in_both_languages():
    nl_sections = {"4": "Kleur : wit, rosé en van robijnrood tot …"}
    assert "rose" in be02.parse_styles(nl_sections, {"4": "Beschrijving van de wijn(en)"}, "nl")
    fr_sections = {"3": "Les vins sont des vins blancs, rouges ou rosés."}
    assert "rose" in be02.parse_styles(fr_sections, {"3": "DESCRIPTION DU OU DES VINS"}, "fr")
    assert "rose" not in be02.parse_styles(
        {"3": "vins blancs"}, {"3": "DESCRIPTION DU OU DES VINS"}, "fr",
        grape_details=[{"slug": "siegerrebe", "colour": "rose"}],
    )


def _p(num: str, title: str) -> str:
    return f'<p class="ti-grseq-1"><span class="bold">{num}. {title}</span></p>'


def test_be_slicer_keeps_the_real_sections_over_nested_restarts():
    html = (
        _p("1", "Naam/namen") + "Hagelandse wijn"
        + _p("2", "Type geografische aanduiding") + "BOB"
        + _p("3", "Categorieën van wijnbouwproducten") + "1. Wijn"
        + _p("4", "Beschrijving van de wijn(en)") + "intro"
        + _p("1", "auxerrois, bacchus, cabernet cortis") + "Witte wijnen: fris. Rosé-wijnen: fijn."
        + _p("2", "acolon, cabernet dorsa") + "Rode wijnen: fruitig."
        + _p("5", "Wijnbereidingsprocedés") + "proc"
        + _p("5.2", "Maximumopbrengsten") + "yields"
        + _p("1", "Een gemiddelde maximum gemeten over een periode van 3 jaar, voor witte wijnen voor: a") + "60"
        + _p("2", "Een gemiddelde maximum gemeten over een periode van 3 jaar, voor rode wijnen voor: b") + "55"
        + _p("6", "Afgebakend geografisch gebied") + "area"
        + _p("7", "Wijndruivenras(sen)") + "auxerrois B"
    )
    sections, titles = be02.extract_sections(html)
    assert titles["1"] == "Naam/namen" and titles["3"].startswith("Categorieën")
    assert "Rosé-wijnen" in sections["4"] and "Rode wijnen" in sections["4"]
    assert titles["6"].startswith("Afgebakend") and titles["7"].startswith("Wijndruivenras")
    assert "60" in sections["5.2"]


# ---- RO: the yield table names varieties section 7 does not ---------------

def test_ro_yield_table_varieties_become_accessories():
    grapes = ro02.parse_grapes("Fetească albă B\nCabernet Sauvignon N")
    sections = {
        "5.2": "1.\nMerlot, Băbească Neagră, Burgund Mare\n17\xa0000 kilograme de struguri pe hectar\n"
               "2.\nla maturitate deplină a recoltei, soiurile Pinot gris, Fetească albă\n"
               "15\xa0000 kilograme de struguri pe hectar",
    }
    titles = {"5.2": "Producții maxime"}
    added = ro02.add_yield_table_varieties(grapes, sections, titles)
    assert set(added) == {"merlot", "babeasca-neagra", "blaufrankisch", "pinot-gris"}
    assert set(grapes["accessory"]) == set(added)
    assert "feteasca-alba" in grapes["principal"] and "feteasca-alba" not in grapes["accessory"]
    assert all(d["source"] == "yield-table" for d in grapes["details"] if d["role"] == "accessory")


# ---- BG: a column header glued to a name keeps the name --------------------

def test_bg_header_phrase_glued_to_a_name_keeps_the_name():
    out = bg02.parse_grapes("Алиготе\nСорт грозде Viognier\nСортове грозде\nГаме ноар")
    slugs = out["principal"]
    assert "viognier" in slugs and "aligote" in slugs
    assert len(slugs) == 3


# ---- SK: the Odroda cell "Rosa" --------------------------------------------

def test_sk_odroda_cell_rosa_binds_the_slovak_crossing():
    body = (
        "MUŠTOVÉ Neronet\n"
        " MODRÉ Rimava\n"
        "        Rosa\n"
        "        Rudava\n"
        "        Rulandské modré             Pinot noir, Červený klevner\n"
    )
    out = sk_parse_grapes(body)
    assert "rosa" in out["principal"]
    assert [d["name"] for d in out["details"] if d["slug"] == "rosa"] == ["Rosa"]


# ---- IT: the varietal types of article 1 ----------------------------------

ART1 = """La denominazione di origine controllata «Colli Altotiberini» e' riservata ai vini bianchi, rossi e
rosato che rispondono alle condizioni ed ai requisiti stabiliti dal presente disciplinare di produzione.
Tali vini sono i seguenti:
«Colli Altotiberini» bianco ed anche nelle tipologie spumante e superiore;
«Colli Altotiberini» rosso ed anche nelle tipologie novello e riserva;
«Colli Altotiberini» Cabernet Sauvignon;
«Colli Altotiberini» Merlot riserva;
«Colli Altotiberini» Pinot;
«Friuli Latisana» Malvasia, anche nella tipologia novello;
"San Colombano al Lambro” o “San Colombano” Rosso (anche nella tipologia frizzante)
"""


def test_art1_varietal_types_read_exact_names_only():
    set_pliego_context("colli-altotiberini")
    try:
        got = {d["slug"]: d["name"] for d in article1_varietal_types(ART1, "Colli Altotiberini")}
    finally:
        set_pliego_context(None)
    assert got == {"cabernet-sauvignon": "Cabernet Sauvignon", "merlot": "Merlot"}


def test_art1_needs_a_curated_surface_not_a_legacy_synonym():
    assert article1_varietal_types("«Colli Etruschi Viterbesi» Rossetto;\n", "Colli Etruschi Viterbesi") == []


def test_art1_never_binds_the_wines_own_name():
    got = article1_varietal_types(
        '"San Colombano al Lambro” o “San Colombano” Rosso (anche nella tipologia frizzante)\n',
        "San Colombano al Lambro",
    )
    assert got == []


# ---- GR: the strict header pass, the prose enumeration and the cap -------

from _lib.gr import specifikacija as GR  # noqa: E402

MALVASIA = """1. ΟΝΟΜΑ ΠΡΟΣ ΚΑΤΑΧΩΡΗΣΗ
Malvasia Χάνδακας - Candia
2. ΠΕΡΙΓΡΑΦΗ ΤΩΝ ΟΙΝΩΝ
Ο οίνος είναι γλυκός, από λιαστά σταφύλια.
7. ΕΠΙΤΡΕΠΟΜΕΝΕΣ ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ ΑΜΠΕΛΟΥ
Ο οίνος από λιαστά σταφύλια Π.Ο.Π. Malvasia Χάνδακας-Candia παράγεται από σταφύλια των
ποικιλιών Ασύρτικο, Αθήρι, Βιδιανό, Θραψαθήρι, Λιάτικο (με λευκή οινοποίηση), Μοσχάτο
άσπρο (Μοσχάτο Σπίνας) και Malvasia di Candia aromatica. Οι ανωτέρω ποικιλίες μετέχουν
σε οποιοδήποτε ποσοστό εκτός των δύο τελευταίων οι οποίες εφόσον μετέχουν θα
καλύπτουν συνολικά ποσοστό μέχρι 15%.
8. ∆ ΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ
2. Η ποικιλία αμπέλου malvasia και ο οίνος malvasia
Το 73% των Malvasia που μελετήθηκαν είναι λευκές, αλλά υπάρχουν επίσης ερυθρές, ροζέ οίνοι.
Candia aromatica. Οι ανωτέρω ποικιλίες μετέχουν σε οποιοδήποτε ποσοστό εκτός των
"""


def test_gr_strict_pass_reads_the_padded_delta_header_and_the_cap_clause():
    sections, titles = GR.extract_sections(MALVASIA, strict=True)
    assert titles["link_to_terroir"].startswith("ΔΕΣΜΟΣ")
    assert titles["grape_varieties"].startswith("ΕΠΙΤΡΕΠΟΜΕΝΕΣ")
    lenient, _lt = GR.extract_sections(MALVASIA, strict=False)
    assert "link_to_terroir" not in lenient  # the padded Delta hides it from the old reading
    grapes = GR.parse_grape_list(sections["grape_varieties"], "malvasia-handakas-candia")
    got = [(d["slug"], d["role"]) for d in grapes["details"]]
    assert got[:5] == [("assyrtiko", "principal"), ("athiri", "principal"), ("vidiano", "principal"),
                       ("thrapsathiri", "principal"), ("liatiko", "principal")]
    assert got[5:] == [("muscat-a-petits-grains", "accessory"),
                       ("malvasia-di-candia-aromatica", "accessory")]
    # the narrative's "ερυθρές, ροζέ οίνοι" stays in the link body, not the styles
    assert "ερυθρές" in sections["link_to_terroir"]
    assert GR.parse_styles(sections) == ["blanc"]


RODOS = """6. ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ ΑΜΠΕΛΟΥ
Ο οίνος λευκός Π.Ο.Π. Ρόδος (Rhodes) παράγεται από νωπά σταφύλια της ποικιλίας
Αθήρι σε ποσοστό τουλάχιστον 70% και των ποικιλιών Μαλαγουζιά και Ασύρτικο κατά το
υπόλοιπο ποσοστό.
Ο οίνος ερυθρός Π.Ο.Π. Ρόδος (Rhodes) παράγεται από νωπά σταφύλια της ποικιλίας
Μανδηλαριά σε ποσοστό τουλάχιστον 70%.
7. ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ
Ιστορικός δεσμός.
"""


def test_gr_thin_prose_section_keeps_the_capitalised_scan():
    _sections, _titles, grapes = GR.read_sections_and_grapes(RODOS, "rodos", frozenset({GR.greek_norm("Ρόδος")}))
    slugs = {d["slug"] for d in grapes["details"]}
    assert {"athiri", "malagousia", "assyrtiko", "mandilaria"} <= slugs


def test_gr_colour_form_counts_only_beside_a_wine_word():
    assert GR.parse_styles({"description": "Οι ερυθροί οίνοι χαρακτηρίζονται από …"}) == ["noir"]
    assert GR.parse_styles({"description": "για λευκούς και ερυθρωπούς οίνους."}) == ["blanc", "rose"]
    assert GR.parse_styles({"description": "Σε ερυθρούς οίνους εσοδείας 2006"}) == ["noir"]
    # the hue of an aged red, and a place name
    assert GR.parse_styles({"description": "παρατηρούνται ερυθρωπές και έπειτα ιώδεις αποχρώσεις"}) == []
    assert GR.parse_styles({"description": "ο νομός Λευκάδας και η Λευκωσία"}) == []
