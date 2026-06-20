"""BG national-spec (ИАЛВ продуктова спецификация) (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04).
"""
from __future__ import annotations

import json

from ._shared import _BG_NATIONAL_SPEC_BY_SLUG, NATIONAL_SPECS_BG


def augment_bg_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of BG national-spec sidecar data into stub records.

    Sibling of `augment_gr_records_with_national_specs`. 51 of 54 BG wines
    ship as content-stubs (no fetchable EU-OJ ЕДИНЕН ДОКУМЕНТ). Stage 02f
    (`scripts/bg/02f_extract_national_specs.py`) parses the ИАЛВ / IAVV
    per-wine продуктова спецификация PDF fetched by stage 01c into
    `raw/bg/national-specs-extracted/<slug>.json` (51 of 51).

    For each BG stub with a matching sidecar:
      - grapes            ← section 5 (Винени сортове грозде, colour-split)
      - link_to_terroir   ← section 6 (Връзка с географския район)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:` so the audit can tell
                            EU-OJ-extracted from spec-augmented wines
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True — still NOT an EU-OJ extraction, just
    augmented with the canonical ИАЛВ source. Returns count augmented.
    """
    _BG_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_BG.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "bg" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_BG / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "iavv",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _BG_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
