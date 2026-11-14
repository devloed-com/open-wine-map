"""AT BML Produktspezifikation roster + terroir backfill (stage 04).

An Austrian record is no stub: its EU Einziges Dokument is extracted, and its
§ 7 "Wichtigste Keltertraubensorten" are the card's principal varieties. The
BML Produktspezifikation (stage 02f sidecar,
raw/at/produktspezifikationen-extracted/<slug>.json) is the regulator's
fuller statement of the same designation, and this augmenter adds what the
EU document leaves out:

  - every variety the specification's section f) authorises and the EU
    document does not name, with the sidecar's role — principal for a
    "Hauptsorte" or a member of a closed exclusive list, accessory for the
    rest of the national roster (scripts/at/02f_extract_produktspezifikationen.py)
    — tagged `source: bml-produktspezifikation`; a variety the EU document
    names keeps its EU role and spelling, nothing is ever demoted or removed;
  - the section g) terroir text as `link_to_terroir` where the EU document's
    is under 400 characters (Oberösterreich's 347), so stage 02d has a text
    to ground on — the same rule as the DE BLE backfill;
  - the provenance `_sources_for()` surfaces as the card's Sources row
    ("Produktspezifikation (BML, PDF) — +N varieties added") and the panel
    payload's `bml_produktspezifikation_*` keys.

Wachau: the EU document names Grüner Veltliner and Riesling; the
specification's Gebietswein list adds 14 accessories (visitor flag of
2026-11-07). Weinviertel's specification allows Grüner Veltliner alone, so
its card keeps one grape by law.
"""
from __future__ import annotations

import json

from ._shared import _AT_PRODUKTSPEZIFIKATION_BY_SLUG, PRODUKTSPEZIFIKATION_AT

TERROIR_BACKFILL_MAX_EU_CHARS = 400
SOURCE_TAG = "bml-produktspezifikation"
COLOUR_STYLES = ("blanc", "noir", "rose")


def merge_stated_colours(record: dict, sidecar: dict) -> list[str]:
    """Add the colours the specification states (sidecar `styles_stated`) to
    a record whose EU document already states at least one colour — the
    specification completes the EU list (Oberösterreich's "Die Rotweine
    werden aus den Sorten …" beside the EU text's white). A record whose EU
    text states no colour keeps the berry-colour floor: one stated colour
    would switch the floor off and lose the others (Eisenberg's Welschriesling
    whites). Returns the colours added."""
    styles = list(record.get("styles") or [])
    if not any(s in COLOUR_STYLES for s in styles):
        return []
    added = [c for c in sidecar.get("styles_stated") or [] if c in COLOUR_STYLES and c not in styles]
    if added:
        record["styles"] = styles + added
    return added


def merge_roster(record: dict, sidecar: dict) -> list[str]:
    """Fold the sidecar's varieties the record lacks into record["grapes"];
    returns the added slugs. The record's own details keep their role,
    name and order; the added ones follow with the sidecar's role."""
    grapes = dict(record.get("grapes") or {})
    details = [dict(d) for d in (grapes.get("details") or [])]
    have = {d.get("slug") for d in details if d.get("slug")}
    added: list[str] = []
    for g in sidecar.get("grapes") or []:
        slug = g.get("slug")
        if not slug or slug in have:
            continue
        have.add(slug)
        added.append(slug)
        details.append({
            "slug": slug,
            "name": g.get("name") or slug,
            "role": g.get("role") or "accessory",
            "colour": g.get("colour") or "",
            "source": SOURCE_TAG,
        })
    principal: list[str] = []
    accessory: list[str] = []
    observation: list[str] = []
    for d in details:
        slug = d.get("slug")
        if not slug:
            continue
        bucket = {"accessory": accessory, "observation": observation}.get(d.get("role"), principal)
        if slug not in bucket:
            bucket.append(slug)
    grapes["details"] = details
    grapes["principal"] = principal
    grapes["accessory"] = accessory
    if observation or "observation" in grapes:
        grapes["observation"] = observation
    record["grapes"] = grapes
    return added


def augment_at_records_with_produktspezifikation(records: list[dict]) -> int:
    """In-place merge of the BML sidecars into the AT records; returns the
    number of records that carry a sidecar (added varieties or not — the
    card cites the specification either way)."""
    _AT_PRODUKTSPEZIFIKATION_BY_SLUG.clear()
    if not PRODUKTSPEZIFIKATION_AT.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "at" or record.get("is_sub_denomination"):
            continue
        slug = record.get("slug") or ""
        path = PRODUKTSPEZIFIKATION_AT / f"{slug}.json"
        if not path.exists():
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        src = sidecar.get("source") or {}
        added = merge_roster(record, sidecar)
        styles_added = merge_stated_colours(record, sidecar)
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "source_org": src.get("source_org") or "BML",
            "license": src.get("license") or "",
            "parser_template": sidecar.get("parser_template") or "",
            "role_rule": sidecar.get("role_rule") or "",
            "n_added": len(added),
            "added_slugs": added,
            "styles_added": styles_added,
            "styles_evidence": {c: (sidecar.get("styles_evidence") or {}).get(c, "") for c in styles_added},
            "hauptsorten": list(sidecar.get("hauptsorten") or []),
            "open_roster_clauses": list(sidecar.get("open_roster_clauses") or []),
        }
        zusammenhang = (sidecar.get("zusammenhang_text") or "").strip()
        eu_terroir = (record.get("link_to_terroir") or "").strip()
        if zusammenhang and len(eu_terroir) < TERROIR_BACKFILL_MAX_EU_CHARS \
                and len(zusammenhang) > len(eu_terroir):
            record["link_to_terroir"] = zusammenhang
            section_roles = dict(record.get("section_roles") or {})
            section_roles["link_to_terroir"] = zusammenhang
            record["section_roles"] = section_roles
            rec_src = dict(record.get("source") or {})
            rec_src["terroir_source_url"] = src.get("url") or ""
            rec_src["terroir_source_org"] = "BML"
            record["source"] = rec_src
            provenance["terroir_backfilled"] = True
        record["produktspezifikation"] = provenance
        _AT_PRODUKTSPEZIFIKATION_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented
