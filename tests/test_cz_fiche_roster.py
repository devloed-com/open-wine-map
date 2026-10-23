"""A CZ record whose EU-register single document (fiche technique) names the
appellation's own varieties takes that roster, not the national decree's list.

VOC Znojmo's fiche § 6 names three white varieties; the card had listed the
decree's 67, reds included (visitor flag 2026-10-22). A podoblast fiche
reproduces the decree's list of its day and keeps the decree's roster.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.augment import cz as cz_augment  # noqa: E402
from _lib.augment._shared import _CZ_FICHE_ROSTER_BY_SLUG, _CZ_NATIONAL_SPEC_BY_SLUG  # noqa: E402

FICHE_DIR = ROOT / "raw" / "cz" / "register-fiches-extracted"
SPEC_DIR = ROOT / "raw" / "cz" / "national-specs"


@pytest.mark.parametrize(
    "fiche_n,national_n,own",
    [(3, 67, True), (5, 67, True), (33, 67, True), (34, 67, False), (55, 67, False), (0, 67, False), (3, 0, False)],
)
def test_own_roster_rule(fiche_n, national_n, own):
    assert cz_augment.fiche_roster_is_own(fiche_n, national_n) is own


@pytest.mark.skipif(
    not (FICHE_DIR / "znojmo.json").exists() or not (SPEC_DIR / "varieties.json").exists(),
    reason="raw/cz caches not on disk",
)
def test_znojmo_takes_the_fiche_roster_and_the_podoblast_keeps_the_decree():
    records = [
        {"country": "cz", "slug": "znojmo", "region": "Morava"},
        {"country": "cz", "slug": "znojemska", "region": "Morava"},
    ]
    assert cz_augment.augment_cz_records_with_national_specs(records) == 2
    znojmo, znojemska = records
    assert znojmo["grapes"]["principal"] == ["gruner-veltliner", "sauvignon", "riesling"]
    assert znojmo["grapes"]["accessory"] == []
    assert {d["colour"] for d in znojmo["grapes"]["details"]} == {"blanc"}
    assert znojmo["styles"] == ["white"]
    assert znojmo["register_fiche_roster"]["n_varieties"] == 3
    assert znojmo["register_fiche_roster"]["url"].endswith("/attachments/17135")
    assert "national_spec" not in znojmo
    assert _CZ_FICHE_ROSTER_BY_SLUG["znojmo"]["n_varieties"] == 3
    assert "znojmo" not in _CZ_NATIONAL_SPEC_BY_SLUG
    assert len(znojemska["grapes"]["principal"]) > 60
    assert "register_fiche_roster" not in znojemska
    assert znojemska["national_spec"]["n_varieties"] == 67


@pytest.mark.skipif(
    not (FICHE_DIR / "sobes.json").exists() or not (SPEC_DIR / "varieties.json").exists(),
    reason="raw/cz caches not on disk",
)
def test_sobes_closed_roster_and_litomericka_open_roster():
    """The 2011 template (section 6 "Hrozny" in a./b./c. blocks): Šobes names
    eight main varieties and Pálava under b. only, and no "other varieties"
    clause; Litoměřická names nineteen and opens the roster to every
    EU-recognised variety, so the decree's remainder is its accessory list."""
    records = [
        {"country": "cz", "slug": "sobes", "region": "Morava"},
        {"country": "cz", "slug": "litomericka", "region": "Čechy"},
        {"country": "cz", "slug": "mikulovska", "region": "Morava"},
    ]
    cz_augment.augment_cz_records_with_national_specs(records)
    sobes, litomericka, mikulovska = records
    assert len(sobes["grapes"]["principal"]) == 8
    assert "gruner-veltliner" in sobes["grapes"]["principal"]
    assert sobes["grapes"]["accessory"] == ["palava"]
    assert sobes["register_fiche_roster"]["n_varieties"] == 8
    assert "national_spec" not in sobes
    national = set(mikulovska["grapes"]["principal"])
    assert len(litomericka["grapes"]["principal"]) == 19
    assert set(litomericka["grapes"]["principal"]) <= national
    assert set(litomericka["grapes"]["accessory"]) == national - set(litomericka["grapes"]["principal"])
    assert litomericka["register_fiche_roster"]["n_varieties"] == 19
