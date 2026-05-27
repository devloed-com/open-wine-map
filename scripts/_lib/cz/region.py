"""Derive the Czech vinařská oblast (wine region) for a wine GI.

The Czech wine corpus has 13 GIs registered in eAmbrosia:

  - 2 macro PDOs (Čechy / Morava) = the two Czech wine macro regions
    (Bohemia / Moravia). They are themselves PDOs, not PGIs.
  - 2 macro PGIs (české / moravské) = the same two macro territories
    but registered as PGIs ("zemské víno české" / "zemské víno
    moravské").
  - 9 sub-region / district / single-vineyard PDOs:
       Bohemia (Čechy):     Litoměřická, Mělnická
       Moravia (Morava):    Velkopavlovická, Znojemská, Mikulovská,
                            Slovácká, Šobes (vineyard tract inside
                            Znojemská), Znojmo (sub-region of Znojemská),
                            Novosedelské Slámové víno (single-varietal,
                            sub-region of Mikulovská)

The region drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). Region labels follow the AT/IT/ES/SI/HR/
SK convention — shown in their native form, not gettext-translated.
"""

from __future__ import annotations

import re
import unicodedata

# The 2 Czech wine macro regions (canonical Czech spelling).
REGIONS = (
    "Čechy",
    "Morava",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}


# Curated file_number → region. Hand-verified against eAmbrosia + the
# Czech wine-law region structure (Zákon č. 321/2004 Sb.).
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-CZ-A0888": "Čechy",     # Čechy
    "PDO-CZ-A0894": "Čechy",     # Litoměřická (sub-region of Čechy)
    "PDO-CZ-A0895": "Čechy",     # Mělnická (sub-region of Čechy)
    "PGI-CZ-A0900": "Čechy",     # české (PGI = whole Bohemia)
    "PDO-CZ-A0899": "Morava",    # Morava
    "PDO-CZ-A0890": "Morava",    # Slovácká (sub-region of Morava)
    "PDO-CZ-A0892": "Morava",    # Znojemská (sub-region of Morava)
    "PDO-CZ-A0896": "Morava",    # Velkopavlovická (sub-region of Morava)
    "PDO-CZ-A0897": "Morava",    # Mikulovská (sub-region of Morava)
    "PDO-CZ-A1086": "Morava",    # Znojmo (sub-area of Znojemská)
    "PDO-CZ-A1089": "Morava",    # Šobes (named vineyard, Znojemská)
    "PDO-CZ-A1321": "Morava",    # Novosedelské Slámové víno (Mikulovská)
    "PGI-CZ-A0902": "Morava",    # moravské (PGI = whole Moravia)
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def find_region_in_text(text: str) -> str | None:
    """Scan text for a region name. Returns the canonical form or None.
    Earliest match wins."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle, canon in _CANON_BY_NORM.items():
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        if best is None or pos < best[0]:
            best = (pos, canon)
    return best[1] if best else None


def derive_region(record: dict, *text_candidates: str) -> str:
    """Resolve the vinařská oblast for one record. The curated
    file_number map is authoritative; the text scan only runs when the
    file_number is unknown."""
    if record.get("region"):
        return record["region"]
    curated = region_for_file_number(record.get("file_number", ""))
    if curated:
        return curated
    for text in text_candidates:
        hit = find_region_in_text(text or "")
        if hit:
            return hit
    return ""
