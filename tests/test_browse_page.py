"""The browse index (`/<locale>/appellations/`) reads like the About dialog
(2026-10-21) and stays the static crawl hub: the map's own design tokens and
theme choice, the dialog's title and heading treatment, on a page-wide
multi-column list whose DOM — one h1, an h2 per country, plain lists of real
links, the CollectionPage JSON-LD, no app bundle — is what crawlers read."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import map_template as mt  # noqa: E402
from _lib.map_template import (  # noqa: E402
    _BROWSE_CSS,
    _BROWSE_TEMPLATE,
    _THEME_PREPAINT_JS,
    _design_tokens_css,
    _render_browse_page,
    _static_page_css,
    build_labels,
)

_OLD_ACCENTS = ("#7a1f3a", "#7A1F2B", "#7a1f2b")


def _page(locale: str = "en") -> str:
    aocs = {
        "mercurey": {"country": "fr", "name": "Mercurey", "class_label": "AOC (PDO)"},
        "rioja": {"country": "es", "name": "Rioja", "class_label": "DOCa (PDO)"},
        "naoussa": {"country": "gr", "name": "Νάουσα", "name_latin": "Naoussa",
                    "class_label": "PDO"},
    }
    return _render_browse_page(
        locale=locale,
        labels=build_labels(lambda s: s),
        country_labels={"fr": "France", "es": "Spain", "gr": "Greece"},
        aocs=aocs,
        index_slugs=["rioja", "naoussa", "mercurey"],
    )


def test_design_tokens_are_the_maps() -> None:
    # The `:root` block is the shell's, braces undone — one source per colour.
    tokens = _design_tokens_css()
    assert tokens.startswith(":root {")
    assert "{{" not in tokens and "}}" not in tokens
    shell = mt._STYLE_CSS
    block = shell[shell.index(":root {{"): shell.index("}}", shell.index(":root {{")) + 2]
    assert tokens.strip() == block.replace("{{", "{").replace("}}", "}")
    assert "--c-accent:#934050" in tokens
    for name in ("--n-0", "--n-850", "--n-dark-panel", "--c-accent-ink-dark", "--fs-md"):
        assert name + ":" in tokens, name


def test_page_roles_follow_the_theme_setting_then_the_os() -> None:
    css = _static_page_css()
    light = css[css.index(":root { --pg-bg"):]
    assert "--pg-accent:var(--c-accent)" in light
    assert "html.theme-dark { --pg-bg:var(--n-dark-panel)" in css
    assert "--pg-accent:var(--c-accent-ink-dark)" in css
    # Without JS the OS scheme decides; an explicit light choice wins over it.
    assert "@media (prefers-color-scheme: dark) {\n  html:not(.theme-light) {" in css
    # The pre-paint script is the map's rule: localStorage `theme`, else the OS.
    assert "localStorage.getItem('theme')" in _THEME_PREPAINT_JS
    assert "(t==='dark')||(t!=='light'&&" in _THEME_PREPAINT_JS
    assert "classList.add(dark?'theme-dark':'theme-light')" in _THEME_PREPAINT_JS
    page = _page()
    assert f"<script>{_THEME_PREPAINT_JS}</script>" in page
    assert page.index("<script>") < page.index("<style>")


def test_components_use_roles_and_the_about_treatment() -> None:
    for old in _OLD_ACCENTS:
        assert old not in _BROWSE_CSS and old not in _BROWSE_TEMPLATE, old
    assert re.search(r"#[0-9a-fA-F]{3,6}\b", _BROWSE_CSS) is None, "components carry no literal colour"
    assert "var(--n-" not in _BROWSE_CSS and "var(--side-" not in _BROWSE_CSS
    # The About dialog's title: 20px over a 2px accent rule.
    assert ".browse-main h1 { font-size:20px;" in _BROWSE_CSS
    assert "border-bottom:2px solid var(--pg-accent-rule)" in _BROWSE_CSS
    # Its section headings: small, uppercase, accent.
    h2 = _BROWSE_CSS[_BROWSE_CSS.index(".browse-country h2 {"):]
    h2 = h2[: h2.index("}")]
    for rule in ("font-size:var(--fs-sm)", "text-transform:uppercase", "color:var(--pg-accent)"):
        assert rule in h2, rule
    # Its ruled credit line.
    assert ".browse-footer { margin-top:20px; padding-top:10px;" in _BROWSE_CSS
    assert "border-top:1px solid var(--pg-rule)" in _BROWSE_CSS
    # The list stays page-wide and multi-column — a 520 px column would not
    # hold 1,600 links.
    assert "column-width:250px" in _BROWSE_CSS
    assert "max-width:1100px" in _BROWSE_CSS


def test_header_is_the_brand_block_and_the_locale_names() -> None:
    page = _page("fr")
    header = page[page.index('<header class="browse-header">'): page.index("</header>")]
    assert header.index('<a class="browse-brand" href="/fr/">') < header.index('<nav class="browse-lang"')
    assert 'src="/assets/pin-icon.svg"' in header
    assert "Open Wine Map</a>" in header
    for code, name in (("fr", "Français"), ("en", "English"), ("es", "Español"), ("nl", "Nederlands")):
        assert f'href="/{code}/appellations/"' in header
        assert f">{name}</a>" in header
    assert 'class="lang active" aria-current="page">Français</a>' in header
    assert "browse-header { background:" not in _BROWSE_CSS  # the maroon bar is gone


def test_social_card_tags_match_the_map_shell() -> None:
    # Ahrefs (2026-11-06): the four browse hubs were the only pages without
    # og:image and twitter:* — the shell template carries the social card, the
    # browse template did not.
    page = _page("fr")
    assert '<meta property="og:image" content="https://www.openwinemap.com/assets/social-card.png">' in page
    assert '<meta property="og:image:width" content="1200">' in page
    assert '<meta property="og:image:alt" content="Toutes les appellations' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert '<meta name="twitter:image" content="https://www.openwinemap.com/assets/social-card.png">' in page
    assert page.count('<meta name="twitter:description" content="') == 1


def test_dom_for_machines_is_unchanged() -> None:
    page = _page()
    assert page.count("<h1>") == 1 and "<h1>Toutes les appellations</h1>" in page
    for cc, label in (("fr", "France"), ("es", "Spain"), ("gr", "Greece")):
        assert f'<section class="browse-country" id="c-{cc}">' in page
        assert f"{label} (1)</h2>" in page
    assert '<li><a href="/en/mercurey">Mercurey</a> <small>AOC (PDO)</small></li>' in page
    assert '<li><a href="/en/naoussa">Naoussa (Νάουσα)</a> <small>PDO</small></li>' in page
    assert '<link rel="canonical" href="https://www.openwinemap.com/en/appellations/">' in page
    assert 'hreflang="x-default" href="https://www.openwinemap.com/en/appellations/"' in page
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
    assert ld["@type"] == "CollectionPage" and ld["inLanguage"] == "en"
    # Static and self-contained: no app bundle, no data blob, nothing folded.
    assert "app." not in page and "__OWM_DATA" not in page and "maplibre" not in page.lower()
    assert "<details" not in page
    assert '<footer class="browse-footer">' in page and 'class="heart"' in page
    assert '<meta name="theme-color" content="#934050" media="(prefers-color-scheme: light)">' in page
