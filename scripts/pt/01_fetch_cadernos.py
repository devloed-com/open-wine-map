"""Fetch the IVV caderno-de-especificações PDF for each PT wine GI.

Pipeline stage 01 (pt).

For each wine in `raw/pt/eambrosia/index.json`, match by normalised name
against `raw/pt/ivv/cadernos-index.json` (scraped in stage 00) and pull
the IVV PDF. Manual overrides live at
`raw/pt/ivv/cadernos/manual_overrides.json` (gitignored) — slug-keyed
`{pdf_url, source_org, verification_note}` — and take precedence over
the auto-matched URL. Mirrors the FR
`raw/inao/cahiers/manual_overrides.json` and ES
`raw/es/oj-pages/manual_overrides.json` patterns.

Outputs:
  raw/pt/ivv/cadernos/<slug>.pdf       (sha-pinned)
  raw/pt/ivv/cadernos/manifest.json    (per-slug status + sha)

Wines without an IVV match and without an override end up with
`status: "no-caderno"` and no PDF; stage 02 emits stub records for them.
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
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.pt.name_match import build_lookup, find_match  # noqa: E402

INDEX_PATH = ROOT / "raw" / "pt" / "eambrosia" / "index.json"
IVV_INDEX_PATH = ROOT / "raw" / "pt" / "ivv" / "cadernos-index.json"
OUT_DIR = ROOT / "raw" / "pt" / "ivv" / "cadernos"
MANIFEST_PATH = OUT_DIR / "manifest.json"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    try:
        r = session.get(url, timeout=120, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[err] {url[:80]}: {exc}", file=sys.stderr)
        return None
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.2, help="seconds between fetches")
    ap.add_argument("--limit", type=int, default=0, help="cap on entries (0 = all)")
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="slug substring (repeatable)",
    )
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(
            f"error: {INDEX_PATH} missing — run scripts/pt/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1
    if not IVV_INDEX_PATH.exists():
        print(
            f"error: {IVV_INDEX_PATH} missing — run scripts/pt/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    overrides: dict[str, dict] = {}
    if OVERRIDES_PATH.exists():
        try:
            raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
            overrides = {k: v for k, v in raw.items() if not k.startswith("__")}
        except (ValueError, OSError) as exc:
            print(f"[warn] could not read overrides: {exc}", file=sys.stderr)

    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    ivv_entries = json.loads(IVV_INDEX_PATH.read_text(encoding="utf-8"))["entries"]
    ivv_lookup = build_lookup(ivv_entries)

    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    if args.limit:
        wines = wines[: args.limit]

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/pdf",
        }
    )

    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists() and not args.refresh:
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            manifest = {}

    n_ok = n_cached = n_no_caderno = n_bad = n_override = 0
    for w in tqdm(wines, desc="cadernos", leave=False):
        slug = w["slug"]
        pdf_path = OUT_DIR / f"{slug}.pdf"
        if pdf_path.exists() and not args.refresh:
            n_cached += 1
            continue

        override = overrides.get(slug) or overrides.get(w["giIdentifier"])
        source_url: str | None
        source_kind: str
        if override and override.get("pdf_url"):
            source_url = override["pdf_url"]
            source_kind = "override"
        else:
            match = find_match(w["name"], ivv_lookup)
            if match is None:
                manifest[slug] = {
                    "status": "no-caderno",
                    "name": w["name"],
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_no_caderno += 1
                continue
            source_url = match["pdf_url"]
            source_kind = "ivv"

        r = fetch(session, source_url)
        time.sleep(args.throttle)
        if r is None or r.status_code != 200:
            manifest[slug] = {
                "status": "fetch-error",
                "source_url": source_url,
                "http_status": r.status_code if r else 0,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "pdf" not in ctype and not r.content[:4] == b"%PDF":
            manifest[slug] = {
                "status": "not-pdf",
                "source_url": source_url,
                "content_type": ctype,
                "bytes": len(r.content),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            n_bad += 1
            continue

        pdf_path.write_bytes(r.content)
        sha = _sha256(r.content)
        manifest[slug] = {
            "status": "ok",
            "source_url": source_url,
            "final_url": r.url,
            "source_kind": source_kind,
            "sha256": sha,
            "bytes": len(r.content),
            "from_override": source_kind == "override",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if source_kind == "override":
            n_override += 1
        n_ok += 1

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "license": (
                    "© Instituto da Vinha e do Vinho, I.P. — public regulator "
                    "data. Per-PDF status with sha256."
                ),
                "n_wines": len(wines),
                "counts": {
                    "ok": n_ok,
                    "cached": n_cached,
                    "override": n_override,
                    "no_caderno": n_no_caderno,
                    "fetch_error_or_not_pdf": n_bad,
                },
                "by_slug": manifest,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(
        f"[done] ok={n_ok} cached={n_cached} override={n_override} "
        f"no-caderno={n_no_caderno} bad={n_bad} → "
        f"{OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
