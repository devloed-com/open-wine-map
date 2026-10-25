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
})
# Bulgarian months — appear in publication-date stretches that bleed into
# the area description. Not dropped from a list under an „Област X:"
# header, where "Септември" is the obshtina (област Пазарджик).
_MONTHS = frozenset({
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


def _chunk_names(body: str, *, keep_months: bool = False) -> list[str]:
    """The obshtina-name candidates of a stretch of area text, in order and
    with repeats — the filters of `parse_commune_list`, which dedupes."""
    body = _SELO_BELONGS_RE.sub("община ", body)
    body = _OBLAST_MARKER_RE.sub(", ", body)
    body = _OBSHTINA_MARKER_RE.sub(", ", body)
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
        if not key:
            continue
        if any(t in _PROSE_TOKENS for t in key.split()):
            continue
        if len(key.split()) > 5:
            continue
        if key in _DROP_WORDS or len(key) < 3:
            continue
        if key in _MONTHS and not keep_months:
            continue
        out.append(chunk)
    return out


def parse_commune_list(text: str) -> list[str]:
    """Extract obshtina names from an ЕДИНЕН ДОКУМЕНТ section-6 area body.

    Result: deduped list of canonical obshtina-name candidates that the
    geometry resolver unions against the GISCO LAU `BG_*` polygon set.
    Order preserved for debug-log readability. A text that lists its
    obshtini under „Област X:" headers is read by `parse_area` instead
    (`area_fields`), which keeps a name repeated in two области.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for chunk in _chunk_names(_truncate_at_terroir_section(text)):
        key = _normalise_commune(chunk)
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out


# The 28 области and the three-letter EKATTE code GISCO LAU 2024 prints in
# each obshtina's id (BG_VAR09 is Вълчи дол, област Варна). A name a text
# lists under „Област X:" is looked up among X's obshtini only: two obshtini
# are called Бяла (BG_RSE04, BG_VAR05), and Дунавска равнина's ЕДИНЕН
# ДОКУМЕНТ names both, one under Русе and one under Варна.
OBLAST_CODES: dict[str, str] = {
    "благоевград": "BLG", "бургас": "BGS", "варна": "VAR", "велико търново": "VTR",
    "видин": "VID", "враца": "VRC", "габрово": "GAB", "добрич": "DOB",
    "кърджали": "KRZ", "кюстендил": "KNL", "ловеч": "LOV", "монтана": "MON",
    "пазарджик": "PAZ", "перник": "PER", "плевен": "PVN", "пловдив": "PDV",
    "разград": "RAZ", "русе": "RSE", "силистра": "SLS", "сливен": "SLV",
    "смолян": "SML", "софия": "SFO", "софийска": "SFO", "софия град": "SOF",
    "столична": "SOF", "стара загора": "SZR", "търговище": "TGV", "хасково": "HKV",
    "шумен": "SHU", "ямбол": "JAM",
}

# „Област Монтана:" — the header of the PGI template's per-oblast list. The
# colon is required: "находящо се в област Плевен" is prose, not a header.
_OBLAST_HEADER_RE = re.compile(
    r"\bОбласт\s+([А-ЯЁ][а-яё]+(?:[\s-][А-ЯЁа-яё][а-яё]+)?)\s*:",
)
# "Следните землища на населени места, както са изброени по общини, се
# изключват от очертанията на района:" — what follows lists, per obshtina,
# the villages whose lands are cut out of the area.
_EXCLUSION_RE = re.compile(
    r"[^.:]*?\b(?:се\s+изключват|изключват\s+се)\b[^:]*:", re.IGNORECASE,
)
_HOLDER_RE = re.compile(r"\bОбщина\s+([^:,.;]+?)\s*:")
# "Баните - само землищата на с. Вишнево и с. Гълъбово" — an obshtina of
# which only some villages' lands are in the area.
_PARTIAL_RE = re.compile(r"^(.+?)\s+[-–—]\s+само\s+землищ", re.IGNORECASE)


# One name the regulator writes for two obshtini. "Добрич" in област Добрич
# is the city's obshtina (BG_DOB28) and the rural one around it, of which the
# city is an enclave (GISCO's Добрич-селска, BG_DOB15; община Добричка): the
# ИАЛВ's Черноморски район spec files "гр. Добрич" and Добричка's villages
# (Бенковски, Богдан, Божурово, Карапелит, Стефан Караджа …) under one
# "Община Добрич:" (settlement list: bg.wikipedia, "Община Добричка"), and
# Дунавска равнина names "Добрич" as one of seven of the oblast's eight
# obshtini — drawn as the city alone, an island in an undrawn ring
# (2026-10-24). Keyed (normalised name, oblast code) → normalised GISCO names.
OBSHTINA_GROUPS: dict[tuple[str, str], tuple[str, ...]] = {
    ("добрич", "DOB"): ("добрич", "добрич селска"),
}


def oblast_code(name: str) -> str | None:
    key = re.sub(r"[\s-]+", " ", (name or "").casefold()).strip()
    return OBLAST_CODES.get(key)


def parse_area(text: str) -> dict | None:
    """Read the PGI template — obshtini listed under „Област X:" headers,
    then the villages cut out of them — into {members: [(name, oblast
    code)], partial: [name]}. `partial` lists the obshtini the area holds
    only in part: those named "X - само землищата на с. …" and those the
    exclusion clause cuts villages out of. GISCO carries no unit below the
    obshtina, so such an obshtina is drawn whole and the card says so.
    None when the text has no such header (a PDO's settlement list)."""
    if not text:
        return None
    body = _truncate_at_terroir_section(text)
    heads = [h for h in _OBLAST_HEADER_RE.finditer(body) if oblast_code(h.group(1))]
    if not heads:
        return None
    excl = _EXCLUSION_RE.search(body, heads[0].start())
    members_end = excl.start() if excl else len(body)
    members: list[tuple[str, str]] = []
    partial: list[str] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, code: str, is_partial: bool) -> None:
        key = (_normalise_commune(name), code)
        if not key[0] or key in seen:
            return
        seen.add(key)
        members.append((name, code))
        if is_partial:
            partial.append(name)

    for i, h in enumerate(heads):
        if h.start() >= members_end:
            break
        code = oblast_code(h.group(1)) or ""
        end = min(heads[i + 1].start() if i + 1 < len(heads) else members_end, members_end)
        in_clause = False
        for piece in re.split(r"\s*[,;]\s*", body[h.end():end]):
            piece = piece.strip(" .")
            if not piece:
                continue
            m = _PARTIAL_RE.match(piece)
            if m:
                in_clause = True
                add(_TIER_PREFIX_RE.sub("", m.group(1)).strip(" .,;:"), code, True)
                continue
            if in_clause and _SETTLEMENT_DROP_RE.match(piece):
                # a village of the open "само землищата на" clause
                continue
            in_clause = False
            for name in _chunk_names(piece, keep_months=True):
                add(name, code, False)
    if excl:
        by_key = {_normalise_commune(n): n for n, _ in members}
        for h in _HOLDER_RE.finditer(body[excl.end():]):
            name = by_key.get(_normalise_commune(h.group(1)))
            if name and name not in partial:
                partial.append(name)
    return {"members": members, "partial": partial}


def area_fields(text: str) -> dict:
    """The commune fields a BG record carries for its area text. The PGI
    template gives the oblast-scoped list (`geo_communes_scoped`, [name,
    oblast code] pairs) and the obshtini held only in part
    (`geo_communes_partial`); any other text the deduped legacy reading."""
    parsed = parse_area(text)
    if parsed and parsed["members"]:
        return {
            "geo_communes": [n for n, _ in parsed["members"]],
            "geo_communes_scoped": [[n, c] for n, c in parsed["members"]],
            "geo_communes_partial": list(parsed["partial"]),
        }
    return {"geo_communes": parse_commune_list(text) if text else []}
