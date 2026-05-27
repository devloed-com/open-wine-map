"""Switzerland — 26 cantons table.

Switzerland is the first non-EU country in the corpus, and the first
whose AOC system is split across 26 cantonal jurisdictions rather than
a single national regulator. Each canton has its own AOC règlement /
Reglement / regolamento; the federal OFAG publishes only a thin
"Répertoire suisse des AOC" enumerating the names.

The 26 cantons are listed below in OFAG-PDF order with:
  - 2-letter ISO 3166-2:CH code (lowercase here, uppercase in the PDF)
  - canonical name in the canton's primary language(s)
  - BFS canton id (1-26, matches swissBOUNDARIES3D `KANTONSNUMMER`)
  - official language(s) — used to pick `source_lang` per record
  - has_wine_aoc — bool: every canton appears in the OFAG 2026 register
    so this is True for all 26 (kept as a field for future-proofing)

The bilingual / trilingual cantons (BE FR-DE, FR FR-DE, VS FR-DE, GR
DE-IT-RM) use the *first* listed language as the default source_lang
for their AOC règlements. Empirically: BE/FR/VS règlements are
published in French (the wine-producing parts of those cantons are
French-speaking); GR's règlement is published in German.
"""

from __future__ import annotations

# (code, canonical name, BFS canton id, default source_lang, alt source_langs)
CANTONS: tuple[tuple[str, str, int, str, tuple[str, ...]], ...] = (
    ("ag", "Aargau",                     19, "de", ()),
    ("ai", "Appenzell Innerrhoden",      16, "de", ()),
    ("ar", "Appenzell Ausserrhoden",     15, "de", ()),
    ("be", "Bern / Berne",                2, "fr", ("de",)),   # wine = Lac de Bienne (FR)
    ("bl", "Basel-Landschaft",           13, "de", ()),
    ("bs", "Basel-Stadt",                12, "de", ()),
    ("fr", "Fribourg / Freiburg",        10, "fr", ("de",)),
    ("ge", "Genève",                     25, "fr", ()),
    ("gl", "Glarus",                      8, "de", ()),
    ("gr", "Graubünden / Grigioni",      18, "de", ("it", "rm")),
    ("ju", "Jura",                       26, "fr", ()),
    ("lu", "Luzern",                      3, "de", ()),
    ("ne", "Neuchâtel",                  24, "fr", ()),
    ("nw", "Nidwalden",                   7, "de", ()),
    ("ow", "Obwalden",                    6, "de", ()),
    ("sg", "St. Gallen",                 17, "de", ()),
    ("sh", "Schaffhausen",               14, "de", ()),
    ("so", "Solothurn",                  11, "de", ()),
    ("sz", "Schwyz",                      5, "de", ()),
    ("tg", "Thurgau",                    20, "de", ()),
    ("ti", "Ticino",                     21, "it", ()),
    ("ur", "Uri",                         4, "de", ()),
    ("vd", "Vaud",                       22, "fr", ()),
    ("vs", "Valais / Wallis",            23, "fr", ("de",)),   # wine ~80 % FR-side
    ("zg", "Zug",                         9, "de", ()),
    ("zh", "Zürich",                      1, "de", ()),
)

CANTON_CODES: tuple[str, ...] = tuple(c[0] for c in CANTONS)

CANTON_NAME: dict[str, str] = {c[0]: c[1] for c in CANTONS}
CANTON_BFS_ID: dict[str, int] = {c[0]: c[2] for c in CANTONS}
CANTON_SOURCE_LANG: dict[str, str] = {c[0]: c[3] for c in CANTONS}
CANTON_ALT_LANGS: dict[str, tuple[str, ...]] = {c[0]: c[4] for c in CANTONS}

# Reverse: BFS id → canton code (for joining swissBOUNDARIES3D `KANTONSNUMMER`).
CANTON_CODE_BY_BFS: dict[int, str] = {c[2]: c[0] for c in CANTONS}

# Reverse: upper-case 2-letter abbreviation → code (for parsing the OFAG PDF
# which writes "AG", "AI", "AR", … in column 1).
CANTON_CODE_BY_ABBREV: dict[str, str] = {c[0].upper(): c[0] for c in CANTONS}


def source_lang_for_canton(canton: str) -> str:
    """Default source-language for an AOC règlement of the given canton."""
    return CANTON_SOURCE_LANG.get(canton, "de")


def canton_name(code: str) -> str:
    """Native canton name (the form shown in panel headers + frontmatter)."""
    return CANTON_NAME.get(code, code.upper())
