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
