"""Czech-keyword tables for parsing the EUR-Lex "JEDNOTNÝ DOKUMENT".

Structurally identical to the Slovak parser (same `<p class="ti-grseq-1">`
section header tags, same numbered subsections, same single-document
anchor — the Czech word "JEDNOTNÝ DOKUMENT" happens to be identical to
the Slovak one). This module only contributes the **Czech-language
tables** that map section titles → semantic roles; the extraction
machinery (regex for headers, slice-from-anchor) lives in
`scripts/cz/02_extract_pliegos.py` and reuses the SI / HR / SK idiom.

Czech EU-OJ single-document template:

  1.  Název                                       — name(s)
  2.  Druh zeměpisného označení                   — PDO / PGI
  3.  Kategorie výrobků z révy vinné              — categories
  4.  Popis vína                                  — description
  5.  Enologické postupy                          — practices + max yields
  6.  Vymezená zeměpisná oblast                   — area
  7.  Hlavní moštové odrůdy                       — grape varieties
  8.  Popis souvislostí                           — link to terroir
  9.  Další základní podmínky                     — labelling, packaging

In v1 none of the 13 CZ wines carry a fetchable EU single document —
they all ship as content-stubs awaiting curator-pinned URLs. The
keyword tables ship pre-wired so a single curator-pinned EU-OJ URL
unlocks parsing without code changes.
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*JEDNOTNÝ\s+DOKUMENT\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. route_sections iterates keywords
# most-specific-first, then sections in document order.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "název",
        "název produktu",
    ),
    "category": (
        "kategorie výrobků z révy vinné",
        "kategorie",
        "druh zeměpisného označení",
        "sektor",
    ),
    "description": (
        "popis vína",
        "popis vín",
        "popis výrobku",
        "popis produktu",
    ),
    "viticultural_practices": (
        "enologické postupy",
        "vinařské postupy",
        "maximální výnosy",
        "nejvyšší výnosy",
    ),
    "geo_area": (
        "vymezená zeměpisná oblast",
        "vymezení zeměpisné oblasti",
        "zeměpisná oblast",
        "stručný popis vymezené zeměpisné oblasti",
    ),
    "grape_varieties": (
        "hlavní moštové odrůdy",
        "moštové odrůdy",
        "moštová odrůda",
        "odrůdy révy vinné",
        "hlavní odrůdy révy vinné",
    ),
    "link_to_terroir": (
        "popis souvislostí",
        "popis souvislosti",
        "souvislost se zeměpisnou oblastí",
        "souvislost",
    ),
    "additional_conditions": (
        "další základní podmínky",
        "další podmínky",
        "jiné podmínky",
        "další základní požadavky",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`.
_GEO_AREA_TITLE_BLOCKLIST = (
    "druh zeměpisného označení",
    "kategorie výrobků z révy vinné",
)


# Grape role headers inside the grape-variety section. Czech single
# documents — when they exist — rarely carry an explicit principal/
# accessory split. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(hlavn[íý]|doporučen[éý]|doporucen[éý]|povolen[éý]|"
    r"doplňkov[éý]|doplnkov[éý])\s*"
    r"(?:odrůdy?|moštové\s+odrůdy?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "hlavn": "principal",
    "dopor": "principal",
    "povolen": "accessory",
    "doplň": "accessory",
    "dopln": "accessory",
}


# Czech colour vocabulary for style detection.
COLOUR_BY_KEYWORD = {
    "červené víno": "noir",
    "červená vína": "noir",
    "červených vín": "noir",
    "bílé víno": "blanc",
    "bílá vína": "blanc",
    "bílých vín": "blanc",
    "růžové víno": "rose",
    "růžová vína": "rose",
    "rosé víno": "rose",
    "klaret": "rose",
}


# Style markers in Czech, mapped to the shared style-taxonomy slugs.
# Czech wine-law predikat ladder: pozdní sběr / výběr z hroznů / výběr
# z bobulí / výběr z cibéb / ledové víno / slámové víno.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(šumivé|šumivá|šumivý|šumivého)\s+vín[oa]?\b", re.I), "sparkling"),
    (re.compile(r"\bperlivé\b", re.I), "semi-sparkling"),
    (re.compile(r"\bslámové víno\b", re.I), "vin-de-paille"),
    (re.compile(r"\bledové víno\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bpozdní sběr\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvýběr z hroznů\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvýběr z bobulí\b", re.I), "grains-nobles"),
    (re.compile(r"\bvýběr z cibéb\b", re.I), "grains-nobles"),
    (re.compile(r"\bslámové\b", re.I), "vin-de-paille"),
    (re.compile(r"\bsuché víno\b", re.I), "dry"),
)
