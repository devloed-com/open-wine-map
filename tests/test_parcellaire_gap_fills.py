"""INAO parcellaire gap fills: the checked-in pin table is well-formed and
every pinned commune sits in the record's aire; the fill helper draws a
donor's parcels inside the commune when it has some, the whole commune
otherwise, and leaves a stale pin alone."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import box, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.parcellaire_gaps import (  # noqa: E402
    DEFAULT_FILLS_PATH,
    HOW_COMMUNE,
    HOW_DONOR,
    FillSpec,
    apply_gap_fill,
    disclosure,
    load_gap_fills,
    parcel_gaps,
)

AIRES_CSV = ROOT / "raw" / "inao" / "aoc-aop-aires-communes.csv"
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"


def test_checked_in_pins_are_well_formed():
    pins = load_gap_fills()
    assert "cotes-du-rhone-villages" in pins
    for slug, spec in pins.items():
        assert spec.communes and all(len(c) == 5 and c.isdigit() for c in spec.communes), slug
        assert spec.reason.strip() and spec.source.strip(), slug
        assert spec.verified, slug
        assert slug not in spec.donors, slug


@pytest.mark.skipif(not AIRES_CSV.exists() or not EXTRACTED.exists(), reason="raw/ not present")
def test_every_pinned_commune_is_in_the_records_aire():
    with AIRES_CSV.open(encoding="latin-1") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    by_name: dict[str, set[str]] = {}
    for r in rows:
        by_name.setdefault(r["Aire géographique"], set()).add(r["CI"])
    for slug, spec in load_gap_fills().items():
        rec_path = EXTRACTED / f"{slug}.json"
        if not rec_path.exists():
            pytest.skip(f"{slug} not extracted")
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        aire = by_name.get(rec["name"], set())
        assert aire, (slug, rec["name"])
        missing = [c for c in spec.communes if c not in aire]
        assert not missing, (slug, missing)


def test_loader_rejects_a_bad_pin(tmp_path: Path):
    p = tmp_path / "pins.json"
    p.write_text(json.dumps({"x": {"communes": {"1234": "short"}, "reason": "r", "source": "s"}}))
    with pytest.raises(ValueError):
        load_gap_fills(p)
    p.write_text(json.dumps({"x": {"communes": {"12345": "ok"}, "reason": "", "source": "s"}}))
    with pytest.raises(ValueError):
        load_gap_fills(p)


def test_parcel_gaps_folds_unknown_codes():
    insee_idx = {"00001": {}, "00002": {}}
    gaps, unknown = parcel_gaps({"00001", "00002", "99999"}, {"00001"}, insee_idx)
    assert gaps == {"00002"}
    assert unknown == {"99999"}


def test_apply_gap_fill_donor_then_commune_and_stale():
    geom = box(0, 0, 1, 1)
    communes = {"00002": box(1, 0, 2, 1), "00003": box(2, 0, 3, 1), "00004": box(3, 0, 4, 1)}
    insee_idx = {c: mapping(g) for c, g in communes.items()}
    names = {"00002": "Deux", "00003": "Trois", "00004": "Quatre"}
    # Donor parcels inside commune 00002, reaching commune 00003's boundary
    # (a touching sliver): the coverage index says the donor has rows in
    # 00002 only, so 00003 is drawn whole, never as the sliver.
    donor = box(1.25, 0.25, 2.0, 0.75)
    spec = FillSpec(
        slug="rec", communes={"00002": "Deux", "00003": "Trois", "00004": "Quatre"},
        donors=["donor"], reason="r", source="s",
    )
    res = apply_gap_fill(
        spec, geom, {"00002", "00003", "00005"}, insee_idx, names,
        lambda s: donor if s == "donor" else None, lambda s: "Donor AOC",
        lambda s, c: s == "donor" and c == "00002",
    )
    by = {f["insee"]: f for f in res.filled}
    assert by["00002"]["how"] == HOW_DONOR and by["00002"]["donor"] == "Donor AOC"
    assert by["00003"]["how"] == HOW_COMMUNE and by["00003"]["donor"] == ""
    assert [s["insee"] for s in res.stale] == ["00004"]
    assert res.gaps == [{"insee": "00005", "name": "00005"}]
    assert res.geom.area == pytest.approx(1 + 0.375 + 1)
    assert shape(mapping(res.geom)).is_valid
    d = disclosure(res)
    assert d["geom_parcel_fill"] == [
        {"name": "Deux", "how": HOW_DONOR, "donor": "Donor AOC"},
        {"name": "Trois", "how": HOW_COMMUNE, "donor": ""},
    ]
    assert d["geom_parcel_gaps"] == ["00005"]


def test_default_pins_path_is_checked_in():
    assert DEFAULT_FILLS_PATH.exists()
