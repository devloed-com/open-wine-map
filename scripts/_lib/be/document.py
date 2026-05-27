"""Section-keyword tables for the EU-OJ single-document templates used
by Belgian wine GIs.

Belgium publishes its single documents in either Dutch (Flemish wines:
"ENIG DOCUMENT") or French (Walloon wines: "DOCUMENT UNIQUE"). The
HTML template is otherwise identical to every other EU country's
single document — same `<p class="ti-grseq-1">` section headers, same
numbered subsections — so the HTML-extraction machinery (regex for
headers, slice-from-anchor) lives in `scripts/be/02_extract_pliegos.py`
and reuses the SK/SI idiom directly; this module contributes only the
**per-language tables** that map section titles → semantic roles.

Standard EU single-document template:
  1.  Naam / Dénomination(s)                     — name(s)
  2.  Type geografische aanduiding /             — PDO / PGI
      Type d'indication géographique
  3.  Categorieën van wijnbouwproducten /        — categories
      Catégories de produits de la vigne
  4.  Beschrijving van de wijn(en) /             — description
      Description du / des vin(s)
  5.  Wijnbereidingsprocedés /                   — practices + max yields
      Pratiques vitivinicoles
  6.  Afgebakend geografisch gebied /            — area
      Zone géographique délimitée
  7.  Wijndruivenras(sen) /                      — grape varieties
      Cépage(s) principal / aux
  8.  Beschrijving van het (de) verband(en) /    — link to terroir
      Description du / des lien(s)
  9.  Andere essentiële voorwaarden /            — labelling, packaging
      Autres conditions essentielles

Anchors in each template:
  - NL  "ENIG DOCUMENT"
  - FR  "DOCUMENT UNIQUE"

Picking the per-record language: callers select the table set via the
record's `source_lang` field (`"nl"` or `"fr"`).
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------- anchors --

DOC_ANCHOR_RE = {
    # Older OJ publications wrap the anchor text in <span class="bold">,
    # newer ones put it bare. Tolerate both.
    "nl": re.compile(
        r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>'
        r'(?:\s*<[^>]+>)*\s*ENIG\s+DOCUMENT\s*(?:</[^>]+>\s*)*</p>',
        re.I | re.S,
    ),
    "fr": re.compile(
        r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>'
        r'(?:\s*<[^>]+>)*\s*DOCUMENT\s+UNIQUE\s*(?:</[^>]+>\s*)*</p>',
        re.I | re.S,
    ),
}

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role, per source language.
# route_sections iterates keywords most-specific-first, then sections in
# document order.
SECTION_ROLE_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "nl": {
        "name": (
            "naam/namen",
            "namen waarvoor",
            "naam",
        ),
        "category": (
            "categorieën van wijnbouwproducten",
            "categorieen van wijnbouwproducten",
            "categorieën",
            "categorieen",
            "type geografische aanduiding",
            "sector",
        ),
        "description": (
            "beschrijving van de wijn",
            "beschrijving van het wijn",
            "beschrijving van het product",
        ),
        "viticultural_practices": (
            "wijnbereidingsprocedés",
            "wijnbereidingsprocedes",
            "oenologische procedés",
            "oenologische procedes",
            "maximumopbrengsten",
        ),
        "geo_area": (
            "afgebakend geografisch gebied",
            "afgebakend gebied",
            "geografisch gebied",
            # Flemish overheid wording variants
            "geografische gebied",
            "afbakening van het betrokken geografische gebied",
            "afbakening van het",
        ),
        "grape_varieties": (
            "wijndruivenras",
            "wijndruivenrassen",
            "voornaamste wijndruiven",
            "wijndruiven",
            "druivenrassen",
        ),
        "link_to_terroir": (
            "beschrijving van het (de) verband",
            "beschrijving van het verband",
            "beschrijving van de verband",
            "beschrijving van de verbanden",
            "verband",
            "verbanden",
        ),
        "additional_conditions": (
            "andere essentiële voorwaarden",
            "andere essentiele voorwaarden",
            "andere voorwaarden",
            "essentiële voorwaarden",
            "essentiele voorwaarden",
        ),
    },
    "fr": {
        "name": (
            "dénomination(s)",
            "denomination(s)",
            "dénomination",
            "denomination",
            "nom",
        ),
        "category": (
            "catégories de produits de la vigne",
            "categories de produits de la vigne",
            "catégories",
            "categories",
            "type d'indication géographique",
            "type d'indication geographique",
        ),
        "description": (
            "description du vin",
            "description des vins",
            "description du / des vin",
            "description du/des vin",
        ),
        "viticultural_practices": (
            "pratiques vitivinicoles",
            "pratiques œnologiques",
            "pratiques oenologiques",
            "rendements maximaux",
            "rendement maximal",
        ),
        "geo_area": (
            "zone géographique délimitée",
            "zone geographique delimitee",
            "zone délimitée",
            "zone delimitee",
            "aire géographique",
            "aire geographique",
        ),
        "grape_varieties": (
            "cépage(s) principal",
            "cepage(s) principal",
            "cépages principaux",
            "cepages principaux",
            "cépage principal",
            "cepage principal",
            "principale(s) variété(s) à raisins de cuve",
            "variétés de raisins",
            "varietes de raisins",
            "cépage",
            "cepage",
        ),
        "link_to_terroir": (
            "description du (des) lien(s)",
            "description du / des lien",
            "description du/des lien",
            "description du lien",
            "description des liens",
            "lien avec",
            "lien au terroir",
        ),
        "additional_conditions": (
            "autres conditions essentielles",
            "autres conditions",
            "conditions essentielles",
        ),
    },
}


# Title-prefix that disqualifies a section from `geo_area` even when
# the title contains a role keyword (e.g. section 2 "Type indication
# géographique" carries "géographique" but isn't the area).
_GEO_AREA_TITLE_BLOCKLIST = {
    "nl": (
        "type geografische aanduiding",
        "categorieën van wijnbouwproducten",
        "categorieen van wijnbouwproducten",
    ),
    "fr": (
        "type d'indication géographique",
        "type d'indication geographique",
        "catégories de produits de la vigne",
        "categories de produits de la vigne",
    ),
}


# Grape role headers inside the grape-variety section. The EU single
# document occasionally splits principal vs accessory; the template is
# usually flat. Defaults to "principal".
_GRAPE_ROLE_HEADER_NL_SRC = (
    r"\b(voornaamste|hoofd|principale|geautoriseerde|toegestane|"
    r"bijkomende|aanvullende)\s*"
    r"(?:druivenras(?:sen)?|wijndruiven(?:ras(?:sen)?)?|rassen)?\s*:?\s*"
)
_GRAPE_ROLE_HEADER_FR_SRC = (
    r"\b(principal[aeux]*|primaire[s]?|secondaire[s]?|accessoire[s]?|"
    r"complémentaire[s]?|complementaire[s]?|autoris[ée]e?s?)\s*"
    r"(?:cépages?|cepages?|variétés?|varietes?)?\s*:?\s*"
)

ROLE_HEADER_RE = {
    "nl": re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_NL_SRC}$", re.IGNORECASE),
    "fr": re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_FR_SRC}$", re.IGNORECASE),
}
INLINE_ROLE_RE = {
    "nl": re.compile(_GRAPE_ROLE_HEADER_NL_SRC, re.IGNORECASE),
    "fr": re.compile(_GRAPE_ROLE_HEADER_FR_SRC, re.IGNORECASE),
}

ROLE_BY_KEYWORD = {
    "nl": {
        "voornaamste": "principal",
        "hoofd": "principal",
        "principale": "principal",
        "geautoriseerde": "principal",
        "toegestane": "principal",
        "bijkomende": "accessory",
        "aanvullende": "accessory",
    },
    "fr": {
        "principal": "principal",
        "primaire": "principal",
        "secondaire": "accessory",
        "accessoire": "accessory",
        "complémentaire": "accessory",
        "complementaire": "accessory",
        "autoris": "principal",
    },
}


# Lines inside the grape-variety section that are role-section labels
# (filter these out — they only set state, never count as a variety).
_GRAPE_LINE_DROP = {
    "nl": (
        "wijndruivenras", "wijndruivenrassen", "druivenrassen",
        "voornaamste", "hoofd", "geautoriseerde", "toegestane",
        "bijkomende", "aanvullende",
    ),
    "fr": (
        "cépage", "cepage", "cépages", "cepages",
        "principal", "principaux",
        "secondaire", "secondaires", "accessoire", "accessoires",
        "complémentaire", "complementaire",
        "autorisé", "autorise", "autorisée", "autorisee",
    ),
}


# Colour vocabulary per source language. Used by parse_styles.
COLOUR_BY_KEYWORD: dict[str, dict[str, str]] = {
    "nl": {
        "rode wijn": "noir",
        "rode wijnen": "noir",
        "witte wijn": "blanc",
        "witte wijnen": "blanc",
        "rosé wijn": "rose",
        "rosé wijnen": "rose",
        "rose wijn": "rose",
    },
    "fr": {
        "vin rouge": "noir",
        "vins rouges": "noir",
        "vin blanc": "blanc",
        "vins blancs": "blanc",
        "vin rosé": "rose",
        "vins rosés": "rose",
        "vin rose": "rose",
        "vins roses": "rose",
    },
}


# Style markers per source language, mapped to shared style-taxonomy slugs.
# Belgium produces still wines plus crémants/mousseux and one Limburg-side
# late-harvest tradition. Keep this conservative.
STYLE_MARKERS: dict[str, tuple[tuple[re.Pattern, str], ...]] = {
    "nl": (
        (re.compile(r"\bmousserend(e)?\s+kwaliteitswijn(en)?\b", re.I), "sparkling-quality"),
        (re.compile(r"\bmousserend(e)?\s+wijn(en)?\b", re.I), "sparkling"),
        (re.compile(r"\bparelwijn\b", re.I), "semi-sparkling"),
        (re.compile(r"\bcrémant\b|\bcremant\b", re.I), "cremant"),
        (re.compile(r"\blikeurwijn(en)?\b", re.I), "vin-de-liqueur"),
        (re.compile(r"\bwijn uit overrijpe druiven\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bwijn uit gerimpelde druiven\b", re.I), "vin-de-paille"),
        (re.compile(r"\blate\s+oogst\b|\blaat\s+geoogst\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bijswijn\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bdroge wijn(en)?\b", re.I), "dry"),
    ),
    "fr": (
        (re.compile(r"\bvin(s)?\s+mousseux\s+de\s+qualité\b", re.I), "sparkling-quality"),
        (re.compile(r"\bvin(s)?\s+mousseux\b", re.I), "sparkling"),
        (re.compile(r"\bcrémant\b|\bcremant\b", re.I), "cremant"),
        (re.compile(r"\bvin(s)?\s+pétillant\b", re.I), "semi-sparkling"),
        (re.compile(r"\bvin\s+de\s+liqueur\b", re.I), "vin-de-liqueur"),
        (re.compile(r"\bvin(s)?\s+de\s+raisins\s+surm[ûu]ris\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bvin(s)?\s+de\s+raisins\s+pass[eé]rill[eé]s\b", re.I), "vin-de-paille"),
        (re.compile(r"\bvendanges\s+tardives\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bvin\s+de\s+glace\b", re.I), "vendanges-tardives"),
        (re.compile(r"\bvin(s)?\s+sec(s)?\b", re.I), "dry"),
    ),
}
