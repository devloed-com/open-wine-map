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


# the document's roster is a fraction of the fiche's: the single document
# names a handful of varieties where the technical file lists the whole
# authorised roster with its MAIN / OTHER tags
FICHE_WIDER_ROSTER_MAX_SHARE = 0.5


def fiche_roster_is_wider(doc_n: int, fiche_n: int) -> bool:
    return fiche_n > 0 and doc_n < FICHE_WIDER_ROSTER_MAX_SHARE * fiche_n


def augment_sk_records_with_register_fiche(records: list[dict]) -> int:
    """A non-stub SK record whose EU single document § 7 names a few varieties
    where the register's technical file lists the authorised roster with a
    MAIN / OTHER split takes the fiche's roster (2026-11-07): the document's
    own § 7 varieties stay principal, the fiche's MAIN join them, its OTHER are
    the accessories, and the card cites the fiche (`register_fiche_roster`,
    the CZ pattern in reverse — there the fiche is the narrower list).
    Stredoslovenská: § 7 of OJ C 122/2020 names Furmint alone, the fiche of
    2013 ten main and thirty other varieties; the card had carried one pill.
    The roles overlay (augment/fiche_roles.py) then leaves the record alone.
    Returns the count augmented."""
    from _lib.grape_lexicon import DEFAULT_COLOUR  # noqa: E402
    from _lib.lexicon_loading import _load_vivc_colour_by_slug  # noqa: E402
    from _lib.register_fiche import load_sidecar  # noqa: E402

    from ._shared import _REGISTER_FICHE_ROSTER_BY_SLUG

    vivc_colour: dict | None = None
    augmented = 0
    for record in records:
        if (record.get("country") != "sk" or record.get("stub")
                or record.get("is_sub_denomination")):
            continue
        slug = record.get("slug") or ""
        fiche = load_sidecar("sk", slug) if slug else None
        if not fiche:
            continue
        fg = fiche.get("grapes") or {}
        main = [s for s in fg.get("principal") or [] if s]
        other = [s for s in fg.get("accessory") or [] if s and s not in main]
        if not main or not other:
            continue
        grapes = dict(record.get("grapes") or {})
        own_principal = [s for s in grapes.get("principal") or [] if s]
        own_accessory = [s for s in grapes.get("accessory") or [] if s]
        if not fiche_roster_is_wider(len(set(own_principal + own_accessory)), len(main) + len(other)):
            continue
        if vivc_colour is None:
            vivc_colour = _load_vivc_colour_by_slug()
        details = list(grapes.get("details") or [])
        seen = {d.get("slug") for d in details if d.get("slug")}
        for d in fg.get("details") or []:
            s = d.get("slug")
            if not s or s in seen:
                continue
            seen.add(s)
            details.append({
                "slug": s,
                "name": d.get("name") or s,
                "role": "accessory" if d.get("role") == "accessory" else "principal",
                "colour": d.get("colour") or DEFAULT_COLOUR.get(s) or vivc_colour.get(s) or "",
                "source": "eambrosia-register-fiche",
            })
        principal = own_principal + [s for s in main if s not in own_principal]
        accessory = [s for s in own_accessory + other if s not in principal]
        grapes["principal"] = list(dict.fromkeys(principal))
        grapes["accessory"] = list(dict.fromkeys(accessory))
        grapes["details"] = details
        record["grapes"] = grapes
        src = fiche.get("source") or {}
        prov = {
            "url": src.get("url") or "",
            "ref": src.get("ref") or "",
            "attachment_uri": src.get("attachment_uri") or "",
            "n_varieties": len(main) + len(other),
            "n_main": len(main),
            "n_other": len(other),
            "n_document": len(set(own_principal + own_accessory)),
            "source_org": "eambrosia-register",
        }
        record["register_fiche_roster"] = prov
        _REGISTER_FICHE_ROSTER_BY_SLUG[slug] = prov
        augmented += 1
    return augmented
