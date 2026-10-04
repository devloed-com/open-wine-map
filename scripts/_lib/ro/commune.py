"""Romanian commune-list parser for DOCUMENT UNIC section 6.

Romanian documento-unic publications enumerate the appellation's
delimited area as a flat commune list, sometimes grouped by județ
(county) and sometimes interspersed with municipal-tier qualifiers
(*municipiul*, *orașul*, *comuna*, *satul*) plus sub-village hamlets
(*satul X aparținând comunei Y*).

`parse_commune_list` extracts the deduped commune-name list from one
such section body; the resulting names are passed to
`ROPolygonIndex.commune_union` which unions the matching GISCO LAU
polygons. Same architecture as `scripts/_lib/at/gemeinde.py` and
`scripts/_lib/pt/commune_list.py`.

Romanian-specific quirks the normaliser handles:

  - Diacritics: `Ș` (S-comma-below, U+0218) vs `Ş` (S-cedilla, U+015E)
    and `Ț` (T-comma-below) vs `Ţ` (T-cedilla). The Unicode-compliant
    form is the comma-below; cedilla forms appear in older publications
    because of legacy code-page conversion. We fold both to ASCII for
    the LAU-key, but preserve the original in the parsed output.
  - Municipal-tier prefixes: `municipiul/orașul/comuna NAME` → `NAME`.
  - Satul-hierarchy: `satul X aparținând comunei Y` → keep Y (commune,
    not the hamlet — GISCO LAU polygons are at commune granularity).
  - Article-stripping: `Județul X` (the county header) is a *section*
    marker, not a commune. We track and skip it.
  - Romanian definite articles attached as suffixes (`Bucureștiul →
    București`) — left alone; LAU_NAME uses the bare form.
"""

from __future__ import annotations

import re
import unicodedata

# Romanian county (județ) names — used as section markers in the commune
# list, NOT as commune candidates. ASCII-folded keys.
_JUDET_NAMES = frozenset({
    "alba", "arad", "arges", "bacau", "bihor", "bistrita-nasaud",
    "botosani", "braila", "brasov", "buzau", "calarasi", "caras-severin",
    "cluj", "constanta", "covasna", "dambovita", "dolj", "galati",
    "giurgiu", "gorj", "harghita", "hunedoara", "ialomita", "iasi",
    "ilfov", "maramures", "mehedinti", "mures", "neamt", "olt",
    "prahova", "salaj", "satu-mare", "sibiu", "suceava", "teleorman",
    "timis", "tulcea", "valcea", "vaslui", "vrancea", "bucuresti",
    "satu mare", "caras severin", "bistrita nasaud",
})

# Tier prefixes that precede a commune name — `municipiul`, `orașul`,
# `comuna`, `satul`. Romanian publications carry both the modern
# comma-below diacritic (`ș`, `ț`) and the legacy cedilla (`ş`, `ţ`)
# from older font encodings; the regex matches both.
_TIER_PREFIX_RE = re.compile(
    r"^\s*(?:cu\s+)?"
    r"(?:(?P<word>municipiul|municipiile|municipiu|"
    r"ora[șş]ul|orasul|ora[șş]ele|orasele|ora[șş]|oras|"
    r"comuna|comunele|satul|satele|sat|sate|"
    r"cartier(?:ul|ele)|"
    r"loca[lt]it[ăaâ][țţt](?:ile|ea|i)(?:\s+component[ăae])?)\s+"
    r"|(?P<abbr>com\.|loc\.)\s*"
    r"|(?P<bare>com)\s+)",
    re.IGNORECASE,
)

# The specs also glue the tier word to the name — "ComunaDimitrie Cantemir",
# "sateleTârzii" — after a lost space in the PDF→text step. Repaired
# case-sensitively (a capital right after the word), before the split,
# so _TIER_PREFIX_RE's required whitespace then matches.
_GLUED_PREFIX_RE = re.compile(
    r"\b(Comuna|comuna|Satele|satele|Satul|satul|Municipiul|municipiul|"
    r"Ora[șş]ul|ora[șş]ul)(?=[A-ZĂÂÎŞȘŢȚ])"
)

# Spec spelling → GISCO LAU_NAME spelling, both already normalised.
# Applied on the SPEC side only, in `ROPolygonIndex.commune_union`, so
# the index keys stay untouched — and never as a fuzzy fallback: at ≥ 90
# a fuzzy step binds villages to the wrong neighbouring commune (Galda
# de Sus → Gârda de Sus, Bădeni → Brădeni). Every source key was checked
# absent from the 3,181 GISCO RO keys and every target present.
_SPELLING_ALIASES: dict[str, str] = {
    "isacea": "isaccea",                    # Oraş Isaccea, Tulcea
    "naieni": "naeni",                      # Năeni, Buzău
    "buzoiesti": "buzoesti",                # Buzoeşti, Argeş
    "boldesti scaieni": "boldesti scaeni",  # Oraş Boldeşti-Scăeni, Prahova
    "tautii magherus": "tautii magheraus",  # Oraş Tăuţii-Măgherăuş, Maramureş
    "moldoveneati": "moldovenesti",         # Moldoveneşti, Cluj
    "covasant": "covasint",                 # Covăsinţ, Arad
    "sacuieni": "secuieni",                 # Secuieni, Bacău (3 GISCO rows — needs the county scope)
}

# "satul X aparținând comunei Y" / "sat X din comuna Y" — the salient
# unit is Y (the commune). The phrase appears mid-list; we rewrite it
# in-place so the tokeniser picks up Y, not X.
_SATUL_BELONGS_RE = re.compile(
    r"\b(?:satul|satele|sat)\s+[^,;]+?\b"
    r"(?:apar[țţt]in[âaă]nd|din)\s+(?:comuna|comunei|comunele|comunelor)\s+",
    re.IGNORECASE,
)

# Județ section markers — `Județul X[:]`, `în județul X[,]` — act as
# commune-list section dividers. Both modern (`ț`) and cedilla (`ţ`)
# diacritics appear in the corpus.
# `ului` is the genitive ("judeţului Vaslui"); without it the marker
# stopped at "judeţul" and left "ui Vaslui" behind.
_JUDET_MARKER_RE = re.compile(
    r"\b(?:în\s+)?(?:jude[țţt](?:ului|ul|ele|elor)?|jud\.)\s*",
    re.IGNORECASE,
)

# The județ a marker introduces is HARVESTED, not only used as a divider.
# Romanian commune names repeat heavily across counties — `Izvoarele` is
# 5 communes, `Fântânele` 7, `Ștefan cel Mare` 6 — and unioning every
# homonym drew Colinele Dobrogei (a Black Sea appellation) across the
# whole country. The județ set a record declares is the disambiguator;
# see `ROPolygonIndex.commune_union`. A header's county list runs from
# the marker to the first sentence / list break, at most 120 characters.
_JUDET_WINDOW_RE = re.compile(r"[^.;:\n]{1,120}")
# Capturing, so the split keeps the separators and token offsets survive.
_JUDET_SPLIT_RE = re.compile(r"(,|\bși\b|\bsi\b|\bşi\b)", re.IGNORECASE)

# Splits commune lists. Commas, semicolons, the conjunction "și",
# colons (which often follow "Județul X:"), and newlines all act as
# separators.
_COMMUNE_SPLIT_RE = re.compile(
    r"\s*[,;:\n]\s*|\s+(?:și|şi|si)\s+|\s+[-–]\s+(?=com\b)", re.IGNORECASE,
)

# Tokens whose presence in a chunk strongly indicates it is section
# prose, not a commune name. These never appear in a Romanian commune
# name and they're frequent in the geo-area section's lead-in.
_PROSE_TOKENS = frozenset({
    "aria", "zona", "geografica", "delimitata", "delimitat", "cuprinde",
    "format", "formata", "formată", "alcatuit", "alcătuit", "alcatuita",
    "alcătuită", "include", "urmatoarele", "următoarele", "unitati",
    "unități", "administrativ", "administrative", "teritoriale",
    "teritoriul", "produsele", "produselor", "vitivinicole", "podgoria",
    "podgoriei", "podgorii", "produc", "producția", "regiune", "regiunii",
    "viticol", "viticole", "viticolă", "respectiv", "anume", "precum",
    "totalitatea", "ansamblul",
})

# Drop these as not-a-commune-name tokens (regulatory / connective words
# that survived the tier-prefix strip).
_DROP_WORDS = frozenset({
    "localitatea", "localitatile", "localitati", "componente",
    "centrele", "centrul", "centru", "centre",
    "respectiv", "anume", "precum", "inclusiv", "exclusiv", "incluzand",
    "incluzând", "din", "in", "în", "la", "pe", "cu", "cuprinzand",
    "cuprinzând", "format", "formata", "formată", "alcatuit", "alcătuit",
    "alcatuita", "alcătuită", "delimitata", "delimitată", "delimitat",
    "judetele", "județele", "judetul", "județul",
    # Calendar months — appear in publication dates that bleed into the
    # area description.
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie",
    "decembrie",
})


def _normalise_commune(name: str) -> str:
    """ASCII-fold + lowercase + cedilla→comma fold + strip noise. The
    GISCO LAU index keys on this form. Romanian commune names like
    «Câmpulung la Tisa» normalise to "campulung la tisa"."""
    if not name:
        return ""
    s = name.strip()
    # Fold the typographic dashes (U+2010–U+2015) to "-" first: NFKD +
    # ascii-ignore deletes them outright, so "Bereşti—Meria" collapsed to
    # "berestimeria".
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    # Pre-fold cedilla forms to comma-below before NFKD strips them.
    s = s.replace("Ş", "S").replace("ş", "s").replace("Ţ", "T").replace("ţ", "t")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    # Strip municipal-tier prefix if a stray one survived.
    s = _TIER_PREFIX_RE.sub("", s)
    # Strip trailing parenthesised qualifiers and brackets.
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    # Collapse hyphens to spaces — Câmpia-Turzii / Campia Turzii both
    # appear in cahier text; LAU_NAME uses the hyphen form sometimes
    # and the space form sometimes. We normalise both to single spaces.
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip(_EDGE_STRIP)
    return s


# Trailing "component-locality" descriptor that follows a commune name in
# both the EU DOCUMENT UNIC and the national caiet de sarcini:
#   «municipiul Aiud- localităţi componente: Aiud, Gârbova…»
#   «comuna Daia cu satele Daia, Dăiţa…»
#   «Zimnicea cu localităţile componente»
# We keep the commune name (the head) and drop the descriptor tail. The
# "sate/localit" cut only fires after a dash or "cu" so legitimate names
# such as «Satu Nou» / «Satu Mare» survive.
_DESCRIPTOR_TAIL_RE = re.compile(
    r"\s*(?:"
    r"[-–]\s*(?:sate|satul|satele|localit\w*)"
    r"|[-–]\s*sat\s+(?=\w)"
    r"|\s(?:satele|satul)\b"
    r"|cu\s+(?:satele|satul|sate|localit\w*|urm[ăa]toarele)"
    r"|\slocalit[ăaâ][țţt]i(?:le)?\s+componente"
    r")\b.*$",
    re.IGNORECASE,
)
# Only after a stripped town prefix ("oraşul Urlaţi cu Arioneştii Noi"):
# an unconditional "cu <Name>" cut would turn the commune Malu cu Flori
# into Malu, which is a different GISCO key.
_TOWN_CU_TAIL_RE = re.compile(r"\s+cu\s+(?=[A-ZĂÂÎŞȘŢȚ]).*$")
# Only after a stripped commune prefix ("Com. Lungeşti - Lungeşti"): an
# unconditional dash cut would truncate hyphenated village names. And
# only when no descriptor tail was cut: "- satul …" / "cu satele …"
# already marks where the village list starts, so what precedes it is the
# whole name, dash included — "Com. Albeşti - Paleologu - satul …" and
# "Comuna Bereşti – Meria cu satele …" name the communes Albeşti-Paleologu
# and Bereşti-Meria, while "albesti" and "beresti" are other GISCO keys.
_COMMUNE_DASH_TAIL_RE = re.compile(r"\s+[-–]\s+.*$")
# "Com. Lungeşti - Lungeşti - satele …": the part after the dash repeats the
# head, so it is the seat village, not the second half of a dash-joined name.
_REPEATED_HEAD_RE = re.compile(r"^(?P<head>.+?)\s+[-–]\s+(?P=head)(?:\s|$)", re.IGNORECASE)
_PAGE_FOOTER_RE = re.compile(r"\b(?:Page\s+\d+\s+of\s+\d+|Pagina\s+\d+\s+din\s+\d+)\b", re.IGNORECASE)


# Edge characters trimmed off each split chunk — punctuation plus the
# bullet glyphs ("- ", "•", "·") that lead area-list lines in both the
# EU DOCUMENT UNIC and the national caiet de sarcini.
_EDGE_STRIP = " .,;:\t-–•·"


def _truncate_at_terroir_section(text: str) -> str:
    """Section 6 text sometimes runs into section 7 (grape varieties)
    without a clean page break — cut at the well-known Romanian
    section-7 lead-in to avoid the grape names leaking into the
    commune list."""
    marker_re = re.compile(
        r"\b(soiu(?:l|rile)?\s+(?:principal|de\s+struguri|de\s+vinifica)|"
        r"struguri\s+de\s+vinifica)",
        re.IGNORECASE,
    )
    m = marker_re.search(text)
    return text[: m.start()] if m else text


def _county_prefix(token: str) -> tuple[str | None, int]:
    """The județ key `token` starts with and the number of words it spans,
    0 when the token does not start with a county. A prefix, not the whole
    token: a header may carry a descriptor tail ("Judeţul Vaslui – zona
    Huşi") or run on into prose ("judeţului Olt pe raza localităţilor")."""
    words = re.findall(r"[a-z0-9]+", _normalise_commune(token))
    for n in (2, 1):
        if len(words) >= n and " ".join(words[:n]) in _JUDET_NAMES:
            return " ".join(words[:n]), n
    return None, 0


_WORDS_RE = re.compile(r"\S+")


def _judet_headers(text: str) -> list[tuple[int, list[str]]]:
    """Every county header in `text`: (marker offset, [județ keys]).

    The county list after a marker is read token by token (comma / "şi")
    and ends at the first token that does not start with a county name.
    Two failure modes this closes:

      - a tier-prefixed token is a commune even when it carries a county's
        name: "Judeţul Dolj, comuna Călăraşi" declares Dolj only, not also
        the county Călăraşi;
      - a later marker is a header of its own unless it continues the list
        ("judeţul Constanţa şi judeţul Tulcea"): in "Judeţul Galaţi,
        Tecuci, Iveşti, Judeţul Vaslui, …" the Vaslui names are not Galaţi's.
    """
    out: list[tuple[int, list[str]]] = []
    consumed = 0
    for mk in _JUDET_MARKER_RE.finditer(text):
        if mk.start() < consumed:
            continue
        window = _JUDET_WINDOW_RE.match(text, mk.end())
        if window is None:
            continue
        found: list[str] = []
        pos = end = mk.end()
        for i, part in enumerate(_JUDET_SPLIT_RE.split(window.group(0))):
            tok_start = pos + len(part) - len(part.lstrip())
            pos += len(part)
            tok = part.strip()
            if i % 2 or not tok:
                continue
            if cont := _JUDET_MARKER_RE.match(tok):
                tok_start += cont.end()
                tok = tok[cont.end():]
            if _TIER_PREFIX_RE.match(tok):
                break
            key, n_words = _county_prefix(tok)
            if key is None:
                break
            if key not in found:
                found.append(key)
            county_words = list(_WORDS_RE.finditer(tok))[:n_words]
            if len(county_words) == n_words and len(_WORDS_RE.findall(tok)) > n_words:
                # Prose runs on after the county ("judeţul Iaşi pe raza comunei
                # Bohotin judeţul Vaslui, …"): the header ends with the county
                # words, so a later marker in the same token opens its own
                # section instead of being consumed with this one.
                end = tok_start + county_words[-1].end()
                break
            end = pos
        if found:
            out.append((mk.start(), found))
            consumed = end
    return out


def parse_commune_list_scoped(text: str) -> list[tuple[str, list[str]]]:
    """Extract commune-name candidates from an area description, each
    paired with the județe the surrounding section header declares.

    Romanian specs group the list under county headers — "Judeţul Iaşi:",
    "Localități din judeţul Buzău:", "1.Blaj – jud. Alba:" — and the same
    commune name recurs in several counties (Griviţa is a commune in both
    Galaţi and Vaslui; Costeşti in Iaşi, Buzău and Vaslui). A record-wide
    county mask cannot tell those apart; the header the name sits under
    can. Names before any header carry an empty list and fall back to the
    record-wide mask in the resolver.

    Result: (original-form chunk, [județ keys]) in document order, deduped
    on (normalised key, județ set).
    """
    if not text:
        return []
    body = unicodedata.normalize("NFKC", text)
    body = _truncate_at_terroir_section(body)
    body = _PAGE_FOOTER_RE.sub(" ", body)
    # Drop parenthetical "(satele X, Y şi Z)" groups whole — they enumerate
    # sub-village hamlets (not GISCO-commune-level) and, because they carry
    # internal commas, would otherwise fragment across the comma split and
    # leave the head commune name glued to "(satele …".
    body = re.sub(r"\([^)]*\)", " ", body)
    # Rewrite "satul X aparținând comunei Y" → "comuna Y" so the
    # tier-prefix strip below picks up Y, not the (uncrappable) X.
    body = _SATUL_BELONGS_RE.sub("comuna ", body)
    body = _GLUED_PREFIX_RE.sub(r"\1 ", body)

    # Segment the body at each county header; every segment inherits the
    # header's județe. The header itself stays in the segment: the județ
    # word is demoted to a separator and the county name is then rejected
    # as a chunk by `_JUDET_NAMES`, as before.
    segments: list[tuple[str, list[str]]] = []
    pos = 0
    current: list[str] = []
    for start, found in _judet_headers(body):
        segments.append((body[pos:start], current))
        current = found
        pos = start
    segments.append((body[pos:], current))

    seen: set[tuple[str, tuple[str, ...]]] = set()
    out: list[tuple[str, list[str]]] = []
    for seg, judete in segments:
        seg = _JUDET_MARKER_RE.sub(", ", seg)
        for raw in _COMMUNE_SPLIT_RE.split(seg):
            chunk = raw.strip(_EDGE_STRIP)
            if not chunk:
                continue
            # Strip a leading municipal-tier prefix (municipiul / orașul /
            # comuna / com. / satul …); remember which, because two tail
            # cuts are only safe after a prefix of a given tier.
            pm = _TIER_PREFIX_RE.match(chunk)
            prefix = ""
            if pm:
                prefix = (pm.group("word") or pm.group("abbr") or pm.group("bare") or "").lower()
                chunk = chunk[pm.end():].strip(_EDGE_STRIP)
            # Drop a trailing "- localităţi componente …" / "cu satele …"
            # descriptor so the bare commune name matches the GISCO key —
            # never at the chunk start, which would empty "localităţile
            # componente Mediaş" and "cu localitatea Jamu Mare".
            tm = _DESCRIPTOR_TAIL_RE.search(chunk)
            described = bool(tm and tm.start() > 0)
            if described:
                chunk = chunk[:tm.start()].strip(_EDGE_STRIP)
            if prefix.startswith(("ora", "municipi")):
                chunk = _TOWN_CU_TAIL_RE.sub("", chunk).strip(_EDGE_STRIP)
            elif prefix.startswith("com") and (
                not described or _REPEATED_HEAD_RE.match(chunk)
            ):
                chunk = _COMMUNE_DASH_TAIL_RE.sub("", chunk).strip(_EDGE_STRIP)
            if not chunk:
                continue
            key = _normalise_commune(chunk)
            if not key:
                continue
            dedupe_key = (key, tuple(judete))
            if dedupe_key in seen:
                continue
            # Reject if any prose-only token (`cuprinde`, `aria`, …) sits
            # in the chunk — that's section lead-in, not a commune name.
            if any(t in _PROSE_TOKENS for t in key.split()):
                continue
            # Romanian commune names rarely exceed 4 tokens; longer chunks
            # are almost always prose.
            if len(key.split()) > 5:
                continue
            if key in _DROP_WORDS or len(key) < 2:
                continue
            # A county-named chunk is a header ("Judeţul Iaşi" → "Iaşi") —
            # unless it carried a tier word, in which case it is the
            # county seat (Municipiul Iaşi). Likewise a digit-first chunk
            # is a list number, unless it is the commune "23 August".
            if not prefix and (key in _JUDET_NAMES or not key[0].isalpha()):
                continue
            seen.add(dedupe_key)
            # Keep the original-form chunk (pre-normalisation) for the
            # display / audit log; the resolver will renormalise.
            out.append((chunk, list(judete)))
    return out


def parse_commune_list(text: str) -> list[str]:
    """Extract commune-name candidates from an area description (the
    unscoped view of `parse_commune_list_scoped`, deduped on the name).

    Result: deduped list of canonical name candidates that the geometry
    resolver unions against the GISCO LAU `RO_*` polygon set. Order
    preserved for debug-log readability.
    """
    seen: set[str] = set()
    out: list[str] = []
    for chunk, _judete in parse_commune_list_scoped(text):
        key = _normalise_commune(chunk)
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out


def parse_judet_list(text: str) -> list[str]:
    """Harvest the județe an area description declares, normalised to the
    `_JUDET_NAMES` key form.

    Only used to disambiguate a commune name that matches several GISCO
    polygons, and the resolver skips a name it cannot disambiguate, so
    this is fail-safe in both directions: too many județe leaves an
    ambiguity unresolved, too few drops a commune. Neither can add area
    the spec did not delimit.
    """
    if not text:
        return []
    out: list[str] = []
    for _start, found in _judet_headers(unicodedata.normalize("NFKC", text)):
        for key in found:
            if key not in out:
                out.append(key)
    return out


def judet_source_text(record: dict) -> str:
    """The text `parse_judet_list` should read for a record: the area body
    plus the section TITLES. When the PDF→HTML conversion mangles a
    DOCUMENT UNIC's numbering, the county sub-headers of section 6
    ("Judeţul Iaşi", "Judeţul Galaţi", …) get parsed as top-level sections
    — the area body comes out empty, the commune list falls back to the
    whole-document density scan, and the counties survive only as titles.
    Dealurile Moldovei declares six that way and had no mask at all before
    the titles were read."""
    roles = record.get("section_roles") or {}
    titles = record.get("section_titles") or {}
    return " . ".join(
        t for t in (
            roles.get("geo_area") or "",
            record.get("geo_area_brief") or "",
            *[str(v) for v in titles.values()],
        ) if t
    )
