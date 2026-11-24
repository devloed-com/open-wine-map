"""Baden and Württemberg drawn from the Gemarkungen their documents list
(scripts/_lib/de/gemarkung.py, the `lgl-gemarkung-union` step of
scripts/_lib/de/geometry.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _lib.de import gemarkung as g

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "raw" / "de" / "lgl" / "gemarkungen.gpkg"
EXTRACTED = ROOT / "raw" / "de" / "dokumente-extracted"
SIDECARS = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
FIGSHARE = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"

# The EU single document's shape (Württemberg, OJ C/2025/5177, section 6).
EU_AREA = """Bundesland Baden-Württemberg
Zu der geschützten Ursprungsbezeichnung Württemberg gehören die Rebflächen folgender Gemeinden (Gemarkungen) und deren Ortsteile:
Abstatt (835), Adolzfurt (371), Hofen (976), Hofen (1467), Hof und Lembach (926), Stetten (761), Stetten (1441), Zuffenhausen (1481).
Die genaue Abgrenzung ergibt sich aus den Karten mit den parzellenmäßig abgegrenzten Rebflächen der oben genannten Gemeinden, welche unter www.ble.de/eu-qualitaetskennzeichen-wein einsehbar sind.
Bundesland Bayern
Zu der geschützten Ursprungsbezeichnung Württemberg gehören die Rebflächen folgender Gemeinden (Gemarkungen) und deren Ortsteile:
Die Gemeinden Nonnenhorn, Wasserburg und Bodholz und die Gemarkungen Hoyren und Aeschach der Großen Kreisstadt Lindau. Die genaue Abgrenzung ergibt sich aus den Karten.
"""

# The BLE Produktspezifikation's shape (Baden, § 4), as pdftotext -layout
# prints it: one list per Bereich, the Gemeinde printed beside each number.
BLE_SPEC = """3. Beschreibung des Weines/der Weine
Der Wein (1234) schmeckt.

4. Abgrenzung des Gebiets

Das Gebiet der geschützten Ursprungsbezeichnung Baden teilt sich in folgende
übergeordnete Bereiche:
Badische Bergstraße, Bodensee

Zur geschützten Ursprungsbezeichnung gehören im Bereich Badische Bergstraße die
Rebflächen folgender Gemeinden (Gemarkungen) und deren Ortsteile:


Dossenheim (2995), Heidelberg, Stadt (3320), Hirschberg an der
Bergstraße (2960), Weinheim, Stadt (2940), Weinheim, Stadt
(2941)
                                   Seite 12 von 30

Zur geschützten Ursprungsbezeichnung gehören im Bereich Bodensee die Rebflächen
folgender Gemeinden (Gemarkungen) und deren Ortsteile:
Singen (Hohentwiel), Stadt (6620), Konstanz,
Universitätsstadt (6660)

5. Traditionelle Begriffe
Ein Begriff (9999).
"""


def test_eu_document_lists_numbered_units_and_the_bavarian_ones():
    area = g.parse_area(EU_AREA)
    assert [(u.name, u.number) for u in area.units] == [
        ("Abstatt", 835), ("Adolzfurt", 371), ("Hofen", 976), ("Hofen", 1467),
        ("Hof und Lembach", 926), ("Stetten", 761), ("Stetten", 1441), ("Zuffenhausen", 1481),
    ]
    assert area.by_gemeinden == ["Nonnenhorn", "Wasserburg", "Bodholz"]
    assert area.by_partial == [("Lindau", ["Hoyren", "Aeschach"])]


def test_ble_section_4_is_sliced_and_read_per_bereich():
    text = g.section_4(BLE_SPEC)
    assert "(1234)" not in text and "(9999)" not in text and "Seite 12" not in text
    area = g.parse_area(text)
    assert [(u.number, u.name, u.bereich) for u in area.units] == [
        (2995, "Dossenheim", "Badische Bergstraße"),
        (3320, "Heidelberg, Stadt", "Badische Bergstraße"),
        (2960, "Hirschberg an der Bergstraße", "Badische Bergstraße"),
        (2940, "Weinheim, Stadt", "Badische Bergstraße"),
        (2941, "Weinheim, Stadt", "Badische Bergstraße"),
        (6620, "Singen (Hohentwiel), Stadt", "Bodensee"),
        (6660, "Konstanz, Universitätsstadt", "Bodensee"),
    ]
    assert not area.by_gemeinden


def test_section_4_reads_the_heading_without_a_full_stop():
    text = g.section_4("3 Beschreibung\nx\n4 Abgrenzung des Gebietes\n4.1 Bundesland Baden-Württemberg\n"
                       "folgender Gemeinden (Gemarkungen) und deren Ortsteilen:\nAbstatt (835)\n"
                       "5 Traditionelle Begriffe\n")
    assert [u.number for u in g.parse_area(text).units] == [835]


def test_a_number_repeated_in_a_list_is_one_unit():
    area = g.parse_area("Gemeinden (Gemarkungen) und deren Ortsteile: A (10), B (11), A (10).")
    assert [u.number for u in area.units] == [10, 11]


@pytest.mark.parametrize("printed, layer, ok", [
    ("Gronau", ("Gronau", "Oberstenfeld"), True),
    ("Weinheim, Stadt", ("Lützelsachsen", "Weinheim"), True),          # Baden prints the Gemeinde
    ("Kressbronn", ("Kreßbronn am Bodensee", "Kreßbronn am Bodensee"), True),
    ("Wimpfen", ("Wimpfen", "Bad Wimpfen"), True),
    ("Hirschberg an der Bergstraße", ("Großsachsen", "Hirschberg a.d.B."), True),
    ("Konstanz, Universitätsstadt", ("Konstanz", "Konstanz"), True),
    ("Radebeul Stadt", ("Hohenhaslach", "Sachsenheim"), False),        # another Land's number
    ("Stetten", ("Massenbach", "Schwaigern"), False),
])
def test_printed_name_must_agree_with_the_layer(printed, layer, ok):
    assert (g.name_agreement(printed, *layer) >= g.NAME_MATCH_MIN) is ok


def test_pin_table_is_well_formed():
    pins = g.load_pins()
    assert pins, "gemarkung_pins.json is empty"
    for fn, by_number in pins.items():
        assert fn.startswith(("PDO-DE-", "PGI-DE-"))
        for printed, pin in by_number.items():
            assert isinstance(printed, int) and isinstance(pin["number"], int)
            assert pin["number"] != printed
            for key in ("printed", "reason", "source", "verified"):
                assert pin.get(key), (fn, printed, key)


# ───────────────────────────── against the cached layer and records ──

needs_layer = pytest.mark.skipif(not LAYER.exists(), reason="LGL Gemarkung layer not fetched")
needs_records = pytest.mark.skipif(
    not (EXTRACTED / "wurttemberg.json").exists() or not (SIDECARS / "baden.json").exists(),
    reason="DE records not extracted")


@needs_layer
def test_pins_are_not_stale():
    layer = g.GemarkungLayer(LAYER)
    for fn, by_number in g.load_pins().items():
        rows = layer.rows(list(by_number) + [p["number"] for p in by_number.values()])
        for printed, pin in by_number.items():
            assert printed not in rows, f"{fn}: the register now carries {printed} — drop the pin"
            target = rows.get(pin["number"])
            assert target, f"{fn}: pin target {pin['number']} is not in the layer"
            assert g.name_agreement(pin["printed"], target["name"], target["gemeinde"]) >= g.NAME_MATCH_MIN


@needs_records
def test_areas_are_found_for_baden_and_wurttemberg_only():
    areas = g.load_areas(EXTRACTED, SIDECARS)
    kinds = {a["slug"]: a["source_kind"] for a in areas.values()}
    assert kinds.get("wurttemberg") == "eu-single-document"
    assert kinds.get("baden") == "ble-produktspezifikation"
    assert len(areas["PDO-DE-A1276"]["area"].units) >= 270
    assert len(areas["PDO-DE-A1264"]["area"].units) >= 340


@needs_layer
@needs_records
def test_every_listed_unit_is_in_the_register_under_its_printed_name():
    layer = g.GemarkungLayer(LAYER)
    pins = g.load_pins()
    for fn in ("PDO-DE-A1276", "PDO-DE-A1264"):
        area = g.load_areas(EXTRACTED, SIDECARS)[fn]["area"]
        rows = layer.rows(u.number for u in area.units)
        missing = [u for u in area.units if u.number not in rows and u.number not in pins.get(fn, {})]
        assert not missing, f"{fn}: not in the register and not pinned: {missing}"
        wrong = [(u.number, u.name, rows[u.number]["name"]) for u in area.units if u.number in rows
                 and g.name_agreement(u.name, rows[u.number]["name"], rows[u.number]["gemeinde"])
                 < g.NAME_MATCH_MIN]
        assert not wrong, f"{fn}: printed name disagrees with the register: {wrong}"


@needs_layer
@needs_records
@pytest.mark.skipif(not FIGSHARE.exists() or not GISCO.exists(), reason="shared geodata missing")
def test_index_draws_both_regions_from_their_gemarkungen_and_the_landweine_follow():
    import geopandas as gpd
    from _lib.de.geometry import DEPolygonIndex

    idx = DEPolygonIndex(FIGSHARE, GISCO, gemarkung_gpkg=LAYER,
                         gemarkung_areas=g.load_areas(EXTRACTED, SIDECARS),
                         gemarkung_pins=g.load_pins())

    def km2(geom):
        return gpd.GeoSeries([geom], crs=4326).to_crs(3035).area.iloc[0] / 1e6

    geom, source, stats = idx.resolve("PDO-DE-A1276")
    assert source == "lgl-gemarkung-union"
    assert stats["gemarkungen"] == stats["gemarkungen_listed"] and not stats["names_unmatched"]
    assert stats["pinned"] == ["Stetten (761) → 768 Stetten (Schwaigern)"]
    assert stats["gemeinden"] == ["Nonnenhorn", "Wasserburg (Bodensee)", "Bodolz"]
    assert stats["partial"] == ["Lindau (Bodensee) (Hoyren, Aeschach)"]
    # Bétard drew 10,757 km² of whole Landkreise.
    assert 2_400 < km2(geom) < 3_100

    geom, source, stats = idx.resolve("PDO-DE-A1264")
    assert source == "lgl-gemarkung-union" and not stats["names_unmatched"]
    assert 3_300 < km2(geom) < 3_900                     # Bétard: 13,231 km²

    # A Landwein that is the union of one of them follows, and says so.
    geom, source, stats = idx.resolve("PGI-DE-A1305")    # Schwäbischer Landwein
    assert source == "region-pdo-union" and stats["gemarkung_members"] == 1
    assert 2_400 < km2(geom) < 3_100
    # The other eleven Anbaugebiete keep their Bétard polygon.
    assert idx.resolve("PDO-DE-A1270")[1] == "figshare-pdo"


@needs_layer
@needs_records
@pytest.mark.skipif(not FIGSHARE.exists() or not GISCO.exists(), reason="shared geodata missing")
def test_landweine_follow_their_own_specification_not_a_wider_member_table():
    """Three member-table errors the whole-Landkreis polygons had hidden
    (2026-11-17), each settled by § 3 / § 4 of the Landwein's own BLE
    Produktspezifikation: Landwein Main lists Bavarian communes only,
    Landwein Rhein-Neckar the places of Baden and Württemberg only, and
    Bayerischer Bodensee-Landwein three communes of the Lindau shore."""
    import geopandas as gpd
    from _lib.de.geometry import DE_LANDWEIN_AREA, DE_PGI_MEMBER_PDOS, DEPolygonIndex

    assert DE_PGI_MEMBER_PDOS["PGI-DE-A1282"] == ("PDO-DE-A1267",)
    assert set(DE_PGI_MEMBER_PDOS["PGI-DE-A1287"]) == {"PDO-DE-A1276", "PDO-DE-A1264"}
    assert "PGI-DE-A1280" not in DE_PGI_MEMBER_PDOS and "PGI-DE-A1280" in DE_LANDWEIN_AREA

    idx = DEPolygonIndex(FIGSHARE, GISCO, gemarkung_gpkg=LAYER,
                         gemarkung_areas=g.load_areas(EXTRACTED, SIDECARS),
                         gemarkung_pins=g.load_pins())

    def km2(geom):
        return gpd.GeoSeries([geom], crs=4326).to_crs(3035).area.iloc[0] / 1e6

    main, source, stats = idx.resolve("PGI-DE-A1282")
    assert source == "region-pdo-union" and not stats.get("gemarkung_members")
    assert abs(km2(main) - km2(idx.resolve("PDO-DE-A1267")[0])) < 1          # Franken, nothing else

    rn, source, stats = idx.resolve("PGI-DE-A1287")
    assert source == "region-pdo-union" and stats["gemarkung_members"] == stats["resolved"] == 2
    assert 5_800 < km2(rn) < 6_900                                            # Baden + Württemberg

    lake, source, stats = idx.resolve("PGI-DE-A1280")
    assert source == "gisco-commune-union" and stats["gemeinden"] == 3 and not stats["unmatched"]
    assert stats["partial"] == ["Lindau (Gemarkungen Hoyren, Aeschach)"]
    assert km2(lake) < 80


def test_sidecars_carry_the_area_text_only_where_stage_04_reads_it():
    """The area section rides the sidecar where one of the three readers
    reads it: numbered Gemarkungen of Baden-Württemberg (Baden, Württemberg),
    Bavarian Gemeinden by Kreis (Franken, Landwein Main:
    scripts/_lib/de/gemeinde_list.py), or one of the other layouts
    (scripts/_lib/de/area_units.py — Rheingau, Ahr, Saale-Unstrut …). Each
    such sidecar says which, by exactly one counter."""
    if not SIDECARS.exists():
        pytest.skip("DE sidecars not extracted")
    sides = {p.stem: json.loads(p.read_text(encoding="utf-8"))
             for p in SIDECARS.glob("*.json")
             if not p.name.startswith("_") and p.stem != "manifest"}
    assert sorted(s for s, d in sides.items() if "n_gemarkungen" in d) == ["baden", "wurttemberg"]
    assert sorted(s for s, d in sides.items() if "n_gemeinden" in d) == ["franken", "landwein-main"]
    by_units = {s for s, d in sides.items() if "n_area_units" in d}
    assert {"rheingau", "ahr", "hessische-bergstrae", "saale-unstrut", "mittelrhein"} <= by_units
    for s, d in sides.items():
        counters = [k for k in ("n_gemarkungen", "n_gemeinden", "n_area_units") if k in d]
        assert ("area_text" in d) == (len(counters) == 1), s
