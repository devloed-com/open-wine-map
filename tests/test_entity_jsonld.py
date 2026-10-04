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
    _entity_lead,
    _lang_switcher,
)

_COUNTRY_LABELS = {"fr": "France", "es": "España", "nl": "Nederland"}
_REGION_LABELS = {"PRIORAT": "Priorat"}
_LABELS = {"facet_principal_h": "Principal grapes"}
_GRAPES_INFO = {"garnacha": {"name": "Garnacha"}}
_STYLE_LABELS = {"red": "red", "white": "white", "rose": "rosé"}

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
    translated = {**_RICH, "summary": "Priorat is a prestigious wine zone wine region of Catalonia with schist soils.",
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


def test_meta_description_is_facts_first_then_the_records_own_words() -> None:
    rec = {"name": "Santenay", "kind": "AOC", "class_label": "AOC (PDO)", "country": "fr",
           "region": "PRIORAT", "grapes_principal": ["garnacha"], "styles_simple": ["red", "white"],
           "summary": "Seuls peuvent prétendre à l'appellation…",
           "terroir_facts": {"facts": [
               {"subsection": "facteurs_naturels",
                "bullet": "The Côte de Beaune forms a rectilinear relief of tectonic origin "
                          "extending over approximately 25 kilometres."},
               {"subsection": "facteurs_naturels",
                "bullet": "At Santenay, the Côte curves westward and continues along the left "
                          "bank of the Dheune valley, a river draining the granitic hinterland, "
                          "with slopes that are predominantly south-facing."}]}}
    meta = _build_entity_meta(
        "santenay", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO,
        style_labels=_STYLE_LABELS,
    )
    desc = meta["meta_description"]
    assert desc.startswith(
        "Santenay, Priorat, France · AOC (PDO). White, red — Garnacha. At Santenay, the Côte curves"
    )
    assert len(desc) <= 160 and desc.endswith("…")
    assert "Seuls peuvent" not in desc
    # No styles known: the grapes alone; no lead at all: head + facts only.
    meta = _build_entity_meta(
        "santenay", {**rec, "styles_simple": []}, "en", _LABELS, _REGION_LABELS,
        _COUNTRY_LABELS, _GRAPES_INFO, style_labels=_STYLE_LABELS,
    )
    assert meta["meta_description"].startswith("Santenay, Priorat, France · AOC (PDO). Garnacha. At Santenay")
    bare = {**rec, "terroir_facts": {}}
    meta = _build_entity_meta(
        "santenay", bare, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO,
        style_labels=_STYLE_LABELS,
    )
    assert meta["meta_description"] == "Santenay, Priorat, France · AOC (PDO). White, red — Garnacha."


def test_lead_prefers_a_natural_factors_bullet_that_names_the_record_alone() -> None:
    # Rioja: the first bullets are about the Rioja Alavesa sub-zone ("Rioja"
    # followed by a capitalised word is a sibling's name); the human-factors
    # decree history never leads.
    rec = {"name": "Rioja", "terroir_facts": {"facts": [
        {"subsection": "produit", "bullet": "The wines of Rioja Alavesa are versatile."},
        {"subsection": "facteurs_humains", "bullet": "The Rioja appellation was recognised by decree in 1925."},
        {"subsection": "facteurs_naturels", "bullet": "Sunshine hours in Rioja Alavesa are similar to Rioja Alta."},
        {"subsection": "facteurs_naturels", "bullet": "Clay-limestone soils dominate the northernmost part of the Rioja appellation."},
    ]}}
    assert _entity_lead(rec, "en").startswith("Clay-limestone soils")
    # No standalone mention among the natural bullets → the first natural one.
    rec2 = {"name": "Pauillac", "terroir_facts": {"facts": [
        {"subsection": "facteurs_humains", "bullet": "The ruling of the Lesparre tribunal of 1926 fixed Pauillac."},
        {"subsection": "facteurs_naturels", "bullet": "The geographical area lies in the Gironde department."},
    ]}}
    assert _entity_lead(rec2, "en").startswith("The geographical area lies")


def test_title_ladder_keeps_a_map_word_and_drops_the_scheme_before_it() -> None:
    labels = {**_LABELS, "title_with_map": "{name} wine map"}
    short = {"name": "Mercurey", "class_label": "AOC (PDO)", "country": "fr", "region": "PRIORAT"}
    meta = _build_entity_meta("mercurey", short, "en", labels, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Mercurey — AOC (PDO) · Priorat, France · Open Wine Map"
    long = {**short, "name": "Aglianico del Vulture Superiore", "class_label": "DOCG (PDO)"}
    meta = _build_entity_meta("x", long, "en", labels, _REGION_LABELS, _COUNTRY_LABELS, {})
    # 71 chars with the scheme; the scheme goes before the map word does.
    assert meta["page_title"] == "Aglianico del Vulture Superiore wine map — DOCG · Priorat, France"
    assert len(meta["page_title"]) <= 65
    longer = {**long, "name": "Aglianico del Vulture Superiore riserva speciale"}
    meta = _build_entity_meta("x", longer, "en", labels, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Aglianico del Vulture Superiore riserva speciale wine map"
    # A non-EN locale carries its phrase from the first tier, brand included
    # when it fits, else without the brand.
    fr = {**_LABELS, "title_with_map": "{name}, carte du vignoble"}
    meta = _build_entity_meta("mercurey", short, "fr", fr, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Mercurey, carte du vignoble — AOC (PDO) · Priorat, France"


def test_greek_names_lead_with_the_latin_form_and_the_region_exonym() -> None:
    labels = {**_LABELS, "title_with_map": "{name} wine map"}
    rec = {"name": "Νάουσα", "name_latin": "Naoussa", "class_label": "PDO", "country": "fr",
           "region": "Μακεδονία", "grapes_principal": ["garnacha"],
           "terroir_facts": {"facts": [{"subsection": "facteurs_naturels",
                                       "bullet": "The Naoussa zone sits at 80 to 400 m."}]}}
    meta = _build_entity_meta(
        "naoussa", rec, "en", labels, {}, _COUNTRY_LABELS, _GRAPES_INFO,
        title_regions={"Μακεδονία": "Macedonia"},
    )
    assert meta["page_title"] == "Naoussa (Νάουσα) — PDO · Macedonia, France · Open Wine Map"
    assert meta["meta_description"].startswith("Naoussa (Νάουσα), Macedonia, France · PDO. Garnacha.")
    graph = _parse(meta["jsonld_html"])
    place = _node(graph, "AdministrativeArea")
    assert place["name"] == "Νάουσα" and place["alternateName"] == "Naoussa"
    assert any(c.get("name") == "Macedonia" for c in place["containedInPlace"])


def test_a_region_equal_to_the_country_is_not_printed() -> None:
    rec = {"name": "Pago de Otazu", "class_label": "Vino de Pago (PDO)", "country": "es",
           "region": "España", "grapes_principal": ["garnacha"]}
    meta = _build_entity_meta("pago-de-otazu", rec, "en", _LABELS, {}, _COUNTRY_LABELS, _GRAPES_INFO)
    assert meta["page_title"] == "Pago de Otazu — Vino de Pago (PDO) · España · Open Wine Map"
    assert meta["meta_description"].startswith("Pago de Otazu, España · Vino de Pago (PDO). Garnacha.")
    graph = _parse(meta["jsonld_html"])
    place = _node(graph, "AdministrativeArea")
    contained = place["containedInPlace"]
    contained = contained if isinstance(contained, list) else [contained]
    assert [c["@type"] for c in contained] == ["Country"]


def test_meta_description_names_children_when_the_record_has_no_lead() -> None:
    # /en/schwyz: no facts, no summary, no grapes — indexed only as the parent of
    # Zürichsee. Bing flagged the bare head line (42 chars) as too short.
    rec = {"name": "Schwyz", "kind": "AOC", "class_label": "AOC", "country": "fr",
           "region": "PRIORAT", "grapes_principal": [], "summary": "", "terroir_facts": {}}
    kids = [{"name": "Zürichsee", "path": "/en/zurichsee", "classification": "AOC"}]
    labels = {**_LABELS, "entity_nav_children": "Related denominations"}
    meta = _build_entity_meta(
        "schwyz", rec, "en", labels, _REGION_LABELS, _COUNTRY_LABELS, {}, children=kids
    )
    assert meta["meta_description"] == (
        "Schwyz, Priorat, France · AOC. Related denominations: Zürichsee."
    )
    # With grapes the grape clause still leads; the children follow.
    meta = _build_entity_meta(
        "schwyz", {**rec, "grapes_principal": ["garnacha"]}, "en", labels,
        _REGION_LABELS, _COUNTRY_LABELS, _GRAPES_INFO, children=kids,
    )
    assert meta["meta_description"] == (
        "Schwyz, Priorat, France · AOC. Garnacha. Related denominations: Zürichsee."
    )
    # A lead sentence keeps the old behaviour: children are not appended.
    meta = _build_entity_meta(
        "schwyz", {**rec, "terroir_facts": {"facts": [{"bullet": "Schist soils."}]}}, "en",
        labels, _REGION_LABELS, _COUNTRY_LABELS, {}, children=kids,
    )
    assert "Related denominations" not in meta["meta_description"]


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
    # The branded, scheme-stripped tier comes before any unbranded one.
    assert _entity_title("Côte de Nuits-Villages ou Vins fins de la Côte de Nuits", "AOC (PDO)",
                         "Burgundy", "France", country_code="fr") == (
        "Côte de Nuits-Villages — AOC · Burgundy, France · Open Wine Map")
    assert _entity_title("Hermitage ou Ermitage ou l'Hermitage", "AOC (PDO)", "Rhône Valley",
                         "France", country_code="fr") == (
        "Hermitage — AOC (PDO) · Rhône Valley, France · Open Wine Map")
    # " ou " is only an alias separator for France; a bilingual Swiss name is left whole.
    assert _entity_title("Bern / Berne", "AOC", "Trois-Lacs", "Suisse", country_code="ch") == (
        "Bern / Berne — AOC · Trois-Lacs, Suisse · Open Wine Map")
    # Never longer than the cap unless even the bare name exceeds it.
    assert len(_entity_title("Sierras de Las Estancias y Los Filabres", "Vino de la Tierra (PGI)",
                             "España", "Spain", country_code="es")) <= 65


def test_description_grapes_are_ranked_title_cased_and_latin() -> None:
    rec = {"name": "Rioja", "class_label": "DOCa (PDO)", "country": "es", "region": "La Rioja",
           "grapes_principal": ["alarije", "albillo-mayor", "chardonnay", "tempranillo", "grenache"],
           "grape_names": {"alarije": "alarije", "albillo-mayor": "albillo mayor",
                           "chardonnay": "chardonnay", "tempranillo": "tempranillo",
                           "grenache": "garnacha tinta"},
           "styles_simple": ["red"]}
    # Sort keys as render() builds them: negative for a grape the country
    # knows (more negative = more characteristic), 0 for the rest.
    rank = {"tempranillo": -1.0, "grenache": -0.8, "chardonnay": -0.2}
    meta = _build_entity_meta(
        "rioja", rec, "en", _LABELS, {}, {"es": "Spain"}, {}, style_labels=_STYLE_LABELS,
        grape_rank=rank,
    )
    assert meta["meta_description"] == (
        "Rioja, La Rioja, Spain · DOCa (PDO). Red — Tempranillo, Garnacha Tinta, Chardonnay."
    )
    # A Cyrillic regulator spelling yields to the lexicon's Latin name.
    bg = {"name": "Мелник", "name_latin": "Melnik", "class_label": "PDO", "country": "es",
          "grapes_principal": ["grenache"], "grape_names": {"grenache": "Гренаш"}}
    meta = _build_entity_meta("melnik", bg, "en", _LABELS, {}, {"es": "Spain"},
                              {"grenache": {"name": "Grenache"}})
    assert "Grenache" in meta["meta_description"] and "Гренаш" not in meta["meta_description"]


def test_cider_and_spirit_titles_carry_no_vineyard_map_phrase() -> None:
    fr = {**_LABELS, "title_with_map": "{name}, carte du vignoble"}
    rec = {"name": "Calvados", "class_label": "AOC (IG spiritueux)", "country": "fr",
           "region": "PRIORAT", "is_wine": False}
    meta = _build_entity_meta("calvados", rec, "fr", fr, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Calvados — AOC (IG spiritueux) · Priorat, France · Open Wine Map"
    wine = {**rec, "is_wine": True}
    meta = _build_entity_meta("calvados", wine, "fr", fr, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"].startswith("Calvados, carte du vignoble —")


def test_long_latin_native_names_fall_back_to_the_latin_form_before_losing_the_region() -> None:
    labels = {**_LABELS, "title_with_map": "{name}, wijnkaart"}
    rec = {"name": "Κρασοχώρια Λεμεσού - Λαόνα", "name_latin": "Krasochoria Lemesou - Laona",
           "class_label": "BOB", "country": "fr", "region": "PRIORAT"}
    meta = _build_entity_meta("x", rec, "nl", labels, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Krasochoria Lemesou - Laona, wijnkaart — BOB · Priorat, France"
    assert meta["meta_description"].startswith("Krasochoria Lemesou - Laona (Κρασοχώρια Λεμεσού - Λαόνα), Priorat, France")


def test_description_head_uses_the_french_primary_alias() -> None:
    rec = {"name": "Côte de Nuits-Villages ou Vins fins de la Côte de Nuits", "class_label": "AOC (PDO)",
           "country": "fr", "region": "PRIORAT"}
    meta = _build_entity_meta("x", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {})
    assert meta["meta_description"].startswith("Côte de Nuits-Villages, Priorat, France · AOC (PDO).")
    graph = _parse(meta["jsonld_html"])
    assert _node(graph, "AdministrativeArea")["name"] == rec["name"]


def test_description_grapes_named_by_the_record_lead_in_text_order() -> None:
    rec = {"name": "Pauillac", "class_label": "AOC (PDO)", "country": "fr", "region": "PRIORAT",
           "grapes_principal": ["cabernet-franc", "cabernet-sauvignon", "cot", "merlot"],
           "grape_names": {"cabernet-franc": "cabernet franc", "cabernet-sauvignon": "cabernet-sauvignon",
                           "cot": "cot", "merlot": "merlot"},
           "terroir_facts": {"facts": [{"subsection": "facteurs_humains",
                                       "bullet": "Merlot arrived late; Cabernet-Sauvignon dominates the gravel."}]}}
    rank = {"cot": -40.0, "cabernet-franc": -120.0, "cabernet-sauvignon": -150.0, "merlot": -160.0}
    meta = _build_entity_meta("pauillac", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {},
                              grape_rank=rank)
    assert "Merlot, Cabernet-Sauvignon, Cabernet Franc." in meta["meta_description"]


def test_region_named_after_the_appellation_is_not_repeated() -> None:
    rec = {"name": "Mosel", "class_label": "PDO", "country": "fr", "region": "Mosel",
           "grapes_principal": ["garnacha"]}
    meta = _build_entity_meta("mosel", rec, "en", _LABELS, {"Mosel": "Mosel"}, _COUNTRY_LABELS,
                              _GRAPES_INFO)
    assert meta["page_title"] == "Mosel — PDO · France · Open Wine Map"
    assert meta["meta_description"].startswith("Mosel, France · PDO.")


def test_greek_grape_spelling_without_a_lexicon_name_falls_back_to_the_slug() -> None:
    rec = {"name": "Σαντορίνη", "name_latin": "Santorini", "class_label": "PDO", "country": "fr",
           "grapes_principal": ["assyrtiko", "aidani"],
           "grape_names": {"assyrtiko": "Ασύρτικο Β", "aidani": "Αηδάνι Άσπρο Β"}}
    meta = _build_entity_meta("santorini", rec, "en", _LABELS, {}, _COUNTRY_LABELS,
                              {"assyrtiko": {"name": "Assyrtiko"}})
    assert "Assyrtiko, Aidani." in meta["meta_description"]
    assert "Άσπρο" not in meta["meta_description"]



def test_styles_keep_their_colours_and_read_in_a_fixed_order() -> None:
    rec = {"name": "Mosel", "class_label": "PDO", "country": "fr", "region": "PRIORAT",
           "styles_simple": ["other", "oxidative", "red", "rose", "sparkling", "sweet", "white"]}
    labels = {**_STYLE_LABELS, "sparkling": "sparkling", "sweet": "sweet", "oxidative": "oxidative",
              "other": "other"}
    meta = _build_entity_meta("mosel", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {},
                              style_labels=labels)
    assert "White, red, rosé, sparkling, sweet, oxidative, other." in meta["meta_description"]


def test_grape_mentions_need_word_boundaries() -> None:
    rec = {"name": "X", "class_label": "AOC", "country": "fr", "region": "PRIORAT",
           "grapes_principal": ["cot", "merlot"], "grape_names": {"cot": "cot", "merlot": "merlot"},
           "terroir_facts": {"facts": [{"subsection": "facteurs_naturels",
                                       "bullet": "The coteaux face south; Merlot dominates."}]}}
    meta = _build_entity_meta("x", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {},
                              grape_rank={"merlot": -10.0, "cot": -5.0})
    assert "Merlot, Cot." in meta["meta_description"]


def test_product_comite_and_branded_term_tier_and_lead_budget() -> None:
    rec = {"name": "Rhum de la Martinique", "class_label": "AOC (spirit-drink GI)", "country": "fr",
           "region": "RHUM", "is_wine": False}
    meta = _build_entity_meta("rhum", rec, "en", _LABELS, {"RHUM": "Rum"}, _COUNTRY_LABELS, {})
    # "Rum" is a product, not a place; the branded scheme-stripped tier fits.
    assert meta["page_title"] == "Rhum de la Martinique — AOC · France · Open Wine Map"
    assert "Rum" not in meta["meta_description"]
    long = {"name": "Coteaux du Layon Saint-Lambert-du-Lattay", "class_label": "AOC (PDO)",
            "country": "fr", "region": "PRIORAT", "grapes_principal": ["garnacha"],
            "styles_simple": ["white", "sweet"], "grape_names": {"garnacha": "chenin blanc"},
            "terroir_facts": {"facts": [{"subsection": "facteurs_naturels", "bullet": (
                "The Layon valley cuts through the Armorican schists over a long distance and "
                "the slopes face south.")}]}}
    labels = {**_STYLE_LABELS, "sweet": "sweet"}
    meta = _build_entity_meta("x", long, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {},
                              style_labels=labels)
    d = meta["meta_description"]
    # Enough room: the lead is kept and clamped once, never "……".
    assert d.count("…") <= 1 and "……" not in d


def test_seo_name_with_parentheses_uses_a_slash() -> None:
    from _lib.map_template import seo_display_name
    assert seo_display_name({"name": "Ρετσίνα Χαλκίδας (Ευβοίας)", "name_latin": "Retsina Halkidas (Evias)"}) == (
        "Retsina Halkidas (Evias) / Ρετσίνα Χαλκίδας (Ευβοίας)"
    )
    assert seo_display_name({"name": "Νάουσα", "name_latin": "Naoussa"}) == "Naoussa (Νάουσα)"


def test_description_budget_drops_styles_before_the_lead_and_children_only_without_facts() -> None:
    rec = {"name": "Rioja", "class_label": "DOCa (PDO)", "country": "es", "region": "La Rioja",
           "grapes_principal": ["tempranillo", "grenache", "chardonnay"],
           "grape_names": {"tempranillo": "tempranillo", "grenache": "garnacha tinta", "chardonnay": "chardonnay"},
           "styles_simple": ["white", "red", "rose", "sparkling"],
           "terroir_facts": {"facts": [{"subsection": "facteurs_naturels", "bullet": (
               "The clay-limestone soils found in the northernmost part of the Rioja appellation "
               "are the most suited to ageing.")}]}}
    labels = {**_STYLE_LABELS, "sparkling": "sparkling"}
    kids = [{"name": "Rioja Alta", "path": "/en/rioja-alta", "classification": ""}]
    meta = _build_entity_meta("rioja", rec, "en", _LABELS, {}, {"es": "Spain"}, {},
                              style_labels=labels, children=kids)
    d = meta["meta_description"]
    assert d.startswith("Rioja, La Rioja, Spain · DOCa (PDO). Tempranillo, Garnacha Tinta, Chardonnay. The clay-limestone")
    assert "Related denominations" not in d and "White" not in d


def test_title_keeps_the_term_with_the_country_before_the_country_alone() -> None:
    labels = {**_LABELS, "title_with_map": "{name} wine map"}
    rec = {"name": "Coteaux du Layon Saint-Lambert-du-Lattay", "class_label": "AOC (PDO)",
           "country": "fr", "region": "PRIORAT"}
    meta = _build_entity_meta("x", rec, "en", labels, {"PRIORAT": "Loire Valley"}, _COUNTRY_LABELS, {})
    # The region outlives the country; the term goes first here (70 chars with it).
    assert meta["page_title"] == "Coteaux du Layon Saint-Lambert-du-Lattay wine map — Loire Valley"



def test_self_named_region_or_country_is_dropped_even_through_the_alias() -> None:
    fr = {**_LABELS, "title_with_map": "{name}, carte du vignoble"}
    rec = {"name": "Alsace ou Vin d'Alsace", "class_label": "AOC (PDO)", "country": "fr",
           "region": "ALSACE", "grapes_principal": ["garnacha"]}
    meta = _build_entity_meta("alsace-ou-vin-d-alsace", rec, "en", fr, {"ALSACE": "Alsace"},
                              _COUNTRY_LABELS, _GRAPES_INFO)
    # The full register name still leads the title when it fits; the region
    # that repeats the alias is gone, and the description head uses the alias.
    import html as _html
    assert _html.unescape(meta["page_title"]) == "Alsace ou Vin d'Alsace — AOC (PDO) · France · Open Wine Map"
    assert meta["meta_description"].startswith("Alsace, France · AOC (PDO).")
    kriti = {"name": "Κρήτη", "name_latin": "Kriti", "class_label": "PGI", "country": "fr",
             "region": "Κρήτη"}
    meta = _build_entity_meta("kriti", kriti, "en", _LABELS, {}, _COUNTRY_LABELS, {},
                              title_regions={"Κρήτη": "Crete"})
    assert meta["page_title"] == "Kriti (Κρήτη) — PGI · France · Open Wine Map"
    malta = {"name": "Malta", "class_label": "DOK (PDO)", "country": "es", "region": "Malta"}
    meta = _build_entity_meta("malta", malta, "en", _LABELS, {}, {"es": "Malta"}, {})
    assert meta["page_title"] == "Malta — DOK (PDO) · Open Wine Map"
    assert meta["meta_description"].startswith("Malta · DOK (PDO).")


def test_title_keeps_the_region_over_the_country_and_ends_with_a_branded_bare_name() -> None:
    nl = {**_LABELS, "title_with_map": "{name}, kaart van het wijngebied"}
    rec = {"name": "Chassagne-Montrachet", "class_label": "AOC (BOB)", "country": "fr",
           "region": "PRIORAT"}
    meta = _build_entity_meta("x", rec, "nl", nl, {"PRIORAT": "Bourgogne"}, {"fr": "Frankrijk"}, {})
    assert meta["page_title"] == "Chassagne-Montrachet, kaart van het wijngebied — AOC · Bourgogne"
    long = {**rec, "name": "Alsace grand cru Altenberg de Bergbieten"}
    meta = _build_entity_meta("x", long, "nl", nl, {"PRIORAT": "Elzas"}, {"fr": "Frankrijk"}, {})
    assert meta["page_title"] == "Alsace grand cru Altenberg de Bergbieten · Open Wine Map"


def test_primeur_does_not_paint_a_white_appellation_red_and_synonyms_collapse() -> None:
    rec = {"name": "Muscadet", "class_label": "AOC (PDO)", "country": "fr", "region": "PRIORAT",
           "styles": ["primeur", "white"], "styles_simple": ["red", "white"],
           "grapes_principal": ["nielluccio", "sangiovese", "melon"],
           "grape_names": {"nielluccio": "nielluccio", "sangiovese": "sangiovese", "melon": "melon"}}
    meta = _build_entity_meta("muscadet", rec, "en", _LABELS, _REGION_LABELS, _COUNTRY_LABELS, {},
                              style_labels=_STYLE_LABELS, canon_of={"nielluccio": "sangiovese"})
    d = meta["meta_description"]
    assert "White — Nielluccio, Melon." in d and "Red" not in d
    # Without a cahier spelling the slug's words are used, not a VIVC prime.
    alb = {"name": "Romagna Albana", "class_label": "DOCG", "country": "it", "region": "X",
           "grapes_principal": ["albana"]}
    meta = _build_entity_meta("romagna-albana", alb, "en", _LABELS, {}, {"it": "Italy"},
                              {"albana": {"name": "Forsellina N.", "canonical_name": "Albana Bianca"}})
    assert "Albana." in meta["meta_description"] and "Forsellina" not in meta["meta_description"]


def test_bilingual_swiss_name_does_not_repeat_its_region() -> None:
    rec = {"name": "Valais / Wallis", "class_label": "AOC", "country": "fr", "region": "Valais"}
    meta = _build_entity_meta("valais-wallis", rec, "en", _LABELS, {"Valais": "Valais"}, _COUNTRY_LABELS, {})
    assert meta["page_title"] == "Valais / Wallis — AOC · France · Open Wine Map"

