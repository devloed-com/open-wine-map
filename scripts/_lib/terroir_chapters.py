"""Own-chapter window inside a cahier shared by several appellations.

INAO publishes one cahier des charges for the 51 Alsace grands crus. Its
section X ("Lien au terroir") is one 339 KB text that repeats, per cru, a
chapter headed `« Alsace grand cru <Cru> »` followed by the usual
`1°- / 2°- / 3°-` sub-sections. Stage 02 does not split shared cahiers
(CLAUDE.md), so every cru record carries the whole lien, and the 02d
slicer — which keys spans by section number — used to grade every cru
against the LAST chapter (Zotzenberg, alphabetically last): 51 pages
carried Zotzenberg's geology, slope and 1992 date (2026-09-11 review).

`own_chapter` returns the (start, end) window of the record's own
chapter so the slicer and the audit can restrict the lien to it. A
chapter heading is a guillemet-quoted `« <prefix> <name> »` on its own
line immediately followed by the `1°` anchor; names are compared
accent-folded and case-folded.
"""

from __future__ import annotations

import re
import unicodedata

DEFAULT_PREFIX = "Alsace grand cru"
_ANCHOR_1 = r"\s*1°"


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().replace("’", "'").split())


def chapter_windows(lien: str, prefix: str = DEFAULT_PREFIX) -> list[tuple[str, int, int]]:
    """[(chapter name, start, end)] for every chapter heading in `lien`,
    in document order; `end` is the next chapter's start (or len(lien))."""
    rx = re.compile(r"«\s*" + re.escape(prefix) + r"\s+([^»\n]{1,80}?)\s*»[ \t]*\n" + _ANCHOR_1)
    heads = [(m.group(1).strip(), m.start()) for m in rx.finditer(lien)]
    out: list[tuple[str, int, int]] = []
    for i, (name, start) in enumerate(heads):
        end = heads[i + 1][1] if i + 1 < len(heads) else len(lien)
        out.append((name, start, end))
    return out


def is_shared(lien: str, prefix: str = DEFAULT_PREFIX) -> bool:
    return len(chapter_windows(lien, prefix)) > 1


def own_chapter(lien: str, record_name: str, prefix: str = DEFAULT_PREFIX) -> tuple[int, int] | None:
    """Window of the chapter whose heading names `record_name` (with or
    without the shared prefix), or None when the lien has several chapters
    but none is this record's — the caller must not fall back to another
    cru's chapter."""
    windows = chapter_windows(lien, prefix)
    if len(windows) < 2:
        return None
    want = fold(record_name)
    pfx = fold(prefix)
    if want.startswith(pfx):
        want = want[len(pfx):].strip()
    for name, start, end in windows:
        if fold(name) == want:
            return start, end
    return None
