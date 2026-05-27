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
    r"^\s*(municipiul|municipiile|municipiu|"
    r"ora[șş]ul|orasul|ora[șş]ele|orasele|ora[șş]|oras|"
    r"comuna|comunele|satul|satele)\s+",
    re.IGNORECASE,
)

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
_JUDET_MARKER_RE = re.compile(
    r"\b(?:în\s+)?jude[țţt](?:ul|ele|elor)?\s+",
    re.IGNORECASE,
)

# Splits commune lists. Commas, semicolons, the conjunction "și",
# colons (which often follow "Județul X:"), and newlines all act as
# separators.
_COMMUNE_SPLIT_RE = re.compile(r"\s*[,;:\n]\s*|\s+(?:și|si)\s+", re.IGNORECASE)

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
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return s


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


def parse_commune_list(text: str) -> list[str]:
    """Extract commune names from a DOCUMENT UNIC section-6 area body.

    The result is a deduped list of canonical commune-name candidates
    that ROPolygonIndex.commune_union resolves against the GISCO LAU
    name index. Order-of-appearance preserved (helps debugging)."""
    if not text:
        return []
    body = _truncate_at_terroir_section(text)
    # Rewrite "satul X aparținând comunei Y" → "comuna Y" so the
    # tier-prefix strip below picks up Y, not the (uncrappable) X.
    body = _SATUL_BELONGS_RE.sub("comuna ", body)
    # "Județul X[:]" / "în județul X" → comma. The județ word + its
    # following județ-name end up as 1-token chunks that
    # `_JUDET_NAMES` then rejects.
    body = _JUDET_MARKER_RE.sub(", ", body)

    seen: set[str] = set()
    out: list[str] = []
    for raw in _COMMUNE_SPLIT_RE.split(body):
        chunk = raw.strip(" .,;:")
        if not chunk:
            continue
        # Strip a leading municipal-tier prefix (municipiul / orașul /
        # comuna / satul …).
        chunk = _TIER_PREFIX_RE.sub("", chunk).strip(" .,;:")
        if not chunk:
            continue
        key = _normalise_commune(chunk)
        if not key or key in seen:
            continue
        # Reject if any prose-only token (`cuprinde`, `aria`, …) sits
        # in the chunk — that's section lead-in, not a commune name.
        if any(t in _PROSE_TOKENS for t in key.split()):
            continue
        # Romanian commune names rarely exceed 4 tokens; longer chunks
        # are almost always prose.
        if len(key.split()) > 5:
            continue
        if (key in _JUDET_NAMES or key in _DROP_WORDS
                or len(key) < 3 or not key[0].isalpha()):
            continue
        seen.add(key)
        # Keep the original-form chunk (pre-normalisation) for the
        # display / audit log; the resolver will renormalise.
        out.append(chunk)
    return out
