"""Derive the Belgian wine region for a wine GI.

Belgium's wine corpus splits cleanly along its language-community
boundary: the 5 Flemish wines (3 PDOs + 2 PGIs) sit in `Vlaanderen`,
the 4 Walloon wines sit in `Wallonië` (Dutch spelling, used as the
native label across the map UI for Vlaanderen-Wallonië parity). The
cross-border Maasvallei Limburg PDO sits in `Vlaanderen` (it is the
Belgian Limburg / Dutch Limburg wine area; the BE side dominates the
appellation territory and brand).

The region drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). Region labels follow the
AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK/CZ convention — shown in their
native form, not gettext-translated.
"""

from __future__ import annotations

REGIONS = (
    "Vlaanderen",
    "Wallonië",
)


# Curated file_number → region, hand-verified against eAmbrosia + the
# Belgian wine-law region structure (Flemish vs Walloon).
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Flemish DOPs (Dutch-language source)
    "PDO-BE-A1492": "Vlaanderen",          # Haspengouwse wijn
    "PDO-BE-A1499": "Vlaanderen",          # Hagelandse wijn
    "PDO-BE-A1426": "Vlaanderen",          # Heuvellandse wijn
    # Flemish PGI + sparkling-quality PDO (Dutch-language source)
    "PGI-BE-A1429": "Vlaanderen",          # Vlaamse landwijn
    "PDO-BE-A1430": "Vlaanderen",          # Vlaamse mousserende kwaliteitswijn
    # Walloon wines (French-language source)
    "PDO-BE-A0009": "Wallonië",            # Côtes de Sambre et Meuse
    "PGI-BE-A0010": "Wallonië",            # Vin de pays des jardins de Wallonie
    "PDO-BE-A0011": "Wallonië",            # Vin mousseux de qualité de Wallonie
    "PDO-BE-A0012": "Wallonië",            # Crémant de Wallonie
    # Cross-border BE+NL PDO, BE-primary by file_number ordering. Sits in
    # the Belgian Limburg Maas valley; ships on the BE side. NL will alias
    # it when country #17 lands.
    "PDO-BE+NL-02172": "Vlaanderen",       # Maasvallei Limburg
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def derive_region(record: dict, *_text_candidates: str) -> str:
    """Resolve the wine region for one BE record. Belgium's wine-region
    split is unambiguous (Vlaamse vs Walloon community), so the curated
    file_number map is authoritative; the text scan is unused."""
    if record.get("region"):
        return record["region"]
    return region_for_file_number(record.get("file_number", ""))
