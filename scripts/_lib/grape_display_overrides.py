"""Per-record grape display-name overrides.

A grape pill shows the regulator's own spelling verbatim (`details[].name`),
with the VIVC prime name in brackets. When that surface is a *source*
defect — the Haute-Marne cahier drops a comma and the candidate comes out as
"petit grains blancs muscat ottonel" — the slug is folded by `GRAPE_ALIAS`
but the verbatim label still reads wrong. The checked-in table
`grape_display_overrides.json` (record slug → grape slug → {name, reason,
source}) replaces the label for that one record; sub-denominations inherit
their parent's entries. An entry whose grape slug the record no longer
carries is ignored with a loud STALE warning, never applied elsewhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OVERRIDES_PATH = Path(__file__).resolve().parent / "grape_display_overrides.json"

_REQUIRED = ("name", "reason", "source")


def load_grape_display_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict[str, dict]]:
    """`{record_slug: {grape_slug: {name, reason, source}}}` — validated, or
    an empty dict when the file is absent."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for rec_slug, grapes in data.items():
        if rec_slug.startswith("__"):
            continue
        if not isinstance(grapes, dict):
            raise ValueError(f"grape_display_overrides: {rec_slug!r} must map grape slugs")
        for g_slug, ent in grapes.items():
            if not isinstance(ent, dict) or any(not (ent.get(k) or "").strip() for k in _REQUIRED):
                raise ValueError(
                    f"grape_display_overrides: {rec_slug!r}/{g_slug!r} needs non-empty "
                    f"{', '.join(_REQUIRED)}"
                )
        out[rec_slug] = grapes
    return out


def display_name_overrides(
    overrides: dict[str, dict[str, dict]],
    record_slug: str,
    parent_slug: str | None,
    carried: set[str],
) -> dict[str, str]:
    """`{grape_slug: name}` to apply on one record: the parent's entries
    first, the record's own on top. Entries for a grape the record does not
    carry are dropped with a STALE warning on stderr."""
    out: dict[str, str] = {}
    for key in ((parent_slug or ""), record_slug):
        for g_slug, ent in (overrides.get(key) or {}).items():
            if g_slug not in carried:
                if key == record_slug:
                    print(
                        f"[grape-display] STALE override {key}/{g_slug}: the record no longer "
                        f"carries that grape — re-verify scripts/_lib/grape_display_overrides.json",
                        file=sys.stderr,
                    )
                continue
            out[g_slug] = ent["name"].strip()
    return out
