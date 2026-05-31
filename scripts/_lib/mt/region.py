"""MT region facet — the Maltese archipelago's two wine islands.

Malta's corpus is three wine GIs:

  - Malta PDO          (PDO-MT-A1630) → region "Malta"   (the main island)
  - Gozo PDO           (PDO-MT-A1629) → region "Gozo"    (Maltese: Għawdex)
  - Maltese Islands PGI (PGI-MT-A1631) → region "Maltese Islands"
    (the whole archipelago — the PGI umbrella over both PDOs)

Region labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK/CZ/NL
convention — shown in their native form, not gettext-translated.
"""

from __future__ import annotations

_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-MT-A1630": "Malta",
    "PDO-MT-A1629": "Gozo",
    "PGI-MT-A1631": "Maltese Islands",
}


def derive_region(record: dict) -> str:
    fn = (record.get("file_number") or "").strip()
    return _REGION_BY_FILE_NUMBER.get(fn, "Maltese Islands")
