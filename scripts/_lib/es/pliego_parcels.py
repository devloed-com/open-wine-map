"""Parse SIGPAC polygon + parcela inclusion lists from Spanish pliego text.

Spanish wine pliegos that share communes with neighbouring DOPs (Priorat
↔ Montsant being the canonical example) split each shared commune at
SIGPAC-polygon level. The pliego text encodes this with phrases like:

  "la parte norte del municipio de Falset comprendida por los polígonos
  números 1, 4, 5, 6, 7, 21 y 25 enteros; y por las parcelas 38, 39,
  40, 71, 92 ... del polígono n.º 2"

This module extracts:

  - **whole-polygon inclusions** per municipio: `{municipio: {pol_num,
    pol_num, ...}}`
  - (future) parcela-level inclusions: `{municipio: {pol_num: {parcela_num,
    ...}}}` — not implemented in v1; whole-polygon coverage is enough for
    the Priorat/Montsant overlap fix.

The output feeds into `scripts/_lib/es/sigpac.py:SigpacIndex.polygons_in_municipi`
to compute parcel-precision (Multi)Polygons.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _normalise_municipi(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    for art in ("el ", "la ", "els ", "les ", "lo ", "los ", "las "):
        if s.startswith(art):
            s = s[len(art):]
    return s


@dataclass
class PolygonInclusion:
    """Whole-polygon inclusion for one municipio."""
    municipio: str  # Catalan/Spanish name as it appears in the pliego
    municipio_norm: str
    polygon_numbers: set[int]


# Polygon-list inner pattern. Accepts:
#   - comma-separated:   `1, 4, 5`
#   - " y / i " bridge:  `21 y 25` (Spanish/Catalan "and")
#   - hyphen range:      `1-7`
#   - dotted enum:       `1. 4. 5`
#   - "del N al N" range:  `del 11 al 16`
#   - plain " al " range:  `7 al 11`
# The trailing "ambos incluidos" / "inclusive estos" of a closed range
# is not part of the list and is simply left unmatched.
_NUMBER_LIST_INNER = (
    r"\d+"
    r"(?:"
    r"\s*[,;.]\s*\d+"            # ", 4"
    r"|\s+(?:y|i|hasta\s+el)\s+\d+"  # " y 25"
    r"|\s*-\s*\d+"               # "-7"
    r"|,?\s*del?\s+\d+\s+al\s+\d+"  # ", del 11 al 16"
    r"|\s+al\s+\d+"              # " al 11"
    r")*"
)

# A closed-range list with no bare number in front: "del 1 al 12 y del
# 18 al 29" / "del 33 al 42" (Sierra Sur de Jaén). Kept apart from the
# comma form because POLYGONS_LIST_RE demands a leading "N," to stay
# clear of "polígono 19 parcelas …" references.
_RANGE_LIST = (
    r"del?\s+\d+\s+al\s+\d+"
    r"(?:\s*(?:,|;|\s(?:y|i|e))\s*del?\s+\d+\s+al\s+\d+)*"
)

# The keyword that opens a polygon list. Pliegos write "polígonos
# números", "polígonos n.º", "polígonos catastrales" (Rueda, Campo de
# Borja, Valdejalón) and "polígonos catastrales actuales" (Sierra Sur de
# Jaén); the qualifiers are optional and never change the meaning.
_POLYGONS_KW = (
    r"pol[ií]gonos?\s+(?:catastrales\s+)?(?:actuales\s+)?"
    r"(?:números?\s+|n\s*[ºo°]?\s*\.?\s*)?"
)

# Pattern A — "X polígonos números 1, 4, 5, 6, 7, 21 y 25 enteros".
# `enteros` is the keyword that says "the whole polygon is included".
WHOLE_POLYGONS_RE = re.compile(
    _POLYGONS_KW
    + rf"(?P<list>{_NUMBER_LIST_INNER})"
    r"\s*enteros?\b",
    re.IGNORECASE,
)

# Pattern B — "Los polígonos números 8, 9, ..., 30 y 31" or
# "Polígonos 1, 2, 3, del 11 al 16" (no `enteros` keyword but the
# format is clearly enumerative). Requires *plural* polígonos and a
# multi-number list, otherwise we'd false-positive on "polígono 19" /
# "del polígono n.º 2" style references that introduce parcela lists.
POLYGONS_LIST_RE = re.compile(
    r"(?<![\.\d])(?:los\s+)?"
    + _POLYGONS_KW
    + r"(?P<list>\d+\s*[,;]\s*"  # at least one comma to ensure multi-number
    rf"{_NUMBER_LIST_INNER}"
    rf"|{_RANGE_LIST})",
    re.IGNORECASE,
)

# Two anchor forms:
#  A. "del municipio de X" / "del término municipal de X" / "el municipio
#     de X" — explicit municipio reference (Priorat-pliego style). The
#     name candidate must START with an uppercase letter so we don't
#     match function words like "del polígono".
#  B. Line-start colon header: "Falset:\n" — Montsant-pliego style block
#     header per municipi. Stricter — capitalized first letter, name ≥3
#     chars, not in a stopword set.
MUNICIPIO_ANCHOR_RE = re.compile(
    r"(?:del?\s+(?:municipio|t[eé]rmino\s+municipal)\s+"
    r"(?:de(?:l)?\s+)?)"
    r"(?P<name>[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]{1,40}?)"
    r"(?=[,;:\n)]|\s+(?:y|i|comprendid|los|que|polígono))",
)

# Block-header colon anchor.
COLON_MUNI_ANCHOR_RE = re.compile(
    r"(?:^|\n)\s*(?P<name>[A-ZÀ-ÿ][A-Za-zÀ-ÿ' ]{2,40}?)\s*:\s*\n",
    re.MULTILINE,
)

# C. Parenthetical anchor: "Alcaudete (polígonos catastrales actuales del
#    1 al 12 …) y Martos (polígonos …)" (Sierra Sur de Jaén), "Órbita
#    (polígonos catastrales 1, 2, 4 y 5)" (Rueda). The name is the
#    capitalised run right before the bracket; a run that swallowed an
#    earlier list item ("Los Villares y Valdepeñas") keeps only the part
#    after the last "y" / "i" / "e".
PAREN_MUNI_ANCHOR_RE = re.compile(
    r"(?P<name>[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ' ]{1,40}?)\s*\(\s*(?=pol[ií]gonos)",
)

# D. Post-anchor: "los polígonos catastrales número 4, 5, … y 11 del
#    término municipal de Mallén" (Campo de Borja) — the municipio comes
#    AFTER its list, so a list followed by this phrase binds to that
#    name rather than to the closest preceding anchor.
POST_MUNI_ANCHOR_RE = re.compile(
    r"\s*del?\s+t[eé]rmino\s+municipal\s+de(?:l)?\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ' ]{1,40}?)"
    r"(?=[,;:\n).]|\s+(?:y|i|e)\s|$)",
)

# Stopwords that look like names but aren't (Spanish/Catalan function
# words that may end up at the start of a fragment).
_ANCHOR_STOPWORDS = frozenset({
    "los", "las", "el", "la", "els", "les", "lo",
    "polígono", "poligono", "polígonos", "poligonos",
    "capítulo", "capitulo", "parcela", "parcelas",
    "del", "que", "ha", "y", "i", "o",
    "comprendida", "comprendido",
})


def _parse_number_list(s: str) -> set[int]:
    """Parse "1, 4, 5, 6, 7, 21 y 25" / "8, ... 30 y 31" / "1 al 5"
    (range) / "del 11 al 16" (prefixed range) into a set of integers."""
    out: set[int] = set()
    s = re.sub(r"\s+(?:y|i)\s+", ",", s)
    # Drop "del" prefix that may appear before a range ("del 11 al 16").
    s = re.sub(r",?\s*del?\s+(\d+\s+al)", r",\1", s, flags=re.IGNORECASE)
    # Expand ranges: "X al Y" / "X-Y" / "X hasta el Y".
    s = re.sub(
        r"(\d+)\s*(?:hasta\s+el|al|-)\s*(\d+)",
        lambda m: ",".join(str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1)),
        s,
        flags=re.IGNORECASE,
    )
    for tok in re.split(r"[,;.]\s*|\s+", s):
        tok = tok.strip()
        if tok.isdigit():
            out.add(int(tok))
    return out


def parse_polygon_inclusions(text: str) -> list[PolygonInclusion]:
    """Extract per-municipio whole-polygon inclusions from a pliego's
    geographical area text.

    Two pliego layouts are handled:

      A. "la parte norte del municipio de Falset comprendida por los
         polígonos números 1, 4, 5, 6, 7, 21 y 25 enteros …" (Priorat
         style — inline `del municipio de X` anchor + `enteros` keyword)

      B. "Falset:\\nLos polígonos números 8, 9, 10, ..., 30 y 31;\\n…"
         (Montsant style — colon-anchored block header per municipio,
         no `enteros` keyword)

    Strategy: collect anchors from both patterns, then for each polygon
    mention find the closest preceding anchor and attribute the polygon
    set to that municipio."""
    # Pattern A anchors: del/el municipio de X (inline)
    inline_anchors = [
        (m.start(), m.group("name").strip().rstrip(",;:."))
        for m in MUNICIPIO_ANCHOR_RE.finditer(text)
        if m.group("name").strip().lower() not in _ANCHOR_STOPWORDS
    ]
    # Pattern B anchors: line-start NAME: (block header)
    colon_anchors = [
        (m.start(), m.group("name").strip())
        for m in COLON_MUNI_ANCHOR_RE.finditer(text)
        if m.group("name").strip().lower() not in _ANCHOR_STOPWORDS
    ]
    # Pattern C anchors: NAME (polígonos …). The anchor position is the
    # bracket, so it is the closest preceding anchor for its own list.
    paren_anchors = []
    for m in PAREN_MUNI_ANCHOR_RE.finditer(text):
        name = re.split(r"\s+(?:y|i|e)\s+", m.group("name").strip())[-1].strip()
        if name and name.lower() not in _ANCHOR_STOPWORDS:
            paren_anchors.append((m.end() - 1, name))
    anchors = sorted(inline_anchors + colon_anchors + paren_anchors, key=lambda a: a[0])

    by_muni_norm: dict[str, PolygonInclusion] = {}

    # Strict pass: enteros-marked polygons (Pattern A)
    for m in WHOLE_POLYGONS_RE.finditer(text):
        _attribute(m, text, anchors, _parse_number_list(m.group("list")), by_muni_norm)

    # Soft pass: any "polígonos N, N, N" enumeration. Avoid double-counting
    # by skipping mentions whose start position overlaps an enteros match.
    enteros_spans = {(m.start(), m.end()) for m in WHOLE_POLYGONS_RE.finditer(text)}
    for m in POLYGONS_LIST_RE.finditer(text):
        if any(s <= m.start() < e for s, e in enteros_spans):
            continue
        _attribute(m, text, anchors, _parse_number_list(m.group("list")), by_muni_norm)

    return list(by_muni_norm.values())


def _attribute(
    match: re.Match,
    text: str,
    anchors: list[tuple[int, str]],
    polygons: set[int],
    out: dict[str, PolygonInclusion],
) -> None:
    """Bind `polygons` to a municipio — the "del término municipal de X"
    phrase right after the list when there is one, else the closest
    preceding anchor — and add them to that municipio's inclusion set
    in `out` (in-place)."""
    if not polygons:
        return
    municipio = None
    post = POST_MUNI_ANCHOR_RE.match(text, match.end())
    if post and post.group("name").strip().lower() not in _ANCHOR_STOPWORDS:
        municipio = post.group("name").strip()
    else:
        for anchor_pos, anchor_name in anchors:
            if anchor_pos < match.start():
                municipio = anchor_name
            else:
                break
    if not municipio:
        return
    norm = _normalise_municipi(municipio)
    existing = out.get(norm)
    if existing:
        existing.polygon_numbers.update(polygons)
    else:
        out[norm] = PolygonInclusion(
            municipio=municipio,
            municipio_norm=norm,
            polygon_numbers=polygons,
        )
