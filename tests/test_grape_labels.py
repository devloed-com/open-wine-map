"""Pill-label typography fold (scripts/_lib/grape_labels.py)."""
from _lib.grape_labels import (
    clean_name,
    fold_capitals,
    is_capitals,
    latin_label,
    mixed_case_spellings,
)
from unidecode import unidecode


def test_is_capitals():
    assert is_capitals("CABERNET SAUVIGNON")
    assert is_capitals("ΝΤΟΠΙΟ ΜΑΥΡΟ")
    assert not is_capitals("Merlot N")
    assert not is_capitals("PX")
    assert not is_capitals("Pinot noir")
    assert not is_capitals("")


def test_fold_restores_corpus_spelling_with_accents():
    spellings = mixed_case_spellings([
        [{"slug": "xynisteri", "name": "Ξυνιστέρι"}],
        [{"slug": "xynisteri", "name": "ΞΥΝΙΣΤΕΡΙ"}],
        [{"slug": "barbera", "name": "Barbera N."}],
    ])
    assert fold_capitals("ΞΥΝΙΣΤΕΡΙ", "xynisteri", spellings) == "Ξυνιστέρι"
    # A colour-coded spelling is never borrowed; the name is lower-cased for
    # the client's Title Case instead.
    assert fold_capitals("BARBERA", "barbera", spellings) == "barbera"


def test_fold_is_per_grape_and_leaves_mixed_case_alone():
    spellings = mixed_case_spellings([[{"slug": "roditis", "name": "Roditis"}]])
    assert fold_capitals("RODITIS", "roditis", spellings) == "Roditis"
    assert fold_capitals("RODITIS", "savatiano", spellings) == "roditis"
    assert fold_capitals("Merlot N", "merlot", spellings) == "Merlot N"


def test_greek_capitals_without_a_spelling_stay_as_written():
    # Lower-casing would lose the tonos Greek capitals omit ("σοβινιον").
    assert fold_capitals("ΣΟΒΙΝΙΟΝ", "sauvignon", {}) == "ΣΟΒΙΝΙΟΝ"
    assert fold_capitals("ΝΤΟΠΙΟ ΜΑΥΡΟ", "mavro", {}) == "ΝΤΟΠΙΟ ΜΑΥΡΟ"
    # Cyrillic carries no accents to lose.
    assert fold_capitals("МАВРУД", "mavrud", {}) == "мавруд"


def test_clean_name_strips_extraction_debris_only():
    assert clean_name("Chardonnay") == "Chardonnay"
    assert clean_name(" -Garganega") == "Garganega"
    assert clean_name("Seite 6 von 10 -7- Domina") == "Domina"
    assert clean_name("Μανδηλαριά σε") == "Μανδηλαριά"
    assert clean_name("Moscato bianco e") == "Moscato bianco"
    assert clean_name("Würzer;") == "Würzer"
    assert clean_name("Moscatel-") == "Moscatel"
    # Spellings stay: a name ending in "or", a colour code, an apostrophe.
    assert clean_name("rayon d or") == "rayon d or"
    assert clean_name("Rayon d'Or") == "Rayon d'Or"
    assert clean_name("Sangiovese N.") == "Sangiovese N."
    assert clean_name("Optima 113") == "Optima 113"


def test_latin_label_of_greek_capitals_is_titled():
    assert latin_label("ΟΦΘΑΛΜΟ", unidecode) == "Ophthalmo"
    assert latin_label("ΝΤΟΠΙΟ ΜΑΥΡΟ", unidecode) == "Ntopio Mauro"
    assert latin_label("Ξυνιστέρι", unidecode) == unidecode("Ξυνιστέρι")
