"""Per-record grape-pill labels: the regulator's spelling, typography folded.

A pill shows the spelling the record's own document uses (stage 04
`grape_names`). Some national specifications print the variety table in
capitals — the MASAF annex rows ("CABERNET SAUVIGNON"), the ΥΠΑΑΤ and
moa.gov.cy .doc specs ("ΞΥΝΙΣΤΕΡΙ") — which is typography, not spelling,
and the client's Title Case leaves capitals alone. `fold_capitals` replaces
such a name with the corpus's own mixed-case spelling of the same word
(accents restored: ΞΥΝΙΣΤΕΡΙ → Ξυνιστέρι), else with its lower case for the
client to title — except a Greek one, which keeps its capitals: Greek drops
the tonos in capitals, so "ΣΟΒΙΝΙΟΝ" lower-cased would be a misspelling.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

# OIV colour code after a variety name ("Merlot N", "Barbera N.", Greek Β/Ν/Γ).
_COLOUR_CODE_RE = re.compile(r"\s+(?:B|N|G|Rs|Rg|RS|Β|Ν|Γ)\.?$")
_LETTER_RUN_RE = re.compile(r"[^\W\d_]{2,}")
_GREEK_RE = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
# Extraction debris around a name, never part of a spelling: PDF symbol-font
# glyphs in the Unicode private-use area (the MASAF annexes' «» and bullets),
# a running page header ("Seite 6 von 10 -7- Domina"), a list's punctuation,
# and a conjunction the list scan carried over ("Μανδηλαριά σε", "Moscato
# bianco e"). The conjunctions are a closed list: "Rayon d'Or" ends in "or".
_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")
_PAGE_HEADER_RE = re.compile(r"^\s*seite\s+\d+\s+von\s+\d+\s*(?:-\s*\d+\s*-)?\s*", re.I)
_TRAILING_CONJUNCTION_RE = re.compile(r"\s+(?:σε|και|e|ed|und|y|et)$", re.I)


def _key(name: str) -> str:
    base = _COLOUR_CODE_RE.sub("", name.strip())
    base = "".join(
        c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c)
    )
    return re.sub(r"[\W_]+", "", base.casefold())


def clean_name(name: str) -> str:
    """The name without the extraction debris around it; "" if nothing is left."""
    s = _PRIVATE_USE_RE.sub("", name or "")
    s = _PAGE_HEADER_RE.sub("", s)
    s = re.sub(r"^[\W_]+", "", s)
    s = re.sub(r"[\s,;:\-–—]+$", "", s)
    s = _TRAILING_CONJUNCTION_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def is_capitals(name: str) -> bool:
    """True for a name written in capitals ("SAVATIANO", "ΝΤΟΠΙΟ ΜΑΥΡΟ");
    a two-letter run alone ("Pinot N", "PX") is not."""
    letters = [c for c in name if c.isalpha()]
    if not letters or not any(len(m) >= 4 for m in _LETTER_RUN_RE.findall(name)):
        return False
    return all(c.isupper() for c in letters)


def mixed_case_spellings(details_lists) -> dict[tuple[str, str], str]:
    """(grape slug, folded key) → the most frequent mixed-case spelling the
    corpus uses for it, a spelling without a colour code only."""
    counts: dict[tuple[str, str], Counter] = {}
    for details in details_lists:
        for d in details or []:
            slug = d.get("slug")
            name = clean_name(d.get("name") or "")
            if not slug or not name or is_capitals(name) or _COLOUR_CODE_RE.search(name):
                continue
            counts.setdefault((slug, _key(name)), Counter())[name] += 1
    return {k: c.most_common(1)[0][0] for k, c in counts.items()}


def fold_capitals(name: str, slug: str, spellings: dict[tuple[str, str], str]) -> str:
    if not is_capitals(name):
        return name
    found = spellings.get((slug, _key(name)))
    if found:
        return found
    return name if _GREEK_RE.search(name) else name.lower()


def latin_label(name: str, transliterate) -> str:
    """The pill bracket's Latin form of `name`. A name kept in Greek capitals
    is transliterated from its lower case and titled ("ΟΦΘΑΛΜΟ" → "Ophthalmo",
    not "OPhThALMO")."""
    if not is_capitals(name):
        return transliterate(name)
    latin = transliterate(name.lower())
    return " ".join(w[:1].upper() + w[1:] for w in latin.split())
