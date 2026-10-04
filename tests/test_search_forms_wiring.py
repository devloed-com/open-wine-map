"""The search-only name forms reach the map: the startup field exists, the
region helper merges its three sources, and the Bulgarian bracket is the
official system."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.i18n import compile_catalogs  # noqa: E402
from _lib.map_template import STARTUP_AOCS_FIELDS  # noqa: E402
from _lib.region_search_terms import derived_forms, region_search_terms_for  # noqa: E402
from _lib.romanise import search_forms, search_key  # noqa: E402


def test_search_forms_is_a_startup_field() -> None:
    assert "search_forms" in STARTUP_AOCS_FIELDS


def test_greek_region_gets_its_romanisations() -> None:
    terms = region_search_terms_for(["Μακεδονία"])["Μακεδονία"]
    keys = {search_key(f) for f in terms["forms"]}
    assert "makedonia" in keys
    # A derived romanisation is searchable, never echoed.
    assert not any(search_key(f) == "makedonia" for f in terms["labels"])


def test_cyrillic_region_gets_official_and_unidecode_forms() -> None:
    assert derived_forms("Тракийска низина") == ["Trakiyska nizina", "Trakiiska nizina"]


def test_french_bassin_gets_every_locale_label_as_an_echo_form() -> None:
    compile_catalogs()
    terms = region_search_terms_for(["BOURGOGNE"])["BOURGOGNE"]
    keys = {search_key(f) for f in terms["forms"]}
    assert {"burgundy", "borgona", "bourgogne"} <= keys, terms
    # The proper-cased fr label is kept although it folds to the INAO key:
    # it is what the English map echoes when a visitor types "bourgogne".
    assert "Bourgogne" in terms["labels"], terms


def test_forms_are_distinct_after_normalisation() -> None:
    for region, terms in region_search_terms_for(["Toscana", "Κρήτη", "BOURGOGNE"]).items():
        forms = terms["forms"]
        assert len({search_key(f) for f in forms}) == len(forms), region
        assert set(terms["labels"]) <= set(forms), region


def test_record_forms_are_search_only_extras() -> None:
    assert search_forms("Άγιο Όρος", "Ayio Oros", "gr") == ["Agio Oros"]
    assert search_forms("Bourgogne", "", "fr") == []
