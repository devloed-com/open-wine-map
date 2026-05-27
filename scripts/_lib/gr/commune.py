"""Greek δήμος / κοινότητα parser for the ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ section-6 geo-area
body.

Greece's three-level administrative hierarchy after the Kallikratis
reform (Law 3852/2010):

  Επικράτεια (state) → Περιφέρεια (region, 13) → Περιφερειακή ενότητα
                       (regional unit / former νομός, 74)
                     → Δήμος (municipality / dimos, 332)
                     → Δημοτική Ενότητα / Δημοτική Κοινότητα (community)
                     → Τοπική Κοινότητα (local community / village)

GISCO LAU 2024 stores Greek units at the **community** level
(`Δημοτική Κοινότητα NAME`) under CNTR_CODE='EL'. The normaliser
preserves Greek (no NFKD-ASCII fold) and strips the tier-prefix so
both sides of the index key on the bare community / δήμος name.

Greek publication idioms the parser handles:

  - Tier prefixes: `Δήμος NAME` / `Κοινότητα NAME` / `Δημοτική
    Κοινότητα NAME` / `Τοπική Κοινότητα NAME` → `NAME`.
  - Periphereia / nomos section markers: `Περιφερειακή Ενότητα X` /
    `Π.Ε. X` / `Νομός X` / `στον νομό X` → demoted to a list
    separator.
  - Hierarchy: `Τοπική Κοινότητα X του Δήμου Y` → keep Y (the
    δήμος, since GISCO community polygons aggregate up to the δήμος).
  - Pre-Kallikratis spellings: `Δήμος + ων-suffix` (genitive). The
    normaliser keeps the original form; the resolver does
    exact-match-first, so a `_normalise_commune` collision against
    the LAU_NAME key is what it needs.
"""

from __future__ import annotations

import re

# Greek peripheries (περιφέρειες, 13). Used as commune-list section
# markers, NOT as commune candidates. Stored casefolded (Greek
# casefold preserves the Greek block).
_PERIPHEREIA_NAMES = frozenset({
    "ανατολικη μακεδονια και θρακη", "ανατολική μακεδονία και θράκη",
    "αττικη", "αττική",
    "βορειο αιγαιο", "βόρειο αιγαίο",
    "δυτικη ελλαδα", "δυτική ελλάδα",
    "δυτικη μακεδονια", "δυτική μακεδονία",
    "ηπειρος", "ήπειρος",
    "θεσσαλια", "θεσσαλία",
    "ιονια νησια", "ιόνια νησιά",
    "κεντρικη μακεδονια", "κεντρική μακεδονία",
    "κρητη", "κρήτη",
    "νοτιο αιγαιο", "νότιο αιγαίο",
    "πελοποννησος", "πελοπόννησος",
    "στερεα ελλαδα", "στερεά ελλάδα",
})

# Hierarchy rewrite: `Τοπική Κοινότητα X του δήμου Y` /
# `Τοπική Κοινότητα X (Δήμος Y)` — salient unit is Y (the δήμος).
# Rewrite to `Δήμος Y` so the tier-prefix strip below picks up Y.
_TOPIKI_BELONGS_RE = re.compile(
    r"\b(?:τοπικ(?:ή|η)\s+κοινότητα|τοπικη\s+κοινοτητα|"
    r"δημοτικ(?:ή|η)\s+κοινότητα|δημοτικη\s+κοινοτητα|"
    r"δημοτικ(?:ή|η)\s+ενότητα|δημοτικη\s+ενοτητα)"
    r"\s+[^,;()]+?\s+"
    r"(?:του|της|στον|στην)\s+"
    r"(?:δήμου|δημου|δήμο|δημο)\s+",
    re.IGNORECASE,
)

# Periphereia + regional-unit + nomos markers — consumed *with* the
# trailing region name (1–4 Greek words) so the region name doesn't
# bleed into the candidate list.
_REGION_MARKER_RE = re.compile(
    r"\b(?:στ(?:ην|ον|η)\s+|"
    r"της\s+|του\s+|"
    r"της\s+περιφέρειας\s+|περιφέρει(?:α|ας|ες)\s+|"
    r"περιφερειακή\s+ενότητα\s+|περιφερειακης\s+ενοτητας\s+|"
    r"π\.\s*ε\.\s+|"
    r"νομός\s+|νομού\s+|νομο\s+|"
    r"σ?την?\s+νομαρχία\s+|στον\s+νομό\s+)"
    r"[Α-ΩΆΈΉΊΌΎΏΪΫα-ωάέήίόύώϊϋΐΰ-]+(?:\s+[Α-ΩΆΈΉΊΌΎΏΪΫα-ωάέήίόύώϊϋΐΰ-]+){0,3}",
    re.IGNORECASE | re.UNICODE,
)

# Tier prefixes preceding a δήμος / κοινότητα name.
_TIER_PREFIX_RE = re.compile(
    r"^\s*("
    r"δήμοι|δήμος|δήμο|δήμου|δήμους|"
    r"δημοι|δημος|δημο|δημου|δημους|"
    r"κοινότητα|κοινότητες|κοινότητας|κοινοτητα|κοινοτητες|κοινοτητας|"
    r"δημοτικ(?:ή|η)\s+κοινότητα|δημοτικ(?:ή|η)\s+κοινοτητα|"
    r"δημοτικ(?:ή|η)\s+ενότητα|δημοτικ(?:ή|η)\s+ενοτητα|"
    r"τοπικ(?:ή|η)\s+κοινότητα|τοπικ(?:ή|η)\s+κοινοτητα"
    r")\s+",
    re.IGNORECASE,
)

# Same prefix anywhere in the body — promoted to a list-separator so a
# `στους δήμους X, Y και Z` lead-in doesn't trap the first δήμος name
# inside a long prose chunk.
_DIMOS_MARKER_RE = re.compile(
    r"\b(?:στ(?:ους|ον|ις|ην)\s+|τους\s+|του\s+|στ(?:η|ην)\s+)?"
    r"(?:δήμο(?:υ|υς|ν|ι)?|δημο(?:υ|υς|ν|ι)?|"
    r"κοινότητα(?:ς)?|κοινοτητα(?:ς)?|"
    r"δημοτικ(?:ή|η)\s+κοινότητα(?:ς)?|δημοτικ(?:ή|η)\s+κοινοτητα(?:ς)?|"
    r"τοπικ(?:ή|η)\s+κοινότητα(?:ς)?|τοπικ(?:ή|η)\s+κοινοτητα(?:ς)?)\s+",
    re.IGNORECASE,
)

# Splitter — comma, semicolon, em-dash, en-dash, "και", newline, colon.
_COMMUNE_SPLIT_RE = re.compile(r"\s*[,;:\n—–]\s*|\s+και\s+", re.IGNORECASE)

# Tokens whose presence in a chunk signals it is prose, not a name.
_PROSE_TOKENS = frozenset({
    "περιοχή", "περιοχης", "περιοχης", "γεωγραφική", "γεωγραφικη",
    "γεωγραφικής", "γεωγραφικης", "οριοθετημένη", "οριοθετημενη",
    "οριοθετημένης", "οριοθετημενης", "ζώνη", "ζωνη", "ζώνης", "ζωνης",
    "περιλαμβάνει", "περιλαμβανει", "περιλαμβάνεται", "περιλαμβανεται",
    "καλύπτει", "καλυπτει", "παρακάτω", "παρακατω", "ακόλουθες",
    "ακολουθες", "ακολούθων", "ακολουθων", "εξής", "εξης",
    "αμπελώνες", "αμπελωνες", "αμπελώνας", "αμπελωνας",
    "αμπέλι", "αμπελι", "αμπελιού", "αμπελιου",
    "παραγωγή", "παραγωγη", "παραγωγής", "παραγωγης",
    "διοικητική", "διοικητικη", "διοικητικής", "διοικητικης",
    "έκταση", "εκταση", "έκτασης", "εκτασης",
    "οινικ(ός|ού|ής)", "οινικη",
})

# Drop these as not-a-name tokens (connectives / wine-law verbs that
# may survive the tier-prefix strip).
_DROP_WORDS = frozenset({
    "και", "ή", "η", "ότι", "οτι", "όπως", "οπως", "καθώς",
    "καθως", "συμπεριλαμβανομένων", "συμπεριλαμβανομενων",
    "συγκεκριμένα", "συγκεκριμενα",
    "στ", "στο", "στη", "στην", "στις", "στους", "στον", "στα",
    "του", "της", "των", "ο", "η", "οι", "τα", "τις", "τους",
    "από", "απο", "για", "με", "σε", "προς", "παρά", "παρα",
    # Greek months (genitive forms appear in publication-date prose
    # that bleeds into the area description).
    "ιανουαρίου", "ιανουαριου", "φεβρουαρίου", "φεβρουαριου",
    "μαρτίου", "μαρτιου", "απριλίου", "απριλιου", "μαΐου", "μαιου",
    "ιουνίου", "ιουνιου", "ιουλίου", "ιουλιου", "αυγούστου",
    "αυγουστου", "σεπτεμβρίου", "σεπτεμβριου", "οκτωβρίου",
    "οκτωβριου", "νοεμβρίου", "νοεμβριου", "δεκεμβρίου", "δεκεμβριου",
})


# GISCO LAU 2024 stores Greek units with the `Δημοτική Κοινότητα ` /
# `Τοπική Κοινότητα ` tier prefix baked into LAU_NAME. The normaliser
# must strip those so the bare community / δήμος name keys both sides
# of the index.
_LAU_TIER_PREFIX_RE = re.compile(
    r"^\s*(δημοτική\s+κοινότητα|δημοτικη\s+κοινοτητα|"
    r"τοπική\s+κοινότητα|τοπικη\s+κοινοτητα|"
    r"δημοτική\s+ενότητα|δημοτικη\s+ενοτητα|"
    r"δήμος|δημος|κοινότητα|κοινοτητα)\s+",
    re.IGNORECASE,
)


def _normalise_commune(name: str) -> str:
    """Greek-preserving normaliser. casefold + tier-prefix strip +
    collapse hyphens/whitespace. The GISCO LAU index keys on this
    form. Greek `casefold()` handles monotonic + polytonic
    diacritics consistently; we additionally strip the standalone
    tonos marks so `«Σαντορίνη»` and `«Σαντορινη»` collide.

    Greek community names like «Δημοτική Κοινότητα Σαντορίνης»
    normalise to "σαντορίνης".
    """
    if not name:
        return ""
    s = name.strip()
    s = s.casefold()
    # Strip both the publication-text tier-prefix and the GISCO
    # `δημοτική κοινότητα` baked-in prefix.
    s = _LAU_TIER_PREFIX_RE.sub("", s)
    s = _TIER_PREFIX_RE.sub("", s)
    # Strip trailing parenthesised qualifiers / brackets.
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return s


def _truncate_at_terroir_section(text: str) -> str:
    """Section 6 sometimes bleeds into section 7 without a clean break.
    Cut at the well-known Greek section-7 lead-in to avoid grape
    names leaking into the commune list."""
    marker_re = re.compile(
        r"\b(κύρι(?:α|ες)\s+(?:οινοποιήσιμ|ποικιλί)|"
        r"ποικιλί(?:α|ες)\s+σταφυλιού|"
        r"οινοποιήσιμ(?:η|ες)\s+ποικιλί)",
        re.IGNORECASE,
    )
    m = marker_re.search(text)
    return text[: m.start()] if m else text


def parse_commune_list(text: str) -> list[str]:
    """Extract δήμος / κοινότητα names from an ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ section-6
    area body.

    Result: deduped list of canonical name candidates that the
    geometry resolver unions against the GISCO LAU `EL_*` polygon
    set. Order preserved for debug-log readability.
    """
    if not text:
        return []
    body = _truncate_at_terroir_section(text)
    body = _TOPIKI_BELONGS_RE.sub("δήμος ", body)
    body = _REGION_MARKER_RE.sub(", ", body)
    body = _DIMOS_MARKER_RE.sub(", ", body)

    seen: set[str] = set()
    out: list[str] = []
    for raw in _COMMUNE_SPLIT_RE.split(body):
        chunk = raw.strip(" .,;:")
        if not chunk:
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
        if key in _PERIPHEREIA_NAMES:
            continue
        seen.add(key)
        out.append(chunk)
    return out
