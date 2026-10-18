"""The map chrome's shared contracts: the CSS design tokens (one accent, kept
in step with the paint), and — as the UX pass adds them — the hover paint
state and the viewport meta."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import map_template as mt  # noqa: E402

CSS = mt._STYLE_CSS


def _token(name: str) -> str:
    m = re.search(name + r":(#[0-9a-fA-F]{3,6})", CSS)
    assert m, f"token {name} missing from :root"
    return m.group(1).lower()


def test_root_tokens_exist_and_are_used() -> None:
    assert ":root {" in CSS
    for name in ("--c-accent", "--c-pgi", "--c-spirit", "--c-cream", "--n-0", "--n-900",
                 "--n-dark-panel", "--note-bg"):
        _token(name)
        assert f"var({name})" in CSS, name
    assert CSS.count("var(--") > 100


def test_one_accent_colour() -> None:
    # The three former burgundies are one token; the browse page keeps its own CSS.
    body = CSS[CSS.index("}", CSS.index(":root {")) :]
    for old in ("#7a1f3a", "#7A1F2B", "#7a1f2b"):
        assert old not in body, old
    assert _token("--c-accent") == "#934050"


def test_tokens_match_the_paint_colours() -> None:
    src = inspect.getsource(mt._build_source_block).lower()
    assert _token("--c-accent") in src
    assert _token("--c-pgi") in src


def _source_block() -> str:
    return mt._build_source_block(
        layer_url="/map-data/appellations.pmtiles",
        overview_layer_url="/map-data/appellations-overview.pmtiles",
        source_type="pmtiles", area_q1=1.0, area_q3=100.0, lod=None,
    )


def test_source_block_has_hover_state_under_the_selection() -> None:
    block = _source_block()
    assert "['feature-state', 'hover']" in block
    assert "['feature-state', 'selected']" in block
    # Every fill layer carries both: the selection override comes first.
    for layer in ("'appellations-fill'", "'appellations-fill-overview'"):
        i = block.index(layer)
        chunk = block[i: block.index("map.addLayer", i + 1) if "map.addLayer" in block[i + 1:] else len(block)]
        assert "['feature-state', 'selected'], false], 0.60, ['boolean', ['feature-state', 'hover']" in chunk, layer


def test_non_wine_records_take_the_spirits_colour() -> None:
    block = _source_block()
    assert "['==', ['get', 'is_wine'], '0'], '#a07530'" in block
    assert block.index("'is_wine'") < block.index("['get', 'kind'], 'IGP'")
    assert _token("--c-spirit") == "#a07530"


def test_viewport_fit_cover_and_phone_chrome() -> None:
    assert 'viewport-fit=cover' in mt._PAGE_TEMPLATE
    # The phone bar is not a second heading: the sidebar's {brand_tag} owns <h1>.
    bar = mt._PAGE_TEMPLATE[mt._PAGE_TEMPLATE.index('<header id="mobile-bar">'):]
    bar = bar[: bar.index("</header>")]
    assert "<h1" not in bar and "{brand_tag}" not in bar
    for needle in ('id="mobile-search"', 'id="sidebar-toggle"', 'aria-controls="sidebar"', 'aria-expanded="false"'):
        assert needle in bar, needle
    assert '<div id="scrim" hidden aria-hidden="true"></div>' in mt._PAGE_TEMPLATE
    assert 'class="sheet-handle"' in mt._PAGE_TEMPLATE
    css = CSS.replace("{{", "{").replace("}}", "}")
    assert "#mobile-bar, #scrim, #panel .sheet-handle { display:none }" in css
    assert "@media (min-width: 769px) and (max-width: 1024px)" in css
    assert "100dvh" in css and "env(safe-area-inset-bottom" in css


def test_tree_rows_share_one_height_and_one_chevron_slot() -> None:
    css = CSS.replace("{{", "{").replace("}}", "}")
    assert "padding-right:27px" not in css
    assert re.search(r"\.facet \.tree-toggle, \.facet \.tree-toggle-spacer \{ flex:0 0 28px; width:28px", css)
    assert ".facet .tree-row { min-height:26px }" in css
    phone = css[css.index("@media (max-width: 768px)"):]
    assert ".facet .tree-row { min-height:44px }" in phone
    assert ".facet, .facet.facet-appellations { max-height:none }" in phone
    # The drawer's brand block is hidden visually on phones, never removed: it
    # is the page <h1> on the home and fold pages.
    assert "#sidebar .brand-title, #sidebar .subtitle { position:absolute; width:1px; height:1px;" in phone
    assert "#sidebar .brand-title { display:none" not in phone
    assert re.search(r"\.facet \.tree-toggle, \.facet \.tree-toggle-spacer \{ flex-basis:44px; width:44px; height:44px", phone)
