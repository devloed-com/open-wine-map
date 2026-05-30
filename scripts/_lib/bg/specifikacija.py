"""Parser for the Bulgarian national продуктова спецификация (ИАЛВ / IAVV).

The 51 grandfathered BG wine GIs whose EU-OJ ЕДИНЕН ДОКУМЕНТ was never
published have their canonical specification published by the Изпълнителна
агенция по лозата и виното (eavw.com) as a per-wine продуктова спецификация
PDF "съгласно Регламент 1308/2013, чл. 94". Format-to-text conversion lives
in stage 02f (`scripts/bg/02f_extract_national_specs.py`); this module parses
the already-extracted text (pdftotext -layout output).

Document layout — a numbered template (1..8/9), stable across the corpus:

    1. Вино със ЗНП … (наименование + традиционно наименование)  → name
    2. Виното се произвежда по традиционната технология …       → description / styles
    3. Районът за производство на вино със ЗНП … е очертан …     → geo area / communes
    4. Максималният добив …                                       → yield
    5. Винените сортове грозде разрешени … са: …                  → grape varieties
    6. Връзка с географския район. (а) Природни / б) Човешки)     → link to terroir
    7. Приложими изисквания.                                       → requirements
    8. Контролен орган …                                           → control body

Numbered headers sit at a consistent left indent in the -layout text; a
monotonic-progression guard drops backward cross-reference anchors
("… съгласно т. 4 …" inside an earlier section).

Section 5 groups varieties under Bulgarian colour markers — `за бели вина`
(white → blanc), `за червени вина` (red → noir, often `за червени вина и
розе`), `за розе` / `розе` (rosé). When no colour marker is present the
section is a flat list after the verb `са`/`е` following the quoted name
(single-variety + small-roster wines). There is no principal/accessory split
in the BG spec (same as PT/IT/HR), so every variety is `principal`.

All string handling is Cyrillic-preserving — comparisons use `.casefold()`,
never NFKD-ASCII (which would erase Cyrillic). See the Cyrillic-handling note
in CLAUDE.md.

Public entry point:
  `parse_specifikacija(text, slug)` → dict with the same shape as the
  SI/HR/DE national-spec sidecars.
"""

from __future__ import annotations

import re

from _lib.grape_entity import match_variety

# ───────────────────────────────────────────────────── numbered slicing ──

# Line-start numbered anchor: `N.` (1–2 digits) + space, optionally indented.
_NUM_ANCHOR_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]+\S")

# Role classification by Bulgarian keyword in the section's leading text.
# Keywords are casefolded substrings matched against the first ~160 chars of
# the section body (which still carries the wrapped header line).
_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "grape_varieties": ("винените сортове", "виненият сорт", "сортове грозде", "сорт грозде"),
    "link_to_terroir": ("връзка с географск", "връзката с географск", "причинно-следствена връзка"),
    "geo_area": (
        "районът за производство",
        "район за производство",
        "районът на производство",
        "очертан при следните граници",
        "географски район",
        "географската зона",
    ),
    "yield": ("максималният добив", "максимален добив", "максималния добив"),
    "description": (
        "виното се произвежда",
        "вината се произвеждат",
        "виното със знп",
        "описание на вино",
        "произвежда по традиционната технология",
    ),
    "requirements": ("приложими изисквания", "други условия", "специфични изисквания"),
    "control": ("контролен орган", "контрол"),
    "name": ("вино със знп", "гарантирано наименование", "наименование за произход"),
}


def _numbered_sections(text: str) -> dict[int, str]:
    """Slice text into {number → body} on the `N.` line anchors. The body is
    everything between this anchor and the next accepted one (the wrapped
    title stays at the head of the body, which routing handles)."""
    text = text.replace("\x0c", "\n")
    anchors = list(_NUM_ANCHOR_RE.finditer(text))
    accepted: list[tuple[int, int]] = []  # (number, anchor_start)
    last = 0
    for m in anchors:
        n = int(m.group(1))
        # Real outline numbers advance (1→2→3…); an anchor that doesn't
        # exceed the last accepted number is a cross-reference, not a heading.
        if n <= last or n > last + 4:
            continue
        last = n
        accepted.append((n, m.start()))
    out: dict[int, str] = {}
    for i, (n, start) in enumerate(accepted):
        end = accepted[i + 1][1] if i + 1 < len(accepted) else len(text)
        out[n] = text[start:end].strip()
    return out


def _route_sections(sections: dict[int, str]) -> dict[str, str]:
    """Map each numbered section to a role by scanning its leading text."""
    routed: dict[str, str] = {}
    for _n, body in sorted(sections.items()):
        head = body[:180].casefold()
        for role, keywords in _ROLE_KEYWORDS.items():
            if role in routed:
                continue
            if any(kw in head for kw in keywords):
                routed[role] = body
                break
    return routed


def _strip_header_line(body: str) -> str:
    """Drop the leading numbered-header sentence so the role body starts at
    real content. The header is the run from `N.` to the first sentence
    terminator (`:` for grapes / `.` ending the title clause)."""
    # Remove the leading "N." marker.
    body = re.sub(r"^\s*\d{1,2}\.\s*", "", body, count=1)
    return body.strip()


# ───────────────────────────────────────────────────────── grape parsing ──

# Colour markers inside section 5. `за червени вина и розе` is matched whole
# so its " и розе" is not later treated as a variety separator.
_COLOUR_MARKER_RE = re.compile(
    r"(?:^|\n)\s*[-–•]?\s*за\s+(бели|червени|розови|розе)\s*(?:вина)?(?:\s+и\s+розе)?\s*:?",
    re.I,
)
_COLOUR_HINT = {"бели": "blanc", "червени": "noir", "розови": "rose", "розе": "rose"}
_GRAPE_SPLIT_RE = re.compile(r"\s*[,;]\s*|\s+и\s+", re.I)

# A line/phrase that ends a variety list (prose or the next section's prose).
_LIST_STOP_RE = re.compile(
    r"връзка\s+с\s+географ|приложими|максимал|контролен|съгласно|райони?т|"
    r"производство\s+на\s+грозде|^\s*\d{1,2}\.\s",
    re.I,
)

# Anchor for the flat (no-colour-marker) list: closing quote of the GI name
# followed by the verb `са`/`е` (optionally `,` and `:`).
_FLAT_LIST_RE = re.compile(r'["”“»]\s*,?\s*(?:са|е)\b\s*:?\s*', re.S)


def _build_grapes() -> dict:
    return {"principal": [], "accessory": [], "observation": [], "details": []}


def _add_one(grapes: dict, name: str, colour_hint: str) -> bool:
    m = match_variety(name)
    if m is None or m.slug in grapes["principal"]:
        return False
    grapes["principal"].append(m.slug)
    grapes["details"].append({
        "slug": m.slug, "name": name, "role": "principal",
        "colour": m.colour or colour_hint or "",
    })
    return True


def _add(grapes: dict, raw: str, colour_hint: str) -> bool:
    name = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip(" \t.;,–-")
    if not name or len(name) < 2:
        return False
    if _add_one(grapes, name, colour_hint):
        return True
    if match_variety(name) is not None:
        return False  # matched a slug already listed — not a miss
    # Source typo: two grapes run together with no separator ("Шардоне
    # Димят" — missing comma). Split on whitespace and accept only when
    # EVERY piece matches a known variety, so legitimate two-word names
    # (Каберне совиньон, Мискет червен) are never wrongly split.
    pieces = name.split()
    if len(pieces) >= 2 and all(match_variety(p) is not None for p in pieces):
        added = False
        for p in pieces:
            added = _add_one(grapes, p, colour_hint) or added
        return added
    return False


def _list_tokens(chunk: str) -> list[str]:
    """Join the run of list lines (variety names wrap across lines in the
    -layout text), stopping at the first prose/heading line, and return the
    comma/и-separated tokens."""
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
        if s.endswith("."):  # a list usually ends with a full stop
            break
    blob = " ".join(lines)
    # Some specs carry a stray leading conjunction after the colour marker
    # ("за червени вина и розе: и Мерло и Каберне совиньон" — Варна); drop it
    # so the first variety isn't swallowed into an "и Мерло" token.
    blob = re.sub(r"^\s*и\s+", "", blob)
    return [t for t in _GRAPE_SPLIT_RE.split(blob) if t.strip() and t.strip() != "и"]


def _parse_grapes(section5: str) -> dict:
    grapes = _build_grapes()
    markers = list(_COLOUR_MARKER_RE.finditer(section5))
    if markers:
        for i, m in enumerate(markers):
            colour = _COLOUR_HINT.get(m.group(1).lower(), "")
            end = markers[i + 1].start() if i + 1 < len(markers) else len(section5)
            for tok in _list_tokens(section5[m.end():end]):
                _add(grapes, tok, colour)
        if grapes["principal"]:
            return grapes
    # Flat list: strip up to the verb after the quoted GI name, then split.
    fm = _FLAT_LIST_RE.search(section5)
    tail = section5[fm.end():] if fm else _strip_header_line(section5)
    for tok in _list_tokens(tail):
        _add(grapes, tok, "")
    return grapes


# ───────────────────────────────────────────────────────────── styles ──

_COLOUR_TO_STYLE = {"blanc": "blanc", "noir": "rouge", "gris": "blanc", "rose": "rose"}
_STYLE_MARKERS = [
    (re.compile(r"\bпенлив", re.I), "sparkling"),
    (re.compile(r"\bискрящ", re.I), "sparkling"),
    (re.compile(r"\bполупенлив|перлант", re.I), "semi-sparkling"),
    (re.compile(r"\bликьорн", re.I), "vin-de-liqueur"),
    (re.compile(r"\bдесертн|късна?\s+реколта|ледено\s+вино", re.I), "vendanges-tardives"),
    (re.compile(r"\bботритиз|благородна?\s+плесен", re.I), "grains-nobles"),
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


# ───────────────────────────────────────────────────────────── public ──

def parse_specifikacija(text: str, slug: str) -> dict:
    sections = _numbered_sections(text)
    routed = _route_sections(sections)

    section5 = routed.get("grape_varieties", "")
    grapes = _parse_grapes(section5) if section5 else _build_grapes()

    description = _strip_header_line(routed.get("description", ""))
    geo_area = _strip_header_line(routed.get("geo_area", ""))
    link = _strip_header_line(routed.get("link_to_terroir", ""))

    return {
        "summary": derive_summary(description or geo_area),
        "grapes": grapes,
        "geo_area_brief": derive_summary(geo_area, max_chars=2000),
        "link_to_terroir": link,
        "styles": _parse_styles(description, grapes),
        "section_roles": {
            "description": description,
            "geo_area": geo_area,
            "grape_varieties": _strip_header_line(section5),
            "link_to_terroir": link,
        },
        "section_titles": {str(n): (b.splitlines()[0][:90] if b else "")
                           for n, b in sorted(sections.items())},
        "n_sections": len(sections),
        "parser_template": "iavv-specifikacija-v1",
    }
