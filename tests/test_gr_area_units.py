"""The Greek area-units layer (2026-09-24): what `parse_area_units` separates in a
spec's delimitation prose, the phonetic / stem keys the resolver falls back to,
and the per-record pin file. Texts are the regulator's own sentences (ΥΠΑΑΤ
national specs, raw/gr/national-specs-extracted), trimmed to the clause."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.gr.commune import (  # noqa: E402
    _normalise_commune,
    parse_area_units,
    record_pins,
)
from _lib.gr.geometry import phonetic_key, stem_key  # noqa: E402

OVERRIDES = ROOT / "scripts" / "_lib" / "gr" / "commune_overrides.json"
LAU_TABLE = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"


def test_container_of_a_list_is_not_a_member_but_a_listed_container_is():
    # Κάρυστος: the δήμος opens a parenthesised list and is also listed in it
    u = parse_area_units(
        "περιλαμβάνει τις περιοχές του Δήμου Καρύστου (Δ.Δ. Καρύστου, Αετού, Γραμπιάς, "
        "Καλυβίων, Πλατανιστού) τα Δ.Δ. του Δήμου Μαρμαρίου και των κοινοτήτων Αμυγδαλιάς, "
        "Καφηρέως και Κομήτου και σε υψόμετρο από 10 μέτρα."
    )
    assert u["communities"][:5] == ["Καρύστου", "Αετού", "Γραμπιάς", "Καλυβίων", "Πλατανιστού"]
    assert "Μαρμαρίου" not in u["communities"]
    assert u["dimoi"] == ["Μαρμαρίου"]  # "τα Δ.Δ. του Δήμου Μαρμαρίου": every community
    assert "Καρύστου" in u["containers"]


def test_dimos_specified_by_kai_sygkekrimena_is_a_container():
    # Θαψανά / Τύρναβος: "του Δ.Δ. Λευκών του Δήμου Πάρου", "του Δήμου Τυρνάβου και συγκεκριμένα"
    u = parse_area_units("περιλαμβάνει τις περιοχές του Δ.Δ. Λευκών του Δήμου Πάρου.")
    assert u["communities"] == ["Λευκών"] and u["dimoi"] == [] and u["containers"] == ["Πάρου"]
    u = parse_area_units(
        "περιλαμβάνει τις περιοχές του Δήμου Τυρνάβου και συγκεκριμένα της Δημοτικής Κοινότητας "
        "Τυρνάβου και των Τοπικών Κοινοτήτων Αργυροπουλείου, Δαμασίου και Δένδρων Τυρνάβου της "
        "Δημοτικής Ενότητας Τυρνάβου και της Δημοτικής Κοινότητας Αμπελώνος και των Τοπικών "
        "Κοινοτήτων Βρυοτόπου, Δελερίων και Ροδιάς της Δημοτικής Ενότητας Αμπελώνος."
    )
    assert u["dimoi"] == [] and u["units"] == []
    assert u["communities"] == [
        "Τυρνάβου", "Αργυροπουλείου", "Δαμασίου", "Δένδρων Τυρνάβου",
        "Αμπελώνος", "Βρυοτόπου", "Δελερίων", "Ροδιάς",
    ]


def test_coordinated_unit_after_a_list_is_a_member():
    # Πλαγιές Κιθαιρώνα: the community's unit is a container, the second unit is joined by "καθώς και"
    u = parse_area_units(
        "περιλαμβάνει τις περιοχές στις Πλαγιές του όρους Κιθαιρώνα και συγκεκριμένα στα "
        "διοικητικά όρια της Τοπικής Κοινότητας Πλαταιών της Δημοτικής Ενότητας Πλαταιών του "
        "Ν. Βοιωτίας καθώς και της Δημοτικής Ενότητας Ερυθρών του Ν. Αττικής σε υψόμετρο από 300 έως 400 μέτρα."
    )
    assert u["communities"] == ["Πλαταιών"] and u["units"] == ["Ερυθρών"]
    # Πλαγιές Πάρνηθας: "και την περιοχή της Δημοτικής Κοινότητας Αφιδνών" is a member
    u = parse_area_units(
        "περιλαμβάνει τις περιοχές στα διοικητικά όρια των Δ.Δ. Πύλης, Σκούρτων και Στεφάνης του "
        "Δήμου Δερβενοχωρίων του Νομού Βοιωτίας και την περιοχή της Δημοτικής Κοινότητας Αφιδνών "
        "του Νομού Αττικής σε υψόμετρο από 280 έως 540 μέτρα."
    )
    assert u["communities"] == ["Πύλης", "Σκούρτων", "Στεφάνης", "Αφιδνών"]
    assert u["containers"] == ["Δερβενοχωρίων"]


def test_municipal_units_named_as_members_and_their_dimos_as_container():
    u = parse_area_units(
        "Υπουργική Απόφαση αριθ. 297688/20.9.2006 (ΦΕΚ 1436/B/29.9.2006) η οποία τροποποιήθηκε από "
        "την αριθ. 201641/15-12-2011 (ΦΕΚ 2899/Β/15.12.2011) Η οριοθετημένη περιοχή περιλαμβάνει "
        "τις κτηματικές περιοχές των Δημοτικών Ενοτήτων Παληοκάστρου και Παραληθαίων του Δήμου "
        "Τρικκαίων, των Δημοτικών Ενοτήτων Βασιλικής, Καλαμπάκας, Τυμφαίων και Χασίων του Δήμου "
        "Καλαμπάκας του Ν. Τρικάλων, σε υψόμετρο από 150 έως 800 μέτρα."
    )
    assert u["units"] == ["Παληοκάστρου", "Παραληθαίων", "Βασιλικής", "Καλαμπάκας", "Τυμφαίων", "Χασίων"]
    assert u["dimoi"] == [] and "Τρικκαίων" in u["containers"]
    assert u["decree_year"] == 2011  # the latest decree dates the tier words


def test_locality_of_a_dimos_is_drawn_as_its_container():
    u = parse_area_units("περιλαμβάνει την περιοχή Ριτσώνα του Δήμου Αυλίδας στο Νομό Ευβοίας σε υψόμετρο μεγαλύτερο από 30 μέτρα.")
    assert u["localities"] == [{"name": "Ριτσώνα", "container": "Αυλίδας", "tier": "dimos"}]
    assert u["communities"] == [] and u["dimoi"] == []


def test_whole_unit_texts_and_exclusions():
    u = parse_area_units("περιλαμβάνει τις περιοχές που βρίσκονται στα διοικητικά όρια του νομού Ηλείας σε υψόμετρο από 10 έως 700 μέτρα. Εξαιρούνται οι περιοχές των αποξηραμένων λιμνών Κοτυχίου, Μουριάς και Αγουλινίτσας.")
    assert u["whole_unit"] and u["communities"] == []
    u = parse_area_units("περιλαμβάνει τις Κοινότητες Τρικώμου, Κοσματίου και στην ευρύτερη περιοχή του Ν. Γρεβενών.")
    assert u["whole_unit"]


def test_abbreviated_tier_and_prose_items_are_cleaned():
    u = parse_area_units("περιλαμβάνει τις περιοχές των Δ.Δ Κάρπης, Γρίβας, Γουμένισσας, Γερακώνας και Φιλυριάς του Δήμου Γουμένισσας και στα Δ.Δ. Ευρωπού, Πολυπέτρου και Τούμπας του Δήμου Ευρωπού του Νομού Κιλκίς σε υψόμετρο μεγαλύτερο από 80 μέτρα.")
    assert u["communities"] == ["Κάρπης", "Γρίβας", "Γουμένισσας", "Γερακώνας", "Φιλυριάς", "Ευρωπού", "Πολυπέτρου", "Τούμπας"]
    assert "Υπουργικές Αποφάσεις" not in parse_area_units(
        "τροποποιήθηκε από τις αριθ. 278475 / 26-2-2008 (ΦΕΚ 391/Β/7-3-2008.) Υπουργικές Αποφάσεις. "
        "Η οριοθετημένη περιοχή περιλαμβάνει τα Δ.Δ. Μαρώνειας, Ξυλαγανής του Δήμου Μαρώνειας."
    )["communities"]


@pytest.mark.parametrize("spec, gisco, how", [
    ("Κομήτου", "Κομίτου", "phonetic"),
    ("Ρογών", "Ρωγών", "phonetic"),
    ("Μεσσοράχης", "Μεσορράχης", "phonetic"),
    ("Μυρoδάτου", "Μυρωδάτου", "phonetic"),  # Latin o in the spec
    ("Κερασίτσας", "Κερασίτσης", "stem"),
    ("Λάρυμνας", "Λαρύμνης", "stem"),
    ("Πυθαγόρειο", "Πυθαγορείου", "stem"),
    ("Δρακαίοι", "Δρακαίων", "stem"),
    ("Καστελίου", "Καστελλίων", "stem"),
])
def test_phonetic_and_stem_keys_bridge_the_spec_and_gisco_spellings(spec, gisco, how):
    a, b = _normalise_commune(spec), _normalise_commune(gisco)
    if how == "phonetic":
        assert phonetic_key(a) == phonetic_key(b)
    assert stem_key(a) == stem_key(b)


def test_phonetic_key_keeps_ou_apart_from_i():
    assert phonetic_key("κομήτου") != phonetic_key("κομήτοι")
    assert phonetic_key("λουτρών") == phonetic_key("λουτρων")


def test_pin_file_is_sourced_and_well_formed():
    doc = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    recs = doc["records"]
    assert recs, "no pins"
    for slug, names in recs.items():
        for name, spec in names.items():
            for gid in (spec["gisco"] if isinstance(spec["gisco"], list) else [spec["gisco"]]):
                assert gid.startswith("EL_") and gid[3:].isdigit() and len(gid) in (5, 7, 9, 11), (slug, name, gid)
            assert spec["reason"] and spec["source"], (slug, name)
            # an empty pin marks a source defect and cites the regulator's own text
            public = ("wikipedia.org", "GISCO") + (("minagric.gr",) if spec["gisco"] == [] else ())
            assert any(tok in spec["source"] for tok in public), (slug, name)
    assert record_pins("karystos")[_normalise_commune("Κομήτου")] == "EL_29050202"
    assert record_pins("no-such-record") == {}


@pytest.mark.skipif(not LAU_TABLE.exists(), reason="GISCO LAU zip not fetched")
def test_every_pin_names_a_gisco_row_or_prefix():
    import geopandas as gpd

    doc = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    ids = set(gpd.read_file(LAU_TABLE, where="CNTR_CODE='EL'", ignore_geometry=True)["GISCO_ID"])
    for slug, names in doc["records"].items():
        for name, spec in names.items():
            for gid in (spec["gisco"] if isinstance(spec["gisco"], list) else [spec["gisco"]]):
                assert any(i == gid or i.startswith(gid) for i in ids), (slug, name, gid)


def test_town_level_phrasings_2026_09_24():
    # Νέα Μεσημβρία: an article between the tier word and the name
    u = parse_area_units(
        "περιλαμβάνει τα διοικητικά όρια του Δημοτικού Διαμερίσματος της Νέας Μεσημβρίας "
        "του Δήμου Αγίου Αθανασίου του Νομού Θεσσαλονίκης."
    )
    assert u["communities"] == ["Νέας Μεσημβρίας"] and u["containers"] == ["Αγίου Αθανασίου"]
    # Ίλιον: a toponym inside a community — the community is its proxy
    u = parse_area_units("περιλαμβάνει την περιοχή με τοπωνύμιο «Πύργος Βασιλίσσης» στο Ίλιον Αττικής.")
    assert u["localities"] == [{"name": "Πύργος Βασιλίσσης", "container": "Ίλιον Αττικής", "tier": "community"}]
    assert u["communities"] == []
    # Πλαγιές Πεντελικού: a boundary traced through named places, "Αγ." kept whole
    u = parse_area_units(
        "περιλαμβάνει την αμπελουργική ζώνη που οριοθετείται από την διαχωριστική γραμμή "
        "Δροσιά- Άνοιξη- Άγιος Στέφανος- Λίμνη Μαραθώνα – Αγ. Γεώργιος Βρανά – Κουκουνάρι – "
        "Σταματοβούνι – Διόνυσος – Δροσιά."
    )
    assert u["landmarks"] == [
        "Δροσιά", "Άνοιξη", "Άγιος Στέφανος", "Λίμνη Μαραθώνα", "Αγ. Γεώργιος Βρανά",
        "Κουκουνάρι", "Σταματοβούνι", "Διόνυσος",
    ]
    assert u["communities"] == []
    # a former επαρχία, also inside a text that names the prefecture (whole-unit flag stays)
    u = parse_area_units("βρίσκονται στα διοικητικά όρια των περιοχών τέως επαρχίας Μεγάρων.")
    assert u["eparchies"] == ["Μεγάρων"] and not u["whole_unit"]
    u = parse_area_units("βρίσκονται στα διοικητικά όρια του Νομού Ευβοίας στην πρώην επαρχία Χαλκίδας.")
    assert u["eparchies"] == ["Χαλκίδας"] and u["whole_unit"]
    # Μεταξάτα: "της νήσου Κεφαλληνίας" qualifies a named area — not a whole-island text
    u = parse_area_units("περιλαμβάνει την περιοχή Μοναστήρια Μεταξάτων της νήσου Κεφαλληνίας.")
    assert not u["whole_unit"] and u["communities"] == ["Μοναστήρια Μεταξάτων"]
    assert parse_area_units("περιλαμβάνει τις περιοχές της νήσου Ικαρίας σε υψόμετρο από 30 μέτρα.")["whole_unit"]
    # Σιάτιστα (salvaged .doc): a municipal unit named as the area
    u = parse_area_units(
        "ΟΡΙΟΘΕΤΗΜΕΝΗ ΠΕΡΙΟΧΗ Η οριοθετημένη περιοχή για την παραγωγή των οίνων Π.Γ.Ε. Σιάτιστα "
        "περιλαμβάνει τη διοικητική περιοχή της Δημοτικής Ενότητας Σιάτιστας του Δήμου Βοίου "
        "της περιφερειακής ενότητας Κοζάνης σε υψόμετρο 600 μέτρα και άνω. ΜΕΓΙΣΤΗ ΑΠΟΔΟΣΗ"
    )
    assert u["units"] == ["Σιάτιστας"] and u["containers"] == ["Βοίου"] and not u["whole_unit"]


@pytest.mark.parametrize("spec, gisco", [
    ("Παιανία", "Παιανίας"),          # nominative -ία
    ("Άγιος Στέφανος", "Αγίου Στεφάνου"),  # the short-stem word
    ("Άνοιξη", "Ανοίξεως"),
    ("Σιάτιστας", "Σιατίστης"),
    ("Δροσιά", "Δροσιάς"),
])
def test_stem_key_bridges_town_spellings(spec, gisco):
    assert stem_key(_normalise_commune(spec)) == stem_key(_normalise_commune(gisco))


def test_eparchy_pins_are_sourced_and_well_formed():
    from _lib.gr.commune import eparchy_pins

    doc = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    for name, spec in (doc.get("eparchies") or {}).items():
        assert isinstance(spec["gisco"], list) and spec["gisco"], name
        for gid in spec["gisco"]:
            assert gid.startswith("EL_") and gid[3:].isdigit() and len(gid) in (5, 7, 9, 11), (name, gid)
        assert spec["reason"] and spec["source"] and "wikipedia.org" in spec["source"], name
        assert _normalise_commune(name) in eparchy_pins()


def test_boundary_landmarks_draw_the_polygon_they_outline():
    from pathlib import Path

    from _lib.gr.commune import landmark_points
    from _lib.gr.geometry import GRPolygonIndex

    idx = GRPolygonIndex(figshare_gpkg=Path("/nonexistent"))
    units = parse_area_units(
        "περιλαμβάνει την αμπελουργική ζώνη που οριοθετείται από την διαχωριστική γραμμή "
        "Δροσιά- Άνοιξη- Άγιος Στέφανος- Λίμνη Μαραθώνα – Αγ. Γεώργιος Βρανά – Κουκουνάρι – "
        "Σταματοβούνι – Διόνυσος – Δροσιά."
    )
    points = landmark_points("playies-pentelikou")
    assert points["Κουκουνάρι"] is None and points["Διόνυσος"] == (23.8837, 38.1011)
    geom, stats = idx.units_union(units, landmark_points=points)
    assert geom is not None and geom.area > 0
    assert stats["landmarks_polygon"] == [
        "Δροσιά", "Άνοιξη", "Άγιος Στέφανος", "Λίμνη Μαραθώνα", "Αγ. Γεώργιος Βρανά", "Διόνυσος",
    ]
    assert stats["landmarks_unmatched"] == ["Κουκουνάρι", "Σταματοβούνι"]
    from shapely.geometry import Point

    assert geom.contains(Point(23.875, 38.1315))  # Σταμάτα, inside the line, not named by it
    assert geom.contains(Point(23.8748, 38.1169))  # Ροδόπολη
    # too few located points: the coarser unit reading applies instead
    geom2, stats2 = idx.units_union(units, landmark_points={"Δροσιά": (23.85, 38.1167)})
    assert geom2 is None and stats2["landmarks_polygon"] == []


def test_landmark_file_is_sourced():
    doc = json.loads((ROOT / "scripts" / "_lib" / "gr" / "landmarks.json").read_text(encoding="utf-8"))
    for slug, names in doc["records"].items():
        for name, spec in names.items():
            if spec is None:
                assert slug in doc.get("_unlocated", {}), (slug, name)
                continue
            assert -90 < spec["lat"] < 90 and -180 < spec["lon"] < 180, (slug, name)
            assert spec["source"].startswith(("wikidata:Q", "geonames:")), (slug, name)
