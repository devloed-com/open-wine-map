"""Parser for the dűlő (named single-vineyard) annex of a Hungarian
termékleírás.

Hungarian product specifications carry a MELLÉKLET ("Feltüntethető
kisebb földrajzi egységek" — registrable smaller geographic units) whose
**Dűlők** section is a 3-column table:

    település megnevezése   |  dűlőnév megnevezése  |  aldűlő megnevezése
    Abaújszántó                Bea                     Alsó-Bea, Felső-Bea
    Abaújszántó                Sulyom                  Délrefekvő-Sulyom, …
    Bekecs                     Nagy-hegy               Kozér, Kutyafogó, …

A dűlő is the Hungarian "cru" / named-vineyard granularity (the FR climat
/ IT MGA·UGA / ES paraje analogue). Tokaj alone enumerates ~450 of them.
Like the IT menzioni/UGA decision, this granularity is NOT modelled as
sub-denomination records (no per-dűlő polygons exist publicly) — it is a
flat, source-attributed chip list (`dulok`) grouped by település on the
parent appellation's panel + wiki page.

v1 supports the canonical 3-column `… megnevezése` table (Tokaj — 427
dűlők across 27 települések). Other layouts seen in the corpus — Villány's
"2-up" carry-forward table (két település|dűlő oszloppár egy soron) and
the specs that only define dűlőnév *rules* without enumerating a list —
are a Phase-2 follow-up (see CURATOR_TODO); a fragile parse that
mis-attributes a dűlő to the wrong village is worse than none.

`parse_dulok(text)` takes the `pdftotext -layout` text of a termékleírás
and returns a list of `{"telepules", "dulo", "aldulok": [...]}`.
"""

from __future__ import annotations

import re

from .termekleiras import _strip_footers

_LETTER = r"[A-Za-zÁÉÍÓÖŐÚÜŰ]"

# The Dűlők-table column header — "település megnevezése  dűlőnév
# megnevezése  aldűlő megnevezése". Requiring "megnevez" on both the
# település and dűlő columns is what keeps narrative prose (e.g. section
# IX's "Település- és dűlőnév használata") from matching as a header.
_DULO_HEADER_RE = re.compile(
    r"telep[üu]l[eé]s\s+megnevez.*d[űu]l[őo]\w*\s+megnevez", re.IGNORECASE)
# A standalone "Dűlők" section heading (precedes the header on its own line).
_DULO_SECTION_RE = re.compile(r"^\s*D[űu]l[őo]k\s*$", re.IGNORECASE)

# Lines that are not dűlő rows even after footer-stripping: the leading
# "Települések" comma-list block and the "körülhatárolás:" line that sit
# above the Dűlők table, plus the annex title.
_NON_ROW_RE = re.compile(
    r"^\s*(?:telep[üu]l[eé]sek\b|k[öo]r[üu]lhat[áa]rol|mell[eé]klet\b|"
    r"felt[üu]ntethet|kisebb\s+f[öo]ldrajzi)",
    re.IGNORECASE,
)


def parse_dulok(text: str) -> list[dict]:
    """Extract the dűlő rows from a termékleírás. Returns
    [{telepules, dulo, aldulok:[...]}, ...] in document order; empty if
    the spec carries no canonical Dűlők table."""
    if not text:
        return []
    lines = _strip_footers(text).split("\n")

    start = None
    for i, ln in enumerate(lines):
        if _DULO_HEADER_RE.search(ln):
            start = i + 1
            break
    if start is None:
        return []

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    last_telepules = ""
    for ln in lines[start:]:
        if not ln.strip():
            continue
        if _DULO_HEADER_RE.search(ln) or _DULO_SECTION_RE.match(ln) or _NON_ROW_RE.match(ln):
            continue
        # Columns are separated by runs of 2+ spaces (pdftotext -layout).
        cols = [c.strip() for c in re.split(r"\s{2,}", ln.strip()) if c.strip()]
        if not cols:
            continue
        if len(cols) == 1:
            # A lone token: a continuation dűlő under the previous
            # település (cell left blank), or stray prose. Keep a short
            # alphabetic token as a dűlő; reject long prose.
            tok = cols[0]
            if last_telepules and len(tok.split()) <= 4 and re.search(
                    _LETTER, tok) and not tok.endswith((":", ".")):
                telepules, dulo, aldulok = last_telepules, tok, []
            else:
                continue
        else:
            telepules, dulo = cols[0], cols[1]
            aldulok = []
            if len(cols) >= 3:
                aldulok = [a.strip() for a in re.split(r"\s*,\s*", cols[2]) if a.strip()]
            last_telepules = telepules
        if not (telepules and dulo) or not re.search(_LETTER, dulo):
            continue
        key = (telepules.casefold(), dulo.casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"telepules": telepules, "dulo": dulo, "aldulok": aldulok})
    return rows


def group_by_telepules(dulok: list[dict]) -> list[tuple[str, list[str]]]:
    """Group parsed dűlők by település (order preserved). Each dűlő name
    carries its aldűlők appended in parentheses when present."""
    out: list[tuple[str, list[str]]] = []
    index: dict[str, int] = {}
    for row in dulok:
        tel = row["telepules"]
        name = row["dulo"]
        if row.get("aldulok"):
            name = f"{name} ({', '.join(row['aldulok'])})"
        if tel not in index:
            index[tel] = len(out)
            out.append((tel, []))
        out[index[tel]][1].append(name)
    return out
