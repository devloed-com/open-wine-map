"""Grape roles from the EU register's technical file (fiche technique).

Where a country's national source lists its varieties without a principal /
accessory split (SI, SK, HU, BG, GR, HR, RO, MT — every variety read
"principal" on the card), the register's technical file tags each variety
MAIN (named in the single document) or OTHER (the rest of the product
specification's authorised list). Decision of 2026-10-23 (validator phase
E, option B): membership stays the national roster — the newer, legally
binding list — and the fiche supplies the roles.

The overlay applies only where the fiche covers the card's roster
(`COVERAGE_MIN`): a fiche of another vintage (Somlói's names 5 varieties
where the termékleírás names 43) would otherwise demote the national list
wholesale. A card variety the fiche does not list was added to the national
roster after the state's filing and was not a main variety then: it is
shown as accessory and counted (`n_unlisted`) on the card's source line. A
national source that splits roles itself (Bela krajina's pravilnik) is left
untouched, and CZ keeps its own fiche rule (augment/cz.py: the fiche *is* the
roster where it is narrower than the decree).

The RO yield-table split is not a role statement of its own: a variety the
single document names only in its yield table is accessory because §7 omits
it (ro/02 `add_yield_table_varieties`). Decision of 2026-10-25: the fiche
roles apply there too, and a yield-table variety the fiche tags MAIN is
listed (`yield_conflict`, the document's own spellings) so the card says the
two documents disagree — Dealurile Olteniei's Merlot.
"""
from __future__ import annotations

from _lib.augment._shared import _REGISTER_FICHE_ROLES_BY_SLUG
from _lib.register_fiche import load_sidecar

FICHE_ROLE_COUNTRIES = ("si", "sk", "hu", "bg", "gr", "hr", "ro", "mt")
COVERAGE_MIN = 0.8


def fiche_role_sets(fiche: dict | None) -> tuple[set[str], set[str]] | None:
    """The fiche's MAIN and OTHER slug sets, or None when it splits no roles."""
    grapes = (fiche or {}).get("grapes") or {}
    main = {s for s in grapes.get("principal") or [] if s}
    other = {s for s in grapes.get("accessory") or [] if s} - main
    if not main or not other:
        return None
    return main, other


def coverage(card_slugs, fiche_slugs) -> float:
    card = set(card_slugs)
    if not card:
        return 0.0
    return len(card & set(fiche_slugs)) / len(card)


def overlay(record: dict, fiche: dict | None) -> tuple[dict | None, str]:
    """Give the record's roster the fiche's roles, in place. Returns the
    provenance and "applied", or None and the reason nothing changed."""
    if record.get("register_fiche_roster"):
        # the roster itself came from the fiche, roles included (augment/cz.py,
        # augment/sk.py); the document's own § 7 varieties keep their role
        return None, "fiche-roster"
    grapes = record.get("grapes") or {}
    principal = [s for s in grapes.get("principal") or [] if s]
    if not principal:
        return None, "no-roster"
    accessory = [s for s in grapes.get("accessory") or [] if s]
    yield_names = _yield_table_names(record)
    if accessory and not set(accessory) <= set(yield_names):
        return None, "national-roles"
    roster = principal + [s for s in accessory if s not in principal]
    sets = fiche_role_sets(fiche)
    if sets is None:
        return None, "no-split"
    main, other = sets
    cov = coverage(roster, main | other)
    if cov < COVERAGE_MIN:
        return None, "coverage"
    new_principal = [s for s in roster if s in main]
    if not new_principal:
        return None, "no-main"
    new_accessory = [s for s in roster if s not in main]
    unlisted = [s for s in new_accessory if s not in other]
    yield_conflict = [yield_names[s] for s in accessory if s in main]
    role_of = {s: "principal" for s in new_principal}
    role_of.update({s: "accessory" for s in new_accessory})
    for d in grapes.get("details") or []:
        role = role_of.get(d.get("slug"))
        if role:
            d["role"] = role
    grapes["principal"] = new_principal
    grapes["accessory"] = new_accessory
    record["grapes"] = grapes
    src = (fiche or {}).get("source") or {}
    prov = {
        "url": src.get("url") or "",
        "ref": src.get("ref") or "",
        "attachment_uri": src.get("attachment_uri") or "",
        "file_number": (fiche or {}).get("file_number") or "",
        "n_main": len(new_principal),
        "n_other": len(new_accessory) - len(unlisted),
        "n_unlisted": len(unlisted),
        "coverage": round(cov, 3),
        "source_org": "eambrosia-register",
    }
    if yield_conflict:
        prov["yield_conflict"] = yield_conflict
    return prov, "applied"


def _yield_table_names(record: dict) -> dict[str, str]:
    """slug → the document's spelling, for the varieties an RO single
    document names only in its yield table."""
    if record.get("country") != "ro":
        return {}
    return {d["slug"]: d.get("name") or d["slug"]
            for d in (record.get("grapes") or {}).get("details") or []
            if d.get("source") == "yield-table" and d.get("slug")}


def apply_register_fiche_roles(records: list[dict], countries=FICHE_ROLE_COUNTRIES) -> dict:
    """Run the overlay over every parent record of the listed countries that
    has a fiche sidecar; returns the counts stage 04 logs."""
    counts: dict = {"applied": 0, "pills_to_accessory": 0, "skipped": {}}
    for record in records:
        cc = record.get("country")
        slug = record.get("slug") or ""
        if cc not in countries or not slug or record.get("is_sub_denomination"):
            continue
        fiche = load_sidecar(cc, slug)
        if not fiche:
            continue
        before = len((record.get("grapes") or {}).get("principal") or [])
        prov, reason = overlay(record, fiche)
        if prov is None:
            counts["skipped"][reason] = counts["skipped"].get(reason, 0) + 1
            continue
        record["register_fiche_roles"] = prov
        _REGISTER_FICHE_ROLES_BY_SLUG[slug] = prov
        counts["applied"] += 1
        counts["pills_to_accessory"] += max(before - prov["n_main"], 0)
        if prov.get("yield_conflict"):
            counts["yield_conflict"] = counts.get("yield_conflict", 0) + 1
    return counts
