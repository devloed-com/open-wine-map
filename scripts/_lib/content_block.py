"""Server-side render of the appellation detail-panel content block.

A faithful Python port of the STABLE subset of the JS ``renderAocCard`` pipeline
in :mod:`map_template` (and its helpers), so a per-appellation page can ship a
crawlable, server-rendered ``<article>`` built from the same ``aocs`` record the
client panel uses. v1 is wired but not yet emitted to any page — Phase 3 will
inject it into ``<article id="ssr-content">``; for now it ships as additive,
unit-tested code (zero SEO surface).

Scope is deliberately narrower than the JS panel: name, meta line, DGC / approx
/ stub lines, style chips, grape pills (with the canonical-bracket logic), the
PT role disclaimer, terroir facts (bullet + verbatim modes), summary (shown only
when there are no facts), the cross-border note, and the sources block. The
volatile HU ``dűlők`` / IT ``menzioni`` chip sections are LEFT to the client
panel — their per-record shape churns more and they add no crawlable-summary
value.

Each helper mirrors its JS counterpart one-for-one (same HTML templates + the
same escaping) so the two renderers stay aligned; ``tests/test_content_block.py``
snapshots the output as a drift guard, and every ``<article>`` carries a
``data-ssr-sig`` (a hash of its normalised text) used only as a test-only
determinism guard — the client panel removes ``#ssr-content`` at boot and
re-renders from the record, so there is NO runtime signature cross-check. A
change to one renderer that isn't mirrored in the other therefore fails
silently as crawler-vs-user divergence, not a crash; the parity tests are the
only guard.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

# Per-jurisdiction regulator-published specification document name, in the
# regulator's own language — mirrors STUB_DOC_NAMES in map_template.py's JS.
STUB_DOC_NAMES = {
    "fr": "cahier des charges",
    "es": "pliego de condiciones",
    "pt": "caderno de especificações",
    "it": "disciplinare di produzione",
    "at": "Produktspezifikation",
    "si": "specifikacija proizvoda",
    "hr": "specifikacija proizvoda",
    "ro": "caiet de sarcini",
    "de": "Produktspezifikation",
    "hu": "termékleírás",
    "bg": "продуктова спецификация",
    "gr": "προδιαγραφή προϊόντος",
    "cy": "τεχνικός φάκελος",
    "sk": "špecifikácia výrobku",
    "cz": "specifikace výrobku",
    "lu": "cahier des charges",
    "be": "enig document / document unique",
    "nl": "enig document",
    "mt": "single document",
    "ch": "règlement cantonal",
}

FACTS_SUB_ORDER = ("facteurs_naturels", "facteurs_humains", "produit", "interactions")

# Per-country regulator term for a sub-denomination, in the regulator's own
# language and pluralised (the section lists several) — the heading for the
# sub-appellations block. Shown verbatim like region/bassin facet labels, NOT
# gettext-translated, so the page carries the exact term the source document
# (and an informed searcher) uses. Countries without a single clean term
# (CH régionale/locale tiers, LU per-commune) fall back to the generic
# translated `entity_nav_children` label.
SUBDENOM_HEADINGS = {
    "fr": "Dénominations géographiques complémentaires",
    "es": "Subzonas",
    "it": "Sottozone",
    "pt": "Sub-regiões",
    "de": "Einzellagen",
}


@dataclass(frozen=True)
class RenderCtx:
    """Everything ``render_content_block`` needs from ``render()``'s scope.

    Mirrors the JS module-scope globals (LABELS, REGION_LABELS, COUNTRY_LABELS,
    COUNTRY_FLAG_EMOJI, GRAPES_INFO, STYLES_INFO, STYLE_LABELS,
    GITHUB_NEW_ISSUE_URL, LANG)."""

    locale: str
    labels: dict
    region_labels: dict
    country_labels: dict
    country_flag_emoji: dict
    grapes_info: dict
    styles_info: dict
    style_labels: dict
    github_new_issue_url: str


# ---------------------------------------------------------------- primitives

def esc(s) -> str:
    """Port of escapeHtml/escapeAttr — identical entity set, & first."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# JS: s.replace(/(?:^|[\s\-'(])\p{L}/gu, c => c.toUpperCase()) — uppercase a
# letter at a word boundary (start, or after space / - / ' / "(" ).
_TITLE_RE = re.compile(r"(?:^|[\s\-'(])[^\W\d_]", re.UNICODE)


def to_title_case(s: str) -> str:
    return _TITLE_RE.sub(lambda m: m.group(0).upper(), s or "")


# JS fmt: tpl.replace(/\{(\w+)\}/g, (_, k) => vars[k] != null ? vars[k] : '')
# (single braces — the template's \\{{…\\}} renders to \{…\}).
_FMT_RE = re.compile(r"\{(\w+)\}")


def fmt(tpl: str, variables: dict) -> str:
    def repl(m: re.Match) -> str:
        v = variables.get(m.group(1))
        return "" if v is None else str(v)

    return _FMT_RE.sub(repl, tpl or "")


# ---------------------------------------------------------------- name helpers

def grape_name(slug: str, ctx: RenderCtx) -> str:
    info = ctx.grapes_info.get(slug)
    raw = info["name"] if info and info.get("name") else slug.replace("-", " ")
    return to_title_case(raw)


def grape_url(slug: str, ctx: RenderCtx) -> str:
    info = ctx.grapes_info.get(slug)
    if info and info.get("page_url"):
        return info["page_url"]
    title = slug.replace("-", "_")
    title = (title[:1].upper() + title[1:]) if title else title
    return f"https://{ctx.locale}.wikipedia.org/wiki/{title}"


_CANON_COLOR_WORD_RE = re.compile(
    r"\b(tinto|tinta|blanco|blanca|noir|blanc|gris|rouge|ros[eé])\b", re.IGNORECASE
)
_CANON_COLOR_LETTER_RE = re.compile(r"\s+(b|n|g|rs|rg)$", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]", re.IGNORECASE)


def _canon_norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))  # strip diacritics
    s = _CANON_COLOR_LETTER_RE.sub("", s)
    s = _CANON_COLOR_WORD_RE.sub("", s)
    s = _NON_ALNUM_RE.sub("", s)
    return s.lower()


def canonical_equals_cahier(canon: str, cahier: str) -> bool:
    """True when the cahier spelling and the VIVC prime name are the same
    variety after light normalisation — suppresses redundant brackets."""
    return _canon_norm(canon) == _canon_norm(cahier)


def region_label(region: str, ctx: RenderCtx) -> str:
    if not region:
        return ctx.labels["meta_no_region"]
    return ctx.region_labels.get(region, region)


def name_with_latin(rec: dict) -> str:
    native = esc(rec.get("name") or "")
    latin = rec.get("name_latin") or ""
    if not latin or latin == rec.get("name"):
        return native
    return native + ' <span class="latin">(' + esc(latin) + ")</span>"


def _one_country_chip(code: str, ctx: RenderCtx) -> str:
    flag = ctx.country_flag_emoji.get(code, "")
    name = ctx.country_labels.get(code, "")
    if not flag and not name:
        return ""
    flag_span = f'<span class="country-flag" aria-hidden="true">{flag}</span>' if flag else ""
    name_span = f'<span class="country-name">{esc(name)}</span>' if name else ""
    return f'<span class="meta-country">{flag_span}{name_span}</span>'


def country_chip_html(code: str, aliases, ctx: RenderCtx) -> str:
    if not code:
        return ""
    codes = [code, *(aliases or [])]
    chips = [c for c in (_one_country_chip(x, ctx) for x in codes) if c]
    return " · ".join(chips)


# ---------------------------------------------------------------- attribution

def _src_marker(country: str, ctx: RenderCtx) -> str:
    source_lang = country if country in ("es", "pt") else "fr"
    if ctx.locale == source_lang:
        return ""
    lab = ctx.labels
    if country == "es":
        text, aria = lab["es_marker"], lab["es_marker_aria"]
    elif country == "pt":
        text = lab.get("pt_marker") or lab["fr_marker"]
        aria = lab.get("pt_marker_aria") or lab["fr_marker_aria"]
    else:
        text, aria = lab["fr_marker"], lab["fr_marker_aria"]
    return f' <span class="fr-marker" title="{esc(aria)}">{esc(text)}</span>'


def _attr_paragraph(tpl: str, source_html: str) -> str:
    """Port of the {source}-placeholder split shared by translationAttribution
    and buildFactsAttribution."""
    placeholder = "{source}"
    idx = tpl.find(placeholder)
    if idx >= 0:
        pre, post = tpl[:idx], tpl[idx + len(placeholder):]
    else:
        pre, post = tpl + " ", ""
    return f'<p class="translation-attr">{esc(pre)}{source_html}{esc(post)}</p>'


def _translation_attribution(t: dict | None, country: str, ctx: RenderCtx) -> str:
    if not t:
        return ""
    lab = ctx.labels
    if country == "es":
        label_text = lab["translation_source_label_es"]
    elif country == "pt":
        label_text = lab.get("translation_source_label_pt") or lab["translation_source_label"]
    else:
        label_text = lab["translation_source_label"]
    url = t.get("source_pdf_url")
    source_html = (
        f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label_text)}</a>'
        if url
        else esc(label_text)
    )
    return _attr_paragraph(lab["translation_attribution"], source_html)


def _build_facts_source_label(country: str, ctx: RenderCtx) -> str:
    if country == "es":
        return ctx.labels["facts_attribution_source_label_es"]
    if country == "pt":
        return ctx.labels["facts_attribution_source_label_pt"]
    return ctx.labels["facts_attribution_source_label"]


def _build_facts_attribution(tpl_key: str, country: str, cahier_url: str, ctx: RenderCtx) -> str:
    label_text = _build_facts_source_label(country, ctx)
    source_html = (
        f'<a href="{esc(cahier_url)}" target="_blank" rel="noopener">{esc(label_text)}</a>'
        if cahier_url
        else esc(label_text)
    )
    return _attr_paragraph(ctx.labels[tpl_key], source_html)


# ---------------------------------------------------------------- terroir

def _render_verbatim_facts(rec: dict, tf: dict, ctx: RenderCtx) -> str:
    text = tf.get("verbatim_text") or ""
    if not text:
        return ""
    cahier_url = tf.get("cahier_source_pdf_url") or ""
    flag = tf.get("validation_flag") or ""
    badge = (
        f'<span class="verbatim-badge" title="{esc(flag)}">'
        f'{esc(ctx.labels["facts_verbatim_to_verify"])}</span>'
        if flag
        else ""
    )
    body = f'<blockquote class="facts-verbatim">{esc(text)}</blockquote>'
    attribution = _build_facts_attribution(
        "facts_verbatim_attribution", rec.get("country") or "fr", cahier_url, ctx
    )
    head = f'<h2>{ctx.labels["panel_facts_h"]}{" " + badge if badge else ""}</h2>'
    return f"{head}{body}{attribution}"


def render_terroir_facts(rec: dict, ctx: RenderCtx) -> str:
    tf = rec.get("terroir_facts")
    if not tf:
        return ""
    if tf.get("mode") == "verbatim":
        return _render_verbatim_facts(rec, tf, ctx)
    facts = tf.get("facts") or []
    if not facts:
        return ""
    lab = ctx.labels
    wiki_url = tf.get("wiki_source_url") or ""
    if wiki_url:
        wiki_attr = (
            f' <span class="wiki-attr">(<a href="{esc(wiki_url)}" target="_blank" '
            f'rel="noopener">{esc(lab["facts_wiki_marker"])}</a>)</span>'
        )
    else:
        wiki_attr = f' <span class="wiki-attr">({esc(lab["facts_wiki_marker"])})</span>'

    grouped: dict[str, list] = {}
    for f in facts:
        k = f.get("subsection") or "facteurs_naturels"
        grouped.setdefault(k, []).append(f)

    sub_labels = {
        "facteurs_naturels": lab["facts_sub_facteurs_naturels"],
        "facteurs_humains": lab["facts_sub_facteurs_humains"],
        "produit": lab["facts_sub_produit"],
        "interactions": lab["facts_sub_interactions"],
    }
    blocks: list[str] = []
    for k in FACTS_SUB_ORDER:
        sub = grouped.get(k)
        if not sub:
            continue
        items = "".join(
            f'<li>{esc(f.get("bullet") or "")}'
            f'{wiki_attr if f.get("provenance") == "wiki" else ""}</li>'
            for f in sub
        )
        blocks.append(
            f'<div class="facts-sub-h">{esc(sub_labels.get(k, k))}</div>'
            f'<ul class="facts">{items}</ul>'
        )
    if not blocks:
        return ""
    attribution = _build_facts_attribution(
        "facts_attribution", rec.get("country") or "fr", tf.get("cahier_source_pdf_url") or "", ctx
    )
    return f'<h2>{lab["panel_facts_h"]}</h2>{"".join(blocks)}{attribution}'


# ---------------------------------------------------------------- sources

def render_sources(sources: dict | None, ctx: RenderCtx) -> str:
    sources = sources or {}
    lab = ctx.labels
    links: list[str] = []
    if sources.get("boagri"):
        homo = (
            f' — {lab["src_homologated"]} {esc(sources["homologation_date"])}'
            if sources.get("homologation_date")
            else ""
        )
        jorf = f', {lab["src_jorf"]} {esc(sources["jorf_date"])}' if sources.get("jorf_date") else ""
        links.append(
            f'<li><a href="{esc(sources["boagri"])}" target="_blank" rel="noopener">'
            f'{lab["src_cahier"]}</a>{homo}{jorf}</li>'
        )
    if sources.get("show_texte"):
        links.append(
            f'<li><a href="{esc(sources["show_texte"])}" target="_blank" rel="noopener">'
            f'{lab["src_show_texte"]}</a></li>'
        )
    if sources.get("product"):
        links.append(
            f'<li><a href="{esc(sources["product"])}" target="_blank" rel="noopener">'
            f'{lab["src_product"]}</a></li>'
        )
    if sources.get("eur_lex_url"):
        links.append(
            f'<li><a href="{esc(sources["eur_lex_url"])}" target="_blank" rel="noopener">'
            f'{lab["src_eur_lex"]}</a></li>'
        )
    if sources.get("national_pliego_url"):
        added = len(sources.get("national_pliego_added_slugs") or [])
        note = f' — +{added} {lab["src_national_pliego_added"]}' if added else ""
        links.append(
            f'<li><a href="{esc(sources["national_pliego_url"])}" target="_blank" rel="noopener">'
            f'{lab["src_national_pliego"]}</a>{note}</li>'
        )
    if sources.get("national_spec_url"):
        org = (
            f' — {esc(sources["national_spec_source_org"])}'
            if sources.get("national_spec_source_org")
            else ""
        )
        links.append(
            f'<li><a href="{esc(sources["national_spec_url"])}" target="_blank" rel="noopener">'
            f'{lab["src_national_spec"]}</a>{org}</li>'
        )
    if sources.get("chzo_spec_url"):
        reg = f' — {esc(sources["chzo_spec_region"])}' if sources.get("chzo_spec_region") else ""
        org = (
            f' ({esc(str(sources["chzo_spec_source_org"]).upper())})'
            if sources.get("chzo_spec_source_org")
            else ""
        )
        links.append(
            f'<li><a href="{esc(sources["chzo_spec_url"])}" target="_blank" rel="noopener">'
            f'{lab["src_chzo_spec"]}</a>{reg}{org}</li>'
        )
    if sources.get("regional_register_url"):
        reg = (
            f' — {esc(sources["regional_register_region"])}'
            if sources.get("regional_register_region")
            else ""
        )
        links.append(
            f'<li><a href="{esc(sources["regional_register_url"])}" target="_blank" rel="noopener">'
            f'{lab["src_regional_register"]}</a>{reg}</li>'
        )
    if sources.get("id_eambrosia"):
        from urllib.parse import quote

        eambrosia_url = (
            "https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/"
            f"details/{quote(str(sources['id_eambrosia']), safe='')}"
        )
        file_num = (
            f' — {lab["src_eambrosia_id"]} {esc(sources["file_number"])}'
            if sources.get("file_number")
            else ""
        )
        links.append(
            f'<li><a href="{esc(eambrosia_url)}" target="_blank" rel="noopener">'
            f'{lab["src_eambrosia"]}</a>{file_num}</li>'
        )
    syndicate = sources.get("syndicate")
    if syndicate and syndicate.get("url"):
        sy_label = f' — {esc(syndicate["label"])}' if syndicate.get("label") else ""
        links.append(
            f'<li><a href="{esc(syndicate["url"])}" target="_blank" rel="noopener">'
            f'{lab["src_syndicate"]}</a>{sy_label}</li>'
        )
    return f'<h2>{lab["panel_sources_h"]}</h2><ul class="sources">{"".join(links)}</ul>'


# ------------------------------------------------------------ provenance line

# Native source-document term for the EU single document, per country — the
# FALLBACK when no more-specific national-spec key is present on the record.
# Regulator is then "the EU eAmbrosia register" (gated on id_eambrosia).
_EU_DOC_TERM = {
    "es": "documento único", "it": "documento unico", "at": "Einziges Dokument",
    "de": "Einziges Dokument", "si": "enotni dokument", "hr": "jedinstveni dokument",
    "hu": "egységes dokumentum", "ro": "document unic", "bg": "единен документ",
    "gr": "ενιαίο έγγραφο", "cy": "ενιαίο έγγραφο", "sk": "jednotný dokument",
    "cz": "jednotný dokument", "nl": "enig document", "mt": "single document",
}

# national-spec source-org token → human regulator name (the literal token
# `_sources_for` surfaces as *_source_org). Falls back to the per-country
# default in `_provenance_source` when the token is absent/unknown.
_PROV_ORG_LABEL = {
    "onvpv": "ONVPV", "iavv": "ИАЛВ/IAVV", "ypaat": "ΥΠΑΑΤ",
    "upv-sr": "ÚPV SR", "mprv-sr": "MPRV SR", "szpi": "SZPI",
    "agrarminiszterium": "Agrárminisztérium", "mkgp": "MKGP",
    "moa-cy": "the Cyprus Department of Agriculture",
}

# per-country national-spec defaults (regulator, native doc term) for the
# countries whose provenance resolves from `national_spec_url`.
_PROV_NATIONAL = {
    "hu": ("Agrárminisztérium", "termékleírás"),
    "ro": ("ONVPV", "caiet de sarcini"),
    "bg": ("ИАЛВ/IAVV", "продуктова спецификация"),
    "gr": ("ΥΠΑΑΤ", "προδιαγραφή προϊόντος"),
    "sk": ("ÚPV SR", "špecifikácia výrobku"),
    "cy": ("the Cyprus Department of Agriculture", "τεχνικός φάκελος"),
}


def _provenance_source(rec: dict, ctx: RenderCtx) -> tuple[str, str, bool, str] | None:
    """Resolve ``(regulator_html, doc_term, is_roster, extra_html)`` for the
    provenance line, mirroring ``_sources_for``'s most-specific-first cascade.

    Returns ``None`` when no public regulator source resolves (no line shown).
    ``is_roster`` True means the authorised-variety list is a national/regional
    roster, NOT an appellation-specific authorisation (CZ national list, IT
    regional register, CH cantonal règlement) — the grapes clause is then
    suppressed so we never misattribute a country-wide roster as this
    designation's own. ``extra_html`` is a short per-record differentiator
    (registration ref / homologation date) appended only to the grapeless
    skeleton, so the degenerate strings are not byte-identical across records.

    ``regulator_html`` is render-ready (proper-noun acronyms are esc'd; the
    descriptive fallbacks come from the gettext catalog so they localise).
    """
    s = rec.get("sources") or {}
    country = rec.get("country") or "fr"
    lab = ctx.labels
    file_number = s.get("file_number") or ""
    has_eambrosia = bool(s.get("id_eambrosia"))
    extra = f" ({esc(file_number)})" if file_number else ""
    eambrosia_reg = lab["provenance_reg_eambrosia"]

    def eu_fallback() -> tuple[str, str, bool, str] | None:
        if s.get("eur_lex_url") and has_eambrosia:
            return (eambrosia_reg, _EU_DOC_TERM.get(country, "single document"), False, extra)
        return None

    if country == "fr":
        if s.get("boagri"):
            d = s.get("homologation_date") or s.get("jorf_date") or ""
            return ("INAO", "cahier des charges", False, f" ({esc(d)})" if d else "")
        return None
    if country == "es":
        if s.get("national_pliego_url"):
            return ("MAPA", "pliego de condiciones", False, extra)
        return eu_fallback()
    if country == "pt":
        return ("IVV", "caderno de especificações", False, extra) if s.get("ivv_caderno_url") else None
    if country == "it":
        if s.get("masaf_pdf_filename") or s.get("masaf_filename"):
            return ("MASAF", "disciplinare di produzione", False, extra)
        if s.get("regional_register_url"):
            # varieties come from a region-wide register, not this IGT's spec
            return ("MASAF", "disciplinare di produzione", True, extra)
        return eu_fallback()
    if country == "de":
        if s.get("ble_produktspezifikation_url"):
            return ("BLE", "Produktspezifikation", False, extra)
        return eu_fallback()
    if country == "si":
        if s.get("specifikacija_url"):
            reg = _PROV_ORG_LABEL.get(s.get("specifikacija_source_org"), "MKGP")
            return (esc(reg), "specifikacija proizvoda", False, extra)
        return eu_fallback()
    if country == "hr":
        if s.get("specifikacija_url"):
            return ("Ministarstvo poljoprivrede", "specifikacija proizvoda", False, extra)
        return eu_fallback()
    if country in _PROV_NATIONAL:
        if s.get("national_spec_url"):
            default_reg, doc = _PROV_NATIONAL[country]
            reg = _PROV_ORG_LABEL.get(s.get("national_spec_source_org"), default_reg)
            return (esc(reg), doc, False, extra)
        return eu_fallback()
    if country == "cz":
        # CZ authorises one national 67-variety list across every wine —
        # always a roster, never an appellation-specific authorisation.
        if s.get("national_spec_url") or s.get("chzo_spec_url"):
            return ("SZPI", "specifikace výrobku", True, extra)
        return None
    if country == "lu":
        return ("IVV", "cahier des charges", False, extra) if s.get("cahier_url") else None
    if country == "ch":
        # NON-EU — never the eAmbrosia register. Canton-level variety lists →
        # roster (drop the grapes clause); the canton name differentiates.
        if s.get("cantonal_reglement_url") and s.get("canton"):
            canton = s.get("canton_name") or str(s["canton"]).upper()
            reg = fmt(lab["provenance_reg_canton"], {"canton": esc(canton)})
            doc = {"de": "kantonales Reglement", "it": "regolamento cantonale"}.get(
                s.get("source_lang") or "fr", "règlement cantonal"
            )
            return (reg, doc, True, "")
        return None
    if country == "be":
        if s.get("eur_lex_url") and has_eambrosia:
            doc = "enig document" if s.get("source_lang") == "nl" else "document unique"
            return (eambrosia_reg, doc, False, extra)
        return None
    if country in ("at", "nl", "mt"):
        return eu_fallback()
    return None


# A grape display name in prose drops the verbatim-cahier cruft the pills keep:
# the ``— synonym`` / ``- synonym`` tail and the trailing OIV colour letter
# (``B.`` / ``N.`` / ``Rs.`` …) — e.g. "Durella B. - Durello" → "Durella",
# "Negro Amaro N. — Negroamaro" → "Negro Amaro".
_GRAPE_SYNONYM_SEP_RE = re.compile(r"\s+[-—]\s+")
_GRAPE_COLOUR_TAIL_RE = re.compile(r"\s+(?:B|N|G|RS|RG)\.\s*$", re.IGNORECASE)


def _provenance_grape_name(g: str, ctx: RenderCtx) -> str:
    name = _GRAPE_SYNONYM_SEP_RE.split(grape_name(g, ctx), 1)[0]
    return _GRAPE_COLOUR_TAIL_RE.sub("", name).strip()


def _provenance_grape_clause(rec: dict, ctx: RenderCtx) -> str:
    """Clean principal-grape display names for the prose line (not the verbatim
    cahier spelling, which carries OIV colour letters and ``— synonym`` tails
    that read as cruft in a sentence). Lists all when ≤ 4; otherwise 3 names +
    a localised ``and N other grape varieties`` tail (N ≥ 2, so the singular
    ``1 other`` is never produced). Empty when the record has no principal
    grapes."""
    slugs = rec.get("grapes_principal") or []
    if not slugs:
        return ""
    if len(slugs) <= 4:
        return ", ".join(esc(_provenance_grape_name(g, ctx)) for g in slugs)
    names = ", ".join(esc(_provenance_grape_name(g, ctx)) for g in slugs[:3])
    return fmt(ctx.labels["provenance_grapes_more"], {"names": names, "n": len(slugs) - 3})


def _provenance_line(rec: dict, ctx: RenderCtx) -> str:
    """A single honest provenance sentence for the crawler-visible card: names
    the regulator + native source document, and (for appellation-specific
    sources only) the authorised principal grapes. Returns '' when no public
    source resolves. Gated by the caller to the factless gap records."""
    resolved = _provenance_source(rec, ctx)
    if not resolved:
        return ""
    regulator, doc, is_roster, extra = resolved
    doc_em = f"<em>{esc(doc)}</em>"
    grapes = "" if is_roster else _provenance_grape_clause(rec, ctx)
    if grapes:
        sentence = fmt(
            ctx.labels["provenance_with_grapes"],
            {"regulator": regulator, "doc": doc_em, "grapes": grapes},
        )
    else:
        sentence = fmt(
            ctx.labels["provenance_bare"],
            {"regulator": regulator, "doc": doc_em, "extra": extra},
        )
    return f'<p class="provenance-line">{sentence}</p>'


# ---------------------------------------------------------------- pills

def _grape_pill(g: str, cls: str, rec: dict, ctx: RenderCtx) -> str:
    info = ctx.grapes_info.get(g)
    has = bool(info and (info.get("extract") or (info.get("vivc_id") and info.get("vivc_url")) or info.get("note")))
    cls2 = " ".join(x for x in ("pill", "grape", cls, "has-info" if has else "") if x)
    cahier_name = to_title_case((rec.get("grape_names") or {}).get(g) or grape_name(g, ctx))
    canon = (
        (info.get("canonical_name") if info else "")
        or (info.get("name_latin") if info else "")
        or (rec.get("grape_names_latin") or {}).get(g)
        or ""
    )
    if canon and not canonical_equals_cahier(canon, cahier_name):
        label_inner = f'{esc(cahier_name)} <span class="canon">({esc(canon)})</span>'
    else:
        label_inner = esc(cahier_name)
    return (
        f'<a class="{cls2}" data-slug="{esc(g)}" href="{esc(grape_url(g, ctx))}" '
        f'target="_blank" rel="noopener">{label_inner}</a>'
    )


def _style_chips(rec: dict, ctx: RenderCtx) -> str:
    out = []
    for s in rec.get("styles") or []:
        safe = esc(s)
        info = ctx.styles_info.get(s)
        has = bool(info and info.get("extract"))
        cls = " ".join(x for x in ("pill", "style", f"style--{safe}", "has-info" if has else "") if x)
        label = to_title_case(ctx.style_labels.get(s, s))
        if has and info.get("page_url"):
            out.append(
                f'<a class="{cls}" data-slug="{safe}" href="{esc(info["page_url"])}" '
                f'target="_blank" rel="noopener">{label}</a>'
            )
        else:
            tab = ' tabindex="0"' if has else ""
            out.append(f'<span class="{cls}" data-slug="{safe}"{tab}>{label}</span>')
    return "".join(out)


# ---------------------------------------------------------------- meta lines

def _meta_tail(rec: dict, ctx: RenderCtx) -> str:
    gs = rec.get("geom_source")
    if gs in ("aires-csv", "dgc-village-override"):
        return " · " + fmt(ctx.labels["meta_communes_inao"], {"n": rec.get("communes_matched") or 0})
    cm = rec.get("communes_matched")
    if gs not in (
        "parcellaire", "parcellaire-dgc", "aires-csv-dgc",
        "cadastre-lieu-dit-dgc", "sibling-dgc", "parent-appellation",
    ) and cm is not None and cm > 0:
        return " · " + fmt(ctx.labels["meta_communes"], {"n": cm})
    return ""


def _approx_line(rec: dict, ctx: RenderCtx) -> str:
    lab = ctx.labels
    gs = rec.get("geom_source")
    if gs == "sibling-dgc" and rec.get("geom_fallback_slug"):
        u = (
            f'<a class="parent-link" data-slug="{esc(rec["geom_fallback_slug"])}" href="#">'
            f'{esc(rec.get("geom_fallback_name") or rec["geom_fallback_slug"])}</a>'
        )
        return f'<div class="approx-line">{fmt(lab["geom_approx_within"], {"umbrella": u})}</div>'
    if gs == "parent-appellation":
        return f'<div class="approx-line">{esc(lab["geom_approx_parent"])}</div>'
    if gs == "aires-csv-dgc":
        return f'<div class="approx-line">{esc(lab["geom_approx_aires"])}</div>'
    if gs == "cadastre-lieu-dit-dgc" and rec.get("cadastre_lieu_dit"):
        src = (
            '<a href="https://cadastre.data.gouv.fr/" target="_blank" rel="noopener">'
            f'{esc(lab["geom_approx_cadastre_source_label"])}</a>'
        )
        return (
            f'<div class="approx-line">{fmt(lab["geom_approx_cadastre"], {"lieu_dit": esc(rec["cadastre_lieu_dit"]), "commune": esc(rec.get("cadastre_commune") or ""), "source": src})}</div>'
        )
    return ""


# ---------------------------------------------------------------- entry point

def _section(heading: str, pills: str) -> str:
    return f'<h2>{heading}</h2><div class="pills">{pills}</div>' if pills else ""


def render_subappellations(children, ctx: RenderCtx, country: str | None = None) -> str:
    """Crawlable list of an appellation's sub-denominations (DGCs / subzonas /
    Einzellagen / sottozone / …).

    Sub-denominations are folded (``noindex``) as parent-inherited near-
    duplicates, so they have no indexable page of their own. This section is how
    their names enter the indexable surface — each child rendered as real text +
    a link on the *parent's* own page (which earns ranking for the child name),
    paired with the parent's JSON-LD ``containsPlace``. ``children`` items are
    ``{name, path, kind}`` dicts, pre-resolved by the caller (URL logic lives in
    ``map_template``, not here). The heading is the regulator's own term for the
    parent's ``country`` (:data:`SUBDENOM_HEADINGS`), falling back to the generic
    translated ``entity_nav_children`` label."""
    children = children or []
    if not children:
        return ""
    heading = SUBDENOM_HEADINGS.get(country or "") or ctx.labels["entity_nav_children"]
    items = []
    for c in children:
        name = esc(c.get("name") or "")
        path = c.get("path") or ""
        link = f'<a href="{esc(path)}">{name}</a>' if path else name
        kind = c.get("kind") or ""
        kind_html = f' <span class="sub-kind">{esc(kind)}</span>' if kind else ""
        items.append(f"<li>{link}{kind_html}</li>")
    return (
        f'<h2>{esc(heading)}</h2>'
        f'<ul class="subappellations">{"".join(items)}</ul>'
    )


def _normalised_text(html: str) -> str:
    """Visible text only, whitespace-collapsed — the basis for data-ssr-sig."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def render_content_block(rec: dict, slug: str, ctx: RenderCtx, children=None) -> str:
    """Server-rendered crawlable summary of one appellation record.

    Mirrors the JS ``renderAocCard`` minus the volatile HU/IT chip sections.
    Returns a self-contained ``<article id="ssr-content" …>``; the client panel
    replaces it on hydration. ``children`` (pre-resolved ``{name, path, kind}``
    dicts) renders a sub-appellations section so the parent page carries its
    folded sub-denominations' names — see :func:`render_subappellations`."""
    lab = ctx.labels
    country = rec.get("country") or "fr"

    style_chips = _style_chips(rec, ctx)
    principal = "".join(_grape_pill(g, "", rec, ctx) for g in (rec.get("grapes_principal") or []))
    accessory = "".join(
        _grape_pill(g, "accessory", rec, ctx) for g in (rec.get("grapes_accessory") or [])
    )
    observation = "".join(
        _grape_pill(g, "observation", rec, ctx) for g in (rec.get("grapes_observation") or [])
    )
    pt_role_disclaimer = (
        f'<div class="role-disclaimer">{esc(lab["pt_role_disclaimer"])}</div>'
        if country == "pt" and principal
        else ""
    )

    region = region_label(rec["region"], ctx) if rec.get("region") else ""
    region_seg = f" · {esc(region)}" if region else ""
    country_chip = country_chip_html(country, rec.get("country_aliases"), ctx)
    country_seg = f"{country_chip} · " if country_chip else ""
    meta_tail = _meta_tail(rec, ctx)

    dgc_line = (
        f'<div class="dgc-line">{esc(lab["dgc_of"])} '
        f'<a class="parent-link" data-slug="{esc(rec["parent_slug"])}" href="#">'
        f'{esc(rec.get("parent_name") or rec["parent_slug"])}</a></div>'
        if rec.get("is_sub_denomination") and rec.get("parent_slug")
        else ""
    )
    approx_line = _approx_line(rec, ctx)
    stub_line = (
        f'<div class="approx-line">{fmt(lab["stub_message"], {"doc": "<em>" + esc(STUB_DOC_NAMES.get(country, STUB_DOC_NAMES["fr"])) + "</em>"})} '
        f'<a class="stub-help" href="{esc(ctx.github_new_issue_url)}" target="_blank" rel="noopener">'
        f'{esc(lab["stub_help_label"])}</a></div>'
        if rec.get("is_stub")
        else ""
    )

    facts_block = render_terroir_facts(rec, ctx)
    is_translated = bool(rec.get("summary_translation"))
    summary_marker = "" if is_translated else _src_marker(country, ctx)
    if not facts_block and rec.get("summary"):
        summary = (
            f"<p>{esc(rec['summary'])}{summary_marker}</p>"
            f"{_translation_attribution(rec.get('summary_translation'), country, ctx)}"
        )
    else:
        summary = ""

    note = rec.get("note")
    if note and note.get("text"):
        srcs = note.get("sources") or []
        srcs_html = (
            '<div class="note-srcs">'
            + "".join(
                f'<a href="{esc(s.get("url"))}" target="_blank" rel="noopener">{esc(s.get("label"))}</a>'
                for s in srcs
            )
            + "</div>"
            if srcs
            else ""
        )
        note_block = f'<div class="appellation-note"><div class="note-text">ⓘ {esc(note["text"])}</div>{srcs_html}</div>'
    else:
        note_block = ""

    # Honest provenance sentence — only where the card would otherwise emit
    # nothing between the pills and the Sources heading (no terroir facts and
    # no summary). Fills the factless long-tail records with a sourced,
    # answer-engine-liftable line naming the regulator + source document.
    provenance = _provenance_line(rec, ctx) if not facts_block and not summary else ""

    inner = (
        f"<h1>{name_with_latin(rec)}</h1>"
        f'<div class="meta">{country_seg}{esc(rec.get("kind") or "")}{region_seg}{meta_tail}</div>'
        f"{dgc_line}{approx_line}{stub_line}"
        f"{_section(lab['panel_styles_h'], style_chips)}"
        f"{_section(lab['facet_principal_h'], principal)}"
        f"{pt_role_disclaimer}"
        f"{_section(lab['facet_accessory_h'], accessory)}"
        f"{_section(lab['panel_observation_h'], observation)}"
        f"{facts_block or summary}"
        f"{note_block}"
        f"{render_subappellations(children, ctx, country)}"
        f"{provenance}"
        f"{render_sources(rec.get('sources'), ctx)}"
    )
    sig = hashlib.sha256(_normalised_text(inner).encode("utf-8")).hexdigest()[:16]
    return f'<article id="ssr-content" class="aoc-card" data-ssr-sig="{sig}">{inner}</article>'
