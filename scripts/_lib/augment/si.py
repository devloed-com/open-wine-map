"""SI national-spec (specifikacija) augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` so the writer here and the
`_sources_for()` reader in stage 04 reference the same objects.
"""
from __future__ import annotations

import json

from ._shared import _SI_SPECIFIKACIJA_BY_SLUG, SPECIFIKACIJE_SI


def augment_si_records_with_specifikacija(records: list[dict]) -> int:
    """In-place merge of SI national-spec sidecar data into stub records.

    Sibling of `augment_it_records_with_masaf`. The 16 grandfathered SI
    wines (every wine except Cviček) ship as content-stubs because their
    eAmbrosia entry has no fetchable EU-OJ ENOTNI DOKUMENT URL. Stage
    02f (`scripts/si/02f_extract_specifikacije.py`) extracts the
    canonical Slovenian regulator source — either an MKGP per-wine
    `.doc` specifikacija proizvoda or an Uradni list RS pravilnik HTML —
    into a sidecar at `raw/si/specifikacije-extracted/<slug>.json`.

    For each SI stub with a matching sidecar:
      - summary           ← MKGP §2 (opis vin) or pravilnik §2
      - grapes            ← MKGP §6 (sorte) or pravilnik Article-5 +
                            priloga 2 (priporočene → principal,
                            dovoljene → accessory)
      - geo_area_brief    ← MKGP §4 (opredelitev geografskega območja)
      - link_to_terroir   ← MKGP §7 (povezava z geografskim območjem)
                            (pravilnik-derived records have empty
                            link_to_terroir — pravilniki are regulatory
                            lists, not narrative documents)
      - styles            ← MKGP-derived colour/sparkling/predikat tags
      - section_roles     ← unified role dict so 02d can read terroir
                            text uniformly
      - stub_reason       ← prefixed `specifikacija:` so the audit can
                            tell EU-OJ-extracted from spec-augmented
      - specifikacija     ← provenance block (url, sha256, fetched_at,
                            parser_template, source_org, license)

    `record["stub"]` stays True — the record is still NOT an EU-OJ
    extraction, just augmented with the canonical Slovenian regulator
    source. Stage 03 / 04 callers use the `specifikacija` block to
    distinguish and to render attribution.

    Returns the number of records augmented.
    """
    _SI_SPECIFIKACIJA_BY_SLUG.clear()
    if not SPECIFIKACIJE_SI.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "si":
            continue
        if not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = SPECIFIKACIJE_SI / f"{slug}.json"
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
            "matched_okoliši": sidecar.get("matched_okoliši") or [],
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes"):
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
        _SI_SPECIFIKACIJA_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
