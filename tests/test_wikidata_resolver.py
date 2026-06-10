"""Offline unit tests for the pure Wikidata-resolution helpers
(scripts/_lib/wikidata.py) — no network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.wikidata import (  # noqa: E402
    normalize_qid,
    parse_pageprops,
    parse_sparql_p9854,
    resolve_title_qid,
    title_from_page,
    title_resolution_map,
    wikidata_url,
)


def test_normalize_qid() -> None:
    assert normalize_qid("Q1754563") == "Q1754563"
    assert normalize_qid("q42") == "Q42"
    assert normalize_qid("http://www.wikidata.org/entity/Q808584") == "Q808584"
    assert normalize_qid("https://www.wikidata.org/wiki/Q5/") == "Q5"
    assert normalize_qid("") == ""
    assert normalize_qid(None) == ""
    assert normalize_qid("foo") == ""
    assert normalize_qid("Q0") == ""  # leading digit must be 1-9
    assert normalize_qid("P9854") == ""  # property, not item


def test_wikidata_url() -> None:
    assert wikidata_url("Q42") == "https://www.wikidata.org/wiki/Q42"
    assert wikidata_url("") == ""
    assert wikidata_url("garbage") == ""


def test_parse_sparql_p9854() -> None:
    payload = {"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q750979"},
         "e": {"value": "EUGI00000003581"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q808584"},
         "e": {"value": "EUGI00000004441"}},
        # duplicate eAmbrosia id → first binding wins
        {"item": {"value": "http://www.wikidata.org/entity/Q999999"},
         "e": {"value": "EUGI00000003581"}},
    ]}}
    table = parse_sparql_p9854(payload)
    assert table == {"EUGI00000003581": "Q750979", "EUGI00000004441": "Q808584"}


def test_parse_sparql_empty() -> None:
    assert parse_sparql_p9854({}) == {}
    assert parse_sparql_p9854({"results": {"bindings": []}}) == {}


def _mw_payload() -> dict:
    # formatversion=2 shape, with a normalization and a redirect hop + a miss.
    return {"query": {
        "normalized": [{"from": "Rioja_(vino)", "to": "Rioja (vino)"}],
        "redirects": [{"from": "Rioja (vino)", "to": "Rioja (DOCa)"}],
        "pages": [
            {"pageid": 1, "title": "Rioja (DOCa)", "pageprops": {"wikibase_item": "Q1569384"}},
            {"pageid": 2, "title": "Barolo (vino)", "pageprops": {"wikibase_item": "Q808584"}},
            {"title": "Nonexistent", "missing": True},
        ],
    }}


def test_parse_pageprops() -> None:
    pp = parse_pageprops(_mw_payload())
    assert pp == {"Rioja (DOCa)": "Q1569384", "Barolo (vino)": "Q808584"}


def test_resolve_title_qid_follows_normalize_and_redirect() -> None:
    payload = _mw_payload()
    pp = parse_pageprops(payload)
    res = title_resolution_map(payload)
    # requested "Rioja_(vino)" → normalized → redirected → final title
    assert resolve_title_qid("Rioja_(vino)", pp, res) == "Q1569384"
    # direct title hit
    assert resolve_title_qid("Barolo (vino)", pp, res) == "Q808584"
    # unresolved
    assert resolve_title_qid("Nonexistent", pp, res) == ""


def test_title_from_page() -> None:
    assert title_from_page("Rioja (vino)", "https://es.wikipedia.org/wiki/Rioja_(vino)") \
        == "Rioja (vino)"
    # no page_title → derive from URL (underscores → spaces, percent-decoded)
    assert title_from_page(None, "https://fr.wikipedia.org/wiki/Ch%C3%A2teauneuf-du-Pape") \
        == "Châteauneuf-du-Pape"
    assert title_from_page("", "https://fr.wikipedia.org/wiki/Agenais_(IGP)") == "Agenais (IGP)"
    assert title_from_page("", "") == ""
