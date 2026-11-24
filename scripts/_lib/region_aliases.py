"""Regions an appellation is listed under beside its own — the region level of
the listing rule of 2026-10-25 (`country_aliases` for countries, `co_parents`
for parent appellations): a record that spans several regions of its
country's sidebar hierarchy is listed under each. It stays one record (one
slug, one polygon), keeps its primary `region` for the title, the description,
JSON-LD and the facet counts, and the card names every region it spans.

Three sources, merged per record:

1. the curated table `region_aliases.json`: every entry carries a verbatim
   quote of the record's own area text (`tests/test_region_aliases.py` checks
   it against the extracted record) or a reason with its source; an entry
   with `regions: []` suppresses the two derivations below for that record.
2. an umbrella PGI drawn as the union of member PDOs (`region-pdo-union`):
   the regions of its members — the same member table that draws its polygon
   (`<cc>/geometry.py`, `*_PGI_MEMBER_PDOS`).
3. FR: the wine-region buckets whose own AOCs share communes with the
   record's INAO aire (the aires-communes CSV, the legal aire): a bucket
   counts when at least `FR_MIN_SHARED` of the record's communes lie in the
   aires of that bucket's AOCs and they make `FR_MIN_SHARE` of the record's
   aire or `FR_MIN_COVER` of the bucket's. An AOC holding two other AOCs
   (the Bourgogne regionals, Côtes du Rhône, Champagne) is left out of its
   bucket's communes, or every Beaujolais cru would also be "in" Burgundy
   through the Bourgogne aire. ARMAGNAC (the brandy's and Floc's bucket,
   laid over the same Gascon ground as SUD-OUEST by design) is neither a
   source nor a target.

`scripts/sweep_region_aliases.py` is the detector: it lists the geometric
candidates the build does not list (NEW), the table's `rejected` pairs and the
entries the geometry no longer supports (STALE).
"""

from __future__ import annotations

import importlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

TABLE = Path(__file__).with_name("region_aliases.json")

# countries whose umbrella PGIs are drawn from a member-PDO table
MEMBER_TABLE_COUNTRIES: tuple[str, ...] = ("be", "bg", "cz", "de", "hu", "mt", "si", "sk")

FR_EXCLUDED = frozenset({"ARMAGNAC"})
FR_MIN_SHARED = 5
FR_MIN_SHARE = 0.03
FR_MIN_COVER = 0.25
UMBRELLA_HOLD = 0.8


def load_table(path: Path = TABLE) -> dict:
    """{"entries": {slug: {...}}, "rejected": {slug: {region: reason}}}."""
    if not path.exists():
        return {"entries": {}, "rejected": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"entries": raw.get("entries") or {}, "rejected": raw.get("rejected") or {}}


# A record with a member row that is drawn from its own unit list
# (scripts/_lib/de/area_units.py, gemeinde_list.py).
OWN_LIST_SOURCES = ("alkis-gemarkung-union", "gisco-commune-union")


def member_tables() -> dict[str, dict[str, tuple[str, ...]]]:
    out: dict[str, dict[str, tuple[str, ...]]] = {}
    for cc in MEMBER_TABLE_COUNTRIES:
        mod = importlib.import_module(f"_lib.{cc}.geometry")
        out[cc] = getattr(mod, f"{cc.upper()}_PGI_MEMBER_PDOS")
    return out


def _parents(records: Iterable[dict]) -> list[dict]:
    return [r for r in records if not r.get("is_sub_denomination")]


def member_aliases(records: Iterable[dict], tables: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """Umbrella PGIs drawn from their member PDOs → the members' regions."""
    tables = member_tables() if tables is None else tables
    parents = _parents(records)
    region_by_fn: dict[tuple[str, str], str] = {}
    for r in parents:
        if r.get("file_number"):
            region_by_fn[(r["country"], r["file_number"])] = r.get("region") or ""
    out: dict[str, list[str]] = {}
    for r in parents:
        members = (tables.get(r["country"]) or {}).get(r.get("file_number") or "")
        # a German Landwein drawn from the list its own text prints is still
        # the Landwein of the Anbaugebiete its member row names
        own_list = r.get("country") == "de" and r.get("geom_source") in OWN_LIST_SOURCES
        if r.get("geom_source") != "region-pdo-union" and not own_list:
            continue
        if not members:
            continue
        regions = {region_by_fn.get((r["country"], fn), "") for fn in members}
        regions -= {"", r.get("region") or ""}
        if regions:
            out[r["slug"]] = sorted(regions)
    return out


def _umbrellas(aires: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    items = sorted(aires.items(), key=lambda kv: len(kv[1]))
    for slug, aire in aires.items():
        held = 0
        for other, oaire in items:
            if len(oaire) >= len(aire):
                break
            if other != slug and len(oaire & aire) >= UMBRELLA_HOLD * len(oaire):
                held += 1
                if held >= 2:
                    out.add(slug)
                    break
    return out


def fr_aire_aliases(
    records: Iterable[dict], aire_of: Callable[[str], set[str] | None]
) -> dict[str, dict[str, dict]]:
    """{slug: {bucket: {"shared": n, "via": [AOC slugs, most communes first]}}}."""
    recs: dict[str, dict] = {}
    for r in _parents(records):
        if r.get("country") != "fr" or (r.get("region") or "") in FR_EXCLUDED:
            continue
        aire = aire_of(r["name"])
        if aire:
            recs[r["slug"]] = {**r, "aire": set(aire)}
    aoc_aires = {s: v["aire"] for s, v in recs.items() if v.get("kind") == "AOC" and v.get("is_wine", True)}
    umbrellas = _umbrellas(aoc_aires)
    core: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for s, aire in aoc_aires.items():
        if s in umbrellas:
            continue
        for commune in aire:
            core[recs[s]["region"]][commune].add(s)
    out: dict[str, dict[str, dict]] = {}
    for s, v in recs.items():
        n = len(v["aire"])
        for bucket, communes in core.items():
            if bucket == v["region"] or bucket in FR_EXCLUDED:
                continue
            shared = v["aire"] & communes.keys()
            k = len(shared)
            if k < FR_MIN_SHARED:
                continue
            if k / n < FR_MIN_SHARE and k / len(communes) < FR_MIN_COVER:
                continue
            via: dict[str, int] = defaultdict(int)
            for c in shared:
                for a in communes[c]:
                    via[a] += 1
            out.setdefault(s, {})[bucket] = {
                "shared": k,
                "via": [a for a, _ in sorted(via.items(), key=lambda x: (-x[1], x[0]))],
            }
    return out


def derive(
    records: list[dict],
    aire_of: Callable[[str], set[str] | None] | None = None,
    table: dict | None = None,
    tables: dict[str, dict] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({slug: sorted alias regions}, warnings). `records` carry slug,
    name, country, region, kind, is_wine, is_sub_denomination, file_number,
    geom_source. Sub-denominations get none: the sidebar files them under
    their parent's aliases, the card keeps their own region."""
    table = load_table() if table is None else table
    entries = table.get("entries") or {}
    derived: dict[str, set[str]] = defaultdict(set)
    for slug, regions in member_aliases(records, tables).items():
        derived[slug].update(regions)
    if aire_of is not None:
        for slug, buckets in fr_aire_aliases(records, aire_of).items():
            derived[slug].update(buckets)
    by_slug = {r["slug"]: r for r in records}
    regions_by_country: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.get("region"):
            regions_by_country[r["country"]].add(r["region"])
    warnings: list[str] = []
    out: dict[str, list[str]] = {}
    for slug, entry in entries.items():
        if slug.startswith("_"):
            continue
        if slug not in by_slug:
            warnings.append(f"{slug}: not in the corpus (STALE table entry)")
            continue
        derived[slug] = set(entry.get("regions") or [])
    for slug, regions in derived.items():
        rec = by_slug.get(slug)
        if not rec or rec.get("is_sub_denomination"):
            continue
        keep = []
        for region in sorted(regions):
            if region == (rec.get("region") or ""):
                continue
            if region not in regions_by_country[rec["country"]]:
                warnings.append(f"{slug}: alias region {region!r} is no region of {rec['country']} in the build")
                continue
            keep.append(region)
        if keep:
            out[slug] = keep
    return out, warnings
