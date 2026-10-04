"""Parse a flat commune list from a Spanish pliego's brief geographical
area text.

For ES wines that don't have a Figshare polygon (most IGPs, the ~7
post-Nov-2021 PDOs) and don't have polygon-level inclusions (the SIGPAC
path), we fall back to commune-list-union via GISCO LAU.

Pliego patterns handled:

  - Comma + " y " separated names: `Bueu, Cangas, Marín, ..., Vilaboa.`
  - "Los términos municipales de A, B, C ... y D"
  - "constituida por los términos municipales de X, Y, Z..."
  - Newline-per-name with `\n` separator

Filters out:
  - Function-words ("y", "o", "las", "del", ...)
  - Phrases ("así como", "del término municipal de X")
  - Sub-municipal mentions ("parroquias de A, B, C") — we keep only
    the named municipios, not parroquias

Returns a list of commune-name strings; caller unions them via GISCO.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

# Markers that signal the *municipi list ends* (transition from list to
# explanatory prose). Used to truncate the captured commune list. Same
# idiom as scripts/_lib/es/subzona.py:_COMMUNE_LIST_END_MARKERS. Matched
# case-insensitively and across line breaks (`_LIST_END_RE`): the
# mid-sentence ", así\ncomo las parroquias de …" of Barbanza e Iria and
# Betanzos is the same transition as a sentence-initial "Así como". A
# mid-sentence "así como los términos municipales de …" is not: it adds
# whole municipios and is folded into the list first (`_WHOLE_MUNI_CONT_RE`).
_LIST_END_MARKERS = (
    "Así como", "Asi como", "Así mismo", "Asi mismo",
    "Todos los términos municipales mencionados",
    "Dichos polígonos", "Dichos poligonos",
    "según la cartografía", "segun la cartografia",
    "siempre y cuando",
    "comprende todos los términos", "comprende todos los terminos",
    "La mayor parte", "El área de producción se",
    "En los vinos producidos", "En los vinos con la mención",
    "Los polígonos números",
    "Incluye las siguientes parcelas", "incluye las siguientes parcelas",
    "Pol.",
    "polígono ",
    "polígonos ",
    # Spanish-national pliegos often follow the commune list with a
    # SIGPAC parcel table whose header is uppercase "MUNICIPIO\nPOLÍGONO"
    # — rio-negro / rosalejo. Cut at the column header.
    "MUNICIPIO\nPOLÍGONO", "MUNICIPIO POLÍGONO",
    "POLÍGONO\nPARCELA",
    # Footnote anchors (MAPA Spanish-national pliegos): "(*).—Municipio que",
    # "**(En Zaragoza Polígonos...)" — text after this is a footnote, not a
    # commune name.
    "(*).—", "(*) .—", "(*)—",
    "(**).—", "(**) .—", "(**)—",
    "**(En ", "*(En ",
)

_LIST_END_RE = re.compile(
    "|".join(re.sub(r"(?:\\\s|\\\n|\s)+", r"\\s+", re.escape(m)) for m in _LIST_END_MARKERS),
    re.IGNORECASE,
)

# "…, La Viñuela y Yunquera, pertenecientes a la provincia de Málaga, así
# como los términos municipales de Benamejí y Palenciana pertenecientes a la
# provincia de Córdoba." (Sierras de Málaga; Málaga says "los municipios
# de"): the clause continues the whole-municipio list up to the end of its
# sentence, which is then the end of the list.
_WHOLE_MUNI_CONT_RE = re.compile(
    r"\s*,?\s*as[ií]\s+como\s+"
    r"(?:los\s+t[eé]rminos\s+municipales|el\s+t[eé]rmino\s+municipal|los\s+municipios"
    r"|el\s+municipio)\s+de\s+",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"\.(?=\s|$)|\n[ \t]*\n")


def _fold_whole_muni_continuation(body: str) -> str:
    m = _WHOLE_MUNI_CONT_RE.search(body)
    if not m:
        return body
    end = _SENTENCE_END_RE.search(body, m.end())
    return body[: m.start()] + ", " + body[m.end() : end.start() if end else len(body)]


# A parish enumeration bracketed by its municipio: "las parroquias de
# Camboño, Fruíme y Tállara del término municipal de Lousame" (Barbanza e
# Iria), "… Viós en el término municipal de Abegondo" (Betanzos). The
# whole span goes, parishes and closing municipio alike — the module
# docstring's rule is that only *named* municipios are kept, and a
# municipio named only as the holder of a few parishes is not in the zone
# as a whole (Padrón's Iria Flavia and Padrón parishes, not Padrón).
# Bounded so a stray "parroquias de" without a closing clause cannot eat
# the rest of the list.
_PARROQUIA_ENUM_RE = re.compile(
    r"(?:de\s+)?(?:las?\s+)?parroquias?\s+de\b.{0,600}?"
    r"(?:en\s+el|del)\s+(?:t[eé]rmino\s+municipal|concello)\s+de\s+[^,;.\n]+",
    re.IGNORECASE | re.DOTALL,
)


# "- <municipio>: las parroquias de …" lines (Valle del Miño-Ourense): the
# municipio is named before the colon, the parishes after it. When a list
# is written this way the named municipios are the whole list; the
# parishes are dropped per the module docstring. Line-anchored, so the
# page-break footer sitting between two entries is simply skipped.
_MUNI_WITH_PARROQUIAS_RE = re.compile(
    r"^\s*[-•—]\s*(?P<muni>[^:\n]+?)\s*:\s*las?\s+parroquias?\s+de\b",
    re.IGNORECASE | re.MULTILINE,
)

# Phrases that introduce a flat commune enumeration. We capture
# everything between this phrase and the first end marker / period
# followed by capital-letter sentence start.
#
# Patterns tried in order of specificity — the parser uses `.search` so
# the FIRST match in the body wins. Keep the most specific phrasings
# first so a "Demarcación de la zona" intro doesn't steal a later
# "engloba los siguientes municipios:" lead-in.
_LIST_LEADIN_RE = re.compile(
    r"(?:"
    # New (MAPA Spanish-national-format additions): "engloba los
    # siguientes municipios [de la provincia de X]?:" — Bajo Aragón,
    # Valdejalón, Ribera del Gállego-Cinco Villas.
    r"engloba\s+los\s+(?:siguientes\s+)?(?:t[eé]rminos\s+municipales|municipios)"
    r"(?:\s+de\s+la\s+provincia\s+de\s+[A-Za-zÁÉÍÓÚÑÜàáéíóúñü]+)?"
    r"\s*:?"
    # "Comprende los siguientes términos municipales:" / "incluye los
    # siguientes términos municipales:" — Altiplano de Sierra Nevada,
    # Sierras de Las Estancias y Los Filabres.
    r"|(?:comprende|incluye|abarca)\s+los\s+siguientes\s+"
    r"(?:t[eé]rminos\s+municipales|municipios)\s*:?"
    # "está constituida por los siguientes términos municipales:" —
    # Cádiz, Valle del Cinca.
    r"|(?:est[áa]\s+)?constituida\s+por\s+los\s+siguientes\s+"
    r"(?:t[eé]rminos\s+municipales|municipios)\s*:?"
    # "comprende los siguientes 18 municipios de la isla de Mallorca,
    # situados en la zona norte de la isla:" — Serra de Tramuntana.
    r"|comprende\s+los\s+siguientes\s+\d+\s+municipios"
    r"[^:.\n]*:"
    # "Comprende los siguientes términos municipales:" as section opener
    # (no verb prefix in section 9 body). Covered by the (?:comprende|…)
    # branch above, but include the bare "los siguientes términos
    # municipales:" form too — Costa de Cantabria continuations, generic.
    r"|los\s+siguientes\s+(?:t[eé]rminos\s+municipales|municipios)\s*:?"
    # Original patterns (kept verbatim — handle Bailén, Liébana, Ribeiras
    # do Morrazo's section 9 "constituida por los terrenos aptos para la
    # producción de uva de los términos municipales de Bueu, …", etc.):
    r"|los\s+t[eé]rminos\s+municipales\s+(?:(?:y\s+parroquias\s+)?siguientes\s*:|de(?:\s*:)?)?\s*"
    r"|t[eé]rminos\s+municipales\s+de\s+"
    # Defer to the "los términos municipales de" lead-in when a more
    # specific list intro follows the "terrenos aptos … de" preamble
    # (Ribeiras do Morrazo's section 9 is shaped that way).
    r"|terrenos\s+(?:aptos\s+para\s+la\s+producción\s+de\s+uva\s+)?de\s+"
    r"(?!los\s+t[eé]rminos\s+municipales\b)"
    r"|comprende\s+los\s+(?:términos\s+municipales\s+de|municipios\s+de)\s+"
    r"|los\s+municipios\s+(?:de\s+)?"
    r")",
    re.IGNORECASE,
)


# "Provincia de X:" sub-header inside a commune list. MAPA pliegos group
# the commune list per province with these headers (Bajo Aragón, Ribera
# del Gállego-Cinco Villas). Stripped at body-cleanup time so per-province
# sub-lists merge into one flat list.
_PROVINCE_HEADER_RE = re.compile(
    r"\s*Provincia\s+de\s+[A-ZÁÉÍÓÚÑÜ][\w\-]+(?:\s+[A-ZÁÉÍÓÚÑÜ][\w\-]+){0,2}\s*[:.]\s*",
    re.IGNORECASE,
)


# Parenthetical asides inside commune lists ("Zaragoza (en Zaragoza,
# polígonos catastrales 152, 153, …)") — we keep the commune name but
# drop the inline polygon-list / footnote-reference content. Non-greedy
# so nested parens stay sane (the source PDFs don't nest). The negative
# lookahead skips pure footnote anchors like "(*)" and "(**)" so the
# end-marker pass can still match "(*).—Municipio que engloba …".
_PAREN_ASIDE_RE = re.compile(r"\s*\((?!\s*[\*†‡]+\s*\))[^)]*\)")


# Asterisk / dagger footnote markers that follow a commune name in MAPA
# pliegos ("San Miguel de Cinca*", "Zaragoza**"). Matches the pure
# `(*)` / `(**)` parenthetical form too, applied AFTER end-marker
# truncation so the trailing footnote body has been cut already.
_FOOTNOTE_MARKER_RE = re.compile(r"\(\s*[\*†‡]+\s*\)|[\*†‡]+")

# Candidate commune name: title-cased word(s), with optional articles
# and apostrophes. Filters very long matches (likely prose fragments).
_NAME_TOKEN_RE = re.compile(
    r"\b("
    r"(?:[Aa]l?|[Ee]l|[Ll][aoes]s?|[Oo]s?|[Ss]|[Dd]el?|[Ll]\')?"
    r"\s*[A-ZÁÉÍÓÚÑÜÀ][\wÁÉÍÓÚÑÜàáéíóúñüÀÉÍÓÚ\-'’]+"
    r"(?:\s+(?:de(?:l)?|del?\s+los|de\s+las?|i|y)\s+[A-Z][\wÁÉÍÓÚÑÜàáéíóúñü\-'’]+){0,4}"
    r")\b",
)


# Stopwords that look like names but are not. Spanish/Catalan/Galician
# function words + administrative phrases that may slip through.
_NAME_STOPWORDS = frozenset({
    "y", "o", "i", "del", "de", "la", "las", "los", "el", "lo",
    "que", "como", "siempre", "cuando", "según", "segun",
    "denominación", "denominacion", "origen", "indicación",
    "indicacion", "geográfica", "geografica", "protegida",
    "comunidad", "autónoma", "autonoma", "provincia", "provincias",
    "ha", "polígono", "poligono", "polígonos", "poligonos",
    "parcela", "parcelas", "vinos", "vino",
    "amparados", "amparada", "amparado",
    "viñedos", "vinedos",
    "constituida", "constituido",
    "comprende", "comprenden",
    "todos", "toda", "todo", "totalidad",
    "ribera", "monte",  # too generic on their own
    "norte", "sur", "este", "oeste",
    "parte", "asi", "así",
    "isla", "illa", "ille",  # "isla de Mallorca" → keep "Mallorca"
    "mediante",
    "san", "santa",  # too generic alone, keep only with following word
})


# ---------------------------------------------------------------------------
# Name normalisation — the key both sides of the GISCO match are reduced to.
# Lives here rather than in geometry.py so the tokenizers below can use it
# without stage 02 importing geopandas; geometry.py imports it from here.
# ---------------------------------------------------------------------------

def _normalise_commune_name(s: str) -> str:
    """Strip diacritics, articles (leading + GISCO's trailing-comma
    convention), and parenthetical suffixes; lowercase. Same idiom as
    scripts/_lib/lieu_dit.py:_normalise_name on the FR side."""
    # Pliegos type the Valencian/Catalan apostrophe as U+2019 ("Sant Joan
    # d’Alacant") or as an acute accent ("Vall d´Alba"); GISCO uses the
    # ASCII one, and NFKD would simply drop the other forms.
    s = re.sub(r"[\u2018\u2019\u00b4`]", "'", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    # GISCO writes co-official names as "Labastida / Bastida"; the first
    # form is the key. This has to run before the character-class pass
    # below, which turns "/" into a space — it used to run after, so no
    # bilingual name ever matched exactly and every one of them fell
    # through to the noisy first-word lookup. The other forms are indexed
    # too (see `_name_forms`).
    if "/" in s:
        s = s.split("/", 1)[0]
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parenthetical context
    # A hyphen is a word separator, not part of the word: the pliego's
    # "Vélez Rubio" is GISCO's "Vélez-Rubio", and "Oyón-Oion" must key on
    # the first word "oyon" for the pliego's bare "Oyón" to reach it.
    s = re.sub(r"[^A-Za-z0-9\s']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # GISCO lists Catalan / Castilian / Galician / Mallorquí articled
    # names as "Borges del Camp, Les" / "Canonja, La" / "Castell, Es",
    # so after the comma-to-space pass the article surfaces as a
    # trailing token. Pliegos use article-first ("Les Borges del Camp").
    # Strip both forms so the two normalise to the same root.
    _articles = {
        "la", "el", "los", "las", "lo",
        "les", "els", "l'",
        "es", "sa", "ses",
        "o", "a", "os", "as",
    }
    s = re.sub(r"^l'", "", s)
    # Catalan "i" and Castilian "y" are the same conjunction: the pliego's
    # "Sanet i Negrals" is GISCO's "Sanet y Negrals".
    s = re.sub(r"\bi\b", "y", s)
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in _articles:
        s = parts[1]
    parts = s.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in _articles:
        s = parts[0]
    return s


# Particles that vary between a pliego's and GISCO's spelling of one name
# ("Cogollos Vega" / "Cogollos de la Vega", "San Miguel de Cinca" / "San
# Miguel del Cinca"); the remaining words are what identifies the place.
_CONNECTORS = frozenset({
    "de", "del", "la", "las", "los", "el", "l'", "d'", "y", "e", "en",
    "do", "da", "dos", "das", "o", "a", "os", "as",
})


def _content_words(norm: str) -> tuple[str, ...]:
    """The words of a normalised name that identify the place: particles
    dropped, and an elided one ("d'Anglesola", "l'Alcora") peeled off its
    word, so "Sant Joan de Alacant" and "Sant Joan d'Alacant" agree."""
    words = (re.sub(r"^[dl]'", "", w) for w in norm.split())
    return tuple(w for w in words if w and w not in _CONNECTORS)


def _same_name(a: str, b: str) -> bool:
    """Two normalised names that differ only in particles or in where a
    word breaks ("Lapuebla de La barca" / "Lapuebla de Labarca")."""
    return _content_words(a) == _content_words(b) or a.replace(" ", "") == b.replace(" ", "")


# ---------------------------------------------------------------------------
# Municipio names that contain a conjunction — "Los Palacios y Villafranca",
# "Gimenells i el Pla de la Font", "Vielha e Mijaran" — which the " y " /
# " i " / " e " split below would cut in two (and then bind the second half
# to a homonym: Navarra's Villafranca, 580 km from Sevilla). Stage 02 has no
# GISCO access, so the roster is checked in, generated from the LAU zip.
# ---------------------------------------------------------------------------

_COMPOUND_MUNICIPIOS_PATH = Path(__file__).with_name("compound_municipios.json")

# A piece may be re-joined to the next one across a comma or a conjunction,
# never across ";" or a sentence / line break.
_SOFT_SEP_RE = re.compile(r"\s*,\s*|\s+(?:y|i|e)\s+")


@lru_cache(maxsize=1)
def _compound_keys() -> tuple[frozenset[str], frozenset[tuple[str, ...]]]:
    """The compound names as the normalised key and as the content-word
    tuple (particles dropped — the pliego's "Gimenells y Pla de la Font" is
    GISCO's "Gimenells i el Pla de la Font")."""
    doc = json.loads(_COMPOUND_MUNICIPIOS_PATH.read_text(encoding="utf-8"))
    norms = {_normalise_commune_name(m["name"]) for m in doc["municipios"]}
    return frozenset(norms), frozenset(_content_words(n) for n in norms)


# A whole token that is only an article — GISCO's "Les" (Val d'Aran) — or
# nothing once normalised. Never a piece of a compound name.
_BARE_ARTICLES = frozenset({"el", "la", "los", "las", "els", "les", "es", "sa", "a", "o", "os", "as", "l", "d"})


def _bare_article(token: str) -> bool:
    norm = _normalise_commune_name(token)
    return not norm or norm in _BARE_ARTICLES or not _content_words(norm)


def merge_compound_municipios(tokens: list[str], seps: list[str]) -> list[str]:
    """Re-join the pieces of a compound municipio name. `seps[k]` is the
    separator that preceded `tokens[k]` in the source (`seps[0]` is empty).
    Up to four pieces are tried, longest run first, and a run is one name
    only when its whole text is a `compound_municipios.json` name — so two
    real municipios listed side by side are never fused."""
    exact, by_words = _compound_keys()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        end = i
        for j in range(min(i + 3, len(tokens) - 1), i, -1):
            if not all(_SOFT_SEP_RE.fullmatch(seps[k]) for k in range(i + 1, j + 1)):
                continue
            # Every piece must be a name of its own. "Vielha e Mijaran, Les
            # y Bossòst" would otherwise fuse Les — the one municipio whose
            # whole name is an article (Val d'Aran, INE 25125) — into the
            # compound before it, because the normaliser strips a trailing
            # article the way GISCO writes "Borges del Camp, Les".
            if any(_bare_article(tokens[k]) for k in range(i, j + 1)):
                continue
            joined = tokens[i] + "".join(seps[k] + tokens[k] for k in range(i + 1, j + 1))
            norm = _normalise_commune_name(joined)
            if norm in exact or _content_words(norm) in by_words:
                end = j
                break
        if end == i:
            out.append(tokens[i])
        else:
            joined = tokens[i] + "".join(seps[k] + tokens[k] for k in range(i + 1, end + 1))
            out.append(re.sub(r"\s+", " ", joined).strip())
        i = end + 1
    return out


def _split_municipios(body: str, separators: str) -> list[str]:
    """Split an enumeration on the `separators` alternation, keeping every
    compound municipio name whole."""
    parts = re.split(f"({separators})", body)
    return merge_compound_municipios(parts[0::2], [""] + parts[1::2])


# Province-wide IGP pattern: "todos los términos municipales de las
# provincias de Badajoz y Cáceres" (Extremadura). Requires the explicit
# "todos los términos municipales" prefix — otherwise we mis-fire on
# Barbanza-style "the bulk is in the province of Pontevedra" descriptive
# mentions, which are NOT a whole-province inclusion. The second
# alternation handles MAPA-style "es la provincia de Córdoba, incluyendo
# todos sus municipios".
_PROVINCE_WIDE_RE = re.compile(
    r"(?:"
    r"todos?\s+los\s+t[eé]rminos\s+municipales\s+de\s+"
    r"(?:la\s+provincia|las\s+provincias)\s+de\s+"
    r"|(?:es\s+|comprende\s+|abarca\s+)?la\s+provincia\s+de\s+"
    r"(?=[A-ZÀ-ÿ].{0,120}?(?:incluyendo\s+todos\s+sus\s+municipios|todos\s+sus\s+t[eé]rminos))"
    r")"
    r"(?P<provinces>[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+(?:\s+(?:y|i|e)\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]+){0,4})",
    re.IGNORECASE | re.DOTALL,
)


# Whole-CCAA IGP pattern: "todos los términos municipales del territorio
# de Castilla-La Mancha" (Castilla IGP). Captures the CCAA name. Caller
# resolves to province codes via region.CCAA_TO_PROVINCE_INES.
#
# Additional MAPA Spanish-national variants: "totalidad de los
# municipios de la Comunidad Autónoma de Castilla y León" (Castilla y
# León IGP); "se extiende a toda las islas que conforman la Comunidad
# Autónoma de les Illes Balears" (Illes Balears IGP); "Comunidad
# Autónoma de Cantabria, zona comprendida …" as a section-leading
# statement (Costa de Cantabria IGP).
_CCAA_WIDE_RE = re.compile(
    r"(?:t[eé]rminos\s+municipales\s+del\s+territorio\s+de\s+"
    r"|toda\s+la\s+(?:Comunidad\s+Aut[oó]noma|comunidad\s+aut[oó]noma)\s+(?:de\s+)?"
    r"|en\s+toda\s+la\s+Comunidad\s+Aut[oó]noma\s+(?:de\s+)?"
    # MAPA Spanish-national format: "totalidad de los municipios de la
    # Comunidad Autónoma de X".
    r"|totalidad\s+de\s+los\s+municipios\s+de\s+la\s+Comunidad\s+Aut[oó]noma\s+(?:de\s+)?"
    # Illes Balears: "toda(s)? la(s)? isla(s) que conforman la Comunidad
    # Autónoma de X". The Catalan article "les" is tolerated after "de".
    r"|tod[ao]s?\s+l[ao]s?\s+islas?\s+que\s+conforman\s+la\s+Comunidad\s+Aut[oó]noma\s+(?:de\s+(?:les\s+|las\s+)?)?"
    # Section-leading "Comunidad Autónoma de X, zona comprendida …"
    # (Costa de Cantabria's section 9 starts this way). Anchored with
    # `\A` not `^` so it only fires when the geo text BEGINS with this
    # phrase — preceding context like "los términos municipales de la
    # Comunidad Autónoma de Aragón" (a province-context aside in
    # Ribera del Queiles's pliego) is NOT a whole-CCAA inclusion.
    r"|\A[\s\W]*Comunidad\s+Aut[oó]noma\s+de\s+"
    r")"
    # Capture the CCAA name. The trailing optional " y León" / "-La
    # Mancha" lets compound names like "Castilla y León" stay intact —
    # otherwise the lookahead's " y " boundary cuts them at "Castilla".
    r"(?P<ccaa>"
    r"[A-ZÀ-ÿ][A-Za-zÀ-ÿ' \-]{3,40}?"
    r"(?:\s+y\s+Le[oó]n|\s*-\s*La\s+Mancha)?"
    r")"
    r"(?=[,.;\n)]|\s+(?:y|i|hasta|en|con|que|excepto|salvo)\b)",
    re.IGNORECASE,
)


# Island-wide IGP pattern (Baleares: Mallorca / Menorca / Formentera /
# Ibiza). Captures the island name. Caller resolves to GISCO INE codes
# via _lib/es/baleares.py:ines_for_island.
_ISLAND_WIDE_RE = re.compile(
    r"(?:toda\s+la\s+(?:isla|illa)\s+(?:de\s+)?"
    r"|todos\s+los\s+municipios\s+de\s+la\s+(?:isla|illa)\s+(?:de\s+)?"
    r"|comprende\s+todos\s+los\s+municipios\s+de\s+la\s+(?:isla|illa)\s+(?:de\s+)?"
    r"|el\s+territorio\s+de\s+la\s+(?:isla|illa)\s+(?:de\s+)?"
    r"|todo\s+el\s+territorio\s+de\s+la\s+(?:isla|illa)\s+(?:de\s+)?"
    r"|en\s+la\s+(?:isla|illa)\s+(?:de\s+)?)"
    r"(?P<island>(?:Eivissa|d'Eivissa|d Eivissa|Mallorca|Menorca|Ibiza|Formentera))"
    r"(?=[,.;\n)]|\s+(?:y|i|hasta|en|con|que|ubicada|ubicado)\b)",
    re.IGNORECASE,
)


def parse_island_wide(geo_area_brief: str) -> str | None:
    """Detect a "whole island" inclusion (Mallorca IGP: 'toda la isla
    de Mallorca'). Returns the canonical island name or None.

    The island name is one of {"Mallorca", "Menorca", "Formentera",
    "Ibiza"}; caller resolves to the INE municipi list via
    `_lib/es/baleares.py:ines_for_island`."""
    from _lib.es.baleares import island_for
    for m in _ISLAND_WIDE_RE.finditer(geo_area_brief):
        island = island_for(m.group("island"))
        if island:
            return island
    return None


def parse_ccaa_wide(geo_area_brief: str) -> str | None:
    """Detect a "whole CCAA" inclusion (Castilla IGP: 'parcels in all
    communes of Castilla-La Mancha territory'). Returns the canonical
    CCAA name or None."""
    m = _CCAA_WIDE_RE.search(geo_area_brief)
    if not m:
        return None
    raw = m.group("ccaa").strip()
    # Common variants → canonical (mirror of CCAA_ALIASES in region.py
    # but kept local to avoid cycle import)
    aliases = {
        "castilla la mancha": "Castilla-La Mancha",
        "castilla-la mancha": "Castilla-La Mancha",
        "catalunya": "Cataluña",
        "comunitat valenciana": "Comunidad Valenciana",
        "euskadi": "País Vasco",
        "país vasco": "País Vasco",
        "galiza": "Galicia",
        "illes balears": "Baleares",
        "islas baleares": "Baleares",
    }
    return aliases.get(raw.lower(), raw)


def parse_province_wide_list(geo_area_brief: str) -> list[str]:
    """Detect "all communes of province(s) X[, Y, Z]" pattern. Returns
    a list of province names (raw form — caller resolves to INE code +
    GISCO commune list)."""
    text = geo_area_brief
    out: list[str] = []
    seen: set[str] = set()
    for m in _PROVINCE_WIDE_RE.finditer(text):
        raw = m.group("provinces")
        # Split on " y "/" i "/" e " and commas
        for tok in re.split(r"\s+(?:y|i|e)\s+|\s*,\s*", raw):
            tok = tok.strip()
            if not tok or len(tok) > 40:
                continue
            key = tok.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(tok)
    return out


def parse_commune_list(geo_area_brief: str) -> list[str]:
    """Extract a flat list of commune names from an IGP / PDO geo_area_brief.

    Returns names in the order they appear in the text, deduplicated
    by case-folded form. Returns [] when no commune-list lead-in is
    detected — that's the signal for stage 04 to fall back to Figshare
    or skip the wine entirely."""
    text = geo_area_brief
    # Find the first list-introducing phrase; the commune enumeration
    # follows. If multiple lead-ins exist, scan from the first one.
    leadin = _LIST_LEADIN_RE.search(text)
    if not leadin:
        return []
    body = text[leadin.end():]

    munis = [m.group("muni") for m in _MUNI_WITH_PARROQUIAS_RE.finditer(body)]
    if len(munis) >= 2:
        return _dedupe([_clean_token(m) for m in munis])

    # Strip parenthetical asides BEFORE end-marker truncation so polygon
    # text trapped inside parentheses ("Zaragoza (en Zaragoza, polígonos
    # catastrales 152, …)") doesn't trigger a false cut on "polígono".
    # Footnote-marker stripping ("*", "**") is deferred until AFTER
    # end-marker checks so the "(*).—Municipio que engloba …" anchor
    # still matches as an end marker.
    body = _PAREN_ASIDE_RE.sub("", body)
    body = _PARROQUIA_ENUM_RE.sub(" ", body)
    body = _fold_whole_muni_continuation(body)

    # Truncate at the first end marker.
    cut = len(body)
    end = _LIST_END_RE.search(body)
    if end:
        cut = end.start()
    # Also truncate at the first sentence break that's followed by a
    # narrative clause (period + capital letter that ISN'T a continuation
    # of a commune list).
    for m in re.finditer(r"\.\s+[A-Z]", body[:cut]):
        ahead = body[m.start() + 2 : m.start() + 80]
        if any(kw in ahead.lower() for kw in
               ("la mayor", "el resto", "esta zona", "todo el territorio",
                "las parroquias son", "los polígonos",
                "en los vinos", "la uva proceder", "la uva procede",
                "las parcelas",
                "en la siguiente", "se extiende", "se localiza",
                "se sitúa", "la serra", "el conjunto", "las illes",
                "las características", "ocupa una")):
            cut = m.start()
            break
    body = body[:cut]

    # Now-safe to drop footnote markers ("San Miguel de Cinca*"
    # → "San Miguel de Cinca") and replace "Provincia de X:" sub-headers
    # with commas so per-province sub-lists merge.
    body = _FOOTNOTE_MARKER_RE.sub("", body)
    body = _PROVINCE_HEADER_RE.sub(", ", body)

    # Tokenise: split on commas, " y ", " i " (Catalan), semicolons,
    # period-then-newline (sub-list boundary between provinces, after
    # the header has been replaced).
    raw_tokens = _split_municipios(body, r"\s*[,;]\s*|\s+(?:y|i|e)\s+|\.\s*\n+")
    return _dedupe(_clean_token(tok) for tok in raw_tokens)


def _dedupe(names) -> list[str]:
    """Drop empties and case-folded repeats, keeping first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def parse_whole_commune_prefix(geo_area_brief: str) -> list[str]:
    """For DOP pliegos that mix whole-commune inclusions with
    partial-commune (polygon-list) inclusions — Priorat ("Bellmunt,
    Gratallops, ..., La Vilella Baixa, la parte norte del municipio
    de Falset…") and Montsant ("La totalidad de los términos
    municipales siguientes:\\nLa Bisbal de Falset\\nCabacés\\n…").

    Extracts the whole-commune list BEFORE the first partial-commune
    anchor. Returns commune names. Used by the hybrid stage 04
    resolver to compute (whole-commune-union ∪ SIGPAC-polygon-union).
    """
    text = geo_area_brief
    # Find the cutoff: anything that signals we've moved into partial-
    # commune territory (polygon-list / parcela-level / colon-block).
    cut_patterns = [
        r"la\s+parte\s+(?:norte|sur|este|oeste|nordeste|noroeste)\s+",
        r"del?\s+municipio\s+de\s+",
        r"del?\s+t[eé]rmino\s+municipal\s+de\s+",
        r"el\s+municipio\s+de\s+",
        r"Y,?\s+en\s+parte,?",
        r"Y\s+las\s+parcelas",
        r"y\s+las\s+parcelas",
        # "…, así como las zonas de sierra pertenecientes a los términos
        # municipales de Alcaudete (polígonos …)" — Sierra Sur de Jaén;
        # "así como en los polígonos catastrales … de Mallén" — Campo de
        # Borja. The conjunction opens the partial-commune tail.
        r"\bas[ií]\s+como\b",
    ]
    cut = len(text)
    for pat in cut_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m and m.start() < cut:
            cut = m.start()

    # Was there an explicit "totalidad" lead-in (Montsant style)? If so,
    # take from that lead-in's end to the cut. Try the most-specific
    # variant first because the bare "en los términos municipales"
    # often appears earlier in introductory prose and would clobber.
    leadin_specific = re.search(
        r"La\s+totalidad\s+de\s+los\s+t[eé]rminos\s+municipales\s+siguientes\s*:",
        text[:cut],
        re.IGNORECASE,
    )
    if leadin_specific:
        leadin = leadin_specific
    else:
        leadin = re.search(
            r"los\s+t[eé]rminos\s+municipales\s+(?:siguientes\s*:|de)?\s*",
            text[:cut],
            re.IGNORECASE,
        )
    body = text[leadin.end():cut] if leadin else text[:cut]
    # A line break inside a name ("Castillo de\nLocubín") is a PDF wrap,
    # not a list separator: a commune name never ends in a preposition
    # or an article.
    body = re.sub(
        r"\b(de|del|la|las|los|el|les|els|d')\n\s*", r"\1 ", body, flags=re.IGNORECASE,
    )

    raw_tokens = _split_municipios(body, r"\s*[,;]\s*|\s+(?:y|i|e)\s+|\n+")
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw_tokens:
        name = _clean_token(tok)
        if not name:
            continue
        # Drop tokens that look like a single-word fragment carried over
        # from a name like "La Morera de Montsant y su agregado Escaladei"
        # (after splitting on " y ", "su agregado Escaladei" appears as
        # a token starting lowercase — already filtered by _is_commune_token,
        # except the parenthetical-aside form passes here).
        if "agregado" in name.lower():
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _clean_token(t: str) -> str:
    """Trim whitespace + drop tokens that are stopwords, fragments, or
    too long to be commune names."""
    t = re.sub(r"\s+", " ", t).strip().rstrip(",;.")
    if not t or len(t) > 80:
        return ""
    # Token must START with an uppercase letter (Spanish proper noun
    # convention). Articles are tolerated as a prefix.
    if not re.match(r"(?:[ALEOIDS]l?\s+|[Ll]a\s+|[Ll]os\s+|[Ll]as\s+|[Dd]e(?:l)?\s+|[Oo]s?\s+)?[A-ZÁÉÍÓÚÑÜÀ]", t):
        return ""
    if t.lower() in _NAME_STOPWORDS:
        return ""
    # Drop tokens that look like sub-municipal mentions or non-commune
    # narrative ("En total supone una superficie de 1 338", "En la
    # provincia de Jaén").
    if any(t.lower().startswith(p) for p in
           ("las parroquias de ", "la parroquia de ", "parroquias ",
            "parte ", "polígono ", "poligono ", "parcela ",
            "del término ", "del termino ",
            "las pedanías ", "el municipio ", "los municipios ",
            "en total ", "en el ", "en la ", "en los ", "en las ")):
        return ""
    # Strip "del término municipal de X" suffix
    t = re.sub(r"\s+del\s+t[eé]rmino\s+municipal\s+de\s+\S+.*$", "", t, flags=re.IGNORECASE)
    # "los términos municipales de Villaviciosa de Córdoba y de Espiel en
    # la provincia de Córdoba": the repeated "de" after the split and the
    # province tail are the sentence, not the name.
    t = re.sub(r"^de\s+(?=[A-ZÁÉÍÓÚÑÜÀ])", "", t)
    t = re.sub(
        r"\s+en\s+(?:la|el|las|los)\b(?:\s+(?:provincia|comunidad|comarca|isla|zona)\b.*)?$",
        "", t, flags=re.IGNORECASE,
    )
    t = re.sub(r"\s+pertenecientes?\s+a\s.*$", "", t, flags=re.IGNORECASE)
    return t.strip()


# ---------------------------------------------------------------------------
# Parroquia inclusions — the sub-municipal enumerations the functions above
# strip. Resolved against the IET Mapa de Parroquias (scripts/_lib/es/
# parroquia.py); the whole-municipio parsers are untouched by this section.
# ---------------------------------------------------------------------------

# The unit word, tolerant of a PDF line-break hyphen ("parro-quias" in the
# Monterrei documento único) and of the singular.
_PARR = r"parro-?\s*quias?"
_MUNI_UNIT = r"(?:t[eé]rmino\s+municipal|ayuntamiento|concello|municipio)"
_NAME_LIST = r"(?:(?!" + _PARR + r"\s+de\b)[^;:])+?"

# Form A — parishes first, holder last: "las parroquias de A, B y C del
# término municipal de X" / "… en el ayuntamiento de X" / "la parroquia de
# A, del término municipal de X". The list may not cross a ";" or ":", nor
# a second "parroquias de" (that one is the next enumeration); the holder
# ends at punctuation, the conjunction into another enumeration ("y de las
# parroquias de …", Betanzos) or the end of the text.
_PARR_FORM_A_RE = re.compile(
    r"(?:las?\s+)?" + _PARR + r"\s+de\s+(?P<names>" + _NAME_LIST + r")"
    r"\s*,?\s+(?:del|en\s+el)\s+" + _MUNI_UNIT + r"\s+de\s+"
    r"(?P<muni>[^,;.:\n]+?)"
    r"(?=\s*[,;.:\n]|\s+y\s+(?:de\s+)?las?\s+" + _PARR + r"\b|\s+las?\s+" + _PARR + r"\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Form B — holder first: "del ayuntamiento de Riós, las parroquias de A, B y
# C" (Monterrei), "del ayuntamiento de Toén los lugares de … y la parroquia
# de Alongos" (Ribeiro — the lugares between are villages, not parishes, and
# are skipped). The holder ends at a comma / colon or before an article, and
# the enumeration runs to the end of the clause.
# The gap between holder and enumeration may not name another holder —
# "… en el ayuntamiento de Ourense, y del ayuntamiento de Toén los lugares
# de … y la parroquia de Alongos" binds Alongos to Toén, not Ourense.
_PARR_FORM_B_RE = re.compile(
    r"(?:del|en\s+el)\s+" + _MUNI_UNIT + r"\s+de\s+"
    r"(?P<muni>[^,;:\n]+?)(?=\s*[,:]|\s+(?:los|las|la|el)\s)"
    r"(?:(?!(?:del|en\s+el)\s+" + _MUNI_UNIT + r"\s+de\b)[^;])*?"
    r"\b(?:las?\s+)?" + _PARR + r"\s+de\s+(?P<names>" + _NAME_LIST + r")"
    r"(?=\s*[;:]|\s*\.\s*(?:\n|\Z)|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Form C — one line per holder: "- X: las parroquias de A, B y C." (Valle
# del Miño-Ourense). The list may wrap lines; it ends at the sentence's
# period, the next dash line or the end of the text.
_PARR_FORM_C_RE = re.compile(
    r"^\s*[-•—]\s*(?P<muni>[^:\n]+?)\s*:\s*(?:las?\s+)?" + _PARR + r"\s+de\s+"
    r"(?P<names>" + _NAME_LIST + r")"
    r"(?=\s*\.\s*(?:\n|\Z)|\n\s*[-•—]|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

# Whole-municipio inclusions written beside the parish ones: "la totalidad
# del municipio de Negueira de Muñiz" (Terras do Navia), "comprende el
# ayuntamiento de Vilardevós," (Monterrei's ladera subzona). Kept in the
# same result so a resolver sees the record's sub-municipal delimitation in
# one list.
_WHOLE_MUNI_RE = re.compile(
    r"(?:la\s+totalidad\s+del\s+" + _MUNI_UNIT + r"|comprende\s+el\s+ayuntamiento)"
    r"\s+de\s+(?P<muni>[^,;.:\n]+?)(?=\s*[,;.:\n]|\Z)",
    re.IGNORECASE,
)


def parse_parroquia_inclusions(text: str) -> list[dict]:
    """Parishes a pliego names inside a municipio, as
    `[{"municipio": str, "parroquias": [str, …]}, …]` in text order, one
    entry per (municipio, enumeration); a whole-municipio inclusion written
    alongside comes back as `{"municipio": str, "parroquias": [], "whole":
    True}`. Empty when the text enumerates no parishes. The three forms are
    matched in order — line form, parishes-first, holder-first — each on
    the text with the earlier matches blanked, so a holder-first clause can
    never swallow the parishes-first enumeration that follows it."""
    if not text or not re.search(_PARR + r"\s+de\b", text, re.IGNORECASE):
        return []
    body = _PAREN_ASIDE_RE.sub("", text)
    out: list[dict] = []
    for pattern in (_PARR_FORM_C_RE, _PARR_FORM_A_RE, _PARR_FORM_B_RE):
        spans: list[tuple[int, int]] = []
        for m in pattern.finditer(body):
            names = _split_parroquia_names(m.group("names"))
            muni = _clean_token(m.group("muni"))
            if not names or not muni:
                continue
            out.append({"municipio": muni, "parroquias": names, "start": m.start()})
            spans.append(m.span())
        for start, end in spans:
            body = body[:start] + " " * (end - start) + body[end:]
    for m in _WHOLE_MUNI_RE.finditer(body):
        muni = _clean_token(m.group("muni"))
        if muni:
            out.append({"municipio": muni, "parroquias": [], "whole": True, "start": m.start()})
    out.sort(key=lambda e: e.pop("start"))
    return out


def _split_parroquia_names(raw: str) -> list[str]:
    """Split an enumeration on commas and the Castilian " y " (also the
    Oxford ", y "). The Galician " e " is left inside a name ("Fumaces e A
    Trepa" is one parish); a line break inside a name is a PDF wrap, a
    hyphen at it a hyphenation artefact ("Tama-\\nguelos")."""
    raw = re.sub(r"-\n\s*", "-", raw)
    raw = re.sub(r"\s*\n\s*", " ", raw)
    names: list[str] = []
    for tok in re.split(r"\s*,\s*(?:y\s+)?|\s+y\s+", raw):
        tok = re.sub(r"\s+", " ", tok).strip(" .;")
        if not tok or tok.lower() in _NAME_STOPWORDS:
            continue
        if not re.match(r"[A-ZÁÉÍÓÚÑÜÀ]", tok):
            continue
        names.append(tok)
    return _dedupe(names)
