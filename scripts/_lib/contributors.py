"""The people thanked in the About dialog: the names visitors gave to be
credited for a report (the `credit` of `Feedback Note`, or an e-mail), as the
curator entered them in contributors.json at triage. Nothing a visitor types
reaches the page any other way."""
from __future__ import annotations

import json
from pathlib import Path

CONTRIBUTORS_PATH = Path(__file__).with_name("contributors.json")
NAME_MAX = 60
VIA = ("card", "email")


def load_contributors(path: Path = CONTRIBUTORS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("contributors", [])


def contributor_names(path: Path = CONTRIBUTORS_PATH) -> list[str]:
    """Each name once, whitespace-collapsed, in alphabetical order."""
    names = {" ".join(str(r.get("name", "")).split()) for r in load_contributors(path)}
    return sorted((n for n in names if n), key=str.casefold)
