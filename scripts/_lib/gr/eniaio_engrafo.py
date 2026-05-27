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


def greek_norm(s: str) -> str:
    """Greek-aware comparator key. casefold + diacritic-strip + final-sigma
    fold. Handles three Greek-specific gotchas the BG/RO/HU casefold path
    doesn't have:

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
    """
    s = s.casefold()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = s.replace("ς", "σ")
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
}


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
    (re.compile(r"\bγλυκ(?:ύς|είς)\s+οίν(?:ος|οι)\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bξηρ(?:ός|οί)\s+οίν(?:ος|οι)\b", re.I), "dry"),
)
