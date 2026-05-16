"""Parser for the Spanish *national* pliego de condiciones (the canonical
regional-gazette / JCCM-style PDF), not the EU-OJ "documento único".

The documento único only lists *principal* varieties in section 7. The
national pliego (linked from documento único section 9) is the only place
the full set — principal + accessory — is enumerated. This parser pulls
the variety section from a `pdftotext -layout` plain-text rendering.

Currently scoped to the **Castilla-La Mancha (JCCM)** template, which uses
the structure:

    6. VARIEDADES DE UVAS DE VINIFICACIÓN

    - Tintas: Garnacha tinta, Garnacha Peluda, Garnacha Tintorera, ...
    - Blancas: Albillo Real, Macabeo, Sauvignon Blanc, ...

    7. VÍNCULO CON LA ZONA GEOGRÁFICA

Other regional templates (Catalonia DOGC, Murcia BORM, Castilla y León
BOCYL, …) likely need their own header / colour-bullet shapes. Add them as
sibling functions when the corpus needs them.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import sys

_LIB_ROOT = Path(__file__).resolve().parents[1]
if str(_LIB_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT.parent))
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS, slugify  # noqa: E402

# Variety-section header. Two strengths — prefer "strong" (with keyword
# trailer) over "weak" (heading-only) so we don't lock onto an
# unrelated TOC entry that happens to read "6. Variedades".
#
# Variants seen in the ES corpus:
#   "6. VARIEDADES DE UVAS DE VINIFICACIÓN"        (mentrida, JCCM)
#   "6. Variedades de uvas de vinificación"        (valdepeñas)
#   "6.- Variedades de vid"                         (casa-del-blanco)
#   "6. - VARIEDADES VINÍFERAS"                     (montsant, INCAVI)
#   "6. Variedades de Vitis Vinifera"               (cataluña)
#   "6) VARIEDAD O VARIEDADES DE UVA DE LAS QUE..." (calatayud)
#   "F) VARIEDADES DE UVA DE LAS QUE PROCEDE EL VINO."   (condado-de-huelva)
#   "F. VARIEDADES DE UVA AUTORIZADAS."             (montilla-moriles)
#   "6. Variedad o variedades"   (no trailer)        (ribeira-sacra)
# Second alternative `\s+` covers bare-whitespace separators (ribera-del-
# guadiana's body header reads `6 VARIEDADES DE VID.` with no `.` or `)`
# after the digit). Digit count bounded to 1-2 so postal codes, phone
# numbers, and yields in the body (e.g. "06200 Almendralejo",
# "10.000 kg/ha") don't masquerade as section headers under the relaxed
# separator. Leading whitespace bounded to 0-16 chars (same-line only, no
# newlines) so deeply-indented matches inside revision-history tables
# (rueda's MAPA PDF: a column-23 "6) Variedades autorizadas:" table cell)
# don't outrank the real section header further down. 16 accommodates
# legitimate column-1-to-13 headers like valencia's "             6.-
# VARIEDAD O VARIEDADES DE UVAS DE VINIFICACIÓN" (col 13, MAPA layout
# with wide left margin). Combined with the TOC-line filter in
# find_variety_section, this stays robust against pliegos whose TOC
# entries also have the full trailer.
_PREFIX = r"^[ \t\f]{0,16}(?:\d{1,2}|[A-K])(?:\s*[\.\)]\s*-?\s*|\s+)"
_VARIEDAD = r"VARIEDAD(?:ES)?(?:\s+O\s+VARIEDAD(?:ES)?)?"
# Bare `VITIS VIN[IÍ]FERA[S]?` (without "DE" prefix) covers penedes's
# "6.-Variedades Vitis viníferas" header where the existing
# "DE\s+VITIS\s+VIN[IÍ]FERA" form fails — penedes drops the "DE" linker.
_TRAILER = (
    r"\s+(?:DE\s+(?:UVAS?|VID|VINIFICACI[OÓ]N|VITIS\s+VIN[IÍ]FERA[S]?)"
    r"|VITIS\s+VIN[IÍ]FERA[S]?"
    r"|VIN[IÍ]FERAS?|AUTORIZADAS?)"
)
_SECTION_HEADER_STRONG_RE = re.compile(
    _PREFIX + _VARIEDAD + _TRAILER + r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_HEADER_WEAK_RE = re.compile(
    _PREFIX + _VARIEDAD + r"\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Reject candidate header lines that are obviously TOC entries — either a
# dot-leader (4+ consecutive dots) or a trailing standalone page number.
_TOC_LINE_RE = re.compile(r"\.{4,}|\s+\d{1,4}\s*$")

# Next-section heading — used to find the END of the variety body.
# Captures the section prefix + the first word of the title so we can
# decide either by (a) prefix comparison (next number must be strictly
# greater) or (b) the title being a known post-§6 section name.
# Both separator alternatives use `[^\S\n]` (whitespace minus newline) so
# a standalone page number followed by a wrapped variety line on the next
# page does NOT match — penedes's pdftotext output has `…\n10\n\nMacabeo,
# Xarel.lo, …` mid-section, which under bare `\s+` reads as "section 10.
# Macabeo" and truncates the variety body before the list begins.
_NEXT_SECTION_RE = re.compile(
    r"^[^\S\n]*(\d{1,2}|[A-K])(?:[^\S\n]*[\.\)][^\S\n]*-?[^\S\n]+|[^\S\n]+)([A-Za-zÁÉÍÓÚÑáéíóúñ]+)",
    re.MULTILINE,
)

# Titles that indicate a post-variety section regardless of prefix value
# (used by find_variety_section as a semantic fallback for PDFs that
# reuse the same prefix number across multiple sections, e.g. los-
# cerrillos uses "6.-" for both Variedades and Vínculo).
_POST_VARIETY_TITLES = {
    "vínculo", "vinculo",
    "requisitos", "requisito",
    "comprobaciones", "comprobación", "comprobacion",
    "aplicación", "aplicacion", "aplicables", "aplicable",
    "verificación", "verificacion",
    "etiquetado", "envasado",
    "disposiciones", "disposición", "disposicion",
    "nombre", "dirección", "direcciones", "direccion",
    "autoridad", "autoridades",
    "organismos", "organismo",
}

# Colour-bullet line: a header marking the start of a variety enumeration
# for a given colour. Handles both bullet-prefixed ("- Tintas:") and
# "Variedades tintas:" prefix forms; the colour word itself must be present.
_COLOUR_LINE_RE = re.compile(
    r"^\s*"
    r"(?:[-•·*]\s*)?"
    r"(?:variedades?\s+)?"
    r"(tintas?|blancas?|rosadas?|negras?)"
    r"\s*:?\s*",
    re.IGNORECASE,
)

# A bullet-list item — line begins with a bullet glyph. Bullet items are
# self-contained varieties, not continuations of the prior line.
_BULLET_ITEM_RE = re.compile(r"^\s*[•·]\s")

_COLOUR_TO_TAG = {
    "tinta": "noir", "tintas": "noir",
    "negra": "noir", "negras": "noir",
    "blanca": "blanc", "blancas": "blanc",
    "rosada": "rose", "rosadas": "rose",
}

_DROP = {
    "vinificación", "vinificacion", "uvas", "uva", "vino", "vinos",
    "elaboración", "elaboracion", "producción", "produccion",
    "principal", "principales", "secundaria", "secundarias",
    "preferente", "preferentes", "autorizada", "autorizadas",
    "accesoria", "accesorias", "complementaria", "complementarias",
    "tinto", "tintos", "blanco", "blancos", "rosado", "rosados",
    "como", "siguiente", "siguientes", "obtener", "amparados",
    "variedad", "variedades", "viníferas", "viniferas", "vinifera",
    "procede", "procedente", "procedentes", "proceden",
    "permitida", "permitidas", "recomendada", "recomendadas",
    "autorizado", "autorizados", "tradicional", "tradicionales",
    "minoritaria", "minoritarias", "mayoritaria", "mayoritarias",
    "única", "unica", "exclusiva", "exclusivamente",
    "monovarietal", "monovarietales",
    "pliego", "condiciones", "dop", "igp",
    "queda", "quedó", "quedo", "prohibida", "prohibido",
    "plantaciones", "plantación", "plantacion", "nuevas",
    "considerada", "consideradas", "considerado", "considerados",
    "conocida", "conocidas", "conocido", "conocidos",
    "denominada", "denominadas", "denominado", "denominados",
    "localmente", "tienen", "consideración", "consideracion",
    "entra", "productos", "siguientes",
    "las", "tes",
    # Colour/style modifiers that leak out of "X o Y" synonym splits
    # (e.g., "Garnacha roja o gris" → my " o " split yields "gris"
    # alone, which is meaningless without the "Garnacha" prefix).
    "gris", "roja", "rojo", "rojas", "rojos",
    "negra", "negro", "negras", "negros",
    "tinta", "tintas", "blanca", "blancas",
}

# Sentence-fragment leaks: tokens whose first word is one of these are
# almost always prose, not a variety name (e.g., "de las siguientes
# variedades"). The check applies to multi-word tokens — single-word
# entries fall through the standard _DROP set above.
_PROSE_LEAD = {
    "de", "del", "para", "con", "sin", "por", "según", "segun",
    "entre", "todas", "todos", "todo", "toda", "ambas", "ambos",
    "los", "las", "el", "la", "un", "una", "unas", "unos",
    "este", "esta", "estos", "estas",
    "siguiente", "siguientes", "anterior", "anteriores",
    "principal", "principales", "secundaria", "secundarias",
    "como", "que", "donde", "cuando", "mientras",
    # Prose leaks observed in INCAVI / GVA pliegos. "Variedades tintas"
    # / "Variedades blancas" should be caught as colour headers, but
    # when they survive (mid-line in two-column layouts) we drop them.
    "variedades", "variedad", "viníferas", "viniferas", "vinifera",
    "recomendadas", "recomendada", "recomendados", "recomendado",
    "relacionadas", "relacionada", "relacionados", "relacionado",
    "autorizadas", "autorizada", "autorizados", "autorizado",
    "permitidas", "permitida", "permitidos", "permitido",
    "blancas", "blanca", "tintas", "tinta",
    # Sentence fragments lifted from Canarias / Madrid / Galicia pliegos
    # where colour/role sub-headers leak into the first variety.
    "queda", "quedó", "quedo", "obtener", "tienen", "entra",
    "pliego", "preferentes", "preferente",
}

# Sub-section role labels that prefix a variety enumeration. When a chunk
# starts with one of these followed by a colon ("Preferentes: Albillo
# Criollo"), keep only the part after the colon. Lanzarote, Tacoronte,
# Gran Canaria, La Mancha, Bizkaiko Txakolina all use this shape.
_ROLE_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"preferentes?|recomendadas?|recomendados?|autorizadas?|autorizados?"
    r"|principales?|secundarias?|secundarios?|tradicionales?|complementarias?"
    r"|permitidas?|permitidos?|accesorias?|accesorios?|minoritarias?"
    r"|mayoritarias?|exclusivas?|consideradas?|siguientes?"
    r")\s*:\s*",
    re.IGNORECASE,
)

# Letter/digit-bullet line prefix: "a) ", "a. ", "1) ", "B. ", etc. Used
# to strip role-subsection bullets like "a) Variedades blancas" /
# "b. Autorizadas: …" before the line is classified as a colour header
# or a variety enumeration.
_LETTER_BULLET_PREFIX_RE = re.compile(r"^\s*[a-z0-9]\s*[\)\.]\s+", re.IGNORECASE)

# Page-header / footer lines that leak into the variety section in some
# regional pliegos (e.g. Monterrei, Valdeorras, Tarragona). Drop the
# whole line before parsing.
_PAGE_HEADER_RE = re.compile(
    r"pliego\s+de\s+condiciones|^\s*-\s*\d+\s*-\s*$",
    re.IGNORECASE,
)

# Parenthetical content — usually a synonym ("Tempranillo (Cencibel)")
# or a regional classification marker ("(A)", "(R)" in Cataluña). The
# slug-fold via GRAPE_ALIAS already canonicalises both names, so we
# drop the parenthetical from the display name and emit each token
# inside it as a separate variety candidate. Tolerates a missing
# closing paren (column-split fragments like "(Loureiro blanco").
_PAREN_CONTENT_RE = re.compile(r"\(([^)]*)\)?")

# Trailing Spanish connector left over when a comma-list wraps to a
# column-gap break ("Pedro Ximénez y    Malvasía" → after column split
# the left chunk is "Pedro Ximénez y" — the inner " y " split never
# triggers because nothing follows it).
_TRAILING_CONNECTOR_RE = re.compile(r"\s+(?:y/o|y|o|e|u)\s*$", re.IGNORECASE)

# Multi-space gap that signals a column boundary inside the variety
# section — handles two-column variety tables (montsant lays Variedades
# blancas on the left, Variedades tintas on the right; each variety
# line shows one name in each column separated by a wide gap).
_COLUMN_GAP_RE = re.compile(r"\s{3,}")

_COLOUR_SUFFIXES = (
    "-blanc", "-blanca", "-blanco",
    "-noir", "-negra", "-negro",
    "-tinta", "-tinto",
    "-gris",
    "-rosada", "-rosado",
)


def pdf_to_text(pdf_path: Path | str) -> str:
    """Render a PDF as layout-preserving text. Requires `pdftotext` on PATH."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _stitch_continuations(text: str) -> str:
    """Join lines that continue a variety enumeration. A line is a
    continuation when (a) it doesn't open with a colour-bullet, (b) the
    previous line ends without sentence punctuation. JCCM wraps long lists
    at the right margin, e.g.

        - Tintas: Garnacha tinta, Garnacha Peluda, ..., Tempranillo,
        Cabernet Sauvignon, Merlot, Syrah, Petit Verdot, Cabernet Franc y Graciano.
    """
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.rstrip()
        if not s.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        is_colour_header = bool(_COLOUR_LINE_RE.match(s))
        is_bullet_item = bool(_BULLET_ITEM_RE.match(s))
        # A line is a continuation when the previous line is mid-
        # enumeration: contains at least one comma, didn't terminate with
        # a period, AND isn't a tabular row (two-column layouts have a
        # wide whitespace gap mid-line — montsant). Catches both trailing-
        # comma wraps ("…Tempranillo,\nCabernet…") and mid-variety wraps
        # ("…Moscatel de Grano\nMenudo y Garnacha Blanca.").
        prev = out[-1].rstrip() if out else ""
        # Wide-gap detection must look at the line *body*, not its leading
        # indent. JCCM pliegos indent bullet lines deeply ("       -   "),
        # which would otherwise be misread as a column boundary and block
        # continuation joins like `…Cabernet\nSauvignon y Merlot.`
        # (Calatayud, where the wrap split a single variety name into
        # two false slugs `cabernet` + `sauvignon`).
        prev_body = re.sub(r"^\s*[-•·*]?\s*", "", prev) if prev else ""
        prev_is_tabular = bool(prev_body) and bool(_COLUMN_GAP_RE.search(prev_body))
        is_continuation = (
            bool(prev)
            and ("," in prev)
            and not prev.endswith(".")
            and not prev_is_tabular
            and not is_colour_header
            and not is_bullet_item
        )
        if is_continuation:
            out[-1] = out[-1].rstrip() + " " + s.lstrip()
        else:
            out.append(s)
    return "\n".join(out)


def _normalise_token(name: str, ambient_colour: str) -> dict | None:
    """Slugify + alias-fold a single variety token. Mirrors the strict
    proper-noun + length checks used by stage 02's parser.

    Output `name` is lowercased to match the FR cahier-extracted
    convention (display names are canonicalised lowercase; the Wikipedia
    lexicon supplies title-cased variants at the rendering layer when
    available).
    """
    name = _LETTER_BULLET_PREFIX_RE.sub("", name)
    name = _ROLE_LABEL_RE.sub("", name)
    name = _TRAILING_CONNECTOR_RE.sub("", name)
    name = name.strip().strip(" .,;«»\"'·“”")
    if not name or len(name) < 3 or len(name) > 60:
        return None
    if any(c.isdigit() for c in name):
        return None
    if name.lower() in _DROP:
        return None
    words = name.split()
    if not words or len(words) > 5:
        return None
    if not words[0][0].isalpha():
        return None
    # Reject any token containing a prose word — e.g. "Cabernet franc
    # consideradas como autorizadas" (Arabako) where the variety has
    # been concatenated with classification prose. A real variety name
    # never contains "como" / "consideradas" / "conocida" / etc.
    if any(w.lower() in _PROSE_LEAD for w in words):
        # Allow a leading prose word only if it's the colour modifier
        # at the END (handled by colour suffix logic). Otherwise reject.
        return None
    raw = slugify(name)
    if not raw:
        return None
    slug = GRAPE_ALIAS.get(raw, raw)
    for suf in _COLOUR_SUFFIXES:
        if slug.endswith(suf):
            stem = slug[: -len(suf)]
            stem_canon = GRAPE_ALIAS.get(stem, stem)
            if stem_canon in DEFAULT_COLOUR:
                slug = stem_canon
                break
    colour = ambient_colour or DEFAULT_COLOUR.get(slug, "")
    return {"slug": slug, "name": name.lower(), "colour": colour}


def _prefix_value(prefix: str) -> tuple[int, str]:
    """Sort key for section prefixes — numbers compare as ints, letters
    fall back to lexicographic order. Returns (kind, value) so numeric and
    letter prefixes don't mix into the same comparison."""
    return (0, f"{int(prefix):04d}") if prefix.isdigit() else (1, prefix.upper())


def find_variety_section(text: str) -> tuple[int, int] | None:
    """Return (start, end) character offsets of the variety section in
    `text`, or None if not found. The slice excludes the heading line.

    Tries a strong match first (heading + keyword trailer). Falls back to
    a weak match (heading alone) when no strong match is found — this
    handles ribeira-sacra-style "6. Variedad o variedades" headings.
    """
    m = next(
        (c for c in _SECTION_HEADER_STRONG_RE.finditer(text) if not _TOC_LINE_RE.search(c.group(0))),
        None,
    )
    if m is None:
        m = next(
            (c for c in _SECTION_HEADER_WEAK_RE.finditer(text) if not _TOC_LINE_RE.search(c.group(0))),
            None,
        )
    if m is None:
        return None
    body_start = m.end()
    prefix_m = re.match(r"^\s*(\d+|[A-K])", m.group(0), re.IGNORECASE)
    if prefix_m is None:
        return (body_start, len(text))
    section_key = _prefix_value(prefix_m.group(1))
    body_end = len(text)
    for nxt in _NEXT_SECTION_RE.finditer(text, pos=body_start):
        nxt_prefix = nxt.group(1)
        nxt_title = nxt.group(2).lower()
        # Stop on the first heading that either has a strictly-greater
        # prefix or whose title is a known post-variety section name.
        # The title check handles PDFs that reuse the same prefix number
        # (los-cerrillos: "6.- Variedades..." → "6.- Vínculo..."); the
        # prefix check handles standard numbered sections (mentrida:
        # "6. ..." → "7. ...").
        if _prefix_value(nxt_prefix) > section_key or nxt_title in _POST_VARIETY_TITLES:
            body_end = nxt.start()
            break
    return (body_start, body_end)


def parse_variety_section(text: str) -> dict:
    """Parse a `pdftotext -layout` rendering of a Spanish national pliego
    de condiciones and return the variety section (apartado 6) as
    structured data.

    Returns:
        {
            "found": bool,
            "section_text": str,        # raw text of section 6, for debugging
            "details": [                # one per variety, in document order
                {"slug": "grenache", "name": "Garnacha tinta", "colour": "noir"},
                ...
            ],
        }

    The caller decides principal vs accessory based on the documento único
    (which carries the official principal-variety designation in section 7);
    JCCM section 6 doesn't make that split.
    """
    span = find_variety_section(text)
    if span is None:
        return {"found": False, "section_text": "", "details": []}
    section_text = text[span[0] : span[1]].strip()
    stitched = _stitch_continuations(section_text)

    details: list[dict] = []
    seen: set[str] = set()
    current_colour = ""
    for raw_line in stitched.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Drop page-header / footer leaks ("Pliego de condiciones DOP …",
        # standalone page numbers) that survive the section-boundary
        # detection in narrow regional templates.
        if _PAGE_HEADER_RE.search(line):
            continue
        # Strip a leading letter/digit bullet ("a) ", "b. ") before any
        # other classification so "a) Variedades blancas" can be picked
        # up by the colour-line regex below.
        line = _LETTER_BULLET_PREFIX_RE.sub("", line)
        m_col = _COLOUR_LINE_RE.match(line)
        if m_col:
            current_colour = _COLOUR_TO_TAG.get(m_col.group(1).lower(), current_colour)
            payload = line[m_col.end():]
        else:
            payload = line
        # Pre-split the line on wide whitespace gaps so two-column
        # variety tables (montsant: blancas on the left, tintas on the
        # right separated by ~30+ spaces) yield separate variety chunks.
        # Each chunk is then split on the in-line connectors.
        chunks = _COLUMN_GAP_RE.split(payload)
        for raw_chunk in chunks:
            for entry in _entries_from_chunk(raw_chunk, current_colour):
                if entry["slug"] in seen:
                    continue
                seen.add(entry["slug"])
                details.append(entry)
    return {"found": True, "section_text": section_text, "details": details}


def _entries_from_chunk(chunk: str, colour: str) -> list[dict]:
    """Slice a chunk into variety tokens. Splits parenthetical synonyms
    out separately, then splits the bare text on commas, slashes, and
    the Spanish connectors ` y `, ` e `, ` o `."""
    chunk = re.sub(r"^\s*[•·]\s*", "", chunk).rstrip(" .,;:")
    if not chunk.strip():
        return []
    # Extract parenthetical synonyms ("Tempranillo (Cencibel)" → primary
    # "Tempranillo" + synonym "Cencibel"). Drop role-marker singletons
    # like "(A)" / "(R)" via the min-length 3 check downstream.
    paren_tokens = _PAREN_CONTENT_RE.findall(chunk)
    bare = _PAREN_CONTENT_RE.sub(" ", chunk).strip()
    # Strip any leading role label that survived the chunk split
    # (e.g. "Preferentes: Albillo Criollo" → "Albillo Criollo").
    bare = _ROLE_LABEL_RE.sub("", bare)
    # If there's still a `:` in the bare text, the prefix is a sub-heading
    # we don't recognise — keep only the part after the last colon.
    if ":" in bare:
        bare = bare.rsplit(":", 1)[1].strip()
    entries: list[dict] = []
    for source in [bare, *paren_tokens]:
        for tok in re.split(r"[,/]|\s+y\s+|\s+e\s+|\s+o\s+", source):
            entry = _normalise_token(tok, colour)
            if entry is None:
                continue
            entries.append(entry)
    return entries
