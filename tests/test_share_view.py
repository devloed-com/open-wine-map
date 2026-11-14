"""The view in the URL, the share dialog and the embed (2026-10-22, after
Reinier Broeks' Druivenatlas copied the address bar after a grape search and
got the bare map): the address bar carries the filters, the selection, a
shared set and the scheme gates — viewFromQuery / queryFromView in the shared
query core — the share dialog hands out that link and an <iframe> of it, and
?embed=1 draws the map alone with a brand badge and click-through popups."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import map_template as mt  # noqa: E402

APP_JS = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")
CORE = (ROOT / "scripts" / "_lib" / "assets" / "query_core.mjs").read_text(encoding="utf-8")
DEPLOY = (ROOT / "scripts" / "deploy.py").read_text(encoding="utf-8")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i)]


def test_the_query_core_carries_the_view_codec() -> None:
    assert "function viewFromQuery(search)" in CORE and "function queryFromView(view)" in CORE
    keys = _block(CORE, "const VIEW_KEYS", "const SHARE_KEYS")
    for key in ("grape", "main", "style", "class", "type", "country", "region", "sel", "aocs",
                "pdo", "pgi", "spirits", "embed", "theme"):
        assert f"'{key}'" in keys, key
    # A bare ?aocs= set is not a shared view: its gates keep the older rule.
    shared = _block(CORE, "const SHARE_KEYS", ";")
    assert "'aocs'" not in shared and "'theme'" not in shared and "'embed'" in shared
    assert "grapeKeyFor, styleKeyFor, regionKeyFor, viewFromQuery, queryFromView, VIEW_KEYS," in CORE
    # Unknown values are listed, never guessed.
    assert "view.unknown.push('grape:' + g)" in CORE and "view.unknown.push('region:' + r)" in CORE


def test_the_app_reads_the_view_once_and_writes_it_back() -> None:
    assert "const VIEW_QUERY = QC.viewFromQuery(window.location.search);" in APP_JS
    assert "const EMBED = VIEW_QUERY.embed;" in APP_JS
    # applyFilter and the landing entry write the canonical URL; a card open
    # keeps the query behind the slug path.
    assert APP_JS.count("writeHistory(false, currentUrl());") == 2
    assert "writeHistory(push, currentUrl(path));" in APP_JS
    assert "writeHistory(false, window.location.href)" not in APP_JS
    assert "writeHistory(push, path + window.location.hash)" not in APP_JS
    assert "return { slugs: VIEW_QUERY.set.slice(), set: true };" in APP_JS
    assert "new URLSearchParams(window.location.search).get('aocs')" not in APP_JS
    view = _block(APP_JS, "function currentView() {", "function currentUrl(path, view, withHash) {")
    for field in ("grapes: [...filters.grapesAll]", "set: currentStackIsSet ? currentStack.slice() : []",
                  "gates: { pdo: showPdo, pgi: showIgp, spirits: showSpirits }", "embed: EMBED"):
        assert field in view, field


def test_the_chip_tray_and_the_url_partition_the_selection_alike() -> None:
    assert "function collapsedSelection()" in APP_JS
    chips = _block(APP_JS, "function renderActiveFilters() {", "function collapsedSelection() {")
    assert "const sel = collapsedSelection();" in chips
    assert "for (const cc of sel.countries)" in chips and "for (const r of sel.regions)" in chips
    assert "const collapsed = new Set();" not in chips


def test_a_shared_view_takes_its_gates_from_the_url_and_an_embed_saves_nothing() -> None:
    gates = _block(APP_JS, "if (VIEW_QUERY.shared) {", "function saveGate")
    assert "showPdo = VIEW_QUERY.gates.pdo !== false;" in gates
    assert "showIgp = VIEW_QUERY.gates.pgi === true;" in gates
    assert "showSpirits = VIEW_QUERY.gates.spirits === true;" in gates
    # The slug landing's own gate rule still follows.
    assert APP_JS.index("if (VIEW_QUERY.shared) {") < APP_JS.index("for (const s of LANDING.slugs) {")
    assert "localStorage.setItem('show_" not in APP_JS
    # 8 since 2026-11-12: ticking a drink category in the Style tree turns the drinks pill on
    assert APP_JS.count("saveGate('show_") == 8
    assert "function saveGate(key, on) {\n    if (EMBED) return;" in APP_JS


def test_the_urls_view_is_applied_before_the_landing_and_framed() -> None:
    fn = _block(APP_JS, "function applyViewQuery() {", "  applyViewQuery();")
    for line in (
        "for (const k of v.grapes) filters.grapesAll.add(k);",
        "setSlugSelection(visibleSlugsInCountry(cc), true);",
        "setSlugSelection(visibleSlugsInRegion(r.country, r.region), true);",
        "syncAppellationCheckboxes();",
        "refreshTreeTriStates();",
        "if (!CAMERA_GIVEN && !LANDING.slugs.length) map.once('load', () => fitToFiltered(0));",
    ):
        assert line in fn, line
    assert APP_JS.index("  applyViewQuery();") < APP_JS.index("// Open what the URL asks for")
    assert "function fitToFiltered(duration) {" in APP_JS
    assert "duration: duration == null ? 500 : duration" in APP_JS


def test_share_control_and_dialog() -> None:
    assert "if (!EMBED) map.addControl(shareControl, 'top-right');" in APP_JS
    assert APP_JS.index("map.addControl(shareControl") < APP_JS.index("map.addControl(settingsControl")
    assert "if (shareBtn) bar.insertBefore(shareBtn, btn);" in APP_JS
    dlg = _block(APP_JS, "let shareState = null;", "const shareNative")
    for s in (
        "const url = window.location.origin + currentUrl();",
        "theme: st.theme === 'dark' ? 'dark' : null",
        '<iframe src="',
        'loading="lazy"',
        "<p><a href=",
        "track('Share Opened', { via: via, what: subject.kind, locale: LANG });",
        # The embed's theme is the dialog's choice, light by default (writes nothing).
        "theme: 'light',",
        "if (lightRadio) lightRadio.checked = true;",
        "shareState.theme = inp.value === 'dark' ? 'dark' : 'light';",
    ):
        assert s in dlg, s
    assert "if (btn.dataset.copyKind === 'embed' && shareState) props.theme = shareState.theme;" in APP_JS
    assert "const props = { kind: btn.dataset.copyKind, locale: LANG };" in APP_JS
    assert "track('Share Copied', props);" in APP_JS
    assert "if ((aboutDialog && aboutDialog.open) || (shareDialog && shareDialog.open)) return;" in APP_JS
    labels = defaultdict(str, {"share_dialog_h": "Share this view", "copy_label": "Copy"})
    html = mt._build_share_dialog(labels)
    assert '<dialog id="share-dialog"' in html and '<h2 id="share-dialog-h"' in html
    assert 'data-copy-kind="link"' in html and 'data-copy-kind="embed"' in html
    assert '<textarea id="share-embed" readonly' in html and 'id="share-native" hidden' in html
    assert '<input type="radio" name="share-theme" value="light" checked>' in html
    assert '<input type="radio" name="share-theme" value="dark">' in html
    # The parameter reference for advanced users, folded behind an ⓘ.
    assert '<details class="share-params"><summary><span class="info-i" aria-hidden="true">i</span>' in html
    for code in ("grape=sankt-laurent", "pgi=1", "embed=1", "bbox=", "aocs=priorat,montsant", "region=fr:BOURGOGNE", "#8/47.80/16.10"):
        assert code in html, code
    # One parameter per row (feedback 2026-10-22: combined rows read unclearly).
    assert len(mt._SHARE_PARAMS) == 14 and all(k in mt.build_labels(lambda x: x) for _, k in mt._SHARE_PARAMS)
    assert all(" · " not in code for code, _ in mt._SHARE_PARAMS)
    assert "grid-template-columns:fit-content(45%) 1fr" in mt._STYLE_CSS
    assert "{share_dialog_html}" in mt._TEMPLATE
    assert mt._TEMPLATE.index("{about_dialog_html}") < mt._TEMPLATE.index("{share_dialog_html}")
    built = mt.build_labels(lambda x: x)
    for key in ("share_h", "share_dialog_h", "share_view_label", "share_link_h", "share_embed_h",
                "share_embed_intro", "share_copy_link_aria", "share_copy_embed_aria",
                "share_native_label", "share_on_owm", "embed_open_label"):
        assert built[key], key


def test_an_embed_carries_the_shared_area_and_fits_it() -> None:
    # Feedback 2026-10-22: a 480 px iframe showed less than the screen that
    # was shared. The embed URL carries bbox=w,s,e,n (the map's bounds at
    # share time) instead of the camera hash, and any viewport fits it on load.
    keys = _block(CORE, "const VIEW_KEYS", "const SHARE_KEYS")
    assert "'bbox'" in keys and "'bbox'" not in _block(CORE, "const SHARE_KEYS", ";")
    assert "parts.push('bbox=' + v.bbox.map(x => Number(x).toFixed(4)).join(','))" in CORE
    dlg = _block(APP_JS, "let shareState = null;", "const shareNative")
    assert "bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]," in dlg
    assert "currentUrl(null, v, false)" in dlg  # no hash on the embed URL
    assert "aspect-ratio:' + st.ratio.toFixed(2)" in dlg and "Math.min(2.4, Math.max(1.2," in dlg
    assert "const CAMERA_GIVEN = !!INITIAL_CAMERA_HASH || !!VIEW_QUERY.bbox;" in APP_JS
    assert APP_JS.count("if (!CAMERA_GIVEN) {") == 2 and "if (!INITIAL_CAMERA_HASH) {" not in APP_JS
    assert "if (VIEW_QUERY.bbox && !INITIAL_CAMERA_HASH) {" in APP_JS
    assert "map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 0, duration: 0 })" in APP_JS


def test_embed_mode_is_the_map_alone() -> None:
    head = mt._TEMPLATE[: mt._TEMPLATE.index("<style>")]
    # No language redirect inside an embed; the query survives a redirect.
    assert "if (/[?&]embed=1(?:&|$)/.test(window.location.search)) return;" in head
    assert "window.location.replace(dest + search + hash);" in head
    assert "document.documentElement.classList.add('embed');" in head
    assert "var dark = embed ? /[?&]theme=dark(?:&|$)/.test(window.location.search)" in head
    css = mt._STYLE_CSS
    assert "html.embed #sidebar, html.embed #sidebar-rail, html.embed #mobile-bar" in css
    assert ".owm-brand a {{" in css and ".owm-embed-pop" in css
    assert "if (EMBED) { showEmbedPopup(e.lngLat, slugs); return; }" in APP_JS
    assert "map.addControl(brandControl, 'top-left');" in APP_JS
    assert ("track('Embed Viewed', { host: embedHost(), framed: embedFramed(), "
            "view: embedView(), area: embedArea(), locale: LANG });") in APP_JS
    # Which map an embed shows: the view without the embed flags ('map' when
    # bare), class / type keys only when the map's tables know them, and the
    # area fitted on load; the click-throughs carry the view too.
    embed_fns = APP_JS[APP_JS.index("function embedView()"):APP_JS.index("const brandControl")]
    assert "embed: false, theme: null, bbox: null," in embed_fns
    assert "return q ? q.slice(0, 2000) : 'map';" in embed_fns
    assert "VIEW_QUERY.classifications.filter(k => CLASS_LABELS[k] || CLASS_DESCENDANTS[k])" in embed_fns
    assert "return 'fit';" in embed_fns
    assert APP_JS.count("track('Embed Link Clicked', { target: ") == 2
    assert APP_JS.count("view: embedView(), locale: LANG });") == 2
    # Plausible labels a missing property '(none)'; the sentinel must not collide.
    assert ": 'no-referrer'; } catch (e) { return 'no-referrer'; }" in APP_JS
    assert "'(none)'" not in APP_JS[APP_JS.index("function embedHost()"):APP_JS.index("const brandControl")]
    assert "if (EMBED) return VIEW_QUERY.theme === 'dark' ? 'dark' : 'light';" in APP_JS
    assert "function fitPadding(base) {\n    if (EMBED) return base;" in APP_JS
    assert "if (!EMBED) map.addControl(settingsControl, 'top-right');" in APP_JS


def test_share_button_follows_the_settings_button_in_dark_mode() -> None:
    # Feedback 2026-10-22: the stroke icon stayed near-black on the dark control.
    css = mt._STYLE_CSS
    assert "html.theme-dark .owm-settings .owm-settings-btn {{ color:var(--n-dark-text) }}" in css
    assert "html.theme-dark .owm-share .owm-share-btn {{ color:var(--n-dark-text) }}" in css
    # The share dialog takes every dark-mode rule of the About dialog: the panel,
    # the headings, the close button, the focus ring (feedback 2026-10-22: the
    # parameter table painted its dark rows on a dialog that had stayed white).
    assert "html.theme-dark #about-dialog, html.theme-dark #share-dialog {{ background:var(--n-dark-panel)" in css
    assert "html.theme-dark #share-dialog h2, html.theme-dark #share-dialog h3 {{ color:var(--c-accent-ink-dark)" in css
    assert "html.theme-dark #share-dialog .close {{" in css and "html.theme-dark #share-dialog textarea:focus-visible" in css


def test_the_cdn_allows_framing() -> None:
    # The embed needs the X-Frame-Options: SAMEORIGIN edge rule gone. Retiring
    # a security header is applied by hand (scratchpad diff, 2026-10-22); this
    # stays red until it is.
    assert '("X-Frame-Options", "SAMEORIGIN")' not in DEPLOY
    assert '_RETIRED_HEADERS: tuple[str, ...] = ("X-Frame-Options",)' in DEPLOY
