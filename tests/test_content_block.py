"""Drift / regression guard for the server-rendered appellation content block.

`scripts/_lib/content_block.py` is a Python port of the STABLE subset of the JS
`renderAocCard` pipeline. These self-contained tests pin its HTML output so a
change to one renderer that isn't mirrored in the other is caught here, and
verify the branch behaviours (canonical-bracket show/suppress, sub-denomination
line, stub message, cross-border country chips, verbatim facts, native+Latin
name, the deliberate dulok/menzioni omission, escaping, determinism).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.content_block import RenderCtx, render_content_block  # noqa: E402

# Minimal label catalog — every key content_block.py reads, with fmt
# placeholders ({n}/{doc}/{source}/{umbrella}/{lieu_dit}/{commune}) where used.
_LABELS = {
    "meta_no_region": "—",
    "meta_communes": "{n} commune(s)",
    "meta_communes_inao": "{n} communes (INAO)",
    "dgc_of": "Sub-region of",
    "geom_approx_within": "Approx area — inherited from {umbrella}",
    "geom_approx_parent": "Approx area — parent polygon.",
    "geom_approx_aires": "Approx area — commune envelope.",
    "geom_approx_cadastre": "From lieu-dit «{lieu_dit}» (commune {commune}, {source}).",
    "geom_approx_cadastre_source_label": "cadastre.data.gouv.fr",
    "stub_message": "No {doc} found yet.",
    "stub_help_label": "help us find it",
    "panel_styles_h": "Styles",
    "facet_principal_h": "Principal grapes",
    "facet_accessory_h": "Accessory grapes",
    "panel_observation_h": "Observation grapes",
    "pt_role_disclaimer": "All listed as principal.",
    "panel_facts_h": "Terroir",
    "facts_verbatim_to_verify": "to verify",
    "facts_wiki_marker": "via Wikipedia",
    "facts_sub_facteurs_naturels": "Natural factors",
    "facts_sub_facteurs_humains": "Human factors",
    "facts_sub_produit": "Product",
    "facts_sub_interactions": "Interactions",
    "facts_attribution": "Source: {source}",
    "facts_verbatim_attribution": "Quoted from {source}",
    "facts_attribution_source_label": "the cahier des charges",
    "facts_attribution_source_label_es": "el pliego de condiciones",
    "facts_attribution_source_label_pt": "o caderno de especificações",
    "panel_sources_h": "Sources",
    "src_cahier": "Cahier des charges",
    "src_homologated": "homologated",
    "src_jorf": "JORF",
    "src_show_texte": "INAO text",
    "src_product": "INAO product",
    "src_eur_lex": "EUR-Lex",
    "src_national_pliego": "National pliego",
    "src_national_pliego_added": "varieties added",
    "src_national_spec": "National spec",
    "src_chzo_spec": "CHZO spec",
    "src_regional_register": "Regional register",
    "src_eambrosia": "eAmbrosia",
    "src_eambrosia_id": "file",
    "src_syndicate": "Producer body",
    "fr_marker": "(French)",
    "fr_marker_aria": "Source in French",
    "es_marker": "(Spanish)",
    "es_marker_aria": "Source in Spanish",
    "pt_marker": "(Portuguese)",
    "pt_marker_aria": "Source in Portuguese",
    "translation_source_label": "the cahier des charges",
    "translation_source_label_es": "el pliego de condiciones",
    "translation_source_label_pt": "o caderno de especificações",
    "translation_attribution": "Machine-translated from {source}",
    "entity_nav_children": "Sub-appellations",
}

_GRAPES_INFO = {
    "merlot": {"name": "Merlot", "canonical_name": "Merlot Noir", "vivc_id": 1,
               "vivc_url": "https://vivc.de/1", "page_url": "https://fr.wikipedia.org/wiki/Merlot"},
    "aragonez": {"name": "Aragonez", "canonical_name": "Tempranillo Tinto",
                 "page_url": "https://pt.wikipedia.org/wiki/Tempranillo"},
    "touriga-nacional": {"name": "Touriga Nacional", "canonical_name": "Touriga Nacional"},
    "carignan": {"name": "Carignan"},
}
_STYLES_INFO = {"red": {"extract": "Red wine.", "page_url": "https://en.wikipedia.org/wiki/Red_wine"}}
_STYLE_LABELS = {"red": "red", "white": "white"}
_COUNTRY_LABELS = {"fr": "France", "be": "Belgium", "nl": "Netherlands",
                   "it": "Italy", "pt": "Portugal", "es": "Spain", "gr": "Greece"}
_COUNTRY_FLAG = {"fr": "🇫🇷", "be": "🇧🇪", "nl": "🇳🇱", "it": "🇮🇹",
                 "pt": "🇵🇹", "es": "🇪🇸", "gr": "🇬🇷"}


def _ctx(locale: str = "fr") -> RenderCtx:
    return RenderCtx(
        locale=locale, labels=_LABELS, region_labels={"BORDEAUX": "Bordeaux"},
        country_labels=_COUNTRY_LABELS, country_flag_emoji=_COUNTRY_FLAG,
        grapes_info=_GRAPES_INFO, styles_info=_STYLES_INFO, style_labels=_STYLE_LABELS,
        github_new_issue_url="https://github.com/x/y/issues/new",
    )


def _render(rec: dict, slug: str = "x", locale: str = "fr") -> str:
    return render_content_block(rec, slug, _ctx(locale))


def test_basic_shape_and_sig() -> None:
    out = _render({"name": "Bordeaux", "kind": "AOC", "country": "fr", "region": "BORDEAUX",
                   "geom_source": "parcellaire", "grapes_principal": ["merlot"]})
    assert out.startswith('<article id="ssr-content" class="aoc-card" data-ssr-sig="')
    assert out.endswith("</article>")
    assert "<h1>Bordeaux</h1>" in out
    assert "Bordeaux" in out  # region label resolved
    assert "<h2>Principal grapes</h2>" in out


def test_canonical_bracket_shown_when_distinct() -> None:
    out = _render({"name": "Douro", "kind": "DOP", "country": "pt",
                   "grapes_principal": ["aragonez"], "grape_names": {"aragonez": "Aragonez"}})
    assert "Aragonez <span class=\"canon\">(Tempranillo Tinto)</span>" in out
    assert "All listed as principal." in out  # PT role disclaimer


def test_canonical_bracket_suppressed_when_same_or_colour_only() -> None:
    # "Merlot" vs "Merlot Noir": the colour word is stripped in normalisation,
    # so they're equal -> no bracket. Same for an identical canonical name.
    out = _render({"name": "X", "kind": "AOC", "country": "fr", "grapes_principal": ["merlot"]})
    assert "(Merlot Noir)" not in out
    out2 = _render({"name": "X", "kind": "DOP", "country": "pt",
                    "grapes_principal": ["touriga-nacional"]})
    assert "(Touriga Nacional)" not in out2


def test_sub_denomination_line() -> None:
    out = _render({"name": "Clisson", "kind": "AOC", "country": "fr",
                   "is_sub_denomination": True, "parent_slug": "muscadet", "parent_name": "Muscadet"})
    assert '<div class="dgc-line">Sub-region of <a class="parent-link" data-slug="muscadet" href="#">Muscadet</a></div>' in out


def test_stub_message_uses_country_doc_name() -> None:
    out = _render({"name": "Y", "kind": "DOP", "country": "it", "is_stub": True})
    assert "No <em>disciplinare di produzione</em> found yet." in out
    assert 'class="stub-help"' in out


def test_cross_border_two_country_chips() -> None:
    out = _render({"name": "Maasvallei", "kind": "DOP", "country": "be", "country_aliases": ["nl"]})
    assert "🇧🇪" in out and "🇳🇱" in out
    assert "Belgium" in out and "Netherlands" in out
    assert " · " in out  # chips joined


def test_verbatim_facts_block() -> None:
    out = _render({"name": "Z", "kind": "IGP", "country": "es",
                   "terroir_facts": {"mode": "verbatim", "verbatim_text": "Suelos calcáreos.",
                                     "validation_flag": "short", "cahier_source_pdf_url": "http://x/p.pdf"}})
    assert '<blockquote class="facts-verbatim">Suelos calcáreos.</blockquote>' in out
    assert "verbatim-badge" in out
    assert "el pliego de condiciones" in out  # ES source label


def test_bullet_facts_group_and_wiki_marker_and_suppress_summary() -> None:
    rec = {"name": "B", "kind": "AOC", "country": "fr", "summary": "Should be hidden.",
           "terroir_facts": {"facts": [
               {"bullet": "Granite soils.", "subsection": "facteurs_naturels", "provenance": "cahier"},
               {"bullet": "Long tradition.", "subsection": "facteurs_humains", "provenance": "wiki"}],
               "wiki_source_url": "http://w/x", "cahier_source_pdf_url": "http://c/p.pdf"}}
    out = _render(rec)
    assert "Natural factors" in out and "Human factors" in out
    assert "Granite soils." in out and "Long tradition." in out
    assert 'class="wiki-attr"' in out  # wiki-provenance marker on the wiki bullet
    assert "Should be hidden." not in out  # facts present -> summary suppressed


def test_summary_shown_when_no_facts() -> None:
    out = _render({"name": "S", "kind": "AOC", "country": "fr", "summary": "A short note."})
    assert "<p>A short note." in out


def test_name_with_latin() -> None:
    out = _render({"name": "Мавруд", "kind": "DOP", "country": "gr", "name_latin": "Mavrud"})
    assert '<h1>Мавруд <span class="latin">(Mavrud)</span></h1>' in out


def test_subappellations_section_rendered_when_children_passed() -> None:
    rec = {"name": "Muscadet Sèvre et Maine", "kind": "AOC", "country": "fr"}
    kids = [
        {"name": "Clisson", "path": "/en/clisson", "kind": "AOC"},
        {"name": "Le Pallet", "path": "/en/le-pallet", "kind": "AOC"},
    ]
    out = render_content_block(rec, "muscadet", _ctx("en"), children=kids)
    # FR heading is the regulator's own term, not the generic UI label.
    assert "<h2>Dénominations géographiques complémentaires</h2>" in out
    assert '<ul class="subappellations">' in out
    assert '<li><a href="/en/clisson">Clisson</a> <span class="sub-kind">AOC</span></li>' in out
    assert '<a href="/en/le-pallet">Le Pallet</a>' in out


def test_subappellations_heading_per_country_native_term() -> None:
    kids = [{"name": "X", "path": "/en/x", "kind": "DOP"}]
    cases = {
        "es": "Subzonas",
        "it": "Sottozone",
        "pt": "Sub-regiões",
        "de": "Einzellagen",
    }
    for cc, heading in cases.items():
        out = render_content_block({"name": "P", "kind": "DOP", "country": cc},
                                   "p", _ctx("en"), children=kids)
        assert f"<h2>{heading}</h2>" in out


def test_subappellations_heading_falls_back_to_generic_label() -> None:
    # A country with no clean regulator term (e.g. CH) uses the translated label.
    out = render_content_block({"name": "Vaud", "kind": "AOC", "country": "ch"},
                               "vaud", _ctx("en"),
                               children=[{"name": "La Côte", "path": "/en/la-cote", "kind": "AOC"}])
    assert "<h2>Sub-appellations</h2>" in out  # _LABELS['entity_nav_children']


def test_subappellations_section_absent_without_children() -> None:
    out = _render({"name": "Bordeaux", "kind": "AOC", "country": "fr"})
    assert "subappellations" not in out


def test_subappellations_escapes_name_and_path() -> None:
    kids = [{"name": "<b>X</b>", "path": "/en/a&b", "kind": ""}]
    out = render_content_block({"name": "P", "kind": "AOC", "country": "fr"},
                               "p", _ctx("en"), children=kids)
    assert "<b>X</b>" not in out and "&lt;b&gt;X&lt;/b&gt;" in out
    assert 'href="/en/a&amp;b"' in out


def test_dulok_and_menzioni_omitted() -> None:
    out = _render({"name": "Alto Adige", "kind": "DOP", "country": "it",
                   "menzioni": ["Santa Maddalena", "Terlano"],
                   "dulok": [{"dulo": "X", "telepules": "Y", "aldulok": []}]})
    assert "menzioni" not in out
    assert "dulo" not in out
    assert "Santa Maddalena" not in out


def test_escaping() -> None:
    out = _render({"name": "<script>x</script>", "kind": "AOC", "country": "fr"})
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;" in out


def test_sources_block_branches() -> None:
    out = _render({"name": "F", "kind": "AOC", "country": "fr",
                   "sources": {"boagri": "http://b/p.pdf", "homologation_date": "2024-01-01",
                               "show_texte": "http://inao/t", "id_eambrosia": "EUGI/1",
                               "file_number": "PDO-FR-0001"}})
    assert "<h2>Sources</h2>" in out
    assert "Cahier des charges" in out and "homologated 2024-01-01" in out
    assert "eAmbrosia" in out and "PDO-FR-0001" in out


def test_deterministic_output_and_sig() -> None:
    rec = {"name": "D", "kind": "AOC", "country": "fr", "region": "BORDEAUX",
           "grapes_principal": ["merlot", "aragonez"], "geom_source": "parcellaire"}
    a, b = _render(rec), _render(rec)
    assert a == b  # byte-identical incl. data-ssr-sig


def test_fr_source_marker_only_off_locale() -> None:
    rec = {"name": "M", "kind": "AOC", "country": "fr", "summary": "Texte."}
    assert "(French)" not in _render(rec, locale="fr")  # native locale: no marker
    assert "(French)" in _render(rec, locale="en")      # off-locale: marker shown
