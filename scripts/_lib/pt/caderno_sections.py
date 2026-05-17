"""Section finder for IVV cadernos de especificações (PT).

PT cadernos come in three structural variants:

  Variant A — "Roman + Arabic" (Douro, Alentejo, Madeira, Porto, …):
      I.  NOME(S) A REGISTAR
      II. DADOS RELATIVOS AO REQUERENTE
      …
      V. DOCUMENTO ÚNICO
        1. CATEGORIA DE PRODUTOS VITIVINÍCOLAS
        …
        7. RELAÇÃO COM A ÁREA GEOGRÁFICA
      VI. OUTRAS INFORMAÇÕES

  Variant B — "Arabic only / documento único first" (Vinho Verde, Pico):
      1. NOME E TIPO
      2. CATEGORIAS DOS PRODUTOS VITIVINÍCOLAS
      …
      7. RELAÇÃO COM A ZONA GEOGRÁFICA

  Variant C — "Arabic short / older format" (Dão):
      1. Identificação do Nome
      2. Descrição do Vinho
      …
      7. Relação com o Meio Geográfico

Rather than guess the variant, we scan for known Portuguese keywords
anywhere in the document and carve up the text between them. Each
match's position becomes a boundary; consecutive boundaries delimit
the body of one semantic section.

The returned dict maps semantic-role names (`area`, `grapes`, `link`,
`yields`, `description`, `category`, `traditional`, `practices`,
`additional`) to section bodies. Roles that are absent map to "".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Each entry is (role, regex). The regex must match the section
# **header** anywhere on a line; the body extends to the next match.
# Order matters only for tie-breaking (overlapping matches → first wins).
_SECTION_ANCHORS: list[tuple[str, re.Pattern[str]]] = [
    (
        "category",
        re.compile(
            r"CATEGORIAS?\s+D(?:E|OS)\s+PRODUTOS\s+VITIVIN[ÍI]COLAS",
            re.IGNORECASE,
        ),
    ),
    (
        "description",
        re.compile(
            r"DESCRI[ÇC][ÃA]O\s+DO(?:\(S\)|S)?\s+VINHO(?:\(S\)|S)?",
            re.IGNORECASE,
        ),
    ),
    (
        "traditional",
        re.compile(r"MEN[ÇC][ÕO]ES\s+TRADICIONAIS", re.IGNORECASE),
    ),
    (
        "practices",
        re.compile(
            r"PR[ÁA]TICAS\s+(?:VIT[ÍI]COLAS|VIN[ÍI]COLAS|EN[ÓO]L[ÓO]GICAS)",
            re.IGNORECASE,
        ),
    ),
    (
        "area",
        re.compile(
            r"(?:[ÁA]REA\s+DELIMITADA"
            r"|ZONA\s+GEOGR[ÁA]FICA\s+DEMARCADA"
            r"|DELIMITA[ÇC][ÃA]O\s+DA\s+[ÁA]REA\s+GEOGR[ÁA]FICA"
            r"|[ÁA]REA\s+GEOGR[ÁA]FICA\s+DELIMITADA)",
            re.IGNORECASE,
        ),
    ),
    (
        "yields",
        re.compile(
            r"RENDIMENTOS?\s+M[ÁA]XIMOS?(?:\s+POR\s+HECTARE)?",
            re.IGNORECASE,
        ),
    ),
    (
        "grapes",
        re.compile(
            r"(?:UVAS\s+DE\s+VINHO"
            r"|PRINCIPAL(?:\(IS\))?\s+CASTA(?:\(S\))?\s+DE\s+UVA"
            r"|PRINCIPAIS\s+CASTAS"
            r"|CASTAS\s+UTILIZADAS"
            r"|CASTAS\s+PRINCIPAIS"
            r"|VARIEDADES?\s+DE\s+VITIS\s+VIN[ÍI]FERA)",
            re.IGNORECASE,
        ),
    ),
    (
        "link",
        re.compile(
            r"(?:RELA[ÇC][ÃA]O\s+COM\s+A\s+(?:[ÁA]REA|ZONA)\s+GEOGR[ÁA]FICA"
            r"|RELA[ÇC][ÃA]O\s+COM\s+O\s+MEIO\s+GEOGR[ÁA]FICO"
            r"|DESCRI[ÇC][ÃA]O\s+DAS\s+RELA[ÇC][ÕO]ES"
            r"|LIGA[ÇC][ÃA]O\s+(?:AO\s+TERRIT[ÓO]RIO"
            r"|COM\s+A\s+(?:[ÁA]REA|ZONA)\s+GEOGR[ÁA]FICA))",
            re.IGNORECASE,
        ),
    ),
    (
        "additional",
        re.compile(
            r"(?:CONDI[ÇC][ÕO]ES\s+(?:COMPLEMENTARES|SUPLEMENTARES)"
            r"|OUTRAS\s+CONDI[ÇC][ÕO]ES"
            r"|EXIG[ÊE]NCIAS\s+APLIC[ÁA]VEIS)",
            re.IGNORECASE,
        ),
    ),
    (
        "other",
        re.compile(r"OUTRAS\s+INFORMA[ÇC][ÕO]ES", re.IGNORECASE),
    ),
]

# A header is plausible when preceded (within ~6 chars) by a digit
# followed by a period — `1. CATEGORIA…`, `5. ÁREA…`. This filters out
# stray in-prose mentions ("a área delimitada da DOP é …") that would
# otherwise become false anchors.
_NUMERIC_PREFIX_RE = re.compile(r"(?:^|\n)\s*(?:[IVX]{1,4}\.\s*)?\d{1,2}\s*[.\-]?\s+$")
_NUMERIC_PREFIX_LOOKBACK = 12


def pdftotext_layout(pdf_path: Path) -> str:
    """Run `pdftotext -layout` and return the result. PT cadernos
    contain Roman numerals + accented capitals; `-layout` preserves the
    column structure that some cadernos use (notably grape tables)."""
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _find_anchors(text: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, role)] for every matched section header,
    keeping only those preceded by a numeric prefix.
    Sorted by start position."""
    matches: list[tuple[int, int, str]] = []
    for role, pat in _SECTION_ANCHORS:
        for m in pat.finditer(text):
            start = m.start()
            lookback = text[max(0, start - _NUMERIC_PREFIX_LOOKBACK) : start]
            if not _NUMERIC_PREFIX_RE.search(lookback):
                continue
            matches.append((start, m.end(), role))
    matches.sort(key=lambda t: t[0])
    return _dedupe_overlapping(matches)


def _dedupe_overlapping(
    matches: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """If two anchors overlap (same role hits twice via two patterns,
    or two roles share a token), keep the first by position."""
    out: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, role in matches:
        if start < last_end:
            continue
        out.append((start, end, role))
        last_end = end
    return out


def extract_sections(text: str) -> dict[str, str]:
    """Carve the doc into role-keyed bodies.

    Each anchor's body is everything between the end of the anchor and
    the start of the next anchor — i.e. NOT including the header text
    itself. If a role appears twice (Variant A's nested arabic + the
    outer roman numerals), the LAST appearance wins, which in practice
    matches the documento-único interior (the most informative copy).
    """
    anchors = _find_anchors(text)
    if not anchors:
        return {}
    result: dict[str, str] = {}
    n = len(anchors)
    for i, (start, end, role) in enumerate(anchors):
        next_start = anchors[i + 1][0] if i + 1 < n else len(text)
        body = text[end:next_start].strip()
        if not body:
            continue
        # Last-write-wins for repeating roles (Variant A nested headers).
        # The DOCUMENTO ÚNICO interior carries more content than the
        # short Roman-numeral preamble, so the later copy is the one
        # we want.
        result[role] = body
    return result


def first_paragraph(text: str, max_chars: int = 1200) -> str:
    """Return the first paragraph of a section body, capped at
    max_chars. Used to seed the cahier-summary equivalent."""
    text = text.strip()
    if not text:
        return ""
    paras = re.split(r"\n\s*\n", text, maxsplit=2)
    out = (paras[0] if paras else text).strip()
    return out[:max_chars]


def collapse_whitespace(text: str) -> str:
    """Normalise pdftotext output: collapse multi-space → single space,
    keep line breaks. Used when persisting section bodies to JSON to
    avoid huge inline blobs of trailing whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()
