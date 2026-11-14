#!/usr/bin/env python3
"""Stage 01b of the drinks pipeline: the Official Journal single document of
a drink GI the register holds no technical file for.

Spirit drinks registered after 2017 and the cider GIs carry only OJ
publications in the register. The newest OJ C one (`_lib/oj_publications`)
is the single document; it is fetched from EUR-Lex in the owner country's
language as inline HTML. EUR-Lex sits behind an AWS WAF that answers a
non-browser client with HTTP 202 and a JavaScript challenge, so the fetch
runs in headless Chromium (Playwright, the `bootstrap` dependency group),
which solves the challenge; each page is saved under raw/drinks/oj-pages/
with its sha256, and never fetched again unless `--refresh`.

    .venv/bin/python scripts/drinks/01b_fetch_oj_pages.py [--only SLUG …]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.drinks import single_document as sd  # noqa: E402
from _lib.oj_publications import is_oj_c, ordered_publication_uris  # noqa: E402

INDEX_PATH = ROOT / "raw" / "drinks" / "eambrosia" / "index.json"
FILES_MANIFEST = ROOT / "raw" / "drinks" / "technical-files" / "manifest.json"
OUT_DIR = ROOT / "raw" / "drinks" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

COUNTRY_LANG = {
    "fr": "fr", "es": "es", "pt": "pt", "it": "it", "at": "de", "de": "de", "si": "sl",
    "hr": "hr", "hu": "hu", "ro": "ro", "bg": "bg", "gr": "el", "cy": "el", "sk": "sk",
    "cz": "cs", "lu": "fr", "be": "nl", "nl": "nl", "mt": "en",
}


def candidates(meta: dict, override: dict | None) -> list[tuple[str, str]]:
    """(uri, ref) to try, in order: a curator pin, then the OJ C publications
    newest first."""
    out: list[tuple[str, str]] = []
    if override and override.get("url"):
        out.append((override["url"], override.get("note", "manual override")))
    pubs = meta.get("publications") or []
    by_uri = {p["uri"]: p for p in pubs}
    for uri in ordered_publication_uris(pubs):
        if is_oj_c(by_uri.get(uri, {})) or "celex:5" in uri.lower() or "celex%3a5" in uri.lower():
            out.append((uri, by_uri.get(uri, {}).get("text", "")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug (repeatable)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["drinks"]
    files = json.loads(FILES_MANIFEST.read_text(encoding="utf-8"))
    manifest: dict = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    )
    overrides: dict = {}
    if OVERRIDES_PATH.exists():
        overrides = {k: v for k, v in json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).items()
                     if not k.startswith("_")}
    todo = []
    for e in entries:
        meta = files.get(e["slug"]) or {}
        if meta.get("files"):
            continue  # a technical file is the source
        if args.only and e["slug"] not in args.only:
            continue
        if manifest.get(e["slug"], {}).get("status") == "ok" and not args.refresh \
                and (OUT_DIR / f"{e['slug']}.html").exists():
            continue
        cands = candidates(meta, overrides.get(e["slug"]))
        if cands:
            todo.append((e, cands))
    print(f"[plan] {len(todo)} page(s) to fetch", file=sys.stderr)
    if not todo:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = miss = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(locale="en-GB")
        page = ctx.new_page()
        try:
            for entry, cands in todo:
                slug = entry["slug"]
                lang = COUNTRY_LANG.get(entry["country"], "en")
                got = None
                for uri, ref in cands:
                    for try_lang in (lang, "en"):
                        url = sd.to_language(uri, try_lang)
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            page.wait_for_timeout(2500)
                            html = page.content()
                            if len(html) < 8000:
                                # the WAF challenge: give it time, then reload
                                page.wait_for_timeout(6000)
                                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                                page.wait_for_timeout(2500)
                                html = page.content()
                        except Exception as exc:  # noqa: BLE001 — a page that fails is a miss
                            print(f"[warn] {slug}: {url[:100]}: {exc}", file=sys.stderr)
                            continue
                        time.sleep(args.delay)
                        if sd.looks_like_single_document(html):
                            got = (html, url, page.url, try_lang, ref)
                            break
                    if got:
                        break
                if not got:
                    manifest[slug] = {"status": "missed", "tried": [c[0] for c in cands]}
                    miss += 1
                    print(f"[miss] {slug}", file=sys.stderr)
                    continue
                html, url, final_url, got_lang, ref = got
                (OUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
                manifest[slug] = {
                    "status": "ok",
                    "file_number": entry["file_number"],
                    "source_url": url,
                    "final_url": final_url,
                    "lang": got_lang,
                    "ref": ref,
                    "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                    "bytes": len(html.encode("utf-8")),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                ok += 1
                print(f"[ok] {slug} ({got_lang}) {len(html)} bytes", file=sys.stderr)
        finally:
            MANIFEST_PATH.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
            )
            browser.close()
    print(f"[done] ok={ok} missed={miss} manifest={MANIFEST_PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0 if miss == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
