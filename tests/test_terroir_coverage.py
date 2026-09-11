"""Ellipsis-aware grounding coverage (scripts/_lib/terroir_coverage.py)."""
from __future__ import annotations

import pytest
from _lib.terroir_coverage import (
    FUZZY_THRESHOLD,
    SourceMatcher,
    fuzzy_coverage,
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
    assert SourceMatcher(SOURCE).contiguous(quote.lower()) < FUZZY_THRESHOLD
    assert fuzzy_coverage(quote, SOURCE) == 1.0


def test_ellipsis_quote_with_one_ungrounded_span_keeps_whole_quote_grade():
    quote = "Le climat est semi-continental à influence océanique […] vendanges en octobre sous la neige"
    whole = SourceMatcher(SOURCE).contiguous(quote.lower())
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
