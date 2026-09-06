"""Name-matching keys for French appellation names.

Shared by stage 02 (matching a SIQO appellation to its cahier segment
header) and the eAmbrosia register resolver (matching a SIQO appellation to
a register `protectedName`). Extracted verbatim from
`scripts/02_extract_cahiers.py` so both callers fold aliases identically.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_name(s: str) -> str:
    """Loose match key — strips diacritics, casing, spacing/hyphens."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[\W_]+", "", s).lower()


# AOC names regularly carry one or more aliases concatenated with " ou ", " et ",
# or comma-separated lists — e.g. "Cidre de Normandie ou Cidre normand",
# "Cognac ou Eau-de-vie de Cognac ou Eau-de-vie des Charentes",
# "Côtes de Bourg, Bourg et Bourgeais". The cahier itself usually carries only
# one of those variants as its segment header, so a strict normalize-and-equal
# match between parent name and segment header misses them. Splitting both sides
# into alias parts and matching on any shared component closes the gap without
# the false-positive risk of pure substring matching ("Bourgogne" would
# otherwise match a "Bourgogne Passe-tout-grains" segment).
_ALIAS_SPLIT_RE = re.compile(r"\s+ou\s+|\s+et\s+|,\s*", flags=re.IGNORECASE)


def candidate_keys(name: str) -> list[str]:
    """Return a list of normalised match keys for `name` — the full normalised
    form first, followed by aliases split on " ou ", " et ", and commas."""
    keys: list[str] = []
    full = normalize_name(name)
    if full:
        keys.append(full)
    for part in _ALIAS_SPLIT_RE.split(name):
        part = part.strip()
        if not part:
            continue
        k = normalize_name(part)
        if k and k not in keys:
            keys.append(k)
    return keys
