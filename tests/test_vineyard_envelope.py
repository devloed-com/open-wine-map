"""The generalised vineyard footprint (scripts/_lib/vineyard_envelope.py).

Pins the properties the map relies on: parts closer than 2r merge and parts
farther apart stay separate; the footprint contains the input and never
leaves its r-dilation; the component decomposition gives the same answer as
the monolithic closing; the disk cache is keyed on the input geometry and
round-trips; the shape metrics distinguish a fragmented record from a compact
one of the same area.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import shapely
from shapely.geometry import MultiPolygon, box
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import vineyard_envelope as ve  # noqa: E402


def _to4326(g):
    return shp_transform(ve._TO_4326, g)


def _to3035(g):
    return shp_transform(ve._TO_3035, g)


# Two 400 m squares in EPSG:3035 (somewhere in Burgundy), `gap` metres apart.
def _two_squares(gap: float) -> MultiPolygon:
    x0, y0 = 3_842_000.0, 2_756_000.0
    a = box(x0, y0, x0 + 400, y0 + 400)
    b = box(x0 + 400 + gap, y0, x0 + 800 + gap, y0 + 400)
    return MultiPolygon([a, b])


def test_parts_within_2r_merge_and_farther_stay_apart() -> None:
    near = ve.envelope_3035(_two_squares(300), 250)
    far = ve.envelope_3035(_two_squares(700), 250)
    assert near.geom_type == "Polygon"
    assert far.geom_type == "MultiPolygon" and len(far.geoms) == 2


def test_diagonal_neighbours_within_2r_share_a_component() -> None:
    # Offset (280, 280) m: centre-to-corner distance 396 m < 2r = 500 m, but a
    # rounded r-buffer of the bounding box would miss the corner (r·cos 45°).
    x0, y0 = 3_842_000.0, 2_756_000.0
    a = box(x0, y0, x0 + 400, y0 + 400)
    b = box(x0 + 400 + 280, y0 + 400 + 280, x0 + 800 + 280, y0 + 800 + 280)
    groups = ve._components([a, b], 250)
    assert len(groups) == 1
    # Whether the neck survives the erosion is the closing's business; the
    # decomposition must give the same answer as the monolithic closing.
    env = ve.envelope_3035(MultiPolygon([a, b]), 250)
    mono = shapely.make_valid(
        MultiPolygon([a, b]).buffer(250, quad_segs=3).buffer(-250, quad_segs=3)
        .simplify(ve.ENVELOPE_SIMPLIFY_M, preserve_topology=True)
    )
    assert env.symmetric_difference(mono).area / mono.area < 1e-3


def test_footprint_contains_input_and_stays_inside_dilation() -> None:
    g = _two_squares(300)
    env = ve.envelope_3035(g, 250)
    tol = ve.containment_tolerance_m(250)
    assert tol < 40
    assert env.buffer(tol).contains(g)
    assert g.buffer(250 + ve.ENVELOPE_SIMPLIFY_M + 1).contains(env)
    # The bridged gap is the only area gained: 300 m × 400 m at most.
    assert env.area - g.area <= 300 * 400 + 1e-6


def test_component_decomposition_matches_monolithic_closing() -> None:
    # Three clusters far apart, each with a bridgeable pair inside.
    clusters = []
    for k in range(3):
        for p in _two_squares(300).geoms:
            clusters.append(shapely.affinity.translate(p, xoff=k * 5000))
    g = MultiPolygon(clusters)
    groups = ve._components(list(g.geoms), 250)
    assert sorted(len(x) for x in groups) == [2, 2, 2]
    decomposed = ve.envelope_3035(g, 250)
    monolithic = shapely.make_valid(
        g.buffer(250, quad_segs=ve.ENVELOPE_QUAD_SEGS)
        .buffer(-250, quad_segs=ve.ENVELOPE_QUAD_SEGS)
        .simplify(ve.ENVELOPE_SIMPLIFY_M, preserve_topology=True)
    )
    assert abs(decomposed.area - monolithic.area) / monolithic.area < 1e-3
    assert decomposed.symmetric_difference(monolithic).area / monolithic.area < 1e-2


def test_cache_round_trip_is_keyed_on_input(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ve, "CACHE_DIR", tmp_path)
    g = _to4326(_two_squares(300))
    stats: dict = {}
    first = ve.envelope(g, stats=stats)
    assert stats == pytest.approx({"misses": 1, "secs": stats["secs"]})
    second = ve.envelope(g, stats=stats)
    assert stats["hits"] == 1
    assert first.equals_exact(second, 1e-12)
    files = list(tmp_path.rglob("*.wkb"))
    assert len(files) == 1
    # A different input → a different key, never the cached answer.
    other = _to4326(_two_squares(700))
    ve.envelope(other, stats=stats)
    assert stats["misses"] == 2
    assert len(list(tmp_path.rglob("*.wkb"))) == 2
    assert ve.cache_key(g) != ve.cache_key(other)


def test_envelope_never_empty_and_round_trips_projection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ve, "CACHE_DIR", tmp_path)
    g = _to4326(_two_squares(300))
    env = ve.envelope(g)
    assert not env.is_empty
    back = _to3035(env)
    assert back.buffer(ve.containment_tolerance_m()).contains(_two_squares(300))


def test_shape_metrics_separate_fragmented_from_compact() -> None:
    compact = _to4326(box(3_842_000, 2_756_000, 3_842_000 + 3000, 2_756_000 + 3000))
    # Same total area, 36 separate 500 m squares.
    cells = [
        box(3_842_000 + i * 1000, 2_756_000 + j * 1000,
            3_842_000 + i * 1000 + 500, 2_756_000 + j * 1000 + 500)
        for i in range(6) for j in range(6)
    ]
    fragmented = _to4326(MultiPolygon(cells))
    p1, f1 = ve.shape_metrics(compact)
    p2, f2 = ve.shape_metrics(fragmented)
    assert (p1, p2) == (1, 36)
    # Perimeter/area: 4·3000/9e6 vs 36·4·500/9e6 — six times the ink.
    assert f1 == pytest.approx(4 * 3000 / 9e6, rel=0.03)
    assert f2 == pytest.approx(36 * 4 * 500 / 9e6, rel=0.03)


def test_is_envelope_source() -> None:
    assert ve.is_envelope_source("fr", "parcellaire")
    assert ve.is_envelope_source("fr", "parcellaire-dgc")
    assert not ve.is_envelope_source("fr", "aires-csv")
    assert not ve.is_envelope_source("es", "parcellaire")
    assert not ve.is_envelope_source("fr", "parent-appellation")
