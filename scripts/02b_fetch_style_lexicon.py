"""Fetch Wikipedia summaries for distinctive wine styles.

Pipeline stage 02b — sister stage to `02b_fetch_grape_lexicon.py`. Adds an
external public-source track (Wikipedia, CC-BY-SA 4.0) for a curated subset
of style-pill keys whose UI tooltip is genuinely informative: distinctive
French and Spanish styles (vin jaune, crémant, vin doux naturel, vin de
paille, sélection de grains nobles, vendanges tardives, clairet, primeur,
vin de liqueur, fino, manzanilla, amontillado, oloroso, palo cortado,
rancio, mistela) plus the taxonomy interior-group nodes that records
actually carry (fortified, sparkling-quality, late-harvest, raisin-wine,
oxidative, generoso). Top-level buckets (red / white / rosé / sparkling /
sweet / other) and generic leaves (dry / tranquille) are intentionally
excluded — their Wikipedia pages read as general wine education and don't
warrant a tooltip.

Per CLAUDE.md the cahier corpus stays INAO/JORF-only; Wikipedia is admitted
as a bounded narrative layer for grape, AOC, and now style descriptions,
each cached entry recording `revision_id`, `fetched_at`, `page_url`,
`license` so the UI can attribute correctly.

Reads:  raw/wikipedia/style_overrides.json   (curated slug → per-locale title)
Writes: raw/wikipedia/styles/<lang>/<slug>.json
        raw/wikipedia/styles/manifest.json

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

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES_FILE = ROOT / "raw" / "wikipedia" / "style_overrides.json"
OUT_DIR = ROOT / "raw" / "wikipedia" / "styles"
MANIFEST = OUT_DIR / "manifest.json"
LOCALES = ("fr", "en", "es", "nl")

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)
REST_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"


def load_overrides() -> tuple[list[str], dict[str, dict[str, str]]]:
    if not OVERRIDES_FILE.exists():
        print(f"error: {OVERRIDES_FILE} missing", file=sys.stderr)
        sys.exit(1)
    data = json.loads(OVERRIDES_FILE.read_text())
    curated = list(data.get("_curated") or [])
    per_lang = {k: v for k, v in data.items() if not k.startswith("_")}
    return curated, per_lang


def fetch_summary(
    session: requests.Session,
    lang: str,
    slug: str,
    title: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    url = REST_URL.format(lang=lang, title=title.replace(" ", "_"))
    try:
        r = session.get(url, timeout=15)
    except requests.RequestException as e:
        return {"slug": slug, "lang": lang, "error": f"request_failed: {e}", "fetched_at": now}
    if r.status_code != 200:
        return {
            "slug": slug,
            "lang": lang,
            "missing": True,
            "status": r.status_code,
            "tried_title": title,
            "fetched_at": now,
        }
    try:
        data = r.json()
    except ValueError:
        return {"slug": slug, "lang": lang, "error": "bad_json", "fetched_at": now}
    if data.get("type") in ("disambiguation", "no-extract"):
        return {
            "slug": slug,
            "lang": lang,
            "error": data.get("type"),
            "tried_title": title,
            "fetched_at": now,
        }
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.05, help="seconds between API calls")
    ap.add_argument("--locales", nargs="+", default=list(LOCALES))
    args = ap.parse_args()

    curated, per_lang = load_overrides()
    if not curated:
        print("error: style_overrides.json has empty _curated list", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_slugs": len(curated),
        "curated": curated,
        "license": "CC-BY-SA-4.0",
        "source": "wikipedia.org REST summary API",
        "locales": {},
    }
    for lang in args.locales:
        lang_dir = OUT_DIR / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        titles = per_lang.get(lang) or {}
        ok = miss = err = cached = skipped = 0
        for slug in tqdm(curated, desc=f"wikipedia/styles/{lang}", leave=False):
            title = titles.get(slug)
            if not title:
                skipped += 1
                continue
            cache = lang_dir / f"{slug}.json"
            if cache.exists() and not args.refresh:
                cached += 1
                continue
            result = fetch_summary(session, lang, slug, title)
            cache.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            if result.get("missing"):
                miss += 1
            elif result.get("error"):
                err += 1
            else:
                ok += 1
            time.sleep(args.throttle)
        manifest["locales"][lang] = {
            "ok": ok, "miss": miss, "err": err, "cached": cached, "skipped": skipped,
        }
        print(
            f"[02b/styles/{lang}] new ok={ok} miss={miss} err={err} "
            f"cached={cached} skipped={skipped}",
            file=sys.stderr,
        )

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"[02b/styles] manifest: {MANIFEST.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
