"""Parser for the ONVPV national *caiet de sarcini* (the Romanian
national product specification for DOC/DOP and IG/IGP wines).

The national caiet is a separate document from the EU-OJ DOCUMENT UNIC
that `scripts/ro/02_extract_pliegos.py` parses. It is published as a
PDF by the Oficiul Național al Viei și Produselor Vitivinicole
(`onvpv.ro`) and is the canonical source for the ~14 grandfathered RO
wines whose eAmbrosia entry carries only a non-fetchable `Ares(...)`
reference. Same role in the RO pipeline as the ES MAPA pliego, the IT
MASAF disciplinare, the HR/SI national specifikacija and the GR ΥΠΑΑΤ
προδιαγραφή — a national-spec augmentation layer (stage 02f + the
stage-04 augment hook).

Document shape (uniform across DOC and IG caiete, `pdftotext -layout`):

    I.   Definiţie                                  → summary
    II.  Legătura cu aria geografică                → link to terroir
    III. Delimitarea geografică şi administrativă   → area / commune list
         (IG variant: "III. Arealul delimitat …"; the area is grouped by
          `judeţul X:` headers + `municipiul/Comuna/Oraş NAME - sate …`,
          or by `N. Podgoria NAME, din judeţul Y, cu următoarele
          localităţi:` for IGs)
    IV.  Soiurile de struguri                       → grapes
         (`Soiurile albe:` / `Soiuri roşii:` colour headers; comma list)
    V.–X. yields / oenology / labelling             → (unused in v1)

`parse_caiet(text, slug)` returns the same record-fragment shape the EU
extractor's `build_record` produces for the merge-able fields, so the
stage-04 augment hook can splice it into the in-memory stub record.
"""

from __future__ import annotations

import re

from .commune import parse_commune_list
from .document_unic import COLOUR_BY_KEYWORD, STYLE_MARKERS

# Late import — grape_entity lives one package up. Imported lazily inside
# the function to keep this module importable without the heavy lexicon
# when only the section splitter is needed.


# Top-level Roman-numeral section header, e.g. "III. Delimitarea …".
# Longest numerals first so "IV"/"IX"/"XII" win over "I"/"X" at the same
# position; the title must begin with a capital (Romanian incl. Ș/Ț/Î/Â/Ă)
# so numbered subsections like "II.1 Relieful" (digit after the dot) and
# "III.1." don't register as new top-level sections.
# Note the `\s*` (not `\s+`) after the dot: some caiete print the header
# with no space — "III.Delimitarea teritorială" (Viile Caraşului). The
# capital-letter requirement on the title still excludes numbered
# subsections ("II.1 Relieful" — digit after the dot).
_SECTION_HEADER_RE = re.compile(
    r"^[ \t]*(VIII|XII|VII|XI|VI|IV|IX|III|II|I|V|X)[.\)]\s*"
    r"([A-ZȘŞȚŢÎÂĂ][^\n]*)",
    re.M,
)

# Section-title keyword → semantic role. Most-specific first.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("grape_varieties", (
        "soiurile de struguri", "soiuri de struguri",
        "soiul/soiurile", "soiurile autorizate", "soiuri autorizate",
        "soiurile cultivate",
    )),
    ("geo_area", (
        "delimitarea geografică şi administrativă",
        "delimitarea geografica si administrativa",
        "delimitarea geografică", "delimitarea geografica",
        "arealul delimitat", "delimitarea arealului",
        "delimitarea teritorială", "delimitarea teritoriala",
        "arealul de producere", "areal delimitat",
    )),
    ("link_to_terroir", (
        "legătura cu aria geografică", "legatura cu aria geografica",
        "legătura cu aria", "legatura cu aria",
        "legătura cu mediul geografic", "legatura cu mediul geografic",
    )),
    ("description", (
        "tipuri de vin", "caracteristicile vinurilor",
        "caracteristici", "descrierea vinurilor",
    )),
    ("summary", ("definiţie", "definitie", "definiție")),
)


def split_sections(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice the caiet text on top-level Roman-numeral headers. Returns
    (bodies_by_role, titles_by_role); a role keeps the first matching
    section only (caiete don't repeat top-level roles)."""
    # pdftotext emits a form-feed (\x0c) at page breaks, often immediately
    # before a section header ("\x0cV. Producţia…") — that defeats the `^`
    # line anchor and lets one section swallow the next. Fold to newlines.
    text = text.replace("\x0c", "\n")
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return {}, {}
    raw: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = re.sub(r"\s+", " ", m.group(2)).strip(" .")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw.append((title, text[start:end]))

    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for title, body in raw:
        tlow = title.lower()
        for role, keywords in _ROLE_KEYWORDS:
            if role in bodies:
                continue
            if any(kw in tlow for kw in keywords):
                bodies[role] = body.strip()
                titles[role] = title
                break
    return bodies, titles


# Grape-section colour headers: "Soiurile albe:", "- Soiuri roşii:",
# "soiuri roze:", "soiuri aromate". The variety list may follow on the
# same line after the colon. A header may carry a "/roze" (or "/rose")
# second-colour suffix — "- soiuri roşii/roze:" — which the trailing
# `(?:/colour)*` group consumes so the colon isn't left glued to the
# first variety name (else "roze: Cabernet Sauvignon" never resolves).
# The bucket colour is the FIRST captured colour (roşii → noir).
_COLOUR_HEADER_RE = re.compile(
    r"^[ \t]*[-•·]?\s*soiur?i(?:le)?\s+(albe|ro[șşs-]?ii|ro[șş]ii|roze|rose|aromate)"
    r"(?:\s*/\s*(?:albe|ro[șşs-]?ii|ro[șş]ii|roze|rose|aromate))*"
    r"\s*:?",
    re.I,
)
_COLOUR_BY_HEADER = {
    "albe": "blanc",
    "rosii": "noir", "roșii": "noir", "roşii": "noir",
    "roze": "rose", "rose": "rose",
    "aromate": "blanc",
}

# Lines inside the grape section that are descriptive, not variety names.
_GRAPE_PROSE_RE = re.compile(
    r"\b(care\s+provine|asamblări|asamblari|sortiment|men[țţt]iune|"
    r"struguri|produc|recolt)\b",
    re.I,
)


def parse_grapes(body: str) -> dict:
    """Parse the caiet grape section (IV. Soiurile de struguri) into the
    {principal, accessory, observation, details} shape the EU extractor
    produces. Caiete carry no principal/accessory split — every variety
    is `principal`; colour comes from the section header or the matcher."""
    from ..grape_entity import match_variety

    out: dict[str, list] = {
        "principal": [], "accessory": [], "observation": [], "details": [],
    }
    if not body:
        return out

    # Group the section into (colour, text) segments split on the colour
    # headers ("Soiurile albe:" / "Soiuri roşii:"). Lines WITHIN a segment
    # are joined with a space, not a comma — pdftotext -layout wraps a long
    # variety list mid-name ("…Neuburger, Riesling\n      Italian, …"), so
    # splitting per physical line would shear "Riesling Italian" in two.
    segments: list[tuple[str | None, list[str]]] = [(None, [])]
    for raw_line in body.splitlines():
        m = _COLOUR_HEADER_RE.match(raw_line)
        if m:
            key = m.group(1).lower().replace("ş", "s").replace("ș", "s")
            segments.append((_COLOUR_BY_HEADER.get(key), []))
            tail = raw_line[m.end():].strip(" \t:-•·")
            if tail:
                segments[-1][1].append(tail)
            continue
        line = raw_line.strip(" \t-•·")
        if line:
            segments[-1][1].append(line)

    seen: set[str] = set()
    for colour_ctx, lines in segments:
        text = " ".join(lines)
        if not text.strip():
            continue
        if _GRAPE_PROSE_RE.search(text):
            # Drop a "(care provine … din asamblări …)" qualifier; keep the
            # head of the segment, which still carries the variety names.
            text = re.split(r"\(", text, maxsplit=1)[0]
        for cand in re.split(r"\s*[,;]\s*|\s+şi\s+|\s+si\s+|\s+și\s+", text):
            cand = cand.strip(" .\t")
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
                "colour": match.colour or colour_ctx,
            })
    return out


def parse_styles(bodies: dict[str, str], grapes: dict) -> list[str]:
    blob = " ".join(
        bodies.get(r, "") for r in ("summary", "description", "grape_varieties")
    )
    found: set[str] = set()
    for kw, colour_slug in COLOUR_BY_KEYWORD.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob, re.I):
            found.add(colour_slug)
    for pattern, slug in STYLE_MARKERS:
        if pattern.search(blob):
            found.add(slug)
    # Backstop: colour from the matched grapes (a caiet whose section I
    # doesn't name colours still implies them via the variety list).
    _colour_to_style = {"blanc": "blanc", "noir": "rouge", "gris": "rose",
                        "rose": "rose"}
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


def parse_caiet(text: str, slug: str) -> dict:
    """Parse `pdftotext -layout` text of one ONVPV caiet de sarcini into
    a merge-able record fragment."""
    bodies, titles = split_sections(text)
    grapes = parse_grapes(bodies.get("grape_varieties", ""))
    geo_area = bodies.get("geo_area", "")
    geo_communes = parse_commune_list(geo_area) if geo_area else []
    link = (bodies.get("link_to_terroir") or "").strip()
    summary = _derive_summary(bodies.get("summary") or bodies.get("description") or "")
    return {
        "summary": summary,
        "grapes": grapes,
        "geo_area_brief": _derive_summary(geo_area, max_chars=2000),
        "geo_communes": geo_communes,
        "link_to_terroir": link,
        "styles": parse_styles(bodies, grapes),
        "section_roles": {
            "summary": bodies.get("summary", ""),
            "geo_area": geo_area,
            "grape_varieties": bodies.get("grape_varieties", ""),
            "link_to_terroir": link,
        },
        "section_titles": titles,
        "n_sections": len(bodies),
        "n_grapes": len(grapes["details"]),
        "parser_template": "onvpv-caiet-de-sarcini-v1",
    }
