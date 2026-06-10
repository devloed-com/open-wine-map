"""Parsers for the Czech national specifikace documents — the closest
thing the Czech wine system has to per-AOC production rules.

Two parsers, one document each:

  - **parse_varieties(html)** → variety roster from Vyhláška č. 88/2017
    Sb., Příloha č. 2. The decree's appendix groups varieties under
    three Roman-numeral headers:
        I. Bílé moštové odrůdy         (white)
        II. Modré moštové odrůdy       (red / blue)
        III. Odrůdy pro výrobu zemských vín  (zemské víno only)
    Within each header, items appear as a flat run of
    `<num>. <Variety name> <Abbreviation>` tokens. The variety roster
    is at the *national* level — Czech wine law does not restrict
    varieties per podoblast, so every CHOP / CHZO that authorises
    "jakostní víno" or "zemské víno" inherits the same roster.

  - **parse_commune_tree(html)** → per-podoblast obec list from
    Vyhláška č. 254/2010 Sb., Příloha (consolidated through Vyhláška
    č. 75/2025 Sb. effective 2025-04-01). The appendix opens with
    `A. VINAŘSKÁ OBLAST ČECHY` then numbered podoblast headings,
    then a flat numbered run of `<obec>. <katastrální území>.
    <viniční trať>` triples. For our purposes (commune-precision
    geometry) we only need the obec names per podoblast — the
    katastr / trať levels are below the cadastre granularity any
    public Czech vector dataset publishes.

The HTML is fetched from zakonyprolidi.cz (the most accessible CZ-law
mirror — e-sbirka.gov.cz is a JS SPA). The **canonical source** is the
Sbírka zákonů PDF (image-scanned, hard to parse) — the parser
attributes that URL in its output so the panel cites the legal
instrument rather than the mirror.

Czech law text is public per §3(d) of the Czech Copyright Act
(úřední dílo). Layout of the zakonyprolidi.cz site is © AION CS; we
only fetch the law text, do not republish the layout.
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata

# ─── HTML → plaintext ──────────────────────────────────────────


def strip_tags(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


# ─── Vyhláška 88/2017 Sb. — variety table ──────────────────────


_VARIETY_HEADERS: tuple[tuple[str, str], ...] = (
    # (heading-text-with-Roman-prefix, colour-bucket). The Roman prefix
    # is part of the literal terminator so block slicing cuts BEFORE
    # the "II." / "III." marker (otherwise it leaks into the prior
    # block's last entry — "Vrboska Vr II" rather than just "Vrboska Vr").
    ("I. Bílé moštové odrůdy", "blanc"),
    ("II. Modré moštové odrůdy", "noir"),
    ("III. Odrůdy pro výrobu zemských vín", "zemske"),  # mixed-colour
)

# Variety token: a 1-2-digit ordinal, dot, then the Czech variety name
# (one or more word-token segments), then an abbreviation token (1-5
# letters, possibly with comma-separated alternates like `RŠ, RS`). The
# next ordinal terminates the match.
#
# This is the strict per-line pattern: `1. Aurelius Au 2. Auxerrois Ax`.
# We split on ` <num>. ` boundaries; for each piece we strip the trailing
# abbreviation tokens to get the variety name.
_NUMBERED_SPLIT = re.compile(r"(?:^|\s)(\d{1,2})\.\s+")
# After splitting, each token tail looks like: `Aurelius Au` or
# `Veltlínské červené rané VČR, VCR` — the abbreviation is one or more
# all-caps-ish tokens (Latin caps, Czech diacritics on caps OK) with
# optional commas/spaces; capture and strip.
_TRAILING_ABBR = re.compile(
    r"(?:\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž]{0,3}"
    r"(?:\s*,\s*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{1,4})?)+\s*$"
)
# Suspicious tail tokens that aren't abbreviations (must reject). The
# `Müller Thurgau` row uses abbreviation `MT` — the `Thurgau` word is
# part of the name, not an abbreviation, so leave the rejection logic
# strict.
_BAD_NAME_TOKENS = re.compile(r"\b(?:číslo|odrůda|název|zkratka)\b", re.I)


def _parse_variety_block(block_text: str, colour: str) -> list[dict]:
    """Parse one Roman-numeral variety block. Returns a list of
    `{name, abbreviation, colour}` records."""
    out: list[dict] = []
    # Split by ` <num>. ` — keep the captures (the ordinal) interleaved
    # so we know each segment is the body of a numbered item.
    parts = _NUMBERED_SPLIT.split(block_text)
    # `_NUMBERED_SPLIT.split` returns [pre, ord1, body1, ord2, body2, …]
    if len(parts) < 3:
        return out
    # Skip parts[0] (anything before the first ordinal — the header preamble
    # like "Název odrůdy Zkratka").
    seen_ords: set[int] = set()
    for i in range(1, len(parts) - 1, 2):
        try:
            ordinal = int(parts[i])
        except ValueError:
            continue
        body = parts[i + 1].strip()
        if not body:
            continue
        # If the next ordinal would *decrease* (e.g. III → I), we have
        # crossed a sub-section boundary — stop. Tracked via seen_ords
        # in monotonic order.
        if ordinal in seen_ords and ordinal == 1:
            break
        seen_ords.add(ordinal)
        # Drop the trailing abbreviation tokens.
        m_abbr = _TRAILING_ABBR.search(body)
        if m_abbr:
            name = body[: m_abbr.start()].strip(" .,;")
            abbr = body[m_abbr.start():].strip(" ,")
        else:
            name = body.strip(" .,;")
            abbr = ""
        if not name or _BAD_NAME_TOKENS.search(name):
            continue
        # Reject obvious continuation noise (line wraps with stray
        # punctuation, headings that slipped past).
        if len(name) > 60 or len(name) < 3:
            continue
        out.append({
            "ordinal": ordinal,
            "name": name,
            "abbreviation": abbr,
            "slug": _slug(name),
            "colour": colour,
        })
    return out


def parse_varieties(html: str) -> dict:
    """Parse Vyhláška č. 88/2017 Sb. Příloha č. 2 → variety roster.
    Returns
        {
          "varieties": [{ordinal, name, abbreviation, slug, colour}, ...],
          "n_white": int, "n_red": int, "n_zemske": int,
          "source_anchor": "Příloha č. 2 k vyhlášce č. 88/2017 Sb.",
        }
    """
    text = strip_tags(html)
    # Slice from the Příloha č. 2 anchor onward (skip the act body).
    anchor = "Příloha č. 2 k vyhlášce č. 88/2017 Sb."
    idx = text.find(anchor)
    if idx < 0:
        # Permissive fallback — the abbreviation table title.
        idx = text.find("Zkratky moštových odrůd révy vinné")
    if idx < 0:
        return {"varieties": [], "n_white": 0, "n_red": 0, "n_zemske": 0,
                "source_anchor": ""}
    body = text[idx:]
    # Slice to the next Příloha boundary so trailing decree appendices
    # don't bleed in (Příloha č. 3 is the wine-defects table — different
    # numbering, would confuse the variety parser).
    next_appendix = body.find("Příloha č. 3")
    if next_appendix > 0:
        body = body[:next_appendix]

    # Block-terminator markers — any Roman-numeral header that follows a
    # variety block. III. (Odrůdy pro výrobu zemských vín) ends at IV.
    # (Seznam zkratek pro některé tradiční výrazy), which is NOT a
    # variety list but the parser needs to stop there.
    block_terminators = [h for h, _ in _VARIETY_HEADERS] + [
        "IV. Seznam zkratek",
        "Seznam zkratek pro některé tradiční výrazy",
    ]

    varieties: list[dict] = []
    for header, colour in _VARIETY_HEADERS:
        h_idx = body.find(header)
        if h_idx < 0:
            continue
        # Block ends at the next Roman-numeral header (variety section
        # or anything after it like the abbreviations table) or slice end.
        next_h = len(body)
        for term in block_terminators:
            if term == header:
                continue
            i = body.find(term, h_idx + len(header))
            if i > 0 and i < next_h:
                next_h = i
        block = body[h_idx + len(header):next_h]
        varieties.extend(_parse_variety_block(block, colour))

    return {
        "varieties": varieties,
        "n_white": sum(1 for v in varieties if v["colour"] == "blanc"),
        "n_red": sum(1 for v in varieties if v["colour"] == "noir"),
        "n_zemske": sum(1 for v in varieties if v["colour"] == "zemske"),
        "source_anchor": anchor if idx >= 0 else "",
    }


# ─── Vyhláška 254/2010 Sb. — commune tree ──────────────────────


# Pattern: `1. Vinařská podoblast mělnická` — these are the section
# headers inside Příloha. Restrict the name capture to lowercase Czech
# tokens (1-2 words max) so it does NOT bleed into the column-header
# preamble ("Vinařská obec Katastrální území Název viniční trati").
_PODOBLAST_HEADER_RE = re.compile(
    r"\b(\d+)\.\s+Vinařská\s+podoblast\s+"
    r"([a-záčďéěíňóřšťúůýž]+(?:\s+[a-záčďéěíňóřšťúůýž]+)?)"
)

# Canonical podoblast slugs (match _lib/cz/region.py + the eAmbrosia
# slugify output). The Vyhláška names them in lower-case feminine form
# (`mělnická`, `litoměřická`, `slovácká` …); the corpus slug is the
# adjective form (mělnická → melnicka, litoměřická → litomericka).
_PODOBLAST_NAME_TO_SLUG: dict[str, str] = {
    "mělnická": "melnicka",
    "litoměřická": "litomericka",
    "slovácká": "slovacka",
    "znojemská": "znojemska",
    "velkopavlovická": "velkopavlovicka",
    "mikulovská": "mikulovska",
}


def parse_commune_tree(html: str) -> dict:
    """Parse Vyhláška č. 254/2010 Sb. Příloha → per-podoblast obec list.
    Returns
        {
          "podoblasti": {
            "<slug>": {
              "name": "<canonical name>",
              "macro_region": "Čechy"|"Morava",
              "communes": ["<obec1>", "<obec2>", ...],
            },
            ...
          },
          "source_anchor": "Příloha k vyhlášce č. 254/2010 Sb.",
        }

    Implementation: the source HTML is a 3-column table per podoblast
    (Vinařská obec / Katastrální území / Název viniční trati). The
    obec cell carries `rowspan="N"` to cover the KÚ + trať rows it
    contains. We walk `<tr>` rows with a rowspan-tracking state
    machine, treating any column-0 cell as a fresh obec — which is
    correct regardless of how many KÚ/traťs it contains.
    """
    # Locate the appendix table — there's only ever one massive 3-col
    # table per podoblast in this Vyhláška, framed by the podoblast
    # heading just before it.
    anchor_kw = "Vinařské obce a viniční tratě v jednotlivých vinařských podoblastech"
    anchor_idx = html.find(anchor_kw)
    if anchor_idx < 0:
        anchor_idx = html.find("A. VINAŘSKÁ OBLAST ČECHY")
    if anchor_idx < 0:
        return {"podoblasti": {}, "source_anchor": ""}
    body_html = html[anchor_idx:]
    # The headings wrap their ordinals in `<var>1.</var>` / `<var>A.</var>`
    # markup that breaks header regex matching. Strip those wrappers
    # (and inert anchor tags) without touching the table structure.
    body_html = re.sub(r"</?var\b[^>]*>", "", body_html)
    body_html = re.sub(r"<a\b[^>]*></a>", "", body_html)

    # The body has interleaved podoblast headings + tables. Walk the
    # raw HTML, switching the active (macro_region, podoblast_slug)
    # whenever a heading matches, and feeding intervening table rows
    # through the rowspan walker.
    out_pod: dict[str, dict] = {}
    macro_region = ""
    active_slug: str | None = None
    active_name = ""
    active_communes: list[str] = []
    rowspan_active = [0, 0, 0]
    seen_obec: set[str] = set()

    def commit_current():
        if active_slug and active_communes:
            out_pod[active_slug] = {
                "name": active_name,
                "macro_region": macro_region,
                "communes": list(active_communes),
            }

    # Tokenise the body: find headings (`MACRO_BLOCK` / `PODOBLAST_HEADER`)
    # and `<tr>` boundaries in document order.
    events: list[tuple[int, str, object]] = []
    for m in re.finditer(r"A\.\s*VINAŘSKÁ\s+OBLAST\s+ČECHY", body_html):
        events.append((m.start(), "macro", "Čechy"))
    for m in re.finditer(r"B\.\s*VINAŘSKÁ\s+OBLAST\s+MORAVA", body_html):
        events.append((m.start(), "macro", "Morava"))
    for m in _PODOBLAST_HEADER_RE.finditer(body_html):
        name_raw = m.group(2).strip().lower()
        slug = _PODOBLAST_NAME_TO_SLUG.get(name_raw)
        if slug:
            events.append((m.start(), "podoblast", (slug, name_raw)))
    for m in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", body_html, re.S):
        events.append((m.start(), "tr", m.group(1)))
    events.sort(key=lambda e: e[0])

    for _pos, kind, payload in events:
        if kind == "macro":
            commit_current()
            macro_region = payload  # type: ignore[assignment]
            active_slug = None
            active_communes = []
            rowspan_active = [0, 0, 0]
            seen_obec = set()
        elif kind == "podoblast":
            commit_current()
            slug, name_raw = payload  # type: ignore[misc]
            active_slug = slug
            active_name = name_raw.capitalize()
            active_communes = []
            rowspan_active = [0, 0, 0]
            seen_obec = set()
        elif kind == "tr" and active_slug:
            obec = _row_obec(payload, rowspan_active)  # type: ignore[arg-type]
            if obec and obec not in seen_obec:
                seen_obec.add(obec)
                active_communes.append(obec)
    commit_current()

    return {
        "podoblasti": out_pod,
        "source_anchor": "Příloha k vyhlášce č. 254/2010 Sb.",
    }


# `<td …>… </td>` extractor — captures attribute block + inner HTML.
_TD_RE = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.S | re.I)
_ROWSPAN_ATTR_RE = re.compile(r'\browspan\s*=\s*"?(\d+)"?', re.I)
_COLSPAN_ATTR_RE = re.compile(r'\bcolspan\s*=\s*"?(\d+)"?', re.I)
_LEADING_ORDINAL_RE = re.compile(r"^\s*\d{1,3}\.\s*")


def _row_obec(tr_inner_html: str, rowspan_active: list[int]) -> str | None:
    """Walk one `<tr>` row with the rowspan tracker; return the obec
    name (column-0 text) if this row introduces a new obec, else None.

    Bookkeeping: `rowspan_active[c]` = how many rows (counting the
    current one as long as the value is > 0) column `c` is still
    covered by a prior cell's rowspan. The current row processes the
    free columns, activates new spans (as `rs`, count-including-current),
    and at the end decrements every active span by one.
    """
    obec_text: str | None = None
    col = 0
    for m in _TD_RE.finditer(tr_inner_html):
        attrs = m.group(1)
        inner = m.group(2)
        rs_match = _ROWSPAN_ATTR_RE.search(attrs)
        cs_match = _COLSPAN_ATTR_RE.search(attrs)
        rs = int(rs_match.group(1)) if rs_match else 1
        cs = int(cs_match.group(1)) if cs_match else 1
        # Skip over any logical columns whose prior rowspan is still
        # active (their text appeared in an earlier row).
        while col < len(rowspan_active) and rowspan_active[col] > 0:
            col += 1
        if col >= len(rowspan_active):
            break
        if col == 0:
            obec_text = _clean_cell(inner)
        # Activate the span as `rs` (the cell covers this row + the
        # next rs-1 rows). The end-of-row decrement consumes the unit
        # this row contributes.
        for c in range(col, min(col + cs, len(rowspan_active))):
            rowspan_active[c] = rs
        col += cs

    # End-of-row decrement.
    for c in range(len(rowspan_active)):
        if rowspan_active[c] > 0:
            rowspan_active[c] -= 1

    if not obec_text:
        return None
    # Strip the leading "1. " ordinal — what remains is the obec name.
    name = _LEADING_ORDINAL_RE.sub("", obec_text).strip()
    if not name or len(name) > 60:
        return None
    return name


def _clean_cell(inner_html: str) -> str:
    """Strip HTML tags + entities from a `<td>` inner body."""
    text = re.sub(r"<[^>]+>", " ", inner_html)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
