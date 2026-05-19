"""Fetch + parse the *national* pliego de condiciones (PDF, any Spanish
regional gazette template) and emit a sidecar JSON augmenting the doc-
único extraction with the full variety list (principal + accessory).

Pipeline stage 02f (es). One generic parser handles JCCM (Castilla-La
Mancha), INCAVI (Catalonia), AGACAL (Galicia), ITACyL (Castilla y León),
Aragón, Navarra, GVA (Valencia), Canarias, Andalucía, Euskadi, Madrid,
Extremadura, and MAPA — the EU "Real Decreto" pliego section structure
(`6. Variedades de uvas de vinificación`, etc.) is standardised enough
that template-specific regexes aren't needed. See
[scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py)
for the recognised heading variants.

Inputs:
  raw/es/pliegos-extracted/<slug>.json       (doc-único extraction)
  https://<regulator>/.../<pliego>.pdf       (national pliego, fetched once,
                                              URL read from section 9 of the
                                              doc-único record)

Outputs:
  raw/es/national-pliegos/<slug>.pdf         (cached PDF)
  raw/es/national-pliegos-extracted/<slug>.json
      {
        "country": "es",
        "slug": ...,
        "name": ...,
        "parser_template": "es-national-pliego-v1",
        "source": {url, sha256, fetched_at, bytes, filename},
        "varieties": [...],                  # full detail list from §6
        "delta_vs_oj": {
            "oj_slugs": [...],               # what doc-único already had
            "new_slugs": [...],              # additions the pliego brings
        },
        "section_text": "<raw §6 text, for audit>"
      }

Usage:
  --slug <s>    process a single record
  --all         sweep every record that has a pliego PDF URL in section 9
  --refresh     re-fetch the PDF even if cached

Re-runnable: cached PDFs are kept unless `--refresh` is passed. The
output JSON is rewritten every run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.es.national_pliego import parse_variety_section, pdf_to_text  # noqa: E402
from _lib.grape_entity import flush_unknowns_queue, set_pliego_context  # noqa: E402

PLIEGOS_DIR = ROOT / "raw" / "es" / "pliegos-extracted"
PDF_CACHE = ROOT / "raw" / "es" / "national-pliegos"
OUT_DIR = ROOT / "raw" / "es" / "national-pliegos-extracted"

# Optional human-curated overrides: when the doc-único's section-9 URL is
# dead (404, GVA backend timeout, BOE-modification-not-pliego, etc.), the
# curator pins a working replacement URL here. Slug-keyed entries shape:
#   { "<slug>": {
#       "pliego_url": "https://...",
#       "source_org": "mapa|consejo-regulador|boe|...",
#       "verification_note": "<one-line provenance>"
#   } }
# Missing file is fine — overrides are optional. Mirrors the FR pattern at
# raw/inao/cahiers/manual_overrides.json. See CLAUDE.md for the workflow.
OVERRIDES_PATH = PDF_CACHE / "manual_overrides.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)

# Any PDF URL inside the EU-OJ single-document's additional-conditions
# section (section 9 / section_roles["additional_conditions"]). Each ES
# wine GI uses section 9 to link its national pliego de condiciones.
PLIEGO_PDF_RE = re.compile(
    r"https?://[^\s)\]<>\"'»]+?\.pdf",
    re.IGNORECASE,
)


def find_pliego_url(record: dict) -> str | None:
    """Scan the record's section 9 / additional-conditions text for the
    first national-pliego PDF URL. Returns the URL or None."""
    candidates = []
    sections = record.get("sections") or {}
    for key in ("9", "additional_conditions"):
        if key in sections and sections[key]:
            candidates.append(sections[key])
    roles = record.get("section_roles") or {}
    if roles.get("additional_conditions"):
        candidates.append(roles["additional_conditions"])
    for text in candidates:
        m = PLIEGO_PDF_RE.search(text)
        if m:
            return m.group(0)
    return None


def load_overrides() -> dict:
    return json.loads(OVERRIDES_PATH.read_text()) if OVERRIDES_PATH.exists() else {}


def resolve_pliego_url(slug: str, record: dict, overrides: dict) -> tuple[str | None, str]:
    """Return (url, provenance) where provenance is 'override' or 'section-9'.
    Override takes precedence over the doc-único section-9 URL."""
    entry = overrides.get(slug)
    if entry and entry.get("pliego_url"):
        return entry["pliego_url"], "override"
    url = find_pliego_url(record)
    return (url, "section-9") if url else (None, "")


def fetch_pdf(url: str, dest: Path, refresh: bool) -> dict:
    """Download `url` to `dest` unless `dest` exists and `refresh=False`.
    Returns metadata: {sha256, bytes, fetched_at, from_cache}."""
    if dest.exists() and not refresh:
        body = dest.read_bytes()
        return {
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "fetched_at": "",
            "from_cache": True,
        }
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    body = resp.content
    dest.write_bytes(body)
    return {
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "from_cache": False,
    }


def existing_oj_slugs(record: dict) -> list[str]:
    g = record.get("grapes") or {}
    return sorted(set(g.get("principal", [])) | set(g.get("accessory", [])))


PARSER_VERSION = "es-national-pliego-v1"


def process(slug: str, refresh: bool, strict: bool = True, overrides: dict | None = None) -> dict:
    """Fetch, parse, and write the sidecar JSON for `slug`. When
    `strict=False`, missing URL / unparseable PDF return a stub-shaped
    result (`{status: ..., reason: ...}`) instead of raising, so a batch
    sweep can carry on past per-record errors."""
    if overrides is None:
        overrides = load_overrides()
    rec_path = PLIEGOS_DIR / f"{slug}.json"
    if not rec_path.exists():
        if strict:
            raise SystemExit(f"no extracted record for slug: {slug}")
        return {"slug": slug, "status": "skip", "reason": "no-extracted-record"}
    record = json.loads(rec_path.read_text())

    url, url_source = resolve_pliego_url(slug, record, overrides)
    if not url:
        if strict:
            raise SystemExit(
                f"no national-pliego PDF URL found in section 9 / "
                f"additional_conditions or overrides for {slug}"
            )
        return {"slug": slug, "status": "skip", "reason": "no-pliego-url"}

    pdf_dest = PDF_CACHE / f"{slug}.pdf"
    # Override-driven URL change invalidates the slug-keyed PDF cache. The
    # sidecar's source.url tells us what the cached PDF was fetched from;
    # if it disagrees with the override (or no sidecar exists at all, so
    # the cache vintage is unknown), force a refresh.
    sidecar_path = OUT_DIR / f"{slug}.json"
    if url_source == "override" and not refresh:
        cached_url = None
        if sidecar_path.exists():
            cached_url = (json.loads(sidecar_path.read_text()).get("source") or {}).get("url")
        if cached_url != url:
            refresh = True
    try:
        meta = fetch_pdf(url, pdf_dest, refresh=refresh)
    except Exception as e:
        if strict:
            raise
        return {"slug": slug, "status": "fetch-failed", "reason": str(e)[:200], "url": url}

    try:
        text = pdf_to_text(pdf_dest)
    except Exception as e:
        if strict:
            raise
        return {"slug": slug, "status": "pdftotext-failed", "reason": str(e)[:200]}

    set_pliego_context(slug)
    parsed = parse_variety_section(text)
    set_pliego_context(None)
    if not parsed["found"]:
        if strict:
            raise SystemExit(
                f"could not locate variety section (apartado 6) in {pdf_dest}."
            )
        return {"slug": slug, "status": "section-not-found", "reason": "no §6 header matched", "url": url}

    oj_slugs = existing_oj_slugs(record)
    nat_slugs = [d["slug"] for d in parsed["details"]]
    new_slugs = [s for s in nat_slugs if s not in oj_slugs]

    out = {
        "country": "es",
        "slug": slug,
        "name": record.get("name", ""),
        "parser_template": PARSER_VERSION,
        "source": {
            "url": url,
            "filename": pdf_dest.name,
            "sha256": meta["sha256"],
            "bytes": meta["bytes"],
            "fetched_at": meta["fetched_at"],
        },
        "varieties": parsed["details"],
        "delta_vs_oj": {
            "oj_slugs": oj_slugs,
            "new_slugs": new_slugs,
        },
        "section_text": parsed["section_text"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slug}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    out["status"] = "ok"
    return out


def _list_candidate_slugs(overrides: dict | None = None) -> list[str]:
    """Return slugs whose doc-único record has at least one .pdf URL in
    section 9 OR a curator override URL — these are the orchestrator's
    candidate set."""
    if overrides is None:
        overrides = load_overrides()
    candidates: list[str] = []
    for p in sorted(PLIEGOS_DIR.glob("*.json")):
        if p.name == "_index.json":
            continue
        rec = json.loads(p.read_text())
        if rec.get("stub") or rec.get("is_sub_denomination"):
            continue
        if find_pliego_url(rec) or (overrides.get(p.stem) or {}).get("pliego_url"):
            candidates.append(p.stem)
    return candidates


def main(argv: list[str] | None = None) -> int:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument(
        "--slug",
        default=None,
        help="single slug to process. Mutually exclusive with --all.",
    )
    arg_parser.add_argument(
        "--all",
        action="store_true",
        help="process every record that has a pliego PDF URL.",
    )
    arg_parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch the PDF even if cached",
    )
    args = arg_parser.parse_args(argv)

    overrides = load_overrides()
    if overrides:
        print(f"[overrides] {len(overrides)} manual entr(ies) loaded", file=sys.stderr)

    if args.all:
        slugs = _list_candidate_slugs(overrides)
        print(f"# Sweeping {len(slugs)} candidate records\n", file=sys.stderr)
        ok = skip = err = 0
        per_status: dict[str, int] = {}
        for slug in slugs:
            out = process(slug, refresh=args.refresh, strict=False, overrides=overrides)
            status = out.get("status", "ok")
            per_status[status] = per_status.get(status, 0) + 1
            if status == "ok":
                n_total = len(out["varieties"])
                n_new = len(out["delta_vs_oj"]["new_slugs"])
                print(f"  ok      total={n_total:>3d}  new={n_new:>3d}  {slug}")
                ok += 1
            else:
                reason = out.get("reason", "")[:70]
                print(f"  {status:<22s} {slug:30s}  {reason}")
                if status == "skip":
                    skip += 1
                else:
                    err += 1
        print(f"\n# Summary: ok={ok}  skip={skip}  err={err}", file=sys.stderr)
        for status, count in sorted(per_status.items()):
            print(f"   {status:<25s} {count}", file=sys.stderr)
        unknowns_path = ROOT / "raw" / "es" / "extraction-unknowns-national.json"
        n_unknowns = flush_unknowns_queue(unknowns_path)
        if n_unknowns:
            print(
                f"[entity] {n_unknowns} unknown variety candidates → "
                f"review at {unknowns_path.relative_to(ROOT)}",
                file=sys.stderr,
            )
        return 0 if err == 0 else 1

    slug = args.slug or "mentrida"
    out = process(slug, refresh=args.refresh, overrides=overrides)
    src = out["source"]
    delta = out["delta_vs_oj"]
    print(f"# {out['name']}  ({out['slug']})")
    print(f"  PDF      : {src['url']}")
    print(f"  cached   : raw/es/national-pliegos/{src['filename']} "
          f"({src['bytes']:,} bytes, sha256={src['sha256'][:12]}…)")
    print(f"  template : {out['parser_template']}")
    print()
    print(f"  doc-único grapes ({len(delta['oj_slugs'])}):")
    for s in delta["oj_slugs"]:
        print(f"    - {s}")
    print()
    print(f"  pliego §6 varieties ({len(out['varieties'])}):")
    for v in out["varieties"]:
        new = "  NEW" if v["slug"] in delta["new_slugs"] else ""
        print(f"    - {v['slug']:30s}  colour={v['colour']:5s}  «{v['name']}»{new}")
    print()
    print(f"  delta: {len(delta['new_slugs'])} new slugs would be added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
