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
    Κοινότητα NAME` / `Τοπική Κοινότητα NAME` / the pre-Kallikratis
    `Δημοτικό Διαμέρισμα NAME` and `Δ.Δ. NAME` / the self-governing
    `Ψευδοδημοτική Κοινότητα NAME` → `NAME`, through a leading
    article and a qualifying adjective (`το όμορο δημοτικό
    διαμέρισμα NAME`).
  - Periphereia / nomos section markers: `Περιφερειακή Ενότητα X` /
    `Π.Ε. X` / `Νομός X` / `Ν. X` / `στον νομό X` → demoted to a list
    separator. A BARE `του` / `της` / `στην` is not one of these: it
    introduces any genitive place name, the appellation's own area
    included.
  - Self-governing units with no tier word: `(τη) διοικητική περιοχή
    του X` → X. This is the only way Άγιο Όρος is named.
  - Hierarchy: `<sub-unit tier> X του Δήμου Y` → keep **X**. The spec
    is including that one sub-unit; Y is context. GISCO LAU stores
    Greece AT community level (6,142 EL rows against 332 δήμοι), so X
    is itself resolvable — an earlier rule kept Y instead, on the
    premise that community polygons aggregate up to the δήμος, which
    is the opposite of how the layer is built.
  - Pre-Kallikratis spellings: `Δήμος + ων-suffix` (genitive). The
    normaliser keeps the original form; the resolver does
    exact-match-first, so a `_normalise_commune` collision against
    the LAU_NAME key is what it needs — and where the two sides
    decline the name differently, `_COMMUNE_ALIAS` folds them.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

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

# Periphereia + regional-unit + nomos markers — consumed *with* the
# trailing region name (1-4 Greek words) so the region name doesn't
# bleed into the candidate list.
#
# The leading article is optional and is only ever eaten as part of a
# REAL marker. A bare `του` / `της` / `στην` is not a region marker: it
# introduces any genitive place name, including the appellation's own
# delimited area — Άγιο Όρος reads "τη διοικητική περιοχή **του Αγίου
# Όρους**", and the bare branch swallowed Mount Athos itself. Listing
# the bare articles first also shadowed every specific branch below
# them (alternation is first-match-wins), so `περιφερειακή ενότητα` /
# `νομός` were dead code — Τύρναβος kept "περιφερειακής Ενότητας
# Λάρισας" as a commune candidate.
_REGION_MARKER_RE = re.compile(
    r"\b(?:(?:σ)?τ(?:ην|ον|ης|ου|η|ο)\s+)?"
    r"(?:"
    r"περιφερειακ(?:ής|ης|ή|η)\s+εν[οό]τητα(?:ς)?\s+|"
    r"περιφέρει(?:ας|α|ες)\s+|περιφερει(?:ας|α|ες)\s+|"
    r"π\.\s*ε\.\s*|"
    r"νομαρχ[ιί]α(?:ς)?\s+|"
    r"νομ(?:ός|ού|ος|ου|ό|ο)\s+|"
    r"ν\.\s*"
    r")"
    r"[Α-ΩΆΈΉΊΌΎΏΪΫα-ωάέήίόύώϊϋΐΰ-]+(?:\s+[Α-ΩΆΈΉΊΌΎΏΪΫα-ωάέήίόύώϊϋΐΰ-]+){0,3}",
    re.IGNORECASE | re.UNICODE,
)

# `(τη) διοικητική περιοχή του X` — "the administrative area of X" is
# how a spec names a self-governing unit that carries no δήμος /
# κοινότητα tier word (Άγιο Όρος). Demoted to a list separator so X
# survives as a candidate instead of being buried in a prose chunk
# (`διοικητική` is a _PROSE_TOKENS word, which killed the whole chunk).
_ADMIN_AREA_MARKER_RE = re.compile(
    r"\b(?:(?:σ)?τ(?:ην|ον|ης|ου|η|ο)\s+)?"
    r"διοικητικ(?:ής|ης|ή|η)\s+περιοχ(?:ής|ης|ή|η)\s+"
    r"(?:του|της|των)\s+",
    re.IGNORECASE | re.UNICODE,
)

# "(στα διοικητικά) όρια των οικισμών Αγοράς και …", "όρια των Δ.Δ. Πύλης,
# …": the limits phrase introduces a list, so it is a separator — as a prose
# word it swallowed the first name with it (ΠΓΕ Αγορά lost Αγοράς).
_LIMITS_MARKER_RE = re.compile(
    # Only before a list noun: "όρια της Περιφερειακής Ενότητας …" (Εύβοια)
    # names a unit the region marker handles, and stays prose.
    r"\b(?:(?:σ)?τ(?:α|ων)\s+)?(?:διοικητικ(?:ά|α)\s+)?(?:όρια|ορια)\s+(?:των|του|της)\s+"
    r"(?:οικισμ(?:ών|ων)\s+|δ\.\s*δ\b\.?\s*|κοινοτ(?:ήτων|ητων)\s+|"
    r"δημοτικ(?:ών|ων)\s+διαμερισμ(?:άτων|ατων)\s+)",
    re.IGNORECASE | re.UNICODE,
)

# `<sub-unit tier> X του Δήμου Y` — the δήμος is CONTEXT, not part of
# the delimited area: Άγιο Όρος includes "το όμορο δημοτικό διαμέρισμα
# Ουρανούπολης **του Δήμου Σταγίρων - Ακάνθου**", and Στάγιρα is a
# separate GISCO community that is not in the appellation. GISCO LAU
# stores Greece at community level, so the named sub-unit X is itself
# resolvable and is the precise answer; drop the trailing δήμος.
_CAP = "[Α-ΩΆΈΉΊΌΎΏΪΫ]"
_LOW = "[α-ωάέήίόύώϊϋΐΰς]"
# A proper-noun token: capital initial, then either an all-caps or a
# lower-case tail ("ΣΤΑΓΙΡΩΝ" / "Σταγίρων"), optionally hyphen-joined.
_NAME_TOKEN = f"{_CAP}(?:{_CAP}+|{_LOW}*)(?:-{_CAP}(?:{_CAP}+|{_LOW}*))*"
_SUBUNIT_OF_DIMOS_RE = re.compile(
    # Tier words and `του Δήμου` are case-insensitive; the two NAME slots
    # are not. Compiling the whole pattern IGNORECASE turned the capital
    # anchor into "any letter", so the δήμος sweep ate the next list item
    # ("… του Δήμου Τυρνάβου και Δελερίων" lost Δελερίων) or a nomos
    # qualifier ("… του Δήμου Σητείας του Νομού Λασιθίου").
    r"((?i:(?:δημοτικ|τοπικ)(?:ό|ο|ού|ου)\s+διαμ[εέ]ρ[ιί]σμα(?:τος)?|"
    r"(?:δημοτικ|τοπικ)(?:ή|η|ής|ης)\s+(?:κοινότητα|κοινοτητα|ενότητα|ενοτητα)(?:ς)?)"
    # The sub-unit X: one to three proper-noun tokens ("Αγίου Παύλου",
    # "Νίκου Καζαντζάκη"). A single-token slot let a two-word X stop the
    # rewrite, and the δήμος then became a candidate — the Στάγιρα case.
    rf"\s+{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,2}})"
    r"\s+(?i:(?:του|της|στον|στην)\s+(?:δήμου|δημου|δήμο|δημο))\s+"
    # The δήμος name: up to three proper-noun tokens joined by spaces or a
    # dash ("Βόρειας Κυνουρίας", "Σταγίρων - Ακάνθου").
    rf"{_NAME_TOKEN}(?:(?:\s*[-–—]\s*|\s+){_NAME_TOKEN}){{0,2}}",
    re.UNICODE,
)

# Tier prefixes preceding a δήμος / κοινότητα name, with an optional
# leading article and an optional qualifying adjective (`το όμορο
# δημοτικό διαμέρισμα Ουρανούπολης`). Longest alternative first.
# `δημοτικό/τοπικό διαμέρισμα` is the pre-Kallikratis tier word and
# `Ψευδοδημοτική Κοινότητα` is the tier GISCO gives the 68 Greek
# pseudo-municipal communities, Mount Athos among them.
_TIER_PREFIX_RE = re.compile(
    r"^\s*(?:(?:στα|στις|στους|στον|στην|στη|στο|"
    r"το|τα|τη|την|τον|του|της|των|οι|ο|η)\s+)?"
    r"(?:(?:όμορ|ομορ|γειτονικ)[α-ωά-ώ]*\s+)?"
    r"(?:(?:"
    r"ψευδοδημοτικ(?:ή|η)\s+κοινότητα|ψευδοδημοτικ(?:ή|η)\s+κοινοτητα|"
    r"δημοτικ(?:ή|η)\s+κοινότητα|δημοτικ(?:ή|η)\s+κοινοτητα|"
    r"δημοτικ(?:ή|η)\s+ενότητα|δημοτικ(?:ή|η)\s+ενοτητα|"
    r"τοπικ(?:ή|η)\s+κοινότητα|τοπικ(?:ή|η)\s+κοινοτητα|"
    r"(?:δημοτικ|τοπικ)(?:ές|ες|ών|ων)\s+(?:κοινότητες|κοινοτητες|κοινοτήτων|κοινοτητων|"
    r"ενότητες|ενοτητες|ενοτήτων|ενοτητων)|"
    r"δημοτικ(?:ό|ο|ού|ου)\s+διαμ[εέ]ρ[ιί]σμα(?:τος)?|"
    r"τοπικ(?:ό|ο|ού|ου)\s+διαμ[εέ]ρ[ιί]σμα(?:τος)?|"
    r"δήμοι|δήμους|δήμων|δήμου|δήμος|δήμο|"
    r"δημοι|δημους|δημων|δημου|δημος|δημο|"
    r"κοινότητες|κοινότητας|κοινότητα|κοινοτητες|κοινοτητας|κοινοτητα"
    r")\s+|"
    r"δ\.\s*δ\b\.?\s*"
    r")",
    re.IGNORECASE,
)

# Same prefix anywhere in the body — promoted to a list-separator so a
# `στους δήμους X, Y και Z` lead-in doesn't trap the first δήμος name
# inside a long prose chunk.
_DIMOS_MARKER_RE = re.compile(
    r"\b(?:στ(?:ους|ον|ις|ην|α|η|ο)\s+|τ(?:ους|ης|ου|ων|ο|α|η|ην)\s+)?"
    r"(?:(?:όμορ|ομορ|γειτονικ)[α-ωά-ώ]*\s+)?"
    r"(?:"
    # The pre-Kallikratis sub-unit tier ("το όμορο δημοτικό διαμέρισμα
    # Ουρανούπολης") is a separator too, so a prose lead-in
    # ("Περιλαμβάνει …") does not swallow the name after it.
    r"(?:δημοτικ|τοπικ)(?:ό|ο|ού|ου|ά|α|ών|ων)\s+"
    r"διαμ(?:έρισμα|ερισμα|ερίσματος|ερισματος|ερίσματα|ερισματα|ερισμάτων|ερισματων)|"
    # The genitive plural moves the accent (κοινότητα → κοινοτήτων), so it
    # is spelled out, not built on the singular stem.
    r"(?:δημοτικ|τοπικ)(?:ών|ων|ής|ης|ές|ες|ή|η)\s+"
    r"(?:κοινοτήτων|κοινοτητων|ενοτήτων|ενοτητων|"
    r"κοινότητ(?:ας|ες|α)|κοινοτητ(?:ας|ες|α)|ενότητ(?:ας|ες|α)|ενοτητ(?:ας|ες|α))|"
    r"δήμ(?:ους|ων|ου|ο|ος|οι)|δημ(?:ους|ων|ου|ο|ος|οι)|"
    r"κοινοτήτων|κοινοτητων|κοινότητ(?:ας|ες|α)|κοινοτητ(?:ας|ες|α)|"
    # "τις περιοχές του Δ.Δ. Λευκών του Δήμου Πάρου": the abbreviation is a
    # tier word too, else the prose lead-in swallows the name (Θαψανά).
    r"δ\.\s*δ\b\.?|"
    # "δήμους, κοινότητες και περιοχές Κερατέας, Κρωπίας …" (a 1979 decree)
    r"περιοχ(?:ές|ες|ή|η|ής|ης)(?=\s+(?-i:[Α-ΩΆΈΉΊΌΎΏ]))"
    # "του Δημοτικού Διαμερίσματος της Νέας Μεσημβρίας": an article between
    # the tier word and the name is part of the marker
    r")\s+(?:(?:του|της|των)\s+)?",
    re.IGNORECASE,
)

# Splitter — comma, semicolon, em-dash, en-dash, "και", newline, colon.
# Parentheses bracket a sub-list ("Καρύστου (Δ.Δ. Καρύστου, Αετού, …) τα
# Δ.Δ. Μαρμαρίου"), so they separate too.
_COMMUNE_SPLIT_RE = re.compile(
    r"\s*[,;:\n—–()]\s*|\s+καθ(?:ώ|ω)ς(?:\s+και)?\s+|\s+και\s+", re.IGNORECASE
)

# Tokens whose presence in a chunk signals it is prose, not a name.
_PROSE_TOKENS = frozenset(w.casefold() for w in {
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
    "βρίσκεται", "βρισκεται",
    "οινικ(ός|ού|ής)", "οινικη",
})  # fmt: skip

# Drop these as not-a-name tokens (connectives / wine-law verbs that
# may survive the tier-prefix strip).
_DROP_WORDS = frozenset(w.casefold() for w in {
    "και", "ή", "η", "ότι", "οτι", "όπως", "οπως", "καθώς",
    "καθως", "συμπεριλαμβανομένων", "συμπεριλαμβανομενων",
    "συγκεκριμένα", "συγκεκριμενα",
    "στ", "στο", "στη", "στην", "στις", "στους", "στον", "στα",
    # residue of the spec boilerplate and of measure phrases
    "φεκ", "που", "τις", "μέτρα", "μετρα", "άνω", "ανω", "κάτω", "κατω", "όρια", "ορια",
    "υπουργική απόφαση", "υπουργικη αποφαση", "υπουργικές αποφάσεις", "υπουργικες αποφασεις",
    "τα δ.δ", "δ.δ", "δ.δ.",
    "του", "της", "των", "ο", "η", "οι", "τα", "τις", "τους",
    "από", "απο", "για", "με", "σε", "προς", "παρά", "παρα",
    # Greek months (genitive forms appear in publication-date prose
    # that bleeds into the area description).
    "ιανουαρίου", "ιανουαριου", "φεβρουαρίου", "φεβρουαριου",
    "μαρτίου", "μαρτιου", "απριλίου", "απριλιου", "μαΐου", "μαιου",
    "ιουνίου", "ιουνιου", "ιουλίου", "ιουλιου", "αυγούστου",
    "αυγουστου", "σεπτεμβρίου", "σεπτεμβριου", "οκτωβρίου",
    "οκτωβριου", "νοεμβρίου", "νοεμβριου", "δεκεμβρίου", "δεκεμβριου",
})  # fmt: skip


# GISCO LAU 2024 stores Greek units with the `Δημοτική Κοινότητα ` /
# `Τοπική Κοινότητα ` tier prefix baked into LAU_NAME. The normaliser
# must strip those so the bare community / δήμος name keys both sides
# of the index.
_LAU_TIER_PREFIX_RE = re.compile(
    r"^\s*(ψευδοδημοτική\s+κοινότητα|ψευδοδημοτικη\s+κοινοτητα|"
    r"δημοτική\s+κοινότητα|δημοτικη\s+κοινοτητα|"
    r"τοπική\s+κοινότητα|τοπικη\s+κοινοτητα|"
    r"δημοτική\s+ενότητα|δημοτικη\s+ενοτητα|"
    r"δήμος|δημος|κοινότητα|κοινοτητα)\s+",
    re.IGNORECASE,
)

# Publication spelling → GISCO LAU_NAME spelling, both already
# `_normalise_commune`d. Greek administrative names drift between the
# demotic and katharevousa declensions and between nominative and
# genitive, and GISCO follows ELSTAT, which is not consistent about
# either. Same shape as the AT `_GEMEINDE_ALIAS` table: one entry per
# verified pair, keyed left on what the spec writes.
_COMMUNE_ALIAS: dict[str, str] = {
    # ΠΓΕ Άγιο Όρος delimits "τη διοικητική περιοχή του Αγίου Όρους"
    # (genitive); GISCO EL_99010000 is "Ψευδοδημοτική Κοινότητα Άγιο
    # Όρος (Αυτοδιοίκητο)" (nominative), 335.9 km².
    "αγίου όρουσ": "άγιο όροσ",
    # …"και το όμορο δημοτικό διαμέρισμα Ουρανούπολης" (demotic
    # genitive); GISCO EL_13020105 is "Δημοτική Κοινότητα
    # Ουρανοπόλεως" (katharevousa genitive), 21.7 km².
    "ουρανούπολησ": "ουρανοπόλεωσ",
    # ΠΟΠ Ρομπόλα Κεφαλληνίας lists "Βλαχάτων της Κεφαλονιάς"; GISCO
    # EL_35010302 is "Δημοτική Κοινότητα Βλαχάτων Εικοσιμίας" (verified
    # 2026-09-24).
    "βλαχάτων": "βλαχάτων εικοσιμίασ",
    # ΠΓΕ Ίλιον: "στο Ίλιον Αττικής" (nominative, a three-letter stem the
    # stem key leaves alone); GISCO EL_47050000 is "Ψευδοδημοτική Κοινότητα
    # Ιλίου" (verified 2026-09-24).
    "ίλιον": "ιλίου",
}


# A Latin letter typed inside a Greek word ("Μυρoδάτου" with a Latin o, a
# keyboard or OCR slip) is read as the Greek letter it looks like.
_LATIN_TO_GREEK = str.maketrans("aeiokntxyvpbhmz", "αειοκντχυνρβημζ")
_GREEK_LETTER_RE = re.compile(r"[α-ωά-ώϊϋΐΰς]")
_LATIN_IN_WORD_RE = re.compile(r"[a-z]")


def _fold_latin_homoglyphs(s: str) -> str:
    return " ".join(
        w.translate(_LATIN_TO_GREEK) if _GREEK_LETTER_RE.search(w) and _LATIN_IN_WORD_RE.search(w) else w
        for w in s.split(" ")
    )


def _normalise_commune(name: str) -> str:
    """Greek-preserving normaliser. casefold + tier-prefix strip +
    parenthetical strip + collapse hyphens/whitespace + alias fold.
    The GISCO LAU index keys on this form.

    Greek `casefold()` folds the final sigma (ς → σ), so «Σαντορίνη»
    and «ΣΑΝΤΟΡΙΝΗ» collide. It does NOT strip the tonos, so
    «Σαντορίνη» and «Σαντορινη» do not — accented and unaccented
    spellings of the same name are different keys, and a verified
    pair belongs in `_COMMUNE_ALIAS` rather than in a blanket
    diacritic fold (Greek tonos is phonemic: `νόμος` / `νομός`).

    Greek community names like «Δημοτική Κοινότητα Σαντορίνης»
    normalise to "σαντορίνης".
    """
    if not name:
        return ""
    s = name.strip()
    s = _fold_latin_homoglyphs(s.casefold())
    # Strip both the publication-text tier-prefix and the GISCO
    # `δημοτική κοινότητα` baked-in prefix.
    s = _LAU_TIER_PREFIX_RE.sub("", s)
    s = _TIER_PREFIX_RE.sub("", s)
    # Strip trailing parenthesised qualifiers / brackets.
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return _COMMUNE_ALIAS.get(s, s)


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


# Where a national-spec "Οριοθετημένη περιοχή" section stops describing the
# area and starts its boilerplate: the NUTS code line, the map count, the
# legal basis. Everything after it is prose the list parser would mine.
_SPEC_TAIL_RE = re.compile(
    r"\b(?:a\.\s*Περιοχή\s+NUTS|b\.\s*Χάρτης|[ΑΒ]\)\s*Νομικό\s+πλαίσιο|Νομικό\s+πλαίσιο\s*:|"
    r"ΜΕΓΙΣΤΗ\s+ΑΠΟ[Δ∆]ΟΣΗ|Λεπτο[μµ]έρειες\s+της\s+γεωγραφικής|"
    r"[Α-ΩA-Z]\.\s+[Α-Ω]{3,}(?:\s+[Α-Ω]{3,})+)",
    re.IGNORECASE,
)

# The area is a whole administrative or physical unit — "στη Νήσο Θάσο",
# "όλες τις περιοχές του νομού", "στην Περιφερειακή Ενότητα Δράμας", "το
# σύνολο της νήσου Εύβοιας". Such a text is drawn from its NUTS unit; a
# sub-unit it also names is an illustration, not the extent.
_WHOLE_UNIT_RE = re.compile(
    r"(?:\bν[ήη]σο(?:υ|ς)?\b|\bνήσων\b|"
    r"\bόλ(?:ες|η|ο|ων|α)\s+τ(?:ις|ης|ην|ου|ο|α|ων)\s+(?:περιοχ|νομ|νήσ|νησ|έκτασ|εκτασ)|"
    r"\b(?:στ(?:ην|ον|ις|ους)|σε)\s+(?:όλ\w+\s+)?(?:την\s+)?περιφερειακ\w+\s+εν[οό]τητ|"
    r"\bσύνολο\s+τ(?:ης|ου|ων)\s+(?:νήσου|νομού|περιφερει|επαρχ)|"
    r"\bδιοικητικ\w*\s+όρια\s+τ(?:ου|ης)\s+(?:νομού|νήσου|περιφερειακ\w+\s+εν[οό]τητ)|"
    r"\bευρύτερη\s+περιοχή\s+του\s+ν(?:ομού|\.)\s|"
    r"\bολ[οό]κληρ\w*\s+(?:τ\w+\s+)?(?:νομ|νήσ|νησ|επαρχ|περιφερει))",
    re.IGNORECASE | re.UNICODE,
)

# Sub-unit tier words: a text carrying one enumerates communities, and a
# δήμος it names is then the container of the list, not a member of it.
# "την περιοχή Μοναστήρια Μεταξάτων της νήσου Κεφαλληνίας": the island
# only says where the named area is — not a whole-island text.
_NAMED_AREA_BEFORE_ISLAND_RE = re.compile(
    rf"(?i:\bπεριοχ(?:ή|ής))\s+{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}}\s+(?i:της|του)\s*$",
    re.UNICODE,
)


def _whole_unit(body: str) -> bool:
    for m in _WHOLE_UNIT_RE.finditer(body):
        if m.group(0).casefold().startswith(("νήσ", "νησ")) and _NAMED_AREA_BEFORE_ISLAND_RE.search(body[: m.start()]):
            continue
        return True
    return False


_SUBUNIT_TIER_RE = re.compile(
    r"(?:(?:δημοτικ|τοπικ)\w*\s+(?:κοινότητ|κοινοτητ|διαμ[εέ]ρ[ιί]σμ|εν[οό]τ[ηή]τ)|"
    r"\bδ\.\s*δ\b\.?|\bκοινοτ(?:ήτων|ητων|ήτας|ητας|ήτες|ητες)\b|\bκοινότητες\b|\bοικισμ(?:ών|ων|ού|ου)\b)",
    re.IGNORECASE,
)

# "Δήμου Καρύστου", "Δήμων Βουκολιών, Ινναχωρίου, Κισσάμου, Κολυμβαρίου και
# Μυθήμνης": the δήμοι themselves are the members. Names are proper nouns
# (capital initial), one or two tokens, joined by commas / και.
_DIMOS_REF_RE = re.compile(
    rf"(?i:\bδήμ(?:ου|ων|ο|ος|οι)|\bδημ(?:ου|ων|ο|ος|οι))\s+(?:(?i:τέως|πρώην)\s+)?"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?"
    rf"(?:\s*(?:,|(?i:και))\s*{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)*)",
    re.UNICODE,
)
_DIMOS_SPLIT_RE = re.compile(r"\s*,\s*|\s+και\s+", re.IGNORECASE)

# "τα Δ.Δ. του Δήμου Μαρμαρίου", "όλα τα δημοτικά διαμερίσματα του Δήμου X":
# every community of that pre-2011 δήμος — an expansion even inside a text
# that otherwise enumerates communities.
_ALL_SUBUNITS_OF_DIMOS_RE = re.compile(
    rf"(?i:\b(?:όλ(?:α|ων)\s+)?τ(?:α|ων)\s+(?:δ\.\s*δ\.|δημοτικ\w*\s+διαμερισμ[άα]τ\w*|"
    rf"(?:τοπικ|δημοτικ)\w*\s+κοινοτ[ήη]τ\w*)"
    rf"\s+τ(?:ου|ων)\s+(?:τέως\s+|πρώην\s+)?δήμ(?:ου|ων))\s+"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?"
    rf"(?:\s*(?:,|(?i:και))\s*(?i:(?:του\s+)?(?:τέως\s+|πρώην\s+)?δήμου\s+)?{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)*)",
    re.UNICODE,
)
_DIMOS_ITEM_PREFIX_RE = re.compile(r"^(?:του\s+)?(?:τέως\s+|πρώην\s+)?δήμου\s+", re.IGNORECASE)

# "των Δημοτικών Ενοτήτων Παληοκάστρου και Παραληθαίων", "της Δημοτικής
# Ενότητας Βελβεντού": a post-2011 municipal unit named as a member — unless
# the clause before it lists communities ("Τοπικές Κοινότητες Μεγαπλατάνου
# και Καλαποδίου της Δημοτικής Ενότητας Αταλάντης"), when it only says where
# they are.
_DE_REF_RE = re.compile(
    rf"(?i:\bδημοτικ(?:ής|ης|ών|ων)\s+εν[οό]τ[ηή]τ(?:ας|ων|α)|\bδ\.\s*ε\.)\s+(?:(?i:των|της|του)\s+)?"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?"
    rf"(?:\s*(?:,|(?i:και))\s*{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)*)",
    re.UNICODE,
)
# "Δ.Δ. Λευκών του Δήμου Πάρου", "Περιστερίου του Δήμου Αμαλιάδος", "των
# οικισμών Αγοράς … της δημοτικής κοινότητας Δοξάτου": the genitive unit
# after a listed member is its container, not a member.
_CONTAINER_RE = re.compile(
    rf"(?i:\b(?:του|της|των)\s+(?:τέως\s+|πρώην\s+)?"
    rf"(?:δήμου|δήμων|δημοτικ(?:ής|ης|ών|ων)\s+(?:εν[οό]τ[ηή]τ(?:ας|ων)|κοινότητ(?:ας|ων)|κοινοτήτων)|δ\.\s*ε\.))\s+"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)",
    re.UNICODE,
)
# "την περιοχή Ριτσώνα του Δήμου Αυλίδας", "της περιοχής Δοκού του Δήμου
# Χαλκιδέων": a locality below the community tier; when no community
# carries its name, its container is the finest polygon that holds it.
_LOCALITY_RE = re.compile(
    rf"(?i:\bπεριοχ(?:ή|ής|ές|ών))\s+({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)\s+"
    rf"(?i:(?:του|της)\s+(?:τέως\s+|πρώην\s+)?(δήμου|δημοτικ(?:ής|ης)\s+(?:εν[οό]τ[ηή]τας|κοινότητας)))\s+"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)",
    re.UNICODE,
)
# "την περιοχή με τοπωνύμιο «Πύργος Βασιλίσσης» στο Ίλιον Αττικής": a named
# place inside a community; the community is the finest polygon holding it.
_TOPONYM_LOCALITY_RE = re.compile(
    rf"(?i:\bπεριοχ(?:ή|ής)\s+με\s+(?:το\s+)?τοπων[υύ]μιο)\s+[«\"'“]?"
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,2}})[»\"'”]?\s+"
    rf"(?i:στ(?:ο|η|ην|ον|α|ις|ους))\s+({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)",
    re.UNICODE,
)
# "οριοθετείται από την διαχωριστική γραμμή Δροσιά- Άνοιξη- Άγιος Στέφανος-
# Λίμνη Μαραθώνα – …": the area is what a line through named places
# encloses. The places are landmarks, not members — see
# `GRPolygonIndex.units_union`, which draws the units they lie in and
# reports the polygon as approximate.
_BOUNDARY_LINE_RE = re.compile(
    r"(?i:\bοριοθετείται\s+από\s+(?:την\s+|τη\s+)?(?:διαχωριστική\s+)?γραμμή)\s+(.+)",
    re.UNICODE | re.DOTALL,
)
_LANDMARK_SPLIT_RE = re.compile(r"\s*[-–—]\s*")
# a period after three or more letters ends the sentence; "Αγ." does not
_LANDMARK_END_RE = re.compile(r"(?<=[α-ωά-ώϊϋΐΰς]{3})\.(?:\s|$)")
# "στα διοικητικά όρια των περιοχών τέως επαρχίας Μεγάρων": a pre-2006
# επαρχία, a tier GISCO never carried — resolved only through the pin file.
_EPARCHY_RE = re.compile(
    rf"(?i:\b(?:τέως|πρώην)\s+επαρχ(?:ίας|ία|ιας|ια))\s+({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)",
    re.UNICODE,
)
# "Π.Γ.Ε. Πλαγιές Αιγιαλείας", "ΠΟΠ Ρετσίνα Κορωπίου": the appellation's own
# name inside the prose is not a list item.
_GI_NAME_RE = re.compile(
    rf"(?:Π\.?\s*Γ\.?\s*Ε\.?|Π\.?\s*Ο\.?\s*Π\.?|Τοπικ(?:ός|ού)\s+Οίν(?:ος|ου))\s+{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}}",
    re.UNICODE,
)
_LIST_BEFORE_RE = re.compile(
    r"(?:κοινότητ|κοινοτήτ|διαμ[εέ]ρ|δ\.\s*δ\b|οικισμ)", re.IGNORECASE,
)
# For a δήμος, a list of municipal units before it makes it a container too
# ("των Δημοτικών Ενοτήτων Παληοκάστρου και Παραληθαίων του Δήμου Τρικκαίων").
_UNIT_LIST_BEFORE_RE = re.compile(
    r"(?:κοινότητ|κοινοτήτ|διαμ[εέ]ρ|δ\.\s*δ\b|οικισμ|εν[οό]τ[ηή]τ)", re.IGNORECASE,
)
# A period after a single capital ("Δ.Δ.", "Ν.", "Αρχ." is lowercase and
# left alone) is an abbreviation, not a sentence end.
_ABBREV_DOT_RE = re.compile(r"(?<=\b[Α-ΩΆΈΉΊΌΎΏA-Z])\.|(?<=\b[Α-ΩΆΈΉΊΌΎΏA-Z][α-ωά-ώa-z])\.|(?<=\b[Α-ΩΆΈΉΊΌΎΏA-Z][α-ωά-ώa-z]{2})\.")


def _names_in(group: str) -> list[str]:
    out: list[str] = []
    for part in _DIMOS_SPLIT_RE.split(group):
        part = _DIMOS_ITEM_PREFIX_RE.sub("", part.strip(" .,;"))
        if part and part not in out:
            out.append(part)
    return out


_SPECIFIES_AFTER_RE = re.compile(
    r"^\s*(?:\(|:|και\s+συγκεκριμένα\b|δηλαδή\b|που\s+περιλαμβάνει\b)", re.IGNORECASE,
)
# "… και της Δημοτικής Ενότητας Ερυθρών", "… και την περιοχή της Δημοτικής
# Κοινότητας Αφιδνών": a unit joined by a conjunction is a member in its own
# right, even after a list; a container follows its members with no
# conjunction ("Πηγαδιών … της δημοτικής κοινότητας Δοξάτου").
_COORDINATED_BEFORE_RE = re.compile(
    r"(?:^|[\s,])(?:καθώς\s+)?και\s+(?:(?:στην|στη|την|τη)\s+περιοχ\w+\s+)?(?:τ(?:ης|ων|ου|ην|η|ις|ους)\s+)?$",
    re.IGNORECASE,
)


def _is_container_context(
    body: str, start: int, end: int | None = None, list_re: re.Pattern = _LIST_BEFORE_RE,
) -> bool:
    """True when the sentence before `start` lists communities — the unit
    at `start` then only locates them — or when what follows `end` opens
    a specification of it: "Δήμου Καρύστου (Δ.Δ. …)", "του Δήμου
    Τυρνάβου και συγκεκριμένα της Δημοτικής Κοινότητας …"."""
    if end is not None and _SPECIFIES_AFTER_RE.match(body[end:end + 40]):
        return True
    if _COORDINATED_BEFORE_RE.search(body[max(0, start - 40):start]):
        return False
    folded = _ABBREV_DOT_RE.sub("_", body[:start])
    dot = max(folded.rfind(". "), folded.rfind(".\n"))
    clause = body[dot + 1:start] if dot >= 0 else body[:start]
    if list_re.search(clause):
        return True
    return False

# A list item that is prose, not a name: a lowercase first letter ("σε
# υψόμετρο", "και της περιοχής Δοκού", "όρους Κιθαιρώνα") or the decree
# words. A hyphenated line break inside a lowercase run ("Πύρ-γου") is closed.
_PROSE_ITEM_RE = re.compile(r"^[^\W\d_]")
_LINE_BREAK_HYPHEN_RE = re.compile(r"(?<=[α-ωά-ώϊϋΐΰ])-\s*(?=[α-ωά-ώϊϋΐΰ])")
# "Αμφίκλειας- Ελάτειας", "Σερβίων – Βελβεντού": one compound name.
_DASH_SPACING_RE = re.compile(r"(?<=[α-ωά-ώϊϋΐΰς])\s*[-–—]\s*(?=[Α-ΩΆ-ΏΪΫ])")
_PROSE_ITEMS = frozenset(w.casefold() for w in {"υπουργικές αποφάσεις", "υπουργική απόφαση"})


_LEADING_CONNECTIVE_RE = re.compile(r"^(?:καθώς\s+)?και\s+", re.IGNORECASE)


def _clean_items(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        item = _LEADING_CONNECTIVE_RE.sub("", _LINE_BREAK_HYPHEN_RE.sub("", item)).strip(" .,;")
        if not item or item.casefold() in _PROSE_ITEMS:
            continue
        if _PROSE_ITEM_RE.match(item) and not item[0].isupper():
            continue
        # "Σκουραίϊκα που βρίσκονται": the name is the capitalised head, the
        # rest is prose
        head = []
        for tok in item.split():
            if tok[0].islower():
                break
            head.append(tok)
        item = " ".join(head).strip(" .,;")
        if not item or item.casefold() in _PROSE_ITEMS:
            continue
        if item not in out:
            out.append(item)
    return out

# The founding ministerial decision, "Υπουργική Απόφαση αριθ. 310941/24.12.2010":
# its year says which municipal tier a "Δήμος" of the text is (see
# `GRPolygonIndex.units_union`).
_DECREE_YEAR_RE = re.compile(r"\b\d{3,7}\s*/\s*\d{1,2}[.\-/]\d{1,2}[.\-/](\d{4})\b")


# "Α. ΕΡΥΘΡΟΙ ΟΙΝΟΙ: … Β. ΕΡΥΘΡΩΠΟΙ ΟΙΝΟΙ: …" (Λευκάδα): one list per
# wine colour inside the delimitation — a separator, not the boilerplate
# tail the lettered-heading rule would cut at.
_COLOUR_LIST_HEADER_RE = re.compile(
    r"(?:\b[Α-Ω]\.\s+)?(?:ΕΡΥΘΡ|ΛΕΥΚ|ΡΟΖΕ|ΡΟΖ)\w*\s+ΟΙΝΟΙ\s*:", re.UNICODE,
)

# "Εξαιρούνται οι περιοχές …", "εκτός από τα Δ.Δ. …", "πλην …": what follows is
# excluded from the area — never a member; the exclusion itself is not drawn.
_EXCLUSION_RE = re.compile(
    r"\b(?:εξαιρ(?:ούνται|είται|ουμέν\w+)|εκτός\s+(?:από|των|της|του)|πλην)\b",
    re.IGNORECASE,
)

# "(πρώην Νομός)", "(τέως Δήμος)": a former-tier gloss, not a list.
_TIER_GLOSS_RE = re.compile(
    r"\((?:\s*(?:πρώην|πρ\.|τέως|προ\s)[^)]*|\s*περιλαμβάνοντ[^)]*|\s*οικισμ[^)]*|\s*βλέπε[^)]*)\)",
    re.IGNORECASE,
)


_OVERRIDES_PATH = Path(__file__).with_name("commune_overrides.json")


@lru_cache(maxsize=1)
def _load_pins() -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    """commune_overrides.json → ({slug: {normalised name: gisco id or
    prefix}}, {normalised eparchy name: [gisco prefixes]})."""
    if not _OVERRIDES_PATH.exists():
        return {}, {}
    data = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    records: dict[str, dict[str, str]] = {}
    for slug, names in (data.get("records") or {}).items():
        records[slug] = {_normalise_commune(name): spec["gisco"] for name, spec in names.items()}
    eparchies = {
        _normalise_commune(name): list(spec["gisco"])
        for name, spec in (data.get("eparchies") or {}).items()
    }
    return records, eparchies


def record_pins(slug: str) -> dict[str, str]:
    """The per-record unit pins of `slug` (normalised name → GISCO id or
    prefix), from commune_overrides.json; empty when it has none."""
    return dict(_load_pins()[0].get(slug, {}))


def eparchy_pins() -> dict[str, list[str]]:
    """The former-επαρχία compositions of commune_overrides.json (normalised
    name → GISCO prefixes), shared by every record that names one."""
    return dict(_load_pins()[1])


_LANDMARKS_PATH = Path(__file__).with_name("landmarks.json")


@lru_cache(maxsize=1)
def _load_landmarks() -> dict[str, dict[str, tuple[float, float] | None]]:
    if not _LANDMARKS_PATH.exists():
        return {}
    data = json.loads(_LANDMARKS_PATH.read_text(encoding="utf-8"))
    return {
        slug: {name: ((spec["lon"], spec["lat"]) if spec else None) for name, spec in names.items()}
        for slug, names in (data.get("records") or {}).items()
    }


def landmark_points(slug: str) -> dict[str, tuple[float, float] | None]:
    """The (lon, lat) of each place a record's boundary line names, from
    landmarks.json — None for a place no public gazetteer locates."""
    return dict(_load_landmarks().get(slug, {}))


def area_body(text: str) -> str:
    """The delimitation prose of an area section, without the national-spec
    boilerplate tail. NFKC folds the micro sign a PDF text layer uses for μ
    ("Τυµφαίων") into the Greek letter."""
    body = _truncate_at_terroir_section(unicodedata.normalize("NFKC", text or ""))
    body = _LINE_BREAK_HYPHEN_RE.sub("", body)
    body = _DASH_SPACING_RE.sub("-", body)
    body = _TIER_GLOSS_RE.sub(" ", body)
    body = _COLOUR_LIST_HEADER_RE.sub(", ", body)
    m = _SPEC_TAIL_RE.search(body)
    body = body[: m.start()] if m else body
    m = _EXCLUSION_RE.search(body)
    return body[: m.start()] if m else body


def parse_area_units(text: str) -> dict:
    """What an area text delimits by, for `GRPolygonIndex.units_union`:
    `communities` (the list parse of the prose), `dimoi` (δήμοι named as
    members — only when the text does not enumerate sub-units), the
    `whole_unit` flag and the founding decree's `decree_year`."""
    body = area_body(text)
    if not body.strip():
        return {"communities": [], "dimoi": [], "units": [], "containers": [],
                "localities": [], "eparchies": [], "landmarks": [],
                "whole_unit": False, "decree_year": None}
    whole = _whole_unit(body)
    eparchies = [m.group(1).strip() for m in _EPARCHY_RE.finditer(body)]
    landmarks: list[str] = []
    for m in _BOUNDARY_LINE_RE.finditer(body):
        clause = m.group(1)
        end = _LANDMARK_END_RE.search(clause)
        for part in _LANDMARK_SPLIT_RE.split(clause[: end.end()] if end else clause):
            part = part.strip(" .,;\n")
            if part and part[0].isupper() and part not in landmarks:
                landmarks.append(part)
    enumerates = bool(_SUBUNIT_TIER_RE.search(body))
    dimoi: list[str] = []
    all_of: list[str] = []
    for m in _ALL_SUBUNITS_OF_DIMOS_RE.finditer(body):
        all_of.extend(n for n in _names_in(m.group(1)) if n not in all_of)
    dimoi.extend(all_of)
    if not enumerates:
        for m in _DIMOS_REF_RE.finditer(body):
            dimoi.extend(n for n in _names_in(m.group(1)) if n not in dimoi)
    units: list[str] = []
    containers: list[str] = []
    container_spans: list[tuple[int, int]] = []
    for m in _DE_REF_RE.finditer(body):
        names = _names_in(m.group(1))
        if _is_container_context(body, m.start(), m.end()):
            containers.extend(names)
            container_spans.append(m.span())
        else:
            units.extend(n for n in names if n not in units)
    localities: list[dict] = []
    for m in _LOCALITY_RE.finditer(body):
        localities.append({
            "name": m.group(1).strip(), "container": m.group(3).strip(),
            "tier": "dimos" if m.group(2).lower().startswith("δήμ") else "unit",
        })
        containers.append(m.group(3).strip())
    for m in _TOPONYM_LOCALITY_RE.finditer(body):
        localities.append({
            "name": m.group(1).strip(), "container": m.group(2).strip(), "tier": "community",
        })
        containers.append(m.group(2).strip())
    if enumerates:
        for m in _CONTAINER_RE.finditer(body):
            if any(a <= m.start(1) < b for a, b in container_spans):
                continue  # the same phrase, already counted as a unit container
            names = _names_in(m.group(1))
            if _is_container_context(body, m.start(), m.end(), _UNIT_LIST_BEFORE_RE):
                containers.extend(names)
            elif m.group(0).lower().lstrip().split()[1].startswith("δήμ"):
                # "στα διοικητικά όρια του Δήμου Αιγιαλείας και …": a
                # whole δήμος beside the listed communities.
                dimoi.extend(n for n in names if n not in dimoi)
    # A container's name is a member only where the text also lists it as
    # one ("Δήμου Καρύστου (Δ.Δ. Καρύστου, …)"): count the occurrences.
    communities = _clean_items(parse_commune_list(body))
    container_counts: dict[str, int] = {}
    for c in containers:
        container_counts[c] = container_counts.get(c, 0) + 1
    kept: list[str] = []
    count_body = _GI_NAME_RE.sub(" ", body)
    locality_names = {loc["name"] for loc in localities}
    landmark_names = set(landmarks) | {n for lm in landmarks for n in lm.split()}
    for name in communities:
        if name in locality_names or name in eparchies or name in landmark_names:
            continue
        n_container = container_counts.get(name, 0)
        if n_container and len(re.findall(rf"(?<![\w-]){re.escape(name)}(?![\w-])", count_body)) <= n_container:
            continue
        if name in units or name in dimoi:
            continue
        kept.append(name)
    years = [int(y) for y in _DECREE_YEAR_RE.findall(text or "")]
    dimoi = [
        d for d in _clean_items(dimoi)
        if d not in units and (
            d in all_of
            or container_counts.get(d, 0) == 0
            or len(re.findall(rf"(?<![\w-]){re.escape(d)}(?![\w-])", count_body)) > container_counts[d]
        )
    ]
    return {
        "communities": kept,
        "dimoi": dimoi,
        "units": _clean_items(units),
        "containers": _clean_items(containers),
        "localities": localities,
        "eparchies": _clean_items(eparchies),
        "landmarks": landmarks,
        "whole_unit": whole,
        "decree_year": max(years) if years else None,
    }


def parse_commune_list(text: str) -> list[str]:
    """Extract δήμος / κοινότητα names from an ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ section-6
    area body.

    Result: deduped list of canonical name candidates that the
    geometry resolver unions against the GISCO LAU `EL_*` polygon
    set. Order preserved for debug-log readability.
    """
    if not text:
        return []
    body = area_body(text)
    body = _SUBUNIT_OF_DIMOS_RE.sub(r"\1", body)
    body = _ADMIN_AREA_MARKER_RE.sub(", ", body)
    body = _LIMITS_MARKER_RE.sub(", ", body)
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
        if any(ch.isdigit() for ch in key):
            continue
        if key in _DROP_WORDS or len(key) < 3:
            continue
        if key in _PERIPHEREIA_NAMES:
            continue
        seen.add(key)
        out.append(chunk)
    return out
