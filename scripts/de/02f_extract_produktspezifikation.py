"""Extract the BLE Produktspezifikation variety lists + terroir text.

Pipeline stage 02f (de). DE analog of `scripts/it/02f_extract_masaf.py`
and `scripts/es/02f_extract_national_pliegos.py` — pulls the regulator's
canonical variety list from the national specification PDF, and uses the
production-rules section's per-variety thresholds to derive a principal
vs accessory split that the EU Einziges Dokument doesn't carry.

Two source categories, dispatched by the manifest's `category` field:
  - `anbaugebiet` (13 quality-wine PDOs) → `produktspezifikation.extract`,
    the four rigid section-numbered templates + §3.2 principal split.
  - `landwein` (15 Landwein g.g.A. that ship as stubs with no fetchable
    EU Einziges Dokument) → `landwein_spezifikation.extract`, a
    heterogeneous-layout lexicon scan. Landwein has no role split, so its
    sidecar lands as `section-8-flat-no-split` (all-principal) and carries
    the §-Zusammenhang terroir text the stub record otherwise lacks.

Reads:
  raw/de/produktspezifikationen/<slug>.pdf  (downloaded by stage 00 in
    a future revision; currently downloaded ad-hoc by this script)
  raw/de/produktspezifikationen/manifest.json
  raw/de/produktspezifikationen/manual_overrides.json  (curator path)
  raw/de/dokumente-extracted/<slug>.json  (the EU-document records — for
    slug existence check + producer-group metadata)

Writes:
  raw/de/produktspezifikationen-extracted/<slug>.json  (sidecar per slug)
  raw/de/produktspezifikationen-extracted/_index.json
  raw/de/produktspezifikationen-extracted/manifest.json

Role split logic:
  - principal = varieties named with their own Mindestmostgewicht
    threshold in §3.2 of the Produktspezifikation
    (de-facto principal — same pattern as ES MAPA / IT MASAF where the
    regulator's production-rules section is the role-split signal)
  - accessory = all other varieties from §8 (Zugelassene
    Keltertraubensorten), section/colour-tagged
  - When §3.2 is absent or parses empty (older PDF templates), fall back
    to: everything in §8 is principal. Record `role_split_method` so the
    UI knows which Anbaugebiete have an authoritative split.

Re-runnable per slug or in sweep mode:
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --slug mosel
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.de.produktspezifikation import extract as parse_anbaugebiet_pdf  # noqa: E402
from _lib.de.landwein_spezifikation import extract as parse_landwein_pdf  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

PDF_DIR = ROOT / "raw" / "de" / "produktspezifikationen"
MANIFEST = PDF_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
EXTRACTED_DE = ROOT / "raw" / "de" / "dokumente-extracted"
UNKNOWNS = ROOT / "raw" / "de" / "extraction-unknowns-produktspezifikation.json"


def _slug_match(name: str) -> dict | None:
    """Resolve a raw variety name to a slug via the shared grape lexicon.

    Returns {"slug": ..., "name": original_name, "colour": colour}
    or None if no match (queued for curator review)."""
    m = match_variety(name)
    if m is None:
        return None
    return {"slug": m.slug, "name": name, "colour": m.colour or ""}


def _resolve_names(names: list[str], default_role: str) -> tuple[list[dict], list[str]]:
    """Resolve raw variety names → list of {slug,name,colour,role}. Returns
    (resolved, unmatched_names)."""
    resolved: list[dict] = []
    unmatched: list[str] = []
    seen_slugs: set[str] = set()
    for raw_name in names:
        d = _slug_match(raw_name)
        if d is None:
            unmatched.append(raw_name)
            continue
        if d["slug"] in seen_slugs:
            continue
        seen_slugs.add(d["slug"])
        d["role"] = default_role
        resolved.append(d)
    return resolved, unmatched


def _build_record(slug: str, pdf_meta: dict, parsed: dict) -> dict:
    """Build the sidecar record for one Anbaugebiet."""
    set_pliego_context(slug)
    # Principal names from §3.2.
    principal_raw = parsed["section_3_2_principal_names"]
    # All authorised names from §8.
    all_white = parsed["section_8_white_names"]
    all_red = parsed["section_8_red_names"]

    principal_resolved, prin_unmatched = _resolve_names(principal_raw, "principal")
    principal_slugs = {d["slug"] for d in principal_resolved}

    all_resolved: list[dict] = list(principal_resolved)
    section_8_unmatched: list[str] = []
    if principal_slugs:
        # Real role split: §3.2 principal, everything else from §8 = accessory.
        role_split_method = "section-3.2-principal"
        for name in (*all_white, *all_red):
            d = _slug_match(name)
            if d is None:
                section_8_unmatched.append(name)
                continue
            if d["slug"] in principal_slugs:
                continue
            if d["slug"] in {x["slug"] for x in all_resolved}:
                continue
            d["role"] = "accessory"
            all_resolved.append(d)
    else:
        # No §3.2 principal split — everything in §8 = principal, no
        # accessory. Records the limitation so the UI can attribute.
        role_split_method = "section-8-flat-no-split"
        for name in (*all_white, *all_red):
            d = _slug_match(name)
            if d is None:
                section_8_unmatched.append(name)
                continue
            if d["slug"] in {x["slug"] for x in all_resolved}:
                continue
            d["role"] = "principal"
            all_resolved.append(d)

    n_principal = sum(1 for d in all_resolved if d["role"] == "principal")
    n_accessory = sum(1 for d in all_resolved if d["role"] == "accessory")

    return {
        "country": "de",
        "slug": slug,
        "display": pdf_meta.get("display") or slug,
        "role_split_method": role_split_method,
        "n_total": len(all_resolved),
        "n_principal": n_principal,
        "n_accessory": n_accessory,
        "grapes": all_resolved,
        "raw_section_3_2_principal": principal_raw,
        "raw_section_8_white": all_white,
        "raw_section_8_red": all_red,
        "unmatched_names": section_8_unmatched + prin_unmatched,
        # Plain-text §8/§9 "Zusammenhang mit dem geografischen Gebiet"
        # — the richer terroir narrative the BLE PDF carries. Surfaces
        # in stage 04's DE augment as the link_to_terroir source when
        # the EU Einziges Dokument is empty (Ahr, Baden, Hessische
        # Bergstraße, Rheingau, Sachsen, Saale-Unstrut).
        "zusammenhang_text": parsed.get("zusammenhang_text", ""),
        "source": {
            "kind": "ble-produktspezifikation",
            "url": pdf_meta.get("url", ""),
            "sha256": pdf_meta.get("sha256", ""),
            "bytes": pdf_meta.get("bytes", 0),
            "fetched_at": pdf_meta.get("fetched_at", ""),
            "source_org": "BLE",
            "license": "Amtliches Werk §5 UrhG",
            "note": pdf_meta.get("note", ""),
        },
    }


def _process_slug(slug: str, pdf_meta: dict) -> dict | None:
    pdf_path = PDF_DIR / f"{slug}.pdf"
    if not pdf_path.exists():
        print(f"  {slug}: no PDF at {pdf_path}", file=sys.stderr)
        return None
    # Landwein g.g.A. specs use a heterogeneous layout (variety roster at
    # §6/§7/§8, no role split) → the dedicated lexicon-scan parser; the
    # 13 Anbaugebiete use the four rigid section-numbered templates.
    parse_pdf = (
        parse_landwein_pdf
        if pdf_meta.get("category") == "landwein"
        else parse_anbaugebiet_pdf
    )
    try:
        parsed = parse_pdf(pdf_path)
    except Exception as e:  # noqa: BLE001
        print(f"  {slug}: parse error: {e}", file=sys.stderr)
        return None
    record = _build_record(slug, pdf_meta, parsed)
    if record["n_total"] == 0:
        # Older PDF template — no varieties extracted. Skip the sidecar
        # so the EU-document data (already loaded in stage 04) stays
        # authoritative.
        print(
            f"  {slug}: empty parse (older PDF template — needs template-{slug} branch); skipping sidecar",
            file=sys.stderr,
        )
        return None
    out_path = OUT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", action="append", default=[], help="single slug (repeatable)")
    ap.add_argument("--all", action="store_true", help="process all PDFs in manifest")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"error: {MANIFEST} missing — run scripts/de/00_fetch_data.py first "
              "(or manually populate raw/de/produktspezifikationen/)",
              file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_slug = manifest.get("by_slug", {})

    if args.slug:
        slugs = list(args.slug)
    elif args.all:
        slugs = sorted(by_slug.keys())
    else:
        print("error: pass --all or --slug SLUG", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    n_ok = n_skip = 0
    for slug in tqdm(slugs, desc="02f-de", leave=False):
        pdf_meta = by_slug.get(slug, {})
        rec = _process_slug(slug, pdf_meta)
        if rec is None:
            n_skip += 1
            continue
        index[slug] = {
            "slug": slug,
            "n_principal": rec["n_principal"],
            "n_accessory": rec["n_accessory"],
            "role_split_method": rec["role_split_method"],
            "n_unmatched": len(rec["unmatched_names"]),
        }
        n_ok += 1

    set_pliego_context(None)
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    OUT_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_org": "BLE",
        "license": "Amtliches Werk §5 UrhG",
        "n_extracted": n_ok,
        "n_skipped": n_skip,
        "by_slug": index,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    n_unknowns = flush_unknowns_queue(UNKNOWNS)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{UNKNOWNS.relative_to(ROOT)}",
            file=sys.stderr,
        )

    print(
        f"[02f/de] extracted={n_ok} skipped={n_skip} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
