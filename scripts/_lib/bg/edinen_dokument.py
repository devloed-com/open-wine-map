"""Bulgarian-keyword tables for parsing the EUR-Lex "ЕДИНЕН ДОКУМЕНТ".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/bg/02_extract_pliegos.py` and reuses the ES / IT / AT / SI / HR
/ HU / RO idiom directly; this module contributes only the **Bulgarian-
language tables** that map section titles → semantic roles.

Bulgarian EU-OJ single-document template (as seen in the small handful
of publishable BG records — Мелник, Нова Загора, Дунавска равнина — plus
the wider EU corpus in Bulgarian):

  1.  Наименование (наименования)                            — name
  2.  Тип на географското указание                           — PDO (ЗНП) / PGI (ЗГУ)
  3.  Категории лозаро-винарски продукти                     — categories
  4.  Описание на вината                                     — description
  5.  Винарски практики / Енологични практики                — practices + max yields
  6.  Очертан географски район / Демаркиран район            — area
  7.  Основни винени сортове грозде                          — grape varieties
  8.  Описание на връзката(ите)                              — link to terroir
  9.  Други съществени условия / Препратка към публикацията  — additional / reference

Bulgarian regulator-acronyms preserved in keyword-form: ЗНП (Защитено
наименование за произход / PDO) and ЗГУ (Защитено географско указание /
PGI).
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*ЕДИНЕН\s+ДОКУМЕНТ\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. Keywords stored in lowercase
# (casefold-friendly for Cyrillic). Variants harvested from the three
# Bulgarian publications fetched on the first stage-01 run (melnik,
# nova-zagora, dunavska-ravnina) plus general-template forms.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "наименование на продукта",
        "наименование/наименования",
        "наименование (наименования)",
        "наименованието",
        "наименование",
        "име",
    ),
    "category": (
        "вид на географското означение",
        "вид на географското указание",
        "вид географско означение",
        "вид географско указание",
        "категории лозаро-винарски продукти",
        "категории на лозаро-винарските продукти",
        "категория лозаро-винарски продукти",
        "категория на лозаро-винарския продукт",
        "тип на географското указание",
        "тип на географското означение",
        "тип географско указание",
        "тип на гу",
        "категории",
    ),
    "description": (
        "описание на виното или вината",
        "описание на виното(ата)",
        "описание на вината",
        "описание на виното",
        "описание на продукта",
        "описание",
    ),
    "viticultural_practices": (
        "винопроизводствени практики",
        "основни енологични практики",
        "специфични енологични практики",
        "енологични практики",
        "винарски практики",
        "лозарски практики",
        "максимални добиви",
        "максимален добив",
        "максимални рандемани",
    ),
    "geo_area": (
        "определен географски район",
        "определена географска зона",
        "очертан географски район",
        "очертана географска зона",
        "демаркиран район",
        "демаркирана зона",
        "географски район",
        "географска зона",
        "район на производство",
        "зона на производство",
    ),
    "grape_varieties": (
        "винен сорт грозде или винени сортове грозде",
        "винен(и) сорт(ове) грозде",
        "основни винени сортове грозде",
        "основни сортове грозде",
        "основни сортове",
        "винени сортове грозде",
        "винени сортове",
        "винен сорт грозде",
        "сорт или сортове грозде",
        "сорт грозде",
        "сортове грозде",
        "сортове",
    ),
    "link_to_terroir": (
        "описание на връзката или връзките",
        "описание на връзката(ите)",
        "описание на връзката (връзките)",
        "описание на връзката",
        "описание на връзките",
        "връзка с географския район",
        "връзка с географската зона",
        "причинно-следствена връзка",
        "връзката",
        "връзка",
    ),
    "additional_conditions": (
        "други специфични изисквания",
        "други съществени условия",
        "други условия",
        "съществени условия",
        "специфични изисквания",
        "препратка към публикацията на спецификацията",
        "препратка към публикацията",
        "препратка към спецификацията",
        "линк към спецификацията на продукта",
        "линк към спецификацията",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title carries a related keyword. Section 2 ("Вид на
# географското означение") carries "географско" inflected but its body
# is just "ЗНП" / "ЗГУ".
_GEO_AREA_TITLE_BLOCKLIST = (
    "вид на географското означение",
    "вид на географското указание",
    "вид географско означение",
    "вид географско указание",
    "тип на географското указание",
    "тип на географското означение",
    "тип географско указание",
    "тип на гу",
    "категории лозаро-винарски продукти",
    "категории на лозаро-винарските продукти",
    "категория лозаро-винарски продукти",
)


# Grape role headers inside the grape-variety section. Bulgarian DOCUMENT
# UNIC publications generally carry a flat variety list — section 7
# enumerates main varieties without a principal/accessory split; stage 02
# defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(основн(?:и|ите|ия|ият)|препоръчителн(?:и|ите)|допълнителн(?:и|ите)|"
    r"разрешен(?:и|ите)|допустим(?:и|ите)|вторичн(?:и|ите))\s*(?:сортове)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "основ": "principal",
    "препор": "principal",
    "разреш": "principal",
    "допуст": "principal",
    "допълн": "accessory",
    "вторич": "accessory",
}


# Bulgarian colour vocabulary for style detection.
COLOUR_BY_KEYWORD = {
    "бяло вино": "blanc",
    "бели вина": "blanc",
    "бялото вино": "blanc",
    "червено вино": "noir",
    "червени вина": "noir",
    "червеното вино": "noir",
    "розе": "rose",
    "розе вино": "rose",
    "розови вина": "rose",
    "розово вино": "rose",
}


# Style markers in Bulgarian, mapped to the shared style-taxonomy slugs.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bпенлив(?:о|и)\s+вин(?:о|а)\b", re.I), "sparkling"),
    (re.compile(r"\bискрящ(?:о|и)\s+вин(?:о|а)\b", re.I), "sparkling"),
    (re.compile(r"\bперлантно?\s+вин(?:о|а)\b", re.I), "semi-sparkling"),
    (re.compile(r"\bполупенлив(?:о|и)\s+вин(?:о|а)\b", re.I), "semi-sparkling"),
    (re.compile(r"\bкъсна?\s+реколта\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bледено\s+вино\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bдесертно?\s+вин(?:о|а)\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bподбран?\s+гроздобер\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bблагородна?\s+плесен\b", re.I), "grains-nobles"),
    (re.compile(r"\bботритиз(?:иран[ао]?|ис)\b", re.I), "grains-nobles"),
    (re.compile(r"\bликьорн(?:о|и)\s+вин(?:о|а)\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bсух(?:о|и)\s+вин(?:о|а)\b", re.I), "dry"),
    (re.compile(r"\bсладк(?:о|и)\s+вин(?:о|а)\b", re.I), "vendanges-tardives"),
)
