"""Derive the Dutch wine region (province) for a wine GI.

The Netherlands has no wine-law-defined macro wine regions like France's
bassins or Germany's Anbaugebiete — instead, the 12 PGIs ARE the 12
provinces, and each PDO sits in exactly one province. So the region
facet for NL is the province name, surfaced verbatim in Dutch.

The region drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). Region labels follow the
AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK/CZ/BE convention — shown in their
native Dutch form, not gettext-translated.
"""

from __future__ import annotations

# All 12 Dutch provinces, native Dutch spelling.
REGIONS = (
    "Limburg",
    "Gelderland",
    "Zeeland",
    "Noord-Brabant",
    "Zuid-Holland",
    "Noord-Holland",
    "Utrecht",
    "Overijssel",
    "Flevoland",
    "Drenthe",
    "Groningen",
    "Friesland",
)


# Curated file_number → province, hand-verified against eAmbrosia + the
# province each PDO sits in.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # 12 province-wide PGIs (each is exactly its province)
    "PGI-NL-A0961": "Limburg",
    "PGI-NL-A0962": "Gelderland",
    "PGI-NL-A0963": "Zeeland",
    "PGI-NL-A0964": "Noord-Brabant",
    "PGI-NL-A0965": "Zuid-Holland",
    "PGI-NL-A0966": "Noord-Holland",
    "PGI-NL-A0967": "Utrecht",
    "PGI-NL-A0968": "Overijssel",
    "PGI-NL-A0380": "Flevoland",
    "PGI-NL-A0969": "Drenthe",
    "PGI-NL-A0970": "Groningen",
    "PGI-NL-A0972": "Friesland",
    # 10 NL PDOs (and 1 cross-border BE+NL — but that one ships on the
    # BE side as `PDO-BE+NL-02172`; NL skips it)
    "PDO-NL-02114": "Limburg",          # Mergelland (Zuid-Limburg)
    "PDO-NL-02168": "Limburg",          # Vijlen (Zuid-Limburg)
    "PDO-NL-02230": "Gelderland",       # Oolde (Lochem)
    "PDO-NL-02169": "Overijssel",       # Ambt Delden (Hof van Twente)
    "PDO-NL-02402": "Gelderland",       # Achterhoek - Winterswijk
    "PDO-NL-02774": "Gelderland",       # Rivierenland
    "PDO-NL-02775": "Zeeland",          # Schouwen-Duiveland
    "PDO-NL-02776": "Limburg",          # De Voerendaalse Bergen
    "PDO-NL-02873": "Overijssel",       # Twente
}


def region_for_file_number(file_number: str) -> str:
    """Curated region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def derive_region(record: dict, *_text_candidates: str) -> str:
    """Resolve the province for one NL record. The curated file_number
    map is authoritative — every NL wine maps to exactly one province."""
    if record.get("region"):
        return record["region"]
    return region_for_file_number(record.get("file_number", ""))
