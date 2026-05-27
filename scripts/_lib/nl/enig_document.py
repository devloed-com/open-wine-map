"""Dutch-keyword tables for parsing the EUR-Lex "ENIG DOCUMENT" used
by Dutch wine GIs.

The Dutch single-document template is identical to the Flemish-side
Belgian one. We keep an NL-specific module here (rather than re-using
`_lib.be.document`) so that NL-only parser quirks can land in the right
country namespace without churning BE code. For v1 the keyword tables
are a near-verbatim subset of the BE NL tables.

Standard EU single-document template:
  1.  Naam                                  — name(s)
  2.  Type geografische aanduiding          — PDO / PGI
  3.  Categorieën van wijnbouwproducten     — categories
  4.  Beschrijving van de wijn(en)          — description
  5.  Wijnbereidingsprocedés                — practices + max yields
  6.  Afgebakend geografisch gebied         — area
  7.  Wijndruivenras(sen)                   — grape varieties
  8.  Beschrijving van het (de) verband(en) — link to terroir
  9.  Andere essentiële voorwaarden         — labelling, packaging
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    # Older OJ publications wrap the anchor text in <span class="bold">,
    # newer ones put it bare. Tolerate both: any chain of inline tags
    # between p-open and the literal text, and same on the close side.
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>'
    r'(?:\s*<[^>]+>)*\s*ENIG\s+DOCUMENT\s*(?:</[^>]+>\s*)*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
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
}


_GEO_AREA_TITLE_BLOCKLIST = (
    "type geografische aanduiding",
    "categorieën van wijnbouwproducten",
    "categorieen van wijnbouwproducten",
)


_GRAPE_ROLE_HEADER_SRC = (
    r"\b(voornaamste|hoofd|principale|geautoriseerde|toegestane|"
    r"bijkomende|aanvullende)\s*"
    r"(?:druivenras(?:sen)?|wijndruiven(?:ras(?:sen)?)?|rassen)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(_GRAPE_ROLE_HEADER_SRC, re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "voornaamste": "principal",
    "hoofd": "principal",
    "principale": "principal",
    "geautoriseerde": "principal",
    "toegestane": "principal",
    "bijkomende": "accessory",
    "aanvullende": "accessory",
}

_GRAPE_LINE_DROP = (
    "wijndruivenras", "wijndruivenrassen", "druivenrassen",
    "voornaamste", "hoofd", "geautoriseerde", "toegestane",
    "bijkomende", "aanvullende",
)


COLOUR_BY_KEYWORD = {
    "rode wijn": "noir",
    "rode wijnen": "noir",
    "witte wijn": "blanc",
    "witte wijnen": "blanc",
    "rosé wijn": "rose",
    "rosé wijnen": "rose",
    "rose wijn": "rose",
}


STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    # Match the more specific "quality sparkling" pattern before the
    # generic "sparkling" to avoid duplicate hits.
    (re.compile(r"\bmousserend(e)?\s+kwaliteitswijn(en)?\b", re.I), "sparkling-quality"),
    (re.compile(r"\bmousserend(e)?\s+wijn(en)?\b", re.I), "sparkling"),
    (re.compile(r"\bparelwijn\b", re.I), "semi-sparkling"),
    (re.compile(r"\bcrémant\b|\bcremant\b", re.I), "cremant"),
    # Section-3 categories from the EU OJ template:
    # 3 = Likeurwijn (vin de liqueur / fortified);
    # 16 = Wijn uit overrijpe druiven (vendanges tardives — overripe);
    # 15 = Wijn uit gerimpelde druiven (vin de paille — raisined).
    (re.compile(r"\blikeurwijn(en)?\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bwijn uit overrijpe druiven\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bwijn uit gerimpelde druiven\b", re.I), "vin-de-paille"),
    (re.compile(r"\blate\s+oogst\b|\blaat\s+geoogst\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bijswijn\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bdroge wijn(en)?\b", re.I), "dry"),
)
