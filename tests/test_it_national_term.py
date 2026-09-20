"""Regression tests for the Italian DOC / DOCG / IGT term resolver
(scripts/_lib/it/national_term.py).

The roster is the MASAF "Elenco alfabetico dei vini DOP italiani"
(pdftotext -layout). The fixture is a redacted excerpt of the 18.03.2026
build covering the row shapes the parser must survive: a plain row, a
name wrapped over three lines (Bagnoli Friularo), a region wrapped around
the row (Lison), and both file-number spellings (`PDO-IT-A0277` vs the
post-2023 `PDO-IT-02972`).

Pure-function tests — no pdftotext, no raw/.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.it import national_term  # noqa: E402
from _lib.it.national_term import (  # noqa: E402
    file_number_tail,
    it_term_for,
    load_it_term_overrides,
    parse_elenco_text,
)


def test_file_number_tail_strips_scheme_country_letter_and_zeros():
    assert file_number_tail("PDO-IT-A1896") == "1896"
    assert file_number_tail("PDO-IT-01896") == "1896"
    assert file_number_tail("PGI-IT-A0852") == "852"
    assert file_number_tail("PDO-IT-A0880") == "880"
    assert file_number_tail("") == ""


def test_parse_elenco_fixture_rows(fixture_text):
    roster = parse_elenco_text(fixture_text("it_masaf_elenco_excerpt.txt"))
    assert len(roster) == 9
    assert sum(1 for t in roster.values() if t == "DOCG") == 7
    assert roster["880"] == "DOC"
    assert roster["277"] == "DOCG"
    # Name wrapped over three lines — term + file number still on one line.
    assert roster["467"] == "DOCG"
    # Region wrapped around the row.
    assert roster["457"] == "DOCG"
    # Post-2023 numeric-only file numbers join on the bare tail.
    assert roster["2972"] == "DOCG"
    assert roster["3209"] == "DOCG"
    assert roster["610"] == "DOC"


def test_it_term_for_resolves_kind_and_roster(monkeypatch, fixture_text):
    roster = parse_elenco_text(fixture_text("it_masaf_elenco_excerpt.txt"))
    monkeypatch.setattr(national_term, "load_it_terms", lambda: roster)
    monkeypatch.setattr(national_term, "load_it_term_overrides", lambda: {})

    assert it_term_for({"slug": "toscana", "file_number": "PGI-IT-A1517"}, "IGP") == "IGT"
    assert it_term_for({"slug": "abruzzo", "file_number": "PDO-IT-A0880"}, "DOP") == "DOC"
    assert it_term_for({"slug": "casauria", "file_number": "PDO-IT-02972"}, "DOP") == "DOCG"
    assert it_term_for({"slug": "nowhere", "file_number": "PDO-IT-A9999"}, "DOP") == ""
    assert it_term_for({"slug": "abruzzo", "file_number": "PDO-IT-A0880"}, "AOC") == ""


def test_sottozona_resolves_through_parent_file_number(monkeypatch, fixture_text):
    roster = parse_elenco_text(fixture_text("it_masaf_elenco_excerpt.txt"))
    monkeypatch.setattr(national_term, "load_it_terms", lambda: roster)
    monkeypatch.setattr(national_term, "load_it_term_overrides", lambda: {})
    sottozona = {
        "slug": "valtellina-superiore-sassella",
        "file_number": "PDO-IT-A1036",
        "is_sub_denomination": True,
        "parent_slug": "valtellina-superiore",
    }
    assert it_term_for(sottozona, "DOP") == "DOCG"


def test_override_takes_precedence_over_roster(monkeypatch):
    monkeypatch.setattr(national_term, "load_it_terms", lambda: {"1188": "DOCG"})
    assert it_term_for({"slug": "valtenesi", "file_number": "PDO-IT-A1188"}, "DOP") == "DOC"


def test_overrides_file_is_well_formed():
    overrides = load_it_term_overrides()
    assert {"valtenesi", "ciro-classico"} <= set(overrides)
    for slug, entry in overrides.items():
        assert entry["term"] in {"DOC", "DOCG"}, slug
        assert file_number_tail(entry["file_number"]), slug
        assert entry["sources"], slug
        for src in entry["sources"]:
            assert src["label"] and src["url"].startswith("http"), slug
