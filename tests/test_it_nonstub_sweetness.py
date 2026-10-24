"""The sweetness-only MASAF union for non-stub IT records (2026-10-24).

A documento unico that gives sugar thresholds without the words (Marsala,
C/2026/5127) states no sweetness; the disciplinare's Article 6 does. Only the
four sweetness levels cross over, only when the record carries none, and the
colours and categories of the sidecar never do.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.augment.it import SWEETNESS_STYLES, _backfill_it_nonstub_from_masaf  # noqa: E402


def _record(styles):
    return {
        "slug": "marsala", "stub": False, "styles": list(styles),
        "grapes": {"principal": ["grillo"], "accessory": [], "details": []},
        "link_to_terroir": "x" * 50, "geo_area_brief": "Trapani",
    }


def test_sweetness_crosses_when_the_record_has_none():
    rec = _record(["blanc", "noir", "vin-de-liqueur"])
    sidecar = {"styles": ["blanc", "dry", "noir", "rose", "sweet", "vin-de-liqueur"]}
    assert _backfill_it_nonstub_from_masaf(rec, sidecar) is True
    assert rec["styles"] == ["blanc", "dry", "noir", "sweet", "vin-de-liqueur"]
    assert rec["masaf_sweetness"] == ["dry", "sweet"]
    assert "rose" not in rec["styles"]


def test_a_stated_sweetness_keeps_the_eu_document_s():
    rec = _record(["blanc", "sweet"])
    assert _backfill_it_nonstub_from_masaf(rec, {"styles": ["blanc", "dry", "semi-sweet"]}) is False
    assert rec["styles"] == ["blanc", "sweet"]
    assert "masaf_sweetness" not in rec


def test_the_four_levels_only():
    assert SWEETNESS_STYLES == {"dry", "semi-dry", "semi-sweet", "sweet"}
