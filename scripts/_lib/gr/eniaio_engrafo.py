"""Greek-keyword tables for parsing the EUR-Lex "ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ".

The EUR-Lex single document is template-identical across languages: same
`<p class="ti-grseq-1">` section header tags, same numbered subsections,
same single-document anchor at the start of the per-language slab. So the
HTML-extraction machinery (regex for headers, slice-from-anchor) lives in
`scripts/gr/02_extract_pliegos.py` and reuses the ES / IT / AT / SI / HR /
HU / RO / BG idiom directly; this module contributes only the **Greek-
language tables** that map section titles → semantic roles.

Greek EU-OJ single-document template (as seen across the small handful
of publishable GR records and the wider EU corpus in Greek):

  1.  Όνομα (που θα καταχωρισθεί στο μητρώο)              — name
  2.  Είδος γεωγραφικής ένδειξης                           — PDO (ΠΟΠ) / PGI (ΠΓΕ)
  3.  Κατηγορίες αμπελοοινικών προϊόντων                   — categories
  4.  Περιγραφή του οίνου / των οίνων                      — description
  5.  Οινολογικές πρακτικές                                — practices + max yields
  6.  Οριοθετημένη γεωγραφική ζώνη                         — area
  7.  Κύρια οινοποιήσιμη ποικιλία/-ίες σταφυλιού           — grape varieties
  8.  Περιγραφή του δεσμού / των δεσμών                    — link to terroir
  9.  Άλλες ουσιώδεις προϋποθέσεις / Παραπομπή             — additional / reference

Greek regulator-acronyms preserved in keyword-form: ΠΟΠ (Προστατευόμενη
Ονομασία Προέλευσης / PDO) and ΠΓΕ (Προστατευόμενη Γεωγραφική Ένδειξη /
PGI). Greek is heavily inflected — the keyword tables include the most
common case forms (nominative + genitive + accusative). Title comparison
runs through `.casefold()`, which handles Greek polytonic / monotonic
diacritics consistently with `lower()`.
"""

from __future__ import annotations

import re
import unicodedata

SECTION_HEADER_RE = re.compile(
    r'<p[^>]*class="[^"]*\bti-grseq-1\b[^"]*"[^>]*>(.*?)</p>',
    re.S,
)
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\.\s*(.+?)\s*$", re.S)


_INFLECTION_PAREN_RE = re.compile(r"\([^)]{0,5}\)")
# Slash-inflection groups in the post-2024 (Reg. (EU) 2024/1143) template:
# `της/των`, `οινοποιήσιμης/-ων`, `ποικιλίας/-ών`. A slash followed by an
# optional hyphen and 1–4 Greek letters that are NOT followed by another
# Greek letter — the trailing-letter lookahead leaves real alternations
# like `λευκός/ερυθρός` (long segment) untouched.
_INFLECTION_SLASH_RE = re.compile(r"/-?[α-ω]{1,4}(?![α-ω])")


_LATIN_TO_GREEK = str.maketrans("aeiokntxyvpbhmz", "αειοκντχυνρβημζ")
_GREEK_LETTER_RE = re.compile(r"[α-ω]")
_LATIN_IN_WORD_RE = re.compile(r"[a-z]")


def greek_norm(s: str) -> str:
    """Greek-aware comparator key. casefold + diacritic-strip + final-sigma
    fold + inflection-suffix-paren drop. Handles four Greek-specific gotchas
    the BG/RO/HU casefold path doesn't have:

      - **Final sigma** (`ς` U+03C2 vs medial `σ` U+03C3). `.casefold()`
        of capital `Σ` produces `σ`, never `ς`, so a title that ended in
        capital Σ casefolds to `σ` while a keyword typed with `ς` at the
        end never matches. Fold both to `σ` for comparison.
      - **Polytonic vs monotonic diacritics**. Older Greek publications
        (and some OJ pages with the modification-preamble template) use
        polytonic accents (`ΕΝΙΑΊΟ ΈΓΓΡΑΦΟ`); newer ones use monotonic
        or none. NFKD-decompose + drop combining marks (Mn category)
        collapses every diacritic-bearing letter to its base.
      - **NFC vs NFD**. Greek text occasionally comes in NFD form
        (precomposed `ί` vs decomposed `ι` + combining tonos). The
        NFKD + drop-marks chain normalises both.
      - **Parenthetical inflection suffixes**. The combined
        singular/plural template variant writes a section-7 heading as
        `Κύρια(ες) οινοποιήσιμη(ες) ποικιλία(ες) σταφυλιού` — the `(ες)`
        groups splice singular + plural into one title and break every
        substring keyword match (`ποικιλία σταφυλιού` is no longer
        contiguous). Drop short (≤ 5-char) parenthetical groups so the
        inflected title collapses back to the canonical wording. Longer
        word-in-parens decorations (`(ονομασίες)`) and semantic parens
        (`(ξηρού, ημίγλυκου …)`) are left intact. The post-2024
        (Reg. (EU) 2024/1143) template uses the slash variant of the
        same trick — `της/των`, `ποικιλίας/-ών` — so short slash-suffix
        groups are dropped the same way (real alternations like
        `λευκός/ερυθρός` survive via a trailing-letter lookahead).
    """
    s = s.casefold()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = s.replace("ς", "σ")
    # A Latin letter typed inside a Greek word — GISCO's NUTS name "Aττική"
    # carries a Latin A, a spec's "Μυρoδάτου" a Latin o — reads as the
    # Greek letter it looks like.
    s = " ".join(
        w.translate(_LATIN_TO_GREEK) if _GREEK_LETTER_RE.search(w) and _LATIN_IN_WORD_RE.search(w) else w
        for w in s.split(" ")
    )
    s = _INFLECTION_PAREN_RE.sub("", s)
    s = _INFLECTION_SLASH_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# The single-document anchor, in normalised form. Stage 02's slicer
# walks every `ti-grseq-1` header and finds the first whose
# `greek_norm(text)` equals this string.
DOC_ANCHOR_NORM = greek_norm("ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ")


# Section title keyword → semantic role. Keywords stored casefolded; the
# matcher in stage 02 calls `.casefold()` on the title before testing.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "όνομα που θα καταχωρισθεί στο μητρώο",
        "ονομασία που θα καταχωρισθεί στο μητρώο",
        "ονομασία προς καταχώριση",
        "ονομασία/-ες",
        "ονομασία (ονομασίες)",
        "ονομασία",
        "όνομα",
    ),
    "category": (
        "είδος γεωγραφικής ένδειξης",
        "τύπος γεωγραφικής ένδειξης",
        "κατηγορίες αμπελοοινικών προϊόντων",
        "κατηγορία αμπελοοινικών προϊόντων",
        "κατηγορίες αμπελουργικών προϊόντων",
        "κατηγορίες οινικών προϊόντων",
        "κατηγορίες",
    ),
    "description": (
        "περιγραφή του οίνου ή των οίνων",
        "περιγραφή του οίνου/των οίνων",
        "περιγραφή του οίνου",
        "περιγραφή των οίνων",
        "περιγραφή του προϊόντος",
        "περιγραφή",
    ),
    "viticultural_practices": (
        "οινολογικές πρακτικές",
        "οινοποιητικές πρακτικές",
        "οινοποιήσιμες πρακτικές",
        "αμπελοκομικές πρακτικές",
        "αμπελουργικές πρακτικές",
        "ειδικές οινολογικές πρακτικές",
        "μέγιστες αποδόσεις",
        "ανώτατες αποδόσεις",
        "μέγιστη απόδοση",
    ),
    "geo_area": (
        # Reg. (EU) 2024/1143 template, section 9 — genitive, so the
        # nominative keywords below never matched it and the section was
        # dropped from the parse (Μακεδονία, OJ C/2026/2625).
        "συνοπτικός καθορισμός της οριοθετημένης γεωγραφικής περιοχής",
        "οριοθετημένης γεωγραφικής περιοχής",
        "οριοθετημένη γεωγραφική ζώνη",
        "οριοθετημένη γεωγραφική περιοχή",
        "οριοθετημένη περιοχή",
        "γεωγραφική ζώνη",
        "γεωγραφική περιοχή",
        "ζώνη παραγωγής",
        "περιοχή παραγωγής",
    ),
    "grape_varieties": (
        "κύρια οινοποιήσιμη ποικιλία ή ποικιλίες σταφυλιού",
        "κύρια οινοποιήσιμη ποικιλία/-ίες σταφυλιού",
        "κύριες οινοποιήσιμες ποικιλίες σταφυλιού",
        "κυριότερες οινοποιήσιμες ποικιλίες",
        "οινοποιήσιμες ποικιλίες σταφυλιού",
        "οινοποιήσιμες ποικιλίες",
        "ένδειξη της οινοποιήσιμης ποικιλίας αμπέλου",
        "οινοποιήσιμης ποικιλίας αμπέλου",
        "ποικιλίας αμπέλου",
        "ποικιλίας σταφυλιού",
        "ποικιλίες σταφυλιού",
        "ποικιλία σταφυλιού",
        "ποικιλίες αμπέλου",
        "ποικιλία αμπέλου",
        "ποικιλίες",
    ),
    "link_to_terroir": (
        "περιγραφή του δεσμού ή των δεσμών",
        "περιγραφή του δεσμού/των δεσμών",
        "περιγραφή του δεσμού",
        "περιγραφή των δεσμών",
        "δεσμός με τη γεωγραφική περιοχή",
        "δεσμός με τη γεωγραφική ζώνη",
        "αιτιώδης δεσμός",
        "δεσμός",
    ),
    "additional_conditions": (
        "άλλες ουσιώδεις προϋποθέσεις",
        "πρόσθετες προϋποθέσεις",
        "λοιπές προϋποθέσεις",
        "συμπληρωματικές απαιτήσεις",
        "παραπομπή στη δημοσίευση των προδιαγραφών",
        "παραπομπή στη δημοσίευση",
        "σύνδεσμος προς τις προδιαγραφές του προϊόντος",
        "σύνδεσμος προς τις προδιαγραφές",
    ),
}


# Title-prefixes that disqualify a section from being routed to `geo_area`
# even when the title carries a related keyword. Section 2 ("Είδος
# γεωγραφικής ένδειξης") carries "γεωγραφικής" inflected but its body is
# just "ΠΟΠ" / "ΠΓΕ".
_GEO_AREA_TITLE_BLOCKLIST = (
    # The 2024/1143 template's section 3, "Χώρα στην οποία ανήκει η
    # οριοθετημένη γεωγραφική περιοχή", whose body is the word "Ελλάδα" —
    # the RO decoy ("Țara căreia îi aparține…"), in Greek.
    "χώρα στην οποία ανήκει",
    "είδος γεωγραφικής ένδειξης",
    "τύπος γεωγραφικής ένδειξης",
    "κατηγορίες αμπελοοινικών προϊόντων",
    "κατηγορία αμπελοοινικών προϊόντων",
    "κατηγορίες αμπελουργικών προϊόντων",
)


# Grape role headers inside the grape-variety section. Greek single
# documents generally do not split principal / accessory in section 7;
# stage 02 defaults to "principal".
_GRAPE_ROLE_HEADER_RE_SRC = (
    r"\b(κύρι(?:α|ες|ος)|βασικ(?:ή|ές|ές)|συνιστώμεν(?:η|ες)|επιτρεπόμεν(?:η|ες)|"
    r"εγκεκριμέν(?:η|ες)|δευτερεύουσ(?:α|ες)|συμπληρωματικ(?:ή|ές))\s*"
    r"(?:ποικιλί(?:α|ες))?\s*:?\s*"
)
ROLE_HEADER_RE = re.compile(rf"^\s*-?\s*{_GRAPE_ROLE_HEADER_RE_SRC}$", re.IGNORECASE)
INLINE_ROLE_RE = re.compile(rf"{_GRAPE_ROLE_HEADER_RE_SRC}", re.IGNORECASE)

ROLE_BY_KEYWORD = {
    "κύρι": "principal",
    "βασικ": "principal",
    "συνιστ": "principal",
    "επιτρ": "principal",
    "εγκεκ": "principal",
    "δευτε": "accessory",
    "συμπλ": "accessory",
}


# Greek colour vocabulary for style detection.
COLOUR_BY_KEYWORD = {
    "λευκός οίνος": "blanc",
    "λευκοί οίνοι": "blanc",
    "λευκός": "blanc",
    "λευκοί": "blanc",
    "ερυθρός οίνος": "noir",
    "ερυθροί οίνοι": "noir",
    "ερυθρός": "noir",
    "ερυθροί": "noir",
    "κόκκινος οίνος": "noir",
    "κόκκινοι οίνοι": "noir",
    "ροζέ οίνος": "rose",
    "ροζέ οίνοι": "rose",
    "ροζέ": "rose",
    # The inflected forms the ΥΠΑΑΤ specs use in their alcohol minima and
    # category sentences ("για τους ερυθρούς και ερυθρωπούς οίνους …");
    # ερυθρωπός (reddish) is the Greek legal word for rosé (2026-10-23).
    "ερυθρού": "noir", "ερυθρών": "noir", "ερυθρό": "noir", "ερυθρά": "noir",
    "ερυθρή": "noir", "ερυθρές": "noir", "ερυθρούς": "noir",
    "λευκού": "blanc", "λευκών": "blanc", "λευκό": "blanc", "λευκά": "blanc",
    "λευκή": "blanc", "λευκές": "blanc", "λευκούς": "blanc",
    "ερυθρωπός": "rose", "ερυθρωποί": "rose", "ερυθρωπού": "rose", "ερυθρωπών": "rose",
    "ερυθρωπό": "rose", "ερυθρωπά": "rose", "ερυθρωπή": "rose", "ερυθρωπές": "rose",
    "ερυθρωπούς": "rose",
}


# A one-word colour form counts as a whole token beside a wine word (οίνος /
# κρασί within three tokens after it or one before) — "λευκά" is not
# Λευκάδα, "ερυθρωπές … αποχρώσεις" (an aged red's hue) no rosé — or at the
# head of a list of colours that shares one ("για ερυθρούς και 10% vol. για
# λευκούς και ερυθρωπούς οίνους", Larnaka). Shared by the EU-OJ and the
# national-spec parsers of GR and CY: the EU-OJ ones had matched every form
# as a substring, so phase B's inflected forms read Santorini's aged
# Vinsanto ("ερυθρές και καφέ αποχρώσεις") as a red wine (2026-10-23).
_WINE_WORD_RE = re.compile(r"^(?:οιν|κρασ)")
_LIST_GLUE = frozenset({"και", "η", "για", "τουσ", "τισ", "τα", "οι", "vol"})
_COLOUR_FORMS = {greek_norm(kw): colour for kw, colour in COLOUR_BY_KEYWORD.items() if " " not in kw}


def _beside_wine_word(tokens: list[str], i: int) -> bool:
    if any(_WINE_WORD_RE.match(t) for t in tokens[max(0, i - 1):i + 4]):
        return True
    for t in tokens[i + 1:i + 13]:
        if _WINE_WORD_RE.match(t):
            return True
        if t not in _COLOUR_FORMS and t not in _LIST_GLUE:
            return False
    return False


# The wine types a spec declares, colour by colour — "Οίνος λευκός ξηρός,
# ημίξηρος, ημίγλυκος, γλυκός" (Zakynthos), "Οίνος Ερυθρός ξηρός, ημίξηρος
# και ημίγλυκος" (Karditsa): a sweet or semi-sweet type is a style, as IT's
# dolce / amabile are; semi-dry is not added (2026-10-23).
_SWEETNESS = r"(?:ξηροσ|ημιξηροσ|ημιγλυκοσ|γλυκοσ|γλυκυσ)"
_TYPE_HEADER_RE = re.compile(
    rf"\bοινοσ\s+(?:λευκοσ|ερυθροσ|ερυθρωποσ|ροζε)\s+({_SWEETNESS}(?:\s*(?:,|και|η)\s*{_SWEETNESS})*)"
)
# ημίξηρος → Semi-dry since 2026-11-07 (decision: the same type-list rule as the sweet levels)
_SWEETNESS_STYLE = {"ημιξηροσ": "semi-dry", "ημιγλυκοσ": "semi-sweet", "γλυκοσ": "sweet", "γλυκυσ": "sweet"}


def sweetness_type_styles(text: str) -> set[str]:
    """Sweet / semi-sweet from the wine-type headers of a Greek text."""
    found: set[str] = set()
    for m in _TYPE_HEADER_RE.finditer(greek_norm(text or "")):
        for word in re.findall(rf"\b{_SWEETNESS}\b", m.group(1)):
            if word in _SWEETNESS_STYLE:
                found.add(_SWEETNESS_STYLE[word])
    return found


# A sparkling or semi-sparkling type in any inflection, a wine word at most two
# tokens before it or three after: "Οινοποίηση λευκών και ερυθρωπών
# ημιαφρωδών οίνων" (Arkadia), "Δ. ΟΙΝΟΣ ΗΜΙΑΦΡΩΔΗΣ" / "Οίνος λευκός
# ημιαφρώδης ξηρός" (Ήπειρος). The markers below read only "αφρώδη" /
# "αφρώδεις" and the nominative before οίνος; a mention with no wine word
# beside it ("δεν λείπουν και δείγματα αφρωδών", Λήμνος) is no type
# (2026-10-23).
_SPARKLING_STEMS = (("ημιαφρωδ", "semi-sparkling"), ("αφρωδ", "sparkling"))


def sparkling_type_styles(text: str) -> set[str]:
    """Sparkling / semi-sparkling types a Greek text states beside a wine word."""
    tokens = re.findall(r"[^\W\d_]+", greek_norm(text or ""))
    found: set[str] = set()
    for i, tok in enumerate(tokens):
        for stem, slug in _SPARKLING_STEMS:
            if tok.startswith(stem):
                if any(_WINE_WORD_RE.match(t) for t in tokens[max(0, i - 2):i + 4]):
                    found.add(slug)
                break
    return found


def colour_styles(text: str) -> set[str]:
    """The wine colours a Greek text states (`blanc` / `noir` / `rose`)."""
    norm = greek_norm(text or "")
    found = {colour for kw, colour in COLOUR_BY_KEYWORD.items()
             if " " in kw and greek_norm(kw) in norm}
    tokens = re.findall(r"[^\W\d_]+", norm)
    for i, tok in enumerate(tokens):
        colour = _COLOUR_FORMS.get(tok)
        if colour and colour not in found and _beside_wine_word(tokens, i):
            found.add(colour)
    return found


# Style markers in Greek, mapped to the shared style-taxonomy slugs.
# The Greek "λιαστός" (sun-dried straw-wine), "vin doux naturel"
# regulator alias "οίνος γλυκός φυσικός", and "αφρώδης" (sparkling)
# vocabulary cover the Vinsanto / Mavrodafni / Samos / Limnos /
# Patras dessert traditions.
STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bαφρώδ(?:ης|εις)\s+οίν(?:ος|οι)\b", re.I), "sparkling"),
    (re.compile(r"\bαφρώδ(?:η|εις)\b", re.I), "sparkling"),
    (re.compile(r"\bημιαφρώδ(?:ης|εις)\s+οίν(?:ος|οι)\b", re.I), "semi-sparkling"),
    (re.compile(r"\bημιαφρώδ(?:η|εις)\b", re.I), "semi-sparkling"),
    (re.compile(r"\bλιαστός\s+οίν(?:ος|οι)\b", re.I), "vin-de-paille"),
    (re.compile(r"\bλιαστ(?:ός|οί|ών)\b", re.I), "vin-de-paille"),
    (re.compile(r"\bvinsanto\b|\bvin\s*santo\b", re.I), "vin-de-paille"),
    (re.compile(r"\bόψιμη\s+συγκομιδή\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bόψιμος\s+τρύγος\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bοίν(?:ος|οι)\s+γλυκ(?:ός|είς)\s+φυσικ(?:ός|οί)\b", re.I), "vdn"),
    (re.compile(r"\bvin\s+doux\s+naturel\b", re.I), "vdn"),
    (re.compile(r"\bφυσικώς\s+γλυκ(?:ός|είς)\s+οίν(?:ος|οι)\b", re.I), "vdn"),
    (re.compile(r"\bοίν(?:ος|οι)\s+λικέρ\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bλικεροειδ(?:ής|είς)\b", re.I), "vin-de-liqueur"),
    (re.compile(r"\bευγενής\s+σήψη\b", re.I), "grains-nobles"),
    (re.compile(r"\bβοτρύτης\b", re.I), "grains-nobles"),
    # a sweet wine is the Sweet style, not a late harvest (2026-10-23)
    (re.compile(r"\bγλυκ(?:ύς|είς)\s+οίν(?:ος|οι)\b", re.I), "sweet"),
    (re.compile(r"\bξηρ(?:ός|οί)\s+οίν(?:ος|οι)\b", re.I), "dry"),
    # Rosé under its legal name in the ΥΠΑΑΤ specs: a wine type headed
    # "Οίνος Ερυθρωπός ξηρός" / "Γ. ΟΙΝΟΣ ΕΡΥΘΡΩΠΟΣ" / "Ο ερυθρωπός ξηρός
    # οίνος". Only the masculine form beside οίνος / οίνοι names a type: the
    # feminine "ερυθρωπές αποχρώσεις" (Πάρος, an aged red's hue) does not,
    # nor the CY specs' "για λευκούς και ερυθρωπούς οίνους" alcohol rule.
    (re.compile(
        r"\b[οo][ιί]ν(?:ος|οι)\b(?:\W+\w+){0,4}?\W+ερυθρωπ(?:[οό]ς|[οό][ιί])\b"
        r"|\bερυθρωπ(?:[οό]ς|[οό][ιί])\b(?:\W+\w+){0,3}?\W+[οo][ιί]ν(?:ος|οι)\b",
        re.I,
    ), "rose"),
)
