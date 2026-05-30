"""Fetch the ONVPV national *caiete de sarcini* for the grandfathered RO
wines (stage 01c).

The ~14 RO wines whose eAmbrosia entry carries only a non-fetchable
`Ares(...)` reference (no EU-OJ DOCUMENT UNIC) have their canonical
product specification published as a PDF by the Oficiul Național al
Viei și Produselor Vitivinicole (`onvpv.ro`). URLs are curator-pinned
in `raw/ro/national-specs/manual_overrides.json`; this stage fetches
each into `raw/ro/national-specs/<slug>.pdf` and records provenance in
`manifest.json`.

Mirrors the ES MAPA / GR ΥΠΑΑΤ / HR–SI national-spec fetch stage. The
ONVPV host is plain and WAF-free (verified 2026-05-30) — no Playwright
bootstrap needed.

Re-runnable: cached PDFs are kept; pass `--refresh` to re-fetch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "raw" / "ro" / "national-specs"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
LICENSE = (
    "© Oficiul Național al Viei și Produselor Vitivinicole (ONVPV). "
    "Romanian official wine product specification (caiet de sarcini); "
    "public regulatory document."
)


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    u = url.lower()
    if "pdf" in ct or u.endswith(".pdf"):
        return "pdf"
    if "officedocument.wordprocessingml" in ct or u.endswith(".docx"):
        return "docx"
    if "msword" in ct or u.endswith(".doc"):
        return "doc"
    return "pdf"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not OVERRIDES_PATH.exists():
        print(f"[error] no overrides file at {OVERRIDES_PATH}", file=sys.stderr)
        return 2
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    manifest: dict[str, dict] = {}
    n_ok = n_cached = n_bad = 0
    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    for slug, entry in overrides.items():
        if slug.startswith("__"):
            continue
        url = (entry or {}).get("url")
        if not url:
            continue

        existing = next(
            (p for p in OUT_DIR.glob(f"{slug}.*")
             if p.suffix.lower() in (".pdf", ".doc", ".docx")),
            None,
        )
        if existing and not args.refresh:
            n_cached += 1
            manifest[slug] = {
                "status": "cached",
                "filename": existing.name,
                "format": existing.suffix.lower().lstrip("."),
                "source_url": url,
                "source_org": entry.get("source_org", "onvpv"),
                "file_number": entry.get("file_number", ""),
                "sha256": hashlib.sha256(existing.read_bytes()).hexdigest(),
            }
            print(f"  [cached] {slug}", file=sys.stderr)
            continue

        try:
            r = sess.get(url, timeout=60, allow_redirects=True)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            n_bad += 1
            manifest[slug] = {"status": "fetch-error", "source_url": url,
                              "error": str(exc)[:200]}
            print(f"  [error] {slug}: {exc}", file=sys.stderr)
            continue

        ext = _ext_for(r.headers.get("Content-Type", ""), url)
        out_path = OUT_DIR / f"{slug}.{ext}"
        for p in OUT_DIR.glob(f"{slug}.*"):
            if p.suffix.lower() in (".pdf", ".doc", ".docx") and p != out_path:
                p.unlink()
        out_path.write_bytes(r.content)
        sha = hashlib.sha256(r.content).hexdigest()
        n_ok += 1
        manifest[slug] = {
            "status": "ok",
            "filename": out_path.name,
            "format": ext,
            "source_url": url,
            "final_url": r.url,
            "source_org": entry.get("source_org", "onvpv"),
            "file_number": entry.get("file_number", ""),
            "bytes": len(r.content),
            "sha256": sha,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"  [ok] {slug} ({len(r.content)} bytes)", file=sys.stderr)

    MANIFEST_PATH.write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": LICENSE,
            "n_wines": len([k for k in overrides if not k.startswith("__")]),
            "counts": {"ok": n_ok, "cached": n_cached, "fetch_error": n_bad},
            "by_slug": manifest,
        }, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[done] ok={n_ok} cached={n_cached} error={n_bad} → {OUT_DIR}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
