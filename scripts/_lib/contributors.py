"""The people thanked in the About dialog: the names visitors gave to be
credited for a report (the `credit` of `Feedback Note`, an e-mail, or a GitHub
comment), as the curator entered them in contributors.json at triage. Nothing a
visitor types reaches the page any other way, and a link only as the `url` the
curator sets — the public profile the person is known by there."""
from __future__ import annotations

import json
import re
from pathlib import Path

CONTRIBUTORS_PATH = Path(__file__).with_name("contributors.json")
NAME_MAX = 60
VIA = ("card", "email", "github")
# An https URL with no whitespace, quote or angle bracket: safe in an href.
URL_RE = re.compile(r"https://[^\s\"'<>]+")


def load_contributors(path: Path = CONTRIBUTORS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("contributors", [])


def contributor_credits(path: Path = CONTRIBUTORS_PATH) -> list[tuple[str, str | None]]:
    """(name, url or None), each name once, whitespace-collapsed, in alphabetical
    order. A url that is not a plain https URL is dropped, never rendered."""
    by_name: dict[str, str | None] = {}
    for row in load_contributors(path):
        name = " ".join(str(row.get("name", "")).split())
        if not name:
            continue
        url = str(row.get("url") or "").strip()
        url = url if URL_RE.fullmatch(url) else None
        by_name[name] = by_name.get(name) or url
    return sorted(by_name.items(), key=lambda kv: kv[0].casefold())


def contributor_names(path: Path = CONTRIBUTORS_PATH) -> list[str]:
    """Each name once, whitespace-collapsed, in alphabetical order."""
    return [name for name, _ in contributor_credits(path)]
