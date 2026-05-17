"""Sub-region splitter for PT cadernos de especificações.

PT sub-regiões are the DGC analogue (FR) / subzona analogue (ES) —
named sub-regions of a parent DOP/IGP that share the parent's cahier
but carve out an interior aire géographique. Examples:

  - Vinho Verde → Amarante, Ave, Baião, Basto, Cávado, Lima,
                  Monção e Melgaço, Paiva, Sousa (9)
  - Alentejo    → Borba, Évora, Granja-Amareleja, Moura, Portalegre,
                  Redondo, Reguengos, Vidigueira (8)
  - Douro       → Baixo Corgo, Cima Corgo, Douro Superior (3)
  - Dão         → Alva, Besteiros, Castendo, Serra da Estrela,
                  Silgueiros, Terras de Azurara, Terras de Senhorim (7)

PT cadernos enumerate sub-regiões in several formats:

  Pattern A — "Sub-região [de|do|da] NAME" lines in the area or grapes
              section (Vinho Verde, Alentejo's letter-marked variant
              `a) Sub-região Borba - …`).

  Pattern B — Douro-style colon prefix: each sub-region opens its own
              paragraph with `NAME: no distrito de …`. Reliable only
              after a preamble phrase ("três áreas geográficas",
              "três sub-regiões"). Conservative — we require the
              preamble to fire, to avoid false positives on captions.

Wines without a matched pattern get parent-only records — they fall
back to the parent's polygon at the rendering layer (same as FR DGCs
that lack a parcellaire row). Curators can pin sub-regiões via a
future per-DOP override file analogous to the FR DGC override at
`scripts/_lib/cadastre_lieu_dit_overrides.json`.
"""

from __future__ import annotations

import re
import unicodedata


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# Tolerant of stray whitespace inside "Sub-região" (some PDFs render it
# as "Sub -região" or "Sub- região" after pdftotext layout reflow).
_PATTERN_A_RE = re.compile(
    r"(?:^|\n)\s*(?:[a-z]\)\s*)?"
    r"Sub\s*-\s*regi[ãa]o\s+(?:de\s+|do\s+|da\s+)?"
    r"(?P<name>[A-ZÀ-Ÿ][^\n:\-]{1,80}?)"
    r"(?=\s*[:\-\n])"
    r"(?P<body>[^\n]*(?:\n(?!\s*(?:[a-z]\)\s*)?Sub\s*-\s*regi[ãa]o\b)[^\n]*){0,80})",
    re.MULTILINE,
)

_PATTERN_B_PREAMBLE = re.compile(
    r"(?:tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez|"
    r"[2-9]\d?)\s+(?:[áa]reas?\s+geogr[áa]ficas?(?:\s+mais\s+restritas?)?"
    r"|sub-regi[õo]es)"
    r"|[áa]rea\s+das\s+sub-regi[õo]es",
    re.IGNORECASE,
)
# A Pattern B sub-region item: line starts with `CapName:` followed by
# `no distrito|abrange|compreende|nos distritos|no concelho|...`. We
# bound `CapName` to 60 chars (with optional internal spaces / hyphens)
# to keep this narrow.
_PATTERN_B_PREFIX = (
    r"no\s+distrito|nos\s+distritos|abrange|compreende|comp[õo]e-se|engloba"
    r"|no\s+concelho|nos\s+concelhos|os\s+concelhos|os\s+munic[íi]pios"
)
_PATTERN_B_ITEM = re.compile(
    r"(?:^|\n)\s*(?P<name>[A-ZÀ-Ÿ][A-Za-zÀ-ÿ \-]{2,60}?):\s*"
    r"(?P<body>(?:" + _PATTERN_B_PREFIX + r")[^\n]*"
    r"(?:\n(?!\s*[A-ZÀ-Ÿ][A-Za-zÀ-ÿ \-]{2,60}?:\s*"
    r"(?:" + _PATTERN_B_PREFIX + r"))[^\n]*){0,120})",
    re.MULTILINE | re.IGNORECASE,
)


def _clean_name(raw: str) -> str:
    """Trim trailing punctuation + collapse whitespace."""
    s = re.sub(r"\s+", " ", raw).strip()
    return s.rstrip(":,;.-").strip()


def detect_pattern_a(text: str) -> list[dict]:
    """Return sub-region records matching `Sub-região NAME [body]`."""
    out: dict[str, dict] = {}
    for m in _PATTERN_A_RE.finditer(text):
        name = _clean_name(m.group("name"))
        body = (m.group("body") or "").strip()
        if not name or len(name) < 2:
            continue
        slug = slugify(name)
        if slug in out:
            continue
        out[slug] = {
            "name": name,
            "slug": slug,
            "body": body,
            "source_pattern": "A",
        }
    return list(out.values())


def detect_pattern_b(text: str) -> list[dict]:
    """Return sub-region records matching the Douro-style colon prefix.
    Requires a preamble phrase ("três áreas geográficas") to fire."""
    if not _PATTERN_B_PREAMBLE.search(text):
        return []
    out: dict[str, dict] = {}
    for m in _PATTERN_B_ITEM.finditer(text):
        name = _clean_name(m.group("name"))
        body = (m.group("body") or "").strip()
        if not name or len(name) < 3:
            continue
        slug = slugify(name)
        if slug in out:
            continue
        out[slug] = {
            "name": name,
            "slug": slug,
            "body": body,
            "source_pattern": "B",
        }
    return list(out.values())


def _heal_word_breaks(text: str) -> str:
    """pdftotext occasionally splits "Sub-regiões" → "Sub-\nregiões" at a
    soft hyphen; collapse those back so the regexes don't miss them.
    Preserve case so the downstream regexes (which require initial caps)
    still fire."""
    return re.sub(r"(sub)-\s*\n\s*(regi)", r"\1-\2", text, flags=re.IGNORECASE)


def extract_subregioes(area_text: str, grapes_text: str = "") -> list[dict]:
    """Try Pattern A on area + grapes (Vinho Verde lists sub-regiões in
    the grapes section), then Pattern B on area only (Douro-style colon
    prefix). Return whichever fires with ≥2 matches. Empty list for
    parent-only DOPs."""
    if not area_text and not grapes_text:
        return []
    combined = _heal_word_breaks((area_text or "") + "\n" + (grapes_text or ""))
    a = detect_pattern_a(combined)
    if len(a) >= 2:
        return a
    b = detect_pattern_b(_heal_word_breaks(area_text or ""))
    if len(b) >= 2:
        return b
    return []
