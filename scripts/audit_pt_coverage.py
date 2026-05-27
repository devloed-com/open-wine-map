"""Audit PT pipeline coverage end-to-end.

Reports against the current state of:
  - eAmbrosia index (raw/pt/eambrosia/index.json)
  - IVV cadernos manifest (raw/pt/ivv/cadernos/manifest.json)
  - Extracted records (raw/pt/cadernos-extracted/*.json)
  - Translation cache for summaries (raw/translations/summaries/<lang>/)
  - Terroir-fact cache (raw/terroir-facts/<slug>.json with country=pt)
  - Wiki index entries (wiki/_index.json with country=pt)

Sister of `scripts/audit_es_coverage.py`. Run after rerunning the
pipeline to see what's covered, what's stubbed, and what's queued for
curator follow-up.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EAMBROSIA_INDEX = ROOT / "raw" / "pt" / "eambrosia" / "index.json"
CADERNOS_MANIFEST = ROOT / "raw" / "pt" / "ivv" / "cadernos" / "manifest.json"
EXTRACTED_DIR = ROOT / "raw" / "pt" / "cadernos-extracted"
SUMMARIES_DIR = ROOT / "raw" / "translations" / "summaries"
TERROIR_FACTS_DIR = ROOT / "raw" / "terroir-facts"
WIKI_INDEX = ROOT / "wiki" / "_index.json"


def _bullet(label: str, value: object) -> None:
    print(f"  {label:35} {value}")


def main() -> int:
    if not EAMBROSIA_INDEX.exists():
        print(
            f"error: {EAMBROSIA_INDEX} missing — run scripts/pt/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1

    print("=== PT coverage audit ===\n")

    # 1. eAmbrosia
    ea = json.loads(EAMBROSIA_INDEX.read_text(encoding="utf-8"))
    wines = ea.get("wines", [])
    by_kind = Counter(w["kind"] for w in wines)
    print("eAmbrosia (raw/pt/eambrosia/index.json):")
    _bullet("total wines", len(wines))
    for kind, n in sorted(by_kind.items()):
        _bullet(f"  {kind}", n)

    # 2. IVV cadernos
    print("\nIVV cadernos (raw/pt/ivv/cadernos/manifest.json):")
    if CADERNOS_MANIFEST.exists():
        m = json.loads(CADERNOS_MANIFEST.read_text(encoding="utf-8"))
        counts = m.get("counts", {})
        for k in ("ok", "cached", "override", "no_caderno", "fetch_error_or_not_pdf"):
            _bullet(k, counts.get(k, 0))
    else:
        _bullet("(manifest missing)", "run scripts/pt/01_fetch_cadernos.py")

    # 3. Extraction
    print("\nExtraction (raw/pt/cadernos-extracted/*.json):")
    if not EXTRACTED_DIR.exists():
        _bullet("(dir missing)", "run scripts/pt/02_extract_cadernos.py")
    else:
        files = sorted(
            p for p in EXTRACTED_DIR.glob("*.json") if not p.name.startswith("_")
        )
        n_parents = n_subregioes = n_stubs = 0
        per_pattern: Counter[str] = Counter()
        for f in files:
            rec = json.loads(f.read_text(encoding="utf-8"))
            if rec.get("stub"):
                n_stubs += 1
            elif rec.get("is_sub_denomination"):
                n_subregioes += 1
                per_pattern[rec.get("source_pattern", "")] += 1
            else:
                n_parents += 1
        _bullet("total records", len(files))
        _bullet("parents", n_parents)
        _bullet("sub-regiões", n_subregioes)
        _bullet("stubs", n_stubs)
        if per_pattern:
            for pat, n in sorted(per_pattern.items()):
                _bullet(f"sub-pattern {pat or '(none)'}", n)

    # 4. Translation cache (summaries)
    print("\nTranslation cache (raw/translations/summaries/<lang>/<slug>.json):")
    if not SUMMARIES_DIR.exists():
        _bullet("(dir missing)", "run scripts/02c_translate_summaries.py")
    else:
        for lang_dir in sorted(SUMMARIES_DIR.iterdir()):
            if not lang_dir.is_dir():
                continue
            n = sum(
                1
                for p in lang_dir.glob("*.json")
                if (json.loads(p.read_text(encoding="utf-8")).get("country") == "pt")
            )
            _bullet(f"{lang_dir.name}", n)

    # 5. Terroir facts cache
    print("\nTerroir-fact cache (raw/terroir-facts/*.json with country=pt):")
    if TERROIR_FACTS_DIR.exists():
        n_pt = 0
        for p in TERROIR_FACTS_DIR.glob("*.json"):
            if p.stem in ("manifest", "manifest-es"):
                continue
            try:
                if json.loads(p.read_text(encoding="utf-8")).get("country") == "pt":
                    n_pt += 1
            except (ValueError, OSError):
                continue
        _bullet("PT records with facts", n_pt)
        if n_pt == 0:
            _bullet(
                "(empty — expected for v1)",
                "PT 02d sibling script is a follow-up; UI falls back to summary",
            )
    else:
        _bullet("(dir missing)", "no terroir facts at all yet")

    # 6. Wiki index
    print("\nWiki index (wiki/_index.json):")
    if WIKI_INDEX.exists():
        idx = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        n_pt = sum(1 for v in idx.values() if v.get("country") == "pt")
        n_pt_stub = sum(
            1 for v in idx.values()
            if v.get("country") == "pt" and v.get("stub")
        )
        n_pt_sub = sum(
            1 for v in idx.values()
            if v.get("country") == "pt" and v.get("is_sub_denomination")
        )
        _bullet("PT entries", n_pt)
        _bullet("  of which stubs", n_pt_stub)
        _bullet("  of which sub-regiões", n_pt_sub)
        # Region distribution
        regions: Counter[str] = Counter()
        for v in idx.values():
            if v.get("country") == "pt":
                regions[v.get("region", "(none)")] += 1
        print("\nPT records by region:")
        for r, n in sorted(regions.items()):
            _bullet(r, n)
    else:
        _bullet("(missing)", "run scripts/04_build_maps.py")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
