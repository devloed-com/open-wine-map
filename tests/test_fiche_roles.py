"""Grape roles from the EU register fiche where the national source has none
(scripts/_lib/augment/fiche_roles.py, decision 2026-10-23 — validator phase E).

Membership stays the national roster; the fiche's MAIN / OTHER tags give the
roles; a card variety the fiche does not list is accessory and counted; the
overlay needs the fiche to cover the card's roster; a national source that
splits roles itself, a fiche without a split and CZ are left alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.augment import fiche_roles as fr  # noqa: E402
from _lib.augment._shared import _REGISTER_FICHE_ROLES_BY_SLUG  # noqa: E402


def _fiche(main, other, ref="Ares(2011)1"):
    return {
        "file_number": "PDO-XX-A0001",
        "source": {"url": "https://example.test/fiche.pdf", "ref": ref, "attachment_uri": "1"},
        "grapes": {"principal": list(main), "accessory": list(other)},
    }


def _record(principal, accessory=(), country="si", slug="x"):
    details = [{"slug": s, "name": s.title(), "role": "principal", "colour": "blanc"} for s in principal]
    details += [{"slug": s, "name": s.title(), "role": "accessory", "colour": "noir"} for s in accessory]
    return {"country": country, "slug": slug,
            "grapes": {"principal": list(principal), "accessory": list(accessory), "details": details}}


def test_fiche_role_sets_needs_both_tags():
    assert fr.fiche_role_sets(_fiche(["a"], ["b"])) == ({"a"}, {"b"})
    assert fr.fiche_role_sets(_fiche(["a", "b"], [])) is None
    assert fr.fiche_role_sets(_fiche([], ["b"])) is None
    assert fr.fiche_role_sets({}) is None
    # a slug tagged both ways is MAIN
    assert fr.fiche_role_sets(_fiche(["a"], ["a", "b"])) == ({"a"}, {"b"})


def test_overlay_gives_the_fiche_roles_and_counts_the_unlisted():
    rec = _record(["a", "b", "c", "d", "e"])
    prov, why = fr.overlay(rec, _fiche(["a", "b"], ["c", "d"]))
    assert why == "applied"
    assert rec["grapes"]["principal"] == ["a", "b"]
    assert rec["grapes"]["accessory"] == ["c", "d", "e"]
    assert {d["slug"]: d["role"] for d in rec["grapes"]["details"]} == {
        "a": "principal", "b": "principal", "c": "accessory", "d": "accessory", "e": "accessory"}
    assert (prov["n_main"], prov["n_other"], prov["n_unlisted"]) == (2, 2, 1)
    assert prov["coverage"] == 0.8 and prov["ref"] == "Ares(2011)1" and prov["url"]


def test_overlay_skips_a_fiche_that_covers_too_little_of_the_roster():
    rec = _record(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
    prov, why = fr.overlay(rec, _fiche(["a", "b"], ["c"]))
    assert prov is None and why == "coverage"
    assert rec["grapes"]["principal"] == list("abcdefghij") and rec["grapes"]["accessory"] == []


def test_overlay_leaves_a_national_role_split_alone():
    rec = _record(["a", "b"], accessory=["c"])
    prov, why = fr.overlay(rec, _fiche(["a"], ["b", "c"]))
    assert prov is None and why == "national-roles"
    assert rec["grapes"]["principal"] == ["a", "b"] and rec["grapes"]["accessory"] == ["c"]


def test_overlay_skips_a_fiche_without_a_split_or_without_a_main_variety_of_the_card():
    rec = _record(["a", "b"])
    assert fr.overlay(rec, _fiche(["a", "b"], []))[1] == "no-split"
    assert fr.overlay(rec, _fiche(["z"], ["a", "b"]))[1] == "no-main"
    assert fr.overlay({"country": "si", "slug": "x", "grapes": {}}, _fiche(["a"], ["b"]))[1] == "no-roster"
    assert rec["grapes"]["accessory"] == []


def test_apply_runs_on_the_listed_countries_only_and_records_provenance(monkeypatch):
    fiches = {("si", "ok"): _fiche(["a"], ["b"]), ("cz", "cz-one"): _fiche(["a"], ["b"]),
              ("si", "child"): _fiche(["a"], ["b"]), ("hr", "flat"): _fiche(["a", "b"], [])}
    monkeypatch.setattr(fr, "load_sidecar", lambda cc, slug: fiches.get((cc, slug)))
    _REGISTER_FICHE_ROLES_BY_SLUG.clear()
    records = [
        _record(["a", "b"], slug="ok"),
        _record(["a", "b"], country="cz", slug="cz-one"),
        dict(_record(["a", "b"], slug="child"), is_sub_denomination=True),
        _record(["a", "b"], country="hr", slug="flat"),
        _record(["a", "b"], country="fr", slug="no-fiche"),
    ]
    counts = fr.apply_register_fiche_roles(records)
    assert counts["applied"] == 1 and counts["pills_to_accessory"] == 1
    assert counts["skipped"] == {"no-split": 1}
    assert records[0]["register_fiche_roles"]["n_main"] == 1
    assert set(_REGISTER_FICHE_ROLES_BY_SLUG) == {"ok"}
    for r in records[1:]:
        assert "register_fiche_roles" not in r and r["grapes"]["accessory"] == []
