"""Shared parser for the EU register 'fiche technique' PDF — the EU single
document delivered as a browser-gated attachment (see
`scripts/_lib/eambrosia_register.py`).

The `I. <single document>` block is the standard EU single-document template
(numbered sections 1..N: name, categories, description, practices, area,
principal varieties, link/terroir, other conditions). Numbering RESTARTS
under `II. <other information>`. `parse_fiche_sections` slices the `I.` block
and returns `(sections, titles)` keyed by section number, so the caller can
route them with its existing per-language `SECTION_ROLE_KEYWORDS`.

Two layout hazards the template poses, both handled here:
- Section 2 (categories) enumerates EU product categories as deeper-indented
  sub-items whose numbers can collide with a real top-level number
  (CZ: `3. Likérové víno` vs the real `3. POPIS VÍNA`). A monotonic 1→N run
  is therefore gated by an **indentation guard** — real top-level headers sit
  at the left margin (≤ 6 cols); the category sub-items are indented further.
- pdftotext interleaves per-page furniture (running header + dossier ref) and
  the register leaks untranslated `label.*` i18n keys; both are stripped.

Callers pass the localized anchor/end phrases (FR `DOCUMENT UNIQUE` /
`AUTRES INFORMATIONS`, CZ `JEDINÝ DOKLAD` / `DALŠÍ INFORMACE`, …).
"""

from __future__ import annotations

import re

_HEADER_RE = re.compile(r"^([ \t]*)([0-9]+)\.\s+(\S[^\n]*?)\s*$", re.M)
_LABEL_NOISE_RE = re.compile(r"^\s*label\.[\w.]+\s*$", re.M)
# Two kinds of pdftotext-interleaved page furniture: (a) a localized
# ALL-CAPS running header ending in a "N / M" page number — "FICHE TECHNIQUE
# 4 /8", "TECHNICAL FILE 1 /9", "FORMÁLNÍ ČÁST 28 /40", "ФИШ 2 /7", …; and
# (b) the dossier-reference line. A normal prose line is mixed-case and does
# not end in "N / M", so the all-caps + page-tail shape is a safe drop.
_PAGE_NOISE_RE = re.compile(
    r"^[ \t]*(?:[A-ZÀ-ÖØ-ÞĀ-ſΆ-ϿЀ-ӿ][A-ZÀ-ÖØ-ÞĀ-ſ"
    r"Ά-ϿЀ-ӿ .'/-]*\s+\d+\s*/\s*\d+"  # ALL-CAPS running header + "N / M"
    r"|(?:Num[ée]ro de dossier|File number|[ČC][íi]slo spisu)\s*:"  # dossier ref
    r"|Ref\. Ares)"
    r".*$",  # consume the rest of the line (trailing "Číslo spisu: …" etc.)
    re.M,
)
# Real top-level headers sit at the left margin; the section-2 product-
# category sub-items are indented further. 6 columns clears every fiche seen
# (BE sub-items at 7, CZ at 8; top-level at 0-4).
_TOP_LEVEL_MAX_INDENT = 6


def parse_fiche_sections(
    text: str, anchor_terms: tuple[str, ...], end_terms: tuple[str, ...],
) -> tuple[dict[str, str], dict[str, str]]:
    """Slice the `I. <single document>` block into (sections, titles)."""
    text = text.replace("\x0c", "")
    anchor_re = re.compile("|".join(re.escape(t) for t in anchor_terms), re.I)
    a = anchor_re.search(text)
    if not a:
        return {}, {}
    region = text[a.end():]
    if end_terms:
        end_re = re.compile("|".join(re.escape(t) for t in end_terms), re.I)
        e = end_re.search(region)
        if e:
            region = region[: e.start()]
    region = _LABEL_NOISE_RE.sub("", region)
    region = _PAGE_NOISE_RE.sub("", region)

    headers: list[tuple[str, str, int]] = []
    last_top = 0
    for m in _HEADER_RE.finditer(region):
        indent, num, title = m.group(1), m.group(2), m.group(3).strip().rstrip(":").strip()
        if len(indent.expandtabs()) > _TOP_LEVEL_MAX_INDENT:
            continue  # category sub-item, not a top-level header
        if not title[:1].isalpha():
            continue
        n = int(num)
        if n != last_top + 1:
            continue
        last_top = n
        headers.append((str(n), title, m.start()))
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
    return sections, titles
