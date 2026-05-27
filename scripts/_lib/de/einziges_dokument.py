"""German-keyword tables for parsing the EUR-Lex "Einziges Dokument" for
the German (DE) wine corpus.

The EU-OJ single-document template is identical to Austria's — both
countries publish their EINZIGES DOKUMENT under the same EUR-Lex template
(`<p class="ti-grseq-1">EINZIGES DOKUMENT</p>` anchor, numbered subsections
1..9 or 1..10). The parsing helpers live in `scripts/de/02_extract_pliegos.py`
and re-use the same HTML-slice machinery as ES/IT/AT/SI/HR/HU/RO/BG/GR; this
module contributes only the **German-language tables** that map section
titles → semantic roles and grape-role keywords → principal / accessory.

Most tables are byte-identical to the AT module on purpose — the template
is the same. The DE module exists as a sibling so future German-specific
quirks (e.g. Großlage/Einzellage parsing, regional Bundesland markers)
land in the right country namespace without churning AT code.
"""

from __future__ import annotations

import re

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


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title contains the role keyword. Section 2 "Art der
# geografischen Angabe" contains "geografische" but the body is "g.U." /
# "g.g.A." — same trap as the AT corpus.
_GEO_AREA_TITLE_BLOCKLIST = (
    "art der geografischen angabe",
    "kategorien von weinbauerzeugnissen",
)


# Grape role headers inside section 7 (Keltertraubensorten). German
# Einziges Dokumente rarely carry a principal/accessory split — section
# 7 is usually a flat list. Stage 02 defaults to "principal".
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


# German colour vocabulary for style detection. Same set as AT.
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
# German wine carries the Prädikatswein ladder (Kabinett / Spätlese /
# Auslese / Beerenauslese / Trockenbeerenauslese / Eiswein) — same
# botrytis / straw-wine alignment as AT.
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
