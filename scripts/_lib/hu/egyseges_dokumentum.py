"""Hungarian-keyword tables for parsing the EUR-Lex "EGYSÉGES DOKUMENTUM".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/hu/02_extract_pliegos.py` and reuses the ES / IT / AT / SI / HR
idiom directly; this module contributes only the **Hungarian-language
tables** that map section titles → semantic roles.

Hungarian EU-OJ single-document template (as seen across the 26 HU
EGYSÉGES DOKUMENTUM publications):

  1.  A termék elnevezése / Elnevezés(ek) / Bejegyzendő elnevezés  — name
  2.  A földrajzi árujelző típusa                                  — PDO / PGI (OEM / OFJ)
  3.  A szőlőből készült termékek kategóriái                       — categories
  4.  A bor(ok) leírása                                            — description
  5.  Borkészítési eljárások                                       — practices + max yields
  6.  Körülhatárolt földrajzi terület                              — area
  7.  Fontosabb borszőlőfajták / Borszőlőfajta(k)                  — grape varieties
  8.  A kapcsolat(ok) leírása                                      — link to terroir
  9.  További alapvető feltételek / Közzétételre utalás            — additional / reference
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*EGYSÉGES\s+DOKUMENTUM\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. route_sections iterates keywords
# most-specific-first, then sections in document order. Hungarian is
# agglutinative, so keywords use the inflected forms (mostly -áé / -ai
# suffixes) that actually appear in the template titles.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "a termék elnevezése",
        "bejegyzendő elnevezés",
        "bejegyzendo elnevezes",
        "elnevezés",
        "elnevezes",
    ),
    "category": (
        "szőlőből készült termékek kategóriái",
        "szolobol keszult termekek kategoriai",
        "szőlőből készült termékek",
        "termékek kategóriái",
        "földrajzi árujelző típusa",
        "foldrajzi arujelzo tipusa",
        "kategóriái",
        "kategoriai",
    ),
    "description": (
        "a bor(ok) leírása",
        "a bor leírása",
        "a borok leírása",
        "a bor leirasa",
        "borleírás",
        "borleiras",
    ),
    "viticultural_practices": (
        "borkészítési eljárások",
        "borkeszitesi eljarasok",
        "borászati eljárások",
        "boraszati eljarasok",
        "maximális hozamok",
        "maximalis hozamok",
    ),
    "geo_area": (
        "körülhatárolt földrajzi terület",
        "korulhatarolt foldrajzi terulet",
        "földrajzi terület",
        "foldrajzi terulet",
        "termőterület",
        "termoterulet",
    ),
    "grape_varieties": (
        "fontosabb borszőlőfajták",
        "fontosabb borszolofajtak",
        "borszőlőfajta",
        "borszolofajta",
        "szőlőfajták",
        "szolofajtak",
    ),
    "link_to_terroir": (
        "a kapcsolat(ok) leírása",
        "kapcsolat(ok) leírása",
        "kapcsolatok leírása",
        "kapcsolat leírása",
        "kapcsolat leirasa",
        "okozati kapcsolat",
        # Older single-document template variant (e.g. Soltvadkerti):
        # section 8 titled "Kapcsolat a földrajzi területtel". The
        # "földrajzi terület" substring also matches geo_area, so this
        # title is blocklisted from geo_area below to force the link route.
        "kapcsolat a földrajzi területtel",
        "kapcsolat a foldrajzi terulettel",
        "kapcsolat a földrajzi",
        "kapcsolat a foldrajzi",
    ),
    "additional_conditions": (
        "további alapvető feltételek",
        "tovabbi alapveto feltetelek",
        "további feltételek",
        "tovabbi feltetelek",
        "egyéb követelmények",
        "egyeb kovetelmenyek",
        "közzétételre utalás",
        "kozzetetelre utalas",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title carries a related keyword.
_GEO_AREA_TITLE_BLOCKLIST = (
    "földrajzi árujelző típusa",
    "foldrajzi arujelzo tipusa",
    "szőlőből készült termékek kategóriái",
    "szolobol keszult termekek kategoriai",
    # The terroir section "Kapcsolat a földrajzi területtel" contains
    # "földrajzi terület" — keep it out of geo_area so it routes to
    # link_to_terroir instead.
    "kapcsolat a földrajzi",
    "kapcsolat a foldrajzi",
)


# Grape role headers inside the grape-variety section. Hungarian single
# documents rarely carry a principal/accessory split — the section is
# usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(fontosabb|fő|f[oő]bb|engedélyezett|engedelyezett|ajánlott|ajanlott|"
    r"kiegészítő|kiegeszito)\s*(?:fajt[áa]k?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "fontos": "principal",
    "fo": "principal",
    "fő": "principal",
    "engedel": "principal",
    "ajanl": "principal",
    "aján": "principal",
    "kiegesz": "accessory",
    "kieg": "accessory",
}


# Hungarian colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "fehérbor": "blanc",
    "feherbor": "blanc",
    "fehér bor": "blanc",
    "feher bor": "blanc",
    "vörösbor": "noir",
    "vorosbor": "noir",
    "vörös bor": "noir",
    "voros bor": "noir",
    "rozébor": "rose",
    "rozebor": "rose",
    "rozé bor": "rose",
    "roze bor": "rose",
    "rozé": "rose",
    "roze": "rose",
}


# Style markers in Hungarian, mapped to the shared style-taxonomy slugs.
# The Hungarian Tokaji ladder (aszú / szamorodni / fordítás / máslás /
# eszencia / késői szüret / jégbor) maps onto the noble-rot /
# late-harvest / sweet leaves; Bikavér / Csillag / Siller are dry-style
# blends that fold to the colour taxonomy.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bpezsg[őo]\b", re.I), "sparkling"),
    (re.compile(r"\bgy[öo]ngy[öo]z[őo]\s*bor\b", re.I), "semi-sparkling"),
    (re.compile(r"\baszú\b|\baszu\b", re.I), "grains-nobles"),
    (re.compile(r"\beszencia\b", re.I), "grains-nobles"),
    (re.compile(r"\bszamorodni\b", re.I), "grains-nobles"),
    (re.compile(r"\bfordítás\b|\bforditas\b", re.I), "grains-nobles"),
    (re.compile(r"\bmáslás\b|\bmaslas\b", re.I), "grains-nobles"),
    (re.compile(r"\btöppedt\b|\btoppedt\b", re.I), "grains-nobles"),
    (re.compile(r"\bjégbor\b|\bjegbor\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bkésői\s+szüretelésű\b|\bkesoi\s+szuretelesu\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bkésői\s+szüret\b|\bkesoi\s+szuret\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bcsemegebor\b", re.I), "vendanges-tardives"),
    (re.compile(r"\blik[őo]rbor\b|\blikorbor\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bszáraz\b|\bszaraz\b", re.I), "dry"),
)
