"""GB region facet — the home nation each UK wine GI is demarcated to.

The UK wines register is small (6 registered GIs) and every product
specification states its territory in a single `DEMARCATION:` /
`Demarcation:` field whose value is a home nation:

  - English PDO            (PDO-GB-A1585) → England
  - English Regional PGI   (PGI-GB-A1589) → England
  - Welsh PDO              (PDO-GB-A1587) → Wales
  - Welsh Regional PGI     (PGI-GB-A1590) → Wales
  - Sussex PDO             (PDO-GB-02365) → England  (East + West Sussex)
  - Darnibole PDO          (PDO-GB-N1636) → England  (a 5 ha single
                                            vineyard in Cornwall)

Sussex and Darnibole sit geographically inside the English PDO's
territory but are **not** sub-denominations of it: each is a
first-class PDO in its own right on the UK register (Darnibole's
specification says so explicitly — "It qualified under the 'English'
PDO last year, but is considered unique and sufficiently different so
as to merit its own PDO"). v1 therefore models the corpus flat, the
way the CZ podoblasti are modelled as siblings of Čechy / Morava.

Region labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK/CZ/NL/MT
convention — shown in their native form, not gettext-translated.
"""

from __future__ import annotations

_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-GB-A1585": "England",
    "PGI-GB-A1589": "England",
    "PDO-GB-A1587": "Wales",
    "PGI-GB-A1590": "Wales",
    "PDO-GB-02365": "England",
    "PDO-GB-N1636": "England",
}

# Fallback for a GI added to the register after this table was written:
# the specification's own DEMARCATION field, normalised.
_DEMARCATION_TO_REGION: dict[str, str] = {
    "england": "England",
    "wales": "Wales",
    "scotland": "Scotland",
    "northern ireland": "Northern Ireland",
    "east and west sussex": "England",
}


def derive_region(record: dict) -> str:
    fn = (record.get("file_number") or "").strip()
    if fn in _REGION_BY_FILE_NUMBER:
        return _REGION_BY_FILE_NUMBER[fn]
    demarcation = (record.get("demarcation") or "").strip().lower()
    if demarcation in _DEMARCATION_TO_REGION:
        return _DEMARCATION_TO_REGION[demarcation]
    for key, region in _DEMARCATION_TO_REGION.items():
        if key in demarcation:
            return region
    return "United Kingdom"
