"""IT MASAF disciplinare + regional-register + sottozona augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance caches + sidecar dirs live in `_shared` (same objects as the
`_sources_for()` reader in stage 04). `_backfill_it_nonstub_from_masaf` is a
private helper of `augment_it_records_with_masaf` and moves with it;
`synthesize_it_sottozone_records` keeps its call order in stage 04 main().
"""
from __future__ import annotations

import json

from _lib.it.sottozona import extract_sottozone as extract_it_sottozone

from ._shared import (
    _IT_MASAF_BY_SLUG,
    _IT_REGISTER_BY_SLUG,
    IT_REGIONAL_REGISTERS,
    MASAF_DISCIPLINARI_IT,
)


def _backfill_it_nonstub_from_masaf(record: dict, sidecar: dict) -> bool:
    """Fill ONLY the empty fields of a non-stub IT record from its MASAF
    sidecar — the documento unico is canonical, but some OJ docs omit the
    geo area or variety list, and the national disciplinare carries them.
    Never overwrites populated docunico data. Returns True if anything
    was filled."""
    filled = False
    g = record.get("grapes") or {}
    if sidecar.get("grapes") and not (g.get("principal") or g.get("accessory")):
        record["grapes"] = sidecar["grapes"]
        filled = True
    if sidecar.get("menzioni") and not record.get("menzioni"):
        record["menzioni"] = sidecar["menzioni"]
        filled = True
    section_roles = dict(record.get("section_roles") or {})
    if sidecar.get("geo_area_brief") and not (record.get("geo_area_brief") or "").strip():
        record["geo_area_brief"] = sidecar["geo_area_brief"]
        section_roles["geo_area"] = sidecar["geo_area_brief"]
        filled = True
    if sidecar.get("link_to_terroir") and not (record.get("link_to_terroir") or "").strip():
        record["link_to_terroir"] = sidecar["link_to_terroir"]
        section_roles["link_to_terroir"] = sidecar["link_to_terroir"]
        filled = True
    if filled:
        record["section_roles"] = section_roles
        record["masaf_backfill"] = True
    return filled


def augment_it_records_with_masaf(records: list[dict]) -> int:
    """In-place merge of MASAF disciplinare sidecar data into IT stub
    records. Only stubs are touched — wines whose documento unico was
    extracted in stage 02 already carry canonical EUR-Lex data and
    shouldn't be overwritten.

    For each IT stub with a matching sidecar at
    raw/it/masaf-disciplinari-extracted/<slug>.json the following
    fields are merged:
      - summary           ← Article 1 first paragraph
      - regione           ← derived from Article 3 / 9 text
      - grapes            ← parsed from Article 2 (principal-only)
      - geo_area_brief    ← Article 3 body
      - link_to_terroir   ← Article 9 body
      - section_roles     ← {grape_varieties, geo_area, link_to_terroir, ...}
      - stub_reason       ← prefixed "masaf:" so the audit can tell
                            doc-unico-extracted from masaf-augmented
      - masaf             ← provenance block (url, sha256, fetched_at,
                            parser_template, bundle_key, archive_path)

    `record["stub"]` stays True — the record is still NOT a documento
    unico extraction, just augmented. Stage 03 / 04 callers use the
    `masaf` block to distinguish.

    Returns the number of records augmented.
    """
    _IT_MASAF_BY_SLUG.clear()
    if not MASAF_DISCIPLINARI_IT.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "it":
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = MASAF_DISCIPLINARI_IT / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        # Non-stub records carry canonical EUR-Lex documento-unico data —
        # only BACKFILL fields the documento unico left empty (some OJ
        # docs omit the area or variety list), never overwrite. Stubs get
        # the full merge below.
        if not record.get("stub"):
            if _backfill_it_nonstub_from_masaf(record, sidecar):
                augmented += 1
            continue

        # Build the provenance block (also cached for the AOC-blob phase).
        src = sidecar.get("source") or {}
        match_info = sidecar.get("match") or {}
        provenance = {
            "filename": src.get("filename") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "parser_template": sidecar.get("parser_template") or "",
            "bundle_key": src.get("bundle_key") or "",
            "archive_path": src.get("archive_path") or "",
            "match_how": match_info.get("how") or "",
            "pdf_filename": match_info.get("pdf_filename") or "",
            # When an override pinned the URL, surface it for the panel.
            "override_url": src.get("url") or "",
            "override_source_org": src.get("source_org") or "",
        }

        # Merge augmented fields onto the record. Replace rather than
        # union — the record was a stub so there's nothing to lose.
        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("regione") and not record.get("regione"):
            record["regione"] = sidecar["regione"]
        if sidecar.get("grapes"):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("menzioni") and not record.get("menzioni"):
            record["menzioni"] = sidecar["menzioni"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        # IT MASAF is the last national-spec layer to carry styles; merge them
        # the same way every other augment does (union, never clobber). The
        # disciplinare's tipologie + organoleptic articles supply the markers
        # (spumante / passito / vin santo / dolce) the grape-colour floor can't
        # infer; the floor still backfills any colour the scan missed.
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))
        section_roles = dict(record.get("section_roles") or {})
        if sidecar.get("grapes"):
            section_roles.setdefault("grape_varieties", "")
        if sidecar.get("geo_area_brief"):
            section_roles["geo_area"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            section_roles["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("summary"):
            section_roles["description"] = sidecar["summary"]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("masaf:"):
            record["stub_reason"] = f"masaf:{record['stub_reason']}"
        record["masaf"] = provenance
        _IT_MASAF_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_it_records_with_regional_registers(records: list[dict]) -> int:
    """Fill the grape roster of regional-IGT records whose disciplinare
    defers to the Region's authorised-variety register (the annex is
    absent from the MASAF PDF). Each region sidecar at
    raw/it/regional-variety-registers/<region>.json lists the IGT slugs
    (`igts`) that draw from it. Only applied when the record still has no
    grapes, so a varietal IGT (e.g. catalanesca-del-monte-somma, excluded
    from the `igts` lists) is never given a whole regional roster.

    Returns the number of records given a roster."""
    _IT_REGISTER_BY_SLUG.clear()
    sources = IT_REGIONAL_REGISTERS / "sources.json"
    if not sources.exists():
        return 0
    by_slug: dict[str, dict] = {}
    for region in json.loads(sources.read_text(encoding="utf-8")):
        if region.startswith("_"):
            continue
        sidecar_path = IT_REGIONAL_REGISTERS / f"{region}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for igt in sidecar.get("igts", []):
            by_slug[igt] = sidecar

    augmented = 0
    for record in records:
        if record.get("country") != "it":
            continue
        slug = record.get("slug")
        sidecar = by_slug.get(slug)
        if not sidecar:
            continue
        g = record.get("grapes") or {}
        if g.get("principal") or g.get("accessory"):
            continue
        slugs = [v["slug"] for v in sidecar.get("varieties", [])]
        if not slugs:
            continue
        record["grapes"] = {
            "principal": slugs,
            "accessory": [],
            "observation": [],
            "details": [
                {"slug": v["slug"], "name": v["name"], "role": "principal",
                 "colour": v.get("colour", ""),
                 "source": "regional-variety-register"}
                for v in sidecar["varieties"]
            ],
        }
        src = sidecar.get("source") or {}
        provenance = {
            "region": sidecar.get("region", ""),
            "url": src.get("url", ""),
            "source_org": src.get("source_org", ""),
            "note": src.get("note", ""),
            "sha256": src.get("sha256", ""),
            "n_varieties": len(slugs),
        }
        record["regional_register"] = provenance
        _IT_REGISTER_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def synthesize_it_sottozone_records(records: list[dict]) -> int:
    """Emit first-class sub-denomination records for Italian sottozone
    detected in the MASAF disciplinare (Chianti's 7, Valtellina's 5,
    Bardolino's 3, …). The EU documento unico rarely names them, so
    stage 02 emits none — they live in the national disciplinare's
    Article 1, which 02f cached in the sidecar's `article_bodies`.

    Each sottozona becomes a child record mirroring the ES subzona /
    FR DGC model: `is_sub_denomination=True`, `parent_slug`,
    `parent_name`, `parent_id_eambrosia`, inheriting the parent's
    grapes / styles / terroir / regione. Geometry resolves via the
    stage-04 `parent-appellation` inheritance step. Appended to
    `records` (processed after every parent, so parent geometry is
    available). Returns the number of sottozona records created."""
    if not MASAF_DISCIPLINARI_IT.exists():
        return 0
    existing = {r.get("slug") for r in records if r.get("country") == "it"}
    new_records: list[dict] = []
    for record in list(records):
        if record.get("country") != "it" or record.get("is_sub_denomination"):
            continue
        slug = record.get("slug")
        sidecar_path = MASAF_DISCIPLINARI_IT / f"{slug}.json"
        if not slug or not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        bodies = sidecar.get("article_bodies") or {}
        text = " ".join(
            [sidecar.get("geo_area_brief") or "", bodies.get("1", ""), bodies.get("3", "")]
        )
        parent_name = record.get("name") or slug
        for sz in extract_it_sottozone(text, parent_name):
            sz_slug = f"{slug}-{sz['slug']}"
            if not sz["slug"] or sz_slug in existing:
                continue
            existing.add(sz_slug)
            child = dict(record)
            child.update({
                "slug": sz_slug,
                "name": f"{parent_name} {sz['name']}",
                "is_sub_denomination": True,
                "parent_slug": slug,
                "parent_name": parent_name,
                "parent_id_eambrosia": record.get("id_eambrosia") or "",
                "menzioni": [],
                "sottozona_source": "masaf-disciplinare-article-1",
            })
            new_records.append(child)
    records.extend(new_records)
    return len(new_records)
