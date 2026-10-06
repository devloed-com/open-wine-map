"""Derive the US state abbreviation for a wine AVA record.

The UCDavis corpus stores a 2-letter `state` field on each AVA feature
(e.g. "CA", "OR", "WA"). Multi-state AVAs carry a pipe-separated list
("OR|WA"); we return the *first* listed state as the canonical one since
the appellation's legal seat is in that state.

Resolution order:
  1. ``record['state']`` — direct field, first token before "|".
  2. Text scan across ``text_candidates`` — searches for full state names
     and 2-letter abbreviations (word-boundary anchored).
  3. Empty string if nothing resolves.
"""

from __future__ import annotations

import re
import unicodedata

# Full set of US state abbreviations accepted by TTB.
US_STATES = frozenset((
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD",
    "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH",
    "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
))

# Full name (lower, normalised) → 2-letter abbreviation.
# Sorted longest-first so "west virginia" beats "virginia" in text scan.
_STATE_NAMES: dict[str, str] = {
    "alaska": "AK",
    "alabama": "AL",
    "arkansas": "AR",
    "arizona": "AZ",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "iowa": "IA",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "massachusetts": "MA",
    "maryland": "MD",
    "maine": "ME",
    "michigan": "MI",
    "minnesota": "MN",
    "missouri": "MO",
    "mississippi": "MS",
    "montana": "MT",
    "north carolina": "NC",
    "north dakota": "ND",
    "nebraska": "NE",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "nevada": "NV",
    "new york": "NY",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "virginia": "VA",
    "vermont": "VT",
    "washington": "WA",
    "wisconsin": "WI",
    "west virginia": "WV",
    "wyoming": "WY",
}

_SORTED_NAMES = sorted(_STATE_NAMES.items(), key=lambda kv: -len(kv[0]))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def state_for_abbreviation(abbr: str) -> str:
    """Return a canonical 2-letter state code, or '' if unknown."""
    upper = (abbr or "").strip().upper()
    return upper if upper in US_STATES else ""


def find_state_in_text(text: str) -> str | None:
    """Scan free text for a US state name or abbreviation.
    Returns the 2-letter code or None. Longest-match wins."""
    if not text:
        return None
    low = _norm(text)
    for name, abbr in _SORTED_NAMES:
        if name in low:
            return abbr
    for abbr in US_STATES:
        if re.search(r"\b" + re.escape(abbr) + r"\b", text, re.IGNORECASE):
            return abbr
    return None


def derive_state(record: dict, *text_candidates: str) -> str:
    """Resolve the US state abbreviation for one AVA record.

    For multi-state AVAs (e.g. ``state = "OR|WA"``), returns the first
    token — the state where the TTB filed the petition.
    """
    raw = (record.get("state") or "").strip()
    if raw:
        first = raw.split("|")[0].strip().upper()
        if first in US_STATES:
            return first
        hit = _STATE_NAMES.get(first.lower())
        if hit:
            return hit
    for text in text_candidates:
        hit = find_state_in_text(text or "")
        if hit:
            return hit
    return ""
