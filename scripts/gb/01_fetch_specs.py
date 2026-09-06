"""Fetch each UK wine GI's product specification from GOV.UK.

Pipeline stage 01 (gb).

The register entries written by stage 00 each carry a `spec_url` on
`assets.publishing.service.gov.uk`. There is no WAF, no cookie gate and
no JavaScript challenge — unlike the EUR-Lex countries, which is why the
UK pipeline ships no `01b_solve_waf.py` sibling.

Two document formats are served, keyed by `Content-Type`:

  - **PDF** (5 of 6) — the four 2011 DEFRA specifications plus Darnibole.
  - **.docx** (1 of 6) — Sussex, the only post-2021 UK-scheme
    registration. Handled downstream by the stdlib zip →
    `word/document.xml` route the HR pipeline already uses.

Cached documents are reused unless `--refresh` is passed; the manifest
records sha256 + byte count + fetched_at per slug so stage 02 can attach
provenance and so a rerun is a no-op.

Reads:  raw/gb/gov-uk/index.json
Writes: raw/gb/specs/<slug>.{pdf,docx} + manifest.json
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

ROOT = Path(__file__).resolve().parents[2]
INDEX_IN = ROOT / "raw" / "gb" / "gov-uk" / "index.json"
OUT_DIR = ROOT / "raw" / "gb" / "specs"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
LICENSE = "Open Government Licence v3.0 — © Crown copyright, DEFRA / GOV.UK"

_EXT_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[ct]
    for ext in (".pdf", ".docx", ".doc"):
        if url.lower().endswith(ext):
            return ext
    return ".bin"


def _cached(slug: str) -> Path | None:
    for ext in (".pdf", ".docx", ".doc", ".bin"):
        p = OUT_DIR / f"{slug}{ext}"
        if p.exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[],
                    help="restrict to slugs containing this substring (repeatable)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download even when a cached document exists")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds to pause between downloads (default 1.0)")
    args = ap.parse_args()

    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/gb/00_fetch_data.py first",
              file=sys.stderr)
        return 1

    wines = json.loads(INDEX_IN.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
    by_slug: dict[str, dict] = manifest.get("by_slug", {})

    session = requests.Session()
    session.headers["User-Agent"] = UA
    ok = cached = failed = 0

    for w in wines:
        slug, url = w["slug"], w.get("spec_url") or ""
        if not url:
            by_slug[slug] = {"status": "no-spec-url", "source_url": ""}
            failed += 1
            print(f"[miss] {slug}: no product-specification URL", file=sys.stderr)
            continue
        existing = _cached(slug)
        if existing and not args.refresh:
            cached += 1
            print(f"[skip] {slug}: cached ({existing.name})", file=sys.stderr)
            continue
        try:
            r = session.get(url, timeout=120)
            r.raise_for_status()
        except requests.RequestException as exc:
            by_slug[slug] = {"status": "fetch-error", "source_url": url,
                             "error": str(exc)[:300]}
            failed += 1
            print(f"[fail] {slug}: {exc}", file=sys.stderr)
            continue
        ext = _ext_for(r.headers.get("Content-Type", ""), r.url)
        # A format change (docx → pdf on a re-registration) must not leave
        # the previous document behind for stage 02 to pick up.
        for stale in (OUT_DIR.glob(f"{slug}.*")):
            if stale.suffix != ext and stale.name != "manifest.json":
                stale.unlink()
        out_path = OUT_DIR / f"{slug}{ext}"
        out_path.write_bytes(r.content)
        by_slug[slug] = {
            "status": "ok",
            "filename": out_path.name,
            "format": ext.lstrip("."),
            "source_url": url,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type", ""),
            "bytes": len(r.content),
            "sha256": _sha256(r.content),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "register_url": w.get("register_url", ""),
            "spec_title": w.get("spec_title", ""),
        }
        ok += 1
        print(f"[ok]   {slug}: {len(r.content)} bytes → {out_path.name}", file=sys.stderr)
        if args.delay:
            time.sleep(args.delay)

    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": LICENSE,
        "by_slug": dict(sorted(by_slug.items())),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] fetched={ok} cached={cached} failed={failed} "
          f"→ {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
