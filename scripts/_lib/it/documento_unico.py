"""Italian-keyword tables for parsing the EUR-Lex documento unico.

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections
(1..9 or 1..10 depending on template vintage), same DOCUMENTO UNICO
anchor at the start of the per-language slab. So the HTML-extraction
machinery (regex for headers, slice-from-anchor) lives in
`scripts/it/02_extract_pliegos.py` and reuses the ES idiom directly;
this module contributes only the **Italian-language tables** that map
section titles → semantic roles and grape-role keywords → principal /
accessory.

Section numbering across templates (varies by EUR-Lex template
vintage; route_sections in stage 02 uses title-keyword matching to be
template-agnostic):

  Older ti-grseq-1:                   Newer oj-ti-grseq-1:
  1. Denominazione                    1. Denominazione
  2. Tipo di indicazione geografica   2. Tipo di indicazione geografica
  3. Categorie di prodotti            3. Categorie di prodotti
  4. Descrizione dei vini             4. (sometimes empty header)
  5. Pratiche di vinificazione        5. Pratiche di vinificazione
  6. Zona geografica delimitata       6. Descrizione del vino o dei vini
  7. Varietà di uve da vino           7. Pratiche enologiche specifiche
  8. Descrizione del legame           8. Varietà di uve da vino
  9. Ulteriori condizioni             9. Zona geografica delimitata
                                      10. Descrizione del legame
"""

from __future__ import annotations

import re

DOC_UNICO_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*DOCUMENTO\s+UNICO\s*</p>',
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
        "denominazione/denominazioni",
        "denominazione del prodotto",
        "denominazione",
    ),
    "category": (
        "categorie di prodotti vitivinicoli",
        "categoria del prodotto",
        "tipo di indicazione",
    ),
    "description": (
        "descrizione dei vini",
        "descrizione del vino",
        "descrizione organolettica",
    ),
    "viticultural_practices": (
        "pratiche di vinificazione",
        "pratiche enologiche",
        "rese massime",
    ),
    "geo_area": (
        "definizione concisa della zona",
        "definizione breve della zona",
        "zona geografica delimitata",
        "zona di produzione",
        "area geografica",
        "zona geografica",
    ),
    "grape_varieties": (
        "varietà di uve da vino",
        "varietà principale",
        "varietà delle uve",
        "varietà di uve",
        "indicazione della o delle varietà",
        "indicazione delle varietà",
        "varieta di uve da vino",
        "varieta principale",
        "varieta di uve",
        "vitigni",
        "uve da vino",
    ),
    "link_to_terroir": (
        "descrizione del legame",
        "legame con la zona",
        "legame con il territorio",
        "legame",
    ),
    "additional_conditions": (
        "ulteriori condizioni",
        "condizioni supplementari",
        "norme supplementari",
        "confezionamento",
        "etichettatura",
    ),
}


# Grape role headers inside section 7 (varietà di uve). Italian
# disciplinari use a different vocabulary from ES:
#  - principali / raccomandate / idonee   → principal
#  - complementari / accessorie / autorizzate (context-dependent)
# Stage 02 falls back to "principal" when no role marker is found,
# which is the common case for the EUR-Lex documento unico (section 7
# typically just lists varieties without a role split — the full
# split lives in the national disciplinare allegato).
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(principali?|raccomandate?|idonee?|complementari?|"
    r"accessori[ae]?|autorizzate?|consentite?)\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "principal": "principal",
    "principali": "principal",
    "raccomandat": "principal",
    "idone": "principal",
    "complementar": "accessory",
    "accessori": "accessory",
    "autorizzat": "accessory",
    "consentit": "accessory",
}


# Italian colour vocabulary for style detection. Used by parse_styles.
COLOUR_BY_KEYWORD = {
    "rosso": "noir",
    "rossi": "noir",
    "nero": "noir",
    "neri": "noir",
    "bianco": "blanc",
    "bianchi": "blanc",
    "rosato": "rose",
    "rosati": "rose",
    "rose": "rose",
}


# Style markers in Italian. Mapped to the shared style taxonomy slugs.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(spumant[ei])\b", re.I), "sparkling"),
    (re.compile(r"\b(frizzant[ei])\b", re.I), "semi-sparkling"),
    (re.compile(r"\b(passit[oi])\b", re.I), "raisin-wine"),
    (re.compile(r"\bvendemmia\s+tardiva\b", re.I), "vendanges-tardives"),
    (re.compile(r"\b(liquoros[oi])\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\b(vin\s+santo|vinsanto)\b", re.I), "vin-santo"),
    (re.compile(r"\b(novell[oi])\b", re.I), "primeur"),
    (re.compile(r"\b(amabile)\b", re.I), "semi-sweet"),
    (re.compile(r"\b(dolce)\b", re.I), "sweet"),
    (re.compile(r"\b(secco|asciutto)\b", re.I), "dry"),
)
