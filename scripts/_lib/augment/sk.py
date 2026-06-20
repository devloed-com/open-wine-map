"""SK national-spec (ÚPV SR špecifikácia výrobku) (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04).
"""
from __future__ import annotations

import json

from ._shared import _SK_NATIONAL_SPEC_BY_SLUG, NATIONAL_SPECS_SK


def augment_sk_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of SK national-spec sidecar data into stub records.

    Sibling of `augment_bg_records_with_national_specs`. 5 of the SK
    content-stubs (no fetchable EU-OJ JEDNOTNÝ DOKUMENT) are augmented from
    the ÚPV SR (indprop.gov.sk) per-wine špecifikácia výrobku. Stage 02f
    (`scripts/sk/02f_extract_national_specs.py`) parses each text-layer PDF
    fetched by stage 01c into `raw/sk/national-specs-extracted/<slug>.json`.

    For each SK stub with a matching sidecar:
      - grapes            ← section f) označenie odrody alebo odrôd
      - link_to_terroir   ← section g) údaje potvrdzujúce spojitosť
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:` so the audit can tell
                            EU-OJ-extracted from spec-augmented wines
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True — still NOT an EU-OJ extraction, just
    augmented with the canonical ÚPV SR source. Returns count augmented.
    """
    _SK_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_SK.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "sk" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_SK / f"{slug}.json"
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
            "source_org": src.get("source_org") or "upv-sr",
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
        _SK_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
