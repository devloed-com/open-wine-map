"""Fetch the EU-OJ "SINGLE DOCUMENT" HTML page per MT wine GI.

Pipeline stage 01 (mt).

For each wine in `raw/mt/eambrosia/index.json`, scan the `publications`
array for the first HTTP URL and request the English-language HTML
variant of that EUR-Lex page. The page contains the canonical EU single
document — the English equivalent of the FR cahier des charges, the ES
pliego, the IT documento unico, etc. Malta's wine GIs are published in
English (the country's co-official language), so the URL rewrite targets
the EN HTML variant.

Coverage:
  2 of the 3 MT wines (Malta, Gozo) carry an EU-OJ publication URL. The
  "Maltese Islands" PGI has no publication → stage 02 emits a content-
  stub; it still appears on the map via its region-pdo-union geometry.

English variant rules (the `…/TXT/?` landing page returns no document
body — force the HTML variant):
  /legal-content/EN/TXT/    →  /legal-content/EN/TXT/HTML/
  /legal-content/XX/TXT/    →  /legal-content/EN/TXT/HTML/
  /oj                       →  /oj/eng
  uri=...01.FRA             →  uri=...01.ENG

Manual overrides:
  raw/mt/oj-pages/manual_overrides.json (gitignored, optional) keyed by
  giIdentifier or slug → {"url": "<english-html-url>", "note": "..."}.

Outputs:
  raw/mt/oj-pages/<slug>.html          (the English SINGLE-DOCUMENT HTML)
  raw/mt/oj-pages/manifest.json         (per-slug status + final URL)

Re-runnable: cached HTMLs are kept; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "raw" / "mt" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "mt" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def to_english(url: str) -> str:
    """Best-effort URL rewrite: any EUR-Lex / EU-OJ URL → its English
    HTML variant. Forces the `/HTML/` segment because the bare `/TXT/?`
    landing page carries no document body. Idempotent."""
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        url = re.sub(r"/oj(/?)([#?]|$)", r"/oj/eng\2", url)
    url = re.sub(
        r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/",
        "/legal-content/EN/TXT/HTML/",
        url,
    )
    url = re.sub(r"(\d{2}\.)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD|MLT)(?=&|$)", r"\1ENG", url)
    url = re.sub(r"(:)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD|MLT)(?=&|$)", r"\1ENG", url)
    return url


def _is_oj_c_publication(pub: dict) -> bool:
    """OJ Series C carries the single document; OJ Series L is the
    implementing regulation."""
    text = (pub.get("text") or "").lower()
    uri = (pub.get("uri") or "").lower()
    if "official journal c" in text:
        return True
    if "/eli/c/" in uri:
        return True
    if "oj.c_." in uri or "oj:c_" in uri:
        return True
    return False


def _is_corrigendum(pub: dict) -> bool:
    text = (pub.get("text") or "").lower()
    return "corrigendum" in text


def first_http_publication(pubs: list[dict]) -> str | None:
    for pub in pubs:
        uri = pub.get("uri") or ""
        if uri.startswith("http") and _is_oj_c_publication(pub) and not _is_corrigendum(pub):
            return uri
    for pub in pubs:
        uri = pub.get("uri") or ""
        if uri.startswith("http") and _is_oj_c_publication(pub):
            return uri
    for pub in pubs:
        uri = pub.get("uri") or ""
        if uri.startswith("http"):
            return uri
    return None


def fetch_page(session: requests.Session, url: str) -> requests.Response | None:
    backoff = (1.0, 3.0, 9.0)
    last: requests.Response | None = None
    for delay in (0.0, *backoff):
        if delay:
            time.sleep(delay)
        try:
            r = session.get(url, timeout=60, allow_redirects=True)
        except requests.RequestException as exc:
            print(f"[err] {url[:80]}: {exc}", file=sys.stderr)
            return None
        last = r
        if r.status_code != 202:
            return r
    return last


def looks_like_single_document(html: str) -> bool:
    """Heuristic that flags pages that are NOT a single-document
    publication. The SINGLE-DOCUMENT HTML is large (>8 KB) and contains
    literal English phrases."""
    if len(html) < 8000:
        return False
    low = html.lower()
    return (
        "single document" in low
        or "product specification" in low
        or "protected designation of origin" in low
        or "protected geographical indication" in low
        or "geographical indication" in low
    )


def _save_response(
    r: requests.Response, html_cache: Path, pdf_cache: Path,
) -> tuple[Path, str] | None:
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "pdf" in ctype:
        pdf_cache.write_bytes(r.content)
        return pdf_cache, "pdf"
    if not looks_like_single_document(r.text):
        return None
    html_cache.write_text(r.text, encoding="utf-8")
    return html_cache, "html"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.3, help="seconds between API calls")
    ap.add_argument("--limit", type=int, default=0, help="cap on entries to process (0 = all)")
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(f"error: {INDEX_PATH} missing — run scripts/mt/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    overrides: dict[str, dict] = {}
    if OVERRIDES_PATH.exists():
        try:
            overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"[warn] could not read overrides: {exc}", file=sys.stderr)

    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        wines = wines[: args.limit]

    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf",
        "Accept-Language": "en",
    })

    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            manifest = {}

    n_ok = n_cached = n_no_pub = n_bad = n_override = 0
    for w in tqdm(wines, desc="oj-pages", leave=False):
        slug = w["slug"]
        html_cache = OUT_DIR / f"{slug}.html"
        pdf_cache = OUT_DIR / f"{slug}.pdf"
        if (html_cache.exists() or pdf_cache.exists()) and not args.refresh:
            n_cached += 1
            continue

        override = overrides.get(slug) or overrides.get(w["giIdentifier"])
        source_url: str | None
        if override and override.get("url"):
            source_url = override["url"]
            n_override += 1
        else:
            base = first_http_publication(w["publications"])
            source_url = to_english(base) if base else None

        if not source_url:
            manifest[slug] = {
                "status": "no-publication",
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "n_publications": len(w["publications"]),
            }
            n_no_pub += 1
            continue

        r = fetch_page(session, source_url)
        time.sleep(args.throttle)
        if r is None or r.status_code != 200:
            manifest[slug] = {
                "status": "fetch-error",
                "source_url": source_url,
                "http_status": r.status_code if r else 0,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue
        save_result = _save_response(r, html_cache, pdf_cache)
        if save_result is None:
            manifest[slug] = {
                "status": "not-single-document",
                "source_url": source_url,
                "final_url": r.url,
                "bytes": len(r.content),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue
        _, fmt = save_result
        manifest[slug] = {
            "status": "ok",
            "source_url": source_url,
            "final_url": r.url,
            "format": fmt,
            "bytes": len(r.content),
            "from_override": bool(override),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        n_ok += 1

    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": "© European Union, EUR-Lex / Official Journal. Reuse with attribution.",
        "n_wines": len(wines),
        "counts": {
            "ok": n_ok,
            "cached": n_cached,
            "override": n_override,
            "no_publication": n_no_pub,
            "fetch_error_or_not_single_document": n_bad,
        },
        "by_slug": manifest,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[done] ok={n_ok} cached={n_cached} override={n_override} "
        f"no-pub={n_no_pub} bad={n_bad} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
