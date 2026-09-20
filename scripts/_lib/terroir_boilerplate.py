"""Boilerplate detector for terroir facts (W6 of the 2026-09-11 review).

Some regulator texts carry a sentence that is true of any appellation —
"the uniqueness of the wines is due to the particular characteristics of
the area (soil, climate, winds)" appears verbatim in dozens of Greek PGI
specs; Alsace's shared cahier repeats "a homogeneous geo-pedological unit
with a most favourable mesoclimate"; German Landwein specs say the wines
are "shaped mainly by vintage and variety". Extracted as a fact, such a
sentence tells the reader nothing.

The filter is deliberately conservative — two conditions, both required:

- the fact's `cahier_quote` (normalised, ≥ `QUOTE_MIN_CHARS`) matches one
  of the tautology patterns for the record's source language, AND
- that pattern is matched by at least `MIN_SHARED_RECORDS` records of the
  same country.

Shared quotes alone are never enough: several cahiers are legitimately
shared (the Anjou family, the Calabrian IGT text, the Romanian caiete,
the Alsace `produit` slice) and carry real facts. A boilerplate fact is
kept when it is the record's only fact, and a bullet that carries a
number is never treated as boilerplate — quantitative content is
information even when the quoted sentence is the tautology.

The boilerplate sentence usually embeds the appellation's own name ("Η
μοναδικότητα των οίνων ΠΓΕ Χαλκιδική οφείλεται…") and the model quotes
spans of varying length, so "the same quote" is decided by the pattern:
records are grouped per (country, pattern), and a pattern that ≥ 3
records of one country quote is boilerplate for all of them.
"""

from __future__ import annotations

import re
from collections import defaultdict

MIN_SHARED_RECORDS = 3
QUOTE_MIN_CHARS = 60
_HAS_NUMBER = re.compile(r"\d")

TAUTOLOGY_PATTERNS: dict[str, tuple[str, ...]] = {
    "el": (
        r"μοναδικότητα των οίνων .{0,60}οφείλεται στα ιδιαίτερα χαρακτηριστικά",
        r"οίνοι με τυπικότητα και ιδιαίτερους ποιοτικούς χαρακτήρες",
        r"ευνοϊκ\S* εδαφοκλιματ\S* συνθήκ",
    ),
    "fr": (
        r"unité géo-pédologique associés à un mésoclimat des plus favorables",
    ),
    "de": (
        r"prägung überwiegend durch jahrgang und sorte",
        r"jahrgangs- und sortennote",
    ),
    "ro": (
        r"amprenta .{0,40}soiului, solului, microclimatului",
    ),
    "it": (
        r"caratteristiche chimico-fisiche equilibrate",
    ),
    "en": (
        r"uniqueness .{0,40}attributed to",
        r"directly linked to the character",
        r"no uniform description",
        r"defined by their typicity",
        r"favourable soil and climatic conditions",
    ),
}
_COMPILED = {lang: tuple(re.compile(p) for p in pats) for lang, pats in TAUTOLOGY_PATTERNS.items()}


def normalise_quote(q: str) -> str:
    return " ".join((q or "").split()).casefold()


def matching_pattern(quote_norm: str, source_lang: str) -> str | None:
    """The first tautology pattern (its regex source) matching the quote."""
    for rx in _COMPILED.get(source_lang, ()):
        if rx.search(quote_norm):
            return rx.pattern
    return None


def is_tautology(quote_norm: str, source_lang: str) -> bool:
    return matching_pattern(quote_norm, source_lang) is not None


def find_boilerplate(caches: dict[str, dict]) -> dict[str, list[int]]:
    """slug → indices of facts to drop (never all of a record's facts)."""
    hits: dict[str, list[tuple[int, str, str]]] = {}
    by_pattern: dict[tuple[str, str], set[str]] = defaultdict(set)
    for slug, d in caches.items():
        cc = d.get("country") or "fr"
        lang = d.get("source_lang") or "fr"
        for i, f in enumerate(d.get("facts") or []):
            q = normalise_quote(f.get("cahier_quote"))
            if len(q) < QUOTE_MIN_CHARS or _HAS_NUMBER.search(f.get("bullet") or ""):
                continue
            pat = matching_pattern(q, lang)
            if pat is None:
                continue
            hits.setdefault(slug, []).append((i, cc, pat))
            by_pattern[(cc, pat)].add(slug)
    out: dict[str, list[int]] = {}
    for slug, rows in hits.items():
        drops = [i for i, cc, pat in rows if len(by_pattern[(cc, pat)]) >= MIN_SHARED_RECORDS]
        n_facts = len(caches[slug].get("facts") or [])
        if drops and len(drops) >= n_facts:
            drops = drops[1:]  # keep the record's only fact rather than empty it
        if drops:
            out[slug] = drops
    return out
