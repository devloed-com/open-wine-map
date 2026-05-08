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
from _lib.wiki import is_grape_summary  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
OUT_DIR = ROOT / "raw" / "wikipedia" / "grapes"
MANIFEST = OUT_DIR / "manifest.json"
OVERRIDES_FILE = ROOT / "raw" / "wikipedia" / "grape_overrides.json"
LOCALES = ("fr", "en", "es", "nl")

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)
REST_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"

# Per-locale disambiguation suffix used by Wikipedia for grape varieties that
# share a name with a commune / town / other entity (e.g. `Chardonnay` is a
# commune in fr.wikipedia; the grape lives at `Chardonnay (cépage)`).
DISAMBIG = {"fr": "cépage", "en": "grape", "es": "uva", "nl": "druif"}

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
    """Scan extracted cahiers, return {slug: display_name}."""
    slugs: dict[str, str] = {}
    for jp in EXTRACTED.glob("*.json"):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text())
        for d in (rec.get("grapes") or {}).get("details") or []:
            s = d.get("slug")
            if s:
                slugs.setdefault(s, d.get("name", s))
    return slugs


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


def fetch_summary(session: requests.Session, lang: str, slug: str) -> dict:
    """Try `<Title>_(<disambig>)` first (the canonical Wikipedia path for a
    grape that shares its name with a place), fall back to the bare title.
    Reject results whose description suggests a commune/village/river."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_lang = (LANG_OVERRIDES or {}).get(lang, {}).get(slug)
    base = by_lang or SLUG_OVERRIDES.get(slug) or slug_to_title(slug)
    base = base.replace(" ", "_")
    suffix = DISAMBIG.get(lang)
    candidates = []
    # If we already have a precise per-locale override, trust it (skip the
    # speculative `_(disambig)` suffix attempt).
    if by_lang:
        candidates.append(base)
    else:
        if suffix:
            candidates.append(f"{base}_({suffix})")
        candidates.append(base)

    last_data: dict | None = None
    for title in candidates:
        data = _try_one(session, lang, title)
        if data is None:
            continue
        last_data = data
        if looks_like_grape(lang, data):
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
                "fetched_at": now,
            }
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
