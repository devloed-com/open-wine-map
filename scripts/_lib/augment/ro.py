"""RO national-spec (ONVPV caiet de sarcini) (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04).
"""
from __future__ import annotations

import json

from ._shared import _RO_NATIONAL_SPEC_BY_SLUG, NATIONAL_SPECS_RO


def augment_ro_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of RO national-spec sidecar data into stub records.

    Sibling of `augment_gr_records_with_national_specs`. The 14
    grandfathered RO wines (eAmbrosia carries only a non-fetchable
    `Ares(...)` reference — no EU-OJ DOCUMENT UNIC) ship as content-stubs.
    Stage 02f (`scripts/ro/02f_extract_national_specs.py`) parses the
    ONVPV caiet de sarcini fetched by stage 01c into
    `raw/ro/national-specs-extracted/<slug>.json`.

    For each RO stub with a matching sidecar:
      - grapes            ← §IV Soiurile de struguri (colour-grouped)
      - link_to_terroir   ← §II Legătura cu aria geografică
      - geo_communes      ← §III Delimitarea geografică (drives the GISCO
                            commune-union geometry for the 2 grandfathered
                            IGPs — the RO-specific delta vs. GR/HR)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:`
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True. Returns count augmented.
    """
    _RO_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_RO.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "ro" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_RO / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("source_url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "onvpv",
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
        if sidecar.get("geo_communes"):
            record["geo_communes"] = sidecar["geo_communes"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _RO_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
