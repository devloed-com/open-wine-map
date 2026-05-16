"""Balearic island → list of GISCO INE municipi codes.

The 4 IGPs in the Baleares province (07) are island-wide:
  - Mallorca IGP   → "Toda la isla de Mallorca"
  - Menorca IGP    → "todos los municipios de la isla de Menorca"
  - Formentera IGP → "toda la isla de Formentera"
  - Ibiza IGP      → (currently a stub, no eAmbrosia URL)

GISCO LAU has no per-island column for the Baleares — all 67 municipios
share `CNTR_CODE=ES` and a `GISCO_ID` prefix of `ES_07`. We classify
them by centroid bbox: the four islands are well-separated by sea
channels at lng 3.5 and lat 38.8.

INE codes below were derived from the 2024 GISCO LAU snapshot
(`raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`) with bbox classification:

  Formentera (lat < 38.8)                         → 1 municipi
  Ibiza      (lng < 1.7 AND lat ≥ 38.8)           → 5 municipios
  Menorca    (lng > 3.5)                          → 8 municipios
  Mallorca   (otherwise: 1.7 ≤ lng ≤ 3.5)         → 53 municipios

If GISCO publishes new municipios (mergers / splits), regenerate by
re-running the classification routine in stage 04 — the bbox cuts
would still produce the same partition because Balearic island
boundaries are stable.
"""

from __future__ import annotations

# INE codes (the 5-digit GISCO_ID suffix after `ES_`) per Balearic island.
ISLAND_TO_INES: dict[str, frozenset[str]] = {
    "Mallorca": frozenset({
        "07001", "07003", "07004", "07005", "07006", "07007", "07008",
        "07009", "07010", "07011", "07012", "07013", "07014", "07016",
        "07017", "07018", "07019", "07020", "07021", "07022", "07025",
        "07027", "07028", "07029", "07030", "07031", "07033", "07034",
        "07035", "07036", "07038", "07039", "07040", "07041", "07042",
        "07043", "07044", "07045", "07047", "07049", "07051", "07053",
        "07055", "07056", "07057", "07058", "07059", "07060", "07061",
        "07062", "07063", "07065", "07901",
    }),
    "Menorca": frozenset({
        "07002", "07015", "07023", "07032", "07037", "07052", "07064",
        "07902",
    }),
    "Ibiza": frozenset({
        "07026", "07046", "07048", "07050", "07054",
    }),
    "Formentera": frozenset({
        "07024",
    }),
}

# Aliases so the parser can detect island mentions in any co-official
# spelling (Spanish, Catalan, English).
ISLAND_ALIASES: dict[str, str] = {
    "mallorca": "Mallorca",
    "menorca": "Menorca",
    "ibiza": "Ibiza",
    "eivissa": "Ibiza",
    "formentera": "Formentera",
    # Catalan/IGP wording variants
    "illa de mallorca": "Mallorca",
    "isla de mallorca": "Mallorca",
    "illa de menorca": "Menorca",
    "isla de menorca": "Menorca",
    "illa d eivissa": "Ibiza",
    "isla de ibiza": "Ibiza",
    "illa de formentera": "Formentera",
    "isla de formentera": "Formentera",
}


def island_for(name: str) -> str | None:
    """Return canonical island name for a raw mention, or None."""
    n = name.strip().lower()
    return ISLAND_ALIASES.get(n)


def ines_for_island(island: str) -> tuple[str, ...]:
    """Return the GISCO INE codes for an island. Empty tuple if unknown."""
    return tuple(sorted(ISLAND_TO_INES.get(island, ())))
