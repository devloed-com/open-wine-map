#!/usr/bin/env python3
"""Audit — Bétard-fallback geometries that may post-date the source snapshot.

Every appellation whose resolved geometry comes from the Bétard 2022
`EU_PDO.gpkg` (geom_source `figshare-pdo` / `figshare-pdo-alias`) inherits that
dataset's **data snapshot**, which predates publication (CLAUDE.md: the
Nov-2021 cutoff). A GI that was *registered or amended after* the snapshot may
have a boundary the snapshot can't reflect — its map polygon could be stale (an
old perimeter) or, for a brand-new GI, only present because a same-file-number
match happened to land. This audit cross-references each Bétard-tier record's
eAmbrosia registration/amendment dates against the snapshot and buckets it:

  FLAGGED    — Bétard geometry, but the GI's latest eAmbrosia date is AFTER the
               snapshot: verify the current boundary against the polygon.
               (exit != 0 under --strict)
  REVIEWED   — slug in betard_delta_overrides.json: a curator checked the
               post-snapshot amendment did not move the boundary (cite source).
  OK         — Bétard geometry, latest date <= snapshot: contemporaneous.
  NO-DATE    — Bétard geometry but no eAmbrosia entry / no usable date (FR INAO
               records, or a slug that doesn't match the register). Listed so
               the gap is visible, never silently dropped.

The audit is read-only — it changes no geometry. It reads the compact
`wiki/data/aocs.en.*.js` startup blob (geom_source is a startup field) rather
than the multi-GB geojson, plus every `raw/<cc>/eambrosia/index.json`. Fixing a
real FLAGGED finding means re-verifying the boundary upstream (a newer Bétard
release, the regional zone layer, or a commune-list resolver) — not editing
this audit.

Usage:
  uv run scripts/audit_betard_delta.py
  uv run scripts/audit_betard_delta.py --strict          # exit!=0 on FLAGGED
  uv run scripts/audit_betard_delta.py --cutoff 2022-01-01
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "scripts" / "_lib" / "betard_delta_overrides.json"

# Bétard 2022 EU_PDO.gpkg data-snapshot cutoff (see CLAUDE.md — "the dataset's
# Nov-2021 cutoff"). A GI registered or amended after this date may carry a
# boundary the snapshot does not reflect.
BETARD_SNAPSHOT = "2021-11-01"
BETARD_SOURCES = {"figshare-pdo", "figshare-pdo-alias"}


def load_aocs() -> dict[str, dict]:
    files = sorted((ROOT / "wiki" / "data").glob("aocs.en.*.js"))
    if not files:
        sys.exit("error: wiki/data/aocs.en.*.js not found — run stage 04 first")
    txt = files[0].read_text(encoding="utf-8")
    m = re.match(r"window\.__OWM_DATA=(.*);\s*$", txt, re.S)
    if not m:
        sys.exit(f"error: could not parse {files[0].name}")
    return json.loads(m.group(1))["aocs"]


def load_eambrosia() -> dict[str, dict]:
    """slug -> eAmbrosia wine record (across every country index)."""
    out: dict[str, dict] = {}
    for idx in sorted(glob.glob(str(ROOT / "raw" / "*" / "eambrosia" / "index.json"))):
        data = json.loads(Path(idx).read_text(encoding="utf-8"))
        for wine in data.get("wines") or []:
            slug = wine.get("slug")
            if slug:
                out.setdefault(slug, wine)
    return out


def latest_date(wine: dict) -> str:
    dates = [
        (wine.get(k) or "")[:10]
        for k in ("eu_protection_date", "modification_date")
    ]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", default=BETARD_SNAPSHOT,
                    help=f"snapshot date; GIs dated after it are FLAGGED (default {BETARD_SNAPSHOT})")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any unreviewed FLAGGED finding exists")
    args = ap.parse_args()

    aocs = load_aocs()
    eam = load_eambrosia()
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}

    flagged: list[tuple] = []
    reviewed: list[tuple] = []
    ok = 0
    nodate: list[tuple] = []

    for slug, rec in aocs.items():
        if rec.get("geom_source", "") not in BETARD_SOURCES:
            continue
        wine = eam.get(slug)
        latest = latest_date(wine) if wine else ""
        if not latest:
            nodate.append((slug, rec.get("country", ""), rec.get("name", slug)))
            continue
        if latest > args.cutoff:
            row = (slug, rec.get("country", ""), rec.get("name", slug), latest, wine)
            (reviewed if slug in overrides else flagged).append(row)
        else:
            ok += 1

    total = ok + len(flagged) + len(reviewed) + len(nodate)
    print(f"Bétard-fallback geometries (geom_source in {sorted(BETARD_SOURCES)}): {total}")
    print(f"  snapshot cutoff: {args.cutoff}\n")

    if flagged:
        print(f"FLAGGED — amended/registered after the snapshot ({len(flagged)}):")
        by_country: dict[str, list] = defaultdict(list)
        for slug, country, name, latest, wine in flagged:
            by_country[country].append((latest, slug, name, wine))
        for country in sorted(by_country):
            print(f"  [{country}]")
            for latest, slug, name, wine in sorted(by_country[country], reverse=True):
                reg = (wine.get("eu_protection_date") or "")[:10] or "?"
                mod = (wine.get("modification_date") or "")[:10] or "—"
                print(f"    {slug:<40} {name[:34]:<34} reg={reg} mod={mod}")
        print()

    if reviewed:
        print(f"REVIEWED — post-snapshot but curator-confirmed OK ({len(reviewed)}):")
        for slug, country, name, latest, _ in sorted(reviewed):
            note = overrides.get(slug, {})
            print(f"    {slug:<40} [{country}] {note.get('reason', '')}")
        print()

    if nodate:
        print(f"NO-DATE — Bétard geometry, no eAmbrosia date ({len(nodate)}):")
        for slug, country, name in sorted(nodate):
            print(f"    {slug:<40} [{country}] {name[:40]}")
        print()

    print(f"summary: OK={ok}  FLAGGED={len(flagged)}  REVIEWED={len(reviewed)}  NO-DATE={len(nodate)}")
    if args.strict and flagged:
        print(f"\n--strict: {len(flagged)} unreviewed FLAGGED finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
