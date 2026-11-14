"""Fetch the BML Produktspezifikationen — Austria's national specifications.

Pipeline stage 01c (at). The EU Einziges Dokument of an Austrian wine names
only the main varieties; the specification the Bundesministerium für Land-
und Forstwirtschaft (BML) files under Art. 94 Reg. (EU) 1308/2013 lists the
whole authorised roster (see scripts/_lib/at/produktspezifikation.py). Every
one is linked from one BML page, "Weinherkunft", as
`/dam/jcr:<uuid>/<Name> Produktspezifikation.pdf` (the 2025 template
`Produktspezifikation_<Name>.pdf`); the jcr uuid is opaque and may rotate,
so the page is read on every run and the URL is never pinned.

  page link  →  display name (the filename without "Produktspezifikation")
             →  slug (the AT stage-00 slugify)  →  raw/at/produktspezifikationen/<slug>.pdf

A slug the page lists twice (Eisenberg: the Blaufränkisch-only
specification and the 2025 one with Welschriesling) is settled by the
checked-in scripts/_lib/at/produktspezifikation_pins.json; without a pin
the slug is skipped and reported, never guessed. A file the page lists for
a name the eAmbrosia index does not carry is reported as unmatched. The
curator path raw/at/produktspezifikationen/manual_overrides.json (slug →
{url, note}) replaces or adds a URL when the page stops listing one.

A cached PDF is kept while the page still links the same URL; a rotated
URL is re-fetched and a changed sha256 is logged (the regulator published
a new edition). `--refresh` re-fetches everything.

Reads:
  raw/at/eambrosia/index.json                      the AT wine slugs
  scripts/_lib/at/produktspezifikation_pins.json   duplicate-file pins
  raw/at/produktspezifikationen/manual_overrides.json  (optional)
Writes:
  raw/at/produktspezifikationen/<slug>.pdf
  raw/at/produktspezifikationen/weinherkunft.html  the page as fetched
  raw/at/produktspezifikationen/manifest.json      url, sha256, bytes, fetched_at per slug
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.at.produktspezifikation import LICENSE, SOURCE_ORG, slug_for_display  # noqa: E402

BML_HOST = "https://www.bmluk.gv.at"
BML_PAGE = (
    f"{BML_HOST}/themen/landwirtschaft/landwirtschaft-in-oesterreich/"
    "pflanzliche-produktion/wein/Weinherkunft.html"
)
OUT_DIR = ROOT / "raw" / "at" / "produktspezifikationen"
MANIFEST = OUT_DIR / "manifest.json"
PAGE_CACHE = OUT_DIR / "weinherkunft.html"
OVERRIDES = OUT_DIR / "manual_overrides.json"
PINS = ROOT / "scripts" / "_lib" / "at" / "produktspezifikation_pins.json"
EAMBROSIA_INDEX = ROOT / "raw" / "at" / "eambrosia" / "index.json"
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
_LINK_RE = re.compile(r'href="(/dam/jcr:[^"]*Produktspezifikation[^"]*\.pdf)"', re.I)


def display_from_filename(filename: str) -> str:
    """"Vulkanland Steiermark_Produktspezifikation.pdf" → "Vulkanland Steiermark",
    "Produktspezifikation_Kamptal.pdf" → "Kamptal"."""
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    stem = re.sub(r"Produktspezifikation", " ", stem, flags=re.I)
    return re.sub(r"[_\s]+", " ", stem).strip()


def page_links(html: str) -> list[dict]:
    """Every Produktspezifikation PDF the page links, with its display name
    and slug, in page order, deduplicated by URL."""
    out: list[dict] = []
    seen: set[str] = set()
    for path in _LINK_RE.findall(html):
        if path in seen:
            continue
        seen.add(path)
        filename = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        display = display_from_filename(filename)
        out.append({"url": BML_HOST + path, "filename": filename, "display": display,
                    "slug": slug_for_display(display)})
    return out


def choose(candidates: list[dict], pin: dict | None) -> tuple[dict | None, str]:
    """One file per slug: the only candidate, or the pinned filename among
    several; (None, reason) when several candidates have no pin or the pin
    names a file the page no longer lists."""
    if len(candidates) == 1 and not pin:
        return candidates[0], "single"
    if pin:
        for c in candidates:
            if c["filename"] == pin.get("filename"):
                return c, "pinned"
        return None, f"pin names {pin.get('filename')!r}, page lists " + ", ".join(
            repr(c["filename"]) for c in candidates
        )
    return None, "ambiguous: " + ", ".join(repr(c["filename"]) for c in candidates)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def fetch_pdf(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    if r.content[:4] != b"%PDF":
        raise RuntimeError(f"not a PDF ({len(r.content)} bytes) at {url}")
    return r.content


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch every PDF")
    ap.add_argument("--dry-run", action="store_true", help="read the page, write nothing")
    args = ap.parse_args()

    index = _load_json(EAMBROSIA_INDEX, {})
    slugs = {w["slug"]: w.get("name") for w in index.get("wines") or []}
    if not slugs:
        print(f"error: {EAMBROSIA_INDEX} missing — run scripts/at/00_fetch_data.py", file=sys.stderr)
        return 1
    pins = {k: v for k, v in _load_json(PINS, {}).items() if not k.startswith("_")}
    overrides = _load_json(OVERRIDES, {})
    previous = _load_json(MANIFEST, {}).get("by_slug", {})

    try:
        r = requests.get(BML_PAGE, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        html = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"[at-spec] BML page unreachable ({exc}); manifest unchanged "
              f"({len(previous)} entries)", file=sys.stderr)
        return 1 if not previous else 0
    links = page_links(html)
    by_slug: dict[str, list[dict]] = {}
    unmatched_files: list[str] = []
    for link in links:
        if link["slug"] in slugs:
            by_slug.setdefault(link["slug"], []).append(link)
        else:
            unmatched_files.append(link["filename"])
    for slug, ov in overrides.items():
        if slug in slugs and ov.get("url"):
            fn = urllib.parse.unquote(ov["url"].rsplit("/", 1)[-1])
            by_slug[slug] = [{"url": ov["url"], "filename": fn, "display": slugs[slug],
                              "slug": slug, "override": True, "note": ov.get("note", "")}]

    print(f"[at-spec] page lists {len(links)} PDFs for {len(by_slug)} of {len(slugs)} AT wines; "
          f"{len(unmatched_files)} files match no slug", file=sys.stderr)
    if args.dry_run:
        for slug in sorted(by_slug):
            chosen, how = choose(by_slug[slug], pins.get(slug))
            print(f"  {slug:24} {how:10} {chosen['filename'] if chosen else '-'}", file=sys.stderr)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGE_CACHE.write_text(html, encoding="utf-8")
    manifest: dict[str, dict] = {}
    ambiguous: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for slug in sorted(by_slug):
        chosen, how = choose(by_slug[slug], pins.get(slug))
        if chosen is None:
            ambiguous[slug] = how
            print(f"[at-spec] {slug}: {how} — skipped (pin it in {PINS.relative_to(ROOT)})",
                  file=sys.stderr)
            continue
        dest = OUT_DIR / f"{slug}.pdf"
        prev = previous.get(slug) or {}
        cached = dest.exists() and prev.get("url") == chosen["url"] and not args.refresh
        if cached:
            body = dest.read_bytes()
            fetched_at = prev.get("fetched_at") or now
        else:
            print(f"[at-spec] fetch {slug} ← {chosen['filename']}", file=sys.stderr)
            try:
                body = fetch_pdf(chosen["url"])
            except Exception as exc:  # noqa: BLE001
                print(f"[at-spec] {slug}: fetch failed ({exc})", file=sys.stderr)
                if slug in previous and dest.exists():
                    manifest[slug] = previous[slug]
                continue
            sha = hashlib.sha256(body).hexdigest()
            if prev.get("sha256") and prev["sha256"] != sha:
                print(f"[at-spec] {slug}: NEW EDITION (sha256 changed since {prev.get('fetched_at')})",
                      file=sys.stderr)
            dest.write_bytes(body)
            fetched_at = now
        manifest[slug] = {
            "display": chosen["display"],
            "filename": chosen["filename"],
            "url": chosen["url"],
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "fetched_at": fetched_at,
            "cached": cached,
            "chosen_by": how,
            "alternates": sorted(c["filename"] for c in by_slug[slug] if c is not chosen),
            **({"override_note": chosen.get("note", "")} if chosen.get("override") else {}),
        }
    MANIFEST.write_text(json.dumps({
        "generated_at": now,
        "source_page": BML_PAGE,
        "source_page_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "source_org": SOURCE_ORG,
        "license": LICENSE,
        "n_pdfs": len(manifest),
        "by_slug": manifest,
        "unmatched_files": sorted(unmatched_files),
        "ambiguous": ambiguous,
        "missing": sorted(s for s in slugs if s not in manifest),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    missing = sorted(s for s in slugs if s not in manifest)
    print(f"[at-spec] {len(manifest)} PDFs → {OUT_DIR.relative_to(ROOT)}; "
          f"missing: {', '.join(missing) or 'none'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
