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
from urllib.parse import unquote, urljoin, urlparse

import requests

# LexWork SPA URLs (used by ~16 cantons: AG, AI, AR, BE, BL, BS, FR,
# GL, GR, LU, NW, OW, SG, SH, SO, TG, ZG, …) serve a JS shell, not the
# actual règlement text. The real content lives behind an API at
# `/api/<lang>/texts_of_law/<X>` which returns a JSON metadata blob
# whose `pdf_link` field points to the canonical PDF. Stage 01 detects
# the SPA pattern and re-fetches via API + PDF.
LEXWORK_APP_RE = re.compile(r"/app/(de|fr|it)/texts_of_law/(.+)$")

# Some cantonal collections (Jura's RSJU) answer the registered URL with
# an HTML shell that only embeds the règlement in a PDF.js viewer: the
# text is in the PDF the viewer's `file=` parameter points at, and the
# shell itself carries nothing but site navigation. Stage 02 then scanned
# the navigation and found no variety and no commune. Detect the viewer
# and follow its `file=` link to the PDF.
PDF_VIEWER_FILE_RE = re.compile(
    r"""(?:PDFViewer|pdfjs|pdf\.js)/[^"'<>]*?viewer\.html\?[^"'<>]*?\bfile=([^"'&<>]+)""",
    re.I,
)

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


def _is_pdf(body: bytes) -> bool:
    return body.lstrip()[:5] == b"%PDF-"


def fetch_roster_rulings() -> int:
    """The administrative rulings that carry a canton's roster
    (scripts/_lib/ch/roster_rulings.json) into raw/ch/rulings/<slug>.pdf,
    each checked against the sha256 its transcription was read from.
    Returns the number of rulings that could not be fetched or changed."""
    from _lib.ch import roster_rulings

    out_dir = roster_rulings.RULINGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    bad = 0
    for slug, entry in roster_rulings.load().items():
        dest = out_dir / f"{slug}.pdf"
        if dest.exists() and _is_pdf(dest.read_bytes()):
            body, status = dest.read_bytes(), "ok-cached"
        else:
            try:
                lexwork = _resolve_lexwork(entry["url"])
                body = _fetch(lexwork[0] if lexwork else entry["url"])
            except requests.RequestException as e:
                print(f"[01-ch] ruling {slug}: fetch failed — {e}", file=sys.stderr)
                entries[slug] = {"status": "fetch-failed", "url": entry["url"], "error": str(e)}
                bad += 1
                continue
            if not _is_pdf(body):
                print(f"[01-ch] ruling {slug}: {entry['url']} did not return a PDF",
                      file=sys.stderr)
                entries[slug] = {"status": "not-a-pdf", "url": entry["url"]}
                bad += 1
                continue
            dest.write_bytes(body)
            status = "ok-fetched"
        sha = _sha256(body)
        if sha != entry.get("sha256"):
            status = "sha-mismatch"
            bad += 1
            print(f"[01-ch] ruling {slug}: STALE — the PDF changed since its roster was "
                  f"transcribed (sha256 {sha[:12]}… ≠ pinned {str(entry.get('sha256'))[:12]}…); "
                  "re-read scripts/_lib/ch/roster_rulings.json", file=sys.stderr)
        entries[slug] = {
            "status": status, "url": entry["url"], "ruling": entry["ruling"],
            "sha256": sha, "bytes": len(body), "filename": dest.name,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"[01-ch] ruling {slug}: {status} ({len(body):,} bytes)", file=sys.stderr)
        # The wine-type clauses of a ruling whose roster annex is published
        # apart (Zürich): the ruling itself, as <slug>.types.pdf.
        doc = (entry.get("wine_types") or {}).get("document")
        if doc:
            types_dest = out_dir / f"{slug}.types.pdf"
            if types_dest.exists() and _is_pdf(types_dest.read_bytes()):
                types_body, types_status = types_dest.read_bytes(), "ok-cached"
            else:
                try:
                    types_body = _fetch(doc["url"])
                except requests.RequestException as e:
                    print(f"[01-ch] ruling {slug} (wine types): fetch failed — {e}",
                          file=sys.stderr)
                    entries[slug]["wine_types"] = {"status": "fetch-failed", "url": doc["url"]}
                    bad += 1
                    continue
                if not _is_pdf(types_body):
                    print(f"[01-ch] ruling {slug} (wine types): {doc['url']} did not return "
                          "a PDF", file=sys.stderr)
                    entries[slug]["wine_types"] = {"status": "not-a-pdf", "url": doc["url"]}
                    bad += 1
                    continue
                types_dest.write_bytes(types_body)
                types_status = "ok-fetched"
            types_sha = _sha256(types_body)
            if types_sha != doc.get("sha256"):
                types_status = "sha-mismatch"
                bad += 1
                print(f"[01-ch] ruling {slug} (wine types): STALE — the PDF changed since its "
                      "clauses were transcribed; re-read scripts/_lib/ch/roster_rulings.json",
                      file=sys.stderr)
            entries[slug]["wine_types"] = {
                "status": types_status, "url": doc["url"], "sha256": types_sha,
                "bytes": len(types_body), "filename": types_dest.name,
            }
            print(f"[01-ch] ruling {slug} (wine types): {types_status} "
                  f"({len(types_body):,} bytes)", file=sys.stderr)
    (out_dir / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "by_slug": entries,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return bad


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


def _embedded_pdf_url(html_body: bytes, page_url: str) -> str | None:
    """Return the PDF a PDF.js viewer shell embeds, resolved against
    `page_url`, or None when the page is not such a shell."""
    m = PDF_VIEWER_FILE_RE.search(html_body.decode("utf-8", errors="replace"))
    if not m:
        return None
    return urljoin(page_url, unquote(m.group(1)))


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

        if dest.exists() and effective_fmt == "pdf" and not _is_pdf(dest.read_bytes()):
            # A portal's app shell saved under .pdf (Uri's LexFind link, until
            # 2026-11-17): the "cached règlement" was never a document.
            print(f"[01-ch] {canton}: cached {dest.relative_to(ROOT)} is not a PDF — refetching",
                  file=sys.stderr)
            dest.unlink()
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
            if effective_fmt == "pdf" and not _is_pdf(body):
                print(f"[01-ch] {canton}: {effective_url} did not return a PDF "
                      f"({body[:40]!r}) — not saved", file=sys.stderr)
                results[canton] = {
                    "canton": canton, "status": "not-a-pdf", "url": effective_url,
                }
                n_fail += 1
                continue
            dest.write_bytes(body)
            print(f"[01-ch] {canton}: saved {dest.relative_to(ROOT)} "
                  f"({len(body):,} bytes)", file=sys.stderr)
            status = "ok-fetched" + (",manual-override"
                                     if overrides.get(canton) else "")
        fmt = effective_fmt

        # PDF.js-viewer shell (RSJU): the règlement is the embedded PDF,
        # so fetch that instead and hand stage 02 a `reglement.pdf`.
        if fmt == "html":
            embedded = _embedded_pdf_url(body, effective_url)
            if embedded:
                pdf_dest = canton_dir / "reglement.pdf"
                if pdf_dest.exists() and not overrides.get(canton):
                    body = pdf_dest.read_bytes()
                    print(f"[01-ch] {canton}: viewer shell → cached "
                          f"{pdf_dest.relative_to(ROOT)}", file=sys.stderr)
                else:
                    try:
                        body = _fetch(embedded)
                    except requests.RequestException as e:
                        print(f"[01-ch] {canton}: embedded PDF fetch failed — {e}",
                              file=sys.stderr)
                        results[canton] = {
                            "canton": canton, "status": "fetch-failed",
                            "url": embedded, "error": str(e),
                        }
                        n_fail += 1
                        continue
                    pdf_dest.write_bytes(body)
                    print(f"[01-ch] {canton}: viewer shell → saved "
                          f"{pdf_dest.relative_to(ROOT)} ({len(body):,} bytes)",
                          file=sys.stderr)
                dest, fmt, effective_url = pdf_dest, "pdf", embedded

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

    n_rulings_bad = fetch_roster_rulings()

    print(
        f"[done] 01-ch: ok={n_ok} failed={n_fail} no_url={n_unknown} "
        f"overridden={n_overridden} rulings_bad={n_rulings_bad} → {MANIFEST.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if n_fail == 0 and n_rulings_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
