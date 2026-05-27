"""Slovak-keyword tables for parsing the EUR-Lex "JEDNOTNÝ DOKUMENT".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/sk/02_extract_pliegos.py` and reuses the SI / HR idiom directly;
this module contributes only the **Slovak-language tables** that map
section titles → semantic roles.

Slovak EU-OJ single-document template (as seen in the Stredoslovenská
JEDNOTNÝ DOKUMENT):

  1.  Názov                                       — name(s)
  2.  Druh zemepisného označenia                  — PDO / PGI
  3.  Kategórie vinohradníckych a vinárskych
      výrobkov                                    — categories
  4.  Opis vín                                    — description
  5.  Vinárske výrobné postupy                    — practices + max yields
  6.  Vymedzená zemepisná oblasť                  — area
  7.  Hlavné muštové odrody                       — grape varieties
  8.  Opis súvislostí                             — link to terroir
  9.  Iné základné podmienky                      — labelling, packaging

The older template numbers a little differently; route_sections in stage
02 uses title-keyword matching to stay template-agnostic.
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
# most-specific-first, then sections in document order. Slovak is
# heavily inflected, so keywords keep the genitive/locative forms that
# actually appear in the template titles.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "názov",
        "názov produktu",
    ),
    "category": (
        "kategórie vinohradníckych",
        "kategórie vinárskych",
        "kategórie",
        "druh zemepisného označenia",
        "sektor",
    ),
    "description": (
        "opis vín",
        "opis vina",
        "opis výrobku",
        "opis produktu",
    ),
    "viticultural_practices": (
        "vinárske výrobné postupy",
        "vinárske postupy",
        "enologické postupy",
        "maximálne výnosy",
        "najvyššie výnosy",
    ),
    "geo_area": (
        "vymedzená zemepisná oblasť",
        "vymedzenie zemepisnej oblasti",
        "zemepisná oblasť",
        "stručný opis vymedzenej zemepisnej oblasti",
        "vymedzená oblasť",
        "vymedzenie oblasti",
    ),
    "grape_varieties": (
        "hlavné muštové odrody",
        "muštové odrody",
        "muštová odroda",
        "odrody viniča",
        "hlavné odrody viniča",
    ),
    "link_to_terroir": (
        "opis súvislostí",
        "opis súvislosti",
        "súvislosť so zemepisnou oblasťou",
        "súvislosť",
        "údaje potvrdzujúce spojitosť",
        "spojitosť",
    ),
    "additional_conditions": (
        "iné základné podmienky",
        "ďalšie podmienky",
        "iné podmienky",
        "ďalšie základné podmienky",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title contains a role keyword. Section 2 "Druh zemepisného
# označenia" carries "zemepisného" but its body is just "CHOP" / "CHZO".
_GEO_AREA_TITLE_BLOCKLIST = (
    "druh zemepisného označenia",
    "kategórie vinohradníckych",
)


# Grape role headers inside the grape-variety section. Slovak single
# documents rarely carry a principal/accessory split — the section is
# usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(hlavn[eéá]?|odporúčan[eéá]?|odporucan[eéá]?|povolen[eéá]?|"
    r"doplnkov[eéá]?)\s*"
    r"(?:odrody?|mušt[oové]+\s+odrody?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "hlavn": "principal",
    "odpor": "principal",
    "povolen": "accessory",
    "dopln": "accessory",
}


# Slovak colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "červené víno": "noir",
    "červené vína": "noir",
    "červených vín": "noir",
    "biele víno": "blanc",
    "biele vína": "blanc",
    "bielych vín": "blanc",
    "ružové víno": "rose",
    "ružové vína": "rose",
    "ružových vín": "rose",
    "rosé víno": "rose",
}


# Style markers in Slovak, mapped to the shared style-taxonomy slugs.
# The Tokaj predikat ladder (samorodné / výber / esencia) and the
# slamové / ľadové leaves are the obvious mappings.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(šumivé|šumivá|šumivý|šumivého)\s+vín[oa]?\b", re.I), "sparkling"),
    (re.compile(r"\bperlivé\b", re.I), "semi-sparkling"),
    (re.compile(r"\bslamové víno\b", re.I), "vin-de-paille"),
    (re.compile(r"\bľadové víno\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bľadový výber\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvýber z hrozna\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bneskorý zber\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bvýber z cibéb\b", re.I), "grains-nobles"),
    (re.compile(r"\bvýber z bobúľ\b", re.I), "grains-nobles"),
    (re.compile(r"\btokajská\s+esencia\b", re.I), "grains-nobles"),
    (re.compile(r"\btokajský\s+výber\b", re.I), "grains-nobles"),
    (re.compile(r"\bsamorodné\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bsuché víno\b", re.I), "dry"),
)
