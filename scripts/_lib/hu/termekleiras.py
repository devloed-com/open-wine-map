"""Parser for the Hungarian national *termékleírás* (product specification).

The 15 grandfathered HU wines whose eAmbrosia entry carries only a
non-fetchable `Ares(...)` reference (no EU-OJ EGYSÉGES DOKUMENTUM on
EUR-Lex) have their canonical product specification published as a PDF
by the Agrárminisztérium at `boraszat.kormany.hu/termekleirasok2`
(curator-pinned direct download URLs / borvidék-council mirrors).

The document is the EU single-document template rendered in Hungarian
as a PDF, with a stable Roman-numeral outline (identical across regions,
`pdftotext -layout`):

    I.    NÉV                                  → name
    II.   A BOROK LEÍRÁSA                       → description / summary
    III.  KÜLÖNÖS BORÁSZATI ELJÁRÁSOK
    IV.   KÖRÜLHATÁROLT TERÜLET                 → delimited area / communes
    V.    MAXIMÁLIS HOZAM
    VI.   ENGEDÉLYEZETT SZŐLŐFAJTÁK             → grape varieties
    VII.  KAPCSOLAT A FÖLDRAJZI TERÜLETTEL      → link to terroir
    VIII. TOVÁBBI FELTÉTELEK
    IX.   ELLENŐRZÉS
    X.    A HEGYKÖZSÉGI FELADATOK ELLÁTÁSÁNAK RENDJE
    MELLÉKLET                                   → annex (dűlő tables; v1 unused)

Same role in the HU pipeline as the ES MAPA pliego, the IT MASAF
disciplinare, the RO ONVPV caiet and the HR/SI national specifikacija —
a national-spec augmentation layer (stage 02f + the stage-04 augment
hook). `parse_termekleiras(text, slug)` returns the same merge-able
record fragment the EU extractor's `build_record` produces.
"""

from __future__ import annotations

import re

from .commune import parse_commune_list
from .egyseges_dokumentum import COLOUR_BY_KEYWORD, STYLE_MARKERS

# Top-level Roman-numeral section header, e.g. "   IV. KÖRÜLHATÁROLT TERÜLET".
# Longest numerals first so VIII/VII/VI win over V/I at the same position.
# The title is validated below: it must be ALL-CAPS Hungarian (no lowercase)
# and carry no dotted leader — that rejects (a) the table-of-contents lines
# ("I. NÉV ........ 2"), (b) prose like Villány's "IV. Béla király 1249-ben",
# and (c) the annex's restarted "I. Strukturális elemek" headings.
_HEADER_RE = re.compile(
    r"^[ \t]*(X|IX|VIII|VII|VI|IV|V|III|II|I)\.[ \t]+"
    r"([A-ZÁÉÍÓÖŐÚÜŰ][^\n]*?)[ \t]*$",
    re.M,
)

_LOWER_RE = re.compile(r"[a-záéíóöőúüűä]")
_DOTTED_LEADER_RE = re.compile(r"\.{3,}")

# Section-title keyword → semantic role. Most-specific first; a role keeps
# the first matching section only (the outline never repeats a role).
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("grape_varieties", (
        "engedélyezett szőlőfajták", "szőlőfajták", "szőlőfajta",
    )),
    ("link_to_terroir", (
        "kapcsolat a földrajzi területtel", "földrajzi területtel",
        "kapcsolat",
    )),
    ("geo_area", (
        "körülhatárolt terület", "lehatárolt terület",
    )),
    ("description", (
        "a borok leírása", "borok leírása", "bor leírása",
    )),
)

# Repeating page-furniture lines that pdftotext interleaves into every
# section body (version banner, applicability window, "NN/37" page number,
# the running footer). Dropped before the role text is used.
_FOOTER_LINE_RE = re.compile(
    r"^\s*(?:"
    r"\d+\w*\.\s*változat,?"
    r"|\d+\s*/\s*\d+"
    r"|.*szüretelt\s+szőlőből\s+készült.*alkalmazandó.*"
    r"|.*oltalom\s+alatt\s+álló\s+(?:eredetmegjelölés|földrajzi\s+jelzés)"
    r"\s+termékleírása.*"
    r")\s*$",
    re.IGNORECASE,
)


def _strip_footers(text: str) -> str:
    text = text.replace("\x0c", "\n")
    kept = [ln for ln in text.splitlines() if not _FOOTER_LINE_RE.match(ln)]
    return "\n".join(kept)


def split_sections(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice the termékleírás text on top-level Roman-numeral headers.
    Returns (bodies_by_role, titles_by_role)."""
    text = text.replace("\x0c", "\n")
    matches = []
    for m in _HEADER_RE.finditer(text):
        title = re.sub(r"\s+", " ", m.group(2)).strip(" .")
        if _DOTTED_LEADER_RE.search(m.group(2)) or _LOWER_RE.search(title):
            continue  # TOC line / prose / annex sub-heading
        matches.append((m.start(), m.end(), title))
    if not matches:
        return {}, {}

    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (_, end, title) in enumerate(matches):
        body_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = _strip_footers(text[end:body_end]).strip()
        tlow = title.lower()
        for role, keywords in _ROLE_KEYWORDS:
            if role in bodies:
                continue
            if any(kw in tlow for kw in keywords):
                bodies[role] = body
                titles[role] = title
                break
    return bodies, titles


# Product-category subsection headers inside section VI ("1. BOR",
# "2. PEZSGŐ", "3. FÔBOR") and bare colour headers — dropped so the
# comma-list of varieties is what reaches the matcher.
_GRAPE_HEADER_RE = re.compile(r"^\s*(?:\d+\.\s*)?[A-ZÁÉÍÓÖŐÚÜŰ]{2,}\s*:?\s*$")
# Table column headers seen in the tabular variety layout (Balatonboglár,
# Pécs, …): "Terméktípus    Engedélyezett fajták".
_GRAPE_TABLE_HEADER_RE = re.compile(r"termékt[ií]pus|engedélyezett\s+fajt", re.I)


def parse_grapes(body: str) -> dict:
    """Parse section VI (ENGEDÉLYEZETT SZŐLŐFAJTÁK) into the
    {principal, accessory, observation, details} shape. The national
    spec carries no principal/accessory split — every variety is
    `principal`; colour comes from the matcher.

    Two layouts occur: a flat comma list (Tokaj, Villány) and a 2-column
    table whose left cell is the product type ("1. Fehér" / "2. Rozé")
    and right cell the wrapped comma list. Splitting on runs of 2+ spaces
    (the column gap) as well as commas peels the type label off the first
    variety in each table row."""
    from ..grape_entity import match_variety

    out: dict[str, list] = {
        "principal": [], "accessory": [], "observation": [], "details": [],
    }
    if not body:
        return out
    seen: set[str] = set()
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or _GRAPE_HEADER_RE.match(line) or _GRAPE_TABLE_HEADER_RE.search(line):
            continue
        for cand in re.split(r"\s*[,;]\s*|\s{2,}|\s+és\s+", line):
            cand = cand.strip(" .\t-•·()")
            if len(cand) < 3:
                continue
            match = match_variety(cand)
            if match is None:
                continue
            slug = match.slug
            if slug in seen:
                continue
            seen.add(slug)
            out["principal"].append(slug)
            out["details"].append({
                "slug": slug,
                "name": cand,
                "role": "principal",
                "colour": match.colour,
            })
    return out


def parse_styles(bodies: dict[str, str], grapes: dict) -> list[str]:
    blob = " ".join(
        bodies.get(r, "") for r in ("description", "grape_varieties", "link_to_terroir")
    )
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob, re.I):
            found.add(colour_slug)
    for pattern, slug in STYLE_MARKERS:
        if pattern.search(blob):
            found.add(slug)
    _colour_to_style = {"blanc": "blanc", "noir": "noir", "gris": "rose", "rose": "rose"}
    for d in grapes.get("details") or []:
        s = _colour_to_style.get(d.get("colour") or "")
        if s:
            found.add(s)
    return sorted(found)


def _derive_summary(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def parse_termekleiras(text: str, slug: str) -> dict:
    """Parse `pdftotext -layout` text of one HU termékleírás into a
    merge-able record fragment (same shape as the RO caiet parser)."""
    bodies, titles = split_sections(text)
    grapes = parse_grapes(bodies.get("grape_varieties", ""))
    geo_area = bodies.get("geo_area", "")
    geo_communes = parse_commune_list(geo_area) if geo_area else []
    link = (bodies.get("link_to_terroir") or "").strip()
    summary = _derive_summary(bodies.get("description") or geo_area or "")
    return {
        "summary": summary,
        "grapes": grapes,
        "geo_area_brief": _derive_summary(geo_area, max_chars=2000),
        "geo_communes": geo_communes,
        "link_to_terroir": link,
        "styles": parse_styles(bodies, grapes),
        "section_roles": {
            "description": bodies.get("description", ""),
            "geo_area": geo_area,
            "grape_varieties": bodies.get("grape_varieties", ""),
            "link_to_terroir": link,
        },
        "section_titles": titles,
        "n_sections": len(bodies),
        "n_grapes": len(grapes["details"]),
        "parser_template": "hu-termekleiras-v1",
    }
