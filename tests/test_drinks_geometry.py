"""The polygon of a drink GI (scripts/_lib/drinks/geometry.py) and the region
it is filed under (region.py), on small synthetic layers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.drinks import geometry as dg  # noqa: E402
from _lib.drinks import region as dr  # noqa: E402


def _layer(path: Path, units: dict[str, tuple[str, tuple[float, float, float, float]]]) -> Path:
    features = [
        {"type": "Feature", "properties": {"NUTS_ID": code, "NAME_LATN": name, "NUTS_NAME": name},
         "geometry": mapping(box(*bounds))}
        for code, (name, bounds) in units.items()
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


@pytest.fixture()
def geometry(tmp_path: Path) -> dg.DrinksGeometry:
    nuts3 = _layer(tmp_path / "n3.geojson", {
        "ES611": ("Almería", (0, 0, 1, 1)), "ES612": ("Cádiz", (1, 0, 2, 1)),
        "ES620": ("Murcia", (2, 0, 3, 1)), "ITH10": ("Bolzano-Bozen", (5, 5, 6, 6)),
    })
    nuts2 = _layer(tmp_path / "n2.geojson", {
        "ES61": ("Andalucía", (0, 0, 2, 1)), "ES62": ("Región de Murcia", (2, 0, 3, 1)),
        "ITH1": ("Provincia Autonoma di Bolzano/Bozen", (5, 5, 6, 6)),
    })
    return dg.DrinksGeometry(nuts3, nuts2, tmp_path / "no-lau.zip", areas={})


def test_nuts_leaves_are_the_finest_rows() -> None:
    assert dg.nuts_leaves(["ES612", "ES61", "ES6", "ES"]) == ["ES612"]
    assert dg.nuts_leaves(["ES61", "ES62", "ES"]) == ["ES61", "ES62"]
    assert dg.nuts_leaves(["", "DE"]) == ["DE"]


def test_nuts_rows_draw_the_leaves(geometry: dg.DrinksGeometry) -> None:
    record = {"slug": "x", "geo_nuts": [{"code": c, "name": n} for c, n in
                                        (("ES612", "Cádiz"), ("ES61", "Andalucía"), ("ES6", "SUR"), ("ES", "ESPAÑA"))]}
    out = geometry.resolve(record)
    assert out.source == "gisco-nuts-union"
    assert [u["code"] for u in out.units] == ["ES612"]
    assert out.geom.equals(box(1, 0, 2, 1))


def test_a_retired_code_is_found_by_its_name_or_reported(geometry: dg.DrinksGeometry) -> None:
    # ITD1 is the 2010 code of the unit the 2024 layer calls ITH10
    drawn, missing = geometry.resolve_nuts_rows([{"code": "ITD1", "name": "Bolzano-Bozen"}])
    assert drawn == ["ITH10"] and not missing
    drawn, missing = geometry.resolve_nuts_rows([{"code": "ITD9", "name": "Nowhere"}])
    assert not drawn and missing == ["ITD9 Nowhere"]
    # a record whose only row is unknown is not drawn
    out = geometry.resolve({"slug": "y", "geo_nuts": [{"code": "ITD9", "name": "Nowhere"}]})
    assert out.geom is None and out.source == "stub-no-geometry"


def test_levels_above_the_layers_are_unions_by_prefix(geometry: dg.DrinksGeometry) -> None:
    assert geometry.nuts_geom("ES6").equals(box(0, 0, 3, 1))
    assert geometry.nuts_geom("ES").equals(box(0, 0, 3, 1))
    assert geometry.nuts_geom("FR") is None


def test_pin_units_and_cut_outs(geometry: dg.DrinksGeometry) -> None:
    out = geometry.resolve_units(["country:es", "minus:nuts:ES620"])
    assert out.source == "drinks-area-pin" and not out.unresolved
    assert out.geom.equals(box(0, 0, 2, 1))
    assert [u["kind"] for u in out.units] == ["country"]
    # a referenced record brings its own polygon
    out = geometry.resolve_units(["ref:douro"], {"douro": box(9, 9, 10, 10)})
    assert out.geom.equals(box(9, 9, 10, 10)) and out.units == [{"kind": "ref", "slug": "douro"}]
    # a unit that does not resolve leaves the pin undrawn, never half-drawn
    out = geometry.resolve_units(["nuts:ES612", "nuts:XX999"])
    assert out.geom is None and out.unresolved == ["nuts:XX999"]


def test_a_pin_wins_over_the_nuts_rows_and_never_half_draws(geometry: dg.DrinksGeometry) -> None:
    geometry.areas = {"jerez": {"units": ["nuts:ES611"], "quote": "q"},
                      "broken": {"units": ["nuts:ES611", "nuts:XX999"], "quote": "q"}}
    rows = [{"code": "ES612", "name": "Cádiz"}]
    out = geometry.resolve({"slug": "jerez", "geo_nuts": rows})
    assert out.source == "drinks-area-pin" and out.geom.equals(box(0, 0, 1, 1)) and out.pin
    out = geometry.resolve({"slug": "broken", "geo_nuts": rows})
    assert out.geom is None and out.unresolved == ["nuts:XX999"]


def test_largest_part_keeps_the_island(geometry: dg.DrinksGeometry) -> None:
    geometry.areas = {"island": {"units": ["nuts:ES611", "nuts:ITH10"], "quote": "q", "largest_part": True}}
    geometry._nuts3["ITH10"] = box(5, 5, 5.1, 5.1)  # noqa: SLF001 — an islet beside the island
    out = geometry.resolve({"slug": "island"})
    assert out.geom.equals(box(0, 0, 1, 1))


def test_labels_and_localisation(geometry: dg.DrinksGeometry) -> None:
    assert geometry.unit_label({"kind": "nuts", "code": "ES612"}) == "Cádiz"
    assert geometry.unit_label({"kind": "lau", "name": "Chinchón", "country": "es"}) == "Chinchón"
    gd = {"source": "drinks-area-pin",
          "units": [{"kind": "country", "code": "at", "label": ""},
                    {"kind": "ref", "slug": "douro", "label": ""},
                    {"kind": "nuts", "code": "ES612", "label": "Cádiz"}],
          "disclose": {"en": "Drawn whole.", "fr": "Dessinée en entier.", "es": "Entero.", "nl": "Geheel."}}
    out = dg.localise(gd, "fr", {"at": "Autriche"}, {"douro": "Douro"}, "aire de l'appellation {name}")
    assert [u["label"] for u in out["units"]] == ["Autriche", "aire de l'appellation Douro", "Cádiz"]
    assert out["precision"] == "Dessinée en entier." and "disclose" not in out
    assert "precision" not in dg.localise({"units": []}, "fr", {}, {}, "{name}")
    # the source dict is not modified: every locale starts from it
    assert gd["units"][0]["label"] == "" and "disclose" in gd


def test_region_of_a_drink() -> None:
    table = dr.nuts_regions()
    assert table, "empty region table"
    record = {"country": "es"}
    assert dr.derive_region(record, [{"kind": "nuts", "code": "ES612"}], None, {}) == dr.region_of_nuts("ES61")
    # a wine record's area brings its region
    assert dr.derive_region({"country": "pt"}, [{"kind": "ref", "slug": "douro"}], None, {"douro": "Douro/Porto"}) == "Douro/Porto"
    # a municipality is filed where its NUTS-3 unit is
    assert dr.derive_region(record, [{"kind": "lau", "name": "Chinchón", "nuts": "ES300"}], None, {}) == dr.region_of_nuts("ES30")
    # units of several regions, a whole country, or no unit at all: the country
    assert dr.derive_region(record, [{"kind": "nuts", "code": "ES612"}, {"kind": "nuts", "code": "ES300"}], None, {}) == "España"
    assert dr.derive_region({"country": "it"}, [{"kind": "country", "code": "it"}], None, {}) == "Italia"
    assert dr.derive_region({"country": "gr"}, [], None, {}) == "Ελλάδα"
    # a pin's own region wins
    assert dr.derive_region(record, [], {"region": "Galicia"}, {}) == "Galicia"


def test_region_table_codes_are_units_of_the_layers() -> None:
    if not (dg.NUTS3_PATH.exists() and dg.NUTS2_PATH.exists()):
        pytest.skip("GISCO NUTS layers are not on disk")
    geometry = dg.DrinksGeometry(areas={})
    missing = [code for code in dr.nuts_regions() if geometry.nuts_geom(code) is None]
    assert not missing, missing


def test_uk_units_and_a_shared_island(geometry: dg.DrinksGeometry, tmp_path: Path, monkeypatch) -> None:
    ons = tmp_path / "ons"
    ons.mkdir()
    (ons / "countries.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"CTRY25CD": "N92000002", "CTRY25NM": "Northern Ireland"},
         "geometry": mapping(box(20, 20, 21, 21))}]}), encoding="utf-8")
    (ons / "counties.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"CTYUA25CD": "E06000019", "CTYUA25NM": "Herefordshire, County of"},
         "geometry": mapping(box(30, 30, 31, 31))}]}), encoding="utf-8")
    monkeypatch.setattr(dg, "ONS_DIR", ons)
    out = geometry.resolve_units(["uk:county:Herefordshire, County of=Herefordshire"])
    assert out.geom.equals(box(30, 30, 31, 31))
    assert out.units == [{"kind": "uk", "level": "county", "name": "Herefordshire"}]
    assert geometry.resolve_units(["uk:country:Atlantis"]).geom is None
    # the island of Ireland for a UK record: the foreign part is drawn and
    # named, and does not decide the region
    out = geometry.resolve_units(["country:es", "uk:country:Northern Ireland"])
    assert out.geom.equals(box(0, 0, 3, 1).union(box(20, 20, 21, 21)))
    assert dr.derive_region({"country": "gb"}, out.units, None, {}) == "Northern Ireland"
    assert dr.derive_region({"country": "gb"}, [{"kind": "uk", "level": "county", "name": "Somerset"}], None, {}) == "England"
