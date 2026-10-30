"""Does a `both`-provenance terroir fact state something only Wikipedia says?

`both` means each of the fact's two quotes grounds in its source, not that
every claim of the bullet does: the model joins the regulator's sentence and
Wikipedia's in one bullet, and the part only Wikipedia states was shown on the
card without the Wikipedia marker (Manchuela's "13 °C … 600 l/m²", Somontano's
"fueron los romanos quienes consolidaron el cultivo de la vid", La Palma's
tea-barrel duration; card validator, 2026-10-30). This test finds that part.

A term of the bullet is Wikipedia's alone when the fact's `wiki_quote` carries
it and the regulator text does not. The regulator text is the whole record —
the lien 02d graded against, plus every string of the record's extracted
documents (the cahier's other sections, the national-spec and EU-register
sidecars) — because a claim the lien lacks but the area section or the
description states is the regulator's too (Brindisi's comuni, Bonarda's
tasting note). Terms are numbers (a standalone figure: the "2" of "m²" is not
one) and word stems (the first five letters of a word of five letters or
more, accents folded), unit words left out ("metros" against the lien's "m").

The part is Wikipedia's when the bullet carries a Wikipedia-only number, a
Wikipedia-only proper noun (a capitalised word inside the sentence), or two
Wikipedia-only stems; one common word alone is too often an inflection the
regulator writes differently ("llamadas", "mediante"). A German bullet
capitalises every noun, so there the proper-noun shortcut is off and a word
part needs two stems (`source_lang` "de": the DE / AT caches, the German CH
ones). Run `wikipart-2026-10-30`: 119 of the 1,555 `both` facts, the
Manchuela and the Somontano bullet among them. The gate drops the field when
it rewrites a bullet, and stage 04 shows the marker on a `both` fact without
it, so a verdict read on an older text is never carried forward.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_NUM_RE = re.compile(r"(?<![^\W\d_])\d+(?:[.,\s]\d{3})*(?:[.,]\d+)?")
_WORD_RE = re.compile(r"[^\W\d_]{5,}")
_INNER_CAP_RE = re.compile(r"(?<=[\w,;)»”'’]\s)([^\W\d_]{5,})")
STEM = 5
UNIT_STEMS = frozenset({
    "metro", "meter", "metre", "kilom", "hecta", "grado", "degre", "celsi",
    "litro", "liter", "litre", "milim", "millim",
})


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().replace("ς", "σ")


def _numbers(s: str) -> set[str]:
    out = set()
    for m in _NUM_RE.finditer(s):
        t = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", m.group(0)).replace(",", ".")
        out.add(t)
    return out


def _stems(s: str) -> set[str]:
    return {w[:STEM] for w in _WORD_RE.findall(s)}


def _proper_stems(bullet: str) -> set[str]:
    return {fold(w)[:STEM] for w in _INNER_CAP_RE.findall(bullet or "") if w[0].isupper()}


def wiki_only_terms(bullet: str, regulator_text: str, wiki_quote: str, *,
                    capitalised_nouns: bool = True) -> dict[str, list[str]]:
    """The bullet's terms its `wiki_quote` carries and the regulator text lacks.
    `capitalised_nouns` False (German): a capital inside the sentence marks no
    proper noun."""
    b, r, w = fold(bullet), fold(regulator_text), fold(wiki_quote)
    numbers = sorted((_numbers(b) & _numbers(w)) - _numbers(r))
    words = sorted((_stems(b) & _stems(w)) - _stems(r) - UNIT_STEMS)
    proper = sorted(set(words) & _proper_stems(bullet)) if capitalised_nouns else []
    return {"numbers": numbers, "words": words, "proper": proper}


def has_wiki_only_part(terms: dict[str, list[str]]) -> bool:
    return bool(terms["numbers"] or terms["proper"] or len(terms["words"]) >= 2)


def _strings(o, out: list[str]) -> None:
    if isinstance(o, str):
        out.append(o)
    elif isinstance(o, dict):
        for v in o.values():
            _strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _strings(v, out)


def record_documents_text(country: str, slug: str) -> str:
    """Every string of the record's extracted regulator documents: the stage-02
    record and each sidecar of the same slug (national spec, register fiche)."""
    if country == "fr":
        dirs = [ROOT / "raw" / "inao" / "cahier-extracted"]
    else:
        dirs = [d for d in sorted((ROOT / "raw" / country).glob("*extracted*"))
                if d.is_dir() and "baseline" not in d.name]
    out: list[str] = []
    for d in dirs:
        p = d / f"{slug}.json"
        if not p.exists():
            continue
        try:
            _strings(json.loads(p.read_text(encoding="utf-8")), out)
        except (ValueError, OSError):
            continue
    return "\n".join(out)


def mark_wiki_parts(facts: list[dict], regulator_text: str, source_lang: str = "") -> int:
    """Set `wiki_part` on every `both` fact (dropped from the others); returns
    the number of facts whose value changed. `source_lang` is the bullets'
    language (the cache's `source_lang`): German turns the proper-noun test off."""
    changed = 0
    for f in facts:
        if f.get("provenance") == "both":
            new = has_wiki_only_part(wiki_only_terms(
                f.get("bullet") or "", regulator_text, f.get("wiki_quote") or "",
                capitalised_nouns=(source_lang or "").lower() != "de"))
            if f.get("wiki_part") is not new:
                f["wiki_part"] = new
                changed += 1
        elif "wiki_part" in f:
            del f["wiki_part"]
            changed += 1
    return changed
