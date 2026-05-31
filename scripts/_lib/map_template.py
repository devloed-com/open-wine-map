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

import json
from collections.abc import Callable

from _lib.i18n import load_translations


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
        "remove_filter_aria": _("Retirer le filtre {label}"),
        "sidebar_aria": _("Filtres et options de la carte"),
        "lang_switcher_aria": _("Langue"),
        "map_aria": _("Carte des appellations viticoles"),
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
            "Extension de la couverture européenne en cours : France, "
            "Espagne, Portugal, Italie, Autriche, Allemagne, Slovénie, "
            "Croatie, Hongrie, Roumanie, Bulgarie et Grèce sont déjà "
            "cartographiés. Quelques itérations supplémentaires "
            "viendront affiner la qualité des données existantes ; "
            "l'Europe centrale et orientale est à considérer comme une "
            "première version, appelée à être améliorée. À plus long "
            "terme, des classifications hors AOP pourront être ajoutées."
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
        f'    <h1 id="about-dialog-h">{labels["about_h"]}</h1>\n'
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
    index.sort(key=lambda e: (-e["count"], e["label"].casefold()))
    return index


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
) -> str:
    """Render the full map page (index.html) for one locale.

    `aocs` is a {slug: {name, kind, region, ...}} dict serialised inline.
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

    return _TEMPLATE.format(
        lang_attr=locale,
        labels=labels,
        canonical_url=canonical_url,
        og_locale=og_locale,
        og_alt_locales_html=og_alt_locales_html,
        jsonld_html=jsonld_html,
        lang_switcher_html=_lang_switcher(locale, labels["lang_switcher_aria"]),
        about_dialog_html=_build_about_dialog(labels),
        sidebar_disclaimer_html=_build_sidebar_disclaimer(labels),
        source_block=source_block,
        aocs_json=json.dumps(aocs, ensure_ascii=False),
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
        grapes_info_json=json.dumps(grapes_info or {}, ensure_ascii=False),
        grape_search_index_json=json.dumps(grape_search_index, ensure_ascii=False),
        vivc_siblings_json=json.dumps(vivc_siblings, ensure_ascii=False),
        slug_to_canonical_json=json.dumps(slug_to_canonical, ensure_ascii=False),
        grape_synonyms_json=json.dumps(grape_synonyms, ensure_ascii=False),
        styles_info_json=json.dumps(styles_info or {}, ensure_ascii=False),
        region_labels_json=json.dumps(region_labels, ensure_ascii=False),
        country_labels_json=json.dumps(country_labels, ensure_ascii=False),
        country_flag_emoji_json=json.dumps(_COUNTRY_FLAG_EMOJI, ensure_ascii=False),
        source_type=source_type,
    )


_TEMPLATE = """<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<title>{labels[page_title]}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{labels[meta_description]}">
<meta name="theme-color" content="#7A1F2B">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="/assets/favicon-16.png" sizes="16x16" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="canonical" href="{canonical_url}">
<link rel="alternate" hreflang="en" href="https://www.openwinemap.com/">
<link rel="alternate" hreflang="fr" href="https://www.openwinemap.com/fr/">
<link rel="alternate" hreflang="es" href="https://www.openwinemap.com/es/">
<link rel="alternate" hreflang="nl" href="https://www.openwinemap.com/nl/">
<link rel="alternate" hreflang="x-default" href="https://www.openwinemap.com/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Open Wine Map">
<meta property="og:title" content="{labels[page_title]}">
<meta property="og:description" content="{labels[meta_description]}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:image" content="https://www.openwinemap.com/assets/social-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{labels[page_title]}">
{og_alt_locales_html}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{labels[page_title]}">
<meta name="twitter:description" content="{labels[meta_description]}">
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
      window.location.replace(pathFor(code) + hash);
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
  }})();
</script>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>
  html, body {{ margin:0; padding:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; font-size:14px }}
  #app {{ display:flex; height:100vh }}
  #sidebar {{ width:300px; flex:0 0 300px; background:#1a1a1a; color:#eee; overflow-y:auto; border-right:1px solid #333 }}
  #sidebar h1 {{ font-size:15px; padding:14px 16px 4px; margin:0; font-weight:600; letter-spacing:0.02em; display:flex; align-items:center; gap:8px }}
  #sidebar h1 .brand-mark {{ width:18px; height:18px; flex:0 0 18px; display:inline-block }}
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
  #panel .translation-attr {{ font-size:10.5px; color:#888; font-style:italic; margin:0 0 8px }}
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
  #panel .sources {{ margin:4px 0 0; padding-left:18px; font-size:12px; color:#444 }}
  #panel .sources li {{ margin:3px 0 }}
  #panel .sources code {{ font-size:11px; color:#888 }}
  #panel .facts-sub-h {{ font-size:11px; font-weight:600; color:#555; margin:8px 0 2px; text-transform:none; letter-spacing:0 }}
  #panel ul.facts {{ margin:0 0 6px; padding-left:18px; font-size:13px; color:#222 }}
  #panel ul.facts li {{ margin:2px 0 }}
  #panel ul.facts .wiki-attr {{ font-size:10.5px; color:#888; font-style:italic }}
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
</style>
<!-- Privacy-friendly analytics by Plausible -->
<script async src="https://analytics.dev.devloed.com/js/pa-QAprx84urDZKvC3I6r6bc.js"></script>
<script>
  window.plausible=window.plausible||function(){{(plausible.q=plausible.q||[]).push(arguments)}},plausible.init=plausible.init||function(i){{plausible.o=i||{{}}}};
  plausible.init()
</script>
</head>
<body>
<div id="app">
  <aside id="sidebar" data-nosnippet aria-label="{labels[sidebar_aria]}">
    <h1><img class="brand-mark" src="/assets/pin-icon.svg" alt="" aria-hidden="true" width="18" height="18">Open Wine Map</h1>
    <div class="subtitle">{labels[subtitle]}</div>
    {lang_switcher_html}
    <div id="status">{labels[loading]}</div>

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

  <main id="map" aria-label="{labels[map_aria]}"></main>

  <div id="panel">
    <button class="close" type="button" aria-label="{labels[close_aria]}">×</button>
    <div class="body" id="panel-body"></div>
  </div>

  {about_dialog_html}
</div>

<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@3.2.0/dist/pmtiles.js"></script>
<script>
  const AOCS = {aocs_json};
  const FACET_STYLES_TREE = {styles_tree_json};
  const STYLE_DESCENDANTS = {style_descendants_json};
  const FACET_STYLES_SIMPLE = {styles_simple_json};
  const FACET_PRINCIPAL = {principal_json};
  const FACET_ACCESSORY = {accessory_json};
  const FACET_GRAPES_ALL = {grapes_all_json};
  const FACET_REGIONS = {regions_json};
  const STYLE_LABELS = {style_labels_json};
  const SIMPLE_STYLE_LABELS = {simple_style_labels_json};
  const SIMPLE_STYLE_BUCKETS = {simple_style_buckets_json};
  const LABELS = {labels_json};
  // Per-jurisdiction regulator-published specification document name,
  // in the regulator's own language. Used by the stub-message block
  // when no source document has been located for an appellation yet.
  const STUB_DOC_NAMES = {{
    fr: 'cahier des charges',
    es: 'pliego de condiciones',
    pt: 'caderno de especificações',
    it: 'disciplinare di produzione',
    at: 'Produktspezifikation',
    si: 'specifikacija proizvoda',
    hr: 'specifikacija proizvoda',
    ro: 'caiet de sarcini',
  }};
  const GRAPES_INFO = {grapes_info_json};
  // Slug -> siblings sharing the same VIVC variety id. Used to make the
  // grape filter synonym-aware: toggling Cot also matches AOCs that
  // list Malbec / Auxerrois / any other regulatory spelling of vivc_id
  // 2889. The facet list keeps each spelling as its own row (so the user
  // sees the regulator's terminology) — the expansion happens only in
  // the filter predicate.
  const VIVC_SIBLINGS = {vivc_siblings_json};
  // Per-locale canonical row label: each member of a VIVC group maps to
  // the single canonical slug under which the facet renders. Cross-narrow
  // counts roll up via this map so a record using "malbec" increments the
  // canonical "cot" row.
  const SLUG_TO_CANONICAL = {slug_to_canonical_json};
  // Synonyms shown inline on each canonical row (e.g. Côt → [malbec,
  // auxerrois]). Sorted by global usage; the row's `.name` span includes
  // every synonym so the per-facet search input matches any spelling.
  const GRAPE_SYNONYMS = {grape_synonyms_json};
  function expandGrapeSet(set) {{
    if (!set || !set.size) return set;
    const out = new Set(set);
    for (const slug of set) {{
      const sibs = VIVC_SIBLINGS[slug];
      if (sibs) for (const s of sibs) out.add(s);
    }}
    return out;
  }}
  function grapeSynonymsHtml(canonSlug) {{
    const syns = GRAPE_SYNONYMS[canonSlug];
    if (!syns || !syns.length) return '';
    const labels = syns.map(s => grapeName(s)).join(', ');
    return ` <span class="syns">(${{labels}})</span>`;
  }}

  // -------------------------- grape chip filter --------------------------
  //
  // Replaces the long-list checkbox facet for grapes with a typeahead +
  // selected-chip UX. The index ships pre-built (one entry per canonical
  // slug with cahier label + VIVC prime + full alias vocabulary + per-role
  // counts). Match logic: substring against the label and any alias, with
  // a score (prefix > substring, label > alias) so "garna" surfaces
  // Grenache (Garnacha) and "shiraz" surfaces Syrah.
  const GRAPE_SEARCH_INDEX = {grape_search_index_json};
  const _GRAPE_INDEX_NORM = GRAPE_SEARCH_INDEX.map(entry => ({{
    entry,
    labelN: searchNormalize(entry.label),
    aliasesN: (entry.aliases || []).map(a => searchNormalize(a)),
  }}));

  function rankGrapeSuggestions(query, role, limit) {{
    const countKey = role === 'principal' ? 'count_principal'
                   : role === 'accessory' ? 'count_accessory' : 'count';
    const nq = searchNormalize(query || '');
    if (!nq) {{
      return _GRAPE_INDEX_NORM
        .filter(e => e.entry[countKey] > 0)
        .slice(0, limit)
        .map(e => ({{ entry: e.entry, matched: null }}));
    }}
    const out = [];
    for (const e of _GRAPE_INDEX_NORM) {{
      if (e.entry[countKey] === 0) continue;
      let score = -1;
      let matched = null;  // The alias string that matched, if any.
      if (e.labelN.startsWith(nq)) score = 100;
      else if (e.labelN.includes(nq)) score = 80;
      else {{
        // Walk aliases; remember which one matched best so the suggestion
        // can promote that spelling to the primary slot ("Ull de Llebre
        // (Tempranillo)" instead of plain "Tempranillo" when the user
        // typed "ull").
        let bestAliasScore = -1;
        let bestAliasIdx = -1;
        for (let i = 0; i < e.aliasesN.length; i++) {{
          const a = e.aliasesN[i];
          let s = -1;
          if (a.startsWith(nq)) s = 60;
          else if (a.includes(nq)) s = 40;
          if (s > bestAliasScore) {{ bestAliasScore = s; bestAliasIdx = i; }}
        }}
        if (bestAliasScore >= 0) {{
          score = bestAliasScore;
          matched = e.entry.aliases[bestAliasIdx];
        }}
      }}
      if (score >= 0) out.push({{ entry: e.entry, matched, score }});
    }}
    out.sort((a, b) => b.score - a.score || b.entry[countKey] - a.entry[countKey]);
    return out.slice(0, limit).map(o => ({{ entry: o.entry, matched: o.matched }}));
  }}

  function _findGrapeEntry(slug) {{
    for (const e of _GRAPE_INDEX_NORM) if (e.entry.slug === slug) return e.entry;
    return null;
  }}

  function _grapeChipHtml(entry) {{
    const canon = entry.canonical && !canonicalEqualsCahier(entry.canonical, entry.label)
      ? ` <span class="canon">(${{escapeHtml(entry.canonical)}})</span>` : '';
    return (
      `<span class="chip" data-slug="${{escapeAttr(entry.slug)}}">` +
        `<span class="name">${{escapeHtml(toTitleCase(entry.label))}}</span>${{canon}}` +
        `<button class="chip-x" type="button" aria-label="Remove ${{escapeAttr(entry.label)}}">×</button>` +
      `</span>`
    );
  }}

  function _grapeSuggestionHtml(entry, matched, role, active) {{
    // When the query matched on an alias (e.g. "ull de llebre" → Tempranillo
    // via the GRAPE_ALIAS reverse-key "ull-de-llebre"), promote the
    // matched alias to the primary slot so the suggestion reads in the
    // user's terminology — "Ull de Llebre (Tempranillo)" — instead of
    // burying the match in the canonical row label.
    const primary = matched || entry.label;
    const secondary = matched && matched.toLowerCase() !== entry.label.toLowerCase()
      ? entry.label
      : (entry.canonical && !canonicalEqualsCahier(entry.canonical, entry.label) ? entry.canonical : '');
    const secondaryHtml = secondary
      ? ` <span class="canon">${{escapeHtml(toTitleCase(secondary))}}</span>` : '';
    const countKey = role === 'principal' ? 'count_principal'
                   : role === 'accessory' ? 'count_accessory' : 'count';
    const cls = ['suggestion'];
    if (active) cls.push('active');
    return (
      `<div class="${{cls.join(' ')}}" role="option" data-slug="${{escapeAttr(entry.slug)}}">` +
        `<span class="name">${{escapeHtml(toTitleCase(primary))}}</span>${{secondaryHtml}}` +
        `<span class="count">${{entry[countKey]}}</span>` +
      `</div>`
    );
  }}

  function buildGrapeChipFilter(container, role, filterSet) {{
    container.innerHTML =
      `<div class="chip-tray" aria-live="polite"></div>` +
      `<div class="grape-search-wrap">` +
        `<input type="text" class="grape-search" name="grape-search-${{escapeAttr(role)}}" placeholder="${{escapeAttr(LABELS.search_grape_placeholder)}}" autocomplete="off" role="combobox" aria-expanded="false" aria-autocomplete="list">` +
        `<div class="grape-suggestions" role="listbox" hidden></div>` +
      `</div>`;
    const tray = container.querySelector('.chip-tray');
    const input = container.querySelector('.grape-search');
    const drop  = container.querySelector('.grape-suggestions');
    let activeIdx = 0;
    let currentSuggestions = [];

    function renderChips() {{
      const chips = [];
      for (const slug of filterSet) {{
        const e = _findGrapeEntry(slug);
        if (e) chips.push(_grapeChipHtml(e));
      }}
      tray.innerHTML = chips.join('');
    }}

    function renderSuggestions(q) {{
      currentSuggestions = rankGrapeSuggestions(q, role, 12)
        .filter(s => !filterSet.has(s.entry.slug));
      activeIdx = 0;
      if (!currentSuggestions.length) {{
        drop.innerHTML = '';
        drop.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        return;
      }}
      drop.innerHTML = currentSuggestions
        .map((s, i) => _grapeSuggestionHtml(s.entry, s.matched, role, i === activeIdx)).join('');
      drop.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }}

    function highlight(i) {{
      const items = drop.querySelectorAll('.suggestion');
      if (!items.length) return;
      items.forEach((el, k) => el.classList.toggle('active', k === i));
      activeIdx = i;
      const cur = items[i];
      if (cur) cur.scrollIntoView({{ block: 'nearest' }});
    }}

    function pick(slug) {{
      filterSet.add(slug);
      input.value = '';
      renderChips();
      renderSuggestions('');
      applyFilter();
      input.focus();
    }}

    function remove(slug) {{
      filterSet.delete(slug);
      renderChips();
      renderSuggestions(input.value);
      applyFilter();
    }}

    tray.addEventListener('click', (e) => {{
      const btn = e.target.closest('.chip-x');
      if (!btn) return;
      const chip = btn.closest('.chip');
      if (chip) remove(chip.dataset.slug);
    }});

    drop.addEventListener('mousedown', (e) => {{
      const s = e.target.closest('.suggestion');
      if (!s) return;
      e.preventDefault();  // keep focus on input
      pick(s.dataset.slug);
    }});

    drop.addEventListener('mousemove', (e) => {{
      const s = e.target.closest('.suggestion');
      if (!s) return;
      const items = Array.from(drop.querySelectorAll('.suggestion'));
      highlight(items.indexOf(s));
    }});

    input.addEventListener('input', () => renderSuggestions(input.value));
    input.addEventListener('focus', () => renderSuggestions(input.value));
    input.addEventListener('blur', () => {{
      // Delay so the mousedown handler runs before we hide.
      setTimeout(() => {{ drop.hidden = true; input.setAttribute('aria-expanded', 'false'); }}, 120);
    }});
    input.addEventListener('keydown', (e) => {{
      if (e.key === 'ArrowDown') {{
        e.preventDefault();
        if (drop.hidden) renderSuggestions(input.value);
        else highlight((activeIdx + 1) % currentSuggestions.length);
      }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        if (!drop.hidden) highlight((activeIdx - 1 + currentSuggestions.length) % currentSuggestions.length);
      }} else if (e.key === 'Enter') {{
        if (!drop.hidden && currentSuggestions[activeIdx]) {{
          e.preventDefault();
          pick(currentSuggestions[activeIdx].entry.slug);
        }}
      }} else if (e.key === 'Escape') {{
        drop.hidden = true;
        input.setAttribute('aria-expanded', 'false');
      }} else if (e.key === 'Backspace' && !input.value && filterSet.size) {{
        // Remove the most-recently-added chip.
        const last = [...filterSet].pop();
        remove(last);
      }}
    }});

    renderChips();
    container._refresh = () => {{ renderChips(); if (!drop.hidden) renderSuggestions(input.value); }};
  }}

  function refreshAllGrapeChipFilters() {{
    document.querySelectorAll('.grape-chip-filter').forEach(c => c._refresh && c._refresh());
  }}
  const STYLES_INFO = {styles_info_json};
  const REGION_LABELS = {region_labels_json};
  const COUNTRY_LABELS = {country_labels_json};
  const COUNTRY_FLAG_EMOJI = {country_flag_emoji_json};
  const LANG = "{lang_attr}";
  const SOURCE_TYPE = "{source_type}";

  // Plausible custom-event helper. No-ops gracefully if the analytics
  // script failed to load (ad-blocker, offline preview, dev build).
  // All props use bounded slug vocabularies — never raw user text — so
  // the breakdown UI stays useful and no PII can leak.
  function track(name, props) {{
    try {{
      if (typeof window.plausible !== 'function') return;
      window.plausible(name, props ? {{ props: props }} : undefined);
    }} catch (e) {{}}
  }}

  // Title-case the first letter of each word (after start, whitespace,
  // hyphen, or apostrophe). Wikipedia grape titles aren't uniformly
  // cased (FR uses "Cabernet sauvignon" sentence case while EN uses
  // "Cabernet Sauvignon" title case), and the slug fallback is pure
  // lowercase — normalising here makes pills and filter entries
  // consistent regardless of source.
  function toTitleCase(s) {{
    return s.replace(/(?:^|[\\s\\-'(])\\p{{L}}/gu, c => c.toUpperCase());
  }}

  function grapeName(slug) {{
    const info = GRAPES_INFO[slug];
    const raw = (info && info.name) ? info.name : slug.replace(/-/g, ' ');
    return toTitleCase(raw);
  }}

  function regionLabel(region) {{
    if (!region) return LABELS.meta_no_region;
    return REGION_LABELS[region] || region;
  }}

  function oneCountryChip(countryCode) {{
    const flag = COUNTRY_FLAG_EMOJI[countryCode] || '';
    const name = COUNTRY_LABELS[countryCode] || '';
    if (!flag && !name) return '';
    const flagSpan = flag ? `<span class="country-flag" aria-hidden="true">${{flag}}</span>` : '';
    const nameSpan = name ? `<span class="country-name">${{escapeHtml(name)}}</span>` : '';
    return `<span class="meta-country">${{flagSpan}}${{nameSpan}}</span>`;
  }}

  // Cross-border PDOs (e.g. Maasvallei Limburg BE+NL) get a chip per
  // country, joined with " · ". Single-country records render one chip.
  function countryChipHtml(countryCode, aliases) {{
    if (!countryCode) return '';
    const codes = [countryCode].concat(aliases || []);
    return codes.map(oneCountryChip).filter(Boolean).join(' · ');
  }}

  function grapeUrl(slug) {{
    const info = GRAPES_INFO[slug];
    if (info && info.page_url) return info.page_url;
    const title = slug.replace(/-/g, '_').replace(/^./, c => c.toUpperCase());
    return `https://${{LANG}}.wikipedia.org/wiki/${{title}}`;
  }}

  // True when the per-AOC cahier spelling and the VIVC prime name refer
  // to the same variety after a light normalisation (strip diacritics,
  // the INAO trailing colour letter, and the VIVC trailing color word).
  // When equal, we suppress the canonical bracket to avoid pills like
  // "Touriga Nacional (Touriga Nacional)".
  const CANON_COLOR_WORD_RE = /\\b(tinto|tinta|blanco|blanca|noir|blanc|gris|rouge|ros[eé])\\b/gi;
  const CANON_COLOR_LETTER_RE = /\\s+(b|n|g|rs|rg)$/i;
  function canonicalEqualsCahier(canon, cahier) {{
    const norm = s => s
      .normalize('NFKD')
      .replace(/\\p{{Diacritic}}/gu, '')
      .replace(CANON_COLOR_LETTER_RE, '')
      .replace(CANON_COLOR_WORD_RE, '')
      .replace(/[^a-z0-9]/gi, '')
      .toLowerCase();
    return norm(canon) === norm(cahier);
  }}

  function searchNormalize(s) {{
    return (s || '').normalize('NFD').replace(/\\p{{Diacritic}}/gu, '').toLowerCase();
  }}

  // BG / GR appellations carry both a native-script name (Cyrillic /
  // Greek) and an informational Latin transliteration (`name_latin`).
  // Search has to match either form so a user typing "Mavrud" finds
  // "Мавруд".
  function searchableText(rec) {{
    return searchNormalize(((rec && rec.name) || '') + ' ' + ((rec && rec.name_latin) || ''));
  }}

  function nameWithLatin(rec) {{
    const native = escapeHtml((rec && rec.name) || '');
    const latin = (rec && rec.name_latin) || '';
    if (!latin || latin === rec.name) return native;
    return native + ' <span class="latin">(' + escapeHtml(latin) + ')</span>';
  }}

  const proto = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', proto.tile);

  const map = new maplibregl.Map({{
    container: 'map',
    style: {{
      version: 8,
      sources: {{
        basemap: {{
          type: 'raster', tileSize: 256,
          tiles: [
            'https://a.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png',
            'https://b.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png',
            'https://c.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png'
          ],
          attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
        }}
      }},
      layers: [{{ id: 'basemap', type: 'raster', source: 'basemap' }}]
    }},
    center: [2.6, 46.5], zoom: 5.4, hash: true
  }});

  // Preserve URL hash (zoom/lat/lon) when switching locale, and remember
  // the manual choice so future visits stick.
  document.querySelectorAll('#lang-switcher a').forEach(a => {{
    a.addEventListener('click', e => {{
      e.preventDefault();
      try {{ localStorage.setItem('lang_choice', a.dataset.lang); }} catch (err) {{}}
      window.location.href = a.dataset.href + window.location.hash;
    }});
  }});

  // Mobile sidebar toggle.
  const sidebarEl = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebar-toggle');
  if (sidebarToggle) {{
    sidebarToggle.addEventListener('click', () => sidebarEl.classList.toggle('open'));
  }}

  // About dialog. Native <dialog>; backdrop click closes.
  const aboutDialog = document.getElementById('about-dialog');
  const aboutLink = document.getElementById('about-link');
  if (aboutDialog && aboutLink) {{
    aboutLink.addEventListener('click', e => {{
      e.preventDefault();
      if (typeof aboutDialog.showModal === 'function') aboutDialog.showModal();
      else aboutDialog.setAttribute('open', '');
    }});
    aboutDialog.querySelector('.close').addEventListener('click', () => aboutDialog.close());
    aboutDialog.addEventListener('click', e => {{
      const r = aboutDialog.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right
                  && e.clientY >= r.top  && e.clientY <= r.bottom;
      if (!inside) aboutDialog.close();
    }});
  }}

  // Defeat naive scrapers: the address never appears as a contiguous
  // string in rendered HTML. We arm the anchor's href on first
  // interaction (mousedown/focus/touchstart, all of which fire before
  // the click that actually navigates), so the browser handles the
  // mailto: protocol natively. We also copy the address to the
  // clipboard on click so the link still works for users without a
  // configured mailto handler (Firefox silently drops navigation in
  // that case).
  document.querySelectorAll('a.feedback-mail').forEach(a => {{
    const address = () => a.dataset.u + '@' + a.dataset.d;
    const arm = () => {{
      if (a.dataset.u && a.dataset.d) {{
        a.href = 'mailto:' + address() + '?subject=open%20wine%20map';
      }}
    }};
    a.addEventListener('mousedown', arm);
    a.addEventListener('focus', arm);
    a.addEventListener('touchstart', arm, {{ passive: true }});
    a.addEventListener('click', () => {{
      const addr = address();
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(addr).catch(() => {{}});
      }}
      const toast = document.createElement('span');
      toast.className = 'feedback-copied';
      toast.textContent = LABELS.feedback_copied_label;
      a.insertAdjacentElement('afterend', toast);
      requestAnimationFrame(() => toast.classList.add('visible'));
      setTimeout(() => {{
        toast.classList.remove('visible');
        toast.addEventListener('transitionend', () => toast.remove(), {{ once: true }});
      }}, 1800);
    }});
  }});

  let viewMode = 'simple';
  try {{ viewMode = localStorage.getItem('view_mode') || 'simple'; }} catch (e) {{}}
  if (viewMode !== 'advanced') viewMode = 'simple';

  let showIgp = false;
  try {{ showIgp = localStorage.getItem('show_igp') === '1'; }} catch (e) {{}}

  let showSpirits = false;
  try {{ showSpirits = localStorage.getItem('show_spirits') === '1'; }} catch (e) {{}}

  // Spirits toggle is Advanced-only; in Simple mode spirits are always
  // hidden regardless of the persisted preference.
  function spiritsVisible() {{ return viewMode === 'advanced' && showSpirits; }}

  const filters = {{
    q: '',
    styles: new Set(),
    stylesSimple: new Set(),
    principal: new Set(),
    accessory: new Set(),
    grapesAll: new Set(),
    appellations: new Set(),
  }};

  function buildFilterExpr() {{
    const parts = ['all'];
    if (!showIgp) parts.push(['!=', ['get', 'kind'], 'IGP']);
    if (!spiritsVisible()) parts.push(['==', ['get', 'is_wine'], '1']);
    function inField(field, set) {{
      if (set.size === 0) return null;
      const tests = [];
      for (const v of set) tests.push(['in', ';' + v + ';', ['get', field]]);
      return tests.length === 1 ? tests[0] : ['any', ...tests];
    }}
    if (viewMode === 'simple') {{
      if (filters.stylesSimple.size) {{
        const fineSet = new Set();
        for (const b of filters.stylesSimple) {{
          for (const s of (SIMPLE_STYLE_BUCKETS[b] || [])) fineSet.add(s);
        }}
        const sExpr = inField('styles', fineSet);
        if (sExpr) parts.push(sExpr);
      }}
      const gExpr = inField('grapes_all', expandGrapeSet(filters.grapesAll));
      if (gExpr) parts.push(gExpr);
    }} else {{
      const fineStyles = expandStyles(filters.styles);
      const sExpr = fineStyles ? inField('styles', fineStyles) : null;
      const pExpr = inField('grapes_principal', expandGrapeSet(filters.principal));
      const aExpr = inField('grapes_accessory', expandGrapeSet(filters.accessory));
      if (sExpr) parts.push(sExpr);
      if (pExpr) parts.push(pExpr);
      if (aExpr) parts.push(aExpr);
    }}
    if (filters.appellations.size) {{
      const tests = [];
      for (const s of filters.appellations) tests.push(['==', ['get', 'slug'], s]);
      parts.push(tests.length === 1 ? tests[0] : ['any', ...tests]);
    }}
    return parts.length === 1 ? null : parts;
  }}

  function applyFilter(opts) {{
    const expr = buildFilterExpr();
    for (const id of ['appellations-fill', 'appellations-outline',
                       'appellations-fill-villages', 'appellations-outline-villages']) {{
      if (map.getLayer(id)) map.setFilter(id, expr);
    }}
    updateStatus();
    refreshFacetBadges();
    refreshFacetAvailability();
    renderActiveFilters();
    if (opts && opts.fit) fitToFiltered();
  }}

  // Cross-narrow each facet: an option is shown only if at least one record
  // matches every OTHER active filter while carrying that option's key. Counts
  // are recomputed against the same per-facet "other filters" set. Already-
  // checked options stay visible even when their count drops to 0, so the
  // user can always unselect what they selected.
  function refreshFacetAvailability() {{
    const flatFacets = [
      {{ id: 'facet-styles-simple', except: 'stylesSimple', field: 'styles_simple', mode: 'simple' }},
      {{ id: 'facet-grapes-all',    except: 'grapesAll',    field: 'grapes_all',    mode: 'simple' }},
      {{ id: 'facet-principal',     except: 'principal',    field: 'grapes_principal', mode: 'advanced' }},
      {{ id: 'facet-accessory',     except: 'accessory',    field: 'grapes_accessory', mode: 'advanced' }},
    ];
    for (const f of flatFacets) {{
      if (f.mode && f.mode !== viewMode) continue;
      const el = document.getElementById(f.id);
      if (!el) continue;
      const except = new Set([f.except]);
      const counts = new Map();
      const isGrape = f.id !== 'facet-styles-simple';
      for (const slug in AOCS) {{
        const rec = AOCS[slug];
        if (!matchesExceptFacets(rec, slug, except)) continue;
        const vals = rec[f.field] || [];
        if (isGrape) {{
          // Roll up by canonical slug so a record using "malbec" increments
          // the merged "cot" row exactly once even when it carries multiple
          // synonyms of the same VIVC variety.
          const canons = new Set();
          for (const v of vals) canons.add(SLUG_TO_CANONICAL[v] || v);
          for (const c of canons) counts.set(c, (counts.get(c) || 0) + 1);
        }} else {{
          for (const v of vals) counts.set(v, (counts.get(v) || 0) + 1);
        }}
      }}
      el.querySelectorAll('label').forEach(lbl => {{
        const inp = lbl.querySelector('input[type=checkbox]');
        if (!inp) return;
        const key = inp.dataset.key;
        const n = counts.get(key) || 0;
        const countSpan = lbl.querySelector('.count');
        if (countSpan) countSpan.textContent = String(n);
        lbl.classList.toggle('facet-unavailable', n === 0 && !inp.checked);
      }});
    }}
    // Style tree (advanced mode): each node's count is the number of records
    // (in the cross-narrowed set) whose styles intersect that node's
    // descendant slug set — same aggregation the build-time pre-count uses.
    if (viewMode === 'advanced') {{
      const treeEl = document.getElementById('facet-styles');
      if (treeEl) {{
        const except = new Set(['styles']);
        const treeCounts = new Map();
        for (const slug in AOCS) {{
          const rec = AOCS[slug];
          if (!matchesExceptFacets(rec, slug, except)) continue;
          const recStyles = rec.styles || [];
          if (!recStyles.length) continue;
          const recStyleSet = new Set(recStyles);
          for (const node in STYLE_DESCENDANTS) {{
            const ds = STYLE_DESCENDANTS[node];
            for (let i = 0; i < ds.length; i++) {{
              if (recStyleSet.has(ds[i])) {{
                treeCounts.set(node, (treeCounts.get(node) || 0) + 1);
                break;
              }}
            }}
          }}
        }}
        treeEl.querySelectorAll('label').forEach(lbl => {{
          const inp = lbl.querySelector('input[type=checkbox]');
          if (!inp) return;
          const key = inp.dataset.key;
          const n = treeCounts.get(key) || 0;
          const countSpan = lbl.querySelector('.count');
          if (countSpan) countSpan.textContent = String(n);
          lbl.classList.toggle('facet-unavailable', n === 0 && !inp.checked);
        }});
      }}
    }}
    // Appellation facet: per-slug reachability + per-region rollup. The
    // group-level count span shows the number of currently-reachable
    // appellations in the region.
    const appEl = document.getElementById('facet-appellations');
    if (appEl) {{
      const except = new Set(['appellations']);
      appEl.querySelectorAll('.region-group').forEach(group => {{
        let visible = 0;
        group.querySelectorAll('label').forEach(lbl => {{
          const inp = lbl.querySelector('input[type=checkbox]');
          if (!inp) return;
          const slug = inp.dataset.key;
          const rec = AOCS[slug];
          const reachable = rec ? matchesExceptFacets(rec, slug, except) : false;
          const hide = !reachable && !inp.checked;
          lbl.classList.toggle('facet-unavailable', hide);
          if (!hide) visible++;
        }});
        // `.region-group` is now the inner `<details>`; hide the
        // outer `.region-group-wrap` so the sibling checkbox vanishes
        // alongside the disclosure when no AOCs remain visible.
        (group.parentElement || group).classList.toggle('facet-unavailable', visible === 0);
        const countSpan = group.querySelector(':scope > summary > .count');
        if (countSpan) countSpan.textContent = String(visible);
      }});
    }}
  }}

  function facetCounts() {{
    const grapes = (viewMode === 'simple')
      ? filters.grapesAll.size
      : (filters.principal.size + filters.accessory.size);
    const styles = (viewMode === 'simple') ? filters.stylesSimple.size : filters.styles.size;
    return {{
      styles,
      grapes,
      accessory: filters.accessory.size,
      appellations: filters.appellations.size,
    }};
  }}

  function refreshFacetBadges() {{
    const counts = facetCounts();
    const map_ = {{
      styles: counts.styles,
      grapes: viewMode === 'simple' ? counts.grapes : filters.principal.size,
      accessory: filters.accessory.size,
      appellations: counts.appellations,
    }};
    document.querySelectorAll('#sidebar > details[data-facet]').forEach(det => {{
      const key = det.dataset.facet;
      const badge = det.querySelector(':scope > summary .facet-badge');
      if (!badge) return;
      const n = map_[key] || 0;
      badge.textContent = n > 0 ? String(n) : '';
    }});
  }}

  function renderActiveFilters() {{
    const el = document.getElementById('active-filters-chips');
    if (!el) return;
    const chips = [];
    // Style chips (mode-aware).
    if (viewMode === 'simple') {{
      for (const k of filters.stylesSimple) {{
        chips.push({{ kind: 'styleSimple', key: k, label: SIMPLE_STYLE_LABELS[k] || k }});
      }}
    }} else {{
      for (const k of filters.styles) {{
        chips.push({{ kind: 'style', key: k, label: STYLE_LABELS[k] || k }});
      }}
    }}
    // Grape chips.
    if (viewMode === 'simple') {{
      for (const k of filters.grapesAll) {{
        chips.push({{ kind: 'grapeAll', key: k, label: grapeName(k) }});
      }}
    }} else {{
      for (const k of filters.principal) {{
        chips.push({{ kind: 'principal', key: k, label: grapeName(k) }});
      }}
      for (const k of filters.accessory) {{
        chips.push({{ kind: 'accessory', key: k, label: grapeName(k) + ' ·' }});
      }}
    }}
    // Region/appellation chips: collapse fully-selected regions into a
    // single chip; render leftover slugs individually.
    const collapsedSlugs = new Set();
    for (const [region, allSlugs] of REGION_SLUGS) {{
      const slugs = visibleSlugsInRegion(region);
      if (!slugs.length) continue;
      const allIn = slugs.every(s => filters.appellations.has(s));
      if (allIn) {{
        chips.push({{ kind: 'region', key: region, label: region ? regionLabel(region) : LABELS.meta_no_region }});
        for (const s of slugs) collapsedSlugs.add(s);
      }}
    }}
    for (const slug of filters.appellations) {{
      if (collapsedSlugs.has(slug)) continue;
      const rec = AOCS[slug];
      if (!rec) continue;
      chips.push({{ kind: 'appellation', key: slug, label: rec.name }});
    }}
    el.innerHTML = chips.map(c => {{
      const cls = c.kind === 'region' ? 'filter-chip region-chip' : 'filter-chip';
      const removeAria = fmt(LABELS.remove_filter_aria, {{ label: c.label }});
      return `<span class="${{cls}}" data-kind="${{escapeAttr(c.kind)}}" data-key="${{escapeAttr(c.key)}}"><span>${{escapeHtml(c.label)}}</span><button type="button" aria-label="${{escapeAttr(removeAria)}}">×</button></span>`;
    }}).join('');
  }}

  document.getElementById('active-filters-chips').addEventListener('click', e => {{
    const btn = e.target.closest('button');
    if (!btn) return;
    const chip = btn.closest('.filter-chip');
    if (!chip) return;
    const kind = chip.dataset.kind;
    const key = chip.dataset.key;
    if (kind === 'styleSimple') filters.stylesSimple.delete(key);
    else if (kind === 'style') filters.styles.delete(key);
    else if (kind === 'grapeAll') filters.grapesAll.delete(key);
    else if (kind === 'principal') filters.principal.delete(key);
    else if (kind === 'accessory') filters.accessory.delete(key);
    else if (kind === 'appellation') filters.appellations.delete(key);
    else if (kind === 'region') setRegionSelection(key, false);
    // Sync the underlying checkboxes for the cleared filter.
    document.querySelectorAll('#sidebar .facet input[type=checkbox]').forEach(inp => {{
      const k = inp.dataset.key;
      const isApp = inp.closest('#facet-appellations');
      if (isApp && k) {{
        inp.checked = filters.appellations.has(k);
      }}
    }});
    refreshSidebarCheckedState();
    refreshRegionTriStates();
    applyFilter();
  }});

  function refreshSidebarCheckedState() {{
    // Re-sync facet checkboxes (styles only — grapes are chip filters
    // and re-render their chip tray via `refreshAllGrapeChipFilters`).
    const sets = {{
      'facet-styles': filters.styles,
      'facet-styles-simple': filters.stylesSimple,
    }};
    for (const [id, set] of Object.entries(sets)) {{
      const el = document.getElementById(id);
      if (!el) continue;
      el.querySelectorAll('input[type=checkbox]').forEach(inp => {{
        inp.checked = set.has(inp.dataset.key);
      }});
    }}
    refreshAllGrapeChipFilters();
  }}

  function fitToFiltered() {{
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let any = false;
    for (const slug in AOCS) {{
      const rec = AOCS[slug];
      const b = (viewMode === 'simple' && rec.bbox_villages) ? rec.bbox_villages : rec.bbox;
      if (!b) continue;
      if (!matchesClient(rec, slug)) continue;
      if (b[0] < minX) minX = b[0];
      if (b[1] < minY) minY = b[1];
      if (b[2] > maxX) maxX = b[2];
      if (b[3] > maxY) maxY = b[3];
      any = true;
    }}
    if (!any) return;
    if (minX >= maxX || minY >= maxY) return;
    map.fitBounds([[minX, minY], [maxX, maxY]], {{ padding: 40, maxZoom: 10, duration: 500 }});
  }}

  function fmt(tpl, vars) {{
    return tpl.replace(/\\{{(\\w+)\\}}/g, (_, k) => vars[k] != null ? vars[k] : '');
  }}

  function updateStatus() {{
    const el = document.getElementById('status');
    const total = Object.keys(AOCS).length;
    const expr = buildFilterExpr();
    if (!expr) {{ el.textContent = fmt(LABELS.count_total, {{ n: total }}); return; }}
    let n = 0;
    for (const slug in AOCS) if (matchesClient(AOCS[slug], slug)) n++;
    // When the filter excludes every visible record but matches one or
    // more hidden IGPs, surface a one-click reveal so the user understands
    // *why* the camera didn't move. Same idea for hidden spirits.
    if (n === 0) {{
      let nHiddenIgp = 0;
      if (!showIgp) {{
        for (const slug in AOCS) {{
          const rec = AOCS[slug];
          if ((rec.kind || 'AOC') !== 'IGP') continue;
          if (matchesClient(rec, slug, {{ ignoreIgpGate: true }})) nHiddenIgp++;
        }}
      }}
      if (nHiddenIgp > 0) {{
        const prefix = fmt(LABELS.count_filtered, {{ n: 0, total: total }});
        el.textContent = prefix + ' · ';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hint-action';
        btn.textContent = fmt(LABELS.count_hidden_igp_hint, {{ n: nHiddenIgp }});
        btn.addEventListener('click', () => {{
          showIgp = true;
          const igpEl = document.getElementById('show-igp');
          if (igpEl) igpEl.checked = true;
          try {{ localStorage.setItem('show_igp', '1'); }} catch (err) {{}}
          track('Kind Toggled', {{ kind: 'igp', enabled: 'true', locale: LANG, via: 'reveal-hint' }});
          applyFilter({{ fit: true }});
        }});
        el.appendChild(btn);
        return;
      }}
    }}
    el.textContent = fmt(LABELS.count_filtered, {{ n: n, total: total }});
  }}

  function matchesClient(rec, slug, opts) {{
    if (!(opts && opts.ignoreIgpGate) && !showIgp && (rec.kind || 'AOC') === 'IGP') return false;
    if (!spiritsVisible() && rec.is_wine === false) return false;
    if (viewMode === 'simple') {{
      if (filters.stylesSimple.size && !setIntersects(filters.stylesSimple, rec.styles_simple || [])) return false;
      if (filters.grapesAll.size && !setIntersects(expandGrapeSet(filters.grapesAll), rec.grapes_all || [])) return false;
    }} else {{
      if (filters.styles.size) {{
        const fineStyles = expandStyles(filters.styles);
        if (!fineStyles || !setIntersects(fineStyles, rec.styles)) return false;
      }}
      if (filters.principal.size && !setIntersects(expandGrapeSet(filters.principal), rec.grapes_principal)) return false;
      if (filters.accessory.size && !setIntersects(expandGrapeSet(filters.accessory), rec.grapes_accessory)) return false;
    }}
    if (filters.appellations.size && !filters.appellations.has(slug)) return false;
    return true;
  }}

  // Mirrors buildFilterExpr semantics (style/grape expansion via taxonomy +
  // VIVC siblings), but skips facets named in `except` so each facet's own
  // availability can be computed against ONLY the other active filters —
  // the standard faceted-search expansion pattern.
  function matchesExceptFacets(rec, slug, except) {{
    if (!showIgp && (rec.kind || 'AOC') === 'IGP') return false;
    if (!spiritsVisible() && rec.is_wine === false) return false;
    if (viewMode === 'simple') {{
      if (!except.has('stylesSimple') && filters.stylesSimple.size) {{
        const fineSet = new Set();
        for (const b of filters.stylesSimple) {{
          for (const s of (SIMPLE_STYLE_BUCKETS[b] || [])) fineSet.add(s);
        }}
        if (!setIntersects(fineSet, rec.styles || [])) return false;
      }}
      if (!except.has('grapesAll') && filters.grapesAll.size) {{
        if (!setIntersects(expandGrapeSet(filters.grapesAll), rec.grapes_all || [])) return false;
      }}
    }} else {{
      if (!except.has('styles') && filters.styles.size) {{
        const fineStyles = expandStyles(filters.styles);
        if (!fineStyles || !setIntersects(fineStyles, rec.styles || [])) return false;
      }}
      if (!except.has('principal') && filters.principal.size) {{
        if (!setIntersects(expandGrapeSet(filters.principal), rec.grapes_principal || [])) return false;
      }}
      if (!except.has('accessory') && filters.accessory.size) {{
        if (!setIntersects(expandGrapeSet(filters.accessory), rec.grapes_accessory || [])) return false;
      }}
    }}
    if (!except.has('appellations') && filters.appellations.size && !filters.appellations.has(slug)) return false;
    return true;
  }}

  function setIntersects(set, arr) {{
    if (!arr) return false;
    for (const v of arr) if (set.has(v)) return true;
    return false;
  }}

  function buildFacet(containerId, items, store, format, extraFormat) {{
    const el = document.getElementById(containerId);
    const html = items.map(([key, count]) => {{
      const safeKey = String(key).replace(/"/g, '&quot;');
      const label = format ? format(key) : key;
      const extra = extraFormat ? extraFormat(key) : '';
      return `<label><input type="checkbox" data-key="${{safeKey}}"><span class="name">${{label}}${{extra}}</span><span class="count">${{count}}</span></label>`;
    }}).join('');
    el.innerHTML = html;
    el.addEventListener('change', e => {{
      if (e.target.tagName !== 'INPUT') return;
      const k = e.target.dataset.key;
      if (e.target.checked) store.add(k); else store.delete(k);
      if (e.target.checked) {{
        track('Filter Applied', {{ facet: containerId.replace(/^facet-/, ''), value: k, locale: LANG }});
      }}
      applyFilter({{ fit: true }});
    }});
  }}

  function buildStyleTreeFacet(containerId, tree, store) {{
    const el = document.getElementById(containerId);
    const html = tree.map(node => {{
      const safeKey = String(node.slug).replace(/"/g, '&quot;');
      const label = STYLE_LABELS[node.slug] || node.slug;
      const hasChildren = (STYLE_DESCENDANTS[node.slug] || []).length > 1;
      const cls = `tree-row${{ hasChildren ? ' tree-row-parent' : '' }}`;
      return `<label class="${{cls}}" data-depth="${{node.depth}}"><input type="checkbox" data-key="${{safeKey}}"><span class="name">${{label}}</span><span class="count">${{node.count}}</span></label>`;
    }}).join('');
    el.innerHTML = html;
    el.addEventListener('change', e => {{
      if (e.target.tagName !== 'INPUT') return;
      const k = e.target.dataset.key;
      if (e.target.checked) store.add(k); else store.delete(k);
      if (e.target.checked) {{
        track('Filter Applied', {{ facet: 'styles', value: k, locale: LANG }});
      }}
      applyFilter({{ fit: true }});
    }});
  }}

  // Expand a set of taxonomy slugs to the leaf slugs records actually carry,
  // so a click on a parent (e.g. "sweet") catches every descendant record.
  function expandStyles(set) {{
    if (!set.size) return null;
    const out = new Set();
    for (const s of set) {{
      const ds = STYLE_DESCENDANTS[s];
      if (ds && ds.length) for (const d of ds) out.add(d);
      else out.add(s);
    }}
    return out;
  }}

  buildStyleTreeFacet('facet-styles', FACET_STYLES_TREE, filters.styles);
  buildFacet('facet-styles-simple', FACET_STYLES_SIMPLE, filters.stylesSimple, k => SIMPLE_STYLE_LABELS[k] || k);
  document.querySelectorAll('.grape-chip-filter').forEach(container => {{
    const role = container.dataset.role || 'all';
    const set = role === 'principal' ? filters.principal
              : role === 'accessory' ? filters.accessory
              : filters.grapesAll;
    buildGrapeChipFilter(container, role, set);
  }});

  // Map of region → list of slugs, computed once. The appellation tree
  // re-renders on spirits-toggle (entries appear/disappear), but the
  // per-region grouping itself is stable across rebuilds.
  const REGION_SLUGS = (() => {{
    const m = new Map();
    const order = FACET_REGIONS.map(([r]) => r);
    for (const r of order) m.set(r, []);
    m.set('', []);
    for (const slug in AOCS) {{
      const r = AOCS[slug].region || '';
      if (!m.has(r)) m.set(r, []);
      m.get(r).push(slug);
    }}
    for (const arr of m.values()) {{
      arr.sort((a, b) => AOCS[a].name.localeCompare(AOCS[b].name, 'fr'));
    }}
    return m;
  }})();

  function visibleSlugsInRegion(region) {{
    const all = REGION_SLUGS.get(region) || [];
    if (spiritsVisible()) return all;
    return all.filter(s => AOCS[s].is_wine !== false);
  }}

  function setRegionSelection(region, on) {{
    const slugs = visibleSlugsInRegion(region);
    for (const s of slugs) {{
      if (on) filters.appellations.add(s);
      else filters.appellations.delete(s);
    }}
  }}

  function regionTriState(region) {{
    const slugs = visibleSlugsInRegion(region);
    if (!slugs.length) return 'empty';
    let n = 0;
    for (const s of slugs) if (filters.appellations.has(s)) n++;
    if (n === 0) return 'unchecked';
    if (n === slugs.length) return 'checked';
    return 'indeterminate';
  }}

  function buildAppellationFacet() {{
    const el = document.getElementById('facet-appellations');
    const html = [];
    for (const [region, allSlugs] of REGION_SLUGS) {{
      const slugs = spiritsVisible() ? allSlugs : allSlugs.filter(s => AOCS[s].is_wine !== false);
      if (!slugs.length) continue;
      const label = region ? regionLabel(region) : LABELS.meta_no_region;
      const items = slugs.map(slug => {{
        const safeSlug = escapeAttr(slug);
        const rec = AOCS[slug];
        const nameHtml = nameWithLatin(rec);
        const checked = filters.appellations.has(slug) ? ' checked' : '';
        return `<label data-slug="${{safeSlug}}" data-name="${{escapeAttr(searchableText(rec))}}"><input type="checkbox" data-key="${{safeSlug}}"${{checked}}><span class="name">${{nameHtml}}</span></label>`;
      }}).join('');
      const safeRegion = escapeAttr(region);
      // Checkbox lives outside `<summary>` (sibling of `<details>`,
      // not a descendant) so the nested-interactive-in-summary
      // accessibility warning doesn't fire. Visual layout is restored
      // via `.region-group-wrap`'s flex rule — checkbox + disclosure
      // sit in the same row.
      html.push(`<div class="region-group-wrap" data-region="${{safeRegion}}"><input type="checkbox" class="region-select" data-region="${{safeRegion}}" aria-label="${{escapeAttr(LABELS.select_all_aria)}}"><details class="region-group" data-region="${{safeRegion}}"><summary><span class="name">${{escapeHtml(label)}}</span><span class="count">${{slugs.length}}</span></summary><div class="region-items">${{items}}</div></details></div>`);
    }}
    el.innerHTML = html.join('');
    // Reapply current search visibility (so a tree rebuild during a typed
    // query keeps the filtered view).
    refreshFacetVisibility('facet-appellations', filters.q);
    refreshRegionTriStates();
  }}

  // Single delegated listener — buildAppellationFacet may run multiple
  // times (mode swap, spirits toggle), so the handler stays on the
  // container instead of being re-attached each time.
  document.getElementById('facet-appellations').addEventListener('change', e => {{
    const el = document.getElementById('facet-appellations');
    if (e.target.tagName !== 'INPUT') return;
    if (e.target.classList.contains('region-select')) {{
      const region = e.target.dataset.region;
      setRegionSelection(region, e.target.checked);
      for (const inp of el.querySelectorAll(
        `.region-group[data-region="${{CSS.escape(region)}}"] .region-items input[type=checkbox]`
      )) {{
        inp.checked = filters.appellations.has(inp.dataset.key);
      }}
      if (e.target.checked) {{
        track('Filter Applied', {{ facet: 'region', value: region || '(none)', locale: LANG }});
      }}
    }} else {{
      const k = e.target.dataset.key;
      if (e.target.checked) filters.appellations.add(k); else filters.appellations.delete(k);
      if (e.target.checked) {{
        track('Filter Applied', {{ facet: 'appellation', value: k, locale: LANG }});
      }}
    }}
    refreshRegionTriStates();
    applyFilter({{ fit: true }});
  }});

  function refreshRegionTriStates() {{
    const el = document.getElementById('facet-appellations');
    if (!el) return;
    el.querySelectorAll('.region-group').forEach(group => {{
      const region = group.dataset.region;
      // `.region-select` is a sibling of `.region-group` inside the
      // `.region-group-wrap`, not a descendant. Reach via the parent.
      const cb = (group.parentElement || group).querySelector('.region-select');
      if (!cb) return;
      const state = regionTriState(region);
      cb.checked = state === 'checked';
      cb.indeterminate = state === 'indeterminate';
    }});
  }}

  function refreshFacetVisibility(containerId, q) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    const nq = searchNormalize(q);
    // Appellation tree: groups + labels with data-name dataset.
    const groups = el.querySelectorAll('.region-group');
    if (groups.length) {{
      groups.forEach(group => {{
        let visible = 0;
        group.querySelectorAll('label').forEach(lbl => {{
          const match = !nq || lbl.dataset.name.includes(nq);
          lbl.style.display = match ? '' : 'none';
          if (match) visible++;
        }});
        const wrap = group.parentElement;
        if (wrap && wrap.classList.contains('region-group-wrap')) {{
          wrap.style.display = visible ? '' : 'none';
        }} else {{
          group.style.display = visible ? '' : 'none';
        }}
        if (nq && visible) group.open = true;
      }});
      return;
    }}
    // Flat facet (grapes etc.) — match against the .name span text.
    el.querySelectorAll('label').forEach(lbl => {{
      const span = lbl.querySelector('.name');
      const text = searchNormalize(span ? span.textContent : '');
      lbl.style.display = (!nq || text.includes(nq)) ? '' : 'none';
    }});
  }}

  buildAppellationFacet();

  function applyMode() {{
    document.documentElement.classList.toggle('mode-simple', viewMode === 'simple');
    document.documentElement.classList.toggle('mode-advanced', viewMode === 'advanced');
    document.querySelectorAll('#mode-toggle .mode-btn').forEach(b => {{
      const on = b.dataset.mode === viewMode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    }});
    document.querySelectorAll('#sidebar [data-modes]').forEach(el => {{
      const modes = el.dataset.modes.split(/\\s+/);
      el.classList.toggle('mode-hidden', !modes.includes(viewMode));
    }});
    swapMapLayers();
    // The appellation tree's contents depend on spiritsVisible(), which
    // depends on viewMode — rebuild on every mode switch.
    if (document.getElementById('facet-appellations').children.length) {{
      buildAppellationFacet();
    }}
  }}

  function swapMapLayers() {{
    const advLayers = ['appellations-fill', 'appellations-outline'];
    const vilLayers = ['appellations-fill-villages', 'appellations-outline-villages'];
    const showAdv = viewMode === 'advanced';
    for (const id of advLayers) {{
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', showAdv ? 'visible' : 'none');
    }}
    for (const id of vilLayers) {{
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', showAdv ? 'none' : 'visible');
    }}
  }}

  document.querySelectorAll('#mode-toggle .mode-btn').forEach(b => {{
    b.addEventListener('click', () => {{
      const next = b.dataset.mode;
      if (next === viewMode) return;
      viewMode = next;
      try {{ localStorage.setItem('view_mode', viewMode); }} catch (e) {{}}
      track('View Mode Switched', {{ mode: viewMode, locale: LANG }});
      applyMode();
      applyFilter({{ fit: true }});
    }});
  }});

  const igpEl = document.getElementById('show-igp');
  igpEl.checked = showIgp;
  igpEl.addEventListener('change', e => {{
    showIgp = e.target.checked;
    try {{ localStorage.setItem('show_igp', showIgp ? '1' : '0'); }} catch (err) {{}}
    track('Kind Toggled', {{ kind: 'igp', enabled: showIgp ? 'true' : 'false', locale: LANG }});
    applyFilter({{ fit: true }});
  }});

  const spiritsEl = document.getElementById('show-spirits');
  spiritsEl.checked = showSpirits;
  spiritsEl.addEventListener('change', e => {{
    showSpirits = e.target.checked;
    try {{ localStorage.setItem('show_spirits', showSpirits ? '1' : '0'); }} catch (err) {{}}
    track('Kind Toggled', {{ kind: 'spirits', enabled: showSpirits ? 'true' : 'false', locale: LANG }});
    // Spirit AOCs join/leave the appellation tree; rebuild + reapply.
    buildAppellationFacet();
    applyFilter({{ fit: true }});
  }});

  // The merged Appellation facet hosts the appellation search; typing in
  // it auto-expands the section if collapsed, since otherwise the tree
  // updates would be invisible to the user.
  const qInput = document.getElementById('q');
  // Debounced search analytics: fire once after the user stops typing.
  // We send result_count / had_match / query_len only — never the raw
  // string, since search boxes attract typos, names, and assorted junk.
  let searchTrackTimer = null;
  qInput.addEventListener('input', e => {{
    filters.q = e.target.value.trim();
    refreshFacetVisibility('facet-appellations', filters.q);
    const det = qInput.closest('details');
    if (filters.q && det && !det.open) det.open = true;
    if (searchTrackTimer) clearTimeout(searchTrackTimer);
    if (filters.q) {{
      searchTrackTimer = setTimeout(() => {{
        const nq = searchNormalize(filters.q);
        let n = 0;
        for (const slug in AOCS) {{
          if (searchableText(AOCS[slug]).includes(nq)) n++;
        }}
        track('Search Used', {{
          result_count: String(n),
          had_match: n > 0 ? 'true' : 'false',
          query_len: String(filters.q.length),
          locale: LANG,
        }});
      }}, 1000);
    }}
  }});

  // Per-facet search inputs (cépages). They filter only the visible
  // checkboxes in their target facet; they do not affect the map filter.
  document.querySelectorAll('.facet-search[data-facet]').forEach(input => {{
    input.addEventListener('input', e => {{
      refreshFacetVisibility(input.dataset.facet, e.target.value.trim());
    }});
  }});

  document.getElementById('reset').addEventListener('click', () => {{
    track('Filters Reset', {{ locale: LANG }});
    filters.q = '';
    filters.styles.clear(); filters.stylesSimple.clear();
    filters.principal.clear(); filters.accessory.clear(); filters.grapesAll.clear();
    filters.appellations.clear();
    document.querySelectorAll('#sidebar .facet input[type=checkbox]').forEach(c => {{
      c.checked = false;
      c.indeterminate = false;
    }});
    document.querySelectorAll('.facet-search').forEach(i => {{ i.value = ''; }});
    refreshFacetVisibility('facet-appellations', '');
    refreshFacetVisibility('facet-grapes-all', '');
    refreshFacetVisibility('facet-principal', '');
    refreshFacetVisibility('facet-accessory', '');
    applyFilter();
  }});

  // ----- detail panel -----
  const panel = document.getElementById('panel');
  const panelBody = document.getElementById('panel-body');

  function renderSources(slug, sources) {{
    if (!sources) sources = {{}};
    const links = [];
    if (sources.boagri) {{
      const homo = sources.homologation_date ? ' — ' + LABELS.src_homologated + ' ' + escapeHtml(sources.homologation_date) : '';
      const jorf = sources.jorf_date ? ', ' + LABELS.src_jorf + ' ' + escapeHtml(sources.jorf_date) : '';
      links.push(`<li><a href="${{escapeAttr(sources.boagri)}}" target="_blank" rel="noopener">${{LABELS.src_cahier}}</a>${{homo}}${{jorf}}</li>`);
    }}
    if (sources.show_texte) {{
      links.push(`<li><a href="${{escapeAttr(sources.show_texte)}}" target="_blank" rel="noopener">${{LABELS.src_show_texte}}</a></li>`);
    }}
    if (sources.product) {{
      links.push(`<li><a href="${{escapeAttr(sources.product)}}" target="_blank" rel="noopener">${{LABELS.src_product}}</a></li>`);
    }}
    if (sources.eur_lex_url) {{
      links.push(`<li><a href="${{escapeAttr(sources.eur_lex_url)}}" target="_blank" rel="noopener">${{LABELS.src_eur_lex}}</a></li>`);
    }}
    if (sources.national_pliego_url) {{
      const added = (sources.national_pliego_added_slugs || []).length;
      const note = added ? ' — +' + added + ' ' + LABELS.src_national_pliego_added : '';
      links.push(`<li><a href="${{escapeAttr(sources.national_pliego_url)}}" target="_blank" rel="noopener">${{LABELS.src_national_pliego}}</a>${{note}}</li>`);
    }}
    if (sources.national_spec_url) {{
      const org = sources.national_spec_source_org ? ' — ' + escapeHtml(sources.national_spec_source_org) : '';
      links.push(`<li><a href="${{escapeAttr(sources.national_spec_url)}}" target="_blank" rel="noopener">${{LABELS.src_national_spec}}</a>${{org}}</li>`);
    }}
    if (sources.chzo_spec_url) {{
      const reg = sources.chzo_spec_region ? ' — ' + escapeHtml(sources.chzo_spec_region) : '';
      const org = sources.chzo_spec_source_org ? ' (' + escapeHtml(sources.chzo_spec_source_org.toUpperCase()) + ')' : '';
      links.push(`<li><a href="${{escapeAttr(sources.chzo_spec_url)}}" target="_blank" rel="noopener">${{LABELS.src_chzo_spec}}</a>${{reg}}${{org}}</li>`);
    }}
    if (sources.regional_register_url) {{
      const reg = sources.regional_register_region ? ' — ' + escapeHtml(sources.regional_register_region) : '';
      links.push(`<li><a href="${{escapeAttr(sources.regional_register_url)}}" target="_blank" rel="noopener">${{LABELS.src_regional_register}}</a>${{reg}}</li>`);
    }}
    if (sources.id_eambrosia) {{
      const eambrosiaUrl = `https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/${{encodeURIComponent(sources.id_eambrosia)}}`;
      const fileNum = sources.file_number ? ' — ' + LABELS.src_eambrosia_id + ' ' + escapeHtml(sources.file_number) : '';
      links.push(`<li><a href="${{escapeAttr(eambrosiaUrl)}}" target="_blank" rel="noopener">${{LABELS.src_eambrosia}}</a>${{fileNum}}</li>`);
    }}
    if (sources.syndicate && sources.syndicate.url) {{
      const syLabel = sources.syndicate.label ? ' — ' + escapeHtml(sources.syndicate.label) : '';
      links.push(`<li><a href="${{escapeAttr(sources.syndicate.url)}}" target="_blank" rel="noopener">${{LABELS.src_syndicate}}</a>${{syLabel}}</li>`);
    }}
    return '<h2>' + LABELS.panel_sources_h + '</h2><ul class="sources">' + links.join('') + '</ul>';
  }}

  function escapeAttr(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  }}

  function frMarker() {{
    return LANG === 'fr'
      ? ''
      : ` <span class="fr-marker" title="${{escapeAttr(LABELS.fr_marker_aria)}}">${{escapeHtml(LABELS.fr_marker)}}</span>`;
  }}

  function srcMarker(country) {{
    const sourceLang = (country === 'es' || country === 'pt') ? country : 'fr';
    if (LANG === sourceLang) return '';
    const text = country === 'es' ? LABELS.es_marker
      : country === 'pt' ? (LABELS.pt_marker || LABELS.fr_marker)
      : LABELS.fr_marker;
    const aria = country === 'es' ? LABELS.es_marker_aria
      : country === 'pt' ? (LABELS.pt_marker_aria || LABELS.fr_marker_aria)
      : LABELS.fr_marker_aria;
    return ` <span class="fr-marker" title="${{escapeAttr(aria)}}">${{escapeHtml(text)}}</span>`;
  }}

  function translationAttribution(t, country) {{
    if (!t) return '';
    const labelText = country === 'es'
      ? LABELS.translation_source_label_es
      : country === 'pt'
      ? (LABELS.translation_source_label_pt || LABELS.translation_source_label)
      : LABELS.translation_source_label;
    const url = t.source_pdf_url;
    const sourceHtml = url
      ? `<a href="${{escapeAttr(url)}}" target="_blank" rel="noopener">${{escapeHtml(labelText)}}</a>`
      : escapeHtml(labelText);
    const tpl = LABELS.translation_attribution;
    const placeholder = '{{source}}';
    const idx = tpl.indexOf(placeholder);
    const pre = idx >= 0 ? tpl.slice(0, idx) : (tpl + ' ');
    const post = idx >= 0 ? tpl.slice(idx + placeholder.length) : '';
    return `<p class="translation-attr">${{escapeHtml(pre)}}${{sourceHtml}}${{escapeHtml(post)}}</p>`;
  }}

  const FACTS_SUB_ORDER = ['facteurs_naturels', 'facteurs_humains', 'produit', 'interactions'];
  const FACTS_SUB_LABELS = {{
    facteurs_naturels: LABELS.facts_sub_facteurs_naturels,
    facteurs_humains: LABELS.facts_sub_facteurs_humains,
    produit: LABELS.facts_sub_produit,
    interactions: LABELS.facts_sub_interactions,
  }};

  function buildFactsSourceLabel(country) {{
    if (country === 'es') return LABELS.facts_attribution_source_label_es;
    if (country === 'pt') return LABELS.facts_attribution_source_label_pt;
    return LABELS.facts_attribution_source_label;
  }}

  function buildFactsAttribution(tplKey, country, cahierUrl) {{
    const labelText = buildFactsSourceLabel(country);
    const sourceHtml = cahierUrl
      ? `<a href="${{escapeAttr(cahierUrl)}}" target="_blank" rel="noopener">${{escapeHtml(labelText)}}</a>`
      : escapeHtml(labelText);
    const tpl = LABELS[tplKey];
    const placeholder = '{{source}}';
    const idx = tpl.indexOf(placeholder);
    const pre = idx >= 0 ? tpl.slice(0, idx) : (tpl + ' ');
    const post = idx >= 0 ? tpl.slice(idx + placeholder.length) : '';
    return `<p class="translation-attr">${{escapeHtml(pre)}}${{sourceHtml}}${{escapeHtml(post)}}</p>`;
  }}

  function renderVerbatimFacts(r, tf) {{
    const text = tf.verbatim_text || '';
    if (!text) return '';
    const cahierUrl = tf.cahier_source_pdf_url || '';
    const flag = tf.validation_flag || '';
    const badge = flag
      ? `<span class="verbatim-badge" title="${{escapeAttr(flag)}}">${{escapeHtml(LABELS.facts_verbatim_to_verify)}}</span>`
      : '';
    const body = `<blockquote class="facts-verbatim">${{escapeHtml(text)}}</blockquote>`;
    const attribution = buildFactsAttribution('facts_verbatim_attribution', r.country, cahierUrl);
    return `<h2>${{LABELS.panel_facts_h}}${{badge ? ' ' + badge : ''}}</h2>${{body}}${{attribution}}`;
  }}

  function renderTerroirFacts(r) {{
    const tf = r.terroir_facts;
    if (!tf) return '';
    if (tf.mode === 'verbatim') return renderVerbatimFacts(r, tf);
    if (!tf.facts || !tf.facts.length) return '';
    const wikiUrl = tf.wiki_source_url || '';
    const wikiAttr = wikiUrl
      ? ` <span class="wiki-attr">(<a href="${{escapeAttr(wikiUrl)}}" target="_blank" rel="noopener">${{escapeHtml(LABELS.facts_wiki_marker)}}</a>)</span>`
      : ` <span class="wiki-attr">(${{escapeHtml(LABELS.facts_wiki_marker)}})</span>`;
    const grouped = {{}};
    for (const f of tf.facts) {{
      const k = f.subsection || 'facteurs_naturels';
      (grouped[k] = grouped[k] || []).push(f);
    }}
    const blocks = FACTS_SUB_ORDER.flatMap(k => {{
      const facts = grouped[k];
      if (!facts || !facts.length) return [];
      const items = facts.map(f => {{
        const marker = f.provenance === 'wiki' ? wikiAttr : '';
        return `<li>${{escapeHtml(f.bullet)}}${{marker}}</li>`;
      }}).join('');
      return [`<div class="facts-sub-h">${{escapeHtml(FACTS_SUB_LABELS[k] || k)}}</div><ul class="facts">${{items}}</ul>`];
    }});
    if (!blocks.length) return '';
    const attribution = buildFactsAttribution(
      'facts_attribution', r.country, tf.cahier_source_pdf_url || ''
    );
    return `<h2>${{LABELS.panel_facts_h}}</h2>${{blocks.join('')}}${{attribution}}`;
  }}

  function renderDulok(r) {{
    // HU named single-vineyards (dűlők), grouped by település, in a
    // collapsible block. Names are verbatim regulator data (not
    // translated); the termékleírás source is attributed in Sources.
    const dulok = r.dulok || [];
    if (!dulok.length) return '';
    const groups = {{}};
    const order = [];
    for (const d of dulok) {{
      const tel = d.telepules || '';
      let name = d.dulo || '';
      if (d.aldulok && d.aldulok.length) name += ' (' + d.aldulok.join(', ') + ')';
      if (!(tel in groups)) {{ groups[tel] = []; order.push(tel); }}
      groups[tel].push(name);
    }}
    const rows = order.map(tel =>
      `<div class="dulo-row"><span class="dulo-tel">${{escapeHtml(tel)}}</span> ${{
        groups[tel].map(n => escapeHtml(n)).join(', ')}}</div>`).join('');
    return `<details class="dulok"><summary>${{
      fmt(LABELS.panel_dulok_h, {{ n: dulok.length }})}}</summary>${{rows}}</details>`;
  }}

  function renderMenzioni(r) {{
    // IT menzioni geografiche aggiuntive (MGA/UGA crus) — a flat,
    // collapsible name-chip list on the parent panel. Verbatim regulator
    // data (not translated); the disciplinare is attributed in Sources.
    // No per-cru polygons: no licence-clear public GIS layer exists.
    const mz = r.menzioni || [];
    if (!mz.length) return '';
    const chips = mz.map(n =>
      `<span class="pill menzione">${{escapeHtml(toTitleCase(n))}}</span>`).join('');
    return `<details class="dulok menzioni"><summary>${{
      fmt(LABELS.panel_menzioni_h, {{ n: mz.length }})}}</summary>` +
      `<div class="menzioni-chips">${{chips}}</div></details>`;
  }}

  function renderAocCard(slug, isPrimary) {{
    const r = AOCS[slug];
    if (!r) return '';
    const styleChips = (r.styles || []).map(s => {{
      const safe = escapeAttr(s);
      const info = STYLES_INFO[s];
      const has = !!(info && info.extract);
      const cls = ['pill', 'style', `style--${{safe}}`, has ? 'has-info' : ''].filter(Boolean).join(' ');
      const label = toTitleCase(STYLE_LABELS[s] || s);
      if (has && info.page_url) {{
        return `<a class="${{cls}}" data-slug="${{safe}}" href="${{escapeAttr(info.page_url)}}" target="_blank" rel="noopener">${{label}}</a>`;
      }}
      return `<span class="${{cls}}" data-slug="${{safe}}">${{label}}</span>`;
    }}).join('');
    const grapePill = (g, cls) => {{
      const info = GRAPES_INFO[g];
      const has = !!(info && (info.extract || (info.vivc_id && info.vivc_url) || info.note));
      const cls2 = ['pill', 'grape', cls, has ? 'has-info' : ''].filter(Boolean).join(' ');
      // Title-case both the cahier spelling and the canonical bracket so
      // pills stay consistent regardless of source casing ("mourvèdre" /
      // "MOURVEDRE" → "Mourvèdre").
      const cahierName = toTitleCase((r.grape_names && r.grape_names[g]) || grapeName(g));
      // Prefer VIVC's prime name when resolved; fall back to a Latin
      // transliteration of the cahier spelling for non-Latin scripts
      // (Cyrillic / Greek native varieties that VIVC hasn't catalogued)
      // so pills still surface a readable Latin form alongside the
      // native one. Per-record `grape_names_latin` covers slugs that
      // never make it into GRAPES_INFO (no Wikipedia + no VIVC).
      const canon = (info && info.canonical_name)
        || (info && info.name_latin)
        || (r.grape_names_latin && r.grape_names_latin[g])
        || '';
      const labelInner = canon && !canonicalEqualsCahier(canon, cahierName)
        ? `${{escapeHtml(cahierName)}} <span class="canon">(${{escapeHtml(canon)}})</span>`
        : escapeHtml(cahierName);
      return `<a class="${{cls2}}" data-slug="${{escapeAttr(g)}}" href="${{escapeAttr(grapeUrl(g))}}" target="_blank" rel="noopener">${{labelInner}}</a>`;
    }};
    const principal = (r.grapes_principal || []).map(g => grapePill(g, '')).join('');
    const accessory = (r.grapes_accessory || []).map(g => grapePill(g, 'accessory')).join('');
    const observation = (r.grapes_observation || []).map(g => grapePill(g, 'observation')).join('');
    // PT cadernos enumerate every authorised casta as `principal` because
    // the IVV documento-único format doesn't carry a role split (see
    // CLAUDE.md "PT grape role classification — not published by the
    // regulator"). Surface that limitation inline under the principal
    // pills so the rendering is honest about what the regulator publishes.
    const ptRoleDisclaimer = (r.country === 'pt' && principal)
      ? `<div class="role-disclaimer">${{escapeHtml(LABELS.pt_role_disclaimer)}}</div>`
      : '';
    const klass = isPrimary ? 'aoc-card' : 'aoc-card subordinate';
    let metaTail = '';
    if (r.geom_source === 'aires-csv' || r.geom_source === 'dgc-village-override') {{
      metaTail = ' · ' + fmt(LABELS.meta_communes_inao, {{ n: r.communes_matched || 0 }});
    }} else if (
      r.geom_source !== 'parcellaire' && r.geom_source !== 'parcellaire-dgc' &&
      r.geom_source !== 'aires-csv-dgc' && r.geom_source !== 'cadastre-lieu-dit-dgc' &&
      r.geom_source !== 'sibling-dgc' && r.geom_source !== 'parent-appellation'
    ) {{
      metaTail = ' · ' + fmt(LABELS.meta_communes, {{ n: r.communes_matched || 0 }});
    }}
    const region = r.region ? regionLabel(r.region) : '';
    const regionSeg = region ? ` · ${{escapeHtml(region)}}` : '';
    const countryChip = countryChipHtml(r.country, r.country_aliases);
    const countrySeg = countryChip ? `${{countryChip}} · ` : '';
    const dgcLine = r.is_sub_denomination && r.parent_slug
      ? `<div class="dgc-line">${{escapeHtml(LABELS.dgc_of)}} <a class="parent-link" data-slug="${{escapeAttr(r.parent_slug)}}" href="#">${{escapeHtml(r.parent_name || r.parent_slug)}}</a></div>`
      : '';
    let approxLine = '';
    if (r.geom_source === 'sibling-dgc' && r.geom_fallback_slug) {{
      const u = `<a class="parent-link" data-slug="${{escapeAttr(r.geom_fallback_slug)}}" href="#">${{escapeHtml(r.geom_fallback_name || r.geom_fallback_slug)}}</a>`;
      approxLine = `<div class="approx-line">${{fmt(LABELS.geom_approx_within, {{ umbrella: u }})}}</div>`;
    }} else if (r.geom_source === 'parent-appellation') {{
      approxLine = `<div class="approx-line">${{escapeHtml(LABELS.geom_approx_parent)}}</div>`;
    }} else if (r.geom_source === 'aires-csv-dgc') {{
      approxLine = `<div class="approx-line">${{escapeHtml(LABELS.geom_approx_aires)}}</div>`;
    }} else if (r.geom_source === 'cadastre-lieu-dit-dgc' && r.cadastre_lieu_dit) {{
      const src = `<a href="https://cadastre.data.gouv.fr/" target="_blank" rel="noopener">${{escapeHtml(LABELS.geom_approx_cadastre_source_label)}}</a>`;
      approxLine = `<div class="approx-line">${{fmt(LABELS.geom_approx_cadastre, {{ lieu_dit: escapeHtml(r.cadastre_lieu_dit), commune: escapeHtml(r.cadastre_commune || ''), source: src }})}}</div>`;
    }}
    const stubLine = r.is_stub
      ? `<div class="approx-line">${{fmt(LABELS.stub_message, {{ doc: '<em>' + escapeHtml(STUB_DOC_NAMES[r.country] || STUB_DOC_NAMES.fr) + '</em>' }})}}</div>`
      : '';
    const dulokBlock = renderDulok(r);
    const menzioniBlock = renderMenzioni(r);
    const factsBlock = renderTerroirFacts(r);
    const isTranslated = !!r.summary_translation;
    const summaryMarker = isTranslated ? '' : srcMarker(r.country);
    const summary = (!factsBlock && r.summary)
      ? `<p>${{escapeHtml(r.summary)}}${{summaryMarker}}</p>${{translationAttribution(r.summary_translation, r.country)}}`
      : '';
    // Curated, source-cited cross-border note (e.g. Teran SI/HR). Only a
    // handful of appellations carry one — see _lib/appellation_notes.json.
    const noteBlock = (r.note && r.note.text)
      ? `<div class="appellation-note"><div class="note-text">ⓘ ${{escapeHtml(r.note.text)}}</div>${{
          (r.note.sources && r.note.sources.length)
            ? '<div class="note-srcs">' + r.note.sources.map(s =>
                `<a href="${{escapeAttr(s.url)}}" target="_blank" rel="noopener">${{escapeHtml(s.label)}}</a>`).join('') + '</div>'
            : ''
        }}</div>`
      : '';
    return `
      <div class="${{klass}}">
        <h1>${{nameWithLatin(r)}}</h1>
        <div class="meta">${{countrySeg}}${{r.kind}}${{regionSeg}}${{metaTail}}</div>
        ${{dgcLine}}
        ${{approxLine}}
        ${{stubLine}}
        ${{styleChips ? '<h2>' + LABELS.panel_styles_h + '</h2><div class="pills">' + styleChips + '</div>' : ''}}
        ${{principal ? '<h2>' + LABELS.facet_principal_h + '</h2><div class="pills">' + principal + '</div>' : ''}}
        ${{ptRoleDisclaimer}}
        ${{accessory ? '<h2>' + LABELS.facet_accessory_h + '</h2><div class="pills">' + accessory + '</div>' : ''}}
        ${{observation ? '<h2>' + LABELS.panel_observation_h + '</h2><div class="pills">' + observation + '</div>' : ''}}
        ${{factsBlock || summary}}
        ${{dulokBlock}}
        ${{menzioniBlock}}
        ${{noteBlock}}
        ${{renderSources(slug, r.sources)}}
      </div>
    `;
  }}

  function bboxArea(b) {{
    if (!b || b.length < 4) return Infinity;
    const w = b[2] - b[0], h = b[3] - b[1];
    return w > 0 && h > 0 ? w * h : Infinity;
  }}

  function localityRank(slug) {{
    // Sort key: bounding-box area of the rendered geometry, mode-aware.
    // Bbox area penalises spread-out multipolygons (parent cuvée
    // covering every premier-cru fragment in a region) so a localised
    // climat outranks a scattered parent even when the parent's total
    // polygon area is smaller.
    const r = AOCS[slug];
    if (!r) return Infinity;
    const primary = viewMode === 'advanced' ? r.bbox : r.bbox_villages;
    const fallback = viewMode === 'advanced' ? r.bbox_villages : r.bbox;
    const a = bboxArea(primary);
    return Number.isFinite(a) ? a : bboxArea(fallback);
  }}

  function renderPanelStack(slugs, focusIndex) {{
    if (!slugs.length) return;
    const sorted = slugs
      .filter(s => AOCS[s])
      .sort((a, b) => localityRank(a) - localityRank(b));
    if (!sorted.length) return;
    const focus = ((((focusIndex | 0) % sorted.length) + sorted.length) % sorted.length);
    const ordered = focus === 0
      ? sorted
      : [sorted[focus], ...sorted.filter((_, i) => i !== focus)];
    let header = '';
    if (sorted.length > 1) {{
      const pos = `<span class="stack-pos" title="${{escapeAttr(LABELS.stack_cycle_hint)}}">${{focus + 1}} / ${{sorted.length}}</span>`;
      header = `<div class="stack-header"><span>${{fmt(LABELS.stack_header, {{ n: sorted.length }})}}</span>${{pos}}</div>`;
    }}
    panelBody.innerHTML = header + ordered.map((s, i) => renderAocCard(s, i === 0)).join('');
    panel.classList.add('open');
    setSelection(ordered.slice(0, 1));
  }}

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  }}

  // ----- selection highlight + persistence (across reload / language switch) -----
  // Selection is mirrored into both `appellations` (advanced/parcellaire) and
  // `appellations-villages` (simple/commune) sources so the highlight follows
  // the user across mode toggles. setFeatureState calls before map.on('load')
  // throw because the source isn't registered yet — we swallow and re-apply
  // at the end of map.on('load').
  let selectedSlugs = [];

  // Cycling: clicking on the same overlap rotates focus through the stack.
  // Key is the deduped slug set (order-independent) so the user can wobble
  // a few pixels and still cycle; moving to a different overlap resets.
  let lastStackKey = '';
  let stackFocusIndex = 0;

  function setSelectedState(slug, selected) {{
    for (const source of ['appellations', 'appellations-villages']) {{
      const opts = {{ source: source, id: slug }};
      if (SOURCE_TYPE === 'pmtiles') opts.sourceLayer = 'appellations';
      try {{ map.setFeatureState(opts, {{ selected: selected }}); }} catch (e) {{}}
    }}
  }}

  function setSelection(slugs) {{
    for (const s of selectedSlugs) setSelectedState(s, false);
    selectedSlugs = slugs.slice();
    for (const s of selectedSlugs) setSelectedState(s, true);
    try {{
      if (selectedSlugs.length) localStorage.setItem('selected_slugs', JSON.stringify(selectedSlugs));
      else localStorage.removeItem('selected_slugs');
    }} catch (e) {{}}
  }}

  // Restore previously open detail panel after a language switch / reload.
  (function () {{
    let saved = null;
    try {{ saved = localStorage.getItem('selected_slugs'); }} catch (e) {{}}
    if (!saved) return;
    let slugs;
    try {{ slugs = JSON.parse(saved); }} catch (e) {{ return; }}
    if (!Array.isArray(slugs) || !slugs.length) return;
    const valid = slugs.filter(s => AOCS[s]);
    if (!valid.length) return;
    renderPanelStack(valid);
  }})();

  document.querySelector('#panel .close').addEventListener('click', () => {{
    panel.classList.remove('open');
    setSelection([]);
    lastStackKey = '';
    stackFocusIndex = 0;
  }});

  // ----- pill tooltip (Wikipedia, CC BY-SA 4.0) — grapes + styles -----
  const grapeTip = document.createElement('div');
  grapeTip.id = 'grape-tooltip';
  document.body.appendChild(grapeTip);
  let grapeTipCloseTimer = null;
  const cancelGrapeTipClose = () => {{
    if (grapeTipCloseTimer) {{ clearTimeout(grapeTipCloseTimer); grapeTipCloseTimer = null; }}
  }};
  const scheduleGrapeTipClose = () => {{
    cancelGrapeTipClose();
    grapeTipCloseTimer = setTimeout(() => {{ grapeTip.style.display = 'none'; grapeTipCloseTimer = null; }}, 150);
  }};
  grapeTip.addEventListener('mouseenter', cancelGrapeTipClose);
  grapeTip.addEventListener('mouseleave', scheduleGrapeTipClose);

  function positionGrapeTip(el) {{
    const r = el.getBoundingClientRect();
    const top = (r.bottom + 220 > window.innerHeight) ? (r.top - grapeTip.offsetHeight - 6) : (r.bottom + 6);
    const left = Math.min(Math.max(8, r.left), window.innerWidth - grapeTip.offsetWidth - 8);
    grapeTip.style.top = Math.max(8, top) + 'px';
    grapeTip.style.left = left + 'px';
  }}

  function resolvePillInfo(el) {{
    if (el.matches('a.pill.grape.has-info')) {{
      const info = GRAPES_INFO[el.dataset.slug];
      if (!info) return null;
      if (!info.extract && !(info.vivc_id && info.vivc_url) && !info.note) return null;
      return {{ info, url: info.page_url || grapeUrl(el.dataset.slug) }};
    }}
    if (el.matches('.pill.style.has-info')) {{
      const info = STYLES_INFO[el.dataset.slug];
      if (!info || !info.extract) return null;
      return {{ info, url: info.page_url || '' }};
    }}
    return null;
  }}

  panel.addEventListener('mouseover', e => {{
    const el = e.target.closest('a.pill.grape.has-info, .pill.style.has-info');
    if (!el) return;
    const resolved = resolvePillInfo(el);
    if (!resolved) return;
    const {{ info, url }} = resolved;
    const safeUrl = escapeAttr(url);
    const hasExtract = !!info.extract;
    const thumb = (hasExtract && info.thumbnail)
      ? `<img class="thumb" src="${{escapeAttr(info.thumbnail)}}" alt="">` : '';
    // Two translation paths now feed the source-block:
    //   1. info.translation — legacy styles path (raw/translations/styles/)
    //   2. info.is_translated — grapes path (raw/translations/grapes/),
    //      with source_lang on the entry itself.
    const tx = info.translation;
    const grapeTranslated = !tx && info.is_translated && info.source_lang;
    let srcBlock = '';
    if (hasExtract) {{
      if (tx || grapeTranslated) {{
        const srcLang = tx ? tx.source_lang : info.source_lang;
        const srcUrl = (tx ? tx.source_page_url : info.page_url) || url;
        const wikiLabel = LABELS['wiki_lang_' + srcLang]
          || ('Wikipedia ' + (srcLang || '').toUpperCase());
        const wikiLink = srcUrl
          ? `<a href="${{escapeAttr(srcUrl)}}" target="_blank" rel="noopener">${{escapeHtml(wikiLabel)}}</a>`
          : escapeHtml(wikiLabel);
        srcBlock = LABELS.tooltip_translated_from.replace('{{wiki}}', wikiLink);
      }} else {{
        const srcLink = url
          ? `<a href="${{safeUrl}}" target="_blank" rel="noopener">Wikipedia</a>`
          : 'Wikipedia';
        srcBlock = `via ${{srcLink}} · CC BY-SA 4.0${{info.thumbnail ? ' · image: Wikimedia Commons' : ''}}`;
      }}
    }}
    if (info.vivc_id && info.vivc_url) {{
      const vivcLabel = LABELS.vivc_link_label.replace('{{id}}', info.vivc_id);
      const vivcLink = `<a href="${{escapeAttr(info.vivc_url)}}" target="_blank" rel="noopener" title="${{escapeAttr(LABELS.vivc_link_title)}}">${{escapeHtml(vivcLabel)}}</a>`;
      srcBlock += srcBlock ? ` · ${{vivcLink}}` : vivcLink;
    }}
    const extPara = hasExtract ? `<p class="ext">${{escapeHtml(info.extract)}}</p>` : '';
    const notePara = info.note ? `<p class="note">${{escapeHtml(info.note)}}</p>` : '';
    const srcDiv = srcBlock ? `<div class="src">${{srcBlock}}</div>` : '';
    grapeTip.innerHTML = thumb + extPara + notePara + srcDiv;
    cancelGrapeTipClose();
    grapeTip.style.display = 'block';
    positionGrapeTip(el);
  }});

  panel.addEventListener('mouseout', e => {{
    if (e.target.closest('a.pill.grape.has-info, .pill.style.has-info')) scheduleGrapeTipClose();
  }});

  panel.addEventListener('click', e => {{
    const a = e.target.closest('a.parent-link');
    if (!a) return;
    e.preventDefault();
    const slug = a.dataset.slug;
    if (slug && AOCS[slug]) {{
      lastStackKey = '';
      stackFocusIndex = 0;
      renderPanelStack([slug]);
    }}
  }});

  // ----- map interactions -----
  let hoveredSlug = null;

  map.on('load', () => {{
{source_block}
    for (const id of ['appellations-fill', 'appellations-outline',
                      'appellations-fill-villages', 'appellations-outline-villages']) {{
      map.on('mousemove', id, e => {{
        if (!e.features.length) return;
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features[0];
        const slug = f.properties.slug;
        if (slug !== hoveredSlug) hoveredSlug = slug;
      }});
      map.on('mouseleave', id, () => {{
        map.getCanvas().style.cursor = '';
        hoveredSlug = null;
      }});
    }}

    // Single map-level click handler. Per-layer click handlers fired multiple
    // times at boundaries (fill + outline), and the last handler's
    // setSelection won — making the same spot select different things. Hit-
    // testing once at the click point gives one deterministic feature set,
    // and an empty hit becomes "click outside → deselect".
    map.on('click', e => {{
      // 4-pixel bbox around the click — vineyard polygons (grand-cru
      // climats, narrow premier-cru slivers) are often sub-pixel thin at
      // typical zoom; a point-only hit-test misses them.
      const r = 4;
      const bbox = [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
      const features = map.queryRenderedFeatures(bbox, {{
        layers: ['appellations-fill', 'appellations-fill-villages'],
      }});
      if (!features.length) {{
        panel.classList.remove('open');
        setSelection([]);
        lastStackKey = '';
        stackFocusIndex = 0;
        return;
      }}
      // Dedupe by slug, and drop DGCs that share another AOC's polygon
      // (geom_source = parent-appellation / sibling-dgc). They're returned
      // because the underlying geometry was inherited, but they have no
      // distinct shape to click on — selecting one gold-outlines the whole
      // parent and clutters the panel stack with siblings nobody pointed at.
      const seen = new Set();
      const slugs = [];
      for (const f of features) {{
        const s = f.properties.slug;
        if (!s || seen.has(s)) continue;
        seen.add(s);
        const rec = AOCS[s];
        const src = rec && rec.geom_source;
        if (src === 'parent-appellation' || src === 'sibling-dgc') continue;
        slugs.push(s);
      }}
      if (!slugs.length) {{
        panel.classList.remove('open');
        setSelection([]);
        lastStackKey = '';
        stackFocusIndex = 0;
        return;
      }}
      const key = slugs.slice().sort().join('|');
      if (key === lastStackKey && slugs.length > 1) {{
        stackFocusIndex = (stackFocusIndex + 1) % slugs.length;
      }} else {{
        lastStackKey = key;
        stackFocusIndex = 0;
      }}
      renderPanelStack(slugs, stackFocusIndex);
    }});

    // Re-apply feature-state for any selection restored from localStorage
    // before sources existed. Safe no-op when nothing is selected.
    for (const s of selectedSlugs) setSelectedState(s, true);

    applyMode();
    applyFilter();
    updateStatus();
  }});
</script>
</body>
</html>
"""
