"""The umlaut fold of the card's bracket rule, and the sweep that guards it.

`canonical_equals_cahier` deletes an "e" after a / o / u on both sides so the
three spellings of one name — "Gewürztraminer", the Iberian "gewurztraminer",
GB's "Schonburger" — meet VIVC's GEWUERZTRAMINER / SCHOENBURGER (2026-10-23:
408 redundant brackets). The deletion also touches every genuine vowel + e
sequence (piquepoul, jacquère, Jaen, Blauer …), so a pair it alone collapses
must be an umlaut pair: `fold_only_bracket_class` says whether it is, and
`audit_grape_identity.py --strict` fails on a corpus pair it cannot explain.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.content_block import (  # noqa: E402
    canonical_equals_cahier,
    fold_only_bracket_class,
    umlaut_digraph_key,
)


def _audit():
    spec = importlib.util.spec_from_file_location(
        "audit_grape_identity", ROOT / "scripts" / "audit_grape_identity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("prime, spelling, siblings, expected", [
    # the spelling's umlaut is the digraph VIVC writes
    ("Gewuerztraminer", "Gewürztraminer", (), "umlaut"),
    ("Gewuerztraminer", "Gewürztraminer Rs", (), "umlaut"),
    ("Harslevelue", "Hárslevelű", (), "umlaut"),
    ("Csaba Gyoengye", "csabagyöngye", (), "umlaut"),
    ("Blaufraenkisch", "Blaufränkisch", (), "umlaut"),
    ("Phoenix", "Phönix", (), "umlaut"),
    ("Jubilaeumsrebe", "Jubiläumsrebe", (), "umlaut"),
    # no umlaut in this spelling, but a sibling spelling of the slug has it
    ("Gewuerztraminer", "gewurztraminer", ("Gewürztraminer",), "umlaut-sibling"),
    ("Gewuerztraminer", "gewurz-traminer", ("Gewürztraminer", "Gewurztraminer"), "umlaut-sibling"),
    ("Schoenburger", "Schonburger", ("Schönburger Rs",), "umlaut-sibling"),
    ("Zala Gyoengye", "Zala Gyongye", ("zalagyöngye",), "umlaut-sibling"),
    # no spelling of the slug carries an umlaut: the fold collapsed something else
    ("Gewuerztraminer", "gewurztraminer", (), "review"),
    ("Zala Gyoengye", "Zala Gyongye", ("Perle von Zala",), "review"),
    # a sibling without an umlaut vouches for nothing: a trailing conjunction
    # the fold hid behind the prime (it:brachetto-d-acqui, found by the sweep)
    ("Brachetto", "Brachetto e", ("Brachetto", "Brachetto N."), "review"),
    # the fold played no part: equal without it, or not equal with it
    ("Jacquere", "jacquère", (), None),
    ("Piquepoul Blanc", "piquepoul blanc", (), None),
    ("Braquet Noir", "Braquet", (), None),
    ("Cabernet Sauvignon", "Cabernet Sauvignon N.", (), None),
    ("Mencia", "Jaen", (), None),
    ("Blaufraenkisch", "Blauer Limberger", ("Blaufränkisch",), None),
    ("Tempranillo Tinto", "Aragonez", (), None),
    ("Cabernet Sauvignon", "Cabertnet Sauvignon", (), None),
])
def test_fold_only_bracket_class(prime, spelling, siblings, expected):
    assert fold_only_bracket_class(prime, spelling, siblings) == expected
    # a classed pair is one the card renders without a bracket
    if expected:
        assert canonical_equals_cahier(prime, spelling)


def test_umlaut_digraph_key_writes_the_umlaut_as_vivc_does():
    assert umlaut_digraph_key("Gewürztraminer") == "gewuerztraminer"
    assert umlaut_digraph_key("Hárslevelű") == "harslevelue"
    assert umlaut_digraph_key("Kövérszőlő") == "koeverszoeloe"
    assert umlaut_digraph_key("Schönburger Rs") == "schoenburger"
    assert umlaut_digraph_key("Gewurztraminer") == "gewurztraminer"


def test_sweep_classes_canned_pairs_and_orders_review_first():
    pairs = {
        ("Gewürztraminer", "gewurztraminer"): {"de:mosel"},
        ("gewurztraminer", "gewurztraminer"): {"fr:alsace", "es:rioja"},
        ("Schonburger", "schonburger"): {"gb:english-wine"},
        ("Jacquère", "jacquere"): {"fr:savoie"},
        ("Aragonez", "tempranillo"): {"pt:alentejo"},
    }
    primes = {"gewurztraminer": "Gewuerztraminer", "schonburger": "Schoenburger",
              "jacquere": "Jacquere", "tempranillo": "Tempranillo Tinto"}
    rows = _audit().fold_only_brackets(pairs, primes)
    assert [(r["class"], r["name"]) for r in rows] == [
        ("review", "Schonburger"),
        ("umlaut-sibling", "gewurztraminer"),
        ("umlaut", "Gewürztraminer"),
    ]
    assert rows[1]["records"] == ["es:rioja", "fr:alsace"]


@pytest.mark.skipif(not (ROOT / "raw" / "vivc" / "by-slug").exists(), reason="no VIVC cache")
def test_live_corpus_has_no_unexplained_fold_pair():
    rows = _audit().fold_only_brackets()
    review = [(r["name"], r["prime"], r["slug"]) for r in rows if r["class"] == "review"]
    assert review == [], review
    assert rows, "the sweep found no umlaut pair at all — did the corpus or the rule change?"
