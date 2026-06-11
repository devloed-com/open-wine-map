"""HU national-spec (Agrárminisztérium termékleírás) (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04).
"""
from __future__ import annotations

import json

from ._shared import _HU_NATIONAL_SPEC_BY_SLUG, NATIONAL_SPECS_HU


def augment_hu_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of HU national-spec sidecar data into stub records.

    Sibling of `augment_ro_records_with_national_specs`. The 15
    grandfathered HU wines (eAmbrosia carries only a non-fetchable
    `Ares(...)` reference — no EU-OJ EGYSÉGES DOKUMENTUM) ship as
    content-stubs. Stage 02f (`scripts/hu/02f_extract_national_specs.py`)
    parses the Agrárminisztérium termékleírás PDF fetched by stage 01c
    into `raw/hu/national-specs-extracted/<slug>.json`.

    For each HU stub with a matching sidecar:
      - grapes            ← VI. ENGEDÉLYEZETT SZŐLŐFAJTÁK
      - link_to_terroir   ← VII. KAPCSOLAT A FÖLDRAJZI TERÜLETTEL
      - geo_communes      ← IV. KÖRÜLHATÁROLT TERÜLET (commune-precision;
                            geometry still prefers the Bétard polygon
                            these wines already have, so this is a record)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:`
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True. Returns count augmented.
    """
    _HU_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_HU.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "hu":
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_HU / f"{slug}.json"
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
            "source_org": src.get("source_org") or "agrarminiszterium",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        # Fill-if-empty: a stub is fully empty so this fills everything;
        # a non-stub with a thin EU extraction (e.g. Badacsony, whose
        # awkward doc structure left the grape section unrouted) gets only
        # its EMPTY fields filled — good EUR-Lex data is never clobbered.
        cur_grapes = record.get("grapes") or {}
        if (sidecar.get("summary") and not record.get("summary")):
            record["summary"] = sidecar["summary"]
        if (sidecar.get("grapes")
                and (sidecar["grapes"].get("principal") or sidecar["grapes"].get("accessory"))
                and not (cur_grapes.get("principal") or cur_grapes.get("accessory"))):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief") and not record.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("geo_communes") and not record.get("geo_communes"):
            record["geo_communes"] = sidecar["geo_communes"]
        if sidecar.get("dulok") and not record.get("dulok"):
            record["dulok"] = sidecar["dulok"]
        if sidecar.get("link_to_terroir") and not record.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        sidecar_roles = sidecar.get("section_roles") or {}
        for role in ("geo_area", "grape_varieties", "link_to_terroir"):
            if sidecar_roles.get(role) and not section_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub") and record.get("stub_reason") \
                and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _HU_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
