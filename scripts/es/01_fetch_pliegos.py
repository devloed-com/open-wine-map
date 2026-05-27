"""Fetch the EU-OJ "single document" HTML page per ES wine GI.

Pipeline stage 01 (es).

For each wine in `raw/es/eambrosia/index.json`, scan the `publications`
array for the first HTTP URL and request the Spanish-language variant
of that EUR-Lex page. The page contains the canonical EU "single
document" (template sections 1–9) — the equivalent of the FR cahier des
charges. PDF format is not used (eAmbrosia's `singleDocument` field is
null for ALL ES wines).

URL forms handled:
  http://data.europa.eu/eli/C/<YYYY>/<N>/oj
  https://eur-lex.europa.eu/eli/<...>/oj
  https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.C_.<...>.ENG&...
  https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:C_<...>

Spanish variant rules:
  /eli/.../oj  →  /eli/.../oj/spa  (3-letter ISO 639-2)
  legal-content/EN/TXT/  →  legal-content/ES/TXT/HTML/
  uri=...01.ENG&...     →  uri=...01.SPA&...
  uri=...:ENG          →  uri=...:SPA  (when present)

Manual overrides:
  raw/es/oj-pages/manual_overrides.json (gitignored, optional) keyed by
  giIdentifier or slug → {"url": "<spanish-html-url>", "note": "..."}.
  Overrides bypass the eAmbrosia publications list entirely.

Outputs:
  raw/es/oj-pages/<slug>.html          (the Spanish single-document HTML)
  raw/es/oj-pages/manifest.json         (per-slug status + final URL)

Re-runnable: cached HTMLs are kept; pass --refresh to re-fetch.
Wines with no usable publication appear in the manifest with
`status: "no-publication"` and no .html — stage 02 emits stubs for those.
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
INDEX_PATH = ROOT / "raw" / "es" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "es" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)


def to_spanish(url: str) -> str:
    """Best-effort URL rewrite: any EUR-Lex / EU-OJ URL → its Spanish HTML
    variant. Idempotent — already-Spanish URLs pass through unchanged."""
    # /eli/.../oj → append /spa (works for both eur-lex.europa.eu and data.europa.eu)
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        return re.sub(r"/oj(/?)([#?]|$)", r"/oj/spa\2", url)
    # legal-content/EN/TXT/ → legal-content/ES/TXT/HTML/
    new = re.sub(
        r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/",
        "/legal-content/ES/TXT/HTML/",
        url,
    )
    # uriserv URI tail .<LANG3> → .SPA (handles both raw and url-encoded forms)
    new = re.sub(r"(\d{2}\.)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD)(?=&|$)", r"\1SPA", new)
    new = re.sub(r"(:)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD)(?=&|$)", r"\1SPA", new)
    return new


def _is_oj_c_publication(pub: dict) -> bool:
    """OJ Series C (Communications) carries the documento único; OJ Series L
    (Legislation) is the implementing regulation that *approves* the
    modification but doesn't include the pliego itself. Distinguish via the
    `text` ("Official Journal C…") and via URL form (post-2023 ELI: `/eli/c/…`
    or `/eli/C/…`; pre-2023: `OJ.C_.` segment)."""
    text = (pub.get("text") or "").lower()
    uri = (pub.get("uri") or "").lower()
    if "official journal c" in text:
        return True
    if "/eli/c/" in uri:
        return True
    if "oj.c_." in uri:
        return True
    return False


def first_http_publication(pubs: list[dict]) -> str | None:
    """eAmbrosia's `publications` interleaves OJ-cite URLs (http) with internal
    Ares document numbers (e.g. uri="86888"). We want the first http one that
    points at an OJ C (documento único). When eAmbrosia lists both an OJ L
    (modification-approval regulation) and an OJ C (the one that carries the
    pliego), preferring OJ C avoids stage 02's `no-documento-unico-anchor`
    stub. Fall back to any http URL when there's no OJ C — most ES wines
    have only one http publication."""
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
    """Fetch with 202-aware retry. EUR-Lex generates `legal-content/ES/TXT/HTML`
    pages on demand: the first request returns HTTP 202 (Accepted) and
    triggers server-side rendering; subsequent requests return 200 with the
    cached HTML. We retry with exponential backoff up to 3 times."""
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
    """Heuristic that flags pages that are NOT a single-document publication.
    EUR-Lex serves a generic "document not found" / index page in some cases;
    we want to stub those rather than cache a useless page. The single-
    document HTML is large (>30 KB after nav chrome stripped) and contains
    the literal Spanish phrase `pliego de condiciones` somewhere."""
    if len(html) < 8000:
        return False
    return "pliego de condiciones" in html.lower() or "documento único" in html.lower()


def _save_response(
    r: requests.Response, html_cache: Path, pdf_cache: Path,
) -> tuple[Path, str] | None:
    """Dispatch by Content-Type. EUR-Lex serves HTML; MAPA / euskadi.eus
    overrides serve `application/pdf`. Returns (cache_path, format) on success,
    or None if the response is an HTML page that doesn't look like a
    single-document publication.

    PDFs are accepted unconditionally — we trust the curator-supplied URL to
    point at the right pliego (visual confirmation happened during the URL
    research). The `looks_like_single_document` check is HTML-specific."""
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
        print(f"error: {INDEX_PATH} missing — run scripts/es/00_fetch_data.py first",
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
        # MAPA-hosted overrides serve `application/pdf`; EUR-Lex serves HTML.
        # Accept both — the dispatch below routes on Content-Type.
        "Accept": "text/html,application/xhtml+xml,application/pdf",
        "Accept-Language": "es",
    })

    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists() and not args.refresh:
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            manifest = {}

    n_ok = n_cached = n_no_pub = n_bad = n_override = 0
    for w in tqdm(wines, desc="oj-pages", leave=False):
        slug = w["slug"]
        # Cache may be either HTML (EUR-Lex single-document) or PDF (MAPA /
        # euskadi.eus override). Either format counts as cached.
        html_cache = OUT_DIR / f"{slug}.html"
        pdf_cache = OUT_DIR / f"{slug}.pdf"
        if (html_cache.exists() or pdf_cache.exists()) and not args.refresh:
            n_cached += 1
            continue

        # 1) explicit override
        override = overrides.get(slug) or overrides.get(w["giIdentifier"])
        source_url: str | None
        if override and override.get("url"):
            source_url = override["url"]
            n_override += 1
        else:
            # 2) first http publication, translated to ES
            base = first_http_publication(w["publications"])
            source_url = to_spanish(base) if base else None

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
