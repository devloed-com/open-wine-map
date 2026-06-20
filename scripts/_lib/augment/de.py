"""DE BLE Produktspezifikation variety role split + terroir (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance cache + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04).
"""
from __future__ import annotations

import json

from ._shared import _DE_PRODUKTSPEZIFIKATION_BY_SLUG, PRODUKTSPEZIFIKATION_DE


def augment_de_records_with_produktspezifikation(records: list[dict]) -> int:
    """In-place merge of BLE-Produktspezifikation sidecar data into DE
    parent-Anbaugebiet records.

    The EU Einziges Dokument for German wines doesn't carry a principal/
    accessory split — section 7 is a flat list. The BLE national
    Produktspezifikation (Amtliches Werk §5 UrhG) names individual
    varieties with their own Mindestmostgewicht threshold in §3.2 (Mosel
    → Riesling/Elbling/Müller-Thurgau/Dornfelder). Stage 02f extracts
    that split into raw/de/produktspezifikationen-extracted/<slug>.json;
    this augment re-tags the in-memory record's grapes block accordingly.

    Two sidecar categories are merged (both written by stage 02f):
      - the 13 Anbaugebiete (regional PDOs), with a principal/accessory
        split from §3.2 Mindestmostgewicht; and
      - the 15 Landwein g.g.A. that ship as stubs (no EU Einziges
        Dokument). Their BLE spec has no role split, so they arrive as
        `section-8-flat-no-split` (all-principal) and fold their full
        roster + §-Zusammenhang terroir text into the stub record.
    Einzellage sub-denominations are still skipped (they inherit the
    parent Anbaugebiet's varieties at render time).

    For records with `role_split_method == "section-3.2-principal"`:
      - re-tag existing record["grapes"]["details"] items as
        principal/accessory based on the sidecar's slug sets
      - rebuild record["grapes"]["principal"] / ["accessory"] lists
      - fold any new sidecar slugs not already in the EU record

    For records with `role_split_method == "section-8-flat-no-split"`
    (Anbaugebiete whose §3.2 doesn't enumerate per-variety thresholds —
    Franken, Württemberg in v1): the existing all-principal default
    stands; the sidecar just records the BLE source as provenance.

    Stage 04 reads the cached provenance later in the AOC-blob phase
    via `_DE_PRODUKTSPEZIFIKATION_BY_SLUG`.

    Returns the number of records augmented.
    """
    _DE_PRODUKTSPEZIFIKATION_BY_SLUG.clear()
    if not PRODUKTSPEZIFIKATION_DE.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "de":
            continue
        if record.get("is_sub_denomination"):
            continue
        slug = record.get("slug") or ""
        sidecar_path = PRODUKTSPEZIFIKATION_DE / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        method = sidecar.get("role_split_method") or ""
        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "source_org": src.get("source_org") or "BLE",
            "license": src.get("license") or "Amtliches Werk §5 UrhG",
            "role_split_method": method,
            "n_principal": sidecar.get("n_principal") or 0,
            "n_accessory": sidecar.get("n_accessory") or 0,
        }

        # BLE §8/§9 "Zusammenhang" terroir backfill — when the EU
        # Einziges Dokument is sparse (stub or no link_to_terroir), use
        # the BLE PDF's terroir block so 02d can extract facts from it.
        # Affects Ahr, Baden, Hessische Bergstraße, Rheingau, Sachsen,
        # Saale-Unstrut in v1. We also record the BLE PDF URL as the
        # cahier_source for downstream provenance.
        bz = (sidecar.get("zusammenhang_text") or "").strip()
        eu_terroir = (record.get("link_to_terroir") or "").strip()
        if bz and len(eu_terroir) < 400:
            record["link_to_terroir"] = bz
            section_roles = dict(record.get("section_roles") or {})
            section_roles["link_to_terroir"] = bz
            record["section_roles"] = section_roles
            # Surface the BLE PDF as the canonical terroir source so the
            # panel + 02d attribute it correctly.
            rec_src = dict(record.get("source") or {})
            rec_src["terroir_source_url"] = src.get("url") or ""
            rec_src["terroir_source_org"] = "BLE"
            record["source"] = rec_src
            provenance["terroir_backfilled"] = True

        # For both role-split methods, fold the sidecar's variety roster
        # into the in-memory record. The default fold tags non-sidecar
        # EU slugs as `accessory` (the BLE PDF's §3.2 is the principal
        # allowlist); the flat-no-split method instead tags everything
        # as principal because the document doesn't enumerate a split.
        if method in ("section-3.2-principal", "section-8-flat-no-split"):
            # Build slug → role from the sidecar.
            sidecar_role: dict[str, str] = {}
            sidecar_details: list[dict] = []
            for g in sidecar.get("grapes") or []:
                s = g.get("slug")
                if s:
                    sidecar_role[s] = g.get("role") or "principal"
                    sidecar_details.append(g)

            # Re-tag the EU-record's existing details. Keep the EU
            # record's display name (matches the wine's own
            # Einziges-Dokument spelling). When the sidecar has an
            # authoritative §3.2 split, slugs NOT named in the sidecar
            # default to "accessory" — the BLE PDF's §3.2 is the
            # principal-allowlist, so anything outside it is
            # implicitly "alle übrigen Rebsorten". When the sidecar is
            # flat-no-split, every slug is principal (the regulator
            # didn't enumerate a split).
            unmatched_default = (
                "principal" if method == "section-8-flat-no-split" else "accessory"
            )
            grapes = dict(record.get("grapes") or {})
            details_in = grapes.get("details") or []
            new_details: list[dict] = []
            eu_slugs: set[str] = set()
            for d in details_in:
                new_d = dict(d)
                s = new_d.get("slug")
                if s:
                    new_d["role"] = sidecar_role.get(s, unmatched_default)
                new_details.append(new_d)
                if s:
                    eu_slugs.add(s)

            # Fold in any sidecar varieties that the EU record missed
            # (the §8 list is more complete than the EU section 7 for
            # some Anbaugebiete).
            for g in sidecar_details:
                s = g.get("slug")
                if s and s not in eu_slugs:
                    new_details.append({
                        "slug": s,
                        "name": g.get("name", s),
                        "role": g.get("role", "accessory"),
                        "colour": g.get("colour", ""),
                        "source": "ble-produktspezifikation",
                    })

            # Rebuild principal / accessory lists from the re-tagged
            # details (deterministic + dedup-by-first-seen).
            principal: list[str] = []
            accessory: list[str] = []
            seen_p: set[str] = set()
            seen_a: set[str] = set()
            for d in new_details:
                s = d.get("slug")
                if not s:
                    continue
                if d.get("role") == "accessory":
                    if s in seen_a:
                        continue
                    seen_a.add(s)
                    accessory.append(s)
                else:
                    if s in seen_p:
                        continue
                    seen_p.add(s)
                    principal.append(s)
            grapes["principal"] = principal
            grapes["accessory"] = accessory
            grapes["details"] = new_details
            record["grapes"] = grapes

        record["produktspezifikation"] = provenance
        _DE_PRODUKTSPEZIFIKATION_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
