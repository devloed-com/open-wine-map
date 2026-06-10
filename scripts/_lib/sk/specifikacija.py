"""Parser for the Slovak national wine product specification (ÚPV SR).

The SK grandfathered wine GIs whose EU-OJ JEDNOTNÝ DOKUMENT was never
published have their canonical specification published by the Úrad
priemyselného vlastníctva SR (Slovak Industrial Property Office,
indprop.gov.sk) as a per-wine špecifikácia výrobku, one text-layer PDF
per protected name. Format-to-text conversion lives in stage 02f
(`scripts/sk/02f_extract_national_specs.py`); this module parses the
already-extracted text (pdftotext -layout output).

Document layout — lettered sections a)–i), stable across the corpus:

    a) Názov, ktorý sa má chrániť                       → name
    b) Opis vína                                        → description / styles
    c) osobitné enologické postupy …                   → oenological
    d) vymedzenie príslušnej zemepisnej oblasti         → geo area (commune list)
    e) maximálne hektárové výnosy                       → yield
    f) označenie odrody alebo odrôd viniča …            → grape varieties
    g) údaje potvrdzujúce spojitosť                     → link to terroir
    h) iné požiadavky …                                 → requirements
    i) kontrolné orgány …                               → control body

The CHZO (PGI) variant (Slovenská) drops e) but keeps the same letters.

Section f) is a two-column table — `Odroda` (the canonical Slovak name)
on the left, `Synonymum` (a comma list of foreign synonyms) on the
right — grouped under colour-bucket labels `MUŠTOVÉ BIELE` (white →
blanc) and `MUŠTOVÉ MODRÉ` (blue/black → noir), occasionally a
`MUŠTOVÉ RUŽOVÉ` (rosé) bucket. We take ONLY the left column: the
canonical Odroda name, never the synonym list — so the regulator's
canonical spelling drives the slug and the well-known Slovak↔EU
synonym confusion (Pesecká leánka ↔ Feteasca regala) is sidestepped.
There is no principal/accessory split in the ÚPV spec (same as
PT/IT/HR), so every variety is `principal`.

Public entry point:
  `parse_specifikacija(text, slug)` → dict with the same shape as the
  BG/HR/SI national-spec sidecars.
"""

from __future__ import annotations

import re

from _lib.grape_entity import match_variety

# ───────────────────────────────────────────────────────── lettered slicing ──

# Line-start letter anchor: `a)` … `i)` optionally tab/space-prefixed.
_LETTER_ANCHOR_RE = re.compile(r"(?m)^[ \t]*([a-i])\)[ \t]*")

# Role classification by Slovak keyword in the section's leading title text.
# Keywords are casefolded substrings matched against the first ~160 chars
# after the letter so a wrapped title still routes.
_ROLE_KEYWORDS = {
    "name": ("názov, ktorý sa má chrániť", "názov, ktorý sa má"),
    "description": ("opis vína", "opis vin"),
    "oenological": ("enologické postupy", "osobitné enologické"),
    "geo_area": ("vymedzenie príslušnej zemepisnej", "vymedzenie zemepisnej oblasti"),
    "yield": ("maximálne hektárové výnosy", "hektárové výnosy"),
    "grape_varieties": ("označenie odrody", "označenie odrôd"),
    "link_to_terroir": ("údaje potvrdzujúce spojitosť", "potvrdzujúce spojitos"),
    "requirements": ("iné požiadavky", "ďalšie podmienky"),
    "control": ("kontrolné orgány", "kontrolný orgán", "názov a adresa orgánov"),
}


def _lettered_sections(text: str) -> dict[str, str]:
    """Slice text into {letter → body} on the a)…i) line anchors. Body is
    everything between this anchor and the next.

    pdftotext emits a `\\x0c` form-feed (not a newline) at page breaks, so
    a section that starts a new page is normalised to `\\n` first. A
    monotonic-progression guard then drops backward cross-reference
    anchors — a sentence like "…podľa písmena e) …" inside an earlier
    section is a reference, not a real heading."""
    text = text.replace("\x0c", "\n")
    out: dict[str, str] = {}
    accepted: list[tuple[str, int, int]] = []  # (letter, body_start, anchor_start)
    last_ord = ord("a") - 1
    for m in _LETTER_ANCHOR_RE.finditer(text):
        letter = m.group(1)
        o = ord(letter)
        if o <= last_ord:
            continue
        last_ord = o
        accepted.append((letter, m.end(), m.start()))
    for i, (letter, body_start, _astart) in enumerate(accepted):
        end = accepted[i + 1][2] if i + 1 < len(accepted) else len(text)
        out[letter] = text[body_start:end].strip()
    return out


def _route_sections(sections: dict[str, str]) -> dict[str, str]:
    """Map each lettered section to a role by scanning its leading text."""
    routed: dict[str, str] = {}
    for _letter, body in sections.items():
        head = body[:160].casefold()
        for role, keywords in _ROLE_KEYWORDS.items():
            if role in routed:
                continue
            if any(kw in head for kw in keywords):
                routed[role] = _strip_leading_title(body)
                break
    return routed


def _strip_leading_title(body: str) -> str:
    """The lettered slice keeps the (wrapped) section title at its head,
    usually ending with a colon. Drop everything up to and including the
    first colon-terminated line so the role body starts at real content;
    if there is no early colon (the g) terroir narrative has none), keep
    the body intact."""
    m = re.search(r":\s*\n", body)
    if m and m.start() < 300:
        return body[m.end():].strip()
    if ":" in body[:200]:
        idx = body.index(":")
        return body[idx + 1:].strip()
    return body


# ───────────────────────────────────────────────────────────── grape parsing ──

# Colour-bucket labels. They sit in the leftmost column, often as a
# vertical two-line label ("MUŠTOVÉ" then "BIELE"); we match either token.
_BUCKET_WHITE_RE = re.compile(r"\bBIEL", re.I)
_BUCKET_RED_RE = re.compile(r"\bMODR", re.I)
_BUCKET_ROSE_RE = re.compile(r"\bRUŽOV", re.I)
# Leading bucket tokens glued to the first variety of a bucket
# ("MUŠTOVÉ Aurelius", " BIELE   Bouvierovo hrozno").
_BUCKET_PREFIX_RE = re.compile(r"^(?:MUŠTOVÉ|BIELE|MODRÉ|RUŽOVÉ)\s+", re.I)


def _build_grapes() -> dict:
    return {"principal": [], "accessory": [], "observation": [], "details": []}


def _add(grapes: dict, raw: str, colour_hint: str) -> bool:
    name = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip(" \t.;,–-")
    if not name or len(name) < 2:
        return False
    m = match_variety(name)
    if m is None or m.slug in grapes["principal"]:
        return False
    grapes["principal"].append(m.slug)
    grapes["details"].append({
        "slug": m.slug, "name": name, "role": "principal",
        "colour": m.colour or colour_hint or "",
    })
    return True


def _left_column(line: str) -> str:
    """Return the canonical Odroda name: the leftmost text segment, before
    the wide whitespace gap that separates it from the Synonymum column.
    Strips any glued colour-bucket label first ("BIELE   Bouvierovo
    hrozno" → "Bouvierovo hrozno")."""
    s = line.strip()
    s = _BUCKET_PREFIX_RE.sub("", s)
    # The Odroda name is everything up to the first run of 2+ spaces
    # (the column gutter). Canonical Slovak names carry no comma and no
    # 2-space gap, so this never pulls a synonym.
    return re.split(r"\s{2,}", s)[0].strip()


# A line that is nothing but one or more bucket labels (the vertical
# `MUŠTOVÉ` / `BIELE` / `MODRÉ` two-line column header), with no variety.
_BUCKET_LABEL_LINE_RE = re.compile(
    r"^(?:MUŠTOVÉ|BIELE|MODRÉ|RUŽOVÉ)(?:\s+(?:MUŠTOVÉ|BIELE|MODRÉ|RUŽOVÉ))*$",
    re.I,
)


def _parse_grapes(f_body: str) -> dict:
    """Walk the section-f variety table line by line, tracking the current
    colour bucket, taking the left (Odroda) column of each row.

    Only the left column of a real variety row is fed to the matcher: a
    canonical Odroda name is Title-Case and comma-free, so synonym-column
    continuation lines (comma lists, lowercase wrap fragments) and the
    ALL-CAPS bucket labels are filtered out — they otherwise pollute the
    extraction-unknowns queue without ever becoming a variety."""
    grapes = _build_grapes()
    colour = ""
    for line in f_body.splitlines():
        s = line.strip()
        if not s:
            continue
        if _BUCKET_LABEL_LINE_RE.match(s):
            # A dedicated colour-bucket label line; flip the bucket hint
            # (the lexicon colour still dominates) and skip it.
            if _BUCKET_ROSE_RE.search(s):
                colour = "rose"
            elif _BUCKET_RED_RE.search(s):
                colour = "noir"
            elif _BUCKET_WHITE_RE.search(s):
                colour = "blanc"
            continue
        left = _left_column(s)
        if not left or "," in left or not left[:1].isupper():
            continue
        # The §f intro prose ("V Nitrianskej … je povolené pestovať …")
        # and the "Odroda" table header are single-spaced lines that slip
        # past the column gutter; a canonical Odroda name is ≤ 4 words and
        # short, so drop anything longer or containing a sentence period.
        if len(left) > 40 or len(left.split()) > 4 or "." in left:
            continue
        if left.casefold() in ("odroda", "synonymum"):
            continue
        _add(grapes, left, colour)
    return grapes


# ───────────────────────────────────────────────────────────── styles ──

_COLOUR_TO_STYLE = {"blanc": "blanc", "noir": "rouge", "gris": "blanc", "rose": "rose"}
_STYLE_MARKERS = [
    (re.compile(r"\bšumiv|\bsekt\b", re.I), "sparkling"),
    (re.compile(r"\bperliv", re.I), "semi-sparkling"),
    (re.compile(r"\blikér", re.I), "vin-de-liqueur"),
    (re.compile(r"\bslamov", re.I), "vin-de-paille"),
    (re.compile(r"\bľadov|neskorý\s+zber|hrozienkový\s+výber|bobuľový\s+výber|"
                r"výber\s+z\s+hrozna", re.I), "vendanges-tardives"),
    (re.compile(r"\bcibébový\s+výber|botrytíd|ušľachtilá\s+pleseň", re.I), "grains-nobles"),
]


def _parse_styles(description: str, grapes: dict) -> list[str]:
    out: set[str] = set()
    blob = description or ""
    for pat, slug in _STYLE_MARKERS:
        if pat.search(blob):
            out.add(slug)
    for d in grapes.get("details") or []:
        s = _COLOUR_TO_STYLE.get(d.get("colour"))
        if s:
            out.add(s)
    return sorted(out)


def derive_summary(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if cut and not cut.endswith(".") else "")


# ─────────────────────────────── prihláška (old numbered template) ──
# The 1996-era ÚPV "Prihláška označenia pôvodu" template (e.g. Karpatská
# perla, application 0005-96) is an OCR-scanned PDF with numbered `03.N`
# sections instead of the modern lettered a–i layout, and a FLAT inline
# variety list rather than a two-column table:
#   03.2 Zemepisné vymedzenie územia        → geo area + natural conditions
#   03.3 Doklad potvrdzujúci … pôvod         → historical / human factors
#   03.4 Opis vlastností … dané … prostredím → terroir / quality link
#   03.5 Opis spôsobu získavania             → "z … odrôd vinnej révy: …"
# pdftotext over the scan is noisy (`C hardonnay`, `Mu ~kát`, `MUller`),
# but the grape matcher is fuzzy enough to recover almost all of it; a
# couple of targeted OCR repairs close the gap.

_PRIHLASKA_SECTION_RE = re.compile(r"(?m)^[ \t]*03\.(\d)[ \t]+\S")
_VARIETY_LIST_RE = re.compile(r"odrôd\s+vinnej\s+révy\s*:?\s*(.*?)\bz\s+hrozna",
                              re.S | re.I)


def _repair_ocr_variety(s: str) -> str:
    s = re.sub(r"\s+", " ", s.replace("\n", " ")).strip(" \t.;,–-")
    s = s.replace("~", "š").replace("§", "š")
    s = re.sub(r"\bMu\s*škát\b", "Muškát", s, flags=re.I)
    s = re.sub(r"\bDievč[^,]*hrozno\b", "Dievčie hrozno", s, flags=re.I)
    return s


def _prihlaska_sections(text: str) -> dict[str, str]:
    text = text.replace("\x0c", "\n")
    anchors = [(m.group(1), m.start()) for m in _PRIHLASKA_SECTION_RE.finditer(text)]
    out: dict[str, str] = {}
    for i, (num, start) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else len(text)
        out[num] = text[start:end].strip()
    return out


def _parse_prihlaska(text: str) -> dict:
    sections = _prihlaska_sections(text)
    grapes = _build_grapes()
    m = _VARIETY_LIST_RE.search(text)
    if m:
        for tok in m.group(1).split(","):
            name = _repair_ocr_variety(tok)
            if name:
                _add(grapes, name, "")

    geo_area = sections.get("2", "")
    # The terroir narrative spans the natural-conditions, historical and
    # quality-link sections (03.2 / 03.3 / 03.4) — the prihláška analogue
    # of the modern §g "údaje potvrdzujúce spojitosť".
    link = "\n\n".join(s for s in (sections.get("2"), sections.get("3"),
                                   sections.get("4")) if s).strip()
    description = sections.get("1", "")
    return {
        "summary": derive_summary(description or geo_area),
        "grapes": grapes,
        "geo_area_brief": derive_summary(geo_area, max_chars=2000),
        "link_to_terroir": link,
        "styles": _parse_styles(link, grapes),
        "section_roles": {
            "description": description,
            "geo_area": geo_area,
            "grape_varieties": (m.group(1).strip() if m else ""),
            "link_to_terroir": link,
        },
        "section_titles": {f"03.{k}": (v.splitlines()[0][:90] if v else "")
                           for k, v in sorted(sections.items())},
        "n_sections": len(sections),
        "parser_template": "upv-sr-prihlaska-v1",
    }


# ───────────────────────────────────────────────────────────── public ──

def parse_specifikacija(text: str, slug: str) -> dict:
    sections = _lettered_sections(text)
    routed = _route_sections(sections)

    f_body = routed.get("grape_varieties", "")
    grapes = _parse_grapes(f_body) if f_body else _build_grapes()

    # Fall back to the old numbered "prihláška" template when the modern
    # lettered layout yields neither a variety section nor a terroir link
    # (Karpatská perla and any other pre-EU-template ÚPV registration).
    if not grapes["principal"] and not routed.get("link_to_terroir") \
            and _VARIETY_LIST_RE.search(text):
        return _parse_prihlaska(text)

    description = routed.get("description", "")
    geo_area = routed.get("geo_area", "")
    link = (routed.get("link_to_terroir") or "").strip()

    return {
        "summary": derive_summary(description or geo_area),
        "grapes": grapes,
        "geo_area_brief": derive_summary(geo_area, max_chars=2000),
        "link_to_terroir": link,
        "styles": _parse_styles(description, grapes),
        "section_roles": {
            "description": description,
            "geo_area": geo_area,
            "grape_varieties": f_body,
            "link_to_terroir": link,
        },
        "section_titles": {k: (v.splitlines()[0][:90] if v else "")
                           for k, v in sections.items()},
        "n_sections": len(sections),
        "parser_template": "upv-sr-specifikacia-v1",
    }
