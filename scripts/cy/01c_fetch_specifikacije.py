"""Fetch the Cyprus national wine product specification (`τεχνικός
φάκελος`) for each CY wine GI from the Cyprus Department of Agriculture
(Τμήμα Γεωργίας) Lotus Domino site on moa.gov.cy.

Pipeline stage 01c (cy). Sibling of the ES MAPA / IT MASAF / GR ΥΠΑΑΤ /
HR–SI national-spec layers. All 11 CY wine GIs are Art.107 /
Reg.1308/2013 grandfathered names with no fetchable EU-OJ ΕΝΙΑΙΟ
ΕΓΓΡΑΦΟ HTML; the canonical public spec is the per-wine technical-file
PDF published on the moa.gov.cy «Αμπελουργία / Οινολογία» listing page.

Discovery is automatic + reproducible: this stage scrapes that listing
page (public, WAF-free — only the `www.` host works, the bare host
301s), reads every `$file/<…>.pdf` link with its Greek anchor text, and
matches each wine to its PDF by Greek-normalised name (dashes folded to
spaces, exact equality so the «Κρασοχώρια Λεμεσού» parent doesn't grab
the «… - Αφάμης» / «… - Λαόνα» children). The spirits on the same page
(Ζιβανία, Ούζο) and the registration-form PDFs match no wine and are
ignored.

`raw/cy/national-specs/manual_overrides.json` (gitignored, optional)
keyed by slug → {"url": …, "file_number": …, "note": …} takes
precedence per-slug — a safety valve for when a Domino docid rotates.

Each download lands at `raw/cy/national-specs/<slug>.pdf` with a
manifest recording sha256, fetch time, source URL. Stage 02f
(`02f_extract_national_specs.py`) consumes these.

Licence: Cyprus government official act (Τμήμα Γεωργίας / Συμβούλιο
Αμπελοοινικών Προϊόντων) — reuse with attribution.

Re-runnable: cached files are kept; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.cy.eniaio_engrafo import greek_norm  # noqa: E402

INDEX_PATH = ROOT / "raw" / "cy" / "eambrosia" / "index.json"
OUT_DIR = ROOT / "raw" / "cy" / "national-specs"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

# The Department of Agriculture «Αμπελουργία / Οινολογία» page lists every
# wine PDO/PGI technical-file PDF.
LISTING_URL = (
    "https://www.moa.gov.cy/moa/da/da.nsf/"
    "viticultureoenology_el/viticultureoenology_el?opendocument"
)
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)

_PDF_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]*\$file/[^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>',
    re.S | re.I,
)


def _match_key(name: str) -> str:
    """Greek-normalised match key: greek_norm + dashes→space + collapse.
    Folds the en-dash / hyphen / double-space drift between the eAmbrosia
    name and the Domino anchor text ('Λαόνα Ακάμα' vs 'Λαόνα – Ακάμα')."""
    k = greek_norm(name or "")
    k = re.sub(r"[‐-―\-]+", " ", k)
    return re.sub(r"\s+", " ", k).strip()


def _force_www(url: str) -> str:
    """The Domino store only answers on the www host (bare host 301s)."""
    p = urlparse(url)
    if p.netloc == "moa.gov.cy":
        p = p._replace(netloc="www.moa.gov.cy")
    if p.scheme == "http":
        p = p._replace(scheme="https")
    return urlunparse(p)


def scrape_listing(session: requests.Session) -> dict[str, str]:
    """Return {match_key(anchor_text): absolute_pdf_url} for every PDF on
    the listing page."""
    r = session.get(LISTING_URL, timeout=90)
    r.raise_for_status()
    out: dict[str, str] = {}
    for m in _PDF_LINK_RE.finditer(r.text):
        href, raw_txt = m.group(1), m.group(2)
        txt = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_txt)).strip()
        if not txt:
            continue
        url = _force_www(urljoin(LISTING_URL, html_lib.unescape(href)))
        out.setdefault(_match_key(txt), url)
    return out


def fetch_one(session: requests.Session, url: str) -> requests.Response | None:
    try:
        r = session.get(url, timeout=120, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[err] {url[:90]}: {exc}", file=sys.stderr)
        return None
    # eAmbrosia's public attachment API serves a valid PDF body under HTTP
    # 202 (its AWS WAF status); accept 200/202 as long as there's content.
    if r.status_code not in (200, 202) or not r.content:
        print(f"[err] {r.status_code} {url[:90]}", file=sys.stderr)
        return None
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(f"error: {INDEX_PATH} missing — run scripts/cy/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    overrides: dict[str, dict] = {}
    if OVERRIDES_PATH.exists():
        try:
            overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"[warn] could not read overrides: {exc}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "el,en;q=0.8"})

    print(f"[scrape] {LISTING_URL}", file=sys.stderr)
    try:
        listing = scrape_listing(session)
    except requests.RequestException as exc:
        print(f"[warn] listing scrape failed ({exc}); relying on manual_overrides only",
              file=sys.stderr)
        listing = {}
    print(f"[scrape] {len(listing)} PDF links on the listing page", file=sys.stderr)

    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        wines = wines[: args.limit]

    manifest: dict = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}

    fetched = cached = failed = unresolved = 0
    for w in tqdm(wines, desc="fetch-national-specs", leave=False):
        slug = w["slug"]
        ov = overrides.get(slug) or {}
        url = ov.get("url") or listing.get(_match_key(w["name"]))
        if not url:
            unresolved += 1
            manifest[slug] = {**manifest.get(slug, {}), "status": "no-url",
                              "name": w["name"]}
            continue

        existing = next((p for p in OUT_DIR.glob(f"{slug}.*")
                         if p.suffix.lower() in (".pdf",)), None)
        if existing and not args.refresh:
            cached += 1
            continue

        r = fetch_one(session, url)
        if r is None:
            failed += 1
            manifest[slug] = {**manifest.get(slug, {}), "status": "fetch-error",
                              "source_url": url}
            continue

        out_path = OUT_DIR / f"{slug}.pdf"
        out_path.write_bytes(r.content)
        sha = hashlib.sha256(r.content).hexdigest()
        manifest[slug] = {
            "status": "ok",
            "filename": out_path.name,
            "format": "pdf",
            "source_url": url,
            "final_url": r.url,
            "source_org": ov.get("source_org", "moa-cy"),
            "file_number": ov.get("file_number") or w.get("fileNumber", ""),
            "from_override": bool(ov.get("url")),
            "bytes": len(r.content),
            "sha256": sha,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        fetched += 1
        time.sleep(0.4)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[done] fetched={fetched} cached={cached} failed={failed} "
          f"unresolved={unresolved} → {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
