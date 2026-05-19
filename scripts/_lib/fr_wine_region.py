"""FR appellation → wine-region bucket for the map filter/underlay.

INAO's comité régional BOURGOGNE bundles ~950 records spanning four
wine regions sommeliers see as distinct: Burgundy proper, Beaujolais,
Jura, Savoie, Bugey. The raw `comite_regional` value on each record
stays untouched (regulator data, preserved in the cahier-extracted
JSON); this helper is only consumed by stage 04 when emitting the MVT
`region` property used for the filter facet and underlay colour.

Other INAO bassins map 1:1 to a single wine region in sommelier usage
and pass through unchanged.
"""

from __future__ import annotations

from typing import Any

_JURA_SLUGS: frozenset[str] = frozenset({
    "arbois",
    "arbois-pupillin",
    "chateau-chalon",
    "cotes-du-jura",
    "cremant-du-jura",
    "l-etoile",
    "macvin-du-jura",
    "marc-du-jura",
})

_BEAUJOLAIS_CRU_SLUGS: frozenset[str] = frozenset({
    "brouilly",
    "chenas",
    "chiroubles",
    "cote-de-brouilly",
    "fleurie",
    "julienas",
    "morgon",
    "moulin-a-vent",
    "regnie",
    "saint-amour",
})

_SAVOIE_EXTRA_SLUGS: frozenset[str] = frozenset({
    "seyssel",
    "cremant-de-savoie",
    "marc-de-savoie",
    "mousseux-de-savoie",
})

_SAVOIE_PREFIXES: tuple[str, ...] = (
    "vin-de-savoie",
    "roussette-de-savoie",
)

_BUGEY_PREFIXES: tuple[str, ...] = (
    "bugey",
    "roussette-du-bugey",
)


def derive_wine_region(record: dict[str, Any]) -> str:
    """Return the wine-region bucket for an FR record.

    For BOURGOGNE-bassin records, splits into JURA / SAVOIE / BUGEY /
    BEAUJOLAIS / BOURGOGNE by slug rule. Non-BOURGOGNE bassins pass
    through. DGCs ride their parent's bucket via `parent_slug`.
    """
    bassin = record.get("comite_regional") or ""
    if bassin != "BOURGOGNE":
        return bassin
    slug = record.get("slug") or ""
    target = record.get("parent_slug") or slug
    if target in _JURA_SLUGS:
        return "JURA"
    if target.startswith(_BUGEY_PREFIXES):
        return "BUGEY"
    if target.startswith(_SAVOIE_PREFIXES) or target in _SAVOIE_EXTRA_SLUGS:
        return "SAVOIE"
    if target.startswith("beaujolais") or target in _BEAUJOLAIS_CRU_SLUGS:
        return "BEAUJOLAIS"
    return "BOURGOGNE"
