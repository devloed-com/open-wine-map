"""A roster table's label lines, moved off a wrapped variety name (FR section V).

`pdftotext -layout` prints a two-column encépagement table with its row labels
("Vins blancs", "Vins rouges et rosés", the adaptation-variety clause) in the
left column, vertically centred on the row's value lines. A label line can
therefore sit between the two halves of a wrapped variety name — Coteaux
Varois's "… semillon B, ugni / Vins blancs / blanc B, vermentino B.", whose
card lacked Ugni blanc — and a label's prose can share a physical line with the
values — Alsace's "… l'ODG et Voltis B, …, Johanniter / les opérateurs habilités
concernés, d'une convention B, Chenin B", whose Johanniter was lost (card
re-grade of 2026-10-30).

`repair_label_interleave` moves such a left-column stretch above the value line
it interrupts, and only then: the move is made when the two halves form an
exact lexicon surface followed by a colour code (`grape_entity.exact_match`),
so everywhere else the lines stay as printed and `parse_grapes` reads what it
read before (2026-11-07).
"""

from __future__ import annotations

import re

from _lib.fr.dgc_rules import _value_column

_CODE_AFTER = re.compile(r"^(?:B|N|G|Rs|Rg)\b")
_CODE_END = re.compile(r"\b(?:B|N|G|Rs|Rg)\s*$")


def _joins(prev_right: str, right: str) -> bool:
    """Do the last word(s) of `prev_right` and the first of `right` form one
    variety name, closed by a colour code?"""
    from _lib.grape_entity import exact_match  # noqa: PLC0415

    a = prev_right.rstrip()
    if not a or a[-1] in ",;.:" or _CODE_END.search(a):
        return False
    a_words = a.split()
    b_tokens = right.split()
    if not b_tokens:
        return False
    for n_a in (1, 2):
        if len(a_words) < n_a:
            break
        tail = a_words[-n_a:]
        for n_b in (0, 1, 2):
            if len(b_tokens) <= n_b or not _CODE_AFTER.match(b_tokens[n_b]):
                continue
            name = " ".join(tail + b_tokens[:n_b])
            if exact_match(name) is not None:
                return True
    return False


def _columns(line: str, col: int) -> tuple[str, str]:
    """Left / right text of a physical line, cut at the value column: a label's
    prose can run up to one space before the values ("… l'ODG et Voltis B"),
    which `dgc_rules._split` reads as one run."""
    left: list[str] = []
    right: list[str] = []
    for m in re.finditer(r"\S+", line):
        (right if m.start() >= col - 3 and (right or m.start() >= col - 3) else left).append(m.group())
    return " ".join(left), " ".join(right)


def repair_label_interleave(text: str) -> str:
    lines = text.splitlines()
    col = _value_column(lines)
    if col is None:
        return text
    rows = [_columns(ln, col) for ln in lines]
    out: list[str] = []
    left_of: list[str] = []
    right_of: list[str] = []
    prev_right: int | None = None
    pending: list[int] = []
    moved = False

    def emit(line: str, left: str, right: str) -> None:
        out.append(line)
        left_of.append(left)
        right_of.append(right)

    for i, (left, right) in enumerate(rows):
        if not right:
            if prev_right is None:
                emit(lines[i], left, "")
            else:
                pending.append(i)
            continue
        interleaved = [rows[j][0] for j in pending if rows[j][0]] + ([left] if left else [])
        if prev_right is not None and interleaved and _joins(right_of[prev_right], right):
            # the previous value line, its own label first, then the label text
            # that sat inside the wrapped name, then the two value halves
            moved_text = ([left_of[prev_right]] if left_of[prev_right] else []) + interleaved
            out[prev_right] = right_of[prev_right]
            left_of[prev_right] = ""
            out[prev_right:prev_right] = moved_text
            left_of[prev_right:prev_right] = moved_text
            right_of[prev_right:prev_right] = [""] * len(moved_text)
            emit(right, "", right)
            moved = True
        else:
            for j in pending:
                emit(lines[j], rows[j][0], "")
            emit(lines[i], left, right)
        pending = []
        prev_right = len(out) - 1
    if not moved:
        return text
    out.extend(lines[j] for j in pending)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")
