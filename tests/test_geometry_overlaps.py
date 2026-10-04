"""scripts/audit_geometry_overlaps.py — the sliver classes (2026-09-25)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_geometry_overlaps import Feat, Overlap, classify, root_source  # noqa: E402
from shapely.geometry import box  # noqa: E402


def _feat(slug, country, kind, src, parent=""):
    return Feat(
        {"slug": slug, "name": slug, "country": country, "kind": kind,
         "geom_source": src, "parent_slug": parent},
        box(0, 0, 1000, 1000),
    )


def _ov(a, b, width_km, area_km2=5.0):
    return Overlap(a, b, area_km2, 0.02, 0.03, width_km)


def test_border_is_a_thin_band_between_two_countries():
    a, b = _feat("x", "es", "DOP", "mapa-zone"), _feat("y", "pt", "DOP", "caop-concelho-union")
    assert classify(_ov(a, b, 0.1), a.geom_source, b.geom_source, 0.3) == "border"
    assert classify(_ov(a, b, 1.5), a.geom_source, b.geom_source, 0.3) == "suspicious"


def test_tier_is_a_pgi_over_a_pdo_of_one_country():
    a, b = _feat("x", "fr", "AOC", "aires-csv"), _feat("y", "fr", "IGP", "aires-csv")
    assert classify(_ov(a, b, 2.0), "aires-csv", "aires-csv", 0.3) == "tier"
    c = _feat("z", "fr", "EDV", "aires-csv")
    assert classify(_ov(a, c, 2.0), "aires-csv", "aires-csv", 0.3) == "tier"


def test_generalisation_is_thin_and_from_two_sources():
    a = _feat("x", "it", "DOP", "figshare-pdo")
    b = _feat("y", "it", "DOP", "gisco-provincia-union")
    assert classify(_ov(a, b, 0.05), a.geom_source, b.geom_source, 0.3) == "generalisation"
    # wide, one side a commune list of ours → suspicious
    assert classify(_ov(a, b, 1.0), a.geom_source, b.geom_source, 0.3) == "suspicious"


def test_source_drawn_when_both_polygons_come_from_a_zone_layer():
    a = _feat("x", "it", "DOP", "geoportal-zone:toscana")
    b = _feat("y", "it", "DOP", "geoportal-zone:toscana")
    assert classify(_ov(a, b, 1.9), a.geom_source, b.geom_source, 0.3) == "source"
    c, d = _feat("c", "es", "DOP", "mapa-zone"), _feat("d", "es", "DOP", "figshare-pdo")
    assert classify(_ov(c, d, 1.0), c.geom_source, d.geom_source, 0.3) == "source"


def test_same_tier_commune_lists_stay_suspicious():
    a, b = _feat("x", "fr", "AOC", "aires-csv"), _feat("y", "fr", "AOC", "aires-csv")
    assert classify(_ov(a, b, 1.7), "aires-csv", "aires-csv", 0.3) == "suspicious"
    assert classify(_ov(a, b, 0.1), "aires-csv", "aires-csv", 0.3) == "suspicious"


def test_root_source_reads_through_an_inheriting_sub_denomination():
    parent = _feat("p", "it", "DOP", "geoportal-zone:veneto")
    child = _feat("c", "it", "DOP", "parent-appellation", parent="p")
    by_slug = {"p": parent, "c": child}
    assert root_source(child, by_slug) == "geoportal-zone:veneto"
    assert root_source(parent, by_slug) == "geoportal-zone:veneto"
