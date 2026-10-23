"""The browser's Back works on the map (2026-10-21, a visitor on Terre
Alfieri): every navigation — a card opened or closed, a stack cycled, a
card's "All appellations in …" link — is a history entry carrying the view it
showed (filters + open stack), and popstate restores it. The related link
replaces the appellation selection instead of adding to it: after "all of
Italy", a second "all of Piemonte" had changed nothing."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")


def _block(start: str, end: str) -> str:
    i = APP_JS.index(start)
    return APP_JS[i : APP_JS.index(end, i)]


def test_scope_link_replaces_the_selection_and_pushes_an_entry() -> None:
    handler = _block("const sc = e.target.closest('a.scope-link');", "const a = e.target.closest('a.parent-link');")
    assert "filters.appellations.clear();" in handler
    assert handler.index("filters.appellations.clear();") < handler.index("setSlugSelection(slugs, true);")
    # The entry is pushed with the new filters, before applyFilter writes the
    # (new) current entry's snapshot — never onto the previous entry.
    assert handler.index("writeHistory(true, window.location.href);") < handler.index("applyFilter({ fit: true });")


def test_card_opens_push_and_landings_replace() -> None:
    fn = _block("function setAocPath(slug, landing) {", "// What the page URL asks to open on load")
    assert "slugFromPath()" in fn
    assert "writeHistory(push," in fn
    assert "history.replaceState(history.state" not in APP_JS
    assert "setAocPath(ordered[0], via === 'landing');" in APP_JS
    writer = _block("function writeHistory(push, url) {", "function syncAppellationCheckboxes")
    assert "'pushState' : 'replaceState'" in writer
    assert "if (historyRestoring) return;" in writer


def test_the_entry_carries_the_view_and_popstate_restores_it() -> None:
    state = _block("function historyState() {", "function writeHistory")
    for key in ("filters: filterSnapshot()", "stack: currentStack.slice()", "focus: currentFocus", "set: currentStackIsSet"):
        assert key in state, key
    snap = _block("function filterSnapshot() {", "function historyState")
    for facet in ("styles", "classifications", "appellationType", "grapesAll", "mainGrapeOnly", "appellations"):
        assert re.search(rf"\b{facet}:", snap), facet
    pop = _block("window.addEventListener('popstate'", "function setSelectedState")
    # The camera comes back from the entry's hash: Chrome fires hashchange on
    # a traversal only when the path is unchanged, so MapLibre's listener
    # misses a Back that changes the card.
    assert "jumpToHash();" in pop
    assert "map.jumpTo({ center: [parts[2], parts[1]], zoom: parts[0]" in APP_JS
    assert "restoreFilters(st.filters || {});" in pop
    assert "renderPanelStack(stack, idx, false, isSet ? 'set' : 'history');" in pop
    assert "closePanel(false);" in pop
    assert "historyRestoring = true;" in pop and "historyRestoring = false;" in pop
    # Sets are refilled in place: the tree builders hold them by reference.
    restore = _block("function restoreFilters(snap) {", "window.addEventListener('popstate'")
    assert "set.clear();" in restore
    assert "filters.styles = " not in restore
    assert "applyFilter();" in restore


def test_filter_changes_ride_on_their_entry_and_the_landing_is_seeded() -> None:
    apply = _block("function applyFilter(opts) {", "document.getElementById('active-filters-chips').addEventListener('click'")
    # Since 2026-10-22 the entry URL is the canonical view URL (the address
    # bar is the share link), not whatever the bar held.
    assert "writeHistory(false, currentUrl());" in apply
    seed = _block("if (_ssr) showSsrFallback();\n  })();", "map.on('load'")
    assert "writeHistory(false, currentUrl());" in seed
    assert "currentFocus = null;" in _block("function closePanel(returnFocus) {", "// Open what the URL asks for")
