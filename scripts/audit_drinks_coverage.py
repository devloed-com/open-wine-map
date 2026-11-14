#!/usr/bin/env python3
"""Coverage of the spirit drinks, aromatised wines and ciders: the EU GI
register against the corpus, country by country, and the geometry of every
record of the drinks pipeline.

Reads the cached register listing (raw/eambrosia-register/gi-index.json),
the drinks index and extracted records (raw/drinks/), the French records
(raw/inao/cahier-extracted/ with the register bindings of stage 01d) and the
stage-04 startup blob (wiki/data/aocs.en.*.js). Read-only.

Buckets, per Registered drink row of a corpus country:

  DRINKS   — a record of the drinks pipeline (scripts/drinks/)
  FR       — a record of the French pipeline (INAO's referentiel carries it)
  UK       — a United Kingdom row: the drinks pipeline reads the UK's names
             from the GOV.UK register, not from this listing
  MISSING  — in no pipeline: --strict fails

and, per record of the drinks pipeline: extracted or stub (with the reason),
link text read or not, drawn (by which source) or not. An undrawn record must
be listed with its reason in scripts/_lib/drinks/area_queue.json; a listed
record that is drawn is STALE. A register Food name that reads like a cider
or perry and is in no list is reported.

    .venv/bin/python scripts/audit_drinks_coverage.py [--strict] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import product_class as pclass_mod  # noqa: E402
from _lib.drinks import index as ix  # noqa: E402
from _lib.drinks.geometry import load_areas  # noqa: E402

GI_INDEX = ROOT / "raw" / "eambrosia-register" / "gi-index.json"
DRINKS_INDEX = ROOT / "raw" / "drinks" / "eambrosia" / "index.json"
EXTRACTED = ROOT / "raw" / "drinks" / "extracted"
FR_EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
FR_RESOLVED = ROOT / "raw" / "inao" / "register" / "resolved.json"
QUEUE_PATH = ROOT / "scripts" / "_lib" / "drinks" / "area_queue.json"

# a Food-class register name that is a cider or a perry in some language
_CIDER_WORD_RE = re.compile(
    r"\b(cidre|cider|sidra|sidro|sagardo\w*|perry|poir[ée]|apfelwein|[äa]ppelwoi|viez|most|"
    r"jabłecznik|cydr|siider|sidr\w*)\b", re.I,
)
_UK = frozenset({"gb", "uk", "uk(ni)"})


def load_blob() -> dict[str, dict]:
    files = sorted((ROOT / "wiki" / "data").glob("aocs.en.*.js"))
    if not files:
        return {}
    m = re.match(r"window\.__OWM_DATA=(.*);\s*$", files[-1].read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))["aocs"] if m else {}


def fr_records() -> tuple[dict[str, dict], set[str]]:
    """(French non-wine records by slug, the register file numbers the French
    pipeline holds)."""
    records: dict[str, dict] = {}
    ids: set[str] = set()
    if FR_EXTRACTED.exists():
        for path in FR_EXTRACTED.glob("*.json"):
            if path.name.startswith("_"):
                continue
            rec = json.loads(path.read_text(encoding="utf-8"))
            if pclass_mod.product_class(rec) != "wine" and not rec.get("is_sub_denomination"):
                records[rec.get("slug") or path.stem] = rec
                ids.add(str(rec.get("id_appellation") or ""))
    resolved = json.loads(FR_RESOLVED.read_text(encoding="utf-8")) if FR_RESOLVED.exists() else {}
    file_numbers = {v.get("file_number") for k, v in resolved.items() if k in ids and v.get("file_number")}
    return records, file_numbers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit 1 on a MISSING row, an unlisted undrawn record or a STALE queue entry")
    ap.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    args = ap.parse_args()

    if not GI_INDEX.exists() or not DRINKS_INDEX.exists():
        print("error: the register listing or the drinks index is not on disk "
              "(scripts/drinks/00_fetch_index.py)", file=sys.stderr)
        return 2
    rows = json.loads(GI_INDEX.read_text(encoding="utf-8"))
    entries = json.loads(DRINKS_INDEX.read_text(encoding="utf-8"))["drinks"]
    by_file = {e["file_number"]: e for e in entries}
    ciders = ix.load_cider_gis()
    fr_recs, fr_files = fr_records()
    blob = load_blob()
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    areas = load_areas()

    # --- the register against the pipelines ---------------------------------
    per_country: dict[str, Counter] = defaultdict(Counter)
    missing: list[dict] = []
    cider_like: list[dict] = []
    for row in rows:
        if (row.get("status") or "") != "Registered":
            continue
        pclass, _cat = pclass_mod.classify_register_row(row, set(ciders))
        file_number = row.get("fileName") or ""
        listed = ix.countries_of(row)
        name = row.get("protectedName") or ""
        if not pclass and (row.get("qualityProductType") or "") == "Food":
            # a cider is a Food-class GI: French ones are the referentiel's,
            # British ones the GOV.UK register's, the others the checked-in list's
            if file_number in fr_files or (set(listed) & _UK and _CIDER_WORD_RE.search(name)):
                pclass = "cider"
            elif _CIDER_WORD_RE.search(name) and set(listed) & set(ix.CORPUS_COUNTRIES):
                cider_like.append({"file_number": file_number, "name": name, "countries": listed})
        if not pclass:
            continue
        if set(listed) & _UK:
            per_country["gb"]["register"] += 1
            per_country["gb"]["uk"] += 1
            per_country["gb"][pclass] += 1
            continue
        owner, _aliases = ix.owner_and_aliases(row)
        if not owner:
            continue
        country = "fr" if (file_number in fr_files or listed == ["fr"]) else owner
        per_country[country]["register"] += 1
        per_country[country][pclass] += 1
        if file_number in by_file:
            per_country[country]["drinks"] += 1
        elif file_number in fr_files:
            per_country[country]["fr"] += 1
        else:
            per_country[country]["missing"] += 1
            missing.append({"file_number": file_number, "name": row.get("protectedName"), "country": country})

    # --- the records of the drinks pipeline -----------------------------------
    stubs, no_link, undrawn, flagged, stale = [], [], [], [], []
    sources: Counter = Counter()
    records: dict[str, dict] = {}
    for entry in entries:
        path = EXTRACTED / f"{entry['slug']}.json"
        rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"stub": True, "stub_reason": "not-extracted"}
        records[entry["slug"]] = rec
        country = entry["country"]
        if rec.get("stub"):
            per_country[country]["stub"] += 1
            stubs.append({"slug": entry["slug"], "country": country, "reason": rec.get("stub_reason", "")})
        else:
            per_country[country]["extracted"] += 1
            if not (rec.get("link_to_terroir") or "").strip():
                no_link.append(entry["slug"])
        built = blob.get(entry["slug"])
        if blob:
            if built:
                per_country[country]["drawn"] += 1
                sources[built.get("geom_source") or "?"] += 1
                if entry["slug"] in queue["undrawn"]:
                    stale.append(entry["slug"])
            else:
                reason = queue["undrawn"].get(entry["slug"])
                undrawn.append({"slug": entry["slug"], "country": country, "reason": reason or ""})
                if not reason:
                    flagged.append(entry["slug"])
    fr_drawn = sum(1 for slug in fr_recs if slug in blob)
    fr_undrawn = sorted(slug for slug in fr_recs if blob and slug not in blob)
    orphan_pins = sorted(slug for slug in areas if slug not in records)
    orphan_queue = sorted(slug for part in ("undrawn", "coarser_than_text") for slug in queue[part] if slug not in records)

    # --- the report ---------------------------------------------------------------
    cols = ("register", "drinks", "fr", "uk", "missing", "extracted", "stub", "drawn")
    print("Registered drink GIs of the EU register, by owner country\n")
    print(f"  {'':4}" + "".join(f"{c:>10}" for c in cols) + "   spirit / aromatised / cider")
    total: Counter = Counter()
    for country in sorted(per_country):
        c = per_country[country]
        total.update(c)
        print(f"  {country:4}" + "".join(f"{c[k]:>10}" for k in cols)
              + f"   {c['spirit']} / {c['aromatised-wine']} / {c['cider']}")
    print(f"  {'all':4}" + "".join(f"{total[k]:>10}" for k in cols)
          + f"   {total['spirit']} / {total['aromatised-wine']} / {total['cider']}")
    outside = Counter(e.get("register") for e in entries if e.get("register"))
    print(f"\n  Outside the EU listing, in the drinks pipeline: {outside.get('gov-uk', 0)} names of the GOV.UK "
          f"register (the EU rows of the `uk` column are read from there), {outside.get('ofag', 0)} of "
          "Switzerland's federal register (OFAG)")
    print(f"  French pipeline: {len(fr_recs)} non-wine parent records, {len(fr_files)} bound to a register "
          f"file number; {fr_drawn} on the map" + (f"; not drawn: {', '.join(fr_undrawn)}" if fr_undrawn else ""))
    if missing:
        print(f"\nMISSING — {len(missing)} register row(s) in no pipeline:")
        for m in missing:
            print(f"  {m['file_number']:22} {m['country']}  {m['name']}")
    if cider_like:
        print(f"\nCider-like Food names in no list ({len(cider_like)}) — add to scripts/_lib/drinks/cider_gis.json "
              "or dismiss:")
        for c in cider_like:
            print(f"  {c['file_number']:22} {','.join(c['countries'])}  {c['name']}")
    print(f"\nStubs ({len(stubs)}):")
    for s in stubs:
        print(f"  {s['slug']:42} {s['country']}  {s['reason']}")
    if no_link:
        print(f"\nNo link text read ({len(no_link)}): {', '.join(no_link)}")
    if not blob:
        print("\n(no stage-04 build on disk: the geometry part is skipped)")
    else:
        print("\nGeometry of the drinks records, by source:")
        for src, n in sources.most_common():
            print(f"  {src:24} {n}")
        print(f"  {'not drawn':24} {len(undrawn)}")
        for u in undrawn:
            mark = "QUEUED " if u["reason"] else "FLAGGED"
            print(f"    {mark} {u['slug']:40} {u['country']}  {u['reason']}")
        if stale:
            print(f"\nSTALE queue entries (the record is drawn): {', '.join(stale)}")
        print(f"\nDrawn coarser than the text ({len(queue['coarser_than_text'])}):")
        for slug, why in queue["coarser_than_text"].items():
            print(f"  {slug:32} {why}")
    if orphan_pins or orphan_queue:
        print(f"\nPins / queue entries of no record: {', '.join(orphan_pins + orphan_queue)}")

    report = {
        "per_country": {k: dict(v) for k, v in per_country.items()}, "missing": missing,
        "cider_like": cider_like, "stubs": stubs, "no_link": no_link, "sources": dict(sources),
        "undrawn": undrawn, "flagged": flagged, "stale": stale, "fr_undrawn": fr_undrawn,
        "orphan_pins": orphan_pins, "orphan_queue": orphan_queue,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = bool(missing or flagged or stale or orphan_pins or orphan_queue)
    print(f"\n{'FAIL' if failed else 'OK'}: {len(missing)} missing, {len(flagged)} undrawn and unlisted, "
          f"{len(stale)} stale, {len(orphan_pins) + len(orphan_queue)} orphan entries")
    return 1 if (args.strict and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
