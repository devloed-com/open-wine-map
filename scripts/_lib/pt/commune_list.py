"""Parse a PT caderno's "Área Delimitada" section for a flat list of
municípios (concelhos) and distritos.

PT cadernos enumerate the production area at three levels of precision:

  - distrito ("Todos os municípios dos distritos de Braga e de Viana do
    Castelo") — expand to all CAOP municípios in those distritos.
  - município ("os municípios de Arganil, Oliveira do Hospital e Tábua")
    — direct match against CAOP município names.
  - freguesia ("as freguesias de Anelhe, Arcossó, …, do concelho de
    Chaves") — freguesia-precision. For v1 we collect the parent
    município ("Chaves") and let the município polygon stand in;
    freguesia-precision refinement is a follow-up.

Cadernos mix all three patterns in a single area section, often
inside the same paragraph. The parser walks every regex match,
strips freguesia-tail clauses, splits on the Portuguese list
separators (`,`, ` e `, `;`, newlines), and returns a deduped set
of concelho names + distrito names.

Returned shape:
  {
    "concelhos": [name, …],   # município names, deduped, preserved case
    "distritos": [name, …],   # distrito names for the "todos os…" pattern
    "raw_hits": int,          # match-count for the audit
  }

False positives are filtered by:
  - dropping tokens that contain stopword fragments (`abrange`,
    `freguesia`, `até`, `ribeira`, `limite`, …)
  - dropping tokens with letter-letter-letter spacing artefacts from
    pdftotext (`a b r a n g e`)
  - requiring each candidate to start with an uppercase letter and
    be at least 3 characters long after trimming articles
"""

from __future__ import annotations

import re
import unicodedata

_MUNICIPIO_RE = re.compile(
    r"munic[íi]pios?\s+(?:de|da|do|das|dos)\s+([^.;:]+?)"
    r"(?:[.;:]|\bcom\s+exce[çc][ãa]o\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_CONCELHO_RE = re.compile(
    r"concelhos?\s+(?:de|da|do|das|dos)\s+([^.;:]+?)"
    r"(?:[.;:]|\bcom\s+exce[çc][ãa]o\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_DISTRITO_ALL_RE = re.compile(
    r"todos\s+os\s+munic[íi]pios\s+(?:do|dos)\s+distritos?\s+de\s+"
    r"([^.;:]+?)[.;:]",
    re.IGNORECASE | re.DOTALL,
)
# "abrange todo o distrito de Faro" / "todos os concelhos do distrito de X"
_WHOLE_DISTRITO_RE = re.compile(
    r"(?:abrange\s+)?(?:todo|toda|todos|todas)\s+(?:o|a|os|as)\s+"
    r"distritos?\s+de\s+([^.;:,]+?)(?:[.;:,]|$)",
    re.IGNORECASE | re.DOTALL,
)
# Bullet-style "• O distrito de Santarém, à exceção do concelho de Ourém"
# (Tejo, Lisboa). The capital `O`/`Os` is the definite article — this
# form is whole-distrito-minus-exception. Distinguish from "Do/Dos
# distrito" (a scoping prefix to a concelho list) by anchoring on the
# bullet start AND requiring CAPITAL O/Os (case-sensitive).
_BULLET_WHOLE_DISTRITO_RE = re.compile(
    r"(?:^|[\n•·*-])\s*(?:O|Os)\s+distritos?\s+de\s+"
    r"([^.;,\n]+?)(?:[.,;]|\s+(?:à|a)\s+exce[çc][ãa]o|$)",
    re.MULTILINE,
)

# Bare "Distrito de Setúbal." standalone at start of section / line.
# Península de Setúbal's whole area section is literally one sentence:
# "Distrito de Setúbal." with no "todo / abrange" preamble.
# Anchored at start-of-text or start-of-line and capped by a period
# to keep prose mentions out.
_BARE_DISTRITO_RE = re.compile(
    r"(?:^|\n)\s*Distritos?\s+de\s+([^.;:\n,]+?)\s*\.",
)

# Bullet-list concelho pattern — `• Armamar:`, `• Lamego;`,
# `•Tarouca.` (Terras de Cister). Captures the head token-cluster of
# each bullet line, before the first `:` / `;` / `,` / `.`. Restricted
# to short heads (≤ 35 chars) so multi-line bullet bodies don't leak
# in. Bullet chars: `•` (U+2022), `·` (U+00B7), `*`, `-`.
_BULLET_CONCELHO_RE = re.compile(
    r"(?:^|\n)\s*[•·*]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ'\- ]{2,34}?)\s*[:;.,\n]",
)

# Whole-archipelago / whole-RAM patterns. The caderno declares the
# production area as the entire autonomous region rather than
# enumerating its concelhos. Emits a `macro_regions` token that
# `geometry.union_from_parsed` expands into the constituent ilhas.
_MACRO_ACORES_RE = re.compile(
    r"(?:arquip[ée]lago|regi[ãa]o\s+aut[óo]noma)\s+dos\s+A[çc]ores",
    re.IGNORECASE,
)
_MACRO_MADEIRA_RE = re.compile(
    r"(?:arquip[ée]lago|regi[ãa]o\s+aut[óo]noma|regi[ãa]o\s+demarcada)"
    r"\s+da\s+Madeira",
    re.IGNORECASE,
)

# Stop-phrases — when one of these appears inside a captured group, we
# take only the text BEFORE it (so "Almeida, as freguesias de X, Y" →
# we keep "Almeida" only). Bairrada-style "União das freguesias" and
# letter-spaced "a b r a n g e" artefacts also fall into this bucket.
_TAIL_STOPS = re.compile(
    r"\b(?:as\s+freguesias?\s+de|a\s+freguesia\s+de|"
    r"(?:da|na|de)\s+Uni[ãa]o\s+(?:de|das)\s+freguesias?|"
    r"Uni[ãa]o\s+(?:de|das)\s+freguesias?|"
    r"abrange|a\s+b\s+r\s+a\s+n\s+g\s+e"
    r"|com\s+exce[çc][ãa]o|inclui|passa|limita|estende-se|onde|cujo)\b",
    re.IGNORECASE,
)

# Tokens that look like prose noise (boundary descriptions, prepositions).
# Any candidate containing one of these phrases is discarded — Alentejo's
# area section is mostly boundary prose ("Estremoz até à ribeira da Fonte
# Boa") which would otherwise admit "Estremoz" plus a long noise tail.
_NOISE_WORDS = re.compile(
    r"\b(?:at[ée]|ribeira|limite|estrada|serra|barragem|junta|caminho|"
    r"prossegue|segue|continua|ponto|cruzamento|altitude|albufeira)\b",
    re.IGNORECASE,
)

# Single-letter spacing artefact: "a b r a n g e", "f r e g u e s i a".
_LETTER_SPACING = re.compile(r"\b(?:[a-zà-ÿ]\s){2,}[a-zà-ÿ]\b", re.IGNORECASE)

# Token-level cleanup
_LEADING_ARTICLE = re.compile(
    r"^(?:de\s+|da\s+|do\s+|das\s+|dos\s+|e\s+|o\s+|a\s+|os\s+|as\s+)+",
    re.IGNORECASE,
)
_TRAILING_NOISE = re.compile(r"[\s,.;:)\]]+$")
_TRAILING_CONJUNCTION = re.compile(r"\s+e\s*$", re.IGNORECASE)
# pdftotext layout occasionally inserts spaces around hyphens: "Montemor
# -o -Novo" should fold back to "Montemor-o-Novo".
_HYPHEN_SPACING = re.compile(r"\s*-\s*")
# Strip parenthetical content from a candidate ("Mourão (a área total
# das três freguesias" → "Mourão").
_PAREN_TAIL = re.compile(r"\s*\(.*$", re.DOTALL)


def _strip_freguesia_tail(captured: str) -> str:
    """Take only the text up to the first stop-phrase. The captured
    group often opens with the município name and then drops into
    freguesia detail — we want just the município."""
    m = _TAIL_STOPS.search(captured)
    if m:
        return captured[: m.start()].strip()
    return captured.strip()


def _looks_like_name(token: str) -> bool:
    """Crude filter: keep tokens that look like proper-noun place names."""
    if not token or len(token) < 3:
        return False
    if _NOISE_WORDS.search(token):
        return False
    if _LETTER_SPACING.search(token):
        return False
    # First non-whitespace char must be uppercase (after diacritic strip)
    ascii_form = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    if not ascii_form or not ascii_form[0].isupper():
        return False
    # Allow internal hyphens, apostrophes, lower-case particles (de, da, do),
    # but cap token length so we don't admit long sentences.
    if len(token) > 60:
        return False
    return True


def _split_list(text: str) -> list[str]:
    """Split a Portuguese enumeration into candidate name tokens.
    Separators: comma, semicolon, newline, ` e ` (with word boundaries).
    Pdftotext often breaks names across newlines — normalise first."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"\s*,\s*|\s*;\s*|\s+e\s+", text)
    out = []
    for raw in parts:
        p = _PAREN_TAIL.sub("", raw)
        p = _LEADING_ARTICLE.sub("", p).strip()
        p = _TRAILING_CONJUNCTION.sub("", p)
        p = _TRAILING_NOISE.sub("", p)
        # Heal "Montemor -o -Novo" / "Idanha -a -Nova" pdftotext spacing.
        if "-" in p:
            p = _HYPHEN_SPACING.sub("-", p)
        if not p:
            continue
        out.append(p)
    return out


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        key = unicodedata.normalize("NFKD", it).encode("ascii", "ignore").decode().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def parse_commune_list(area_text: str) -> dict:
    """Walk the area text, return {concelhos, distritos, macro_regions, raw_hits}.

    `concelhos` is a list of município names in the canonical
    Portuguese form (with diacritics) preserving case. `distritos`
    is the same for the "todos os municípios do distrito de X" form
    — callers expand it via a CAOP distrito index. `macro_regions`
    is a list of `"acores"` / `"madeira"` tokens emitted when the
    caderno declares the area as the whole autonomous region —
    callers expand each into its constituent ilhas.
    """
    if not area_text:
        return {"concelhos": [], "distritos": [], "macro_regions": [], "raw_hits": 0}

    raw_hits = 0
    concelhos: list[str] = []
    distritos: list[str] = []
    macro_regions: list[str] = []

    for pat in (_MUNICIPIO_RE, _CONCELHO_RE):
        for m in pat.finditer(area_text):
            raw_hits += 1
            captured = _strip_freguesia_tail(m.group(1))
            for token in _split_list(captured):
                if _looks_like_name(token):
                    concelhos.append(token)

    for m in _BULLET_CONCELHO_RE.finditer(area_text):
        raw_hits += 1
        token = m.group(1).strip()
        if _looks_like_name(token):
            concelhos.append(token)

    for pat in (_DISTRITO_ALL_RE, _WHOLE_DISTRITO_RE, _BULLET_WHOLE_DISTRITO_RE,
                _BARE_DISTRITO_RE):
        for m in pat.finditer(area_text):
            raw_hits += 1
            for token in _split_list(m.group(1)):
                if _looks_like_name(token):
                    distritos.append(token)

    if _MACRO_ACORES_RE.search(area_text):
        raw_hits += 1
        macro_regions.append("acores")
    if _MACRO_MADEIRA_RE.search(area_text):
        raw_hits += 1
        macro_regions.append("madeira")

    return {
        "concelhos": _dedupe_preserve_order(concelhos),
        "distritos": _dedupe_preserve_order(distritos),
        "macro_regions": _dedupe_preserve_order(macro_regions),
        "raw_hits": raw_hits,
    }
