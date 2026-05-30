"""Extract the HU national termékleírás PDFs into sidecar records
(stage 02f).

Reads the PDFs stage 01c fetched into `raw/hu/national-specs/`, runs
`pdftotext -layout`, parses with `_lib/hu/termekleiras.py`, and writes
one sidecar JSON per wine to
`raw/hu/national-specs-extracted/<slug>.json` with full provenance.
Stage 04's `augment_hu_records_with_national_specs()` merges the sidecar
into the in-memory stub record at load time (the on-disk
dokumentumok-extracted stub stays immutable).

Mirrors `scripts/ro/02f_extract_national_specs.py`.

Re-runnable per slug or in sweep mode:
    python scripts/hu/02f_extract_national_specs.py --slug tokaj
    python scripts/hu/02f_extract_national_specs.py --all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, set_pliego_context,
)
from _lib.hu.dulo import parse_dulok  # noqa: E402
from _lib.hu.termekleiras import parse_termekleiras  # noqa: E402

SPECS_DIR = ROOT / "raw" / "hu" / "national-specs"
MANIFEST_PATH = SPECS_DIR / "manifest.json"
OVERRIDES_PATH = SPECS_DIR / "manual_overrides.json"
OUT_DIR = ROOT / "raw" / "hu" / "national-specs-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
UNKNOWNS = ROOT / "raw" / "hu" / "extraction-unknowns-national.json"


def pdf_to_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout


def _slugs_to_process(args, manifest: dict) -> list[str]:
    available = [
        s for s, m in manifest.items()
        if isinstance(m, dict) and m.get("status") in ("ok", "cached")
    ]
    if args.slug:
        return [args.slug]
    if args.only:
        return [s for s in available if any(sub in s for sub in args.only)]
    return available


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="single slug")
    ap.add_argument("--only", action="append", default=[],
                    help="slug substring (repeatable)")
    ap.add_argument("--all", action="store_true",
                    help="every slug with a cached termékleírás")
    args = ap.parse_args()
    if not (args.slug or args.only or args.all):
        ap.error("specify --slug SLUG, --only SUBSTR, or --all")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("by_slug", {})
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    index: dict[str, dict] = {}
    if OUT_INDEX.exists():
        index = json.loads(OUT_INDEX.read_text(encoding="utf-8"))

    n_ok = n_grapes = n_terroir = 0
    for slug in _slugs_to_process(args, manifest):
        m = manifest.get(slug, {})
        ov = overrides.get(slug, {})
        cache = SPECS_DIR / f"{slug}.pdf"
        if not cache.exists():
            print(f"  [skip] {slug}: no cached termékleírás", file=sys.stderr)
            continue
        text = pdf_to_text(cache)

        set_pliego_context(slug)
        parsed = parse_termekleiras(text, slug)
        dulok = parse_dulok(text)

        sidecar = {
            "country": "hu",
            "source_lang": "hu",
            "slug": slug,
            "file_number": m.get("file_number") or ov.get("file_number", ""),
            "summary": parsed["summary"],
            "grapes": parsed["grapes"],
            "styles": parsed["styles"],
            "geo_area_brief": parsed["geo_area_brief"],
            "geo_communes": parsed["geo_communes"],
            "dulok": dulok,
            "n_dulok": len(dulok),
            "link_to_terroir": parsed["link_to_terroir"],
            "section_roles": parsed["section_roles"],
            "section_titles": parsed["section_titles"],
            "n_sections": parsed["n_sections"],
            "n_grapes": parsed["n_grapes"],
            "parser_template": parsed["parser_template"],
            "source": {
                "filename": cache.name,
                "format": "pdf",
                "source_url": m.get("source_url") or ov.get("url", ""),
                "source_org": m.get("source_org", "agrarminiszterium"),
                "sha256": m.get("sha256", ""),
                "fetched_at": m.get("fetched_at", ""),
                "license": (
                    "© Agrárminisztérium / Hegyközségi Tanács — Hungarian "
                    "official wine product specification (termékleírás); "
                    "public official act (Szjt. §1(4))."
                ),
            },
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "file_number": sidecar["file_number"],
            "n_grapes": sidecar["n_grapes"],
            "n_communes": len(sidecar["geo_communes"]),
            "n_dulok": sidecar["n_dulok"],
            "has_terroir": bool(sidecar["link_to_terroir"]),
            "parser_template": sidecar["parser_template"],
        }
        n_ok += 1
        if sidecar["n_grapes"]:
            n_grapes += 1
        if sidecar["link_to_terroir"]:
            n_terroir += 1
        print(f"  [ok] {slug}: {sidecar['n_grapes']} grapes, "
              f"{len(sidecar['geo_communes'])} communes, "
              f"{sidecar['n_dulok']} dűlők, "
              f"terroir={'y' if sidecar['link_to_terroir'] else 'n'}",
              file=sys.stderr)

    OUT_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    flush_unknowns_queue(UNKNOWNS)
    print(f"[done] extracted={n_ok} with_grapes={n_grapes} "
          f"with_terroir={n_terroir} → {OUT_DIR}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
