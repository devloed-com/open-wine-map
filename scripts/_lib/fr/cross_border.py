"""French records whose delimited area crosses the border.

A GI France shares with a neighbour stays one record (the Maasvallei rule:
one slug, one polygon, listed under every country it spans). INAO's cahier is
the document in the build, so the record is French; the checked-in
`cross_border_areas.json` gives it the other countries (`country_aliases`,
written on the record by stage 02) and the units of the foreign part, drawn
by stage 04 beside the French communes and named on the card. Each entry
quotes the sentence of the zone section it reads (`tests/test_fr_cross_border.py`
checks the quote against the record and the units against the NUTS layer) and,
where the drawing is coarser than the letter, says so in the four UI languages
(`disclose`).
"""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("cross_border_areas.json")


def load(path: Path = PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}
