"""Parse a BLE Landwein-g.g.A. Produktspezifikation PDF.

Sibling of `produktspezifikation.py` (the per-Anbaugebiet quality-wine
parser). The 15 German Landwein g.g.A. that ship as stubs (no fetchable
EU Einziges Dokument) carry their canonical variety roster + terroir
text only in the BLE national Produktspezifikation, hosted at
https://www.ble.de/SharedDocs/Downloads/DE/Ernaehrung-Lebensmittel/
EU-Qualitaetskennzeichen/Wein/Antraege/Landweingebiete/
01_Produktspezifikationen_Landweine/Landwein_<Fragment>.pdf.

These PDFs are *Amtliche Werke* per §5 UrhG — free reuse with attribution.

Unlike the 13 Anbaugebiete PDFs (four rigid section-numbered templates),
the Landwein specs are heterogeneous: the variety roster sits at §6, §7,
or §8 depending on the document, grouped by colour subheader
("Weißweinsorten" / "Rot- und Roséweinsorten" / "Weiße Rebsorten") OR by
per-Bundesland prose paragraph (Landwein Rhein lists Hessen / NRW /
Rheinland-Pfalz rosters separately). Section numbers are therefore not
reliable anchors.

The parser locates the variety section by KEYWORD ("N. Rebsorten" /
"N. Zugelassene Keltertraubensorten"), slices to the next top-level
numbered header, and runs the shared grape lexicon over the candidate
phrases — the same robust whole-section scan the CH règlement parser
uses. Landwein has no principal/accessory split (the spec lists one flat
roster), so every variety resolves as `principal`; the per-grape colour
comes from the lexicon matcher downstream, not from the colour subheaders.

Output shape mirrors `produktspezifikation.extract` so stage 02f's
`_build_record` consumes both uniformly (the empty principal list routes
to the `section-8-flat-no-split` branch → all-principal):

  {
    "template": "landwein-lexikon-scan",
    "section_3_2_principal_names": [],            # no role split
    "section_8_white_names": [<candidate phrases>],
    "section_8_red_names": [],
    "zusammenhang_text": "...",                   # §-Zusammenhang terroir
  }
"""

from __future__ import annotations

import re
from pathlib import Path

from .produktspezifikation import (
    _PAGE_FURNITURE_RE,
    _strip_paren,
    pdf_to_text,
)

# "N. Rebsorten" / "N. Zugelassene Keltertraubensorten" — variety-section
# header at whatever top-level number the document uses (§6 / §7 / §8).
_VAR_HDR_RE = re.compile(
    r"^\s*(\d+)\s*\.?\s+(?:Rebsorten|Zugelassene\s+(?:Kelter|Keller)traubensorten)\s*\.?\s*$",
    re.M,
)
# Terroir section — two title variants across the Landwein corpus:
#   "N. Angaben, aus denen sich der Zusammenhang … ergibt"  (Rhein, Ahrtaler, …)
#   "N. Zusammenhang mit dem geografischen Gebiet"          (Badischer, Neckar, …)
_ZUS_HDR_RE = re.compile(
    r"^\s*(\d+)\s*\.?\s*(?:Angaben,?\s+aus\s+denen\s+sich\s+der\s+Zusammenhang"
    r"|Zusammenhang\s+mit\s+dem\s+geografischen\s+Gebiet)",
    re.M,
)
# Colour subheaders used as delimiters between variety runs (so the
# header word doesn't glue onto the first variety of the next colour).
_COLOUR_HDR_RE = re.compile(
    r"(?:Wei(?:ß|ss)e?\s+Rebsorten"
    r"|Wei(?:ß|ss)wein(?:e|sorten)?"
    r"|Rote\s+Rebsorten"
    r"|Rot[\s/–-]*(?:und[\s/–-]*)?R[oó]s[ée]wein(?:e|sorten)?"
    r"|Rotwein(?:e|sorten)?"
    r"|Ros[ée]wein(?:e|sorten)?)\s*:?",
    re.I,
)
# Inline "7.2" sub-section numbers embedded in a run-together line.
_NUMTOK_RE = re.compile(r"\b\d+\.\d+\b")
# Prose markers — a candidate carrying any of these is regulatory boilerplate
# (the per-Bundesland sentences), not a variety name.
_PROSE_MARKERS = (
    "rebsort", "keltertrauben", "vinifera", "gattung", "gewonnen", "gekeltert",
    "kreuzung", "anbau", "angabe", "auflistung", "art vitis", "herstellung",
    "darüber", "folgende", "ländern", "versuch", "erzeugung", "zugelassen",
    "befindlich", "nordrhein", "westfalen", "rheinland", "anbaueignung",
)


def _top_header_re(n: int) -> re.Pattern[str]:
    return re.compile(rf"^\s*{n}\s*\.?\s+\S", re.M)


def _variety_section(text: str) -> str:
    m = _VAR_HDR_RE.search(text)
    if not m:
        return ""
    n = int(m.group(1))
    end = _top_header_re(n + 1).search(text, m.end())
    return text[m.end(): end.start() if end else len(text)]


def _candidates(blob: str) -> list[str]:
    blob = _PAGE_FURNITURE_RE.sub("", blob)
    # De-hyphenate pdftotext line-break splits ("Bur-\ngunder" → "Burgunder").
    flat = re.sub(r"([a-zäöüß])-\s+([a-zäöüß])", r"\1\2", blob)
    flat = re.sub(r"\s+", " ", flat)
    flat = _NUMTOK_RE.sub(",", flat)
    flat = _COLOUR_HDR_RE.sub(",", flat)
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;:]|\s+und\s+|\bsowie\b|\.\s", flat):
        name = _strip_paren(part).strip(" .:–-")
        if len(name) <= 2 or len(name.split()) > 4:
            continue
        low = name.lower()
        if any(marker in low for marker in _PROSE_MARKERS):
            continue
        if low in ("alle", "sonstige", "sorten", "weine", "wein"):
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _zusammenhang(text: str) -> str:
    m = _ZUS_HDR_RE.search(text)
    if not m:
        return ""
    z = int(m.group(1))
    end = _top_header_re(z + 1).search(text, m.end())
    block = text[m.start(): end.start() if end else len(text)]
    cleaned: list[str] = []
    prev_empty = False
    for line in block.splitlines():
        if _PAGE_FURNITURE_RE.match(line):
            continue
        line = line.rstrip()
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(line)
        prev_empty = is_empty
    return "\n".join(cleaned).strip()


def extract(pdf_path: Path) -> dict:
    """Parse a BLE Landwein Produktspezifikation PDF. See module docstring."""
    text = pdf_to_text(pdf_path)
    return {
        "template": "landwein-lexikon-scan",
        "section_3_2_principal_names": [],
        "section_8_white_names": _candidates(_variety_section(text)),
        "section_8_red_names": [],
        "zusammenhang_text": _zusammenhang(text),
    }
