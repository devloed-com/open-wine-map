"""The promoted-denomination registry (scripts/_lib/promoted_gis.json) and
its rendering: a DGC that became an appellation of its own stays in the
corpus, marked with where the name went — never dropped, never called
cancelled."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.content_block import (  # noqa: E402
    RenderCtx,
    promoted_badge_html,
    promoted_line_html,
    render_content_block,
)
from _lib.map_template import STARTUP_AOCS_FIELDS, build_labels  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts" / "_lib" / "promoted_gis.json"
CANCELLED = ROOT / "scripts" / "_lib" / "cancelled_gis.json"
SUPPLEMENTS = ROOT / "scripts" / "_lib" / "fr" / "siqo_supplements.json"


def _entries(path: Path = REGISTRY) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("__")}


def test_registry_entries_are_complete_and_cited():
    entries = _entries()
    assert entries, "registry is empty"
    for slug, e in entries.items():
        assert re.fullmatch(r"[a-z0-9-]+", slug), slug
        assert e["name"] and e["country"], slug
        date.fromisoformat(e["promoted_on"])
        assert e["successor_slug"] and e["successor_name"], slug
        assert e["national_act"], slug
        assert e["national_url"].startswith("https://"), slug
        if e.get("cahier_url"):
            assert e["cahier_url"].startswith("https://"), slug


def test_a_promotion_is_not_also_a_cancellation():
    assert not set(_entries()) & set(_entries(CANCELLED))


def test_successor_is_in_the_referentiel_or_its_supplements():
    """The successor record must exist for the link to resolve: either the
    SIQO export carries it or the supplements file adds it."""
    sup = json.loads(SUPPLEMENTS.read_text(encoding="utf-8"))
    supplement_names = {r["appellation"] for r in sup.get("rows", [])}
    for slug, e in _entries().items():
        if e["country"] != "fr":
            continue
        assert e["successor_name"] in supplement_names or _siqo_has(e["successor_name"]), slug


def _siqo_has(name: str) -> bool:
    csv_path = ROOT / "raw" / "inao" / "siqo-referentiel.csv"
    if not csv_path.exists():
        return True  # no corpus checked out — nothing to contradict
    return f",{name}," in csv_path.read_text(encoding="utf-8-sig")


def test_promoted_is_a_startup_field():
    assert "promoted" in STARTUP_AOCS_FIELDS


def _ctx(locale: str = "en") -> RenderCtx:
    labels = build_labels(lambda s: s)
    labels.update({
        "promoted_badge": "Promoted",
        "promoted_line": "On {date} this denomination became the appellation {successor} ({act}).",
        "promoted_cahier": "Specification of the new appellation: {cahier}.",
        "promoted_cahier_link": "BO Agri (PDF)",
        "promoted_badge_title": "Became an appellation in its own right on {date}",
    })
    return RenderCtx(
        locale=locale, labels=labels, region_labels={}, country_labels={"fr": "France"},
        country_flag_emoji={"fr": "🇫🇷"}, grapes_info={}, styles_info={}, style_labels={},
        github_new_issue_url="https://example.invalid/new",
    )


_REC = {
    "name": "Languedoc Montpeyroux", "kind": "AOC", "country": "fr", "region": "",
    "promoted": {
        "promoted_on": "2026-08-11",
        "successor_slug": "montpeyroux",
        "successor_name": "Montpeyroux",
        "national_act": "Arrêté du 11 août 2026",
        "national_url": "https://www.legifrance.gouv.fr/eli/arrete/2026/8/11/AGRT2607509A/jo/texte",
        "cahier_url": "https://info.agriculture.gouv.fr/boagri/document_administratif-x/telechargement",
    },
}


def test_badge_and_line_render_with_localised_date_and_links():
    ctx = _ctx("en")
    badge = promoted_badge_html(_REC, ctx)
    assert 'class="promoted-badge"' in badge and ">Promoted<" in badge
    assert 'title="Became an appellation in its own right on August 11, 2026"' in badge
    assert 'class="promoted-badge sm"' in promoted_badge_html(_REC, ctx, small=True)
    line = promoted_line_html(_REC, ctx)
    assert line.startswith('<div class="promoted-line">')
    assert "August 11, 2026" in line
    assert 'data-slug="montpeyroux"' in line and ">Montpeyroux<" in line
    assert 'href="https://www.legifrance.gouv.fr/eli/arrete/2026/8/11/AGRT2607509A/jo/texte"' in line
    assert 'href="https://info.agriculture.gouv.fr/boagri/document_administratif-x/telechargement"' in line
    assert "Specification of the new appellation:" in line


def test_date_follows_the_page_locale():
    assert "11 août 2026" in promoted_line_html(_REC, _ctx("fr"))
    assert "11 augustus 2026" in promoted_line_html(_REC, _ctx("nl"))


def test_unpromoted_record_renders_nothing():
    ctx = _ctx()
    assert promoted_badge_html({"name": "x"}, ctx) == ""
    assert promoted_line_html({"name": "x"}, ctx) == ""


def test_card_carries_badge_in_meta_and_line_under_the_header():
    html = render_content_block({**_REC, "sources": {}}, "languedoc-montpeyroux", _ctx("en"))
    meta_i = html.index('class="meta"')
    badge_i = html.index('class="promoted-badge"')
    line_i = html.index('class="promoted-line"')
    assert meta_i < badge_i < line_i
    assert "cancelled" not in html
