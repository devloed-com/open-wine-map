"""A bare rosé word is a wine type, never a grape.

VIVC lists ROSE as a synonym of Nebbiolo (#8417), so the MASAF line "spumante
rosato o rosè" and the Hungarian "Rosé" category bound Nebbiolo to Romagna
Oriolo, Prosecco, Franciacorta, Abruzzo, Pécs and others (2026-10-22). The
Oriolo line names Centesimino (VIVC #22606), which the lexicon now carries.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import match_variety  # noqa: E402


@pytest.mark.parametrize("token", ["rosè", "rosé", "Rosé", "ROSÉ", "Rose", "rosato", "Rosato",
                                   "rosati", "rosat"])
def test_rose_words_are_not_grapes(token):
    assert match_variety(token) is None


@pytest.mark.parametrize("token", ["Centesimino", "Centesimino N.", "Savignon rosso"])
def test_centesimino_resolves(token):
    m = match_variety(token)
    assert m is not None and m.slug == "centesimino", (token, m)


def test_nebbiolo_still_resolves():
    m = match_variety("Nebbiolo N.")
    assert m is not None and m.slug == "nebbiolo"
