"""One-off bootstrap: fetch the EUR-Lex single-document HTMLs that
`scripts/be/01_fetch_pliegos.py` couldn't reach because EUR-Lex sits
behind an AWS WAF that returns HTTP 202 + a JavaScript challenge for
non-browser clients.

Headless Chromium runs the WAF challenge JS automatically. We save the
HTML at the same cache path as stage 01 so subsequent runs see it as
already-cached. Per-record source_lang drives the locale + Accept-
Language headers — Flemish wines fetch the NL variant, Walloon the FR
variant.

Run: `.venv/bin/python scripts/be/01b_solve_waf.py`
After: re-run `scripts/be/02_extract_pliegos.py` to pick up the new HTMLs.
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
INDEX_PATH = ROOT / "raw" / "be" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "be" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"


_OJ_LANG_3 = {"fr": "fra", "nl": "nld"}
_LEGAL_LANG_2 = {"fr": "FR", "nl": "NL"}
_URISERV_LANG_3 = {"fr": "FRA", "nl": "NLD"}
_ALL_OJ_LANG_3 = ("ENG", "FRA", "DEU", "ITA", "POR", "SPA", "NLD", "SLV", "SLK", "CES", "HRV", "HUN", "BUL", "RON", "ELL", "GRE")
_ALL_OJ_LANG_3_LOWER = ("eng", "fra", "deu", "ita", "por", "spa", "nld", "slv", "slk", "ces", "hrv", "hun", "bul", "ron", "ell", "gre")


def rewrite_lang(url: str, lang: str) -> str:
    legal2 = _LEGAL_LANG_2[lang]
    uriserv3 = _URISERV_LANG_3[lang]
    oj_lang3_low = _OJ_LANG_3[lang]
    if "uri=OJ:C_" in url or "uri=OJ%3AC_" in url:
        if "/legal-content/" not in url:
            url = re.sub(
                r"https?://eur-lex\.europa\.eu/oj/?\??",
                f"https://eur-lex.europa.eu/legal-content/{legal2}/TXT/HTML/?",
                url,
            )
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        url = re.sub(r"/oj(/?)([#?]|$)", rf"/oj/{oj_lang3_low}\2", url)
    url = re.sub(
        r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/",
        f"/legal-content/{legal2}/TXT/HTML/",
        url,
    )
    pat_dot = "|".join(_ALL_OJ_LANG_3)
    url = re.sub(rf"(\d{{2}}\.)({pat_dot})(?=&|$)", rf"\1{uriserv3}", url)
    url = re.sub(rf"(:)({pat_dot})(?=&|$)", rf"\1{uriserv3}", url)
    pat_low = "|".join(_ALL_OJ_LANG_3_LOWER)
    url = re.sub(rf"/oj/({pat_low})(/?)([#?]|$)", rf"/oj/{oj_lang3_low}\2\3", url)
    return url


def _is_oj_c_publication(pub: dict) -> bool:
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
    return any(kw in text for kw in ("corrigendum", "rectificatif", "rectificatie"))


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


def looks_like_single_document(html: str, lang: str) -> bool:
    if len(html) < 8000:
        return False
    low = html.lower()
    if lang == "nl":
        return (
            "enig document" in low
            or "productdossier" in low
            or "beschermde oorsprongsbenaming" in low
            or "beschermde geografische aanduiding" in low
            or "geografische aanduiding" in low
        )
    return (
        "document unique" in low
        or "cahier des charges" in low
        or "appellation d'origine protégée" in low
        or "indication géographique protégée" in low
        or "indication géographique" in low
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
        print(f"error: {MANIFEST_PATH} missing — run scripts/be/01_fetch_pliegos.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    manifest_root = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_slug = manifest_root.get("by_slug", {})
    overrides: dict[str, dict] = {}
    if OVERRIDES_PATH.exists():
        try:
            overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            overrides = {}

    targets: list[tuple[dict, str]] = []
    for w in wines:
        slug = w["slug"]
        cache = OUT_DIR / f"{slug}.html"
        if cache.exists():
            continue
        info = by_slug.get(slug, {})
        if info.get("status") not in (
            "fetch-error", "playwright-error", "not-single-document",
        ):
            continue
        override = overrides.get(slug) or overrides.get(w["giIdentifier"])
        if override and override.get("url"):
            url = override["url"]
        else:
            base = first_http_publication(w["publications"])
            url = rewrite_lang(base, w.get("source_lang") or "nl") if base else None
        if not url:
            continue
        targets.append((w, url))

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
        for i, (w, url) in enumerate(targets):
            lang = w.get("source_lang") or "nl"
            ctx = browser.new_context(
                locale=f"{lang}-BE",
                extra_http_headers={"Accept-Language": f"{lang}-BE,{lang};q=0.9,en;q=0.8"},
            )
            page = ctx.new_page()
            slug = w["slug"]
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                html = page.content()
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i+1}/{len(targets)}] {slug}: navigate failed: {exc}",
                      file=sys.stderr)
                by_slug[slug] = {
                    "status": "playwright-error",
                    "source_lang": lang,
                    "source_url": url,
                    "error": str(exc)[:300],
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_bad += 1
                ctx.close()
                continue
            if not looks_like_single_document(html, lang):
                print(f"  [{i+1}/{len(targets)}] {slug}: not a single document "
                      f"(bytes={len(html)})", file=sys.stderr)
                by_slug[slug] = {
                    "status": "not-single-document",
                    "source_lang": lang,
                    "source_url": url,
                    "final_url": page.url,
                    "bytes": len(html),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_bad += 1
                ctx.close()
                continue
            (OUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
            by_slug[slug] = {
                "status": "ok",
                "source_lang": lang,
                "source_url": url,
                "final_url": page.url,
                "bytes": len(html),
                "from_playwright": True,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_ok += 1
            print(f"  [{i+1}/{len(targets)}] {slug} ({lang}): ok ({len(html)} B)",
                  file=sys.stderr)
            ctx.close()
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
