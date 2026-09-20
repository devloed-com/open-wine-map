"""Ellipsis-aware grounding coverage (scripts/_lib/terroir_coverage.py)."""
from __future__ import annotations

import pytest
from _lib.terroir_coverage import (
    FUZZY_THRESHOLD,
    SourceMatcher,
    fuzzy_coverage,
    normalize,
    provenance_for,
    split_spans,
)

SOURCE = (
    "Le climat est semi-continental à influence océanique. Les précipitations "
    "annuelles sont d'environ 600 millimètres. Les vignes sont plantées sur des "
    "sols argilo-calcaires du Kimméridgien, en coteaux exposés au sud."
)


def test_verbatim_quote_is_fully_covered():
    assert fuzzy_coverage("Le climat est semi-continental à influence océanique.", SOURCE) == 1.0


def test_normalisation_ignores_case_and_whitespace():
    assert fuzzy_coverage("LE CLIMAT   est semi-continental", SOURCE) == 1.0


def test_absent_quote_scores_low():
    assert fuzzy_coverage("Les vendanges ont lieu en octobre sous la neige.", SOURCE) < FUZZY_THRESHOLD


def test_empty_quote_is_zero():
    assert fuzzy_coverage("", SOURCE) == 0.0
    assert fuzzy_coverage("   ", SOURCE) == 0.0


@pytest.mark.parametrize("join", ["[…]", "[...]", "…", "...", "(…)", "(...)"])
def test_ellipsis_joined_spans_ground_when_every_span_grounds(join):
    quote = f"Le climat est semi-continental à influence océanique {join} sols argilo-calcaires du Kimméridgien"
    # A single contiguous match covers only the longer span (< 0.6); span-wise both are verbatim.
    assert SourceMatcher(SOURCE).contiguous(normalize(quote)) < FUZZY_THRESHOLD
    assert fuzzy_coverage(quote, SOURCE) == 1.0


def test_ellipsis_quote_with_one_ungrounded_span_keeps_whole_quote_grade():
    quote = "Le climat est semi-continental à influence océanique […] vendanges en octobre sous la neige"
    whole = SourceMatcher(SOURCE).contiguous(normalize(quote))
    assert fuzzy_coverage(quote, SOURCE) == whole
    assert fuzzy_coverage(quote, SOURCE) < FUZZY_THRESHOLD


def test_short_spans_are_not_graded_on_their_own():
    quote = "Le climat est semi-continental à influence océanique […] neige"
    assert fuzzy_coverage(quote, SOURCE) == 1.0


def test_split_spans_drops_empty_pieces():
    assert split_spans("a long enough first span […] […] second span here …") == [
        "a long enough first span",
        "second span here",
    ]


def test_source_matcher_reuses_index_across_quotes():
    m = SourceMatcher(SOURCE)
    assert m.coverage("Les précipitations annuelles sont d'environ 600 millimètres.") == 1.0
    assert m.coverage("coteaux exposés au sud") == 1.0
    assert m.coverage("") == 0.0


@pytest.mark.parametrize(
    "cahier,wiki,expected",
    [(1.0, 1.0, "both"), (0.6, 0.2, "cahier"), (0.59, 0.6, "wiki"), (0.5, 0.5, None)],
)
def test_provenance_for(cahier, wiki, expected):
    assert provenance_for(cahier, wiki) == expected


@pytest.mark.parametrize(
    "quote",
    [
        "Les précipitations annuelles sont d’environ 600 millimètres.",     # curly apostrophe
        "Les précipitations annuelles sont d'environ 600 millimètres.",
        "sols argilo‑calcaires du Kimméridgien",                            # non-breaking hyphen
        "sols argilo–calcaires du Kimméridgien",                            # en dash
        "sols argilo—calcaires du Kimméridgien",                            # em dash
    ],
)
def test_typography_variants_of_a_verbatim_quote_match_fully(quote):
    assert fuzzy_coverage(quote, SOURCE) == 1.0


def test_soft_hyphen_bullet_glyph_and_zero_width_characters_are_dropped():
    source = "\u00ad De bodem bestaat uit l\u200bössleem op een kalkrijke ondergrond."
    assert fuzzy_coverage("De bodem bestaat uit lössleem op een kalkrijke ondergrond.", source) == 1.0


def test_hyphenated_line_break_in_the_source_is_closed_up():
    source = "La temperatura media è di 1.900 gradi- giorno nel periodo aprile- ottobre sul versante sud."
    assert fuzzy_coverage("1.900 gradi-giorno nel periodo aprile-ottobre", source) == 1.0
    assert fuzzy_coverage("fra 300 - 400 m", "vigneti fra 300 - 400 m") == 1.0   # spaced dash untouched


def test_low_nine_and_guillemet_quotes_fold_to_straight():
    source = 'Die g.U. „Rosalia" liegt am Osthang; le « terroir » y est calcaire.'
    assert fuzzy_coverage('Die g.U. "Rosalia" liegt am Osthang', source) == 1.0
    assert fuzzy_coverage('le "terroir" y est calcaire', source) == 1.0
