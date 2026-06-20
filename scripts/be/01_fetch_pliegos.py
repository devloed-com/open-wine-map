"""Fetch the EU-OJ single document (ENIG DOCUMENT / DOCUMENT UNIQUE)
HTML page per Belgian wine GI.

Pipeline stage 01 (be).

For each wine in `raw/be/eambrosia/index.json`, scan the `publications`
array for the first HTTP URL and request the per-record `source_lang`
variant of that EUR-Lex page (Dutch for the 6 Flemish + Maasvallei
wines, French for the 4 Walloon wines).

Coverage: 4 of 10 BE wines carry an OJ-C publication URL (the 3 Flemish
DOPs Hagelandse / Haspengouwse / Heuvellandse plus the cross-border
Maasvallei Limburg). The other 6 are Art.107/Reg.1308/2013 grandfathered
names with no public single-document URL. They land as `no-publication`
and stage 02 emits content-stubs. The WAF fallback is
`scripts/be/01b_solve_waf.py`.

URL-rewrite rules (per source_lang):
  nl:  /legal-content/EN/TXT/  →  /legal-content/NL/TXT/HTML/
       uri=...01.ENG           →  uri=...01.NLD
       /oj/eng                 →  /oj/nld
       /oj/?uri=OJ:C_XXX       →  /legal-content/NL/TXT/HTML/?uri=OJ:C_XXX
  fr:  /legal-content/EN/TXT/  →  /legal-content/FR/TXT/HTML/
       uri=...01.ENG           →  uri=...01.FRA
       /oj/eng                 →  /oj/fra
       /oj/?uri=OJ:C_XXX       →  /legal-content/FR/TXT/HTML/?uri=OJ:C_XXX

Manual overrides:
  raw/be/oj-pages/manual_overrides.json (gitignored, optional) keyed by
  giIdentifier or slug → {"url": "<html-url>", "note": "..."}. Overrides
  bypass the eAmbrosia publications list entirely.

Outputs:
  raw/be/oj-pages/<slug>.html          (the per-language single-document HTML)
  raw/be/oj-pages/manifest.json         (per-slug status + final URL)

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
INDEX_PATH = ROOT / "raw" / "be" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "be" / "oj-pages"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)

# The eAmbrosia register attachment endpoint is browser-gated: it serves a
# stub HTML page unless the request carries a real browser User-Agent AND a
# browser-style Accept WITHOUT an explicit `application/pdf` (which itself
# trips the gate). Used only for `*/geographical-indications-register/*` URLs.
_EAMBROSIA_REGISTER_HOST = "geographical-indications-register"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
}

# Per-source-lang URL-rewrite anchors. EU-OJ uses ISO 639-2/B "FRA"/"NLD"
# in the language-tagged uriserv parameters and 3-letter codes "fra"/"nld"
# in the new `/oj/<lang>/...` style.
_OJ_LANG_3 = {"fr": "fra", "nl": "nld"}
_LEGAL_LANG_2 = {"fr": "FR", "nl": "NL"}
_URISERV_LANG_3 = {"fr": "FRA", "nl": "NLD"}
_MODERN_OJ_LANG_3 = {"fr": "FRA", "nl": "NLD"}

_ALL_OJ_LANG_3 = ("ENG", "FRA", "DEU", "ITA", "POR", "SPA", "NLD", "SLV", "SLK", "CES", "HRV", "HUN", "BUL", "RON", "ELL", "GRE")
_ALL_OJ_LANG_3_LOWER = ("eng", "fra", "deu", "ita", "por", "spa", "nld", "slv", "slk", "ces", "hrv", "hun", "bul", "ron", "ell", "gre")


def rewrite_lang(url: str, lang: str) -> str:
    """Best-effort URL rewrite: any EUR-Lex / EU-OJ URL → its `lang`
    HTML variant. Idempotent — already-`lang` URLs pass through."""
    legal2 = _LEGAL_LANG_2[lang]
    uriserv3 = _URISERV_LANG_3[lang]
    oj_lang3_low = _OJ_LANG_3[lang]

    # /oj/?uri=OJ:C_NNNN → /legal-content/<LANG>/TXT/HTML/?uri=OJ:C_NNNN
    # (modern OJ:C ids; the /oj/ endpoint returns a TOC, not the document)
    if "uri=OJ:C_" in url or "uri=OJ%3AC_" in url:
        if "/legal-content/" not in url:
            url = re.sub(
                r"https?://eur-lex\.europa\.eu/oj/?\??",
                f"https://eur-lex.europa.eu/legal-content/{legal2}/TXT/HTML/?",
                url,
            )
    # /eli/.../oj  → /eli/.../oj/<lang3>
    if re.search(r"/oj/?(?:[#?]|$)", url) and not re.search(r"/oj/[a-z]{3}", url):
        url = re.sub(r"/oj(/?)([#?]|$)", rf"/oj/{oj_lang3_low}\2", url)
    # /legal-content/<XX>/TXT/[HTML/] → /legal-content/<LANG>/TXT/HTML/
    url = re.sub(
        r"/legal-content/[A-Z]{2}/TXT(?:/HTML)?/",
        f"/legal-content/{legal2}/TXT/HTML/",
        url,
    )
    # uri=...01.XXX  → uri=...01.<URISERV3>
    pat_dot = "|".join(_ALL_OJ_LANG_3)
    url = re.sub(rf"(\d{{2}}\.)({pat_dot})(?=&|$)", rf"\1{uriserv3}", url)
    # `:XXX` language suffix variant (e.g. "...:ENG&toc=...")
    url = re.sub(rf"(:)({pat_dot})(?=&|$)", rf"\1{uriserv3}", url)
    # `/oj/<lang3>` rewrite to the requested lang3
    pat_low = "|".join(_ALL_OJ_LANG_3_LOWER)
    url = re.sub(rf"/oj/({pat_low})(/?)([#?]|$)", rf"/oj/{oj_lang3_low}\2\3", url)
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
    return any(
        kw in text for kw in ("corrigendum", "rectificatif", "rectificatie")
    )


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


def fetch_page(
    session: requests.Session, url: str, headers: dict | None = None,
) -> requests.Response | None:
    backoff = (1.0, 3.0, 9.0)
    last: requests.Response | None = None
    for delay in (0.0, *backoff):
        if delay:
            time.sleep(delay)
        try:
            r = session.get(url, timeout=60, allow_redirects=True, headers=headers)
        except requests.RequestException as exc:
            print(f"[err] {url[:80]}: {exc}", file=sys.stderr)
            return None
        last = r
        if r.status_code != 202:
            return r
        # The eAmbrosia register attachment endpoint answers 202 with the
        # PDF body inline (not a WAF challenge) — accept it immediately
        # rather than burning the retry budget. EUR-Lex's 202 WAF challenge
        # is HTML, so it still falls through to the backoff retries.
        if "pdf" in (r.headers.get("Content-Type") or "").lower():
            return r
    return last


def looks_like_single_document(html: str, lang: str) -> bool:
    """Heuristic that flags pages that are NOT a single-document
    publication. The single-document HTML is large (>8 KB) and contains
    literal anchors in the source language."""
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
    # fr
    return (
        "document unique" in low
        or "cahier des charges" in low
        or "appellation d'origine protégée" in low
        or "indication géographique protégée" in low
        or "indication géographique" in low
    )


def _save_response(
    r: requests.Response, html_cache: Path, pdf_cache: Path, lang: str,
) -> tuple[Path, str] | None:
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "pdf" in ctype:
        pdf_cache.write_bytes(r.content)
        return pdf_cache, "pdf"
    if not looks_like_single_document(r.text, lang):
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
        print(f"error: {INDEX_PATH} missing — run scripts/be/00_fetch_data.py first",
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
        lang = w.get("source_lang") or "nl"
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
            source_url = rewrite_lang(base, lang) if base else None

        if not source_url:
            manifest[slug] = {
                "status": "no-publication",
                "source_lang": lang,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "n_publications": len(w["publications"]),
            }
            n_no_pub += 1
            continue

        session.headers["Accept-Language"] = f"{lang}-BE,{lang};q=0.9,en;q=0.8"
        req_headers = (
            _BROWSER_HEADERS if _EAMBROSIA_REGISTER_HOST in source_url else None
        )
        r = fetch_page(session, source_url, headers=req_headers)
        time.sleep(args.throttle)
        # 200, or the register attachment endpoint's 202-with-body; the
        # content-type check in _save_response is the real gate.
        if r is None or r.status_code not in (200, 202):
            manifest[slug] = {
                "status": "fetch-error",
                "source_lang": lang,
                "source_url": source_url,
                "http_status": r.status_code if r else 0,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue
        save_result = _save_response(r, html_cache, pdf_cache, lang)
        if save_result is None:
            manifest[slug] = {
                "status": "not-single-document",
                "source_lang": lang,
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
            "source_lang": lang,
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
