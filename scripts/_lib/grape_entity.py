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
  2. VIVC surfaces (prime + synonyms), deduped by `vivc_id`. When
     several by-slug files share a vivc_id, prefer the slug that's
     already in the corpus, then the slug whose normalised form matches
     the prime name, then the shortest.
  3. GRAPE_ALIAS keys as space-separated surfaces.

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
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS, slugify  # noqa: E402,F401

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
_COLOUR_LETTER_RE = re.compile(
    r"(?<=[A-Za-zàâäéèêëîïôöùûüçășțşţáíóúőűñõ"
    r"α-ωάέήίόύώϊϋΐΰ"
    # SK/CZ: ě č ř ť ď ň ů ľ ŕ ô ž š ý — both lower + upper forms.
    r"ěčřťďňůľŕôžšýĚČŘŤĎŇŮĽŔÔŽŠÝ])"
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
    "seibel",
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


@lru_cache(maxsize=1)
def _load_vocabulary() -> Vocabulary:
    exact: dict[str, str] = {}

    for slug in sorted(_clean_corpus_slugs()):
        key = _normalise(_slug_to_search_surface(slug))
        if len(key) < 3 or key in _BANNED_SURFACES:
            continue
        exact.setdefault(key, slug)

    # GRAPE_ALIAS keys are curator-verified disambiguations of names that
    # are otherwise ambiguous across VIVC (e.g. "MOSCATEL" is a synonym
    # of nine VIVC entries; the alias pin says it's `muscat-d-alexandrie`
    # in our corpus). Apply BEFORE VIVC so the alias wins.
    for alias_key, canonical in GRAPE_ALIAS.items():
        key = _normalise(_slug_to_search_surface(alias_key))
        if len(key) < 3 or key in _BANNED_SURFACES:
            continue
        exact.setdefault(key, GRAPE_ALIAS.get(canonical, canonical))

    canonical_by_id = _vivc_canonical_by_id()
    for file_slug, data in _load_vivc_records():
        vid = data.get("vivc_id")
        canonical = canonical_by_id.get(vid) if isinstance(vid, int) else None
        if canonical is None:
            canonical = GRAPE_ALIAS.get(file_slug, file_slug)
        prime = data.get("prime_name")
        if isinstance(prime, str) and prime:
            key = _normalise(prime)
            if len(key) >= 3 and key not in _BANNED_SURFACES:
                exact.setdefault(key, canonical)
        for syn in data.get("synonyms") or []:
            sname = syn.get("name") if isinstance(syn, dict) else None
            if not isinstance(sname, str) or not sname:
                continue
            key = _normalise(sname)
            if len(key) < 3 or key in _BANNED_SURFACES:
                continue
            exact.setdefault(key, canonical)

    return Vocabulary(exact_index=exact, names=tuple(exact.keys()))


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
        return MatchResult(
            slug=canon,
            name=bare,
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
    `cabernet`)."""
    if score >= 95:
        return True
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
