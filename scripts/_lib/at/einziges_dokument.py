"""German-keyword tables for parsing the EUR-Lex "Einziges Dokument".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections
(1..9 or 1..10 depending on template vintage), same EINZIGES DOKUMENT
anchor at the start of the per-language slab. So the HTML-extraction
machinery (regex for headers, slice-from-anchor) lives in
`scripts/at/02_extract_pliegos.py` and reuses the ES / IT idiom directly;
this module contributes only the **German-language tables** that map
section titles → semantic roles and grape-role keywords → principal /
accessory.

German EU-OJ single-document template (post-2014):

  1. Name(n)
  2. Art der geografischen Angabe              — PDO / PGI
  3. Kategorien von Weinbauerzeugnissen
  4. Beschreibung des Weins/der Weine
  5. Weinbereitungsverfahren                   — practices + max yields
  6. Abgegrenztes geografisches Gebiet         — area
  7. Wichtigste Keltertraubensorte(n)          — grape varieties
  8. Beschreibung des Zusammenhangs/der        — link to terroir
     Zusammenhänge
  9. Weitere wesentliche Bedingungen           — labelling, packaging

The newer `oj-ti-grseq-1` template reorders a little; route_sections in
stage 02 uses title-keyword matching to stay template-agnostic.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*EINZIGES\s+DOKUMENT\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. First matching role per section
# wins; route_sections iterates section titles in document order.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "name(n)",
        "name des produkts",
        "name",
    ),
    "category": (
        "kategorien von weinbauerzeugnissen",
        "kategorie des erzeugnisses",
        "art der geografischen angabe",
    ),
    "description": (
        "beschreibung des weins/der weine",
        "beschreibung des weins",
        "beschreibung der weine",
        "beschreibung des erzeugnisses",
    ),
    "viticultural_practices": (
        "weinbereitungsverfahren",
        "önologische verfahren",
        "oenologische verfahren",
        "höchsterträge",
    ),
    "geo_area": (
        "knappe beschreibung der abgegrenzten",
        "abgegrenztes geografisches gebiet",
        "abgegrenztes gebiet",
        "geografisches gebiet",
    ),
    "grape_varieties": (
        "wichtigste keltertraubensorte",
        "keltertraubensorte",
        "keltertraubensorten",
        "rebsorte",
        "rebsorten",
        "traubensorte",
    ),
    "link_to_terroir": (
        "beschreibung des zusammenhangs",
        "beschreibung der zusammenhänge",
        "zusammenhang mit dem geografischen gebiet",
        "zusammenhang",
    ),
    "additional_conditions": (
        "weitere wesentliche bedingungen",
        "weitere bedingungen",
        "verpackung",
        "etikettierung",
        "kennzeichnung",
    ),
}


# EUR-Lex publishes the single document as the member state typed it, so a
# section title occasionally carries a typo: Kremstal's section 7 reads
# "Wichtigste Keltertrauensorte(n)" (a dropped "b") and its section 2
# "Art der geobrafischen Angabe". An exact substring test then never sees
# the keyword and the section is silently unrouted — Kremstal shipped with
# no grape list. `title_has_keyword` therefore falls back to a fuzzy
# partial match, but only for keywords long enough that a near-miss is
# still unambiguous: a short keyword such as "name" or "rebsorte" at 90 %
# would match too much of a wrong title.
_FUZZY_TITLE_MIN_KEYWORD_LEN = 10
_FUZZY_TITLE_THRESHOLD = 90


def title_has_keyword(title_low: str, keyword: str, *, fuzzy: bool = False) -> bool:
    """True when `keyword` occurs in the lower-cased section title. With
    `fuzzy`, a keyword of at least `_FUZZY_TITLE_MIN_KEYWORD_LEN` chars
    also matches a typo'd title at partial ratio ≥ 90."""
    if keyword in title_low:
        return True
    if not fuzzy or len(keyword) < _FUZZY_TITLE_MIN_KEYWORD_LEN:
        return False
    return fuzz.partial_ratio(keyword, title_low) >= _FUZZY_TITLE_THRESHOLD


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title contains the role keyword. The German single
# document names section 2 "Art der geografischen Angabe" — that title
# contains "geografische" but the body is just "g.U." / "g.g.A.".
_GEO_AREA_TITLE_BLOCKLIST = (
    "art der geografischen angabe",
    "kategorien von weinbauerzeugnissen",
)


# Grape role headers inside section 7 (Keltertraubensorten). German
# single documents rarely carry a principal/accessory split — section 7
# is usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(haupt(?:rebsorten?|sorten?)?|wichtigste|"
    r"empfohlene?|zugelassene?|ergänzende?|weitere?)\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "haupt": "principal",
    "wichtigst": "principal",
    "empfohlen": "principal",
    "zugelassen": "accessory",
    "erganzend": "accessory",
    "ergänzend": "accessory",
    "weiter": "accessory",
}


# German colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "rotwein": "noir",
    "rotweine": "noir",
    "weißwein": "blanc",
    "weißweine": "blanc",
    "weisswein": "blanc",
    "weissweine": "blanc",
    "roséwein": "rose",
    "roséweine": "rose",
    "rosewein": "rose",
    "roseweine": "rose",
}


# Style markers in German, mapped to the shared style-taxonomy slugs.
# Austrian wine carries a rich Prädikat ladder; the botrytis / straw-wine
# Prädikate (Beerenauslese, Trockenbeerenauslese, Ausbruch, Strohwein)
# map onto the noble-rot / raisin-wine leaves.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(sekt|schaumwein)\b", re.I), "sparkling"),
    (re.compile(r"\bperlwein\b", re.I), "semi-sparkling"),
    (re.compile(r"\bstrohwein\b", re.I), "vin-de-paille"),
    (re.compile(r"\btrockenbeerenauslese\b", re.I), "grains-nobles"),
    (re.compile(r"\bbeerenauslese\b", re.I), "grains-nobles"),
    (re.compile(r"\bausbruch\b", re.I), "grains-nobles"),
    (re.compile(r"\beiswein\b", re.I), "vendanges-tardives"),
    (re.compile(r"\b(spätlese|spaetlese|auslese)\b", re.I), "vendanges-tardives"),
    (re.compile(r"\blikörwein\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\b(süßwein|suesswein|lieblich)\b", re.I), "sweet"),
    (re.compile(r"\btrocken\b", re.I), "dry"),
)
