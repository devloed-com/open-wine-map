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


def test_about_dialog_sections_are_h3_under_the_title() -> None:
    labels = defaultdict(str, {
        "about_h": "About Open Wine Map",
        "about_sources_h": "Sources", "about_method_h": "How the map is made",
        "about_ai_h": "For AI assistants", "about_privacy_h": "Privacy",
        "about_contrib_h": "Contribute and follow",
    })
    html = _build_about_dialog(labels)
    for heading in ("Sources", "How the map is made", "For AI assistants", "Privacy",
                    "Contribute and follow"):
        assert f"<section><h3>{heading}</h3>" in html
    assert html.index('<h2 id="about-dialog-h"') < html.index("<h3>")


def test_about_method_section_leads_with_the_code_pipeline() -> None:
    # "How the map is made" (2026-10-20): first what the code pipeline extracts
    # from the specifications, then what the language models add, then the
    # level-of-detail note on how the map draws it — so a reader learns the
    # data is parsed, not generated, before reading about the models.
    labels = defaultdict(str, {
        "about_method_h": "How the map is made",
        "about_pipeline_html": "PIPELINE PARAGRAPH",
        "about_lod_html": "LOD {zoom} {radius}",
        "about_llm_html": "LLM PARAGRAPH",
    })
    html = _build_about_dialog(labels, lod={"overview_max_zoom": 11.9, "radius_m": 250})
    section = html[html.index("<h3>How the map is made</h3>"):html.index("<h3>", html.index("<h3>How the map is made</h3>") + 1)]
    assert section.index("PIPELINE PARAGRAPH") < section.index("LLM PARAGRAPH") < section.index("LOD 11.9 250")
