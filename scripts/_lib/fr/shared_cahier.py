"""One appellation's clauses inside a cahier shared by several appellations.

INAO publishes one cahier des charges for the 51 Alsace grands crus. Its
section III (types de produit) and section V (encépagement) state a general
rule and then single crus out: red wine only at Hengst, Kirchberg de Barr and
Vorbourg; Sylvaner only at Zotzenberg; a blend with accessory varieties at
Altenberg de Bergheim and Kaefferkopf, neither of which allows a varietal
Muscat. Stage 02 read both sections whole, so every cru carried the union —
Brand listed Pinot noir and red, and a grape filter returned all 51 crus
(found through the MCP server, 2026-10-04).

The same shape recurs where two or three appellations share a cahier: Anjou,
Cabernet d'Anjou and Rosé d'Anjou (section V is one table, a row block per
appellation — Cot belongs to Rosé d'Anjou only), Pouilly-Fumé and
Pouilly-sur-Loire (Sauvignon and Chasselas respectively).

`own_text` keeps the units of a section that apply to one appellation: the
units naming it when there are any, else the general units, which name no
other appellation and do not except this one. A unit is a lettered clause
("b) - Les vins à appellation d'origine contrôlée « … » sont issus …") when
the section has them, else a table row block (a line opening on an
appellation's « name »), else a sentence. A name inside an "à l'exception
de …" span excepts that appellation rather than naming it. Only names the
cahier's section I declares count, so « vendanges tardives » is not an
appellation, and a register name "X ou Y" answers to either alias. A cahier
is shared only when section I declares an appellation other than the
record's own aliases.
"""

from __future__ import annotations

import re

from _lib.terroir_chapters import fold

_QUOTED = re.compile(r"«\s*([^»]{1,160}?)\s*»")
_CLAUSE = re.compile(r"^[ \t]*[a-z]\)[ \t]*[-–—]", re.MULTILINE)
# A table row opens on the « name » (with any "ou « alias »") and then the
# line ends or a column gap follows — a prose list wrapped onto a line that
# starts with a name ("« Sablet », « Saint-Gervais », …") is not a row.
_ROW = re.compile(
    r"^[ \t]*«\s*([^»\n]{1,160}?)\s*»(?:\s+ou\s+«[^»\n]*»)*[ \t]*(?:$|[ \t]{2})",
    re.MULTILINE,
)
_ALIAS = re.compile(r"\s+ou\s+", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-ZÀ-ÖØ-Þ«])|\n[ \t]*\n")
_EXCEPT = re.compile(r"à\s+l['’]exception\b|\bhormis\b|\bsauf\b|\bexcept[ée]\b", re.IGNORECASE)
_EXCEPT_END = re.compile(r"\b(?:sont|est|peuvent|peut)\b")
# parse_grapes reads the 1° block only; the proportion rules after it name
# the same crus and would read as rosters of their own.
_PROPORTION = re.compile(r"\b2\s*°|\b3\s*°|r[èe]gles?\s+de\s+proportion", re.IGNORECASE)
_COLOUR_ITEM = {
    "red": "rouges",
    "rose": "ros[ée]s",
}


def covered_names(section_i: str) -> set[str]:
    """Folded names of the appellations section I declares."""
    return {fold(m.group(1)) for m in _QUOTED.finditer(section_i or "")}


def aliases(record_name: str) -> set[str]:
    return {fold(record_name)} | {fold(p) for p in _ALIAS.split(record_name or "") if p.strip()}


def is_shared(covered: set[str], record_name: str) -> bool:
    own = aliases(record_name)
    return bool(own & covered) and bool(covered - own)


def _units(text: str, covered: set[str]) -> list[str]:
    starts = [m.start() for m in _CLAUSE.finditer(text)]
    if len(starts) < 2:
        starts = [m.start() for m in _ROW.finditer(text) if fold(m.group(1)) in covered]
    if len(starts) < 2:
        cuts = [0] + [m.end() for m in _SENTENCE.finditer(text)] + [len(text)]
    else:
        cuts = ([0] if starts[0] else []) + starts + [len(text)]
    return [text[a:b] for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]


def _except_spans(unit: str) -> list[tuple[int, int]]:
    spans = []
    for m in _EXCEPT.finditer(unit):
        end = _EXCEPT_END.search(unit, m.end())
        spans.append((m.end(), end.start() if end else len(unit)))
    return spans


def _classify(unit: str, want: set[str], covered: set[str]) -> tuple[bool, bool, bool]:
    """(names the record, excepts it, names another covered appellation)."""
    spans = _except_spans(unit)
    named = excepted = others = False
    for m in _QUOTED.finditer(unit):
        name = fold(m.group(1))
        if name not in covered:
            continue
        inside = any(a <= m.start() < b for a, b in spans)
        if name in want:
            excepted |= inside
            named |= not inside
        elif not inside:
            others = True
    return named, excepted, others


def own_text(text: str, record_name: str, covered: set[str]) -> str:
    """The units of `text` that apply to `record_name`; `text` unchanged
    when the cahier is not shared or no unit applies."""
    if not text or not is_shared(covered, record_name):
        return text
    want = aliases(record_name)
    units = _units(text, covered)
    marks = [_classify(u, want, covered) for u in units]
    own = [u for u, (named, _, _) in zip(units, marks) if named]
    if not own:
        own = [u for u, (named, excepted, others) in zip(units, marks)
               if not (named or excepted or others)]
    return "\n\n".join(own) if own else text


def own_encepagement(text: str, record_name: str, covered: set[str], styles: list[str]) -> str:
    """Section V's 1° block narrowed to `record_name`, with the "pour les
    vins rouges / rosés" items dropped when the record's own types de
    produit carry no such colour."""
    if not text or not is_shared(covered, record_name):
        return text
    cut = _PROPORTION.search(text, 1)
    if cut:
        text = text[: cut.start()]
    units = _units(own_text(text, record_name, covered), covered)
    for colour, word in _COLOUR_ITEM.items():
        if colour in styles:
            continue
        item = re.compile(
            rf"^[ \t]*[-–−][ \t]*pour\s+les\s+vins\s+{word}\b[\s\S]*?"
            rf"(?=^[ \t]*[-–−][ \t]*pour\s+les\s+vins\b|\Z)",
            re.MULTILINE | re.IGNORECASE,
        )
        units = [item.sub("", u) for u in units]
    return "\n\n".join(units)
