"""Derive the Croatian wine region (vinogorje / vinorodno područje) for a wine GI.

Croatian wine law (Zakon o vinu) divides the country into 3 macro wine
regions that themselves appear as PDOs in eAmbrosia:

  - Primorska Hrvatska (coastal Croatia)
  - Istočna kontinentalna Hrvatska (eastern continental Croatia)
  - Zapadna kontinentalna Hrvatska (western continental Croatia)

Each of the other 15 PDOs sits inside exactly one of these. The region
drives stage 03 (wiki frontmatter) and stage 04 (panel header + region
facet filter). Region labels follow the AT / IT / ES / SI convention —
shown in their native form, not gettext-translated.

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re
import unicodedata

# The 3 Croatian macro wine regions (canonical Croatian spelling).
REGIONS = (
    "Primorska Hrvatska",
    "Istočna kontinentalna Hrvatska",
    "Zapadna kontinentalna Hrvatska",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}


# Curated file_number → region, hand-verified against eAmbrosia + the
# Croatian wine-law region structure (3 macro regions each containing
# sub-region PDOs).
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Primorska Hrvatska (coastal): the macro region + its sub-region PDOs
    "PDO-HR-A1658": "Primorska Hrvatska",     # Primorska Hrvatska
    "PDO-HR-A1652": "Primorska Hrvatska",     # Hrvatska Istra
    "PDO-HR-A1650": "Primorska Hrvatska",     # Hrvatsko primorje
    "PDO-HR-A1659": "Primorska Hrvatska",     # Sjeverna Dalmacija
    "PDO-HR-A1661": "Primorska Hrvatska",     # Srednja i Južna Dalmacija
    "PDO-HR-A1648": "Primorska Hrvatska",     # Dalmatinska zagora
    "PDO-HR-A1649": "Primorska Hrvatska",     # Dingač (Pelješac position)
    "PDO-HR-02109": "Primorska Hrvatska",     # Muškat momjanski (Istria)
    "PDO-HR-02087": "Primorska Hrvatska",     # Ponikve (Pelješac)
    # Istočna kontinentalna Hrvatska (eastern continental)
    "PDO-HR-A1651": "Istočna kontinentalna Hrvatska",  # Istočna kontinentalna Hrvatska
    "PDO-HR-A1660": "Istočna kontinentalna Hrvatska",  # Slavonija
    "PDO-HR-A1655": "Istočna kontinentalna Hrvatska",  # Hrvatsko Podunavlje
    # Zapadna kontinentalna Hrvatska (western continental)
    "PDO-HR-A1663": "Zapadna kontinentalna Hrvatska",  # Zapadna kontinentalna Hrvatska
    "PDO-HR-A1653": "Zapadna kontinentalna Hrvatska",  # Moslavina
    "PDO-HR-A1654": "Zapadna kontinentalna Hrvatska",  # Plešivica
    "PDO-HR-A1656": "Zapadna kontinentalna Hrvatska",  # Pokuplje
    "PDO-HR-A1657": "Zapadna kontinentalna Hrvatska",  # Prigorje-Bilogora
    "PDO-HR-A1662": "Zapadna kontinentalna Hrvatska",  # Zagorje – Međimurje
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
