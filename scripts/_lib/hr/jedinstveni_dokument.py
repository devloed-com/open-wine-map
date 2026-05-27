"""Croatian-keyword tables for parsing the EUR-Lex "JEDINSTVENI DOKUMENT".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/hr/02_extract_pliegos.py` and reuses the ES / IT / AT / SI idiom
directly; this module contributes only the **Croatian-language tables**
that map section titles → semantic roles.

Croatian EU-OJ single-document template (as seen in the Muškat momjanski
and Ponikve JEDINSTVENI DOKUMENT publications):

  1.  Naziv koji je potrebno upisati u registar    — name(s)
  2.  Vrsta oznake zemljopisnog podrijetla         — PDO / PGI (ZOI / ZOZP)
  3.  Kategorije proizvoda od vinove loze          — categories
  4.  Opis vina                                    — description
  5.  Enološki postupci                            — practices + max yields
  6.  Razgraničeno zemljopisno područje            — area
  7.  Glavne sorte vinove loze                     — grape varieties
  8.  Opis povezanosti                             — link to terroir
  9.  Daljnji uvjeti / Upućivanje na objavu        — additional / reference

route_sections in stage 02 uses title-keyword matching to stay template-
agnostic across both the older `ti-grseq-1` and newer `oj-ti-grseq-1`
templates.
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*JEDINSTVENI\s+DOKUMENT\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. route_sections iterates keywords
# most-specific-first, then sections in document order. Croatian is
# heavily inflected, so keywords keep the genitive/locative forms that
# actually appear in the template titles.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "naziv koji je potrebno upisati u registar",
        "naziv proizvoda",
        "naziv",
    ),
    "category": (
        "kategorije proizvoda od vinove loze",
        "vrsta oznake zemljopisnog podrijetla",
        "kategorije proizvoda",
    ),
    "description": (
        "opis vina",
        "opis proizvoda",
    ),
    "viticultural_practices": (
        "enološki postupci",
        "enoloski postupci",
        "maksimalni urod",
        "maksimalni prinos",
    ),
    "geo_area": (
        "razgraničeno zemljopisno područje",
        "razgraniceno zemljopisno podrucje",
        "zemljopisno područje",
        "zemljopisno podrucje",
        "definirano područje",
        "definirano podrucje",
    ),
    "grape_varieties": (
        "glavne sorte vinove loze",
        "glavne vinske sorte",
        "vinske sorte",
        "sorte vinove loze",
        "sorta vinove loze",
    ),
    "link_to_terroir": (
        "opis povezanosti",
        "povezanost s područjem proizvodnje",
        "povezanost s podrucjem proizvodnje",
        "povezanost",
    ),
    "additional_conditions": (
        "daljnji uvjeti",
        "dodatni uvjeti",
        "ostali uvjeti",
        "upućivanje na objavu",
        "upucivanje na objavu",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title contains a role keyword. Section 2 ("Vrsta oznake
# zemljopisnog podrijetla") carries "zemljopisnog" but its body is just
# "ZOI" / "ZOZP".
_GEO_AREA_TITLE_BLOCKLIST = (
    "vrsta oznake zemljopisnog podrijetla",
    "kategorije proizvoda od vinove loze",
)


# Grape role headers inside the grape-variety section. Croatian single
# documents rarely carry a principal/accessory split — the section is
# usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(glavne?|preporučene?|preporucene?|dopuštene?|dopustene?|dopunske?)\s*"
    r"(?:sorte?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "glavn": "principal",
    "preporu": "principal",
    "dopust": "accessory",
    "dopun": "accessory",
}


# Croatian colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "crno vino": "noir",
    "crna vina": "noir",
    "crnih vina": "noir",
    "crveno vino": "noir",
    "bijelo vino": "blanc",
    "bijela vina": "blanc",
    "bijelih vina": "blanc",
    "ružičasto vino": "rose",
    "ruzicasto vino": "rose",
    "ružičasta vina": "rose",
    "ruzicasta vina": "rose",
    "rosé vino": "rose",
    "rose vino": "rose",
}


# Style markers in Croatian, mapped to the shared style-taxonomy slugs.
# The Croatian Predikat ladder (kasna berba / izborna berba / izborna berba
# bobica / izborna berba prosušenih bobica / ledeno vino / desertno vino /
# arhivsko vino) maps onto the late-harvest / noble-rot / dessert leaves.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(pjenušac|pjenušavo vino|pjenušava vina)\b", re.I), "sparkling"),
    (re.compile(r"\bbiser(?:no vino|na vina)?\b", re.I), "semi-sparkling"),
    (re.compile(r"\bprošek\b", re.I), "vin-de-paille"),
    (re.compile(r"\bizborna berba prosušenih bobica\b", re.I), "grains-nobles"),
    (re.compile(r"\bizborna berba bobica\b", re.I), "grains-nobles"),
    (re.compile(r"\bledeno vino\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bkasna berba\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bizborna berba\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bdesertno vino\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bsuho vino\b", re.I), "dry"),
)
