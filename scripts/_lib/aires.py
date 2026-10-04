"""Loader for INAO's authoritative AOC × commune lookup tables.

Two CSVs (raw/inao/aoc-aop-aires-communes.csv + igp-aires-communes.csv)
list every commune participating in every appellation, keyed by the INSEE
`code commune insee` (CI) and grouped by the AOC/IGP name (`Aire
géographique`). They're the canonical source — far more complete than
cahier-text extraction, which fails entirely for AOCs whose cahier defers
to legal references (e.g. Champagne's 1919 law) instead of enumerating
communes.

Files are latin-1 encoded with `;` delimiters (the standard French CSV
convention; note the `Département` and `Aire géographique` headers carry
diacritics).
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AOC_CSV = ROOT / "raw" / "inao" / "aoc-aop-aires-communes.csv"
IGP_CSV = ROOT / "raw" / "inao" / "igp-aires-communes.csv"
SUPPLEMENTS_JSON = Path(__file__).resolve().parent / "aires_supplements.json"


def _normalize(s: str) -> str:
    """Loose match key used to match AOC names across data sources."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def load_aires(supplements: bool = True) -> dict[str, dict[str, set[str]]]:
    """Return {normalized_appellation_name: {IDA: {insee_code, …}}}.

    INAO's aires-communes CSV groups commune rows by the human-readable
    "Aire géographique" label, but a label can recur across secteurs —
    notably "Valençay", which is both a wine AOC and a chèvre AOP whose
    commune list is much wider. We segment by the per-aire `IDA` so the
    consumer can disambiguate; `lookup` then picks the right IDA against
    a cahier hint, falling back to the full union when there's nothing
    to disambiguate against.

    The curator supplements (`apply_supplements`) are folded in unless
    `supplements=False`, so every consumer — stage 04's polygons, the
    parcellaire-gap audit — reads the same aire.
    """
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for path in (AOC_CSV, IGP_CSV):
        if not path.exists():
            continue
        with path.open(encoding="latin-1") as f:
            rd = csv.DictReader(f, delimiter=";")
            for row in rd:
                app = (row.get("Aire géographique") or "").strip()
                ci = (row.get("CI") or "").strip()
                ida = (row.get("IDA") or "").strip() or "_"
                if not app or not ci:
                    continue
                key = _normalize(app)
                out[key][ida].add(ci)
                if key not in _CSV_ALIAS_KEYS:
                    _CSV_ALIAS_KEYS[key] = {
                        _normalize(part) for part in re.split(r"\s+ou\s+|\s+et\s+|,", app)
                    } - {key, ""}

    aires = {k: dict(v) for k, v in out.items()}
    if supplements:
        apply_supplements(aires)
    return aires


def load_aire_supplements(path: Path = SUPPLEMENTS_JSON) -> dict[str, dict]:
    """The checked-in pins of `aires_supplements.json`, keyed by record slug."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("__")}


def apply_supplements(
    aires: dict[str, dict[str, set[str]]], pins: dict[str, dict] | None = None
) -> list[dict]:
    """Add to `aires`, in place, the communes a homologated cahier lists and
    the CSV lacks. INAO's CSV rows can be a decade older than the cahier in
    force (IGP Cévennes: rows of 2012, Gard only; the 2024 cahier adds 40
    Lozère communes), and nothing in the CSV says so — hence a cited pin per
    record rather than a parse of every cahier. Returns one status row per
    pin: `added` (INSEE codes folded in), `stale` (pinned codes the CSV
    carries again — not added, the pin wants re-verifying) and `unbound`
    (the pin's aire / IDA is not in the CSV: nothing is added)."""
    report: list[dict] = []
    for slug, pin in (load_aire_supplements() if pins is None else pins).items():
        bucket = aires.get(_normalize(pin["aire"]), {}).get(pin["ida"])
        row = {"slug": slug, "aire": pin["aire"], "added": [], "stale": []}
        row["unbound"] = bucket is None
        if bucket is not None:
            row["stale"] = sorted(c for c in pin["communes"] if c in bucket)
            row["added"] = sorted(c for c in pin["communes"] if c not in bucket)
            bucket.update(row["added"])
        report.append(row)
    return report


def load_aires_departements() -> dict[str, Counter]:
    """Return {normalized_appellation_name: Counter(DÉPARTEMENT → commune rows)}
    over both CSVs, all IDAs of a name pooled (a wine AOC and the cheese AOP
    that shares its name sit in the same départements). The `Département`
    column is INAO's own upper-case ASCII spelling ("PYRENEES-ORIENTALES",
    "COTE-D'OR"); it is what `fr_wine_region.derive_wine_region` reads to
    place a record whose comité régional names no wine region (every IGP,
    a few AOCs) or spans two (SUD-OUEST holds Bordeaux, PROVENCE-CORSE
    holds Corsica)."""
    out: dict[str, Counter] = defaultdict(Counter)
    for path in (AOC_CSV, IGP_CSV):
        if not path.exists():
            continue
        with path.open(encoding="latin-1") as f:
            rd = csv.DictReader(f, delimiter=";")
            for row in rd:
                app = (row.get("Aire géographique") or "").strip()
                dept = (row.get("Département") or "").strip().upper()
                if not app or not dept:
                    continue
                out[_normalize(app)][dept] += 1
    return dict(out)


def lookup_departements(index: dict[str, Counter], name: str) -> Counter:
    """The département profile of `name`'s aire, resolved with the same
    exact → near-exact → single-substring ladder as `lookup` (so a record
    binds to the same CSV name for its région as for its polygon). Empty
    Counter when nothing binds."""
    key = _resolve_key(index, name)
    return index[key] if key else Counter()


# normalised CSV aire name → the normalised alias parts of its raw label
# ("Pouilly-Fumé ou Blanc Fumé de Pouilly et Pouilly-sur-Loire" → {pouillyfume,
# blancfumedepouilly, pouillysurloire}), filled by `load_aires`. A record name
# that sits inside a longer CSV name binds only when it is one of these parts.
_CSV_ALIAS_KEYS: dict[str, set[str]] = {}


def _resolve_key(aires: dict, name: str) -> str | None:
    """The CSV name `name` binds to: exact, then near-exact (a source typo),
    then — for a SIQO 'X ou Y' register name — the exact row of one of its
    aliases ("Moulis ou Moulis-en-Médoc" → "Moulis"; the substring step below
    sees two candidates there and binds nothing), then the single CSV name
    that contains or is contained in it ("Champagne grand cru" → "Champagne")."""
    key = _normalize(name)
    if key in aires:
        return key
    if len(key) < 6:
        return None
    near = _near_exact(key, aires)
    if near is not None:
        return near
    if " ou " in name:
        hits = {k for k in (_normalize(part) for part in name.split(" ou ")) if k in aires}
        if len(hits) == 1:
            return hits.pop()
    # A short CSV name inside a long record name binds only as a whole word
    # of it: "anjou" in "Rosé d'Anjou", not "gard" in "Euskal Sagardoa" (which
    # drew the Basque cider over the Gard until 2026-09-26). The other
    # direction — the record name inside a longer CSV name — binds only when
    # the record is one of the CSV label's alias parts ("Pouilly-sur-Loire"
    # in "Pouilly-Fumé ou Blanc Fumé de Pouilly et Pouilly-sur-Loire"), never
    # when it is a trailing word of another appellation: the new AOC
    # "Montpeyroux" is not the DGC aire "Languedoc Montpeyroux" (2 communes
    # against the cahier's 4, 2026-10-04). An index built without the CSV
    # (tests) carries no alias parts and keeps the plain containment test.
    words = {_normalize(w) for w in re.split(r"[^\w]+", name)}
    parts = {_normalize(p) for p in re.split(r"\s+ou\s+|\s+et\s+|,", name)} - {""}
    candidates = [
        k for k in aires
        if (key in k and (not _CSV_ALIAS_KEYS or parts <= _CSV_ALIAS_KEYS.get(k, set())))
        or (k in key and (len(k) >= 6 or k in words))
    ]
    return candidates[0] if len(candidates) == 1 else None


def _pick_ida(idas: dict[str, set[str]], hint: set[str] | None) -> set[str]:
    """Pick the best IDA bucket given an optional cahier-derived hint.

    With no hint, return the union of all IDAs (legacy behaviour). With
    a non-empty hint, score each IDA by how well its commune set is
    covered by the hint (`|hint ∩ aires| / |aires|`) and pick the best
    bucket — the wine-cahier set will heavily overlap the wine IDA and
    barely overlap the cheese IDA. Buckets with zero overlap are
    discarded; if every bucket has zero overlap (cahier extraction was
    empty or off), fall back to the union.
    """
    if not hint:
        return set().union(*idas.values())
    best_ida: str | None = None
    best_score = 0.0
    best_overlap = 0
    for ida, communes in idas.items():
        if not communes:
            continue
        overlap = len(hint & communes)
        if overlap == 0:
            continue
        score = overlap / len(communes)
        if score > best_score or (score == best_score and overlap > best_overlap):
            best_ida = ida
            best_score = score
            best_overlap = overlap
    if best_ida is not None:
        return idas[best_ida]
    return set().union(*idas.values())


def lookup(
    aires: dict[str, dict[str, set[str]]],
    name: str,
    cahier_insee: set[str] | None = None,
) -> set[str] | None:
    """Match an arbitrary appellation `name` against the loaded aires map.

    Tries exact normalized match first, then a substring fallback so we
    pick up "Champagne grand cru" → "Champagne" if the explicit row is
    missing (rare). When the matched name carries multiple IDAs (e.g.
    a wine AOC sharing its name with a cheese AOP), `cahier_insee`
    disambiguates — pass the INSEE set the cahier-text extraction
    resolved for this record so we keep the wine IDA and drop the
    unrelated one.
    """
    key = _resolve_key(aires, name)
    return _pick_ida(aires[key], cahier_insee) if key else None


def _near_exact(key: str, aires: dict[str, dict[str, set[str]]]) -> str | None:
    """The one CSV name a character or two away from `key` — a source
    typo, not a different appellation. SIQO spells "Calvados Domfontais"
    where the aires CSV (and the cahier, and the EU register) say
    "Calvados Domfrontais"; without this step the substring fallback
    below bound the record to the whole "Calvados" aire — 1,573
    communes across eight départements for a 112-commune appellation.
    Two candidates within reach, or none, bind nothing here."""
    from rapidfuzz import fuzz

    hits = [
        k for k in aires
        if abs(len(k) - len(key)) <= 2 and fuzz.ratio(key, k) >= 95
    ]
    return hits[0] if len(hits) == 1 else None
