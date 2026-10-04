"""A DGC's own colours and roster inside its appellation's cahier.

INAO publishes one cahier per appellation, and a dénomination géographique
complémentaire is a section of it: section III (types de produit) and section
V (encépagement) often give a DGC rules of its own — Touraine Oisly is white
Sauvignon only, Saumur Puy-Notre-Dame red Cabernet franc only, Côtes de
Bordeaux Cadillac red only. Stage 02 used to copy the parent's colours and
roster onto every DGC, so a grape or colour filter returned the whole family.

`dgc_text` returns the part of a section that applies to one DGC, or None when
the section does not name it (the DGC then follows the parent's rule). Two
layouts:

- prose (numbered paragraphs, lettered clauses): the units naming the DGC,
  read with `shared_cahier`'s unit splitter;
- a two-column table (`pdftotext -layout`): a heading naming the DGC — a
  centred line, or one running across both columns — scopes the rows below it
  up to the next heading; otherwise the DGC is a row label in the left column,
  and its row is the value block of the right column that the label overlaps
  (labels are centred on their value, so a name wrapped over two lines, or a
  value printed a line above its label, still pairs up).

`drop_colours` removes, from the parent's text, the units or rows of a colour
the DGC is not allowed (Côtes de Bordeaux's "b)- Les vins blancs sont issus"
for Cadillac), for a DGC whose section V does not name it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from _lib.fr import shared_cahier
from _lib.terroir_chapters import fold

_QUOTED = re.compile(r"«\s*([^»]{1,160}?)\s*»")
_RUN = re.compile(r"\S+(?: \S+)*")
_LABEL_START = re.compile(
    r"(?:AOC|Appellation|D[ée]nominations?|Mention|Indication|Vins?\b|Couleur)", re.I
)
_VALUE_START = re.compile(
    r"(?:-\s*)?(?:c[ée]pages?\s+principa|vins?\b)", re.I
)
_COLOUR_WORD = {
    "white": re.compile(r"\bblancs?\b", re.I),
    "red": re.compile(r"\brouges?\b", re.I),
    "rose": re.compile(r"\bros[ée]s?\b", re.I),
}
_UNIT_COLOUR_HEAD = re.compile(
    r"\bvins?\s+(?:(?:tranquilles?|mousseux|effervescents?|de\s+qualit[ée]|ou|et|,|\s)+)?"
    r"((?:blancs?|rouges?|ros[ée]s?)(?:(?:\s*,\s*|\s+(?:et|ou)\s+)(?:blancs?|rouges?|ros[ée]s?))*)",
    re.I,
)


def key(name: str) -> str:
    return fold(re.sub(r"-\s+", "-", name or ""))


def dgc_keys(dgc_name: str, parent_name: str) -> set[str]:
    """Folded names a DGC answers to: its register name, the part after the
    parent's name ("Touraine Oisly" → "oisly"), and their " ou " aliases."""
    out: set[str] = set()
    pf = key(parent_name)
    for part in [dgc_name, *re.split(r"\s+ou\s+", dgc_name or "", flags=re.I)]:
        k = key(part)
        if not k:
            continue
        out.add(k)
        if k.startswith(pf + " "):
            out.add(k[len(pf):].strip())
    return out


def quoted_keys(text: str) -> set[str]:
    return {key(m.group(1)) for m in _QUOTED.finditer(text or "")}


def names(text: str, want: set[str]) -> bool:
    return bool(quoted_keys(text) & want)


def strip_names(text: str) -> str:
    """Drop « … » names before the grape parser reads a row (the Mâcon DGC
    « Chardonnay » is a commune, not the grape)."""
    return _QUOTED.sub(" ", text or "")


# ---------------------------------------------------------------- table layout


@dataclass
class _Line:
    left: str = ""
    right: str = ""
    runs: list[tuple[int, int, str]] = field(default_factory=list)


def _value_column(lines: list[str]) -> int | None:
    starts: list[int] = []
    for ln in lines:
        runs = [(m.start(), m.end()) for m in _RUN.finditer(ln)]
        for i, (s, _e) in enumerate(runs):
            if s >= 25 and (i > 0 or s >= 30):
                starts.append(s)
    if len(starts) < 3:
        return None
    best, best_n = None, 0
    for s in sorted(set(starts)):
        n = sum(1 for t in starts if s <= t <= s + 6)
        if n > best_n:
            best, best_n = s, n
    two_col = sum(
        1 for ln in lines
        if any(m.start() < best - 3 for m in _RUN.finditer(ln))
        and any(m.start() >= best - 3 for m in _RUN.finditer(ln))
    )
    return best if best_n >= 3 and two_col >= 2 else None


def _split(lines: list[str], col: int) -> list[_Line]:
    out = []
    for ln in lines:
        runs = [(m.start(), m.end(), m.group()) for m in _RUN.finditer(ln)]
        left = " ".join(t for s, _e, t in runs if s < col - 3)
        right = " ".join(t for s, _e, t in runs if s >= col - 3)
        out.append(_Line(left, right, runs))
    return out


def _is_heading(line: _Line, col: int) -> bool:
    if len(line.runs) != 1 or "«" not in line.runs[0][2]:
        return False
    start, end, _ = line.runs[0]
    return (12 <= start < col - 3) or (start < col - 3 and end > col + 6)


def _headings(rows: list[_Line], col: int, covered: set[str]) -> list[tuple[int, str]]:
    """(line index, heading text) for every heading naming a covered name;
    a name cut by the line end ("« Cru Sainte-" / "Victoire »") is joined."""
    out = []
    for i, ln in enumerate(rows):
        if not _is_heading(ln, col):
            continue
        text = ln.runs[0][2]
        j = i + 1
        while text.count("«") > text.count("»") and j < len(rows) and j <= i + 2:
            text += " " + " ".join(t for _s, _e, t in rows[j].runs)
            j += 1
        if quoted_keys(text) & covered:
            out.append((i, text))
    return out


def _blocks(rows: list[_Line], side: str) -> list[tuple[int, int]]:
    """Line spans of the label blocks (left) or value blocks (right)."""
    spans: list[tuple[int, int]] = []
    start = last = None
    gap = 0
    for i, ln in enumerate(rows):
        text = getattr(ln, side)
        if not text:
            gap += 1
            continue
        starts_new = (
            _LABEL_START.match(text) if side == "left" else _VALUE_START.match(text)
        )
        if start is None:
            start = last = i
        elif gap <= 1 and not starts_new:
            last = i
        else:
            spans.append((start, last))
            start = last = i
        gap = 0
    if start is not None:
        spans.append((start, last))
    return spans


def _paired(label: tuple[int, int], values: list[tuple[int, int]]) -> list[tuple[int, int]]:
    a, b = label
    hit = [v for v in values if v[0] <= b and v[1] >= a]
    if hit:
        return hit
    if not values:
        return []
    dist = [(min(abs(v[0] - b), abs(a - v[1])), -v[0], v) for v in values]
    return [min(dist)[2]]


def _table_text(lines: list[str], col: int, want: set[str], covered: set[str]) -> str | None:
    rows = _split(lines, col)
    heads = _headings(rows, col, covered)
    for n, (i, text) in enumerate(heads):
        if quoted_keys(text) & want:
            end = heads[n + 1][0] if n + 1 < len(heads) else len(rows)
            return "\n".join(lines[i:end])
    labels = _blocks(rows, "left")
    values = _blocks(rows, "right")
    picked: list[tuple[int, int]] = []
    for lb in labels:
        text = " ".join(rows[k].left for k in range(lb[0], lb[1] + 1))
        if quoted_keys(text) & want:
            picked.append(lb)
            picked.extend(_paired(lb, values))
    for vb in values:
        text = " ".join(rows[k].right for k in range(vb[0], vb[1] + 1))
        if quoted_keys(text) & want:
            picked.append(vb)
    if not picked:
        return None
    keep = sorted({k for a, b in picked for k in range(a, b + 1)})
    return "\n".join(f"{rows[k].left}  {rows[k].right}".strip() for k in keep)


# ---------------------------------------------------------------- public API


# Section III also describes the wines (an IGP's "Pour l'unité géographique
# « Coteaux du Grésivaudan », les vins blancs présentent une robe …"): in
# prose only a reservation rule sets a DGC's colours.
RESERVATION = re.compile(r"\br[ée]serv[ée]e?s?\b", re.I)


def dgc_text(text: str, want: set[str], covered: set[str],
             prose_rule: re.Pattern | None = None) -> str | None:
    """The part of a section that applies to the DGC answering to `want`;
    None when the section names no `want` (the DGC follows the parent).
    `covered` holds the names of every DGC (and the parent) of the cahier;
    `prose_rule`, when given, is what a prose unit must say to count."""
    if not text or not names(text, want):
        return None
    lines = text.splitlines()
    col = _value_column(lines)
    if col is not None:
        got = _table_text(lines, col, want, covered)
        if got is not None:
            return got
    units = shared_cahier._units(text, covered)
    own: list[str] = []
    for i, u in enumerate(units):
        if not (shared_cahier._classify(u, want, covered)[0]
                and (prose_rule is None or prose_rule.search(u))):
            continue
        own.append(u)
        # "… à partir des cépages figurant dans la liste suivante :" — the
        # list is the next unit, unless that one names another appellation.
        if u.rstrip().endswith(":") and i + 1 < len(units) and not (
            quoted_keys(units[i + 1]) & covered
        ):
            own.append(units[i + 1])
    return "\n\n".join(own) if own else None


def unit_colours(head: str) -> set[str]:
    m = _UNIT_COLOUR_HEAD.search(head or "")
    if not m:
        return set()
    return {c for c, rx in _COLOUR_WORD.items() if rx.search(m.group(1))}


def drop_colours(text: str, allowed: set[str], covered: set[str]) -> str:
    """The parent's text without the units / table rows of a colour outside
    `allowed`, nor the rows or heading scopes of another DGC (`covered` holds
    the DGC names only) — for a DGC its section V does not name. A unit or
    row naming no colour is kept."""
    if not text or not allowed:
        return text
    lines = text.splitlines()
    col = _value_column(lines)
    if col is None:
        keep = []
        for u in shared_cahier._units(text, covered):
            cols = unit_colours(u[:160])
            if cols and not cols & allowed:
                continue
            keep.append(u)
        return "\n\n".join(keep)
    rows = _split(lines, col)
    heads = _headings(rows, col, covered)
    labels = _blocks(rows, "left")
    values = _blocks(rows, "right")
    drop: set[int] = set()
    for n, (i, _t) in enumerate(heads):
        drop.update(range(i, heads[n + 1][0] if n + 1 < len(heads) else len(rows)))
    for lb in labels:
        text_l = " ".join(rows[k].left for k in range(lb[0], lb[1] + 1))
        cols = unit_colours(text_l)
        if (cols and not cols & allowed) or quoted_keys(text_l) & covered:
            for a, b in [lb, *_paired(lb, values)]:
                drop.update(range(a, b + 1))
    return "\n".join(lines[k] for k in range(len(lines)) if k not in drop)
