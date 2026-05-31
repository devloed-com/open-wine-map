"""Text-mode parsers for BE wine specifications delivered as PDF
(non-EU-OJ-HTML) — runs against pdftotext -layout output and produces
the same `(sections, titles)` shape that the EU-OJ HTML parser yields,
so downstream stages (route_sections, parse_grapes, parse_styles,
build_record) work unchanged.

Two text-mode flavours:

1. **`parse_enig_document_text`** — for Vlaamse overheid PDFs that
   are structurally EU "Enig documents" (a numbered 1..9 outline). The
   geconsolideerd enig document for Vlaamse mousserende kwaliteitswijn
   matches this template exactly.

2. **`parse_wallex_text`** — for Walloon WALLEX arrêtés ministériels
   that bundle multiple PDOs in one decree (Chapitre premier =
   common provisions including the area; Chapitre II = Vin mousseux
   de qualité de Wallonie, Articles 11-15; Chapitre III = Crémant de
   Wallonie, Articles 16-22). The parser splits the decree by
   chapter, then routes per slug.

3. **`parse_wallex_standalone_text`** — for a WALLEX arrêté
   ministériel that agrees a *single* AOC (no chapter split). The
   "Côtes de Sambre et Meuse" decree (WALLEX act #2879) is an annexed
   `Cahier des charges` whose Article 1 delimits the zone (bassin
   hydrographique + commune lists) and "Cépages." Article 2 lists the
   authorised varieties as a `Name;`-terminated block.

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


# ────────────────────────────────────────────── walloon WALLEX parser ──


# WALLEX uses a quirky layout: chapter and content concatenated
# without space ("Chapitre IIVin mousseux de qualité de Wallonie"),
# and articles likewise ("Art. 11.Cépages.").
_WALLEX_CHAPTER_II_RE = re.compile(
    r"Chapitre\s+II(?!I)\s*(?:Vin\s+mousseux|[^\n]+)",
    re.IGNORECASE,
)
_WALLEX_CHAPTER_III_RE = re.compile(
    r"Chapitre\s+III\s*(?:Crémant|[^\n]+)",
    re.IGNORECASE,
)
_WALLEX_ARTICLE_RE = re.compile(
    r"Art\.\s*(\d+)\.\s*([A-Z][^\n.]*?)\s*\.",
)
_WALLEX_COMMUNE_LIST_RE = re.compile(
    r"les\s+communes:\s*([^\n]+(?:\n(?!\s*«|\s*Province|\s*Art|\s*Chapitre)[^\n]+)*)",
    re.IGNORECASE,
)


def _wallex_extract_communes(chapter1_text: str) -> str:
    """Extract Article 1's commune lists from Chapter I (Dispositions
    communes). The text enumerates per-province blocks like
    `Province du Brabant wallon: « Roman Païs » les communes: ...`.
    We return a normalised single-paragraph commune list, prefixed
    with the source-province header so it remains a usable
    `geo_area` body for stage 02d."""
    pieces: list[str] = []
    # Walk the chapter 1 prose and collect every "les communes: ..." run
    # along with its preceding « ... » named-sub-area header.
    for m in re.finditer(
        r"«\s*([^»]+?)\s*»\s*les\s+communes:\s*([^\n]+(?:\n(?!\s*«|\s*Province|\s*Art\.|\s*Chapitre)[^\n]+)*)",
        chapter1_text, re.IGNORECASE,
    ):
        sub_area = m.group(1).strip()
        communes = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(",")
        pieces.append(f"« {sub_area} »: {communes}")
    return "\n".join(pieces)


def _wallex_articles_in_chapter(chapter_text: str) -> dict[str, tuple[str, str]]:
    """Return {article_number: (title, body)} for a single chapter."""
    headers = list(_WALLEX_ARTICLE_RE.finditer(chapter_text))
    out: dict[str, tuple[str, str]] = {}
    for i, m in enumerate(headers):
        num = m.group(1)
        title = m.group(2).strip()
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(chapter_text)
        body = chapter_text[body_start:body_end].strip()
        # Drop footer separators and pagination cruft
        body = re.sub(r"En vigueur du.*?page \d+\s*/\s*\d+", "", body, flags=re.S)
        body = re.sub(r"[ \t]+", " ", body).strip()
        out[num] = (title, body)
    return out


_WALLEX_GRAPE_LIST_RE = re.compile(
    r"cépages?\s+suivants?\s*:?\s*\n?\s*((?:[A-Z][^;\n]{2,40}\s*;\s*\n?\s*)+[A-Z][^;\n.]{2,40})\s*\.?",
    re.IGNORECASE,
)


def _wallex_grape_block(article_body: str) -> str:
    """The grape varieties are listed as `Chardonnay;\nPinot noir;\n...`
    after a `cépages suivants:` lead. Return the variety block as
    em-dash-separated items so it matches the existing FR grape parser
    (`_BULLET_SPLIT_RE`)."""
    m = _WALLEX_GRAPE_LIST_RE.search(article_body)
    if m:
        block = m.group(1)
    else:
        # Fallback: take every line that looks like a variety name
        # (starts with capital, is short, contains no period).
        candidates = []
        for line in article_body.splitlines():
            line = line.strip().rstrip(";").rstrip(",")
            if 3 <= len(line) <= 40 and line[0:1].isupper() and "." not in line:
                candidates.append(line)
        block = "\n".join(candidates)
    return re.sub(r"\s*;\s*", "\n", block).strip()


# WALLEX wine-rule: PDO-BE-A0011 (Vin mousseux) takes Chapter II;
# PDO-BE-A0012 (Crémant) takes Chapter III. The slug → chapter mapping
# is keyed by both file_number and slug for resilience.
WALLEX_CHAPTER_BY_SLUG: dict[str, str] = {
    "vin-mousseux-de-qualite-de-wallonie": "II",
    "cremant-de-wallonie": "III",
}
WALLEX_CHAPTER_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-BE-A0011": "II",
    "PDO-BE-A0012": "III",
}


def parse_wallex_text(
    text: str, slug: str = "", file_number: str = "",
) -> tuple[dict[str, str], dict[str, str]]:
    """Parse a Walloon WALLEX cahier into the standard (sections,
    titles) shape, scoped to the chapter corresponding to the given
    slug / file_number. Each Walloon PDO record gets its own chapter
    (II or III); the shared Chapter I supplies the geo_area body."""
    chapter = (
        WALLEX_CHAPTER_BY_SLUG.get(slug)
        or WALLEX_CHAPTER_BY_FILE_NUMBER.get(file_number)
    )
    if chapter is None:
        return {}, {}

    m2 = _WALLEX_CHAPTER_II_RE.search(text)
    m3 = _WALLEX_CHAPTER_III_RE.search(text)
    if m2 is None or m3 is None:
        return {}, {}
    # Chapter I = text[0:m2.start()]; Ch II = [m2.start():m3.start()];
    # Ch III = [m3.start():end]
    ch1_text = text[: m2.start()]
    ch2_text = text[m2.start(): m3.start()]
    ch3_text = text[m3.start():]
    ch_text = ch2_text if chapter == "II" else ch3_text

    articles = _wallex_articles_in_chapter(ch_text)
    # Grape article: II → 11, III → 16
    grape_art = "11" if chapter == "II" else "16"
    yield_art = "14" if chapter == "II" else "20"
    grape_body = ""
    if grape_art in articles:
        _, body = articles[grape_art]
        grape_body = _wallex_grape_block(body)

    # Build a synthetic sections dict that maps to the standard role
    # keys the downstream router expects (per
    # `SECTION_ROLE_KEYWORDS["fr"]` in document.py). Numbers are
    # arbitrary string keys — the router walks `titles` by keyword,
    # not by number.
    sections: dict[str, str] = {}
    titles: dict[str, str] = {}

    sections["1"] = (
        "Vin mousseux de qualité de Wallonie"
        if chapter == "II" else "Crémant de Wallonie"
    )
    titles["1"] = "Dénomination(s)"

    sections["3"] = "Vin mousseux de qualité — v.m.q.p.r.d."
    titles["3"] = "Catégories de produits de la vigne"

    sections["6"] = _wallex_extract_communes(ch1_text)
    titles["6"] = "Zone géographique délimitée"

    sections["7"] = grape_body
    titles["7"] = "Cépage(s) principal/aux"

    # Yield + practices summary (Articles 4, 5, 14/20). v1 keeps this
    # minimal — the grapes + area + provenance are the main user-facing
    # surface.
    practices_bits = []
    for art in ("4", "5"):
        if art in articles:
            t, b = articles[art]
            practices_bits.append(f"Art. {art} — {t}: {b[:300]}")
    if yield_art in articles:
        t, b = articles[yield_art]
        practices_bits.append(f"Art. {yield_art} — {t}: {b[:200]}")
    sections["5"] = "\n\n".join(practices_bits)
    titles["5"] = "Pratiques vitivinicoles"

    # No "lien au terroir" narrative section in WALLEX cahiers —
    # leave empty so 02d won't try to extract from it.
    sections["8"] = ""
    titles["8"] = "Description du / des lien(s)"

    return sections, titles


# ──────────────────────────────── walloon WALLEX single-AOC parser ──


# Single-AOC WALLEX arrêtés (one decree = one appellation, no chapter
# split). Keyed by slug + file_number for resilience, the same way the
# chapter tables are. Two shapes are handled (see parse function):
#   - Côtes de Sambre et Meuse (#2879) — annexed "Cahier des charges"
#     with "Article 1 er." zone + commune lists and a "Cépages." Art. 2
#     variety roster.
#   - Vin de pays des Jardins de Wallonie (#3256) — a flat Art. 1-13
#     decree: the area is the whole Région wallonne (Art. 2) and the
#     varieties are the broad "Vitis vinifera ou croisement" definition
#     (Art. 3) — no named roster, so 0 grapes (the broad-IGP shape).
WALLEX_STANDALONE_SLUGS: set[str] = {
    "cotes-de-sambre-et-meuse",
    "vin-de-pays-des-jardins-de-wallonie",
}
WALLEX_STANDALONE_FILE_NUMBERS: set[str] = {"PDO-BE-A0009", "PGI-BE-A0010"}
_WALLEX_STANDALONE_NAME_FALLBACK: dict[str, str] = {
    "cotes-de-sambre-et-meuse": "Côtes de Sambre et Meuse",
    "vin-de-pays-des-jardins-de-wallonie": "Vin de pays des Jardins de Wallonie",
}

_WALLEX_STD_PAGE_FOOTER_RE = re.compile(
    r"En\s+vigueur\s+du[^\n]*?page\s*\d+\s*/\s*\d+", re.IGNORECASE,
)
# Article 2's variety block runs from "…peuvent être utilisés:" to the
# closing "Les raisins doivent…" sentence.
_WALLEX_STD_GRAPE_BLOCK_RE = re.compile(
    r"c[ée]pages?\s+suivants?\s+peuvent\s+[êe]tre\s+utilis[ée]s\s*:\s*"
    r"(.*?)\n\s*Les\s+raisins\s+doivent",
    re.IGNORECASE | re.S,
)
# The zone delimitation = Article 1 up to the "Cépages." / "Art. 2."
# heading (the CSM annex shape).
_WALLEX_STD_ZONE_RE = re.compile(
    r"(Article\s+1\s*er\.?.*?)\n\s*(?:C[ée]pages?\.|Art\.\s*2\.)",
    re.IGNORECASE | re.S,
)
# Region-wide fallback (the Jardins shape): the area is stated as
# "vendanges récoltées en Région wallonne" / "vins produits en Région
# wallonne" — no commune enumeration.
_WALLEX_STD_REGION_ZONE_RE = re.compile(
    r"((?:vins?|raisins?|vendanges?)[^.\n]*?"
    r"(?:r[ée]colt[ée]es?|produits?)\s+(?:en|dans\s+la)\s+R[ée]gion\s+wallonne[^.\n]*\.)",
    re.IGNORECASE,
)
_WALLEX_STD_YIELD_RE = re.compile(
    r"(rendement\s+(?:moyen\s+)?maximal[^\n]*?\d+\s*hl/ha[^\n]*)", re.IGNORECASE,
)


def parse_wallex_standalone_text(
    text: str, slug: str = "", file_number: str = "", name: str = "",
) -> tuple[dict[str, str], dict[str, str]]:
    """Parse a single-AOC WALLEX cahier des charges into the standard
    (sections, titles) shape. Unlike `parse_wallex_text`, there is no
    chapter split. Two shapes are supported: the CSM annex ("Article 1
    er." zone + "Cépages." Art. 2 roster) and the flat region-wide IGP
    decree (Jardins de Wallonie — area = Région wallonne, no roster)."""
    if (
        slug not in WALLEX_STANDALONE_SLUGS
        and file_number not in WALLEX_STANDALONE_FILE_NUMBERS
    ):
        return {}, {}

    clean = _WALLEX_STD_PAGE_FOOTER_RE.sub("", text)

    m_grapes = _WALLEX_STD_GRAPE_BLOCK_RE.search(clean)
    grape_body = ""
    if m_grapes:
        # The list is `Pinot noir;\nMüller-Thurgau;\n…` — re-emit as
        # newline-separated items for the FR grape parser.
        grape_body = re.sub(r"\s*;\s*", "\n", m_grapes.group(1)).strip()

    m_zone = _WALLEX_STD_ZONE_RE.search(clean)
    if m_zone:
        zone_body = re.sub(r"[ \t]+", " ", m_zone.group(1)).strip()
    else:
        m_region = _WALLEX_STD_REGION_ZONE_RE.search(clean)
        zone_body = re.sub(r"[ \t]+", " ", m_region.group(1)).strip() if m_region else ""

    m_yield = _WALLEX_STD_YIELD_RE.search(clean)
    yield_line = re.sub(r"[ \t]+", " ", m_yield.group(1)).strip() if m_yield else ""

    display_name = name or _WALLEX_STANDALONE_NAME_FALLBACK.get(slug, "")
    is_igp = file_number.startswith("PGI") or slug == "vin-de-pays-des-jardins-de-wallonie"

    sections: dict[str, str] = {}
    titles: dict[str, str] = {}

    sections["1"] = display_name
    titles["1"] = "Dénomination(s)"

    sections["3"] = (
        "Vin de pays — indication géographique protégée"
        if is_igp
        else "Vin de qualité d'appellation d'origine contrôlée (V.Q.P.R.D.)"
    )
    titles["3"] = "Catégories de produits de la vigne"

    sections["5"] = yield_line
    titles["5"] = "Pratiques vitivinicoles"

    sections["6"] = zone_body
    titles["6"] = "Zone géographique délimitée"

    sections["7"] = grape_body
    titles["7"] = "Cépage(s) principal/aux"

    # No "lien au terroir" narrative section in the WALLEX cahier —
    # leave empty so 02d won't try to extract from it.
    sections["8"] = ""
    titles["8"] = "Description du / des lien(s)"

    return sections, titles
