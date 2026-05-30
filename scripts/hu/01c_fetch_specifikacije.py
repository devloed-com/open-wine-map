"""Fetch the HU national *termékleírás* PDFs for the grandfathered HU
wines (stage 01c).

The 15 HU wines whose eAmbrosia entry carries only a non-fetchable
`Ares(...)` reference (no EU-OJ EGYSÉGES DOKUMENTUM) have their canonical
product specification published as a PDF by the Agrárminisztérium at
`boraszat.kormany.hu/termekleirasok2` (the leaf pages are JS shells; the
real PDFs live at opaque-token `/download/...` URLs). URLs are
curator-pinned in `raw/hu/national-specs/manual_overrides.json`; this
stage fetches each into `raw/hu/national-specs/<slug>.pdf` and records
provenance in `manifest.json`.

Mirrors the RO ONVPV / ES MAPA / GR ΥΠΑΑΤ national-spec fetch stage.
`boraszat.kormany.hu` fails some HTTPS stacks with a TLS issuer error
but is fine for `requests` with a browser-ish UA (verified 2026-05-30);
the tokaj entry uses the tokajiborvidek.hu council mirror.

Re-runnable: cached PDFs are kept; pass `--refresh` to re-fetch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "raw" / "hu" / "national-specs"
OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "Mozilla/5.0 (open-wine-map/0.0.1; "
    "+https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com)"
)
LICENSE = (
    "© Agrárminisztérium (boraszat.kormany.hu) / the submitting Hegyközségi "
    "Tanács. Hungarian official wine product specification (termékleírás); "
    "public official act, not copyright-protected (Szjt. 1999. évi LXXVI. "
    "törvény §1(4))."
)


def _curl_fetch(url: str, dest: Path) -> tuple[bytes, str]:
    """Fetch `url` to `dest` via curl. boraszat.kormany.hu serves an
    incomplete certificate chain that Python's `requests`/`ssl` rejects
    ('unable to get local issuer certificate') but curl handles; the
    codebase already shells out to system tools (pdftotext, antiword).
    Returns (bytes, final_url)."""
    eff = subprocess.run(
        ["curl", "-fsSL", "--retry", "2", "--max-time", "120",
         "-A", UA, "-w", "%{url_effective}", "-o", str(dest), url],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return dest.read_bytes(), (eff or url)


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

    for slug, entry in overrides.items():
        if slug.startswith("__"):
            continue
        url = (entry or {}).get("url")
        if not url:
            continue

        existing = OUT_DIR / f"{slug}.pdf"
        if existing.exists() and not args.refresh:
            n_cached += 1
            manifest[slug] = {
                "status": "cached",
                "filename": existing.name,
                "format": "pdf",
                "source_url": url,
                "source_org": entry.get("source_org", "agrarminiszterium"),
                "file_number": entry.get("file_number", ""),
                "sha256": hashlib.sha256(existing.read_bytes()).hexdigest(),
            }
            print(f"  [cached] {slug}", file=sys.stderr)
            continue

        out_path = OUT_DIR / f"{slug}.pdf"
        try:
            with tempfile.NamedTemporaryFile(dir=OUT_DIR, delete=False) as tf:
                tmp = Path(tf.name)
            content, final_url = _curl_fetch(url, tmp)
            tmp.replace(out_path)
        except Exception as exc:  # noqa: BLE001
            n_bad += 1
            err = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            manifest[slug] = {"status": "fetch-error", "source_url": url,
                              "error": (err or str(exc))[:200]}
            print(f"  [error] {slug}: {(err or exc)}", file=sys.stderr)
            continue

        sha = hashlib.sha256(content).hexdigest()
        n_ok += 1
        manifest[slug] = {
            "status": "ok",
            "filename": out_path.name,
            "format": "pdf",
            "source_url": url,
            "final_url": final_url,
            "source_org": entry.get("source_org", "agrarminiszterium"),
            "file_number": entry.get("file_number", ""),
            "bytes": len(content),
            "sha256": sha,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"  [ok] {slug} ({len(content)} bytes)", file=sys.stderr)

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
