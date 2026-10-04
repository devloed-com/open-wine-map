#!/usr/bin/env python3
"""INAO parcellaire gaps — aire communes the parcel layer does not cover.

For every French wine record drawn from the INAO parcellaire (parents by
appellation name, DGCs by id_denomination_geo), compare the communes of its
aire géographique (INAO aires-communes CSV, resolved exactly as stage 04
does) with the communes that carry a parcel row for it, and list the
difference with a class per commune:

  not-digitised   no parcel row for ANY appellation — the commune's
                  delimitation is not in the layer (Vaison-la-Romaine)
  other-aoc       rows for other appellations only (Visan carries Côtes du
                  Rhône parcels, no Côtes du Rhône Villages row)
  dgc-named       (mark) a DGC aire of the same appellation lists the
                  commune — the regulator names it as a producing village

and, apart, the aire codes IGN AdminExpress no longer carries (a pre-merger
code in the CSV: Coteaux-sur-Loire, Valloire-sur-Cisse) — not a gap.

Nothing here changes geometry: a regional appellation's vineless aire
commune is genuinely not on the wine map (Bourgogne: 46 of 315), and the
Alsace grand cru CSV rows list all 47 wine communes for every climat. A
gap a curator verifies against the cahier goes in
scripts/_lib/parcellaire_gap_fills.json (scripts/_lib/parcellaire_gaps.py);
this audit reports every pin as APPLIED (every pinned commune is a current
gap) or STALE (a pinned commune carries parcels again, or is not in the
aire), lists the rows carried forward from an earlier release
(scripts/_lib/parcellaire_carry_forward.json — APPLIED, or STALE when the
current release carries them again) and `--strict` exits non-zero on STALE.

    .venv/bin/python scripts/audit_parcellaire_gaps.py [--min-gaps N] [--only SLUG …]
        [--json PATH] [--strict] [--rebuild-coverage]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.aires import load_aires  # noqa: E402
from _lib.aires import lookup as lookup_aire
from _lib.geom_chain import cahier_insee, load_commune_index  # noqa: E402
from _lib.parcellaire_gaps import load_coverage, load_gap_fills, parcel_gaps  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
COMMUNES_GEOJSON = ROOT / "raw" / "ign" / "communes.geojson"


def _norm(s: str) -> str:
    from _lib.aires import _normalize

    return _normalize(s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-gaps", type=int, default=1)
    ap.add_argument("--only", action="append", default=[], help="slug (repeatable)")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on a STALE pin or a STALE carry-forward entry")
    ap.add_argument("--rebuild-coverage", action="store_true")
    args = ap.parse_args()

    cov = load_coverage(force=args.rebuild_coverage)
    if cov is None:
        sys.exit("no INAO parcellaire shapefile under raw/inao/parcellaire/")
    aires = load_aires()
    commune_idx, insee_idx, insee_name = load_commune_index(COMMUNES_GEOJSON)
    fills = load_gap_fills()

    records = []
    for path in sorted(EXTRACTED.glob("*.json")):
        if path.name == "_index.json":
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        if (r.get("country") or "fr") != "fr" or not r.get("slug"):
            continue
        if (r.get("categorie") or "").lower().startswith("vin") is False and r.get("categorie"):
            continue
        records.append(r)
    if args.only:
        records = [r for r in records if r["slug"] in set(args.only)]

    # DGC aires per parent name: every CSV aire whose name extends the
    # parent's — the `dgc-named` mark.
    dgc_named: dict[str, set[str]] = {}
    for key, idas in aires.items():
        for other, other_idas in aires.items():
            if other != key and other.startswith(key) and len(other) > len(key):
                for codes in other_idas.values():
                    dgc_named.setdefault(key, set()).update(codes)

    rows = []
    stale_pins: list[tuple[str, str]] = []
    applied_pins: list[str] = []
    for r in records:
        slug, name = r["slug"], r["name"]
        is_dgc = bool(r.get("is_sub_denomination"))
        app_name = r.get("parent_name") if is_dgc else name
        if is_dgc:
            parcel_codes = cov.communes_for_denom(app_name or "", r.get("id_denomination_geo") or "")
        else:
            parcel_codes = cov.communes_for_app(name)
        if not parcel_codes:
            continue
        aire_codes = lookup_aire(aires, name, cahier_insee(r, commune_idx)) or set()
        if not aire_codes:
            continue
        gaps, unknown = parcel_gaps(set(aire_codes), parcel_codes, insee_idx)
        pin = fills.get(slug)
        pin_state = ""
        if pin is not None:
            bad = [c for c in pin.communes if c not in gaps]
            if bad:
                pin_state = "STALE"
                for c in bad:
                    stale_pins.append((slug, f"{pin.communes[c]} ({c})"))
            else:
                pin_state = "APPLIED"
                applied_pins.append(slug)
        if len(gaps) < args.min_gaps and not pin:
            continue
        named = dgc_named.get(_norm(app_name or name), set())
        gap_rows = []
        for c in sorted(gaps, key=lambda c: insee_name.get(c, c)):
            cls = "other-aoc" if cov.has_any_row(c) else "not-digitised"
            gap_rows.append({
                "insee": c, "name": insee_name.get(c, c), "class": cls,
                "dgc_named": c in named,
                "pinned": bool(pin and c in pin.communes),
            })
        rows.append({
            "slug": slug, "name": name, "dgc": is_dgc,
            "aire": len(aire_codes), "parcels": len(parcel_codes & set(aire_codes)),
            "gaps": gap_rows, "unknown_codes": sorted(unknown), "pin": pin_state,
        })

    rows.sort(key=lambda x: (x["pin"] == "", -len([g for g in x["gaps"] if g["dgc_named"]]), len(x["gaps"]), x["slug"]))
    stale_carry = [c for c in cov.carried if c["state"] == "STALE"]
    print("# INAO parcellaire gaps — aire communes without a parcel row\n")
    print(f"layer: {cov.shapefile} · records with ≥ {args.min_gaps} gap(s): {len(rows)} · "
          f"pins: {len(applied_pins)} APPLIED, {len(stale_pins)} STALE · "
          f"carried-forward rows: {len(cov.carried) - len(stale_carry)} APPLIED, {len(stale_carry)} STALE\n")
    if cov.carried:
        print("## Rows carried forward from an earlier release (parcellaire_carry_forward.json)\n")
        for c in cov.carried:
            print(f"- **{c['state']}** {c['label']} ({c['key']}): {c['rows']} row(s) of the {c['release']} "
                  f"release — {c['reason'].split('. ')[0]}.")
        print()
    print("| record | aire | with parcels | gaps | not-digitised | other-aoc | dgc-named | pin | communes |")
    print("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for x in rows:
        g = x["gaps"]
        names = ", ".join(
            f"{'**' if gg['pinned'] else ''}{gg['name']}{'**' if gg['pinned'] else ''}"
            f"{' †' if gg['dgc_named'] else ''}" for gg in g[:14]
        ) + (" …" if len(g) > 14 else "")
        print(
            f"| {x['slug']}{' (DGC)' if x['dgc'] else ''} | {x['aire']} | {x['parcels']} | {len(g)} | "
            f"{sum(1 for gg in g if gg['class'] == 'not-digitised')} | "
            f"{sum(1 for gg in g if gg['class'] == 'other-aoc')} | "
            f"{sum(1 for gg in g if gg['dgc_named'])} | {x['pin']} | {names} |"
        )
    print("\n† listed in a DGC aire of the same appellation · **bold** = pinned in parcellaire_gap_fills.json")
    if stale_pins:
        print("\n## STALE pins\n")
        for slug, what in stale_pins:
            print(f"- {slug}: {what} — carries a parcel row now, or is not in the record's aire; re-verify")
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nrows → {args.json}", file=sys.stderr)
    return 1 if (args.strict and (stale_pins or stale_carry)) else 0


if __name__ == "__main__":
    sys.exit(main())
