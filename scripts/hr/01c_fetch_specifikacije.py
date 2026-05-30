"""Fetch the Croatian national specifikacija proizvoda for each HR wine
pinned in `raw/hr/specifikacije/manual_overrides.json`.

Pipeline stage 01c (hr). Sibling of `01_fetch_pliegos.py`, modelled on
`scripts/si/01c_fetch_specifikacije.py`. Covers the 16 grandfathered HR
wines whose EU-OJ JEDINSTVENI DOKUMENT was never published — their
canonical source is the Ministarstvo poljoprivrede (MPS) per-wine
SPECIFIKACIJA PROIZVODA, hosted at poljoprivreda.gov.hr in three
formats: legacy `.doc` (14), `.docx` (Primorska Hrvatska), PDF (Dingač).

These URLs deliberately live in their own overrides file (NOT
`raw/hr/oj-pages/manual_overrides.json`) so they never enter the
EU-OJ stage 01/02 path — stage 01 would save the Dingač PDF as `ok`
and stage 02's HTML JEDINSTVENI-DOKUMENT parser cannot read
`.doc`/`.docx`/`.pdf`. The national specs ride this parallel
01c → 02f → stage-04-augment layer instead.

Each download lands at `raw/hr/specifikacije/<slug>.<ext>` with the
extension chosen from the Content-Type header. A manifest records
sha256, fetch time, source URL.

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
OVERRIDES_PATH = ROOT / "raw" / "hr" / "specifikacije" / "manual_overrides.json"
OUT_DIR = ROOT / "raw" / "hr" / "specifikacije"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    lurl = url.lower()
    if "officedocument.wordprocessingml" in ct or lurl.endswith(".docx"):
        return "docx"
    if "msword" in ct or "application/vnd.ms-word" in ct or lurl.endswith(".doc"):
        return "doc"
    if "pdf" in ct or lurl.endswith(".pdf"):
        return "pdf"
    return "html"


def fetch_one(session: requests.Session, url: str) -> requests.Response | None:
    try:
        return session.get(url, timeout=60, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[err] {url[:90]}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--throttle", type=float, default=0.4)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    if not OVERRIDES_PATH.exists():
        print(f"error: {OVERRIDES_PATH} missing", file=sys.stderr)
        return 1
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    rows = [(k, v) for k, v in overrides.items()
            if not k.startswith("__") and v.get("url")]
    if args.only:
        needles = [s.lower() for s in args.only]
        rows = [(s, v) for s, v in rows if any(n in s for n in needles)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            manifest = {}

    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/msword,application/pdf,*/*",
        "Accept-Language": "hr",
    })

    n_ok = n_cached = n_bad = 0
    for slug, entry in tqdm(rows, desc="hr-specifikacije", leave=False):
        url = entry["url"]
        cached = list(OUT_DIR.glob(f"{slug}.*"))
        cached = [p for p in cached if p.suffix in {".doc", ".docx", ".pdf", ".html"}]
        if cached and not args.refresh:
            n_cached += 1
            continue

        r = fetch_one(session, url)
        time.sleep(args.throttle)
        if r is None or r.status_code != 200:
            manifest[slug] = {
                "status": "fetch-error",
                "source_url": url,
                "http_status": r.status_code if r else 0,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue

        ext = _ext_for(r.headers.get("Content-Type"), url)
        for prior in OUT_DIR.glob(f"{slug}.*"):
            if prior.suffix != f".{ext}":
                prior.unlink()
        out_path = OUT_DIR / f"{slug}.{ext}"
        if ext == "html":
            out_path.write_text(r.text, encoding="utf-8")
        else:
            out_path.write_bytes(r.content)
        manifest[slug] = {
            "status": "ok",
            "source_url": url,
            "final_url": r.url,
            "format": ext,
            "bytes": len(r.content),
            "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
            "source_org": entry.get("source_org", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        n_ok += 1

    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": (
            "MPS product specifications (poljoprivreda.gov.hr): public regulator "
            "material, reuse with attribution."
        ),
        "n_wines": len(rows),
        "counts": {"ok": n_ok, "cached": n_cached, "fetch_error": n_bad},
        "by_slug": manifest,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[done] ok={n_ok} cached={n_cached} bad={n_bad} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
