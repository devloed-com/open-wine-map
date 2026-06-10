"""HTML template for the appellation map.

Kept here (rather than inlined in stage 04) so the template is editable
without ploughing through generator code. The template uses Python str
.format with `{var}` substitution; CSS and JS curly-braces are doubled.

UI chrome (sidebar labels, panel headings, link texts, style-chip names) is
translated via gettext — `build_labels` and `build_style_labels` are the
extraction surface for `pybabel extract`. Per-AOC content (commune lists,
grape names, region names, summary text) stays French — it is verbatim cahier
data and translating it would break the public-sources rule in CLAUDE.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from _lib.content_block import RenderCtx, esc, render_content_block
from _lib.i18n import load_translations
from _lib.wikidata import wikidata_url


def build_style_labels(_: Callable[[str], str]) -> dict[str, str]:
    """Style-tag → translatable label. Sourced from the canonical taxonomy
    in scripts/_lib/style_taxonomy so new tags get a label entry
    automatically. msgid is the FR form (project convention)."""
    from .style_taxonomy import build_style_labels as taxonomy_build_style_labels
    return taxonomy_build_style_labels(_)


def build_labels(_: Callable[[str], str]) -> dict[str, str]:
    """All translatable UI strings for the map. msgid is the French source."""
    return {
        "page_title": _("Open Wine Map — carte des appellations"),
        "subtitle": _("carte des appellations viticoles"),
        "meta_description": _(
            "Carte interactive des appellations viticoles européennes "
            "(AOC, AOP, IGP, DOP) — communes, cépages, styles et liens au "
            "terroir, à partir des données publiques des registres "
            "officiels (INAO, EUR-Lex, eAmbrosia) et de l'IGN."
        ),
        "loading": _("Chargement…"),
        "search_h": _("Recherche"),
        "search_placeholder": _("nom d'appellation…"),
        "search_appellation_placeholder": _("Recherche d'appellation…"),
        "search_grape_placeholder": _("Recherche de cépage…"),
        "active_filters_aria": _("Filtres actifs"),
        "select_all_aria": _("Tout sélectionner"),
        "open_appellation_aria": _("Ouvrir la fiche de {name}"),
        "open_appellation_title": _("Ouvrir la fiche"),
        "show_spirits_label": _("Inclure les spiritueux"),
        "facet_styles_h": _("Style de vin"),
        "facet_principal_h": _("Cépages principaux"),
        "facet_accessory_h": _("Cépages accessoires"),
        "facet_grapes_h": _("Cépages"),
        "facet_regions_h": _("Région"),
        "facet_appellations_h": _("Appellation"),
        "facet_kind_h": _("Type"),
        "kind_aoc": _("AOC / AOP"),
        "kind_igp": _("IGP"),
        "view_mode_h": _("Vue"),
        "view_mode_simple": _("Simple"),
        "view_mode_advanced": _("Avancée"),
        "theme_h": _("Thème"),
        "theme_light": _("Clair"),
        "theme_dark": _("Sombre"),
        "theme_system": _("Système"),
        "show_igp_label": _("Afficher les IGP"),
        "style_simple_red": _("rouge"),
        "style_simple_white": _("blanc"),
        "style_simple_rose": _("rosé"),
        "style_simple_sparkling": _("mousseux"),
        "style_simple_sweet": _("moelleux / liquoreux"),
        "style_simple_other": _("autre"),
        "reset": _("Réinitialiser"),
        "count_total": _("{n} appellations"),
        "count_filtered": _("{n} / {total} appellations"),
        "count_hidden_igp_hint": _("{n} dans IGP masquées — afficher"),
        "close_aria": _("Fermer"),
        "panel_aria": _("Détails de l'appellation"),
        "remove_filter_aria": _("Retirer le filtre {label}"),
        "sidebar_aria": _("Filtres et options de la carte"),
        "lang_switcher_aria": _("Langue"),
        "map_aria": _("Carte des appellations viticoles"),
        "skip_to_map": _("Aller à la carte"),
        "panel_styles_h": _("Styles"),
        "panel_observation_h": _("Variétés d'intérêt"),
        "panel_sources_h": _("Sources"),
        "panel_facts_h": _("Terroir"),
        "panel_dulok_h": _("Dűlők (lieux-dits) : {n}"),
        "panel_menzioni_h": _("Menzioni geografiche aggiuntive (crus) : {n}"),
        "facts_sub_facteurs_naturels": _("Facteurs naturels"),
        "facts_sub_facteurs_humains": _("Facteurs humains"),
        "facts_sub_produit": _("Caractéristiques du produit"),
        "facts_sub_interactions": _("Lien terroir / vin"),
        "facts_attribution": _(
            "Faits dégagés du Lien au terroir par interprétation automatique — voir la {source}."
        ),
        "facts_attribution_source_label": _("source"),
        "facts_wiki_marker": _("via Wikipedia · CC BY-SA 4.0"),
        "facts_verbatim_attribution": _(
            "Citation textuelle du Lien au terroir — voir la {source}."
        ),
        "facts_verbatim_to_verify": _("à vérifier — texte source court"),
        "meta_no_region": _("sans région"),
        "meta_communes_inao": _("{n} commune(s) INAO"),
        "meta_communes": _("{n} commune(s)"),
        "meta_geom_approx": _("aire approchée"),
        "meta_geom_approx_communal": _("aire approchée (à l'échelle communale)"),
        "geom_approx_within": _(
            "Aire approchée — pas de données parcellaires précises pour cette dénomination ; "
            "polygone hérité de {umbrella}."
        ),
        "geom_approx_parent": _(
            "Aire approchée — pas de données parcellaires précises pour cette dénomination ; "
            "polygone hérité de l'appellation parente."
        ),
        "geom_approx_aires": _(
            "Aire approchée — pas de données parcellaires disponibles ; "
            "affichée comme l'emprise de la commune où se situe la dénomination."
        ),
        "geom_approx_cadastre": _(
            "Aire issue du lieu-dit cadastral « {lieu_dit} » "
            "(commune de {commune}, {source})."
        ),
        "geom_approx_cadastre_source_label": _("cadastre.data.gouv.fr"),
        "stack_header": _("{n} appellations à ce point"),
        "stack_cycle_hint": _("Cliquer à nouveau pour parcourir les autres"),
        "src_cahier": _("Cahier des charges (BO Agri, PDF)"),
        "src_homologated": _("homologué"),
        "src_jorf": _("JORF"),
        "src_show_texte": _("Texte officiel INAO (show_texte)"),
        "src_product": _("Fiche produit INAO"),
        "src_syndicate": _("Site officiel de l'interprofession"),
        "src_eur_lex": _("Pliego de condiciones (EUR-Lex, documento único)"),
        "src_national_pliego": _("Pliego de condiciones (national, PDF)"),
        "src_national_pliego_added": _("variétés ajoutées"),
        "src_national_spec": _("Cahier des charges national (PDF)"),
        "src_chzo_spec": _("Spécification du produit (IGP, PDF)"),
        "src_regional_register": _("Registre régional des cépages (PDF)"),
        "src_eambrosia": _("Registre eAmbrosia (UE)"),
        "src_eambrosia_id": _("Numéro de dossier"),
        "legend_h": _("Légende couleurs"),
        "legend_bassin_h": _("Bassin viticole"),
        "legend_area_hint": _("Plus l'aire est petite, plus la teinte est dense."),
        "legend_grapes_h": _("Cépages"),
        "legend_principal": _("principal — variété de la cuvée"),
        "legend_accessory": _("accessoire — assemblage limité"),
        "legend_observation": _("intérêt — observation/conservation"),
        "pt_role_disclaimer": _(
            "Le régulateur portugais (IVV) n'établit pas de distinction principal/accessoire — "
            "toutes les castas autorisées sont listées ensemble dans le caderno de especificações."
        ),
        "bianchello_note": _(
            "Bianchello (ou Biancame) est traité ici comme un cépage distinct, conformément "
            "au disciplinare de la DOP Bianchello del Metauro ; le catalogue VIVC le recense "
            "comme synonyme du Trebbiano Toscano."
        ),
        "stub_message": _(
            "Open Wine Map n'a pas encore trouvé de {doc} pour cette appellation."
        ),
        "stub_help_label": _("aidez-nous à le trouver"),
        "fr_marker": _("(français)"),
        "fr_marker_aria": _("Texte source en français"),
        "es_marker": _("(español)"),
        "es_marker_aria": _("Texte source en espagnol"),
        "pt_marker": _("(português)"),
        "pt_marker_aria": _("Texte source en portugais"),
        "sidebar_toggle_aria": _("Filtres"),
        "tooltip_translated_from": _("Traduit de {wiki} · CC BY-SA 4.0"),
        "wiki_lang_en": _("Wikipédia en anglais"),
        "wiki_lang_fr": _("Wikipédia en français"),
        "wiki_lang_es": _("Wikipédia en espagnol"),
        "wiki_lang_nl": _("Wikipédia en néerlandais"),
        "wiki_lang_pt": _("Wikipédia en portugais"),
        "wiki_lang_hr": _("Wikipédia en croate"),
        "vivc_link_title": _("Vitis International Variety Catalogue (Julius Kühn-Institut)"),
        "vivc_link_label": _("VIVC #{id}"),
        "translation_attribution": _("Traduction automatique depuis {source}"),
        "translation_source_label": _("le cahier des charges"),
        "translation_source_label_es": _("le pliego de condiciones"),
        "translation_source_label_pt": _("le caderno de especificações"),
        "facts_attribution_source_label_es": _("le pliego de condiciones"),
        "facts_attribution_source_label_pt": _("le caderno de especificações"),
        "dgc_of": _("Dénomination géographique complémentaire de"),
        "about_link_label": _("À propos"),
        "about_h": _("À propos d'Open Wine Map"),
        "about_lead_html": _(
            "Carte de référence des appellations viticoles "
            "(AOC, AOP, IGP, DOP), générée automatiquement à partir des "
            "données publiques."
        ),
        "about_made_by_html": _("Réalisé avec ♡ par {devloed}."),
        "about_data_html": _(
            "Sources : INAO ({inao}) pour les cahiers des charges et les "
            "aires parcellaires, IGN ({ign}) pour le fond cartographique, "
            "Wikipedia ({wikipedia}) pour quelques compléments narratifs "
            "(CC BY-SA 4.0), VIVC ({vivc}) — Vitis International Variety "
            "Catalogue, Julius Kühn-Institut — pour les noms canoniques "
            "et numéros de cépage (citation Röckel et al.). Tout extrait "
            "Wikipedia est signalé sur place. Détails et licences dans le "
            "{readme}."
        ),
        "about_contrib_html": _("Suggestions et pull requests bienvenues sur {github}."),
        "feedback_issue_label": _("ticket GitHub"),
        "feedback_email_label": _("e-mail"),
        "feedback_copied_label": _("E-mail copié dans le presse-papiers"),
        "sidebar_disclaimer_html": _(
            "Carte générée automatiquement — des erreurs sont possibles. "
            "Signalez-les via {issue} ou {email}."
        ),
        "about_roadmap_html": _(
            "20 pays européens cartographiés : France, Espagne, Portugal, "
            "Italie, Autriche, Allemagne, Suisse, Slovénie, Croatie, "
            "Hongrie, Roumanie, Bulgarie, Grèce, Slovaquie, Tchéquie, "
            "Luxembourg, Belgique, Pays-Bas, Malte et Chypre. Des "
            "itérations supplémentaires viendront affiner la qualité des "
            "données. La couverture sera étendue au-delà de l'UE et de "
            "la Suisse, ainsi qu'aux classifications hors AOP."
        ),
    }


def build_region_labels(_: Callable[[str], str]) -> dict[str, str]:
    """Bassin (comité régional INAO) → translatable display label.

    The msgid is the FR canonical name as it appears in
    `record.comite_regional` (matches `raw/inao/cahier-extracted/*.json`).
    Public source: INAO comités régionaux list — see
    https://www.inao.gouv.fr/eng/Our-organisation (INAO regional committees).
    A future translator should consult that page; the FR strings here are
    verbatim from the cahier extraction so the join key stays exact.
    """
    return {
        "BOURGOGNE": _("BOURGOGNE"),
        "BEAUJOLAIS": _("BEAUJOLAIS"),
        "JURA": _("JURA"),
        "SAVOIE": _("SAVOIE"),
        "BUGEY": _("BUGEY"),
        "ALSACE ET EST": _("ALSACE ET EST"),
        "VAL DE LOIRE": _("VAL DE LOIRE"),
        "SUD-OUEST": _("SUD-OUEST"),
        "VALLEE DU RHÔNE": _("VALLEE DU RHÔNE"),
        "LANGUEDOC-ROUSSILLON": _("LANGUEDOC-ROUSSILLON"),
        "TOULOUSE-PYRENEES": _("TOULOUSE-PYRENEES"),
        "PROVENCE-CORSE": _("PROVENCE-CORSE"),
        "CHAMPAGNE": _("CHAMPAGNE"),
        "EAUX-DE-VIE DE CIDRE": _("EAUX-DE-VIE DE CIDRE"),
        "VIN DOUX NATURELS": _("VIN DOUX NATURELS"),
        "COGNAC": _("COGNAC"),
        "ARMAGNAC": _("ARMAGNAC"),
        "RHUM": _("RHUM"),
    }


# Country code → flag emoji (Unicode regional-indicator pair). Every
# country code that appears in `record.country` across the corpus has
# a flag — rendered in the panel meta line ahead of the kind. Country
# flag emojis are RGI and render reliably on every modern platform.
_COUNTRY_FLAG_EMOJI: dict[str, str] = {
    "fr": "\U0001F1EB\U0001F1F7",  # 🇫🇷
    "es": "\U0001F1EA\U0001F1F8",  # 🇪🇸
    "pt": "\U0001F1F5\U0001F1F9",  # 🇵🇹
    "it": "\U0001F1EE\U0001F1F9",  # 🇮🇹
    "at": "\U0001F1E6\U0001F1F9",  # 🇦🇹
    "si": "\U0001F1F8\U0001F1EE",  # 🇸🇮
    "hr": "\U0001F1ED\U0001F1F7",  # 🇭🇷
    "hu": "\U0001F1ED\U0001F1FA",  # 🇭🇺
    "ro": "\U0001F1F7\U0001F1F4",  # 🇷🇴
    "bg": "\U0001F1E7\U0001F1EC",  # 🇧🇬
    "gr": "\U0001F1EC\U0001F1F7",  # 🇬🇷
    "de": "\U0001F1E9\U0001F1EA",  # 🇩🇪
    "sk": "\U0001F1F8\U0001F1F0",  # 🇸🇰
    "ch": "\U0001F1E8\U0001F1ED",  # 🇨🇭
    "cz": "\U0001F1E8\U0001F1FF",  # 🇨🇿
    "lu": "\U0001F1F1\U0001F1FA",  # 🇱🇺
    "be": "\U0001F1E7\U0001F1EA",  # 🇧🇪
    "nl": "\U0001F1F3\U0001F1F1",  # 🇳🇱
    "mt": "\U0001F1F2\U0001F1F9",  # 🇲🇹
    "cy": "\U0001F1E8\U0001F1FE",  # 🇨🇾
}


def build_country_labels(_: Callable[[str], str]) -> dict[str, str]:
    """Country code → translatable country name. msgid is the FR form
    (project convention — FR is the gettext source language). Surfaced
    in the panel meta line next to the country flag emoji so users
    unfamiliar with European borders can identify a record's jurisdiction
    without needing to recognise the appellation by name."""
    return {
        "fr": _("France"),
        "es": _("Espagne"),
        "pt": _("Portugal"),
        "it": _("Italie"),
        "at": _("Autriche"),
        "si": _("Slovénie"),
        "hr": _("Croatie"),
        "hu": _("Hongrie"),
        "ro": _("Roumanie"),
        "bg": _("Bulgarie"),
        "gr": _("Grèce"),
        "de": _("Allemagne"),
        "sk": _("Slovaquie"),
        "ch": _("Suisse"),
        "cz": _("Tchéquie"),
        "lu": _("Luxembourg"),
        "be": _("Belgique"),
        "nl": _("Pays-Bas"),
        "mt": _("Malte"),
        "cy": _("Chypre"),
    }


# Region underlay colour, keyed by the value written to the MVT `region`
# property: FR wine region (ALL-CAPS — INAO bassin name, except that the
# BOURGOGNE bassin is split by `derive_fr_wine_region` into BOURGOGNE /
# BEAUJOLAIS / JURA / SAVOIE / BUGEY) or ES Comunidad Autónoma (canonical
# Spanish, mixed case). The two key spaces are disjoint so a single match
# expression serves both countries.
#
# Hand-picked muted palette (Set3-derived) so wine regions are
# distinguishable on a CartoDB Voyager basemap and survive a
# deuteranopia/protanopia simulation. Adjacent regions along the Pyrenees
# (FR SUD-OUEST / LANGUEDOC-ROUSSILLON vs ES Navarra / País Vasco / Aragón
# / Cataluña) are checked for contrast.
#
# Omitted (fall through to transparent):
#   - FR spirit-only bassins (COGNAC, ARMAGNAC, RHUM, EAUX-DE-VIE DE CIDRE)
#     — the underlay shouldn't tint regions whose appellations are non-wine.
#   - ES "España" (fallback for wines whose pliego doesn't yield a CCAA)
#     and "" (explicit multi-region: Cava, Castilla) — these wines are
#     scattered nationwide; tinting them would produce splotchy noise.
_BASSIN_COLOURS: dict[str, str] = {
    # France — wine regions
    "BOURGOGNE": "#fdb462",
    "BEAUJOLAIS": "#bc80bd",
    "JURA": "#ffffb3",
    "SAVOIE": "#b7d9e8",
    "BUGEY": "#e8c89f",
    "ALSACE ET EST": "#80b1d3",
    "VAL DE LOIRE": "#b3de69",
    "SUD-OUEST": "#fb8072",
    "VALLEE DU RHÔNE": "#bebada",
    "LANGUEDOC-ROUSSILLON": "#ffed6f",
    "TOULOUSE-PYRENEES": "#ccebc5",
    "PROVENCE-CORSE": "#fccde5",
    "CHAMPAGNE": "#d9d9d9",
    "VIN DOUX NATURELS": "#8dd3c7",
    # Spain — Comunidades Autónomas
    "Galicia":              "#a6c5d8",
    "Asturias":             "#b3e2cd",
    "Cantabria":            "#a2d4b0",
    "País Vasco":           "#cbd5e8",
    "Navarra":              "#d5b9d8",
    "La Rioja":             "#fbb4ae",
    "Aragón":               "#fed9a6",
    "Cataluña":             "#f4cae4",
    "Comunidad Valenciana": "#ffe5a0",
    "Murcia":               "#fdcdac",
    "Madrid":               "#d8d0e8",
    "Castilla y León":      "#f0e090",
    "Castilla-La Mancha":   "#e5cca8",
    "Extremadura":          "#cce6a8",
    "Andalucía":            "#f0a890",
    "Baleares":             "#a8d8d4",
    "Canarias":             "#c8e0a8",
    # Portugal — wine regions (IVV nomenclature)
    "Minho":                "#b3d8e0",
    "Trás-os-Montes":       "#d4b8a8",
    "Douro/Porto":          "#e8a880",
    "Bairrada":             "#c8d4a0",
    "Dão":                  "#d8c0a0",
    "Beira Interior":       "#cccca8",
    "Lisboa":               "#e0c8d8",
    "Tejo":                 "#d8e0a8",
    "Setúbal":              "#c8b8d0",
    "Alentejo":             "#e8d8a8",
    "Algarve":              "#f0c8a8",
    "Madeira":              "#a8d4c0",
    "Açores":               "#c0d8d8",
}


_SITE_BASE_URL = "https://www.openwinemap.com"
_OG_LOCALES = {"fr": "fr_FR", "en": "en_US", "es": "es_ES", "nl": "nl_NL"}
_GITHUB_URL = "https://github.com/devloed-com/open-wine-map"
_GITHUB_NEW_ISSUE_URL = _GITHUB_URL + "/issues/new"
_DEVLOED_URL = "https://devloed.com"
_INAO_URL = "https://www.inao.gouv.fr/"
_IGN_URL = "https://www.ign.fr/"
_WIKIPEDIA_URL = "https://fr.wikipedia.org/"
_VIVC_URL = "https://www.vivc.de/"
_FEEDBACK_USER = "winemap+feedback"
_FEEDBACK_DOMAIN = "devloed.com"


def _ext_link(url: str, label: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'


def _feedback_email_anchor(label: str) -> str:
    return (
        f'<a href="#" class="feedback-mail" '
        f'data-u="{_FEEDBACK_USER}" data-d="{_FEEDBACK_DOMAIN}">{label}</a>'
    )


def _build_sidebar_disclaimer(labels: dict[str, str]) -> str:
    issue = _ext_link(_GITHUB_NEW_ISSUE_URL, labels["feedback_issue_label"])
    email = _feedback_email_anchor(labels["feedback_email_label"])
    return (
        f'<div id="sidebar-disclaimer">'
        f'{labels["sidebar_disclaimer_html"].format(issue=issue, email=email)}'
        f'</div>'
    )


def _build_about_dialog(labels: dict[str, str]) -> str:
    devloed = _ext_link(_DEVLOED_URL, "devloed.com")
    github = _ext_link(_GITHUB_URL, "GitHub")
    inao = _ext_link(_INAO_URL, "INAO")
    ign = _ext_link(_IGN_URL, "IGN")
    wikipedia = _ext_link(_WIKIPEDIA_URL, "fr.wikipedia.org")
    vivc = _ext_link(_VIVC_URL, "vivc.de")
    readme = _ext_link(_GITHUB_URL + "#public-data-sources", "README")
    paragraphs = [
        labels["about_lead_html"],
        labels["about_made_by_html"].format(devloed=devloed),
        labels["about_data_html"].format(
            inao=inao, ign=ign, wikipedia=wikipedia, vivc=vivc, readme=readme
        ),
        labels["about_roadmap_html"],
        labels["about_contrib_html"].format(github=github),
    ]
    body = "\n      ".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        f'<dialog id="about-dialog" aria-labelledby="about-dialog-h">\n'
        f'  <button class="close" type="button" aria-label="{labels["close_aria"]}">×</button>\n'
        f'  <div class="about-body">\n'
        f'    <h2 id="about-dialog-h">{labels["about_h"]}</h2>\n'
        f"      {body}\n"
        f'  </div>\n'
        f'</dialog>'
    )


_LOCALES_DISPLAY = (("fr", "FR"), ("en", "EN"), ("es", "ES"), ("nl", "NL"))


def _lang_switcher(active: str, aria_label: str) -> str:
    parts = []
    for code, label in _LOCALES_DISPLAY:
        path = "/" if code == "en" else f"/{code}/"
        is_active = code == active
        cls = " active" if is_active else ""
        current_attr = ' aria-current="page"' if is_active else ""
        parts.append(
            f'<a href="{path}" data-href="{path}" data-lang="{code}" '
            f'class="lang{cls}"{current_attr}>{label}</a>'
        )
    return f'<nav id="lang-switcher" aria-label="{aria_label}">' + "".join(parts) + "</nav>"


def _bassin_match_expr() -> str:
    """MapLibre `match` expression mapping `region` → fill colour. Default
    is fully transparent so AOCs with empty `comite_regional` get no underlay."""
    parts = ["['match', ['get', 'region']"]
    for region, colour in _BASSIN_COLOURS.items():
        parts.append(f"        '{region}', '{colour}'")
    parts.append("        'rgba(0,0,0,0)']")
    return ",\n".join(parts)


def _build_source_block(
    *,
    layer_url: str,
    villages_layer_url: str,
    source_type: str,
    area_q1: float,
    area_q3: float,
) -> str:
    """Build the JS that adds appellation sources (detailed + villages) and
    twin fill/outline layers. The mode toggle on the client flips visibility
    between the two sets of layers; the bassin underlay is shared.
    """
    bassin_expr = _bassin_match_expr()

    def _layer_block(suffix: str, source_id: str, layer_meta: str, *, with_bassin: bool) -> str:
        bassin = ""
        if with_bassin:
            bassin = (
                "    map.addLayer({\n"
                f"      id: 'appellations-bassin{suffix}', type: 'fill', source: '{source_id}',\n"
                + layer_meta
                + "      paint: {\n"
                + f"        'fill-color': {bassin_expr},\n"
                + "        'fill-opacity': [\n"
                + "          'interpolate', ['linear'], ['zoom'],\n"
                + "          5, 0.35,\n"
                + "          8, 0.0\n"
                + "        ],\n"
                + "        'fill-outline-color': 'rgba(0,0,0,0)'\n"
                + "      }\n"
                + "    });\n"
            )
        return (
            bassin
            + "    map.addLayer({\n"
            + f"      id: 'appellations-fill{suffix}', type: 'fill', source: '{source_id}',\n"
            + layer_meta
            # Smaller polygons (DGCs, lieux-dits, grand crus) must render
            # on top of their containing parent so the user can see them.
            # MapLibre's fill-sort-key sorts ascending; -area makes the
            # smallest polygon get the highest sort key (drawn last/on top).
            + "      layout: {\n"
            + "        'fill-sort-key': ['-', 0, ['get', 'area']]\n"
            + "      },\n"
            + "      paint: {\n"
            + "        'fill-color': [\n"
            + "          'case',\n"
            + "          ['==', ['get', 'kind'], 'IGP'], '#6e7546',\n"
            + "          '#934050'\n"
            + "        ],\n"
            + "        'fill-opacity': [\n"
            + "          'case',\n"
            + "          ['boolean', ['feature-state', 'selected'], false], 0.60,\n"
            + "          ['interpolate', ['linear'], ['get', 'area'],\n"
            + f"            {area_q1}, 0.50,\n"
            + f"            {area_q3}, 0.20]\n"
            + "        ]\n"
            + "      }\n"
            + "    });\n"
            # Halo line drawn under the outline so the cream selection stroke
            # has a dark edge against the cream basemap. Width 0 / fully
            # transparent unless `selected` feature-state is set.
            + "    map.addLayer({\n"
            + f"      id: 'appellations-halo{suffix}', type: 'line', source: '{source_id}',\n"
            + layer_meta
            + "      layout: {\n"
            + "        'line-sort-key': ['-', 0, ['get', 'area']],\n"
            + "        'line-join': 'round'\n"
            + "      },\n"
            + "      paint: {\n"
            + "        'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#1a0810', 'rgba(0,0,0,0)'],\n"
            + "        'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 4.5, 0],\n"
            + "        'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, 0]\n"
            + "      }\n"
            + "    });\n"
            + "    map.addLayer({\n"
            + f"      id: 'appellations-outline{suffix}', type: 'line', source: '{source_id}',\n"
            + layer_meta
            + "      layout: {\n"
            + "        'line-sort-key': ['-', 0, ['get', 'area']]\n"
            + "      },\n"
            + "      paint: {\n"
            + "        'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#fff8e8', '#2a1014'],\n"
            + "        'line-width': [\n"
            + "          'case',\n"
            + "          ['boolean', ['feature-state', 'selected'], false], 2.5,\n"
            + "          ['interpolate', ['linear'], ['get', 'area'],\n"
            + f"            {area_q1}, 1.2,\n"
            + f"            {area_q3}, 0.3]\n"
            + "        ]\n"
            + "      }\n"
            + "    });\n"
        )

    if source_type == "pmtiles":
        adv_decl = (
            "    map.addSource('appellations', {\n"
            "      type: 'vector',\n"
            f"      url: 'pmtiles://{layer_url}',\n"
            "      promoteId: 'slug',\n"
            "    });\n"
        )
        vil_decl = (
            "    map.addSource('appellations-villages', {\n"
            "      type: 'vector',\n"
            f"      url: 'pmtiles://{villages_layer_url}',\n"
            "      promoteId: 'slug',\n"
            "    });\n"
        )
        layer_meta = "      'source-layer': 'appellations',\n"
    else:
        adv_decl = (
            "    map.addSource('appellations', {\n"
            "      type: 'geojson',\n"
            f"      data: '{layer_url}',\n"
            "      promoteId: 'slug'\n"
            "    });\n"
        )
        vil_decl = (
            "    map.addSource('appellations-villages', {\n"
            "      type: 'geojson',\n"
            f"      data: '{villages_layer_url}',\n"
            "      promoteId: 'slug'\n"
            "    });\n"
        )
        layer_meta = ""

    return (
        adv_decl
        + vil_decl
        # Villages layers are added first so advanced overlays cleanly when
        # toggled on. The bassin underlay is shared across modes; we only
        # add it once (to the villages source — visibility unaffected by
        # which appellation layer is active because bassin is a fill of
        # `region` polygons, not appellation outlines).
        + _layer_block("-villages", "appellations-villages", layer_meta, with_bassin=True)
        + _layer_block("", "appellations", layer_meta, with_bassin=False)
    )


_GRAPE_ALIAS_REVERSE_CACHE: dict[str, list[str]] | None = None


def _grape_alias_reverse() -> dict[str, list[str]]:
    """Build `canonical_slug → [GRAPE_ALIAS source keys]` from the curated
    alias map. Used by `_build_grape_search_index` to surface every
    regulator spelling that collapsed into a canonical slug at extraction
    time (Garnacha → Grenache, Lladoner → Grenache, …) so the chip-filter
    search box can match any of them."""
    global _GRAPE_ALIAS_REVERSE_CACHE  # noqa: PLW0603
    if _GRAPE_ALIAS_REVERSE_CACHE is not None:
        return _GRAPE_ALIAS_REVERSE_CACHE
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _lib.grape_lexicon import GRAPE_ALIAS  # noqa: PLC0415
    out: dict[str, list[str]] = {}
    for src, tgt in GRAPE_ALIAS.items():
        out.setdefault(tgt, []).append(src)
    _GRAPE_ALIAS_REVERSE_CACHE = out
    return out


_LOCALE_COUNTRY = {"fr": "FRANCE", "es": "SPAIN", "pt": "PORTUGAL", "nl": "", "en": ""}
_VIVC_SYNONYM_CAP = 10


def _vivc_synonym_names(vivc_rec: dict | None, locale: str) -> list[str]:
    """Top-N VIVC synonym names for one canonical, sorted so synonyms
    flagged as `official_in` the locale's country come first. Capped to
    keep per-locale payload bounded — Grenache alone has ~600 entries."""
    if not vivc_rec:
        return []
    syns = vivc_rec.get("synonyms") or []
    country = _LOCALE_COUNTRY.get(locale, "")

    def rank(syn: dict) -> tuple[int, str]:
        official = (syn.get("official_in") or "").upper()
        priority = 0 if country and country in official else 1
        return (priority, syn.get("name", ""))

    ranked = sorted(syns, key=rank)[:_VIVC_SYNONYM_CAP]
    return [s["name"].title() for s in ranked if s.get("name")]


def _build_canonical_counts(
    aocs: dict, slug_to_canonical: dict[str, str],
) -> dict[str, dict[str, int]]:
    """Per-field vivc-aggregated AOC counts: `{field → {canon_slug → n}}`
    for `grapes_all` / `grapes_principal` / `grapes_accessory`."""
    sinks: dict[str, dict[str, int]] = {
        "all": {}, "principal": {}, "accessory": {},
    }
    fields = (
        ("grapes_all", sinks["all"]),
        ("grapes_principal", sinks["principal"]),
        ("grapes_accessory", sinks["accessory"]),
    )
    for rec in (aocs or {}).values():
        for field, sink in fields:
            canons = {slug_to_canonical.get(s, s) for s in rec.get(field) or []}
            for c in canons:
                sink[c] = sink.get(c, 0) + 1
    return sinks


def _collect_aliases(
    *, canon: str, siblings: list[str], label: str, grapes_info: dict,
    vivc_by_slug: dict, locale: str, alias_reverse: dict[str, list[str]],
) -> list[str]:
    """Deduped union of sibling cahier names + GRAPE_ALIAS reverse-keys
    folding into this canonical or any of its siblings + top-N VIVC
    synonyms ranked by locale relevance. Skips entries that equal the
    primary label (case-insensitive)."""
    label_norm = label.casefold()
    aliases: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        norm = (name or "").strip()
        if not norm:
            return
        key = norm.casefold()
        if key in seen or key == label_norm:
            return
        seen.add(key)
        aliases.append(norm)

    for sib in siblings:
        sib_info = grapes_info.get(sib) or {}
        _add(sib_info.get("name") or sib.replace("-", " "))
    for target in [canon, *siblings]:
        for src in alias_reverse.get(target, []):
            _add(src.replace("-", " "))
    for syn in _vivc_synonym_names(vivc_by_slug.get(canon), locale):
        _add(syn)
    return aliases


def _build_grape_search_index(
    *, grapes_info: dict, aocs: dict, vivc_by_slug: dict,
    vivc_groups: dict[int, list[str]], slug_to_canonical: dict[str, str],
    locale: str,
) -> list[dict]:
    """One entry per canonical slug, carrying `slug`, `label`, `canonical`
    (VIVC prime), `aliases` (full synonym vocabulary for search), and
    per-role aggregated counts. Drives the chip-filter UI: the search box
    matches the query against `label` + `aliases`, and clicking a
    suggestion adds the `slug` to the filter set (where `expandGrapeSet`
    handles VIVC-sibling propagation at predicate time)."""
    alias_reverse = _grape_alias_reverse()
    counts = _build_canonical_counts(aocs, slug_to_canonical)
    seen_canonicals: set[str] = set()
    index: list[dict] = []
    for slug in grapes_info.keys():
        canon = slug_to_canonical.get(slug, slug)
        if canon in seen_canonicals:
            continue
        seen_canonicals.add(canon)
        info = grapes_info.get(canon) or {}
        label = info.get("name") or canon.replace("-", " ")
        siblings = [s for s in vivc_groups.get(info.get("vivc_id"), []) if s != canon]
        aliases = _collect_aliases(
            canon=canon, siblings=siblings, label=label, grapes_info=grapes_info,
            vivc_by_slug=vivc_by_slug, locale=locale, alias_reverse=alias_reverse,
        )
        canonical_name = info.get("canonical_name") or ""
        if canonical_name and canonical_name.casefold() != label.casefold() \
                and canonical_name not in aliases:
            aliases.insert(0, canonical_name)
        index.append({
            "slug": canon,
            "label": label,
            "canonical": canonical_name,
            "aliases": aliases,
            "count": counts["all"].get(canon, 0),
            "count_principal": counts["principal"].get(canon, 0),
            "count_accessory": counts["accessory"].get(canon, 0),
        })
    index.sort(key=lambda e: (-e["count"], e["label"].casefold(), e["slug"]))
    return index


_HOMEPAGE_HREFLANG = (
    '<link rel="alternate" hreflang="en" href="https://www.openwinemap.com/">\n'
    '<link rel="alternate" hreflang="fr" href="https://www.openwinemap.com/fr/">\n'
    '<link rel="alternate" hreflang="es" href="https://www.openwinemap.com/es/">\n'
    '<link rel="alternate" hreflang="nl" href="https://www.openwinemap.com/nl/">\n'
    '<link rel="alternate" hreflang="x-default" href="https://www.openwinemap.com/">'
)


def _entity_path(locale: str, slug: str) -> str:
    """Per-appellation URL path. EN entities live under /en/<slug> (the CDN
    serves the EN shell for /en/*; bare /<slug> 404s); fr/es/nl under
    /<locale>/<slug>. Matches the shipped client deep-link form (no trailing
    slash)."""
    return f"/en/{slug}" if locale == "en" else f"/{locale}/{slug}"


def _entity_hreflang_block(slug: str) -> str:
    rows = [
        f'<link rel="alternate" hreflang="{lg}" href="{_SITE_BASE_URL}/{lg}/{slug}">'
        for lg in ("en", "fr", "es", "nl")
    ]
    rows.append(f'<link rel="alternate" hreflang="x-default" href="{_SITE_BASE_URL}/en/{slug}">')
    return "\n".join(rows)


def _clamp(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def _entity_grape_names(rec: dict, grapes_info: dict, limit: int) -> list[str]:
    out = []
    for g in (rec.get("grapes_principal") or [])[:limit]:
        nm = (
            (rec.get("grape_names") or {}).get(g)
            or (grapes_info.get(g) or {}).get("name")
            or g.replace("-", " ")
        )
        out.append(nm)
    return out


# Wikidata class for the Place.additionalType — "wine-producing region"
# (Q2140699, "type of region"): an honest place-class true for every record,
# EU and non-EU alike, that types the appellation as a wine region without a
# native schema.org type. Set to "" to omit. The EU PDO/PGI regulatory classes
# (Q13439060 / Q3104453) are deliberately NOT used here — they're EU-only (would
# mis-tag the Swiss AOCs) and assert "protected-as", not "is-a".
_WIKIDATA_GI_TYPE = "https://www.wikidata.org/wiki/Q2140699"

# Regulator source-document URL keys in rec["sources"], in rough canonical
# order — surfaced as the WebPage's isBasedOn (honest provenance: the page is
# generated from these official specs). Identity pages (Wikipedia / Wikidata /
# regulator site) go in sameAs instead; PDFs and legal acts belong here.
_SOURCE_DOC_KEYS = (
    "eur_lex_url", "eu_oj_publication_url", "national_pliego_url",
    "national_spec_url", "specifikacija_url", "specifikacija_final_url",
    "ble_produktspezifikation_url", "masaf_override_url", "ivv_caderno_url",
    "cahier_url", "chzo_spec_url",
)


def _dedupe_urls(urls, cap: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = (u or "").strip()
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)
            if cap and len(out) >= cap:
                break
    return out


def _entity_same_as(rec: dict) -> list[str]:
    """Authoritative external *identity* URLs for the appellation, de-duped and
    order-stable: Wikidata QID (highest reconciliation value) → per-locale
    Wikipedia article → official regulator / producer-body site. Source PDFs and
    legal acts are NOT identity pages (they go in isBasedOn), and the eAmbrosia
    register is a hash-route SPA — one shell for every GI — so it is excluded."""
    s = rec.get("sources") or {}
    tf = rec.get("terroir_facts") or {}
    return _dedupe_urls([
        wikidata_url(rec.get("wikidata_qid") or ""),
        tf.get("wiki_source_url") or "",
        (s.get("syndicate") or {}).get("url") or "",
    ])


def _entity_source_docs(rec: dict) -> list[str]:
    """Up to 3 regulator source-document URLs for WebPage.isBasedOn."""
    s = rec.get("sources") or {}
    return _dedupe_urls((s.get(k) for k in _SOURCE_DOC_KEYS), cap=3)


def _entity_jsonld_description(rec: dict, fallback: str) -> str:
    """Localized one-paragraph description: the translated summary, else the
    first 1–2 terroir-fact bullets, else the 160-char meta description."""
    summary = (rec.get("summary") or "").strip()
    if summary:
        return _clamp(summary, 300)
    facts = ((rec.get("terroir_facts") or {}).get("facts")) or []
    joined = " ".join((f.get("bullet") or "").strip() for f in facts[:2]).strip()
    if joined:
        return _clamp(joined, 300)
    return fallback


def _entity_breadcrumb(slug, rec, canonical_url, locale, breadcrumb_id) -> dict:
    """BreadcrumbList: Open Wine Map → [parent →] appellation. The country level
    is deliberately omitted — there is no per-country landing page, and a
    non-final ListItem without an `item` URL is invalid for Google's
    BreadcrumbList rich result (so every ListItem here carries an `item`)."""
    home = f"{_SITE_BASE_URL}/" if locale == "en" else f"{_SITE_BASE_URL}/{locale}/"
    crumbs = [{"@type": "ListItem", "position": 1, "name": "Open Wine Map", "item": home}]
    pos = 2
    if rec.get("is_sub_denomination") and rec.get("parent_name") and rec.get("parent_slug"):
        crumbs.append({
            "@type": "ListItem", "position": pos, "name": rec["parent_name"],
            "item": f"{_SITE_BASE_URL}{_entity_path(locale, rec['parent_slug'])}",
        })
        pos += 1
    crumbs.append({
        "@type": "ListItem", "position": pos, "name": rec.get("name") or slug,
        "item": canonical_url,
    })
    return {"@type": "BreadcrumbList", "@id": breadcrumb_id, "itemListElement": crumbs}


def _build_entity_jsonld(
    slug, rec, canonical_url, locale, country_labels, region, desc=""
) -> str:
    """schema.org @graph (WebSite → WebPage → Place → BreadcrumbList) for one
    appellation, pre-serialised to an opaque string (its braces are JSON data,
    NOT str.format slots — do not double-brace or esc() it). Modelled as a
    WebPage about an AdministrativeArea (the delimited GI region) with a
    sameAs identity cluster; no Article markup, which would require fabricated
    author / editorial dates for a mechanically generated reference page."""
    name = rec.get("name") or slug
    country = country_labels.get(rec.get("country") or "", "")
    description = _entity_jsonld_description(rec, desc)

    contained: list[dict] = []
    if rec.get("is_sub_denomination") and rec.get("parent_name"):
        contained.append({"@type": "AdministrativeArea", "name": rec["parent_name"]})
    if region:
        contained.append({"@type": "AdministrativeArea", "name": region})
    if country:
        contained.append({"@type": "Country", "name": country})
    for alias in rec.get("country_aliases") or []:
        an = country_labels.get(alias, "")
        if an:
            contained.append({"@type": "Country", "name": an})

    website_id = f"{_SITE_BASE_URL}/#website"
    webpage_id = f"{canonical_url}#webpage"
    place_id = f"{canonical_url}#place"
    breadcrumb_id = f"{canonical_url}#breadcrumb"

    website = {
        "@type": "WebSite", "@id": website_id, "name": "Open Wine Map",
        "url": f"{_SITE_BASE_URL}/", "inLanguage": locale,
    }
    webpage = {
        "@type": "WebPage", "@id": webpage_id, "url": canonical_url, "name": name,
        "description": description, "inLanguage": locale,
        "isPartOf": {"@id": website_id}, "mainEntity": {"@id": place_id},
        "breadcrumb": {"@id": breadcrumb_id},
    }
    based_on = _entity_source_docs(rec)
    if based_on:
        webpage["isBasedOn"] = based_on if len(based_on) > 1 else based_on[0]

    place = {
        "@type": "AdministrativeArea", "@id": place_id, "name": name,
        "url": canonical_url, "description": description, "inLanguage": locale,
    }
    if _WIKIDATA_GI_TYPE:
        place["additionalType"] = _WIKIDATA_GI_TYPE
    bbox = rec.get("bbox")
    if bbox and len(bbox) == 4:
        # stored [minLng, minLat, maxLng, maxLat]; GeoShape box wants
        # "minLat minLng maxLat maxLng".
        place["geo"] = {"@type": "GeoShape", "box": f"{bbox[1]} {bbox[0]} {bbox[3]} {bbox[2]}"}
    if contained:
        place["containedInPlace"] = contained if len(contained) > 1 else contained[0]
    same_as = _entity_same_as(rec)
    if same_as:
        place["sameAs"] = same_as

    breadcrumb = _entity_breadcrumb(slug, rec, canonical_url, locale, breadcrumb_id)
    graph = {"@context": "https://schema.org",
             "@graph": [website, webpage, place, breadcrumb]}
    return (
        '<script type="application/ld+json">'
        + json.dumps(graph, ensure_ascii=False)
        + "</script>"
    )


def _build_entity_meta(
    slug, rec, locale, labels, region_labels, country_labels, grapes_info, folded=False
) -> dict:
    """Per-appellation <head> values.

    index pages (`folded=False`): self-canonical, per-slug hreflang cluster, and
    Place/BreadcrumbList JSON-LD. folded pages (`folded=True` — sub-denominations,
    stubs, no-geometry, thin records): `noindex, follow` + self-canonical, no
    JSON-LD. A folded page still boots the map for its deep-link, but is kept out
    of the index as a near-duplicate of the parent. (Self-canonical, NOT
    canonical->parent: Google treats noindex combined with a canonical to a
    *different* URL as a contradictory signal and may ignore one; the parent is
    indexed independently, and the folded page's empty SSR means no
    near-duplicate-of-parent body is ever server-exposed, so the page simply
    drops out of the index cleanly.)"""
    name = rec.get("name") or slug
    kind = rec.get("kind") or ""
    region = region_labels.get(rec.get("region") or "", rec.get("region") or "")
    country = country_labels.get(rec.get("country") or "", "")
    self_url = f"{_SITE_BASE_URL}{_entity_path(locale, slug)}"
    geo = ", ".join(x for x in (region, country) if x)
    head_bits = " · ".join(x for x in (kind, geo) if x)
    title = f"{name} — {head_bits} · Open Wine Map" if head_bits else f"{name} · Open Wine Map"
    gnames = _entity_grape_names(rec, grapes_info, 4)
    desc = f"{name}, {geo}" if geo else name
    if kind:
        desc = f"{desc} · {kind}"
    if gnames:
        desc = f"{desc}. {labels.get('facet_principal_h', '')}: {', '.join(gnames)}"
    desc = _clamp(desc, 160)
    if folded:
        canonical_url = self_url
        jsonld_html = ""
        robots_meta = '<meta name="robots" content="noindex, follow">\n'
    else:
        canonical_url = self_url
        jsonld_html = _build_entity_jsonld(
            slug, rec, self_url, locale, country_labels, region, desc=desc
        )
        robots_meta = ""
    return {
        "canonical_url": canonical_url,
        "page_title": esc(title),
        "meta_description": esc(desc),
        "og_title": esc(title),
        "og_description": esc(desc),
        "hreflang_block": _entity_hreflang_block(slug),
        "jsonld_html": jsonld_html,
        "robots_meta": robots_meta,
    }


# Per-slug record fields the map needs at STARTUP — the sidebar appellation
# list, search, facet filtering, fly-to, the active-filter chips, and the
# map-click stack dedup. Everything else on a record is panel-open-only and
# ships lazily as /data/d/<locale>/<slug>.json (Phase 3 data-bundle diet), so
# the startup bundle drops from ~13 MB to ~3 MB. This set is the contract
# between the Python emitter and the JS app: a field read by any startup path
# — buildAppellationFacet / searchableText / matchesClient / fitToFiltered /
# localityRank / renderActiveFilters→grapeName / the map-click geom_source
# guard — MUST be listed here, or the sidebar/map silently breaks. 04_build_
# maps.py imports this to emit the complement as the per-slug panel JSON.
STARTUP_AOCS_FIELDS = frozenset({
    "name", "name_latin", "kind", "region", "country", "is_wine",
    "styles", "styles_simple",
    "grapes_principal", "grapes_accessory", "grapes_all",
    "bbox", "bbox_villages", "geom_source",
})


def render(
    *,
    layer_url: str,
    villages_layer_url: str,
    source_type: str,
    aocs: dict,
    facet_styles_tree: list[dict],
    style_descendants: dict[str, list[str]],
    facet_styles_simple: list[tuple[str, int]],
    facet_regions: list[tuple[str, int]],
    locale: str = "fr",
    grapes_info: dict | None = None,
    styles_info: dict | None = None,
    vivc_by_slug: dict | None = None,
    area_quartiles: tuple[float, float] = (0.0, 1.0),
    index_slugs: list[str] | None = None,
    fold_slugs: list[str] | None = None,
    entity_out_dir=None,
) -> tuple[str, str, bytes, dict[str, str]]:
    """Render the full map page (index.html) for one locale.

    Returns `(html, data_filename, data_bytes, entity_pages)`, where
    `entity_pages` is `{slug: html}` for each `entity_slugs` member — the
    pre-rendered per-appellation pages reusing this locale's shell + data bundle
    (empty unless `entity_slugs` is given). The large per-locale `aocs`
    and `grapes_info` blobs are NOT inlined; they are serialised into
    `data_bytes` (a `window.__OWM_DATA=…;` script) which the caller writes to
    `wiki/data/<data_filename>`, referenced by a render-blocking `<script>`.

    `aocs` is a {slug: {name, kind, region, ...}} dict (externalised, see above).
    `facet_*` lists are pre-sorted (by frequency desc, then alpha) and
    rendered as filter checkbox groups. `locale` selects the gettext catalog
    used for UI chrome; the data inside `aocs` is not translated.
    `area_q1` / `area_q3` are the 25th / 75th percentile of polygon area
    (degree²), used for opacity / outline-weight interpolation.
    """
    translations = load_translations(locale)
    _ = translations.gettext
    labels = build_labels(_)
    style_labels = build_style_labels(_)
    region_labels = build_region_labels(_)
    country_labels = build_country_labels(_)

    area_q1, area_q3 = area_quartiles
    source_block = _build_source_block(
        layer_url=layer_url,
        villages_layer_url=villages_layer_url,
        source_type=source_type,
        area_q1=area_q1,
        area_q3=area_q3,
    )

    simple_style_labels = {
        "white": labels["style_simple_white"],
        "rose": labels["style_simple_rose"],
        "red": labels["style_simple_red"],
        "sparkling": labels["style_simple_sparkling"],
        "sweet": labels["style_simple_sweet"],
        "other": labels["style_simple_other"],
    }
    from .style_taxonomy import bucket_descendants
    simple_style_buckets = bucket_descendants()

    vivc_groups: dict[int, list[str]] = {}
    for slug, info in (grapes_info or {}).items():
        vid = info.get("vivc_id")
        if vid is None:
            continue
        vivc_groups.setdefault(vid, []).append(slug)
    # Sort member lists so the VIVC-derived structures (siblings / synonyms /
    # search aliases) are reproducible across builds — grapes_info iteration
    # order is set-derived, so without this the inline blobs vary build-to-build
    # and the homepage HTML is never a no-op rerun.
    for _members in vivc_groups.values():
        _members.sort()
    vivc_siblings: dict[str, list[str]] = {}
    for members in vivc_groups.values():
        if len(members) < 2:
            continue
        for slug in members:
            vivc_siblings[slug] = [s for s in members if s != slug]

    # Curator notes pinned to a grape slug — rendered in the pill tooltip.
    # bianchello: kept as a distinct variety (Bianchello del Metauro
    # disciplinare) although VIVC folds it into Trebbiano Toscano.
    if grapes_info is not None:
        for note_slug, note_key in {"bianchello": "bianchello_note"}.items():
            grapes_info.setdefault(note_slug, {})["note"] = labels[note_key]

    # Per-(slug, country) usage from the corpus + global totals — drive the
    # per-locale canonical row label inside each VIVC group. FR picks the
    # spelling most common in FR records (Côt > Malbec), ES picks the
    # ES-corpus spelling (Garnacha > Grenache), EN/NL fall back to global
    # most-common. The regulator vocabulary closest to the locale stays
    # the front-door label; the alternates render as parenthesised
    # synonyms on the same row.
    slug_country_counts: dict[tuple[str, str], int] = {}
    slug_total_counts: dict[str, int] = {}
    for _slug, rec in (aocs or {}).items():
        country = rec.get("country") or "fr"
        for s in rec.get("grapes_all") or []:
            slug_country_counts[(s, country)] = slug_country_counts.get((s, country), 0) + 1
            slug_total_counts[s] = slug_total_counts.get(s, 0) + 1

    _locale_home_country = {"fr": "fr", "es": "es", "pt": "pt"}.get(locale)

    def _pick_canonical(members: list[str]) -> str:
        if _locale_home_country:
            home_pick = min(
                members,
                key=lambda s: (
                    -slug_country_counts.get((s, _locale_home_country), 0),
                    -slug_total_counts.get(s, 0),
                    s,
                ),
            )
            if slug_country_counts.get((home_pick, _locale_home_country), 0) > 0:
                return home_pick
        return min(members, key=lambda s: (-slug_total_counts.get(s, 0), s))

    slug_to_canonical: dict[str, str] = {}
    grape_synonyms: dict[str, list[str]] = {}
    for members in vivc_groups.values():
        used = [m for m in members if slug_total_counts.get(m, 0) > 0]
        if len(used) < 2:
            continue
        canon = _pick_canonical(used)
        others = [
            m for m in sorted(used, key=lambda s: (-slug_total_counts.get(s, 0), s))
            if m != canon
        ]
        grape_synonyms[canon] = others
        for m in used:
            slug_to_canonical[m] = canon

    def _merged_facet(field: str) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for _slug, rec in (aocs or {}).items():
            canons = {slug_to_canonical.get(s, s) for s in rec.get(field) or []}
            for c in canons:
                counts[c] = counts.get(c, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    facet_principal_merged = _merged_facet("grapes_principal")
    facet_accessory_merged = _merged_facet("grapes_accessory")
    facet_grapes_all_merged = _merged_facet("grapes_all")

    grape_search_index = _build_grape_search_index(
        grapes_info=grapes_info or {},
        aocs=aocs or {},
        vivc_by_slug=vivc_by_slug or {},
        vivc_groups=vivc_groups,
        slug_to_canonical=slug_to_canonical,
        locale=locale,
    )

    canonical_path = "/" if locale == "en" else f"/{locale}/"
    canonical_url = f"{_SITE_BASE_URL}{canonical_path}"
    og_locale = _OG_LOCALES[locale]
    og_alt_locales_html = "\n".join(
        f'<meta property="og:locale:alternate" content="{_OG_LOCALES[other]}">'
        for other in ("fr", "en", "es", "nl") if other != locale
    )

    jsonld_payload = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Open Wine Map",
        "url": canonical_url,
        "description": labels["meta_description"],
        "inLanguage": locale,
    }
    jsonld_html = (
        '<script type="application/ld+json">'
        + json.dumps(jsonld_payload, ensure_ascii=False)
        + "</script>"
    )

    # The two large per-locale reference blobs (AOCS ~12 MB, grape tooltips
    # ~0.6 MB) ship in an external hashed /data/ script rather than inline, so
    # the HTML shell is small and the data caches once per locale across every
    # page that locale will serve (homepages now; per-appellation pages later).
    # Serialise after the grapes_info mutation above so the bianchello note is
    # included. A render-blocking <script> assigns window.__OWM_DATA before the
    # main bundle runs, so the app reads it synchronously with no boot re-thread.
    # `aocs` keeps its build order (deterministic, and it drives the sidebar
    # appellation order — do NOT re-sort it); `grapes_info` is a by-key lookup
    # whose dict order is set-derived and varies across runs, so sort its keys
    # to keep the hashed filename stable (reproducible build / long-cacheable).
    # Only the STARTUP_AOCS_FIELDS subset ships inline; the heavy panel payload
    # (summary, terroir facts, sources, grape display-names, …) loads lazily
    # per slug from /data/d/<locale>/<slug>.json (emitted by 04_build_maps.py).
    # The full `aocs` is still used above for the server-rendered entity cards.
    startup_aocs = {
        slug: {k: v for k, v in rec.items() if k in STARTUP_AOCS_FIELDS}
        for slug, rec in aocs.items()
    }
    data_payload = (
        'window.__OWM_DATA={"aocs":'
        + json.dumps(startup_aocs, ensure_ascii=False)
        + ',"grapes_info":'
        + json.dumps(grapes_info or {}, ensure_ascii=False, sort_keys=True)
        + "};"
    )
    data_bytes = data_payload.encode("utf-8")
    data_filename = f"aocs.{locale}.{hashlib.sha256(data_bytes).hexdigest()[:10]}.js"
    aocs_data_src = f"/data/{data_filename}"

    # Slots split two ways. script_kwargs fill the externalised app <script>
    # (one cached /assets/app.<locale>.<hash>.js shared by every page this
    # locale serves); page_shell + the per-call slots fill the lightweight page
    # shell (head + chrome + asset refs). The CSS carries no fields and ships as
    # one shared, content-hashed stylesheet for the whole corpus. So each of the
    # ~11.6k pages is a small shell referencing three cached bundles
    # (data + app + style) instead of inlining ~450 KB.
    script_kwargs = dict(
        lang_attr=locale,
        github_new_issue_url=_GITHUB_NEW_ISSUE_URL,
        source_block=source_block,
        source_type=source_type,
        styles_tree_json=json.dumps(facet_styles_tree, ensure_ascii=False),
        style_descendants_json=json.dumps(style_descendants, ensure_ascii=False),
        styles_simple_json=json.dumps(facet_styles_simple, ensure_ascii=False),
        principal_json=json.dumps(facet_principal_merged, ensure_ascii=False),
        accessory_json=json.dumps(facet_accessory_merged, ensure_ascii=False),
        grapes_all_json=json.dumps(facet_grapes_all_merged, ensure_ascii=False),
        regions_json=json.dumps(facet_regions, ensure_ascii=False),
        style_labels_json=json.dumps(style_labels, ensure_ascii=False),
        simple_style_labels_json=json.dumps(simple_style_labels, ensure_ascii=False),
        simple_style_buckets_json=json.dumps(simple_style_buckets, ensure_ascii=False),
        labels_json=json.dumps(labels, ensure_ascii=False),
        grape_search_index_json=json.dumps(grape_search_index, ensure_ascii=False),
        vivc_siblings_json=json.dumps(vivc_siblings, ensure_ascii=False, sort_keys=True),
        slug_to_canonical_json=json.dumps(slug_to_canonical, ensure_ascii=False, sort_keys=True),
        grape_synonyms_json=json.dumps(grape_synonyms, ensure_ascii=False, sort_keys=True),
        styles_info_json=json.dumps(styles_info or {}, ensure_ascii=False),
        region_labels_json=json.dumps(region_labels, ensure_ascii=False),
        country_labels_json=json.dumps(country_labels, ensure_ascii=False),
        country_flag_emoji_json=json.dumps(_COUNTRY_FLAG_EMOJI, ensure_ascii=False),
    )

    style_body = _STYLE_CSS.replace("{{", "{").replace("}}", "}")
    style_bytes = style_body.encode("utf-8")
    style_filename = f"style.{hashlib.sha256(style_bytes).hexdigest()[:10]}.css"
    style_href = f"/assets/{style_filename}"

    app_body = _render_app_js(script_kwargs)
    app_bytes = app_body.encode("utf-8")
    app_filename = f"app.{locale}.{hashlib.sha256(app_bytes).hexdigest()[:10]}.js"
    app_src = f"/assets/{app_filename}"

    page_shell = dict(
        lang_attr=locale,
        labels=labels,
        og_locale=og_locale,
        og_alt_locales_html=og_alt_locales_html,
        lang_switcher_html=_lang_switcher(locale, labels["lang_switcher_aria"]),
        about_dialog_html=_build_about_dialog(labels),
        sidebar_disclaimer_html=_build_sidebar_disclaimer(labels),
        aocs_data_src=aocs_data_src,
        style_href=style_href,
        app_src=app_src,
    )

    def _fill(**per_page) -> str:
        return _PAGE_TEMPLATE.format(**page_shell, **per_page)

    html = _fill(
        canonical_url=canonical_url,
        jsonld_html=jsonld_html,
        page_title=labels["page_title"],
        meta_description=labels["meta_description"],
        og_title=labels["page_title"],
        og_description=labels["meta_description"],
        hreflang_block=_HOMEPAGE_HREFLANG,
        robots_meta="",
        ssr_content="",
        # Homepage has no appellation SSR card, so the brand wordmark is the
        # page's single <h1>.
        brand_tag="h1",
    )

    # Per-appellation pages are streamed straight to disk (one per slug) rather
    # than accumulated in a dict — at full-corpus scale the in-memory set would
    # be gigabytes. index slugs get a full, indexable card; fold slugs get a
    # noindex shell (self-canonical) that still boots the map.
    n_index = n_fold = 0
    if entity_out_dir is not None and (index_slugs or fold_slugs):
        ctx = RenderCtx(
            locale=locale, labels=labels, region_labels=region_labels,
            country_labels=country_labels, country_flag_emoji=_COUNTRY_FLAG_EMOJI,
            grapes_info=grapes_info or {}, styles_info=styles_info or {},
            style_labels=style_labels, github_new_issue_url=_GITHUB_NEW_ISSUE_URL,
        )

        def _emit(slug: str, meta: dict, ssr: str) -> None:
            page = _fill(
                canonical_url=meta["canonical_url"],
                jsonld_html=meta["jsonld_html"],
                page_title=meta["page_title"],
                meta_description=meta["meta_description"],
                og_title=meta["og_title"],
                og_description=meta["og_description"],
                hreflang_block=meta["hreflang_block"],
                robots_meta=meta["robots_meta"],
                ssr_content=ssr,
                # Index pages carry the appellation <h1> in their SSR card, so
                # the brand wordmark demotes to a <p>; fold pages (empty SSR)
                # keep the brand as their single <h1>.
                brand_tag="p" if ssr else "h1",
            )
            d = entity_out_dir / slug
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(page, encoding="utf-8")

        for slug in index_slugs or []:
            rec = aocs.get(slug)
            if not rec:
                continue
            meta = _build_entity_meta(
                slug, rec, locale, labels, region_labels, country_labels,
                grapes_info or {}, folded=False,
            )
            _emit(slug, meta, render_content_block(rec, slug, ctx))
            n_index += 1

        for slug in fold_slugs or []:
            rec = aocs.get(slug)
            if not rec:
                continue
            meta = _build_entity_meta(
                slug, rec, locale, labels, region_labels, country_labels,
                grapes_info or {}, folded=True,
            )
            _emit(slug, meta, "")
            n_fold += 1

    assets = {
        "data": (data_filename, data_bytes),
        "style": (style_filename, style_bytes),
        "app": (app_filename, app_bytes),
    }
    return html, assets, n_index, n_fold


_TEMPLATE = """<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<title>{page_title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{meta_description}">
<meta name="referrer" content="strict-origin-when-cross-origin">
{robots_meta}<meta name="theme-color" content="#7A1F2B" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a1a" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="/assets/favicon-16.png" sizes="16x16" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="canonical" href="{canonical_url}">
{hreflang_block}
<meta property="og:type" content="website">
<meta property="og:site_name" content="Open Wine Map">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_description}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:image" content="https://www.openwinemap.com/assets/social-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{og_title}">
{og_alt_locales_html}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_description}">
<meta name="twitter:image" content="https://www.openwinemap.com/assets/social-card.png">
{jsonld_html}
<script>
  // Locale auto-detect — runs before MapLibre or any layout work so the
  // redirect happens before paint. Sticky manual choice always wins; the
  // browser language is consulted only on the EN root with no prior choice.
  (function () {{
    var here = "{lang_attr}";
    var supported = {{ fr: 1, en: 1, es: 1, nl: 1 }};
    function pathFor(code) {{ return code === 'en' ? '/' : '/' + code + '/'; }}
    function go(code) {{
      if (code === here) return;
      var hash = window.location.hash || '';
      // Carry the appellation deep-link (/<lang>/<slug>) across the locale
      // change so a shared link survives an auto-redirect; EN home stays at /.
      var base = '/' + here + '/';
      var rest = window.location.pathname || '/';
      rest = (rest.indexOf(base) === 0) ? rest.slice(base.length) : rest.replace(/^\\//, '');
      rest = rest.replace(/\\/+$/, '').split('/')[0];
      var dest = rest ? ('/' + code + '/' + rest) : pathFor(code);
      window.location.replace(dest + hash);
    }}
    var saved = null;
    try {{ saved = localStorage.getItem('lang_choice'); }} catch (e) {{}}
    if (saved && supported[saved] && saved !== here) {{ go(saved); return; }}
    if (here === 'en' && !saved) {{
      var langs = (navigator.languages && navigator.languages.length)
        ? navigator.languages : [navigator.language || navigator.userLanguage || ''];
      for (var i = 0; i < langs.length; i++) {{
        var code = String(langs[i]).slice(0, 2).toLowerCase();
        if (code === 'en') return;
        if (supported[code]) {{ go(code); return; }}
      }}
    }}
  }})();
  (function () {{
    // Set the initial view-mode class on <html> before paint so the
    // advanced-only sidebar sections don't flash visible while the main
    // bundle is still parsing.
    var mode = 'simple';
    try {{ if (localStorage.getItem('view_mode') === 'advanced') mode = 'advanced'; }} catch (e) {{}}
    document.documentElement.classList.add('mode-' + mode);
    // Mark JS available before paint so the server-rendered #ssr-content card
    // can be hidden via CSS (rule below). The app swaps it for the live panel,
    // so JS users skip the brief boot flash; non-JS visitors and non-rendering
    // crawlers still receive the card in the HTML.
    document.documentElement.classList.add('js');
  }})();
  (function () {{
    // Resolve the effective theme before first paint so dark mode never
    // flashes light. `theme` in localStorage is 'light' | 'dark'; absent /
    // 'system' defers to the OS. Mirrors effectiveTheme() in the main bundle.
    var t = null;
    try {{ t = localStorage.getItem('theme'); }} catch (e) {{}}
    var dark = (t === 'dark') || (t !== 'light'
      && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) document.documentElement.classList.add('theme-dark');
  }})();
</script>
<link rel="stylesheet" href="/assets/vendor/maplibre-gl-4.7.1.css">
<style>
  html, body {{ margin:0; padding:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; font-size:14px }}
  /* Hide the server-rendered card once JS is available (class set pre-paint):
     the app swaps it for the live panel, so JS users skip the boot-time flash;
     non-JS visitors and non-rendering crawlers still receive it in the HTML. */
  html.js #ssr-content {{ display:none }}
  #app {{ display:flex; height:100vh }}
  #sidebar {{ width:300px; flex:0 0 300px; background:#1a1a1a; color:#eee; overflow-y:auto; border-right:1px solid #333 }}
  #sidebar .brand-title {{ font-size:15px; padding:14px 16px 4px; margin:0; font-weight:600; letter-spacing:0.02em; display:flex; align-items:center; gap:8px }}
  #sidebar .brand-title .brand-mark {{ width:18px; height:18px; flex:0 0 18px; display:inline-block }}
  #sidebar .subtitle {{ font-size:11px; color:#888; padding:0 16px 10px; border-bottom:1px solid #333 }}
  #sidebar h2 {{ font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:#888; padding:14px 16px 4px; margin:0 }}
  /* `:not(.grape-search)` excludes the chip-filter's typeahead input —
     it owns its own layout via `.grape-search-wrap`, which already
     applies the 16/16 horizontal margin. Without the exclusion the
     catch-all rule stacks margin on top of the wrap's, leaving the
     grape input 32px narrower than the appellation search. */
  #sidebar input[type=text]:not(.grape-search) {{ width:calc(100% - 32px); margin:0 16px 8px; padding:7px 9px; box-sizing:border-box; background:#222; color:#eee; border:1px solid #444; border-radius:3px; font-size:13px }}
  #sidebar input[type=text]:focus {{ outline:none; border-color:#934050 }}
  #sidebar input[type=text]:focus-visible {{ outline:2px solid #fff8e8; outline-offset:1px; border-color:#934050 }}
  #lang-switcher {{ display:flex; gap:2px; padding:6px 12px 8px; border-bottom:1px solid #333 }}
  #lang-switcher a {{ color:#888; font-size:11px; text-transform:uppercase; letter-spacing:0.08em; text-decoration:none; padding:3px 8px; border-radius:3px }}
  #lang-switcher a:hover {{ color:#fff }}
  #lang-switcher a.active {{ color:#fff8e8; background:#2a2a2a; font-weight:700 }}
  #mode-toggle {{ display:flex; gap:0; padding:8px 16px; border-bottom:1px solid #333 }}
  #mode-toggle .mode-btn {{ flex:1; background:#222; color:#888; border:1px solid #444; padding:6px 8px; cursor:pointer; font-size:12px; letter-spacing:0.04em }}
  #mode-toggle .mode-btn:first-child {{ border-radius:3px 0 0 3px }}
  #mode-toggle .mode-btn:last-child {{ border-radius:0 3px 3px 0; border-left:none }}
  #mode-toggle .mode-btn:hover {{ color:#fff }}
  #mode-toggle .mode-btn.active {{ background:#934050; color:#fff; border-color:#934050 }}
  #theme-toggle {{ display:flex; gap:0; padding:6px 16px 8px }}
  #theme-toggle .theme-btn {{ flex:1; background:#222; color:#888; border:1px solid #444; border-left:none; padding:5px 8px; cursor:pointer; font-size:13px; line-height:1.2 }}
  #theme-toggle .theme-btn:first-child {{ border-left:1px solid #444; border-radius:3px 0 0 3px }}
  #theme-toggle .theme-btn:last-child {{ border-radius:0 3px 3px 0 }}
  #theme-toggle .theme-btn:hover {{ color:#fff }}
  #theme-toggle .theme-btn.active {{ background:#934050; color:#fff; border-color:#934050 }}
  #sidebar [data-modes="simple"].mode-hidden, #sidebar [data-modes="advanced"].mode-hidden {{ display:none }}
  html.mode-simple #sidebar [data-modes="advanced"] {{ display:none }}
  html.mode-advanced #sidebar [data-modes="simple"] {{ display:none }}
  #igp-toggle {{ padding:8px 16px; border-top:1px solid #2a2a2a }}
  #igp-toggle label {{ display:flex; align-items:center; gap:6px; cursor:pointer; font-size:12.5px; color:#ddd }}
  #igp-toggle label:hover {{ color:#fff }}
  #igp-toggle input {{ accent-color:#6e7546 }}
  #spirits-toggle {{ padding:6px 16px 10px }}
  #spirits-toggle label {{ display:flex; align-items:center; gap:6px; cursor:pointer; font-size:12.5px; color:#ddd }}
  #spirits-toggle label:hover {{ color:#fff }}
  #spirits-toggle input {{ accent-color:#a07530 }}
  #active-filters {{ display:flex; align-items:center; gap:6px; padding:8px 12px 4px; min-height:0 }}
  #active-filters:has(#active-filters-chips:empty) {{ padding-bottom:0 }}
  #active-filters-chips {{ display:flex; flex-wrap:wrap; gap:4px; flex:1 }}
  #active-filters-chips:empty {{ display:none }}
  .filter-chip {{ display:inline-flex; align-items:center; gap:4px; padding:2px 4px 2px 8px; background:#2a2a2a; color:#eee; border:1px solid #444; border-radius:11px; font-size:11px; line-height:1.3 }}
  .filter-chip.region-chip {{ border-color:#934050; box-shadow:inset 0 0 0 1px #934050; font-weight:600 }}
  .filter-chip button {{ background:none; border:none; color:#888; cursor:pointer; padding:0 4px; font-size:14px; line-height:1; border-radius:50% }}
  .filter-chip button:hover {{ color:#fff; background:#444 }}
  #active-filters #reset {{ background:transparent; color:#888; border:none; padding:2px 6px; cursor:pointer; font-size:11px; text-decoration:underline; flex:0 0 auto }}
  #active-filters #reset:hover {{ color:#fff }}
  #active-filters-chips:empty + #reset {{ display:none }}
  .facet-search {{ width:calc(100% - 32px); margin:4px 16px 6px; padding:5px 8px; box-sizing:border-box; background:#1f1f1f; color:#eee; border:1px solid #3a3a3a; border-radius:3px; font-size:12px }}
  .facet-search:focus {{ outline:none; border-color:#934050 }}
  /* Grape chip filter — replaces the long-list checkbox facet with a
     typeahead + selected-chip UX. Three instances on the page (simple
     all, advanced principal, advanced accessory) all share these rules. */
  /* Horizontal spacing matches `.facet-search`'s `margin:4px 16px 6px`
     so the grape search input lines up with the appellation search
     input below it. The chip-tray and search-wrap each carry their
     own 16px L/R margin instead of the chip-filter container padding. */
  .grape-chip-filter {{ padding:0 }}
  .grape-chip-filter .chip-tray {{ display:flex; flex-wrap:wrap; gap:4px; margin:4px 16px 6px }}
  .grape-chip-filter .chip-tray:empty {{ display:none }}
  .grape-chip-filter .chip {{ display:inline-flex; align-items:center; gap:4px; padding:2px 4px 2px 8px; background:#3a2730; color:#fff; border:1px solid #934050; border-radius:11px; font-size:11px; line-height:1.3 }}
  .grape-chip-filter .chip .canon {{ color:#cfa; opacity:0.7; font-style:italic }}
  .grape-chip-filter .chip-x {{ background:none; border:none; color:#cfa; cursor:pointer; padding:0 4px; font-size:14px; line-height:1; border-radius:50% }}
  .grape-chip-filter .chip-x:hover {{ color:#fff; background:#5a3045 }}
  .grape-search-wrap {{ position:relative; margin:4px 16px 6px }}
  .grape-search {{ width:100%; padding:5px 8px; box-sizing:border-box; background:#1f1f1f; color:#eee; border:1px solid #3a3a3a; border-radius:3px; font-size:12px }}
  .grape-search:focus {{ outline:none; border-color:#934050 }}
  .grape-suggestions {{ position:absolute; left:0; right:0; top:calc(100% + 2px); z-index:50; max-height:280px; overflow-y:auto; background:#1a1a1a; border:1px solid #3a3a3a; border-radius:3px; box-shadow:0 4px 12px rgba(0,0,0,0.4) }}
  .grape-suggestions[hidden] {{ display:none }}
  .grape-suggestions .suggestion {{ display:flex; align-items:center; gap:6px; padding:5px 8px; cursor:pointer; font-size:12px; color:#ddd; border-bottom:1px solid #2a2a2a }}
  .grape-suggestions .suggestion:last-child {{ border-bottom:none }}
  .grape-suggestions .suggestion.active, .grape-suggestions .suggestion:hover {{ background:#2a1f25 }}
  .grape-suggestions .suggestion .name {{ flex:0 0 auto }}
  .grape-suggestions .suggestion .canon {{ flex:1 1 auto; color:#999; font-style:italic; font-size:11px }}
  .grape-suggestions .suggestion .count {{ flex:0 0 auto; margin-left:auto; color:#888; font-size:11px; font-variant-numeric:tabular-nums }}
  #sidebar > details > summary .facet-badge {{ display:inline-block; margin-left:6px; padding:1px 6px; background:#934050; color:#fff; border-radius:8px; font-size:10px; font-weight:600 }}
  #sidebar > details > summary .facet-badge:empty {{ display:none }}
  #sidebar > details > summary {{ display:flex; align-items:center }}
  #sidebar > details > summary .facet-label {{ flex:1 }}
  .facet .region-group-wrap {{ display:flex; align-items:flex-start; gap:6px; margin:2px 0 }}
  .facet .region-group-wrap > .region-select {{ accent-color:#934050; cursor:pointer; flex:0 0 auto; margin-top:6px }}
  .facet .region-group-wrap > .region-select:checked, .facet .region-group-wrap > .region-select:indeterminate {{ accent-color:#934050 }}
  .facet .region-group-wrap > .region-group {{ flex:1 1 auto; min-width:0 }}
  .facet .region-group > summary {{ display:flex; align-items:center; gap:6px }}
  #status {{ padding:8px 16px; font-size:11px; color:#aaa; background:#222; border-bottom:1px solid #333 }}
  #status .hint-action {{ background:none; border:0; padding:0; margin-left:6px; color:#9ac4ff; font:inherit; cursor:pointer; text-decoration:underline }}
  #status .hint-action:hover {{ color:#cfe0ff }}
  details {{ margin:0 }}
  summary {{ cursor:pointer; padding:8px 16px; color:#bbb; font-size:11px; text-transform:uppercase; letter-spacing:0.06em; user-select:none; border-top:1px solid #2a2a2a }}
  summary:hover {{ color:#fff }}
  summary::-webkit-details-marker {{ color:#666 }}
  .facet {{ max-height:240px; overflow-y:auto; padding:0 16px 8px }}
  .facet.facet-appellations {{ max-height:340px }}
  .facet label {{ display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; font-size:12.5px; color:#ddd }}
  .facet label:hover {{ color:#fff }}
  .facet input[type=checkbox] {{ accent-color:#c0392b; flex:0 0 auto }}
  .facet .name {{ flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }}
  .facet .count {{ color:#666; font-size:11px; margin-left:4px }}
  .facet .syns {{ color:#888; font-size:11px; font-weight:normal }}
  /* Keyboard/SR path to open an appellation panel (the WebGL polygons aren't
     DOM-reachable). Subtle until the row is hovered or the button is focused. */
  .facet .open-aoc {{ flex:0 0 auto; margin-left:auto; background:none; border:none; color:#8a8a8a; cursor:pointer; font-size:14px; line-height:1; padding:0 4px; border-radius:3px; opacity:0.55; transition:opacity 0.12s ease, color 0.12s ease, background 0.12s ease }}
  .facet label:hover .open-aoc {{ opacity:1; color:#cfa }}
  .facet .open-aoc:hover {{ color:#fff; background:#333 }}
  .facet .open-aoc:focus-visible {{ opacity:1 }}
  .facet label.facet-unavailable {{ display:none }}
  .facet .region-group-wrap.facet-unavailable {{ display:none }}
  .facet .tree-row[data-depth="0"] {{ padding-left:0 }}
  .facet .tree-row[data-depth="1"] {{ padding-left:14px }}
  .facet .tree-row[data-depth="2"] {{ padding-left:28px }}
  .facet .tree-row-parent {{ font-weight:600; color:#eee }}
  .facet .tree-row[data-depth="0"]:not(:first-child) {{ margin-top:4px }}
  .facet .tree-row[data-depth="2"] .name {{ color:#bbb }}
  .facet .region-group > summary {{ padding:4px 0; border-top:none; font-size:10.5px; color:#888; letter-spacing:0.06em; display:flex; align-items:center; gap:6px }}
  .facet .region-group > summary:hover {{ color:#ddd }}
  .facet .region-group > summary .name {{ flex:1 }}
  .facet .region-group > summary .count {{ color:#555 }}
  .facet .region-group .region-items {{ padding-left:10px }}
  .facet .empty {{ color:#666; font-size:11px; font-style:italic; padding:4px 0 }}
  #actions {{ position:sticky; bottom:0; background:#1a1a1a; padding:10px 16px; border-top:1px solid #333; display:flex; gap:8px }}
  #actions button {{ flex:1; padding:6px; background:#333; color:#eee; border:1px solid #555; border-radius:3px; cursor:pointer; font-size:12px }}
  #actions button:hover {{ background:#444 }}
  #map {{ flex:1; height:100%; min-width:0 }}
  #panel {{ width:0; flex:0 0 0; background:#fff; border-left:1px solid #ddd; overflow-y:auto; transition:flex-basis 0.18s ease, width 0.18s ease }}
  #panel.open {{ width:440px; flex-basis:440px }}
  #panel .close {{ position:sticky; top:0; float:right; margin:8px 12px; background:#eee; border:none; border-radius:50%; width:28px; height:28px; cursor:pointer; font-size:16px; color:#666; z-index:2 }}
  #panel .close:hover {{ background:#ddd; color:#000 }}
  #panel .body {{ padding:16px 24px 40px; line-height:1.55; color:#222 }}
  #panel .body h1 {{ font-size:22px; margin:8px 0 10px; padding-bottom:6px; border-bottom:2px solid #934050 }}
  #panel .body h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:0.04em; color:#934050; margin:18px 0 6px }}
  #panel .body p {{ margin:0 0 8px }}
  #panel .meta {{ color:#666; font-size:12px; margin-bottom:8px }}
  #panel .meta .meta-country {{ display:inline-flex; align-items:center; gap:5px; color:#444 }}
  #panel .meta .country-flag {{ font-size:13px; line-height:1 }}
  #panel .meta .country-name {{ font-weight:600 }}
  #panel .translation-attr {{ font-size:11.5px; color:#666; font-style:italic; margin:0 0 8px }}
  #panel .translation-attr a {{ color:#888 }}
  #panel .stack-header {{ font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:#888; margin-bottom:6px; padding-bottom:6px; border-bottom:1px solid #eee; display:flex; align-items:center; gap:6px }}
  #panel .stack-pos {{ font-size:10.5px; padding:1px 7px; background:#efe7d8; color:#5a4a2a; border-radius:9px; font-variant-numeric:tabular-nums; letter-spacing:0; text-transform:none; cursor:default }}
  #panel .approx-line {{ font-size:11.5px; color:#7a5a1a; background:#fbf3df; border-left:2px solid #d6b35a; padding:4px 8px; margin:4px 0 8px; border-radius:2px }}
  #panel .approx-line a.parent-link {{ color:#7a5a1a; text-decoration:underline }}
  #panel .role-disclaimer {{ font-size:11px; color:#888; font-style:italic; margin:2px 0 8px; line-height:1.35 }}
  #panel .appellation-note {{ font-size:11.5px; color:#33506b; background:#eef3f8; border-left:2px solid #6f93b5; padding:6px 9px; margin:8px 0; border-radius:2px; line-height:1.45 }}
  #panel .appellation-note .note-srcs {{ margin-top:4px }}
  #panel .appellation-note a {{ color:#33506b; text-decoration:underline }}
  #panel details.dulok {{ margin:8px 0; font-size:11.5px; color:#444 }}
  #panel details.dulok > summary {{ cursor:pointer; font-weight:600; color:#5a4a2a; padding:2px 0; list-style:revert }}
  #panel details.dulok[open] > summary {{ margin-bottom:4px }}
  #panel details.dulok .dulo-row {{ padding:2px 0; line-height:1.4; border-top:1px solid #f0ece2 }}
  #panel details.dulok .dulo-tel {{ font-weight:600; color:#7a5a1a }}
  #panel details.menzioni .menzioni-chips {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:4px }}
  #panel details.menzioni .pill.menzione {{ background:#f3eee2; color:#5a4a2a; border:1px solid #e4dcc8; font-size:11px; padding:1px 7px; border-radius:10px }}
  #panel .appellation-note .note-srcs a {{ margin-right:10px; white-space:nowrap }}
  #panel .aoc-card + .aoc-card {{ margin-top:24px; padding-top:20px; border-top:1px dashed #ccc }}
  #panel .aoc-card h1 {{ font-size:18px; margin:0 0 6px; padding-bottom:4px; border-bottom:2px solid #934050 }}
  #panel .aoc-card.subordinate h1 {{ font-size:16px; color:#444; border-bottom-color:#ccc }}
  /* First-open skeleton: real title shows from startup data; the body shimmers
     until the lazy panel-detail JSON lands (Phase 3 data-bundle diet). */
  #panel .aoc-skeleton .skel {{ display:block; border-radius:4px; height:13px; margin:9px 0;
    background:linear-gradient(90deg,#ececec 25%,#f6f6f6 37%,#ececec 63%);
    background-size:400% 100%; animation:skel-shimmer 1.3s ease infinite }}
  #panel .aoc-skeleton .skel-meta {{ width:55%; height:11px; margin:6px 0 0 }}
  #panel .aoc-skeleton .skel-h {{ width:34%; height:11px; margin:20px 0 10px }}
  #panel .aoc-skeleton .skel-line.short {{ width:68% }}
  @keyframes skel-shimmer {{ 0% {{ background-position:100% 0 }} 100% {{ background-position:0 0 }} }}
  @media (prefers-reduced-motion: reduce) {{ #panel .aoc-skeleton .skel {{ animation:none }} }}
  #panel .sources {{ margin:4px 0 0; padding-left:18px; font-size:12.5px; color:#3a3a3a }}
  #panel .sources li {{ margin:3px 0 }}
  #panel .sources code {{ font-size:11px; color:#888 }}
  #panel .facts-sub-h {{ font-size:11px; font-weight:600; color:#555; margin:8px 0 2px; text-transform:none; letter-spacing:0 }}
  #panel ul.facts {{ margin:0 0 6px; padding-left:18px; font-size:13px; color:#222 }}
  #panel ul.facts li {{ margin:2px 0 }}
  #panel ul.facts .wiki-attr {{ font-size:11px; color:#666; font-style:italic }}
  #panel ul.facts .wiki-attr a {{ color:#888 }}
  #panel blockquote.facts-verbatim {{ margin:4px 0 6px; padding:6px 10px; border-left:3px solid #ddd; background:#f9f7f4; font-size:13px; color:#333; font-style:italic; white-space:pre-wrap }}
  #panel .verbatim-badge {{ display:inline-block; margin-left:8px; padding:1px 8px; background:#fff5e5; color:#a05a00; border:1px solid #f0d8a8; border-radius:9px; font-size:10.5px; font-weight:600; font-style:normal; vertical-align:middle }}
  #panel .pills {{ margin:0 0 4px }}
  .pill {{ display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; background:#eee; border-radius:10px; font-size:11px; color:#333; text-decoration:none }}
  .pill.style {{ background:#fdebe5; color:#934050 }}
  .pill.style.style--red, .pill.style.style--clairet, .pill.style.style--primeur {{ background:#f3d6d6; color:#7a1620 }}
  .pill.style.style--white, .pill.style.style--dry, .pill.style.style--tranquille {{ background:#f6efd1; color:#5a4a10 }}
  .pill.style.style--rose {{ background:#fbdce5; color:#7a3050 }}
  .pill.style.style--sparkling, .pill.style.style--cremant {{ background:#e3eaf2; color:#3a4a5e }}
  .pill.style.style--sweet, .pill.style.style--vendanges-tardives, .pill.style.style--grains-nobles {{ background:#fbe8c0; color:#6a4a08 }}
  .pill.style.style--vdn, .pill.style.style--vin-de-liqueur {{ background:#f4d8a8; color:#5a3508 }}
  .pill.style.style--vin-jaune {{ background:#f7e7a3; color:#5a4810 }}
  .pill.style.style--vin-de-paille {{ background:#f9e4b8; color:#684a08 }}
  .pill.grape {{ background:#e8eef5; color:#234 }}
  a.pill.grape:hover {{ background:#d4dff0; text-decoration:underline }}
  .pill.grape.accessory {{ background:#f0f0f0; color:#666 }}
  a.pill.grape.accessory:hover {{ background:#e0e0e0 }}
  .pill.grape.observation {{ background:#fff8d8; color:#7a5a00 }}
  a.pill.grape.observation:hover {{ background:#f5ecc0 }}
  a.pill.grape.has-info {{ border-bottom:1px dotted currentColor; padding-bottom:1px }}
  .pill.grape .canon {{ opacity:0.65; font-weight:normal; font-size:0.9em }}
  h1 .latin, .facet label .latin {{ opacity:0.55; font-weight:normal; font-size:0.85em; margin-left:0.25em }}
  .pill.style {{ cursor:default }}
  a.pill.style {{ text-decoration:none }}
  a.pill.style:hover {{ text-decoration:underline; opacity:0.85 }}
  .pill.style.has-info {{ border-bottom:1px dotted currentColor; padding-bottom:1px }}
  a.pill.style.has-info {{ cursor:pointer }}
  .fr-marker {{ display:inline-block; margin-left:4px; font-size:10px; color:#999; font-style:italic; vertical-align:baseline }}
  #grape-tooltip .fr-marker {{ font-size:10px; color:#888 }}
  #sidebar-toggle {{ display:none; position:fixed; top:8px; right:8px; z-index:30; width:44px; height:44px; background:#1a1a1a; color:#eee; border:1px solid #444; border-radius:4px; font-size:18px; cursor:pointer; align-items:center; justify-content:center; box-shadow:0 2px 8px rgba(0,0,0,0.2) }}
  #sidebar-toggle:hover {{ background:#2a2a2a }}
  #legend {{ border-top:1px solid #2a2a2a }}
  #legend > summary {{ padding:8px 16px; color:#bbb; font-size:11px; text-transform:uppercase; letter-spacing:0.06em }}
  #legend .legend-body {{ padding:4px 16px 12px; font-size:11.5px; color:#bbb; line-height:1.5 }}
  #legend .swatch-row {{ display:flex; align-items:center; gap:6px; margin:3px 0 }}
  #legend .sw {{ display:inline-block; width:14px; height:14px; border-radius:3px; flex:0 0 14px; border:1px solid rgba(255,255,255,0.1) }}
  #legend .sw.aoc {{ background:#934050 }}
  #legend .sw.igp {{ background:#6e7546 }}
  #legend .sw.principal {{ background:#e8eef5 }}
  #legend .sw.accessory {{ background:#f0f0f0 }}
  #legend .sw.observation {{ background:#fff8d8 }}
  #legend .legend-h {{ color:#888; font-size:10.5px; text-transform:uppercase; letter-spacing:0.06em; margin-top:8px }}
  #legend .legend-h:first-child {{ margin-top:0 }}
  #legend .hint {{ color:#888; font-style:italic; margin-top:4px }}
  @media (max-width: 768px) {{
    #app {{ flex-direction:column }}
    #sidebar-toggle {{ display:flex }}
    #sidebar {{ position:fixed; top:0; left:0; width:280px; height:100vh; flex:0 0 auto; transform:translateX(-100%); transition:transform 0.18s ease; z-index:25; box-shadow:2px 0 12px rgba(0,0,0,0.25) }}
    #sidebar.open {{ transform:translateX(0) }}
    #map {{ flex:1; height:100vh; min-width:0 }}
    #panel {{ position:fixed; bottom:0; left:0; right:0; width:auto; height:0; flex:none; max-height:75vh; transition:height 0.18s ease; border-left:none; border-top:1px solid #ddd; z-index:20 }}
    #panel.open {{ width:auto; height:75vh; flex-basis:auto }}
    #panel .close {{ width:44px; height:44px; font-size:20px }}
    .facet input[type=checkbox] {{ width:18px; height:18px }}
    .facet .open-aoc {{ opacity:1; padding:6px 10px; font-size:18px }}
    #actions button {{ min-height:36px }}
  }}
  #sidebar-footer {{ padding:12px 16px 16px; margin-top:8px; border-top:1px solid #2a2a2a; font-size:11px; color:#888; text-align:center }}
  #sidebar-footer a {{ color:#888; text-decoration:none }}
  #sidebar-footer a:hover {{ color:#fff; text-decoration:underline }}
  #sidebar-footer .sep {{ margin:0 6px; color:#444 }}
  #sidebar-disclaimer {{ padding:0 4px 10px; margin-bottom:10px; border-bottom:1px solid #222; font-size:11px; line-height:1.5; color:#888 }}
  #sidebar-disclaimer a {{ color:#aaa; text-decoration:underline; text-underline-offset:2px }}
  #sidebar-disclaimer a:hover {{ color:#fff }}
  .feedback-copied {{ display:inline-block; margin-left:6px; padding:2px 6px; border-radius:3px; background:#7a1f3a; color:#fff; font-size:10.5px; opacity:0; transform:translateY(-1px); transition:opacity 180ms ease, transform 180ms ease; pointer-events:none }}
  .feedback-copied.visible {{ opacity:1; transform:translateY(0) }}
  #about-dialog {{ width:520px; max-width:calc(100vw - 32px); padding:0; border:1px solid #ccc; border-radius:6px; box-shadow:0 8px 32px rgba(0,0,0,0.18); background:#fff; color:#222 }}
  #about-dialog::backdrop {{ background:rgba(0,0,0,0.45) }}
  #about-dialog .close {{ position:absolute; top:10px; right:10px; background:#eee; border:none; border-radius:50%; width:28px; height:28px; cursor:pointer; font-size:16px; color:#666 }}
  #about-dialog .close:hover {{ background:#ddd; color:#000 }}
  #about-dialog .about-body {{ padding:24px 28px; line-height:1.55 }}
  #about-dialog h1 {{ font-size:20px; margin:0 0 14px; padding-bottom:8px; border-bottom:2px solid #934050 }}
  #about-dialog p {{ margin:0 0 10px }}
  #about-dialog a {{ color:#934050 }}
  #grape-tooltip {{ position:fixed; max-width:340px; background:#fff; color:#222; border:1px solid #ddd; border-radius:4px; padding:10px 12px; font-size:12px; line-height:1.5; box-shadow:0 4px 16px rgba(0,0,0,0.15); z-index:1000; display:none }}
  #grape-tooltip .ext {{ margin:0 0 6px }}
  #grape-tooltip .note {{ margin:0 0 6px; font-style:italic; color:#555 }}
  #grape-tooltip .thumb {{ float:right; width:96px; height:auto; margin:0 0 6px 10px; border-radius:3px; background:#f3f3f3 }}
  #grape-tooltip .src {{ color:#888; font-size:10.5px; clear:both }}
  #grape-tooltip .src a {{ color:#888 }}
  #panel .body a {{ color:#934050 }}
  .maplibregl-popup {{ max-width:320px !important }}
  .maplibregl-popup-content {{ font-size:13px; padding:10px 12px !important }}
  .maplibregl-popup-content h3 {{ margin:0 0 4px; font-size:14px; color:#934050 }}
  .maplibregl-popup-content .meta {{ color:#777; font-size:11px }}
  /* Visible focus indicators (WCAG 2.4.7). Light outline on the dark sidebar,
     burgundy outline on the light panel/dialog. */
  #sidebar a:focus-visible,
  #sidebar button:focus-visible,
  #sidebar summary:focus-visible,
  #sidebar input[type=checkbox]:focus-visible,
  #sidebar-toggle:focus-visible {{ outline:2px solid #fff8e8; outline-offset:2px; border-radius:3px }}
  #panel button:focus-visible,
  #panel a:focus-visible,
  #about-dialog button:focus-visible,
  #about-dialog a:focus-visible {{ outline:2px solid #934050; outline-offset:2px; border-radius:3px }}
  .maplibregl-popup-content a:focus-visible {{ outline:2px solid #934050; outline-offset:2px }}
  /* Skip-to-map link: off-screen until focused, so keyboard users can bypass
     the filter sidebar and jump straight to the map. */
  .skip-link {{ position:absolute; left:8px; top:-48px; z-index:60; background:#7A1F2B; color:#fff;
               padding:8px 14px; border-radius:0 0 4px 4px; font-size:13px; text-decoration:none;
               transition:top 0.15s ease }}
  .skip-link:focus {{ top:0 }}
  /* Respect the OS "reduce motion" setting (WCAG 2.3.3): neutralise the
     panel/sidebar slides, toast fades and any animation. */
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration:0.01ms !important; animation-iteration-count:1 !important;
                              transition-duration:0.01ms !important; scroll-behavior:auto !important }}
  }}
  /* Dark mode. Gated on the `html.theme-dark` class (NOT a media query) so the
     manual light/dark/system toggle works: a pre-paint inline script adds the
     class for system-dark OR a manual dark choice, and removing it forces light
     even on a dark OS — no light-mode reset rules needed. The sidebar is already
     dark; this flips the detail panel, about dialog, grape tooltip and map
     popup. Polygon fill tints are unchanged (map layers, not CSS); the basemap
     swaps live via setLayoutProperty (see the dual basemap sources below). */
  html.theme-dark #panel {{ background:#1c1c1e; border-left-color:#333 }}
  html.theme-dark #panel .body {{ color:#e3e3e3 }}
  html.theme-dark #panel .body h1, html.theme-dark #panel .body h2 {{ color:#d98b97; border-bottom-color:#5a2a33 }}
  html.theme-dark #panel .body a, html.theme-dark #panel .translation-attr a,
  html.theme-dark #about-dialog a, html.theme-dark #grape-tooltip a, html.theme-dark #grape-tooltip .src a {{ color:#d98b97 }}
  /* Focus ring must keep ≥3:1 against the dark surface (WCAG 1.4.11/2.4.11):
     the burgundy #934050 ring drops to ~2:1 on #1c1c1e, so brighten it. */
  html.theme-dark #panel button:focus-visible, html.theme-dark #panel a:focus-visible,
  html.theme-dark #about-dialog button:focus-visible, html.theme-dark #about-dialog a:focus-visible {{ outline-color:#d98b97 }}
  html.theme-dark #panel .close, html.theme-dark #about-dialog .close {{ background:#333; color:#bbb }}
  html.theme-dark #panel .close:hover, html.theme-dark #about-dialog .close:hover {{ background:#444; color:#fff }}
  html.theme-dark #panel .meta {{ color:#9a9a9a }}
  html.theme-dark #panel .meta .meta-country {{ color:#cfcfcf }}
  html.theme-dark #panel .stack-header {{ border-bottom-color:#333 }}
  html.theme-dark #panel .aoc-card + .aoc-card {{ border-top-color:#444 }}
  html.theme-dark #panel .aoc-card.subordinate h1 {{ color:#bbb; border-bottom-color:#444 }}
  html.theme-dark #panel .aoc-skeleton .skel {{ background:linear-gradient(90deg,#2b2b2b 25%,#363636 37%,#2b2b2b 63%); background-size:400% 100% }}
  html.theme-dark #panel .sources, html.theme-dark #panel .facts-sub-h {{ color:#bbb }}
  html.theme-dark #panel ul.facts {{ color:#e0e0e0 }}
  html.theme-dark #panel .translation-attr, html.theme-dark #panel ul.facts .wiki-attr {{ color:#a3a3a3 }}
  html.theme-dark #panel blockquote.facts-verbatim {{ background:#262320; color:#dcdcdc; border-left-color:#555 }}
  html.theme-dark #panel .approx-line {{ background:#322b18; color:#e6cf86; border-left-color:#6a5a2a }}
  html.theme-dark #panel .approx-line a.parent-link {{ color:#e6cf86 }}
  html.theme-dark #panel .appellation-note {{ background:#1e2a36; color:#aecbe6; border-left-color:#3f6182 }}
  html.theme-dark #panel .appellation-note a {{ color:#aecbe6 }}
  html.theme-dark #panel details.dulok {{ color:#ccc }}
  html.theme-dark #panel details.dulok > summary, html.theme-dark #panel details.dulok .dulo-tel {{ color:#d8b86a }}
  html.theme-dark #panel details.dulok .dulo-row {{ border-top-color:#333 }}
  html.theme-dark #about-dialog {{ background:#1c1c1e; color:#e3e3e3; border-color:#444 }}
  html.theme-dark #about-dialog h1 {{ color:#d98b97; border-bottom-color:#5a2a33 }}
  html.theme-dark #grape-tooltip {{ background:#1c1c1e; color:#e3e3e3; border-color:#444; box-shadow:0 4px 16px rgba(0,0,0,0.5) }}
  html.theme-dark #grape-tooltip .note {{ color:#bbb }}
  html.theme-dark #grape-tooltip .thumb {{ background:#333 }}
  html.theme-dark .maplibregl-popup-content {{ background:#1c1c1e; color:#e3e3e3 }}
  html.theme-dark .maplibregl-popup-content h3 {{ color:#d98b97 }}
  html.theme-dark .maplibregl-popup-content .meta {{ color:#aaa }}
  html.theme-dark .maplibregl-popup-close-button {{ color:#aaa }}
  html.theme-dark .maplibregl-popup-anchor-top .maplibregl-popup-tip,
  html.theme-dark .maplibregl-popup-anchor-top-left .maplibregl-popup-tip,
  html.theme-dark .maplibregl-popup-anchor-top-right .maplibregl-popup-tip {{ border-bottom-color:#1c1c1e }}
  html.theme-dark .maplibregl-popup-anchor-bottom .maplibregl-popup-tip,
  html.theme-dark .maplibregl-popup-anchor-bottom-left .maplibregl-popup-tip,
  html.theme-dark .maplibregl-popup-anchor-bottom-right .maplibregl-popup-tip {{ border-top-color:#1c1c1e }}
  html.theme-dark .maplibregl-popup-anchor-left .maplibregl-popup-tip {{ border-right-color:#1c1c1e }}
  html.theme-dark .maplibregl-popup-anchor-right .maplibregl-popup-tip {{ border-left-color:#1c1c1e }}
  /* Pills: the light pastel chips glow on the dark panel — re-tint to dark,
     muted, hue-preserving backgrounds with light text so they read calmly. */
  html.theme-dark .pill {{ background:#2d2d30; color:#d6d6d6 }}
  html.theme-dark .pill.style {{ background:#34232a; color:#e3aab4 }}
  html.theme-dark .pill.style.style--red, html.theme-dark .pill.style.style--clairet, html.theme-dark .pill.style.style--primeur {{ background:#3a1f24; color:#e7a3ab }}
  html.theme-dark .pill.style.style--white, html.theme-dark .pill.style.style--dry, html.theme-dark .pill.style.style--tranquille {{ background:#2f2a16; color:#d9c886 }}
  html.theme-dark .pill.style.style--rose {{ background:#371f2b; color:#e7a6c1 }}
  html.theme-dark .pill.style.style--sparkling, html.theme-dark .pill.style.style--cremant {{ background:#1f2a36; color:#a8c5e1 }}
  html.theme-dark .pill.style.style--sweet, html.theme-dark .pill.style.style--vendanges-tardives, html.theme-dark .pill.style.style--grains-nobles {{ background:#33290f; color:#e6c684 }}
  html.theme-dark .pill.style.style--vdn, html.theme-dark .pill.style.style--vin-de-liqueur {{ background:#2f2110; color:#e2b97e }}
  html.theme-dark .pill.style.style--vin-jaune {{ background:#2f2914; color:#e7d186 }}
  html.theme-dark .pill.style.style--vin-de-paille {{ background:#2f2614; color:#e7c987 }}
  html.theme-dark .pill.grape {{ background:#202d3b; color:#aecbe8 }}
  html.theme-dark a.pill.grape:hover {{ background:#2a3a4c }}
  html.theme-dark .pill.grape.accessory {{ background:#2a2a2c; color:#aeaeae }}
  html.theme-dark a.pill.grape.accessory:hover {{ background:#343437 }}
  html.theme-dark .pill.grape.observation {{ background:#2e2a14; color:#e0cb84 }}
  html.theme-dark a.pill.grape.observation:hover {{ background:#383218 }}
  html.theme-dark #panel .stack-pos {{ background:#2e2a1c; color:#d8c79a }}
  html.theme-dark #panel .verbatim-badge {{ background:#33280f; color:#e6b86a; border-color:#5a4a1e }}
  html.theme-dark #panel details.menzioni .pill.menzione {{ background:#2c2a20; color:#d8c89a; border-color:#3e3a2c }}
</style>
<!-- Privacy-friendly analytics by Plausible -->
<script async src="https://analytics.dev.devloed.com/js/pa-QAprx84urDZKvC3I6r6bc.js"></script>
<script>
  window.plausible=window.plausible||function(){{(plausible.q=plausible.q||[]).push(arguments)}},plausible.init=plausible.init||function(i){{plausible.o=i||{{}}}};
  plausible.init()
</script>
</head>
<body>
<a class="skip-link" href="#map">{labels[skip_to_map]}</a>
<div id="app">{ssr_content}
  <aside id="sidebar" data-nosnippet aria-label="{labels[sidebar_aria]}">
    <{brand_tag} class="brand-title"><img class="brand-mark" src="/assets/pin-icon.svg" alt="" aria-hidden="true" width="18" height="18">Open Wine Map</{brand_tag}>
    <div class="subtitle">{labels[subtitle]}</div>
    {lang_switcher_html}
    <div id="theme-toggle" role="group" aria-label="{labels[theme_h]}">
      <button type="button" data-theme-mode="light" class="theme-btn" aria-pressed="false" aria-label="{labels[theme_light]}" title="{labels[theme_light]}">☀</button>
      <button type="button" data-theme-mode="system" class="theme-btn active" aria-pressed="true" aria-label="{labels[theme_system]}" title="{labels[theme_system]}">◐</button>
      <button type="button" data-theme-mode="dark" class="theme-btn" aria-pressed="false" aria-label="{labels[theme_dark]}" title="{labels[theme_dark]}">☾</button>
    </div>
    <div id="status" role="status" aria-live="polite" aria-atomic="true">{labels[loading]}</div>

    <div id="mode-toggle" role="group" aria-label="{labels[view_mode_h]}">
      <button type="button" data-mode="simple" class="mode-btn active" aria-pressed="true">{labels[view_mode_simple]}</button>
      <button type="button" data-mode="advanced" class="mode-btn" aria-pressed="false">{labels[view_mode_advanced]}</button>
    </div>

    <div id="active-filters" aria-label="{labels[active_filters_aria]}">
      <div id="active-filters-chips"></div>
      <button id="reset" type="button">{labels[reset]}</button>
    </div>

    <details open data-modes="simple" data-facet="styles">
      <summary><span class="facet-label">{labels[facet_styles_h]}</span><span class="facet-badge"></span></summary>
      <div class="facet" id="facet-styles-simple"></div>
    </details>

    <details open data-modes="advanced" data-facet="styles">
      <summary><span class="facet-label">{labels[facet_styles_h]}</span><span class="facet-badge"></span></summary>
      <div class="facet" id="facet-styles"></div>
    </details>

    <details open data-modes="simple" data-facet="grapes">
      <summary><span class="facet-label">{labels[facet_grapes_h]}</span><span class="facet-badge"></span></summary>
      <div class="grape-chip-filter" data-role="all"></div>
    </details>

    <details data-modes="advanced" data-facet="grapes">
      <summary><span class="facet-label">{labels[facet_principal_h]}</span><span class="facet-badge"></span></summary>
      <div class="grape-chip-filter" data-role="principal"></div>
    </details>

    <details data-modes="advanced" data-facet="accessory">
      <summary><span class="facet-label">{labels[facet_accessory_h]}</span><span class="facet-badge"></span></summary>
      <div class="grape-chip-filter" data-role="accessory"></div>
    </details>

    <details open data-facet="appellations">
      <summary><span class="facet-label">{labels[facet_appellations_h]}</span><span class="facet-badge"></span></summary>
      <input type="text" id="q" class="facet-search" placeholder="{labels[search_appellation_placeholder]}" autocomplete="off">
      <div class="facet facet-appellations" id="facet-appellations"></div>
    </details>

    <div id="igp-toggle">
      <label><input type="checkbox" id="show-igp"> <span class="name">{labels[show_igp_label]}</span></label>
    </div>

    <div id="spirits-toggle" data-modes="advanced">
      <label><input type="checkbox" id="show-spirits"> <span class="name">{labels[show_spirits_label]}</span></label>
    </div>

    <details id="legend" open>
      <summary>{labels[legend_h]}</summary>
      <div class="legend-body">
        <div class="legend-h">{labels[legend_bassin_h]}</div>
        <div class="swatch-row"><span class="sw aoc"></span><span>{labels[kind_aoc]}</span></div>
        <div class="swatch-row"><span class="sw igp"></span><span>{labels[kind_igp]}</span></div>
        <div class="hint">{labels[legend_area_hint]}</div>
        <div class="legend-h">{labels[legend_grapes_h]}</div>
        <div class="swatch-row"><span class="sw principal"></span><span>{labels[legend_principal]}</span></div>
        <div class="swatch-row"><span class="sw accessory"></span><span>{labels[legend_accessory]}</span></div>
        <div class="swatch-row"><span class="sw observation"></span><span>{labels[legend_observation]}</span></div>
      </div>
    </details>

    <div id="sidebar-footer">
      {sidebar_disclaimer_html}
      <div id="sidebar-footer-links">
        <a href="#" id="about-link">{labels[about_link_label]}</a>
      </div>
    </div>

  </aside>

  <button id="sidebar-toggle" type="button" aria-label="{labels[sidebar_toggle_aria]}">☰</button>

  <main id="map" tabindex="-1" aria-label="{labels[map_aria]}"></main>

  <div id="panel" tabindex="-1" role="dialog" aria-modal="false" aria-label="{labels[panel_aria]}">
    <button class="close" type="button" aria-label="{labels[close_aria]}">×</button>
    <div class="body" id="panel-body"></div>
  </div>

  {about_dialog_html}
</div>

<script src="/assets/vendor/maplibre-gl-4.7.1.js"></script>
<script src="/assets/vendor/pmtiles-3.2.0.js"></script>
<!-- Per-locale data bundle (appellation records + grape tooltips). Render-
     blocking on purpose so window.__OWM_DATA is defined before the app below
     reads it; hashed filename = immutable, long-cacheable, shared across every
     page of this locale. -->
<script src="{aocs_data_src}"></script>
<script src="{app_src}"></script>
</body>
</html>
"""


def _split_template(t: str) -> tuple[str, str]:
    """Lift the inline CSS out of the monolithic template so it ships as a
    shared, content-hashed /assets/ file. The app JS lives in
    `assets/app.js` (a real, lint-able source file loaded by `_render_app_js`);
    the template references both assets via {style_href} / {app_src}.

    Returns (page_template, style_css):
      * page_template references the two assets via {style_href} / {app_src}
        (and still carries the per-page + per-locale head/chrome fields).
      * style_css is the CSS body (doubled braces, no format fields).

    The <style> delimiter is unique in the template (one <style>, no '</style>'
    inside its body); a lossless-reconstruction assert guards against drift."""
    style_open, style_close = "<style>", "</style>"
    pre, _r = t.split(style_open, 1)
    css, post = _r.split(style_close, 1)
    if pre + style_open + css + style_close + post != t:
        raise AssertionError("map_template: _split_template is not lossless")
    page_template = pre + '<link rel="stylesheet" href="{style_href}">' + post
    return page_template, css


_PAGE_TEMPLATE, _STYLE_CSS = _split_template(_TEMPLATE)

# The map application JS lives in assets/app.js — a real .js file (lint-able,
# eslint-able) rather than an escaped Python string. Build-time per-locale
# values are injected via `__OWM_<slot>__` tokens that sit exactly where the
# old `{slot}` format fields were (literal braces are already real in the .js),
# so `_render_app_js` is byte-for-byte equivalent to the old
# `_APP_JS.format(**kwargs)` (verified by the golden comparator). app.js is now
# the sole source — edit it directly; do not move the JS back into _TEMPLATE.
_APP_JS_SOURCE = (Path(__file__).resolve().parent / "assets" / "app.js").read_text(
    encoding="utf-8"
)
_OWM_TOKEN_RE = re.compile(r"__OWM_(\w+?)__")


def _render_app_js(kwargs: dict[str, str]) -> str:
    """Fill the per-locale build tokens in assets/app.js (single pass, so a
    value can never be re-scanned for another token)."""
    missing: list[str] = []

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in kwargs:
            missing.append(key)
            return m.group(0)
        return str(kwargs[key])

    out = _OWM_TOKEN_RE.sub(_sub, _APP_JS_SOURCE)
    if missing:
        raise KeyError(f"app.js: unfilled build tokens {sorted(set(missing))}")
    return out
