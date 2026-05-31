"""Derive the Cyprus wine district (επαρχία) for a wine GI.

Cyprus wine law organises the island's vineyards by administrative
district (επαρχία). The 4 wine districts double as the 4 PGIs
(Πάφος / Λεμεσός / Λάρνακα / Λευκωσία); the 7 PDOs each sit inside one
district:

  - Πάφος    (Pafos)    — Βουνί Παναγιάς – Αμπελίτης, Λαόνα Ακάμα
  - Λεμεσός  (Lemesos)  — Κουμανδαρία, Κρασοχώρια Λεμεσού (+ Αφάμης /
                          Λαόνα), Πιτσιλιά
  - Λάρνακα  (Larnaka)
  - Λευκωσία (Lefkosia)

The region facet is shown in native Greek, matching the GR αμπελουργική
ζώνη / AT Bundesland / BG винарски район convention — not gettext-
translated.

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re

REGIONS = (
    "Πάφος",
    "Λεμεσός",
    "Λάρνακα",
    "Λευκωσία",
)


def _norm(s: str) -> str:
    """Greek-preserving normaliser. casefold + collapse whitespace,
    strip punctuation outside Greek / Latin / digit."""
    s = s.casefold()
    s = re.sub(r"[^a-z0-9α-ωάέήίόύώϊϋΐΰ \-]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}

# Common inflected / alternative forms seen in the area text.
_TEXT_ALIASES = {
    _norm("Πάφου"): "Πάφος",
    _norm("Paphos"): "Πάφος",
    _norm("Pafos"): "Πάφος",
    _norm("Λεμεσού"): "Λεμεσός",
    _norm("Limassol"): "Λεμεσός",
    _norm("Lemesos"): "Λεμεσός",
    _norm("Λάρνακας"): "Λάρνακα",
    _norm("Larnaca"): "Λάρνακα",
    _norm("Larnaka"): "Λάρνακα",
    _norm("Λευκωσίας"): "Λευκωσία",
    _norm("Nicosia"): "Λευκωσία",
    _norm("Lefkosia"): "Λευκωσία",
}
_CANON_BY_NORM.update(_TEXT_ALIASES)


# Curated file_number → district, hand-verified against the Cyprus wine
# districts + the moa.gov.cy technical files.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-CY-A1622": "Λεμεσός",   # Κουμανδαρία (Commandaria — Limassol foothills)
    "PDO-CY-A1623": "Λεμεσός",   # Κρασοχώρια Λεμεσού - Αφάμης
    "PDO-CY-A1624": "Λεμεσός",   # Κρασοχώρια Λεμεσού - Λαόνα
    "PDO-CY-A1625": "Πάφος",     # Βουνί Παναγιάς – Αμπελίτης
    "PDO-CY-A1626": "Πάφος",     # Λαόνα Ακάμα
    "PDO-CY-A1627": "Λεμεσός",   # Πιτσιλιά (Troodos eastern slopes — Limassol)
    "PDO-CY-A1628": "Λεμεσός",   # Κρασοχώρια Λεμεσού
    "PGI-CY-A1618": "Πάφος",     # Πάφος
    "PGI-CY-A1619": "Λεμεσός",   # Λεμεσός
    "PGI-CY-A1620": "Λάρνακα",   # Λάρνακα
    "PGI-CY-A1621": "Λευκωσία",  # Λευκωσία
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def find_region_in_text(text: str) -> str | None:
    """Scan text for a district name. Returns the canonical form or None.
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
    """Resolve the wine district for one record. The curated file_number
    map is authoritative; the text scan only runs when the file_number
    is unknown."""
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
