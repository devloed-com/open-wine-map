"""Combine OFAG-PDF spine + cantonal-règlement body → per-record JSONs.

Pipeline stage 02 (ch).

Inputs:
  raw/ch/ofag/repertoire-aoc-2026.pdf       (OFAG spine — 63 entries)
  raw/ch/ofag/manifest.json                 (sha256 + license)
  raw/ch/reglements/<canton>/reglement.{pdf,html}   (per-canton règlement)
  raw/ch/reglements/manifest.json           (per-canton metadata)

Outputs:
  raw/ch/dokumente-extracted/<slug>.json    (one JSON per AOC record)
  raw/ch/dokumente-extracted/_index.json    (slug → metadata index)
  raw/ch/dokumente-extracted/manifest.json  (run-level stats)
  raw/ch/extraction-unknowns.json           (unmatched variety names —
                                             curator vocabulary queue)

Record shape (one per OFAG AOC entry — see _lib/ch/ofag_register.py):
  {
    "country": "ch",
    "slug": str,                 // kebab-case identity
    "name": str,                 // OFAG-canonical name
    "canton": str,               // primary canton code
    "cantons": [str, ...],       // all listed cantons (intercantonal-aware)
    "kind": "AOC",
    "tier": "cantonale|régionale|locale",
    "source_lang": "fr|de|it",
    "is_sub_denomination": bool,
    "parent_slug": str (or ""),
    "parent_name": str,
    "parent_canton": str,
    "region": str,               // Swiss wine region (6 of them)
    "sources": [{...}],          // OFAG + canton-règlement provenance
    "section_roles": {
       "summary": str,
       "geo_area": str,
       "varieties": str,
       "link_to_terroir": str (empty in v1)
    },
    "grapes": {"details": [{slug, name, colour, role}, ...]},
    "geo_communes": [{bfs_id, name, canton}, ...]
  }

Sub-denomination model (v1):
- Tier "régionale" and "locale" entries are tagged is_sub_denomination=true
  with parent_slug = the canton's "cantonale" AOC slug (when present).
- Intercantonal AOCs (Vully VD/FR; Zürichsee ZH/SZ) are emitted once with
  `cantons=[primary, secondary]`.
- For VS specifically, the OVV règlement's commune-list parse identifies
  "Grand Cru" communes — per the user-locked scope these become
  per-commune sub-denomination records of the parent Valais AOC.
  (See `_emit_vs_grand_cru` — deferred until commune extraction is
  stable; placeholder hook included.)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.ch.canton import canton_name, source_lang_for_canton  # noqa: E402
from _lib.ch.geometry import CHCommuneIndex  # noqa: E402
from _lib.ch.ofag_register import slugify  # noqa: E402
from _lib.ch.per_aoc_carving import (  # noqa: E402
    CARVE_TEXT_BLOCKS, PER_AOC_COMMUNE_LISTS, VS_GRAND_CRU,
)
from _lib.ch.reglement import (  # noqa: E402
    extract_communes, extract_plaintext, extract_varieties,
    summary_paragraph,
)
from _lib.ch.region import region_for_canton  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)

OFAG_PDF = ROOT / "raw" / "ch" / "ofag" / "repertoire-aoc-2026.pdf"
OFAG_MANIFEST = ROOT / "raw" / "ch" / "ofag" / "manifest.json"
REGLEMENTS_DIR = ROOT / "raw" / "ch" / "reglements"
REGLEMENTS_MANIFEST = REGLEMENTS_DIR / "manifest.json"
SWISSTOPO_GPKG = ROOT / "raw" / "ch" / "swisstopo" / \
    "swissboundaries3d_2026-01_2056_5728.gpkg"

OUT_DIR = ROOT / "raw" / "ch" / "dokumente-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = ROOT / "raw" / "ch" / "dokumente-extracted-manifest.json"
UNKNOWNS = ROOT / "raw" / "ch" / "extraction-unknowns.json"


def _load_reglement_manifest() -> dict:
    if not REGLEMENTS_MANIFEST.exists():
        print(f"[02-ch] ERROR {REGLEMENTS_MANIFEST.relative_to(ROOT)} missing "
              "— run scripts/ch/01_fetch_reglements.py first.", file=sys.stderr)
        sys.exit(2)
    return json.loads(REGLEMENTS_MANIFEST.read_text(encoding="utf-8"))


def _ofag_manifest() -> dict:
    if not OFAG_MANIFEST.exists():
        print(f"[02-ch] ERROR {OFAG_MANIFEST.relative_to(ROOT)} missing "
              "— run scripts/ch/00_fetch_data.py first.", file=sys.stderr)
        sys.exit(2)
    return json.loads(OFAG_MANIFEST.read_text(encoding="utf-8"))


def _build_canton_extracts(commune_idx: CHCommuneIndex,
                           reglement_manifest: dict) -> dict:
    """Per canton: extract text → varieties → communes once. Returns a
    `{canton: {text, varieties, communes, summary, source}}` map."""
    out: dict[str, dict] = {}
    by_canton = reglement_manifest.get("by_canton", {})
    for canton, entry in by_canton.items():
        status = entry.get("status", "")
        if not status.startswith("ok"):
            print(f"[02-ch] {canton}: skip — status={status}", file=sys.stderr)
            continue
        fmt = entry.get("format", "")
        filename = entry.get("filename") or f"reglement.{fmt}"
        path = REGLEMENTS_DIR / canton / filename
        if not path.exists():
            print(f"[02-ch] {canton}: missing file {path.relative_to(ROOT)}",
                  file=sys.stderr)
            continue

        set_pliego_context(f"ch::{canton}::reglement")
        text = extract_plaintext(path)
        lang = entry.get("lang") or source_lang_for_canton(canton)
        varieties = extract_varieties(text, lang, match_variety)
        communes = extract_communes(text, lang, commune_idx)
        # Restrict commune hits to the canton itself (the règlement's
        # area-of-application). A canton's règlement that name-drops
        # another canton's commune in a cross-reference shouldn't add
        # that commune to the AOC's polygon.
        communes = [c for c in communes if c.get("canton") == canton
                    or canton in ("be", "vs", "fr", "gr")]  # bilingual cantons may straddle
        summary = summary_paragraph(text)

        # Per-AOC carving (multi-AOC cantons VD/BE/FR). Returns
        # {slug: [{bfs_id, name, canton}]} for the canton's sub-AOCs.
        per_aoc_communes: dict[str, list[dict]] = {}
        carve_text_fn = CARVE_TEXT_BLOCKS.get(canton)
        if carve_text_fn:
            blocks = carve_text_fn(text)
            for slug, body in blocks.items():
                hits = list(commune_idx.scan_text(body))
                # Restrict to this canton (per the canton-wide rule above).
                kept_hits: list[dict] = []
                seen_bfs: set[int] = set()
                for h in hits:
                    if h["bfs_id"] in seen_bfs:
                        continue
                    if h["canton"] != canton and canton not in ("be", "vs", "fr", "gr"):
                        continue
                    seen_bfs.add(h["bfs_id"])
                    kept_hits.append(h)
                if kept_hits:
                    per_aoc_communes[slug] = kept_hits
        for slug, names in PER_AOC_COMMUNE_LISTS.get(canton, {}).items():
            resolved: list[dict] = []
            seen_bfs = set()
            for name in names:
                for h in commune_idx.lookup(name):
                    if h["bfs_id"] in seen_bfs:
                        continue
                    seen_bfs.add(h["bfs_id"])
                    resolved.append(h)
            if resolved:
                per_aoc_communes[slug] = resolved

        out[canton] = {
            "text": text,
            "varieties": varieties,
            "communes": communes,
            "per_aoc_communes": per_aoc_communes,
            "summary": summary,
            "source_lang": lang,
            "source": {
                "kind": "cantonal-reglement",
                "canton": canton,
                "shelf": entry.get("shelf", ""),
                "url": entry.get("url", ""),
                "format": fmt,
                "filename": filename,
                "sha256": entry.get("sha256", ""),
                "bytes": entry.get("bytes", 0),
                "label": entry.get("source", f"Règlement vinicole — {canton_name(canton)}"),
                "license": entry.get("license", ""),
            },
        }
        carve_summary = (f", carved={sum(len(v) for v in per_aoc_communes.values())} "
                         f"across {len(per_aoc_communes)} sub-AOCs" if per_aoc_communes else "")
        print(f"[02-ch] {canton}: {len(varieties)} varieties, "
              f"{len(communes)} communes, {len(text)} chars{carve_summary}",
              file=sys.stderr)
    return out


def _ofag_source(ofag_meta: dict) -> dict:
    return {
        "kind": "ofag-repertoire",
        "url": ofag_meta.get("source_url", ""),
        "filename": ofag_meta.get("filename", ""),
        "sha256": ofag_meta.get("sha256", ""),
        "bytes": ofag_meta.get("bytes", 0),
        "label": f"OFAG/BLW Répertoire suisse des AOC ({ofag_meta.get('edition','')})",
        "license": ofag_meta.get("license", ""),
    }


def _parent_slug_for(entry, parents_by_canton):
    """Return (parent_slug, parent_name) for non-cantonale tiers."""
    if entry.tier == "cantonale":
        return ("", "")
    canton = entry.canton
    parent = parents_by_canton.get(canton)
    if parent is None:
        return ("", "")
    return (slugify(parent.name), parent.name)


def _build_record(entry, parents_by_canton, canton_data, ofag_source):
    """Build one stage-02 JSON record for an OFAG entry."""
    slug = slugify(entry.name)
    primary_canton = entry.canton
    extract = canton_data.get(primary_canton)
    parent_slug, parent_name = _parent_slug_for(entry, parents_by_canton)
    is_sub = bool(parent_slug)
    source_lang = (extract.get("source_lang") if extract
                   else source_lang_for_canton(primary_canton))

    sources = [ofag_source]
    if extract:
        sources.append(extract["source"])

    grapes = (extract.get("varieties") if extract else []) or []
    # Per-AOC carving (multi-AOC cantons VD/BE/FR): if the canton's
    # extract has a per-AOC commune list for this slug, that wins over
    # the canton-wide commune list. Sub-AOCs WITHOUT a specific carved
    # list and without their own commune enumeration must NOT inherit
    # the canton-wide list — they fall through to `parent-aoc` polygon
    # inheritance in stage 04 (geo_communes left empty).
    per_aoc_map = (extract.get("per_aoc_communes") if extract else {}) or {}
    carved = per_aoc_map.get(slug)
    if carved:
        communes = carved
    elif is_sub:
        # Sub-denomination without carved data — let stage 04 inherit
        # the parent's polygon rather than over-broadly using the
        # canton-wide commune union.
        communes = []
    else:
        # Cantonale (parent): canton-wide commune scan is correct.
        communes = (extract.get("communes") if extract else []) or []
    summary = (extract.get("summary") if extract else "") or ""

    return {
        "country": "ch",
        "slug": slug,
        "name": entry.name,
        "canton": primary_canton,
        "cantons": list(entry.cantons),
        "kind": "AOC",
        "tier": entry.tier,
        "source_lang": source_lang,
        "is_sub_denomination": is_sub,
        "parent_slug": parent_slug,
        "parent_name": parent_name,
        "parent_canton": primary_canton if is_sub else "",
        "region": region_for_canton(primary_canton),
        "sources": sources,
        "section_roles": {
            "summary": summary,
            "geo_area": "",      # canton-wide; commune list carried separately
            "varieties": "",     # ditto
            "link_to_terroir": "",
        },
        "grapes": {"details": grapes},
        "geo_communes": communes,
        "n_grapes": len(grapes),
        "n_communes": len(communes),
        "stub_reason": "" if extract else "no-reglement",
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ofag_meta = _ofag_manifest()
    reglement_meta = _load_reglement_manifest()

    commune_idx = CHCommuneIndex(SWISSTOPO_GPKG)
    canton_data = _build_canton_extracts(commune_idx, reglement_meta)
    ofag_source = _ofag_source(ofag_meta)

    import subprocess
    text_proc = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(OFAG_PDF), "-"],
        capture_output=True, check=True,
    )
    from _lib.ch.ofag_register import parse as parse_ofag_text
    entries = parse_ofag_text(text_proc.stdout.decode("utf-8"))

    # Index parents by canton (the "cantonale" entry per canton).
    parents_by_canton: dict[str, object] = {}
    for e in entries:
        if e.tier == "cantonale":
            parents_by_canton.setdefault(e.canton, e)

    records: list[dict] = []
    by_kind = Counter()
    by_canton = Counter()
    by_geom_status = Counter()
    for e in entries:
        rec = _build_record(e, parents_by_canton, canton_data, ofag_source)
        records.append(rec)
        by_kind[rec["tier"]] += 1
        by_canton[rec["canton"]] += 1
        by_geom_status["with_communes" if rec["geo_communes"] else "no_communes"] += 1

    # Emit VS Grand Cru per-commune sub-denomination records. Per the
    # OVV Art. 86, the canonical list is fanned out across communal
    # règlements not enumerated in OVV itself; the 12 communes below
    # were researched 2026-05 from Vinum Montis + grandcrusion.ch +
    # Thomas Vino historical reportage. Each becomes a sub-AOC of
    # `valais-wallis` with a single-commune polygon resolution.
    vs_extract = canton_data.get("vs", {})
    valais_parent = next((e for e in entries if e.canton == "vs" and e.tier == "cantonale"), None)
    if valais_parent is not None:
        for gc in VS_GRAND_CRU:
            display_name = gc["grand_cru_name"]
            gc_slug = slugify(display_name)
            commune_name = gc["commune"]
            commune_hits = commune_idx.lookup(commune_name)
            if not commune_hits and gc.get("alias"):
                commune_hits = commune_idx.lookup(gc["alias"])
            geo_communes = commune_hits[:1]  # single-commune
            confidence = gc.get("confidence") or "confirmed"
            sources = [ofag_source]
            if vs_extract:
                sources.append(vs_extract["source"])
            gc_record = {
                "country": "ch",
                "slug": gc_slug,
                "name": display_name,
                "canton": "vs",
                "cantons": ["vs"],
                "kind": "AOC",
                "tier": "locale",   # commune-level grand cru
                "source_lang": "fr",
                "is_sub_denomination": True,
                "parent_slug": "valais-wallis",
                "parent_name": "Valais / Wallis",
                "parent_canton": "vs",
                "region": "Valais",
                "sources": sources,
                "section_roles": {
                    "summary": (
                        f"AOC Grand Cru de {commune_name}"
                        f" — homologuée par règlement communal "
                        f"({gc.get('year') or 'année non confirmée'}, "
                        f"OVV art. 86)."
                    ),
                    "geo_area": "",
                    "varieties": "",
                    "link_to_terroir": "",
                },
                "grapes": {"details": []},
                "geo_communes": geo_communes,
                "n_grapes": 0,
                "n_communes": len(geo_communes),
                "grand_cru": {
                    "commune": commune_name,
                    "year_homologated": gc.get("year"),
                    "confidence": confidence,
                    "research_sources": gc.get("sources") or [],
                },
                "stub_reason": "" if geo_communes else "vs-grand-cru-commune-not-resolved",
            }
            records.append(gc_record)
            by_kind["locale"] += 1
            by_canton["vs"] += 1
            by_geom_status["with_communes" if geo_communes else "no_communes"] += 1

    # Write per-record JSONs.
    for rec in records:
        path = OUT_DIR / f"{rec['slug']}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write _index.json (slug → minimal metadata).
    index = {
        rec["slug"]: {
            "slug": rec["slug"], "name": rec["name"],
            "canton": rec["canton"], "cantons": rec["cantons"],
            "tier": rec["tier"], "source_lang": rec["source_lang"],
            "is_sub_denomination": rec["is_sub_denomination"],
            "parent_slug": rec["parent_slug"],
            "region": rec["region"], "n_grapes": rec["n_grapes"],
            "n_communes": rec["n_communes"],
        }
        for rec in sorted(records, key=lambda r: r["slug"])
    }
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_records": len(records),
        "by_tier": dict(by_kind),
        "by_canton": dict(sorted(by_canton.items())),
        "by_geom_status": dict(by_geom_status),
        "n_parents": sum(1 for r in records if not r["is_sub_denomination"]),
        "n_sub_denominations": sum(1 for r in records if r["is_sub_denomination"]),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False,
                                      indent=2, sort_keys=True), encoding="utf-8")

    flush_unknowns_queue(UNKNOWNS)
    print(f"[done] 02-ch: {len(records)} records → {OUT_DIR.relative_to(ROOT)}",
          file=sys.stderr)
    print(f"  by_tier={dict(by_kind)}  by_geom={dict(by_geom_status)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
