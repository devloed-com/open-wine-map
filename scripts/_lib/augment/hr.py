"""HR national-spec (specifikacija) augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` so the writer here and the
`_sources_for()` reader in stage 04 reference the same objects.
"""
from __future__ import annotations

import json

from ._shared import _HR_SPECIFIKACIJA_BY_SLUG, SPECIFIKACIJE_HR


def augment_hr_records_with_specifikacija(records: list[dict]) -> int:
    """In-place merge of HR national-spec sidecar data into stub records.

    Sibling of `augment_si_records_with_specifikacija`. The 16
    grandfathered HR wines (everything except Muškat momjanski + Ponikve)
    ship as content-stubs because their eAmbrosia entry has no fetchable
    EU-OJ JEDINSTVENI DOKUMENT URL. Stage 02f
    (`scripts/hr/02f_extract_specifikacije.py`) extracts the canonical
    Ministarstvo poljoprivrede per-wine SPECIFIKACIJA PROIZVODA (14
    `.doc`, 1 `.docx`, 1 PDF) into a sidecar at
    `raw/hr/specifikacije-extracted/<slug>.json`.

    For each HR stub with a matching sidecar:
      - summary           ← lettered section b) (opis svojstava vina)
      - grapes            ← section f) (sorte vinove loze; colour-grouped,
                            all principal — the MPS spec has no
                            principal/accessory split, same as PT/IT)
      - geo_area_brief    ← section d) (granice područja)
      - link_to_terroir   ← section g) (…povezane sa zemljopisnim
                            uvjetima); empty for the Primorska docx
      - styles            ← colour/sparkling/dessert/liqueur tags
      - section_roles     ← unified role dict so 02d reads terroir text
      - stub_reason       ← prefixed `specifikacija:` so the audit can
                            tell EU-OJ-extracted from spec-augmented
      - specifikacija     ← provenance block (url, sha256, fetched_at,
                            parser_template, source_org, license)

    `record["stub"]` stays True — the record is still NOT an EU-OJ
    extraction, just augmented with the canonical Croatian regulator
    source. Returns the number of records augmented.
    """
    _HR_SPECIFIKACIJA_BY_SLUG.clear()
    if not SPECIFIKACIJE_HR.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "hr":
            continue
        if not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = SPECIFIKACIJE_HR / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "final_url": src.get("final_url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "",
            "license": src.get("license") or "",
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
            existing_styles = set(record.get("styles") or [])
            record["styles"] = sorted(existing_styles | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("specifikacija:"):
            record["stub_reason"] = f"specifikacija:{record['stub_reason']}"
        record["specifikacija"] = provenance
        _HR_SPECIFIKACIJA_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
