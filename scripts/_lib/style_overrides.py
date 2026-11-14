"""Per-record style additions a curator read where the reader does not yet.

A reader states what the text states; where a country's reader has no rule
for a sentence yet, the style is simply missing. After the taxonomy change of
2026-11-14 (a liqueur wine is fortified, sweet only where its text says so)
that left Porto, Madeira and the French mistelles under "Fortified" alone:
the Porto caderno prints its sweetness grades as a table, Madeira's lists
"extra-seco; seco; meio-seco; meio-doce e doce", and neither is read by the
PT reader. The checked-in `style_overrides.json` adds those styles for the
one record until the reader does (record slug → `add`, `basis`, `evidence`,
`reason`, `source`, `verified`):

  basis "stated"  the record's own text names the level as a type of the
                  wine; every `evidence` quote is a verbatim passage of the
                  extracted record. The card states what the text states.
  basis "method"  the text names no level and the style follows from the
                  production method it lays down — a mistelle is grape must
                  fortified before it ferments, so the must's sugar is the
                  wine's. An interpretation: the entry carries a `disclose`
                  sentence in the four UI languages and the card prints it
                  under the style pills (the 2026-11-07 rule).

Sub-denominations inherit their parent's entry. An entry whose record
already carries every style it adds is STALE — the reader states it now —
and is reported on stderr; `tests/test_style_overrides.py` fails on it, so a
pin retires when its reader arrives. Never use the table to add a style no
public text supports, and never to remove one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .style_taxonomy import NODES

OVERRIDES_PATH = Path(__file__).resolve().parent / "style_overrides.json"

BASES = ("stated", "method")
LOCALES = ("en", "fr", "es", "nl")
_REQUIRED = ("country", "reason", "source", "verified")
_KNOWN_STYLES = frozenset(NODES)


def _filled(obj: object, keys: tuple[str, ...]) -> bool:
    return isinstance(obj, dict) and all(str(obj.get(k) or "").strip() for k in keys)


def _problem(ent: object) -> str:
    """What is wrong with one entry, or an empty string."""
    if not isinstance(ent, dict):
        return "must be an object"
    if not _filled(ent, _REQUIRED):
        return f"needs non-empty {', '.join(_REQUIRED)}"
    add = ent.get("add")
    if not isinstance(add, list) or not add:
        return "needs a non-empty `add` list"
    unknown = [s for s in add if s not in _KNOWN_STYLES]
    if unknown:
        return f"adds unknown style(s) {unknown}"
    if ent.get("basis") not in BASES:
        return f"needs `basis` in {BASES}"
    evidence = ent.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(
        _filled(ev, ("file", "field", "quote")) for ev in evidence
    ):
        return "needs `evidence` rows of file / field / quote"
    if ent["basis"] == "method" and not _filled(ent.get("disclose"), LOCALES):
        return f"is a `method` entry and discloses itself in {', '.join(LOCALES)}"
    if ent["basis"] == "stated" and ent.get("disclose"):
        return "is a `stated` entry and needs no `disclose` — the text says it"
    return ""


def load_style_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    """`{record_slug: entry}` — validated, or an empty dict when the file is
    absent."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for slug, ent in data.items():
        if slug.startswith("__"):
            continue
        problem = _problem(ent)
        if problem:
            raise ValueError(f"style_overrides: {slug!r} {problem}")
        out[slug] = ent
    return out


def style_additions(
    overrides: dict[str, dict], slug: str, parent_slug: str | None, carried: set[str],
) -> tuple[str, list[str]]:
    """`(entry key, styles to add)` for one record: its own entry, else its
    parent's. Empty when there is no entry or the record carries every style
    already; that case is STALE for the record's own entry and is said on
    stderr."""
    key = slug if slug in overrides else (parent_slug or "")
    ent = overrides.get(key)
    if not ent:
        return "", []
    add = [s for s in ent["add"] if s not in carried]
    if not add:
        if key == slug:
            print(
                f"[style-override] STALE {slug}: the record already carries "
                f"{', '.join(ent['add'])} — its reader states it now; drop the entry from "
                f"scripts/_lib/style_overrides.json",
                file=sys.stderr,
            )
        return "", []
    return key, add


def disclosure(overrides: dict[str, dict], key: str) -> dict[str, str] | None:
    """The `disclose` sentences of the entry `key` (per UI locale), or None
    for a `stated` entry."""
    return (overrides.get(key) or {}).get("disclose") or None
