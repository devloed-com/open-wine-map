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

import re

# Markers that signal the *municipi list ends* (transition from list to
# explanatory prose). Used to truncate the captured commune list. Same
# idiom as scripts/_lib/es/subzona.py:_COMMUNE_LIST_END_MARKERS.
_LIST_END_MARKERS = (
    "Así como", "Asi como", "Así mismo", "Asi mismo",
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
    r"|los\s+t[eé]rminos\s+municipales\s+(?:siguientes\s*:|de)?\s*"
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

    # Strip parenthetical asides BEFORE end-marker truncation so polygon
    # text trapped inside parentheses ("Zaragoza (en Zaragoza, polígonos
    # catastrales 152, …)") doesn't trigger a false cut on "polígono".
    # Footnote-marker stripping ("*", "**") is deferred until AFTER
    # end-marker checks so the "(*).—Municipio que engloba …" anchor
    # still matches as an end marker.
    body = _PAREN_ASIDE_RE.sub("", body)

    # Truncate at the first end marker.
    cut = len(body)
    for marker in _LIST_END_MARKERS:
        i = body.find(marker)
        if 0 <= i < cut:
            cut = i
    # Also truncate at the first sentence break that's followed by a
    # narrative clause (period + capital letter that ISN'T a continuation
    # of a commune list).
    for m in re.finditer(r"\.\s+[A-Z]", body[:cut]):
        ahead = body[m.start() + 2 : m.start() + 80]
        if any(kw in ahead.lower() for kw in
               ("la mayor", "el resto", "esta zona", "todo el territorio",
                "las parroquias son", "los polígonos",
                "en los vinos", "la uva proceder", "la uva procede",
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
    raw_tokens = re.split(r"\s*[,;]\s*|\s+(?:y|i|e)\s+|\.\s*\n+", body)
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw_tokens:
        name = _clean_token(tok)
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

    raw_tokens = re.split(r"\s*[,;]\s*|\s+(?:y|i|e)\s+|\n+", body)
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
    return t.strip()
