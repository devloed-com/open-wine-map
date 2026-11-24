"""Extract the BLE Produktspezifikation variety lists + terroir text.

Pipeline stage 02f (de). DE analog of `scripts/it/02f_extract_masaf.py`
and `scripts/es/02f_extract_national_pliegos.py` — pulls the regulator's
canonical variety list from the national specification PDF, and uses the
production-rules section's per-variety thresholds to derive a principal
vs accessory split that the EU Einziges Dokument doesn't carry.

Two source categories, dispatched by the manifest's `category` field:
  - `anbaugebiet` (13 quality-wine PDOs) → `produktspezifikation.extract`,
    the four rigid section-numbered templates + §3.2 principal split.
  - `landwein` (15 Landwein g.g.A. that ship as stubs with no fetchable
    EU Einziges Dokument) → `landwein_spezifikation.extract`, a
    heterogeneous-layout lexicon scan. Landwein has no role split, so its
    sidecar lands as `section-8-flat-no-split` (all-principal) and carries
    the §-Zusammenhang terroir text the stub record otherwise lacks.

Reads:
  raw/de/produktspezifikationen/<slug>.pdf  (downloaded by stage 00 in
    a future revision; currently downloaded ad-hoc by this script)
  raw/de/produktspezifikationen/manifest.json
  raw/de/produktspezifikationen/manual_overrides.json  (curator path)
  raw/de/dokumente-extracted/<slug>.json  (the EU-document records — for
    slug existence check + producer-group metadata)

Writes:
  raw/de/produktspezifikationen-extracted/<slug>.json  (sidecar per slug)
  raw/de/produktspezifikationen-extracted/_index.json
  raw/de/produktspezifikationen-extracted/manifest.json

Roles: none. No BLE specification draws a principal / accessory line, so
every authorised variety of § 8 is listed alike (`role_split_method` is
always `section-8-flat-no-split` since 2026-11-17). The varieties § 3.2
singles out — a minimum must weight of their own, a planting share — are
kept as `raw_section_3_2_principal` for reference; they had been shown as
principal, which the card validator graded misleading.

Re-runnable per slug or in sweep mode:
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --slug mosel
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.de import area_units, ble_styles, gemarkung, gemeinde_list  # noqa: E402
from _lib.de.grape_pins import german_match  # noqa: E402
from _lib.de.landwein_spezifikation import extract as parse_landwein_pdf  # noqa: E402
from _lib.de.produktspezifikation import extract as parse_anbaugebiet_pdf  # noqa: E402
from _lib.de.produktspezifikation import pdf_to_text  # noqa: E402
from _lib.extract_index import write_index  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    exact_match,
    flush_unknowns_queue,
    is_curated_surface,
    match_variety,
    set_pliego_context,
)

# «Roter Muskateller» is another passport in Germany than in Austria
match_variety = german_match(match_variety)
exact_match = german_match(exact_match)

PDF_DIR = ROOT / "raw" / "de" / "produktspezifikationen"
MANIFEST = PDF_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
EXTRACTED_DE = ROOT / "raw" / "de" / "dokumente-extracted"
UNKNOWNS = ROOT / "raw" / "de" / "extraction-unknowns-produktspezifikation.json"


def _slug_match(name: str) -> dict | None:
    """Resolve a raw variety name to a slug via the shared grape lexicon.

    Returns {"slug": ..., "name": original_name, "colour": colour}
    or None if no match (queued for curator review)."""
    m = match_variety(name)
    if m is None:
        return None
    return {"slug": m.slug, "name": name, "colour": m.colour or ""}


_INWORD_HYPHEN = re.compile(r"(?<=[a-zäöüß])-(?=[a-zäöüß])")


def _matches(name: str) -> list[dict]:
    """The variety a roster name states — or the two it states where the
    list lost a comma: Mosel's § 8 prints "Findling Gelber Kleinberger,
    Gelber Muskateller" (2026-11-17). Tried only on a name that matched
    nothing whole, and both halves must be exact names the lexicon vouches
    for (the ES reader's rule), so a name the lexicon lacks is never cut
    into two lucky halves."""
    # A hyphen set inside a word: Badischer Landwein and Landwein Oberrhein
    # print "Blauer Spät-burgunder". The matcher split it at the hyphen and
    # read "burgunder" — a VIVC synonym of Blaufränkisch, already on the list
    # as «Blauer Limberger» — so neither card had Pinot noir (card validator,
    # 2026-11-17). The closed form is tried first; "Müller-Thurgau" and
    # "Riesling-Silvaner" have a capital after the hyphen and are untouched.
    closed = _INWORD_HYPHEN.sub("", name)
    if closed != name:
        hit = exact_match(closed)
        if hit is not None:
            return [{"slug": hit.slug, "name": closed, "colour": hit.colour or ""}]
    d = _slug_match(name)
    if d is not None:
        return [d]
    words = name.strip(" .,;:()").split()
    if len(words) < 2:
        return []
    if len(words) <= 6:
        for i in range(1, len(words)):
            left, right = " ".join(words[:i]), " ".join(words[i:])
            a, b = exact_match(left), exact_match(right)
            if (a and b and a.slug != b.slug
                    and is_curated_surface(left) and is_curated_surface(right)):
                return [{"slug": a.slug, "name": left, "colour": a.colour or ""},
                        {"slug": b.slug, "name": right, "colour": b.colour or ""}]
    # The last name of a list that ran into what follows it — the sentence
    # after the roster, a page footer: Sachsen's "… Regent, Saint Laurent ⏎ Die
    # in Anbaueignungsprüfungen angestellten Rebsorten sind ebenfalls …",
    # Hessische Bergstraße's "Blauer Zweigelt. Seite 6 von 10", Württemberg's
    # "Tauberschwarz. In diese Listen können weitere Rebsorten aufgenommen
    # werden". Neither card had the variety (card validator on Sachsen,
    # 2026-11-17). Its leading words are the name when they are an exact
    # name the lexicon vouches for and at least two words of prose follow.
    for i in range(min(4, len(words) - 2), 0, -1):
        head = " ".join(words[:i]).rstrip(".,;:")
        hit = exact_match(head)
        if hit is not None and is_curated_surface(head):
            return [{"slug": hit.slug, "name": head, "colour": hit.colour or ""}]
    return []


def _resolve_names(names: list[str], default_role: str) -> tuple[list[dict], list[str]]:
    """Resolve raw variety names → list of {slug,name,colour,role}. Returns
    (resolved, unmatched_names)."""
    resolved: list[dict] = []
    unmatched: list[str] = []
    seen_slugs: set[str] = set()
    for raw_name in names:
        hits = _matches(raw_name)
        if not hits:
            unmatched.append(raw_name)
        for d in hits:
            if d["slug"] in seen_slugs:
                continue
            seen_slugs.add(d["slug"])
            d["role"] = default_role
            resolved.append(d)
    return resolved, unmatched


def _build_record(slug: str, pdf_meta: dict, parsed: dict) -> dict:
    """Build the sidecar record for one Anbaugebiet."""
    set_pliego_context(slug)
    # Principal names from §3.2.
    principal_raw = parsed["section_3_2_principal_names"]
    # All authorised names from §8.
    all_white = parsed["section_8_white_names"]
    all_red = parsed["section_8_red_names"]

    # No role split (Boris, 2026-11-17): no BLE specification draws a
    # principal / accessory line, so every authorised variety is listed
    # alike — as the EU single documents list them. Until then the varieties
    # § 3.2 singles out (a minimum must weight of their own, a planting
    # share) were shown as principal and the rest as accessory; the card
    # validator graded that misleading with and without a disclosure line
    # (Mosel: Spätburgunder and Chardonnay accessory, and "Riesling" /
    # "Elbling" of § 3.2 read as the white variety only; Sachsen: Riesling
    # and Müller-Thurgau accessory; Baden: an artefact of wrapped rows).
    # The names § 3.2 singles out stay in the sidecar for reference
    # (`raw_section_3_2_principal`); they lead the list.
    principal_resolved, prin_unmatched = _resolve_names(principal_raw, "principal")

    all_resolved: list[dict] = list(principal_resolved)
    section_8_unmatched: list[str] = []
    role_split_method = "section-8-flat-no-split"
    for name in (*all_white, *all_red):
        hits = _matches(name)
        if not hits:
            section_8_unmatched.append(name)
        for d in hits:
            if d["slug"] in {x["slug"] for x in all_resolved}:
                continue
            d["role"] = "principal"
            all_resolved.append(d)

    n_principal = sum(1 for d in all_resolved if d["role"] == "principal")
    n_accessory = sum(1 for d in all_resolved if d["role"] == "accessory")

    return {
        "country": "de",
        "slug": slug,
        "display": pdf_meta.get("display") or slug,
        "role_split_method": role_split_method,
        "n_total": len(all_resolved),
        "n_principal": n_principal,
        "n_accessory": n_accessory,
        "grapes": all_resolved,
        "raw_section_3_2_principal": principal_raw,
        "raw_section_8_white": all_white,
        "raw_section_8_red": all_red,
        "unmatched_names": section_8_unmatched + prin_unmatched,
        # Plain-text §8/§9 "Zusammenhang mit dem geografischen Gebiet"
        # — the richer terroir narrative the BLE PDF carries. Surfaces
        # in stage 04's DE augment as the link_to_terroir source when
        # the EU Einziges Dokument is empty (Ahr, Baden, Hessische
        # Bergstraße, Rheingau, Sachsen, Saale-Unstrut).
        "zusammenhang_text": parsed.get("zusammenhang_text", ""),
        "source": {
            "kind": "ble-produktspezifikation",
            "url": pdf_meta.get("url", ""),
            "sha256": pdf_meta.get("sha256", ""),
            "bytes": pdf_meta.get("bytes", 0),
            "fetched_at": pdf_meta.get("fetched_at", ""),
            "source_org": "BLE",
            "license": "Amtliches Werk §5 UrhG",
            "note": pdf_meta.get("note", ""),
        },
    }


def _process_slug(slug: str, pdf_meta: dict) -> dict | None:
    pdf_path = PDF_DIR / f"{slug}.pdf"
    if not pdf_path.exists():
        print(f"  {slug}: no PDF at {pdf_path}", file=sys.stderr)
        return None
    # Landwein g.g.A. specs use a heterogeneous layout (variety roster at
    # §6/§7/§8, no role split) → the dedicated lexicon-scan parser; the
    # 13 Anbaugebiete use the four rigid section-numbered templates.
    parse_pdf = (
        parse_landwein_pdf
        if pdf_meta.get("category") == "landwein"
        else parse_anbaugebiet_pdf
    )
    try:
        parsed = parse_pdf(pdf_path)
    except Exception as e:  # noqa: BLE001
        print(f"  {slug}: parse error: {e}", file=sys.stderr)
        return None
    record = _build_record(slug, pdf_meta, parsed)
    # § 4 "Abgrenzung des Gebiets" where it lists the Gemarkungen by their
    # land-register number (Baden, Württemberg: scripts/_lib/de/gemarkung.py)
    # or the Bavarian Gemeinden by Regierungsbezirk and Kreis (Franken,
    # Landwein Main: scripts/_lib/de/gemeinde_list.py): stage 04 draws the
    # record from them. Only those sidecars carry the key.
    text = pdf_to_text(pdf_path)
    area_text = gemarkung.section_4(text)
    n_units = len(gemarkung.parse_area(area_text).units)
    n_gemeinden = gemeinde_list.n_names(gemeinde_list.parse_lists(area_text))
    if n_units >= gemarkung.MIN_UNITS:
        record["area_text"] = area_text
        record["n_gemarkungen"] = n_units
    elif n_gemeinden >= gemeinde_list.MIN_NAMES:
        record["area_text"] = area_text
        record["n_gemeinden"] = n_gemeinden
    else:
        # The other layouts (scripts/_lib/de/area_units.py): a Gemeinde list
        # in prose (Rheingau § 3, Ahr, Hessische Bergstraße), Gemarkungen by
        # Kreis (Mitteldeutscher Landwein), the Rhineland's numbered
        # Gemarkungen (Landwein Rhein).
        section = area_units.area_section(text)
        n_named = len(area_units.parse(section))
        if n_named >= area_units.MIN_UNITS:
            record["area_text"] = section
            record["n_area_units"] = n_named
    # The wine types the specification states (scripts/_lib/de/ble_styles.py):
    # the styles of a record with no EU single document to state them, each
    # with its sentence; `description_text` is what was read, for the card
    # validator.
    stated = ble_styles.stated_styles(text)
    if stated:
        record["styles_stated"] = sorted(stated)
        record["styles_evidence"] = stated
        record["description_text"] = re.sub(r"\n\s*\n+", "\n\n",
                                            ble_styles.readable_text(text)).strip()
    if record["n_total"] == 0:
        # Older PDF template — no varieties extracted. Skip the sidecar
        # so the EU-document data (already loaded in stage 04) stays
        # authoritative.
        print(
            f"  {slug}: empty parse (older PDF template — needs template-{slug} branch); skipping sidecar",
            file=sys.stderr,
        )
        return None
    out_path = OUT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", action="append", default=[], help="single slug (repeatable)")
    ap.add_argument("--all", action="store_true", help="process all PDFs in manifest")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"error: {MANIFEST} missing — run scripts/de/00_fetch_data.py first "
              "(or manually populate raw/de/produktspezifikationen/)",
              file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_slug = manifest.get("by_slug", {})

    if args.slug:
        slugs = list(args.slug)
    elif args.all:
        slugs = sorted(by_slug.keys())
    else:
        print("error: pass --all or --slug SLUG", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    n_ok = n_skip = 0
    for slug in tqdm(slugs, desc="02f-de", leave=False):
        pdf_meta = by_slug.get(slug, {})
        rec = _process_slug(slug, pdf_meta)
        if rec is None:
            n_skip += 1
            continue
        index[slug] = {
            "slug": slug,
            "n_principal": rec["n_principal"],
            "n_accessory": rec["n_accessory"],
            "role_split_method": rec["role_split_method"],
            "n_unmatched": len(rec["unmatched_names"]),
        }
        n_ok += 1

    set_pliego_context(None)
    # a --slug run merges into the index on disk (extract_index.py)
    write_index(OUT_INDEX, index, partial=bool(args.slug))
    OUT_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_org": "BLE",
        "license": "Amtliches Werk §5 UrhG",
        "n_extracted": n_ok,
        "n_skipped": n_skip,
        "by_slug": index,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    n_unknowns = flush_unknowns_queue(UNKNOWNS)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"{UNKNOWNS.relative_to(ROOT)}",
            file=sys.stderr,
        )

    print(
        f"[02f/de] extracted={n_ok} skipped={n_skip} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
