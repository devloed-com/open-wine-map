"""ES national-pliego variety augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` so the writer here and the
`_sources_for()` reader in stage 04 reference the same objects.
"""
from __future__ import annotations

import json

from ._shared import _ES_NATIONAL_PLIEGO_BY_SLUG, NATIONAL_PLIEGOS_ES


def augment_es_records_with_national_pliegos(records: list[dict]) -> int:
    """In-place merge of national-pliego sidecar varieties into each ES
    record's `grapes` field. Returns the number of records augmented.

    Mutations per record:
      - new variety slugs (those NOT already in principal ∪ accessory) are
        appended to `grapes.accessory`
      - matching entries are appended to `grapes.details` with
        `role="accessory"` and `source="national-pliego"` so the UI can
        distinguish doc-único-canonical varieties from pliego-augmented ones
      - a top-level `national_pliego` block carries provenance for
        `_sources_for()` to surface in the panel
    """
    _ES_NATIONAL_PLIEGO_BY_SLUG.clear()
    if not NATIONAL_PLIEGOS_ES.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "es":
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_PLIEGOS_ES / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        new_slugs = list(sidecar.get("delta_vs_oj", {}).get("new_slugs") or [])
        if not new_slugs:
            # Still stamp provenance — the pliego was parsed even if it
            # added nothing new. Skip the merge but keep attribution
            # consistent for the audit.
            nat_provenance = {
                "url": sidecar.get("source", {}).get("url", ""),
                "sha256": sidecar.get("source", {}).get("sha256", ""),
                "fetched_at": sidecar.get("source", {}).get("fetched_at", ""),
                "parser_template": sidecar.get("parser_template", ""),
                "added_slugs": [],
            }
            record["national_pliego"] = nat_provenance
            _ES_NATIONAL_PLIEGO_BY_SLUG[slug] = nat_provenance
            continue
        grapes = dict(record.get("grapes") or {})
        principal = list(grapes.get("principal") or [])
        accessory = list(grapes.get("accessory") or [])
        details = list(grapes.get("details") or [])
        existing = set(principal) | set(accessory)
        added: list[str] = []
        slug_to_detail = {d.get("slug"): d for d in sidecar.get("varieties", [])}
        for s in new_slugs:
            if s in existing:
                continue
            accessory.append(s)
            existing.add(s)
            added.append(s)
            detail = dict(slug_to_detail.get(s) or {"slug": s, "name": s, "colour": ""})
            detail["role"] = "accessory"
            detail["source"] = "national-pliego"
            details.append(detail)
        grapes["accessory"] = accessory
        grapes["details"] = details
        record["grapes"] = grapes
        nat_provenance = {
            "url": sidecar.get("source", {}).get("url", ""),
            "sha256": sidecar.get("source", {}).get("sha256", ""),
            "fetched_at": sidecar.get("source", {}).get("fetched_at", ""),
            "parser_template": sidecar.get("parser_template", ""),
            "added_slugs": added,
        }
        record["national_pliego"] = nat_provenance
        _ES_NATIONAL_PLIEGO_BY_SLUG[slug] = nat_provenance
        if added:
            augmented += 1
    return augmented
