"""The style taxonomy is a graph with a tree drawn over it (2026-11-14, the
Manzanilla question): fortification is an axis of its own, a liqueur wine is
not sweet by its category, and a generoso is oxidative only through the types
whose ageing is."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import style_taxonomy as st  # noqa: E402


def test_fortified_is_a_bucket_of_its_own():
    assert "fortified" in st.BUCKETS and "fortified" in st.FACET_BUCKET_ORDER
    assert st.parent("fortified") is None
    assert st.FACET_BUCKET_ORDER.index("sweet") < st.FACET_BUCKET_ORDER.index("fortified") \
        < st.FACET_BUCKET_ORDER.index("oxidative")


def test_a_liqueur_wine_is_not_sweet_by_its_category():
    assert st.simple_buckets("vin-de-liqueur") == {"fortified"}
    assert "vin-de-liqueur" not in st.descendants("sweet")
    assert "fortified" not in st.descendants("sweet")


def test_a_vdn_and_a_mistela_are_sweet_by_definition():
    for slug in ("vdn", "mistela"):
        assert st.simple_buckets(slug) == {"fortified", "sweet"}
        assert slug in st.descendants("sweet") and slug in st.descendants("fortified")


def test_manzanilla_and_fino_are_neither_sweet_nor_oxidative():
    for slug in ("generoso", "fino", "manzanilla"):
        assert st.simple_buckets(slug) == {"fortified"}
        assert slug not in st.descendants("oxidative")
        assert slug not in st.descendants("sweet")


def test_the_oxidative_sherry_types_are_reached_from_both_parents():
    for slug in ("amontillado", "oloroso", "palo-cortado"):
        assert st.simple_buckets(slug) == {"fortified", "oxidative"}
        assert slug in st.descendants("oxidative") and slug in st.descendants("generoso")


def test_the_tree_shows_every_node_once_under_its_primary_parent():
    order = st.taxonomy_dfs_order(roots=st.FACET_BUCKET_ORDER)
    slugs = [slug for slug, _, _ in order]
    assert len(slugs) == len(set(slugs)) and set(slugs) == set(st.all_slugs())
    by_slug = {slug: (parent, depth) for slug, parent, depth in order}
    assert by_slug["generoso"] == ("fortified", 1)
    assert by_slug["manzanilla"] == ("generoso", 2)
    assert by_slug["oloroso"] == ("generoso", 2)      # shown once, not under oxidative too
    assert by_slug["vdn"] == ("fortified", 1)


def test_every_extra_parent_is_a_node():
    for node in st.NODES.values():
        for extra in node.extra_parents:
            assert extra in st.NODES and extra != node.parent, node.slug
