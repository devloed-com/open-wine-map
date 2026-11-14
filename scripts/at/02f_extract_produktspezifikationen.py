"""Extract the BML Produktspezifikation roster and terroir text (Austria).

Pipeline stage 02f (at) — the AT sibling of scripts/de/02f_extract_produktspezifikation.py.
Reads the PDFs stage 01c fetched, parses each with
scripts/_lib/at/produktspezifikation.py and writes one sidecar per wine that
stage 04 merges into the in-memory record (scripts/_lib/augment/at.py) and
stage 02d reads as the terroir source where the EU single document's link
text is short (Oberösterreich).

Roles. The specification's section f) decides, in this order:
  - a "Hauptsorten … sind …" sentence (Wachau, Wien, Burgenland, Niederösterreich,
    Steiermark): the named varieties are principal, the rest of the roster
    accessory (`role_rule: hauptsorten`);
  - the national roster without that sentence (the Bundesland designations,
    the three Landwein PGIs — 35 varieties in two colour blocks, Wiener
    Gemischter Satz's white half): every variety accessory — the EU single
    document's § 7 "Wichtigste Keltertraubensorten" is the principal list,
    which the augmenter keeps (`role_rule: national-roster`);
  - a closed list of named varieties (Kamptal's five, Thermenregion's ten,
    Rosalia's two): every variety principal, as the EU document lists them
    (`role_rule: exclusive-list`);
  - an open reference only ("Alle weißen Qualitätsweinrebsorten", Ruster
    Ausbruch): no roster, the EU document's stays (`role_rule: open`).

Reads:
  raw/at/produktspezifikationen/<slug>.pdf + manifest.json
Writes:
  raw/at/produktspezifikationen-extracted/<slug>.json
  raw/at/produktspezifikationen-extracted/_index.json + manifest.json
  raw/at/extraction-unknowns-produktspezifikation.json  (roster names the lexicon lacks)

  .venv/bin/python scripts/at/02f_extract_produktspezifikationen.py --slug wachau
  .venv/bin/python scripts/at/02f_extract_produktspezifikationen.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.at.produktspezifikation import (  # noqa: E402
    LICENSE,
    PARSER_TEMPLATE,
    ROSTER_COLOURS,
    SOURCE_ORG,
    extract,
)
from _lib.extract_index import write_index  # noqa: E402

PDF_DIR = ROOT / "raw" / "at" / "produktspezifikationen"
MANIFEST = PDF_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "at" / "produktspezifikationen-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
UNKNOWNS = ROOT / "raw" / "at" / "extraction-unknowns-produktspezifikation.json"


def assign_roles(grapes: dict) -> tuple[list[dict], str]:
    """The sidecar's variety list with a role each, and the rule that set it
    (see the module docstring)."""
    roster = grapes.get("roster") or []
    hauptsorten = set(grapes.get("hauptsorten") or [])
    kind = grapes.get("roster_kind") or "empty"
    if not roster:
        return [], "open" if kind == "open" else "empty"
    if hauptsorten:
        rule = "hauptsorten"
    elif kind == "national-roster":
        rule = "national-roster"
    else:
        rule = "exclusive-list"
    out: list[dict] = []
    for v in roster:
        if rule == "hauptsorten":
            role = "principal" if v["slug"] in hauptsorten else "accessory"
        elif rule == "national-roster":
            role = "accessory"
        else:
            role = "principal"
        out.append({
            "slug": v["slug"],
            "name": v["name"],
            "colour": v.get("colour") or ROSTER_COLOURS.get(v["slug"], ""),
            "role": role,
        })
    return out, rule


def build_sidecar(slug: str, meta: dict, parsed: dict) -> dict:
    grapes, rule = assign_roles(parsed["grapes"])
    return {
        "country": "at",
        "slug": slug,
        "display": meta.get("display") or parsed.get("name") or slug,
        "parser_template": PARSER_TEMPLATE,
        "role_rule": rule,
        "roster_kind": parsed["grapes"].get("roster_kind"),
        "n_total": len(grapes),
        "n_principal": sum(1 for g in grapes if g["role"] == "principal"),
        "n_accessory": sum(1 for g in grapes if g["role"] == "accessory"),
        "grapes": grapes,
        "hauptsorten": parsed["grapes"].get("hauptsorten") or [],
        "tiers": parsed["grapes"].get("tiers") or {},
        "open_roster_clauses": parsed["grapes"].get("open_roster_clauses") or [],
        "unmatched_names": parsed["grapes"].get("unmatched") or [],
        # the wine colours sections b) and g) state, each with its sentence
        # (stage 04 completes the EU document's colour list with them)
        "styles_stated": sorted(parsed.get("styles_stated") or {}),
        "styles_evidence": parsed.get("styles_stated") or {},
        "section_letters": parsed.get("section_letters") or {},
        "sections_found": parsed.get("sections_found") or [],
        "zusammenhang_text": parsed.get("zusammenhang_text") or "",
        "geo_area_text": parsed.get("geo_area_text") or "",
        "description_text": parsed.get("description_text") or "",
        "source": {
            "kind": "bml-produktspezifikation",
            "url": meta.get("url", ""),
            "filename": meta.get("filename", ""),
            "sha256": meta.get("sha256", ""),
            "bytes": meta.get("bytes", 0),
            "fetched_at": meta.get("fetched_at", ""),
            "source_org": SOURCE_ORG,
            "license": LICENSE,
            "alternates": meta.get("alternates") or [],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", action="append", default=[], help="one slug (repeatable)")
    ap.add_argument("--all", action="store_true", help="every PDF in the manifest")
    args = ap.parse_args()
    if not MANIFEST.exists():
        print(f"error: {MANIFEST} missing — run scripts/at/01c_fetch_produktspezifikationen.py",
              file=sys.stderr)
        return 1
    by_slug = json.loads(MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
    slugs = list(args.slug) if args.slug else (sorted(by_slug) if args.all else [])
    if not slugs:
        print("error: pass --all or --slug SLUG", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    unknowns: dict[str, list[str]] = {}
    n_ok = n_skip = 0
    for slug in slugs:
        meta = by_slug.get(slug)
        pdf = PDF_DIR / f"{slug}.pdf"
        if not meta or not pdf.exists():
            print(f"  {slug}: no PDF in the manifest", file=sys.stderr)
            n_skip += 1
            continue
        try:
            parsed = extract(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"  {slug}: parse error: {exc}", file=sys.stderr)
            n_skip += 1
            continue
        if "grapes" not in parsed["sections_found"]:
            print(f"  {slug}: no section f) found ({parsed['sections_found']}); skipping", file=sys.stderr)
            n_skip += 1
            continue
        sidecar = build_sidecar(slug, meta, parsed)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        if sidecar["unmatched_names"]:
            unknowns[slug] = sidecar["unmatched_names"]
        index[slug] = {
            "slug": slug,
            "role_rule": sidecar["role_rule"],
            "n_total": sidecar["n_total"],
            "n_principal": sidecar["n_principal"],
            "n_accessory": sidecar["n_accessory"],
            "n_unmatched": len(sidecar["unmatched_names"]),
            "link_chars": len(sidecar["zusammenhang_text"]),
        }
        print(f"  {slug:24} {sidecar['role_rule']:16} total={sidecar['n_total']:2} "
              f"principal={sidecar['n_principal']:2} accessory={sidecar['n_accessory']:2} "
              f"link={len(sidecar['zusammenhang_text'])}"
              + (f" unmatched={sidecar['unmatched_names']}" if sidecar["unmatched_names"] else ""),
              file=sys.stderr)
        n_ok += 1

    write_index(OUT_INDEX, index, partial=bool(args.slug))
    OUT_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_org": SOURCE_ORG,
        "license": LICENSE,
        "parser_template": PARSER_TEMPLATE,
        "n_extracted": n_ok,
        "n_skipped": n_skip,
        "by_slug": index,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if unknowns or UNKNOWNS.exists():
        UNKNOWNS.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "roster names of section f) the grape lexicon does not resolve, per slug",
            "by_slug": unknowns,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[02f/at] extracted={n_ok} skipped={n_skip} → {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
