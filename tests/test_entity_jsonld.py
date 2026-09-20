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

from _lib.map_template import (  # noqa: E402
    _build_entity_jsonld,
    _build_entity_meta,
    _lang_switcher,
)

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


def test_description_uses_summary_when_no_facts_and_readable() -> None:
    # ES record, ES page: the summary is written in the page locale.
    place = _node(_graph(_RICH, slug="priorat", locale="es"), "AdministrativeArea")
    assert place["description"].startswith("El Priorat es una zona")
    # Same record on the EN page: an untranslated ES summary is not an English
    # description — fall back to the meta text.
    place = _node(_graph(_RICH, slug="priorat", locale="en", desc="META"), "AdministrativeArea")
    assert place["description"] == "META"
    # …unless stage 02c translated it.
    translated = {**_RICH, "summary": "Priorat is a prestigious wine zone.",
                  "summary_translation": {"translator": "x"}}
    place = _node(_graph(translated, slug="priorat", locale="en"), "AdministrativeArea")
    assert place["description"].startswith("Priorat is a prestigious")


def test_description_prefers_facts_over_summary_and_the_bullet_naming_the_record() -> None:
    # Facts XOR summary, as on the panel: a record with facts never surfaces
    # its summary (for FR that is the untranslated decree boilerplate).
    rec = {"name": "Santenay", "country": "fr",
           "summary": "Seuls peuvent prétendre à l'appellation d'origine contrôlée…",
           "terroir_facts": {"facts": [
               {"bullet": "The Côte de Beaune forms a rectilinear relief."},
               {"bullet": "At Santenay, the Côte curves westward."},
               {"bullet": "The parcels sit between 210 and 450 metres."}]}}
    place = _node(_graph(rec, locale="en"), "AdministrativeArea")
    assert place["description"] == (
        "At Santenay, the Côte curves westward. The Côte de Beaune forms a rectilinear relief."
    )
    assert "Seuls peuvent" not in place["description"]

    none_rec = {"name": "X", "country": "fr", "summary": "", "terroir_facts": {}}
    place2 = _node(_graph(none_rec, desc="META FALLBACK"), "AdministrativeArea")
    assert place2["description"] == "META FALLBACK"


def test_meta_description_leads_with_the_record_and_fits_160() -> None:
    rec = {"name": "Santenay", "kind": "AOC", "class_label": "AOC (PDO)", "country": "fr",
           "region": "PRIORAT", "grapes_principal": ["garnacha"],
           "summary": "Seuls peuvent prétendre à l'appellation…",
           "terroir_facts": {"facts": [
               {"bullet": "The Côte de Beaune forms a rectilinear relief of tectonic origin "
                          "extending over approximately 25 kilometres."},
               {"bullet": "At Santenay, the Côte curves westward and continues along the left "
                          "bank of the Dheune valley, a river draining the granitic hinterland, "
                          "with slopes that are predominantly south-facing."}]}}
    meta = _build_entity_meta(
        "santenay", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO
    )
    desc = meta["meta_description"]
    assert desc.startswith("Santenay, Priorat, France · AOC (PDO). At Santenay, the Côte curves")
    assert len(desc) <= 160 and desc.endswith("…")
    assert "Seuls peuvent" not in desc and "Principal grapes" not in desc

    # A short lead leaves room for the grapes; no lead at all → the grape
    # template alone, as before.
    short = {**rec, "terroir_facts": {"facts": [{"bullet": "Schist soils."}]}}
    meta = _build_entity_meta(
        "santenay", short, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO
    )
    assert meta["meta_description"] == (
        "Santenay, Priorat, France · AOC (PDO). Schist soils. Principal grapes: Garnacha."
    )
    bare = {**rec, "terroir_facts": {}}
    meta = _build_entity_meta(
        "santenay", bare, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO
    )
    assert meta["meta_description"] == (
        "Santenay, Priorat, France · AOC (PDO). Principal grapes: Garnacha."
    )


def test_lang_switcher_keeps_the_appellation_on_entity_pages() -> None:
    home = _lang_switcher("en", "Language")
    assert 'href="/fr/"' in home and 'href="/"' in home
    page = _lang_switcher("en", "Language", slug="santenay")
    for path in ("/fr/santenay", "/en/santenay", "/es/santenay", "/nl/santenay"):
        assert f'href="{path}" data-href="{path}"' in page
    assert 'href="/fr/"' not in page and 'data-lang="en" class="lang active"' in page


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


def test_entity_title_shortens_progressively_and_prefers_the_french_alias() -> None:
    from _lib.map_template import _entity_title

    full = _entity_title("Santenay", "AOC (PDO)", "Burgundy", "France", country_code="fr")
    assert full == "Santenay — AOC (PDO) · Burgundy, France · Open Wine Map"
    # Brand goes first…
    assert _entity_title("Cebreros", "Vino de Calidad (PDO)", "Castilla y León", "Spain",
                         country_code="es") == "Cebreros — Vino de Calidad (PDO) · Castilla y León, Spain"
    # …then the term; the region stays.
    assert _entity_title("Lambrusco Grasparossa di Castelvetro", "DOC (AOP)", "Emilia-Romagna",
                         "Italie", country_code="it") == (
        "Lambrusco Grasparossa di Castelvetro — Emilia-Romagna, Italie")
    # A French "X ou Y" register name: the primary alias with everything kept
    # beats the full name with everything cut.
    assert _entity_title("Côte de Nuits-Villages ou Vins fins de la Côte de Nuits", "AOC (PDO)",
                         "Burgundy", "France", country_code="fr") == (
        "Côte de Nuits-Villages — AOC (PDO) · Burgundy, France")
    assert _entity_title("Hermitage ou Ermitage ou l'Hermitage", "AOC (PDO)", "Rhône Valley",
                         "France", country_code="fr") == (
        "Hermitage — AOC (PDO) · Rhône Valley, France · Open Wine Map")
    # " ou " is only an alias separator for France; a bilingual Swiss name is left whole.
    assert _entity_title("Bern / Berne", "AOC", "Trois-Lacs", "Suisse", country_code="ch") == (
        "Bern / Berne — AOC · Trois-Lacs, Suisse · Open Wine Map")
    # Never longer than the cap unless even the bare name exceeds it.
    assert len(_entity_title("Sierras de Las Estancias y Los Filabres", "Vino de la Tierra (PGI)",
                             "España", "Spain", country_code="es")) <= 65
