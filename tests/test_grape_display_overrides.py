"""The per-record grape display override table is complete and applies only
to grapes the record carries (parent entries inherited, stale ones dropped)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_display_overrides import (  # noqa: E402
    OVERRIDES_PATH,
    display_name_overrides,
    load_grape_display_overrides,
)


def test_checked_in_table_is_valid():
    table = load_grape_display_overrides()
    assert "haute-marne" in table
    for rec_slug, grapes in table.items():
        for g_slug, ent in grapes.items():
            assert ent["name"] == ent["name"].strip().lower(), (rec_slug, g_slug)


def test_apply_inherits_parent_and_drops_stale(tmp_path: Path, capsys):
    p = tmp_path / "o.json"
    p.write_text(json.dumps({
        "__doc__": "x",
        "parent": {"a": {"name": "a name", "reason": "r", "source": "s"},
                   "gone": {"name": "z", "reason": "r", "source": "s"}},
        "child": {"b": {"name": "b name", "reason": "r", "source": "s"},
                  "missing": {"name": "m", "reason": "r", "source": "s"}},
    }), encoding="utf-8")
    table = load_grape_display_overrides(p)
    got = display_name_overrides(table, "child", "parent", {"a", "b", "c"})
    assert got == {"a": "a name", "b": "b name"}
    err = capsys.readouterr().err
    assert "STALE override child/missing" in err
    assert "parent/gone" not in err  # a parent entry absent on the child is normal inheritance


def test_haute_marne_entry_targets_a_carried_grape():
    rec = ROOT / "raw" / "inao" / "cahier-extracted" / "haute-marne.json"
    if not rec.exists():
        return
    carried = {d["slug"] for d in json.load(rec.open())["grapes"]["details"]}
    table = load_grape_display_overrides(OVERRIDES_PATH)
    for g_slug in table["haute-marne"]:
        assert g_slug in carried, g_slug
