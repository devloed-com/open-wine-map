"""The curator pins of scripts/_lib/drinks/areas.json: every pin quotes the
record's own area text, names units the layers carry, and says in the four
UI languages where its drawing departs from the letter."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.drinks import geometry as dg  # noqa: E402

EXTRACTED = ROOT / "raw" / "drinks" / "extracted"
AREAS = dg.load_areas()
UNIT_RE = re.compile(
    r"^(?:minus:)?(?:country:[a-z]{2}|nuts:[A-Z]{2}[0-9A-Z]{0,3}|lau:[A-Z]{2}:[^@=]+(?:@[A-Z]{2}[0-9A-Z]{1,3})?"
    r"|lauid:[A-Z]{2}:\d{2,8}=.+|uk:(?:country|county):[^=]+(?:=.+)?|ref:[a-z0-9-]+)$"
)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def test_the_table_is_not_empty() -> None:
    assert len(AREAS) > 100


@pytest.mark.parametrize("slug", sorted(AREAS))
def test_pin_is_well_formed(slug: str) -> None:
    pin = AREAS[slug]
    assert pin.get("units"), slug
    for unit in pin["units"]:
        assert UNIT_RE.match(unit), f"{slug}: {unit!r}"
    assert not all(u.startswith("minus:") for u in pin["units"]), slug
    assert _fold(pin.get("quote", "")), f"{slug}: no quote"
    date.fromisoformat(pin["verified"])
    if "disclose" in pin:
        assert set(pin["disclose"]) == {"en", "fr", "es", "nl"}, slug
        assert all(v.strip().endswith(".") for v in pin["disclose"].values()), slug
    assert set(pin) <= {"units", "quote", "quote_field", "note", "disclose", "largest_part",
                        "region", "verified"}, slug


@pytest.mark.parametrize("slug", sorted(AREAS))
def test_quote_is_in_the_record(slug: str) -> None:
    path = EXTRACTED / f"{slug}.json"
    if not path.exists():
        pytest.skip("raw/drinks/extracted is not on disk (raw/ is not checked in)")
    record = json.loads(path.read_text(encoding="utf-8"))
    pin = AREAS[slug]
    if pin.get("quote_field") == "sections":
        hay = _fold(" ".join(str(v) for v in (record.get("section_roles") or {}).values()))
    else:
        hay = _fold(record.get("geo_area_brief") or "")
    assert _fold(pin["quote"]) in hay, f"{slug}: quote not in the record's area text"


def test_every_unit_resolves_against_the_layers() -> None:
    if not (dg.NUTS3_PATH.exists() and dg.NUTS2_PATH.exists() and dg.LAU_ZIP.exists()
            and (dg.ONS_DIR / "countries.geojson").exists()):
        pytest.skip("the GISCO / ONS layers are not on disk")
    geometry = dg.DrinksGeometry(areas={})
    bad = {}
    for slug, pin in AREAS.items():
        out = geometry.resolve_units([u for u in pin["units"] if "ref:" not in u])
        if out.unresolved:
            bad[slug] = out.unresolved
    assert not bad, bad


def test_referenced_records_exist() -> None:
    refs = {u.split(":", 1)[1]: slug for slug, pin in AREAS.items() for u in pin["units"]
            if u.startswith("ref:")}
    assert refs
    index = ROOT / "wiki" / "_index.json"
    if not index.exists():
        pytest.skip("wiki/_index.json is not on disk")
    data = json.loads(index.read_text(encoding="utf-8"))
    known = set(data) if isinstance(data, dict) else {e.get("slug") for e in data}
    if "aocs" in data and isinstance(data["aocs"], (dict, list)):
        aocs = data["aocs"]
        known = set(aocs) if isinstance(aocs, dict) else {e.get("slug") for e in aocs}
    missing = {ref: slug for ref, slug in refs.items() if ref not in known}
    assert not missing, missing
