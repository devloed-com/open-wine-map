"""Heuristics for filtering Wikipedia summary results to grape varieties only.

The REST summary endpoint returns *something* for almost any title — including
surnames, communes, mountains, comic-book characters, etc. We do not want to
attribute those to a grape pill. Each cached fetch and each lexicon load runs
the same positive-keyword check: an article only counts as a grape if its
description or extract mentions one of the per-locale grape-vocabulary
markers below.
"""

from __future__ import annotations

# Positive markers that almost always appear in real grape articles in each
# locale's Wikipedia. Negative-keyword filtering (rejecting "commune", etc.)
# is too leaky — we only accept on a positive hit.
GRAPE_KEYWORDS = {
    "fr": ("cépage", "vinifera", "vitis vinifera", "vigne cultivée"),
    "en": ("grape variety", "variety of grape", "type of grape",
           "grape cultivar", "wine grape", "wine-grape",
           "vinifera", "vitis vinifera", "varietal"),
    "es": ("uva", "vinífera", "vinifera", " vid ", "vitis vinifera",
           "variedad vinífera"),
    "nl": ("druif", "druivenras", "druivensoort", "vitis vinifera",
           "wijndruif"),
    "pt": ("casta", "videira", "uva", "vitis vinifera", "vinífera",
           "variedade de uva"),
}


def is_grape_summary(lang: str, description: str, extract: str) -> bool:
    """True iff the article looks like a grape variety in `lang`."""
    blob = ((description or "") + " " + (extract or "")).lower()
    return any(k in blob for k in GRAPE_KEYWORDS.get(lang, ()))
