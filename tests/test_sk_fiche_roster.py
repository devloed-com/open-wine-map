"""A non-stub SK record whose EU single document § 7 names a few varieties
takes the register fiche's roster (augment/sk.py, 2026-11-07).

Stredoslovenská's single document (OJ C 122/2020) names Furmint alone in § 7;
the register's technical file lists ten main and thirty other varieties. The
card had carried one pill. The document's own variety stays principal, the
fiche's MAIN join it, its OTHER are the accessories; the roles overlay then
leaves the record alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import register_fiche  # noqa: E402
from _lib.augment import fiche_roles  # noqa: E402
from _lib.augment import sk as sk_augment  # noqa: E402
from _lib.augment._shared import _REGISTER_FICHE_ROSTER_BY_SLUG  # noqa: E402

FICHE_DIR = ROOT / "raw" / "sk" / "register-fiches-extracted"


def _fiche(main, other):
    details = [{"slug": s, "name": s.title(), "role": "principal", "colour": "blanc"} for s in main]
    details += [{"slug": s, "name": s.title(), "role": "accessory", "colour": "noir"} for s in other]
    return {"grapes": {"principal": list(main), "accessory": list(other), "details": details},
            "source": {"url": "https://ec.europa.eu/x/attachments/17675", "ref": "Ares(2013)1",
                       "attachment_uri": "17675"}}


def _record(principal, slug="stredoslovenska", stub=False):
    return {"country": "sk", "slug": slug, "stub": stub,
            "grapes": {"principal": list(principal), "accessory": [], "observation": [],
                       "details": [{"slug": s, "name": s, "role": "principal", "colour": ""}
                                   for s in principal]}}


@pytest.mark.parametrize("doc_n,fiche_n,wider", [(1, 40, True), (19, 40, True), (20, 40, False),
                                                  (3, 0, False), (0, 4, True)])
def test_wider_roster_rule(doc_n, fiche_n, wider):
    assert sk_augment.fiche_roster_is_wider(doc_n, fiche_n) is wider


def test_the_fiche_roster_joins_the_document_variety(monkeypatch):
    fiches = {("sk", "stredoslovenska"): _fiche(["riesling", "welschriesling"], ["andre", "devin"])}
    monkeypatch.setattr(register_fiche, "load_sidecar", lambda cc, slug: fiches.get((cc, slug)))
    _REGISTER_FICHE_ROSTER_BY_SLUG.clear()
    rec = _record(["furmint"])
    assert sk_augment.augment_sk_records_with_register_fiche([rec]) == 1
    assert rec["grapes"]["principal"] == ["furmint", "riesling", "welschriesling"]
    assert rec["grapes"]["accessory"] == ["andre", "devin"]
    assert [d["slug"] for d in rec["grapes"]["details"]] == ["furmint", "riesling", "welschriesling", "andre", "devin"]
    assert rec["grapes"]["details"][1]["source"] == "eambrosia-register-fiche"
    assert rec["register_fiche_roster"]["n_varieties"] == 4
    assert rec["register_fiche_roster"]["url"].endswith("/attachments/17675")
    assert _REGISTER_FICHE_ROSTER_BY_SLUG["stredoslovenska"]["n_document"] == 1
    # the roles overlay leaves a fiche-sourced roster alone
    assert fiche_roles.overlay(rec, fiches[("sk", "stredoslovenska")]) == (None, "fiche-roster")


def test_a_document_roster_near_the_fiche_s_size_a_stub_and_an_unsplit_fiche_are_left_alone(monkeypatch):
    fiches = {("sk", "a"): _fiche(["x", "y"], ["z"]), ("sk", "b"): _fiche(["x", "y"], ["z"]),
              ("sk", "c"): _fiche(["x", "y", "z"], [])}
    monkeypatch.setattr(register_fiche, "load_sidecar", lambda cc, slug: fiches.get((cc, slug)))
    recs = [_record(["x", "y"], slug="a"), _record(["q"], slug="b", stub=True), _record(["q"], slug="c")]
    assert sk_augment.augment_sk_records_with_register_fiche(recs) == 0
    assert all("register_fiche_roster" not in r for r in recs)
    assert recs[0]["grapes"]["principal"] == ["x", "y"]


@pytest.mark.skipif(not (FICHE_DIR / "stredoslovenska.json").exists(), reason="raw/sk fiches not on disk")
def test_stredoslovenska_takes_its_fiche_roster():
    rec = _record(["furmint"])
    assert sk_augment.augment_sk_records_with_register_fiche([rec]) == 1
    assert rec["grapes"]["principal"][0] == "furmint"
    assert len(rec["grapes"]["principal"]) == 11
    assert len(rec["grapes"]["accessory"]) == 30
    assert rec["register_fiche_roster"]["ref"] == "Ares(2013)3381798"
