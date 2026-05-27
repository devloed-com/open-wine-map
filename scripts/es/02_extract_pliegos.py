"""Extract structured fields from each cached EUR-Lex single-document HTML.

Pipeline stage 02 (es).

For each Spanish wine GI in `raw/es/eambrosia/index.json`:
  - if a cached HTML exists at `raw/es/oj-pages/<slug>.html`, parse the
    "DOCUMENTO ÚNICO" block into numbered sections (the EU 2024 wine GI
    template — sections 1..10 in the Spanish-language variant)
  - else emit a stub record so the wine remains searchable
  - run subzona extraction on the brief geographical-area section and
    emit one child record (`is_sub_denomination=True`) per detected subzona, mirroring
    the FR DGC pattern. See `scripts/_lib/es/subzona.py` for the patterns.

Output: one JSON per wine under `raw/es/pliegos-extracted/<slug>.json`,
plus a `_index.json` mapping slug → metadata (mirrors the FR `_index.json`
shape so stage 04 can iterate uniformly).

The EU 2024 wine GI single-document template (in Spanish):

  1. Nombre(s)                          — name
  2. Tipo de indicación geográfica      — kind (DOP / IGP)
  3. País / clasificación               — country + CN code
  4. ...
  5. Categorías de productos vitivinícolas
  6. Descripción del vino o vinos       — per wine type
  7. Prácticas vitivinícolas
     7.1. Prácticas enológicas
     7.2. Rendimientos máximos
  8. Variedad o variedades de uva       — grape varieties
  9. Definición breve de la zona        — brief geographical area
  10. Vínculo con la zona geográfica    — link to terroir (Phase 5 input)
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.es.subzona import extract_subzonas, slugify as _subzona_slug  # noqa: E402
from _lib.es.national_pliego import _split_concatenated  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)
from _lib.grape_lexicon import (  # noqa: E402
    DEFAULT_COLOUR, GRAPE_ALIAS, GRAPE_BLOCKLIST, slugify as _grape_slug,
)

INDEX_IN = ROOT / "raw" / "es" / "eambrosia" / "index.json"
OJ_DIR = ROOT / "raw" / "es" / "oj-pages"
OJ_MANIFEST = OJ_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "es" / "pliegos-extracted"
INDEX_OUT = OUT_DIR / "_index.json"


def strip_tags(html: str) -> str:
    """Drop tags, decode HTML entities, collapse whitespace. Preserves
    paragraph breaks via `\\n` between block-level elements so a downstream
    consumer can detect them."""
    # Insert newlines before block-ish tags so paragraphs separate cleanly.
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    # Drop everything else.
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    # Collapse non-newline whitespace runs, preserve newlines.
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


# Section headers in the single document are paragraphs with class
# `ti-grseq-1` (older EUR-Lex template, sections numbered 1..9) or
# `oj-ti-grseq-1` (newer template, sections 1..10/11). Both are matched
# by the same regex; semantic role routing happens in route_sections().
SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


def find_section_offsets(html: str) -> list[tuple[str, str, int, int]]:
    """Returns [(section_num, title, header_start, header_end)] in document
    order. Only headers whose plaintext starts with a numeric prefix are
    returned — bare-text oj-ti-grseq-1 paragraphs (sub-headings like
    "Producto vitivinícola" without numbering) are skipped."""
    out: list[tuple[str, str, int, int]] = []
    for m in SECTION_HEADER_RE.finditer(html):
        plaintext = re.sub(r"\s+", " ", strip_tags(m.group(1))).strip()
        nm = SECTION_NUM_RE.match(plaintext)
        if not nm:
            continue
        out.append((nm.group(1), nm.group(2).strip(), m.start(), m.end()))
    return out


# Spanish-national-format section header regex. Matches lines that start with
# a digit (1–99 with optional `.subnumber`), then `.` or `)`, then whitespace,
# then an uppercase Spanish heading. Curator-supplied MAPA pliegos almost all
# use this layout — sections like:
#   "1. NOMBRE QUE SE DEBE PROTEGER"        (Bullas)
#   "1. DENOMINACIÓN QUE DEBE PROTEGERSE."  (Pago de Otazu — trailing period)
#   "  4. DEMARCACIÓN DE LA ZONA GEOGRÁFICA"
#   "    1. NOMBRE Y TIPO"                   (Costa de Cantabria — EU 2024 too)
# Mixed-case headings ("1. Nombre que se debe proteger") also match because
# `[A-ZÁÉÍÓÚÑÜ]` only constrains the first letter; trailing `:` or `.` is
# tolerated via the optional `[:.]?` before `$`.
# Three section-prefix layouts seen across the Spanish corpus:
#   - digit-prefixed (1, 2, 7.1, …)         — most pliegos, plus EU 2024
#   - uppercase letter (A, B, B.1, …)        — Andalucía IGPs (Bailén etc.)
#   - lowercase letter (a, b, b.1, …)        — Pago pliegos (Dominio de Valdepusa)
# After the number/letter: `.` or `)`, then optional dashes/whitespace, then an
# uppercase Spanish heading. The sub-regex shape is identical across the three;
# the alternatives differ only in the prefix character class.
_HEAD_TAIL = r"[\.\)][\s\-–—]+([A-ZÁÉÍÓÚÑÜ][^\n]{4,80}?)\s*[:.]?\s*$"
PDF_DIGIT_RE = re.compile(rf"^[ \t]*(\d{{1,2}}(?:\.\d+)*){_HEAD_TAIL}", re.MULTILINE)
PDF_UPPER_RE = re.compile(rf"^[ \t]*([A-Z](?:\.\d+)*){_HEAD_TAIL}", re.MULTILINE)
PDF_LOWER_RE = re.compile(rf"^[ \t]*([a-z](?:\.\d+)*){_HEAD_TAIL}", re.MULTILINE)


_PDF_INTRA_LINE_WS_RE = re.compile(r"(\S) {2,}")


def pdftotext(pdf_path: Path) -> str:
    """Run `pdftotext -layout` and return the plaintext. Layout mode preserves
    column structure well enough for tabular data (analytical characteristics
    tables) and keeps section headers on their own line.

    Two cleanups before returning: drop `\\x0c` page-break markers (they
    prepend the first heading on a new page and prevent `^[ \\t]*` from
    matching) and collapse intra-line runs of 2+ spaces to a single space
    so column-aligned headings like
    `G)  EXPLICACIÓN            DETALLADA         DEL     VINCULO` stay
    under the 80-char limit of `_HEAD_TAIL`. Leading whitespace is
    preserved (the regex requires a non-space char before the run) so
    `_stitch_lines` can still use indent for continuation detection."""
    raw = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return _PDF_INTRA_LINE_WS_RE.sub(r"\1 ", raw.replace("\x0c", ""))


def extract_sections_from_pdf_text(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice plaintext (from pdftotext -layout) into numbered sections.

    Mirrors `extract_sections` (which operates on HTML) so route_sections
    works uniformly. Sub-section bodies (e.g. `7.1`, `7.2`) are kept as
    separate entries; route_sections' `_gather_subsections` helper backfills
    the parent if it ends up empty.

    Precedence dispatch on prefix style — digit > uppercase letter > lowercase
    letter. Picking the first regex that finds matches avoids over-matching
    subsections-as-sections in pliegos that mix layers (e.g. Bullas's
    digit-prefixed top-level sections with `a) Características` subsections
    inside section 2 — without the precedence rule, lowercase `a)` would
    split section 2's body)."""
    for regex in (PDF_DIGIT_RE, PDF_UPPER_RE, PDF_LOWER_RE):
        matches = list(regex.finditer(text))
        if matches:
            break
    else:
        return {}, {}
    # Dedupe BEFORE computing body boundaries. Spanish national-format pliegos
    # routinely use enumeration markers like `1.- La zona de producción...`
    # *inside* a section's body — those match the section-header regex too.
    # Without dedup, body boundaries land on subsections (section 4 truncates
    # to zero because the next match is `1.-` immediately after its header).
    #
    # When multiple matches share a number, prefer the one whose heading text
    # is most uppercase — real top-level section titles in the Spanish corpus
    # are almost always ALL CAPS (`2. DESCRIPCIÓN DEL VINO`), while
    # enumeration markers carry sentence-case content (`2.- El término
    # tradicionalmente utilizado…`). When all candidates have similar case
    # mix (e.g. Mondéjar-style sentence-case top-level), the first-occurrence
    # wins by tiebreaker.
    def _heading_score(title: str) -> int:
        letters = [c for c in title if c.isalpha()]
        if not letters:
            return 0
        return int(100 * sum(1 for c in letters if c.isupper()) / len(letters))

    best: dict[str, tuple[int, re.Match[str]]] = {}
    for m in matches:
        num = m.group(1)
        score = _heading_score(m.group(2))
        if num not in best or score > best[num][0]:
            best[num] = (score, m)
    deduped = sorted((m for _, m in best.values()), key=lambda m: m.start())
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(deduped):
        num = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(".:")
        start = m.end()
        end = deduped[i + 1].start() if i + 1 < len(deduped) else len(text)
        bodies[num] = text[start:end].strip()
        titles[num] = title
    return bodies, titles


# The "DOCUMENTO ÚNICO" anchor inside the EUR-Lex page. The block above it
# is the modification-cover (sections 1–N of the modification template); we
# only want the single-document side. Match the *heading paragraph*
# specifically — a bare `re.search(r"DOCUMENTO\s+ÚNICO")` also matches
# prose mentions like "No se modifica el documento único" that pepper the
# modification cover, slicing the document too early and leaking 2.x / 10+
# cover sections into `extract_sections`.
DOC_UNICO_ANCHOR_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>\s*DOCUMENTO\s+ÚNICO\s*</p>',
    re.I | re.S,
)


def slice_documento_unico(html: str) -> str | None:
    """Return the HTML substring from the DOCUMENTO ÚNICO anchor to the end
    of the article body, or None if the anchor isn't present (means the
    page wasn't a single-document publication and stage 01 should not have
    cached it — but the looks_like_single_document filter lets some edge
    cases through)."""
    m = DOC_UNICO_ANCHOR_RE.search(html)
    if not m:
        return None
    return html[m.start():]


def extract_sections(html: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice the single document into top-level numeric sections.

    Returns (bodies, titles) keyed by section number string ("1", "2", ...,
    "7.1", "7.2", ...). Top-level sections collect their own body PLUS any
    nested sub-sections so consumers that look up `sections["7"]` get the
    whole 7.x block.
    """
    headers = find_section_offsets(html)
    if not headers:
        return {}, {}
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, _hstart, hend) in enumerate(headers):
        end = headers[i + 1][2] if i + 1 < len(headers) else len(html)
        bodies[num] = strip_tags(html[hend:end]).strip()
        titles[num] = title
    return bodies, titles


# ES pliegos list grape varieties in two shapes:
#  - newer "documento único" template: one variety per line, with synonyms
#    embedded as " - " separators ("MAZUELA - CARIÑENA", "MACABEO - VIURA")
#  - older / narrative pliegos: comma-separated within colour-and-role
#    groups, synonyms joined by " o " ("Bermejuela o Marmajuelo")
# Role markers ("Preferentes:" / "Autorizadas:") and colour-group headers
# ("Variedades de uvas blancas:" / "Variedades tintas:") subdivide the
# section. The parser walks line-by-line so it works for both templates.

_ROLE_HEADER_RE = re.compile(
    r"^\s*-?\s*(preferentes?|principales?|permitidas?|recomendadas?|autorizadas?|accesorias?|complementarias?)\s*:?\s*$|"
    r"^\s*-?\s*(preferentes?|principales?|permitidas?|recomendadas?|autorizadas?|accesorias?|complementarias?)\s*:\s*",
    re.IGNORECASE,
)
_INLINE_ROLE_RE = re.compile(
    r"\b(preferentes?|principales?|permitidas?|recomendadas?|autorizadas?|accesorias?|complementarias?)\s*:\s*",
    re.IGNORECASE,
)
_COLOUR_HEADER_RE = re.compile(
    # Long form ("Variedades de uvas blancas:") or bare colour header
    # ("Blancas:" / "Tintas:"). The long form must sit after a sentence
    # terminator (start-of-line, `:`, `;`, `.`, newline) so we don't
    # match colour adjectives mid-sentence ("Ondarrabi Zuri como variedad
    # blanca" in the Getariako Txakolina narrative used to chop the line
    # mid-token). Tolerated ordinal prefixes between the terminator and
    # "Variedades": "a." / "a)" / "1." / "1)" / bare digit (the bare digit
    # absorbs page-footer remnants like "-2Variedades" left after the
    # hyphen-linebreak collapser eats `-2-\n` mid-section).
    r"(?:^|[:;\n.])\s*(?:[a-z][.)]\s+|\d+[.)]?\s*)?"
    r"variedades?\s+(?:de\s+uvas?\s+)?(tinta|blanca|negra|rosa)s?\b|"
    r"^\s*(tinta|blanca|negra|rosada)s?\b\s*:",
    re.IGNORECASE,
)
# Trailing colour qualifier — narrative pliegos sometimes annotate each
# variety inline ("Ondarrabi Zuri como variedad blanca y Ondarrabi
# Beltza como variedad tinta" in Getariako Txakolina section 6). Strip
# the connector while preserving the colour so it flows into the slug.
_COMO_VARIEDAD_RE = re.compile(
    r"\s+como\s+variedad(?:es)?\s+(tinta|blanca|negra|rosada|tintorera)\s*$",
    re.IGNORECASE,
)
_COLOUR_SUFFIX_RE = re.compile(
    r"\s+(tinta|blanca|negra|tintorera|rosada|gris)\s*$",
    re.IGNORECASE,
)
_ROLE_BY_KEYWORD = {
    "preferent": "principal",
    "principal": "principal",
    "permitida": "principal",
    "recomendad": "principal",
    "autorizada": "accessory",
    "accesoria": "accessory",
    "complementaria": "accessory",
}
_COLOUR_BY_KEYWORD = {
    "tinta": "noir",
    "negra": "noir",
    "tintorera": "noir",
    "blanca": "blanc",
    "rosada": "rose",
    "rosa": "rose",
    "gris": "gris",
}
_GRAPE_DROP_TOKENS = {
    "variedad", "variedades", "varietal", "varietales",
    "principal", "principales", "preferentes", "preferente",
    "autorizada", "autorizadas", "accesoria", "accesorias",
    "complementaria", "complementarias", "permitidas",
    "recomendada", "recomendadas",
    "tinta", "tintas", "blanca", "blancas", "negra", "negras",
    "rosada", "rosadas", "rosa", "rosas",
    "vino", "vinos", "uva", "uvas", "tipo", "tipos",
    "elaboración", "elaboracion", "vinificación", "vinificacion",
}
# Connector words that pad multi-word header phrases ("variedades de
# uva"). When *every* word in a candidate token is a drop-token or one
# of these connectors, the candidate is a section heading, not a name.
_GRAPE_HEADER_STOPWORDS = {"de", "del", "la", "las", "el", "los"}

# Function words that betray prose fragments — when present in a candidate
# grape token they mark sentence material, not a variety name.
_GRAPE_PROSE_MARKERS = {
    "es", "son", "que", "se", "el", "los", "las", "una", "esta",
    "su", "del", "como", "con", "por", "para", "sin", "ha", "han", "hay",
    "este", "estos", "estas", "siguientes", "siguiente",
    "exclusivamente", "denominados", "denominado", "denomina",
    "menciones", "nombre", "decir", "asimismo",
    # "en" appears in narrative recommendation paragraphs (Betanzos:
    # "Agudelo en blancas y Mencía en tintas") that pad the variety
    # section. No real grape name contains "en" as a token.
    "en",
}

# Some narrative pliegos add a "Pe- / dro Ximénez" hyphen-line-break.
# Stitch those back before splitting.
_HYPHEN_LINEBREAK_RE = re.compile(r"-\s*\n\s*", re.MULTILINE)


_PAREN_SYNONYM_RE = re.compile(r"\s*\(([^)]+)\)\s*")
# Unbalanced-paren cleanup for column-split fragments where pdftotext
# drops either the opening or closing paren on a line break:
#   "(Loureira blanco"  → bare "" + synonym "Loureira blanco"
#   "Marqués)"          → bare "Marqués"
# Captures everything after a lone `(` and strips a lone trailing `)`.
_OPEN_PAREN_TAIL_RE = re.compile(r"\(([^()]*)$")
_BARE_TRAILING_PAREN_RE = re.compile(r"\)\s*$")

# Role / colour sub-section labels followed by a colon ("uva tinta:",
# "uvas blancas:", "variedad principal:", "sinónimos:"). The line-level
# header regex doesn't match these compact forms when they appear
# mid-line, so we strip them off the leading edge of each token.
_LEADING_COLON_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"(?:uvas?\s+)?(?:tinta|blanca|negra|rosada|rosa)s?"
    r"|variedad(?:es)?(?:\s+(?:principal|secundaria|preferente|autorizada|tradicional|recomendada|complementaria|minoritaria|mayoritaria|accesoria)s?)?"
    r"|sin[oó]nimos?|sin\.?"
    r"|principal(?:es)?|secundarias?|preferentes?|autorizadas?|recomendadas?"
    r"|tradicionales?|complementarias?|minoritarias?|mayoritarias?|accesorias?"
    r")\s*\.?\s*:\s*",
    re.IGNORECASE,
)


def _split_synonym_group(token: str) -> list[str]:
    """Return [primary, *synonyms] from a single grape token. Splits on
    ' - ' (newer template), ' o ' / ' u ' (older narrative), '/' (Basque
    Txakoli / Galician templates), and parenthesised aliases like
    `Chenín blanco (Agudelo)` (Betanzos), `Albarín blanco (Branco
    lexítimo)` (Betanzos). Tolerates an unbalanced opening paren left by
    a column-split fragment. Preserves the primary name's position so
    callers can prefer it for display."""
    paren_synonyms = _PAREN_SYNONYM_RE.findall(token)
    bare = _PAREN_SYNONYM_RE.sub(" ", token).strip()
    open_tail = _OPEN_PAREN_TAIL_RE.search(bare)
    if open_tail:
        paren_synonyms.append(open_tail.group(1))
        bare = bare[: open_tail.start()].rstrip()
    bare = _BARE_TRAILING_PAREN_RE.sub("", bare).rstrip()
    # Accept hyphen-minus, en-dash, em-dash, and the spacy bullet forms used
    # by recent pliegos ("Tempranillo — Tinto fino", "Macabeo – Viura").
    parts = re.split(r"\s+[-–—]\s+|\s+o\s+|\s+u\s+|\s*/\s*", bare, flags=re.IGNORECASE)
    parts.extend(paren_synonyms)
    return [p.strip(" .,;:") for p in parts if p.strip(" .,;:")]


_LEADING_CONNECTOR_RE = re.compile(r"^(?:y/o|y|o|u|e|et|i)\s+", re.IGNORECASE)
_TRAILING_CONNECTOR_RE = re.compile(r"\s+(?:y/o|y|o|u|e|et|i)$", re.IGNORECASE)
# Footnote markers `[1]` / `[2]` etc. appear right after a variety name in
# Andalusian pliegos that introduce new varieties as "modificación de menor
# importancia" — e.g. `Petit Verdot. [1]`. Without stripping them, the
# digit-check rejects the whole token.
_FOOTNOTE_MARKER_RE = re.compile(r"\[\d+\]")


def _normalise_grape_entry(name: str, ambient_colour: str | None) -> dict | None:
    """Pre-clean a variety token (footnote/colon-label/connector strip,
    structural-noise drop) and hand off to the vocab matcher. Returns
    `{slug, name, colour}` on match, `None` otherwise. Unmatched tokens
    land in the curator queue via `match_variety`."""
    name = name.strip().strip("«»\"'·")
    name = _FOOTNOTE_MARKER_RE.sub("", name).strip()
    name = _LEADING_COLON_LABEL_RE.sub("", name)
    name = _LEADING_CONNECTOR_RE.sub("", name)
    name = _TRAILING_CONNECTOR_RE.sub("", name)
    name = name.strip(" .,;:()")
    m_como = _COMO_VARIEDAD_RE.search(name)
    if m_como:
        cq = _COLOUR_BY_KEYWORD.get(m_como.group(1).lower())
        if cq:
            ambient_colour = cq
        name = name[: m_como.start()].rstrip(" .,;:()")
    if not name or len(name) < 3 or len(name) > 60:
        return None
    if any(c.isdigit() for c in name):
        return None
    if name.lower() in _GRAPE_DROP_TOKENS:
        return None

    words = name.split()
    if not words or len(words) > 4:
        return None
    if all(w.lower() in _GRAPE_DROP_TOKENS or w.lower() in _GRAPE_HEADER_STOPWORDS
           for w in words):
        return None
    # Varieties are proper nouns — the first character must be a letter
    # AND uppercase. Rejects "son los vinos", "y vijariego negro" after
    # the leading-connector strip already failed, lowercase prose, etc.
    first = words[0]
    if not first[0].isalpha() or not first[0].isupper():
        return None

    result = match_variety(name, ambient_colour=ambient_colour or None)
    if result is None or result.slug in GRAPE_BLOCKLIST:
        return None
    return {"slug": result.slug, "name": result.name.lower(), "colour": result.colour}


_HEADER_LINE_RE = re.compile(
    r"^[-•·*]|"
    r"^(?:preferent|principal|permitid|recomendad|autorizad|accesori|complementari)|"
    r"^[a-z]\.\s|"           # "a. Variedades de uvas blancas"
    r"^\d+\.\s|"             # "1. La elaboración..."
    r"variedades?\s+(?:de\s+uvas?\s+)?(?:tinta|blanca|negra|rosa)s?\b",
    re.IGNORECASE,
)


_PDF_PAGE_FOOTER_RE = re.compile(r"^\s*-\s*\d+\s*-\s*$")


def _stitch_lines(text: str) -> list[str]:
    """Join continuation lines into their predecessor so multi-line variety
    enumerations parse correctly. Two continuation signals:

      1. Indentation: line indent > predecessor's. Narrative pliegos
         indent continuation lines under the role-header bullet.
      2. List-mode (pdf-extracted national pliegos): predecessor contains
         a comma and doesn't end with a sentence terminator — a soft line
         break inside a comma-separated list (e.g. `… Vijariego, Pedro\n
         Ximénez, Moscatel …` in Laujar-Alpujarra). Without this, the
         break splits a single variety name (`Pedro Ximénez`) into two
         bogus entries.

    Pliegos that put one variety per non-indented line (Priorat, Montsant)
    stay split because their lines contain no comma. PDF page-footer
    markers like ` -2- ` are dropped before stitching."""
    out: list[str] = []
    prev_indent = 0
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or _PDF_PAGE_FOOTER_RE.match(stripped):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        is_header = bool(_HEADER_LINE_RE.match(stripped))
        is_indent_continuation = bool(out) and indent > prev_indent and not is_header
        prev = out[-1] if out else ""
        is_list_continuation = (
            bool(out) and not is_header
            and "," in prev and not prev.rstrip().endswith((".", ";"))
        )
        if is_indent_continuation or is_list_continuation:
            out[-1] = (prev + " " + stripped).strip()
        else:
            out.append(stripped)
            prev_indent = indent
    return out


def _emit_grape_with_split(
    entry: dict, role: str, seen_slugs: set[str], details: list[dict],
) -> None:
    """Append `entry` to `details` after greedy-decomposing any typo-glued
    slug (e.g. `tempranillo-cencibel`, `pinot-noir-mazuela`) into known
    canonical sub-slugs via `_split_concatenated`. Reuses the helper added
    for the national-pliego parser — same vocabulary, same decomposition
    rules — so both ES extractor paths share one fix."""
    for sub in _split_concatenated(entry["slug"]):
        if sub in seen_slugs:
            continue
        seen_slugs.add(sub)
        if sub == entry["slug"]:
            entry["role"] = role
            details.append(entry)
        else:
            details.append({
                "slug": sub,
                "name": sub.replace("-", " "),
                "colour": entry["colour"],
                "role": role,
            })


def parse_grapes(section_text: str) -> dict:
    """Extract `{principal, accessory, observation, details}` from the ES
    pliego's variety section. Output shape matches FR (see
    scripts/_lib/grape_lexicon.parse_grapes) so stage 04 needs no
    country-specific branching.

    Strategy: walk line-by-line. A role header ("Preferentes:" / "Autorizadas:")
    flips the current role bucket; a colour header ("Variedades tintas:") sets
    the ambient colour. Within each line, top-level separators (`,`, `;`,
    ` y `) split varieties; ` - ` and ` o ` inside one variety token mark
    regional synonyms (collapsed to one canonical slug via GRAPE_ALIAS).
    """
    if not section_text or not section_text.strip():
        return {"principal": [], "accessory": [], "observation": [], "details": []}

    text = _HYPHEN_LINEBREAK_RE.sub("", section_text)
    # pdftotext sometimes emits Wingdings-style bullets as Private Use Area
    # glyphs (e.g. U+F0B7 in Somontano). Normalise them to a comma so the
    # downstream token splitter treats them as variety separators rather
    # than concatenating "tempranillo. <PUA> blancas: alcañón" into one
    # bogus token.
    text = re.sub(r"[-]+", ",", text)
    role = "principal"
    ambient_colour: str | None = None
    details: list[dict] = []
    seen_slugs: set[str] = set()

    for raw_line in _stitch_lines(text):
        line = raw_line.strip().strip("-•·").strip()
        if not line:
            continue

        # Colour header — sets ambient for subsequent variety tokens.
        m_col = _COLOUR_HEADER_RE.search(line)
        if m_col:
            colour_kw = (m_col.group(1) or m_col.group(2) or "").lower()
            ambient_colour = _COLOUR_BY_KEYWORD.get(colour_kw)
            after = line[m_col.end():].lstrip(" :")
            if not after:
                continue
            line = after  # process inline grapes that follow the header

        # Role header — flips current bucket; consume the rest of the line.
        m_role = _ROLE_HEADER_RE.match(line)
        if m_role:
            kw = (m_role.group(1) or m_role.group(2) or "").lower()
            for k, v in _ROLE_BY_KEYWORD.items():
                if kw.startswith(k):
                    role = v
                    break
            line = line[m_role.end():].lstrip(" :")
            if not line:
                continue

        # Inline role marker mid-line ("Preferentes: A, B. Autorizadas: C, D").
        for m in _INLINE_ROLE_RE.finditer(line):
            pass  # split below

        segments = _INLINE_ROLE_RE.split(line)
        # _INLINE_ROLE_RE.split returns alternating [text, role_kw, text, role_kw, …]
        # when the regex has a capture group. Walk pairs.
        i = 0
        while i < len(segments):
            seg = segments[i] or ""
            if i > 0:
                # The element at i-1 was the role keyword that introduced this seg.
                kw = (segments[i - 1] or "").lower()
                for k, v in _ROLE_BY_KEYWORD.items():
                    if kw.startswith(k):
                        role = v
                        break

            for tok in re.split(r"[,;]|\s+y\s+", seg):
                tok = tok.strip(" .:")
                if not tok:
                    continue
                for synonym in _split_synonym_group(tok):
                    entry = _normalise_grape_entry(synonym, ambient_colour)
                    if entry is None:
                        continue
                    _emit_grape_with_split(entry, role, seen_slugs, details)
                    # Subsequent synonyms inside the same token alias onto
                    # the same canonical slug; the dedup loop swallows them.
            i += 2

    return {
        "principal":   [e["slug"] for e in details if e["role"] == "principal"],
        "accessory":   [e["slug"] for e in details if e["role"] == "accessory"],
        "observation": [e["slug"] for e in details if e["role"] == "observation"],
        "details":     details,
    }


# ----- ES style detection -----------------------------------------------
#
# Section titles 3..6 in the single document each describe one wine
# category produced under the GI ("VINO TINTO", "VINO DE LICOR", "VINO
# DE AGUJA"). Body text under sections 3/4/8 also names rancio / mistela
# / dulce-natural / sherry sub-styles when they apply. We harvest both.
# Slug taxonomy lives in scripts/_lib/style_taxonomy.

_STYLE_TITLE_PATTERNS: tuple[tuple[re.Pattern, tuple[str, ...]], ...] = (
    # Carbonation
    (re.compile(r"\bvino(?:s)? espumoso(?:s)? de calidad\b", re.I),
        ("sparkling", "sparkling-quality")),
    (re.compile(r"\bvino(?:s)? espumoso(?:s)?\b", re.I), ("sparkling",)),
    (re.compile(r"\bvino(?:s)? de aguja\b", re.I), ("sparkling", "semi-sparkling")),
    # Sweet / fortified categories (EU OJ product categories)
    (re.compile(r"\bvinos? generosos? de licor\b", re.I),
        ("sweet", "fortified", "vin-de-liqueur", "oxidative", "generoso")),
    (re.compile(r"\bvinos? de licor\b", re.I), ("sweet", "fortified", "vin-de-liqueur")),
    (re.compile(r"\bvinos? generosos?\b", re.I), ("oxidative", "generoso")),
    (re.compile(r"\bvinos? de uvas? sobremadur", re.I),
        ("sweet", "late-harvest", "uvas-sobremaduradas")),
    (re.compile(r"\bvinos? de uvas? pasificad", re.I),
        ("sweet", "raisin-wine", "uvas-pasificadas")),
    # Colour
    (re.compile(r"\bvino(?:s)? tinto(?:s)?\b", re.I), ("red",)),
    (re.compile(r"\bvino(?:s)? blanco(?:s)?\b", re.I), ("white",)),
    (re.compile(r"\bvino(?:s)? rosado(?:s)?\b", re.I), ("rose",)),
)

_STYLE_BODY_PATTERNS: tuple[tuple[re.Pattern, tuple[str, ...]], ...] = (
    (re.compile(r"\bvinos? rancios?\b", re.I), ("oxidative", "rancio")),
    (re.compile(r"\bnaturalmente dulce|dulces? naturales?\b", re.I),
        ("sweet", "dulce-natural")),
    (re.compile(r"\bmistelas?\b", re.I), ("sweet", "fortified", "mistela")),
)

# Sherry sub-styles are gated on the document being a "vinos generosos"
# pliego — otherwise we false-positive on the Spanish adjective "fino"
# (= elegant), on "Tinto Fino" the Tempranillo synonym, and on common
# tasting-note words like "oloroso" (= fragrant).
_SHERRY_GATE = re.compile(r"\bvinos? generosos?\b", re.I)
_SHERRY_SUBSTYLE_PATTERNS: tuple[tuple[re.Pattern, tuple[str, ...]], ...] = (
    (re.compile(r"\bfino\b", re.I), ("oxidative", "generoso", "fino")),
    (re.compile(r"\bmanzanilla\b", re.I), ("oxidative", "generoso", "manzanilla")),
    (re.compile(r"\bamontillado\b", re.I), ("oxidative", "generoso", "amontillado")),
    (re.compile(r"\boloroso\b", re.I), ("oxidative", "generoso", "oloroso")),
    (re.compile(r"\bpalo cortado\b", re.I), ("oxidative", "generoso", "palo-cortado")),
)

# Colour-list regex catches bare-adjective enumerations of wine colours
# ("blancos, rosados, tintos", "Blanco/Rosado", "tinto y rosado",
# "(BLANCO, ROSADO Y TINTO)"). Masculine plural form excludes feminine
# grape descriptors ("variedades blancas", "uvas tintas"). Separator
# must be comma, slash, or the word "y" — adjacent words alone do not
# qualify.
_COLOUR_TOKEN_RE = re.compile(r"\b(tintos?|blancos?|rosados?)\b", re.I)
_COLOUR_LIST_RE = re.compile(
    r"\b(?:tintos?|blancos?|rosados?)\b"
    r"(?:\s*(?:[,/;]|\by\b)\s*"
    r"\b(?:tintos?|blancos?|rosados?)\b)+",
    re.I,
)
# Single-colour section title suffix ("Rías Baixas Tinto"). Masculine
# form only; feminine grape titles like "VARIEDADES BLANCAS" don't match.
_TITLE_COLOUR_TAIL_RE = re.compile(
    r"\b(tintos?|blancos?|rosados?)\s*$", re.I,
)
# EU 2024 template: each wine type is introduced by "Producto
# vitivinícola\n<descriptor>". When the descriptor is a single colour
# adjective (Monterrei: just "Blanco") the colour-list regex misses it.
_PRODUCTO_VITIVINICOLA_COLOUR_RE = re.compile(
    r"Producto\s+vitivinícola\s*\n\s*(?:Vinos?\s+)?"
    r"(Tintos?|Blancos?|Rosados?)\b",
    re.I,
)
# "Los vinos serán tintos secos" / "los vinos de licor tintos" — the
# Spanish-national template often inserts 1–2 modifier words between
# "vinos" and the colour adjective. Masculine plural keeps grape
# descriptors out.
_VINOS_FLEX_COLOUR_RE = re.compile(
    r"\bvinos?\s+(?:[\wáéíóúñ]+\s+){1,2}(tintos?|blancos?|rosados?)\b",
    re.I,
)
# Tabular column header: three masculine-plural colour adjectives in a
# row, separated only by whitespace. Three-in-a-row is unambiguous wine
# context (Serra de Tramuntana section 1: "Blanco Rosado Tinto" header).
_THREE_COLOUR_WS_RE = re.compile(
    r"\b(tintos?|blancos?|rosados?)\s+"
    r"(tintos?|blancos?|rosados?)\s+"
    r"(tintos?|blancos?|rosados?)\b",
    re.I,
)
# Wine-type heading at line start, e.g. "Tinto tempranillo:" (Pago
# Florentino), "Blancos:", "Rosados jóvenes:". Up to two trailing words
# before the colon. Masculine form only. The leading boundary also
# accepts `:` and `;` so inline parameter rows ("Visual: blancos:
# amarillo a dorado: tintos: …", Alicante) and clause separators
# ("blancos y rosados; Tintos:") count as line-equivalent starts.
_LINE_START_COLOUR_HEADER_RE = re.compile(
    r"(?:^|[\n:;])\s*(tintos?|blancos?|rosados?)(?:\s+\w+){0,2}\s*:",
    re.I,
)
_COLOUR_SLUGS = {"tinto": "red", "blanco": "white", "rosado": "rose"}


def _colour_slug(token: str) -> str | None:
    return _COLOUR_SLUGS.get(token.lower().rstrip("s"))


def parse_styles_es(sections: dict[str, str], titles: dict[str, str]) -> list[str]:
    """Derive a sorted list of taxonomy slugs from the per-category section
    titles (canonical signal) and a body-text scan (catches rancio /
    mistela / dulce-natural / sherry sub-styles named only in description
    sections). Slugs are deduped; no role/group hierarchy is implied at
    this layer — the taxonomy resolves that downstream."""
    found: set[str] = set()
    # 1. Older "documento único" template: each wine category is a section
    # title in its own right ("VINO TINTO", "VINO DE LICOR").
    for num, title in titles.items():
        tl = (title or "").lower()
        if not tl.startswith("vino") and "mistela" not in tl and "dulce" not in tl:
            continue
        for pat, slugs in _STYLE_TITLE_PATTERNS:
            if pat.search(tl):
                found.update(slugs)
                break
    # 2. Newer EU 2024 template: one section "Categorías de productos
    # vitivinícolas" enumerates the category names in its body. Scan that
    # body with the same title patterns (Cava: "Vino espumoso de calidad"
    # in section 5).
    categorias_bodies = [
        sections.get(k, "") for k, t in titles.items()
        if "categor" in (t or "").lower()
    ]
    for body in categorias_bodies:
        bl = (body or "").lower()
        for pat, slugs in _STYLE_TITLE_PATTERNS:
            if pat.search(bl):
                found.update(slugs)
    # Join sections with `\n` so section boundaries register as line
    # starts — needed for `_LINE_START_COLOUR_HEADER_RE` to fire on
    # cross-section headers like Pago Florentino's "Tinto tempranillo:"
    # (which opens section 2.2 right after section 2's last figure row).
    body = "\n".join(sections.values())
    # Sherry sub-styles + rancio / dulce / mistela: only emit when the
    # word appears with category context, not as an aside. Restrict to
    # description sections (3, 4, 6) to limit false positives. Kept
    # narrow so grape-variety sections ("Variedad(es) de uva de
    # vinificación", body: "Palomino Fino") don't promote "fino".
    descr_keys = {k for k, t in titles.items()
                  if any(kw in (t or "").lower()
                         for kw in ("descripción", "descripcion", "tipos", "vino "))}
    descr_blob = " ".join(sections.get(k, "") for k in descr_keys) or body
    for pat, slugs in _STYLE_BODY_PATTERNS:
        if pat.search(descr_blob):
            found.update(slugs)
    gate_blob = body + " " + " ".join(titles.values())
    if _SHERRY_GATE.search(gate_blob):
        for pat, slugs in _SHERRY_SUBSTYLE_PATTERNS:
            if pat.search(descr_blob):
                found.update(slugs)
    # Colour detection scans the full pliego: the explicit "vinos X"
    # / colour-list / line-start-header regexes are unambiguous enough
    # (masculine plural, wine-prefixed, or 3-in-a-row) that scanning
    # outside descripción-shaped sections is safe. Castelló's section
    # 1 alone — where the parser dumps the full pliego because of a
    # "2.-" numbering quirk — needs this wider sweep to surface its
    # colours. The masculine-plural constraint excludes feminine grape
    # descriptors ("variedades blancas", "uvas tintas") and the
    # "vinos" prefix on path 4 excludes "Palomino Fino" / "Tinta de
    # Toro" grape names, so unscoped scanning stays safe.
    all_titles_text = " ".join(titles.values())
    blob_for_colour = (all_titles_text + " " + body).lower()
    # Explicit "vinos X" form (Priorat / Tarragona / Málaga style):
    # promote when missing.
    if "red" not in found and re.search(
        r"\bvinos? tintos?\b", blob_for_colour
    ):
        found.add("red")
    if "white" not in found and re.search(
        r"\bvinos? blancos?\b", blob_for_colour
    ):
        found.add("white")
    if "rose" not in found and re.search(
        r"\bvinos? rosados?\b", blob_for_colour
    ):
        found.add("rose")
    # "vinos serán tintos" / "vinos de licor tintos": 1–2 words between
    # "vinos" and the colour (Ribera del Queiles section 2: "Los vinos
    # serán tintos secos…").
    for m in _VINOS_FLEX_COLOUR_RE.finditer(blob_for_colour):
        slug = _colour_slug(m.group(1))
        if slug:
            found.add(slug)
    # Bare-adjective colour-list: "blancos, rosados, tintos" (Valle del
    # Cinca), "Blanco/Rosado" (Cava), "(BLANCO, ROSADO Y TINTO)" (Toro
    # title 4), "Vino tinto y rosado" (Montsant title 8.2).
    for m in _COLOUR_LIST_RE.finditer(blob_for_colour):
        for tok in _COLOUR_TOKEN_RE.findall(m.group(0)):
            slug = _colour_slug(tok)
            if slug:
                found.add(slug)
    # Three colour adjectives in a row, whitespace-separated. Used for
    # tabular column headers (Serra de Tramuntana section 1: "Blanco
    # Rosado Tinto" above analytical-parameters columns).
    for m in _THREE_COLOUR_WS_RE.finditer(blob_for_colour):
        for tok in (m.group(1), m.group(2), m.group(3)):
            slug = _colour_slug(tok)
            if slug:
                found.add(slug)
    # Wine-type line-start header (Pago Florentino section 2.2: "Tinto
    # tempranillo:" / "Blancos:" / "Rosados jóvenes:"). Masculine form
    # excludes feminine grape descriptors.
    for m in _LINE_START_COLOUR_HEADER_RE.finditer(body):
        slug = _colour_slug(m.group(1))
        if slug:
            found.add(slug)
    # Single-colour section-title suffix ("Rías Baixas Tinto").
    for t in titles.values():
        m = _TITLE_COLOUR_TAIL_RE.search((t or "").strip())
        if m:
            slug = _colour_slug(m.group(1))
            if slug:
                found.add(slug)
    # EU 2024 single-colour producto-vitivinícola descriptor (Monterrei
    # section 6 body: "Producto vitivinícola\nBlanco\n…").
    for m in _PRODUCTO_VITIVINICOLA_COLOUR_RE.finditer(body):
        slug = _colour_slug(m.group(1))
        if slug:
            found.add(slug)
    return sorted(found)


# Template-agnostic section roles. EUR-Lex publishes single documents in
# two layouts: the older `ti-grseq-1` template numbers sections 1..9 with
# "Descripción del vino" at #4, "Zona geográfica" at #6, "Variedad" at #7,
# "Vínculo" at #8; the newer `oj-ti-grseq-1` template numbers them at #6,
# #9, #8, #10 respectively. Routing by title keyword keeps downstream
# consumers indifferent to which template the page used.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "denominación del producto", "nombre(s)", "nombre del producto",
        "nombre y tipo",
        # Spanish national-format MAPA pliegos: variants on "name to protect".
        "nombre que se debe proteger", "denominación que debe protegerse",
        "denominación que debe proteger",
        "nombre a proteger", "nombre protegido",
    ),
    "description": (
        "descripción del", "descripcion del",
        "descripción de los", "descripcion de los",
    ),
    "viticultural_practices": (
        "prácticas vitivinícolas", "practicas vitivinicolas",
        "prácticas enológicas", "practicas enologicas",
    ),
    "geo_area": (
        "zona geográfica delimitada", "zona geografica delimitada",
        "definición breve de la zona", "definicion breve de la zona",
        # Spanish national-format headings — diacritics are inconsistent in
        # source PDFs (DELIMITACION vs DELIMITACIÓN; DEMARCACIÓN vs DEMARCACION).
        "demarcación de la zona", "demarcacion de la zona",
        "delimitación de la zona", "delimitacion de la zona",
        "zona delimitada",
        # Variants with "área" instead of "zona":
        "demarcación del área", "demarcacion del area",
        "delimitación del área", "delimitacion del area",
        # Bare-title variants (Bajo Aragón / Córdoba have section "ZONA
        # GEOGRÁFICA" with no qualifier). Route_sections iterates section
        # titles in document order so the section-4/D match beats a
        # later "VÍNCULO CON LA ZONA GEOGRÁFICA" section that would also
        # contain this substring.
        "zona geográfica", "zona geografica",
    ),
    "grape_varieties": (
        # Tightened: the bare keyword "variedad" used to match amendment
        # titles like "VINOS BLANCOS: … VARIEDADES NOBLES" (Valdeorras)
        # or "CAMBIOS EN LAS VARIEDADES" (Emporda/Costers/Pla de Bages),
        # robbing the routing of the real section-7 grape list. The phrase
        # "de uva" reliably qualifies a grape-variety section.
        "variedad(es) de uva", "variedades de uva", "variedad de uva",
        "variedades de uvas", "variedad o variedades",
        # EU 2024 template variant ("PRINCIPALES UVAS DE VINIFICACIÓN"):
        "uvas de vinificación", "uvas de vinificacion",
        "principales uvas",
    ),
    "link_to_terroir": (
        "vínculo", "vinculo", "descripción del (de los) vínculo",
    ),
    "additional_conditions": (
        "condiciones complementarias", "otros requisitos aplicables",
        "otros requisitos",
        # Spanish national-format trailing sections:
        "requisitos legales aplicables", "embotellado", "etiquetado",
    ),
}


def _gather_subsections(sections: dict[str, str], parent_num: str) -> str:
    """Concatenate `<parent_num>.x` sub-section bodies in numeric order.

    The newer EUR-Lex `oj-ti-grseq-1` single-document template often leaves
    a parent section (e.g. "8 — Descripción del vínculo") empty and puts
    the actual content under numbered sub-sections (8.1 factores naturales,
    8.3 factores humanos, 8.4 producto, 8.5 nexo causal). Routing only the
    parent section drops that content; this helper backfills it."""
    prefix = f"{parent_num}."
    children = sorted(
        (k for k in sections if k.startswith(prefix)),
        key=lambda k: tuple(int(p) if p.isdigit() else 0 for p in k.split(".")),
    )
    return "\n".join(sections[k] for k in children if sections.get(k))


_AMENDMENT_TITLE_PREFIXES = (
    "vinos blancos:", "vinos tintos:",
    "plantaciones",
    "cambios", "varios cambios",
    "incorporación", "incorporacion",
    "mejora",
    "resto",
    "densidad",
    # Single-grape amendment headers ("Variedad Syrah", "Variedades
    # Tempranillo y Garnacha", "Variedad Moscatel de Alejandría").
    "variedad syrah", "variedad moscatel", "variedades tempranillo",
)


def _is_amendment_title(title: str) -> bool:
    t = title.lower().strip()
    return any(t.startswith(p) for p in _AMENDMENT_TITLE_PREFIXES)


_GRAPE_COLOUR_FALLBACK_KEYWORDS = ("variedades blancas", "variedades tintas")


def _match_section_body(
    sections: dict[str, str],
    titles: dict[str, str],
    keywords: tuple[str, ...],
    exclude_amendments: bool,
) -> str | None:
    for num, title in titles.items():
        if exclude_amendments and _is_amendment_title(title):
            continue
        if not any(kw in title.lower() for kw in keywords):
            continue
        body = sections.get(num, "")
        if not body.strip():
            body = _gather_subsections(sections, num)
        return body
    return None


def route_sections(sections: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Map semantic role → section body using title keyword matching. First
    title that matches a role's keyword list wins (same idiom as FR
    `route_sections` in `scripts/02_extract_cahiers.py`).

    When the matched parent section is empty (newer EUR-Lex template often
    leaves "8 — Descripción del vínculo" blank and puts the content in
    8.1/8.3/8.4/8.5), fall back to concatenating its numbered children.

    Amendment-section titles (prefixed "CAMBIOS …", "Incorporación …",
    "PLANTACIONES …", "VINOS BLANCOS:" wine-category headers) are
    excluded from grape_varieties matching — they false-positive on the
    bare token "variedades" but are not the section we want.

    Grape-variety routing prefers an explicit "variedad(es) de uva" /
    "uvas de vinificación" title over the colour-organised
    "Variedades blancas" / "Variedades tintas" fallback. Some pliegos
    (e.g. Ribera del Guadiana) carry a real section 7 titled
    "Variedades de uva de vinificación" plus stray oj-ti-grseq-1
    paragraphs inside the yields list that start "1. Variedades
    blancas 12 000 kg…"; the explicit-first pass routes around them."""
    routed: dict[str, str] = {}
    for role, keywords in SECTION_ROLE_KEYWORDS.items():
        body = _match_section_body(
            sections, titles, keywords,
            exclude_amendments=(role == "grape_varieties"),
        )
        if body is not None:
            routed[role] = body
    if "grape_varieties" not in routed:
        body = _match_section_body(
            sections, titles, _GRAPE_COLOUR_FALLBACK_KEYWORDS,
            exclude_amendments=True,
        )
        if body is not None:
            routed["grape_varieties"] = body
    return routed


def derive_summary(role_text: str, max_chars: int = 600) -> str:
    """Pick a concise summary from the routed `description` section."""
    text = re.sub(r"\s+", " ", role_text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def build_record(wine: dict, sections: dict[str, str], titles: dict[str, str],
                 oj_meta: dict) -> dict:
    routed = route_sections(sections, titles)
    grapes = parse_grapes(routed.get("grape_varieties", ""))
    styles = parse_styles_es(sections, titles)
    return {
        "country": "es",
        "source_lang": "es",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,  # subzonas not yet extracted (Phase 3)
        "categories": wine.get("kind") and [wine["kind"]] or [],
        "summary": derive_summary(routed.get("description") or routed.get("geo_area") or ""),
        "sections": sections,
        "section_titles": titles,
        "section_roles": routed,
        "grapes": grapes,
        "styles": styles,
        "geo_area_brief": routed.get("geo_area", ""),
        "link_to_terroir": routed.get("link_to_terroir", ""),
        "producer_group": wine["producer_group"],
        "publications": wine["publications"],
        "source": {
            "filename": f"{wine['slug']}.html",
            "source_url": oj_meta.get("source_url", ""),
            "final_url": oj_meta.get("final_url", ""),
            "bytes": oj_meta.get("bytes", 0),
            "fetched_at": oj_meta.get("fetched_at", ""),
        },
        "stub": False,
    }


def build_subzona_record(parent: dict, sub: dict) -> dict:
    """Wrap one extracted subzona into a child denomination record. Inherits
    most parent fields (kind, source, publications, sections, link_to_terroir,
    grapes, styles) — same idiom as FR DGC records (see
    `scripts/02_extract_cahiers.py` deep-copy of parent into dgc_record)."""
    rec = json.loads(json.dumps(parent))  # deep copy
    rec["name"] = sub["name"]
    rec["slug"] = f"{parent['slug']}-{sub['slug']}" if sub["slug"] else parent["slug"]
    rec["is_sub_denomination"] = True
    rec["parent_id_eambrosia"] = parent["id_eambrosia"]
    rec["parent_slug"] = parent["slug"]
    rec["parent_name"] = parent["name"]
    rec["subzona_communes"] = sub["communes"]
    rec["subzona_source_pattern"] = sub["source_pattern"]
    # Replace the parent's geo_area_brief with the subzona-specific commune
    # list so downstream consumers (stage 04 commune-resolution) see only
    # this subzona's communes when computing the polygon.
    rec["geo_area_brief"] = "\n".join(sub["communes"])
    return rec


def build_stub(wine: dict, oj_meta: dict, reason: str) -> dict:
    return {
        "country": "es",
        "source_lang": "es",
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine["fileNumber"],
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "is_sub_denomination": False,
        "categories": wine.get("kind") and [wine["kind"]] or [],
        "summary": "",
        "sections": {},
        "section_titles": {},
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [],
        "geo_area_brief": "",
        "link_to_terroir": "",
        "producer_group": wine["producer_group"],
        "publications": wine["publications"],
        "source": {
            "filename": "",
            "source_url": oj_meta.get("source_url", ""),
            "final_url": oj_meta.get("final_url", ""),
            "bytes": 0,
            "fetched_at": oj_meta.get("fetched_at", ""),
        },
        "stub": True,
        "stub_reason": reason,
    }


def _extract_from_html(cache: Path) -> tuple[dict[str, str], dict[str, str], str]:
    """Existing EUR-Lex single-document path. Returns (sections, titles,
    parse_reason); parse_reason is empty string on success, otherwise the
    stub_reason to record."""
    html = cache.read_text(encoding="utf-8")
    doc = slice_documento_unico(html)
    if doc is None:
        return {}, {}, "no-documento-unico-anchor"
    sections, titles = extract_sections(doc)
    if not sections:
        return {}, {}, "no-sections"
    return sections, titles, ""


def _extract_from_pdf(cache: Path) -> tuple[dict[str, str], dict[str, str], str]:
    """MAPA / euskadi.eus Spanish-national-format path. pdftotext to text,
    then PDF_SECTION_HEADER_RE finds numbered headings."""
    try:
        text = pdftotext(cache)
    except subprocess.CalledProcessError as exc:
        print(f"[fail] {cache.name}: pdftotext failed: {exc}", file=sys.stderr)
        return {}, {}, "pdftotext-failed"
    sections, titles = extract_sections_from_pdf_text(text)
    if not sections:
        return {}, {}, "no-pdf-sections"
    return sections, titles, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/es/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_IN.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        wines = wines[: args.limit]

    oj_manifest: dict = {}
    if OJ_MANIFEST.exists():
        try:
            oj_manifest = json.loads(OJ_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    extracted = stubs = parse_failed = subzonas_emitted = 0
    index: dict[str, dict] = {}
    if shutil.which("pdftotext") is None:
        print("warn: pdftotext not on PATH — PDF pliegos will fail to extract "
              "(brew install poppler)", file=sys.stderr)

    for w in tqdm(wines, desc="extract-pliegos", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        oj_meta = oj_manifest.get(slug, {})
        html_cache = OJ_DIR / f"{slug}.html"
        pdf_cache = OJ_DIR / f"{slug}.pdf"

        if pdf_cache.exists():
            sections, titles, parse_reason = _extract_from_pdf(pdf_cache)
        elif html_cache.exists():
            sections, titles, parse_reason = _extract_from_html(html_cache)
        else:
            sections, titles, parse_reason = {}, {}, oj_meta.get("status") or "no-html-cached"

        if parse_reason or not sections:
            record = build_stub(w, oj_meta, parse_reason or "no-sections")
            if parse_reason in ("no-html-cached", "no-publication", "fetch-error",
                                "not-single-document", "playwright-error"):
                stubs += 1
            else:
                parse_failed += 1
        else:
            record = build_record(w, sections, titles, oj_meta)
            # Update source filename to reflect actual cache file (HTML or PDF).
            record["source"]["filename"] = (
                pdf_cache.name if pdf_cache.exists() else html_cache.name
            )
            extracted += 1

        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "country": "es",
            "id_eambrosia": w["giIdentifier"],
            "file_number": w["fileNumber"],
            "slug": slug,
            "name": w["name"],
            "kind": w["kind"],
            "filename": out_path.name,
            "is_sub_denomination": False,
            "parent_slug": "",
            "stub": record["stub"],
            "stub_reason": record.get("stub_reason", ""),
            "sections_present": sorted(record["sections"]),
            "n_grapes": len(record["grapes"].get("details") or []),
        }

        # Emit one child record per detected subzona. Skipped for stubs
        # (no geo_area_brief to extract from). The child slug is
        # `<parent>-<subzona>` to keep slugs globally unique without
        # forcing curators to remember which subzona belongs to which
        # parent (e.g. `rioja-rioja-alta`, `costers-del-segre-urgell`).
        if not record["stub"] and record.get("geo_area_brief"):
            subs = extract_subzonas(record["geo_area_brief"], record["name"])
            for sub in subs:
                child = build_subzona_record(record, sub)
                child_path = OUT_DIR / f"{child['slug']}.json"
                child_path.write_text(json.dumps(child, ensure_ascii=False, indent=2), encoding="utf-8")
                index[child["slug"]] = {
                    "country": "es",
                    "id_eambrosia": w["giIdentifier"],
                    "file_number": w["fileNumber"],
                    "slug": child["slug"],
                    "name": child["name"],
                    "kind": w["kind"],
                    "filename": child_path.name,
                    "is_sub_denomination": True,
                    "parent_slug": w["slug"],
                    "parent_name": w["name"],
                    "subzona_source_pattern": sub["source_pattern"],
                    "n_communes": len(sub["communes"]),
                    "stub": False,
                    "stub_reason": "",
                    "sections_present": sorted(record["sections"]),
                    "n_grapes": len(record["grapes"].get("details") or []),
                }
                subzonas_emitted += 1

    set_pliego_context(None)
    INDEX_OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    unknowns_path = ROOT / "raw" / "es" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"review at {unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )
    print(
        f"[done] extracted={extracted} stubs={stubs} parse_failed={parse_failed} "
        f"subzonas={subzonas_emitted} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    print(
        f"[done] generated_at={datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
