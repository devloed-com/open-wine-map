"""Fetch every cantonal wine règlement / Reglement / regolamento.

Pipeline stage 01 (ch).

For each of the 26 cantons listed in `_lib/ch/canton.py`:
  - look up the URL in `_lib/ch/reglement_index.py` (the seeded
    + agent-researched table covering all 26 cantons)
  - allow override from `raw/ch/reglements/manual_overrides.json`
  - download to `raw/ch/reglements/<canton>/<filename>.{html,pdf}`
  - record sha256 + license + source URL in `manifest.json`

Per-canton manifest entry:
  {canton, shelf, lang, format, url, source, license, sha256, bytes,
   fetched_at, status (ok | manual-override | fetch-failed | unknown-format)}

The downloaded files are passed to stage 02 (`02_extract_reglements.py`)
which parses each canton's règlement into the per-AOC variety + commune
list. The fetch step is intentionally dumb — no parsing here — so a
fetch failure doesn't block other cantons.

Manual overrides (gitignored, optional):
  raw/ch/reglements/manual_overrides.json
  {
    "<canton>": {
      "url": "https://...",
      "format": "html|pdf",
      "lang": "de|fr|it",
      "note": "curator note"
    }
  }
Override URL takes precedence; everything else falls back to the seeded
registry entry.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# LexWork SPA URLs (used by ~16 cantons: AG, AI, AR, BE, BL, BS, FR,
# GL, GR, LU, NW, OW, SG, SH, SO, TG, ZG, …) serve a JS shell, not the
# actual règlement text. The real content lives behind an API at
# `/api/<lang>/texts_of_law/<X>` which returns a JSON metadata blob
# whose `pdf_link` field points to the canonical PDF. Stage 01 detects
# the SPA pattern and re-fetches via API + PDF.
LEXWORK_APP_RE = re.compile(r"/app/(de|fr|it)/texts_of_law/(.+)$")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.ch.canton import CANTON_CODES  # noqa: E402
from _lib.ch.reglement_index import CANTON_REGLEMENT_URLS  # noqa: E402

OUT_DIR = ROOT / "raw" / "ch" / "reglements"
MANIFEST = OUT_DIR / "manifest.json"
OVERRIDES = OUT_DIR / "manual_overrides.json"

UA = (
    "open-wine-map/0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_overrides() -> dict:
    if OVERRIDES.exists():
        try:
            return json.loads(OVERRIDES.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[01-ch] WARN manual_overrides.json invalid JSON: {e}",
                  file=sys.stderr)
    return {}


def _resolve_entry(canton: str, overrides: dict) -> dict | None:
    """Merge override + seeded-registry entry into one resolved dict."""
    seeded = CANTON_REGLEMENT_URLS.get(canton, {})
    override = overrides.get(canton, {})
    merged = {**seeded, **{k: v for k, v in override.items() if v}}
    if not merged.get("url"):
        return None
    if not merged.get("format"):
        # Infer from URL extension.
        path = urlparse(merged["url"]).path.lower()
        merged["format"] = "pdf" if path.endswith(".pdf") else "html"
    return merged


def _fetch(url: str) -> bytes:
    print(f"[01-ch] fetch {url}", file=sys.stderr)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=180,
                     allow_redirects=True)
    r.raise_for_status()
    return r.content


def _resolve_lexwork(url: str) -> tuple[str, str] | None:
    """If the URL is a LexWork SPA path (`/app/<lang>/texts_of_law/X`),
    dereference it via the API to the canonical PDF link.

    Returns (pdf_url, "pdf") on success, None if the URL isn't LexWork
    or the API call fails (caller falls back to the original URL)."""
    parsed = urlparse(url)
    m = LEXWORK_APP_RE.search(parsed.path)
    if not m:
        return None
    lang, shelf = m.group(1), m.group(2)
    api_url = f"{parsed.scheme}://{parsed.netloc}/api/{lang}/texts_of_law/{shelf}"
    try:
        body = _fetch(api_url)
        meta = json.loads(body)
        pdf_url = meta.get("text_of_law", {}).get("pdf_link", "")
        if pdf_url:
            return pdf_url, "pdf"
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"[01-ch] LexWork API call failed for {api_url}: {e}",
              file=sys.stderr)
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    overrides = _load_overrides()

    results: dict[str, dict] = {}
    n_ok = n_fail = n_unknown = n_overridden = 0

    for canton in CANTON_CODES:
        entry = _resolve_entry(canton, overrides)
        if entry is None:
            print(f"[01-ch] {canton}: no URL in registry or overrides — skip",
                  file=sys.stderr)
            results[canton] = {
                "canton": canton, "status": "no-url",
            }
            n_unknown += 1
            continue

        # LexWork-SPA bypass: dereference to the canonical PDF URL.
        effective_url = entry["url"]
        effective_fmt = entry["format"]
        lexwork = _resolve_lexwork(effective_url)
        if lexwork is not None:
            effective_url, effective_fmt = lexwork

        canton_dir = OUT_DIR / canton
        canton_dir.mkdir(parents=True, exist_ok=True)
        dest = canton_dir / f"reglement.{effective_fmt}"

        if dest.exists() and not overrides.get(canton):
            body = dest.read_bytes()
            print(f"[01-ch] {canton}: cached {dest.relative_to(ROOT)} "
                  f"({len(body):,} bytes)", file=sys.stderr)
            status = "ok-cached"
        else:
            try:
                body = _fetch(effective_url)
            except requests.RequestException as e:
                print(f"[01-ch] {canton}: fetch failed — {e}", file=sys.stderr)
                results[canton] = {
                    "canton": canton,
                    "status": "fetch-failed",
                    "url": effective_url,
                    "error": str(e),
                }
                n_fail += 1
                continue
            dest.write_bytes(body)
            print(f"[01-ch] {canton}: saved {dest.relative_to(ROOT)} "
                  f"({len(body):,} bytes)", file=sys.stderr)
            status = "ok-fetched" + (",manual-override"
                                     if overrides.get(canton) else "")
        fmt = effective_fmt

        results[canton] = {
            "canton": canton,
            "status": status,
            "url": entry["url"],
            "shelf": entry.get("shelf", ""),
            "lang": entry.get("lang", ""),
            "format": fmt,
            "source": entry.get("source", ""),
            "license": entry.get("license", ""),
            "sha256": _sha256(body),
            "bytes": len(body),
            "filename": dest.name,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        n_ok += 1
        if overrides.get(canton):
            n_overridden += 1

    MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_total": len(CANTON_CODES),
        "n_ok": n_ok,
        "n_overridden": n_overridden,
        "n_failed": n_fail,
        "n_no_url": n_unknown,
        "by_canton": results,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] 01-ch: ok={n_ok} failed={n_fail} no_url={n_unknown} "
        f"overridden={n_overridden} → {MANIFEST.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
