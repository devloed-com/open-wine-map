"""Guards the single-<h1>-per-page invariant (Bing SiteScan / SEO: a page
should have exactly one <h1>).

The map chrome wraps both the homepage and every entity page, so the heading
levels are conditional: the brand wordmark is the page <h1> only when there is
no appellation SSR card (homepage + fold pages); on an index entity page it
demotes to a <p> and the appellation name (from the SSR content block) is the
single <h1>. The About-dialog title is an <h2>, never a second <h1>.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.map_template import _PAGE_TEMPLATE, _SIDEBAR, _build_about_dialog  # noqa: E402


def test_brand_heading_tag_is_parameterized() -> None:
    # Brand wordmark wraps in a {brand_tag} slot (h1 on homepage / fold, p on
    # index pages) and carries the stable .brand-title class for styling. It
    # lives in the sidebar chrome (`_SIDEBAR`), which `_PAGE_TEMPLATE` composes
    # via the `%%SIDEBAR%%` placeholder at render time.
    assert "%%SIDEBAR%%" in _PAGE_TEMPLATE
    assert '<{brand_tag} class="brand-title">' in _SIDEBAR
    assert "</{brand_tag}>" in _SIDEBAR
    # The brand is no longer a hard-coded <h1>.
    assert "<h1><img class=\"brand-mark\"" not in _SIDEBAR
    assert "<h1><img class=\"brand-mark\"" not in _PAGE_TEMPLATE


def test_about_dialog_title_is_h2_not_h1() -> None:
    html = _build_about_dialog(defaultdict(str, {"about_h": "About Open Wine Map"}))
    assert '<h2 id="about-dialog-h"' in html
    assert "<h1" not in html
