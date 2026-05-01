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


def load_aires() -> dict[str, set[str]]:
    """Return {normalized_appellation_name: {insee_code, …}} merging both CSVs.

    The same commune can appear under several aire labels (Bordeaux + a
    sub-appellation, for instance) — this maps each appellation label to
    the union of its INSEE codes regardless.
    """
    out: dict[str, set[str]] = defaultdict(set)
    raw_to_norm: dict[str, str] = {}

    for path in (AOC_CSV, IGP_CSV):
        if not path.exists():
            continue
        with path.open(encoding="latin-1") as f:
            rd = csv.DictReader(f, delimiter=";")
            for row in rd:
                app = (row.get("Aire géographique") or "").strip()
                ci = (row.get("CI") or "").strip()
                if not app or not ci:
                    continue
                key = _normalize(app)
                raw_to_norm.setdefault(key, app)
                out[key].add(ci)

    return dict(out)


def lookup(aires: dict[str, set[str]], name: str) -> set[str] | None:
    """Match an arbitrary appellation `name` against the loaded aires map.

    Tries exact normalized match first, then a substring fallback so we
    pick up "Champagne grand cru" → "Champagne" if the explicit row is
    missing (rare).
    """
    key = _normalize(name)
    if key in aires:
        return aires[key]
    # Substring fallback in either direction. We require length≥6 to
    # avoid spurious matches (a 3-letter "Cot" name could substring into
    # dozens of unrelated entries).
    if len(key) < 6:
        return None
    candidates = [k for k in aires if key in k or k in key]
    if len(candidates) == 1:
        return aires[candidates[0]]
    return None
