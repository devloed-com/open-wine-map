"""Extract the Greek national product specifications fetched by stage 01c
into per-wine sidecars under `raw/gr/national-specs-extracted/`.

Pipeline stage 02f (gr). Sibling of the ES MAPA / IT MASAF / DE BLE /
HR–SI specifikacije layers: it augments the 138 GR stub records (wines
with no fetchable EU-OJ ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ) by parsing the ΥΠΑΑΤ national
spec (`scripts/_lib/gr/specifikacija.py`). Stage 04's
`augment_gr_records_with_national_specs()` merges the sidecar into the
in-memory stub record at load time; the on-disk dokumenti-extracted JSON
stays immutable.

Re-runnable per slug or in sweep mode:
    .venv/bin/python scripts/gr/02f_extract_national_specs.py --slug samos
    .venv/bin/python scripts/gr/02f_extract_national_specs.py --all
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.gr.specifikacija import parse_spec  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue,
    set_pliego_context,
)

SPECS_DIR = ROOT / "raw" / "gr" / "national-specs"
MANIFEST_PATH = SPECS_DIR / "manifest.json"
OVERRIDES_PATH = SPECS_DIR / "manual_overrides.json"
OUT_DIR = ROOT / "raw" / "gr" / "national-specs-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
UNKNOWNS = ROOT / "raw" / "gr" / "extraction-unknowns-national.json"

_SPEC_EXTS = ("pdf", "doc", "docx")


EXTRACTED_DIR = ROOT / "raw" / "gr" / "dokumenti-extracted"


def _cache_file(slug: str) -> Path | None:
    for c in sorted(glob.glob(str(SPECS_DIR / f"{slug}.*"))):
        if c.rsplit(".", 1)[-1].lower() in _SPEC_EXTS:
            return Path(c)
    return None


def _appellation_name(slug: str) -> str:
    """The appellation's Greek name (excluded from grape matching)."""
    rec = EXTRACTED_DIR / f"{slug}.json"
    if rec.exists():
        try:
            return json.loads(rec.read_text(encoding="utf-8")).get("name", "") or ""
        except (ValueError, OSError):
            pass
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", help="single slug")
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--all", action="store_true", help="every slug with a cached spec")
    args = ap.parse_args()
    if not (args.slug or args.only or args.all):
        ap.error("specify --slug SLUG, --only SUBSTR, or --all")

    if not OVERRIDES_PATH.exists():
        print(f"error: {OVERRIDES_PATH} missing — run stage 01c first", file=sys.stderr)
        return 1
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}

    if args.slug:
        targets = [args.slug]
    elif args.only:
        needles = [s.lower() for s in args.only]
        targets = [s for s in overrides if any(n in s.lower() for n in needles)]
    else:
        targets = sorted(overrides)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    if OUT_INDEX.exists():
        try:
            index = json.loads(OUT_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            index = {}

    extracted = skipped = failed = 0
    for slug in targets:
        cache = _cache_file(slug)
        if cache is None:
            skipped += 1
            continue
        set_pliego_context(slug)
        try:
            parsed = parse_spec(cache, slug, name=_appellation_name(slug))
        except Exception as exc:  # noqa: BLE001 — keep the sweep going
            print(f"[err] {slug}: {exc}", file=sys.stderr)
            failed += 1
            continue

        m = manifest.get(slug, {})
        sidecar = {
            "country": "gr",
            "source_lang": "el",
            "slug": slug,
            "file_number": m.get("file_number") or overrides.get(slug, {}).get("file_number", ""),
            "summary": parsed["summary"],
            "grapes": parsed["grapes"],
            "styles": parsed["styles"],
            "geo_area_brief": parsed["geo_area_brief"],
            "link_to_terroir": parsed["link_to_terroir"],
            "section_roles": parsed["section_roles"],
            "section_titles": parsed["section_titles"],
            "n_sections": parsed["n_sections"],
            "n_grapes": parsed["n_grapes"],
            "parser_template": parsed["parser_template"],
            "source": {
                "filename": cache.name,
                "format": cache.suffix.lower().lstrip("."),
                "source_url": m.get("source_url") or overrides.get(slug, {}).get("url", ""),
                "source_org": m.get("source_org", "ypaat"),
                "sha256": m.get("sha256", ""),
                "fetched_at": m.get("fetched_at", ""),
            },
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "slug": slug,
            "file_number": sidecar["file_number"],
            "n_grapes": sidecar["n_grapes"],
            "n_terroir_chars": len(sidecar["link_to_terroir"]),
            "parser_template": sidecar["parser_template"],
        }
        extracted += 1

    set_pliego_context(None)
    OUT_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    n_unknowns = flush_unknowns_queue(UNKNOWNS)
    print(f"[done] extracted={extracted} skipped={skipped} failed={failed} "
          f"unknown-candidates={n_unknowns} → {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
