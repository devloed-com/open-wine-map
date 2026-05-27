"""Derive the Slovak vinohradnícka oblasť (wine region) for a wine GI.

Slovakia has 6 vinohradnícke oblasti (wine regions), 5 of which appear
as DOPs in the corpus (Malokarpatská, Južnoslovenská, Nitrianska,
Stredoslovenská, Východoslovenská) plus the Tokaj vinohradnícka oblasť
(Vinohradnícka oblasť Tokaj DOP). One PDO (Karpatská perla) sits inside
the Malokarpatská oblasť as a specialised regional brand; one DOP
(Skalický rubín) sits inside the Malokarpatská oblasť as a single-
varietal area; one DOP (TOKAJSKÉ VÍNO zo slovenskej oblasti) is the
post-Bétard rebranded Tokaj wine PDO. The single PGI (Slovenská) spans
the whole country.

The region drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). Region labels follow the AT/IT/ES/SI/HR
convention — shown in their native form, not gettext-translated.
"""

from __future__ import annotations

import re
import unicodedata

# The 6 Slovak wine regions (canonical Slovak spelling). The Tokaj
# oblasť is treated as its own region facet because it carries its
# own PDOs distinct from the other 5.
REGIONS = (
    "Malokarpatská",
    "Južnoslovenská",
    "Nitrianska",
    "Stredoslovenská",
    "Východoslovenská",
    "Tokaj",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}


# Curated file_number → region, hand-verified against eAmbrosia + the
# Slovak wine-law region structure (5 wine oblasti + Tokaj).
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-SK-A1354": "Východoslovenská",
    "PDO-SK-A1355": "Stredoslovenská",
    "PDO-SK-A1356": "Južnoslovenská",
    "PDO-SK-A1357": "Nitrianska",
    "PDO-SK-A1360": "Malokarpatská",
    "PDO-SK-A1598": "Malokarpatská",   # Karpatská perla
    "PDO-SK-A0120": "Tokaj",            # Vinohradnícka oblasť Tokaj
    "PDO-SK-02856": "Tokaj",            # TOKAJSKÉ VÍNO zo slovenskej oblasti
    "PDO-SK-01899": "Malokarpatská",   # Skalický rubín — Skalica is in Malokarpatská
    "PGI-SK-A1361": "Slovensko",        # Slovenská — country-wide PGI
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
    """Resolve the vinohradnícka oblasť for one record. The curated
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
