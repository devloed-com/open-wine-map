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
    """Style-tag → translatable label. Mirrors the same set in 03_generate_wiki.py
    (which stays French — wiki .md files are not localised)."""
    return {
        "red": _("rouge"),
        "white": _("blanc"),
        "rose": _("rosé"),
        "sparkling": _("mousseux"),
        "tranquille": _("tranquille"),
        "sweet": _("moelleux"),
        "dry": _("sec"),
        "vdn": _("vin doux naturel"),
        "vin-de-liqueur": _("vin de liqueur"),
        "vin-jaune": _("vin jaune"),
        "vin-de-paille": _("vin de paille"),
        "vendanges-tardives": _("vendanges tardives"),
        "grains-nobles": _("grains nobles"),
        "primeur": _("primeur"),
        "clairet": _("clairet"),
        "cremant": _("crémant"),
    }


def build_labels(_: Callable[[str], str]) -> dict[str, str]:
    """All translatable UI strings for the map. msgid is the French source."""
    return {
        "page_title": _("open wine map — carte des appellations"),
        "subtitle": _("carte des appellations françaises"),
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
        "close_aria": _("Fermer"),
        "panel_styles_h": _("Styles"),
        "panel_categories_h": _("Catégories INAO"),
        "panel_observation_h": _("Variétés d'intérêt"),
        "panel_sources_h": _("Sources"),
        "meta_no_region": _("sans région"),
        "meta_geom_parcellaire": _("géométrie parcellaire"),
        "meta_communes_inao": _("{n} commune(s) INAO"),
        "meta_communes": _("{n} commune(s)"),
        "stack_header": _("{n} appellations à ce point — du plus spécifique au plus large"),
        "src_cahier": _("Cahier des charges (BO Agri, PDF)"),
        "src_homologated": _("homologué"),
        "src_jorf": _("JORF"),
        "src_show_texte": _("Texte officiel INAO (show_texte)"),
        "src_product": _("Fiche produit INAO"),
        "legend_h": _("Légende couleurs"),
        "legend_bassin_h": _("Bassin viticole"),
        "legend_area_hint": _("Plus l'aire est petite, plus la teinte est dense."),
        "legend_grapes_h": _("Cépages"),
        "legend_principal": _("principal — variété de la cuvée"),
        "legend_accessory": _("accessoire — assemblage limité"),
        "legend_observation": _("intérêt — observation/conservation"),
        "fr_marker": _("(français)"),
        "fr_marker_aria": _("Texte source en français"),
        "sidebar_toggle_aria": _("Filtres"),
        "translation_attribution": _("Traduction automatique depuis {source}"),
        "translation_source_label": _("le cahier des charges"),
        "dgc_of": _("Dénomination géographique complémentaire de"),
        "about_link_label": _("À propos"),
        "about_h": _("À propos d'open wine map"),
        "about_made_by_html": _("Réalisé avec ♡ par {devloed}."),
        "about_data_html": _(
            "Données publiques de l'INAO ({inao}) et de l'IGN ({ign}). "
            "Détails et licences dans le {readme}."
        ),
        "about_contrib_html": _("Suggestions et pull requests bienvenues sur {github}."),
        "about_future_html": _("Sera progressivement étendu à d'autres pays."),
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


# Per-bassin underlay colour. Hand-picked muted palette (Set3-derived) so the
# wine bassins are distinguishable on a CartoDB Voyager basemap and survive a
# deuteranopia/protanopia simulation. Spirit-only bassins (COGNAC, ARMAGNAC,
# RHUM, EAUX-DE-VIE DE CIDRE — Normandy/Brittany cider+calvados country) are
# omitted: they fall through to the match-expression default (transparent),
# so the underlay doesn't tint regions whose appellations are non-wine. The
# spirit AOCs themselves still render normally when the Advanced spirits
# toggle is on.
_BASSIN_COLOURS: dict[str, str] = {
    "BOURGOGNE": "#fdb462",
    "ALSACE ET EST": "#80b1d3",
    "VAL DE LOIRE": "#b3de69",
    "SUD-OUEST": "#fb8072",
    "VALLEE DU RHÔNE": "#bebada",
    "LANGUEDOC-ROUSSILLON": "#ffed6f",
    "TOULOUSE-PYRENEES": "#ccebc5",
    "PROVENCE-CORSE": "#fccde5",
    "CHAMPAGNE": "#d9d9d9",
    "VIN DOUX NATURELS": "#8dd3c7",
}


_GITHUB_URL = "https://github.com/devloed-com/open-wine-map"
_DEVLOED_URL = "https://devloed.com"
_INAO_URL = "https://www.inao.gouv.fr/"
_IGN_URL = "https://www.ign.fr/"


def _ext_link(url: str, label: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'


def _build_about_dialog(labels: dict[str, str]) -> str:
    devloed = _ext_link(_DEVLOED_URL, "devloed.com")
    github = _ext_link(_GITHUB_URL, "GitHub")
    inao = _ext_link(_INAO_URL, "INAO")
    ign = _ext_link(_IGN_URL, "IGN")
    readme = _ext_link(_GITHUB_URL + "#public-data-sources", "README")
    paragraphs = [
        labels["about_made_by_html"].format(devloed=devloed),
        labels["about_data_html"].format(inao=inao, ign=ign, readme=readme),
        labels["about_contrib_html"].format(github=github),
        labels["about_future_html"],
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


def _lang_switcher(active: str) -> str:
    parts = []
    for code, label in _LOCALES_DISPLAY:
        path = "map.html" if code == "fr" else f"map.{code}.html"
        cls = " active" if code == active else ""
        parts.append(
            f'<a href="{path}" data-href="{path}" data-lang="{code}" class="lang{cls}">{label}</a>'
        )
    return '<div id="lang-switcher">' + "".join(parts) + "</div>"


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
            + "      paint: {\n"
            + "        'fill-color': [\n"
            + "          'case',\n"
            + "          ['boolean', ['feature-state', 'selected'], false], '#d97706',\n"
            + "          ['==', ['get', 'kind'], 'IGP'], '#5a7a4a',\n"
            + "          '#7a1f3a'\n"
            + "        ],\n"
            + "        'fill-opacity': [\n"
            + "          'case',\n"
            + "          ['boolean', ['feature-state', 'selected'], false], 0.55,\n"
            + "          ['interpolate', ['linear'], ['get', 'area'],\n"
            + f"            {area_q1}, 0.50,\n"
            + f"            {area_q3}, 0.20]\n"
            + "        ]\n"
            + "      }\n"
            + "    });\n"
            + "    map.addLayer({\n"
            + f"      id: 'appellations-outline{suffix}', type: 'line', source: '{source_id}',\n"
            + layer_meta
            + "      paint: {\n"
            + "        'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#d97706', '#3a0e1c'],\n"
            + "        'line-width': [\n"
            + "          'case',\n"
            + "          ['boolean', ['feature-state', 'selected'], false], 2.0,\n"
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
            "    });\n"
        )
        vil_decl = (
            "    map.addSource('appellations-villages', {\n"
            "      type: 'vector',\n"
            f"      url: 'pmtiles://{villages_layer_url}',\n"
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


def render(
    *,
    layer_url: str,
    villages_layer_url: str,
    source_type: str,
    aocs: dict,
    facet_styles: list[tuple[str, int]],
    facet_styles_simple: list[tuple[str, int]],
    facet_principal: list[tuple[str, int]],
    facet_accessory: list[tuple[str, int]],
    facet_grapes_all: list[tuple[str, int]],
    facet_regions: list[tuple[str, int]],
    locale: str = "fr",
    grapes_info: dict | None = None,
    area_q1: float = 0.0,
    area_q3: float = 1.0,
) -> str:
    """Render the full map.html for one locale.

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
    simple_style_buckets = {
        "red": ["red", "clairet", "primeur"],
        "white": ["white"],
        "rose": ["rose"],
        "sparkling": ["sparkling", "cremant"],
        "sweet": ["sweet", "vdn", "vin-de-liqueur", "vin-jaune", "vin-de-paille",
                  "vendanges-tardives", "grains-nobles"],
        "other": ["dry", "tranquille"],
    }

    return _TEMPLATE.format(
        lang_attr=locale,
        labels=labels,
        lang_switcher_html=_lang_switcher(locale),
        about_dialog_html=_build_about_dialog(labels),
        github_url=_GITHUB_URL,
        source_block=source_block,
        aocs_json=json.dumps(aocs, ensure_ascii=False),
        styles_json=json.dumps(facet_styles, ensure_ascii=False),
        styles_simple_json=json.dumps(facet_styles_simple, ensure_ascii=False),
        principal_json=json.dumps(facet_principal, ensure_ascii=False),
        accessory_json=json.dumps(facet_accessory, ensure_ascii=False),
        grapes_all_json=json.dumps(facet_grapes_all, ensure_ascii=False),
        regions_json=json.dumps(facet_regions, ensure_ascii=False),
        style_labels_json=json.dumps(style_labels, ensure_ascii=False),
        simple_style_labels_json=json.dumps(simple_style_labels, ensure_ascii=False),
        simple_style_buckets_json=json.dumps(simple_style_buckets, ensure_ascii=False),
        labels_json=json.dumps(labels, ensure_ascii=False),
        grapes_info_json=json.dumps(grapes_info or {}, ensure_ascii=False),
        region_labels_json=json.dumps(region_labels, ensure_ascii=False),
    )


_TEMPLATE = """<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<title>{labels[page_title]}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>
  // Locale auto-detect — runs before MapLibre or any layout work so the
  // redirect happens before paint. Sticky manual choice always wins; the
  // browser language is consulted only on the FR root with no prior choice.
  (function () {{
    var here = "{lang_attr}";
    var supported = {{ fr: 1, en: 1, es: 1, nl: 1 }};
    function pathFor(code) {{ return code === 'fr' ? 'map.html' : 'map.' + code + '.html'; }}
    function go(code) {{
      if (code === here) return;
      var hash = window.location.hash || '';
      window.location.replace(pathFor(code) + hash);
    }}
    var saved = null;
    try {{ saved = localStorage.getItem('lang_choice'); }} catch (e) {{}}
    if (saved && supported[saved] && saved !== here) {{ go(saved); return; }}
    if (here === 'fr' && !saved) {{
      var langs = (navigator.languages && navigator.languages.length)
        ? navigator.languages : [navigator.language || navigator.userLanguage || ''];
      for (var i = 0; i < langs.length; i++) {{
        var code = String(langs[i]).slice(0, 2).toLowerCase();
        if (code === 'fr') return;
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
  #sidebar h1 {{ font-size:15px; padding:14px 16px 4px; margin:0; font-weight:600; letter-spacing:0.02em }}
  #sidebar .subtitle {{ font-size:11px; color:#888; padding:0 16px 10px; border-bottom:1px solid #333 }}
  #sidebar h2 {{ font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:#888; padding:14px 16px 4px; margin:0 }}
  #sidebar input[type=text] {{ width:calc(100% - 32px); margin:0 16px 8px; padding:7px 9px; box-sizing:border-box; background:#222; color:#eee; border:1px solid #444; border-radius:3px; font-size:13px }}
  #sidebar input[type=text]:focus {{ outline:none; border-color:#7a1f3a }}
  #lang-switcher {{ display:flex; gap:2px; padding:6px 12px 8px; border-bottom:1px solid #333 }}
  #lang-switcher a {{ color:#888; font-size:11px; text-transform:uppercase; letter-spacing:0.08em; text-decoration:none; padding:3px 8px; border-radius:3px }}
  #lang-switcher a:hover {{ color:#fff }}
  #lang-switcher a.active {{ color:#d97706; background:#2a2a2a }}
  #mode-toggle {{ display:flex; gap:0; padding:8px 16px; border-bottom:1px solid #333 }}
  #mode-toggle .mode-btn {{ flex:1; background:#222; color:#888; border:1px solid #444; padding:6px 8px; cursor:pointer; font-size:12px; letter-spacing:0.04em }}
  #mode-toggle .mode-btn:first-child {{ border-radius:3px 0 0 3px }}
  #mode-toggle .mode-btn:last-child {{ border-radius:0 3px 3px 0; border-left:none }}
  #mode-toggle .mode-btn:hover {{ color:#fff }}
  #mode-toggle .mode-btn.active {{ background:#7a1f3a; color:#fff; border-color:#7a1f3a }}
  #sidebar [data-modes="simple"].mode-hidden, #sidebar [data-modes="advanced"].mode-hidden {{ display:none }}
  html.mode-simple #sidebar [data-modes="advanced"] {{ display:none }}
  html.mode-advanced #sidebar [data-modes="simple"] {{ display:none }}
  #igp-toggle {{ padding:8px 16px; border-top:1px solid #2a2a2a }}
  #igp-toggle label {{ display:flex; align-items:center; gap:6px; cursor:pointer; font-size:12.5px; color:#ddd }}
  #igp-toggle label:hover {{ color:#fff }}
  #igp-toggle input {{ accent-color:#5a7a4a }}
  #spirits-toggle {{ padding:6px 16px 10px }}
  #spirits-toggle label {{ display:flex; align-items:center; gap:6px; cursor:pointer; font-size:12.5px; color:#ddd }}
  #spirits-toggle label:hover {{ color:#fff }}
  #spirits-toggle input {{ accent-color:#a07530 }}
  #active-filters {{ display:flex; align-items:center; gap:6px; padding:8px 12px 4px; min-height:0 }}
  #active-filters:has(#active-filters-chips:empty) {{ padding-bottom:0 }}
  #active-filters-chips {{ display:flex; flex-wrap:wrap; gap:4px; flex:1 }}
  #active-filters-chips:empty {{ display:none }}
  .filter-chip {{ display:inline-flex; align-items:center; gap:4px; padding:2px 4px 2px 8px; background:#2a2a2a; color:#eee; border:1px solid #444; border-radius:11px; font-size:11px; line-height:1.3 }}
  .filter-chip.region-chip {{ border-color:#7a1f3a }}
  .filter-chip button {{ background:none; border:none; color:#888; cursor:pointer; padding:0 4px; font-size:14px; line-height:1; border-radius:50% }}
  .filter-chip button:hover {{ color:#fff; background:#444 }}
  #active-filters #reset {{ background:transparent; color:#888; border:none; padding:2px 6px; cursor:pointer; font-size:11px; text-decoration:underline; flex:0 0 auto }}
  #active-filters #reset:hover {{ color:#fff }}
  #active-filters-chips:empty + #reset {{ display:none }}
  .facet-search {{ width:calc(100% - 32px); margin:4px 16px 6px; padding:5px 8px; box-sizing:border-box; background:#1f1f1f; color:#eee; border:1px solid #3a3a3a; border-radius:3px; font-size:12px }}
  .facet-search:focus {{ outline:none; border-color:#7a1f3a }}
  #sidebar > details > summary .facet-badge {{ display:inline-block; margin-left:6px; padding:1px 6px; background:#7a1f3a; color:#fff; border-radius:8px; font-size:10px; font-weight:600 }}
  #sidebar > details > summary .facet-badge:empty {{ display:none }}
  #sidebar > details > summary {{ display:flex; align-items:center }}
  #sidebar > details > summary .facet-label {{ flex:1 }}
  .facet .region-group > summary {{ display:flex; align-items:center; gap:6px }}
  .facet .region-group > summary .region-select {{ accent-color:#7a1f3a; cursor:pointer; flex:0 0 auto }}
  .facet .region-group > summary .region-select:checked, .facet .region-group > summary .region-select:indeterminate {{ accent-color:#7a1f3a }}
  #status {{ padding:8px 16px; font-size:11px; color:#aaa; background:#222; border-bottom:1px solid #333 }}
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
  .facet .region-group {{ margin:2px 0 }}
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
  #panel .body h1 {{ font-size:22px; margin:8px 0 10px; padding-bottom:6px; border-bottom:2px solid #7a1f3a }}
  #panel .body h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:0.04em; color:#7a1f3a; margin:18px 0 6px }}
  #panel .body p {{ margin:0 0 8px }}
  #panel .meta {{ color:#666; font-size:12px; margin-bottom:8px }}
  #panel .translation-attr {{ font-size:10.5px; color:#888; font-style:italic; margin:0 0 8px }}
  #panel .translation-attr a {{ color:#888 }}
  #panel .stack-header {{ font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:#888; margin-bottom:6px; padding-bottom:6px; border-bottom:1px solid #eee }}
  #panel .aoc-card + .aoc-card {{ margin-top:24px; padding-top:20px; border-top:1px dashed #ccc }}
  #panel .aoc-card h1 {{ font-size:18px; margin:0 0 6px; padding-bottom:4px; border-bottom:2px solid #7a1f3a }}
  #panel .aoc-card.subordinate h1 {{ font-size:16px; color:#444; border-bottom-color:#ccc }}
  #panel .sources {{ margin:4px 0 0; padding-left:18px; font-size:12px; color:#444 }}
  #panel .sources li {{ margin:3px 0 }}
  #panel .sources code {{ font-size:11px; color:#888 }}
  #panel .pills {{ margin:0 0 4px }}
  .pill {{ display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; background:#eee; border-radius:10px; font-size:11px; color:#333; text-decoration:none }}
  .pill.style {{ background:#fdebe5; color:#7a1f3a }}
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
  .fr-marker {{ display:inline-block; margin-left:4px; font-size:10px; color:#999; font-style:italic; vertical-align:baseline }}
  #grape-tooltip .fr-marker {{ font-size:10px; color:#888 }}
  #sidebar-toggle {{ display:none; position:fixed; top:8px; right:8px; z-index:30; width:44px; height:44px; background:#1a1a1a; color:#eee; border:1px solid #444; border-radius:4px; font-size:18px; cursor:pointer; align-items:center; justify-content:center; box-shadow:0 2px 8px rgba(0,0,0,0.2) }}
  #sidebar-toggle:hover {{ background:#2a2a2a }}
  #legend {{ border-top:1px solid #2a2a2a }}
  #legend > summary {{ padding:8px 16px; color:#bbb; font-size:11px; text-transform:uppercase; letter-spacing:0.06em }}
  #legend .legend-body {{ padding:4px 16px 12px; font-size:11.5px; color:#bbb; line-height:1.5 }}
  #legend .swatch-row {{ display:flex; align-items:center; gap:6px; margin:3px 0 }}
  #legend .sw {{ display:inline-block; width:14px; height:14px; border-radius:3px; flex:0 0 14px; border:1px solid rgba(255,255,255,0.1) }}
  #legend .sw.aoc {{ background:#7a1f3a }}
  #legend .sw.igp {{ background:#5a7a4a }}
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
  #about-dialog {{ width:520px; max-width:calc(100vw - 32px); padding:0; border:1px solid #ccc; border-radius:6px; box-shadow:0 8px 32px rgba(0,0,0,0.18); background:#fff; color:#222 }}
  #about-dialog::backdrop {{ background:rgba(0,0,0,0.45) }}
  #about-dialog .close {{ position:absolute; top:10px; right:10px; background:#eee; border:none; border-radius:50%; width:28px; height:28px; cursor:pointer; font-size:16px; color:#666 }}
  #about-dialog .close:hover {{ background:#ddd; color:#000 }}
  #about-dialog .about-body {{ padding:24px 28px; line-height:1.55 }}
  #about-dialog h1 {{ font-size:20px; margin:0 0 14px; padding-bottom:8px; border-bottom:2px solid #7a1f3a }}
  #about-dialog p {{ margin:0 0 10px }}
  #about-dialog a {{ color:#7a1f3a }}
  #grape-tooltip {{ position:fixed; max-width:340px; background:#fff; color:#222; border:1px solid #ddd; border-radius:4px; padding:10px 12px; font-size:12px; line-height:1.5; box-shadow:0 4px 16px rgba(0,0,0,0.15); pointer-events:none; z-index:1000; display:none }}
  #grape-tooltip .ext {{ margin:0 0 6px }}
  #grape-tooltip .thumb {{ float:right; width:96px; height:auto; margin:0 0 6px 10px; border-radius:3px; background:#f3f3f3 }}
  #grape-tooltip .src {{ color:#888; font-size:10.5px; clear:both }}
  #grape-tooltip .src a {{ color:#888 }}
  #panel .body a {{ color:#7a1f3a }}
  .maplibregl-popup {{ max-width:320px !important }}
  .maplibregl-popup-content {{ font-size:13px; padding:10px 12px !important }}
  .maplibregl-popup-content h3 {{ margin:0 0 4px; font-size:14px; color:#7a1f3a }}
  .maplibregl-popup-content .meta {{ color:#777; font-size:11px }}
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h1>open wine map</h1>
    <div class="subtitle">{labels[subtitle]}</div>
    {lang_switcher_html}
    <div id="status">{labels[loading]}</div>

    <div id="mode-toggle" role="group" aria-label="{labels[view_mode_h]}">
      <button type="button" data-mode="simple" class="mode-btn active">{labels[view_mode_simple]}</button>
      <button type="button" data-mode="advanced" class="mode-btn">{labels[view_mode_advanced]}</button>
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

    <details data-modes="simple" data-facet="grapes">
      <summary><span class="facet-label">{labels[facet_grapes_h]}</span><span class="facet-badge"></span></summary>
      <input type="text" class="facet-search" data-facet="facet-grapes-all" placeholder="{labels[search_grape_placeholder]}" autocomplete="off">
      <div class="facet" id="facet-grapes-all"></div>
    </details>

    <details data-modes="advanced" data-facet="grapes">
      <summary><span class="facet-label">{labels[facet_principal_h]}</span><span class="facet-badge"></span></summary>
      <input type="text" class="facet-search" data-facet="facet-principal" placeholder="{labels[search_grape_placeholder]}" autocomplete="off">
      <div class="facet" id="facet-principal"></div>
    </details>

    <details data-modes="advanced" data-facet="accessory">
      <summary><span class="facet-label">{labels[facet_accessory_h]}</span><span class="facet-badge"></span></summary>
      <input type="text" class="facet-search" data-facet="facet-accessory" placeholder="{labels[search_grape_placeholder]}" autocomplete="off">
      <div class="facet" id="facet-accessory"></div>
    </details>

    <details data-facet="appellations">
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

    <details id="legend">
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
      <a href="#" id="about-link">{labels[about_link_label]}</a>
      <span class="sep">·</span>
      <a href="{github_url}" target="_blank" rel="noopener">GitHub</a>
    </div>

  </div>

  <button id="sidebar-toggle" type="button" aria-label="{labels[sidebar_toggle_aria]}">☰</button>

  <div id="map"></div>

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
  const FACET_STYLES = {styles_json};
  const FACET_STYLES_SIMPLE = {styles_simple_json};
  const FACET_PRINCIPAL = {principal_json};
  const FACET_ACCESSORY = {accessory_json};
  const FACET_GRAPES_ALL = {grapes_all_json};
  const FACET_REGIONS = {regions_json};
  const STYLE_LABELS = {style_labels_json};
  const SIMPLE_STYLE_LABELS = {simple_style_labels_json};
  const SIMPLE_STYLE_BUCKETS = {simple_style_buckets_json};
  const LABELS = {labels_json};
  const GRAPES_INFO = {grapes_info_json};
  const REGION_LABELS = {region_labels_json};
  const LANG = "{lang_attr}";

  function grapeName(slug) {{
    const info = GRAPES_INFO[slug];
    return (info && info.name) ? info.name : slug.replace(/-/g, ' ');
  }}

  function regionLabel(region) {{
    if (!region) return LABELS.meta_no_region;
    return REGION_LABELS[region] || region;
  }}

  function grapeUrl(slug) {{
    const info = GRAPES_INFO[slug];
    if (info && info.page_url) return info.page_url;
    const title = slug.replace(/-/g, '_').replace(/^./, c => c.toUpperCase());
    return `https://${{LANG}}.wikipedia.org/wiki/${{title}}`;
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
    if (filters.q) {{
      parts.push(['in', filters.q.toLowerCase(), ['downcase', ['get', 'name']]]);
    }}
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
      const gExpr = inField('grapes_all', filters.grapesAll);
      if (gExpr) parts.push(gExpr);
    }} else {{
      const sExpr = inField('styles', filters.styles);
      const pExpr = inField('grapes_principal', filters.principal);
      const aExpr = inField('grapes_accessory', filters.accessory);
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
    renderActiveFilters();
    if (opts && opts.fit) fitToFiltered();
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
      return `<span class="${{cls}}" data-kind="${{escapeAttr(c.kind)}}" data-key="${{escapeAttr(c.key)}}"><span>${{escapeHtml(c.label)}}</span><button type="button" aria-label="${{escapeAttr(LABELS.close_aria)}}">×</button></span>`;
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
    // Re-sync all facet checkboxes to current filter sets.
    const sets = {{
      'facet-styles': filters.styles,
      'facet-styles-simple': filters.stylesSimple,
      'facet-principal': filters.principal,
      'facet-accessory': filters.accessory,
      'facet-grapes-all': filters.grapesAll,
    }};
    for (const [id, set] of Object.entries(sets)) {{
      const el = document.getElementById(id);
      if (!el) continue;
      el.querySelectorAll('input[type=checkbox]').forEach(inp => {{
        inp.checked = set.has(inp.dataset.key);
      }});
    }}
  }}

  // Fit-to-filtered safety belt: when spirits are hidden, clamp the bbox to
  // mainland France + Corsica so a stray IGP polygon (say a still-visible
  // Atlantique IGP that overlaps a wine appellation) cannot drag the camera
  // to a hemispheric view. Loose bounds — meant to forbid overshoots, not
  // to constrain real selections inside France.
  const MAINLAND_BBOX = [-5.5, 41.0, 10.0, 51.5];

  function fitToFiltered() {{
    const expr = buildFilterExpr();
    if (!expr) return;
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
    if (!spiritsVisible()) {{
      minX = Math.max(minX, MAINLAND_BBOX[0]);
      minY = Math.max(minY, MAINLAND_BBOX[1]);
      maxX = Math.min(maxX, MAINLAND_BBOX[2]);
      maxY = Math.min(maxY, MAINLAND_BBOX[3]);
    }}
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
    el.textContent = fmt(LABELS.count_filtered, {{ n: n, total: total }});
  }}

  function matchesClient(rec, slug) {{
    if (!showIgp && (rec.kind || 'AOC') === 'IGP') return false;
    if (!spiritsVisible() && rec.is_wine === false) return false;
    if (filters.q && !rec.name.toLowerCase().includes(filters.q.toLowerCase())) return false;
    if (viewMode === 'simple') {{
      if (filters.stylesSimple.size && !setIntersects(filters.stylesSimple, rec.styles_simple || [])) return false;
      if (filters.grapesAll.size && !setIntersects(filters.grapesAll, rec.grapes_all || [])) return false;
    }} else {{
      if (filters.styles.size && !setIntersects(filters.styles, rec.styles)) return false;
      if (filters.principal.size && !setIntersects(filters.principal, rec.grapes_principal)) return false;
      if (filters.accessory.size && !setIntersects(filters.accessory, rec.grapes_accessory)) return false;
    }}
    if (filters.appellations.size && !filters.appellations.has(slug)) return false;
    return true;
  }}

  function setIntersects(set, arr) {{
    if (!arr) return false;
    for (const v of arr) if (set.has(v)) return true;
    return false;
  }}

  function buildFacet(containerId, items, store, format) {{
    const el = document.getElementById(containerId);
    const html = items.map(([key, count]) => {{
      const safeKey = String(key).replace(/"/g, '&quot;');
      const label = format ? format(key) : key;
      return `<label><input type="checkbox" data-key="${{safeKey}}"><span class="name">${{label}}</span><span class="count">${{count}}</span></label>`;
    }}).join('');
    el.innerHTML = html;
    el.addEventListener('change', e => {{
      if (e.target.tagName !== 'INPUT') return;
      const k = e.target.dataset.key;
      if (e.target.checked) store.add(k); else store.delete(k);
      applyFilter({{ fit: true }});
    }});
  }}

  buildFacet('facet-styles', FACET_STYLES, filters.styles, k => STYLE_LABELS[k] || k);
  buildFacet('facet-styles-simple', FACET_STYLES_SIMPLE, filters.stylesSimple, k => SIMPLE_STYLE_LABELS[k] || k);
  buildFacet('facet-principal', FACET_PRINCIPAL, filters.principal, grapeName);
  buildFacet('facet-accessory', FACET_ACCESSORY, filters.accessory, grapeName);
  buildFacet('facet-grapes-all', FACET_GRAPES_ALL, filters.grapesAll, grapeName);

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
        const name = escapeHtml(AOCS[slug].name);
        const checked = filters.appellations.has(slug) ? ' checked' : '';
        return `<label data-slug="${{safeSlug}}" data-name="${{escapeAttr(AOCS[slug].name.toLowerCase())}}"><input type="checkbox" data-key="${{safeSlug}}"${{checked}}><span class="name">${{name}}</span></label>`;
      }}).join('');
      const safeRegion = escapeAttr(region);
      html.push(`<details class="region-group" data-region="${{safeRegion}}"><summary><input type="checkbox" class="region-select" data-region="${{safeRegion}}" aria-label="${{escapeAttr(LABELS.select_all_aria)}}"><span class="name">${{escapeHtml(label)}}</span><span class="count">${{slugs.length}}</span></summary><div class="region-items">${{items}}</div></details>`);
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
    }} else {{
      const k = e.target.dataset.key;
      if (e.target.checked) filters.appellations.add(k); else filters.appellations.delete(k);
    }}
    refreshRegionTriStates();
    applyFilter({{ fit: true }});
  }});

  function refreshRegionTriStates() {{
    const el = document.getElementById('facet-appellations');
    if (!el) return;
    el.querySelectorAll('.region-group').forEach(group => {{
      const region = group.dataset.region;
      const cb = group.querySelector('.region-select');
      if (!cb) return;
      const state = regionTriState(region);
      cb.checked = state === 'checked';
      cb.indeterminate = state === 'indeterminate';
    }});
  }}

  function refreshFacetVisibility(containerId, q) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    const lc = (q || '').toLowerCase();
    // Appellation tree: groups + labels with data-name dataset.
    const groups = el.querySelectorAll('.region-group');
    if (groups.length) {{
      groups.forEach(group => {{
        let visible = 0;
        group.querySelectorAll('label').forEach(lbl => {{
          const match = !lc || lbl.dataset.name.includes(lc);
          lbl.style.display = match ? '' : 'none';
          if (match) visible++;
        }});
        group.style.display = visible ? '' : 'none';
        if (lc && visible) group.open = true;
      }});
      return;
    }}
    // Flat facet (grapes etc.) — match against the .name span text.
    el.querySelectorAll('label').forEach(lbl => {{
      const span = lbl.querySelector('.name');
      const text = (span ? span.textContent : '').toLowerCase();
      lbl.style.display = (!lc || text.includes(lc)) ? '' : 'none';
    }});
  }}

  buildAppellationFacet();

  function applyMode() {{
    document.documentElement.classList.toggle('mode-simple', viewMode === 'simple');
    document.documentElement.classList.toggle('mode-advanced', viewMode === 'advanced');
    document.querySelectorAll('#mode-toggle .mode-btn').forEach(b => {{
      b.classList.toggle('active', b.dataset.mode === viewMode);
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
      applyMode();
      applyFilter({{ fit: true }});
    }});
  }});

  const igpEl = document.getElementById('show-igp');
  igpEl.checked = showIgp;
  igpEl.addEventListener('change', e => {{
    showIgp = e.target.checked;
    try {{ localStorage.setItem('show_igp', showIgp ? '1' : '0'); }} catch (err) {{}}
    applyFilter({{ fit: true }});
  }});

  const spiritsEl = document.getElementById('show-spirits');
  spiritsEl.checked = showSpirits;
  spiritsEl.addEventListener('change', e => {{
    showSpirits = e.target.checked;
    try {{ localStorage.setItem('show_spirits', showSpirits ? '1' : '0'); }} catch (err) {{}}
    // Spirit AOCs join/leave the appellation tree; rebuild + reapply.
    buildAppellationFacet();
    applyFilter({{ fit: true }});
  }});

  // The merged Appellation facet hosts the appellation search; typing in
  // it auto-expands the section if collapsed, since otherwise the tree
  // updates would be invisible to the user.
  const qInput = document.getElementById('q');
  qInput.addEventListener('input', e => {{
    filters.q = e.target.value.trim();
    refreshFacetVisibility('facet-appellations', filters.q);
    const det = qInput.closest('details');
    if (filters.q && det && !det.open) det.open = true;
    applyFilter();
  }});

  // Per-facet search inputs (cépages). They filter only the visible
  // checkboxes in their target facet; they do not affect the map filter.
  document.querySelectorAll('.facet-search[data-facet]').forEach(input => {{
    input.addEventListener('input', e => {{
      refreshFacetVisibility(input.dataset.facet, e.target.value.trim());
    }});
  }});

  document.getElementById('reset').addEventListener('click', () => {{
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

  function translationAttribution(t) {{
    if (!t) return '';
    const labelText = LABELS.translation_source_label;
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

  function renderAocCard(slug, isPrimary) {{
    const r = AOCS[slug];
    if (!r) return '';
    const styleChips = (r.styles || []).map(s => {{
      const safe = escapeAttr(s);
      return `<span class="pill style style--${{safe}}">${{STYLE_LABELS[s] || s}}</span>`;
    }}).join('');
    const grapePill = (g, cls) => {{
      const info = GRAPES_INFO[g];
      const has = !!(info && info.extract);
      const cls2 = ['pill', 'grape', cls, has ? 'has-info' : ''].filter(Boolean).join(' ');
      const display = (info && info.name) ? info.name : g.replace(/-/g, ' ');
      return `<a class="${{cls2}}" data-slug="${{escapeAttr(g)}}" href="${{escapeAttr(grapeUrl(g))}}" target="_blank" rel="noopener">${{escapeHtml(display)}}</a>`;
    }};
    const principal = (r.grapes_principal || []).map(g => grapePill(g, '')).join('');
    const accessory = (r.grapes_accessory || []).map(g => grapePill(g, 'accessory')).join('');
    const observation = (r.grapes_observation || []).map(g => grapePill(g, 'observation')).join('');
    const cats = (r.categories || []).join(', ');
    const isTranslated = !!r.summary_translation;
    const summaryMarker = isTranslated ? '' : frMarker();
    const summary = r.summary ? `<p>${{escapeHtml(r.summary)}}${{summaryMarker}}</p>${{translationAttribution(r.summary_translation)}}` : '';
    const klass = isPrimary ? 'aoc-card' : 'aoc-card subordinate';
    let metaTail;
    if (r.geom_source === 'parcellaire') {{
      metaTail = ' · ' + LABELS.meta_geom_parcellaire;
    }} else if (r.geom_source === 'aires-csv') {{
      metaTail = ' · ' + fmt(LABELS.meta_communes_inao, {{ n: r.communes_matched || 0 }});
    }} else {{
      metaTail = ' · ' + fmt(LABELS.meta_communes, {{ n: r.communes_matched || 0 }});
    }}
    const region = regionLabel(r.region);
    const dgcLine = r.is_dgc && r.parent_slug
      ? `<div class="dgc-line">${{escapeHtml(LABELS.dgc_of)}} <a class="parent-link" data-slug="${{escapeAttr(r.parent_slug)}}" href="#">${{escapeHtml(r.parent_name || r.parent_slug)}}</a></div>`
      : '';
    return `
      <div class="${{klass}}">
        <h1>${{escapeHtml(r.name)}}</h1>
        <div class="meta">${{r.kind}} · ${{escapeHtml(region)}}${{metaTail}}</div>
        ${{dgcLine}}
        ${{summary}}
        ${{styleChips ? '<h2>' + LABELS.panel_styles_h + '</h2><div class="pills">' + styleChips + '</div>' : ''}}
        ${{cats ? '<h2>' + LABELS.panel_categories_h + '</h2><p>' + escapeHtml(cats) + '</p>' : ''}}
        ${{principal ? '<h2>' + LABELS.facet_principal_h + '</h2><div class="pills">' + principal + '</div>' : ''}}
        ${{accessory ? '<h2>' + LABELS.facet_accessory_h + '</h2><div class="pills">' + accessory + '</div>' : ''}}
        ${{observation ? '<h2>' + LABELS.panel_observation_h + '</h2><div class="pills">' + observation + '</div>' : ''}}
        ${{renderSources(slug, r.sources)}}
      </div>
    `;
  }}

  function renderPanelStack(slugs) {{
    if (!slugs.length) return;
    // Most-specific first: smaller polygon = grand cru / lieu-dit before
    // the regional appellation that contains it. AOCS[slug].area is in
    // raw degree² (computed at build time) — relative ordering is what
    // matters, the unit doesn't.
    const sorted = slugs
      .filter(s => AOCS[s])
      .sort((a, b) => (AOCS[a].area || 0) - (AOCS[b].area || 0));
    const header = sorted.length > 1
      ? `<div class="stack-header">${{fmt(LABELS.stack_header, {{ n: sorted.length }})}}</div>`
      : '';
    panelBody.innerHTML = header + sorted.map((s, i) => renderAocCard(s, i === 0)).join('');
    panel.classList.add('open');
  }}

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  }}

  document.querySelector('#panel .close').addEventListener('click', () => panel.classList.remove('open'));

  // ----- grape tooltip (Wikipedia, CC BY-SA 4.0) -----
  const grapeTip = document.createElement('div');
  grapeTip.id = 'grape-tooltip';
  document.body.appendChild(grapeTip);

  function positionGrapeTip(el) {{
    const r = el.getBoundingClientRect();
    const top = (r.bottom + 220 > window.innerHeight) ? (r.top - grapeTip.offsetHeight - 6) : (r.bottom + 6);
    const left = Math.min(Math.max(8, r.left), window.innerWidth - grapeTip.offsetWidth - 8);
    grapeTip.style.top = Math.max(8, top) + 'px';
    grapeTip.style.left = left + 'px';
  }}

  panel.addEventListener('mouseover', e => {{
    const a = e.target.closest('a.pill.grape.has-info');
    if (!a) return;
    const info = GRAPES_INFO[a.dataset.slug];
    if (!info || !info.extract) return;
    const url = escapeAttr(info.page_url || grapeUrl(a.dataset.slug));
    const thumb = info.thumbnail
      ? `<img class="thumb" src="${{escapeAttr(info.thumbnail)}}" alt="">` : '';
    const fallback = (LANG !== 'fr' && info.lang_fallback)
      ? ` <span class="fr-marker">${{escapeHtml(LABELS.fr_marker)}}</span>` : '';
    grapeTip.innerHTML = thumb + `<p class="ext">${{escapeHtml(info.extract)}}${{fallback}}</p>` +
      `<div class="src">via <a href="${{url}}" target="_blank" rel="noopener">Wikipedia</a> · CC BY-SA 4.0 · image: Wikimedia Commons</div>`;
    grapeTip.style.display = 'block';
    positionGrapeTip(a);
  }});

  panel.addEventListener('mouseout', e => {{
    if (e.target.closest('a.pill.grape.has-info')) grapeTip.style.display = 'none';
  }});

  panel.addEventListener('click', e => {{
    const a = e.target.closest('a.parent-link');
    if (!a) return;
    e.preventDefault();
    const slug = a.dataset.slug;
    if (slug && AOCS[slug]) renderPanelStack([slug]);
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
      map.on('click', id, e => {{
        if (!e.features.length) return;
        // queryRenderedFeatures at the click point returns one feature per
        // overlapping polygon (e.g. Chambertin grand cru AND its parent
        // Gevrey-Chambertin AOC AND Bourgogne). Dedupe by slug — a single
        // AOC can produce multiple tile fragments along seams.
        const seen = new Set();
        const slugs = [];
        for (const f of e.features) {{
          const s = f.properties.slug;
          if (s && !seen.has(s)) {{ seen.add(s); slugs.push(s); }}
        }}
        renderPanelStack(slugs);
      }});
    }}

    applyMode();
    applyFilter();
    updateStatus();
  }});
</script>
</body>
</html>
"""
