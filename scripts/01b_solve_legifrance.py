"""One-off bootstrap: fetch the consolidated cahier des charges from Légifrance
LODA pages for AOCs that have no BO Agri publication.

Stage 01 cannot reach legifrance.gouv.fr because the site is fronted by
Cloudflare's "managed challenge" (HTTP 403 + `cf-mitigated: challenge` for
non-browser clients; even headless Chromium gets parked on `Un instant…` because
it fails fingerprint/timing checks). Cookie-injection workaround: open a LODA
URL once in your normal browser, copy the `cf_clearance` cookie + the User-Agent
string Cloudflare issued it for, paste them here, and the script reuses them
across the batch.

`cf_clearance` is bound to (UA, IP) at the cookie issuer; the UA you paste must
match the one your browser sent when it got the cookie. Lifetime is typically
30 min – several hours.

Sister script to scripts/es/01b_solve_waf.py (different source; ES uses
auto-pass through CloudFront, FR needs manual cookie due to the tighter
managed-challenge profile).

Cookie/UA sourcing, in priority order:
  1. env vars LEGIFRANCE_CF_CLEARANCE + LEGIFRANCE_USER_AGENT
  2. ~/.config/openwinemap/legifrance.json  ({"cf_clearance": "...",
     "user_agent": "..."}; gitignored, persistent)
  3. interactive prompt (with offer to save to (2) for next time)

Reads:
  raw/inao/cahiers/manual_overrides.json  (curator-supplied LODA URLs)
  raw/inao/cahiers/manifest.json          (stage 01 manifest)
Writes:
  raw/inao/cahiers/<sha256>.pdf           (rendered consolidated décret)
  raw/inao/cahiers/manifest.json          (in-place — adds filename + sha256
                                           + fetched_at + from_legifrance flag)

Run: `.venv/bin/python scripts/01b_solve_legifrance.py`
After: `.venv/bin/python scripts/02_extract_cahiers.py`
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "raw" / "inao" / "cahiers" / "manual_overrides.json"
MANIFEST = ROOT / "raw" / "inao" / "cahiers" / "manifest.json"
CAHIERS_DIR = ROOT / "raw" / "inao" / "cahiers"

CONFIG_PATH = Path.home() / ".config" / "openwinemap" / "legifrance.json"

# A LODA page that has rendered the consolidated décret carries the décret
# article container. Cloudflare challenge pages do not — waiting for it is the
# cleanest "past-the-wall" signal.
LODA_CONTENT_SELECTOR = "article, main, .main-article, [class*=content-page]"
LODA_TEXT_MARKER_FN = (
    "() => { const t = document.body && document.body.innerText || ''; "
    "return t.includes('Décret') || t.includes('Arrêté') || t.includes('JORF'); }"
)
LODA_NAVIGATION_TIMEOUT_MS = 60_000


def _read_creds_env() -> tuple[str, str]:
    return (
        os.environ.get("LEGIFRANCE_CF_CLEARANCE", "").strip(),
        os.environ.get("LEGIFRANCE_USER_AGENT", "").strip(),
    )


def _read_creds_file() -> tuple[str, str]:
    if not CONFIG_PATH.exists():
        return "", ""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError) as exc:
        print(f"warn: could not read {CONFIG_PATH}: {exc}", file=sys.stderr)
        return "", ""
    return (cfg.get("cf_clearance") or "").strip(), (cfg.get("user_agent") or "").strip()


def _prompt_for_creds(missing_cookie: bool, missing_ua: bool) -> tuple[str, str]:
    print(
        "Légifrance is Cloudflare-walled. Paste a fresh cf_clearance cookie\n"
        "and the matching User-Agent from your browser:\n"
        "  1. Open https://www.legifrance.gouv.fr/loda/id/JORFTEXT000024908725\n"
        "     in Chrome (clear any 'Un instant…' interstitial; you should see\n"
        "     the décret).\n"
        "  2. DevTools → Application → Cookies → www.legifrance.gouv.fr →\n"
        "     copy the value of `cf_clearance`.\n"
        "  3. DevTools → Network → click any request → request headers →\n"
        "     copy the `User-Agent` header value.\n",
        file=sys.stderr,
    )
    cookie = getpass.getpass("cf_clearance: ").strip() if missing_cookie else ""
    ua = input("User-Agent: ").strip() if missing_ua else ""
    return cookie, ua


def _save_creds(cookie: str, ua: str) -> None:
    try:
        ans = input(f"Save to {CONFIG_PATH} for next run? [Y/n] ").strip().lower()
    except EOFError:
        ans = "n"
    if ans not in ("", "y", "yes"):
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"cf_clearance": cookie, "user_agent": ua},
                   ensure_ascii=False, indent=2)
    )
    CONFIG_PATH.chmod(0o600)  # cookie is sensitive
    print(f"saved → {CONFIG_PATH} (chmod 600)", file=sys.stderr)


def _require_creds(cookie: str, ua: str) -> tuple[str, str]:
    if not cookie or not ua:
        print("error: cf_clearance and User-Agent are both required",
              file=sys.stderr)
        raise SystemExit(2)
    return cookie, ua


def _resolve_creds_cascade() -> tuple[str, str]:
    cookie, ua = _read_creds_env()
    if cookie and ua:
        return cookie, ua
    f_cookie, f_ua = _read_creds_file()
    cookie = cookie or f_cookie
    ua = ua or f_ua
    if cookie and ua:
        return cookie, ua
    p_cookie, p_ua = _prompt_for_creds(not cookie, not ua)
    cookie = cookie or p_cookie
    ua = ua or p_ua
    if cookie and ua:
        _save_creds(cookie, ua)
    return cookie, ua


def load_credentials(reauth: bool = False) -> tuple[str, str]:
    """Resolve cf_clearance + user_agent from env / config file / prompt.

    `reauth=True` skips env + file and goes straight to the interactive prompt
    — handy when the saved cookie has expired (cf_clearance is bound to UA+IP
    and lives ~30 min by default; refreshing means pasting a new pair)."""
    if reauth:
        cookie, ua = _prompt_for_creds(True, True)
        if cookie and ua:
            _save_creds(cookie, ua)
        return _require_creds(cookie, ua)
    return _require_creds(*_resolve_creds_cascade())


def inject_cookie(ctx: BrowserContext, cf_clearance: str) -> None:
    ctx.add_cookies([
        {
            "name": "cf_clearance",
            "value": cf_clearance,
            "domain": ".legifrance.gouv.fr",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "None",
        },
    ])


def cache_pdf(content: bytes) -> tuple[str, Path]:
    """Content-address the PDF; mirror stage 01's download_pdf so the manifest
    can reference it the same way."""
    digest = hashlib.sha256(content).hexdigest()
    dest = CAHIERS_DIR / f"{digest}.pdf"
    if not dest.exists():
        dest.write_bytes(content)
    return digest, dest


class StaleCookieError(RuntimeError):
    """Raised when Cloudflare hasn't let us past the interstitial — almost
    always means cf_clearance has expired (default lifetime ~30 min)."""


CHALLENGE_TITLES = ("Just a moment...", "Un instant…", "Un instant...")


def render_one(page: Page, url: str) -> bytes:
    """Navigate and render to PDF. Raises StaleCookieError on Cloudflare wall."""
    page.goto(url, wait_until="domcontentloaded", timeout=LODA_NAVIGATION_TIMEOUT_MS)
    # The cookie carries us past the JS interstitial — wait until décret text is
    # actually present in the body. networkidle is unreliable on Légifrance
    # (analytics beacons keep firing), so we sniff the DOM instead.
    try:
        page.wait_for_function(LODA_TEXT_MARKER_FN, timeout=LODA_NAVIGATION_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001
        if page.title() in CHALLENGE_TITLES:
            raise StaleCookieError(
                "Cloudflare interstitial still up — cf_clearance is stale "
                "(re-run with --reauth to paste a fresh cookie)"
            ) from exc
        raise
    # Brief settle for hydration; ignore networkidle timeout if it never quiets.
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:  # noqa: BLE001
        pass
    return page.pdf(format="A4", print_background=False, prefer_css_page_size=False)


def _select_targets(
    overrides: dict, manifest: dict, refresh: bool,
    only_ids: list[str], limit: int,
) -> list[tuple[str, str, str]]:
    """Pick the LODA URLs that need fetching. Returns [(id_app, name, url), …].

    Targets are entries whose override carries a `legifrance_loda_urls` value.
    Skip rules:
      - filename empty: always fetch.
      - filename set + from_legifrance=True: skip unless --refresh (already a
        materialised Légifrance PDF).
      - filename set + from_legifrance=False: skip unless --refresh (stage 01
        grabbed *something* via show_texte / a fallback URL; the curator may
        want to override it with a Légifrance render to fix a stage-02 stub).
    """
    out: list[tuple[str, str, str]] = []
    for id_app, entry in overrides.items():
        if id_app == "_README":
            continue
        loda_urls = entry.get("legifrance_loda_urls") or []
        if not loda_urls:
            continue
        m = manifest.get(id_app, {})
        if m.get("filename") and not refresh:
            continue
        out.append((id_app, entry.get("name", ""), loda_urls[0]))
    if only_ids:
        wanted = set(only_ids)
        out = [t for t in out if t[0] in wanted]
    if limit:
        out = out[:limit]
    return out


def _record_success(
    manifest: dict, id_app: str, name: str, url: str,
    dest_name: str, digest: str,
) -> None:
    # Match stage 01's schema so stage 02 can read every entry uniformly.
    m = manifest.setdefault(id_app, {})
    m.setdefault("name", name)
    for k in ("canonical_idproduit", "canonical_produit", "signe_fr", "signe_ue",
              "categorie", "comite_regional", "product_url", "show_texte_url",
              "boagri_url"):
        m.setdefault(k, "")
    for k in ("show_texte_paths", "boagri_url_candidates", "legifrance_jorftext_ids"):
        m.setdefault(k, [])
    m["filename"] = dest_name
    m["sha256"] = digest
    m["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    m["from_legifrance"] = True
    m["legifrance_loda_url"] = url


def _fetch_loop(
    targets: list[tuple[str, str, str]], manifest: dict,
    cf_clearance: str, user_agent: str, throttle: float, headed: bool,
) -> tuple[int, int]:
    n_ok = n_bad = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(
            user_agent=user_agent,
            locale="fr-FR",
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            viewport={"width": 1280, "height": 1024},
        )
        inject_cookie(ctx, cf_clearance)
        page = ctx.new_page()
        for i, (id_app, name, url) in enumerate(targets):
            label = f"[{i+1}/{len(targets)}] id={id_app:>5} {name[:40]}"
            try:
                pdf_bytes = render_one(page, url)
            except StaleCookieError as exc:
                print(f"  {label}: {exc}", file=sys.stderr)
                print("  ↳ aborting batch — re-run with --reauth", file=sys.stderr)
                n_bad += len(targets) - i  # account for the rest we won't try
                break
            except Exception as exc:  # noqa: BLE001 — playwright errors vary
                print(f"  {label}: navigate failed: {exc}", file=sys.stderr)
                n_bad += 1
                continue
            if len(pdf_bytes) < 8000:
                print(f"  {label}: PDF suspiciously small ({len(pdf_bytes)} B) — "
                      f"likely Cloudflare interstitial; cookie may be stale",
                      file=sys.stderr)
                n_bad += 1
                continue
            digest, dest = cache_pdf(pdf_bytes)
            _record_success(manifest, id_app, name, url, dest.name, digest)
            print(f"  {label}: ok ({len(pdf_bytes)} B → {dest.name[:12]}…)",
                  file=sys.stderr)
            n_ok += 1
            if i + 1 < len(targets):
                time.sleep(throttle)
        browser.close()
    return n_ok, n_bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--throttle", type=float, default=3.0,
                    help="seconds between page loads (default 3)")
    ap.add_argument("--only", action="append", default=[],
                    help="restrict to id_appellation(s); repeatable")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the number of LODA fetches (smoke-test mode)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch even if a PDF already exists for this id")
    ap.add_argument("--headed", action="store_true",
                    help="open a visible browser (handy if cookie was issued for "
                         "a different fingerprint and you need to re-trigger CF)")
    ap.add_argument("--reauth", action="store_true",
                    help="ignore env + saved file and prompt for a fresh "
                         "cf_clearance + User-Agent (use after the cookie expires)")
    args = ap.parse_args()

    if not OVERRIDES.exists() or not MANIFEST.exists():
        print(f"error: {OVERRIDES} or {MANIFEST} missing — run stage 01 first",
              file=sys.stderr)
        return 1

    overrides = json.loads(OVERRIDES.read_text())
    manifest = json.loads(MANIFEST.read_text())
    targets = _select_targets(
        overrides, manifest, args.refresh, args.only, args.limit
    )
    if not targets:
        print("[01b-legifrance] nothing to do — all Légifrance overrides already "
              "cached, or no targets matched", file=sys.stderr)
        return 0

    cf_clearance, user_agent = load_credentials(reauth=args.reauth)
    print(f"[01b-legifrance] {len(targets)} LODA URLs; UA={user_agent[:60]}…",
          file=sys.stderr)
    n_ok, n_bad = _fetch_loop(
        targets, manifest, cf_clearance, user_agent, args.throttle, args.headed
    )
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                    sort_keys=True))
    print(f"[01b-legifrance] fetched={n_ok} failed={n_bad}", file=sys.stderr)
    return 0 if n_bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
