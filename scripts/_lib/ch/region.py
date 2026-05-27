"""Swiss wine-region facet — 6 regions per Swiss Wine Promotion.

Switzerland groups its 23 wine-producing cantons into 6 wine regions
(Swiss Wine Promotion, the national wine-marketing body):

  - Valais          (canton VS alone — biggest producer, ~40 % national)
  - Vaud            (canton VD alone)
  - Genève          (canton GE alone)
  - Trois-Lacs      (NE + BE/Lac de Bienne + FR/Vully — the lake region
                     straddling 3 cantons)
  - Ticino          (canton TI alone)
  - Deutschschweiz  (the 17 German-speaking cantons + Romansh GR)

Each AOC maps to exactly one wine region via its primary canton (or via
the intercantonal duplicate's primary side, for Vully and Zürichsee).
Region labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE convention —
shown in the native form (here: French and German labels per Swiss
Wine Promotion's own usage), not gettext-translated.

The facet drives stage 03 (wiki frontmatter) and stage 04 (panel header
+ region filter). Mirrors `_lib/at/region.py`, `_lib/de/region.py`.
"""

from __future__ import annotations

# Canonical wine-region labels — Swiss Wine Promotion conventions.
WINE_REGIONS: tuple[str, ...] = (
    "Valais",
    "Vaud",
    "Genève",
    "Trois-Lacs",
    "Ticino",
    "Deutschschweiz",
)

# canton code → wine region
_REGION_BY_CANTON: dict[str, str] = {
    "vs": "Valais",
    "vd": "Vaud",
    "ge": "Genève",
    "ne": "Trois-Lacs",
    "fr": "Trois-Lacs",   # FR wine = Cheyres + Vully fribourgeois
    "be": "Trois-Lacs",   # BE wine = Bielersee + Thunersee + Lac de Bienne
    "ti": "Ticino",
    # Deutschschweiz — the 17 German-speaking cantons + Romansh GR
    "ag": "Deutschschweiz",
    "ai": "Deutschschweiz",
    "ar": "Deutschschweiz",
    "bl": "Deutschschweiz",
    "bs": "Deutschschweiz",
    "gl": "Deutschschweiz",
    "gr": "Deutschschweiz",
    "ju": "Trois-Lacs",   # JU has 1 AOC; geographically near the Trois-Lacs
    "lu": "Deutschschweiz",
    "nw": "Deutschschweiz",
    "ow": "Deutschschweiz",
    "sg": "Deutschschweiz",
    "sh": "Deutschschweiz",
    "so": "Deutschschweiz",
    "sz": "Deutschschweiz",
    "tg": "Deutschschweiz",
    "ur": "Deutschschweiz",
    "zg": "Deutschschweiz",
    "zh": "Deutschschweiz",
}


def region_for_canton(canton: str) -> str:
    """Swiss wine region for the given canton code, or 'Schweiz' if unknown."""
    return _REGION_BY_CANTON.get((canton or "").lower(), "Schweiz")


def derive_region(record: dict) -> str:
    """Resolve the wine region for one CH record. The canton is
    authoritative — a CH record always carries `canton` after stage 02."""
    if record.get("region"):
        return record["region"]
    return region_for_canton(record.get("canton") or "")
