"""Vocabulary-anchored grape entity recognition.

A single matcher used by both ES extractors (EU-OJ documento único and
national pliego) and, eventually, the PT caderno. Replaces the prose
blacklist gatekeeping with a positive vocabulary match: cross-corpus
extracted slugs ∪ VIVC primes + synonyms ∪ GRAPE_ALIAS keys.

A token is accepted only when its normalised form (lowercased, NFKD
diacritic-stripped, optional INAO colour-letter suffix stripped) hits an
entry in the vocabulary. Unmatched tokens are logged to an in-process
queue and surfaced as `raw/<country>/extraction-unknowns.json` at the
end of the run via `flush_unknowns_queue`.

Vocabulary precedence (first-write-wins via `setdefault`):
  1. Cross-corpus canonical slugs (excluding phantom concatenations).
     Stable corpus mappings win. `loureiro-tinto` stays separate from
     `mencia` even though VIVC merges them via DNA.
  2. GRAPE_ALIAS keys as space-separated surfaces — curator-verified
     disambiguations, so they outrank anything VIVC infers.
  3. VIVC surfaces, deduped by `vivc_id` and ranked by how strongly the
     record claims the name: prime names first, then synonyms flagged
     "official name in <country>", then plain legacy synonyms. Without
     that ranking a legacy synonym could outrank another record's prime
     name purely on file order. When several by-slug files share a
     vivc_id, prefer the slug that's already in the corpus, then the
     slug whose normalised form matches the prime name, then the
     shortest.

A small set of bare colour adjectives ("TINTA", "BLANCA", "GRIS", …)
that appear as VIVC synonyms is excluded — they're prose, not
identifiers, and the extractor's `_DROP` set already handles them
upstream.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process
from unidecode import unidecode

_LIB_ROOT = Path(__file__).resolve().parent
if str(_LIB_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT.parent))
from _lib.grape_lexicon import (  # noqa: E402,F401
    COLOUR_QUALIFIED_SLUGS,
    COLOUR_WORD_VARIETIES,
    DEFAULT_COLOUR,
    GRAPE_ALIAS,
    slugify,
)

_REPO_ROOT = _LIB_ROOT.parent.parent

_VIVC_DIR = _REPO_ROOT / "raw" / "vivc" / "by-slug"
_CORPUS_DIRS = (
    _REPO_ROOT / "raw" / "inao" / "cahier-extracted",
    _REPO_ROOT / "raw" / "es" / "pliegos-extracted",
    _REPO_ROOT / "raw" / "pt" / "cadernos-extracted",
)

_GRAPE_CATEGORIES = ("principal", "accessory", "observation", "all")
# `token_sort_ratio` penalises length mismatch — a 5-word prose chunk
# can't score high against a 1-word grape name, even when the grape
# word is present. Cutoff 85 rejects `Merenzao en tintas` (71) and
# `Ourense` → ondenc (77), keeping only typo-fix matches like a
# 1-letter swap or a dropped accent. token_set_ratio would have scored
# all of these 100 because the grape word is a strict subset.
_FUZZY_CUTOFF = 85

# INAO colour-letter suffixes. Case-sensitive on purpose — lowercase `b`
# is too common as a final letter (`Bobal B` correctly strips `B`, but
# stripping a final `b` from any token would shred legitimate names).
# The code follows any letter: a per-script allowlist had left out the
# Croatian ć (Babić N matched nothing), the Italian ò and ì (Groppello di
# Revò N) and the Greek capitals (ΑΣΥΡΤΙΚΟ Β), which then fell to fuzzy.
_COLOUR_LETTER_RE = re.compile(
    r"(?<=[^\W\d_])"
    r"\s+(B|N|G|Rs|Rg|R|Β|Ν|Γ)\Z"
)
_COLOUR_LETTER_TO_NAME = {
    "B": "blanc",
    "N": "noir",
    "G": "gris",
    "Rs": "rose",
    "Rg": "rouge",
    "R": "rouge",
    # Greek pliegos mix Greek capital Β / Ν / Γ (glyph-identical to Latin
    # B / N / G, different code points) with Latin letters at the end
    # of variety names; both map to the same colour buckets.
    "Β": "blanc",
    "Ν": "noir",
    "Γ": "gris",
}

# Surfaces that never identify a variety on their own. Two classes:
#   1. Bare colour-adjectives that VIVC surfaces as standalone synonyms
#      (e.g. tinta-porto-santo's synonym list has the bare word "TINTA").
#      The upstream `_DROP` set already filters them at the extractor
#      pre-processing stage, but defence-in-depth keeps them out too.
#   2. Bare breeder-family names that only name a determinate cultivar
#      when carrying their release number — "Seibel" alone is the
#      French-American hybridiser family (Seibel 5455 = Plantet, …), and
#      bare "Seibel" otherwise fuzzy-matches the Tempranillo VIVC synonym
#      "Sensibel" (85.7, same first char → passes the sanity guard).
_BANNED_SURFACES = frozenset({
    "tinta", "tintas", "tinto", "tintos",
    "blanca", "blancas", "blanco", "blancos",
    "negra", "negras", "negro", "negros",
    "gris", "grises",
    "rojo", "rojos", "roja", "rojas",
    "rosada", "rosadas", "rosado", "rosados",
    # The rosé colour words: VIVC lists ROSE as a synonym of Nebbiolo (#8417),
    # so a bare "rosé" / "rosè" from a wine-type line ("spumante rosato o
    # rosè", the Hungarian "Rosé" category) bound Nebbiolo to Prosecco,
    # Romagna Oriolo, Alto Adige, Mór … (2026-10-22). _normalise folds the
    # accents, so the key is the bare form.
    "rose", "roses", "rosee", "rosees",
    "rosato", "rosati", "rosata", "rosate", "rosat", "rosats",
    # Wine-style and colour words, place names and adjectives a variety list
    # carries that had fuzzy-matched a cultivar (sweep of 2026-10-22): the
    # Hungarian Siller / Egri Csillag styles and "piros" (red), the Alto Adige
    # Kretzer, a bare "blanc", the Italian "gentile" and "rosa", Lacryma (of
    # Lacryma Christi), the Greek Κάβα (aged-wine category), Πάτρα and
    # Μοναστήρι. _normalise romanises the Greek.
    "siller", "csillag", "piros", "kretzer", "blanc", "gentile", "rosa",
    "lacryma", "kaba", "patra", "monasteri",
    # the Greek "Για" (for) and the Retsina style word, which a fresh GR 02f
    # had bound to Giro negre and Ritino (2026-10-11)
    "gia", "retsina", "retsinas",
    # "da sole / da soli / da sola o congiuntamente" (alone or together), the
    # phrase every MASAF complement clause carries: VIVC lists SOLE under
    # Folle blanche and SOLA under Molinara (Abruzzo, Aleatico di Puglia).
    "sole", "soli", "sola",
    # the bare colour word of "Moscato giallo" / "Trebbiano giallo", a VIVC
    # synonym of Trebbiano di Soave
    "giallo",
    # "verde" (green) is a VIVC synonym of the Greek Lagorthi; Lacryma Christi
    # is Vesuvio's wine, not a grape (it had matched Lacrima and Albanello)
    "verde", "lacryma christi", "lacryma christi bianco", "lacryma christi rosso",
    "lacryma christi rosato",
    # Claims of passports fetched in the same sweep, caught by the second
    # re-extraction: "m 2" (a Geneva règlement's square metre) is Karmin's
    # breeder code "M. 2", "Roche" (the Vaud commune) a legacy synonym of
    # Ruchè, "Montagna" (the Alto Adige comune) the VIVC prime of Paolina,
    # and VIVC folds a bare "Asprouda" under several Greek cultivars —
    # Anchialos's spec names it as a local name of Savatiano.
    "m 2", "roche", "montagna", "asprouda",
    # Squinzano's "ad esclusione dei moscati" (the muscats) had bound Moscato
    # giallo; a "grano" left over from "Moscatel de ⏎ Grano Menudo" the
    # Portuguese Granho; Limnos's prose names "Μοσχάτο" for its Muscat of
    # Alexandria, which a bare "Moschato" had turned into Muscat blanc.
    "moscati", "grano", "moskhato",
    # Bare colour words of the corpus languages (review of 2026-10-22). The HU
    # national specs head each block with "Fehér" (white) and the Majarcă albă
    # passport (#11866) lists FEHER among its synonyms, so pinning it put
    # Majarcă on six Hungarian cards; the Valais règlement's "blanche" had bound
    # Mondeuse blanche; thirty more bare words bound something latent ("nera" →
    # Pinot noir, "crna" → Plavac mali, "albe" → Elbling, "roter" → Roter
    # Veltliner, "weisser" → Elbling, "bílá" → Okatica bijela …). A real variety
    # that is a colour word stays out: "Bianca" and "Nero", the Hungarian
    # crossings; "tinta" / "tinto" were banned already. Keys are the
    # `_normalise` forms (Greek and Cyrillic romanised).
    "feher", "voros", "kek", "szurke", "roze", "bila", "bile", "bily", "biele", "biela",
    "cervena", "cervene", "cerveny", "modra", "modre", "modry", "ruzove", "ruzova", "ruzovy",
    "bijela", "bijelo", "bijeli", "crna", "crno", "crni", "bela", "belo", "beli", "rdeca",
    "rdece", "rdeci", "bialo", "cherveno", "cherveni", "chervena", "alb", "alba", "albe",
    "negru", "negre", "neagra", "rosu", "rosie", "rosii", "nera", "nere", "neri", "bianco",
    "bianchi", "bianche", "rosso", "rossa", "rossi", "rosse", "weiss", "weisse", "weisser",
    "weisses", "rot", "rote", "roter", "rotes", "blau", "blaue", "blauer", "grau", "graue",
    "grauer", "blanche", "blanches", "noir", "noire", "noirs", "noires", "rouge", "rouges",
    "branco", "branca", "brancas", "brancos", "leuko", "leuka", "eruthro", "eruthra", "kokkino",
    "wit", "witte", "rood", "rode", "zwart", "zwarte", "blauw", "blauwe", "white", "red",
    "black",
    "seibel",
    # Bare "Bouschet" is the teinturier-breeding family (Petit / Gros /
    # Alicante Bouschet), never one cultivar — it reaches the matcher
    # only as the wrapped half of "Alicante ⏎ Bouschet" (Menfi), where
    # it bound to Petit Bouschet.
    "bouschet",
    # Hungarian bare "muskotály" is a wine-type / labelling term (Egri
    # Classicus muskotály, Mátra's Muskotály bortípus — defined in the
    # termékleírás as a blend from an enumerated Muscat list) or a
    # line-wrap fragment of a qualified Muscat ("Sárga ⏎ muskotály",
    # "Ottonel ⏎ muskotály") — never a variety row of its own. The word
    # is Hungarian-only, so a global ban is safe.
    "muskotaly",
    # Bare "Vernaccia" names a different variety per region (S.
    # Gimignano's white, Oristano's flor white, the Marche/Umbria black
    # Vernaccia nera) and VIVC hands it to Vermentino. The one corpus
    # record using the bare form (Colli Martani: "Vernaccia Nera o
    # Vernaccia, di seguito indicata solo come Vernaccia") already binds
    # correctly through its "Vernaccia nera" composition line, so the
    # bare surface only ever adds a wrong slug.
    "vernaccia",
    # Bare "Cabernet" is a group designation, never a determinate
    # cultivar: Italian disciplinari define it in-document as Cabernet
    # franc e/o Cabernet Sauvignon (e/o Carmenère) and the IT MASAF
    # parser expands it before matching; elsewhere it only occurs as a
    # line-wrap truncation of one of the two. Unmatched bare occurrences
    # land in the unknowns queue, where they stay visible.
    "cabernet",
    # "Italia" reaches the matcher as the country column of EUR-Lex
    # variety tables ("Italia - Greco bianco B.", Cirò) — it once bound a
    # stale vocab slug and today fuzzy-matches rossese at 92. The table
    # grape Italia never appears in a wine variety roster.
    "italia",
    # The Italian adjective "aromatico" and its inflections reach the matcher
    # as bare tokens from MASAF clauses ("altri vitigni non aromatici", "del
    # tipo aromatico"). VIVC lists AROMATO on Muscat bleu (#16002, pinned
    # 2026-10-23 for the NL provincie PGIs), which "aromatico" then
    # fuzzy-matched at 87 on Terratico di Bibbona, Trevenezie and Vigneti
    # delle Dolomiti; a multi-word surface ("Malvasia di Candia aromatica",
    # "Traminer aromatico") is unaffected.
    "aromatico", "aromatica", "aromatici", "aromatiche",
})


@dataclass(frozen=True)
class MatchResult:
    slug: str
    name: str
    colour: str
    method: str


@dataclass(frozen=True)
class Vocabulary:
    exact_index: dict[str, str]
    names: tuple[str, ...]
    # The surfaces the lexicon itself vouches for — corpus slugs, GRAPE_ALIAS
    # keys, VIVC prime names and the synonyms VIVC flags as a country's
    # official name — as opposed to VIVC's unflagged synonyms,
    # which include place names ("Valtellina", "Avola", "Barolo").
    curated: frozenset = frozenset()


@dataclass
class _UnknownsQueue:
    seen: dict[str, dict] = field(default_factory=dict)


_UNKNOWNS = _UnknownsQueue()

_CURRENT_PLIEGO: list[str | None] = [None]


def set_pliego_context(slug: str | None) -> None:
    """Set the pliego slug attributed to subsequent `match_variety` calls
    that don't pass `source_pliego` explicitly. Callers wrap a per-pliego
    parse with `set_pliego_context(slug)` / `set_pliego_context(None)`."""
    _CURRENT_PLIEGO[0] = slug


def current_pliego_context() -> str | None:
    """The record slug a per-record parse set, so a country parser can apply
    a per-record binding (IT `grape_context_overrides.json`)."""
    return _CURRENT_PLIEGO[0]


def _normalise(name: str) -> str:
    """Lowercase + Cyrillic→Latin transliteration + NFKD diacritic-strip
    + collapse whitespace + collapse hyphens / dots / commas to single
    spaces. The vocab surface form. `unidecode` is a no-op for Latin
    input (covers all 9 pre-BG corpora) and romanises Cyrillic for BG."""
    transliterated = unidecode(name)
    nfkd = unicodedata.normalize("NFKD", transliterated)
    ascii_form = nfkd.encode("ascii", "ignore").decode().lower()
    ascii_form = re.sub(r"[-_./,]+", " ", ascii_form)
    ascii_form = re.sub(r"\s+", " ", ascii_form).strip()
    return ascii_form


def _slug_to_search_surface(slug: str) -> str:
    return slug.replace("-", " ")


def _grapes_in_record(rec: dict, slugs: set[str]) -> None:
    grapes = rec.get("grapes")
    if isinstance(grapes, dict):
        for role in _GRAPE_CATEGORIES:
            for g in grapes.get(role) or []:
                if isinstance(g, str):
                    slugs.add(g)
                elif isinstance(g, dict) and isinstance(g.get("slug"), str):
                    slugs.add(g["slug"])
    elif isinstance(grapes, list):
        for g in grapes:
            if isinstance(g, str):
                slugs.add(g)
            elif isinstance(g, dict) and isinstance(g.get("slug"), str):
                slugs.add(g["slug"])


@lru_cache(maxsize=1)
def _corpus_slug_frequency() -> dict[str, int]:
    """GRAPE_ALIAS-folded slug → number of pliegos / cahiers / cadernos
    that list it. Used as the primary tiebreaker when several VIVC
    by-slug files share a vivc_id — the slug most pliegos already use
    wins, so the new matcher doesn't churn the dominant canonical."""
    freq: dict[str, int] = {}
    for src in _CORPUS_DIRS:
        if not src.exists():
            continue
        for f in sorted(src.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            per_record: set[str] = set()
            _grapes_in_record(rec, per_record)
            for s in per_record:
                canonical = GRAPE_ALIAS.get(s, s)
                freq[canonical] = freq.get(canonical, 0) + 1
    return freq


@lru_cache(maxsize=1)
def _raw_corpus_slugs() -> frozenset[str]:
    return frozenset(_corpus_slug_frequency().keys())


def _next_vocab_piece(
    parts: list[str], i: int, vocab: frozenset[str], excluded: str,
) -> tuple[str | None, int]:
    for j in range(min(len(parts), i + 4), i, -1):
        candidate = "-".join(parts[i:j])
        if candidate == excluded:
            continue
        if candidate in vocab or GRAPE_ALIAS.get(candidate, candidate) in vocab:
            return candidate, j
    return None, i


def _is_phantom_slug(slug: str, vocab: frozenset[str]) -> bool:
    """Mirror of `_decomposes_into_known_with_alias` in national_pliego.
    A slug is phantom when it greedily decomposes into 2+ pieces in the
    vocab AND at least one piece is a GRAPE_ALIAS source key — i.e., a
    concatenation of known sub-slugs where one piece is itself an alias
    (`tempranillo-cencibel`)."""
    parts = slug.split("-")
    if len(parts) < 2:
        return False
    pieces: list[str] = []
    i = 0
    while i < len(parts):
        piece, j = _next_vocab_piece(parts, i, vocab, slug)
        if piece is None:
            return False
        pieces.append(piece)
        i = j
    return len(pieces) >= 2 and any(p in GRAPE_ALIAS for p in pieces)


@lru_cache(maxsize=1)
def _clean_corpus_slugs() -> frozenset[str]:
    raw = _raw_corpus_slugs()
    vocab = raw | frozenset(GRAPE_ALIAS.keys())
    return frozenset(s for s in raw if not _is_phantom_slug(s, vocab))


def _load_vivc_records() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    if not _VIVC_DIR.exists():
        return out
    for f in sorted(_VIVC_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append((f.stem, data))
    return out


@lru_cache(maxsize=1)
def _vivc_canonical_by_id() -> dict[int, str]:
    """vivc_id → canonical slug. Among VIVC by-slug files that share a
    vivc_id, prefer (a) a slug present in the clean corpus, (b) a slug
    whose normalised surface matches the prime name, (c) the shortest
    slug, (d) alphabetical.
    """
    clean_corpus = _clean_corpus_slugs()
    freq = _corpus_slug_frequency()
    candidates: dict[int, list[tuple[tuple, str]]] = {}
    for file_slug, data in _load_vivc_records():
        vid = data.get("vivc_id")
        if not isinstance(vid, int) or not vid:
            continue
        corpus_rank = 0 if file_slug in clean_corpus else 1
        corpus_freq_rank = -freq.get(file_slug, 0)
        prime_normalised = _normalise(data.get("prime_name") or "")
        slug_normalised = _normalise(_slug_to_search_surface(file_slug))
        prime_match_rank = 0 if (
            prime_normalised and slug_normalised == prime_normalised
        ) else 1
        rank = (corpus_rank, corpus_freq_rank, prime_match_rank, len(file_slug), file_slug)
        candidates.setdefault(vid, []).append((rank, file_slug))
    return {
        vid: GRAPE_ALIAS.get(min(items)[1], min(items)[1])
        for vid, items in candidates.items()
    }


# A slug spells an elided article as a word ("bianco-d-alessano"), a token
# keeps the apostrophe ("Bianco d'Alessano"): register both forms, or the
# alias never fires (Valle d'Itria, Lizzano and Martina lost the variety).
_ELISION_RE = re.compile(r"\b([dl]) (?=\w)")


def _claim_into(exact: dict[str, str], name: object, canonical: str) -> None:
    if not isinstance(name, str) or not name:
        return
    key = _normalise(name)
    if len(key) < 3 or key in _BANNED_SURFACES:
        return
    exact.setdefault(key, canonical)


def _claim_vivc_synonyms(exact: dict[str, str], records: list, *, official: bool) -> None:
    """Claim the VIVC synonyms of one tier: those VIVC flags as a country's
    official name, or the unflagged legacy ones."""
    for canonical, data, _file_slug, _resolved in records:
        for syn in data.get("synonyms") or []:
            if isinstance(syn, dict) and bool(syn.get("official_in")) is official:
                _claim_into(exact, syn.get("name"), canonical)


@lru_cache(maxsize=1)
def _load_vocabulary() -> Vocabulary:
    exact: dict[str, str] = {}

    for slug in sorted(_clean_corpus_slugs()):
        key = _normalise(_slug_to_search_surface(slug))
        if len(key) < 3 or key in _BANNED_SURFACES:
            continue
        exact.setdefault(key, slug)
        exact.setdefault(_ELISION_RE.sub(r"\1'", key), slug)

    # GRAPE_ALIAS keys are curator-verified disambiguations of names that
    # are otherwise ambiguous across VIVC (e.g. "MOSCATEL" is a synonym
    # of nine VIVC entries; the alias pin says it's `muscat-d-alexandrie`
    # in our corpus). Apply BEFORE VIVC so the alias wins.
    for alias_key, canonical in GRAPE_ALIAS.items():
        key = _normalise(_slug_to_search_surface(alias_key))
        if len(key) < 3 or key in _BANNED_SURFACES:
            continue
        exact.setdefault(key, GRAPE_ALIAS.get(canonical, canonical))
        exact.setdefault(_ELISION_RE.sub(r"\1'", key), GRAPE_ALIAS.get(canonical, canonical))

    # VIVC keeps every name a variety has ever borne, so one surface is
    # routinely claimed by several records — "Freisa" is the prime name of
    # VIVC #4256 and also a legacy synonym on Croatina, "Grenache noir" is
    # France's official name for Garnacha Tinta and a plain synonym on
    # Alicante Henri Bouschet. Walking records in one pass let file order
    # decide those, which silently bound both surfaces to the wrong variety.
    #
    # Rank the claims instead, strongest evidence first: a prime name beats
    # another record's synonym, and a synonym VIVC flags as the official name
    # in some country beats an unflagged legacy one. Ties inside a tier are
    # still order-dependent — those are the genuinely ambiguous names, and
    # scripts/audit_ambiguous_synonyms.py lists them for curator pinning.
    canonical_by_id = _vivc_canonical_by_id()
    records = []
    for file_slug, data in _load_vivc_records():
        vid = data.get("vivc_id")
        canonical = canonical_by_id.get(vid) if isinstance(vid, int) else None
        if canonical is None:
            canonical = GRAPE_ALIAS.get(file_slug, file_slug)
        records.append((canonical, data, file_slug, isinstance(vid, int) and bool(vid)))

    for canonical, data, _file_slug, _resolved in records:
        _claim_into(exact, data.get("prime_name"), canonical)
    _claim_vivc_synonyms(exact, records, official=True)
    # A canonical slug keeps its own name against another record's unflagged
    # synonym: the passport of Agostenga (#107), fetched in the sweep of
    # 2026-10-22, lists MALVASIA BIANCA too, and file order handed the
    # regulators' "Malvasia bianca B." to it on 29 Italian cards.
    for canonical, _data, file_slug, resolved in records:
        if resolved and canonical == file_slug:
            _claim_into(exact, _slug_to_search_surface(file_slug), canonical)
    # a name some country registers officially ("Carignano" in Italy) is a
    # variety name; the unflagged tier holds the place names
    curated = frozenset(exact)
    _claim_vivc_synonyms(exact, records, official=False)

    return Vocabulary(exact_index=exact, names=tuple(exact.keys()), curated=curated)


def is_curated_surface(token: str) -> bool:
    """True when `token` (colour code stripped) is a name the lexicon vouches
    for — a corpus slug, a GRAPE_ALIAS key, a VIVC prime name or a synonym VIVC
    flags as a country's official name — and not only an unflagged VIVC synonym. A parser uses it to tell a variety that shares
    its appellation's name ("Cesanese di Affile") from a place name VIVC keeps
    as a synonym ("Valtellina" → Veltliner rot, "Avola" → Ribolla gialla)."""
    cleaned = _prep_token(token)
    if not cleaned:
        return False
    vocab = _load_vocabulary()
    bare, _ = _strip_colour_letter(cleaned)
    return _normalise(cleaned) in vocab.curated or _normalise(bare) in vocab.curated


def _strip_colour_letter(token: str) -> tuple[str, str | None]:
    """Strip a trailing 1-2 letter INAO colour marker. Returns
    (bare_token, colour_name_or_None). Conservative: leaves the token
    alone when fewer than 3 chars of variety name would remain, and
    skips `<word> L.` shapes (Vitis vinifera L., …)."""
    if token.endswith((" L.", " L")):
        return token, None
    m = _COLOUR_LETTER_RE.search(token)
    if not m:
        return token, None
    bare = token[: m.start()].rstrip()
    if len(bare) < 3:
        return token, None
    return bare, _COLOUR_LETTER_TO_NAME.get(m.group(1))


def _prep_token(token: str) -> str:
    if not token:
        return ""
    cleaned = token.strip().strip(" .,;:«»\"'·“”()")
    return re.sub(r"\s+", " ", cleaned)


def match_variety(
    token: str,
    ambient_colour: str | None = None,
    source_pliego: str | None = None,
) -> MatchResult | None:
    """Match a candidate token against the variety vocabulary. Returns
    `None` on miss and logs the candidate to the in-process unknowns
    queue. The returned `name` preserves the source token's casing; the
    `colour` prefers explicit-suffix > ambient > `DEFAULT_COLOUR`."""
    if source_pliego is None:
        source_pliego = _CURRENT_PLIEGO[0]
    cleaned = _prep_token(token)
    if len(cleaned) < 3 or len(cleaned) > 80:
        if cleaned:
            _log_unknown(token, cleaned, cleaned, _normalise(cleaned), source_pliego)
        return None

    vocab = _load_vocabulary()
    full_key = _normalise(cleaned)
    if not full_key or len(full_key) < 3 or full_key in _BANNED_SURFACES:
        return None

    if full_key in vocab.exact_index:
        canon = vocab.exact_index[full_key]
        return MatchResult(
            slug=canon,
            name=cleaned,
            colour=ambient_colour or DEFAULT_COLOUR.get(canon, ""),
            method="exact",
        )

    bare, explicit_colour = _strip_colour_letter(cleaned)
    bare_key = _normalise(bare) if bare != cleaned else full_key
    if bare_key != full_key and bare_key in vocab.exact_index:
        canon = vocab.exact_index[bare_key]
        name = bare
        qualified = COLOUR_QUALIFIED_SLUGS.get((canon, explicit_colour or ""))
        if qualified:
            canon, adjective = qualified
            name = f"{bare} {adjective}"
        return MatchResult(
            slug=canon,
            name=name,
            colour=explicit_colour or ambient_colour or DEFAULT_COLOUR.get(canon, ""),
            method="exact-after-colour-strip",
        )

    # Hyphenated-pair fallback for tokens like "TEMPRANILLO-CENCIBEL" or
    # "MACABEO-VIURA" that the chunk splitter left intact (no spaces
    # around the hyphen). Try each side as an independent variety; the
    # first piece that exact-matches wins. This catches synonym-pair
    # cells in OJ-tabular HTML before the fuzzy fallback inflates a
    # short-word overlap into a false positive. Each piece is tried
    # both as-is and after stripping a trailing colour-letter suffix —
    # IT documenti unici list synonyms as "Pinot bianco B. - Pinot",
    # where the head carries the colour code that must be peeled off
    # before the vocabulary lookup catches the canonical Italian name.
    if "-" in bare or "–" in bare or "—" in bare:
        for piece in re.split(r"\s*[-–—]\s*", bare):
            piece = piece.strip(" .,;:«»\"'·“”()")
            if len(piece) < 3:
                continue
            piece_bare, piece_colour = _strip_colour_letter(piece)
            for variant in (piece, piece_bare) if piece_bare != piece else (piece,):
                v_key = _normalise(variant)
                if not v_key or len(v_key) < 3 or v_key in _BANNED_SURFACES:
                    continue
                if v_key in vocab.exact_index:
                    canon = vocab.exact_index[v_key]
                    return MatchResult(
                        slug=canon,
                        name=variant,
                        colour=(
                            explicit_colour or piece_colour
                            or ambient_colour or DEFAULT_COLOUR.get(canon, "")
                        ),
                        method="exact-after-hyphen-split",
                    )

    candidate_key = bare_key if bare != cleaned else full_key
    candidate_name = bare if bare != cleaned else cleaned
    if len(candidate_key) < 3 or candidate_key in _BANNED_SURFACES:
        _log_unknown(token, cleaned, candidate_name, candidate_key, source_pliego)
        return None

    best = process.extractOne(
        candidate_key,
        vocab.names,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=_FUZZY_CUTOFF,
    )
    if best is not None and _fuzzy_passes_sanity(candidate_key, best[0], best[1]):
        match_name, score, _idx = best
        canon = vocab.exact_index[match_name]
        return MatchResult(
            slug=canon,
            name=candidate_name,
            colour=explicit_colour or ambient_colour or DEFAULT_COLOUR.get(canon, ""),
            method=f"fuzzy:{int(score)}",
        )

    _log_unknown(token, cleaned, candidate_name, candidate_key, source_pliego)
    return None


def exact_match(token: str, ambient_colour: str | None = None) -> MatchResult | None:
    """`match_variety` restricted to its exact paths, and silent: a miss is
    not logged to the unknowns queue. For a reader testing a *hypothesis*
    — two halves of a wrapped name joined, an Article 1 varietal type —
    where a miss is the expected answer, not a lexicon gap."""
    cleaned = _prep_token(token)
    if len(cleaned) < 3 or len(cleaned) > 80:
        return None
    vocab = _load_vocabulary()
    full_key = _normalise(cleaned)
    if full_key and len(full_key) >= 3 and full_key not in _BANNED_SURFACES \
            and full_key in vocab.exact_index:
        canon = vocab.exact_index[full_key]
        return MatchResult(
            slug=canon, name=cleaned,
            colour=ambient_colour or DEFAULT_COLOUR.get(canon, ""), method="exact",
        )
    bare, explicit_colour = _strip_colour_letter(cleaned)
    bare_key = _normalise(bare) if bare != cleaned else full_key
    if bare_key != full_key and len(bare_key) >= 3 and bare_key not in _BANNED_SURFACES \
            and bare_key in vocab.exact_index:
        canon = vocab.exact_index[bare_key]
        return MatchResult(
            slug=canon, name=bare,
            colour=explicit_colour or ambient_colour or DEFAULT_COLOUR.get(canon, ""),
            method="exact-after-colour-strip",
        )
    return None


def match_roster_cell(
    token: str,
    ambient_colour: str | None = None,
    source_pliego: str | None = None,
) -> MatchResult | None:
    """`match_variety` for a token the reader knows to be a whole cell of a
    variety table (the SK §f Odroda column): a banned colour word that is
    also a registered cultivar (`COLOUR_WORD_VARIETIES` — "Rosa", VIVC
    #22422) binds here and nowhere else."""
    key = _normalise(_prep_token(token))
    slug = COLOUR_WORD_VARIETIES.get(key)
    if slug is not None:
        return MatchResult(
            slug=slug, name=_prep_token(token),
            colour=ambient_colour or DEFAULT_COLOUR.get(slug, ""), method="exact-roster-cell",
        )
    return match_variety(token, ambient_colour, source_pliego)


def _fuzzy_passes_sanity(candidate_key: str, match_name: str, score: float) -> bool:
    """Reject fuzzy matches likely to be false positives.

    `token_sort_ratio` at the 85-94 range frequently scores a name + 1-2
    leading-or-trailing letters against an unrelated lexicon entry —
    `pergolin` (Slovenian/Friulian native) hit `spergolina` (a sauvignon
    synonym) at 88.9%. Both span the cutoff because the longer name
    contains the candidate as a substring after a single-char prefix.

    Rule: for fuzzy matches below 95, the first non-space character of
    the candidate and the matched name must agree. Above 95, allow
    first-char mismatches — that's the score range where dropping a
    leading vowel (`aleatico` ↔ `leatico`) is a real spelling drift.

    This catches the prefix-shift class while preserving every typo
    fold I've seen in the corpus (the FR cahier typos all keep the
    first letter — `chardonay` ↔ `chardonnay`, `cabarnet` ↔
    `cabernet`).

    A name and its match that both carry numbers must carry the same ones,
    at any score: "Incrocio Manzoni 2-14" is not 2-15, "Gm 324-58" not
    Hibernal's 322-58 (sweep of 2026-10-22). A number on one side only — a
    footnote ("Merlot. 3"), a share ("Corvina veronese 35") — is left to the
    score.

    Below 95 the candidate must also carry five letters or more: a four-letter
    word scores 88 against any five-letter name that contains it ("doña", the
    wrapped half of Extremadura's "Doña ⏎ Blanca", against Razaki's synonym
    "Donna")."""
    # joined, so "6.013" and "6.0.13" (Manzoni bianco) count as the same number
    cand_digits = "".join(re.findall(r"\d", candidate_key))
    match_digits = "".join(re.findall(r"\d", match_name))
    if cand_digits and match_digits and cand_digits != match_digits:
        return False
    if score >= 95:
        return True
    if len(re.findall(r"[^\W\d_]", candidate_key)) < 5:
        return False
    cand = candidate_key.lstrip()
    matched = match_name.lstrip()
    if not cand or not matched:
        return False
    return cand[0] == matched[0]


def _log_unknown(
    original: str,
    cleaned: str,
    bare: str,
    nkey: str,
    source_pliego: str | None,
) -> None:
    vocab = _load_vocabulary()
    best = process.extractOne(nkey, vocab.names, scorer=fuzz.token_sort_ratio)
    fuzzy_best = None
    if best is not None:
        match_name, score, _idx = best
        fuzzy_best = [vocab.exact_index[match_name], int(score)]
    key = f"{source_pliego or ''}::{nkey}"
    if key in _UNKNOWNS.seen:
        return
    _UNKNOWNS.seen[key] = {
        "pliego_slug": source_pliego,
        "token": original,
        "cleaned": cleaned,
        "bare": bare,
        "normalised": nkey,
        "fuzzy_best": fuzzy_best,
        "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def flush_unknowns_queue(out_path: Path) -> int:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidates": sorted(
            _UNKNOWNS.seen.values(),
            key=lambda r: (r.get("pliego_slug") or "", r.get("normalised") or ""),
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(_UNKNOWNS.seen)


def reset_unknowns_queue() -> None:
    _UNKNOWNS.seen.clear()


def vocabulary_size() -> int:
    return len(_load_vocabulary().exact_index)


def preheat_vocabulary() -> int:
    """Force the vocabulary cache to load now. Use at the start of an
    extractor that wipes its own `<country>/cahier-extracted/` or
    `pliegos-extracted/` dir before processing — the rmtree blanks the
    cross-corpus contribution that the canonical-by-vivc-id rank relies
    on, so the cache must be locked while disk is still in baseline
    state. Returns the vocabulary size for telemetry."""
    return vocabulary_size()
