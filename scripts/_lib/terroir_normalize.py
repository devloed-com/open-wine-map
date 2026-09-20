"""Deterministic clean-up of terroir-fact bullets (stage-04 render + the
`normalize_terroir_facts.py` cache post-pass).

Three mechanical defects the 2026-09-11 review found in 8–12 % of bullets,
none of which needs a model to fix:

- regulatory colour codes copied from the cahier's grape roster
  ("Pinot noir N", "Riesling B", "Gewurztraminer Rs") — stripped when the
  preceding words resolve to a grape in the lexicon, so a stray capital
  after a place name is left alone;
- the INAO mentions "VT" / "SGN" left unexpanded — spelled out;
- no terminal punctuation — a period is appended;
- residual Greek / Cyrillic script in a Latin-target translation: a
  homoglyph inside a Latin word ("Thermoheliоhydric" with a Cyrillic о,
  "Piniatorοs" with a Greek ο) is mapped to its Latin lookalike, and a
  whole non-Latin token left as a gloss ("(ξερολιθιές)", "(смолница)",
  "Мискет врачански") is transliterated with unidecode. Only applied to
  the four target locales, only when the bullet is predominantly Latin
  (a Greek source bullet rendered untranslated is left alone), and never
  to a Greek-letter chemical prefix ("α-terpineol").

Arrows, label prefixes and "according to the document" are left to a
targeted re-extraction under the prompt rules in `terroir_prompts`: they
need rewording, not a regex.
"""

from __future__ import annotations

import re

from unidecode import unidecode

from _lib import grape_entity, grape_lexicon

COLOUR_CODES = ("N", "B", "G", "Rs", "Rg")
_CODE_RE = re.compile(r"(?:\s+|\s*\()(N|B|G|Rs|Rg)\)?(?=[\s,;:.)\]/]|$)")
# apostrophes split ("l'ugni blanc" → l / ugni / blanc) so the elided article never hides a name
_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)
_MAX_NAME_WORDS = 4

_EXPANSIONS = [
    (re.compile(r"\bVT\s*/\s*SGN\b"), "Vendanges Tardives / Sélection de Grains Nobles"),
    (re.compile(r"\bVT\b"), "Vendanges Tardives"),
    (re.compile(r"\bSGN\b"), "Sélection de Grains Nobles"),
]
_TERMINAL = ".!?…"
_TARGET_LOCALES = ("en", "fr", "es", "nl")
_NON_LATIN = re.compile(r"[Ѐ-ӿͰ-Ͽ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_CHEM_PREFIX = re.compile(r"^[αβγδ]-\w")
_HOMOGLYPH = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "к": "k", "м": "m", "т": "t", "н": "n", "в": "v", "ѕ": "s", "ԁ": "d", "ԛ": "q",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X", "І": "I", "Ј": "J",
    "К": "K", "М": "M", "Т": "T", "Н": "H", "В": "B", "Ѕ": "S",
    "ο": "o", "ς": "s", "σ": "s", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "n", "ρ": "p",
    "τ": "t", "υ": "u", "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
_HOMOGLYPH_CHARS = {chr(k) for k in _HOMOGLYPH}


_VOCAB = None


def _is_grape(name: str) -> bool:
    """True when `name` is a known variety surface: the grape matcher's exact
    index (VIVC prime names + synonyms + the lexicon) first, then the
    lexicon tables for surfaces the index does not carry."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = grape_entity._load_vocabulary()
    if grape_entity._normalise(name) in _VOCAB.exact_index:
        return True
    slug = grape_lexicon._canonical_slug(name)
    return bool(slug) and (slug in grape_lexicon.DEFAULT_COLOUR or slug in grape_lexicon.GRAPE_ALIAS)


def strip_colour_codes(bullet: str) -> str:
    """Remove ` N` / ` B` / ` G` / ` Rs` / ` Rg` (also `(B)`) after a grape name."""
    out = bullet
    pos = 0
    while True:
        m = _CODE_RE.search(out, pos)
        if not m:
            return out
        before = out[: m.start()]
        words = _WORD_RE.findall(before)[-_MAX_NAME_WORDS:]
        hit = any(_is_grape(" ".join(words[i:])) for i in range(len(words)))
        if hit:
            out = before + out[m.end():]
            pos = m.start()
        else:
            pos = m.end()


def expand_mentions(bullet: str) -> str:
    for rx, full in _EXPANSIONS:
        bullet = rx.sub(full, bullet)
    return bullet


def ensure_terminal_period(bullet: str) -> str:
    b = bullet.rstrip()
    if not b or b[-1] in _TERMINAL:
        return b
    return b + "."


def _latinize_token(token: str) -> str:
    if _CHEM_PREFIX.match(token):
        return token
    letters = _LETTER.findall(token)
    non_latin = [c for c in letters if _NON_LATIN.match(c)]
    if not non_latin:
        return token
    if len(non_latin) * 2 < len(letters) and all(c in _HOMOGLYPH_CHARS for c in non_latin):
        return token.translate(_HOMOGLYPH)  # a stray lookalike inside a Latin word
    return "".join(unidecode(c) if _NON_LATIN.match(c) else c for c in token)


def latinize_residual_script(bullet: str) -> str:
    """Latin-script a mostly-Latin bullet: homoglyphs mapped, whole
    non-Latin tokens transliterated. A bullet whose letters are ≥ 80 %
    non-Latin is left untouched — it is an untranslated source bullet, not
    a residue."""
    letters = _LETTER.findall(bullet)
    if not letters:
        return bullet
    share = sum(1 for c in letters if _NON_LATIN.match(c)) / len(letters)
    if share == 0 or share >= 0.8:
        return bullet
    return re.sub(r"\S+", lambda m: _latinize_token(m.group(0)), bullet)


def normalize_bullet(bullet: str, lang: str = "") -> str:
    """Apply every deterministic fix. `lang` is the locale the bullet is
    rendered in: for the four target locales residual Greek / Cyrillic
    script is also Latinised."""
    if not bullet:
        return bullet
    out = expand_mentions(strip_colour_codes(bullet))
    if lang in _TARGET_LOCALES:
        out = latinize_residual_script(out)
    return ensure_terminal_period(out)


def normalize_facts(facts: list[dict], lang: str = "") -> int:
    """Normalise `bullet` on every fact in place; returns how many changed."""
    n = 0
    for f in facts:
        b = f.get("bullet") or ""
        nb = normalize_bullet(b, lang)
        if nb != b:
            f["bullet"] = nb
            n += 1
    return n


def normalize_aocs(aocs: dict[str, dict], lang: str = "") -> dict[str, dict]:
    """Stage-04 hook: return a new aocs dict whose `terroir_facts.facts[].bullet`
    are normalised. Records are copied, never mutated — the per-locale dicts
    share record objects with the source `aocs`."""
    out: dict[str, dict] = {}
    for slug, rec in aocs.items():
        tf = rec.get("terroir_facts")
        facts = (tf or {}).get("facts") if isinstance(tf, dict) else None
        if not facts:
            out[slug] = rec
            continue
        new_facts = [{**f, "bullet": normalize_bullet(f.get("bullet") or "", lang)} for f in facts]
        if all(a.get("bullet") == b.get("bullet") for a, b in zip(facts, new_facts)):
            out[slug] = rec
            continue
        out[slug] = {**rec, "terroir_facts": {**tf, "facts": new_facts}}
    return out
