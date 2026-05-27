"""Fetch the EU-OJ "Enotni dokument" HTML page per SI wine GI.

Pipeline stage 01 (si).

For each wine in `raw/si/eambrosia/index.json`, scan the `publications`
array for the first HTTP URL and request the Slovenian-language variant
of that EUR-Lex page. The page contains the canonical EU single document
("ENOTNI DOKUMENT") — the Slovenian equivalent of the FR cahier des
charges, the ES pliego, the IT documento unico and the AT Einziges
Dokument.

Coverage:
  Only 1 of the 17 SI wines (Cviček) carries a fetchable OJ-C publication
  URL — the other 16 are Art.107/Reg.1308/2013 grandfathered names with
  no public single-document URL. They land as `no-publication` and stage
  02 emits content-stubs (the IT/ES curator-queue pattern). The other
  failure mode is the EUR-Lex AWS WAF (HTTP 202 + JavaScript challenge);
  `scripts/si/01b_solve_waf.py` bootstraps the blocked subset via headless
  Chromium.

Slovenian variant rules (same as ES/IT/AT, with the language swap):
  /eli/.../oj  →  /eli/.../oj/slv  (3-letter ISO 639-2)
  legal-content/EN/TXT/  →  legal-content/SL/TXT/HTML/
  uri=...01.ENG&...     →  uri=...01.SLV&...

Manual overrides:
  raw/si/oj-pages/manual_overrides.json (gitignored, optional) keyed by
  giIdentifier or slug → {"url": "<slovenian-html-url>", "note": "..."}.
  Overrides bypass the eAmbrosia publications list entirely.

Outputs:
  raw/si/oj-pages/<slug>.html          (the Slovenian Enotni-dokument HTML)
  raw/si/oj-pages/manifest.json         (per-slug status + final URL)

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
INDEX_PATH = ROOT / "raw" / "si" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "si" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def to_slovenian(url: str) -> str:
    """Best-effort URL rewrite: any EUR-Lex / EU-OJ URL → its Slovenian
    HTML variant. Idempotent — already-Slovenian URLs pass through."""
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        return re.sub(r"/oj(/?)([#?]|$)", r"/oj/slv\2", url)
    new = re.sub(
        r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/",
        "/legal-content/SL/TXT/HTML/",
        url,
    )
    new = re.sub(r"(\d{2}\.)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD|SLV)(?=&|$)", r"\1SLV", new)
    new = re.sub(r"(:)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD|SLV)(?=&|$)", r"\1SLV", new)
    return new


def _is_oj_c_publication(pub: dict) -> bool:
    """OJ Series C carries the single document; OJ Series L is the
    implementing regulation. Distinguish via the `text` and URL form."""
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
    """A Corrigendum / Popravek publication is a short correction notice,
    not the full single document — deprioritise it."""
    text = (pub.get("text") or "").lower()
    return "corrigendum" in text or "popravek" in text


def first_http_publication(pubs: list[dict]) -> str | None:
    """Pick the single-document URL. Priority: non-corrigendum OJ-C → any
    OJ-C → any http URL."""
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
    """Fetch with 202-aware retry. EUR-Lex generates `legal-content/SL/TXT/HTML`
    pages on demand: the first request returns HTTP 202 and triggers
    server-side rendering; subsequent requests return 200. The AWS WAF
    also returns 202 — those stay 202 across retries and get handed off
    to stage 01b."""
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
    publication. The Enotni-dokument HTML is large (>8 KB) and contains
    literal Slovenian phrases."""
    if len(html) < 8000:
        return False
    low = html.lower()
    return (
        "enotni dokument" in low
        or "specifikacija proizvoda" in low
        or "označba porekla" in low
        or "geografska označba" in low
    )


def _save_response(
    r: requests.Response, html_cache: Path, pdf_cache: Path,
) -> tuple[Path, str] | None:
    """Dispatch by Content-Type. EUR-Lex serves HTML; curator-pinned
    overrides may serve `application/pdf`. Returns (cache_path, format)
    on success, or None if the response is an HTML page that doesn't
    look like a single document."""
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
        print(f"error: {INDEX_PATH} missing — run scripts/si/00_fetch_data.py first",
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
        "Accept-Language": "sl",
    })

    # Always load the existing manifest and merge — `--refresh` re-fetches
    # the processed wines but must not erase entries for wines outside
    # this run's `--only` / `--limit` scope.
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
            source_url = to_slovenian(base) if base else None

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
