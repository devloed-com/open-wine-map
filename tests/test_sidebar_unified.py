"""One sidebar for everyone (2026-10): the Simple / Advanced view-mode toggle
is gone. The style facet is the taxonomy tree with the seven buckets as its
depth-0 rows in the chip order (white → rosé → red → sparkling → sweet →
oxidative → other), the two scope toggles (PGIs, spirits) sit under the count,
and nothing in the template or the app reads a view mode any more."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.map_template import _LAB_HEAD_TOP, _SIDEBAR, _TEMPLATE  # noqa: E402
from _lib.style_taxonomy import (  # noqa: E402
    BUCKETS,
    FACET_BUCKET_ORDER,
    descendants_map,
    taxonomy_dfs_order,
)

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")


def test_sidebar_has_no_view_mode() -> None:
    for needle in ("data-modes", "mode-toggle", "facet-styles-simple", "view_mode"):
        assert needle not in _SIDEBAR, needle
        assert needle not in _TEMPLATE, needle
    assert len(re.findall(r'data-facet="styles"', _SIDEBAR)) == 1


def test_scope_row_sits_under_the_count() -> None:
    status = _LAB_HEAD_TOP.index('id="status"')
    scope = _LAB_HEAD_TOP.index('id="scope"')
    omni = _LAB_HEAD_TOP.index('id="omnisearch"')
    assert status < scope < omni
    scope_html = _LAB_HEAD_TOP[scope:omni]
    assert 'id="show-igp"' in scope_html and 'id="show-spirits"' in scope_html
    assert 'role="group"' in scope_html


def test_app_js_reads_no_view_mode() -> None:
    for needle in ("viewMode", "stylesSimple", "__OWM_styles_simple_json__", "View Mode Switched",
                   "spiritsVisible", "applyMode"):
        assert needle not in APP_JS, needle
    # The only mention of the old key is the one-off removal from storage.
    assert APP_JS.count("'view_mode'") == 1
    assert "localStorage.removeItem('view_mode')" in APP_JS


def test_tree_rows_keep_button_and_label_as_siblings() -> None:
    # A <button> is a labelable element: nested in the checkbox's <label> it
    # would take the row's name as its own. Both trees render the disclosure /
    # open button as a sibling of the label inside the row.
    assert '<label class="tree-row' not in APP_JS
    assert '<label data-slug=' not in APP_JS
    assert '<div class="aoc-row" data-slug=' in APP_JS
    assert 'class="tree-toggle" aria-expanded="false" aria-controls=' in APP_JS


def test_facet_bucket_order_is_the_chip_order() -> None:
    assert FACET_BUCKET_ORDER == ("white", "rose", "red", "sparkling", "sweet", "oxidative", "other")
    assert set(FACET_BUCKET_ORDER) == set(BUCKETS)
    order = taxonomy_dfs_order(roots=FACET_BUCKET_ORDER)
    assert [slug for slug, _, depth in order if depth == 0] == list(FACET_BUCKET_ORDER)
    # The default (membership) order is untouched — the MCP context keys on it.
    assert [slug for slug, _, depth in taxonomy_dfs_order() if depth == 0] == list(BUCKETS)


def test_bucket_expansion_includes_the_bucket_itself() -> None:
    # A depth-0 pick must match the records that carry the bucket slug itself
    # (the former chip path dropped it, so "white" filtered nothing).
    dm = descendants_map()
    for b in BUCKETS:
        assert b in dm[b], b
