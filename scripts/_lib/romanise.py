"""Search-only romanisations of Greek- and Cyrillic-script appellation names.

GR / CY records carry the regulator's Greek name plus the EU register's own
Latin transcription (`name_latin`, e.g. "Ayio Oros"); BG records carry the
Cyrillic name plus a Latin bracket. Visitors type the *national*
romanisation ("agio oros", "targovishte"), which matches neither. Every
function here is a pure, deterministic derivation of the regulator's own
string — no new data, no licence — and feeds the search index only.

- `elot743`         ELOT 743 / ISO 843 type-1 transliteration of Greek.
- `bg_streamlined`  Bulgaria's official Streamlined System (Transliteration
                    Act 2009).
- `fold_confusables` repairs Latin strings typed with a Greek / Cyrillic
                    homoglyph (the EU transcription of Αργολίδα is "Αrgolida"
                    with GREEK CAPITAL ALPHA as its first letter).
- `search_key`      the Python mirror of app.js `searchNormalize`.
- `search_forms`    the extra forms a record should be findable by.
- `latin_form_bg`   the BG bracket (what bg/02_extract_pliegos.py shows).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from unidecode import unidecode

_GREEK_SINGLE = {
    "α": "a",
    "β": "v",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "ζ": "z",
    "η": "i",
    "θ": "th",
    "ι": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "φ": "f",
    "χ": "ch",
    "ψ": "ps",
    "ω": "o",
}
_GREEK_GAMMA_DIGRAPHS = {"γ": "ng", "ξ": "nx", "χ": "nch", "κ": "gk"}
_GREEK_VOWELS = set("αεηιουω")
_GREEK_VOICED = set("βγδζλμνρ")
_ACCENT_MARKS = {"́", "̀", "͂"}
_DIALYTIKA = "̈"

_BG_SINGLE = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sht",
    "ъ": "a",
    "ь": "y",
    "ю": "yu",
    "я": "ya",
}
_BG_COUNTRY = "българия"

_CONFUSABLES = {
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "ο": "o",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
}

# Every run of non-letter characters splits sub-tokens, so "Asti/ΑΤΗΝΑ" keeps
# its Greek word: a slash or comma must isolate a native word as a hyphen does.
_SUBTOKEN_SEPARATORS = re.compile(r"([^\w]+|_+)")
_NON_ALNUM_RUN = re.compile(r"[\W_]+")


def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch).startswith("L")


def _is_greek(ch: str) -> bool:
    return ("Ͱ" <= ch <= "Ͽ" or "ἀ" <= ch <= "῿") and _is_letter(ch)


def _is_cyrillic(ch: str) -> bool:
    return "Ѐ" <= ch <= "ԯ" and _is_letter(ch)


def _is_latin(ch: str) -> bool:
    return _is_letter(ch) and unicodedata.name(ch, "").startswith("LATIN")


@dataclass(frozen=True)
class _Cell:
    char: str
    marks: frozenset[str]
    scripted: bool


def _cells(text: str, in_script, form: str) -> list[_Cell]:
    """Split normalised text into cells. A letter of the target script absorbs
    the combining marks that follow it (so accents are stripped before
    mapping); everything else, marks on Latin letters included, passes
    through as-is. Greek is decomposed (NFD) so the tonos comes off; Cyrillic
    is composed (NFC) because й is canonically и + breve and must stay й."""
    cells: list[_Cell] = []
    for ch in unicodedata.normalize(form, text):
        if unicodedata.category(ch) == "Mn" and cells and cells[-1].scripted:
            last = cells[-1]
            cells[-1] = _Cell(last.char, last.marks | {ch}, True)
            continue
        cells.append(_Cell(ch, frozenset(), in_script(ch)))
    return cells


def _cased(out: str, cells: list[_Cell], i: int) -> str:
    """Casing follows the source letter by letter: a lowercase source letter
    gives lowercase; an uppercase one gives an uppercase first letter, and the
    whole multi-letter output ("CH", "OU") when the adjacent source letter —
    the next one, or the previous one at the end of a word — is uppercase too."""
    if not cells[i].char.isupper():
        return out
    adjacent = None
    if i + 1 < len(cells) and cells[i + 1].scripted:
        adjacent = cells[i + 1]
    elif i > 0 and cells[i - 1].scripted:
        adjacent = cells[i - 1]
    if adjacent is not None and adjacent.char.isupper():
        return out.upper()
    return out[:1].upper() + out[1:]


def _greek_vowel_digraph(cells: list[_Cell], i: int) -> str | None:
    """ου / αυ / ευ / ηυ starting at `i`, or None when the pair is not a
    digraph (an accent on the first vowel or a dialytika on the second)."""
    c0 = cells[i].char.lower()
    nxt = cells[i + 1]
    if nxt.char.lower() != "υ" or c0 not in "αεηο":
        return None
    if cells[i].marks & _ACCENT_MARKS or _DIALYTIKA in nxt.marks:
        return None
    if c0 == "ο":
        return "ou"
    after = cells[i + 2] if i + 2 < len(cells) and cells[i + 2].scripted else None
    voiced = after is not None and after.char.lower() in (_GREEK_VOWELS | _GREEK_VOICED)
    return _GREEK_SINGLE[c0] + ("v" if voiced else "f")


def _greek_chunk(cells: list[_Cell], i: int) -> tuple[str, int]:
    """Transliterate the letter(s) starting at `i`; returns (output, span)."""
    c0 = cells[i].char.lower()
    has_next = i + 1 < len(cells) and cells[i + 1].scripted
    c1 = cells[i + 1].char.lower() if has_next else ""
    at_word_start = i == 0 or not cells[i - 1].scripted

    if c0 == "γ" and c1 in _GREEK_GAMMA_DIGRAPHS:
        return _GREEK_GAMMA_DIGRAPHS[c1], 2
    if c0 == "μ" and c1 == "π":
        at_word_end = not (i + 2 < len(cells) and cells[i + 2].scripted)
        return ("b" if at_word_start or at_word_end else "mp"), 2
    if c0 == "ν" and c1 == "τ":
        return "nt", 2
    digraph = _greek_vowel_digraph(cells, i) if has_next else None
    if digraph is not None:
        return digraph, 2
    if c0 in _GREEK_SINGLE:
        return _GREEK_SINGLE[c0], 1
    return unidecode(cells[i].char), 1


def elot743(text: str) -> str:
    """ELOT 743 / ISO 843 type-1 transliteration of the Greek letters in
    `text`; Latin letters, digits, spaces and punctuation pass through
    unchanged ("Malvasia Χάνδακας-Candia" → "Malvasia Chandakas-Candia").

    Accents (tonos, dialytika, every combining mark) are stripped from Greek
    letters before mapping. Digraphs come first: γγ ng, γξ nx, γχ nch, γκ gk;
    μπ b at the start or end of a word and mp inside one; ντ nt; ου ou; αυ / ευ / ηυ
    av / ev / iv before a vowel or a voiced consonant (β γ δ ζ λ μ ν ρ) and
    af / ef / if before a voiceless consonant or at the end of the word. As
    in the standard, an accent on the first vowel or a dialytika on the
    second breaks the vowel digraph ("άυπνος" → "aypnos", "Καΐκι" → "Kaiki").
    Casing follows the source (see `_cased`); the final sigma maps like σ."""
    cells = _cells(text, _is_greek, "NFD")
    out: list[str] = []
    i = 0
    while i < len(cells):
        if not cells[i].scripted:
            out.append(cells[i].char)
            i += 1
            continue
        chunk, span = _greek_chunk(cells, i)
        out.append(_cased(chunk, cells, i))
        i += span
    return unicodedata.normalize("NFC", "".join(out))


def _bg_word(cells: list[_Cell], start: int, end: int) -> str:
    word = "".join(c.char for c in cells[start:end])
    if word.lower() == _BG_COUNTRY:
        if word.isupper():
            return "BULGARIA"
        return "Bulgaria" if word[0].isupper() else "bulgaria"
    out: list[str] = []
    i = start
    while i < end:
        c0 = cells[i].char.lower()
        if c0 == "и" and i + 2 == end and cells[i + 1].char.lower() == "я":
            out.append(_cased("ia", cells, i))
            i += 2
            continue
        chunk = _BG_SINGLE.get(c0)
        out.append(_cased(chunk, cells, i) if chunk else unidecode(cells[i].char))
        i += 1
    return "".join(out)


def bg_streamlined(text: str) -> str:
    """Bulgaria's official Streamlined System (Transliteration Act, 2009):
    а a, б b, в v, г g, д d, е e, ж zh, з z, и i, й y, к k, л l, м m, н n,
    о o, п p, р r, с s, т t, у u, ф f, х h, ц ts, ч ch, ш sh, щ sht, ъ a,
    ь y, ю yu, я ya; a word-final "ия" is "ia" (София → Sofia) and the
    country name България is "Bulgaria". Casing follows the source (see
    `_cased`); non-Cyrillic characters pass through unchanged."""
    cells = _cells(text, _is_cyrillic, "NFC")
    out: list[str] = []
    i = 0
    while i < len(cells):
        if not cells[i].scripted:
            out.append(cells[i].char)
            i += 1
            continue
        end = i
        while end < len(cells) and cells[end].scripted:
            end += 1
        out.append(_bg_word(cells, i, end))
        i = end
    return unicodedata.normalize("NFC", "".join(out))


def _fold_subtoken(token: str) -> str:
    has_latin = False
    for ch in token:
        if _is_latin(ch):
            has_latin = True
        elif _is_letter(ch) and ch not in _CONFUSABLES:
            return token
    if not has_latin:
        return token
    return "".join(_CONFUSABLES.get(ch, ch) for ch in token)


def fold_confusables(text: str) -> str:
    """Replace Greek / Cyrillic letters that are visual homoglyphs of Latin
    letters (Α→A, Ο→O, Р→P, с→c, …) inside Latin words.

    The rule is applied per sub-token — the pieces between whitespace and
    hyphens — and a sub-token is folded only when it contains at least one
    Latin letter AND every one of its non-Latin letters is in the homoglyph
    table. So "Αrgolida" becomes "Argolida", while "Άγιο Όρος" (no Latin
    letter) and "Malvasia Χάνδακας-Candia" (the Greek sub-token carries ν δ
    κ ς, which are not homoglyphs) are left exactly as they are: a genuine
    Greek or Cyrillic word must never be Latinised by this function."""
    parts = _SUBTOKEN_SEPARATORS.split(text)
    return "".join(part if n % 2 else _fold_subtoken(part) for n, part in enumerate(parts))


# JS's \p{Diacritic} also covers spacing marks that are not category Mn — the
# modifier-letter block (ʼ ʰ ˆ ˇ …), the Latin-1 accents (´ ¨ ¯ ¸ ^ `), the
# middle dot and the Greek tonos / dialytika signs — and deletes them where
# a plain "non-letter" fold would leave a space ("dʼAlba" → "dalba").
_SPACING_DIACRITICS = frozenset(
    {"\u005e", "\u0060", "\u00a8", "\u00af", "\u00b4", "\u00b7", "\u00b8",
     "\u0374", "\u0375", "\u037a", "\u0384", "\u0385"}
    | {chr(c) for c in range(0x02B0, 0x0300)}
)


def search_key(text: str) -> str:
    """Python mirror of `searchNormalize` in scripts/_lib/assets/app.js (NFD,
    drop combining marks, lower-case — not casefold, which would turn ς into
    σ where JS `toLowerCase` does not), then every run of non-letter /
    non-digit characters collapsed to one space and the ends stripped. Used
    only to decide whether two forms are the same to the search box."""
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(
        ch for ch in decomposed
        if unicodedata.category(ch) != "Mn" and ch not in _SPACING_DIACRITICS
    )
    return _NON_ALNUM_RUN.sub(" ", stripped.lower()).strip()


def search_forms(name: str, name_latin: str, country: str) -> list[str]:
    """The extra search-only forms for a record: the national romanisation
    plus the unidecode spelling (GR / CY: ELOT 743; BG: the Streamlined
    System — so the old unidecode bracket stays findable after the displayed
    bracket switches, and the official form is findable whatever `name_latin`
    holds). Forms already covered by the name or the (confusable-folded)
    `name_latin` are dropped, as are duplicates and empty strings; order is
    preserved. Every other country gets no extra form."""
    if country in ("gr", "cy"):
        candidates = [elot743(name), unidecode(name)]
    elif country == "bg":
        candidates = [bg_streamlined(name), unidecode(name)]
    else:
        return []
    taken = {search_key(name), search_key(fold_confusables(name_latin or ""))}
    forms: list[str] = []
    for form in candidates:
        form = form.strip()
        key = search_key(form)
        if not form or not key or key in taken:
            continue
        taken.add(key)
        forms.append(form)
    return forms


def latin_form_bg(name: str) -> str:
    """The Latin bracket for a BG record: the Streamlined-System form when it
    differs from the native name, else "" (a name already in Latin script
    gets no bracket)."""
    latin = bg_streamlined(name or "").strip()
    return latin if latin and latin != name else ""
