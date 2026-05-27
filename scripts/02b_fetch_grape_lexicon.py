"""Fetch Wikipedia summaries for grape varieties used in the AOC corpus.

Pipeline stage 02b — adds an external public-source track (Wikipedia, CC-BY-SA
4.0) for the grape lexicon shown in the map sidepanel. Per CLAUDE.md the
cahier corpus stays INAO/JORF-only; Wikipedia is admitted *only* for grape
varietal descriptions, and each cached entry records `revision_id`,
`fetched_at`, `page_url`, `license` so the UI can attribute correctly.

Reads:  raw/inao/cahier-extracted/*.json  (collects unique grape slugs)
Writes: raw/wikipedia/grapes/<lang>/<slug>.json
        raw/wikipedia/grapes/manifest.json

Re-runnable: cached entries are kept. Negative cache entries (`missing` /
`error`) are auto-invalidated when their `vivc_consulted` fingerprint is
older than the current `raw/vivc/by-slug/<slug>.json` — picks up newly
populated VIVC synonyms without a full `--refresh`. Pass --refresh to
re-fetch every (slug, lang) regardless.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.grape_corpus import collect_grape_slugs as _collect_corpus  # noqa: E402
from _lib.wiki import is_grape_summary  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
OUT_DIR = ROOT / "raw" / "wikipedia" / "grapes"
MANIFEST = OUT_DIR / "manifest.json"
OVERRIDES_FILE = ROOT / "raw" / "wikipedia" / "grape_overrides.json"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"
LOCALES = ("fr", "en", "es", "nl", "pt", "it")

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
REST_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_LICENSE = "CC-BY-SA-4.0"

# Per-locale disambiguation suffix used by Wikipedia for grape varieties that
# share a name with a commune / town / other entity (e.g. `Chardonnay` is a
# commune in fr.wikipedia; the grape lives at `Chardonnay (cépage)`).
DISAMBIG = {"fr": "cépage", "en": "grape", "es": "uva", "nl": "druif", "pt": "casta",
            "it": "vitigno"}

# When VIVC's `official_in` flag matches the locale's country, that synonym
# is the regulator-aligned name in that locale's region and gets priority.
LOCALE_COUNTRY = {"fr": "FRANCE", "es": "SPAIN", "nl": "NETHERLANDS", "pt": "PORTUGAL"}

# Cap the number of VIVC-derived candidates per (slug, locale) — politeness
# to Wikipedia and a guard against pathological synonym fan-outs (Monastrell
# has 131 synonyms).
VIVC_CANDIDATE_CAP = 20

# Cahier slugs whose canonical Wikipedia title is something else entirely.
# Used in all locales (Wikipedia keeps these titles consistent across langs).
SLUG_OVERRIDES = {
    "cot": "Malbec",
}

# Per-locale overrides loaded from `raw/wikipedia/grape_overrides.json`.
# Discovered automatically by `scripts/_lib/wiki_probe.py` (Wikipedia search +
# is_grape_summary validation), then stored verbatim. Hand-editable.
LANG_OVERRIDES: dict[str, dict[str, str]] = {}
if OVERRIDES_FILE.exists():
    LANG_OVERRIDES = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))

def slug_to_title(slug: str) -> str:
    """Best-effort title from kebab-case slug. Wikipedia REST follows redirects
    so capitalising the first segment is usually enough."""
    parts = slug.split("-")
    parts[0] = parts[0].capitalize()
    return "_".join(parts)


def looks_like_grape(lang: str, data: dict) -> bool:
    return is_grape_summary(lang, data.get("description", ""), data.get("extract", ""))


def collect_grape_slugs() -> dict[str, str]:
    """`{slug: display_name}` from FR cahiers + ES pliegos + PT cadernos.

    Delegates to `scripts/_lib/grape_corpus.py`, which exposes the same walk
    behind a richer return type (per-lang counts → dominant-cahier-lang
    index used by 02b_translate_grapes and stage 04)."""
    return {slug: entry["name"] for slug, entry in _collect_corpus().items()}


def _title_case_prime(prime: str) -> str:
    """`TEMPRANILLO TINTO` → `Tempranillo Tinto`. `str.title()` keeps the
    capital after apostrophes (`D'AUNIS` → `D'Aunis`) — a per-token
    `.capitalize()` collapses them to `D'aunis`."""
    return prime.title()


_VIVC_CACHE: dict[str, dict | None] = {}


def _load_vivc(slug: str) -> dict | None:
    """Return the by-slug VIVC record or None. Lazy + module-scope cache.
    Treats `resolved_via == "miss"` and ambiguous records (no `vivc_id`) as
    unresolved — we still use any candidate synonyms found in those records,
    but only via the primary `prime_name` field when one is set."""
    if slug in _VIVC_CACHE:
        return _VIVC_CACHE[slug]
    path = VIVC_BY_SLUG / f"{slug}.json"
    if not path.exists():
        _VIVC_CACHE[slug] = None
        return None
    rec = json.loads(path.read_text(encoding="utf-8"))
    _VIVC_CACHE[slug] = rec
    return rec


def _vivc_fingerprint(slug: str) -> dict | None:
    """Fingerprint of the VIVC record consulted by the synonym chain, or
    None when no VIVC record exists. Stored on each cache write so reruns
    can auto-invalidate stale negatives when VIVC arrives or changes."""
    rec = _load_vivc(slug)
    if not rec:
        return None
    return {"vivc_id": rec.get("vivc_id"), "fetched_at": rec.get("fetched_at")}


def _build_donor_index(lang_dir: Path) -> dict[int, dict]:
    """Per-locale `vivc_id → ok-record` index. Two cahier slugs that resolve
    to the same VIVC variety share the same Wikipedia article — once one is
    cached for a locale, every other synonym slug in that locale can reuse
    its `extract` / `wikipedia_title` / `page_url` / `revision_id` instead
    of round-tripping the REST API."""
    out: dict[int, dict] = {}
    for f in lang_dir.glob("*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("missing") or rec.get("error") or not rec.get("extract"):
            continue
        vivc = _load_vivc(f.stem)
        if not vivc or not vivc.get("vivc_id"):
            continue
        out.setdefault(vivc["vivc_id"], rec)
    return out


def _shared_record(slug: str, lang: str, donor: dict, vivc: dict | None, now: str) -> dict:
    """Re-shape a donor's wiki content under a new (slug, lang). The wiki
    payload (extract / title / page_url / revision_id) is verbatim; we
    record `matched_via: shared-vivc:<id>:<donor_slug>` so the audit can
    attribute reuse and `vivc_consulted` for the standard freshness check."""
    return {
        "lang": lang,
        "slug": slug,
        "wikipedia_title": donor.get("wikipedia_title"),
        "extract": donor.get("extract", ""),
        "description": donor.get("description", ""),
        "page_url": donor.get("page_url"),
        "revision_id": donor.get("revision_id"),
        "thumbnail": donor.get("thumbnail"),
        "license": WIKIPEDIA_LICENSE,
        "matched_via": f"shared-vivc:{vivc['vivc_id']}:{donor.get('slug')}",
        "vivc_consulted": vivc,
        "fetched_at": now,
    }


def _is_negative(cached: dict) -> bool:
    """Detect every negative-cache shape: current `missing` / `error` records
    and the legacy `not_grape: True` records written by older script
    versions before `error` was a structured field."""
    return bool(cached.get("missing") or cached.get("error") or cached.get("not_grape"))


def _cache_is_fresh(cached: dict, slug: str, donors: dict[int, dict] | None = None) -> bool:
    """`ok` records are never auto-invalidated — `is_grape_summary` already
    validated the match, so re-fetching only risks regression. Negative
    entries invalidate when either condition holds:
      • a donor for this slug's vivc_id is now available (donor-aware
        recovery can resolve negatives a prior run couldn't);
      • the VIVC fingerprint the cache consulted differs from the current
        one (newly populated synonyms widen the candidate chain).
    Pre-fingerprint legacy entries (no `vivc_consulted`) invalidate
    whenever any VIVC record now exists for the slug."""
    if not _is_negative(cached):
        return True
    if donors is not None:
        vivc = _load_vivc(slug)
        if vivc and vivc.get("vivc_id") in donors:
            return False
    consulted = cached.get("vivc_consulted")
    current = _vivc_fingerprint(slug)
    if consulted is None and current is None:
        return True
    if consulted is None or current is None:
        return False
    return consulted.get("fetched_at") == current.get("fetched_at")


def _vivc_candidates(slug: str, lang: str) -> list[tuple[str, str]]:
    """`[(candidate_title, matched_via), …]` for the VIVC synonym chain.
    Order: prime → priority synonyms (`official_in` matches the locale's
    country) → remaining synonyms by descending length. Capped at
    `VIVC_CANDIDATE_CAP`."""
    rec = _load_vivc(slug)
    if not rec or not rec.get("prime_name"):
        return []
    prime = _title_case_prime(rec["prime_name"])
    country = LOCALE_COUNTRY.get(lang)
    syns = rec.get("synonyms") or []

    priority: list[str] = []
    rest: list[str] = []
    for syn in syns:
        name = syn.get("name", "").strip()
        if not name:
            continue
        official = (syn.get("official_in") or "").upper()
        if country and country in official:
            priority.append(name)
        else:
            rest.append(name)
    rest.sort(key=len, reverse=True)

    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def push(title: str, via: str) -> None:
        norm = title.casefold()
        if norm in seen:
            return
        seen.add(norm)
        out.append((title, via))

    push(prime, "vivc-prime")
    for name in priority:
        push(_title_case_prime(name), f"vivc-synonym-official:{name}")
    for name in rest:
        push(_title_case_prime(name), f"vivc-synonym:{name}")
    return out[:VIVC_CANDIDATE_CAP]


def _try_one(session: requests.Session, lang: str, title: str) -> dict | None:
    url = REST_URL.format(lang=lang, title=title)
    try:
        r = session.get(url, timeout=15)
    except requests.RequestException:
        return None
    if r.status_code == 200:
        try:
            data = r.json()
        except ValueError:
            return None
        if data.get("type") not in ("disambiguation", "no-extract"):
            return data
    return None


def _build_candidates(lang: str, slug: str) -> list[tuple[str, str]]:
    """Ordered `[(title, matched_via), …]` candidate list per (slug, lang).

    1. The per-lang `LANG_OVERRIDES` title (curator-pinned), bare.
    2. The slug-derived title with `_(disambig)` suffix, then bare.
    3. The VIVC-derived chain: prime → priority synonyms → rest.

    `matched_via` records which path produced a successful hit; consumed by
    the audit script to attribute coverage gains to VIVC."""
    by_lang = (LANG_OVERRIDES or {}).get(lang, {}).get(slug)
    base = by_lang or SLUG_OVERRIDES.get(slug) or slug_to_title(slug)
    base = base.replace(" ", "_")
    suffix = DISAMBIG.get(lang)
    out: list[tuple[str, str]] = []
    if by_lang:
        out.append((base, "override"))
    else:
        if suffix:
            out.append((f"{base}_({suffix})", "primary-disambig"))
        out.append((base, "primary"))
    for title, via in _vivc_candidates(slug, lang):
        norm_title = title.replace(" ", "_")
        if suffix:
            out.append((f"{norm_title}_({suffix})", f"{via}-disambig"))
        out.append((norm_title, via))
    return out


def _summary_record(
    lang: str, slug: str, data: dict, matched_via: str, now: str, vivc: dict | None
) -> dict:
    return {
        "lang": lang,
        "slug": slug,
        "wikipedia_title": data.get("title"),
        "extract": data.get("extract", ""),
        "description": data.get("description", ""),
        "page_url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
        "revision_id": data.get("revision"),
        "thumbnail": (data.get("thumbnail") or {}).get("source"),
        "license": WIKIPEDIA_LICENSE,
        "matched_via": matched_via,
        "vivc_consulted": vivc,
        "fetched_at": now,
    }


def fetch_summary(session: requests.Session, lang: str, slug: str) -> dict:
    """Walk the candidate chain for (slug, lang) until we hit an article
    that `is_grape_summary` accepts. Reject anything else."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    vivc = _vivc_fingerprint(slug)
    candidates = _build_candidates(lang, slug)
    last_data: dict | None = None
    for title, matched_via in candidates:
        data = _try_one(session, lang, title)
        if data is None:
            continue
        last_data = data
        if looks_like_grape(lang, data):
            return _summary_record(lang, slug, data, matched_via, now, vivc)
    if last_data is not None:
        return {
            "slug": slug,
            "lang": lang,
            "error": "not_grape_topic",
            "rejected_title": last_data.get("title"),
            "vivc_consulted": vivc,
            "fetched_at": now,
        }
    return {
        "slug": slug,
        "lang": lang,
        "missing": True,
        "vivc_consulted": vivc,
        "fetched_at": now,
    }


def _fetch_locale(
    session: requests.Session, lang: str, slugs: list[str], *, refresh: bool, throttle: float
) -> dict[str, int]:
    lang_dir = OUT_DIR / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    donors = _build_donor_index(lang_dir)
    ok = miss = err = cached = revalidated = shared = 0
    for slug in tqdm(slugs, desc=f"wikipedia/{lang}", leave=False):
        cache = lang_dir / f"{slug}.json"
        if cache.exists() and not refresh:
            cached_data = json.loads(cache.read_text(encoding="utf-8"))
            if _cache_is_fresh(cached_data, slug, donors):
                cached += 1
                continue
            revalidated += 1
        result = _resolve_one(session, lang, slug, donors, throttle)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if result.get("missing"):
            miss += 1
        elif result.get("error"):
            err += 1
        else:
            ok += 1
            if str(result.get("matched_via", "")).startswith("shared-vivc:"):
                shared += 1
            else:
                _register_donor(donors, slug, result)
    return {
        "ok": ok, "miss": miss, "err": err,
        "cached": cached, "revalidated": revalidated, "shared": shared,
    }


def _resolve_one(
    session: requests.Session, lang: str, slug: str, donors: dict[int, dict], throttle: float
) -> dict:
    """Try the donor index first (free, no API call). On miss, fall back to
    the candidate-chain fetch — that path is the only one paying the
    `throttle` sleep."""
    vivc = _vivc_fingerprint(slug)
    if vivc and vivc.get("vivc_id") in donors:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return _shared_record(slug, lang, donors[vivc["vivc_id"]], vivc, now)
    result = fetch_summary(session, lang, slug)
    time.sleep(throttle)
    return result


def _register_donor(donors: dict[int, dict], slug: str, rec: dict) -> None:
    """A freshly-fetched `ok` record becomes a donor for later synonym slugs
    in the same locale. First-write-wins keeps the canonical donor stable
    (no thrash if multiple synonyms get fetched in sequence)."""
    vivc = _load_vivc(slug)
    if not vivc or not vivc.get("vivc_id"):
        return
    donors.setdefault(vivc["vivc_id"], rec)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.05, help="seconds between API calls")
    ap.add_argument("--locales", nargs="+", default=list(LOCALES))
    args = ap.parse_args()

    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/02_extract_cahiers.py first", file=sys.stderr)
        return 1

    slugs = collect_grape_slugs()
    print(
        f"[02b] {len(slugs)} unique grape slugs across {len(args.locales)} locales",
        file=sys.stderr,
    )

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_slugs": len(slugs),
        "license": WIKIPEDIA_LICENSE,
        "source": "wikipedia.org REST summary API",
        "locales": {},
    }
    for lang in args.locales:
        stats = _fetch_locale(session, lang, sorted(slugs), refresh=args.refresh, throttle=args.throttle)
        manifest["locales"][lang] = stats
        print(
            f"[02b/{lang}] new ok={stats['ok']} miss={stats['miss']} err={stats['err']} "
            f"cached={stats['cached']} revalidated={stats['revalidated']} "
            f"shared={stats['shared']}",
            file=sys.stderr,
        )

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[02b] manifest: {MANIFEST.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
