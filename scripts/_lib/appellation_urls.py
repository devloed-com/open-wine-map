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


def resolve(
    slug: str, parent_slug: str, region: str, data: dict
) -> dict | None:
    by_slug = data.get("by_slug", {})
    by_bassin = data.get("by_bassin", {})
    if slug and slug in by_slug:
        return by_slug[slug]
    if parent_slug and parent_slug in by_slug:
        return by_slug[parent_slug]
    if region and region in by_bassin:
        return by_bassin[region]
    return None
