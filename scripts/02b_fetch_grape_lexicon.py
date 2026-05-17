"""Fetch Wikipedia summaries for grape varieties used in the AOC corpus.

Pipeline stage 02b — adds an external public-source track (Wikipedia, CC-BY-SA
4.0) for the grape lexicon shown in the map sidepanel. Per CLAUDE.md the
cahier corpus stays INAO/JORF-only; Wikipedia is admitted *only* for grape
varietal descriptions, and each cached entry records `revision_id`,
`fetched_at`, `page_url`, `license` so the UI can attribute correctly.

Reads:  raw/inao/cahier-extracted/*.json  (collects unique grape slugs)
Writes: raw/wikipedia/grapes/<lang>/<slug>.json
        raw/wikipedia/grapes/manifest.json

Re-runnable: cached entries are kept; pass --refresh to re-fetch everything.
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
LOCALES = ("fr", "en", "es", "nl", "pt")

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
REST_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"

# Per-locale disambiguation suffix used by Wikipedia for grape varieties that
# share a name with a commune / town / other entity (e.g. `Chardonnay` is a
# commune in fr.wikipedia; the grape lives at `Chardonnay (cépage)`).
DISAMBIG = {"fr": "cépage", "en": "grape", "es": "uva", "nl": "druif", "pt": "casta"}

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
    LANG_OVERRIDES = json.loads(OVERRIDES_FILE.read_text())

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
    rec = json.loads(path.read_text())
    _VIVC_CACHE[slug] = rec
    return rec


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
    lang: str, slug: str, data: dict, matched_via: str, now: str
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
        "license": "CC-BY-SA-4.0",
        "matched_via": matched_via,
        "fetched_at": now,
    }


def fetch_summary(session: requests.Session, lang: str, slug: str) -> dict:
    """Walk the candidate chain for (slug, lang) until we hit an article
    that `is_grape_summary` accepts. Reject anything else."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidates = _build_candidates(lang, slug)
    last_data: dict | None = None
    for title, matched_via in candidates:
        data = _try_one(session, lang, title)
        if data is None:
            continue
        last_data = data
        if looks_like_grape(lang, data):
            return _summary_record(lang, slug, data, matched_via, now)
    if last_data is not None:
        return {
            "slug": slug,
            "lang": lang,
            "error": "not_grape_topic",
            "rejected_title": last_data.get("title"),
            "fetched_at": now,
        }
    return {"slug": slug, "lang": lang, "missing": True, "fetched_at": now}


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
        "license": "CC-BY-SA-4.0",
        "source": "wikipedia.org REST summary API",
        "locales": {},
    }
    for lang in args.locales:
        lang_dir = OUT_DIR / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        ok = miss = err = cached = 0
        for slug in tqdm(sorted(slugs), desc=f"wikipedia/{lang}", leave=False):
            cache = lang_dir / f"{slug}.json"
            if cache.exists() and not args.refresh:
                cached += 1
                continue
            result = fetch_summary(session, lang, slug)
            cache.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            if result.get("missing"):
                miss += 1
            elif result.get("error"):
                err += 1
            else:
                ok += 1
            time.sleep(args.throttle)
        manifest["locales"][lang] = {"ok": ok, "miss": miss, "err": err, "cached": cached}
        print(f"[02b/{lang}] new ok={ok} miss={miss} err={err} cached={cached}", file=sys.stderr)

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"[02b] manifest: {MANIFEST.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
