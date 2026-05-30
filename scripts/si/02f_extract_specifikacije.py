"""Extract the Slovenian national specifikacija proizvoda for each SI
content-stub. Sibling of stage 02 — covers the 16 grandfathered SI
wines whose EU-OJ Enotni dokument was never published.

Pipeline stage 02f (si). DE / IT / ES analog: pulls the regulator's
canonical product specification from the national source and writes a
sidecar JSON that stage 04's `augment_si_records_with_specifikacija()`
merges into each in-memory stub record.

Reads:
  raw/si/specifikacije/<slug>.{doc,html}    (fetched by stage 01c)
  raw/si/specifikacije/manifest.json
  raw/si/oj-pages/manual_overrides.json     (slug → url mapping)
  raw/si/dokumenti-extracted/<slug>.json    (slug existence check)

Writes:
  raw/si/specifikacije-extracted/<slug>.json   (sidecar)
  raw/si/specifikacije-extracted/_index.json
  raw/si/specifikacije-extracted/manifest.json

Parser branches (two):
  - MKGP `.doc` files (11 wines) — antiword (via Docker `owm-antiword`
    image) → text → `_lib.si.specifikacija.parse_mkgp_doc`
  - Uradni list RS HTML pravilniki (5 wines, 2 distinct documents) →
    `_lib.si.specifikacija.parse_uradni_list_pravilnik`

The `.doc` conversion shells out to a Docker image built from
`scripts/si/Dockerfile.doc-converter` (debian:bookworm-slim + antiword).
Build once with:
  docker build -t owm-antiword:latest -f scripts/si/Dockerfile.doc-converter scripts/si/

Re-runnable per slug or sweep:
  .venv/bin/python scripts/si/02f_extract_specifikacije.py --slug teran
  .venv/bin/python scripts/si/02f_extract_specifikacije.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.si.specifikacija import (  # noqa: E402
    parse_mkgp_doc, parse_uradni_list_pravilnik,
)
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, set_pliego_context,
)

OVERRIDES_PATH = ROOT / "raw" / "si" / "oj-pages" / "manual_overrides.json"
SPECS_DIR = ROOT / "raw" / "si" / "specifikacije"
SPECS_MANIFEST = SPECS_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "si" / "specifikacije-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
UNKNOWNS = ROOT / "raw" / "si" / "extraction-unknowns-specifikacije.json"
DOCKER_IMAGE = "owm-antiword:latest"


def antiword_to_text(doc_path: Path) -> str:
    """Convert a Word 97-2003 .doc to UTF-8 text via the antiword Docker
    image. Uses `-w 0` (no line wrap) so paragraphs stay intact, and
    `-m UTF-8.txt` so Slovenian diacritics survive."""
    abs_dir = str(doc_path.parent.resolve())
    name = doc_path.name
    try:
        result = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{abs_dir}:/data:ro",
             DOCKER_IMAGE,
             "-w", "0", "-m", "UTF-8.txt",
             f"/data/{name}"],
            capture_output=True, timeout=60, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker not on PATH; install Docker Desktop or rebuild the antiword "
            f"image: docker build -t {DOCKER_IMAGE} -f scripts/si/Dockerfile.doc-converter scripts/si/"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"antiword timed out on {doc_path.name}") from exc
    if result.returncode != 0:
        # Antiword returns nonzero for some warnings — keep the output if
        # it has substantive content.
        stderr = result.stderr.decode("utf-8", errors="replace")
        if not result.stdout.strip():
            raise RuntimeError(
                f"antiword failed on {doc_path.name}: rc={result.returncode}\n{stderr[:400]}"
            )
    return result.stdout.decode("utf-8", errors="replace")


def _sidecar_for(slug: str, parsed: dict, source: dict) -> dict:
    return {
        "country": "si",
        "source_lang": "sl",
        "slug": slug,
        "summary": parsed.get("summary", ""),
        "grapes": parsed.get("grapes") or {},
        "geo_area_brief": parsed.get("geo_area_brief", ""),
        "link_to_terroir": parsed.get("link_to_terroir", ""),
        "section_roles": parsed.get("section_roles") or {},
        "section_titles": parsed.get("section_titles") or {},
        "styles": parsed.get("styles") or [],
        "n_sections": parsed.get("n_sections", 0),
        "parser_template": parsed.get("parser_template", ""),
        "matched_okoliši": parsed.get("matched_okoliši", []),
        "source": source,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", help="single slug")
    ap.add_argument("--all", action="store_true", help="process every slug with a cached spec")
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    args = ap.parse_args()

    if not args.slug and not args.all and not args.only:
        ap.error("specify --slug SLUG, --only SUBSTR, or --all")

    if not OVERRIDES_PATH.exists():
        print(f"error: {OVERRIDES_PATH} missing", file=sys.stderr)
        return 1
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    fetch_manifest: dict[str, dict] = {}
    if SPECS_MANIFEST.exists():
        try:
            fetch_manifest = json.loads(SPECS_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
        except (ValueError, OSError):
            fetch_manifest = {}

    targets: list[str] = []
    if args.slug:
        targets = [args.slug]
    elif args.only:
        needles = [s.lower() for s in args.only]
        targets = [s for s in overrides if not s.startswith("__")
                   and any(n in s.lower() for n in needles)]
    else:
        targets = [s for s in overrides if not s.startswith("__")
                   and (overrides[s].get("url") or "").startswith("http")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    if OUT_INDEX.exists():
        try:
            index = json.loads(OUT_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            index = {}

    n_ok = n_skipped = n_failed = 0
    for slug in tqdm(targets, desc="specifikacije-extract", leave=False):
        set_pliego_context(slug)
        cached = list(SPECS_DIR.glob(f"{slug}.*"))
        cached = [p for p in cached if p.suffix in {".doc", ".html", ".pdf"}]
        if not cached:
            n_skipped += 1
            continue
        spec_path = cached[0]

        fmt = spec_path.suffix.lstrip(".")
        source_meta = fetch_manifest.get(slug, {})
        source = {
            "url": source_meta.get("source_url") or overrides.get(slug, {}).get("url", ""),
            "final_url": source_meta.get("final_url", ""),
            "format": fmt,
            "filename": spec_path.name,
            "sha256": source_meta.get("sha256") or
                      hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "bytes": source_meta.get("bytes") or spec_path.stat().st_size,
            "fetched_at": source_meta.get("fetched_at", ""),
            "source_org": overrides.get(slug, {}).get("source_org", ""),
            "license": (
                "MKGP product specification (Slovenia) — public regulator material, "
                "reuse with attribution"
                if fmt == "doc"
                else "Uradni list RS — Slovenian official gazette, regulatory text is public"
            ),
        }

        try:
            if fmt == "doc":
                text = antiword_to_text(spec_path)
                parsed = parse_mkgp_doc(text, slug)
            elif fmt == "html":
                html = spec_path.read_text(encoding="utf-8")
                parsed = parse_uradni_list_pravilnik(html, slug)
                if parsed is None:
                    raise RuntimeError("no pravilnik parser matched the HTML")
            else:
                raise RuntimeError(f"unsupported format: {fmt}")
        except Exception as exc:  # noqa: BLE001 — surface to manifest
            print(f"[err] {slug}: {exc}", file=sys.stderr)
            n_failed += 1
            continue

        sidecar = _sidecar_for(slug, parsed, source)
        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        n_principal = len(parsed.get("grapes", {}).get("principal") or [])
        n_accessory = len(parsed.get("grapes", {}).get("accessory") or [])
        index[slug] = {
            "filename": out_path.name,
            "parser_template": parsed.get("parser_template", ""),
            "n_principal": n_principal,
            "n_accessory": n_accessory,
            "n_sections": parsed.get("n_sections", 0),
            "summary_chars": len(parsed.get("summary") or ""),
            "has_terroir": bool((parsed.get("link_to_terroir") or "").strip()),
        }
        n_ok += 1

    set_pliego_context(None)
    OUT_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    OUT_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_summary": (
            "MKGP product specifications (.doc): public regulator material, "
            "reuse with attribution. Uradni list RS pravilniki (.html): "
            "Slovenian official gazette, regulatory text is public per "
            "Slovenian copyright law (úradni dílo)."
        ),
        "counts": {
            "ok": n_ok,
            "skipped_no_spec": n_skipped,
            "failed": n_failed,
            "total_in_index": len(index),
        },
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    n_unknowns = flush_unknowns_queue(UNKNOWNS)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{UNKNOWNS.relative_to(ROOT)}",
            file=sys.stderr,
        )
    print(
        f"[done] ok={n_ok} skipped={n_skipped} failed={n_failed} "
        f"→ {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
