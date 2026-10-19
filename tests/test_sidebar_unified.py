"""One sidebar for everyone (2026-10): the Simple / Advanced view-mode toggle
is gone. The style facet is the taxonomy tree with the seven buckets as its
depth-0 rows in the chip order (white → rosé → red → sparkling → sweet →
oxidative → other), and nothing in the template or the app reads a view mode
any more.

The 2026-10-18 feedback pass (the Miro review): the search comes first with a
clear button, the PDO / PGI / spirits scope toggles are the legend pills on the
map, language and theme live in the ⚙ control, the desktop sidebar folds to a
rail, countries and regions sort alphabetically, sub-denominations nest under
their parent with the parent's name stripped, the start view fits the corpus
and no card is reopened from localStorage."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.map_template import (  # noqa: E402
    _LAB_HEAD_TOP,
    _LAB_LEGEND_FOOTER,
    _SIDEBAR,
    _TEMPLATE,
    STARTUP_AOCS_FIELDS,
    _lang_switcher,
)
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


def test_search_comes_first_and_the_scope_row_is_gone() -> None:
    # Feedback 2026-10-18: "search more prominent" — the field sits right under
    # the brand, with a magnifier and a clear button; the count follows it.
    # The scope toggles left the sidebar for the legend pills on the map.
    brand = _LAB_HEAD_TOP.index('class="brand-title"')
    omni = _LAB_HEAD_TOP.index('id="omnisearch"')
    status = _LAB_HEAD_TOP.index('id="status"')
    assert brand < omni < status
    assert 'class="omni-icon"' in _LAB_HEAD_TOP
    assert 'id="omni-clear"' in _LAB_HEAD_TOP and 'hidden>×</button>' in _LAB_HEAD_TOP
    assert 'id="scope"' not in _SIDEBAR and 'id="show-igp"' not in _SIDEBAR
    assert "clearSearch('button')" in APP_JS and "clearSearch('escape')" in APP_JS
    # The results are not a popup: while the box holds text they replace the
    # filters (the dropdown over the tree read as a layout error).
    assert "function setSearching(on) { sidebarEl.classList.toggle('searching', on); }" in APP_JS
    assert "renderSeeds" not in APP_JS and "setTimeout(hideDrop" not in APP_JS
    css = _TEMPLATE.replace("{{", "{").replace("}}", "}")
    assert ".omni-suggestions { position:static;" in css
    assert "#sidebar.searching > details, #sidebar.searching #active-filters, #sidebar.searching #status { display:none }" in css


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


def test_scope_toggles_never_move_the_camera() -> None:
    # Showing PGIs or spirits widens what is drawn where the reader already
    # looks (feedback 2026-10-18: "toggling shouldn't move the area the map is
    # showing"); only a facet pick fits the map to its matches.
    for var in ("showPdo", "showIgp", "showSpirits"):
        start = APP_JS.index(f"{var} = e.target.checked;")
        handler = APP_JS[start:APP_JS.index("\n  });", start)]
        assert "track('Kind Toggled'" in handler, var
        assert "applyFilter();" in handler, var
        assert "fit: true" not in handler, var


def test_tree_rows_without_children_carry_a_chevron_spacer() -> None:
    # The count column lines up because every row ends in a slot of the
    # chevron's width — a button, or an inert spacer (feedback 2026-10-18: the
    # 27px padding only matched the desktop chevron; phones draw it 44px).
    assert '<span class="tree-toggle-spacer" aria-hidden="true"></span>' in APP_JS


def test_appellation_type_tree_is_withheld_but_dormant() -> None:
    # Boris 2026-10-18: drop the appellation-type facet for now (to come back
    # with the AVAs). Only the markup is gone; the builder keeps its null-guard.
    assert 'data-facet="appellation-type"' not in _SIDEBAR
    assert 'id="facet-appellation-type"' not in _SIDEBAR
    assert "buildTreeFacet('facet-appellation-type', FACET_TERM_TREE, filters.appellationType, TERM_LABELS, 'appellation-type');" in APP_JS
    assert "if (!el) return;  // defensive null-guard" in APP_JS


def test_only_the_appellation_tree_starts_open() -> None:
    # Boris 2026-10-18: by default only the appellation tree is expanded; the
    # three facet trees start collapsed. A tick that reaches a collapsed tree
    # through the search opens its section (revealCheckedTreeRows).
    assert '<details open data-facet="appellations">' in _SIDEBAR
    assert _SIDEBAR.count("<details open") == 1
    assert '<details data-facet="styles">' in _SIDEBAR
    assert "section.open = true" in APP_JS


def test_legend_pills_are_the_scope_control_with_scheme_hints() -> None:
    # The review's mockups: one pill per scheme on the map, each a checkbox
    # and an ⓘ that opens the scheme definition the card's pills already carry
    # (TERMS_INFO keys pdo / pgi / spirit-gi), by hover, focus or a tap.
    assert "pill('aoc', 'show-pdo', LABELS.scheme_pdo, LABELS.show_pdo_label, 'pdo', LABELS.scope_hint_pdo)" in APP_JS
    assert "pill('igp', 'show-igp', LABELS.scheme_pgi, LABELS.show_igp_label, 'pgi', LABELS.scope_hint_pgi)" in APP_JS
    assert "pill('spirit', 'show-spirits', LABELS.legend_spirits_label, LABELS.show_spirits_label, 'spirit-gi', LABELS.scope_hint_spirits)" in APP_JS
    assert 'class="scope-hint gi-scheme has-info" data-key="${hintKey}"' in APP_JS
    assert "const scopeRow = legendControl._el || null;" in APP_JS
    assert "scopeRow.addEventListener('click'" in APP_JS
    assert "scopeRow.addEventListener('focusin', showHint)" in APP_JS
    # Touch drives the hint through the click alone: a tap is a burst of
    # synthetic mouse events (mouseover, click, mouseout), and the trailing
    # mouseout would otherwise close what the tap just opened.
    assert "e.pointerType === 'touch' && e.target.closest('.scope-hint')" in APP_JS
    assert "if (e.type === 'mouseover' && touching()) return;" in APP_JS
    # PDOs can be hidden too: the filter, the client matcher and the landing
    # gate all know the third scheme.
    assert "if (!showPdo) parts.push(['any', ['==', ['get', 'is_wine'], '0'], ['==', ['get', 'kind'], 'IGP']]);" in APP_JS
    assert APP_JS.count("if (!showPdo && isPdoRec(rec)) return false;") == 2
    assert "if (gates.includes('pdo')) showPdo = true;" in APP_JS


def test_language_and_theme_live_in_the_settings_control() -> None:
    # Feedback 2026-10-18: "move to config". The block is server-rendered in
    # the sidebar footer (a no-JS visitor keeps the language links) and lifted
    # into the ⚙ control top-right of the map by app.js; the theme switch keeps
    # its three states but now says Light / System / Dark.
    assert 'id="config-menu"' in _LAB_LEGEND_FOOTER and "{lang_switcher_html}" in _LAB_LEGEND_FOOTER
    assert "{lang_switcher_html}" not in _LAB_HEAD_TOP and 'id="theme-toggle"' not in _LAB_HEAD_TOP
    for mode, label in (("light", "theme_light"), ("system", "theme_system"), ("dark", "theme_dark")):
        assert f'data-theme-mode="{mode}"' in _LAB_LEGEND_FOOTER
        # Icon-only since 2026-10-19 (the words made the cells cramped): the
        # word is the accessible name and the hover hint, never visible text.
        assert "aria-label=\"{labels[" + label + "]}\" title=\"{labels[" + label + "]}\"><svg" in _LAB_LEGEND_FOOTER
        assert "{labels[" + label + "]}</button>" not in _LAB_LEGEND_FOOTER
    # Inline SVG icons (sun / monitor / moon — the convention), never the
    # ☀ ◐ ☾ glyphs (emoji on some platforms); the row sits beside its heading.
    assert _LAB_LEGEND_FOOTER.count('class="theme-btn') == 3
    assert '<rect x="3" y="4" width="18" height="13" rx="2"/>' in _LAB_LEGEND_FOOTER
    assert '<div class="config-section config-row"><div class="config-h" id="theme-h">' in _LAB_LEGEND_FOOTER
    for glyph in ("☀", "◐", "☾"):
        assert glyph not in _LAB_LEGEND_FOOTER, glyph
    css = _TEMPLATE.replace("{{", "{").replace("}}", "}")
    assert ".config-row { display:flex; align-items:center; justify-content:space-between;" in css
    assert "#theme-toggle .theme-btn { display:inline-flex; align-items:center; justify-content:center; width:36px; height:30px;" in css
    assert "#theme-toggle .theme-btn { width:44px; height:36px }" in css
    assert "#sidebar > * { flex:0 0 auto }" in css
    assert "map.addControl(settingsControl, 'top-right');" in APP_JS
    assert "function homeSettings()" in APP_JS and "bar.insertBefore(btn, sidebarToggle || null);" in APP_JS
    assert "menu.classList.add('placed'); this._el.appendChild(menu);" in APP_JS
    assert "if (settingsControl.isOpen()) { e.stopPropagation(); settingsControl.setOpen(false, true); return; }" in APP_JS
    html = _lang_switcher("en", "Language")
    assert ">English</a>" in html and ">Français</a>" in html and 'data-lang="nl"' in html


def test_desktop_sidebar_folds_to_a_rail() -> None:
    assert 'id="sidebar-collapse"' in _LAB_HEAD_TOP and 'id="sidebar-rail"' in _LAB_HEAD_TOP
    assert 'id="rail-search"' in _LAB_HEAD_TOP and 'id="rail-expand"' in _LAB_HEAD_TOP
    # Restored before first paint, like the theme.
    assert "localStorage.getItem('sidebar_collapsed')" in _TEMPLATE
    assert "classList.add('sidebar-collapsed')" in _TEMPLATE
    assert "function setSidebarCollapsed(on, via, focusSearch)" in APP_JS
    assert "setSidebarCollapsed(false, 'rail-search', true)" in APP_JS


def test_countries_and_regions_sort_alphabetically() -> None:
    assert "countryLabel(a[0]).localeCompare(countryLabel(b[0]), LANG));" in APP_JS
    assert "regionLabel(a[0]).localeCompare(regionLabel(b[0]), LANG)));" in APP_JS
    assert "total(b[1]) - total(a[1])" not in APP_JS
    assert "b[1].length - a[1].length" not in APP_JS


def test_sub_denominations_nest_under_their_parent() -> None:
    # Fifteen "Aloxe-Corton premier …" rows read the same after the ellipsis:
    # a child sits under its parent behind a chevron, its label the part that
    # distinguishes it, and an appellation name wraps rather than truncates.
    assert "parent_slug" in STARTUP_AOCS_FIELDS
    assert "function childLabel(rec, parentRec)" in APP_JS
    assert "const subId = `fa-sub-${escapeAttr(cc)}-${escapeAttr(slug)}`;" in APP_JS
    assert "children.map(c => row(c, 1, AOCS[slug], ''))" in APP_JS
    css = _TEMPLATE.replace("{{", "{").replace("}}", "}")
    assert ".facet .aoc-row .name { white-space:normal; overflow:visible; text-overflow:clip" in css


def test_start_view_fits_the_corpus_and_nothing_is_restored() -> None:
    assert "bounds: corpusBounds(), fitBoundsOptions: { padding: startPadding() }" in APP_JS
    assert "center: [2.6, 46.5], zoom: 5.4" not in APP_JS
    # The Atlantic islands are left out of the fit, not off the map.
    assert "if (!b || b[2] < -12) continue;" in APP_JS
    # The last open card is no longer reopened; the stored key is removed once.
    assert APP_JS.count("'selected_slugs'") == 1
    assert "localStorage.removeItem('selected_slugs')" in APP_JS
    assert "localStorage.getItem('selected_slugs')" not in APP_JS
