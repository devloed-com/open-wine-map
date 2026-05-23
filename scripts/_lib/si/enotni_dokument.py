"""Slovenian-keyword tables for parsing the EUR-Lex "ENOTNI DOKUMENT".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/si/02_extract_pliegos.py` and reuses the ES / IT / AT idiom
directly; this module contributes only the **Slovenian-language tables**
that map section titles → semantic roles.

Slovenian EU-OJ single-document template (post-2024 — Reg. (EU) 2024/1143,
as seen in the Cviček ENOTNI DOKUMENT):

  1.  Ime ali imena                              — name(s)
  2.  Vrsta geografske označbe                   — PDO / PGI
  3.  Država, ki ji pripada … geografsko območje — country
  4.  Razvrstitev … po tarifni številki …        — CN classification
  5.  Kategorije proizvodov vinske trte           — categories
  6.  Opis vina ali vin                          — description
  7.  Vinarske prakse                            — practices + max yields
  8.  Sorta ali sorte vinske trte …              — grape varieties
  9.  Jedrnat opis razmejenega geografskega
      območja                                    — area
  10. Povezava z geografskim območjem            — link to terroir
  11. Dodatne veljavne zahteve                   — labelling, packaging

The older template numbers a little differently; route_sections in stage
02 uses title-keyword matching to stay template-agnostic.
"""

from __future__ import annotations

import re

DOC_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*ENOTNI\s+DOKUMENT\s*</p>',
    re.I | re.S,
)

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


# Section title keyword → semantic role. route_sections iterates keywords
# most-specific-first, then sections in document order. Slovenian is
# heavily inflected, so keywords keep the genitive/locative forms that
# actually appear in the template titles.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "ime ali imena",
        "ime proizvoda",
        "ime",
    ),
    "category": (
        "kategorije proizvodov vinske trte",
        "vrsta geografske označbe",
        "sektor",
    ),
    "description": (
        "opis vina ali vin",
        "opis vina",
        "opis vin",
        "opis proizvoda",
    ),
    "viticultural_practices": (
        "vinarske prakse",
        "enološki postopki",
        "enoloski postopki",
        "največji donosi",
        "najvecji donosi",
    ),
    "geo_area": (
        "jedrnat opis razmejenega geografskega območja",
        "razmejenega geografskega območja",
        "razmejeno geografsko območje",
        "geografskega območja",
        "geografsko območje",
    ),
    "grape_varieties": (
        "sorta ali sorte vinske trte",
        "sorte vinske trte",
        "sorta vinske trte",
        "sorte vinske trte za pridelavo vina",
    ),
    "link_to_terroir": (
        "povezava z geografskim območjem",
        "povezava z območjem",
        "povezava",
    ),
    "additional_conditions": (
        "dodatne veljavne zahteve",
        "dodatne zahteve",
        "druge bistvene zahteve",
        "zahteve",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title contains a role keyword. Section 2 "Vrsta geografske
# označbe" carries "geografske" but its body is just "ZOP" / "ZGP".
_GEO_AREA_TITLE_BLOCKLIST = (
    "vrsta geografske označbe",
    "kategorije proizvodov vinske trte",
)


# Grape role headers inside the grape-variety section. Slovenian single
# documents rarely carry a principal/accessory split — the section is
# usually a flat list. Stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(glavne?|priporočene?|priporocene?|dovoljene?|dopolnilne?)\s*"
    r"(?:sorte?)?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "glavn": "principal",
    "priporo": "principal",
    "dovoljen": "accessory",
    "dopoln": "accessory",
}


# Slovenian colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "rdeče vino": "noir",
    "rdeča vina": "noir",
    "rdečih vin": "noir",
    "belo vino": "blanc",
    "bela vina": "blanc",
    "belih vin": "blanc",
    "rosé vino": "rose",
    "rozé vino": "rose",
    "rožnato vino": "rose",
    "rožnata vina": "rose",
}


# Style markers in Slovenian, mapped to the shared style-taxonomy slugs.
# The Slovenian Predikat ladder (pozna trgatev / izbor / jagodni izbor /
# suhi jagodni izbor / ledeno vino / slamno vino) maps onto the late-
# harvest / noble-rot / straw-wine leaves.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(peneče|peneča|penina|peneče vino)\b", re.I), "sparkling"),
    (re.compile(r"\bbiser\b", re.I), "semi-sparkling"),
    (re.compile(r"\bslamno vino\b", re.I), "vin-de-paille"),
    (re.compile(r"\bsuhi jagodni izbor\b", re.I), "grains-nobles"),
    (re.compile(r"\bjagodni izbor\b", re.I), "grains-nobles"),
    (re.compile(r"\bledeno vino\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bpozna trgatev\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bizbor\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bsuho vino\b", re.I), "dry"),
)
