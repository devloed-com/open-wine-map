#!/usr/bin/env python3
"""The French corpus against INAO's portal of official delimitation plans.

INAO's «portail des plans officiels de délimitation» is a public Nextcloud
share holding the scanned parcel plans (one folder per denomination, one
sub-folder per commune, one TIF per cadastral sheet) and
`inventaire_etat_de_la_delimitation.xlsx`, one row per (appellation, commune).
This audit binds every French record to its inventory appellation and plan
folder and runs six checks (`_lib/fr/plan_inventory_audit.py` holds the logic
and the bucket rules):

  1  parcellaire records: «oui, plan disponible» communes with no parcel row;
     parcel rows in a commune the inventory marks non; plans in preparation
  2  commune-union records: what the card says about a parcel delimitation;
     parcel communes that are a small share of the drawn aire (Champagne)
  3  the aire géographique: the inventory's communes against INAO's rows (with
     the supplements) and the cahier's list, former communes folded
  4  the plan folders against «plan disponible» (INAO against INAO)
  5  revisions under way, plans much older than the cahier, parcel rows an
     earlier shapefile release had
  6  sub-denominations with plans of their own that we draw coarser

and lists what it cannot bind. Buckets: CONFLICT-OURS, CONFLICT-INVENTORY,
UNDETERMINED, INTERNAL, REVISION. Read-only: it changes no data, geometry or
card. The share is listed with `PROPFIND Depth: 1` and cached under
raw/cache/inao-plans-portal/; without `--fetch` only the cache is read.

    .venv/bin/python scripts/audit_plan_inventory.py [--only SLUG …] [--json PATH]
        [--strict] [--fetch] [--all]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import aires as A  # noqa: E402
from _lib.dgc_village_overrides import DGC_VILLAGE_INSEE  # noqa: E402
from _lib.fr import former_communes as FC  # noqa: E402
from _lib.fr import parcel_area as PA  # noqa: E402
from _lib.fr import plan_inventory as PI  # noqa: E402
from _lib.fr import plans_portal as PP  # noqa: E402
from _lib.fr.plan_inventory_audit import (  # noqa: E402
    BUCKETS,
    CONFLICT_OURS,
    INTERNAL,
    Finding,
    RecordContext,
    check_aire,
    check_commune_union,
    check_dates,
    check_parcellaire,
    check_plans,
    check_subdenomination,
    group_inventory,
    match_records,
    norm,
)
from _lib.fr.seat_communes import flat, name_pattern, zone_text  # noqa: E402
from _lib.geom_chain import cahier_insee, load_commune_index  # noqa: E402
from _lib.parcellaire_gaps import CACHE_DIR as COVERAGE_CACHE  # noqa: E402
from _lib.parcellaire_gaps import load_coverage, load_gap_fills  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"


def _load_aires_vs_cahier():
    import importlib.util

    spec = importlib.util.spec_from_file_location("audit_aires_vs_cahier",
                                                  ROOT / "scripts" / "audit_aires_vs_cahier.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_AVC = _load_aires_vs_cahier()


def _classify(text: str, name: str, code: str) -> tuple[str, str]:
    """audit_aires_vs_cahier's reading of one name in the zone text, its
    exclusion-clause rule included («… à l'exception de Saint-Grégoire … pour
    la production des pommes»)."""
    verdict, quote = _AVC.classify(text, name, code)
    if verdict == "whole":
        # «Banyuls-dels-Aspres en partie (sections AA, A2 …)»: the qualifier
        # stands between the name and its bracket, which classify does not see
        for m in name_pattern(name).finditer(text):
            after = text[m.end(): m.end() + 40]
            if re.match(r"(?i)\s*(?:en\s+partie|pour\s+partie|\(?\s*pour\s+(?:la|le)\s+seule?|\(\s*sections?\b)", after):
                return "partial", "in part: … " + re.sub(r"\s+", " ", text[max(0, m.start() - 40): m.end() + 80]) + " …"
        for clause in _AVC._EXCLUSION_CLAUSE_RE.finditer(text):
            if name_pattern(name).search(clause.group(0)):
                return "partial", "named in an exclusion: « " + re.sub(r"\s+", " ", clause.group(0))[:140] + " … »"
    return verdict, quote
COMMUNES = ROOT / "raw" / "ign" / "communes.geojson"
WIKI_DATA = ROOT / "wiki" / "data"
MANIFEST = ROOT / "raw" / "manifest.json"

# Records whose inventory appellation carries another name, each with why.
NAME_PINS: dict[str, dict] = {
    "la-liviniere": {
        "inventory": "minervois-la livinière", "sign": "AOC",
        "reason": "the EU register (PDO-FR-A0667) and SIQO name the AOC «La Livinière»; the inventory "
                  "still writes its former name «Minervois-La Livinière»",
    },
    "marc-d-alsace-gewurztraminer": {
        "inventory": "marc d'alsace", "sign": "AOC",
        "reason": "the referentiel's appellation column reads «Marc d'Alsace» (the record carries the "
                  "registered name, siqo_supplements.json `name_overrides`)",
    },
}


def _near(key: str, by_key: dict) -> str | None:
    from rapidfuzz import fuzz

    hits = [k for k in by_key if abs(len(k) - len(key)) <= 2 and fuzz.ratio(key, k) >= 95]
    return hits[0] if len(hits) == 1 else None


def _load_build() -> tuple[dict[str, dict], str]:
    blobs = sorted(WIKI_DATA.glob("aocs.en.*.js"), key=lambda p: p.stat().st_mtime)
    if not blobs:
        sys.exit("no startup blob under wiki/data/ — run stage 04 first")
    text = blobs[-1].read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"): text.rindex("}") + 1])["aocs"]
    return {k: v for k, v in data.items() if v.get("country") == "fr"}, blobs[-1].name


def _panel(slug: str) -> dict:
    p = WIKI_DATA / "d" / "en" / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _old_coverage(current: str) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str]]:
    """Communes per appellation and per denomination in the earlier releases
    whose coverage index is cached."""
    by_app: dict[str, set[str]] = defaultdict(set)
    by_denom: dict[str, set[str]] = defaultdict(set)
    releases = []
    for p in sorted(COVERAGE_CACHE.glob("*.json")):
        if p.stem >= Path(current).stem:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        releases.append(p.stem[:10])
        for app, denoms in data["by_app"].items():
            for d, codes in denoms.items():
                # a cache written before 2026-09-28 keeps a field of two codes
                # ("49078,49115", a merged commune) as one string
                split = {part.strip() for c in codes for part in c.split(",") if part.strip()}
                by_app[app].update(split)
                by_denom[d].update(split)
    return by_app, by_denom, releases


def _folder_index(portal: PP.Portal, records: list[dict], match_by_slug: dict) -> tuple[dict, list[str], dict, list[dict]]:
    """slug → (folder, {code: name}, sample); the folders no record takes; how
    each folder was bound; and the folders whose sampled sheets carry the
    number of an unrelated denomination (INAO's filing, check 4)."""
    dirs = PP.appellation_dirs(portal)
    by_denom = {str(r.get("id_denomination_geo") or ""): r["slug"] for r in records if r.get("id_denomination_geo")}
    by_slug_rec = {r["slug"]: r for r in records}
    # a record's whole name first, then its inventory name, then the " ou "
    # aliases: «Auxey-Duresses ou Auxey-Duresses Côte de Beaune» (a DGC) must
    # not take the parent's folder through its first alias
    full: dict[str, str] = {}
    alias: dict[str, str] = {}
    for r in records:
        full.setdefault(norm(r["name"]), r["slug"])
        inv = match_by_slug.get(r["slug"])
        if inv:
            full.setdefault(norm(inv[0][1]), r["slug"])
    for r in records:
        names = [r["name"]] + ([match_by_slug[r["slug"]][0][1]] if r["slug"] in match_by_slug else [])
        for n in names:
            for part in re.split(r"\s+ou\s+", n):
                alias.setdefault(norm(part), r["slug"])
    out: dict[str, tuple] = {}
    via: dict[str, str] = {}
    unbound: list[str] = []
    misfiled: list[dict] = []
    cands = []
    for d in dirs:
        communes = PP.commune_folders(portal, d)
        if communes is None:
            unbound.append(f"{d} (not listed — run with --fetch)")
            continue
        sample = None
        entries = portal.list(PP.PAR_APPELLATION + d + "/") or []
        first = next((e.name for e in entries if e.is_dir and PP.commune_dir(e.name)), None)
        if first:
            sample = PP.sample_folder(portal, d, first)
        key = PP.folder_key(d)
        by_name = full.get(key) or alias.get(key)
        by_sheet = (by_denom.get(sample.denoms[0]) if sample and len(sample.denoms) == 1 else None)
        cands.append((d, communes, sample, by_name, by_sheet))
    # 1. the folder's name and its sheets' number agree; 2. the sheets' number
    # (AOC_RASTEAU holds the still wine's sheets, 2899); 3. the name (a climat's
    # sheets carry its premier cru's number, Ladoix's climats 665; a folder can
    # hold another denomination's sheets: Volnay premier cru's Flagey folder)
    # on a tie the folder with more sheets (Sainte-Croix-du-Mont has two
    # folders, one holding a modification's assemblage only)
    cands.sort(key=lambda c: (-(c[2].sheets if c[2] else 0), c[0]))
    for phase in (1, 2, 3):
        for d, communes, sample, by_name, by_sheet in cands:
            if d in via:
                continue
            slug = (by_name if phase == 1 and by_name and by_name == by_sheet
                    else by_sheet if phase == 2 and by_sheet and by_sheet not in out
                    else by_name if phase == 3 and by_name and by_name not in out else None)
            if slug is None or slug in out:
                continue
            out[slug] = (d, communes, sample)
            via[d] = ("name and sheets" if phase == 1 else "name" if phase == 3
                      else f"sheets ({sample.denoms[0]})")
    for d, communes, sample, by_name, by_sheet in cands:
        if d in via:
            continue
        taken = by_name or by_sheet
        unbound.append(d + (f" (record {taken} already bound to {out[taken][0]})" if taken in out
                            else f" (files carry AOC_{'/'.join(sample.denoms)})" if sample and sample.denoms
                            else ""))
    for slug, (d, communes, sample) in out.items():
        own = str(by_slug_rec[slug].get("id_denomination_geo") or "")
        if not (sample and sample.denoms and own) or own in sample.denoms:
            continue
        others = [by_denom.get(x, x) for x in sample.denoms]
        via[d] += f"; its sampled sheets carry {', '.join(sample.denoms)} ({', '.join(others)})"
        if own.startswith("p"):
            # a provisional id of siqo_supplements.json (Montpeyroux, p23354):
            # the sheets give INAO's number
            continue
        # a climat's sheets carry its premier cru's number, a parent's sheets
        # a DGC's of the same name: normal. Another denomination is not.
        name_key = norm(by_slug_rec[slug]["name"])
        related = [o for o in others if o in by_slug_rec
                   and (name_key.startswith(norm(by_slug_rec[o]["name"]))
                        or norm(by_slug_rec[o]["name"]).startswith(name_key))]
        if not related:
            misfiled.append({"slug": slug, "folder": d, "commune_folder": sample.commune,
                             "carries": sample.denoms, "carries_records": others, "own": own})
    return out, unbound, via, misfiled


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[], help="record slug (repeatable)")
    ap.add_argument("--json", type=Path, help="write every finding")
    ap.add_argument("--strict", action="store_true", help="exit 1 on a CONFLICT-OURS finding")
    ap.add_argument("--fetch", action="store_true",
                    help="list on INAO's share the folders the cache lacks (else the cache only)")
    ap.add_argument("--all", action="store_true", help="print every finding (default: the first 60 per bucket)")
    args = ap.parse_args()

    if not PI.INVENTORY_XLSX.exists():
        sys.exit(f"{PI.INVENTORY_XLSX.relative_to(ROOT)} missing — run stage 00")
    rows = PI.read_rows(PI.INVENTORY_XLSX)
    commune_idx, insee_idx, insee_name = load_commune_index(COMMUNES, FC.FORMER_GEOJSON, FC.MOVEMENTS_CSV)
    former = FC.load(insee_idx, log=False)

    def canon(code: str) -> str:
        if code in insee_idx:
            return code
        # the arrondissements of Paris, Lyon and Marseille (the shapefile codes
        # Côtes de Provence's Marseille parcels 13209)
        for lo, hi, city in (("75101", "75120", "75056"), ("69381", "69389", "69123"),
                             ("13201", "13216", "13055")):
            if lo <= code <= hi and len(code) == 5:
                return city
        return former.commune_of_today(code)

    def recoded(code: str) -> bool:
        end = former.successor.get(code)
        return bool(end) and former.predecessors.get(end, set()) <= {code}

    def name_of(code: str) -> str:
        return insee_name.get(code) or former.name(code)

    old_names: dict[str, list[str]] = defaultdict(list)
    for code, nm in FC.former_names(insee_idx):
        old_names[code].append(nm)
    inventory = group_inventory(rows, canon)
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(EXTRACTED.glob("*.json")) if not p.name.startswith("_")]
    records = [r for r in records if (r.get("country") or "fr") == "fr" and r.get("slug")]
    by_slug = {r["slug"]: r for r in records}
    A.register_product_names(
        sorted({r["name"] for r in records if r.get("product_class") == "spirit"}),
        sorted({r["name"] for r in records if not r.get("product_class")}),
    )
    in_scope = [r for r in records if not (r.get("kind") == "EDV" and r.get("signe_fr") != "AOC")]
    out_of_scope = [r for r in records if r not in in_scope]
    match = match_records(in_scope, inventory.keys(), NAME_PINS, _near)

    build, blob_name = _load_build()
    cov = load_coverage()
    if cov is None:
        sys.exit("no INAO parcellaire shapefile under raw/inao/parcellaire/")
    cov_denom: dict[str, set[str]] = defaultdict(set)
    for denoms in cov.by_app.values():
        for d, codes in denoms.items():
            cov_denom[d].update(codes)
    old_app, old_denom, old_releases = _old_coverage(cov.shapefile)
    digitised = {canon(c) for c in cov.digitised}
    aires = A.load_aires()
    supplements = A.load_aire_supplements()
    fills = load_gap_fills()
    table = PI.table()
    portal = PP.Portal(offline=not args.fetch)
    folders, unbound_folders, folder_via, misfiled = _folder_index(portal, in_scope, match.by_slug)

    def fold(codes) -> set[str]:
        return {canon(c) for c in (codes or ()) if c}

    folder_names: dict[str, dict[str, str]] = {}
    findings = [Finding(
        "4", INTERNAL, m["slug"], by_slug[m["slug"]]["name"], "folder-sheets-other-denomination",
        f"{m['folder']}/{m['commune_folder']}: its sheets carry the number {', '.join(m['carries'])} "
        f"({', '.join(m['carries_records'])}), not the record's {m['own']}",
        evidence=m, route="question for INAO: a plan filed under another denomination")
        for m in misfiled if not args.only or m["slug"] in args.only]
    aire_counts: Counter = Counter()
    contexts: dict[str, RecordContext] = {}
    for r in records:
        slug = r["slug"]
        if args.only and slug not in args.only:
            continue
        b = build.get(slug, {})
        geom = b.get("geom_source") or ""
        is_dgc = bool(r.get("is_sub_denomination"))
        hint = cahier_insee(r, commune_idx)
        inv_key = match.by_slug.get(slug, (None,))[0]
        inv = inventory.get(inv_key) if inv_key else None
        parent = by_slug.get(r.get("parent_slug") or "")
        own_rows = A.lookup(aires, r["name"], hint) or set()
        if is_dgc:
            parent_rows = (A.lookup(aires, r.get("parent_name") or "", hint) or set()) if parent else set()
            if own_rows and own_rows == parent_rows:
                own_rows = set()
            rows_raw = own_rows or parent_rows
        else:
            rows_raw = own_rows
        elsewhere = set(FC.resolve(set(rows_raw), insee_idx, former).elsewhere) if rows_raw else set()
        rows_raw = set(rows_raw) - elsewhere
        aire = fold(rows_raw)
        if is_dgc:
            coverage = fold(cov_denom.get(str(r.get("id_denomination_geo") or ""), ()))
            coverage_old = fold(old_denom.get(str(r.get("id_denomination_geo") or ""), ()))
        else:
            coverage = fold(cov.communes_for_app(r["name"]))
            coverage_old = fold(old_app.get(r["name"], ()))
        drawn: set[str] = set()
        table_source = (table.get(slug) or {}).get("source", "")
        if geom == "aires-csv":
            drawn = fold(PI.communes_for(slug)) if table_source else aire
        elif geom == "aires-csv-dgc":
            drawn = aire if own_rows else set()
        elif geom == "dgc-village-override":
            drawn = fold(DGC_VILLAGE_INSEE.get(str(r.get("id_denomination_geo") or ""), ()))
        elif geom == "communes":
            drawn = fold(hint)
        elif geom in ("parcellaire", "parcellaire-dgc"):
            drawn = coverage
        elif geom == "parent-appellation" and parent is not None:
            pg = build.get(parent["slug"], {}).get("geom_source")
            drawn = (fold(cov.communes_for_app(parent["name"])) if pg == "parcellaire"
                     else fold(A.lookup(aires, parent["name"], cahier_insee(parent, commune_idx))))
        card = ""
        if geom in ("aires-csv", "dgc-village-override", "communes"):
            card = (f"communes-{'inventory' if table_source == 'inao-plan-inventory' else 'cahier'}"
                    if table_source else (PA.parcel_area_note(slug, r.get("sections")) or ""))
        folder, fcommunes, sample = folders.get(slug, ("", None, None))
        ctx = RecordContext(
            slug=slug, name=r["name"], is_dgc=is_dgc, geom_source=geom, inv=inv,
            aire=aire, aire_own=bool(own_rows), cahier=fold(hint), coverage=coverage,
            coverage_any=digitised, coverage_old=coverage_old, drawn=drawn,
            gap_fills=fold((fills.get(slug).communes if fills.get(slug) else {}).keys()),
            folders=({canon(c): n for c, n in fcommunes.items()} if fcommunes is not None else None),
            folder=folder, card_parcel_area=card,
            own_parcel_area=PA.sets_own_parcel_area(r.get("sections")),
            parcel_area_table=table_source,
            homologated_at=((r.get("source") or {}).get("homologated_at") or ""),
            plan_dates=((sample.first, sample.last) if sample else ("", "")),
            names={c: name_of(c) for c in (aire | coverage | fold(hint) | drawn
                                             | (inv.codes() if inv else set())
                                             | {canon(c) for c in (fcommunes or {})})},
            kind=r.get("kind") or "",
            cahier_own=not is_dgc,
            aire_decided=fold(c for k in ("not_drawn", "remove")
                              for c in ((supplements.get(slug) or {}).get(k) or {})),
            gap_audit_aire=fold(A.lookup(aires, r["name"], hint)),
            name_shared=len(aires.get(A._resolve_key(aires, r["name"]) or "", {})) if own_rows else 0,
        )
        contexts[slug] = ctx
        if inv is None:
            continue
        # the codes the sources dispute and the commune list stage 02 read
        # does not hold: does the zone text name them? (a qualified name —
        # «Ponteilla en partie (sections …)» — never reaches the list)
        inv_codes = inv.codes()
        oui = inv.codes(lambda st: st.oui)
        disputed = (inv_codes ^ aire) | (coverage - aire) | (oui - coverage)
        if geom == "dgc-village-override":
            disputed |= oui - drawn
        if disputed:
            # a name in the text counts only as a whole list item under its
            # own département: «Saint-Vérand» in the Saône-et-Loire list is
            # not Saint-Vérand (Rhône), «Communes incluses en partie» are not
            # whole communes (audit_aires_vs_cahier.classify)
            text = zone_text(r)
            if geom == "dgc-village-override":
                # a DGC's commune list is in its mentions clause, not the
                # zone section (Champagne's grand cru villages)
                text = flat(" ".join(v for v in (r.get("sections") or {}).values() if isinstance(v, str)))
            for c in disputed:
                for n in [name_of(c), *old_names.get(c, ())]:
                    if not n or n == c or not name_pattern(n).search(text):
                        continue
                    verdict, quote = _classify(text, n, c)
                    if verdict == "whole":
                        ctx.cahier_text.add(c)
                        ctx.cahier_partial.pop(c, None)
                        break
                    ctx.cahier_partial.setdefault(c, f"{verdict}: {quote}")
                # a commune of today the text names by a former commune of it
                # («Oger», Blancs-Coteaux since 2018): named in part
                if c not in ctx.cahier_text and c not in ctx.cahier_partial:
                    for prev in sorted(former.predecessors.get(c, ())):
                        pname = former.name(prev)
                        if prev != c and pname and pname != prev and name_pattern(pname).search(text):
                            ctx.cahier_partial[c] = f"named by its former commune {pname} ({prev})"
                            break
        # the plan dates of the disputed communes' own folders
        if folder and geom in ("parcellaire", "parcellaire-dgc"):
            names = folder_names.setdefault(folder, PP.commune_folder_names(portal, folder))
            by_today = {canon(c): n for c, n in names.items()}
            for c in ((oui - coverage) | (coverage - aire - ctx.any_cahier)) & set(by_today):
                got = PP.commune_plan_dates(portal, folder, by_today[c])
                if got:
                    ctx.commune_plans[c] = got
        for fn in (check_parcellaire, check_commune_union, check_plans, check_dates, check_subdenomination):
            findings.extend(fn(ctx))
        f3, counts = check_aire(ctx, aire_raw=rows_raw, canon=canon, recoded=recoded)
        findings.extend(f3)
        aire_counts.update(counts)

    # ------------------------------------------------------------- report
    inv_meta = json.loads(MANIFEST.read_text(encoding="utf-8")).get("inao-plan-inventory", {}) if MANIFEST.exists() else {}
    print("# INAO delimitation-plan inventory and plans against the French corpus\n")
    print(f"inventory: {len(rows):,} rows, {len(inventory):,} appellations, last modified "
          f"{inv_meta.get('last_modified', '?')} · parcellaire: {cov.shapefile} (earlier: "
          f"{', '.join(old_releases) or 'none'}) · build: {blob_name} · plan folders: "
          f"{len(folders)} bound, {len(unbound_folders)} not · requests this run: {portal.requests}\n")
    stale_table = [s for s in table if not (_panel(s).get("geom_parcel_area") or "").startswith("communes-")]
    if stale_table:
        print(f"note: the build predates parcel_area_communes.json for {', '.join(stale_table)} — "
              "drawn here as the table says, as the next stage-04 build will\n")
    scoped = [r for r in in_scope if not args.only or r["slug"] in args.only]
    print(f"## Binding\n\n{len(scoped) - len([u for u in match.unmatched_records if not args.only or u['slug'] in args.only])} "
          f"of {len(scoped)} records bound to an inventory appellation "
          f"({', '.join(f'{k} {v}' for k, v in Counter(v[1] for s, v in match.by_slug.items() if not args.only or s in args.only).most_common())}); "
          f"{len(out_of_scope)} IG spirit records are outside the inventory (AOC and IGP only).\n")
    for u in match.unmatched_records:
        if args.only and u["slug"] not in args.only:
            continue
        print(f"- unbound record {u['slug']}: {u['reason']}")
    record_keys = {norm(r["name"]) for r in records}
    wine_like = []
    folder_keys = {PP.folder_key(d) for d in PP.appellation_dirs(portal)}
    cov_keys = {norm(a) for a in cov.by_app}
    for key in match.unmatched_inventory:
        n = key[1]
        k = norm(n)
        why = [w for w, ok in (("plan folder", k in folder_keys), ("parcellaire shapefile", k in cov_keys),
                               ("a record's name extends it or it extends one",
                                len(k) >= 8 and any(rk.startswith(k) or k.startswith(rk)
                                                    for rk in record_keys if len(rk) >= 8)))
               if ok]
        if why:
            wine_like.append((n, inventory[key], why))
    if not args.only:
        print(f"\n{len(match.unmatched_inventory)} inventory appellations bind no record; "
              f"{len(wine_like)} look like wine or spirit names:")
        for n, app, why in wine_like:
            oui = len(app.codes(lambda s: s.oui))
            print(f"- «{n}» ({app.signe}, {len(app.communes)} communes, {oui} oui) — {', '.join(why)}")
        if unbound_folders:
            print(f"\n{len(unbound_folders)} plan folder(s) bind no record: " + "; ".join(unbound_folders[:40])
                  + (" …" if len(unbound_folders) > 40 else ""))

    # The queue audit_parcellaire_gaps.py prints — aire communes with no parcel
    # row of a parcellaire record — read against the inventory: «oui, plan
    # disponible» is a delimitation the shapefile lacks, «non» an aire commune
    # with no parcel to draw (not a gap)
    gap_queue: dict[str, Counter] = {}
    gap_rows = []
    for slug, c in contexts.items():
        if c.geom_source not in ("parcellaire", "parcellaire-dgc") or c.inv is None:
            continue
        gaps = {g for g in c.gap_audit_aire if g in insee_idx} - c.coverage - c.gap_fills
        if not gaps:
            continue
        cls = Counter()
        for g in gaps:
            st = c.inv.communes.get(g)
            cls["oui, plan disponible" if st and st.oui and st.plan == "disponible"
                else "oui, en cours" if st and st.oui else "non" if st else "not listed"] += 1
        gap_queue[slug] = cls
        gap_rows.append({"slug": slug, **cls})
    if gap_queue:
        tot = sum(gap_queue.values(), Counter())
        print(f"\n## The parcellaire-gap queue against the inventory\n\n{len(gap_queue)} parcellaire records "
              f"carry {sum(tot.values())} aire commune(s) with no parcel row; the inventory marks "
              + ", ".join(f"{v} {k}" for k, v in tot.most_common())
              + ". «non» settles a gap as an aire commune with nothing to draw; «oui, plan disponible» "
                "is a delimitation the shapefile lacks (check 1a).")

    # every commune-union record with parcel communes in the inventory: the
    # share of the drawn communes that hold them (Champagne: 321 of 617)
    union_share = []
    for slug, c in contexts.items():
        if c.geom_source not in ("aires-csv", "aires-csv-dgc", "dgc-village-override", "communes") or c.inv is None:
            continue
        oui = c.inv.codes(lambda st: st.oui)
        if oui and c.drawn:
            union_share.append({"slug": slug, "drawn": len(c.drawn), "oui": len(oui & c.drawn),
                                "share": round(len(oui & c.drawn) / len(c.drawn), 3), "dgc": c.is_dgc,
                                "kind": c.kind, "table": c.parcel_area_table})
    if union_share and not args.only:
        print("\n## Commune unions with a parcel area in the inventory\n")
        print("| record | drawn | oui | share | |\n|---|---:|---:|---:|---|")
        for u in sorted(union_share, key=lambda u: u["share"]):
            print(f"| {u['slug']} | {u['drawn']} | {u['oui']} | {u['share']:.0%} | "
                  f"{'DGC ' if u['dgc'] else ''}{u['kind']}{' · ' + u['table'] if u['table'] else ''} |")

    by_bucket = Counter(f.bucket for f in findings)
    by_check = Counter((f.check, f.bucket) for f in findings)
    print("\n## Findings\n")
    print("| bucket | " + " | ".join(f"check {c}" for c in ("1a", "1b", "1c", "2a", "2b", "3", "4", "5a", "5b", "5c", "6"))
          + " | total |")
    print("|---|" + "---:|" * 12)
    for bkt in BUCKETS:
        print(f"| {bkt} | " + " | ".join(str(by_check.get((c, bkt), "")) for c in
                                          ("1a", "1b", "1c", "2a", "2b", "3", "4", "5a", "5b", "5c", "6"))
              + f" | {by_bucket.get(bkt, 0)} |")
    print(f"\naire codes that differ only by a merger or a change of code (not findings): "
          f"{aire_counts.get('merged', 0)} merged since, {aire_counts.get('code-changed', 0)} code changed; "
          f"{aire_counts.get('different', 0)} genuinely different")
    for bkt in BUCKETS:
        got = [f for f in findings if f.bucket == bkt]
        if not got:
            continue
        print(f"\n### {bkt} ({len(got)})\n")
        for f in sorted(got, key=lambda f: (f.check, f.kind, f.slug))[: None if args.all else 60]:
            names = ", ".join(f"{c['name']} ({c['insee']})" for c in f.communes[:8])
            more = f" … +{len(f.communes) - 8}" if len(f.communes) > 8 else ""
            print(f"- [{f.check} {f.kind}] **{f.slug}** — {f.summary}"
                  + (f": {names}{more}" if names else "") + (f" → {f.route}" if f.route and bkt == CONFLICT_OURS else ""))
        if not args.all and len(got) > 60:
            print(f"- … {len(got) - 60} more (--all)")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "findings": [f.to_json() for f in findings],
            "unmatched_records": match.unmatched_records,
            "out_of_scope": [r["slug"] for r in out_of_scope],
            "unmatched_inventory_wine_like": [{"name": n, "signe": a.signe, "communes": len(a.communes),
                                               "oui": len(a.codes(lambda s: s.oui)), "why": w}
                                              for n, a, w in wine_like],
            "unbound_folders": unbound_folders,
            "folders": {s: {"folder": v[0], "communes": len(v[1]), "via": folder_via.get(v[0]),
                            "sample": v[2].__dict__ if v[2] else None} for s, v in folders.items()},
            "aire_code_differences": dict(aire_counts),
            "gap_queue": gap_rows,
            "union_share": union_share,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nfindings → {args.json}", file=sys.stderr)
    return 1 if args.strict and by_bucket.get(CONFLICT_OURS) else 0


if __name__ == "__main__":
    sys.exit(main())
