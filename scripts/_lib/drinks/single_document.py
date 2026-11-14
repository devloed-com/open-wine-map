"""The single document of a drink GI as EUR-Lex publishes it.

A spirit drink registered after 2017 has no Art. 20 technical file: the
register lists the Official Journal C publication of its application, whose
annex is the single document of Reg. (EU) 2019/787 (name, category,
description, geographical area, method, link, …). A cider or perry GI is a
Food-class GI whose single document follows Reg. (EU) No 1151/2012 (name,
description of the product, concise definition of the geographical area,
link). Both are numbered headings over paragraphs, in the owner's language,
so the page is flattened to lines and read with the technical file's
heading words (`technical_file.ROLE_HEADINGS`).

`cached_page` reads what scripts/drinks/01b_fetch_oj_pages.py stored.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from pathlib import Path

from _lib.drinks import technical_file as tf

# two-letter path code and three-letter Formex code of EUR-Lex, per language
EURLEX_LANG: dict[str, tuple[str, str]] = {
    "bg": ("BG", "BUL"), "es": ("ES", "SPA"), "cs": ("CS", "CES"), "de": ("DE", "DEU"),
    "el": ("EL", "ELL"), "en": ("EN", "ENG"), "fr": ("FR", "FRA"), "hr": ("HR", "HRV"),
    "it": ("IT", "ITA"), "hu": ("HU", "HUN"), "nl": ("NL", "NLD"), "pt": ("PT", "POR"),
    "ro": ("RO", "RON"), "sk": ("SK", "SLK"), "sl": ("SL", "SLV"),
}

_BLOCK_RE = re.compile(r"</(?:p|div|td|th|tr|li|h[1-6]|table)\s*>|<br\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)

# "SINGLE DOCUMENT" in the corpus languages (the annex opens on it; the
# pages that precede it are the Commission's notice and the opposition rule)
_ANCHORS = (
    "single document", "document unique", "documento unico", "documento único",
    "einziges dokument", "enig document", "egységes dokumentum", "jedinstveni dokument",
    "enotni dokument", "jednotný dokument", "document unic", "единен документ",
    "ενιαιο εγγραφο", "ενιαίο έγγραφο", "technical file", "main specifications of the technical file",
    "principales especificaciones", "hauptspezifikationen", "principali specifiche",
    "a műszaki dokumentáció főbb előírásai", "основни спецификации", "summary",
)


def to_language(url: str, lang: str) -> str:
    """The EUR-Lex URL of the same act in `lang`, as inline HTML."""
    two, three = EURLEX_LANG.get(lang, EURLEX_LANG["en"])
    if "data.europa.eu/eli/" in url or "/eli/" in url:
        base = re.sub(r"^https?://data\.europa\.eu/eli/", "https://eur-lex.europa.eu/eli/", url)
        base = re.sub(r"/(?:[a-z]{3})/?$", "", base.rstrip("/"))
        return f"{base}/{three.lower()}"
    new = re.sub(r"/legal-content/[A-Z]{2}/(?:TXT|ALL)(?:/HTML)?/", f"/legal-content/{two}/TXT/HTML/", url)
    new = re.sub(r"(\.\d{2}\.)[A-Z]{3}(?=&|$)", rf"\g<1>{three}", new)
    return new


def html_to_lines(html: str) -> list[str]:
    """The page as text lines, one per block element."""
    body = _SCRIPT_RE.sub(" ", html or "")
    body = _BLOCK_RE.sub("\n", body)
    body = _TAG_RE.sub(" ", body)
    body = html_mod.unescape(body).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in body.split("\n")]
    return [ln for ln in lines if ln]


def _merge_numbered(lines: list[str]) -> list[str]:
    """EUR-Lex prints a heading number and its title as two table cells
    ("3." / "Description of the spirit drink"): join them."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if re.fullmatch(r"\(?\d{1,2}(?:\.\d{1,2})*[.)]?", ln) and i + 1 < len(lines):
            out.append(f"{ln} {lines[i + 1]}")
            i += 2
            continue
        out.append(ln)
        i += 1
    return out


def looks_like_single_document(html: str) -> bool:
    low = (html or "").lower()
    return len(low) > 6000 and any(a in low for a in _ANCHORS)


_TOP_RE = re.compile(r"^(\d{1,2})\s*\.?\s+(?!\d)(\S.{2,160})$")


def _numbered_sections(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """[(n, title, body lines)] for the top-level headings of a single
    document: "N. Title" lines whose numbers rise from 1. A sub-heading
    ("6.1. Details of the geographical area …") and a numbered step inside a
    section ("1. A gyümölcs kiválasztása" under 5) stay in the body."""
    heads: list[tuple[int, int, str]] = []
    last = 0
    for i, ln in enumerate(lines):
        m = _TOP_RE.match(ln)
        if not m:
            continue
        n = int(m.group(1))
        title = m.group(2).strip()
        if n != last + 1 or len(title) > 150 or title[:1].islower():
            continue
        # a step list restarts at 1 inside a section: keep the first run only
        heads.append((n, i, title))
        last = n
    out = []
    for j, (n, i, title) in enumerate(heads):
        stop = heads[j + 1][1] if j + 1 < len(heads) else len(lines)
        out.append((n, title, lines[i + 1: stop]))
    return out


def parse(html: str, lang: str = "") -> dict | None:
    """Slice a single-document page into the technical file's roles, or None
    when the page carries none (a WAF stub, a cancellation notice). The
    numbered top-level headings are the sections; each is given its role by
    its title (`technical_file` heading words). A page without that
    numbering falls back to the heading reader of the word-processor form."""
    lines = _merge_numbered(html_to_lines(html))
    if len(lines) < 20:
        return None
    start = 0
    low = [ln.lower() for ln in lines]
    for i, ln in enumerate(low):
        if len(ln) < 90 and any(ln.strip(" ‘’'\"“”«»„").startswith(a) for a in _ANCHORS):
            start = i + 1
    body = lines[start:]
    sections = _numbered_sections(body)
    roles: dict[str, str] = {}
    titles: dict[str, str] = {}
    if len(sections) >= 4:
        for _n, title, sec in sections:
            role = tf._heading_role(title, anywhere=True)  # noqa: SLF001 — the shared heading reader
            if role in (None, "stop") or role in roles:
                continue
            tail = title.split(":", 1)[1].strip() if ":" in title else ""
            text = tf._paragraphs(([tail] if tail else []) + sec)  # noqa: SLF001
            if len(text) < 12:
                continue
            roles[role] = text
            titles[role] = title
    if roles.get("link") or roles.get("description") or roles.get("geo_area"):
        return {"layout": "single-document", "roles": roles, "geo_nuts": [], "section_titles": titles}
    parsed = tf._parse_form(body)  # noqa: SLF001
    parsed["layout"] = "single-document"
    return parsed


def cached_page(oj_dir: Path, slug: str) -> dict | None:
    """{html, lang, source_url, final_url, sha256, fetched_at, ref} for a
    page stage 01b stored, or None."""
    manifest_path = oj_dir / "manifest.json"
    html_path = oj_dir / f"{slug}.html"
    if not manifest_path.exists() or not html_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    meta = manifest.get(slug)
    if not meta or meta.get("status") != "ok":
        return None
    return {**meta, "html": html_path.read_text(encoding="utf-8", errors="replace")}
