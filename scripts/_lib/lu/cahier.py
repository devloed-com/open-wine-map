"""Parser for the IVV 2020 *Cahier des charges AOP Moselle
luxembourgeoise* (the canonical Luxembourg wine specification).

The cahier is a 14-page French PDF with 10 lettered sections (a-j):

  a) La dénomination à protéger
  b) La description du vin                       (5 sub-types)
  c) Pratiques spécifiques (mention particulière)
  d) La délimitation de la zone géographique concernée
  e) Les rendements maximaux à l'hectare
  f) L'indication des variétés                   (14 varieties, each with prose)
  g) Lien avec l'aire géographique               (climat / terroir / facteurs)
  h) Autorités de contrôle
  i) Étiquetage
  j) Pratiques culturales

This parser carves the `pdftotext -layout` output into a structured
``CahierExtract`` with one body string per section + a grape-variety
list. Stage 02 emits the parent + per-commune sub-denomination records
from that structure.

Parser strategy: section anchors (`a)` … `j)`) always sit at line
start in the pdftotext output, so we split on those *line-anchored*
markers first, then collapse paragraphs *within* each section. That
avoids the fused-header pitfall where a section heading and its first
content line have no blank line between them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Section letter → keyword substring (lowercase) that must appear in the
# heading line. Used as a sanity guard so a stray `a)` inside body text
# doesn't get mistaken for a section anchor.
SECTION_ANCHORS: tuple[tuple[str, str], ...] = (
    ("a", "dénomination"),
    ("b", "description du vin"),
    ("c", "pratiques spécifiques"),
    ("d", "délimitation de la zone"),
    ("e", "rendements maximaux"),
    ("f", "indication des variétés"),
    ("g", "lien avec l"),
    ("h", "autorités"),
    ("i", "étiquetage"),
    ("j", "pratiques culturales"),
)


# 14 LU varieties as enumerated in cahier section f. The colour default
# is the wine-style colour for varieties typically vinified that way;
# Pinot gris is classed 'gris' (kept distinct so the style facet
# rendering is honest).
LU_VARIETY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Elbling", "blanc"),
    ("Rivaner", "blanc"),
    ("Sylvaner", "blanc"),
    ("Auxerrois", "blanc"),
    ("Pinot blanc", "blanc"),
    ("Chardonnay", "blanc"),
    ("Pinot gris", "gris"),
    ("Riesling", "blanc"),
    ("Gewürztraminer", "blanc"),
    ("Muscat-Ottonel", "blanc"),
    ("Pinot noir précoce", "noir"),
    ("Pinot noir", "noir"),
    ("Saint Laurent", "noir"),
    ("Gamay", "noir"),
)


@dataclass
class GrapeVariety:
    header: str
    colour: str
    description: str


@dataclass
class CahierExtract:
    raw_text: str
    sections: dict[str, str] = field(default_factory=dict)

    denomination: str = ""
    wine_descriptions: dict[str, str] = field(default_factory=dict)
    commune_perimetre_text: str = ""
    yields_text: str = ""
    varieties: list[GrapeVariety] = field(default_factory=list)
    lien_au_terroir: str = ""
    autorite_controle: str = ""
    etiquetage: str = ""
    pratiques_culturales: str = ""

    def section_body(self, letter: str) -> str:
        return self.sections.get(letter, "")


# ─── pre-processing ────────────────────────────────────────────


_PAGE_NUMBER_RE = re.compile(r"^\s*-?\s*\d{1,2}\s*-?\s*$")


def _strip_page_numbers(text: str) -> str:
    """Drop lonely page-number lines + the form-feed page-break
    characters pdftotext layout inserts at the start of each page.
    Without the form-feed strip, a `\\x0c` precedes section headings
    that fall at a page boundary (e.g. `\\x0ca) La dénomination`),
    silently breaking the ``^([a-j])\\)`` anchor regex."""
    text = text.replace("\f", "")
    keep: list[str] = []
    for line in text.split("\n"):
        if _PAGE_NUMBER_RE.match(line):
            continue
        keep.append(line)
    return "\n".join(keep)


def _join_section_paragraphs(text: str) -> str:
    """Collapse intra-paragraph soft line breaks into spaces; keep
    paragraph breaks (blank lines) as `\\n`."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        s = line.rstrip()
        if not s.strip():
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        current.append(s.strip())
    if current:
        paragraphs.append(" ".join(current).strip())
    return "\n".join(paragraphs)


# ─── section splitter ─────────────────────────────────────────


def _split_sections(text: str) -> dict[str, str]:
    """Walk the cleaned text line-by-line; an `^[a-j])\\s+` line that
    contains the matching anchor keyword opens a new section. The
    heading line itself is *not* included in the body."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.split("\n"):
        # Tag the line as a section heading if it starts with a letter
        # anchor AND contains the keyword that letter expects.
        m = re.match(r"^([a-j])\)\s+(.*)$", line)
        if m:
            letter, rest = m.group(1), m.group(2).lower()
            for anchor_letter, kw in SECTION_ANCHORS:
                if anchor_letter == letter and kw in rest:
                    current = letter
                    blocks[current] = []
                    break
            else:
                # `a)` etc. inside body text — keep in body.
                if current is not None:
                    blocks[current].append(line)
            continue
        if current is not None:
            blocks[current].append(line)
    # Join + collapse paragraphs per section.
    return {
        letter: _join_section_paragraphs("\n".join(lines)).strip()
        for letter, lines in blocks.items()
    }


# ─── section b: wine descriptions ─────────────────────────────


_WINE_TYPE_HEADERS: tuple[tuple[str, str], ...] = (
    ("1", "blanc"),
    ("2", "rouge"),
    ("3", "rose"),
    ("4", "mousseux-cremant"),
    ("5", "mention-particuliere"),
)


def _parse_wine_descriptions(section_b: str) -> dict[str, str]:
    """Carve section b into ``{style-slug: body}``. Numbered subsection
    markers like "1. Les vins blancs" introduce each subsection."""
    out: dict[str, str] = {}
    if not section_b:
        return out
    # The numbered markers always start a paragraph after section-paragraph
    # joining. Find every numbered marker; cut at the next one or EOS.
    # The number is followed by `.` + space + `Les` (singular) or `Le`
    # (mousseux) — both start with a capital `L`.
    # Lookahead for the line start so the matcher doesn't consume the
    # `\n` that the next marker needs to be detected (otherwise markers
    # 3 + 5 are silently skipped after 2 + 4 are matched). Capture the
    # full header phrase so the body slice starts cleanly after it.
    matches = list(re.finditer(
        r"(?:^|(?<=\n))\s*(\d)\.\s+[^\n]*?"
        r"(?:blancs|rouges|rosés|Luxembourg|particulière)\s*",
        section_b,
    ))
    for i, m in enumerate(matches):
        num = m.group(1)
        header_end = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_b)
        body = section_b[header_end:body_end].strip()
        for marker, slug in _WINE_TYPE_HEADERS:
            if marker == num:
                out[slug] = body
                break
    return out


# ─── section f: varieties ──────────────────────────────────────


def _parse_varieties(section_f: str) -> list[GrapeVariety]:
    """Walk section f looking for variety headers from
    :data:`LU_VARIETY_HEADERS`. After paragraph joining, each variety
    header is the first token of its paragraph, e.g.
    ``"Elbling L'Elbling est un cépage..."``. The next variety header
    terminates the current variety's body."""
    if not section_f:
        return []
    # Headers sorted longest-first so "Pinot noir précoce" matches
    # before "Pinot noir".
    headers_sorted = sorted(LU_VARIETY_HEADERS, key=lambda kv: -len(kv[0]))
    # Locate every header occurrence: at paragraph start (after `\n`)
    # OR at text start, followed by a space (= start of body text).
    positions: list[tuple[int, str, str]] = []
    for header, colour in headers_sorted:
        pattern = re.compile(
            rf"(?:^|\n)({re.escape(header)})\b",
            flags=re.UNICODE,
        )
        for m in pattern.finditer(section_f):
            positions.append((m.start(1), header, colour))
    # Dedupe overlapping (Pinot noir vs Pinot noir précoce).
    positions.sort(key=lambda t: (t[0], -len(t[1])))
    deduped: list[tuple[int, str, str]] = []
    last_end = -1
    for start, header, colour in positions:
        if start < last_end:
            continue
        deduped.append((start, header, colour))
        last_end = start + len(header)
    deduped.sort(key=lambda t: t[0])

    out: list[GrapeVariety] = []
    for i, (start, header, colour) in enumerate(deduped):
        body_start = start + len(header)
        body_end = deduped[i + 1][0] if i + 1 < len(deduped) else len(section_f)
        body = section_f[body_start:body_end].strip()
        out.append(GrapeVariety(header=header, colour=colour, description=body))
    return out


# ─── public entrypoint ────────────────────────────────────────


def parse_cahier(raw_text: str) -> CahierExtract:
    cleaned = _strip_page_numbers(raw_text)
    sections = _split_sections(cleaned)

    extract = CahierExtract(raw_text=raw_text, sections=sections)
    extract.denomination = sections.get("a", "").strip()
    extract.wine_descriptions = _parse_wine_descriptions(sections.get("b", ""))
    extract.commune_perimetre_text = sections.get("d", "")
    extract.yields_text = sections.get("e", "")
    extract.varieties = _parse_varieties(sections.get("f", ""))
    extract.lien_au_terroir = sections.get("g", "")
    extract.autorite_controle = sections.get("h", "")
    extract.etiquetage = sections.get("i", "")
    extract.pratiques_culturales = sections.get("j", "")
    return extract


def iter_variety_canonical_slugs(
    varieties: Iterable[GrapeVariety],
) -> list[tuple[GrapeVariety, str]]:
    """Resolve each cahier variety header to a shared lexicon slug.
    Yields ``(variety, canonical-slug)`` tuples."""
    from .. import grape_lexicon

    out: list[tuple[GrapeVariety, str]] = []
    for v in varieties:
        slug = grape_lexicon.slugify(v.header)
        out.append((v, slug))
    return out
