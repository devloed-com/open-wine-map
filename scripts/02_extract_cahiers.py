"""Extract structured fields from each downloaded cahier des charges.

Pipeline stage 02.

For each cahier PDF in `raw/inao/cahiers/<sha>.pdf` (indexed by the manifest
written by stage 01), run `pdftotext -layout` and parse the XII-section legal
template to produce one JSON file per *denomination* under
`raw/inao/cahier-extracted/`.

A "denomination" here is one row of `id_denomination_geo` in the SIQO
referentiel. Most appellations have a single denomination — their own name —
but some (Muscadet Sèvre et Maine, Côtes du Rhône Villages, Coteaux du Layon,
Alsace grand cru, ...) carry several Dénominations Géographiques
Complémentaires (DGCs) under the same `id_appellation`. Each DGC gets its
own JSON, reuses the parent appellation's cahier (a single PDF per
appellation), and is tagged with `parent_*` fields so downstream stages can
render the relation.

A single BO Agri PDF sometimes bundles multiple *appellations* (e.g. all 51
Alsace grand crus share one file, or a JORF "sommaire" packs ~30 cahiers).
The parser splits on `Cahier des charges de l'appellation d'origine
contrôlée « <NAME> »` headers and keeps only the segment whose name matches
the parent appellation.

Re-runnable: a per-PDF cache keyed by sha avoids re-running pdftotext.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from _lib.fr import dgc_rules, shared_cahier, siqo
from _lib.fr.naming import candidate_keys, normalize_name
from _lib.grape_entity import (
    flush_unknowns_queue,
    preheat_vocabulary,
    set_pliego_context,
)
from _lib.grape_lexicon import parse_grapes, parse_styles
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CAHIERS = ROOT / "raw" / "inao" / "cahiers"
MANIFEST_PATH = CAHIERS / "manifest.json"
TEXT_CACHE = CAHIERS / ".text"
OUT_DIR = ROOT / "raw" / "inao" / "cahier-extracted"
INDEX_PATH = OUT_DIR / "_index.json"
SIQO_CSV = ROOT / "raw" / "inao" / "siqo-referentiel.csv"
TESSDATA_DIR = ROOT / "raw" / "_tools" / "tessdata"
FRA_TRAINEDDATA_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/fra.traineddata"

CAHIER_HEADER_RE = re.compile(
    r"Cahier des charges\s+(?:de|des)\s+(?:"
    r"l['’]appellation d['’]origine [\wÀ-ÿ]+"
    r"|l['’]Indication G[ée]ographique Prot[ée]g[ée]e"
    r"|[\wÀ-ÿ ]+?\s+appellations? d['’]origine [\wÀ-ÿ]+"
    r")\s*"
    r"[«\"]\s*([^»\"\n]+?)\s*[»\"]",
    re.IGNORECASE,
)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
# Cahiers use a mix of HYPHEN-MINUS, EN DASH, EM DASH, HORIZONTAL BAR, MINUS SIGN
DASH = r"[-–—―−]"
SECTION_HDR_RE = re.compile(
    # Section header: roman numeral, then either a period (post-2024 cahiers
    # write "I. Nom de l'appellation"), a dash ("I − Nom"), or both
    # ("I. − Nom"). Title runs to end of line. Requiring at least one of
    # period/dash separates real headers from in-sentence Roman references.
    # Leading whitespace includes \x0c so headers landing right after a page
    # break (pdftotext emits \x0c at page boundaries) still match.
    rf"^[ \t\x0c]*({'|'.join(ROMAN)})[ \t]*(?:\.[ \t]*(?:{DASH}[ \t]*)?|{DASH}[ \t]*)([^\n]+?)\s*$",
    re.MULTILINE,
)
CHAPITRE_RE = re.compile(r"^[ \t]*(?:CHAPITRE|Chapitre)\s+[IVX]+(?:er)?\b", re.MULTILINE)

# A "<département header>: <comma list of communes>" block. The dept name is
# a short proper-noun token (no commas, no colons) introduced by one of:
#   - "du département du <D>" / "des départements de <D>" (single-dept form,
#     possibly followed by additional context like "sur la base du COG ...")
#   - "Département <D>:" / "- D <D> :" (multi-dept form, one per line)
# Match a département header introducing a comma-separated commune list.
# Two grammatical forms in INAO cahiers:
#   "... du département du Jura, sur la base du COG de l'année 2021 :"
#   "- Département de Maine-et-Loire : Bouchemaine, ..."
# Department names are 1+ capitalised words possibly hyphenated; we anchor
# the end on either a comma, a parenthesis, or a colon.
# French article that introduces a dept name in cahiers. Each alternative
# includes the trailing whitespace it needs so the dept token comes right
# after — important because "de l'Yonne" has no space between the apostrophe
# and the proper noun.
_ART = r"(?:du\s+|de\s+(?:la|le|les)\s+|de\s+l['’]\s*|d['’]\s*|de(?:s)?\s+)"

_DEPT_HEADER_PATTERN = (
    # in-paragraph form: "... du département <ART><DEPT> ... :"
    # Prefix alternatives are case-insensitive (sentence-start "Dans le"
    # alongside mid-sentence "dans le"); the dept-name capture is NOT,
    # because we rely on uppercase initials to bound a proper-noun span.
    r"(?:"
    r"(?i:du\s+|de(?:s)?\s+|de\s+(?:la|le|les)\s+|de\s+l['’]\s*|d['’]\s*|dans\s+(?:le|les)\s+)"
    r"(?i:d[ée]partements?)\s+(?i:" + _ART + r")"
    # or per-line list form: "- Département <ART><DEPT> :"
    + r"|(?:^|\n)\s*-?\s*(?i:d[ée]partement)\s+(?i:" + _ART + r")"
    + r")"
    + r"(?P<dept>"
    + r"[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*"
    + r"(?:-[\wÀ-ÿ'’]+)*"
    + r"(?:[ \t]+[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*(?:-[\wÀ-ÿ'’]+)*)*"
    + r")"
    + r"\s*(?:\(\d+\))?"
    # up to four whole lines then the rest of a line before the colon — each
    # iteration must end on its newline, so a line with no colon costs its
    # length, not every way of splitting it (the optional `\n?` form took
    # 40 s on Saint-Chinian's centred "Département de l'Aude" headers)
    + r"(?P<after>(?:[^:\n]*\n){0,4}?[^:\n]*):"
    + r"(?P<communes>[^\n]*(?:\n(?!\s*\n|\s*-?\s*(?i:D[ée]partement|Dans\s+(?:le|les)\s+d[ée]partement)|\s*\d[ \t]*(?:°|[-–][ \t]*[A-Za-zÀ-ÿ])|\s*[IVX]+\s*\.\s*-|\s*[a-z]\)[ \t])[^\n]*)*)"
)
DEPT_HEADER_RE = re.compile(_DEPT_HEADER_PATTERN, re.MULTILINE)
# Sub-block headers inside section IV: "1° - Aire géographique",
# "1°- Aire parcellaire délimitée", plus the degree-less "1 - Aire
# géographique" / "1) Aire …" forms the 2024 PNOCDC republications use
# (Pouilly-Loché). The marker (°, dash or paren) is mandatory so a body
# line that merely starts with a digit ("3 communes …") never opens a
# block. Without the split the whole section is scanned and the aire de
# proximité immédiate list is taken as the aire géographique.
# Intra-line gaps are [ \t] only: a page-number line ("   2") followed by a
# form feed and "- Département du Rhône : …" must not glue into one header.
_AIRE_BLOCK_HEADER_PATTERN = (
    r"^[ \t\x0c]*(\d[ \t]*(?:°[ \t]*[-–)]?|[-–]|\))[ \t]*[A-Za-zÀ-ÿ][^\n]*)$"
)
# Sentence-form aire, used when a block carries no "Département de X :"
# list: "… sont assurés sur le territoire de la commune de Mâcon du
# département de Saône-et-Loire" / "des communes de A, B et C du
# département de l'Yonne". One match per (commune list, département).
_AIRE_SENTENCE_PATTERN = (
    r"(?:territoire\s+)?(?i:de\s+la\s+commune|des\s+communes)\s+(?i:de\s+|d['’]\s*)"
    r"(?P<communes>[^:;.]+?)\s+"
    r"(?i:du|dans\s+le)\s+(?i:d[ée]partement)\s+(?i:" + _ART + r")"
    r"(?P<dept>"
    r"[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*(?:-[\wÀ-ÿ'’]+)*"
    r"(?:\s+[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*(?:-[\wÀ-ÿ'’]+)*)*"
    r")"
)
AIRE_SENTENCE_RE = re.compile(_AIRE_SENTENCE_PATTERN)
COG_YEAR_RE = re.compile(r"code officiel g[ée]ographique de l['’]ann[ée]e\s+(\d{4})")
# The Loire republications (Saumur 2019 and 2024, Touraine, Anjou …) and
# some 260 other cahiers print the aire as a table: a label column ("Vins
# tranquilles blancs et / rosés", "Dénomination géographique complémentaire
# « Puy-Notre-Dame »") beside the commune column. pdftotext -layout
# interleaves the label words with the commune lines of the same row, so a
# commune read "Doué-en-Anjou (… de Doué-la-Vins tranquilles blancs et
# Fontaine …)" and every row repeated the list. The table is recognised by
# its "COMMUNES" header cell; `strip_table_label_column` then cuts each row
# block at the commune column.
_AIRE_TABLE_HEADER_RE = re.compile(
    r"^[ \t]*(?:COULEUR\s+DES\s+VINS|TYPE\s+DE\s+VIN|APPELLATION\s+D['’]ORIGINE"
    r"|D[ÉE]NOMINATIONS?\s+G[ÉE]OGRAPHIQUES?)[^\n]*\n"
    r"(?:[^\n]*\n){0,6}?[^\n]*\bCOMMUNES\b",
    re.MULTILINE,
)
# The BO Agri running header pdftotext prints at every page break. Inside a
# commune list it splits the list with a blank line, which ends the
# "Département de X :" capture (Marc d'Alsace's Haut-Rhin list stopped at
# Houssen); after a comma the list continues, so the header and its blank
# lines fold into one newline, elsewhere the blank lines stay.
_BO_PAGE_HEADER_RE = re.compile(r"(,?)\n[ \t\x0c]*Publié au BO[^\n]*\n((?:[ \t\x0c]*\n)*)")
# Sentence-form proximity zone, where the section has no numbered sub-blocks
# (the IGP template): "La zone de proximité immédiate définie par dérogation
# … est constituée par …". From that sentence on the text is the proximity
# zone, never the aire — Côtes du Lot's six out-of-département cantons were
# read as its aire until 2026-10-04.
_PROX_SENTENCE_RE = re.compile(
    r"^[ \t\x0c]*(?:La|L['’])\s*(?:zone|aire)\s+de\s+proximit[ée]\s+imm[ée]diate\b",
    re.MULTILINE | re.IGNORECASE,
)
# A whole département as the aire — "La récolte des raisins, la vinification
# et l'élaboration des vins … sont réalisées dans le département du Lot",
# "… sur le territoire du département de la Haute-Marne", "… sur la totalité
# du territoire du département de la Drôme", "… dans toutes les communes du
# département des Bouches-du-Rhône", "l'ensemble des communes des
# départements de l'Aude, de l'Hérault, du Gard et des Pyrénées-Orientales"
# — names no commune, so the record carries the département itself. The
# sentence is anchored here; the names are read from the window that follows
# it against the département table, so "Lot-et-Garonne", "Alpes de Haute
# Provence" and an article-less list come out whole.
_WHOLE_DEPT_ANCHOR_RE = re.compile(
    r"(?:(?i:r[ée]colte|production|toutes\s+les\s+[ée]tapes)[^.;:]{0,240}?"
    r"(?i:r[ée]alis[ée]e?s?|effectu[ée]e?s?|assur[ée]e?s?|ont\s+lieu|a\s+lieu)\s+"
    r"(?i:dans|sur)\s+(?i:la\s+totalit[ée]\s+du\s+territoire\s+(?:du|des)|le\s+territoire\s+(?:du|des)"
    r"|l['’]ensemble\s+(?:des\s+communes\s+)?(?:du|des)|toutes\s+les\s+communes\s+(?:du|des)|le|les|du|des)"
    r"\s+(?i:d[ée]partements?)\s+"
    r"|(?i:l['’]ensemble\s+des\s+communes\s+(?:du|des)\s+d[ée]partements?)\s+)"
)
_WHOLE_DEPT_WINDOW_END_RE = re.compile(
    r"[.;:]|\b(?i:ainsi\s+que|[àa]\s+l['’]ex(?:ception|clusion)|sauf|hormis|except[ée]|"
    r"et\s+(?:sur|les\s+communes|des\s+communes|pour)|correspondant|selon|sur\s+la\s+base)\b"
)


_DEPT_ITEM_ARTICLE_RE = re.compile(
    r"^(?:(?:et|ou)\s+)?(?:du|de\s+la|de\s+l['’]|des|de|d['’])\s*", re.IGNORECASE,
)


def _dept_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s'’-]+", " ", s).strip(" .,;:()")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def _is_parent_denom(d: dict) -> bool:
    """True iff a SIQO denomination row represents its appellation's parent
    record (vs a DGC). Strict equality covers the common case; fuzzy
    fallback via candidate_keys folds synonym order ("Alsace" vs "Alsace
    ou Vin d'Alsace"), case-only differences ("Comté Tolosan" vs "Comté
    tolosan"), and composite forms ("Blagny" vs "Blagny ou Blagny Côte de
    Beaune")."""
    if d["denomination"] == d["appellation"]:
        return True
    denom_keys = set(candidate_keys(d["denomination"]))
    app_keys = set(candidate_keys(d["appellation"]))
    return bool(denom_keys & app_keys)


_FRENCH_WORD_RE = re.compile(
    r"\b(de|la|le|du|les|des|et|en|pour|par|dans|est|ou|une|un|au|aux)\b",
    re.IGNORECASE,
)


def _looks_like_glyph_junk(text: str) -> bool:
    """Some cahier PDFs (CAVB / lr-origine / INAO-extranet 2011 cohort) embed
    Type 1C subset fonts without a ToUnicode CMap. pdftotext returns the raw
    glyph codes, which look like ASCII punctuation rather than text. Detect
    by counting common French function words — real cahiers have these
    extremely densely; glyph-junk has near zero."""
    sample = text[:8000]
    if not sample.strip():
        return False
    hits = len(_FRENCH_WORD_RE.findall(sample))
    return hits < 15


def _ensure_fra_traineddata() -> Path:
    """Return a directory containing fra.traineddata, downloading on first
    use. Tesseract loads language data from the directory pointed at by
    TESSDATA_PREFIX (or system defaults). We prefer a project-local cache so
    the pipeline doesn't depend on the user having brew tesseract-lang."""
    target = TESSDATA_DIR / "fra.traineddata"
    if target.exists():
        return TESSDATA_DIR
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    import urllib.request
    print(f"[ocr] downloading fra.traineddata to {target} (one-time, ~4 MB)", file=sys.stderr)
    urllib.request.urlretrieve(FRA_TRAINEDDATA_URL, target)
    return TESSDATA_DIR


def _ocr_pdf(pdf_path: Path) -> str:
    """Rasterise each page at 300 DPI and OCR with tesseract -l fra. Page
    boundaries marked with \\f to mirror pdftotext output."""
    import tempfile
    tessdata = _ensure_fra_traineddata()
    parts: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(td_path / "p")],
            check=True, capture_output=True,
        )
        for img in sorted(td_path.glob("p-*.png")):
            out_base = img.with_suffix("")
            subprocess.run(
                ["tesseract", "-l", "fra", str(img), str(out_base)],
                check=True, capture_output=True,
                env={**__import__("os").environ, "TESSDATA_PREFIX": str(tessdata)},
            )
            parts.append(out_base.with_suffix(".txt").read_text(encoding="utf-8"))
    return "\f".join(parts)


def pdftotext(pdf_path: Path) -> str:
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cached = TEXT_CACHE / f"{pdf_path.stem}.txt"
    if cached.exists() and cached.stat().st_mtime >= pdf_path.stat().st_mtime:
        return cached.read_text(encoding="utf-8")
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    if _looks_like_glyph_junk(out):
        print(f"[ocr] {pdf_path.name}: pdftotext yielded glyph-junk, falling back to OCR", file=sys.stderr)
        out = _ocr_pdf(pdf_path)
    cached.write_text(out, encoding="utf-8")
    return out


def split_bundle(text: str) -> dict[str, str]:
    """A BO Agri PDF can bundle many cahiers. Split into segments keyed by
    the appellation name from each `Cahier des charges...« NAME »` header.

    Two distinct PDF layouts to reconcile:

    1. **INAO PNO** — each cahier carries two header occurrences: a
       sentence-case preamble citing the homologation decret, then the
       all-caps section title. We want the LAST (canonical title) so the
       segment doesn't lose the cahier body to a tiny preamble carve-off.

    2. **BO Agri "Avis" + cahier annex** — the cahier header repeats on
       every PDF page as a page-footer (often 6–15 times). We want the
       FIRST occurrence so the segment covers the whole cahier annex.

    Heuristic: if a name occurs ≥3 times we treat it as page-footer
    repetition and key the segment to the FIRST occurrence; otherwise we
    keep the legacy "last" rule.
    """
    matches = list(CAHIER_HEADER_RE.finditer(text))
    if not matches:
        return {}
    positions_by_key: dict[str, list[int]] = {}
    canonical: dict[str, str] = {}
    for m in matches:
        name = m.group(1).strip()
        key = normalize_name(name)
        positions_by_key.setdefault(key, []).append(m.start())
        canonical[key] = name  # last-seen casing (purely for display)
    starts: dict[str, int] = {
        key: (positions[0] if len(positions) >= 3 else positions[-1])
        for key, positions in positions_by_key.items()
    }
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    segments: dict[str, str] = {}
    for i, (key, pos) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        segments[canonical[key]] = text[pos:end]
    return segments


def find_segment(segments: dict[str, str], target: str) -> str | None:
    """Match by normalized name, falling back to alias-component matching and
    finally substring contains.

    Cahiers like "Alsace grand cru" carry a single header for 51 individual
    lieux-dits — we accept a substring match in either direction so each
    lieu-dit can re-use the master cahier as its source.
    """
    if not segments:
        return None
    if len(segments) == 1:
        return next(iter(segments.values()))
    target_keys = candidate_keys(target)
    if not target_keys:
        return None
    for name, body in segments.items():
        seg_keys = set(candidate_keys(name))
        if seg_keys.intersection(target_keys):
            return body
    target_key = target_keys[0]
    for name, body in segments.items():
        nk = normalize_name(name)
        if target_key in nk or nk in target_key:
            return body
    return None


# IGPs use Arabic-numbered sections (1, 2, 3.1, 3.2, ...) under
# "Chapitre 1 : Dénomination et conditions de production".
IGP_SECTION_HDR_RE = re.compile(
    # Section header in IGP cahiers. Concrete shapes seen in the corpus:
    #   "1 Nom de l'IGP"                          (pre-2020 INAO template)
    #   "1. Nom de l'indication géographique"     (post-2020, dot after number)
    #   "4.1 - Eléments..."                       (cidre IGPs; dot subnumber)
    #   "4-1- Obligations..."                     (some AOPs hyphen subnumber)
    #   "4-1-1- Déclaration..."
    #   "1) DENOMINATION DU PRODUIT"              (BO Agri "Avis" cahier annex
    #                                              for cidre IGPs)
    # Allow `.` *or* `-` as subnumber separator inside the captured number,
    # then any of `. - : )` plus optional dash before the heading.
    #
    # Intra-header whitespace is `[ \t]*`, NOT `\s*`. The 2025 BO Agri
    # MAASA template emits each page as `<centered page number>\n\x0c<page
    # header>\n…` — a permissive `\s*` would bind the trailing page number
    # of one page to the "Publié au BO Agri…" header text on the next
    # page, producing phantom section titles. Restricting to space/tab
    # keeps the header recognition single-line. Leading whitespace does
    # admit \x0c, as the Roman regex does: a header that opens a new page
    # sits right after the form feed ("\x0c5    Encépagement" in the
    # Île-de-France cahier) and was otherwise never seen.
    # Top-level number is capped at 2 digits (1–99). Real IGP cahiers never
    # exceed ~12 top-level sections, but the unbounded form picked up 5-digit
    # postal codes ("11010 Vitoria-Gasteiz") as phantom section markers
    # whenever a misrouted cahier (e.g. an EU letter-section AOP) flowed
    # through this parser. Subsection depth stays unbounded (`4.1.2.3`).
    # Title must start uppercase (a lowercase start would re-admit the
    # analytic-norm lines like "125 mg/l …" as phantom titles) — with one
    # carve-out: a literal lowercase "lien" start, seen in the Côte
    # Vermeille cahier ("10- lien avec la zone géographique").
    rf"^[ \t\x0c]*(\d{{1,2}}(?:[.\-]\d+)*)[\.\-:\)]*[ \t]*(?:{DASH}[ \t]*)?"
    rf"((?:[A-ZÉÈÀÂÔÎÏÛŸ]|lien\b)[\wÀ-ÿ '’\-]{{3,80}})[ \t]*[:.]?[ \t]*$",
    re.MULTILINE,
)
# Match `Chapitre 1 :` (legacy) and `CHAPITRE 1 – DENOMINATION` (post-2020
# template uses uppercase + em-dash instead of colon).
IGP_CHAPITRE_RE = re.compile(
    r"^\s*Chapitre\s+\d+\s*[:\-–—―−]", re.MULTILINE | re.IGNORECASE
)


# Helpers for IGP section-number arithmetic. IGP cahiers number sections as
# either `4.1` (dot subnumber, most templates) or `4-1` (hyphen subnumber, used
# by some AOPs like Cornouaille). Hoisted to module scope so
# extract_igp_sections stays under the cognitive-complexity threshold.
def _is_subnumber(n: str) -> bool:
    return ("." in n) or ("-" in n)


def _num_parts(n: str) -> list[int]:
    return [int(p) for p in re.split(r"[.\-]", n) if p]


def _subnum_sep(n: str) -> str:
    return "-" if "-" in n else "."


def extract_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice a single-appellation cahier into Roman-numeral sections.

    Returns (bodies, titles) keyed by the Roman numeral. Titles let
    downstream code route semantic roles (aire / encépagement / lien) by
    keyword rather than fixed numbering — the post-2020 INAO template
    shifted geography from IV to III and encépagement from V to IV, so any
    cahier using the new layout was getting silently mis-parsed.

    The XII-section template repeats inside CHAPITRE II (déclarations) and
    CHAPITRE III (contrôles). We keep only CHAPITRE Ier sections — those
    are the ones consumed by the wiki.
    """
    chapitre_starts = [m.start() for m in CHAPITRE_RE.finditer(segment)]
    body = segment[: chapitre_starts[1]] if len(chapitre_starts) >= 2 else segment

    matches = list(SECTION_HDR_RE.finditer(body))
    present = {m.group(1) for m in matches}
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    last_roman = ""
    for i, m in enumerate(matches):
        roman = m.group(1)
        if roman == last_roman:
            # The cahier repeats the numeral it just used ("IV.- Aires …"
            # then "IV.-Encépagement" in Picpoul de Pinet): a typo for the
            # next numeral, which is then missing from the whole document
            # and whose successor follows right after. Relabel instead of
            # dropping the section on the floor. The successor test keeps
            # a CHAPITRE-II/III "II … II" repeat from being renamed.
            idx = ROMAN.index(roman)
            following = matches[i + 1].group(1) if i + 1 < len(matches) else ""
            if (idx + 2 < len(ROMAN) and ROMAN[idx + 1] not in present
                    and following == ROMAN[idx + 2]):
                roman = ROMAN[idx + 1]
        if roman in bodies:
            continue
        last_roman = roman
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[roman] = body[start:end].strip()
        titles[roman] = title
    return bodies, titles


# The XII canonical section titles of the AOC template, for a cahier whose
# headings carry no numeral at all: the 2024 Saumur cahier (arrêté du 12
# janvier 2024) prints "CHAPITRE Ier / Nom de l'appellation / Dénominations
# géographiques … / Couleurs et types de produit / Aires et zones …" as bare
# centred lines — pdftotext never sees the "I. -" the PDF draws as list
# numbering — so the Roman splitter returned nothing and the record was
# silently rescued from the superseded 2019 cahier. Each pattern must fill
# a whole line on its own; the sub-block "1°- Encépagement" does not.
_UNNUMBERED_TITLES: tuple[tuple[str, str], ...] = (
    ("I", r"Nom de l['’]appellation"),
    ("II", r"D[ée]nominations? g[ée]ographiques? et mentions? compl[ée]mentaires?"),
    ("III", r"Couleurs? et types? de produits?"),
    ("IV", r"Aires? et zones? dans lesquelles diff[ée]rentes op[ée]rations sont r[ée]alis[ée]es"),
    ("V", r"Enc[ée]pagement"),
    ("VI", r"Conduite du vignoble"),
    ("VII", r"R[ée]colte, transport et maturit[ée] du raisin"),
    ("VIII", r"Rendements?(?:\.?\s*" + DASH + r"?\s*Entr[ée]e en production)?"),
    ("IX", r"Transformation, [ée]laboration, [ée]levage, conditionnement, stockage"),
    ("X", r"Lien avec la zone g[ée]ographique"),
    ("XI", r"Mesures transitoires"),
    ("XII", r"R[èe]gles de pr[ée]sentation et d['’][ée]tiquetage"),
)
_UNNUMBERED_HDR_RE = re.compile(
    r"^[ \t\x0c]*(" + "|".join(f"(?P<r{i}>{pat})" for i, (_, pat) in enumerate(_UNNUMBERED_TITLES))
    + r")[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_unnumbered_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """The Roman-template sections of a cahier whose headings lost their
    numerals — see `_UNNUMBERED_TITLES`. Same (bodies, titles) shape as
    `extract_sections`; CHAPITRE Ier only; a title seen twice keeps its
    first occurrence."""
    chapitre_starts = [m.start() for m in CHAPITRE_RE.finditer(segment)]
    body = segment[: chapitre_starts[1]] if len(chapitre_starts) >= 2 else segment
    matches = list(_UNNUMBERED_HDR_RE.finditer(body))
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        roman = next(
            _UNNUMBERED_TITLES[j][0] for j in range(len(_UNNUMBERED_TITLES)) if m.group(f"r{j}")
        )
        if roman in bodies:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[roman] = body[m.end():end].strip()
        titles[roman] = re.sub(r"\s+", " ", m.group(1)).strip()
    return bodies, titles


# Title keywords that identify each semantic role inside a cahier. Match
# is case-insensitive substring on the section title; the first match wins.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    # "Aires et zones dans lesquelles..." or "Aire géographique" — match
    # phrases that imply a commune/parcel zone, not generic mentions of
    # "géographique" (which appears in Champagne's section II,
    # "Dénominations géographiques, mentions complémentaires").
    "aire": ("aires et zones", "aire géographique", "aire geographique"),
    "couleur": ("couleur",),
    "encepagement": ("encépagement", "encepagement"),
    "rendement": ("rendement",),
    "lien": ("lien avec", "lien au terroir", "lien au territoire"),
    "transformation": ("transformation",),
    "nom": ("nom de l'appellation", "nom de l’appellation"),
}


def route_sections(bodies: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Map semantic role → section body using title keywords.

    Falls back to the legacy fixed-numeral mapping when titles are empty
    or untitled — keeps older cahiers working.
    """
    routed: dict[str, str] = {}
    for role, keywords in SECTION_ROLE_KEYWORDS.items():
        for roman, title in titles.items():
            if any(kw in title.lower() for kw in keywords):
                routed[role] = bodies.get(roman, "")
                break
    # Legacy fallback for the pre-2020 numbering. Only used when title-based
    # routing didn't find a match (e.g. the old template's section II is
    # "Pas de disposition particulière" with no descriptive title).
    if "aire" not in routed:
        routed["aire"] = bodies.get("IV", "")
    if "couleur" not in routed:
        routed["couleur"] = bodies.get("III", "")
    if "encepagement" not in routed:
        routed["encepagement"] = bodies.get("V", "")
    if "lien" not in routed:
        routed["lien"] = bodies.get("X", "")
    return routed


# "1°- Encépagement" / "1° - Encépagement" / "1 - Encépagement": the
# sub-block of section V that carries the role lists.
ENCEPAGEMENT_BLOCK_RE = re.compile(
    rf"^[ \t\x0c]*1[ \t]*(?:°[ \t]*{DASH}?|{DASH}|\))[ \t]*Enc[ée]pagement\b",
    re.MULTILINE | re.IGNORECASE,
)


def encepagement_block(section: str) -> str:
    """Drop whatever precedes the "1°- Encépagement" sub-block of section V.

    The 2025 MASA republications (Costières de Nîmes) open section V with
    the page header and the règles-de-proportion prose *before* the 1°
    sub-block; `parse_grapes` truncates at the first "règles de
    proportion" and so read nothing. A section that opens with the
    sub-block — or has none — is returned unchanged.
    """
    m = ENCEPAGEMENT_BLOCK_RE.search(section)
    if m is None or m.start() == 0:
        return section
    return section[m.start():]


_IGP_LIEN_KEYWORDS = ("lien avec", "lien au terroir", "lien au territoire", "lien à l'origine")
_IGP_LIEN_ABSORB_THRESHOLD = 800


def _is_short_lien_parent(num: str, title: str, txt: str) -> bool:
    """A parent-numbered section whose title is the lien-narrative heading
    and whose body is too short to be the actual lien content."""
    if _is_subnumber(num):
        return False
    if len(txt) >= _IGP_LIEN_ABSORB_THRESHOLD:
        return False
    return any(kw in title.lower() for kw in _IGP_LIEN_KEYWORDS)


def _absorb_following_subnumbers(
    ordered: list[tuple[str, str, str]], parent_idx: int,
) -> tuple[str, str, str]:
    """Return a new (num, title, body) for the parent at `parent_idx`, with
    every following sub-numbered entry's body appended until the next parent.
    Returns the parent unchanged if no sub-numbered entries follow."""
    num, title, txt = ordered[parent_idx]
    merged: list[str] = [txt] if txt else []
    j = parent_idx + 1
    while j < len(ordered) and _is_subnumber(ordered[j][0]):
        _, ch_title, ch_txt = ordered[j]
        merged.append(f"{ch_title}\n{ch_txt}" if ch_title else ch_txt)
        j += 1
    if len(merged) <= 1:
        return num, title, txt
    return num, title, "\n\n".join(p for p in merged if p)


def _absorb_lien_orphans(
    ordered: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Merge sub-numbered entries that document-order-follow a short Lien
    parent into that parent's body.

    Some IGP cahiers number the lien-narrative sub-sections inconsistently
    (e.g. parent `7 – Lien avec la zone géographique` followed by
    `8-1 Spécificité de la zone` / `8-2 Spécificité du produit` /
    `8-3 Lien causal…` — the children claim parent "8" but the actual
    parent is "7"). Without absorption, the parent stays at the bare title
    fragment and the lien text is dropped on the floor.

    Triggers only when the parent's title matches a lien-narrative keyword
    AND the parent body is shorter than the absorption threshold —
    legitimate well-numbered sections are left alone.
    """
    out = list(ordered)
    for i, (num, title, txt) in enumerate(out):
        if _is_short_lien_parent(num, title, txt):
            out[i] = _absorb_following_subnumbers(out, i)
    return out


def extract_igp_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice an IGP cahier into Arabic-numbered sections.

    Returns (bodies, titles). Titles let downstream code route the
    lien-narrative by keyword rather than positional fallback — IGP
    cahiers number the lien section as either 7 or 8 depending on the
    template and other sections sometimes claim that number too, so the
    older `sections.get("8") or sections.get("7")` lookup picked the
    wrong section for cahiers like Maures.

    Format: `1 Nom de l'IGP`, `2 Mentions...`, with subsections like
    `4.1 Zone géographique`. The top-level "4" usually contains nothing
    but a subheader; the real content lives in 4.1 / 4.2. We therefore
    keep both parents and children, and when a parent's body is empty we
    backfill it with the concatenated children so downstream lookups
    (which key on `"4"`) don't see an empty string.

    Special case for the lien-narrative section: when the parent's title
    is "Lien avec la zone géographique" / "Lien au terroir" /
    "Lien à l'origine" and its body is short (< 800 chars), absorb every
    sub-numbered section that follows it in document order — even if
    those children claim a different parent number (the haute-vallée-de-
    l-Orb cahier numbers them as `8-1`/`8-2`/`8-3` under parent `7 – Lien`).
    """
    chapitre_starts = [m.start() for m in IGP_CHAPITRE_RE.finditer(segment)]
    body = segment[: chapitre_starts[1]] if len(chapitre_starts) >= 2 else segment

    matches = list(IGP_SECTION_HDR_RE.finditer(body))

    ordered: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for i, m in enumerate(matches):
        num = m.group(1)
        if num in seen:
            continue
        seen.add(num)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        ordered.append((num, title, body[start:end].strip()))

    ordered = _absorb_lien_orphans(ordered)
    raw: dict[str, str] = {num: txt for (num, _, txt) in ordered}
    titles: dict[str, str] = {num: ttl for (num, ttl, _) in ordered}

    # Backfill sparse parents from their children. Section numbers may use
    # `.` (most templates) or `-` (some AOPs, e.g. Cornouaille's "4-1-").
    sections: dict[str, str] = {}
    for num, txt in raw.items():
        if _is_subnumber(num):
            continue
        if txt and len(txt) > 40:
            sections[num] = txt
            continue
        sep = next((_subnum_sep(k) for k in raw
                    if k.startswith((num + ".", num + "-"))), ".")
        children = sorted(
            (k for k in raw if k.startswith(num + sep)),
            key=_num_parts,
        )
        merged = "\n\n".join(raw[c] for c in children if raw[c])
        sections[num] = merged or txt
    return sections, titles


# Eaux-de-vie / spiritueux cahiers depart from the AOC XII-section template.
# They open with "Partie I : Fiche technique" and use either letter-headed
# (A. − Nom, B. − Description) or arabic-numbered (1. Nom, 2. Description)
# top-level sections. Detection anchors on the Partie I header so we don't
# mis-fire on AOC cahiers that happen to contain enumerated lists.
SPIRITUEUX_PARTIE_I_RE = re.compile(
    r"Partie\s+I\b[\s:\-–—―−]*Fiche\s+technique", re.IGNORECASE
)
SPIRITUEUX_PARTIE_II_RE = re.compile(r"Partie\s+II\b", re.IGNORECASE)
SPIRITUEUX_HDR_LETTER_RE = re.compile(
    rf"^[ \t\x0c]*([A-H])\s*\.\s*(?:{DASH}\s*)?([A-ZÉÈÀÂÔÎÏÛŸ][^\n]{{3,90}}?)\s*$",
    re.MULTILINE,
)
SPIRITUEUX_HDR_DIGIT_RE = re.compile(
    rf"^[ \t\x0c]*(\d{{1,2}})\s*\.\s*(?:{DASH}\s*)?([A-ZÉÈÀÂÔÎÏÛŸ][^\n]{{3,90}}?)\s*$",
    re.MULTILINE,
)

SPIRITUEUX_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nom": (
        "nom de l'appellation", "nom de l’appellation",
        "nom et catégorie", "nom et categorie",
    ),
    # "Description de la boisson spiritueuse" — the closest analog to
    # AOC section III (Couleur et types de produit). We route it under
    # "couleur" so derive_summary and downstream renderers consume it
    # transparently.
    "couleur": ("description de la boisson",),
    "aire": (
        "aire géographique", "aire geographique",
        "zone géographique", "zone geographique",
        "définition de l'aire", "définition de l’aire",
        "définition de la zone", "definition de la zone",
    ),
    "lien": (
        "lien à l'origine", "lien à l’origine",
        "lien avec la zone", "lien avec le milieu",
        "éléments corroborant le lien", "elements corroborant le lien",
    ),
}


def is_spiritueux_template(segment: str) -> bool:
    """A spiritueux/eaux-de-vie cahier opens with `Partie I … Fiche technique`."""
    return bool(SPIRITUEUX_PARTIE_I_RE.search(segment[:5000]))


def extract_spiritueux_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice a spiritueux cahier into top-level Partie-I sections.

    When both letter-headed (A./B./...) and arabic-numbered (1./2./...)
    headers appear, letters are top-level and digits are nested
    subsections — we keep only the level we recognise as top-level.
    """
    m_p1 = SPIRITUEUX_PARTIE_I_RE.search(segment)
    if not m_p1:
        return {}, {}
    m_p2 = SPIRITUEUX_PARTIE_II_RE.search(segment, m_p1.end())
    body = segment[m_p1.end(): m_p2.start() if m_p2 else len(segment)]

    letter_matches = list(SPIRITUEUX_HDR_LETTER_RE.finditer(body))
    if len(letter_matches) >= 3:
        matches = letter_matches
    else:
        matches = list(SPIRITUEUX_HDR_DIGIT_RE.finditer(body))

    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in bodies:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[label] = body[start:end].strip()
        titles[label] = title
    return bodies, titles


def route_by_keywords(
    bodies: dict[str, str], titles: dict[str, str], keywords_by_role: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    """Map semantic role → section body by title keyword, first match wins."""
    routed: dict[str, str] = {}
    for role, keywords in keywords_by_role.items():
        for label, title in titles.items():
            if any(kw in title.lower() for kw in keywords):
                routed[role] = bodies.get(label, "")
                break
    return routed


def route_spiritueux(bodies: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Map semantic role → spiritueux section body using title keywords."""
    return route_by_keywords(bodies, titles, SPIRITUEUX_ROLE_KEYWORDS)


# The 2026 eau-de-vie template (Marc d'Alsace Gewurztraminer, arrêté du 2
# septembre 2026). "Chapitre Ier : Conditions de production et lien à
# l'origine" carries Arabic "N. - Title" sections — Nom, Description de la
# boisson spiritueuse, Définition de la zone géographique concernée,
# Description de la méthode d'obtention (whose "4.1° Matière première" names
# the grape), Lien à l'origine géographique, Règles de présentation —
# Chapitre II the declarations and Chapitre III the control plan, whose
# table rows "A. - RÈGLES STRUCTURELLES / B. - RÈGLES ANNUELLES / C. –
# PRODUIT" are letter headers: they passed for an EU documento único (A/B/C)
# and the record came out with no aire, no lien and no grape.
SPIRITUEUX_2026_DESCRIPTION_RE = re.compile(
    rf"^[ \t\x0c]*\d{{1,2}}\s*\.\s*(?:{DASH}\s*)?Description\s+de\s+la\s+boisson\s+spiritueuse",
    re.MULTILINE | re.IGNORECASE,
)
SPIRITUEUX_CHAPITRE_RE = re.compile(
    r"^[ \t\x0c]*Chapitre\s+(?:I(?:er|ᵉʳ|°)?|II|III|IV|\d)\b", re.MULTILINE,
)
SPIRITUEUX_2026_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    **SPIRITUEUX_ROLE_KEYWORDS,
    "encepagement": (
        "méthode d'obtention", "méthode d’obtention", "methode d'obtention",
        "matière première", "matiere premiere",
    ),
}
MATIERE_PREMIERE_RE = re.compile(
    rf"^[ \t\x0c]*\d\.\d\s*°?\s*(?:{DASH}\s*)?Mati[èe]re\s+premi[èe]re\b",
    re.MULTILINE | re.IGNORECASE,
)
_SPIRITUEUX_SUBBLOCK_RE = re.compile(r"^[ \t\x0c]*\d\.\d\s*°", re.MULTILINE)
# "5. - Lien à l'origine géographique" is a section; "1. Description des
# facteurs du lien au terroir" inside it is a sub-item — the dash tells them
# apart, so the dash is mandatory here where SPIRITUEUX_HDR_DIGIT_RE has it
# optional.
SPIRITUEUX_2026_HDR_RE = re.compile(
    rf"^[ \t\x0c]*(\d{{1,2}})\s*\.\s*{DASH}\s*([A-ZÉÈÀÂÔÎÏÛŸ][^\n]{{3,90}}?)\s*$",
    re.MULTILINE,
)


def is_spiritueux_2026_template(segment: str) -> bool:
    """A 2026-template eau-de-vie cahier has a numbered "Description de la
    boisson spiritueuse" section (the Partie-I template is tested first)."""
    return bool(SPIRITUEUX_2026_DESCRIPTION_RE.search(segment[:20000]))


def extract_spiritueux_2026_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice Chapitre Ier of a 2026-template eau-de-vie cahier into its
    Arabic-numbered sections; the later chapters are left out."""
    chapters = list(SPIRITUEUX_CHAPITRE_RE.finditer(segment))
    start = chapters[0].end() if chapters else 0
    end = chapters[1].start() if len(chapters) >= 2 else len(segment)
    body = segment[start:end]
    matches = list(SPIRITUEUX_2026_HDR_RE.finditer(body))
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in bodies:
            continue
        titles[label] = re.sub(r"\s+", " ", m.group(2)).strip()
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[label] = body[m.end(): stop].strip()
    return bodies, titles


def matiere_premiere_block(section: str) -> str:
    """The "N.1° Matière première" sub-block of the méthode d'obtention
    section — the one that names the grape — or the section when it has
    none."""
    m = MATIERE_PREMIERE_RE.search(section)
    if m is None:
        return section
    rest = section[m.end():]
    nxt = _SPIRITUEUX_SUBBLOCK_RE.search(rest)
    return rest[: nxt.start()] if nxt else rest


def is_grape_spirit(categorie: str) -> bool:
    """An eau-de-vie made from grapes or wine (marc, vin), whose matière
    première is an encépagement — not cider, pear or fruit spirits."""
    cat = (categorie or "").lower()
    return "marc" in cat or "de vin" in cat or "raisin" in cat


# EU "documento único" letter-section template. Used by Franco-Spanish /
# cross-border AOPs registered directly under the EU framework (e.g. the
# cider AOP "Euskal Sagardoa / Sidra del País Vasco / Cidre du Pays Basque").
# Same A.–H. letter headers as the spiritueux Fiche technique, but without
# the `Partie I : Fiche technique` wrapper that gates the spiritueux parser.
# Detection requires A, B, and C to all appear as line-anchored letter
# headers — they're the first three sections of every EU documento único
# (Nom, Description, Délimitation), so a cahier missing any of the three
# isn't this template. Scans the full segment because section B can run
# many pages before C appears (Euskal Sagardoa's B is ~260 lines).
EU_LETTER_REQUIRED_PREFIX = {"A", "B", "C"}

EU_LETTER_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nom": (
        "nom de l'appellation", "nom de l’appellation",
        "nom(s) devant", "nom devant",
    ),
    "couleur": (
        "description du produit", "description des produits",
        "description de la boisson",
    ),
    "aire": (
        "délimitation de l'aire", "délimitation de l’aire",
        "delimitation de l'aire", "delimitation de l’aire",
        "aire géographique", "aire geographique",
        "zone géographique", "zone geographique",
    ),
    "lien": (
        "lien avec l'aire", "lien avec l’aire",
        "lien avec la zone", "lien avec le milieu",
        "lien à l'origine", "lien à l’origine",
        "éléments corroborant le lien", "elements corroborant le lien",
    ),
}


def is_eu_letter_template(segment: str) -> bool:
    """An EU documento-único cahier with A./B./C. headers and no Partie I anchor.

    Spiritueux cahiers also use letter headers but they sit under
    `Partie I : Fiche technique` — keep that branch in charge of them so
    the existing spiritueux routing still wins.
    """
    if SPIRITUEUX_PARTIE_I_RE.search(segment):
        return False
    letters = {m.group(1) for m in SPIRITUEUX_HDR_LETTER_RE.finditer(segment)}
    return EU_LETTER_REQUIRED_PREFIX.issubset(letters)


def extract_eu_letter_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice an EU letter-section cahier into A.–H. sections."""
    matches = list(SPIRITUEUX_HDR_LETTER_RE.finditer(segment))
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in bodies:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(segment)
        bodies[label] = segment[start:end].strip()
        titles[label] = title
    return bodies, titles


def route_eu_letter(bodies: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    routed: dict[str, str] = {}
    for role, keywords in EU_LETTER_ROLE_KEYWORDS.items():
        for label, title in titles.items():
            if any(kw in title.lower() for kw in keywords):
                routed[role] = bodies.get(label, "")
                break
    return routed


def parse_communes(field: str) -> list[str]:
    """Split `Commune A, Commune B et Commune C` into individual tokens.

    Both `, ` and ` et ` separate, but only at top level — `(...)` may
    enclose its own commas and "et"s (e.g. `Le Controis-en-Sologne (pour
    le territoire des communes déléguées de Feings, Fougères-sur-Bièvre
    et Ouchamps)`), and those must stay attached to their commune.
    pdftotext also leaves stray spaces after a soft-wrapped hyphen
    (`Saint-\n Claude-de-Diray` → `Saint- Claude-de-Diray`); we re-glue.
    """
    s = re.sub(r"\s+", " ", field).strip().rstrip(".;")
    # a soft-wrapped hyphen also precedes a lowercase particle
    # ("Fontevraud-\nl'Abbaye", "Villeneuve-\nde-la-Raho")
    s = re.sub(r"-\s+(?=[A-Za-zÀ-ÿ])", "-", s)
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and ch == ",":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
        elif depth == 0 and s[i : i + 4] == " et ":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
            i += 3  # consume " et"; loop's i += 1 takes the trailing space
        else:
            cur.append(ch)
        i += 1
    tok = "".join(cur).strip()
    if tok:
        out.append(tok)
    return out


def _clean_commune_tokens(tokens: list[str]) -> list[str]:
    """Drop the prose that rides along with a sentence-form commune list.

    A commune name starts with a capital and never contains a sentence
    break, but the sentence form leaks asides into the split tokens:
    "sur la base du code officiel géographique …" (Barsac), "située"
    (Loupiac: "la commune de Loupiac, située dans le département"). Applied
    to the sentence path only — the list form ("Département de X : …")
    legitimately carries lowercase-initial tokens in IGP layouts
    ("l'ensemble des communes …"), so it is left as it was.
    """
    out: list[str] = []
    for c in tokens:
        if ". " in c:
            c = c.split(". ", 1)[0].strip()
        if not c or not c[:1].isupper() or "code officiel" in c.lower():
            continue
        out.append(c)
    return out


def strip_table_label_column(text: str) -> str:
    """Cut the label column off a tabular aire list.

    Each row of the table is a block of non-blank lines whose commune cell
    starts at one column — the leftmost indent of the block's indented
    lines, always deep in the page. A line of the block that starts at the
    margin carries the row label ("Vins tranquilles rouges", "rosés",
    "Dénomination géographique complémentaire « La Méjanelle »"); what it
    has at the commune column is commune text, the rest is dropped, and a
    label line with nothing at that column disappears so the list is not cut
    by a blank. A block that is not mostly indented lines is a plain
    paragraph and is left as it was.
    """
    out: list[str] = []
    block: list[str] = []

    def lead(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def flush() -> None:
        leads = [lead(line) for line in block]
        indented = [x for x in leads if x >= 8]
        dept_leads = [x for line, x in zip(block, leads)
                      if x >= 8 and re.match(r"-?\s*D[ée]partement\b", line.lstrip(" "))]
        # the commune cell starts where the block's "Département de X :"
        # lines do — the table header's own cells ("COMPLEMENTAIRES") and a
        # row's centred line sit elsewhere — else at the indent most of the
        # block's indented lines share; a margin line keeps what it has at
        # that column, past a space so a label is never cut mid-word, and
        # nothing else
        if dept_leads:
            col = min(dept_leads)
        elif len(indented) >= 2:
            col = Counter(indented).most_common(1)[0][0]
        else:
            col = 0
        # a table row: mostly cell lines, or "Département" lines sharing one
        # indent beside a line that carries both a label and cell text. A
        # centred "Département de l'Aude" over a list at the margin (Saint-
        # Chinian's proximity zone) is neither and is left as it was.
        mostly_cells = len(indented) >= 2 and len(indented) * 10 >= len(block) * 6
        dept_rows = [line for line, x in zip(block, leads)
                     if x >= 8 and re.match(r"-?\s*D[ée]partement\b", line.lstrip(" "))]
        two_columns = bool(dept_rows) and all(":" in line for line in dept_rows) and any(
            x < 8 and len(line) > col and line[col - 1] == " " and line[col:].strip()
            for line, x in zip(block, leads)
        )
        if col < 8 or not (mostly_cells or two_columns):
            out.extend(block)
        else:
            for line, x in zip(block, leads):
                if x >= 8:
                    out.append(line)
                    continue
                if len(line) > col and line[col - 1] == " " and line[col:].strip():
                    out.append(" " * col + line[col:])
        block.clear()

    for line in text.split("\n"):
        if line.strip():
            block.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def whole_departements(text: str) -> list[str]:
    """Départements the aire sentence names as a whole, in text order, spelt
    as the département table spells them."""
    from _lib.geom_chain import DEPT_NAME_TO_CODE

    by_key = {_dept_key(name): name for name in DEPT_NAME_TO_CODE}
    flat = re.sub(r"-\s*\n\s*", "-", text)
    flat = re.sub(r"\s+", " ", flat)
    out: list[str] = []
    for m in _WHOLE_DEPT_ANCHOR_RE.finditer(flat):
        window = flat[m.end(): m.end() + 400]
        stop = _WHOLE_DEPT_WINDOW_END_RE.search(window)
        if stop:
            window = window[: stop.start()]
        # "du Doubs, de la Haute-Saône, du Territoire de Belfort, et du Jura":
        # each item, its article dropped, must be a département whole — the
        # first that is not ends the list
        for item in re.split(r"\s*,\s*|\s+et\s+|\s+ou\s+", window):
            item = _DEPT_ITEM_ARTICLE_RE.sub("", item.strip())
            name = by_key.get(_dept_key(item))
            if name is None:
                if item.strip():
                    break
                continue
            if name not in out:
                out.append(name)
    return out


_PARAGRAPH_AFTER_RE = re.compile(
    r"(?:[ \t]*\n)+((?:(?![ \t]*\n|[ \t\x0c]*-?[ \t]*D[ée]partement\b|[ \t]*\d[ \t]*(?:°|[-–][ \t]*[A-Za-zÀ-ÿ])"
    r"|[ \t]*[IVX]+[ \t]*\.[ \t]*-)[^\n]*\n?)+)"
)


def _list_paragraph_after(text: str, pos: int) -> str:
    """The paragraph after `pos` when it reads as a commune list — mostly
    capitalised, comma-separated tokens — else an empty string."""
    m = _PARAGRAPH_AFTER_RE.match(text, pos)
    if not m:
        return ""
    para = m.group(1)
    first = para.strip().split("\n", 1)[0]
    if "," not in first and " et " not in first:
        return ""  # a table header, a title, prose
    tokens = parse_communes(para)
    if len(tokens) < 2 or any("«" in t or re.fullmatch(r"[A-ZÉÈÀÂÔÎÏÛŸ' ]{6,}", t) for t in tokens):
        return ""
    capitalised = sum(1 for t in tokens if t[:1].isupper())
    return para if capitalised * 10 >= len(tokens) * 7 else ""


def extract_aire(section_iv: str) -> dict:
    """Parse section IV. Returns geographique/proximite_immediate commune lists
    and, when the aire is a whole département, `aire_departements`."""
    cog_match = COG_YEAR_RE.search(section_iv)
    cog_year = int(cog_match.group(1)) if cog_match else None

    section_iv = _BO_PAGE_HEADER_RE.sub(
        lambda m: ",\n" if m.group(1) else "\n" + m.group(2), section_iv,
    )
    if _AIRE_TABLE_HEADER_RE.search(section_iv):
        section_iv = strip_table_label_column(section_iv)
    # a name hyphenated across lines ("Saône-et-\nLoire", "Doué-la-\nFontaine")
    section_iv = re.sub(r"(?<=\w)-\n(?=[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸa-zà-ÿ])", "-", section_iv)

    blocks = re.split(_AIRE_BLOCK_HEADER_PATTERN, section_iv, flags=re.MULTILINE)
    # blocks: [pre, header1, body1, header2, body2, ...]
    by_block: dict[str, str] = {}
    for i in range(1, len(blocks) - 1, 2):
        by_block[blocks[i].strip()] = blocks[i + 1]

    sentence_form_used = False

    def by_dept(text: str) -> dict[str, list[str]]:
        nonlocal sentence_form_used
        result: dict[str, list[str]] = defaultdict(list)
        for m in DEPT_HEADER_RE.finditer(text):
            dept = re.sub(r"\s+", " ", m.group("dept")).strip(" '’.,:")
            # `after` captures interstitial context like "sur la base du COG"
            # — we don't need it but we discard it explicitly so a stray
            # comma/period there isn't treated as a commune separator.
            communes_raw = m.group("communes")
            communes_raw = re.split(r"\n\s*\n|\f", communes_raw)[0]
            # "Département de l'Ardèche : 96 communes" — the count is not a
            # commune; and a header whose list starts after a blank line
            # ("de la Meuse :\n\nBilly-sous-les-Côtes, …") has its list in
            # the next paragraph, when that paragraph reads as a list.
            communes_raw = re.sub(r"^\s*\d+\s+communes?\b\s*:?", "", communes_raw)
            if not communes_raw.strip():
                communes_raw = _list_paragraph_after(text, m.end())
            communes = [c.split(". ", 1)[0].strip() if ". " in c else c
                        for c in parse_communes(communes_raw)]
            if communes:
                # a table lists the same communes once per wine type
                result[dept].extend(c for c in communes if c not in result[dept])
        if not result:
            for m in AIRE_SENTENCE_RE.finditer(text):
                dept = re.sub(r"\s+", " ", m.group("dept")).strip(" '’.,:")
                communes = _clean_commune_tokens(parse_communes(m.group("communes")))
                if communes:
                    result[dept].extend(communes)
                    sentence_form_used = True
        return dict(result)

    aire_geo_text = next(
        (v for k, v in by_block.items() if "Aire g" in k or "géographique" in k.lower()),
        section_iv,
    )
    aire_prox_text = next(
        (v for k, v in by_block.items() if "proximit" in k.lower()),
        "",
    )
    if not aire_prox_text:
        m = _PROX_SENTENCE_RE.search(aire_geo_text)
        if m:
            aire_geo_text, aire_prox_text = aire_geo_text[: m.start()], aire_geo_text[m.start():]

    geo = by_dept(aire_geo_text)
    geo_from_sentence = sentence_form_used
    whole = whole_departements(aire_geo_text)
    if whole and geo_from_sentence:
        # "La récolte … est réalisée dans le département du Lot" is the aire;
        # a sentence naming one commune of that département is a DGC's zone
        # (Côtes du Lot Rocamadour), not the appellation's. A list the same
        # text carries for a whole département (a DGC's, an exclusion list)
        # stays on the record; the wiki shows the département whole.
        geo = {d: c for d, c in geo.items() if d not in whole}
    out = {
        "code_officiel_geographique_annee": cog_year,
        "aire_geographique": geo,
        "aire_proximite_immediate": by_dept(aire_prox_text) if aire_prox_text else {},
    }
    if whole:
        out["aire_departements"] = whole
    return out


def parse_appellation_header(segment: str) -> dict:
    """Pull JORF/decret/arrêté references from the cahier preamble."""
    head = segment[:1500]
    out: dict[str, str] = {}
    m = re.search(
        r"homologu[ée](?:e)?\s+pa(?:r)?\s+(?:le\s+|l['’]\s*)?(d[ée]cret|arr[êée]t[ée])\s*(?:n[°º]?\s*([\d\-/]+)\s+)?du\s+([^\n,]+?)\s*(?:,\s*(?:JORF|publi)|\.|\n)",
        head, re.IGNORECASE,
    )
    if m:
        out["homologation_type"] = m.group(1).lower()
        out["homologation_numero"] = m.group(2) or ""
        out["homologation_date"] = m.group(3).strip()
    m = re.search(r"JORF(?: n[°º]?\s*[\d]+)?\s+du\s+([^\n]+?)(?:\s+page|\s+texte|\.|\n)", head, re.IGNORECASE)
    if m:
        out["jorf_date"] = m.group(1).strip()
    m = re.search(r"modifi[ée](?:e)?\s+par\s+(?:l['’]?arr[êe]t[ée]|le d[ée]cret)\s+du\s+([^\n,]+?)(?:,|\.|\n)", head, re.IGNORECASE)
    if m:
        out["derniere_modification_date"] = m.group(1).strip()
    return out


def extract_one(name: str, text: str) -> dict | None:
    segments = split_bundle(text)
    segment = find_segment(segments, name) if segments else text
    if not segment:
        return None

    if is_spiritueux_template(segment):
        sections, section_titles = extract_spiritueux_sections(segment)
        if not sections:
            return None
        kind = "EDV"
        routed = route_spiritueux(sections, section_titles)
        aire = extract_aire(routed.get("aire", ""))
        lien = routed.get("lien", "")
        return {
            "name": name,
            "kind": kind,
            "header": parse_appellation_header(segment),
            "is_bundle_member": len(segments) > 1,
            "bundle_size": len(segments),
            "sections": sections,
            "section_titles": section_titles,
            "section_roles": routed,
            "aire": aire,
            "lien_au_terroir": lien,
        }

    if is_spiritueux_2026_template(segment):
        sections, section_titles = extract_spiritueux_2026_sections(segment)
        if sections:
            routed = route_by_keywords(sections, section_titles, SPIRITUEUX_2026_ROLE_KEYWORDS)
            if routed.get("encepagement"):
                routed["encepagement"] = matiere_premiere_block(routed["encepagement"])
            return {
                "name": name,
                "kind": "EDV",
                "header": parse_appellation_header(segment),
                "is_bundle_member": len(segments) > 1,
                "bundle_size": len(segments),
                "sections": sections,
                "section_titles": section_titles,
                "section_roles": routed,
                "aire": extract_aire(routed.get("aire", "")),
                "lien_au_terroir": routed.get("lien", ""),
            }

    sections, section_titles = extract_sections(segment)
    if len(sections) < 3:
        # Headings without numerals (the 2024 Saumur layout): accept the
        # unnumbered read only when it finds most of the template, so a
        # stray centred "Encépagement" line never passes for a cahier.
        un_sections, un_titles = extract_unnumbered_sections(segment)
        if len(un_sections) >= 6:
            sections, section_titles = un_sections, un_titles

    # EU documento-único letter-section template (Franco-Spanish / cross-
    # border AOPs). Gated on AOC Roman parser returning <3 sections — every
    # standard AOC cahier yields 10+ Roman sections, so this only fires for
    # cahiers that genuinely lack the XII-section template. Without the gate
    # the detector false-fires on AOC cahiers whose section X bodies start
    # bullet items "A. ...", "B. ...", "C. ...".
    if len(sections) < 3 and is_eu_letter_template(segment):
        eu_sections, eu_titles = extract_eu_letter_sections(segment)
        if eu_sections:
            routed = route_eu_letter(eu_sections, eu_titles)
            aire = extract_aire(routed.get("aire", ""))
            lien = routed.get("lien", "")
            return {
                "name": name,
                "kind": "AOP",
                "header": parse_appellation_header(segment),
                "is_bundle_member": len(segments) > 1,
                "bundle_size": len(segments),
                "sections": eu_sections,
                "section_titles": eu_titles,
                "section_roles": routed,
                "aire": aire,
                "lien_au_terroir": lien,
            }

    kind = "AOC"
    # Some IGP cahiers leak a single Roman "I" via a stray bullet inside the
    # CHAPITRE-1 heading; if the Arabic IGP layout looks more substantial,
    # prefer that. Heuristic: if Arabic returns >= 4 sections, switch.
    igp_sections, igp_titles = extract_igp_sections(segment)
    if len(igp_sections) >= 4 and len(sections) <= 2:
        sections = igp_sections
        section_titles = igp_titles
        kind = "IGP"
    elif not sections:
        sections = igp_sections
        section_titles = igp_titles
        kind = "IGP" if sections else "unknown"
    if not sections:
        return None

    if kind == "AOC":
        routed = route_sections(sections, section_titles)
        aire = extract_aire(routed.get("aire", ""))
        lien = routed.get("lien", "")
    else:
        # IGP layout: aire géographique is usually section 4. Pick the lien
        # by title-keyword match — section numbers vary (typically 7 or 8,
        # but Maures has section 8 for labelling and section 7 for the
        # lien), so positional fallback alone is fragile.
        lien_key = next(
            (k for k, t in igp_titles.items()
             if any(kw in t.lower() for kw in SECTION_ROLE_KEYWORDS["lien"])),
            None,
        )
        # Encépagement is usually section 5, but some templates fold it
        # into "4 – Encépagement et conduite de vignoble" (4.1 / 4.2 / 4.3
        # — Lavilledieu), where section 5 is the harvest. Route by title
        # keyword first; a sub-numbered hit resolves to its parent, whose
        # body carries the merged children.
        enc_key = next(
            (k for k, t in igp_titles.items()
             if any(kw in t.lower() for kw in SECTION_ROLE_KEYWORDS["encepagement"])),
            None,
        )
        if enc_key is not None and _is_subnumber(enc_key):
            enc_key = re.split(r"[.\-]", enc_key)[0]
        routed = {
            "aire": sections.get("4", ""),
            "couleur": sections.get("3", ""),
            "encepagement": sections.get(enc_key or "5", ""),
            "lien": sections.get(lien_key, "") if lien_key else next(
                (sections.get(k, "") for k in ("8", "7", "9") if sections.get(k)), "",
            ),
        }
        aire = extract_aire(routed["aire"])
        lien = routed["lien"]

    return {
        "name": name,
        "kind": kind,
        "header": parse_appellation_header(segment),
        "is_bundle_member": len(segments) > 1,
        "bundle_size": len(segments),
        "sections": sections,
        "section_titles": section_titles,
        "section_roles": routed,
        "aire": aire,
        "lien_au_terroir": lien,
    }


EMPTY_AIRE = {
    "code_officiel_geographique_annee": "",
    "aire_geographique": {},
    "aire_proximite_immediate": {},
}


def _stub_source(meta: dict | None) -> dict:
    m = meta or {}
    return {
        "filename": m.get("filename", ""),
        "pdf_sha256": m.get("sha256", ""),
        "boagri_url": m.get("boagri_url", ""),
        "boagri_url_candidates": m.get("boagri_url_candidates", []),
        "show_texte_url": m.get("show_texte_url", ""),
        "product_url": m.get("product_url", ""),
        "legifrance_jorftext_ids": m.get("legifrance_jorftext_ids", []),
        "fetched_at": m.get("fetched_at", ""),
        "rescued_from_pdf": "",
        "homologated_at": "",
        "latest_known_pdf": "",
        "latest_known_homologated_at": "",
    }


def _stub_common(name: str, id_app: str, id_denom: str, slug_str: str, meta: dict | None,
                 categories: list[str], stub_reason: str) -> dict:
    m = meta or {}
    return {
        "country": "fr",
        "name": name,
        "kind": "STUB",
        "header": "",
        "is_bundle_member": False,
        "bundle_size": 0,
        "sections": {},
        "section_titles": {},
        "section_roles": {},
        "aire": dict(EMPTY_AIRE),
        "lien_au_terroir": "",
        "id_appellation": id_app,
        "id_denomination_geo": id_denom,
        "slug": slug_str,
        "stub_reason": stub_reason,
        "source": _stub_source(meta),
        "signe_fr": m.get("signe_fr", ""),
        "signe_ue": m.get("signe_ue", ""),
        "categorie": m.get("categorie", ""),
        "categories": categories,
        "comite_regional": m.get("comite_regional", ""),
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [],
    }


def _stub_index_entry(record: dict, parent_slug: str = "") -> dict:
    return {
        "country": "fr",
        "id_appellation": record["id_appellation"],
        "id_denomination_geo": record["id_denomination_geo"],
        "name": record["name"],
        "slug": record["slug"],
        "filename": f"{record['slug']}.json",
        "is_sub_denomination": bool(record.get("is_sub_denomination")),
        "parent_slug": parent_slug,
        "communes_count": 0,
        "sections_present": [],
        "grapes_count": 0,
        "styles": [],
        "categories": record["categories"],
        "stub_reason": record["stub_reason"],
    }


def _emit_parent_stub(id_app: str, parent_denom: dict, parent_slug: str,
                      meta: dict | None, categories: list[str], out_dir: Path) -> dict:
    name = parent_denom["appellation"]
    stub_reason = "no-pdf" if not meta else "no-extract"
    record = _stub_common(name, id_app, parent_denom["id_denomination_geo"],
                          parent_slug, meta, categories, stub_reason)
    record["is_sub_denomination"] = False
    (out_dir / f"{parent_slug}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def _emit_dgc_stub(id_app: str, parent_denom: dict, parent_slug: str, dgc: dict,
                   meta: dict | None, categories: list[str], out_dir: Path) -> dict:
    dgc_slug = slug(dgc["denomination"])
    stub_reason = "no-pdf" if not meta else "no-extract"
    record = _stub_common(dgc["denomination"], id_app, dgc["id_denomination_geo"],
                          dgc_slug, meta, categories, stub_reason)
    record["is_sub_denomination"] = True
    record["parent_id_appellation"] = id_app
    record["parent_id_denomination_geo"] = parent_denom["id_denomination_geo"]
    record["parent_slug"] = parent_slug
    record["parent_name"] = parent_denom["appellation"]
    (out_dir / f"{dgc_slug}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


_DGC_COLOURS = frozenset({"white", "red", "rose"})


def _apply_dgc_rules(dgc: dict, parent: dict, dgc_names: list[str]) -> None:
    """Give a DGC the colours and roster its parent's cahier states for it
    (`dgc_rules`): its own section III rule when one names it — else the
    parent's styles —, its own section V rows or clauses when they name it,
    else the parent's roster without the clauses of a colour the DGC is not
    allowed. A DGC its cahier never singles out keeps the parent's fields."""
    roles = parent.get("section_roles") or {}
    covered_dgc = set().union(*(dgc_rules.dgc_keys(n, parent["name"]) for n in dgc_names))
    covered = covered_dgc | {dgc_rules.key(a) for a in shared_cahier.aliases(parent["name"])}
    want = dgc_rules.dgc_keys(dgc["name"], parent["name"])
    own_iii = dgc_rules.dgc_text(roles.get("couleur") or "", want, covered,
                                 dgc_rules.RESERVATION)
    applied: dict[str, str] = {}
    if own_iii is not None:
        mention_text = " ".join(
            v for v in (parent.get("sections") or {}).values() if isinstance(v, str)
        )
        dgc["styles"] = parse_styles(own_iii, dgc["categories"], mention_text)
        applied["types"] = "own"
    v_text = encepagement_block(roles.get("encepagement") or "")
    cut = shared_cahier._PROPORTION.search(v_text, 1)
    if cut:
        v_text = v_text[: cut.start()]
    own_v = dgc_rules.dgc_text(v_text, want, covered)
    how = "own"
    colours = set(dgc["styles"]) & _DGC_COLOURS
    if own_v is None and colours and not (set(parent["styles"]) & _DGC_COLOURS) <= colours:
        own_v = dgc_rules.drop_colours(v_text, colours, covered_dgc)
        how = "colour"
    if own_v is not None:
        grapes = parse_grapes(dgc_rules.strip_names(own_v))
        if grapes["principal"]:
            dgc["grapes"] = {
                "principal": [t["slug"] for t in grapes["principal"]],
                "accessory": [t["slug"] for t in grapes["accessory"]],
                "observation": [t["slug"] for t in grapes["observation"]],
                "details": grapes["all"],
            }
            applied["encepagement"] = how
    if applied:
        dgc["dgc_rules"] = applied


def emit_stub_records(
    siqo_denoms: dict[str, list[dict]],
    siqo_categories: dict[str, list[str]],
    manifest: dict,
    index: dict,
    slug_map: dict[str, str],
    out_dir: Path,
) -> int:
    """Emit placeholder JSONs for SIQO denominations stage 02 couldn't
    extract from a cahier — either because stage 01 didn't resolve a PDF
    (`stub_reason="no-pdf"`) or because the resolved PDF didn't contain
    the cahier text (`stub_reason="no-extract"`). Stubs let stage 03
    render a "cahier non disponible" page so every appellation in SIQO
    is at least searchable.

    Stub records share the same schema as extracted ones (so stage 03's
    `_index.json` consumers don't need to special-case them), but their
    `kind == "STUB"`, `aire`/`grapes`/`styles` are empty, and
    `stub_reason` records why they're missing. Re-running stage 01 +
    stage 02 promotes a stub to a full record automatically.
    """
    written = 0
    extracted_app_ids = {entry.get("id_appellation") for entry in index.values()}
    for id_app, denoms in siqo_denoms.items():
        if not denoms:
            continue
        meta = manifest.get(id_app)
        parent_denom = next((d for d in denoms if _is_parent_denom(d)), None)
        if parent_denom is None:
            parent_denom = {
                "id_denomination_geo": "",
                "denomination": denoms[0]["appellation"],
                "appellation": denoms[0]["appellation"],
                "categories": [],
            }
        parent_slug = slug_map.get(id_app) or slug(parent_denom["appellation"])
        categories = siqo_categories.get(id_app, []) or denoms[0]["categories"]

        if id_app not in extracted_app_ids:
            record = _emit_parent_stub(
                id_app, parent_denom, parent_slug, meta, categories, out_dir
            )
            index[parent_denom["id_denomination_geo"] or f"app:{id_app}"] = (
                _stub_index_entry(record, parent_slug="")
            )
            written += 1

        for d in denoms:
            if d["id_denomination_geo"] == parent_denom["id_denomination_geo"]:
                continue
            if d["id_denomination_geo"] in index:
                continue
            dgc_categories = d["categories"] or categories
            record = _emit_dgc_stub(
                id_app, parent_denom, parent_slug, d, meta, dgc_categories, out_dir
            )
            index[d["id_denomination_geo"]] = _stub_index_entry(record, parent_slug)
            written += 1
    return written


# Each cahier carries its homologation date next to the title in one of
# three forms:
#   "homologué par le décret n°2011-1724 du 30 novembre 2011"
#   "homologué par l'arrêté du 30 novembre 2011"
#   "homologué par le décret n°2011-1724 du 30/11/2011"
# We extract that date so the cross-bundle rescue can pick the most
# recent cahier when the same AOC appears in multiple PDFs (an older
# JORF homologation + a later modification arrêté re-publishing the
# updated cahier). Stored as ISO YYYY-MM-DD; missing dates compare last.
_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
# "homologué par le décret n° … du …", "par l'arrêté du …", "par arrêté du …"
# (no article — 150 cahiers), "pa l'arrêté" (INAO's own typo, Montpeyroux
# 2026), "du 1er septembre".
_HOMOL_HEAD = (
    r"homologu[ée]e?\s+pa(?:r)?\s+(?:le\s+|l['’]\s*)?(?:d[ée]cret|arr[êe]t[ée])\s+"
    r"(?:n[°º]?\s*\S+\s+)?du\s+(\d{1,2})(?:er)?"
)
_HOMOL_LONG_RE = re.compile(
    _HOMOL_HEAD + r"\s+"
    r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|"
    r"septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})",
    re.IGNORECASE,
)
_HOMOL_NUMERIC_RE = re.compile(
    _HOMOL_HEAD + r"[\s/-](\d{1,2})[\s/-](\d{4})",
    re.IGNORECASE,
)


def homologation_date(segment: str, before: str = "") -> str | None:
    """Best-effort ISO YYYY-MM-DD for the homologation date stamped in a
    cahier segment. Returns None when no date can be parsed.

    `before` is the text that precedes the segment in its PDF: a BO Agri
    cover sheet or a JORF décret preamble stamps the date above the
    "Cahier des charges" title the bundle splitter cuts at, so a segment
    whose head carries no date is read together with the 600 characters
    before it (263 of 467 parents had no date before 2026-10-04)."""
    for head in (segment[:1500], before[-600:] + " " + segment[:300]):
        if not head.strip():
            continue
        iso = _homologation_date_in(head)
        if iso:
            return iso
    return None


def _homologation_date_in(head: str) -> str | None:
    m = _HOMOL_LONG_RE.search(head)
    if m:
        day = int(m.group(1))
        month = _FR_MONTHS.get(m.group(2).lower().replace("é", "e").replace("û", "u"))
        year = int(m.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    m = _HOMOL_NUMERIC_RE.search(head)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _text_before(text: str, segment: str) -> str:
    """The text that precedes `segment` inside `text` ("" when the segment
    is the text itself or cannot be located)."""
    if not segment or segment is text:
        return ""
    pos = text.find(segment[:400])
    return text[:pos] if pos > 0 else ""


def build_global_segment_index(
    cahiers_dir: Path,
) -> dict[str, tuple[str, str, str]]:
    """Scan every PDF in `cahiers_dir`, bundle-split it, and return a dict
    mapping normalised cahier name → (pdf_filename, segment_text, date_iso).

    INAO routinely lands an appellation on a "modification arrêté" PDF that
    doesn't actually carry the cahier we want — but a sibling AOC's PDF
    often does (BO Agri JORF issues bundle many cahiers). One pass over
    the corpus lets us rescue those cases by matching the cahier header
    name across PDFs. Scanning the directory (not just the manifest)
    means PDFs that stage 01 fetched as fallback candidates also feed
    the rescue index.

    When the same cahier name appears in multiple PDFs (the same cahier
    text often gets re-published in subsequent modification arrêtés), we
    keep the entry with the latest homologation date — the most recent
    publication is authoritative. Entries with no parsable date sort
    earliest, so any dated entry beats them.
    """
    index: dict[str, tuple[str, str, str]] = {}
    for pdf_path in sorted(cahiers_dir.glob("*.pdf")):
        try:
            text = pdftotext(pdf_path)
        except subprocess.CalledProcessError:
            continue
        for header_name, segment in split_bundle(text).items():
            date_iso = homologation_date(segment, _text_before(text, segment)) or ""
            # Insert under every alias-split key so a parent named
            # "Cidre de Normandie ou Cidre normand" can rescue from a
            # segment header that only carries one of the aliases.
            for key in candidate_keys(header_name):
                existing = index.get(key)
                if existing is None or date_iso > existing[2]:
                    index[key] = (pdf_path.name, segment, date_iso)
    return index


def _disambiguate_slugs(items: list[tuple[str, dict]]) -> dict[str, str]:
    """Map id_appellation → unique slug for *parent* denominations.

    Multiple SIQO entries can share an appellation name — e.g. id=330 is
    the AOC eau-de-vie "Calvados" and id=888 is the IGP "Vin tranquille"
    "Calvados". Both naïvely slugify to `calvados`, so the second-written
    JSON would clobber the first. We pre-scan for base-slug collisions
    and disambiguate every member of a colliding set with a short
    categorie-derived suffix (`-spiritueux`, `-vin`, `-mousseux`),
    falling back to the SIQO id when categorie doesn't separate them.
    """
    base = {id_app: slug(meta["name"]) for id_app, meta in items}
    by_slug: dict[str, list[str]] = defaultdict(list)
    for id_app, s in base.items():
        by_slug[s].append(id_app)
    out: dict[str, str] = {}
    meta_by_id = dict(items)
    for s, ids in by_slug.items():
        if len(ids) == 1:
            out[ids[0]] = s
            continue
        used: set[str] = set()
        for id_app in ids:
            cat = (meta_by_id[id_app].get("categorie") or "").lower()
            if "eau-de-vie" in cat or "eaux-de-vie" in cat or "spiritueuse" in cat or "spiritueux" in cat:
                disc = "spiritueux"
            elif "mousseux" in cat or "effervescent" in cat:
                disc = "mousseux"
            elif "tranquille" in cat or cat.startswith("vin"):
                disc = "vin"
            elif "doux naturel" in cat or "vdn" in cat:
                disc = "vdn"
            else:
                disc = id_app
            candidate = f"{s}-{disc}"
            if candidate in used:
                candidate = f"{s}-{id_app}"
            used.add(candidate)
            out[id_app] = candidate
    return out


WINE_SIGNS = siqo.WINE_SIGNS


def load_siqo_denominations() -> dict[str, list[dict]]:
    """Group SIQO rows by id_appellation → [denominations].

    Each denomination is `{id_denomination_geo, denomination, appellation,
    categories: [..]}`. The same `id_denomination_geo` can appear several
    times (one row per produit); we collapse to one entry per
    id_denomination_geo and union the `categorie` values across rows.

    Filters: VITICOLE sector, AOC/AOP/IGP signs, état "Publié" — same
    filters stage 01 applied when building the cahier manifest.
    """
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    if not SIQO_CSV.exists():
        return {}
    for row in siqo.siqo_rows(SIQO_CSV):
        if not siqo.is_wine_row(row):
            continue
        id_app = row["id_appellation"].strip()
        id_denom = row["id_denomination_geo"].strip()
        if not id_denom:
            continue
        denom = row["denomination"].strip()
        app = row["appellation"].strip()
        cat = row["categorie"].strip()
        entry = out[id_app].setdefault(
            id_denom,
            {
                "id_denomination_geo": id_denom,
                "denomination": denom,
                "appellation": app,
                "categories": set(),
            },
        )
        if cat:
            entry["categories"].add(cat)
    # Flatten + sort: parent denomination (denomination == appellation) first,
    # then DGCs alphabetically. The parent ordering matters for slug
    # collision handling — when a DGC's denomination_slug happens to clash
    # with another row, we want the parent to keep the canonical slug.
    flat: dict[str, list[dict]] = {}
    for id_app, denoms in out.items():
        items: list[dict] = []
        for d in denoms.values():
            d["categories"] = sorted(d["categories"])
            items.append(d)
        items.sort(
            key=lambda d: (not _is_parent_denom(d), d["denomination"].lower())
        )
        flat[id_app] = items
    return flat


def load_siqo_categories() -> dict[str, list[str]]:
    """Map id_appellation → sorted list of distinct `categorie` values.

    Each appellation in the SIQO referentiel can carry several rows, one
    per (categorie, denomination_geo). The manifest collapses them to a
    single value, which loses information for AOCs that produce more than
    one wine type (Champagne: tranquille + mousseux, Maury: VDN +
    tranquille, etc.). We re-derive the full set here.
    """
    out: dict[str, set[str]] = defaultdict(set)
    if not SIQO_CSV.exists():
        return {}
    for row in siqo.siqo_rows(SIQO_CSV):
        id_app = (row.get("id_appellation") or "").strip()
        cat = (row.get("categorie") or "").strip()
        if id_app and cat:
            out[id_app].add(cat)
        if id_app:
            out[id_app].update(_produit_mention_categories(row.get("produit") or ""))
    return {k: sorted(v) for k, v in out.items()}


# The `categorie` column files some mention products under "Vin tranquille"
# while the product's own name carries the mention ("Alsace grand cru
# Kaefferkopf vendanges tardives Gewurztraminer", "Monbazillac sélection de
# grains nobles"), so the style was lost; the name is the regulator's word.
_PRODUIT_MENTION_CATEGORIES = (
    (re.compile(r"\bvendanges\s+tardives\b", re.IGNORECASE), "Vin de vendanges tardives"),
    (re.compile(r"\bs[ée]lection\s+de\s+grains\s+nobles\b", re.IGNORECASE),
     "Vin de sélection de grains nobles"),
)


def _produit_mention_categories(produit: str) -> set[str]:
    return {cat for rx, cat in _PRODUIT_MENTION_CATEGORIES if rx.search(produit)}


def dropped_denominations(
    prior_index: dict, manifest: dict, siqo_denoms: dict[str, list[dict]]
) -> list[dict]:
    """Records of the previous full run that this run would not emit at all.

    A full run rebuilds `cahier-extracted/` from the referentiel, so a
    denomination the SIQO export stopped listing vanishes from the corpus
    without anyone deciding so — INAO's export lags its own catalogue by
    months in both directions. The index keys follow the emission rule
    (`id_denomination_geo`, else `app:<id_appellation>`), so the universe of
    keys this run can produce is known before anything is deleted.
    """
    universe: set[str] = set()
    for id_app, denoms in siqo_denoms.items():
        universe.update(d["id_denomination_geo"] for d in denoms)
        if not any(_is_parent_denom(d) for d in denoms):
            universe.add(f"app:{id_app}")
    for id_app in manifest:
        if id_app not in siqo_denoms:
            universe.add(f"app:{id_app}")
    out = []
    for key, entry in prior_index.items():
        if key in universe:
            continue
        out.append({
            "key": key,
            "slug": entry.get("slug", ""),
            "name": entry.get("name", ""),
            "id_appellation": entry.get("id_appellation", ""),
        })
    return sorted(out, key=lambda d: d["name"].lower())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="appellation name substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--allow-drop", action="store_true",
        help="let a full run remove records the SIQO referentiel no longer lists "
             "(the default refuses: a record leaves the corpus by a cited decision, "
             "never because an export stopped listing it)",
    )
    args = ap.parse_args()

    if shutil.which("pdftotext") is None:
        print("error: pdftotext not on PATH (brew install poppler)", file=sys.stderr)
        return 1
    if shutil.which("tesseract") is None or shutil.which("pdftoppm") is None:
        print("warning: tesseract / pdftoppm missing — OCR fallback will fail "
              "on Type 1C-font cahiers (brew install tesseract poppler)", file=sys.stderr)

    if not MANIFEST_PATH.exists():
        print(f"error: {MANIFEST_PATH} missing — run scripts/01_scrape_cahiers.py first", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    siqo_categories = load_siqo_categories()
    siqo_denoms = load_siqo_denominations()
    # The manifest is a fetch cache: its `name` is the referentiel's at fetch
    # time. The record (name, slug) follows the referentiel as read through
    # `siqo.siqo_rows` — supplements and the name overrides included — so a
    # pin or a renamed row does not wait for a stage-01 re-run.
    siqo_names = {
        r["id_appellation"].strip(): r["appellation"].strip()
        for r in siqo.siqo_rows() if siqo.is_wine_row(r)
    }
    for id_app, meta in manifest.items():
        siqo_name = siqo_names.get(id_app)
        if siqo_name and siqo_name != meta.get("name"):
            print(
                f"[name] {id_app}: manifest {meta.get('name')!r} → referentiel {siqo_name!r}",
                file=sys.stderr,
            )
            meta["name"] = siqo_name
    # Include manifest entries with no filename too — they can still extract
    # via the cross-bundle rescue index when a sibling AOC's PDF carries
    # their cahier (e.g. Légifrance-canonical AOCs whose cookie expired
    # and whose cahier is in a BO Agri bundle on disk). The extraction loop
    # below special-cases empty filenames to skip the PDF read and jump
    # straight to rescue lookup.
    items = sorted(
        manifest.items(),
        key=lambda kv: kv[1]["name"].lower(),
    )
    if args.only:
        needles = [s.lower() for s in args.only]
        items = [(k, v) for k, v in items if any(n in v["name"].lower() for n in needles)]
    if args.limit:
        items = items[: args.limit]

    # Preheat the grape-entity vocabulary cache BEFORE the rmtree. The
    # vocab's canonical-by-vivc-id ranking reads cross-corpus extracted
    # slugs; wiping `cahier-extracted/` first would blank the FR
    # contribution and flip the canonical slug for FR-canonical
    # varieties (e.g. `aubun` would lose to `corvo` from PT/duriense
    # under VIVC's shared vivc_id 761).
    if not (args.only or args.limit):
        if INDEX_PATH.exists():
            prior_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            dropped = dropped_denominations(prior_index, manifest, siqo_denoms)
            for d in dropped:
                print(
                    f"[dropped] {d['name']} ({d['slug']}, id_appellation {d['id_appellation']}): "
                    f"no longer in the SIQO referentiel or the manifest",
                    file=sys.stderr,
                )
            if dropped and not args.allow_drop:
                print(
                    f"error: this run would remove {len(dropped)} record(s) listed above. A record "
                    f"is never removed because the SIQO export stopped listing it: keep it with a "
                    f"`retained` row in scripts/_lib/fr/siqo_supplements.json and record the public "
                    f"act in scripts/_lib/cancelled_gis.json or promoted_gis.json — or re-run with "
                    f"--allow-drop if the removal is the decision.",
                    file=sys.stderr,
                )
                return 2
        preheat_vocabulary()
        shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    extracted = no_segment = no_sections = errors = dgc_emitted = rescued = 0
    global_segments = build_global_segment_index(CAHIERS)

    # Pre-compute disambiguated slugs so name collisions (e.g. AOC spirit
    # "Calvados" vs IGP wine "Calvados") don't overwrite each other on
    # disk. Suffix colliding entries with a categorie-derived hint
    # (`-spiritueux`, `-vin`, `-mousseux`) so the resulting filenames
    # stay readable; fall back to the SIQO id when categorie doesn't
    # disambiguate.
    slug_map = _disambiguate_slugs(items)

    for id_app, meta in tqdm(items, desc="extract", leave=False):
        # Empty filename → no PDF assigned (Légifrance-canonical AOC whose
        # rendered PDF has been wiped, or stage 01 fell through to
        # legifrance-only). Try the cross-bundle rescue index directly.
        if not meta.get("filename"):
            text = ""
        else:
            pdf_path = CAHIERS / meta["filename"]
            if not pdf_path.exists():
                print(f"[skip] {meta['name']}: missing {pdf_path.name}", file=sys.stderr)
                errors += 1
                continue
            try:
                text = pdftotext(pdf_path)
            except subprocess.CalledProcessError as exc:
                print(f"[fail] {meta['name']}: pdftotext: {exc}", file=sys.stderr)
                errors += 1
                continue

        record = extract_one(meta["name"], text) if text else None
        rescue_pdf: str | None = None
        rescue_date: str = ""
        if record is None:
            rescue = next(
                (r for k in candidate_keys(meta["name"])
                 if (r := global_segments.get(k)) is not None),
                None,
            )
            if rescue and rescue[0] != meta.get("filename"):
                rescue_pdf, rescue_segment, rescue_date = rescue
                record = extract_one(meta["name"], rescue_segment)
                if record is not None:
                    print(
                        f"[rescue] {meta['name']} ({id_app}) "
                        f"-> segment from {rescue_pdf[:16]} "
                        f"({rescue_date or 'no-date'})",
                        file=sys.stderr,
                    )
                    rescued += 1
        if record is None:
            segments = split_bundle(text)
            if not segments:
                print(f"[no-sections] {meta['name']} ({id_app})", file=sys.stderr)
                no_sections += 1
            else:
                print(
                    f"[no-segment] {meta['name']} ({id_app}) not in bundle of "
                    f"{len(segments)}: {sorted(segments)[:3]}...",
                    file=sys.stderr,
                )
                no_segment += 1
            continue

        record["country"] = "fr"
        record["id_appellation"] = id_app
        record["slug"] = slug_map[id_app]
        set_pliego_context(record["slug"])
        source_filename = rescue_pdf or meta["filename"]
        source_sha = (
            rescue_pdf.removesuffix(".pdf") if rescue_pdf else meta["sha256"]
        )
        # Date the cahier we ended up using. Rescue path already carries
        # the homologation date from build_global_segment_index; for the
        # assigned-PDF path we re-split and parse the segment we used.
        # Stored as ISO YYYY-MM-DD; downstream consumers (wiki/map) can
        # surface it as "Cahier homologué le …" and use it to detect
        # when a newer publication exists for the same AOC.
        if rescue_pdf:
            homologated_at = rescue_date
        else:
            seg_for_date = find_segment(split_bundle(text), meta["name"]) or text
            homologated_at = homologation_date(seg_for_date, _text_before(text, seg_for_date)) or ""
        latest_known = next(
            (r for k in candidate_keys(meta["name"])
             if (r := global_segments.get(k)) is not None),
            None,
        )
        latest_pdf = latest_known[0] if latest_known else ""
        latest_date = latest_known[2] if latest_known else ""
        record["source"] = {
            "filename": source_filename,
            "pdf_sha256": source_sha,
            "boagri_url": meta["boagri_url"],
            "show_texte_url": meta["show_texte_url"],
            "product_url": meta["product_url"],
            "fetched_at": meta["fetched_at"],
            "rescued_from_pdf": rescue_pdf or "",
            "homologated_at": homologated_at,
            "latest_known_pdf": latest_pdf,
            "latest_known_homologated_at": latest_date,
        }
        # Only present when stage 01's register tier won the resolution, so a
        # BO Agri-sourced record keeps a byte-identical `source` block.
        if meta.get("source_kind"):
            record["source"]["source_kind"] = meta["source_kind"]
            for key in (
                "register_file_number",
                "register_attachment_uri",
                "register_attachment_url",
                "register_attachment_name",
                "register_protected_name",
            ):
                record["source"][key] = meta.get(key, "")
        record["signe_fr"] = meta.get("signe_fr", "")
        record["signe_ue"] = meta.get("signe_ue", "")
        record["categorie"] = meta.get("categorie", "")
        record["categories"] = siqo_categories.get(id_app, [])
        record["comite_regional"] = meta.get("comite_regional", "")

        # Pull encépagement + couleur from the routed section map (handles
        # both the old template — V/III — and the post-2020 template where
        # encépagement is IV and couleur is II). Spiritueux/eaux-de-vie
        # cahiers (kind=EDV) don't carry an encépagement section, and their
        # "Description de la boisson" doesn't yield wine-style colours, so
        # we skip both parsers and emit empty results.
        roles = record.get("section_roles") or {}
        if record["kind"] == "EDV" and not (
            roles.get("encepagement") and is_grape_spirit(record["categorie"])
        ):
            record["grapes"] = {"principal": [], "accessory": [], "observation": [], "details": []}
            record["styles"] = []
        elif record["kind"] == "EDV":
            # a 2026-template marc / eau-de-vie de vin names its grape in the
            # matière première block; no wine style follows from a spirit
            grapes = parse_grapes(roles["encepagement"])
            record["grapes"] = {
                "principal": [t["slug"] for t in grapes["principal"]],
                "accessory": [t["slug"] for t in grapes["accessory"]],
                "observation": [t["slug"] for t in grapes["observation"]],
                "details": grapes["all"],
            }
            record["styles"] = []
        else:
            # A cahier shared by several appellations (the 51 Alsace grands
            # crus, Anjou / Cabernet d'Anjou / Rosé d'Anjou, the two Pouilly)
            # singles appellations out in sections III and V; read only the
            # clauses that apply to this record (no-op for any other cahier).
            covered = shared_cahier.covered_names(
                roles.get("nom") or (record.get("sections") or {}).get("I", "")
            )
            iii_text = shared_cahier.own_text(roles.get("couleur") or "", meta["name"], covered)
            mention_text = " ".join(
                v for v in (record.get("sections") or {}).values() if isinstance(v, str)
            )
            record["styles"] = parse_styles(iii_text, record["categories"], mention_text)
            v_text = shared_cahier.own_encepagement(
                encepagement_block(roles.get("encepagement") or ""),
                meta["name"], covered, record["styles"],
            )
            grapes = parse_grapes(v_text)
            record["grapes"] = {
                "principal": [t["slug"] for t in grapes["principal"]],
                "accessory": [t["slug"] for t in grapes["accessory"]],
                "observation": [t["slug"] for t in grapes["observation"]],
                "details": grapes["all"],
            }

        # The parent record is everything we just built. Find its SIQO row to
        # carry id_denomination_geo through, then emit one JSON per
        # denomination (parent + DGCs). Parent denomination = the SIQO row
        # whose `denomination == appellation`. DGCs reuse parent sections /
        # aire / grapes / styles — the cahier text is shared, and parsing
        # DGC-specific sub-sections is out of scope for v1.
        denoms = siqo_denoms.get(id_app, [])
        parent_denom = next((d for d in denoms if _is_parent_denom(d)), None)
        # When no SIQO row matches the appellation at all (e.g. Fiefs
        # Vendéens — all 5 denominations are DGCs) we leave parent_denom
        # = None. The parent record still gets emitted with meta["name"]
        # and the index falls back to id_appellation as the key.
        if parent_denom is not None:
            record["id_denomination_geo"] = parent_denom["id_denomination_geo"]

        out_path = OUT_DIR / f"{record['slug']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        # When the appellation has no parent denomination row in SIQO
        # (e.g. Fiefs Vendéens — all rows are DGCs), index by a synthetic
        # "app:<id>" key. Plain `id_app` would collide with the
        # `id_denomination_geo` namespace (the two ID spaces overlap — e.g.
        # id_denom="1028" exists as a Pommard DGC, same numeric value as
        # Fiefs Vendéens's id_app=1028).
        parent_key = record.get("id_denomination_geo") or f"app:{id_app}"
        index[parent_key] = {
            "country": "fr",
            "id_appellation": id_app,
            "id_denomination_geo": record.get("id_denomination_geo") or "",
            "name": meta["name"],
            "slug": record["slug"],
            "filename": out_path.name,
            "is_sub_denomination": False,
            "parent_slug": "",
            "communes_count": sum(len(v) for v in record["aire"]["aire_geographique"].values()),
            "sections_present": sorted(record["sections"]),
            "grapes_count": len(record["grapes"]["details"]),
            "styles": record["styles"],
            "categories": record["categories"],
        }
        extracted += 1

        # DGCs of this appellation: emit one JSON per id_denomination_geo
        # whose denomination differs from the appellation name. They share
        # the parent's cahier source, sections, aire, grapes, and styles —
        # but each gets its own slug, name, and parent_* link so the wiki
        # and map can render them independently. SIQO sometimes attaches a
        # narrower categorie set to a DGC (e.g. some Côtes du Rhône Villages
        # entries are tranquille-only); we use the DGC-level categorie list
        # when it's a strict subset, else fall back to the parent's.
        parent_id_denom = (
            parent_denom["id_denomination_geo"] if parent_denom else None
        )
        dgc_names = [
            d["denomination"] for d in denoms
            if not (parent_id_denom and d["id_denomination_geo"] == parent_id_denom)
        ]
        for d in denoms:
            if parent_id_denom and d["id_denomination_geo"] == parent_id_denom:
                continue
            dgc_slug = slug(d["denomination"])
            dgc_name = d["denomination"]
            dgc_record = json.loads(json.dumps(record))  # deep copy
            dgc_record["name"] = dgc_name
            dgc_record["slug"] = dgc_slug
            dgc_record["id_denomination_geo"] = d["id_denomination_geo"]
            dgc_record["is_sub_denomination"] = True
            dgc_record["parent_id_appellation"] = id_app
            dgc_record["parent_id_denomination_geo"] = (
                parent_denom["id_denomination_geo"] if parent_denom else ""
            )
            dgc_record["parent_slug"] = record["slug"]
            dgc_record["parent_name"] = record["name"]
            dgc_categories = d["categories"] or record["categories"]
            dgc_record["categories"] = dgc_categories
            if record["kind"] != "EDV":
                _apply_dgc_rules(dgc_record, record, dgc_names)

            dgc_path = OUT_DIR / f"{dgc_slug}.json"
            dgc_path.write_text(json.dumps(dgc_record, ensure_ascii=False, indent=2), encoding="utf-8")
            index[d["id_denomination_geo"]] = {
                "country": "fr",
                "id_appellation": id_app,
                "id_denomination_geo": d["id_denomination_geo"],
                "name": dgc_name,
                "slug": dgc_slug,
                "filename": dgc_path.name,
                "is_sub_denomination": True,
                "parent_slug": record["slug"],
                "communes_count": sum(len(v) for v in dgc_record["aire"]["aire_geographique"].values()),
                "sections_present": sorted(dgc_record["sections"]),
                "grapes_count": len(dgc_record["grapes"]["details"]),
                "styles": dgc_record["styles"],
                "categories": dgc_categories,
            }
            dgc_emitted += 1

    set_pliego_context(None)
    if args.only or args.limit:
        # A partial run must leave every unselected record untouched. The
        # stub pass walks the whole SIQO referentiel and would rewrite
        # every record outside the selection as `no-extract` (it once
        # stubbed 1,131 records on a 61-name `--only` run), and the index
        # would shrink to the selection — so skip the stub pass and merge
        # the fresh entries into the index on disk instead.
        stubs = 0
        if INDEX_PATH.exists():
            merged = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            merged.update(index)
            index = merged
    else:
        stubs = emit_stub_records(
            siqo_denoms, siqo_categories, manifest, index, slug_map, OUT_DIR
        )

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    unknowns_path = ROOT / "raw" / "inao" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"review at {unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )
    print(
        f"[done] extracted={extracted} dgcs={dgc_emitted} rescued={rescued} "
        f"stubs={stubs} no-segment={no_segment} no-sections={no_sections} "
        f"errors={errors}",
        file=sys.stderr,
    )
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
