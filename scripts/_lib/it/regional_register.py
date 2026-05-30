"""Parser for the per-region authorised wine-grape variety registers
that Italian regional IGTs reference by annex ("i vitigni idonei alla
coltivazione nella Regione X, riportati nell'allegato 1") rather than
listing inline.

Each Region publishes the list as an official act (public-domain under
art. 5 L. 633/1941 — atti ufficiali delle amministrazioni pubbliche).
Three colour encodings appear across the regions, so the parser has one
branch per encoding, dispatched by `template`:

  - "suffix"   — "<code> Variety N." with a trailing colour code
                 (Umbria, Sicilia, Calabria). N/B/G/RS/RG/RB.
  - "columns"  — "<code>  VARIETY  Nero  <synonyms>" with the colour as
                 a spelled word in its own whitespace column (Lazio).
  - "vbcode"   — "<code> Variety V.B.N." (Campania). V.B.N/V.B.B/V.B.G.

Variety names resolve through the shared grape lexicon
(`_lib.grape_entity.match_variety`); the register's colour marker is
passed as the ambient colour so per-region colour wins over the lexicon
default.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grape_entity import match_variety  # noqa: E402

_SUFFIX_COLOUR = {
    "N": "noir", "B": "blanc", "G": "gris",
    "RS": "rose", "RG": "rose", "RB": "rose",
}
_WORD_COLOUR = {
    "nero": "noir", "nera": "noir", "bianco": "blanc", "bianca": "blanc",
    "grigio": "gris", "grigia": "gris", "rosa": "rose", "rosato": "rose",
    "rossa": "rose", "rosso": "noir",
}
_VB_COLOUR = {"N": "noir", "B": "blanc", "G": "gris"}

# "<optional 1-2 leading numeric codes>  <name>  <colour-suffix>."
_SUFFIX_RE = re.compile(
    r"^[ \t]*(?:\d{1,4}[ \t]+){0,2}(?P<name>[A-Za-zÀ-ÿ][\w' .’\-/]+?)"
    r"[ \t]+(?P<col>N|B|G|RS|RG|RB)\.(?:[ \t]|$)",
)
_VB_RE = re.compile(
    r"^[ \t]*(?:\d{1,4}[ \t]+){0,2}(?P<name>[A-Za-zÀ-ÿ][\w' .’\-/]+?)"
    r"[ \t]+V\.?B\.?(?P<col>[NBG])\.?(?:[ \t]|$)",
)


def _emit(name: str, colour: str, out: list[dict], seen: set[str]) -> None:
    name = name.strip(" .,-–—\t")
    if not name or len(name) > 60:
        return
    hit = match_variety(name, ambient_colour=colour or None)
    if hit is None or hit.slug in seen:
        return
    if hit.method.startswith("fuzzy"):
        score = int(hit.method.split(":")[1])
        if score < 90 or len(re.sub(r"[\W\d_]", "", name)) < 7:
            return
    seen.add(hit.slug)
    out.append({"slug": hit.slug, "name": hit.name,
                "colour": hit.colour or colour, "raw": name})


def _parse_suffix(text: str, out: list[dict], seen: set[str]) -> None:
    for line in text.splitlines():
        m = _SUFFIX_RE.match(line)
        if m:
            _emit(m.group("name"), _SUFFIX_COLOUR.get(m.group("col"), ""), out, seen)


def _parse_vbcode(text: str, out: list[dict], seen: set[str]) -> None:
    for line in text.splitlines():
        m = _VB_RE.match(line)
        if m:
            _emit(m.group("name"), _VB_COLOUR.get(m.group("col"), ""), out, seen)


def _parse_columns(text: str, out: list[dict], seen: set[str]) -> None:
    for line in text.splitlines():
        # code <gap> NAME <gap> COLOUR-WORD <gap> synonyms
        fields = re.split(r"[ \t]{2,}", line.strip())
        if len(fields) < 3:
            continue
        if not re.fullmatch(r"\d{1,4}", fields[0]):
            continue
        col = _WORD_COLOUR.get(fields[2].strip().lower())
        if col is None:
            continue
        _emit(fields[1], col, out, seen)


_TEMPLATES = {
    "suffix": _parse_suffix,
    "vbcode": _parse_vbcode,
    "columns": _parse_columns,
}


def parse_register(text: str, template: str) -> list[dict]:
    """Return [{slug, name, colour, raw}] for one region register's
    pdftotext-layout output, using the named encoding branch."""
    fn = _TEMPLATES.get(template)
    if fn is None:
        raise ValueError(f"unknown register template {template!r}")
    out: list[dict] = []
    seen: set[str] = set()
    fn(text, out, seen)
    return out
