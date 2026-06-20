"""Tests for the per-appellation JSON-LD `@graph` (scripts/_lib/map_template.py).

Pins the structured-data contract that SEO + AI-answer-engine grounding rely
on: a WebSite → WebPage → Place → BreadcrumbList graph with stable `@id`
cross-references, a localized description, `inLanguage`, a `sameAs` identity
cluster (Wikidata → Wikipedia → regulator), and a BreadcrumbList in which
every non-final item carries an `item` URL (the country level is dropped — a
URL-less middle item is invalid for Google's BreadcrumbList rich result).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.map_template import _build_entity_jsonld, _build_entity_meta  # noqa: E402

_COUNTRY_LABELS = {"fr": "France", "es": "España", "nl": "Nederland"}
_REGION_LABELS = {"PRIORAT": "Priorat"}
_LABELS = {"facet_principal_h": "Principal grapes"}
_GRAPES_INFO = {"garnacha": {"name": "Garnacha"}}

_BASE = "https://www.openwinemap.com"


def _parse(html: str) -> dict:
    assert html.startswith('<script type="application/ld+json">')
    assert html.endswith("</script>")
    body = html[len('<script type="application/ld+json">'):-len("</script>")]
    return json.loads(body)


def _graph(rec: dict, slug="x", locale="en", region="Priorat", desc="fallback desc") -> dict:
    canonical = f"{_BASE}/{locale}/{slug}"
    return _parse(
        _build_entity_jsonld(slug, rec, canonical, locale, _COUNTRY_LABELS, region, desc=desc)
    )


def _node(graph: dict, typ: str) -> dict:
    return next(n for n in graph["@graph"] if n["@type"] == typ)


_RICH = {
    "name": "Priorat", "kind": "DOP", "country": "es", "region": "Priorat",
    "bbox": [0.7, 41.1, 1.0, 41.4], "wikidata_qid": "Q1754563",
    "summary": "El Priorat es una zona vitícola de gran prestigio.",
    "terroir_facts": {"wiki_source_url": "https://es.wikipedia.org/wiki/Priorato_(vino)"},
    "sources": {"eur_lex_url": "https://eur-lex.europa.eu/x",
                "syndicate": {"url": "https://www.doqpriorat.org", "label": "DOQ"}},
}


def test_valid_json_and_context() -> None:
    g = _graph(_RICH, slug="priorat", locale="es")
    assert g["@context"] == "https://schema.org"
    assert isinstance(g["@graph"], list)


def test_graph_node_types_and_ids() -> None:
    g = _graph(_RICH, slug="priorat", locale="es")
    canonical = f"{_BASE}/es/priorat"
    assert {n["@type"] for n in g["@graph"]} == {
        "WebSite", "WebPage", "AdministrativeArea", "BreadcrumbList"
    }
    assert _node(g, "WebSite")["@id"] == f"{_BASE}/#website"
    assert _node(g, "WebPage")["@id"] == f"{canonical}#webpage"
    assert _node(g, "AdministrativeArea")["@id"] == f"{canonical}#place"
    assert _node(g, "BreadcrumbList")["@id"] == f"{canonical}#breadcrumb"


def test_cross_references_resolve_by_id() -> None:
    g = _graph(_RICH, slug="priorat", locale="es")
    wp = _node(g, "WebPage")
    assert wp["mainEntity"]["@id"] == _node(g, "AdministrativeArea")["@id"]
    assert wp["breadcrumb"]["@id"] == _node(g, "BreadcrumbList")["@id"]
    assert wp["isPartOf"]["@id"] == _node(g, "WebSite")["@id"]


def test_sameas_rich_record_ordered_and_deduped() -> None:
    place = _node(_graph(_RICH, slug="priorat", locale="es"), "AdministrativeArea")
    assert place["sameAs"] == [
        "https://www.wikidata.org/wiki/Q1754563",
        "https://es.wikipedia.org/wiki/Priorato_(vino)",
        "https://www.doqpriorat.org",
    ]


def test_sameas_omitted_when_no_identifiers() -> None:
    bare = {"name": "X", "kind": "AOC", "country": "fr", "sources": {}, "terroir_facts": {}}
    place = _node(_graph(bare), "AdministrativeArea")
    assert "sameAs" not in place


def test_sameas_dedupes_shared_url() -> None:
    rec = {"name": "X", "country": "fr", "wikidata_qid": "",
           "terroir_facts": {"wiki_source_url": "https://example.org/a"},
           "sources": {"syndicate": {"url": "https://example.org/a"}}}
    place = _node(_graph(rec), "AdministrativeArea")
    assert place["sameAs"] == ["https://example.org/a"]


def test_description_prefers_summary() -> None:
    place = _node(_graph(_RICH, slug="priorat", locale="es"), "AdministrativeArea")
    assert place["description"].startswith("El Priorat es una zona")


def test_description_falls_back_to_facts_then_meta() -> None:
    facts_rec = {"name": "X", "country": "fr", "summary": "",
                 "terroir_facts": {"facts": [{"bullet": "Schist soils."},
                                              {"bullet": "Cool nights."}]}}
    place = _node(_graph(facts_rec), "AdministrativeArea")
    assert "Schist soils." in place["description"] and "Cool nights." in place["description"]

    none_rec = {"name": "X", "country": "fr", "summary": "", "terroir_facts": {}}
    place2 = _node(_graph(none_rec, desc="META FALLBACK"), "AdministrativeArea")
    assert place2["description"] == "META FALLBACK"


def test_inlanguage_matches_locale() -> None:
    for loc in ("en", "fr", "es", "nl"):
        g = _graph(_RICH, slug="priorat", locale=loc)
        for typ in ("WebSite", "WebPage", "AdministrativeArea"):
            assert _node(g, typ)["inLanguage"] == loc


def test_breadcrumb_every_nonfinal_item_has_url() -> None:
    # The reported Google error: a non-final ListItem (the country) without
    # `item`. The country level is now dropped, so every non-final crumb has a
    # URL.
    g = _graph(_RICH, slug="priorat", locale="es")
    items = _node(g, "BreadcrumbList")["itemListElement"]
    assert [i["position"] for i in items] == list(range(1, len(items) + 1))
    assert all("item" in i for i in items[:-1])
    assert items[0]["name"] == "Open Wine Map"
    assert items[0]["item"] == f"{_BASE}/es/"
    assert items[-1]["item"] == f"{_BASE}/es/priorat"
    # no country crumb
    assert "España" not in [i["name"] for i in items]


def test_breadcrumb_subdenomination_inserts_parent() -> None:
    sub = dict(_RICH, is_sub_denomination=True, parent_name="Cataluña",
               parent_slug="catalunya")
    items = _node(_graph(sub, slug="x", locale="es"), "BreadcrumbList")["itemListElement"]
    names = [i["name"] for i in items]
    assert names == ["Open Wine Map", "Cataluña", "x" if False else sub["name"]]
    parent = items[1]
    assert parent["name"] == "Cataluña"
    assert parent["item"] == f"{_BASE}/es/catalunya"
    assert all("item" in i for i in items)  # all carry a URL


def test_contains_place_lists_children_with_absolute_urls() -> None:
    # A parent enumerates its folded sub-denominations as containsPlace — the
    # entity-graph half of surfacing children that have no indexable page.
    kids = [
        {"name": "Clisson", "path": "/en/clisson", "kind": "AOC"},
        {"name": "Gorges", "path": "/en/gorges", "kind": "AOC"},
    ]
    html = _build_entity_jsonld(
        "muscadet", _RICH, f"{_BASE}/en/muscadet", "en", _COUNTRY_LABELS, "Loire",
        desc="d", children=kids,
    )
    place = _node(_parse(html), "AdministrativeArea")
    assert place["containsPlace"] == [
        {"@type": "AdministrativeArea", "name": "Clisson", "url": f"{_BASE}/en/clisson"},
        {"@type": "AdministrativeArea", "name": "Gorges", "url": f"{_BASE}/en/gorges"},
    ]


def test_contains_place_omitted_without_children() -> None:
    place = _node(_graph(_RICH, slug="priorat", locale="es"), "AdministrativeArea")
    assert "containsPlace" not in place


def test_geo_box_axis_order() -> None:
    rec = dict(_RICH, bbox=[2.0, 43.0, 3.0, 44.0])
    place = _node(_graph(rec), "AdministrativeArea")
    assert place["geo"] == {"@type": "GeoShape", "box": "43.0 2.0 44.0 3.0"}


def test_additionaltype_is_wine_region() -> None:
    place = _node(_graph(_RICH, slug="priorat", locale="es"), "AdministrativeArea")
    assert place["additionalType"] == "https://www.wikidata.org/wiki/Q2140699"


def test_isbasedon_from_source_docs() -> None:
    wp = _node(_graph(_RICH, slug="priorat", locale="es"), "WebPage")
    assert wp["isBasedOn"] == "https://eur-lex.europa.eu/x"


def test_no_article_or_fabricated_dates() -> None:
    g = _graph(_RICH, slug="priorat", locale="es")
    assert "Article" not in {n["@type"] for n in g["@graph"]}
    blob = json.dumps(g)
    for forbidden in ("datePublished", "dateModified", '"author"'):
        assert forbidden not in blob


def test_folded_page_emits_no_jsonld() -> None:
    meta = _build_entity_meta(
        "priorat", _RICH, "es", _LABELS, _REGION_LABELS, _COUNTRY_LABELS,
        _GRAPES_INFO, folded=True,
    )
    assert meta["jsonld_html"] == ""


def test_index_page_emits_jsonld() -> None:
    meta = _build_entity_meta(
        "priorat", _RICH, "es", _LABELS, _REGION_LABELS, _COUNTRY_LABELS,
        _GRAPES_INFO, folded=False,
    )
    assert meta["jsonld_html"].startswith('<script type="application/ld+json">')


def test_jsonld_survives_str_format() -> None:
    # The {jsonld_html} template slot is a str.format field; its JSON braces are
    # data, not format fields. Round-tripping must not corrupt or raise.
    html = _build_entity_jsonld(
        "priorat", _RICH, f"{_BASE}/es/priorat", "es", _COUNTRY_LABELS, "Priorat",
    )
    assert "{jsonld_html}".format(jsonld_html=html) == html
