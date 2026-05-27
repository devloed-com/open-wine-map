"""Derive the Greek wine region (αμπελουργική ζώνη) for a wine GI.

Greek wine law and the EDOAO (National Interprofessional Wine
Organisation of Greece, ΚΕΟΣΟΕ) classify the country's vineyards into
9 traditional macro wine regions. The 33 PDOs and 114 PGIs map onto
those 9 regions; several of the regions also appear as PGIs in their
own right (PGI Μακεδονία, PGI Πελοπόννησος, PGI Κρήτη, PGI Θεσσαλία,
PGI Ήπειρος, PGI Νησιά Αιγαίου …) — the regional PGIs are first-class
records, not parents to sub-denominations.

The region facet is shown in native Greek (with monotonic accentuation),
matching the AT Bundesland / HR macro region / HU borrégió / RO regiune
viticolă / BG винарски район convention — not gettext-translated.

The 9 macro wine regions:

  - Μακεδονία              Northern mainland — Naoussa, Goumenissa,
                              Amynteo, Πλαγιές Μελίτωνα, Καβάλα,
                              Δράμα, Φλώρινα, Κοζάνη, Σιάτιστα, …
  - Θράκη                  NE mainland — PGI Έβρος, PGI Ξάνθη,
                              PGI Ροδόπη, Αβδήρων, Ισμάρου, …
  - Θεσσαλία               Central-east mainland — Ραψάνη, Μεσενικόλα,
                              Αγχίαλος (north Magnesia),
                              Tyrnavos PGI, …
  - Ήπειρος                NW mainland — Zίτσα, PGI Ζίτσα variants,
                              Μέτσοβο, …
  - Στερεά Ελλάδα         Central mainland — PGIs of Αττική,
                              Βοιωτία, Ευβοία, Ληλάντιο Πεδίο,
                              Φωκίδα, …
  - Πελοπόννησος           Southern mainland — Νεμέα, Μαντινεία,
                              Πάτρα, Μαυροδάφνη Πατρών,
                              Μοσχάτο Πατρών, Μοσχάτος Ρίου Πάτρας,
                              Μονεμβασιά-Malvasia, …
  - Ιόνια Νησιά            Western islands — Ρομπόλα Κεφαλληνίας,
                              Μοσχάτος Κεφαλληνίας,
                              Μαυροδάφνη Κεφαλληνίας, Κέρκυρα, …
  - Νησιά Αιγαίου          Aegean islands — Σαντορίνη, Πάρος,
                              Malvasia Πάρος, Λήμνος, Μοσχάτος Λήμνου,
                              Ρόδος, Μοσχάτος Ρόδου, Σάμος, Χίος,
                              Λέσβος, Ικαρία, Άνδρος, …
  - Κρήτη                  Crete — Δαφνές, Αρχάνες, Πεζά, Σητεία,
                              Χάνδακας-Candia, Malvasia Σητείας,
                              Malvasia Χάνδακας-Candia, …

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re

REGIONS = (
    "Μακεδονία",
    "Θράκη",
    "Θεσσαλία",
    "Ήπειρος",
    "Στερεά Ελλάδα",
    "Πελοπόννησος",
    "Ιόνια Νησιά",
    "Νησιά Αιγαίου",
    "Κρήτη",
)


def _norm(s: str) -> str:
    """Greek-preserving normaliser. casefold + collapse whitespace,
    strip punctuation outside Greek / Latin / digit. Greek `casefold()`
    handles polytonic + monotonic diacritics consistently."""
    s = s.casefold()
    # Greek block U+0370-U+03FF + Greek extended U+1F00-U+1FFF
    s = re.sub(r"[^a-z0-9α-ωάέήίόύώϊϋΐΰ \-]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}

# Extra fuzzy aliases for the text scan — common alternative names
# and historical regional spellings.
_TEXT_ALIASES = {
    _norm("Κεντρική Μακεδονία"): "Μακεδονία",
    _norm("Δυτική Μακεδονία"): "Μακεδονία",
    _norm("Ανατολική Μακεδονία"): "Μακεδονία",
    _norm("Δυτική Στερεά"): "Στερεά Ελλάδα",
    _norm("Κεντρική Στερεά"): "Στερεά Ελλάδα",
    _norm("Αττική"): "Στερεά Ελλάδα",
    _norm("Επτάνησα"): "Ιόνια Νησιά",
    _norm("Κυκλάδες"): "Νησιά Αιγαίου",
    _norm("Δωδεκάνησα"): "Νησιά Αιγαίου",
    _norm("Β. Αιγαίου"): "Νησιά Αιγαίου",
    _norm("Ν. Αιγαίου"): "Νησιά Αιγαίου",
}
_CANON_BY_NORM.update(_TEXT_ALIASES)


# Curated file_number → αμπελουργική ζώνη, hand-verified against the
# Greek wine-law regional classification (EDOAO) + eAmbrosia. Populated
# for every PDO (33) at v1; PGIs are added incrementally as the audit
# flags `region=?` slugs.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Μακεδονία (Macedonia) — northern mainland PDOs (4)
    "PDO-GR-A1610": "Μακεδονία",     # Νάουσα (Naoussa)
    "PDO-GR-A1251": "Μακεδονία",     # Γουμένισσα (Goumenissa)
    "PDO-GR-A1395": "Μακεδονία",     # Αμύνταιο (Amynteo)
    "PDO-GR-A1096": "Μακεδονία",     # Πλαγιές Μελίτωνα (Slopes of Meliton)
    # Θεσσαλία (Thessaly) — central east (3)
    "PDO-GR-A0116": "Θεσσαλία",      # Ραψάνη (Rapsani)
    "PDO-GR-A1253": "Θεσσαλία",      # Μεσενικόλα (Mesenikola)
    "PDO-GR-A1484": "Θεσσαλία",      # Αγχίαλος (Anchialos)
    # Ήπειρος (Epirus) — NW (1)
    "PDO-GR-A1532": "Ήπειρος",       # Ζίτσα (Zitsa)
    # Πελοπόννησος (Peloponnese) — south mainland (7)
    "PDO-GR-A1554": "Πελοπόννησος",  # Μαντινεία (Mantinia)
    "PDO-GR-A1573": "Πελοπόννησος",  # Νεμέα (Nemea)
    "PDO-GR-A1239": "Πελοπόννησος",  # Πάτρα (Patra)
    "PDO-GR-A1048": "Πελοπόννησος",  # Μαυροδάφνη Πατρών
    "PDO-GR-A1087": "Πελοπόννησος",  # Μοσχάτο Πατρών
    "PDO-GR-A1316": "Πελοπόννησος",  # Μοσχάτος Ρίου Πάτρας
    "PDO-GR-A1533": "Πελοπόννησος",  # Μονεμβασία-Malvasia
    # Ιόνια Νησιά (Ionian Islands) — west islands (3)
    "PDO-GR-A1240": "Ιόνια Νησιά",  # Ρομπόλα Κεφαλληνίας
    "PDO-GR-A1055": "Ιόνια Νησιά",  # Μαυροδάφνη Κεφαλληνίας
    "PDO-GR-A1566": "Ιόνια Νησιά",  # Μοσχάτος Κεφαλληνίας
    # Νησιά Αιγαίου (Aegean Islands) — east+south islands (8)
    "PDO-GR-A1065": "Νησιά Αιγαίου", # Σαντορίνη (Santorini)
    "PDO-GR-A1570": "Νησιά Αιγαίου", # Πάρος (Paros)
    "PDO-GR-A1614": "Νησιά Αιγαίου", # Λήμνος (Limnos)
    "PDO-GR-A1432": "Νησιά Αιγαίου", # Μοσχάτος Λήμνου
    "PDO-GR-A1612": "Νησιά Αιγαίου", # Ρόδος (Rodos)
    "PDO-GR-A1567": "Νησιά Αιγαίου", # Μοσχάτος Ρόδου
    "PDO-GR-A1564": "Νησιά Αιγαίου", # Σάμος (Samos)
    "PDO-GR-A1607": "Νησιά Αιγαίου", # Malvasia Πάρος
    # Κρήτη (Crete) — Cretan PDOs (7)
    "PDO-GR-A1340": "Κρήτη",         # Αρχάνες (Arhanes)
    "PDO-GR-A1390": "Κρήτη",         # Δαφνές (Dafnes)
    "PDO-GR-A1401": "Κρήτη",         # Πεζά (Peza)
    "PDO-GR-A1613": "Κρήτη",         # Σητεία (Sitia)
    "PDO-GR-A1615": "Κρήτη",         # Χάνδακας-Candia
    "PDO-GR-A1617": "Κρήτη",         # Malvasia Χάνδακας-Candia
    "PDO-GR-A1608": "Κρήτη",         # Malvasia Σητείας
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
    """Resolve the wine region for one record. The curated file_number
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
