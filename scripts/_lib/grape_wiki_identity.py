"""Is a cached Wikipedia grape entry still the pill's own article?

Stage 02b finds a grape's article by its slug-derived title and, when that
misses, by walking the slug's VIVC passport: the prime name, the synonyms, a
donor slug that carries the same variety number. Such a match is only as good
as the passport it was made through, and an `ok` cache entry is never
re-fetched — so when a slug's VIVC pin is corrected or withdrawn the article
found through the old passport stays on the pill. Pugnitello, pinned `false`
since 2026-10-25, still opened the Montepulciano article it had borrowed as
"the same number"; Picardan (now #527) the Bourboulenc one (2026-11-14: 18
slugs, 498 pills).

`passport_match_is_stale` is the one test, shared by stage 04 (the entry is
not shown), the 02b fetcher (the entry is due for a re-fetch) and
`audit_grape_wikipedia.py`. A match made by the slug's own title (`primary`,
a legacy entry without `matched_via`) or by a curator pin (`override`) names
the article itself and is never stale by this rule — the audit's title test
covers those.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from unidecode import unidecode

ROOT = Path(__file__).resolve().parents[2]
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"
VIVC_OVERRIDES = ROOT / "raw" / "vivc" / "slug_overrides.json"

# `matched_via` values that mean "found through the VIVC passport".
PASSPORT_ROUTES = ("shared-vivc:", "vivc-prime", "vivc-synonym")


@lru_cache(maxsize=1)
def vivc_records() -> dict[str, dict]:
    """slug → its raw/vivc/by-slug record (resolved or not)."""
    out: dict[str, dict] = {}
    if not VIVC_BY_SLUG.exists():
        return out
    for f in VIVC_BY_SLUG.glob("*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out[rec.get("slug") or f.stem] = rec
    return out


@lru_cache(maxsize=1)
def current_vivc_ids() -> dict[str, int]:
    return {
        slug: rec["vivc_id"] for slug, rec in vivc_records().items()
        if isinstance(rec.get("vivc_id"), int) and not isinstance(rec.get("vivc_id"), bool)
    }


@lru_cache(maxsize=1)
def withdrawn_slugs() -> frozenset[str]:
    """Slugs a curator pinned `vivc_id: false` — VIVC has no entry for the
    name, or files it under several primes."""
    if not VIVC_OVERRIDES.exists():
        return frozenset()
    try:
        data = json.loads(VIVC_OVERRIDES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return frozenset()
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else data
    return frozenset(
        slug for slug, pin in entries.items()
        if isinstance(pin, dict) and pin.get("vivc_id") is False
    )


def consulted_vivc_id(record: dict) -> int | None:
    vid = (record.get("vivc_consulted") or {}).get("vivc_id")
    return vid if isinstance(vid, int) and not isinstance(vid, bool) else None


def passport_match_is_stale(
    record: dict, slug: str, *,
    current: dict[str, int] | None = None, withdrawn: frozenset[str] | None = None,
) -> bool:
    """True when `record` (a raw/wikipedia/grapes entry) was matched through a
    VIVC passport that is no longer the slug's: the slug resolves to another
    number now, or its pin was withdrawn. A slug that merely has no resolution
    yet keeps its entry — an unresolved slug is a gap, not a decision."""
    via = str(record.get("matched_via") or "")
    if not via.startswith(PASSPORT_ROUTES):
        return False
    consulted = consulted_vivc_id(record)
    if consulted is None:
        return False
    current = current_vivc_ids() if current is None else current
    now = current.get(slug)
    if now is not None:
        return now != consulted
    withdrawn = withdrawn_slugs() if withdrawn is None else withdrawn
    return slug in withdrawn


# ---- whose article is it? ---------------------------------------------------
#
# The second way a pill gets another grape's article: a VIVC synonym, or the
# slug's own title, that Wikipedia redirects to a better-known homonym.
# Chenanson's synonym VAALBLAAR STEIN is a South African name of Chenin blanc;
# Raffiat de Moncade's ROUSSELET redirects to Gewürztraminer; "Mollard"
# redirects to Carignan. The test: the article's title is none of the slug's
# own names and is the own name — slug or VIVC prime — of another slug that
# carries a different variety number.


def norm_title(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", unidecode(text or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def fold_umlaut(text: str) -> str:
    # VIVC writes ue / oe / ae for the German umlauts
    return re.sub(r"(?<=[aou])e", "", text)


def own_names(slug: str) -> set[str]:
    """The slug, and the prime name and synonyms of the passport it has."""
    names = {norm_title(slug)}
    rec = vivc_records().get(slug) or {}
    raw = [rec.get("prime_name"), rec.get("name"), rec.get("query")]
    raw += [s.get("name") for s in (rec.get("synonyms") or []) if isinstance(s, dict)]
    for name in raw:
        if name:
            names.update((norm_title(name), fold_umlaut(norm_title(name))))
    return names


@lru_cache(maxsize=1)
def _owner_index() -> dict[str, frozenset[tuple[str, int]]]:
    idx: dict[str, set[tuple[str, int]]] = {}
    for slug, vid in current_vivc_ids().items():
        idx.setdefault(norm_title(slug), set()).add((slug, vid))
        prime = (vivc_records().get(slug) or {}).get("prime_name")
        if prime:
            idx.setdefault(fold_umlaut(norm_title(prime)), set()).add((slug, vid))
    return {k: frozenset(v) for k, v in idx.items()}


def title_is_own(slug: str, title: str) -> bool:
    """The article is titled as the slug, as a name of its passport, or as the
    family the slug's name extends ("Grenache" for grenache-gris)."""
    t = norm_title(title)
    names = own_names(slug)
    tw, sw = set(t.split()), set(norm_title(slug).split())
    return bool(t) and (t in names or fold_umlaut(t) in names or tw <= sw or sw <= tw)


def article_is_anothers(slug: str, title: str) -> list[str]:
    """The slugs whose own article `title` is, when it is not this slug's: a
    slug with another variety number (any number, for a slug that has none)
    named by its slug or its VIVC prime. Empty when the title is one of this
    slug's own names."""
    if title_is_own(slug, title):
        return []
    t = norm_title(title)
    mine = current_vivc_ids().get(slug)
    idx = _owner_index()
    hits = idx.get(t, frozenset()) | idx.get(fold_umlaut(t), frozenset())
    return sorted({other for other, vid in hits if other != slug and vid != mine})
