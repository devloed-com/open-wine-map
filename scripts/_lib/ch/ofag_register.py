"""Parse the OFAG "Répertoire suisse des AOC" PDF into spine records.

The Office fédéral de l'agriculture publishes one canonical PDF
("Répertoire suisse des appellations d'origine contrôlée (AOC)",
trilingual FR/DE/IT) listing every Swiss wine AOC. The 2026 edition
holds 63 listed entries across 26 cantons (61 unique AOCs once the
2 intercantonal duplicates — Vully VD/FR, Zürichsee ZH/SZ — are
deduped).

PDF layout (pdftotext -layout):

  AG              Aargau                             1
                                                       Aargau            <- col 53: cantonale
  BE              Bern / Berne                       3
                                                       Bern / Berne      <- col 53: cantonale
                                                                         Bielersee / Lac de Bienne   <- col 71: régionale
                                                                         Thunersee                   <- col 71: régionale
  GE              Genève                            23
                                                       Genève            <- col 53: cantonale
                                                                                                     Coteau de Chevrens  <- col 99: locale
                                                                                                     ...

Column thresholds (empirical, tolerant to ±5 chars across page layouts):
  - col 0:        canton abbreviation (`^[A-Z]{2}`)
  - col 16:       canton name
  - col ~44:      count
  - col 30-60:    cantonale AOC name
  - col 60-85:    régionale AOC name
  - col 85-110:   locale AOC name

Intercantonal handling: when the same AOC slug appears under two
cantons (Vully in VD+FR; Zürichsee in ZH+SZ) the parser emits ONE
record with `cantons=["vd", "fr"]` and the primary canton = first
encountered (VD for Vully, ZH for Zürichsee).

OFAG PDF typo handling: the 2026 PDF has `BL Basel-Stadt` (the BL
abbreviation row repeated for Basel-Stadt instead of `BS`). The
parser uses the canton NAME field as the authoritative key — if the
abbreviation doesn't match the canton name's CANTON_NAME lookup, the
name wins and a warning is logged.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from .canton import CANTON_CODE_BY_ABBREV, CANTON_NAME

# Column-position thresholds.
COL_CANTONALE_MIN, COL_CANTONALE_MAX = 30, 60
COL_REGIONALE_MIN, COL_REGIONALE_MAX = 60, 85
COL_LOCALE_MIN = 85

# Recognise a canton-header line: 2-letter uppercase abbrev + spaces + name.
CANTON_HEADER_RE = re.compile(r"^([A-Z]{2})\s{2,}([A-Z][^\d]+?)\s+(\d{1,3})\s*$")
# Variant: canton header with same-line cantonale name (e.g. "AI Appenzell ... 1 Appenzell Innerrhoden").
CANTON_HEADER_INLINE_RE = re.compile(
    r"^([A-Z]{2})\s{2,}([A-Z][^\d]+?)\s+(\d{1,3})\s+(.+?)\s*$"
)


@dataclass
class OfagEntry:
    """One AOC as listed in the OFAG répertoire."""
    name: str                       # the AOC name (verbatim from OFAG)
    canton: str                     # primary canton code (2-letter, lower)
    cantons: list[str] = field(default_factory=list)   # all listed cantons
    tier: str = "cantonale"         # cantonale | régionale | locale
    abbrev: str = ""                # OFAG-listed abbreviation for primary canton


def slugify(s: str) -> str:
    """Same slugify as elsewhere in the corpus — NFKD strip + kebab-case."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def _canton_from_name(name: str) -> str | None:
    """Resolve a canton name (as printed in OFAG, e.g. 'Bern / Berne',
    'Valais / Wallis', 'Basel-Stadt') to its 2-letter code."""
    target = name.strip().casefold()
    for code, canonical in CANTON_NAME.items():
        if canonical.casefold() == target:
            return code
    # Tolerant fallback: substring on slugified form.
    target_slug = slugify(name)
    for code, canonical in CANTON_NAME.items():
        if slugify(canonical) == target_slug:
            return code
    return None


def _tier_for_position(pos: int) -> str | None:
    """Tier classification based on the indent (column position) of an
    AOC-name line. Returns None for positions outside the data columns."""
    if COL_CANTONALE_MIN <= pos < COL_CANTONALE_MAX:
        return "cantonale"
    if COL_REGIONALE_MIN <= pos < COL_REGIONALE_MAX:
        return "régionale"
    if pos >= COL_LOCALE_MIN:
        return "locale"
    return None


def parse(text: str) -> list[OfagEntry]:
    """Parse the OFAG répertoire text (pdftotext -layout output) into
    a list of AOC entries. Skips header/preamble lines automatically.

    The PDF has two tables: a per-canton AOC-count summary on page 1
    (ends with "Total ... 63") and the actual AOC-name table on
    pages 2-3 (also ends with "Total"). We start the parse AFTER the
    first "Total" line and stop on the second."""
    entries: list[OfagEntry] = []
    by_slug: dict[str, OfagEntry] = {}
    current_canton: str | None = None
    seen_first_data_block = False  # set after we've crossed the first "Total"

    lines = text.splitlines()

    def _emit(name: str, tier: str, canton: str, abbrev: str) -> None:
        name = name.strip()
        if not name:
            return
        slug = slugify(name)
        if slug in by_slug:
            ex = by_slug[slug]
            if canton not in ex.cantons:
                ex.cantons.append(canton)
            return
        entry = OfagEntry(
            name=name,
            canton=canton,
            cantons=[canton],
            tier=tier,
            abbrev=abbrev,
        )
        entries.append(entry)
        by_slug[slug] = entry

    for line in lines:
        raw = line.rstrip()
        if not raw.strip():
            continue
        # Skip column-header / footer / language-marker repeats. The
        # "cantonale" / "regionale" tokens reliably mark a repeated
        # column-header band emitted between page breaks.
        if any(s in raw for s in (
            "Abréviation", "Abkürzung", "Abbreviazione", "Nombre", "Anzahl",
            "Numero di DOC", "Office fédéral", "Schwarzenburgstrasse",
            "pflanzlicheprodukte", "blw.admin.ch", "Répertoire suisse",
            "Schweizerisches Verzeichnis", "Repertorio svizzero",
            "Situation au", "Stand per", "Stato al",
            "cantonale", "Kantonale", "régionale", "regionale",
            "Regionale", "locale", "Lokale", "AOC / KUB", "AOC/KUB",
        )):
            continue
        if raw.strip().startswith("Total"):
            if seen_first_data_block:
                # End of AOC-name table on page 3.
                break
            # End of the page-1 canton-count summary table — skip to
            # the AOC-name table below.
            seen_first_data_block = True
            current_canton = None
            continue

        m_inline = CANTON_HEADER_INLINE_RE.match(raw)
        m_header = CANTON_HEADER_RE.match(raw) if not m_inline else None
        m = m_inline or m_header
        if m:
            abbrev = m.group(1)
            canton_name_field = m.group(2).strip()
            # Authoritative: canton name → code. Abbreviation is checked
            # and a typo warning issued, but name wins.
            code = _canton_from_name(canton_name_field)
            if code is None:
                # Last-resort: look up by abbreviation.
                code = CANTON_CODE_BY_ABBREV.get(abbrev)
            if code is None:
                # Not a canton header (probably a header repeat we
                # didn't filter); ignore.
                continue
            expected_abbrev = code.upper()
            if abbrev != expected_abbrev:
                print(
                    f"[ofag-parser] WARN typo in OFAG PDF: abbreviation {abbrev!r} "
                    f"for canton {canton_name_field!r} — expected {expected_abbrev!r}",
                    file=sys.stderr,
                )
            current_canton = code
            if m_inline and seen_first_data_block:
                # Same-line cantonale name (e.g. AI).
                _emit(m.group(4), "cantonale", code, expected_abbrev)
            continue

        if not seen_first_data_block or current_canton is None:
            continue
        # Indented AOC line: classify by column position.
        pos = len(raw) - len(raw.lstrip())
        tier = _tier_for_position(pos)
        if tier is None:
            continue
        name_value = raw.strip()
        # Footnote markers like "1" or "2" appended in superscript can
        # appear; strip trailing single-digit isolated tokens.
        name_value = re.sub(r"\s+\d{1,2}\s*$", "", name_value).strip()
        if not name_value or name_value.lower().startswith("total"):
            continue
        _emit(name_value, tier, current_canton, current_canton.upper())

    return entries


def parse_path(path) -> list[OfagEntry]:
    """Convenience: parse a file path containing pdftotext output."""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse(text)


def to_dicts(entries: Iterable[OfagEntry]) -> list[dict]:
    """JSON-friendly form for the spine file."""
    return [
        {
            "name": e.name,
            "slug": slugify(e.name),
            "canton": e.canton,
            "cantons": e.cantons,
            "tier": e.tier,
            "abbrev": e.abbrev,
        }
        for e in entries
    ]
