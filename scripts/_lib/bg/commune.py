"""Bulgarian обшина (obshtina, LAU2 / municipality) parser for the
ЕДИНЕН ДОКУМЕНТ section-6 geo-area body.

Bulgaria's three-level administrative hierarchy:

  Република (state) → Област (province, 28 of them — section marker)
                    → Община (municipality / obshtina, LAU2 unit — 265)
                    → Населено място (settlement: гр.X / town, с.X / village)

The geometry-resolver target is the **община** (commune granularity);
GISCO LAU 2024 stores Bulgarian obshtini under CNTR_CODE='BG' with
`LAU_NAME` in native Cyrillic. So both sides of the index are
Cyrillic and the normaliser preserves Cyrillic (.casefold() + collapse
whitespace + tier-prefix strip), in contrast to the RO normaliser
which NFKD-ASCII-folds (would erase Cyrillic entirely).

Bulgarian publication idioms the parser handles:

  - Province (област) as section marker: `Област Благоевград:` /
    `в област Благоевград` → demoted to a list separator (its position
    matters, but its name is not a commune).
  - Municipal tier-prefix: `община NAME` / `общините NAME, NAME` →
    `NAME`. The plural `общините` introduces a sub-list.
  - Settlement-tier prefix: `гр. NAME` / `с. NAME` / `град NAME` /
    `село NAME` → drop the settlement entirely; we only keep the
    parent obshtina. (Settlements are LAU3 in GISCO and not in the
    LAU 2024 file.)
  - Hierarchy: `с. X от община Y` / `с. X в община Y` → keep Y.
"""

from __future__ import annotations

import re

from unidecode import unidecode

# Bulgarian provinces (области, 28). Used as commune-list section
# markers, NOT as commune candidates. Stored casefolded.
_OBLAST_NAMES = frozenset({
    "благоевград", "бургас", "варна", "велико търново", "видин", "враца",
    "габрово", "добрич", "кърджали", "кюстендил", "ловеч", "монтана",
    "пазарджик", "перник", "плевен", "пловдив", "разград", "русе",
    "силистра", "сливен", "смолян", "софия", "софия-град", "стара загора",
    "търговище", "хасково", "шумен", "ямбол",
})

# Hierarchy rewrite: `с. X в община Y` / `село X от общината Y` —
# salient unit is Y (the obshtina). We rewrite to `община Y` so the
# tier-prefix strip below picks up Y, not the unmatched settlement X.
_SELO_BELONGS_RE = re.compile(
    r"\b(?:с\.|село|гр\.|град)\s+[^,;]+?\s+"
    r"(?:в|от|на|към)\s+(?:община(?:та)?|общините)\s+",
    re.IGNORECASE,
)

# Province (област) marker — `Област NAME`, `в област NAME`, … —
# consumed *with* the trailing province name (1–2 Cyrillic words) so
# the province name doesn't bleed into the obshtina-candidate list.
# Filtering by `_OBLAST_NAMES` later is unreliable because 28 of 265
# BG obshtinas share their name with their parent province (Пловдив,
# Бургас, Варна, Сливен, Видин, Враца, …) — those obshtinas must
# survive when they appear after `общините `, not after `област `.
_OBLAST_MARKER_RE = re.compile(
    r"\b(?:в\s+|на\s+)?област(?:та|ите)?\s+[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)?",
    re.IGNORECASE,
)

# Tier prefixes preceding an obshtina name — `община`, `общините`,
# `общинските` — single-form match (no case folding inside the regex,
# IGNORECASE flag carries Cyrillic).
_TIER_PREFIX_RE = re.compile(
    r"^\s*(община(?:та|ите)?|общините|общинските)\s+",
    re.IGNORECASE,
)

# Same prefix anywhere in the body — promoted to a list-separator so a
# `… се намират в общините X, Y и Z` lead-in doesn't trap the first
# obshtina name inside a long prose chunk.
_OBSHTINA_MARKER_RE = re.compile(
    r"\b(?:в\s+|на\s+|от\s+)?(?:община(?:та|ите)?|общините|общинските)\s+",
    re.IGNORECASE,
)

# Settlement-tier prefix. Drop the settlement entirely; the parent
# obshtina is what we want. If the surrounding text doesn't name a
# parent obshtina, the settlement was probably the commune-name itself
# (some BG obshtini share their name with a town — Лясковец, Сандански,
# Мелник). To handle that case, we keep the name *and* let the obshtina
# resolver try it as a candidate.
_SETTLEMENT_PREFIX_RE = re.compile(
    r"^\s*(с\.|село|гр\.|град)\s+",
    re.IGNORECASE,
)

# Splitter — comma, semicolon, em-dash, en-dash, "и", newline, colon.
# Em-dash is used in BG publications as a sub-list separator: the
# obshtina is listed before the em-dash, its constituent settlements
# after, all on one line.
_COMMUNE_SPLIT_RE = re.compile(r"\s*[,;:\n—–]\s*|\s+и\s+", re.IGNORECASE)

# Chunks starting with a settlement-tier prefix (`с.` / `село` / `гр.` /
# `град`) name settlements, not obshtini — drop them entirely. The
# parent obshtina is found elsewhere in the list (preceded by `община`
# or implicit at the start of a sub-list bullet).
_SETTLEMENT_DROP_RE = re.compile(
    r"^\s*(с\.|село|гр\.|град)\s+",
    re.IGNORECASE,
)

# Tokens whose presence in a chunk signals it is prose, not an obshtina
# name. Casefolded Cyrillic + Latin (for romanised quotes).
_PROSE_TOKENS = frozenset({
    "район", "райони", "райна", "географски", "географската",
    "географския", "очертан", "очертана", "очертаният", "очертаните",
    "демаркиран", "демаркирана", "демаркираният", "демаркираните",
    "включва", "включват", "включително", "обхваща", "обхващат",
    "разположен", "разположена", "следните", "следните се", "както",
    "следва", "както следва", "землището", "землищата", "териториите",
    "територии", "лозовите", "лозя", "лозята", "винарски", "винарска",
    "вино", "вината", "виното", "произведени", "произведено", "от",
    "за", "на", "за която", "регистрирано",
})

# Drop these as not-an-obshtina-name tokens (connectives / wine-law
# verbs that may survive the tier-prefix strip).
_DROP_WORDS = frozenset({
    "и", "или", "както", "така", "това", "тези", "който", "която",
    "включително", "изключително", "съответно", "именно", "точно",
    "в", "на", "при", "от", "за", "до", "с", "край", "над", "под",
    "общините", "общината", "общинските",
    # Bulgarian months — appear in publication-date stretches that
    # bleed into the area description.
    "януари", "февруари", "март", "април", "май", "юни", "юли",
    "август", "септември", "октомври", "ноември", "декември",
})


def _normalise_commune(name: str) -> str:
    """Cyrillic-preserving normaliser. casefold + tier-prefix strip +
    collapse hyphens/whitespace. The GISCO LAU index keys on this form.
    Bulgarian commune names like «Велико Търново» normalise to
    "велико търново"."""
    if not name:
        return ""
    s = name.strip()
    s = s.casefold()
    s = _TIER_PREFIX_RE.sub("", s)
    s = _SETTLEMENT_PREFIX_RE.sub("", s)
    # Strip trailing parenthesised qualifiers / brackets.
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return s


def _ascii_key(name: str) -> str:
    """Romanised fallback key — only consulted when the Cyrillic
    lookup misses (e.g. older texts quote obshtina names in transliterated
    form). Both sides of any ascii-keyed index are produced via the same
    function."""
    s = _normalise_commune(name)
    s = re.sub(r"[^a-z0-9 ]+", " ", unidecode(s))
    return re.sub(r"\s+", " ", s).strip()


def _truncate_at_terroir_section(text: str) -> str:
    """Section 6 text sometimes bleeds into section 7 (grape varieties)
    without a clean break — cut at the well-known Bulgarian section-7
    lead-in to avoid grape names leaking into the commune list."""
    marker_re = re.compile(
        r"\b(основни?\s+(?:сортове|винени)|винени\s+сортове|сорт(?:ове)?\s+грозде)",
        re.IGNORECASE,
    )
    m = marker_re.search(text)
    return text[: m.start()] if m else text


def parse_commune_list(text: str) -> list[str]:
    """Extract obshtina names from an ЕДИНЕН ДОКУМЕНТ section-6 area body.

    Result: deduped list of canonical obshtina-name candidates that the
    geometry resolver unions against the GISCO LAU `BG_*` polygon set.
    Order preserved for debug-log readability.
    """
    if not text:
        return []
    body = _truncate_at_terroir_section(text)
    body = _SELO_BELONGS_RE.sub("община ", body)
    body = _OBLAST_MARKER_RE.sub(", ", body)
    body = _OBSHTINA_MARKER_RE.sub(", ", body)

    seen: set[str] = set()
    out: list[str] = []
    for raw in _COMMUNE_SPLIT_RE.split(body):
        chunk = raw.strip(" .,;:")
        if not chunk:
            continue
        if _SETTLEMENT_DROP_RE.match(chunk):
            continue
        chunk = _TIER_PREFIX_RE.sub("", chunk).strip(" .,;:")
        if not chunk:
            continue
        key = _normalise_commune(chunk)
        if not key or key in seen:
            continue
        if any(t in _PROSE_TOKENS for t in key.split()):
            continue
        if len(key.split()) > 5:
            continue
        if key in _DROP_WORDS or len(key) < 3:
            continue
        seen.add(key)
        out.append(chunk)
    return out
