"""French aires: the communes the cahier lists against INAO's commune rows.

The cahier des charges is the delimitation; INAO's aires-communes CSV is a
publication of it and can lag it, be cut short or carry a neighbouring code
(Cassis de Saintonge: 36 rows for some four hundred communes; Marc des Côtes
du Rhône: Gignac for Gigondas). For every French parent that binds an aire of
the CSV and whose cahier lists communes, this audit reads the zone section of
the cahier in the build and reports

- **cahier-only**: communes the cahier names that the rows (with the pins of
  `scripts/_lib/aires_supplements.json`) lack, each classed by its place in
  the text — `whole` (an item of a commune list under its département),
  `partial` (the cahier includes it in part: a qualifier in brackets, an "en
  partie" sub-list), `unclear` (a canton or arrondissement heading, a name the
  list reader took from prose, another département's heading above it);
- **rows-only** (report only): communes of the rows whose name the zone text
  does not carry — a commune nouvelle the cahier lists by its former communes,
  a neighbouring code in the rows, or a whole canton the cahier names; read
  the text before concluding anything.

Buckets: OK, PINNED (every whole commune is pinned), NEW (whole communes not
pinned — pin them once the cahier is confirmed the newest published, with the
quote), UNCLEAR. A detector: it changes no polygon. `--emit-pins PATH` writes
the `whole` / `partial` findings in the pin table's shape for review.

    .venv/bin/python scripts/audit_aires_vs_cahier.py --drinks
    .venv/bin/python scripts/audit_aires_vs_cahier.py --only calvados-spiritueux --json tmp/validation/aires-vs-cahier.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import aires as A  # noqa: E402
from _lib.fr import former_communes as FC  # noqa: E402
from _lib.fr.seat_communes import flat as _flat  # noqa: E402
from _lib.fr.seat_communes import name_pattern as _name_pattern  # noqa: E402
from _lib.geom_chain import (  # noqa: E402
    cahier_insee,
    dept_code_for,
    load_commune_index,
    written_names,
)

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
COMMUNES = ROOT / "raw" / "ign" / "communes.geojson"

_DEPT_HEAD_RE = re.compile(
    r"(?i)d[ée]partements?\s+(?:du\s+|de\s+la\s+|de\s+l['’]\s*|des\s+|de\s+|d['’]\s*)"
    r"([A-ZÀ-Ÿ][\wÀ-ÿ'’-]*(?:[ \t-]+[A-ZÀ-Ÿ][\wÀ-ÿ'’-]*)*)"
)
_PARTIAL_MODE_RE = re.compile(
    r"(?i)communes?\s+(?:incluses?\s+|retenues?\s+|comprises?\s+|situ[ée]es?\s+)?(?:en|pour)\s+(totalit[ée]|partie)"
    r"|communes?\s+(enti[èe]res?|partielles?)\b|parties?\s+de\s+communes?"
)
_PARTIAL_QUALIFIER_RE = re.compile(
    r"(?i)partie|section|pour\s+le\s+seul|uniquement|seulement|exclusion|except|lieux?-dits?|rive\b|"
    r"au\s+(?:nord|sud)|[àa]\s+l['’](?:est|ouest)|parcelles?"
)
# "… sur le territoire de ces communes, en dehors de Losse, Mont-de-Marsan, …"
# (Armagnac: listed for the ageing, excluded from the vineyard and the still)
_EXCLUSION_CLAUSE_RE = re.compile(
    r"(?i)(?:en dehors d|a l'exception d|a l'exclusion d|\bhormis\b|\bexcepte)[^.]{0,500}"
)
_HEADING_BEFORE_RE = re.compile(r"(?i)(?:cantons?|arrondissements?)\s+(?:de\s+|d['’]\s*|du\s+|des\s+)?(?:la\s+|le\s+|les\s+)?$")


# An unread list of this many names fails --strict: under it the record is a
# sentence-form mention the reader took for a list (Cassis de Dijon's « Dijon,
# dans le département de la Côte d'Or »), reported with --all.
UNREAD_MIN_NAMES = 5


def _dept_code_of(heading: str) -> str | None:
    return dept_code_for(heading.strip())


def classify(zone: str, name: str, code: str) -> tuple[str, str]:
    """(`whole` | `partial` | `unclear`, the evidence) for one commune name in
    the zone text (already `_flat`)."""
    best: tuple[str, str] | None = None
    for m in _name_pattern(name).finditer(zone):
        before, after = zone[max(0, m.start() - 70): m.start()], zone[m.end(): m.end() + 110]
        quote = re.sub(r"\s+", " ", zone[max(0, m.start() - 45): m.end() + 60]).strip()
        heads = list(_DEPT_HEAD_RE.finditer(zone[: m.start()]))
        dept = _dept_code_of(heads[-1].group(1)) if heads else None
        article = re.search(r"(?i)(?:\b(?:les|le|la)\s+|\bl')$", before)
        if dept is not None and not code.startswith(dept):
            verdict = ("unclear", f"under the heading of département {dept}: … {quote} …")
        elif article and not _flat(name).lower().startswith(article.group(0).strip().lower()):
            # "Les Salles" is not Salles
            verdict = ("unclear", f"the text reads another name: … {quote} …")
        elif _HEADING_BEFORE_RE.search(before) or re.match(r"\s*:", after):
            verdict = ("unclear", f"a canton or list heading: … {quote} …")
        else:
            qual = re.match(r"\s*\(([^)]{0,200})\)", after)
            modes = [x for x in _PARTIAL_MODE_RE.finditer(zone[heads[-1].end() if heads else 0: m.start()])]
            mode = (modes[-1].group(0).lower() if modes else "")
            if qual and _PARTIAL_QUALIFIER_RE.search(qual.group(1)):
                verdict = ("partial", f"({qual.group(1).strip()})")
            elif "partie" in mode or "partiel" in mode:
                verdict = ("partial", f"under « {modes[-1].group(0).strip()} »")
            elif re.search(r"[,:;]\s*$|\bet\s+$|^\s*$", before[-6:]) or re.match(r"\s*(?:[,;.]|et\s)", after):
                verdict = ("whole", f"… {quote} …")
            else:
                verdict = ("unclear", f"not a list item: … {quote} …")
        if best is None or (verdict[0] == "whole" and best[0] != "whole"):
            best = verdict
    return best or ("unclear", "name not found in the zone text")


def audit(only: set[str] | None, drinks_only: bool, bare_rows: bool = False) -> list[dict]:
    commune_idx, insee_idx, insee_name = load_commune_index(COMMUNES, FC.FORMER_GEOJSON, FC.MOVEMENTS_CSV)
    former = FC.load(insee_idx, log=False)
    chef = {}
    if FC.FORMER_GEOJSON.exists():
        chef = {f["properties"]["code"]: f["properties"]["chefLieu"]
                for f in json.loads(FC.FORMER_GEOJSON.read_text(encoding="utf-8"))["features"]}

    def canon(code: str) -> str:
        return code if code in insee_idx else (former.successor.get(code) or chef.get(code) or code)

    def label(code: str) -> str:
        return insee_name.get(code) or former.name(code)

    # the name a commune of today had (INSEE's rename rows): a cahier older
    # than the change lists « Saint-Ouen » for Saint-Ouen-la-Thène
    old_names: dict[str, list[str]] = {}
    for code, name in FC.former_names(insee_idx):
        old_names.setdefault(code, []).append(name)

    recs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(EXTRACTED.glob("*.json")) if not p.name.startswith("_")]
    A.register_product_names(
        sorted({r["name"] for r in recs if r.get("product_class") == "spirit"}),
        sorted({r["name"] for r in recs if not r.get("product_class")}),
    )
    bare, full = A.load_aires(supplements=False), A.load_aires()
    pins = A.load_aire_supplements()
    out = []
    for rec in recs:
        if rec.get("is_sub_denomination") or (drinks_only and not rec.get("product_class")):
            continue
        if only and rec["slug"] not in only:
            continue
        hint = cahier_insee(rec, commune_idx)
        key = A._resolve_key(bare, rec["name"])
        listed = sum(len(v) for v in ((rec.get("aire") or {}).get("aire_geographique") or {}).values())
        if key and listed and not hint:
            # a list none of whose names resolves is a reader gap, not an
            # empty aire: said, never skipped (Marc d'Auvergne's 88 communes
            # under « Puy-deDôme » were, until 2026-11-13)
            by = (rec.get("aire") or {}).get("aire_geographique") or {}
            out.append({"slug": rec["slug"], "name": rec["name"], "aire_key": key, "idas": sorted(bare[key]),
                        "ida": "", "homologated_at": (rec.get("source") or {}).get("homologated_at"),
                        "cahier_communes": 0, "rows": len(A.lookup(full, rec["name"], None) or ()),
                        "pinned": [], "dead_codes": [], "whole": {}, "partial": {}, "unclear": {},
                        "rows_only": [], "neighbours": {}, "bucket": "UNREAD",
                        "unread": {k: len(v) for k, v in by.items()}})
            continue
        if not hint or not key:
            continue
        rows = A.lookup(bare if bare_rows else full, rec["name"], hint) or set()
        # the aire of the label the cahier's communes overlap most
        ida = max(bare[key], key=lambda i: len({canon(c) for c in bare[key][i]} & {canon(c) for c in hint}))
        zone_raw = (rec.get("section_roles") or {}).get("aire") or ""
        if not isinstance(zone_raw, str) or not zone_raw:
            zone_raw = (rec.get("sections") or {}).get("IV") or ""
        zone = _flat(re.split(r"(?i)proximit[ée]\s+imm[ée]diate", zone_raw)[0])
        # page furniture inside a list: the page number, the BO running header
        zone = re.sub(r"(?m)^[ \t\x0c]*(?:\d{1,3}(?:[ \t]*/[ \t]*\d{1,3})?|Publie a[ui] BO[^\n]*)[ \t]*$", "", zone)
        zone = zone.replace("\x0c", "")
        exclusions = [m.group(0) for m in _EXCLUSION_CLAUSE_RE.finditer(zone)]
        # INAO's table keeps the code a commune lost when it passed to another
        # département (Chassieu, 38088, of the Rhône since 1967): not a row of
        # the aire, and stage 04 draws none of it
        dead = sorted(FC.resolve(set(rows), insee_idx, former).elsewhere)
        rows = rows - set(dead)
        c_rows = {canon(c) for c in rows}
        row = {"slug": rec["slug"], "name": rec["name"], "aire_key": key,
               "dead_codes": [f"{c} {former.name(c)}" for c in dead],
               "idas": sorted(bare[key]), "ida": ida,
               "homologated_at": (rec.get("source") or {}).get("homologated_at"),
               "cahier_communes": len(hint), "rows": len(rows),
               "pinned": sorted(c for k in ("communes", "not_drawn", "remove")
                                 for c in (pins.get(rec["slug"]) or {}).get(k, {})),
               "whole": {}, "partial": {}, "unclear": {}, "rows_only": [], "neighbours": {}}
        decided = set() if bare_rows else set((pins.get(rec["slug"]) or {}).get("not_drawn", {}))
        for code in sorted(hint):
            if canon(code) in c_rows or code in rows or code in decided:
                continue
            verdict, evidence = classify(zone, label(code), code)
            if evidence.startswith("name not found"):
                # the name the commune had, or the one this cahier writes for
                # it (commune_name_pins.json)
                for old in [*old_names.get(code, ()), *written_names(rec, label(code))]:
                    v, e = classify(zone, old, code)
                    if not e.startswith("name not found"):
                        verdict, evidence = v, f"as « {old} »: {e}"
                        break
            if verdict == "whole":
                for clause in exclusions:
                    if _name_pattern(label(code)).search(clause):
                        verdict = "partial"
                        evidence = "named in an exclusion: « " + re.sub(r"\s+", " ", clause)[:140] + " … »"
                        break
            if evidence.startswith("name not found") and code in insee_idx:
                # a commune of today the cahier lists by its former communes:
                # whole when every one of them is named
                preds = sorted(former.predecessors.get(code, ()))
                named = [c for c in preds if _name_pattern(former.name(c)).search(zone)]
                if preds and len(named) == len(preds):
                    verdict = "whole"
                    evidence = ("every former commune of it is listed: "
                                + ", ".join(former.name(c) for c in preds))
                elif preds:
                    verdict = "unclear"
                    evidence = ("the cahier lists " + ", ".join(former.name(c) for c in named)
                                + " and not " + ", ".join(former.name(c) for c in preds if c not in named))
            row[verdict][code] = {"name": label(code), "evidence": evidence,
                                  **({"former": True} if code not in insee_idx else {})}
        c_hint = {canon(c) for c in hint}
        for code in sorted(rows):
            if canon(code) in c_hint:
                continue
            if not any(_name_pattern(re.sub(r"\s*\(.*\)$", "", n)).search(zone)
                       for n in [label(code), *old_names.get(code, ())]):
                # a commune of today whose former communes the cahier names
                if any(_name_pattern(former.name(p)).search(zone)
                       for p in former.predecessors.get(code, ()) if p != code):
                    continue
                row["rows_only"].append(f"{code} {label(code)}")
                # a row one or two codes away from a commune the cahier lists
                # and the rows lack: INAO's file carries the neighbouring code
                for other in row["whole"]:
                    if other[:2] == code[:2] and other[2:].isdigit() and code[2:].isdigit() \
                            and 0 < abs(int(other[2:]) - int(code[2:])) <= 2:
                        row["neighbours"][code] = {"name": label(code), "for": other,
                                                   "for_name": row["whole"][other]["name"]}
        row["bucket"] = ("NEW" if row["whole"] else "UNCLEAR" if row["unclear"] or row["partial"]
                         else "PINNED" if row["pinned"] else "OK")
        out.append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", action="append", default=[], help="record slug (repeatable)")
    ap.add_argument("--drinks", action="store_true", help="spirits, ciders and aromatised wines only")
    ap.add_argument("--json", type=Path, help="write every row")
    ap.add_argument("--emit-pins", type=Path, help="write the whole / partial findings in the pin table's shape")
    ap.add_argument("--all", action="store_true", help="list the OK and PINNED records too")
    ap.add_argument("--bare", action="store_true",
                    help="compare with INAO's rows alone, the pins left out (to rebuild a pin)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on a NEW or UNCLEAR record (use with --drinks: the wines are a curator queue)")
    args = ap.parse_args()
    rows = audit(set(args.only) or None, args.drinks, bare_rows=args.bare)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
        if r["bucket"] in ("OK", "PINNED") and not args.all:
            continue
        if r["bucket"] == "UNREAD" and not args.all and sum(r["unread"].values()) < UNREAD_MIN_NAMES:
            continue
        print(f"{r['bucket']:<8} {r['slug']}  (cahier {r['homologated_at'] or 'undated'}: "
              f"{r['cahier_communes']} communes; rows {r['rows']}, IDA {', '.join(r['idas'])})")
        if r["bucket"] == "UNREAD":
            print("    the record lists names under headings that are no département, none resolves: "
                  + "; ".join(f"« {k} » {n}" for k, n in r["unread"].items()))
        for kind in ("whole", "partial", "unclear"):
            for code, item in r[kind].items():
                print(f"    {kind:<8} {code} {item['name']}{' (former commune)' if item.get('former') else ''}"
                      f" — {item['evidence'][:150]}")
        for code, item in r["neighbours"].items():
            print(f"    row {code} {item['name']} stands where the cahier lists {item['for']} {item['for_name']}")
        if r["dead_codes"]:
            print(f"    codes of communes that left the département before the cahiers, not drawn "
                  f"({len(r['dead_codes'])}): " + "; ".join(r["dead_codes"][:6])
                  + (" …" if len(r["dead_codes"]) > 6 else ""))
        if r["rows_only"]:
            shown = "; ".join(r["rows_only"][:10])
            print(f"    rows only, name not in the zone text ({len(r['rows_only'])}): {shown}"
                  f"{' …' if len(r['rows_only']) > 10 else ''}")
    dead = [r["slug"] for r in rows if r["dead_codes"]]
    if dead:
        print(f"codes of communes that left the département before the cahiers: {len(dead)} record(s) "
              f"({', '.join(dead[:8])}{' …' if len(dead) > 8 else ''}) — not drawn, see --all")
    print("summary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" of {len(rows)} records")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.emit_pins:
        staged = {
            r["slug"]: {
                "aire_key": r["aire_key"], "ida": r["ida"], "rows": r["rows"],
                "homologated_at": r["homologated_at"],
                "communes": {c: i["name"] for c, i in r["whole"].items()},
                "remove": {c: i for c, i in r["neighbours"].items()},
                "not_drawn": {c: f"{i['name']} — the cahier includes it in part {i['evidence']}; not drawn."
                              for c, i in r["partial"].items()},
                "evidence": {c: i["evidence"] for c, i in r["whole"].items()},
            }
            for r in rows if r["whole"] or r["partial"]
        }
        args.emit_pins.parent.mkdir(parents=True, exist_ok=True)
        args.emit_pins.write_text(json.dumps(staged, ensure_ascii=False, indent=1), encoding="utf-8")
    unread = [r for r in rows if r["bucket"] == "UNREAD" and sum(r["unread"].values()) >= UNREAD_MIN_NAMES]
    if args.strict and (counts.get("NEW") or counts.get("UNCLEAR") or unread):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
