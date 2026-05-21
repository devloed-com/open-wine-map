"""Extract Menzioni / Unità Geografiche Aggiuntive (MGA / UGA).

MGA/UGA are the Italian "cru" granularity layer — finer-grained named
geographic units inside a DOP, used as label terms. The 2024 wine-law
reform unified the terminology under UGA (Unità Geografica Aggiuntiva)
but older disciplinari and EUR-Lex documenti unici use either form.
Examples:

  - Chianti Classico DOP → 11 UGAs (Castellina, Castelnuovo Berardenga,
    Gaiole, Greve, Lamole, Montefioralle, Panzano, Radda, San Casciano,
    San Donato in Poggio, Vagliagli — all Gran Selezione-eligible).
  - Barolo DOP → 181 MGAs (Cannubi, Brunate, Bussia, Cerequio, …)
    enumerated in the national disciplinare allegato. Documento unico
    only references the existence of MGAs in narrative form; the full
    list is national-disciplinare-only.
  - Barbaresco DOP → 66 MGAs.

v1 scope (decided with the user): MGA/UGA are NOT modelled as
sub-denomination records. Instead they appear as a flat chip list
(`menzioni: []`) on the parent record's detail panel, no per-cru
polygons.

Two extraction sources:

  1. **Documento unico** (this module): scan for a trigger phrase
     `Unità/Menzioni Geografiche Aggiuntive` followed by a colon and
     a list of names. Two list shapes:
     - **Numbered**: `:\n1. Name\n2. Name\n...` (Chianti Classico style).
     - **Comma**: `: Name1, Name2, ... e NameN`
       (smaller DOPs with 2-3 UGAs).
     Comma-list bare-prose form `... Unità Geografiche Aggiuntive
     Name1, Name2 e Name3` is also supported via a fallback regex.

  2. **National disciplinare allegato** (stage 02f): the complete list
     lives in a numbered annex to the national disciplinare PDF.
     Barolo's 181 MGAs are only available there.

This module covers source #1. Stage 02f-MASAF augments
`menzioni: []` with the allegato names when available.
"""

from __future__ import annotations

import re
import unicodedata


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


_TRIGGER_RE = re.compile(
    r"(?:unit[àa]|menzion[ei])\s+geografich[ei]\s+aggiuntiv[ei]",
    re.IGNORECASE,
)


# After the trigger, look for the FIRST colon within `_TRIGGER_TAIL_MAX`
# chars (Chianti Classico's prose between trigger and colon is ~150
# chars; we cap at 400 to allow for verbose explanations).
_TRIGGER_TAIL_MAX = 400

# After the colon, the list block extends until any of these terminators
# (a blank line, a new section header, or characteristic disciplinare
# phrasings that mark the end of the list).
_LIST_END_RE = re.compile(
    r"\n\s*\n|"                                    # blank line
    r"\n\s*\d{1,2}\.\d|"                           # numbered subsection like "5.2"
    r"\n\s*[A-Z][a-z]+\s+\w+\s+legale|"            # "Quadro giuridico"-style header
    r"\bTipo\s+di\s+condizione\b|"
    r"\bDescrizione\s+della\s+condizione\b|"
    r"\bLink\s+al\s+disciplinare\b",
    re.IGNORECASE,
)


_NAME_DROP_TOKENS = frozenset({
    "e", "ed", "del", "della", "dei", "delle", "il", "la", "lo", "gli", "le",
    "di", "in", "tra", "fra", "con", "per", "a", "alla", "alle", "ai",
    "uga", "mga",
    "comune", "comuni", "tipologia", "tipologie",
    "vino", "vini",
})


# A single name in the captured block. Italian proper nouns: starts
# with uppercase, may include apostrophes, hyphens, accents. We cap
# length at 60 chars to filter prose fragments.
_NAME_TOKEN_RE = re.compile(
    r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:[ \-][A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*"
)


def _names_from_numbered_block(block: str) -> list[str]:
    """Parse a `1. NAME\n2. NAME\n...` numbered list. Names may sit on
    the same line as the number ("1. Castellina") or on the next line
    ("1.\nCastellina") — the latter is what EUR-Lex's renderer
    produces."""
    out: list[str] = []
    # Split on numeric markers. The `(?m)` flag matters because
    # the number prefix sits on its own line.
    parts = re.split(r"(?m)^\s*\d{1,3}\.\s*", block)
    for part in parts[1:]:  # parts[0] is the prefix before the first "1."
        # Take the first non-empty line — that's the name.
        for line in part.splitlines():
            line = line.strip().rstrip(".,;:")
            if not line:
                continue
            # Reject lines that look like prose or labels.
            if line[0].islower():
                break
            if any(c.isdigit() for c in line):
                break
            if len(line) > 60:
                break
            if line.lower() in _NAME_DROP_TOKENS:
                break
            m = _NAME_TOKEN_RE.match(line)
            if m and m.group(0) == line:
                out.append(line)
            break
    return out


def _names_from_comma_block(block: str) -> list[str]:
    """Parse a `Name1, Name2, ... e NameN` comma-separated list."""
    s = re.sub(r"\s+", " ", block).strip().rstrip(".,;:")
    s = re.split(r"\s+(?:rispettivamente|come\s+segue|tipologie?|sono|che|i\s+cui)\b",
                 s, maxsplit=1)[0].strip().rstrip(",.;")
    out: list[str] = []
    for tok in re.split(r",|\be\s+|\bed\s+", s):
        name = tok.strip().strip("«»\"'").rstrip(".,;:")
        if not name:
            continue
        if name.lower() in _NAME_DROP_TOKENS:
            continue
        if name[0].islower():
            continue
        if any(c.isdigit() for c in name):
            continue
        if len(name) < 2 or len(name) > 60:
            continue
        out.append(name)
    return out


def extract_menzioni(text: str, parent_wine_name: str) -> list[dict]:
    """Return [{name, slug, source_pattern}, ...] for MGA/UGA names found
    in `text`. Deduped on slug; parent-wine slug excluded."""
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = {slugify(parent_wine_name)}

    for trig in _TRIGGER_RE.finditer(text):
        tail_start = trig.end()
        tail = text[tail_start:tail_start + _TRIGGER_TAIL_MAX]
        # Find the first `:` in the tail; bail if no colon (the trigger
        # is in narrative form, not introducing a list).
        colon = tail.find(":")
        if colon < 0:
            continue
        list_start = tail_start + colon + 1
        # Find the end of the list block.
        rest = text[list_start:]
        end_m = _LIST_END_RE.search(rest)
        list_block = rest[: end_m.start()] if end_m else rest[:1500]

        # Decide list shape: numbered or comma. Numbered if at least 2
        # markers `\n<digit><digit?>.` appear in the block.
        if len(re.findall(r"(?m)^\s*\d{1,3}\.\s*", list_block)) >= 2:
            names = _names_from_numbered_block(list_block)
            pattern = "numbered-list"
        else:
            names = _names_from_comma_block(list_block)
            pattern = "comma-list"

        for name in names:
            sl = slugify(name)
            if not sl or sl in seen:
                continue
            seen.add(sl)
            out.append({"name": name, "slug": sl, "source_pattern": pattern})
    return out
