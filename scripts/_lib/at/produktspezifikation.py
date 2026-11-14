"""BML Produktspezifikation parser (Austria, stage 02f).

The EU Einziges Dokument of an Austrian wine names only the main varieties
(§ 7 "Wichtigste Keltertraubensorten": Wachau's Grüner Veltliner and
Riesling). The national specification the Bundesministerium für Land- und
Forstwirtschaft (BML) files under Art. 94 Reg. (EU) 1308/2013 — one PDF per
designation, all linked from one BML page — is the fuller statement: its
section f) names the "Hauptsorten" and lists the whole authorised roster
(Wachau: 17 Gebietswein, 9 Ortswein, 2 Riedenwein varieties; the
Bundesland-wide designations the national 36-variety roster). The same
lettered a)–i) template everywhere:

  a) Zu schützender Name                    f) Angabe der Keltertraubensorte(n)
  b) Beschreibung der … Eigenschaften       g) Angaben über Güte und Eigenschaften
  c) Spezifische önologische Verfahren         (the terroir link; three sub-blocks)
  d) Abgrenzung des … geografischen Gebiets h) Geltende Anforderungen
  e) Höchstertrag je Hektar                 i) Name und Anschrift der Behörden

The letters are not reliable anchors: `pdftotext -layout` glued Kärnten's
"g)" title to the end of the roster ("Rotburger).Angaben über Güte …"), and
the 2025 template (Kamptal, Wagram, Thermenregion, Eisenberg) prints the
terroir title without a letter. Sections are therefore found by their
title's opening words, a letter accepted where printed; a title wraps over
up to six lines and ends with a colon.

Section f) shapes (every one of the 31 PDFs of 2026-11-08 is one of these):
  - the national roster in two numbered colour blocks ("1. Weißweinrebsorten:
    … 2. Rotweinrebsorten: …", names with their synonyms in brackets), with
    or without a closing "Die Hauptsorten des Weinbaugebiets X sind …"
    sentence — the Bundesland PDOs and the three Landwein PGIs;
  - a DAC rule: "Die Hauptsorten der Wachau sind Grüner Veltliner und
    Riesling." then the Gebietswein / Ortswein / Riedenwein lists in „quotes“;
  - an exclusive prose list: "ausschließlich die Qualitätsweinrebsorten Grüner
    Veltliner, Riesling, Chardonnay, Weißer Burgunder und Grauer Burgunder"
    (Kamptal), "dürfen folgende Rebsorten verwendet werden: …" (Südsteiermark);
  - one or two varieties: "ausschließlich die Qualitätswein-Rebsorte
    Blaufränkisch" (Mittelburgenland), "Blaufränkisch oder Zweigelt" (Rosalia);
  - an open reference and nothing else: "Alle weißen Qualitätsweinrebsorten"
    (Ruster Ausbruch).

Names are read by a longest-first window over the words of each segment
(separators: punctuation, quotes, the conjunctions) through the lexicon's
exact matcher — never the fuzzy one, so a prose noun cannot drift onto a
cultivar. Bracket contents are the regulator's synonyms of the name before
the bracket and are dropped ("Chardonnay (Morillon)"). Two Austrian readings
are pinned: a bare "Morillon" is Chardonnay (the Rebsortenverordnung's
synonym; the lexicon's unpinned surface is the French Pinot noir synonym),
and the bare family words "Burgunder" / "Veltliner" never bind (VIVC files
BURGUNDER under Blaufränkisch). "Gemischter Satz" is a field blend, not a
variety. Verified against the 31 PDFs on 2026-11-08 (tests/test_at_produktspezifikation.py).
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

from _lib.at.einziges_dokument import COLOUR_BY_KEYWORD
from _lib.grape_entity import exact_match

PARSER_TEMPLATE = "bml-produktspezifikation-v1"
SOURCE_ORG = "BML"
LICENSE = (
    "Amtliches Werk — § 7 UrhG (Österreich): a product specification filed by the "
    "Bundesministerium für Land- und Forstwirtschaft under Art. 94 Reg. (EU) 1308/2013 "
    "and published on bmluk.gv.at; reuse with attribution to the BML."
)

# (key, regex of the title's opening words). The order is the template's.
SECTION_TITLES: tuple[tuple[str, str], ...] = (
    ("name", r"Zu schützender Name"),
    ("description", r"Beschreibung der wichtigsten analytischen"),
    ("practices", r"Spezifische önologische Verfahren"),
    ("geo_area", r"Abgrenzung des betreffenden geografischen Gebiets"),
    ("yield", r"Höchstertrag je Hektar"),
    ("grapes", r"Angabe der Keltertraubensorten?\b"),
    ("link", r"Angaben über Güte und Eigenschaften"),
    ("requirements", r"Geltende Anforderungen"),
    ("authorities", r"Name und (?:die )?Anschrift der Behörden"),
)
_TITLE_ALTERNATION = "|".join(f"(?P<{k}>{rx})" for k, rx in SECTION_TITLES)
_HEADER_RE = re.compile(rf"^\s*(?:(?P<letter>[a-i])\)\s+)?(?:{_TITLE_ALTERNATION})")
# A title glued to the previous sentence ("Rotburger).Angaben über Güte …"): two
# word characters before the punctuation, so a lettered header "a) Zu …" is not cut.
_GLUED_TITLE_RE = re.compile(
    rf"([A-Za-zÄÖÜäöüß0-9]{{2}}[.)]\.?)\s*(?=(?:{'|'.join(rx for _, rx in SECTION_TITLES)}))"
)
_PAGE_FURNITURE_RE = re.compile(r"^\s*(?:\d{1,3}|Seite \d+ von \d+)\s*$")
_MAX_TITLE_LINES = 6

# "Hauptsorten" as "the main varieties are …" — never the field-blend name.
_HAUPTSORTEN_RE = re.compile(r"\bHauptsorten\b[^.:]*?\bsind\b(?P<names>[^.]+)\.", re.S)
_OPEN_ROSTER_RES = (
    re.compile(r"\b[Aa]lle(?:n)? (?:weißen |roten )?Qualitätsweinrebsorten\b"),
    re.compile(r"\bsämtliche Qualitäts(?:wein)?rebsorten\b"),
    re.compile(r"\bandere(?:n)? Qualitäts(?:wein)?rebsorten\b"),
    re.compile(r"\bautochthone(?:n)? Rebsorten\b"),
    re.compile(r"\b(?:einer oder mehreren )?roten Qualitätsrebsorten\b"),
)
_TIER_WORDS = (("gebietswein", "Gebietswein"), ("ortswein", "Ortswein"), ("riedenwein", "Riedenwein"))
_COLOUR_MARKER_RE = re.compile(
    r"(Weißweinrebsorten\s*:|Rotweinrebsorten\s*:|\bWeißwein muss\b|\bRotwein muss\b|"
    r"\bweißen (?:Qualitäts)?(?:wein)?rebsorten\b|\broten (?:Qualitäts)?(?:wein)?rebsorten\b)"
)
_SEGMENT_SPLIT_RE = re.compile(
    r"[,;:/„“”\"»«*–—]|\s+(?:und|oder|sowie|als|bei|aus|in|mit|für|der|die|das|den|des|dem|"
    r"ein|eine|einer|einem|zu|nach|von|ohne)\s+|\.(?! )"
)
_BRACKET_RE = re.compile(r"\([^)]*\)")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n\s*([a-zäöüß])")
# A footnote ("* Definition Schilcher …") runs from its asterisk to the next blank line.
_FOOTNOTE_RE = re.compile(r"^\s*\*\s.*?(?=\n\s*\n|\Z)", re.M | re.S)
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß][\w.\-]*")

# Austrian readings of a surface the lexicon resolves otherwise, or not at all.
SURFACE_PINS = {
    # Rebsortenverordnung / every BML roster: "Chardonnay (Morillon)"; the
    # Steiermark DACs list the variety as bare "Morillon".
    "morillon": "chardonnay",
}
# Family words the Austrian texts only ever write with a colour adjective; alone
# they are a VIVC synonym of something else (BURGUNDER → Blaufränkisch).
BARE_FAMILY_WORDS = {"burgunder", "veltliner"}
# Blends and categories a roster line names beside the varieties.
NOT_A_VARIETY = {"gemischter satz", "wiener gemischter satz", "burgundercuvée", "burgundercuvee"}
# The designations and Bundesländer the texts name around their varieties; VIVC
# keeps some as synonyms ("Steiermark" under Furmint). Never a variety here.
PLACE_WORDS = {
    "österreich", "burgenland", "kärnten", "niederösterreich", "oberösterreich", "salzburg",
    "steiermark", "tirol", "vorarlberg", "wien", "bergland", "weinland", "steirerland",
    "südsteiermark", "weststeiermark", "vulkanland steiermark", "vulkanland", "oststeiermark",
    "wachau", "kamptal", "kremstal", "traisental", "wagram", "weinviertel", "carnuntum",
    "thermenregion", "neusiedlersee", "leithaberg", "rosalia", "mittelburgenland", "eisenberg",
    "ruster ausbruch", "rust", "waldviertel", "donau",
}
# Words of the rule prose a capitalised one-to-three-word segment can consist of;
# only for the unknowns report (the matcher never binds them anyway).
_PROSE_WORDS = {
    "für", "die", "der", "das", "den", "des", "wird", "je", "alle", "bei", "wein", "weine",
    "weinen", "rotwein", "weißwein", "rebsorte", "rebsorten", "sorte", "sorten", "angabe",
    "gemeinde", "ried", "reserve", "kategorie", "bezeichnung", "ursprungsbezeichnung",
    "herkunftsbezeichnung", "verkehrsbezeichnung", "gewinnung", "landwein", "sturm",
    "spätlese", "auslese", "beerenauslese", "trockenbeerenauslese", "eiswein", "strohwein",
    "schilcher", "klassik", "hauptsorten", "leitsorten", "weinbauregion", "weinbaugebiet",
    "weinbaugebiets", "weinbaugemeinden", "wortverbindungen", "definition", "rosé", "rot",
    "qualitätswein", "gebietswein", "ortswein", "riedenwein", "cuvée", "cuvee", "verschnitt",
    "verschnitte", "qualitätsweinrebsorten", "qualitätsrebsorten", "keltertraubensorten",
}
NATIONAL_ROSTER_MIN = 20
# The wine-colour class of every Austrian quality-wine variety, as the Bundesland
# specifications print the national roster ("1. Weißweinrebsorten: … 2.
# Rotweinrebsorten: …" — Rebsortenverordnung); the colour of a name a DAC list
# gives in quotes without a block, where the lexicon has none.
ROSTER_COLOURS = {
    **{s: "blanc" for s in (
        "bouvier", "chardonnay", "velteliner-rouge-precoce", "furmint", "goldburger", "pinot-gris",
        "gruner-veltliner", "jubilaeumsrebe", "muller-thurgau", "muscat-a-petits-grains",
        "muscat-ottonel", "neuburger", "roter-veltliner", "rotgipfler", "sauvignon", "scheurebe",
        "sylvaner", "gewurztraminer", "pinot-blanc", "riesling", "welschriesling", "zierfandler",
    )},
    **{s: "noir" for s in (
        "blauburger", "pinot-noir", "blauer-portugieser", "blauer-wildbacher", "blaufrankisch",
        "cabernet-franc", "cabernet-sauvignon", "merlot", "rathay", "roesler", "sankt-laurent",
        "syrah", "zweigelt",
    )},
}


def slug_for_display(display: str) -> str:
    """The AT stage-00 slug of a designation name ("Kärnten" → "karnten")."""
    s = unicodedata.normalize("NFKD", display).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def pdf_to_text(pdf_path: Path) -> str:
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True,
    )
    return out.stdout.decode("utf-8", errors="replace")


def _clean_lines(text: str) -> list[str]:
    text = text.replace("\f", "\n")
    text = _GLUED_TITLE_RE.sub(r"\1\n", text)
    return [ln.rstrip() for ln in text.split("\n") if not _PAGE_FURNITURE_RE.match(ln)]


def slice_sections(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """{section key: body text} and {section key: letter printed} — the body
    starts after the title's last line (the one ending with a colon) and runs
    to the next title. A title met a second time (a sub-item restating it)
    is kept with the first body."""
    lines = _clean_lines(text)
    sections: dict[str, str] = {}
    letters: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    i = 0
    while i < len(lines):
        m = _HEADER_RE.match(lines[i])
        key = m.lastgroup if m else None
        if key == "letter":  # a letter alone matched nothing — not a header
            key = None
        if m and key and key not in sections and key != current:
            if current:
                sections[current] = "\n".join(body).strip("\n")
            current, body = key, []
            if m.group("letter"):
                letters[key] = m.group("letter")
            j = i
            while j < len(lines) and j - i < _MAX_TITLE_LINES and not lines[j].rstrip().endswith(":"):
                j += 1
            i = j + 1
            continue
        if current:
            body.append(lines[i])
        i += 1
    if current:
        sections[current] = "\n".join(body).strip("\n")
    return sections, letters


def join_hyphens(text: str) -> str:
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", join_hyphens(text)).strip()


def _paragraphs(text: str) -> list[str]:
    """Blank-line paragraphs, a paragraph cut by a page break (ending on a comma
    or mid-sentence — Wachau's Ortswein list) joined with the next."""
    out: list[str] = []
    for p in re.split(r"\n\s*\n", join_hyphens(text)):
        flat = _flat(p)
        if not flat:
            continue
        if out and out[-1][-1] not in ".:;!?":
            out[-1] = out[-1] + " " + flat
        else:
            out.append(flat)
    return out


def _segments(text: str) -> list[str]:
    text = _BRACKET_RE.sub(" ", text).replace("St. ", "St. ")
    return [s.replace(" ", " ") for s in _SEGMENT_SPLIT_RE.split(text) if s and s.strip()]


def resolve_variety(surface: str, ambient_colour: str | None = None):
    """The lexicon's exact match of a roster surface, with the Austrian pins;
    None for a blend name, a bare family word or a surface nothing vouches for."""
    key = surface.strip().strip(".").lower()
    if key in NOT_A_VARIETY or key in BARE_FAMILY_WORDS or key in PLACE_WORDS:
        return None
    if key in SURFACE_PINS:
        return exact_match(SURFACE_PINS[key], ambient_colour)
    return exact_match(surface, ambient_colour)


def scan_varieties(text: str, ambient_colour: str | None = None) -> tuple[list[dict], list[str]]:
    """Every variety a text names, in order of first mention, with the surface
    the text writes — a longest-first window of one to four words over each
    separator-bounded segment. Returns (matches, unmatched capitalised
    surfaces of a roster-looking segment)."""
    found: list[dict] = []
    seen: set[str] = set()
    labels = {m.group(1).strip().lower() for m in re.finditer(r"([A-ZÄÖÜ][\w\-. ]*?)\s*:", text)}
    segments = _segments(text)
    matched_flags: list[bool] = []
    candidates: list[str | None] = []
    for seg in segments:
        words = _WORD_RE.findall(seg)
        seg_matched = False
        i = 0
        while i < len(words):
            hit = None
            for n in (4, 3, 2, 1):
                if len(words[i:i + n]) < n:
                    continue
                span = " ".join(words[i:i + n])
                if not span[:1].isupper():
                    continue
                m = resolve_variety(span, ambient_colour)
                if m:
                    hit = (span, m, n)
                    break
            if hit:
                span, m, n = hit
                seg_matched = True
                if m.slug not in seen:
                    seen.add(m.slug)
                    found.append({"slug": m.slug, "name": span.strip("."),
                                  "colour": m.colour or ambient_colour or ROSTER_COLOURS.get(m.slug, "")})
                i += n
                continue
            i += 1
        matched_flags.append(seg_matched)
        # a short segment of capitalised words that bound nothing may be a roster
        # name the lexicon lacks (a typo, a new crossing): reported when it sits
        # beside a matched segment and is neither a label nor a word of the rule
        surface = " ".join(words).strip(".")
        is_candidate = (
            1 <= len(words) <= 3 and all(w[:1].isupper() for w in words) and not seg_matched
            and surface.lower() not in NOT_A_VARIETY and surface.lower() not in BARE_FAMILY_WORDS
            and surface.lower() not in PLACE_WORDS and surface.lower() not in labels
            and not any(w.lower() in _PROSE_WORDS for w in words)
        )
        candidates.append(surface if is_candidate else None)
    unmatched: list[str] = []
    for k, surface in enumerate(candidates):
        if surface is None:
            continue
        beside = (k > 0 and matched_flags[k - 1]) or (k + 1 < len(matched_flags) and matched_flags[k + 1])
        if beside and surface not in unmatched:
            unmatched.append(surface)
    return found, unmatched


def parse_grapes(body: str) -> dict:
    """Section f) read into: `roster` (every variety named, with the block
    colour as the fallback colour), `hauptsorten` (the "Hauptsorten … sind"
    sentence), `tiers` (the Gebietswein / Ortswein / Riedenwein lists where
    the text has them), `open_roster_clauses` (the references to every quality
    variety) and `roster_kind` — `national-roster` (the 36-variety Bundesland
    template, ≥ NATIONAL_ROSTER_MIN names), `exclusive-list` (a closed list
    of named varieties), `open` (no variety named, an open reference only)."""
    text = _FOOTNOTE_RE.sub("", join_hyphens(body))
    flat = _flat(text)
    roster: list[dict] = []
    seen: set[str] = set()
    unmatched: list[str] = []
    ambient: str | None = None
    for part in _COLOUR_MARKER_RE.split(flat):
        if _COLOUR_MARKER_RE.fullmatch(part):
            low = part.lower()
            ambient = "blanc" if "weiß" in low else "noir" if "rot" in low else ambient
            continue
        found, miss = scan_varieties(part, ambient)
        for f in found:
            if f["slug"] not in seen:
                seen.add(f["slug"])
                roster.append(f)
        unmatched.extend(m for m in miss if m not in unmatched)
    hauptsorten: list[str] = []
    hm = _HAUPTSORTEN_RE.search(flat)
    if hm:
        hauptsorten = [f["slug"] for f in scan_varieties(hm.group("names"))[0]]
    tiers: dict[str, list[str]] = {}
    for para in _paragraphs(text):
        for key, word in _TIER_WORDS:
            if word in para and key not in tiers:
                slugs = [f["slug"] for f in scan_varieties(para)[0]]
                if slugs:
                    tiers[key] = slugs
    if len(tiers) < 2:  # one tier word in a labelling sentence is no tier structure
        tiers = {}
    open_clauses: list[str] = []
    for rx in _OPEN_ROSTER_RES:
        for m in rx.finditer(flat):
            if m.group(0) not in open_clauses:
                open_clauses.append(m.group(0))
    if not roster:
        kind = "open" if open_clauses else "empty"
    elif len(roster) >= NATIONAL_ROSTER_MIN:
        kind = "national-roster"
    else:
        kind = "exclusive-list"
    return {
        "roster": roster,
        "hauptsorten": hauptsorten,
        "tiers": tiers,
        "open_roster_clauses": open_clauses,
        "roster_kind": kind,
        "unmatched": unmatched,
    }


_COLOUR_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(COLOUR_BY_KEYWORD, key=len, reverse=True)) + r")\b",
    re.I,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+")


def stated_colour_styles(*texts: str) -> dict[str, str]:
    """{colour slug: the first sentence that states it} — the wine colours the
    specification's own prose states with a wine word ("Rund 2/3 der
    Anbaufläche sind mit Weißwein bepflanzt, ein Drittel mit Rotwein", "Die
    Rotweine werden aus den Sorten …", "Rot- und Roséweine spielen eine sehr
    untergeordnete Rolle"), the EU reader's own colour table. Never a berry
    colour: the roster's "Rotweinrebsorten" block headers are not passed in."""
    out: dict[str, str] = {}
    for text in texts:
        for sent in _SENTENCE_SPLIT_RE.split(_flat(text or "")):
            for m in _COLOUR_WORD_RE.finditer(sent):
                out.setdefault(COLOUR_BY_KEYWORD[m.group(1).lower()], sent.strip())
    return out


def section_text(body: str) -> str:
    """A section body as prose: hyphenated line breaks closed, paragraphs kept."""
    return "\n\n".join(_paragraphs(body))


def extract(pdf_path: Path) -> dict:
    text = pdf_to_text(pdf_path)
    sections, letters = slice_sections(text)
    grapes = parse_grapes(sections.get("grapes", ""))
    description = section_text(sections.get("description", ""))
    link = section_text(sections.get("link", ""))
    return {
        "styles_stated": stated_colour_styles(description, link),
        "parser_template": PARSER_TEMPLATE,
        "name": _flat(sections.get("name", "")),
        "section_letters": letters,
        "sections_found": sorted(sections),
        "grapes": grapes,
        "zusammenhang_text": link,
        "geo_area_text": section_text(sections.get("geo_area", "")),
        "description_text": description,
    }
