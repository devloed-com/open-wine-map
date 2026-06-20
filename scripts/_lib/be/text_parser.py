"""Text-mode parsers for BE wine specifications delivered as PDF
(non-EU-OJ-HTML) — runs against pdftotext -layout output and produces
the same `(sections, titles)` shape that the EU-OJ HTML parser yields,
so downstream stages (route_sections, parse_grapes, parse_styles,
build_record) work unchanged.

Two text-mode flavours:

1. **`parse_enig_document_text`** — for Vlaamse overheid PDFs that
   are structurally EU "Enig documents" (a numbered 1..9 outline). The
   geconsolideerd enig document for Vlaamse mousserende kwaliteitswijn
   and the productdossier for Vlaamse landwijn match this template.

2. **`parse_fiche_technique_text`** — for the eAmbrosia EU register
   "fiche technique" PDF whose `I. DOCUMENT UNIQUE` block is the
   standard single-document template (FR). Used for the Walloon wines
   whose only EU-OJ reference is a non-fetchable Ares(...) summary —
   the register attachment carries the varieties + terroir narrative
   that the (abrogated) WALLEX ministerial decrees lacked.

Both produce a `(sections, titles)` pair whose keys are stringy section
numbers ("1", "2", …) keyed against the existing
`SECTION_ROLE_KEYWORDS["nl"]` / `["fr"]` tables, so the rest of stage 02
treats the PDF and HTML inputs identically.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────────── pdftotext wrapper ──


def pdftotext(pdf_path: Path) -> str:
    """Return -layout-mode plaintext from a PDF. Empty string on error."""
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return r.stdout or ""


# ──────────────────────────────────────── flemish EU-template (text) ──


# `   N. Title` or `N. Title` where Title starts with a capital letter
# and may run on to the next line. Use `[ \t]*` (not `\s*`) so the
# leading match doesn't eat the prior `\n` — otherwise re.MULTILINE
# anchors at the previous blank line and the body slice includes the
# header itself.
_FLEMISH_HEADER_RE = re.compile(
    r"^[ \t]*([0-9]+)\.\s+([A-ZÀ-Ö][^\n]*?)\s*$",
    re.MULTILINE,
)
# Header that begins with `N.` then whitespace then a continuation of
# the previous line wrap (the EU template often breaks long titles
# across two lines).
_FLEMISH_HEADER_CONTINUATION_RE = re.compile(r"^\s{6,}([a-zà-ö].+?)\s*$")


def _normalise_title(raw: str, body_before_next_header: str) -> str:
    """Some Flemish headers wrap across 2 lines (e.g. section 4's
    "Een beschrijving van de wijn (zijn belangrijkste analytische en
    organoleptische kenmerken):" runs into the next text line). The
    detection is: the body has a continuation line indented at the
    same level. We keep just the first line for the canonical title
    — it's enough for keyword routing."""
    return raw.strip().rstrip(":").strip()


def parse_enig_document_text(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse a Vlaamse overheid 'geconsolideerd enig document' PDF
    text into (sections, titles) keyed by section number. Section
    bodies include all lines between this header and the next."""
    # pdftotext emits form-feed (\x0c) at page breaks; strip them so
    # they don't sit between the post-`\n` anchor and the leading
    # spaces of a section header and block the match.
    text = text.replace("\x0c", "")
    headers: list[tuple[str, str, int]] = []
    for m in _FLEMISH_HEADER_RE.finditer(text):
        num = m.group(1)
        title = _normalise_title(m.group(2), "")
        # Reject the 4-digit year (e.g. "2024") that occasionally
        # matches the pattern in the footer or address blocks.
        if len(num) == 4 and num.isdigit():
            continue
        headers.append((num, title, m.start()))
    if not headers:
        return {}, {}
    sections: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, start) in enumerate(headers):
        end = headers[i + 1][2] if i + 1 < len(headers) else len(text)
        # Slice from end of the header line to start of next header
        header_end = text.find("\n", start) + 1 if text.find("\n", start) != -1 else start
        body = text[header_end:end].strip()
        # Collapse internal newlines but preserve paragraph breaks
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        sections[num] = body
        titles[num] = title
    return sections, titles


# ───────────────────────────────────── EU fiche-technique (DOCUMENT UNIQUE) ──


# The eAmbrosia register serves, per GI, an EU "fiche technique" PDF whose
# `I. DOCUMENT UNIQUE` block is the standard single-document template
# (1 Dénomination … 5 Zone délimitée, 6 Cépages principaux, 7 Description
# du ou des liens [terroir], 8 Autres conditions). Numbering RESTARTS under
# `II. AUTRES INFORMATIONS`, so we slice to the `I.` block only and keep a
# strictly increasing 1→N run (the sub-items "1. Vin" / "4. Vin mousseux"
# under section 2 break monotonicity and are dropped — the Malta/HU idiom).
_FT_ANCHOR_RE = re.compile(r"I\.\s*DOCUMENT\s+UNIQUE", re.I)
_FT_END_RE = re.compile(r"II\.\s*AUTRES\s+INFORMATIONS", re.I)
_FT_HEADER_RE = re.compile(r"^[ \t]*([0-9]+)\.\s+([A-ZÀ-Ý][^\n]*?)\s*$", re.M)
# i18n placeholder keys leak into the PDF when a sub-field was left blank
# (e.g. "label.newWineName.singleDocument.linkWithArea.conciseDetails").
_FT_LABEL_NOISE_RE = re.compile(r"^\s*label\.[\w.]+\s*$", re.M)
# Per-page furniture pdftotext interleaves mid-section (running header +
# dossier ref) — drop so it can't land inside a section body.
_FT_PAGE_NOISE_RE = re.compile(
    r"^.*(?:FICHE TECHNIQUE\s+\d+\s*/\s*\d+|Num[ée]ro de dossier:|Ref\. Ares).*$",
    re.M | re.I,
)
# Section 6 lists each variety as "* Name COLOUR (OIV)" / "** Name (OTHER)".
_FT_GRAPE_PREFIX_RE = re.compile(r"^\s*\*+\s*")
_FT_GRAPE_SUFFIX_RE = re.compile(r"\s*\((?:OIV|OTHER)\)\s*$", re.I)


def parse_fiche_technique_text(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse the `I. DOCUMENT UNIQUE` block of an eAmbrosia fiche-technique
    PDF into the standard (sections, titles) shape, keyed against the FR
    `SECTION_ROLE_KEYWORDS`."""
    text = text.replace("\x0c", "")
    a = _FT_ANCHOR_RE.search(text)
    if not a:
        return {}, {}
    region = text[a.end():]
    e = _FT_END_RE.search(region)
    if e:
        region = region[: e.start()]
    region = _FT_LABEL_NOISE_RE.sub("", region)
    region = _FT_PAGE_NOISE_RE.sub("", region)

    headers: list[tuple[str, str, int]] = []
    last_top = 0
    for m in _FT_HEADER_RE.finditer(region):
        n = int(m.group(1))
        if n != last_top + 1:
            continue
        last_top = n
        headers.append((str(n), m.group(2).strip().rstrip(":").strip(), m.start()))
    if not headers:
        return {}, {}

    sections: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, (num, title, start) in enumerate(headers):
        end = headers[i + 1][2] if i + 1 < len(headers) else len(region)
        nl = region.find("\n", start)
        header_end = nl + 1 if nl != -1 else start
        body = region[header_end:end].strip()
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        sections[num] = body
        titles[num] = title

    # Clean the variety section: strip the "*"/"**" bullets and the
    # "(OIV)"/"(OTHER)" origin tags so the shared grape parser sees one
    # bare variety name per line.
    grape_num = next(
        (n for n, t in titles.items() if "cépages" in t.lower() or "cepages" in t.lower()),
        None,
    )
    if grape_num and sections.get(grape_num):
        cleaned = []
        for ln in sections[grape_num].splitlines():
            ln = _FT_GRAPE_PREFIX_RE.sub("", ln)
            ln = _FT_GRAPE_SUFFIX_RE.sub("", ln).strip()
            if ln:
                cleaned.append(ln)
        sections[grape_num] = "\n".join(cleaned)
    return sections, titles
