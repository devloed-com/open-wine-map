"""Universal Swiss-règlement parser — FR / DE / IT family.

Switzerland has 26 cantons each publishing their own wine règlement;
the formats vary substantially (LexWork-PDFs, hand-rolled cantonal
HTML, ASIT-style WordPress dumps). Rather than write 26 per-canton
parsers, we use a keyword-driven approach that works across families:

1. Convert PDF / HTML → plaintext.
2. Locate the variety-list section by language-specific keywords
   ("Cépages admis" / "Zugelassene Rebsorten" / "Vitigni ammessi"
   plus 6 sibling variants per language).
3. Locate the production-area section by language-specific keywords
   ("Aire de production" / "Produktionsgebiet" / "Zona di produzione"
   plus variants).
4. Run the shared grape lexicon (`_lib.grape_entity.match_variety`)
   over the variety-list section text to extract slug-resolved varieties.
5. Run the swissBOUNDARIES3D BFS-name index over the production-area
   section text to extract commune candidates.

For 26 cantons, this is a 80/20 strategy — covers the bulk of the
content. Per-AOC carving (VD's article-by-article split, GE's premier-
cru annex) is deferred to Phase 2; v1 attaches the canton-wide
variety + commune lists to every AOC of that canton.
"""

from __future__ import annotations

import html as html_lib
import re
import subprocess
from pathlib import Path

# Scanning a whole règlement (≈50 KB of regulatory prose) with the
# shared grape lexicon is noise-prone in two ways, both observed in the
# CH corpus:
#   1. Weak fuzzy hits — common words / place fragments matched to
#      obscure non-Swiss grape slugs (vigne→viognier, "Nein"→durif,
#      blanc→alicante-branco). token_sort_ratio in the 85-94 band is
#      almost never a real variety in prose. Require fuzzy ≥ this floor.
_CH_FUZZY_FLOOR = 95
#   2. A handful of French/German prose words that are EXACT grape
#      aliases out of context (the word "canton"→chenin, "Dame"→folle-
#      blanche, "Menu"→orbois, "aucun"→altesse, "Roussillon"→alicante-
#      bouschet). These survive the fuzzy floor, so drop them by surface.
#      Normalised (lowercase, diacritic-stripped) forms.
_CH_STOP_SURFACES = frozenset({
    "canton", "dame", "menu", "aucun", "roussillon",
    "saure",          # German "Säure" (acid) → calitor
    "ferneyvoltaire",  # French town near Geneva → sacy (hyphen-split)
    "weisse", "weiss", "rote", "roten",  # German colour headers → obscure grapes
})

# Section-keyword tables — earliest match wins; ordering is most-
# specific first. The keyword body is matched case-insensitively
# against the plain-text lines.
SECTION_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": {
        "varieties": (
            "cépages admis",
            "cépages autorisés",
            "encépagement",
            "liste des cépages",
            "variétés admises",
            "variétés autorisées",
        ),
        "area": (
            "aire de production",
            "aire géographique",
            "aire délimitée",
            "zone de production",
            "zone géographique",
            "délimitation de l'aire",
            "périmètre",
        ),
    },
    "de": {
        "varieties": (
            "zugelassene rebsorten",
            "zulässige rebsorten",
            "zugelassene traubensorten",
            "rebsorten",
            "traubensorten",
            "weinsorten",
            "weinhefen",
            "rebsortenverzeichnis",
        ),
        "area": (
            "produktionsgebiet",
            "produktionsgebiete",
            "produktionszone",
            "abgrenzung",
            "rebbaugebiet",
            "rebbaugebiete",
            "weinbaugebiet",
            "geografisches gebiet",
        ),
    },
    "it": {
        "varieties": (
            "vitigni ammessi",
            "vitigni autorizzati",
            "varietà ammesse",
            "varietà autorizzate",
            "elenco dei vitigni",
            "ampelografia",
        ),
        "area": (
            "zona di produzione",
            "area di produzione",
            "zona delimitata",
            "delimitazione della zona",
            "perimetro",
            "area geografica",
        ),
    },
}


def pdf_to_text(path: Path) -> str:
    """Run pdftotext -layout and return UTF-8 plaintext."""
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, timeout=180, check=False,
        )
        return out.stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def html_to_text(path: Path) -> str:
    """Strip tags from an HTML file with windows-1252 / latin-1 / utf-8
    auto-detection via the meta charset declaration."""
    raw = path.read_bytes()
    # Cheap encoding sniff — pick the first one that produces a meta
    # charset, defaulting to utf-8.
    encoding = "utf-8"
    m = re.search(rb'charset\s*=\s*["\']?([\w-]+)', raw[:2048], re.I)
    if m:
        encoding = m.group(1).decode("ascii", errors="replace").lower()
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    # Normalise line breaks for block-level tags.
    text = re.sub(r"<(?:/p|/tr|/li|/td|/th|/h[1-6]|br\s*/?)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_plaintext(path: Path) -> str:
    """Dispatch by extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_to_text(path)
    if suffix in {".html", ".htm"}:
        return html_to_text(path)
    # Plaintext fallback.
    return path.read_text(encoding="utf-8", errors="replace")


def find_section(text: str, keywords: tuple[str, ...]) -> tuple[int, int] | None:
    """Locate a section by case-insensitive keyword match. Returns the
    (start, end) char offsets of the section body (header line up to the
    next ALL-CAPS heading / numbered article / end of document) or None.

    `end` is a heuristic — the next line that looks like a chapter/
    article heading (matching `^(Art\\.|Chapitre|Section|Titre|Anhang|
    Allegato|Annexe)\\s+\\w`) or end of document, whichever comes first.
    """
    low = text.lower()
    pos = -1
    for kw in keywords:
        p = low.find(kw)
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        return None
    # Walk forward to the end of the section.
    next_heading_re = re.compile(
        r"\n\s*(?:art(?:icle|\.|icolo)?\s+\d+|chapitre\s+\w+|section\s+\w+|"
        r"titre\s+\w+|kapitel\s+\w+|abschnitt\s+\w+|teil\s+\w+|"
        r"annexe(?:\s+\w+)?|anhang|allegato|capitolo)\b",
        re.I,
    )
    m = next_heading_re.search(text, pos + 1)
    end = m.start() if m else len(text)
    # Cap section body to a sane length to avoid bleeding into many
    # subsequent articles when the keyword appears in a Table of Contents.
    end = min(end, pos + 6000)
    return (pos, end)


def extract_section_body(text: str, lang: str, kind: str) -> str:
    """Return the plaintext of the variety / area section for the
    given language and kind ("varieties" or "area"), or "" if not
    located."""
    kws = SECTION_KEYWORDS.get(lang, {}).get(kind, ())
    if not kws:
        return ""
    span = find_section(text, kws)
    if span is None:
        return ""
    return text[span[0]:span[1]]


def _surface_norm(s: str) -> str:
    """Lowercase + diacritic-strip + keep letters only — for matching a
    candidate chunk against `_CH_STOP_SURFACES`."""
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in decomposed if c.isalpha() and not unicodedata.combining(c))


def extract_varieties(text: str, lang: str, match_fn, commune_index=None) -> list[dict]:
    """Run `match_fn` (the shared `_lib.grape_entity.match_variety`)
    over candidate variety-name tokens in the variety section. Returns
    `[{slug, name, colour}]` deduplicated by slug.

    `match_fn(name)` returns a `MatchResult` with `.slug`, `.colour`
    and `.method`, or `None`.

    Token candidates: lines stripped of leading list markers
    (digits / dots / dashes / parentheses). The match function does
    its own normalisation.

    `commune_index` (a `CHCommuneIndex`, optional) is the place-name
    guard: a chunk that is itself a Swiss commune is area-of-application
    prose (Genève, Sion, Cortaillod, …), not a grape, and is skipped."""
    # The lexicon is robust at matching grape names, but a whole-document
    # scan also feeds it thousands of prose words, so we guard against the
    # two false-positive modes a règlement produces (see the module-level
    # _CH_FUZZY_FLOOR / _CH_STOP_SURFACES notes). The whole-document scan
    # is still the recall strategy — cantonal règlements frequently bury
    # the variety list in an annex or refer to it by article.
    section = text
    candidates: set[str] = set()

    def _add(chunk: str) -> None:
        # Strip a leading FR/IT/DE determiner ("il Merlot", "la Bondola",
        # "le Gamay", "der Riesling") and trailing footnote / cross-
        # reference tails ("Cabernet Franc (2", "Sauvignon blanc *") so
        # the bare name matches EXACT instead of being knocked below the
        # fuzzy floor.
        chunk = re.sub(r"^(?:il|lo|gli|la|le|i|l'|der|die|das|den|du|des|de|d')\s+",
                       "", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"\s*\(.*$", "", chunk)
        chunk = re.sub(r"[*†‡]+\s*$", "", chunk)
        chunk = chunk.strip(" .;:)(")
        if 2 <= len(chunk) <= 60 and re.search(r"[A-Za-zÀ-ÿ]", chunk):
            candidates.add(chunk)
        # Must-weight lines name the variety before its threshold
        # ("Blauburgunder 19,4 °Brix", "Pinot noir 17,2 °Oe") — add the
        # name-before-first-number as a candidate too. The matcher + all
        # guards still gate it, so this only recovers real varieties.
        head = re.split(r"\s+\d", chunk, maxsplit=1)[0].strip(" .;:)(")
        if head != chunk and 2 <= len(head) <= 60 and re.search(r"[A-Za-zÀ-ÿ]", head):
            candidates.add(head)

    for raw_line in section.splitlines():
        line = re.sub(r"^[\s\d.,()/\-•·*°ºª§]+", "", raw_line).strip()
        # Drop a leading single-letter ordinal marker ("a)", "b)") that
        # the numeric-marker strip above doesn't cover.
        line = re.sub(r"^[a-zA-Z]\)\s*", "", line).strip()
        if not line:
            continue
        # Split on slashes (synonyms), commas, and the FR/IT/DE list
        # conjunctions ("il Merlot e il Petit Verdot", "X et Y") that
        # join multiple variety mentions on one line.
        for chunk in re.split(r"\s*/\s*|,\s+|\s+(?:e|et|und|oder|ou|y)\s+", line):
            _add(chunk)

    resolved: list[dict] = []
    seen_slugs: set[str] = set()
    for cand in sorted(candidates):
        # Place-name guard: a Swiss commune is not a grape.
        if commune_index is not None and commune_index.lookup(cand):
            continue
        # Prose-word collisions that are exact grape aliases out of context.
        if _surface_norm(cand) in _CH_STOP_SURFACES:
            continue
        match = match_fn(cand)
        if match is None:
            continue
        # Whole-document prose scan can't trust weak fuzzy hits.
        if match.method.startswith("fuzzy:"):
            try:
                score = int(match.method.split(":", 1)[1])
            except ValueError:
                score = 0
            if score < _CH_FUZZY_FLOOR:
                continue
        if match.slug in seen_slugs:
            continue
        seen_slugs.add(match.slug)
        resolved.append({
            "slug": match.slug,
            "name": cand,
            "colour": match.colour or "",
            "role": "principal",
        })
    return resolved


def extract_communes(text: str, lang: str, commune_index) -> list[dict]:
    """Scan the area section for commune-name matches against the
    swissBOUNDARIES3D commune index. Returns `[{bfs_id, name, canton}]`
    deduplicated by bfs_id.

    `commune_index` is a `CHCommuneIndex` instance with `.lookup(name)`
    returning a list of `{"bfs_id", "name", "canton"}` candidates."""
    section = extract_section_body(text, lang, "area")
    if len(section) < 200:
        section = text
    out: list[dict] = []
    seen: set[int] = set()
    # Iterate commune-name candidates from the section. We use the
    # commune index's own scan to avoid pulling every word.
    for hit in commune_index.scan_text(section):
        if hit["bfs_id"] in seen:
            continue
        seen.add(hit["bfs_id"])
        out.append(hit)
    return out


def summary_paragraph(text: str, *, max_chars: int = 800) -> str:
    """Return the first non-trivial paragraph of the règlement, used
    as a placeholder summary. Heuristics: skip preamble headers
    ('vu …', 'gestützt auf …'), pick the first paragraph > 80 chars."""
    paras = re.split(r"\n\s*\n", text)
    for p in paras:
        line = re.sub(r"\s+", " ", p).strip()
        if len(line) < 80:
            continue
        # Skip preamble citations.
        if line.lower().startswith(("vu ", "vu l", "gestützt auf",
                                    "visto", "il ", "le conseil",
                                    "der grosse rat", "der landrat")):
            continue
        return line[:max_chars]
    return ""
