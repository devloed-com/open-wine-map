"""Search-only romanisations of Greek / Cyrillic names (scripts/_lib/romanise.py)."""

from __future__ import annotations

import pytest
from _lib.romanise import (
    bg_streamlined,
    elot743,
    fold_confusables,
    latin_form_bg,
    search_forms,
    search_key,
)


@pytest.mark.parametrize(
    ("greek", "latin"),
    [
        ("Άγιο Όρος", "Agio Oros"),
        ("Ήπειρος", "Ipeiros"),
        ("Αμύνταιο", "Amyntaio"),
        ("Χανιά", "Chania"),
        ("Εύβοια", "Evvoia"),
        ("Παγγαίο", "Pangaio"),
        ("Κέρκυρα", "Kerkyra"),
        ("Νάουσα", "Naousa"),
        ("Αργολίδα", "Argolida"),
        ("Ρομπόλα Κεφαλληνίας", "Rompola Kefallinias"),
        ("Μπατίκι", "Batiki"),
        ("Αυλώνα", "Avlona"),
        ("Ευρώπη", "Evropi"),
        ("Λευκωσία", "Lefkosia"),
        ("Πάφος", "Pafos"),
        ("Malvasia Χάνδακας-Candia", "Malvasia Chandakas-Candia"),
        ("Άγχιαλος", "Anchialos"),
        ("Σαντορίνη", "Santorini"),
    ],
)
def test_elot743_pinned_names(greek, latin):
    assert elot743(greek) == latin


def test_elot743_keeps_source_casing():
    assert elot743("ΧΑΝΙΑ") == "CHANIA"
    assert elot743("ΛΕΜΕΣΟΥ") == "LEMESOU"
    assert elot743("Ούζο") == "Ouzo"
    assert elot743("ΜΠΑΤΙΚΙ") == "BATIKI"
    assert elot743("Θήρα") == "Thira"


def test_elot743_dialytika_vowels_map_like_plain_ones():
    assert elot743("Καΐκι") == "Kaiki"
    assert elot743("Καϋμένος") == "Kaymenos"
    assert elot743("ϊ ϋ") == "i y"


def test_elot743_passes_latin_through_untouched():
    assert elot743("Côtes du Rhône 2024") == "Côtes du Rhône 2024"
    assert elot743("") == ""


def test_elot743_diphthong_before_voiceless_consonant_and_at_word_end():
    assert elot743("Ναύπλιο") == "Nafplio"
    assert elot743("Ευαγγελία") == "Evangelia"
    assert elot743("ταυ") == "taf"


@pytest.mark.parametrize(
    ("cyrillic", "latin"),
    [
        ("Търговище", "Targovishte"),
        ("Ямбол", "Yambol"),
        ("Хърсово", "Harsovo"),
        ("Тракийска низина", "Trakiyska nizina"),
        ("Свищов", "Svishtov"),
        ("Любимец", "Lyubimets"),
        ("Оряховица", "Oryahovitsa"),
        ("Ивайловград", "Ivaylovgrad"),
        ("Южно Черноморие", "Yuzhno Chernomorie"),
        ("София", "Sofia"),
        ("България", "Bulgaria"),
        ("Мелник", "Melnik"),
    ],
)
def test_bg_streamlined_pinned_names(cyrillic, latin):
    assert bg_streamlined(cyrillic) == latin


def test_bg_streamlined_casing_and_passthrough():
    assert bg_streamlined("СОФИЯ") == "SOFIA"
    assert bg_streamlined("БЪЛГАРИЯ") == "BULGARIA"
    assert bg_streamlined("Южно") == "Yuzhno"
    assert bg_streamlined("ЮЖНО") == "YUZHNO"
    assert bg_streamlined("Melnik 55") == "Melnik 55"
    assert bg_streamlined("Мелник 55") == "Melnik 55"


def test_bg_word_final_ia_only_at_the_end_of_a_word():
    assert bg_streamlined("Мария") == "Maria"
    assert bg_streamlined("Марияна") == "Mariyana"


def test_bg_short_i_survives_normalisation():
    assert bg_streamlined("й") == "y"
    assert bg_streamlined("й") == "y"
    assert bg_streamlined("ѝ") == "i"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Αrgolida", "Argolida"),
        ("Άγιο Όρος", "Άγιο Όρος"),
        ("Malvasia Χάνδακας-Candia", "Malvasia Χάνδακας-Candia"),
        ("Ayio Oros", "Ayio Oros"),
        ("Меlnik", "Melnik"),
        ("Мелник", "Мелник"),
        ("", ""),
    ],
)
def test_fold_confusables(text, expected):
    assert fold_confusables(text) == expected


def test_search_key_mirrors_the_js_normaliser():
    assert search_key("Aloxe-Corton") == "aloxe corton"
    assert search_key("Άγιο Όρος") == "αγιο ορος"
    assert search_key("  Côtes  du Rhône ") == "cotes du rhone"
    assert search_key("") == ""


def test_search_forms_gr_elot_and_unidecode_coincide():
    assert search_forms("Άγιο Όρος", "Ayio Oros", "gr") == ["Agio Oros"]


def test_search_forms_gr_both_forms_differ_from_the_register():
    assert search_forms("Ήπειρος", "Ipiros", "gr") == ["Ipeiros", "Epeiros"]


def test_search_forms_gr_confusable_register_form_covers_both():
    assert search_forms("Αργολίδα", "Αrgolida", "gr") == []


def test_search_forms_cy_uses_the_greek_rules():
    assert search_forms("Πάφος", "Pafos", "cy") == ["Paphos"]
    assert search_forms("Λευκωσία", "Lefkosia", "cy") == ["Leukosia"]
    assert search_forms("Λάρνακα", "Larnaka", "cy") == []


def test_search_forms_bg_keeps_the_old_unidecode_spelling():
    assert search_forms("Търговище", "Targovishte", "bg") == ["T'rgovishche"]
    assert search_forms("Търговище", "T'rgovishche", "bg") == ["Targovishte"]


def test_search_forms_other_countries_and_empty_input():
    assert search_forms("Bourgogne", "", "fr") == []
    assert search_forms("", "", "gr") == []


def test_latin_form_bg():
    assert latin_form_bg("Търговище") == "Targovishte"
    assert latin_form_bg("София") == "Sofia"
    assert latin_form_bg("Melnik") == ""
    assert latin_form_bg("") == ""


def test_word_final_mp_is_b() -> None:
    assert elot743("Τζαμπ") == "Tzab"
    assert elot743("Μπατίκι") == "Batiki"
    assert elot743("Ρομπόλα") == "Rompola"


def test_fold_confusables_isolates_a_native_word_behind_a_slash() -> None:
    assert fold_confusables("Asti/ΑΤΗΝΑ") == "Asti/ΑΤΗΝΑ"
    assert fold_confusables("Kos,ΤΟΚΟ") == "Kos,ΤΟΚΟ"
    assert fold_confusables("Αrgolida") == "Argolida"


def test_search_key_deletes_spacing_diacritics_like_js() -> None:
    assert search_key("dʼAlba") == "dalba"
    assert search_key("l´Empordà") == "lemporda"
    assert search_key("col·lecció") == "colleccio"
    assert search_key("Aloxe-Corton") == "aloxe corton"
