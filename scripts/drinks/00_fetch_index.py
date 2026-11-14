#!/usr/bin/env python3
"""Stage 00 of the drinks pipeline: which spirit-drink, aromatised-wine and
cider GIs of the EU register the map holds.

Reads the register listing (`_lib/eambrosia_register.load_gi_rows`, one POST,
cached under raw/eambrosia-register/) and keeps the Registered rows that are
a spirit drink (Reg. (EU) 2019/787), an aromatised wine (register classes
2.21 / 2.22) or a cider of the curated `_lib/drinks/cider_gis.json`, in a
corpus country. Left to another pipeline, and listed in the manifest with the
reason: the French GIs INAO's referentiel carries (the FR stages — stage 01d's
bindings say which file numbers those are). The United Kingdom's drinks are
not read from the EU listing but from the GOV.UK register (`_lib/drinks/
uk_register.py`: the spirit-drinks register and the ciders and perries of the
food register), `register: "gov-uk"` in their entries; Switzerland's four
spirit AOPs from the curated transcription of OFAG's federal register
(`_lib/drinks/ch_register.json`), `register: "ofag"`.

A GI of several countries is one record: its owner is the first corpus
country of the file number, the others ride `country_aliases` so the sidebar
lists it under each (the Maasvallei rule).

Writes raw/drinks/eambrosia/index.json + manifest.json. Refuses a slug that
another corpus already uses.

    .venv/bin/python scripts/drinks/00_fetch_index.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import eambrosia_register as er  # noqa: E402
from _lib.drinks import index as di  # noqa: E402
from _lib.drinks import uk_register as uk  # noqa: E402

OUT_DIR = ROOT / "raw" / "drinks" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"
FR_RESOLVED = ROOT / "raw" / "inao" / "register" / "resolved.json"
NAME_PINS_PATH = ROOT / "scripts" / "_lib" / "drinks" / "name_pins.json"
CH_REGISTER_PATH = ROOT / "scripts" / "_lib" / "drinks" / "ch_register.json"
EXTRACTED_OWN = ROOT / "raw" / "drinks" / "extracted"


def fr_owned_file_numbers() -> set[str]:
    """The register file numbers bound to an INAO appellation (stage 01d)."""
    if not FR_RESOLVED.exists():
        print(f"[warn] {FR_RESOLVED.relative_to(ROOT)} missing — run scripts/01d_resolve_register.py; "
              "every French register row is left to the FR stages by its country alone",
              file=sys.stderr)
        return set()
    data = json.loads(FR_RESOLVED.read_text(encoding="utf-8"))
    return {v.get("file_number") for v in data.values() if v.get("file_number")}


def other_corpus_slugs() -> dict[str, str]:
    """slug → the extracted directory that holds it, over every other corpus."""
    out: dict[str, str] = {}
    for index_path in sorted((ROOT / "raw").glob("*/*-extracted/_index.json")):
        if index_path.parent == EXTRACTED_OWN:
            continue
        for json_path in index_path.parent.glob("*.json"):
            if json_path.name != "_index.json":
                out.setdefault(json_path.stem, str(index_path.parent.relative_to(ROOT)))
    return out


def apply_name_pins(entries: list[dict]) -> None:
    """A multi-country GI whose first registered alias is not in its owner's
    language takes the alias that is (`name_pins.json`: file number → the
    alias, which must be one of the registered ones)."""
    if not NAME_PINS_PATH.exists():
        return
    pins = {k: v for k, v in json.loads(NAME_PINS_PATH.read_text(encoding="utf-8")).items()
            if not k.startswith("_")}
    by_file = {e["file_number"]: e for e in entries}
    for file_number, pin in pins.items():
        entry = by_file.get(file_number)
        if entry is None:
            print(f"[name-pin] STALE {file_number}: not in the index", file=sys.stderr)
            continue
        want = pin["name"]
        aliases = di.aliases_of(entry["registered_name"])
        if want not in aliases:
            print(f"[name-pin] STALE {file_number}: {want!r} is not a registered alias "
                  f"({aliases})", file=sys.stderr)
            continue
        entry["name_aliases"] = [a for a in aliases if a not in (want, entry["name_latin"])]
        entry["name"] = want
        entry["slug"] = di.record_slug(entry)


def fetch_uk_boundaries(refresh: bool = False) -> dict:
    """The ONS units the UK area pins name (`uk:country:…` / `uk:county:…` of
    scripts/_lib/drinks/areas.json), into raw/drinks/ons/: fetched when a
    named unit is not in the cached layer."""
    import hashlib

    import requests
    from _lib.drinks.geometry import ONS_DIR, load_areas

    wanted: dict[str, set[str]] = {"countries.geojson": set(), "counties.geojson": set()}
    for pin in load_areas().values():
        for unit in pin.get("units") or []:
            unit = unit.removeprefix("minus:")
            if unit.startswith("uk:"):
                _, level, name = unit.split(":", 2)
                wanted["countries.geojson" if level == "country" else "counties.geojson"].add(
                    name.partition("=")[0]
                )
    ONS_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}
    for filename, names in wanted.items():
        if not names:
            continue
        path = ONS_DIR / filename
        have: set[str] = set()
        if path.exists() and not refresh:
            have = {next((v for k, v in f["properties"].items() if k.endswith("NM")), "")
                    for f in json.loads(path.read_text(encoding="utf-8")).get("features") or []}
        if not names <= have:
            fc = uk.fetch_boundaries(requests.Session(), filename, sorted(names))
            got = {next((v for k, v in f["properties"].items() if k.endswith("NM")), "")
                   for f in fc.get("features") or []}
            for missing in sorted(names - got):
                print(f"[ons] {filename}: no unit named {missing!r}", file=sys.stderr)
            path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        data = path.read_bytes()
        report[filename] = {"service": uk.ONS_LAYERS[filename][0], "names": sorted(names),
                            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                            "license": uk.ONS_LICENSE}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch the register listing")
    ap.add_argument("--no-uk", action="store_true",
                    help="keep the United Kingdom's entries of the index on disk instead of "
                         "reading the GOV.UK register (offline run)")
    args = ap.parse_args()

    rows = er.load_gi_rows(refresh=args.refresh)
    ciders = di.load_cider_gis()
    entries, skipped = di.select(
        rows, cider_file_numbers=set(ciders), fr_owned_file_numbers=fr_owned_file_numbers(),
    )
    apply_name_pins(entries)

    # The United Kingdom's drinks: the GOV.UK register (the EU listing's UK
    # rows were skipped above as `uk-register`).
    uk_pending: list[dict] = []
    if args.no_uk:
        previous = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["drinks"] if INDEX_PATH.exists() else []
        uk_entries = [e for e in previous if e.get("register") == "gov-uk"]
    else:
        import requests

        uk_entries, uk_pending = uk.entries(requests.Session(), rows)
    entries += uk_entries
    # Switzerland's spirit AOPs: the curated transcription of OFAG's register
    ch_table = json.loads(CH_REGISTER_PATH.read_text(encoding="utf-8"))
    for spirit in ch_table["spirits"]:
        names = di.naming(spirit["name"])
        entries.append({
            "slug": di.record_slug(names), **names,
            "file_number": "", "id_register": None,
            "register": "ofag", "register_url": ch_table["register_url"],
            "cahier_url": spirit["cahier_url"], "resume_url": spirit.get("resume_url", ""),
            "source_lang": spirit["lang"],
            "country": "ch", "country_aliases": [],
            "product_class": "spirit", "drink_category": spirit["drink_category"],
            "register_category": "Spiritueux", "kind": "EDV", "gi_type": spirit["type"],
            "registration_date": spirit["decision"], "status": "Registered",
        })
    entries.sort(key=lambda e: (e["country"], e["slug"]))

    taken = other_corpus_slugs()
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for e in entries:
        if not e["slug"]:
            collisions.append(f"{e['file_number']}: empty slug for {e['registered_name']!r}")
        elif e["slug"] in taken:
            collisions.append(f"{e['slug']} ({e['file_number']}) is already a record of {taken[e['slug']]}")
        elif e["slug"] in seen:
            collisions.append(f"{e['slug']}: {e['file_number']} and {seen[e['slug']]}")
        seen[e["slug"]] = e["file_number"]
    if collisions:
        for line in collisions:
            print(f"[slug] {line}", file=sys.stderr)
        print("[fail] slug collision — pin a name in scripts/_lib/drinks/name_pins.json",
              file=sys.stderr)
        return 2

    listed_ciders = {e["file_number"] for e in entries if e["product_class"] == "cider"}
    for file_number in sorted(set(ciders) - listed_ciders):
        print(f"[cider] STALE {file_number}: not a Registered row of a corpus country",
              file=sys.stderr)

    ons = fetch_uk_boundaries(refresh=args.refresh) if not args.no_uk else {}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(
        json.dumps({"generated_at": now, "drinks": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = {
        "generated_at": now,
        "source_url": er.API + "/api/gi-applications/filter",
        "license": "© European Union, GI register (eAmbrosia). Reuse authorised with attribution.",
        "n_register_rows": len(rows),
        "n_drinks": len(entries),
        "by_country": dict(sorted(Counter(e["country"] for e in entries).items())),
        "by_class": dict(sorted(Counter(e["product_class"] for e in entries).items())),
        "by_category": dict(sorted(Counter(e["drink_category"] for e in entries).items())),
        "multi_country": {e["file_number"]: [e["country"], *e["country_aliases"]]
                          for e in entries if e["country_aliases"]},
        "left_to_other_pipelines": dict(sorted(Counter(s["reason"] for s in skipped).items())),
        "skipped": skipped,
        "uk_register": {
            "source_url": uk.SEARCH_URL,
            "license": "Open Government Licence v3.0 — © Crown copyright, DEFRA / GOV.UK.",
            "n": len(uk_entries),
            "not_registered": uk_pending,
            "boundaries": ons,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[done] {len(entries)} drinks ({manifest['by_class']}) in "
        f"{len(manifest['by_country'])} countries; left to other pipelines: "
        f"{manifest['left_to_other_pipelines']} -> {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
