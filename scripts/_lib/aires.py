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
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AOC_CSV = ROOT / "raw" / "inao" / "aoc-aop-aires-communes.csv"
IGP_CSV = ROOT / "raw" / "inao" / "igp-aires-communes.csv"


def _normalize(s: str) -> str:
    """Loose match key used to match AOC names across data sources."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def load_aires() -> dict[str, dict[str, set[str]]]:
    """Return {normalized_appellation_name: {IDA: {insee_code, …}}}.

    INAO's aires-communes CSV groups commune rows by the human-readable
    "Aire géographique" label, but a label can recur across secteurs —
    notably "Valençay", which is both a wine AOC and a chèvre AOP whose
    commune list is much wider. We segment by the per-aire `IDA` so the
    consumer can disambiguate; `lookup` then picks the right IDA against
    a cahier hint, falling back to the full union when there's nothing
    to disambiguate against.
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

    return {k: dict(v) for k, v in out.items()}


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
    key = _normalize(name)
    if key in aires:
        return _pick_ida(aires[key], cahier_insee)
    if len(key) < 6:
        return None
    candidates = [k for k in aires if key in k or k in key]
    if len(candidates) == 1:
        return _pick_ida(aires[candidates[0]], cahier_insee)
    return None
