"""Derive the Australian state/territory for a wine GI record.

Australia has 6 states and 2 major territories.  Wine Australia's GI
hierarchy places each Zone, Region, and Subregion within one (or
occasionally two) administrative states; multi-state GIs are rare
(e.g. Riverina spans NSW and VIC) and are tagged with the primary state
where the bulk of the production area lies.

Resolution order:
  1. ``record['state']`` — direct field, first token before "|".
  2. Text scan across ``text_candidates`` — searches for full state names
     (longest-match first to avoid "South" matching "South Australia"
     before "New South Wales") and 2-letter abbreviations.
  3. Empty string if nothing resolves.
"""

from __future__ import annotations

import re
import unicodedata

AU_STATES = frozenset(("NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"))

# Full name (lower, normalised) → 2-letter abbreviation.
# Order matters for text scan: longest names must come first to avoid
# "south australia" consuming the "south" in "new south wales".
_STATE_NAMES: dict[str, str] = {
    "australian capital territory": "ACT",
    "northern territory": "NT",
    "new south wales": "NSW",
    "western australia": "WA",
    "south australia": "SA",
    "queensland": "QLD",
    "tasmania": "TAS",
    "victoria": "VIC",
}

_SORTED_NAMES = sorted(_STATE_NAMES.items(), key=lambda kv: -len(kv[0]))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def state_for_abbreviation(abbr: str) -> str:
    """Return a canonical 2-letter state code, or '' if unknown."""
    upper = (abbr or "").strip().upper()
    return upper if upper in AU_STATES else ""


def find_state_in_text(text: str) -> str | None:
    """Scan free text for an Australian state name or abbreviation.
    Returns the 2-letter code or None. Longest-match wins."""
    if not text:
        return None
    low = _norm(text)
    for name, abbr in _SORTED_NAMES:
        if name in low:
            return abbr
    for abbr in AU_STATES:
        if re.search(r"\b" + re.escape(abbr) + r"\b", text, re.IGNORECASE):
            return abbr
    return None


def derive_state(record: dict, *text_candidates: str) -> str:
    """Resolve the AU state abbreviation for one GI record.

    For multi-state GIs (e.g. ``state = "NSW|VIC"``), returns the first
    token — the primary state listed in the Wine Australia register.
    """
    raw = (record.get("state") or "").strip()
    if raw:
        first = raw.split("|")[0].strip().upper()
        if first in AU_STATES:
            return first
        hit = _STATE_NAMES.get(first.lower())
        if hit:
            return hit
    for text in text_candidates:
        hit = find_state_in_text(text or "")
        if hit:
            return hit
    return ""
