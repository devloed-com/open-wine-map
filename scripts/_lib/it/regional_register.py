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
  - "catalogoviti" — the MASAF Registro Nazionale delle Varietà di Vite
                 (catalogoviti.politicheagricole.it, CREA-VIT) queried
                 per province: its search endpoint `post1.php` returns
                 the varieties classified "idonee alla coltivazione" in
                 a province as JSON rows, each name carrying the same
                 N./B./G./RS. colour suffix as the regional PDFs. For a
                 Region that classifies on its whole territory (Molise,
                 Lombardia — the 2011 MASAF classificazione lists which)
                 the union over its provinces is the regional list, so
                 a Region that publishes no standalone PDF (Molise) or
                 only a JS-gated page (Lombardia) is served from the
                 national register instead. Stage 02h caches the rows
                 per province in `<region>.catalogoviti.json`; the
                 parser reads that JSON text.

Variety names resolve through the shared grape lexicon
(`_lib.grape_entity.match_variety`); the register's colour marker is
passed as the ambient colour so per-region colour wins over the lexicon
default.
"""

from __future__ import annotations

import html
import json
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


_TAG_RE = re.compile(r"<[^>]+>")


def catalogoviti_variety_lines(cache_text: str) -> list[str]:
    """The distinct "<code> <Name> <COL>." lines of a stage-02h
    catalogoviti cache (`{"provinces": {code: {"rows": [...]}}}`), the
    union over its provinces in register-code order. A row is the
    endpoint's positional array: `[codice, "<a …>Name N. </a>", clone
    code, …]`; the variety-only filter leaves the clone columns empty,
    but a clone row that slips through is keyed by the same codice and
    collapses into its variety."""
    data = json.loads(cache_text)
    by_code: dict[str, str] = {}
    for prov in (data.get("provinces") or {}).values():
        for row in prov.get("rows") or []:
            if len(row) < 2:
                continue
            name = html.unescape(_TAG_RE.sub("", str(row[1]))).strip()
            if name:
                by_code.setdefault(str(row[0]).strip(), name)
    return [f"{code} {name}" for code, name in sorted(by_code.items())]


def _parse_catalogoviti(text: str, out: list[dict], seen: set[str]) -> None:
    _parse_suffix("\n".join(catalogoviti_variety_lines(text)), out, seen)


_TEMPLATES = {
    "suffix": _parse_suffix,
    "vbcode": _parse_vbcode,
    "columns": _parse_columns,
    "catalogoviti": _parse_catalogoviti,
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
