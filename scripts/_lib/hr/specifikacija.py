"""Parser for the Croatian national specifikacija proizvoda (MPS).

The 16 grandfathered HR wine PDOs whose EU-OJ JEDINSTVENI DOKUMENT was
never published have their canonical specification published by the
Ministarstvo poljoprivrede (poljoprivreda.gov.hr) as a per-wine
SPECIFIKACIJA PROIZVODA "sukladno Uredbi 1308/2013, članak 94." in
three formats — 14 legacy `.doc`, 1 `.docx` (Primorska Hrvatska), 1
PDF (Dingač). Format-to-text conversion lives in stage 02f
(`scripts/hr/02f_extract_specifikacije.py`); this module parses the
already-extracted text.

Document layout — lettered sections a)–j):

    a) Naziv koji se zaštićuje                         → name
    b) Opis najznačajnijih … svojstava vina            → description / styles
    c) Specifični enološki postupci i ograničenja      → oenological
    d) Granice područja                                → geo area
    e) Maksimalni urod po hektaru                      → yield
    f) Sorte vinove loze                               → grape varieties
    g) Pojedinosti … povezane sa zemljopisnim uvjetima → link to terroir
    h) Prihvatljivi zahtjevi …                         → requirements
    (i/j vary — controls / labelling)

`.doc` (antiword) and PDF (pdftotext) preserve the literal `a)`…`j)`
prefixes, so the lettered slicer is the primary path. The `.docx`
(Word auto-numbered list) drops the letters, so for that one document
the grape colour markers ("Bijele sorte:" / "Crne sorte:") are scanned
directly and the lettered-section narrative is best-effort.

The grape section (and the docx) groups varieties under Croatian
colour markers — `Bijele sorte` (white → blanc), `Crne sorte`
(black → noir), `Sive sorte` (grey → gris), `Rose`. There is no
principal/accessory split in the MPS spec (same as PT/IT), so every
variety is `principal`.

Public entry point:
  `parse_specifikacija(text, slug)` → dict with the same shape as the
  SI/IT/DE national-spec sidecars.
"""

from __future__ import annotations

import re

from _lib.grape_entity import match_variety

# ───────────────────────────────────────────────────────── lettered slicing ──

# Line-start letter anchor: `a)` … `j)` optionally tab/space-prefixed.
_LETTER_ANCHOR_RE = re.compile(r"(?m)^[ \t]*([a-j])\)[ \t]*")

# Role classification by keyword in the section's leading title text.
# Order matters only for disambiguation; keywords are matched against the
# first ~160 chars after the letter so the wrapped g) title still routes.
_ROLE_KEYWORDS = {
    "name": ("naziv koji se zaštićuje", "naziv koji se zašti"),
    "description": ("opis najznačajnijih", "opis najzna", "svojstava vina"),
    "oenological": ("specifični enološki", "enološki postupci"),
    "geo_area": ("granice područja", "zemljopisno područje proizvodnje"),
    "yield": ("maksimalni urod",),
    "grape_varieties": ("sorte vinove loze",),
    "link_to_terroir": (
        "pojedinosti koje se odnose na kakvoću",
        "povezane sa zemljopisnim",
        "povezanost sa zemljopisnim",
    ),
    "requirements": ("prihvatljivi zahtjevi",),
}


def _lettered_sections(text: str) -> dict[str, str]:
    """Slice text into {letter → body} on the a)…j) line anchors. Body is
    everything between this anchor and the next (the wrapped title stays
    at the head of the body, which classification handles).

    pdftotext emits a `\\x0c` form-feed (not a newline) at page breaks, so
    a section that starts a new page is normalised to `\\n` first or its
    `^`-anchored letter would be missed (Dingač's g)). A monotonic-
    progression guard then drops backward cross-reference anchors — a
    sentence like "…propisanim točkom e) Maksimalni urod…" inside an
    earlier section is a reference, not a real heading."""
    text = text.replace("\x0c", "\n")
    out: dict[str, str] = {}
    accepted: list[tuple[str, int, int]] = []  # (letter, body_start, anchor_start)
    last_ord = ord("a") - 1
    anchors = list(_LETTER_ANCHOR_RE.finditer(text))
    for m in anchors:
        letter = m.group(1)
        o = ord(letter)
        # Real outline letters advance (a→b→c…); an anchor that jumps
        # backward or repeats is a cross-reference ("…točkom e) …" inside
        # section c), not a heading. Forward-only tolerates a skipped
        # letter without cascading rejections.
        if o <= last_ord:
            continue
        last_ord = o
        accepted.append((letter, m.end(), m.start()))
    for i, (letter, body_start, _astart) in enumerate(accepted):
        end = accepted[i + 1][2] if i + 1 < len(accepted) else len(text)
        out[letter] = text[body_start:end].strip()
    return out


def _keyword_sections(text: str) -> dict[str, str]:
    """Fallback slicer for documents whose lettered a)…j) prefixes were
    lost (the Primorska Hrvatska `.docx`, where Word auto-numbered the
    outline). Anchor on the role-keyword heading lines themselves and
    slice each body to the next heading — so section g) terroir text is
    recovered even without its letter."""
    lines = text.splitlines()
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    anchors: list[tuple[int, str, int]] = []  # (char_offset, role, body_start)
    seen: set[str] = set()
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if not low or len(low) > 200:
            continue
        for role, keywords in _ROLE_KEYWORDS.items():
            if role in seen:
                continue
            if any(low.startswith(kw) or (kw in low and len(low) < 160) for kw in keywords):
                body_start = offsets[i] + len(line) + 1
                anchors.append((offsets[i], role, body_start))
                seen.add(role)
                break

    anchors.sort()
    routed: dict[str, str] = {}
    for j, (_off, role, body_start) in enumerate(anchors):
        end = anchors[j + 1][0] if j + 1 < len(anchors) else len(text)
        routed[role] = text[body_start:end].strip()
    return routed


def _route_sections(sections: dict[str, str]) -> dict[str, str]:
    """Map each lettered section to a role by scanning its leading text."""
    routed: dict[str, str] = {}
    for letter, body in sections.items():
        head = body[:160].lower()
        for role, keywords in _ROLE_KEYWORDS.items():
            if role in routed:
                continue
            if any(kw in head for kw in keywords):
                # Drop the title line from the body for the matched role.
                routed[role] = _strip_leading_title(body)
                break
    return routed


def _strip_leading_title(body: str) -> str:
    """The lettered slice keeps the (wrapped) section title at its head,
    ending with a colon. Drop everything up to and including the first
    colon-terminated line so the role body starts at real content."""
    m = re.search(r":\s*\n", body)
    if m and m.start() < 300:
        return body[m.end():].strip()
    # Title may end with ':' mid-line (no newline) — cut at first ':'.
    if ":" in body[:300]:
        idx = body.index(":")
        return body[idx + 1:].strip()
    return body


# ───────────────────────────────────────────────────────────── grape parsing ──

_COLOUR_MARKER_RE = re.compile(
    r"(?:^|\n)\s*(?:\d+\.\s*)?(bijele|crne|sive|rose|roze)\s+sorte\s*:?\s*",
    re.I,
)
_COLOUR_HINT = {
    "bijele": "blanc",
    "crne": "noir",
    "sive": "gris",
    "rose": "noir",
    "roze": "noir",
}
_GRAPE_SPLIT_RE = re.compile(r"\s*,\s*|\s+i\s+", re.I)
# A line that ends a comma variety list (next section title or prose).
_LIST_STOP_RE = re.compile(
    r"najvažnij|najznačajnij|najzastupljenij|^\s*[a-j]\)|^\s*\d+\.\s+sorte|"
    r"podloga|^\s*g\)|pojedinosti",
    re.I,
)


def _build_grapes() -> dict:
    return {"principal": [], "accessory": [], "observation": [], "details": []}


# Trailing Croatian colour adjectives the regulator appends to many
# variety names ("Croatina crna", "Carmenere crni", "Okatica bijela").
# Stripped only as a fallback so names whose canonical form keeps the
# colour word (Plavac mali crni, Muškat crveni) match on the first try.
_COLOUR_ADJ_RE = re.compile(
    r"\s+(crni|crna|crno|bijeli|bijela|bijelo|sivi|siva|sivo|"
    r"crveni|crvena|crveno|žuti|žuta|žuto)$",
    re.I,
)


def _add(grapes: dict, raw: str, colour_hint: str) -> bool:
    name = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip(" \t.;,–-")
    if not name or len(name) < 2:
        return False
    m = match_variety(name)
    if m is None:
        # Retry without a trailing colour adjective ("Croatina crna" →
        # "Croatina"); keep the colour as the hint.
        stripped = _COLOUR_ADJ_RE.sub("", name).strip()
        if stripped and stripped != name:
            m = match_variety(stripped)
            if m is not None:
                name = stripped
    if m is None:
        return False
    if m.slug in grapes["principal"]:
        return False
    grapes["principal"].append(m.slug)
    grapes["details"].append({
        "slug": m.slug, "name": name, "role": "principal",
        "colour": m.colour or colour_hint or "",
    })
    return True


def _parse_grapes_by_colour(text: str) -> dict:
    """Scan the whole (or f-section) text for `Bijele sorte:` / `Crne
    sorte:` colour markers; the comma list immediately following each is
    the variety roster. Works for both lettered docs and the docx."""
    grapes = _build_grapes()
    markers = list(_COLOUR_MARKER_RE.finditer(text))
    for i, m in enumerate(markers):
        colour = _COLOUR_HINT.get(m.group(1).lower(), "")
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        chunk = text[m.end():end]
        # Keep only the run of lines up to the first prose/heading line.
        lines: list[str] = []
        for line in chunk.splitlines():
            s = line.strip()
            if not s:
                if lines:
                    break
                continue
            if _LIST_STOP_RE.search(s):
                break
            lines.append(s)
            # A list is usually one comma-line; stop after it ends with '.'
            if s.endswith("."):
                break
        blob = " ".join(lines)
        for tok in _GRAPE_SPLIT_RE.split(blob):
            _add(grapes, tok, colour)
    return grapes


def _parse_grapes_from_fbody(f_body: str) -> dict:
    """Fallback for single-variety / un-coloured grape sections (Dingač:
    just `Plavac mali crni` then prose). Take the first non-empty lines
    until prose ("Sorta …", "Podloga", description) begins."""
    grapes = _build_grapes()
    for line in f_body.splitlines():
        s = line.strip(" \t.;")
        if not s:
            continue
        if _LIST_STOP_RE.search(s) or s.lower().startswith("sorta "):
            break
        for tok in _GRAPE_SPLIT_RE.split(s):
            _add(grapes, tok, "")
        # Single bare variety name on its own line — stop before prose.
        if not re.search(r",| i ", s):
            break
    return grapes


# ───────────────────────────────────────────────────────────── styles ──

_STYLE_MARKERS = [
    (re.compile(r"\bpjenušav", re.I), "sparkling-quality"),
    (re.compile(r"\bbiser\s+vin", re.I), "semi-sparkling"),
    (re.compile(r"\bliker(?:sk)", re.I), "vin-de-liqueur"),
    (re.compile(r"\bdesertn", re.I), "vendanges-tardives"),
    (re.compile(r"\bprosušen|prezrel", re.I), "vendanges-tardives"),
]
_COLOUR_TO_STYLE = {"blanc": "blanc", "noir": "rouge", "gris": "blanc"}


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


# ───────────────────────────────────────────────────────────── public ──

def parse_specifikacija(text: str, slug: str) -> dict:
    sections = _lettered_sections(text)
    lettered = len(sections) >= 5
    routed = _route_sections(sections) if lettered else _keyword_sections(text)

    f_body = routed.get("grape_varieties", "")
    # Colour-marker scan first (covers multi-variety + docx); fall back to
    # the bare f-section list for single-variety wines like Dingač.
    grapes = _parse_grapes_by_colour(f_body or text)
    if not grapes["principal"] and f_body:
        grapes = _parse_grapes_from_fbody(f_body)
    if not grapes["principal"] and not lettered:
        grapes = _parse_grapes_by_colour(text)

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
        "section_titles": {k: (v[:80] if v else "") for k, v in sections.items()},
        "n_sections": len(sections),
        "parser_template": "mps-specifikacija-v1" if lettered else "mps-specifikacija-docx",
    }
