"""The polygon-vs-text audit's classification and layer helpers
(scripts/audit_geometry_vs_text.py), on synthetic squares."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("audit_geometry_vs_text", ROOT / "scripts" / "audit_geometry_vs_text.py")
agt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agt)


def _layer():
    layer = agt.Layer("test")
    for i in range(4):
        layer.add(f"u{i}", f"Unit {i}", box(i * 10, 0, i * 10 + 10, 10), cntr="XX")
    layer.add("dup", "Castro", box(100, 0, 110, 10), cntr="XX")
    layer.add("dup2", "Castro", box(200, 0, 210, 10), cntr="YY")
    layer.build()
    return layer


def test_norm_strips_articles_diacritics_and_brackets():
    assert agt.norm("Les Baux-de-Provence") == "baux de provence"
    assert agt.norm("Vilardevós (San Miguel)") == "vilardevos"
    assert agt.norm("L'Étoile") == "etoile"


def test_layer_coverage_and_name_lookup():
    layer = _layer()
    geom = box(0, 0, 25, 10)  # u0, u1 whole; u2 half
    whole, part = layer.covered(geom)
    assert {layer.ids[i] for i in whole} == {"u0", "u1"} and {layer.ids[i] for i in part} == {"u2"}
    assert len(layer.by_name("castro")) == 2 and len(layer.by_name("Castro", within={"cntr": "YY"})) == 1
    assert layer.by_name("unit 3") == [3]


def test_classify_commune_union_vs_zone_sources():
    named = {"u0", "u1", "u2"}
    ok, d = agt.classify("gisco-commune-list", named, {"u0", "u1", "u2"}, set(), named_above=[])
    assert ok == "OK" and d["missing"] == [] and d["extra"] == []
    sus, d = agt.classify("gisco-commune-list", named, {"u0", "u1", "u3"}, set(), named_above=[])
    assert sus == "SUSPECT" and d["missing"] == ["u2"] and d["extra"] == ["u3"]
    # a parcellaire record draws parts of its named communes: expected
    ok, d = agt.classify("parcellaire", named, set(), {"u0", "u1", "u2"}, named_above=[])
    assert ok == "OK" and d["part"] == ["u0", "u1", "u2"]
    # a zone drawing two whole units the text never names is the signal
    sus, d = agt.classify("mapa-zone", named, {"u0", "u1", "u2", "u3", "dup"}, set(), named_above=[])
    assert sus == "SUSPECT" and d["extra"] == ["dup", "u3"]
    assert agt.classify("figshare-pdo", set(), {"u0"}, set(), named_above=["Provincia di X"])[0] == "ABOVE-COMMUNE"
    assert agt.classify("figshare-pdo", set(), {"u0"}, set(), named_above=[])[0] == "NO-UNITS"


def test_overrides_table_is_well_formed():
    import json
    d = json.loads((ROOT / "scripts" / "_lib" / "geometry_text_overrides.json").read_text(encoding="utf-8"))
    for slug, e in d.items():
        if slug.startswith("_"):
            continue
        assert {"reason", "source", "verified"} <= set(e), slug
        assert isinstance(e.get("missing", []), list) and isinstance(e.get("extra", []), list)


def _bg_layer():
    layer = agt.Layer("bg")
    for i, (uid, name) in enumerate([("BG_RSE04", "Бяла"), ("BG_VAR05", "Бяла"), ("BG_PVN10", "Долна Митрополия"),
                                     ("BG_PVN11", "Долни Дъбник"), ("BG_VAR09", "Вълчи дол")]):
        layer.add(uid, name, box(i * 10, 0, i * 10 + 10, 10), cntr="BG")
    layer.build()
    return layer


def test_bg_names_are_held_to_their_oblast_header():
    """Two obshtini are called Бяла: the text's oblast header picks one; the
    space-closed and abbreviated spellings of Дунавска равнина's text bind
    inside the oblast only (2026-10-24)."""
    layer = _bg_layer()
    assert [layer.ids[i] for i in agt._bg_oblast_hits(layer, "Бяла", "BG_VAR")] == ["BG_VAR05"]
    assert [layer.ids[i] for i in agt._bg_oblast_hits(layer, "Вълчидол", "BG_VAR")] == ["BG_VAR09"]
    assert [layer.ids[i] for i in agt._bg_oblast_hits(layer, "Д. Митрополия", "BG_PVN")] == ["BG_PVN10"]
    assert agt._bg_oblast_hits(layer, "Д. Митрополия", "BG_VAR") == []
    rec = {"geo_communes": ["Бяла", "Бяла"], "geo_communes_scoped": [["Бяла", "RSE"], ["Бяла", "VAR"]],
           "geo_area_brief": "Област Русе: Бяла. Област Варна: Бяла."}
    out = agt.named_units("bg", "x", rec, {}, {}, layer, geom=box(0, 0, 10, 10))
    assert out["ids"] == {"BG_RSE04", "BG_VAR05"} and not out["unresolved"]


def test_fr_token_cuts_a_partial_commune_qualifier():
    # "Commune retenue en partie : X pour le seul territoire de …" — X is the
    # commune, drawn in part only (2026-10-30)
    assert agt.fr_token("Mercurol-Veaunes pour le seul territoire de la commune déléguée de Mercurol") == ("Mercurol-Veaunes", True)
    assert agt.fr_token("Kaysersberg Vignoble pour le territoire des communes déléguées de Kientzheim et de Sigolsheim") == ("Kaysersberg Vignoble", True)
    assert agt.fr_token("Tain-l’Hermitage") == ("Tain-l’Hermitage", False)


def test_a_curated_drink_area_is_pinned_unless_a_named_unit_is_missing():
    extra_only = {"missing": [], "extra": ["a", "b", "c"]}
    assert agt.curated_area_bucket("SUSPECT", "drinks-area-pin", extra_only) == "PINNED"
    assert agt.curated_area_bucket("SUSPECT", "gisco-nuts-union", extra_only) == "PINNED"
    # a name the parser read that the polygon lacks is still a finding
    assert agt.curated_area_bucket("SUSPECT", "drinks-area-pin", {"missing": ["x"], "extra": []}) == "SUSPECT"
    # every other source keeps its verdict, and so does a verdict that is not SUSPECT
    assert agt.curated_area_bucket("SUSPECT", "aires-csv", extra_only) == "SUSPECT"
    assert agt.curated_area_bucket("OK", "drinks-area-pin", extra_only) == "OK"
