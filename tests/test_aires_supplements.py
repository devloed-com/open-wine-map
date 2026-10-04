"""INAO aires-CSV supplements: the checked-in pin table is well-formed, every
pinned commune is a current commune the CSV lacks (a pin the CSV has caught up
with is STALE and fails here), and `load_aires` folds the pins in."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.aires import (  # noqa: E402
    IGP_CSV,
    _normalize,
    apply_supplements,
    load_aire_supplements,
    load_aires,
    lookup,
)

COMMUNES = ROOT / "raw" / "ign" / "communes.geojson"
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"


def test_checked_in_pins_are_well_formed():
    pins = load_aire_supplements()
    assert "cevennes" in pins
    for slug, pin in pins.items():
        assert pin["aire"].strip() and pin["ida"].strip(), slug
        assert pin["communes"], slug
        for code in list(pin["communes"]) + list(pin.get("not_drawn", {})):
            assert len(code) == 5 and code.isdigit(), (slug, code)
        assert not set(pin["communes"]) & set(pin.get("not_drawn", {})), slug
        assert pin["reason"].strip() and pin["source"].strip() and pin["verified"], slug


def test_apply_adds_missing_and_reports_stale_and_unbound():
    aires = {"cevennes": {"2217": {"30007", "48004"}}}
    pins = {
        "cevennes": {"aire": "Cévennes", "ida": "2217", "communes": {"48004": "a", "48019": "b"}},
        "nowhere": {"aire": "Nulle part", "ida": "1", "communes": {"01001": "c"}},
    }
    report = {r["slug"]: r for r in apply_supplements(aires, pins)}
    assert aires["cevennes"]["2217"] == {"30007", "48004", "48019"}
    assert report["cevennes"]["added"] == ["48019"]
    assert report["cevennes"]["stale"] == ["48004"]
    assert report["nowhere"]["unbound"] and not report["nowhere"]["added"]
    assert "nullepart" not in aires


@pytest.mark.skipif(not IGP_CSV.exists(), reason="raw/ not present")
def test_no_pin_is_stale_or_unbound_against_the_csv():
    for row in apply_supplements(load_aires(supplements=False)):
        assert not row["unbound"], row["slug"]
        assert not row["stale"], (row["slug"], row["stale"])


@pytest.mark.skipif(not IGP_CSV.exists(), reason="raw/ not present")
def test_lookup_returns_the_supplemented_aire():
    aires, bare = load_aires(), load_aires(supplements=False)
    for slug, pin in load_aire_supplements().items():
        got = lookup(aires, pin["aire"])
        assert set(pin["communes"]) <= got, slug
        assert not set(pin.get("not_drawn", {})) & got, slug
        assert got - lookup(bare, pin["aire"]) == set(pin["communes"]), slug


@pytest.mark.skipif(not COMMUNES.exists() or not EXTRACTED.exists(), reason="raw/ not present")
def test_pinned_communes_are_current_communes_named_by_the_cahier():
    feats = json.loads(COMMUNES.read_text(encoding="utf-8"))["features"]
    names = {f["properties"]["code"]: f["properties"]["nom"] for f in feats}
    for slug, pin in load_aire_supplements().items():
        rec = json.loads((EXTRACTED / f"{slug}.json").read_text(encoding="utf-8"))
        assert rec["name"] == pin["aire"], slug
        zone = (rec.get("section_roles") or {}).get("aire", "")
        zone = _normalize(re.split(r"proximité\s+immédiate", zone)[0])
        for code, name in pin["communes"].items():
            assert names.get(code) == name, (slug, code, name)
            assert _normalize(name) in zone, (slug, name)
