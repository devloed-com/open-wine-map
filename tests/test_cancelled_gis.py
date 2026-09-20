"""The cancelled-GI registry (scripts/_lib/cancelled_gis.json) and its
rendering: a cancelled appellation stays in the corpus and is marked, never
silently dropped."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.content_block import (  # noqa: E402
    RenderCtx,
    cancelled_badge_html,
    cancelled_line_html,
    render_content_block,
)
from _lib.map_template import STARTUP_AOCS_FIELDS, build_labels  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts" / "_lib" / "cancelled_gis.json"


def _entries() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("__")}


def test_registry_entries_are_complete_and_cited():
    entries = _entries()
    assert entries, "registry is empty"
    for slug, e in entries.items():
        assert re.fullmatch(r"[a-z0-9-]+", slug), slug
        assert e["name"] and e["country"] and e["file_number"], slug
        date.fromisoformat(e["cancelled_on"])
        assert e["regulation"].startswith("Commission Implementing Regulation"), slug
        assert e["regulation_url"].startswith("http://data.europa.eu/eli/reg_impl/"), slug
        if e.get("national_act"):
            assert e.get("national_url", "").startswith("https://"), slug
        if e.get("successor_slug"):
            assert e.get("successor_name"), slug


def test_cancelled_is_a_startup_field():
    assert "cancelled" in STARTUP_AOCS_FIELDS


def _ctx(locale: str = "en") -> RenderCtx:
    labels = build_labels(lambda s: s)
    labels.update({
        "cancelled_badge": "Cancelled",
        "cancelled_line": "Cancelled on {date} by {regulation}.",
        "cancelled_national_act": "National act: {act}.",
        "cancelled_successor": "Succeeded by {successor}.",
        "cancelled_badge_title": "Registration cancelled on {date}",
    })
    return RenderCtx(
        locale=locale, labels=labels, region_labels={}, country_labels={"fr": "France"},
        country_flag_emoji={"fr": "🇫🇷"}, grapes_info={}, styles_info={}, style_labels={},
        github_new_issue_url="https://example.invalid/new",
    )


_REC = {
    "name": "Cité de Carcassonne", "kind": "IGP", "country": "fr", "region": "",
    "cancelled": {
        "cancelled_on": "2025-12-17",
        "regulation": "Commission Implementing Regulation (EU) 2025/2538",
        "regulation_url": "http://data.europa.eu/eli/reg_impl/2025/2538/oj",
        "national_act": "Arrêté du 31 mars 2025",
        "national_url": "https://www2.inao.gouv.fr/produit/17118",
    },
}


def test_badge_and_line_render_with_localised_date_and_links():
    ctx = _ctx("en")
    badge = cancelled_badge_html(_REC, ctx)
    assert 'class="cancelled-badge"' in badge and ">Cancelled<" in badge
    assert 'title="Registration cancelled on December 17, 2025"' in badge
    assert 'class="cancelled-badge sm"' in cancelled_badge_html(_REC, ctx, small=True)
    line = cancelled_line_html(_REC, ctx)
    assert line.startswith('<div class="cancelled-line">')
    assert "December 17, 2025" in line
    assert 'href="http://data.europa.eu/eli/reg_impl/2025/2538/oj"' in line
    assert 'href="https://www2.inao.gouv.fr/produit/17118"' in line
    assert "National act:" in line
    assert "Succeeded by" not in line


def test_date_follows_the_page_locale():
    assert "17 décembre 2025" in cancelled_line_html(_REC, _ctx("fr"))
    assert "17 december 2025" in cancelled_line_html(_REC, _ctx("nl"))


def test_uncancelled_record_renders_nothing():
    ctx = _ctx()
    assert cancelled_badge_html({"name": "x"}, ctx) == ""
    assert cancelled_line_html({"name": "x"}, ctx) == ""


def test_card_carries_badge_in_meta_and_line_before_dgc():
    html = render_content_block({**_REC, "sources": {}}, "cite-de-carcassonne", _ctx("en"))
    meta_i = html.index('class="meta"')
    badge_i = html.index('class="cancelled-badge"')
    line_i = html.index('class="cancelled-line"')
    assert meta_i < badge_i < line_i
