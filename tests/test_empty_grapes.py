"""Guard: the empty-grape-list classifier (stage-04 warning + audit_empty_grapes).

The classification itself is pinned on a synthetic corpus so it cannot drift;
the second test runs it on the real build when one is present (wiki/ is
gitignored, so CI skips it) and asserts only that the INHERIT bucket — a pure
stage-04 defect, never a source gap — stays at its known size or shrinks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_gaps import classify, load_overrides, summary_line  # noqa: E402


def _rec(**kw):
    base = {"country": "fr", "kind": "AOC", "is_wine": True, "is_sub_denomination": False,
            "parent_slug": "", "is_stub": False, "grapes_principal": [], "grapes_accessory": [],
            "grapes_all": []}
    base.update(kw)
    return base


def test_classify_buckets():
    aocs = {
        "full": _rec(grapes_principal=["merlot"]),
        "gap": _rec(),
        "gap-child": _rec(is_sub_denomination=True, parent_slug="gap"),
        "inherit": _rec(is_sub_denomination=True, parent_slug="full"),
        "reviewed": _rec(country="be", kind="IGP"),
        "stub": _rec(is_stub=True),
        "cider": _rec(kind="EDV", is_wine=False),
    }
    b = classify(aocs, {"reviewed": {"reason": "no variety named"}})
    assert [r["slug"] for r in b["FLAGGED"]] == ["gap"]
    assert b["FLAGGED"][0]["children"] == 1
    assert [r["slug"] for r in b["INHERIT"]] == ["inherit"]
    assert [r["slug"] for r in b["REVIEWED"]] == ["reviewed"]
    assert [r["slug"] for r in b["STUB"]] == ["stub"]
    assert [r["slug"] for r in b["NON-WINE"]] == ["cider"]
    assert "FLAGGED=1 parents (+1 sub-denominations" in summary_line(b)


def test_overrides_file_is_well_formed():
    ov = load_overrides()
    for slug, entry in ov.items():
        assert entry.get("reason") and entry.get("source"), slug


@pytest.mark.skipif(not list((ROOT / "wiki" / "data").glob("aocs.en.*.js")), reason="no stage-04 build")
def test_current_build_inherit_bucket_does_not_grow():
    from audit_empty_grapes import load_aocs  # noqa: E402

    b = classify(load_aocs(), load_overrides())
    # A sub-denomination must never render fewer grapes than its parent
    # (the 12 Valais grands crus did until 2026-09-20).
    assert not b["INHERIT"], [r["slug"] for r in b["INHERIT"]]
    assert all(isinstance(r["children"], int) for r in b["FLAGGED"])
    assert json.dumps(b)  # serialisable for --json
