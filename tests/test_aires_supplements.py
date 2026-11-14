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
        # a pin decides something: communes to add, rows to remove, or communes
        # the cahier names and that are deliberately not drawn (Armagnac)
        assert pin["communes"] or pin.get("remove") or pin.get("not_drawn"), slug
        for key in ("communes", "not_drawn", "remove"):
            for code in pin.get(key, {}):
                assert len(code) == 5 and code[2:].isdigit(), (slug, code)
        assert not set(pin["communes"]) & set(pin.get("not_drawn", {})), slug
        assert not set(pin["communes"]) & set(pin.get("remove", {})), slug
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


def test_apply_removes_a_row_the_cahier_does_not_list():
    """INAO's rows carry Gignac (84048) where the cahier lists Gigondas
    (84049): the pin adds the one and removes the other; a row to remove that
    the CSV no longer carries is reported, not an error."""
    aires = {"marc": {"7": {"84048", "84004"}}}
    pins = {"marc": {"aire": "Marc", "ida": "7", "communes": {"84049": "Gigondas"},
                     "remove": {"84048": "Gignac", "84999": "gone"}}}
    (row,) = apply_supplements(aires, pins)
    assert aires["marc"]["7"] == {"84004", "84049"}
    assert row["added"] == ["84049"] and row["removed"] == ["84048"]
    assert row["stale_remove"] == ["84999"] and not row["stale"]


@pytest.mark.skipif(not IGP_CSV.exists(), reason="raw/ not present")
def test_no_pin_is_stale_or_unbound_against_the_csv():
    for row in apply_supplements(load_aires(supplements=False)):
        assert not row["unbound"], row["slug"]
        assert not row["stale"], (row["slug"], row["stale"])
        assert not row["stale_remove"], (row["slug"], row["stale_remove"])


@pytest.mark.skipif(not IGP_CSV.exists(), reason="raw/ not present")
def test_lookup_returns_the_supplemented_aire():
    aires, bare = load_aires(), load_aires(supplements=False)
    for slug, pin in load_aire_supplements().items():
        # per aire (IDA): « Calvados » is the spirit's aire and the wine IGP's
        key = _normalize(pin["aire"])
        got, before = aires[key][pin["ida"]], bare[key][pin["ida"]]
        assert set(pin["communes"]) <= got, slug
        assert not set(pin.get("not_drawn", {})) & got, slug
        assert not set(pin.get("remove", {})) & got, slug
        assert got - before == set(pin["communes"]), slug
        assert before - got == set(pin.get("remove", {})), slug
        if len(aires[key]) == 1:
            assert lookup(aires, pin["aire"]) == got, slug


def _unligature(s: str) -> str:
    """IGN writes « Dœuil-sur-le-Mignon » where a cahier types « Doeuil »; the
    loose key drops the ligature, so it is spelled out on both sides first."""
    return s.replace("œ", "oe").replace("Œ", "Oe").replace("æ", "ae").replace("Æ", "Ae")


@pytest.mark.skipif(not COMMUNES.exists() or not EXTRACTED.exists(), reason="raw/ not present")
def test_pinned_communes_are_communes_named_by_the_cahier():
    """A pinned commune is a commune of today the zone text names — or names
    by every one of its former communes — or a former commune that kept an
    outline of its own; a removed row is a commune the zone text does not
    name. The pin binds the aire the record itself resolves to (INAO cuts a
    long label short: « Eau-de-vie de vin originaire du Languedoc ou Fine du
    Languedoc ou »)."""
    from _lib import aires as aires_mod
    from _lib.fr import former_communes

    feats = json.loads(COMMUNES.read_text(encoding="utf-8"))["features"]
    names = {f["properties"]["code"]: f["properties"]["nom"] for f in feats}
    former = former_communes.load(set(names), log=False)
    old_names: dict[str, list[str]] = {}
    for code, old in former_communes.former_names(set(names)):
        old_names.setdefault(code, []).append(old)
    bare = load_aires(supplements=False)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in EXTRACTED.glob("*.json")
               if not p.name.startswith("_")]
    aires_mod.register_product_names(
        sorted({r["name"] for r in records if r.get("product_class") == "spirit"}),
        sorted({r["name"] for r in records if not r.get("product_class")}),
    )
    by_slug = {r["slug"]: r for r in records}
    for slug, pin in load_aire_supplements().items():
        rec = by_slug[slug]
        assert aires_mod._resolve_key(bare, rec["name"]) == _normalize(pin["aire"]), slug
        zone = (rec.get("section_roles") or {}).get("aire", "")
        zone = re.split(r"proximité\s+immédiate", zone)[0]
        # page furniture inside a list: "Saint-\n   2/8\n\fPublié au BO …\n\nMaigrin"
        zone = re.sub(r"(?m)^[ \t\x0c]*(?:\d{1,3}(?:[ \t]*/[ \t]*\d{1,3})?|Publié a[ui] BO[^\n]*)[ \t]*$", "", zone)
        zone = _normalize(_unligature(zone))

        def named(name: str) -> bool:
            return _normalize(_unligature(name)) in zone

        # a département the cahier names whole (Génépi des Alpes: « départements
        # … de la Savoie et de la Haute-Savoie ») vouches for its communes
        whole = {code for code, dept in (pin.get("whole_departements") or {}).items()
                 if dept in ((rec.get("aire") or {}).get("aire_departements") or [])}
        assert set(pin.get("whole_departements") or {}) == whole, slug
        for code, name in pin["communes"].items():
            if code in names:
                assert names[code] == name, (slug, code, name)
                if code[:2] in whole:
                    continue
                preds = former.predecessors.get(code, set()) - {code}
                assert (named(name) or any(named(old) for old in old_names.get(code, ()))
                        or (preds and all(named(former.name(c)) for c in preds))), (slug, name)
            else:
                assert code in former.geoms and former.name(code) == name, (slug, code, name)
                assert named(name), (slug, name)
        for code in pin.get("remove", {}):
            assert not named(names[code]), (slug, code, names[code])
