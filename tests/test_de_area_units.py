"""The German area-text reader for the layouts outside Baden-Württemberg and
Bavaria (scripts/_lib/de/area_units.py) and the Länder's Gemarkung layers it
binds to (scripts/_lib/de/katasterbezirk.py).

Bétard 2022 drew Mittelrhein's part in Nordrhein-Westfalen as Bonn,
Königswinter and Bad Honnef whole where the text names five Gemarkungen, no
part of Frankfurt am Main for the Rheingau, and Saale-Unstrut as 48 whole
municipalities where the text names a hundred Gemarkungen (CURATOR_TODO,
feedback triage 2026-11-24)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.de import area_units as au  # noqa: E402
from _lib.de import katasterbezirk as kb  # noqa: E402

EXTRACTED = ROOT / "raw" / "de" / "dokumente-extracted"
SIDECARS = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
LAYERS = ROOT / "raw" / "de" / "katasterbezirke"
GISCO = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"

needs_corpus = pytest.mark.skipif(
    not (EXTRACTED / "mittelrhein.json").exists() or not (LAYERS / "manifest.json").exists()
    or not GISCO.exists(),
    reason="DE records, Gemarkung layers or GISCO LAU not on disk")

MITTELRHEIN = """Land Rheinland-Pfalz
Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der Gemeinden und deren Ortsteilen Bacharach (Bacharach (3503), Steeg (3502)), Bad Ems (0950), Breitscheid (Landkreis Mainz-Bingen) (0261), Sankt Goar (St. Goar (1837), Werlau (1836)), Urbar (1355, 1839), Vallendar (1352), Weinähr (0833).
Land Nordrhein-Westfalen
Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der Stadt Königswinter mit den Gemarkungen Oberdollendorf, Niederdollendorf und Königswinter, der Stadt Bad Honnef mit der Gemarkung Honnef (Rhöndorf) und der Stadt Bonn mit der Gemarkung Kessenich.
Die genaue Abgrenzung ergibt sich aus den Karten mit den parzellenmäßig abgegrenzten Rebflächen der oben genannten Gemeinden, welche unter www.ble.de/eu-qualitaetskennzeichen-wein einsehbar sind.
Die Herstellung von Qualitätswein mit dem geschützten Namen „Mittelrhein“ darf in einem anderen Gebiet erfolgen, sofern das Gebiet der Herstellung in demselben Bundesland (Rheinland-Pfalz, Nordrhein-Westfahlen) oder in einem benachbarten Bundesland (Baden-Württemberg, Hessen, Saarland, Niedersachsen) liegt."""

SAALE_UNSTRUT = """Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der Gemarkungen Bad Kösen, Freyburg/Unstrut und Zscheiplitz im Landkreis Burgenlandkreis, Quedlinburg und Westerhausen im Landkreis Harz sowie Gröna und Könnern im Landkreis Salzlandkreis des Landes Sachsen-Anhalt.
In Thüringen gehören zur geschützten Ursprungsbezeichnung die Rebflächen in den Gemarkungen Auerstedt, Weichau im Landkreis Weimarer Land, Seitenroda, Tümplingund Wichmar im Landkreis Saale-Holzland-Kreis, Rastenberg im Landkreis Sömmerda, Weimar Ortsteil Schöndorf, Weimar Ortsteil Tiefurt und die kreisfreien Städte Jena und Erfurt.
Zur geschützten Ursprungsbezeichnung gehören weiterhin die Rebflächen der Gemarkungen Werder (Havel), Phöben, Plessow und Neu Töplitz der Stadt Werder (Havel) im Landkreis Potsdam-Mittelmark des Landes Brandenburg.
Die genaue Abgrenzung ergibt sich aus den Karten."""

# § 3 of the Rheingau's BLE specification as `pdftotext -layout` prints it.
RHEINGAU_BLE = """Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der Städte und Ge-
meinden Eltville am Rhein, Felsberg, Flörsheim am Main, Frankfurt am Main, Geisen-
heim, Hochheim am Main, Kiedrich, Lorch, Oestrich-Winkel, Rüdesheim am Rhein, Wal-
luf und der Landeshauptstadt Wiesbaden des Bundeslandes Hessen.
Die Herstellung von Qualitätswein b. A. mit dem geschützten Namen „Rheingau“ muss im Anbaugebiet,
in einem anderen Anbaugebiet des Landes Hessen oder in einem Anbaugebiet eines benachbarten Landes erfolgen.
"""

SAARLAND = ("Zur geschützten geografischen Angabe gehören: die Flächen der Städte und Gemeinden "
            "Merzig, Mettlach und Beckingen im Landkreis Merzig-Wadern, die Flächen der Städte und "
            "Gemeinden Mandelbachtal und Bexbach im Saar-Pfalz-Kreis sowie die Flächen der Städte "
            "und Gemeinden St. Wendel, Oberthal und Nohfelden im Landkreis St. Wendel. Die genaue "
            "Abgrenzung ergibt sich aus den Karten mit den Gemeindegrenzen.")


def _by_kind(units):
    out: dict[str, list] = {}
    for u in units:
        out.setdefault(u.kind, []).append(u)
    return out


def test_numbered_list_reads_nested_gemarkungen_two_numbers_and_a_kreis_gloss():
    units = [u for u in au.parse(MITTELRHEIN) if u.kind == "numbered"]
    got = [(u.name, u.number, u.holder, u.kreis, u.land) for u in units]
    assert got == [
        ("Bacharach", 3503, "Bacharach", "", "rp"),
        ("Steeg", 3502, "Bacharach", "", "rp"),
        ("Bad Ems", 950, "", "", "rp"),
        ("Breitscheid", 261, "", "Mainz-Bingen", "rp"),
        ("St. Goar", 1837, "Sankt Goar", "", "rp"),
        ("Werlau", 1836, "Sankt Goar", "", "rp"),
        ("Urbar", 1355, "", "", "rp"),
        ("Urbar", 1839, "", "", "rp"),
        ("Vallendar", 1352, "", "", "rp"),
        ("Weinähr", 833, "", "", "rp"),
    ]


def test_a_city_with_its_gemarkungen_names_those_not_the_city():
    """«der Stadt Bonn mit der Gemarkung Kessenich»: Kessenich, held by Bonn."""
    units = [u for u in au.parse(MITTELRHEIN) if u.kind == "gemarkung"]
    assert [(u.name, u.holder, u.land, u.gloss) for u in units] == [
        ("Oberdollendorf", "Königswinter", "nw", ""),
        ("Niederdollendorf", "Königswinter", "nw", ""),
        ("Königswinter", "Königswinter", "nw", ""),
        ("Honnef", "Bad Honnef", "nw", "Rhöndorf"),
        ("Kessenich", "Bonn", "nw", ""),
    ]


def test_the_closing_sentences_name_no_unit():
    """The Länder the wine may be made in are not part of the area."""
    lands = {u.land for u in au.parse(MITTELRHEIN)}
    assert lands == {"rp", "nw"}


def test_gemarkungen_by_kreis_each_under_its_land():
    kinds = _by_kind(au.parse(SAALE_UNSTRUT))
    st = [(u.name, u.kreis) for u in kinds["gemarkung"] if u.land == "st"]
    assert st == [("Bad Kösen", "Burgenlandkreis"), ("Freyburg/Unstrut", "Burgenlandkreis"),
                  ("Zscheiplitz", "Burgenlandkreis"), ("Quedlinburg", "Harz"),
                  ("Westerhausen", "Harz"), ("Gröna", "Salzlandkreis"), ("Könnern", "Salzlandkreis")]
    th = [(u.name, u.kreis) for u in kinds["gemarkung"] if u.land == "th"]
    # "Tümplingund Wichmar": the document lost the space
    assert th == [("Auerstedt", "Weimarer Land"), ("Weichau", "Weimarer Land"),
                  ("Seitenroda", "Saale-Holzland-Kreis"), ("Tümpling", "Saale-Holzland-Kreis"),
                  ("Wichmar", "Saale-Holzland-Kreis"), ("Rastenberg", "Sömmerda")]
    assert [(u.name, u.holder, u.land) for u in kinds["ortsteil"]] == [
        ("Schöndorf", "Weimar", "th"), ("Tiefurt", "Weimar", "th")]
    assert [(u.name, u.land) for u in kinds["gemeinde"]] == [("Jena", "th"), ("Erfurt", "th")]
    bb = [(u.name, u.holder, u.kreis) for u in kinds["gemarkung"] if u.land == "bb"]
    assert bb == [("Werder (Havel)", "Werder (Havel)", "Potsdam-Mittelmark"),
                  ("Phöben", "Werder (Havel)", "Potsdam-Mittelmark"),
                  ("Plessow", "Werder (Havel)", "Potsdam-Mittelmark"),
                  ("Neu Töplitz", "Werder (Havel)", "Potsdam-Mittelmark")]


def test_a_pdf_gemeinde_list_is_unwrapped_and_keeps_the_landeshauptstadt():
    units = au.parse(RHEINGAU_BLE)
    assert [u.name for u in units] == [
        "Eltville am Rhein", "Felsberg", "Flörsheim am Main", "Frankfurt am Main", "Geisenheim",
        "Hochheim am Main", "Kiedrich", "Lorch", "Oestrich-Winkel", "Rüdesheim am Rhein",
        "Walluf", "Wiesbaden"]
    assert {u.kind for u in units} == {"gemeinde"} and {u.land for u in units} == {"he"}


def test_a_lead_repeated_per_kreis_is_one_list():
    units = au.parse(SAARLAND)
    assert [(u.name, u.kreis) for u in units] == [
        ("Merzig", "Merzig-Wadern"), ("Mettlach", "Merzig-Wadern"), ("Beckingen", "Merzig-Wadern"),
        ("Mandelbachtal", "Saar-Pfalz-Kreis"), ("Bexbach", "Saar-Pfalz-Kreis"),
        ("St. Wendel", "St. Wendel"), ("Oberthal", "St. Wendel"), ("Nohfelden", "St. Wendel")]


def test_area_section_is_found_under_either_number():
    spec = ("2. Beschreibung\nText.\n\n3. Abgrenzung des Gebietes\nZur geschützten …\n"
            "3 Mittelhainger (5490)\n\n4. Traditionelle Begriffe\nMehr.\n")
    assert au.area_section(spec) == "Zur geschützten …\n3 Mittelhainger (5490)"
    assert au.area_section("1. Name\n2. Beschreibung\n") == ""


# ───────────────────────────────────────────────── against the corpus ──

@pytest.fixture(scope="module")
def world():
    import geopandas as gpd

    lau = gpd.read_file(f"zip://{GISCO}", where="CNTR_CODE = 'DE'").to_crs("EPSG:4326")
    communes = au.CommuneRows([(r.GISCO_ID, r.LAU_NAME, r.geometry) for r in lau.itertuples()])
    return kb.Gemarkungen(LAYERS), communes, au.load_areas(EXTRACTED, SIDECARS), au.load_pins()


def _resolved(world, fn):
    gm, communes, areas, pins = world
    return au.resolve(areas[fn]["units"], gm, communes, pins.get(fn))


@needs_corpus
def test_mittelrhein_binds_every_unit_and_no_whole_city(world):
    res = _resolved(world, "PDO-DE-A1269")
    assert not res.unmatched and not res.disagree
    assert {b.how for b in res.bound} == {"gemarkung"}
    nw = sorted(b.label for b in res.bound if b.land == "nw")
    assert nw == ["Honnef", "Kessenich", "Königswinter", "Niederdollendorf", "Oberdollendorf"]
    # "Breitscheid (Landkreis Mainz-Bingen) (0261)": the Kreis the text gives
    # decides, not the number (0261 is the Breitscheid of the Landkreis Neuwied)
    breit = [b for b in res.bound if b.unit.name == "Breitscheid"]
    assert [b.lau_id[:8] for b in breit] == ["DE_07339"]


@needs_corpus
def test_a_number_whose_kreis_the_text_contradicts_is_not_drawn_without_a_pin(world):
    gm, communes, areas, _pins = world
    res = au.resolve(areas["PDO-DE-A1269"]["units"], gm, communes, None)
    assert res.unmatched == ["Breitscheid (0261)"]
    assert res.disagree and "Breitscheid" in res.disagree[0]


@needs_corpus
def test_rheingau_is_its_twelve_gemeinden_frankfurt_among_them(world):
    gm, communes, areas, _pins = world
    assert areas["PDO-DE-A1273"]["source_kind"] == "ble-produktspezifikation"
    res = _resolved(world, "PDO-DE-A1273")
    assert not res.unmatched and len(res.bound) == 12
    assert {b.how for b in res.bound} == {"gemeinde"}
    assert "DE_06412000" in {b.lau_id for b in res.bound}      # Frankfurt am Main


@needs_corpus
def test_saale_unstrut_binds_all_but_a_name_no_gemarkung_of_the_kreis_carries(world):
    """«Graitschen … im Landkreis Saale-Holzland-Kreis»: the Kreis has
    Graitschen auf der Höhe and Graitschen bei Bürgel, none called Graitschen
    — not drawn, named on the card."""
    res = _resolved(world, "PDO-DE-A1275")
    assert res.unmatched == ["Graitschen"]
    assert {b.land for b in res.bound} == {"st", "th", "bb"}
    whole = sorted(b.label for b in res.bound if b.how == "gemeinde")
    assert whole == ["Erfurt", "Jena"]
    assert not [b for b in res.bound if b.how == "gemeinde-for-part"]


@needs_corpus
def test_the_rhineland_numbers_agree_with_the_land_register(world):
    """Every number Mosel, Nahe and Pfalz print is a Gemarkung of that name
    in Rheinland-Pfalz's layer; Mosel's four Saarland units are the Gemeinde
    Perl, drawn whole."""
    for fn, n in (("PDO-DE-A1271", 101), ("PDO-DE-A1272", 187)):
        res = _resolved(world, fn)
        assert not res.unmatched and len(res.bound) == n and {b.land for b in res.bound} == {"rp"}
    mosel = _resolved(world, "PDO-DE-A1270")
    assert not mosel.unmatched
    assert {b.label for b in mosel.bound if b.how == "gemeinde-for-part"} == {"Perl"}


@needs_corpus
def test_pins_name_units_of_their_record_and_are_not_stale(world):
    gm, communes, areas, pins = world
    assert pins, "area_unit_pins.json is empty"
    for fn, entries in pins.items():
        labels = {au._label(u) for u in areas[fn]["units"]}
        for label, pin in entries.items():
            assert pin.get("reason") and pin.get("verified"), f"{fn} {label}: uncited pin"
            if label not in labels:
                # a record that shares another's pins need not print every name
                continue
            unit = next(u for u in areas[fn]["units"] if au._label(u) == label)
            assert au._pinned(unit, pin, gm, communes), f"{fn} {label}: stale pin"
    assert any(au._label(u) == "Stedten" for u in areas["PDO-DE-A1275"]["units"])


@needs_corpus
def test_a_landwein_is_read_from_its_own_list(world):
    """Landwein der Ruwer names eleven Gemarkungen of the Ruwer valley and
    Landwein der Saar nineteen; both had been drawn as all of the Mosel."""
    ruwer, saar = _resolved(world, "PGI-DE-A1288"), _resolved(world, "PGI-DE-A1289")
    assert (len(ruwer.bound), len(saar.bound)) == (11, 19)
    assert not ruwer.unmatched and not saar.unmatched


def test_layer_manifest_credits_every_land():
    if not (LAYERS / "manifest.json").exists():
        pytest.skip("Gemarkung layers not fetched")
    manifest = json.loads((LAYERS / "manifest.json").read_text(encoding="utf-8"))
    for code, cfg in kb.SERVICES.items():
        assert code in manifest, f"{code}: layer not fetched"
        assert manifest[code]["licence_url"] == cfg["licence_url"]
        assert manifest[code]["n_gemarkungen"] > 100


@needs_corpus
def test_a_gemeinde_with_its_districts_in_a_bracket_is_those_gemarkungen(world):
    """Rheinhessen: "Bingen am Rhein (Bingen, Büdesheim, Dietersheim,
    Dromersheim, Gaulsheim, Kempten, Sponsheim)" — not Bingerbrück, which the
    Nahe lists as "Bingen am Rhein (Bingerbrueck (3521))". A spelling the
    register writes otherwise binds inside the Gemeinde ("Groß-Winternheim")."""
    res = _resolved(world, "PDO-DE-A1274")
    assert not res.unmatched
    bingen = sorted(b.label for b in res.bound if b.unit.name.startswith("Bingen am Rhein"))
    assert bingen == ["Bingen", "Büdesheim", "Dietersheim", "Dromersheim", "Gaulsheim", "Kempten",
                      "Sponsheim"]
    ingelheim = {b.label for b in res.bound if b.unit.name.startswith("Ingelheim am Rhein")}
    assert "Großwinternheim" in ingelheim
    assert sum(1 for b in res.bound if b.how == "gemeinde") == 117
    nahe = _resolved(world, "PDO-DE-A1271")
    assert "Bingerbrück" in {b.label for b in nahe.bound}
    # "mit Ausnahme Bingerbrück" (Rheinischer Landwein) is the same seven
    rl = _resolved(world, "PGI-DE-A1301")
    assert sorted(b.label for b in rl.bound if b.unit.name.startswith("Bingen am Rhein")) == bingen


@needs_corpus
def test_a_pin_names_its_target_for_the_card(world):
    gm, communes, areas, pins = world
    res = _resolved(world, "PDO-DE-A1269")
    breit = [b for b in res.bound if au._label(b.unit) == "Breitscheid (0261)"]
    assert au.pin_text("Breitscheid (0261)", breit) == "Breitscheid (0261) → 3501 Breitscheid"
    su = _resolved(world, "PDO-DE-A1275")
    assert au.pin_text("Kromsdorf", [b for b in su.bound if b.unit.name == "Kromsdorf"]) == \
        "Kromsdorf → Großkromsdorf, Kleinkromsdorf"
    assert au.pin_text("Stedten", [b for b in su.bound if b.unit.name == "Stedten"]) == \
        "Stedten → Stedten (Seegebiet Mansfelder Land)"
