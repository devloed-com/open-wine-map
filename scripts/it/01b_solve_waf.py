"""One-off bootstrap: fetch the EUR-Lex documento-unico HTMLs that
`scripts/it/01_fetch_pliegos.py` couldn't reach because EUR-Lex sits
behind an AWS WAF that returns HTTP 202 + a JavaScript challenge for
non-browser clients.

Headless Chromium runs the WAF challenge JS automatically (the WAF
sets a cookie after the JS solves a token; the second navigation gets
the real HTML). We then save the HTML at the same cache path as
stage 01 so subsequent runs see it as already-cached and skip.

Run: `.venv/bin/python scripts/it/01b_solve_waf.py`
After: re-run `scripts/it/02_extract_pliegos.py` to pick up the new HTMLs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "raw" / "it" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "it" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"


def to_italian(url: str) -> str:
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        return re.sub(r"/oj(/?)([#?]|$)", r"/oj/ita\2", url)
    new = re.sub(r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/", "/legal-content/IT/TXT/HTML/", url)
    new = re.sub(r"(\d{2}\.)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD)(?=&|$)", r"\1ITA", new)
    new = re.sub(r"(:)(?:ENG|FRA|DEU|ITA|POR|SPA|NLD)(?=&|$)", r"\1ITA", new)
    return new


def _is_oj_c_publication(pub: dict) -> bool:
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
    for pub in pubs:
        uri = pub.get("uri") or ""
        if uri.startswith("http") and _is_oj_c_publication(pub):
            return uri
    for pub in pubs:
        uri = pub.get("uri") or ""
        if uri.startswith("http"):
            return uri
    return None


def looks_like_single_document(html: str) -> bool:
    if len(html) < 8000:
        return False
    low = html.lower()
    return (
        "documento unico" in low
        or "disciplinare di produzione" in low
        or "denominazione di origine" in low
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--throttle", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(f"error: {INDEX_PATH} missing", file=sys.stderr)
        return 1
    if not MANIFEST_PATH.exists():
        print(f"error: {MANIFEST_PATH} missing — run scripts/it/01_fetch_pliegos.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    manifest_root = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_slug = manifest_root.get("by_slug", {})

    targets: list[tuple[dict, str]] = []
    for w in wines:
        slug = w["slug"]
        cache = OUT_DIR / f"{slug}.html"
        if cache.exists():
            continue
        info = by_slug.get(slug, {})
        if info.get("status") != "fetch-error":
            continue
        url = first_http_publication(w["publications"])
        if not url:
            continue
        targets.append((w, to_italian(url)))

    if args.only:
        needles = [s.lower() for s in args.only]
        targets = [(w, u) for w, u in targets if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        targets = targets[: args.limit]

    print(f"[01b] {len(targets)} WAF-blocked wines to bootstrap via Chromium",
          file=sys.stderr)
    if not targets:
        return 0

    n_ok = n_bad = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="it-IT",
            extra_http_headers={"Accept-Language": "it-IT,it;q=0.9,en;q=0.8"},
        )
        page = ctx.new_page()
        for i, (w, url) in enumerate(targets):
            slug = w["slug"]
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                html = page.content()
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i+1}/{len(targets)}] {slug}: navigate failed: {exc}",
                      file=sys.stderr)
                by_slug[slug] = {
                    "status": "playwright-error",
                    "source_url": url,
                    "error": str(exc)[:300],
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_bad += 1
                continue
            if not looks_like_single_document(html):
                print(f"  [{i+1}/{len(targets)}] {slug}: not a single document "
                      f"(bytes={len(html)})", file=sys.stderr)
                by_slug[slug] = {
                    "status": "not-single-document",
                    "source_url": url,
                    "final_url": page.url,
                    "bytes": len(html),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_bad += 1
                continue
            (OUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
            by_slug[slug] = {
                "status": "ok",
                "source_url": url,
                "final_url": page.url,
                "bytes": len(html),
                "from_playwright": True,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_ok += 1
            print(f"  [{i+1}/{len(targets)}] {slug}: ok ({len(html)} B)",
                  file=sys.stderr)
            if i + 1 < len(targets):
                time.sleep(args.throttle)
        browser.close()

    from collections import Counter as C
    counts = C(info.get("status") for info in by_slug.values())
    manifest_root["by_slug"] = by_slug
    manifest_root["counts"] = {
        "ok": counts["ok"],
        "no_publication": counts["no-publication"],
        "fetch_error_or_not_single_document": (
            counts["fetch-error"] + counts["not-single-document"]
            + counts["playwright-error"]
        ),
        "playwright_solved": sum(
            1 for v in by_slug.values() if v.get("from_playwright")
        ),
    }
    manifest_root["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(json.dumps(manifest_root, ensure_ascii=False, indent=2,
                                        sort_keys=True), encoding="utf-8")
    print(f"[01b] solved={n_ok} failed={n_bad}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
