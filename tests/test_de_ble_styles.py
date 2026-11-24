"""The wine types a BLE Produktspezifikation states
(scripts/_lib/de/ble_styles.py), the German roster names the lexicon lacked
and the 02f / stage-04 wiring.

The excerpts are short passages of the BLE specifications (Amtliches Werk
§ 5 UrhG) as `pdftotext -layout` prints them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from _lib.augment import de as augment_de
from _lib.de import ble_styles
from _lib.grape_entity import match_variety

ROOT = Path(__file__).resolve().parents[1]
SIDECARS = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
PDFS = ROOT / "raw" / "de" / "produktspezifikationen"

AHR = """                                  „AHR“
        Qualitätswein, Prädikatswein, Sekt b.A. und Qualitätsperlwein
            Produktspezifikation für eine geschützte Ursprungsbezeichnung

1. Geschützter Name
      „Ahr“

2. Beschreibung des Weines/der Weine
   2.1. Analytisch
          a) 18 Milliäquivalent je Liter bei Weißwein und Roséwein,
          b) 20 Milliäquivalent je Liter bei Rotwein,
          c) 30 Milliäquivalent je Liter bei Wein, der den traditionellen Begriff Beerenauslese
             oder Eiswein trägt,
             a) 150 mg/l bei Rotwein;
             b) 200 mg/l bei Weißwein und Roséwein.
      2.2. Organoleptisch
         An der Ahr werden insbesondere Rotweine und daneben auch traditionell Rosé- und
         Weißweine hergestellt. Weine aus diesem Ursprung können zur Herstellung von
         Qualitätsperlwein und Sekt b.A. mit der Ursprungsbezeichnung „Ahr“ verwendet werden.
3. Abgrenzung des Gebietes
         Zum Anbaugebiet gehören die Rebflächen der Gemeinden Rotweinstadt, Sektdorf und
         Weißwein am See.
4. Traditionelle Begriffe, die mit dieser Ursprungsbezeichnung verbunden sind
         Prädikatswein ergänzt durch: Kabinett, Spätlese, Auslese, Beerenauslese,
         Trockenbeerenauslese, Eiswein.
5. Spezifische önologische Verfahren
7. Rebsorten
         Rotwein- und Roséweinsorten: Blauer Spätburgunder, Likörwein ist keine Sorte.
8. Angaben, aus denen sich der Zusammenhang ergibt
         8.4 Kategorien von Erzeugnissen
       8.4.2. Erzeugnisart „Perlwein“
           Für Qualitätsperlwein muss das Grundprodukt die Mindestanforderungen erfüllen.
  9. Sonstige Anforderungen gemäß nationaler Rechtsvorschriften
"""


def test_colours_come_from_the_description_not_from_a_legal_ceiling():
    stated = ble_styles.stated_styles(AHR)
    assert {"blanc", "noir", "rose"} <= set(stated)
    for colour in ("blanc", "noir", "rose"):
        assert "An der Ahr werden insbesondere Rotweine" in stated[colour]
        assert "mg/l" not in stated[colour] and "Milliäquivalent" not in stated[colour]


def test_an_elided_compound_is_read_whole():
    assert set(ble_styles.stated_styles(
        "2. Beschreibung der Weine\nAn der Hessischen Bergstraße werden überwiegend Weißweine, "
        "daneben auch Rot- und Roséweine hergestellt.\n")) == {"blanc", "noir", "rose"}
    assert set(ble_styles.stated_styles(
        "2.2 Organoleptisch\nDie Sorten werden zu Weiß-, Rosé- und Rotweinen ausgebaut.\n")) \
        == {"blanc", "noir", "rose"}
    # a line-break hyphen is closed, an elision at a line end is kept
    assert set(ble_styles.stated_styles(
        "Rotweine sind von hellroter Farbe. Weiß-\nherbste und Roséweine sind von heller "
        "Farbe. Es gibt Rot-\nund Weißweine.\n")) == {"blanc", "noir", "rose"}


def test_categories_and_praedikate_are_read_outside_the_area_and_the_roster():
    stated = ble_styles.stated_styles(AHR)
    assert {"sparkling", "semi-sparkling", "grains-nobles", "vendanges-tardives"} <= set(stated)
    # the traditional terms state the Prädikate; the acidity ceiling does not
    assert "Prädikatswein ergänzt durch: Kabinett, Spätlese" in stated["grains-nobles"]
    assert "Milliäquivalent" not in stated["grains-nobles"]
    # the roster section and the area section are not read: no Likörwein,
    # and the commune names add nothing
    assert "vin-de-liqueur" not in stated
    readable = ble_styles.readable_text(AHR)
    assert "Rotweinstadt" not in readable and "keine Sorte" not in readable
    assert "Erzeugnisart „Perlwein“" in readable and "Sonstige Anforderungen" not in readable


def test_a_region_s_own_must_weights_state_a_praedikat_a_ceiling_does_not():
    text = ("2. Beschreibung\nWeißweine sind hell.\n"
            "c) 30 Milliäquivalent je Liter bei Wein, der den Begriff Beerenauslese trägt,\n")
    assert "grains-nobles" not in ble_styles.stated_styles(text)
    text += "5.1.2.4. Beerenauslese alle Rebsorten        15,3%vol / (110° Öchsle)\n"
    assert "grains-nobles" in ble_styles.stated_styles(text)


def test_an_ice_wine_is_not_a_late_harvest():
    """The EU reader's table files Eiswein under the late-harvest marker and
    leaves the ice-wine pill to stage 04's scan of the record's sections; a
    stub has no sections, so Baden listed Eiswein as a Prädikat and showed no
    ice wine (card validator, 2026-11-17)."""
    assert set(ble_styles.stated_styles(
        "4. Traditionelle Begriffe\nPrädikatswein ergänzt durch: Kabinett und Eiswein.\n")) \
        == {"icewine"}
    stated = ble_styles.stated_styles(AHR)
    assert {"icewine", "vendanges-tardives", "grains-nobles"} <= set(stated)
    # the acidity ceiling "bei Wein, der den Begriff … Eiswein trägt" states none
    assert "Milliäquivalent" not in stated["icewine"]


def test_sweetness_words_and_rotling_add_nothing():
    stated = ble_styles.stated_styles(
        "3.3 Organoleptisch\nLikörwein\nDiese Weine verfügen meist über eine Restsüße, können "
        "aber auch trocken ausgebaut werden. Ein Rotling entspricht optisch einem lieblichen "
        "Wein.\n")
    assert set(stated) == {"vin-de-liqueur"}


def test_a_negated_category_is_not_stated():
    assert ble_styles.stated_styles(
        "2. Beschreibung\nDer Wein darf keine Perlage entwickeln, die ihn zum Perlwein macht.\n"
    ) == {}


def test_blanc_de_noirs_is_white_where_no_white_wine_is_named():
    assert set(ble_styles.stated_styles(
        "2. Beschreibung\nRotweine und Blanc de Noirs werden erzeugt.\n")) == {"noir", "blanc"}


@pytest.mark.parametrize("quote, want", [
    ("Auch Schaum-, Perl- und Likörweine können die kontrollierte Ursprungsbezeichnung "
     "«AOC Schwyz» tragen.", ["sparkling", "semi-sparkling", "vin-de-liqueur"]),
    ("Auch Schaum- Perl- und Likörweine können die kontrollierte Ursprungsbezeichnung tragen.",
     ["sparkling", "semi-sparkling", "vin-de-liqueur"]),
    ("Réserve: … für Rotweine und von mindestens 12 Monaten für Weissweine auf den Markt "
     "gelangt.", ["blanc", "noir"]),
    ("Roséwein darf insgesamt bis höchstens 10% mit Weisswein verschnitten werden.",
     ["blanc", "rose"]),
    ("35 Milliäquivalent pro Liter bei Eiswein", []),
])
def test_clause_styles(quote, want):
    assert ble_styles.clause_styles(quote) == want


# ── the specifications themselves ────────────────────────────────────────

NO_EU_COLOURS = ("ahr", "baden", "hessische-bergstrae", "rheingau", "sachsen", "saale-unstrut")


@pytest.mark.parametrize("slug", NO_EU_COLOURS)
def test_every_region_without_an_eu_statement_states_its_types(slug):
    path = SIDECARS / f"{slug}.json"
    if not path.exists():
        pytest.skip("DE sidecars not extracted")
    side = json.loads(path.read_text(encoding="utf-8"))
    assert {"blanc", "noir", "rose", "sparkling", "semi-sparkling", "grains-nobles",
            "vendanges-tardives", "icewine"} <= set(side["styles_stated"]), slug
    assert set(side["styles_evidence"]) == set(side["styles_stated"])
    assert ("vin-de-liqueur" in side["styles_stated"]) == (slug in ("baden", "sachsen"))
    assert side["description_text"]


def test_a_landwein_states_its_three_colours_and_no_praedikat():
    if not (SIDECARS / "badischer-landwein.json").exists():
        pytest.skip("DE sidecars not extracted")
    for path in sorted(SIDECARS.glob("*landwein*.json")):
        side = json.loads(path.read_text(encoding="utf-8"))
        assert side["styles_stated"] == ["blanc", "noir", "rose"], path.stem


def test_the_augmenter_gives_stated_styles_to_a_record_with_no_colour(monkeypatch, tmp_path):
    side = {"role_split_method": "section-8-flat-no-split", "grapes": [],
            "styles_stated": ["blanc", "noir", "sparkling"],
            "styles_evidence": {"blanc": "W", "noir": "R", "sparkling": "S"}, "source": {}}
    for slug in ("stub", "amendment", "stated"):
        (tmp_path / f"{slug}.json").write_text(json.dumps(side), encoding="utf-8")
    monkeypatch.setattr(augment_de, "PRODUKTSPEZIFIKATION_DE", tmp_path)
    records = [
        {"country": "de", "slug": "stub", "styles": []},
        # an EU amendment that names its sparkling categories only (Saale-Unstrut)
        {"country": "de", "slug": "amendment", "styles": ["semi-sparkling", "sparkling"]},
        # an EU document that states its colours keeps them
        {"country": "de", "slug": "stated", "styles": ["blanc", "dry"]},
    ]
    assert augment_de.augment_de_records_with_produktspezifikation(records) == 3
    stub, amendment, stated = records
    assert stub["styles"] == ["blanc", "noir", "sparkling"]
    assert stub["produktspezifikation"]["styles_stated"] == ["blanc", "noir", "sparkling"]
    assert amendment["styles"] == ["blanc", "noir", "semi-sparkling", "sparkling"]
    assert amendment["produktspezifikation"]["styles_stated"] == ["blanc", "noir"]
    assert stated["styles"] == ["blanc", "dry"]
    assert "styles_stated" not in stated["produktspezifikation"]


# ── roster names ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, slug, colour", [
    ("Chardonel", "chardonel", "blanc"),
    ("Grünfränkisch", "grunfrankisch", "blanc"),
    ("Zähringer", "zahringer", "rose"),
    ("Muskat Gutedel", "muskat-gutedel", "blanc"),
    ("Ruling", "ruling", "blanc"),
    ("Kolor", "kolor", "noir"),
    ("Rabner", "rabaner", "blanc"),
    ("Cabernet Eidos", "cabernet-eidos", "noir"),
    ("Cantaro", "cantaro", "blanc"),
    ("Sauvignon Rytos", "sauvignon-rytos", "blanc"),
    ("Färbertraube", "farbertraube", "noir"),
    ("Blauer Gelbhölzer", "blauer-gelbholzer", "noir"),
    ("Blauer Kölner", "blauer-kolner", "noir"),
    ("Blauer Elbling", "blauer-elbling", "noir"),
    ("Mohrenkönigin", "mohrenkonigin", "noir"),
    ("Kleiner Fränkischer Burgunder", "kleiner-frankischer-burgunder", "noir"),
    ("Vogelfränkisch", "vogelfraenkisch", "blanc"),
    ("Grüner Adelfränkisch", "adelfraenkisch", "blanc"),
    ("Roter Müller Thurgau", "roter-muller-thurgau", "rose"),
    ("Roter Räuschling", "roter-raeuschling", "rose"),
])
def test_a_ble_roster_name_binds_its_own_variety_exactly(name, slug, colour):
    """Each had fuzzy-matched a look-alike or matched nothing (sweep of the
    28 sidecars, 2026-11-17): «Chardonel» read as Chardonnay on Baden."""
    hit = match_variety(name)
    assert hit and (hit.slug, hit.colour, hit.method) == (slug, colour, "exact"), (name, hit)


def test_the_look_alikes_keep_their_own_names():
    for name, slug in (("Chardonnay", "chardonnay"), ("Grüner Silvaner", "sylvaner"),
                       ("Roter Elbling", "roter-elbling"), ("Müller Thurgau", "muller-thurgau"),
                       ("Räuschling", "raeuschling"), ("Rabaner", "rabaner")):
        assert match_variety(name).slug == slug, name


def _stage_02f():
    spec = importlib.util.spec_from_file_location(
        "de_02f", ROOT / "scripts" / "de" / "02f_extract_produktspezifikation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_roster_name_that_lost_its_comma_is_two_varieties():
    """Mosel § 8: "Findling Gelber Kleinberger, Gelber Muskateller"."""
    matches = _stage_02f()._matches
    assert [(d["slug"], d["name"]) for d in matches("Findling Gelber Kleinberger")] == [
        ("bouvier", "Findling"), ("kleinberger", "Gelber Kleinberger")]
    # a hyphen set inside a word is closed before the matcher can split the
    # name at it: "burgunder" alone is a VIVC synonym of Blaufränkisch, and
    # Badischer Landwein and Landwein Oberrhein had no Pinot noir
    assert [(d["slug"], d["name"]) for d in matches("Blauer Spät-burgunder")] == [
        ("pinot-noir", "Blauer Spätburgunder")]
    assert [d["slug"] for d in matches("Müller-Thurgau")] == ["muller-thurgau"]
    assert [d["slug"] for d in matches("Riesling-Silvaner")] == ["muller-thurgau"]
    # a whole name is never cut, nor a name the lexicon lacks
    assert [d["slug"] for d in matches("Gelber Kleinberger")] == ["kleinberger"]
    assert matches("Unbekannte Neuzüchtung") == []
    assert matches("die Voraussetzung sind") == []


def test_the_last_name_of_a_list_is_cut_from_the_sentence_after_it():
    """Sachsen's roster ends "… Regent, Saint Laurent" and the next paragraph
    was joined to it; Hessische Bergstraße's last name carried the page
    footer, Württemberg's the sentence after its full stop. None of the three
    varieties was read (card validator on Sachsen, 2026-11-17)."""
    matches = _stage_02f()._matches
    assert [(d["slug"], d["name"]) for d in matches(
        "Saint Laurent Die in Anbaueignungsprüfungen angestellten Rebsorten sind ebenfalls "
        "zu Produktion von Landwein zugelassen")] == [("sankt-laurent", "Saint Laurent")]
    assert [(d["slug"], d["name"]) for d in matches("Blauer Zweigelt. Seite 6 von 10 -7-")] == [
        ("zweigelt", "Blauer Zweigelt")]
    assert [d["slug"] for d in matches(
        "Tauberschwarz. In diese Listen können weitere Rebsorten aufgenommen werden")] == [
        "tauberschwarz"]
    # prose that opens on no variety name stays unread, a code is no name
    assert matches("wenn die Voraussetzungen für die Klassifizierung festgestellt worden sind") == []
    assert matches("VB Cal. 1-22 Rotling Alle genannten Rebsorten dürfen verwendet werden") == []
    assert matches("„Alter fränkischer Satz“ verwendet werden") == []


def test_cabernet_bordo_is_a_variety_of_its_own():
    """VIVC #22814 CABERNET BORDO (Germany); the BLE's list of classified
    varieties has it beside Cabernet Franc. It was folded into Cabernet franc
    and six German lists that print both showed one pill."""
    from _lib.grape_entity import match_variety
    assert match_variety("Cabernet Bordo").slug == "cabernet-bordo"
    assert match_variety("Cabernet Franc").slug == "cabernet-franc"
    assert match_variety("Roter Traminer").slug == "gewurztraminer"


def test_section_8_ends_at_the_link_section_whatever_its_dot(tmp_path):
    """Baden, Franken, Sachsen and Württemberg print "9. Angaben": their § 8
    ran to the end of the document (Baden: 141 "unmatched names")."""
    from _lib.de import produktspezifikation as ps

    text = ("8. Zugelassene Keltertraubensorten\nWeiße Rebsorten:\nRiesling, Kerner\n"
            "Rote Rebsorten:\nRegent, Kolor\n\n9. Angaben, aus denen sich der Zusammenhang "
            "ergibt\nfruchtige, stoffige Weine, die für die Region spezifisch sind\n")
    assert "stoffige" not in ps._slice_section_a_8(text)
    assert ps._parse_template_a_authorised(text) == {"white": ["Riesling", "Kerner"],
                                                      "red": ["Regent", "Kolor"]}
    side = SIDECARS / "baden.json"
    if side.exists():
        baden = json.loads(side.read_text(encoding="utf-8"))
        assert all(len(n) < 40 for n in baden["unmatched_names"]), "prose in the roster"
        slugs = {g["slug"] for g in baden["grapes"]}
        assert {"chardonel", "chardonnay", "zahringer", "muskat-gutedel", "ruling", "kolor"} <= slugs


def test_the_two_baden_landweine_carry_pinot_noir():
    for slug in ("badischer-landwein", "landwein-oberrhein"):
        path = SIDECARS / f"{slug}.json"
        if not path.exists():
            pytest.skip("DE sidecars not extracted")
        grapes = {g["slug"]: g["name"] for g in json.loads(path.read_text(encoding="utf-8"))["grapes"]}
        assert grapes.get("pinot-noir") == "Blauer Spätburgunder", slug
