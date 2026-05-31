"""English-keyword tables for parsing the EUR-Lex "SINGLE DOCUMENT".

Malta is the first country in the corpus whose EU single documents are
published in **English** (`source_lang="en"`). English is a co-official
language of Malta, and eAmbrosia's `publications[].uri` for both Maltese
PDOs (Malta PDO-MT-A1630, Gozo PDO-MT-A1629) points at the English
(`…01.ENG`) variant of the EU-OJ "SINGLE DOCUMENT". Using English as the
source language is also convenient: EN is the canonical rendered surface
(`/`), so the extracted narrative needs no machine translation for the
homepage — stage 02e only translates the terroir bullets into fr/es/nl.

English EU-OJ single-document template (post-2019 Reg. (EU) 2019/33):

  1.  Name(s)                                       — name(s)
  2.  Geographical indication type                  — PDO / PGI
  3.  Categories of grapevine products              — categories
  4.  Description of the wine(s)                     — description
  5.  Wine making practices                          — practices + max yields
  6.  Demarcated geographical area                   — area
  7.  Main wine grapes variety(ies)                  — grape varieties
  8.  Description of the link(s)                      — link to terroir
  9.  Essential further conditions                    — labelling, packaging

Both Malta documents are "STANDARD AMENDMENT" communications — the
substantive SINGLE DOCUMENT slab appears after an amendment preamble, so
the anchor matches the standalone `SINGLE DOCUMENT` paragraph (NOT the
`COMMUNICATION OF STANDARD AMENDMENT MODIFYING THE SINGLE DOCUMENT`
preamble that merely contains the phrase). Sections 4 and 5 carry nested
`<p class="ti-grseq-1">` subsections that restart numbering at 1
(per-wine-type descriptions, per-variety oenological practices) — the
monotonic-number guard in `scripts/mt/02_extract_pliegos.py` keeps those
from shadowing the real top-level sections 5-9 (the HU/BG idiom).
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*SINGLE\s+DOCUMENT\s*</p>',
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
        "name(s)",
        "name",
    ),
    "category": (
        "categories of grapevine products",
        "categories",
        "geographical indication type",
    ),
    "description": (
        "description of the wine",
        "description of the product",
    ),
    "viticultural_practices": (
        "wine making practices",
        "winemaking practices",
        "specific oenological practices",
        "maximum yields",
    ),
    "geo_area": (
        "demarcated geographical area",
        "geographical area",
        "defined geographical area",
    ),
    "grape_varieties": (
        "main wine grapes variety",
        "main wine grape variety",
        "wine grape variet",
        "grape variet",
    ),
    "link_to_terroir": (
        "description of the link",
        "link with the geographical area",
        "link to the geographical area",
        "causal link",
    ),
    "additional_conditions": (
        "essential further conditions",
        "further conditions",
        "other conditions",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`.
_GEO_AREA_TITLE_BLOCKLIST = (
    "geographical indication type",
    "categories of grapevine products",
)


# The Maltese single documents list section-7 varieties as a flat block
# (one variety per line, no principal/accessory split). Stage 02 defaults
# every match to "principal". The role-header machinery is retained for
# parity with the other parsers but rarely fires on EN documents.
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(main|principal|recommended|authorised|authorized|accessory|"
    r"secondary|complementary)\s*"
    r"(?:wine\s+grape\s+variet(?:y|ies)|variet(?:y|ies)|grapes?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "main": "principal",
    "princip": "principal",
    "recommend": "principal",
    "authoris": "principal",
    "authoriz": "principal",
    "accessor": "accessory",
    "secondar": "accessory",
    "complement": "accessory",
}


# English colour vocabulary for style detection.
COLOUR_BY_KEYWORD = {
    "red wine": "red",
    "red wines": "red",
    "white wine": "white",
    "white wines": "white",
    "rosé wine": "rose",
    "rose wine": "rose",
    "rosé wines": "rose",
    "rosé": "rose",
}


# Style markers in English (+ Maltese traditional terms), mapped to the
# shared style-taxonomy slugs. Maltese practice names: Passito / Imqadded
# are dried-grape (appassimento) wines; Ġellewża and Girgentina are the
# two native varieties (handled by the grape lexicon, not here).
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bsparkling\s+wine", re.I), "sparkling"),
    (re.compile(r"\bquality\s+sparkling\s+wine", re.I), "sparkling-quality"),
    (re.compile(r"\bsemi[\s-]?sparkling|\bpearl\s+wine", re.I), "semi-sparkling"),
    (re.compile(r"\bliqueur\s+wine", re.I), "vin-de-liqueur"),
    (re.compile(r"\blate\s+harvest", re.I), "late-harvest"),
    (re.compile(r"\bpassito\b|\bimqadded\b|\bdried\s+grapes?\b|\braisin\s+wine", re.I),
     "raisin-wine"),
    (re.compile(r"\bnoble\s+rot|\bbotrytis", re.I), "grains-nobles"),
)


# Lines inside the grape section that are headers / boilerplate, not
# variety names. Kept short so genuine names are never dropped.
_GRAPE_LINE_DROP = (
    "main wine grapes",
    "grape variety",
    "grape varieties",
)
