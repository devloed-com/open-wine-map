"""Match Italian wine eAmbrosia slugs to MASAF disciplinare PDFs and
parse the canonical structure.

MASAF publishes 4 7z archives at the root MASAF disciplinari page
(IDPagina/4625 on www.masaf.gov.it), grouped:

  - "Disciplinari DOP (A-D)"   ~155 PDFs
  - "Disciplinari DOP (E-N)"   ~113 PDFs
  - "Disciplinari DOP (O-Z)"   ~143 PDFs
  - "Disciplinari IGP"         ~111 PDFs (filenames prefixed "IGT ")

Each PDF is the consolidated national disciplinare di produzione,
attached to the founding DM and its modifications. Structure follows
the standard 10-article template:

  Articolo 1 — Denominazione e vini
  Articolo 2 — Base ampelografica       ← grape varieties
  Articolo 3 — Zona di produzione delle uve  ← commune list / geo
  Articolo 4 — Norme per la viticoltura
  Articolo 5 — Norme per la vinificazione
  Articolo 6 — Caratteristiche al consumo
  Articolo 7 — Designazione e presentazione
  Articolo 8 — Confezionamento
  Articolo 9 — Legame con l'ambiente geografico  ← terroir
  Articolo 10 — Riferimenti alla struttura di controllo (optional)

`match_wines_to_bundles` does filename→slug matching (exact-after-
normalisation > substring > rapidfuzz token-ratio >= 90 on alt-name
slugs), and `extract_articles` carves the pdftotext output into a
{article_num: body_text} dict.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz


# Filename markers that should be stripped before slugifying — these
# are doc-type qualifiers MASAF embeds inconsistently.
_JUNK_RE = re.compile(
    r"\b(disciplinare(\s+di\s+produzione)?|DOCG|DOC|DOP|IGT|IGP)\b\.?", re.I
)


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("'", " ").replace('"', "").replace("’", " ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


@dataclass(frozen=True)
class PdfRecord:
    bundle: str
    archive_path: str  # path inside the .7z
    filename: str  # base filename (without extension)
    primary_slug: str  # slug of the full title
    alt_slugs: tuple[str, ...]  # slug of each alternative name


def derive_alt_slugs(filename: str) -> list[str]:
    """Each MASAF filename gets multiple candidate slugs:
    the full title, plus each alternative name on either side of
    ' o ' (Italian "or") or ' e ' (Italian "and") splits, plus the
    junk-stripped variant. Order matters for tie-breaking: the full
    title comes first, then splits."""
    clean = re.sub(r"^IGT[_ ]", "", filename).strip()
    no_junk = _JUNK_RE.sub(" ", clean).strip()
    candidates: list[str] = [clean, no_junk]
    for sep in (r"\s+o\s+", r"\s+e\s+"):
        for piece in re.split(sep, no_junk):
            piece = piece.strip()
            if piece:
                candidates.append(piece)
    seen: list[str] = []
    for c in candidates:
        s = _slugify(c)
        if s and s not in seen:
            seen.append(s)
    return seen


def build_pdf_index(bundle_files: Iterable[tuple[str, str]]) -> list[PdfRecord]:
    """`bundle_files` is an iterable of (bundle_name, archive_path)
    tuples; `archive_path` looks like
    'Disciplinari DOP (A-D)/Barolo.pdf'. Returns a list of `PdfRecord`s
    in input order."""
    out: list[PdfRecord] = []
    for bundle, path in bundle_files:
        if not path.lower().endswith(".pdf"):
            continue
        fname = path.split("/")[-1].rsplit(".", 1)[0]
        slugs = derive_alt_slugs(fname)
        if not slugs:
            continue
        out.append(PdfRecord(
            bundle=bundle,
            archive_path=path,
            filename=fname,
            primary_slug=slugs[0],
            alt_slugs=tuple(slugs),
        ))
    return out


@dataclass(frozen=True)
class MatchOutcome:
    wine_slug: str
    pdf_index: int | None  # index into the PdfRecord list, or None
    how: str  # 'exact' / 'substring' / 'fuzzy:NN' / 'none'


def match_wines_to_pdfs(
    wines: list[dict],
    pdfs: list[PdfRecord],
    fuzzy_cutoff: int = 90,
) -> list[MatchOutcome]:
    """Each wine resolves to at most one PdfRecord (one-to-one assignment).
    Matching order: exact-after-normalisation > substring on primary
    slug > fuzzy on any alt slug. PDFs already claimed by an earlier
    wine are excluded from substring + fuzzy fallback."""
    exact_index: dict[str, int] = {}
    for i, rec in enumerate(pdfs):
        for s in rec.alt_slugs:
            exact_index.setdefault(s, i)

    assigned: dict[int, str] = {}  # pdf-idx -> wine-slug
    outcomes: list[MatchOutcome] = []

    for w in wines:
        cands: set[str] = {w["slug"], _slugify(w.get("name") or "")}
        if " o " in (w.get("name") or ""):
            for p in w["name"].split(" o "):
                cands.add(_slugify(p.strip()))
        cands.discard("")

        # 1. Exact match on alt-slug, claim if unassigned.
        hit_idx = None
        for c in cands:
            j = exact_index.get(c)
            if j is not None and j not in assigned:
                hit_idx = j
                break
        if hit_idx is not None:
            assigned[hit_idx] = w["slug"]
            outcomes.append(MatchOutcome(w["slug"], hit_idx, "exact"))
            continue

        # 2. Substring match on primary slug (wine in PDF or vice versa).
        sub_idx = None
        for i, rec in enumerate(pdfs):
            if i in assigned:
                continue
            for c in cands:
                if len(c) >= 6 and (c in rec.primary_slug or rec.primary_slug in c):
                    sub_idx = i
                    break
            if sub_idx is not None:
                break
        if sub_idx is not None:
            assigned[sub_idx] = w["slug"]
            outcomes.append(MatchOutcome(w["slug"], sub_idx, "substring"))
            continue

        # 3. Fuzzy fallback against all alt-slugs of unassigned PDFs.
        best_score = 0
        best_idx: int | None = None
        for i, rec in enumerate(pdfs):
            if i in assigned:
                continue
            for slug in rec.alt_slugs:
                for c in cands:
                    score = fuzz.ratio(c, slug)
                    if score > best_score:
                        best_score = score
                        best_idx = i
        if best_idx is not None and best_score >= fuzzy_cutoff:
            assigned[best_idx] = w["slug"]
            outcomes.append(MatchOutcome(w["slug"], best_idx, f"fuzzy:{int(best_score)}"))
            continue

        outcomes.append(MatchOutcome(w["slug"], None, "none"))

    return outcomes


# Article parser. `pdftotext -layout` output preserves columns but
# also right-aligns article headers. We anchor on lines that begin
# with optional whitespace + "Articolo N" + (optionally) a name on
# the same or next non-blank line.

# Leading whitespace allows form-feed (\x0c) because MASAF PDFs typically
# start each new article on its own page, and pdftotext -layout emits a
# bare \x0c at the start of the article-header line.
_ARTICLE_HEAD_RE = re.compile(
    r"^[ \t\x0c]*(?:Articolo|Art\.)[ \t]+(\d+)\b[ \t]*([^\n]*)$",
    re.M,
)

# Some disciplinari (older Brunello, some Sangue di Giuda variants)
# put each article's title on the next non-blank line, e.g.
#   "Articolo 1"
#   "(Denominazione)"
# which we still anchor on the Articolo N header.


def find_article_offsets(text: str) -> list[tuple[int, int, int]]:
    """Returns [(article_num, header_start, header_end)] sorted by
    document position. `header_end` is the offset just past the header
    line's trailing newline."""
    out: list[tuple[int, int, int]] = []
    for m in _ARTICLE_HEAD_RE.finditer(text):
        try:
            num = int(m.group(1))
        except ValueError:
            continue
        out.append((num, m.start(), m.end()))
    # Sort by header_start (already in order from finditer, but be safe).
    out.sort(key=lambda t: t[1])
    return out


def extract_articles(text: str) -> dict[int, str]:
    """Carves the pdftotext output into a dict {article_num: body}.
    Body excludes the header line and stops at the next article's
    header (or EOF). Newer disciplinari sometimes have the header
    appear twice (TOC + body); the LAST occurrence is kept since
    that's where the real body sits."""
    heads = find_article_offsets(text)
    if not heads:
        return {}

    # When the same article number appears multiple times (TOC + body),
    # take the LAST occurrence — TOC lines have no body content.
    last_by_num: dict[int, tuple[int, int, int]] = {}
    for tup in heads:
        last_by_num[tup[0]] = tup
    ordered = sorted(last_by_num.values(), key=lambda t: t[1])

    bodies: dict[int, str] = {}
    for i, (num, _hstart, hend) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        body = text[hend:end]
        # Trim a per-article sub-title on the first non-blank line:
        # MASAF disciplinari place "Denominazione e vini" /
        # "(Base ampelografica)" / etc. immediately after the header.
        # Keep it — downstream consumers may want it as a salience hint.
        bodies[num] = body.strip()
    return bodies


# Grape extraction from Article 2 ("Base ampelografica"). Two formats
# dominate, both handled here:
#
#   Bullet/list:     "Vermentino: da 0 a 100 %;\nSauvignon: da 0 a 100 %;"
#                    "principali: Bosco e/o Albarola e/o Vermentino bianco"
#   Prose:           "...esclusivamente dal vitigno Nebbiolo."
#                    "...uve del vitigno Sangiovese."
#
# We collect candidates from both:
#   (a) line/comma/semicolon-split phrases (drops percentage + role tails)
#   (b) "vitigno NAME" / "vitigni NAME [e/o NAME]+" regex matches
# and feed each candidate through grape_entity.match_variety, which
# handles the actual fuzzy resolution against the canonical vocab.

# Newlines, commas, semicolons — and the guillemets / smart double
# quotes that wrap a DOP name ("Vittoria» Frappato", "Cori” Bianco
# Bellone") — all separate one candidate phrase from the next.
_LINE_SPLIT_RE = re.compile(r"[\n,;«»“”\"]+")

# Characters trimmed from candidate variety phrases — Italian
# disciplinari sprinkle quotation marks, parens, stops, and list-bullet
# dashes around names.
_TRIM_CHARS = " .,;:«»\"'·“”()-–—•*"

# Drops phrases that contain Italian role/section noise but no variety
# name (so they don't reach match_variety and inflate unknowns queue).
_GRAPE_LINE_DROP = (
    "principal", "principali", "raccomandat", "complementar", "accessori",
    "autorizzat", "consentit", "idoneo", "idonee",
    "varietà", "varieta", "uve da vino", "vitigni", "vitigno",
    "elencat", "iscritt", "registro nazionale", "uvaggio", "uva a bacca",
    "denominazione", "vino", "produzione", "ottenuti", "deve essere",
    "composizione ampelografica", "regione", "doc", "docg",
)

# "vitigno X" / "vitigni X e/o Y e/o Z" patterns. Lookahead stops at
# common Italian connectives or sentence terminators. A colon ("vitigno
# Nebbiolo: dal 70%") and an open paren ("vitigno Nebbiolo (Spanna) dal
# 90%") are terminators too — Italian disciplinari attach the percentage
# range or a synonym gloss to the variety name with either.
_VITIGNO_RE = re.compile(
    r"\bvitign[oi]\s+([A-ZÀÈÉÌÒÙ][\w\sàèéìòù'’\-/.]+?)"
    r"(?=\s*(?:per|al|dal|nel|nella|in\s|con\s|che\s|;|,|:|\(|\.|"
    r"\bn\.|\bb\.|\bg\.|\brs\.|\brg\.|\brb\.|$))",
    re.U,
)

# Strip trailing colour suffixes "N." / "B." / "G." / "RS." / "RG." /
# "RB." commonly attached to Italian variety names. Disciplinari write
# the code in either case ("Barbera N.", "Syrah n.") — match both.
_COLOUR_SUFFIX_RE = re.compile(r"\s+(?:[NBGRS]+\.?)+\s*$", re.I)


def _scan_vitigno_phrases(text: str) -> list[str]:
    """Extract everything that follows "vitigno"/"vitigni" up to a
    plausible terminator. Splits compound matches on " e/o ", " e ",
    " o ", "/" so each variety is a separate candidate."""
    candidates: list[str] = []
    for m in _VITIGNO_RE.finditer(text):
        body = m.group(1).strip(_TRIM_CHARS)
        for part in re.split(r"\s+e/o\s+|\s+e\s+|\s+o\s+|/", body):
            p = part.strip(_TRIM_CHARS)
            if p:
                candidates.append(p)
    return candidates


# A percentage tail is the variety's allowed share — "Corvina Veronese
# dal 45% al 95%", "Nebbiolo: dal 70% all'85%". Everything from the
# leading connective run ("dal", "al", "fino ad", bare range numbers …)
# through the first `<digits>%` and on to end-of-string is dropped, so
# the bare variety name survives.
_PERCENT_TAIL_RE = re.compile(
    r"\s*[:\-]?\s*"
    r"(?:(?:dal?|dall['’]|d[ae]ll[ae]|degli|agli|al|all['’]|alla|"
    r"fino\s+ad?|sino\s+ad?|per|circa|almeno|minimo|massimo|"
    r"da\s+0\s+a|un\s+massimo\s+di|l['’])\s*|\d+(?:[.,]\d+)?\s*)*"
    r"\d+(?:[.,]\d+)?\s*%.*$",
    re.I,
)


def _strip_percent_tail(s: str) -> str:
    return _PERCENT_TAIL_RE.sub("", s).strip(_TRIM_CHARS)


# Quantity prose left dangling on a candidate once the percentage figure
# itself has been split onto a neighbouring chunk by pdftotext's column
# layout ("Raboso Piave in misura non inferiore" ← "… al 95%",
# "Bianchello almeno per il" ← "… 95%", "Fortana loc" ← "località").
# Strip from the first variety-impossible word — optionally preceded by
# a run of weak articles/prepositions — through end-of-string.
_TRAILING_NOISE_RE = re.compile(
    r"\s+(?:(?:in|per|non|ad?|e|che|nella?|del|dello|della)\s+)*"
    r"(?:fino|sino|loc|min|max|circa|inoltre|almeno|massimo|minimo|misura|"
    r"inferiore|superiore|ambito|aziendale|vigneti|presenti|present\w*|"
    r"coltivazione|congiuntamente|disgiuntamente|concorr\w*|costituit\w*|"
    r"riservat\w*|seguent\w*)\b.*$",
    re.I,
)


def _strip_role_prefix(s: str) -> str:
    """When a chunk starts with a role keyword + colon
    ("Vitigni principali: Bosco"), take what comes AFTER the colon —
    the colon separates the role marker from the variety list. When the
    colon has already been consumed by the caller's colon-split, a bare
    leading "vitigno"/"vitigni"/"varietà" word is stripped instead, so
    "vitigno Nebbiolo" still reduces to "Nebbiolo"."""
    m = re.match(
        r"(?i)^\s*(?:vitign[oi](?:\s+\w+)?|varie?t[aà](?:\s+\w+)?|"
        r"composizione\s+ampelografica|principali|complementari|"
        r"accessor[ei]|raccomandat[ei])\s*:\s*(.+)$",
        s,
    )
    if m:
        return m.group(1).strip()
    m = re.match(r"(?i)^\s*(?:vitign[oi]|varie?t[aà])\s+(.+)$", s)
    return m.group(1).strip() if m else s


# Wine-type / qualifier words that wrap a variety name in a disciplinare
# ("rosso Sangiovese", "Schiava è") but are never part of one. Peeled
# off either end of a candidate. Colour words (bianco / nero) are NOT
# listed — they head real names (Nero d'Avola, Bianco di Alessano) and
# distinguish paired cultivars (Bombino bianco vs Bombino nero).
# NB: "uva"/"uve" are deliberately absent — they head real variety
# names (Uva Rara, Uva di Troia), unlike the pure wine-type words here.
_WINETYPE_WORDS = frozenset({
    "rosso", "rossi", "rosato", "rosati", "rosse", "spumante",
    "novello", "passito", "frizzante", "vivace", "superiore", "riserva",
    "classico", "amabile", "dolce", "secco", "liquoroso", "vino", "vini",
    "è", "e",
})
# A candidate that is *only* a colour/type word carries no variety.
_BARE_TYPE_WORDS = _WINETYPE_WORDS | {"bianco", "bianca", "bianchi", "nero", "nera"}


def _strip_winetype(s: str) -> str:
    parts = s.split()
    while parts and parts[0].lower() in _WINETYPE_WORDS:
        parts.pop(0)
    while parts and parts[-1].lower() in _WINETYPE_WORDS:
        parts.pop()
    return " ".join(parts)


def article2_candidate_phrases(text: str) -> list[str]:
    """All candidate variety phrases from an article-2 body. Order is
    preserved so the caller can early-exit on first hit per phrase.

    Italian disciplinari list varieties in one of three shapes:
      (a) bullet/list   "Vermentino: da 0 a 100 %;\\nSauvignon: ..."
      (b) role + list   "Vitigni principali: Bosco e/o Albarola e/o Vermentino"
      (c) prose         "...esclusivamente dal vitigno Nebbiolo."
    All three are covered: (a) + (b) by the comma/semicolon split on
    a single-line view of the body, (c) by the explicit `vitigno`-
    regex scan.
    """
    if not text:
        return []
    out: list[str] = []
    # Rejoin a word pdftotext hyphenated across a line break ("Erb-\n
    # aluce" → "Erbaluce"); only when the hyphen sits tight against the
    # preceding letter, so a spaced "rosso - rosato" dash is left alone.
    single = re.sub(r"(?<=\w)-\n[^\S\n]*", "", text)
    # Collapse spaces/tabs but KEEP newlines: disciplinari that list one
    # variety per line ("Merlot\nCabernet franc\nRefosco …") rely on the
    # newline as the enumeration separator (_LINE_SPLIT_RE splits on it).
    single = re.sub(r"[^\S\n]+", " ", single)
    # A parenthetical after a variety name is a synonym gloss ("Corvina
    # Veronese (Cruina o Corvina)", "Nebbiolo (Spanna)") — drop it so the
    # head name detaches cleanly. Surfacing the gloss as its own
    # candidate is unsafe: a regional synonym ("Spanna") fuzzy-matches
    # the wrong canonical variety.
    single = re.sub(r"\([^)]*\)", " ", single)
    # Treat "e/o", " ed ", " e " and " o " as enumeration separators
    # (Italian "and/or" / "and" / "or") so multi-variety phrases — and
    # the "synonym1 o synonym2" gloss disciplinari use ("Calabrese o
    # Nero d'Avola", "Granaccia o Pigato") — split cleanly. A standalone
    # " o "/" e " never occurs inside a single variety name.
    cleaned = re.sub(r"\s+e/o\s+", ",", single, flags=re.I)
    cleaned = re.sub(r"\s+o\s+", ",", cleaned)
    cleaned = re.sub(r"\s+ed?\s+", ",", cleaned)
    for chunk in _LINE_SPLIT_RE.split(cleaned):
        # A chunk may carry a role marker + the variety name on either
        # side of a colon ("la seguente composizione ampelografica:
        # Cesanese di Affile"). Process each colon-split half as its
        # own candidate; the role-side gets filtered by the drop list,
        # the variety-side reaches match_variety.
        for piece in chunk.split(":"):
            piece = piece.strip(_TRIM_CHARS)
            if not piece:
                continue
            piece = _strip_role_prefix(piece)
            piece = _strip_percent_tail(piece)
            piece = _TRAILING_NOISE_RE.sub("", piece).strip(_TRIM_CHARS)
            piece = _COLOUR_SUFFIX_RE.sub("", piece).strip(_TRIM_CHARS)
            piece = _strip_winetype(piece)
            if not piece or piece.lower() in _BARE_TYPE_WORDS:
                continue
            low = piece.lower()
            # Anchor each drop term at a word start — a free substring
            # test would discard real varieties that merely contain a
            # noise stem ("vino" inside "Cor·vino·ne", "regione" …).
            if (
                any(re.search(r"\b" + re.escape(d), low) for d in _GRAPE_LINE_DROP)
                and len(piece) < 80
            ):
                continue
            if len(piece) < 80:
                out.append(piece)
    # (c) vitigno-prose scan — independent of the chunk pipeline.
    for c in _scan_vitigno_phrases(text):
        out.append(c)
    return out


def _loose_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_grapes_with(matcher, article2_body: str, wine_name: str = "") -> dict:
    """Apply `matcher(phrase) -> MatchResult | None` to each candidate
    in `article2_body`. Returns {principal: [...], accessory: [],
    observation: [], details: [...]}. MASAF disciplinari don't carry
    an explicit principal/accessory split in v1 — all matches default
    to `principal`, like the doc-unico parser in 02_extract_pliegos.

    A grape matched only from a phrase that restates `wine_name` (the
    appellation's own name) is dropped — but only when other varieties
    were also found. Article 2 opens by restating the DOP name, and a
    DOP name occasionally collides head-on with a registered VIVC
    synonym ("Brunello di Montalcino" is a Sangiovese synonym, so it
    exact-matches the slug `nielluccio`); yet a varietally-named DOP
    (Cesanese di Affile) must keep the grape that equals its own name.
    A fuzzy hit is trusted only at score >= 90 and on a phrase long
    enough to be a real name: a 5-letter Italian function word
    ("nella") or a colour-glossed region phrase otherwise fuzzy-matches
    an unrelated variety. After the vocab additions almost every true
    variety resolves exact, so the low-confidence fuzzy band is noise."""
    out = {
        "principal": [],
        "accessory": [],
        "observation": [],
        "details": [],
    }
    name_key = _loose_key(wine_name)
    seen: set[str] = set()
    hits: list[tuple] = []  # (MatchResult, from_wine_name)
    for phrase in article2_candidate_phrases(article2_body):
        hit = matcher(phrase)
        if hit is None or hit.slug in seen:
            continue
        if hit.method.startswith("fuzzy"):
            score = int(hit.method.split(":")[1])
            if score < 90 or len(re.sub(r"[\W\d_]", "", phrase)) < 7:
                continue
        seen.add(hit.slug)
        hits.append((hit, bool(name_key) and _loose_key(phrase) == name_key))

    real = [h for h, from_name in hits if not from_name]
    keep = real if real else [h for h, _ in hits]
    for hit in keep:
        out["principal"].append(hit.slug)
        out["details"].append({
            "slug": hit.slug,
            "name": hit.name,
            "role": "principal",
            "colour": hit.colour,
            "source": "masaf-disciplinare",
        })
    return out


def derive_summary(article1_body: str, max_chars: int = 600) -> str:
    """Article 1's first paragraph (after the per-article sub-title)
    is the canonical natural-language summary. Cut to max_chars at the
    nearest sentence boundary."""
    if not article1_body:
        return ""
    # Drop the per-article sub-title on the first line ("Denominazione
    # e vini" / "(Denominazione)") — it's redundant with the document
    # header. We detect it as a short (<60 char) line with no number.
    lines = article1_body.splitlines()
    head = []
    for ln in lines:
        s = ln.strip()
        if not head and not s:
            continue
        if not head and len(s) < 60 and not re.match(r"^\d+\.", s):
            continue
        head.append(s)
    text = re.sub(r"\s+", " ", " ".join(head)).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def derive_geo_area(article3_body: str, max_chars: int = 4000) -> str:
    """Article 3 ('Zona di produzione delle uve') body. Returned trimmed
    of leading sub-title noise and capped at max_chars so the panel
    doesn't drown in commune lists."""
    if not article3_body:
        return ""
    text = article3_body.strip()
    # Drop per-article sub-title on first ≤60-char line (same logic
    # as `derive_summary`).
    lines = text.splitlines()
    kept = []
    skip_subtitle = True
    for ln in lines:
        s = ln.strip()
        if skip_subtitle:
            if not s:
                continue
            if len(s) < 60 and not re.match(r"^\d+\.", s):
                skip_subtitle = False
                continue
            skip_subtitle = False
        kept.append(s)
    body = "\n".join(kept).strip()
    if len(body) > max_chars:
        body = body[:max_chars].rsplit(".", 1)[0] + "."
    return body


def derive_terroir(article9_body: str, max_chars: int = 4000) -> str:
    """Same shape as `derive_geo_area` but for Article 9 ('Legame con
    l'ambiente geografico')."""
    return derive_geo_area(article9_body, max_chars=max_chars)


_LEGAME_TITLE_RE = re.compile(
    r"legame\s+con\s+(?:l['’]ambiente|la\s+zona)\s+geografic",
    re.I,
)


def pick_terroir_article(articles: dict[int, str]) -> tuple[int, str]:
    """Return (article_number, derived_terroir_body) for the article
    whose title is the 'Legame con l'ambiente geografico' section.
    The canonical MASAF template puts it at Article 9; the older
    Veneto-IGT template (colli-trevigiani, conselvano, marca-
    trevigiana, veneto-orientale) shifts it to Article 8 because
    Article 9 there holds 'Riferimenti alla struttura di controllo'.
    Tries Art 9 then Art 8 by title-keyword match; falls back to Art 9
    when neither matches (the established canonical default)."""
    for n in (9, 8):
        body = articles.get(n, "")
        if body and _LEGAME_TITLE_RE.search(body[:300]):
            return n, derive_terroir(body)
    return 9, derive_terroir(articles.get(9, ""))
