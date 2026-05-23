"""Augment IT records with the MASAF national disciplinare di produzione.

Pipeline stage 02f (it).

Italy's stage 01/02 documenti unici cover 129 of 531 wines (24 %) —
the rest live in eAmbrosia without an EUR-Lex publication URL. The
MASAF ministry publishes the FULL consolidated disciplinare for every
DOP + IGT as PDFs bundled into 4 7-Zip archives (~100 MB total),
fetched by stage 00 into
[raw/it/masaf-disciplinari/bundles/](raw/it/masaf-disciplinari/bundles/).

This stage:
  1. enumerates eAmbrosia wines that are CURRENTLY STUBS (no documento
     unico extracted),
  2. matches each to one PDF inside the bundles (exact > substring >
     rapidfuzz ≥ 90),
  3. extracts the PDF on-demand into the per-slug cache at
     [raw/it/masaf-disciplinari/pdfs/](raw/it/masaf-disciplinari/pdfs/),
  4. carves the pdftotext output into articles 1..10 and parses
     grapes (Art. 2), geo area (Art. 3), terroir (Art. 9),
  5. writes a sidecar JSON under
     [raw/it/masaf-disciplinari-extracted/](raw/it/masaf-disciplinari-extracted/)
     that stage 04 merges into each stub at load time.

The on-disk stub records stay immutable — augmentation is in-memory
and propagates via a slug-keyed cache, mirroring the ES national-pliego
pattern in [scripts/es/02f_extract_national_pliegos.py](scripts/es/02f_extract_national_pliegos.py).

Per-record provenance carried in the sidecar:
  source.bundle        — bundle key ('dop-AD', 'dop-EN', 'dop-OZ', 'igp')
  source.archive_path  — filename inside the 7z (verbatim)
  source.sha256        — sha256 of the extracted PDF
  source.bytes         — PDF size
  source.fetched_at    — UTC timestamp of extraction
  match.how            — 'exact' / 'substring' / 'fuzzy:NN' / 'override'
  match.pdf_filename   — readable filename for the audit log

Usage:
  --slug <s>     process a single slug (raises on miss in strict mode)
  --all          sweep every stub record
  --refresh      re-extract the PDF even if cached on disk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import py7zr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)
from _lib.it.masaf import (  # noqa: E402
    PdfRecord, build_pdf_index, derive_geo_area, derive_summary,
    derive_terroir, extract_articles, match_wines_to_pdfs, parse_grapes_with,
)
from _lib.it.region import derive_regione  # noqa: E402
from _lib.it.province import load_comune_regione_map, resolve_gisco_lau  # noqa: E402

EAMBROSIA_INDEX = ROOT / "raw" / "it" / "eambrosia" / "index.json"
EXTRACTED_DIR = ROOT / "raw" / "it" / "disciplinari-extracted"
GISCO_DIR = ROOT / "raw" / "es" / "gisco"
BUNDLES_DIR = ROOT / "raw" / "it" / "masaf-disciplinari" / "bundles"
BUNDLES_MANIFEST = BUNDLES_DIR / "manifest.json"
PDF_CACHE = ROOT / "raw" / "it" / "masaf-disciplinari" / "pdfs"
OUT_DIR = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
OUT_MANIFEST = OUT_DIR / "_index.json"

OVERRIDES_PATH = BUNDLES_DIR.parent / "manual_overrides.json"

PARSER_VERSION = "it-masaf-disciplinare-v1"


def load_overrides() -> dict:
    """Curator-pinned PDF URLs for slugs that have no MASAF bundle
    entry (the 10 IGTs / newer DOPs that aren't in the 4 archives).
    Mirrors the ES / PT / FR override pattern. Schema:

      { "<slug>": {
          "pdf_url": "https://...",
          "source_org": "masaf|regione|consorzio|gazzetta",
          "verification_note": "<one-line provenance>"
      } }
    """
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        return json.loads(OVERRIDES_PATH.read_text())
    except (ValueError, OSError):
        return {}


def load_bundles_manifest() -> dict:
    if not BUNDLES_MANIFEST.exists():
        raise SystemExit(
            f"missing {BUNDLES_MANIFEST.relative_to(ROOT)} — "
            f"run scripts/it/00_fetch_data.py first"
        )
    return json.loads(BUNDLES_MANIFEST.read_text())


def enumerate_bundle_pdfs() -> tuple[list[PdfRecord], dict[str, str]]:
    """Walk each .7z archive listed in the manifest and return the
    derived PdfRecord index. Also returns a `{bundle_key: archive_filename}`
    map for cache-key derivation. Reading the archive's TOC is cheap
    (py7zr only reads the central directory)."""
    manifest = load_bundles_manifest()
    bundle_files: list[tuple[str, str]] = []
    bundle_archives: dict[str, str] = {}
    for key, spec in manifest["bundles"].items():
        archive = BUNDLES_DIR / spec["filename"]
        if not archive.exists():
            raise SystemExit(
                f"bundle archive missing: {archive.relative_to(ROOT)}"
            )
        bundle_archives[key] = spec["filename"]
        with py7zr.SevenZipFile(archive) as z:
            for n in z.getnames():
                if n.lower().endswith(".pdf"):
                    bundle_files.append((key, n))
    return build_pdf_index(bundle_files), bundle_archives


def load_wines() -> list[dict]:
    if not EAMBROSIA_INDEX.exists():
        raise SystemExit(
            f"missing {EAMBROSIA_INDEX.relative_to(ROOT)} — "
            f"run scripts/it/00_fetch_data.py first"
        )
    return json.loads(EAMBROSIA_INDEX.read_text())["wines"]


def load_extracted_status() -> dict[str, dict]:
    """{slug: extracted-record}, slug-keyed for stub detection. A record
    with `stub: true` is what 02f targets; non-stub records already have
    documento unico data and shouldn't be rewritten."""
    out: dict[str, dict] = {}
    if not EXTRACTED_DIR.exists():
        return out
    for p in sorted(EXTRACTED_DIR.glob("*.json")):
        if p.name == "_index.json":
            continue
        try:
            rec = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        slug = rec.get("slug")
        if slug:
            out[slug] = rec
    return out


def extract_pdf_from_bundle(bundle_key: str, archive_path: str,
                            dest: Path) -> bytes:
    """Pull one PDF out of a .7z bundle and write it to `dest`.
    py7zr's `extract(targets=…)` preserves the in-archive subdir; we
    extract to a sibling temp dir and copy to the slug-keyed cache
    path so callers don't see the bundle layout."""
    import shutil
    import tempfile
    manifest = load_bundles_manifest()
    archive = BUNDLES_DIR / manifest["bundles"][bundle_key]["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with py7zr.SevenZipFile(archive) as z:
            z.extract(path=tmp, targets=[archive_path])
        src = Path(tmp) / archive_path
        if not src.exists():
            raise RuntimeError(
                f"archive_path {archive_path!r} not present after "
                f"extract from {archive.name}"
            )
        shutil.copyfile(src, dest)
    return dest.read_bytes()


def pdf_to_text(pdf_path: Path) -> str:
    """Shell out to pdftotext -layout. Same dep the ES + PT pipelines
    already require (poppler from system); raises CalledProcessError on
    failure so the per-slug fallback in main() can surface the error."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def collapse_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def build_record(wine: dict, articles: dict[int, str], pdf_meta: dict,
                 match_info: dict, comune_map: dict) -> dict:
    """Build the sidecar JSON. The shape mirrors the doc-unico extracted
    record where it can (slug / name / kind / file_number / id_eambrosia
    / regione / grapes / styles / sections_present) so stage 04 can
    merge it into the stub with minimal branching."""
    set_pliego_context(wine["slug"])
    grapes = parse_grapes_with(match_variety, articles.get(2, ""), wine.get("name", ""))
    set_pliego_context(None)

    summary = derive_summary(articles.get(1, ""))
    geo_area = derive_geo_area(articles.get(3, ""))
    terroir = derive_terroir(articles.get(9, ""))

    # If the wine's name is already DOC/DOCG-prefixed in article 1, the
    # summary tends to be a self-referential opening sentence. Cap at
    # ~600 chars (handled in derive_summary).

    regione = derive_regione(
        {"file_number": wine.get("fileNumber") or ""},
        geo_area,
        wine.get("name", ""),
        comune_map=comune_map,
    )

    return {
        "country": "it",
        "source_lang": "it",
        "parser_template": PARSER_VERSION,
        "id_eambrosia": wine["giIdentifier"],
        "file_number": wine.get("fileNumber") or "",
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "regione": regione,
        "summary": summary,
        "grapes": grapes,
        "geo_area_brief": geo_area,
        "link_to_terroir": terroir,
        "articles_present": sorted(articles.keys()),
        # Subsection of articles useful to downstream consumers — we
        # keep articles 1 / 3 / 9 verbatim so 02d-style terroir
        # extraction can later run against them when stage 02 is silent.
        "article_bodies": {
            str(n): articles.get(n, "") for n in (1, 2, 3, 9) if articles.get(n)
        },
        "source": pdf_meta,
        "match": match_info,
    }


def process_slug(
    wine: dict,
    pdfs: list[PdfRecord],
    outcomes_by_slug: dict[str, "object"],
    overrides: dict,
    refresh: bool,
    strict: bool,
    extracted_status: dict[str, dict],
    comune_map: dict,
) -> dict:
    slug = wine["slug"]

    # Skip non-stubs — they already have docunico data.
    rec = extracted_status.get(slug)
    if rec and not rec.get("stub"):
        return {"slug": slug, "status": "skip", "reason": "not-a-stub"}

    pdf_cache_dir = PDF_CACHE
    pdf_dest = pdf_cache_dir / f"{slug}.pdf"

    override = overrides.get(slug)
    if override and override.get("pdf_url"):
        # Curator override: fetch the URL directly.
        import requests
        if pdf_dest.exists() and not refresh:
            body = pdf_dest.read_bytes()
        else:
            try:
                resp = requests.get(
                    override["pdf_url"],
                    headers={"User-Agent": "open-wine-map/0.0.1 (mailto:winemap@devloed.com)"},
                    timeout=120,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                body = resp.content
                pdf_dest.parent.mkdir(parents=True, exist_ok=True)
                pdf_dest.write_bytes(body)
            except Exception as e:  # noqa: BLE001
                if strict:
                    raise
                return {"slug": slug, "status": "fetch-failed", "reason": str(e)[:160]}
        pdf_meta = {
            "url": override["pdf_url"],
            "source_org": override.get("source_org", ""),
            "verification_note": override.get("verification_note", ""),
            "filename": pdf_dest.name,
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        match_info = {"how": "override", "pdf_filename": pdf_dest.name}
    else:
        outcome = outcomes_by_slug.get(slug)
        if outcome is None or outcome.pdf_index is None:
            if strict:
                raise SystemExit(
                    f"no MASAF bundle match for slug {slug!r}; add a curator "
                    f"override in {OVERRIDES_PATH.relative_to(ROOT)}"
                )
            return {"slug": slug, "status": "skip", "reason": "no-bundle-match"}
        pdf_rec: PdfRecord = pdfs[outcome.pdf_index]
        if pdf_dest.exists() and not refresh:
            body = pdf_dest.read_bytes()
        else:
            try:
                body = extract_pdf_from_bundle(
                    pdf_rec.bundle, pdf_rec.archive_path, pdf_dest
                )
            except Exception as e:  # noqa: BLE001
                if strict:
                    raise
                return {"slug": slug, "status": "extract-failed",
                        "reason": str(e)[:160]}
        pdf_meta = {
            "bundle_key": pdf_rec.bundle,
            "archive_path": pdf_rec.archive_path,
            "filename": pdf_dest.name,
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        match_info = {"how": outcome.how, "pdf_filename": pdf_rec.filename}

    try:
        text = pdf_to_text(pdf_dest)
    except subprocess.CalledProcessError as e:
        if strict:
            raise
        return {"slug": slug, "status": "pdftotext-failed",
                "reason": e.stderr[:160] if e.stderr else str(e)[:160]}

    articles = extract_articles(text)
    if not articles:
        if strict:
            raise SystemExit(
                f"no 'Articolo N' anchors detected in {pdf_dest} — "
                f"PDF may be image-only or use a non-standard template"
            )
        return {"slug": slug, "status": "no-articles", "reason": "no-anchors"}

    record = build_record(wine, articles, pdf_meta, match_info, comune_map)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return {
        "slug": slug,
        "status": "ok",
        "n_articles": len(articles),
        "n_grapes": len(record["grapes"]["details"]),
        "regione": record["regione"],
        "match_how": match_info["how"],
        "pdf_filename": match_info.get("pdf_filename") or pdf_dest.name,
    }


def write_index(records: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MANIFEST.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "parser_template": PARSER_VERSION,
                "n_sidecars": sum(1 for r in records if r.get("status") == "ok"),
                "by_status": _group_counts(records, "status"),
                "by_match_how": _group_counts(
                    [r for r in records if r.get("status") == "ok"], "match_how"
                ),
            },
            ensure_ascii=False, indent=2, sort_keys=True,
        )
    )


def _group_counts(records: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        k = r.get(key, "")
        if not k:
            continue
        out[k] = out.get(k, 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default=None,
                    help="process a single slug (strict mode)")
    ap.add_argument("--all", action="store_true",
                    help="sweep every stub record")
    ap.add_argument("--refresh", action="store_true",
                    help="re-extract the PDF from the bundle even if cached")
    args = ap.parse_args(argv)

    if not args.slug and not args.all:
        ap.error("pass --slug <s> or --all")

    pdfs, _archives = enumerate_bundle_pdfs()
    print(
        f"[bundles] indexed {len(pdfs)} PDFs across {len(_archives)} archives",
        file=sys.stderr,
    )

    wines = load_wines()
    outcomes = match_wines_to_pdfs(wines, pdfs)
    outcomes_by_slug = {o.wine_slug: o for o in outcomes}
    n_matched = sum(1 for o in outcomes if o.pdf_index is not None)
    print(
        f"[match] {n_matched}/{len(wines)} eAmbrosia wines matched to a bundle PDF",
        file=sys.stderr,
    )

    overrides = load_overrides()
    if overrides:
        print(f"[overrides] {len(overrides)} manual entr(ies) loaded",
              file=sys.stderr)

    extracted_status = load_extracted_status()
    n_stubs = sum(1 for r in extracted_status.values() if r.get("stub"))
    print(
        f"[stubs] {n_stubs} stub records in {EXTRACTED_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )

    gisco_lau = resolve_gisco_lau(GISCO_DIR)
    comune_map = load_comune_regione_map(str(gisco_lau)) if gisco_lau else {}
    if comune_map:
        print(f"[regione] GISCO commune index: {len(comune_map)} names",
              file=sys.stderr)
    else:
        print("[regione] warn: GISCO LAU not found — regione derivation "
              "falls back to province/file-number signals", file=sys.stderr)

    if args.slug:
        wine = next((w for w in wines if w["slug"] == args.slug), None)
        if wine is None:
            raise SystemExit(f"no eAmbrosia wine with slug {args.slug!r}")
        out = process_slug(wine, pdfs, outcomes_by_slug, overrides,
                           refresh=args.refresh, strict=True,
                           extracted_status=extracted_status,
                           comune_map=comune_map)
        if out.get("status") == "ok":
            print(f"# {wine['name']} ({wine['slug']})")
            print(f"  match    : {out['match_how']:14s} {out['pdf_filename']!r}")
            print(f"  articles : {out['n_articles']}")
            print(f"  grapes   : {out['n_grapes']}")
            print(f"  regione  : {out['regione'] or '(unresolved)'}")
            sidecar = json.loads((OUT_DIR / f"{wine['slug']}.json").read_text())
            print(f"\n  summary  : {sidecar['summary'][:240]}…"
                  if len(sidecar['summary']) > 240
                  else f"\n  summary  : {sidecar['summary']}")
            details = sidecar["grapes"]["details"][:12]
            print(f"\n  grapes ({len(sidecar['grapes']['details'])}):")
            for d in details:
                print(f"    - {d['slug']:30s} colour={d['colour']:5s}  «{d['name']}»")
            if len(sidecar["grapes"]["details"]) > len(details):
                print(f"    ... +{len(sidecar['grapes']['details']) - len(details)} more")
        else:
            print(f"# {wine['name']} ({wine['slug']})")
            for k, v in out.items():
                print(f"  {k}: {v}")
        return 0

    # Sweep mode.
    results: list[dict] = []
    for wine in wines:
        slug = wine["slug"]
        res = process_slug(wine, pdfs, outcomes_by_slug, overrides,
                           refresh=args.refresh, strict=False,
                           extracted_status=extracted_status,
                           comune_map=comune_map)
        results.append(res)
        if res["status"] == "ok":
            print(
                f"  ok       {res['match_how']:14s} grapes={res['n_grapes']:>2d}  "
                f"{slug}",
                file=sys.stderr,
            )
        elif res["status"] != "skip" or res.get("reason") not in (
            "not-a-stub", "no-bundle-match",
        ):
            print(
                f"  {res['status']:<16s} {slug:40s}  {res.get('reason', '')[:60]}",
                file=sys.stderr,
            )

    write_index(results)
    unknowns_path = ROOT / "raw" / "it" / "extraction-unknowns-masaf.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )

    by_status = _group_counts(results, "status")
    print("\n[done] sweep summary:", file=sys.stderr)
    for status, count in sorted(by_status.items()):
        print(f"   {status:<25s} {count}", file=sys.stderr)
    return 0 if by_status.get("extract-failed", 0) + by_status.get("pdftotext-failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
