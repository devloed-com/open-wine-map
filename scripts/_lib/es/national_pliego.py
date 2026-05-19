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

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_LIB_ROOT = Path(__file__).resolve().parents[1]
if str(_LIB_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT.parent))
from _lib.grape_entity import match_variety  # noqa: E402
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS, slugify  # noqa: E402

_REPO_ROOT = _LIB_ROOT.parent.parent
# Sources for the "known variety" vocabulary used by the in-line typo
# splitter. The national-pliegos themselves are EXCLUDED — that's the
# corpus where the typos live; including it would let `malbec-cabernet-
# franc` survive as a "known" slug and block the split.
_KNOWN_SLUG_SOURCES = (
    _REPO_ROOT / "raw" / "inao" / "cahier-extracted",
    _REPO_ROOT / "raw" / "es" / "pliegos-extracted",
    _REPO_ROOT / "raw" / "pt" / "cadernos-extracted",
)

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

# Inline-allowed words that appear in legitimate variety names but are
# also in `_PROSE_LEAD` to catch sentence-leaks. Connectors `de`/`del`
# join the grape stem to a place qualifier (Ull *de* Llebre, Moscatel
# *de* Alejandría, Malvasía *de* Sitges). Colour adjectives `tinta` /
# `blanca` / `tinto` / `blanco` / `rosado` qualify the grape (Garnacha
# *tinta*, Garnacha *blanca*, Xarel.lo *rosado*) and ride through the
# alias / colour-suffix machinery downstream. They are still rejected
# when they open the token (which signals a colour-header leak).
_PROSE_LEAD_INLINE_ALLOWED = {
    "de", "del",
    "tinta", "tintas", "tinto", "tintos",
    "blanca", "blancas", "blanco", "blancos",
    "rosada", "rosadas", "rosado", "rosados",
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
# Suffix → colour it expresses. Used when collapsing a redundant colour
# suffix on a slug: strip only when the stem's `DEFAULT_COLOUR` matches
# the suffix's colour ("merlot noir" → "merlot" because Merlot is `noir`
# by default; but "garnacha blanca" → `grenache-blanc` stays because
# Grenache is `noir` by default and `-blanc` carries the colour shift).
_SUFFIX_TO_COLOUR = {
    "-blanc": "blanc", "-blanca": "blanc", "-blanco": "blanc",
    "-noir": "noir", "-negra": "noir", "-negro": "noir",
    "-tinta": "noir", "-tinto": "noir",
    "-gris": "gris",
    "-rosada": "rose", "-rosado": "rose",
}


def _grapes_in_record(rec: dict, slugs: set[str]) -> None:
    """Collect every variety slug a record exposes. Handles both shapes
    seen across FR / ES / PT extractors: top-level `grapes` as a
    dict-of-role-lists, top-level `grapes` as a flat list, and entries
    whose elements are either bare slugs or `{slug, name, ...}` dicts."""
    grapes = rec.get("grapes")
    if isinstance(grapes, dict):
        for role in ("principal", "accessory", "observation", "all"):
            for g in grapes.get(role) or []:
                if isinstance(g, str):
                    slugs.add(g)
                elif isinstance(g, dict) and isinstance(g.get("slug"), str):
                    slugs.add(g["slug"])
    elif isinstance(grapes, list):
        for g in grapes:
            if isinstance(g, str):
                slugs.add(g)
            elif isinstance(g, dict) and isinstance(g.get("slug"), str):
                slugs.add(g["slug"])


@lru_cache(maxsize=1)
def _raw_known_slugs() -> frozenset[str]:
    """Cross-corpus union of slugs from FR cahiers + ES EU-OJ pliegos +
    PT cadernos — the curated extractors. Each slug is GRAPE_ALIAS-
    folded so the splitter compares like-for-like with `_normalise_
    token`'s output."""
    raw: set[str] = set()
    for src in _KNOWN_SLUG_SOURCES:
        if not src.exists():
            continue
        for f in src.glob("*.json"):
            if f.name.startswith("_"):
                continue
            try:
                rec = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            _grapes_in_record(rec, raw)
    return frozenset(GRAPE_ALIAS.get(s, s) for s in raw)


def _next_vocab_piece(
    parts: list[str], i: int, vocab: frozenset[str], excluded: str,
) -> tuple[str | None, int]:
    """Longest prefix at `parts[i:]` that resolves into `vocab` (directly
    or via GRAPE_ALIAS), excluding `excluded` so a slug can never
    shield itself from decomposition. Returns `(piece, j)` so the caller
    advances to `parts[j:]`, or `(None, i)` on miss."""
    for j in range(min(len(parts), i + 4), i, -1):
        candidate = "-".join(parts[i:j])
        if candidate == excluded:
            continue
        if candidate in vocab or GRAPE_ALIAS.get(candidate, candidate) in vocab:
            return candidate, j
    return None, i


def _decomposes_into_known_with_alias(slug: str, vocab: frozenset[str]) -> bool:
    """True when `slug` greedily decomposes into 2+ pieces in `vocab` and
    at least one piece is a `GRAPE_ALIAS` source key. The alias-source
    requirement is what distinguishes a buggy concatenation
    (`tempranillo-cencibel` — "cencibel" is in GRAPE_ALIAS) from a
    legitimate composite (`cabernet-sauvignon` — neither part is in
    GRAPE_ALIAS)."""
    parts = slug.split("-")
    if len(parts) < 2:
        return False
    pieces: list[str] = []
    i = 0
    while i < len(parts):
        piece, j = _next_vocab_piece(parts, i, vocab, slug)
        if piece is None:
            return False
        pieces.append(piece)
        i = j
    return len(pieces) >= 2 and any(p in GRAPE_ALIAS for p in pieces)


@lru_cache(maxsize=1)
def _known_canonical_slugs() -> frozenset[str]:
    """Cross-corpus known slugs, with self-decomposable concatenation
    artifacts filtered out so the splitter doesn't get shielded by its
    own polluted corpus (`tempranillo-cencibel`, `aragonez-tinta-roriz`,
    …). A slug is dropped when it decomposes into 2+ known-vocabulary
    pieces with at least one alias-source piece — see
    `_decomposes_into_known_with_alias`."""
    raw = _raw_known_slugs()
    vocab = raw | frozenset(GRAPE_ALIAS.keys())
    return frozenset(s for s in raw if not _decomposes_into_known_with_alias(s, vocab))


def _longest_known_prefix(
    parts: list[str], i: int, known: frozenset[str], max_window: int,
) -> tuple[str | None, int]:
    """Longest prefix at `parts[i:]` that resolves to a slug in `known`.
    Returns `(canon_slug, j)` so the caller can advance to `parts[j:]`;
    returns `(None, i)` when no prefix matches."""
    for j in range(min(len(parts), i + max_window), i, -1):
        candidate = "-".join(parts[i:j])
        canon = GRAPE_ALIAS.get(candidate, candidate)
        if canon in known:
            return canon, j
    return None, i


def _split_concatenated(slug: str, max_window: int = 4) -> list[str]:
    """Greedy-decompose a slug into 2+ known canonical sub-slugs from
    left to right. The longest prefix that resolves into the known set
    wins at each step; if the whole slug can be covered by ≥ 2
    consecutive matches, return the split list, otherwise return `[slug]`
    unchanged. Catches in-line missing-comma typos like "Malbec
    Cabernet Franc" → `["malbec", "cabernet-franc"]` in the source
    pliegos (casa-del-blanco, lanzarote)."""
    known = _known_canonical_slugs()
    if slug in known:
        return [slug]
    parts = slug.split("-")
    if len(parts) < 2:
        return [slug]
    out: list[str] = []
    i = 0
    while i < len(parts):
        canon, j = _longest_known_prefix(parts, i, known, max_window)
        if canon is None:
            return [slug]
        out.append(canon)
        i = j
    return out if len(out) >= 2 else [slug]


def pdf_to_text(pdf_path: Path | str) -> str:
    """Render a PDF as layout-preserving text. Requires `pdftotext` on PATH."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


_TRAILING_CONNECTOR_CHECK_RE = re.compile(
    r"(?:,|\s+(?:y|o|e|u|y/o))$", re.IGNORECASE,
)


def _looks_like_wrap_continuation(prev: str) -> bool:
    """A `prev` line that *plausibly* wraps into the next is either:
      - trailing-connector wrap: prev ends with `,` / ` y` / ` o` / ` e`
        / ` u` / ` y/o` (mentrida, valdepeñas);
      - mid-name wrap inside a long comma-list: prev accumulates many
        commas AND is long enough that the variety-name probably got
        clipped at the right margin (calatayud's "…Monastrell, Syrah,
        Cabernet" → next line "Sauvignon y Merlot.").

    A short bullet-list entry with a single internal comma for a
    composite name like "Tempranillo, Ull de llebre" is NOT a wrap —
    each bullet line is an independent variety. Joining them produced
    spurious concatenated slugs (`samso-pinot-noir-syrah`,
    `garrut-trepat-mazuela`) in costers-del-segre."""
    stripped = prev.rstrip()
    if _TRAILING_CONNECTOR_CHECK_RE.search(stripped):
        return True
    body = prev.strip()
    if not body:
        return False
    comma_count = body.count(",")
    return comma_count >= 3 or (comma_count >= 1 and len(body) >= 60)


def _is_continuation_line(prev: str, is_colour_header: bool, is_bullet_item: bool) -> bool:
    """Decide whether to merge the current line into `prev`. Returns
    `False` when `prev` is empty, sentence-terminated, two-column tabular,
    or when the current line is itself a colour header / bulleted item —
    each is a fresh entry, not a wrap target."""
    if not prev or prev.endswith(".") or is_colour_header or is_bullet_item:
        return False
    # Wide-gap detection must look at the line *body*, not its leading
    # indent. JCCM pliegos indent bullet lines deeply ("       -   "),
    # which would otherwise be misread as a column boundary and block
    # continuation joins like `…Cabernet\nSauvignon y Merlot.`
    # (Calatayud, where the wrap split a single variety name into
    # two false slugs `cabernet` + `sauvignon`).
    prev_body = re.sub(r"^\s*[-•·*]?\s*", "", prev)
    if prev_body and _COLUMN_GAP_RE.search(prev_body):
        return False
    return _looks_like_wrap_continuation(prev)


def _stitch_continuations(text: str) -> str:
    """Join lines that continue a variety enumeration. Continuation
    requires that the previous line *looks like* a wrap point —
    `_looks_like_wrap_continuation`. Bullet-list lines (one variety
    per line, possibly with one internal comma for a composite name
    like "Tempranillo, Ull de llebre") are NOT continuations even if
    they contain a comma. JCCM wraps long lists at the right margin:

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
        prev = out[-1].rstrip() if out else ""
        if _is_continuation_line(prev, is_colour_header, is_bullet_item):
            out[-1] = out[-1].rstrip() + " " + s.lstrip()
        else:
            out.append(s)
    return "\n".join(out)


def _normalise_token(name: str, ambient_colour: str) -> dict | None:
    """Pre-clean a candidate variety token (bullet / role-label / trailing-
    connector strip, structural-noise drop) and hand off to the vocab
    matcher. Returns `{slug, name, colour}` on match, `None` otherwise.
    Unmatched tokens land in the curator queue via `match_variety`."""
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
    result = match_variety(name, ambient_colour=ambient_colour or None)
    if result is None:
        return None
    return {"slug": result.slug, "name": result.name.lower(), "colour": result.colour}


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


def _emit_entry(entry: dict, seen: set[str], details: list[dict]) -> None:
    """Append `entry` to `details`, expanding any concatenated-typo slug
    via `_split_concatenated` and skipping anything already seen. Each
    decomposed sub-slug rides the original entry's colour."""
    for sub in _split_concatenated(entry["slug"]):
        if sub in seen:
            continue
        seen.add(sub)
        if sub == entry["slug"]:
            details.append(entry)
        else:
            details.append({
                "slug": sub,
                "name": sub.replace("-", " "),
                "colour": entry["colour"],
            })


def _process_variety_line(
    raw_line: str, current_colour: str, seen: set[str], details: list[dict],
) -> str:
    """Tokenise one stitched line into variety entries (with column-gap
    pre-split + chunk splitting + typo-decomposition) and append them
    to `details`. Returns the updated `current_colour` so the caller's
    rolling state survives across lines."""
    line = raw_line.strip()
    if not line or _PAGE_HEADER_RE.search(line):
        return current_colour
    line = _LETTER_BULLET_PREFIX_RE.sub("", line)
    m_col = _COLOUR_LINE_RE.match(line)
    if m_col:
        current_colour = _COLOUR_TO_TAG.get(m_col.group(1).lower(), current_colour)
        payload = line[m_col.end():]
    else:
        payload = line
    for raw_chunk in _COLUMN_GAP_RE.split(payload):
        for entry in _entries_from_chunk(raw_chunk, current_colour):
            _emit_entry(entry, seen, details)
    return current_colour


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
        current_colour = _process_variety_line(raw_line, current_colour, seen, details)
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
