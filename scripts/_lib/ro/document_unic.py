"""Romanian-keyword tables for parsing the EUR-Lex "DOCUMENT UNIC".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/ro/02_extract_pliegos.py` and reuses the ES / IT / AT / SI / HR
/ HU idiom directly; this module contributes only the **Romanian-language
tables** that map section titles → semantic roles.

Romanian EU-OJ single-document template (as seen across the 34 RO
DOCUMENT UNIC publications — Drăgăşani, Cotnari, Recaș, Murfatlar,
Dealu Mare, Târnave, …):

  1.  Denumire (denumiri)                              — name
  2.  Tipul indicației geografice                      — PDO / PGI (DOP / IGP)
  3.  Categoriile de produse vitivinicole              — categories
  4.  Descrierea vinurilor                             — description
  5.  Practici vitivinicole / oenologice               — practices + max yields
  6.  Aria geografică delimitată                       — area
  7.  Soiul (soiurile) principal(e) de struguri        — grape varieties
  8.  Descrierea legăturii (legăturilor)               — link to terroir
  9.  Alte condiții esențiale / Trimitere la publicare — additional / reference

Some older publications use the modification-preamble form
"DOCUMENTUL UNIC" (definite article); both forms are matched.
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*DOCUMENT(?:UL)?\s+UNIC\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. route_sections iterates keywords
# most-specific-first, then sections in document order. Romanian is a
# Romance language with rich inflection (definite-article suffixes -ul,
# -ului, -urilor); keywords are stored in lowercase, ASCII-folded forms
# alongside the diacritic-bearing originals so the title-match works
# against both stripped and original casings.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "denumire/denumiri",
        "denumire (denumiri)",
        "denumire de bun rangul",
        "denumirea care urmează a fi înregistrată",
        "denumirea care urmeaza a fi inregistrata",
        "denumirea/denumirile",
        "denumire",
    ),
    "category": (
        "categoriile de produse vitivinicole",
        "categorii de produse vitivinicole",
        "tipul indicației geografice",
        "tipul indicatiei geografice",
        "tip de indicație geografică",
        "tip de indicatie geografica",
        "categoriile",
        "categorii",
    ),
    "description": (
        "descrierea vinurilor",
        "descrierea vinului",
        "descrierea produsului",
        "descriere",
    ),
    "viticultural_practices": (
        "practici vitivinicole",
        "practici oenologice",
        "practicile vitivinicole",
        "practicile oenologice",
        "randamente maxime",
        "producția maximă",
        "productia maxima",
    ),
    "geo_area": (
        "aria geografică delimitată",
        "aria geografica delimitata",
        "zona geografică delimitată",
        "zona geografica delimitata",
        "arealul delimitat",
        "aria delimitată",
        "aria delimitata",
    ),
    "grape_varieties": (
        "soiul/soiurile principale de struguri de vinificație",
        "soiul/soiurile principale de struguri de vinificatie",
        "soiul (soiurile) principal(e) de struguri",
        "soiurile principale de struguri",
        "soiul principal de struguri",
        "soiuri de struguri",
        "soiurile de struguri",
        "soiul de struguri",
        "soiuri",
    ),
    "link_to_terroir": (
        "descrierea legăturii (legăturilor)",
        "descrierea legaturii (legaturilor)",
        "descrierea legăturii",
        "descrierea legaturii",
        "legătura cu aria delimitată",
        "legatura cu aria delimitata",
        "legătura cu zona geografică",
        "legatura cu zona geografica",
        "legătura cauzală",
        "legatura cauzala",
        "legătura",
        "legatura",
    ),
    "additional_conditions": (
        "alte condiții esențiale",
        "alte conditii esentiale",
        "alte condiții",
        "alte conditii",
        "condiții suplimentare",
        "conditii suplimentare",
        "trimitere la publicarea caietului",
        "trimitere la publicare",
        "linkul la specificațiile produsului",
        "linkul la specificatiile produsului",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title carries a related keyword. Section 2 ("Tipul
# indicației geografice") carries "geografice" inflected but its body
# is just "DOP" / "IGP".
_GEO_AREA_TITLE_BLOCKLIST = (
    "tipul indicației geografice",
    "tipul indicatiei geografice",
    "tip de indicație geografică",
    "tip de indicatie geografica",
    "categoriile de produse vitivinicole",
    "categorii de produse vitivinicole",
)


# Grape role headers inside the grape-variety section. Romanian DOCUMENT
# UNIC publications rarely carry a principal/accessory split — the
# section is usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(principal[ăea]?|principale|secundar[ăea]?|secundare|recomandat[ăea]?|"
    r"autorizat[ăea]?|admis[ăea]?|complementar[ăea]?)\s*(?:soiur[ie])?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "princip": "principal",
    "recoman": "principal",
    "autori": "principal",
    "admis": "principal",
    "secund": "accessory",
    "complement": "accessory",
}


# Romanian colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "vin alb": "blanc",
    "vinuri albe": "blanc",
    "vin roșu": "noir",
    "vin rosu": "noir",
    "vinuri roșii": "noir",
    "vinuri rosii": "noir",
    "vin roze": "rose",
    "vin rosé": "rose",
    "vinuri roze": "rose",
    "vinuri rosé": "rose",
    "vin rozé": "rose",
    "vinuri rozé": "rose",
}


# Style markers in Romanian, mapped to the shared style-taxonomy slugs.
# Romanian late-harvest / botrytised / dessert vocabulary covers the
# Cotnari Grasă (botrytis) and Murfatlar dessert tradition; the
# `pelin`-style aromatised wines fall outside the wine-GI scope.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bvin\s+spumant\b|\bvinuri\s+spumante\b", re.I), "sparkling"),
    (re.compile(r"\bvin\s+spumos\b|\bvinuri\s+spumoase\b", re.I), "sparkling"),
    (re.compile(r"\bvin\s+petiant\b|\bvin\s+perlant\b", re.I), "semi-sparkling"),
    (re.compile(r"\bcules\s+t[âa]rziu\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvin\s+de\s+ghea[țt][ăa]\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvin\s+de\s+desert\b|\bvinuri\s+de\s+desert\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bcules\s+selec(?:t|ț)ionat\s+de\s+boabe\s+nobile\b", re.I), "grains-nobles"),
    (re.compile(r"\bselec(?:t|ț)ie\s+de\s+boabe\s+nobile\b", re.I), "grains-nobles"),
    (re.compile(r"\bbotritizat\b|\bbotritis\b", re.I), "grains-nobles"),
    (re.compile(r"\bcules\s+selec(?:t|ț)ionat\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvin\s+licoros\b|\bvinuri\s+licoroase\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bvin\s+sec\b|\bvinuri\s+seci\b", re.I), "dry"),
)
