"""ES national-pliego variety augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` so the writer here and the
`_sources_for()` reader in stage 04 reference the same objects.
"""
from __future__ import annotations

import json
import re

from _lib.terroir_chapters import fold

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
        # A subzona is a part of its DO: the DO's national pliego is its
        # pliego too (Rioja Alta lacked the Malvasía the Rioja pliego adds).
        pliego_slug = (
            record.get("parent_slug") if record.get("is_sub_denomination") else slug
        ) or slug
        sidecar_path = NATIONAL_PLIEGOS_ES / f"{pliego_slug}.json"
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
            _apply_subzona_principals(record, sidecar)
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
        _apply_subzona_principals(record, sidecar)
        if added:
            augmented += 1
    return augmented


# Vinos de Madrid's pliego names each subzona's principal varieties after
# the DO's list ("Principales Subzona de Arganda — Blancas: Malvar. — Tintas:
# Tinto Fino (Tempranillo)."); the rest of the DO's roster stays allowed.
_PRINCIPALES = re.compile(
    r"Principales\s+Subzona\s+de\s+([^\n]+?)\s*\n(.*?)(?=Principales\s+Subzona|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _apply_subzona_principals(record: dict, sidecar: dict) -> None:
    if not record.get("is_sub_denomination"):
        return
    want = fold(record.get("name") or "")
    for m in _PRINCIPALES.finditer(sidecar.get("section_text") or ""):
        if fold(m.group(1)) != want:
            continue
        from _lib.grape_entity import match_variety
        named: set[str] = set()
        for n in re.split(r"[,;\n()]|\s+y\s+|:", m.group(2)):
            n = n.strip(" .-")
            hit = match_variety(n) if n and fold(n) not in ("blancas", "tintas") else None
            if hit is not None and not hit.method.startswith("fuzzy"):
                named.add(hit.slug)
        grapes = record.get("grapes") or {}
        details = grapes.get("details") or []
        roster = list(grapes.get("principal") or []) + list(grapes.get("accessory") or [])
        principal = [s for s in roster if s in named]
        if not principal:
            return
        grapes["principal"] = [s for s in roster if s in principal]
        grapes["accessory"] = [s for s in roster if s not in principal]
        for d in details:
            d["role"] = "principal" if d.get("slug") in principal else "accessory"
        record["grapes"] = grapes
        return
