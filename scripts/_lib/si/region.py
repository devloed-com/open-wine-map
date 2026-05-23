"""Derive the Slovenian vinorodna dežela (wine region) for a wine GI.

Slovenia has 3 vinorodne dežele (wine regions): Podravje, Posavje and
Primorska. They are also the 3 Slovenian wine PGIs. The 14 PDOs each sit
inside exactly one region (most are vinorodni okoliši — wine districts —
or traditional-name PDOs tied to one district).

The region drives stage 03 (wiki frontmatter) and stage 04 (panel header
+ region facet filter). Region labels follow the AT/IT/ES convention —
shown in their native form, not gettext-translated.

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re
import unicodedata

# The 3 Slovenian wine regions (canonical Slovenian spelling).
REGIONS = (
    "Podravje",
    "Posavje",
    "Primorska",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}


# Curated file_number → region, hand-verified against eAmbrosia + the
# Slovenian wine-law district structure (the 3 PGIs are the regions
# themselves).
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Podravje
    "PDO-SI-A0639": "Podravje",   # Štajerska Slovenija
    "PDO-SI-A0769": "Podravje",   # Prekmurje
    "PGI-SI-A0995": "Podravje",   # Podravje (PGI)
    # Posavje
    "PDO-SI-A0772": "Posavje",    # Bizeljsko Sremič
    "PDO-SI-A0871": "Posavje",    # Dolenjska
    "PDO-SI-A0878": "Posavje",    # Bela krajina
    "PDO-SI-A1520": "Posavje",    # Bizeljčan
    "PDO-SI-A1561": "Posavje",    # Cviček
    "PDO-SI-A1576": "Posavje",    # Belokranjec
    "PDO-SI-A1579": "Posavje",    # Metliška črnina
    "PGI-SI-A1061": "Posavje",    # Posavje (PGI)
    # Primorska
    "PDO-SI-A0270": "Primorska",  # Goriška Brda
    "PDO-SI-A0448": "Primorska",  # Vipavska dolina
    "PDO-SI-A0616": "Primorska",  # Kras
    "PDO-SI-A0609": "Primorska",  # Slovenska Istra
    "PDO-SI-A1581": "Primorska",  # Teran
    "PGI-SI-A1094": "Primorska",  # Primorska (PGI)
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
    """Resolve the vinorodna dežela for one record. The curated
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
