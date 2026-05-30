"""Fetch the Greek national product specification for each GR wine whose
`raw/gr/national-specs/manual_overrides.json` entry carries a URL.

Pipeline stage 01c (gr). Sibling of `01_fetch_pliegos.py` — covers the
canonical ΥΠΑΑΤ (Greek Ministry of Rural Development and Food) regulator
sources that stage 01's EU-OJ ΕΝΙΑΙΟ-ΕΓΓΡΑΦΟ fetcher / parser doesn't
understand. 138 of 147 GR wines are pre-2009 grandfathered names with no
fetchable EU single document; their canonical public spec is the national
`προδιαγραφή προϊόντος` / `τεχνικός φάκελος` published on minagric.gr.

Host caveat: the modern `https://www.minagric.gr/...` host and
`minagric.gov.gr` are Akamai/edgesuite WAF-blocked (HTTP 403) to non-browser
clients; the canonical reachable host is the legacy four-w host
`http://wwww.minagric.gr/greek/data/pop-pge/` (four w's, plain HTTP). The
override URLs already point at that host.

Each download lands at `raw/gr/national-specs/<slug>.<ext>` with extension
chosen from the URL / Content-Type (`.pdf`, `.doc`, `.docx`). A manifest
records sha256, fetch time, source URL. Stage 02f
(`02f_extract_national_specs.py`) consumes these.

Re-runnable: cached files are kept; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
OVERRIDES_PATH = ROOT / "raw" / "gr" / "national-specs" / "manual_overrides.json"
OUT_DIR = ROOT / "raw" / "gr" / "national-specs"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    u = url.lower()
    if "officedocument.wordprocessingml" in ct or u.endswith(".docx"):
        return "docx"
    if "msword" in ct or "application/vnd.ms-word" in ct or u.endswith(".doc"):
        return "doc"
    if "pdf" in ct or u.endswith(".pdf"):
        return "pdf"
    # default to the URL's own extension when the server omits a useful CT
    for ext in ("docx", "doc", "pdf"):
        if u.endswith("." + ext):
            return ext
    return "bin"


def fetch_one(session: requests.Session, url: str) -> requests.Response | None:
    try:
        r = session.get(url, timeout=90, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[err] {url[:90]}: {exc}", file=sys.stderr)
        return None
    # eAmbrosia's attachment API serves a valid PDF body under HTTP 202
    # (its AWS WAF status); accept 200/202 as long as there's content.
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

    if not OVERRIDES_PATH.exists():
        print(f"error: {OVERRIDES_PATH} missing", file=sys.stderr)
        return 1

    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    items = sorted(overrides.items())
    if args.only:
        needles = [s.lower() for s in args.only]
        items = [(s, v) for s, v in items if any(n in s.lower() for n in needles)]
    if args.limit:
        items = items[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "el,en;q=0.8"})

    fetched = cached = failed = 0
    for slug, entry in tqdm(items, desc="fetch-national-specs", leave=False):
        url = (entry or {}).get("url")
        if not url:
            continue
        # locate an existing cache file regardless of extension
        existing = next((p for p in OUT_DIR.glob(f"{slug}.*")
                         if p.suffix.lower() in (".pdf", ".doc", ".docx", ".bin")), None)
        if existing and not args.refresh:
            cached += 1
            continue

        r = fetch_one(session, url)
        if r is None:
            failed += 1
            manifest[slug] = {**manifest.get(slug, {}), "status": "fetch-error",
                              "source_url": url}
            continue

        ext = _ext_for(r.headers.get("Content-Type", ""), url)
        out_path = OUT_DIR / f"{slug}.{ext}"
        # drop a stale cache file of a different extension
        for p in OUT_DIR.glob(f"{slug}.*"):
            if p.suffix.lower() in (".pdf", ".doc", ".docx", ".bin") and p != out_path:
                p.unlink()
        out_path.write_bytes(r.content)
        sha = hashlib.sha256(r.content).hexdigest()
        manifest[slug] = {
            "status": "ok",
            "filename": out_path.name,
            "format": ext,
            "source_url": url,
            "final_url": r.url,
            "source_org": (entry or {}).get("source_org", "ypaat"),
            "file_number": (entry or {}).get("file_number", ""),
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
          f"→ {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
