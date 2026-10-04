"""Hand-curated interprofession / syndicat website URLs per appellation.

Resolves the "Site officiel de l'interprofession" link shown in the
sidepanel Sources block. Not derivable from INAO data — interprofessions
are private trade bodies with no machine-readable directory.

Resolution order (per AOC):
  1. by_slug[slug]            explicit per-appellation entry
  2. by_slug[parent_slug]     DGCs inherit the parent appellation's link
  3. by_bassin[region]        regional fallback (e.g. BIVB for all Burgundy)

Edit `appellation_urls.json` to add entries; no code change required.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "appellation_urls.json"


def load() -> dict:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


# Region keys whose body is a spirit interprofession: the only region
# fallback a spirit record may take (a Jura wine body on a cherry brandy, a
# South-West wine body on a Basque cider, is a wrong body — worse than none).
_SPIRIT_REGION_KEYS = frozenset({"COGNAC", "ARMAGNAC"})
# Product comités that are not region keys and name a body of their own.
_PRODUCT_COMITES = frozenset({"EAUX-DE-VIE DE CIDRE"})


def resolve(
    slug: str, parent_slug: str, region: str, data: dict, comite: str = "",
    is_wine: bool = True,
) -> dict | None:
    """by_slug (record, then parent; an explicit null means verified none) →
    by_bassin[region] → by_bassin[comité]. The FR `region` is a wine region
    since 2026-09-26 (BORDEAUX, ROUSSILLON, …), so `by_bassin` is keyed by
    those where a body is region-wide; a non-wine record takes a region body
    only when it is a spirit body; the raw INAO comité is tried last, and
    only for a product comité (the cider comité → IDAC) — never for a comité
    that is also a region key, which handed Whisky breton to the BNIC."""
    by_slug = data.get("by_slug", {})
    by_bassin = data.get("by_bassin", {})
    if slug and slug in by_slug:
        return by_slug[slug]
    if parent_slug and parent_slug in by_slug:
        return by_slug[parent_slug]
    if region and region in by_bassin and (is_wine or region in _SPIRIT_REGION_KEYS):
        return by_bassin[region]
    if comite and comite in _PRODUCT_COMITES and comite in by_bassin:
        return by_bassin[comite]
    return None
