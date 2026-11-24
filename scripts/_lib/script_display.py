"""Greek and Cyrillic names in a Latin-language interface.

Rules settled with Boris on 2026-11-17 (CLAUDE.md "Greek and Cyrillic names
on screen"):

* **Two kinds of surface.** Interface text — a filter chip, a search row, a
  prose line, a title, a description, a browse list, an MCP answer — leads
  with the Latin form and keeps the original in brackets where there is
  room: "Mavrud (Мавруд)". A surface that quotes the regulator — the card's
  name, a grape pill showing the document's spelling — keeps the original
  first: "Мавруд (Mavrud)".
* **Which Latin form.** The catalogue's name where one exists (a grape's VIVC
  prime: Sultanina, Rkatsiteli; an appellation's EU-register transcription),
  else the national standard — ELOT 743 for Greek, the Streamlined System for
  Bulgarian (`_lib/romanise.py`). Never a mechanical ASCII fold: unidecode
  writes "Akheloi" for Ахелой (Aheloy) and "Atheri" for Αθήρι (Athiri).
* **The original is language-tagged** (`lang="el"` / `lang="bg"`, WCAG 3.1.2)
  wherever it is written into a page.
* Lists sort by the Latin form; search matches both.

The corpus has two non-Latin scripts and one language each: Greek (Greece,
Cyprus) and Bulgarian. A third would need its own entry here and in the
JavaScript mirror (`scriptLang` / `nativeHtml` in app.js).
"""

from __future__ import annotations

import re

from _lib import romanise

_GREEK = "Ͱ-Ͽἀ-῿"
_CYRILLIC = "Ѐ-ӿ"
GREEK_RE = re.compile(f"[{_GREEK}]")
CYRILLIC_RE = re.compile(f"[{_CYRILLIC}]")
NON_LATIN_RE = re.compile(f"[{_GREEK}{_CYRILLIC}]")

# A regulator's berry-colour code after a variety name ("Αθήρι Β", "Λιάτικο
# Ν"): a code, not a letter of the name — ELOT 743 would write "Athiri V".
_COLOUR_CODE_RE = re.compile(r"\s+(?:B|N|G|Rs|Rg|RS|Β|Ν|Γ)\.?$")

# A run of one script inside a longer string: its letters, and the spaces,
# digits, hyphens, apostrophes and combining marks between them. The run ends
# on a letter, so "Мелник 82" tags "Мелник" and "Naoussa (Νάουσα)" tags the
# bracket's content only. Mirrored by NATIVE_RUN_RES in app.js.
_BETWEEN = r"\s0-9̀-ͯ’.\-"


def _run_re(letters: str) -> re.Pattern:
    return re.compile(f"[{letters}](?:[{letters}{_BETWEEN}]*[{letters}])?")


_RUNS: tuple[tuple[str, re.Pattern], ...] = (
    ("el", _run_re(_GREEK)),
    ("bg", _run_re(_CYRILLIC)),
)


def script_lang(text: str) -> str:
    """The language of a string in another script: "el", "bg" or ""."""
    if GREEK_RE.search(text or ""):
        return "el"
    if CYRILLIC_RE.search(text or ""):
        return "bg"
    return ""


def romanise_name(name: str) -> str:
    """The national-standard Latin form of a Greek or Cyrillic name, its
    trailing colour code dropped; "" for a name already in Latin script."""
    lang = script_lang(name)
    if not lang:
        return ""
    base = _COLOUR_CODE_RE.sub("", (name or "").strip())
    return (romanise.elot743(base) if lang == "el" else romanise.bg_streamlined(base)).strip()


def latin_name(native: str, catalogue: str = "") -> str:
    """The Latin form an interface surface leads with: the catalogue's name
    where one exists, else the national standard; "" for a Latin name."""
    if not script_lang(native):
        return ""
    return (catalogue or "").strip() or romanise_name(native)


def _esc(s: str) -> str:
    # content_block.esc / app.js escapeHtml: the same entity set, & first
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def native_html(text: str) -> str:
    """`text` escaped for HTML, every Greek or Cyrillic run language-tagged."""
    out = _esc(text or "")
    for lang, pattern in _RUNS:
        out = pattern.sub(lambda m, lang=lang: f'<span lang="{lang}">{m.group(0)}</span>', out)
    return out
