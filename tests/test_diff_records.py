"""scripts/diff_records.py — the per-record regression diff."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("diff_records", ROOT / "scripts" / "diff_records.py")
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)


def _rec(**kw):
    base = {"name": "A", "class_label": "AOC (PDO)", "region": "R", "country": "fr", "styles": ["red"],
            "grapes_principal": ["merlot"], "grapes_accessory": [], "geom_source": "parcellaire", "area": 1.0,
            "communes": 3, "facts_n": 2, "facts_sha": "x", "summary_sha": "", "source_urls": ["u"], "is_stub": False,
            "parent_slug": "", "children_n": 0}
    base.update(kw)
    return base


def test_diff_reports_added_removed_and_field_changes():
    a = {"records": {"a": _rec(), "b": _rec(name="B"), "gone": _rec()}}
    b = {"records": {"a": _rec(grapes_principal=["merlot", "cot"], area=1.01), "b": _rec(name="B", area=1.5), "new": _rec()}}
    d = dr.diff(a, b)
    assert d["added"] == ["new"] and d["removed"] == ["gone"]
    assert d["changed"]["a"]["fields"]["grapes_principal"] == {"added": ["cot"], "removed": []}
    assert "area" not in d["changed"]["a"]["fields"]  # within the 2 % tolerance
    assert d["changed"]["b"]["fields"]["area"]["ratio"] == 1.5
    md = dr.markdown(d)
    assert "`a` (fr): grapes_principal: +1 −0 (+cot)" in md and "×1.5" in md
