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
    for name in ("--c-accent", "--c-pgi", "--c-spirit", "--c-cream", "--n-0", "--n-850",
                 "--n-dark-panel", "--note-bg", "--side-bg", "--side-text", "--side-text-3"):
        _token(name)
        assert f"var({name})" in CSS, name
    assert CSS.count("var(--") > 100
    # The sidebar's palette is light by default and redefined for dark mode
    # (feedback 2026-10-18: light mode had left the menu dark).
    dark = CSS[CSS.index("html.theme-dark {{"):]
    dark = dark[: dark.index("}}")]
    for name in ("--side-bg:#1a1a1a", "--side-text:#eee", "--side-focus:var(--c-cream)"):
        assert name in dark, name
    assert "--side-bg:#fff" in CSS[CSS.index(":root {{"):CSS.index("html.theme-dark {{")]


def test_one_accent_colour() -> None:
    # The three former burgundies are one token — on the map and, since
    # 2026-10-21, on the self-contained pages, which take the map's tokens
    # (the browse index and the 404 had kept the old accent in their own CSS).
    body = CSS[CSS.index("}", CSS.index(":root {")) :]
    head = mt._TEMPLATE[: mt._TEMPLATE.index("<style>")]
    for old in ("#7a1f3a", "#7A1F2B", "#7a1f2b"):
        assert old not in body, old
        assert old not in mt._BROWSE_CSS, old
        assert old not in mt._static_page_css(), old
        assert old not in head, old
        assert old not in mt._BROWSE_TEMPLATE, old
    assert _token("--c-accent") == "#934050"
    assert f'<meta name="theme-color" content="{_token("--c-accent")}"' in mt._TEMPLATE
    assert f'<meta name="theme-color" content="{_token("--c-accent")}"' in mt._BROWSE_TEMPLATE


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
    for needle in ('id="sidebar-toggle"', 'aria-controls="sidebar"', 'aria-expanded="false"'):
        assert needle in bar, needle
    # The drawer's button is a magnifier, not a ☰ (2026-10-21: the drawer is
    # search-first and a burger said "menu"); open, the CSS swaps it to ×.
    assert "☰" not in bar
    assert '<svg class="ico-search"' in bar
    assert '<span class="ico-close" aria-hidden="true">×</span>' in bar
    # The bar's separate search button went on 2026-10-18 (it opened the same
    # drawer); the ⚙ is homed into the bar by app.js (homeSettings) on phones.
    assert 'id="mobile-search"' not in bar
    assert '<div id="scrim" hidden aria-hidden="true"></div>' in mt._PAGE_TEMPLATE
    assert 'class="sheet-handle"' in mt._PAGE_TEMPLATE
    css = CSS.replace("{{", "{").replace("}}", "}")
    assert "#mobile-bar, #scrim, #panel .sheet-handle { display:none }" in css
    assert '#sidebar-toggle[aria-expanded="true"] svg { display:none }' in css
    assert '#sidebar-toggle[aria-expanded="true"] .ico-close { display:inline }' in css
    assert "@media (min-width: 769px) and (max-width: 1024px)" in css
    assert "100dvh" in css and "env(safe-area-inset-bottom" in css


def test_tree_rows_share_one_height_and_one_chevron_slot() -> None:
    css = CSS.replace("{{", "{").replace("}}", "}")
    assert "padding-right:27px" not in css
    assert re.search(r"\.facet \.tree-toggle, \.facet \.tree-toggle-spacer \{ flex:0 0 28px; width:28px; height:24px", css)
    assert ".facet .tree-row { min-height:24px }" in css
    phone = css[css.index("@media (max-width: 768px)"):]
    # Phones keep the desktop row height — the country rows' rhythm (a 44 px
    # row read as padding) — and widen the chevron slot to a 36 × 26 px target,
    # above the 24 px WCAG AA minimum.
    assert ".facet .tree-row { min-height:44px }" not in phone
    assert ".facet, .facet.facet-appellations { max-height:none }" in phone
    # Desktop: the appellation tree flexes to the sidebar's remaining height and
    # the footer sits at the bottom (feedback 2026-10-18); phones keep the drawer
    # as the one scroll surface.
    assert '#sidebar > details[data-facet="appellations"][open] { flex:1 1 auto; min-height:190px; overflow-y:auto }' in css
    assert '#sidebar > details[data-facet="appellations"] > summary { position:sticky; top:0;' in css
    assert ".facet.facet-appellations { max-height:none; overflow:visible }" in css
    assert "#sidebar-footer { flex:0 0 auto; margin-top:auto;" in css
    # The maker's credit under the links reads one notch brighter than the
    # footer, its link and heart in the accent — sidebar tokens, so it follows
    # the theme (2026-10-20).
    assert "#sidebar-credit { margin:10px 0 0; font-size:var(--fs-xs); color:var(--side-text-2) }" in css
    assert "#sidebar-credit .heart { color:var(--side-accent-ink) }" in css
    assert "#sidebar-footer #sidebar-credit a { color:var(--side-accent-ink); font-weight:600 }" in css
    assert "#about-dialog .about-credit .heart { color:var(--c-accent) }" in css
    assert "html.theme-dark #about-dialog .about-credit .heart { color:var(--c-accent-ink-dark) }" in css
    assert '#sidebar > details[data-facet="appellations"][open] { flex:0 0 auto; min-height:0; overflow:visible }' in phone
    assert ".owm-legend .scope-hint { width:24px; height:24px" in phone
    assert ".owm-legend .scope-hint { display:inline-flex" in css
    # On phones the map's ⚙ control is empty and hidden; the bar hosts the button.
    assert ".maplibregl-ctrl-top-right .owm-settings { display:none }" in phone
    assert "#config-menu.in-bar { position:fixed;" in phone
    # The drawer's brand block is hidden visually on phones, never removed: it
    # is the page <h1> on the home and fold pages.
    assert "#sidebar .brand-title, #sidebar .subtitle { position:absolute; width:1px; height:1px;" in phone
    assert "#sidebar .brand-title { display:none" not in phone
    assert re.search(r"\.facet \.tree-toggle, \.facet \.tree-toggle-spacer \{ flex-basis:36px; width:36px \}", phone)


APP_JS = (Path(__file__).resolve().parents[1] / "scripts/_lib/assets/app.js").read_text()


def test_hit_test_keeps_an_inheritor_whose_donor_is_not_painted() -> None:
    """A sub-denomination that inherits its polygon (parent-appellation /
    sibling-dgc) is dropped from the hover / click stack only while its donor
    is painted too. Under a filter the parent fails and the child passes
    (Romagna Oriolo under ?grape=nebbiolo, 2026-10-22) the child is the only
    thing painted there: dropping it left a polygon nobody could hover or
    open. The donor is read from the record, else from the tile feature."""
    body = APP_JS[APP_JS.index("function hitSlugsAt(point)"):]
    body = body[: body.index("return slugs;")]
    assert "donor && donor !== s && hit.has(donor)" in body
    assert "(rec && rec.parent_slug) || p.parent_slug" in body
    assert "(rec && rec.geom_fallback_slug) || p.geom_fallback_slug" in body
    # The unconditional drop is gone.
    assert "if (src === 'parent-appellation' || src === 'sibling-dgc') continue;" not in body


def test_boundary_fold_has_a_line_for_both_lod_bands() -> None:
    """2026-11-07: Margaux at z12 opened "About this boundary" on nothing — the
    footprint note was the fold's only line and the zoom had hidden it. A
    footprint record carries one line per band, the zoom shows the band on
    screen, and the parcels label is translated in every UI locale."""
    js = (Path(mt.__file__).resolve().parent / "assets" / "app.js").read_text()
    assert "data-lod-band=" in js
    assert "LABELS.geom_lod_footprint" in js and "LABELS.geom_lod_parcels" in js
    assert "el.hidden = el.dataset.lodBand !== band" in js
    msgid = mt.build_labels(lambda s: s)["geom_lod_parcels"]
    assert "{radius}" in msgid
    from babel.messages.pofile import read_po

    for lang in ("en", "es", "nl"):
        po = Path(mt.__file__).resolve().parents[2] / "locale" / lang / "LC_MESSAGES" / "messages.po"
        with po.open("rb") as fh:
            msg = read_po(fh).get(msgid)
        assert msg is not None and msg.string and "{radius}" in msg.string, lang
