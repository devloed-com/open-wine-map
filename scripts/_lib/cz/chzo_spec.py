"""Parser for the two Czech CHZO (PGI / "zemské víno") product
specifications published by the SZPI (Státní zemědělská a potravinářská
inspekce — the Czech Food Inspection Authority):

  - Specifikace CHZO „moravské"  → moravské zemské víno (PGI-CZ-A0902)
  - Specifikace CHZO „české"     → české zemské víno  (PGI-CZ-A0900)

Both are genuine full EU-template product specifications (numbered
sections 1–9). Unlike the Czech CHOP (PDO) tier — for which the
regulator publishes only the national variety roster + commune decrees
(no per-appellation narrative) — these two CHZO specs carry the two
narrative layers the rest of the corpus relies on:

  - **Section 1 (Popis vinařského regionu / oblasti)** — the regulator's
    description of the wine region's terroir: 1.1 meteorology (ČHMÚ
    30-year climate normals, Huglin index) and 1.2 geology + soils, with
    per-bioregion (≈ per-podoblast) soil prose. This is tier-agnostic —
    it describes the *physical* Morava / Čechy wine region, so it is the
    correct terroir source for every CZ wine that sits in that region
    (the 9 Moravian + 4 Bohemian appellations), not only the PGI.
  - **Section 2 (Druhy výrobků — popis vín)** — per-style organoleptic
    descriptions, one subsection per wine type: still (2.1, split into
    Bílé / Růžové / Červené), Likérové víno (2.2 → vin-de-liqueur),
    Šumivé víno (2.3 → sparkling), Perlivé víno (2.4 + 2.5 →
    semi-sparkling), Částečně zkvašený mošt (2.6 → grape must, not a
    wine style). These authorise the real style roster for the PGI tier.

Czech law / regulator documents are public per §3(d) of the Czech
Copyright Act (úřední dílo). The SZPI PDF is the canonical source; the
parser attributes its URL so the panel cites the regulator.
"""

from __future__ import annotations

import re

# Region → PGI file number. Both regions' macro CHOP + podoblasti also
# draw their terroir grounding from the same region spec (see module
# docstring), but only the PGI is the spec's own subject.
CHZO_PGI_FILE_NUMBER = {
    "moravske": "PGI-CZ-A0902",
    "ceske": "PGI-CZ-A0900",
}

# Czech wine region the spec describes (native form, matches record["region"]).
CHZO_REGION = {
    "moravske": "Morava",
    "ceske": "Čechy",
}

# Style markers scanned in section 2 (Druhy výrobků). Czech wine-type
# names → canonical taxonomy slugs (style_taxonomy.py).
_STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\blikérov", re.I), "vin-de-liqueur"),
    (re.compile(r"\bšumiv", re.I), "sparkling"),
    (re.compile(r"\bperliv", re.I), "semi-sparkling"),
)

# Colour words in the section-2 still-wine subsection headers.
_COLOUR_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bbíl[éýáeo]", re.I), "white"),
    (re.compile(r"\brůžov", re.I), "rose"),
    (re.compile(r"\bčerven", re.I), "red"),
)

# A numbered section header line: `1   Popis…`, `1.1 Zhodnocení…`,
# `2.3 Šumivé víno`. pdftotext -layout keeps the leading number + tab/
# spaces. We only need the top-level + first sub-level.
_SECTION_RE = re.compile(r"(?m)^[ \t]*(\d+)(?:\.(\d+))?[ \t]+(\S.*)$")


def _sections(text: str) -> list[tuple[int, int | None, str, int]]:
    """Return (top, sub, title, char_offset) for every numbered header,
    in document order."""
    out = []
    for m in _SECTION_RE.finditer(text):
        top = int(m.group(1))
        sub = int(m.group(2)) if m.group(2) else None
        title = re.sub(r"\s+", " ", m.group(3)).strip()
        out.append((top, sub, title, m.start()))
    return out


def _slice_top_section(text: str, want: int) -> str:
    """Return the body of top-level section `want` — from its header to
    the next top-level (sub=None) header with a different number."""
    heads = _sections(text)
    start = None
    end = len(text)
    for i, (top, sub, _title, off) in enumerate(heads):
        if top == want and sub is None and start is None:
            start = off
            # find the next top-level header after this one
            for top2, sub2, _t2, off2 in heads[i + 1:]:
                if sub2 is None and top2 != want:
                    end = off2
                    break
            break
    if start is None:
        return ""
    return text[start:end].strip()


def parse_chzo_spec(text: str, slug: str) -> dict:
    """Parse one SZPI CHZO spec (`pdftotext -layout` output).

    `slug` is `moravske` or `ceske`.

    Returns:
      region              — Morava / Čechy
      pgi_file_number     — the PGI this spec belongs to
      region_terroir_text — section 1 body (region intro + 1.1 climate +
                            1.2 geology/soils); the terroir-grounding text
      styles              — style slugs authorised (section 2)
      source_anchor       — the section-1 heading
    """
    region_block = _slice_top_section(text, 1)
    styles_block = _slice_top_section(text, 2)

    # Clean the region terroir text: collapse runs of blank lines, drop
    # the page-footer noise pdftotext leaves between pages.
    terroir = re.sub(r"[ \t]+", " ", region_block)
    terroir = re.sub(r"\n{3,}", "\n\n", terroir).strip()

    styles: set[str] = set()
    for pat, style_slug in _STYLE_MARKERS:
        if pat.search(styles_block):
            styles.add(style_slug)
    for pat, colour_slug in _COLOUR_MARKERS:
        if pat.search(styles_block):
            styles.add(colour_slug)

    source_anchor = ""
    m = _SECTION_RE.search(region_block)
    if m:
        source_anchor = re.sub(r"\s+", " ", m.group(0)).strip()

    return {
        "region": CHZO_REGION.get(slug, ""),
        "pgi_file_number": CHZO_PGI_FILE_NUMBER.get(slug, ""),
        "region_terroir_text": terroir,
        "styles": sorted(styles),
        "source_anchor": source_anchor,
    }
