"""Fetch the public reference datasets the Germany (DE) pipeline depends on.

Pipeline stage 00 (de).

Sources:

1. **eAmbrosia EU register** (spine — list of DE wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=DE + productType=WINE + status=registered
   → 46 wine GIs (19 PDO + 27 PGI). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU); we share the response with the
   ES + PT + IT + AT + SI + HR + HU + RO + BG + GR pipelines via separate
   per-country index files.

   Coverage in eAmbrosia: 27 of 46 DE wines carry an OJ-C publication URL
   (~59 %, vs AT's 100 %, IT's ~26 %, SI/HR/BG/GR's ~5 %). The 19 with no
   `publications` URL are Art. 107 / Reg. 1308/2013 grandfathered names
   whose only eAmbrosia reference is a non-fetchable `Ares(...)` summary-
   sheet — they ship as content-stubs (IT/ES curator-queue pattern) but
   nonetheless appear on the map because Bétard 2022 covers every German
   PDO (Germany was an EU founding member).

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers all
   EU PDOs including the 13 traditional German Anbaugebiete (`PDO-DE-A12xx`,
   `PDO-DE-A0867`). Stage 04 uses this as the primary geometry source.

3. **Eurostat GISCO LAU** — *already cached* by the ES pipeline at
   `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (covers all EU LAU2 units
   including ~10 800 German Gemeinden). Reserved for the Phase-2 commune-
   list fallback parser; v1 geometry chain uses Bétard + parent-Anbaugebiet
   inheritance + PGI region-union (no GISCO step needed).

4. **BLE Produktspezifikation PDFs** — the national specification per
   Anbaugebiet, published by the Bundesanstalt für Landwirtschaft und
   Ernährung as *Amtliches Werk §5 UrhG*. 13 PDFs, one per Anbaugebiet,
   downloaded into `raw/de/produktspezifikationen/<slug>.pdf`. Stage
   02f parses these for the principal/accessory variety split that the
   EU Einziges Dokument doesn't carry.

Outputs:
- raw/de/eambrosia/index.json — filtered DE-wine list with derived slug + kind
- raw/de/eambrosia/manifest.json — fetch metadata for the eAmbrosia call

Each DE wine GI record carries:
- giIdentifier (e.g. EUGI00000003500) — internal EU id, unstable
- fileNumber (e.g. PDO-DE-A1270) — stable EU GI catalogue id
- name — protectedNames[0]
- slug — kebab-case derived from name (the unit of identity downstream)
- kind — DOP or IGP (same convention as ES/PT/IT/AT/SI/HR/HU/RO/BG/GR)
- producer_group — {name, url, email, address} for sidebar attribution
- publications — array of {text, uri} OJ citations (input to stage 01)
- raw — the full eAmbrosia record (preserved for traceability)
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "raw" / "de" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Shared upstream artifacts already fetched by the ES pipeline. Asserted
# here so a fresh DE-only checkout fails loudly rather than silently
# producing geometry-less records downstream.
FIGSHARE_GPKG_PATH = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_LAU_PATH = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"

EAMBROSIA_LIST_URL = (
    "https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications"
)

# BLE Produktspezifikation per Anbaugebiet — Amtliches Werk §5 UrhG.
BLE_PRODUKTSPEZIFIKATIONEN_DIR = ROOT / "raw" / "de" / "produktspezifikationen"
BLE_PRODUKTSPEZIFIKATIONEN_LICENSE = (
    "© BLE (Bundesanstalt für Landwirtschaft und Ernährung). "
    "Amtliches Werk gemäß §5 UrhG — Quellenangabe erforderlich."
)
BLE_BASE = (
    "https://www.ble.de/SharedDocs/Downloads/DE/Ernaehrung-Lebensmittel/"
    "EU-Qualitaetskennzeichen/Wein/Antraege/Bestimmte_Anbaugebiete/"
    "01_Produktspezifiaktion_Anbaugebiete"
)
# (slug, BLE filename region fragment, display name). The Hessische-
# Bergstraße filename is truncated to `_Hessisch.pdf` on the BLE side.
BLE_PRODUKTSPEZIFIKATIONEN = (
    ("ahr",                 "Ahr",                 "Ahr"),
    ("baden",               "Baden",               "Baden"),
    ("franken",             "Franken",             "Franken"),
    ("hessische-bergstrae", "Hessisch",            "Hessische Bergstraße"),
    ("mittelrhein",         "Mittelrhein",         "Mittelrhein"),
    ("mosel",               "Mosel",               "Mosel"),
    ("nahe",                "Nahe",                "Nahe"),
    ("pfalz",               "Pfalz",               "Pfalz"),
    ("rheingau",            "Rheingau",            "Rheingau"),
    ("rheinhessen",         "Rheinhessen",         "Rheinhessen"),
    ("saale-unstrut",       "Saale_Unstrut",       "Saale-Unstrut"),
    ("sachsen",             "Sachsen",             "Sachsen"),
    ("wurttemberg",         "Wuerttemberg",        "Württemberg"),
)
# BLE Produktspezifikation per Landwein g.g.A. — same Amtliches-Werk §5
# UrhG source, parallel directory. These 15 Landwein PGIs have no
# fetchable EU Einziges Dokument (they ship as stubs), so the BLE
# national Produktspezifikation is the canonical source for their
# authorised-variety roster + Zusammenhang terroir text. The URL works
# without the cache-buster `v=` param, so we omit it (robust to BLE
# version bumps).
BLE_LANDWEINE_BASE = (
    "https://www.ble.de/SharedDocs/Downloads/DE/Ernaehrung-Lebensmittel/"
    "EU-Qualitaetskennzeichen/Wein/Antraege/Landweingebiete/"
    "01_Produktspezifikationen_Landweine"
)
# (slug, BLE filename fragment, display name).
BLE_LANDWEINE = (
    ("ahrtaler-landwein",            "Ahrtaler",                     "Ahrtaler Landwein"),
    ("badischer-landwein",           "Badischer",                    "Badischer Landwein"),
    ("bayerischer-bodensee-landwein","Bayerischer_Bodensee-Landwein","Bayerischer Bodensee-Landwein"),
    ("brandenburger-landwein",       "Brandenburger",                "Brandenburger Landwein"),
    ("landwein-main",                "Main",                         "Landwein Main"),
    ("landwein-neckar",              "Neckar",                       "Landwein Neckar"),
    ("landwein-oberrhein",           "Oberrhein",                    "Landwein Oberrhein"),
    ("landwein-rhein",               "Rhein",                        "Landwein Rhein"),
    ("landwein-rhein-neckar",        "Rhein-Neckar",                 "Landwein Rhein-Neckar"),
    ("mitteldeutscher-landwein",     "Mitteldeutscher",              "Mitteldeutscher Landwein"),
    ("regensburger-landwein",        "Regensburger",                 "Regensburger Landwein"),
    ("rheingauer-landwein",          "Rheingauer",                   "Rheingauer Landwein"),
    ("schwabischer-landwein",        "Schwaebischer_Landwein",       "Schwäbischer Landwein"),
    ("starkenburger-landwein",       "Starkenburger",                "Starkenburger Landwein"),
    ("taubertaler-landwein",         "Taubertaeler",                 "Taubertäler Landwein"),
)
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
LICENSE = (
    "© European Union, eAmbrosia register. Reuse authorised with attribution."
)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; the DE convention (same as ES/PT/IT/AT/
    SI/HR/HU/RO/BG/GR) is `DOP`/`IGP`."""
    return {"PDO": "DOP", "PGI": "IGP"}.get(gi_type, gi_type)


def project(rec: dict) -> dict:
    name = (rec.get("protectedNames") or [""])[0]
    return {
        "giIdentifier": rec["giIdentifier"],
        "fileNumber": rec.get("fileNumber") or "",
        "name": name,
        "slug": slugify(name),
        "kind": normalise_kind(rec.get("giType") or ""),
        "status": rec.get("status") or "",
        "eu_protection_date": rec.get("euProtectionDate") or "",
        "modification_date": rec.get("modificationDate") or "",
        "producer_group": {
            "name": rec.get("producerGroupName") or "",
            "url": rec.get("producerGroupUrl") or "",
            "email": rec.get("producerGroupEmail") or "",
            "address": rec.get("producerGroupAdress") or "",
            "country": rec.get("producerGroupCountry") or "",
        },
        "publications": rec.get("publications") or [],
        "raw": rec,
    }


def _fetch_ble_pdf(slug: str, url: str, display: str, category: str) -> dict:
    """Fetch one BLE PDF (cache hit if already on disk) → manifest entry."""
    import hashlib  # local — keeps the module's top imports lean

    dest = BLE_PRODUKTSPEZIFIKATIONEN_DIR / f"{slug}.pdf"
    cached = dest.exists()
    if cached:
        body = dest.read_bytes()
    else:
        print(f"[ble] fetch {slug} ({display})", file=sys.stderr)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        body = r.content
        if body[:4] != b"%PDF":
            raise RuntimeError(
                f"BLE returned non-PDF for {slug} ({len(body)} bytes) — "
                "the URL pattern may have rotated."
            )
        dest.write_bytes(body)
    return {
        "display": display,
        "url": url,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "cached": cached,
        "category": category,
    }


def fetch_ble_produktspezifikationen() -> dict:
    """Download the BLE Produktspezifikation PDFs — 13 per-Anbaugebiet
    quality-wine specs + 15 per-Landwein g.g.A. specs. Each is *Amtliches
    Werk §5 UrhG* — free reuse with attribution. Re-runs are cache hits:
    if the PDF already exists, the sha256 is re-computed but the file is
    not re-fetched."""
    BLE_PRODUKTSPEZIFIKATIONEN_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for slug, fragment, display in BLE_PRODUKTSPEZIFIKATIONEN:
        v_param = "v=1" if slug == "hessische-bergstrae" else "v=3"
        url = f"{BLE_BASE}/Produktspezifikation_{fragment}.pdf?__blob=publicationFile&{v_param}"
        manifest[slug] = _fetch_ble_pdf(slug, url, display, "anbaugebiet")

    # Landwein g.g.A. specs — parallel BLE directory, no `v=` param.
    for slug, fragment, display in BLE_LANDWEINE:
        url = f"{BLE_LANDWEINE_BASE}/Landwein_{fragment}.pdf?__blob=publicationFile"
        manifest[slug] = _fetch_ble_pdf(slug, url, display, "landwein")

    (BLE_PRODUKTSPEZIFIKATIONEN_DIR / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": BLE_PRODUKTSPEZIFIKATIONEN_LICENSE,
        "source_org": "BLE",
        "n_pdfs": len(manifest),
        "by_slug": manifest,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def fetch_list() -> tuple[list[dict], str]:
    print(f"[fetch] {EAMBROSIA_LIST_URL}", file=sys.stderr)
    r = requests.get(
        EAMBROSIA_LIST_URL,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json(), r.headers.get("etag") or ""


def assert_shared_artifacts() -> None:
    missing = [
        str(p.relative_to(ROOT))
        for p in (FIGSHARE_GPKG_PATH, GISCO_LAU_PATH)
        if not p.exists()
    ]
    if missing:
        print(
            "[error] shared artifacts missing — run scripts/es/00_fetch_data.py "
            f"first to populate: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)


# Six DE Einzellage PDOs are modelled as sub-denominations of their parent
# Anbaugebiet (Franken / Nahe / Mosel). The parent map is hand-verified
# against the EU-OJ Einziges Dokument of each Einzellage, which names
# its Anbaugebiet in section 6.
_EINZELLAGE_PARENT_BY_FILE_NUMBER: dict[str, tuple[str, str]] = {
    "PDO-DE-N1822": ("PDO-DE-A1267", "Franken"),         # Bürgstadter Berg
    "PDO-DE-02403": ("PDO-DE-A1267", "Franken"),         # Würzburger Stein-Berg
    "PDO-DE-02363": ("PDO-DE-A1271", "Nahe"),            # Monzinger Niederberg
    "PDO-DE-02081": ("PDO-DE-A1270", "Mosel"),           # Uhlen Blaufüsser Lay
    "PDO-DE-02082": ("PDO-DE-A1270", "Mosel"),           # Uhlen Laubach
    "PDO-DE-02083": ("PDO-DE-A1270", "Mosel"),           # Uhlen Roth Lay
}


def _annotate_einzellagen(projected: list[dict]) -> int:
    """Tag the 6 Einzellage PDOs as sub-denominations of their parent
    Anbaugebiet. Returns the number of records annotated."""
    by_file_number = {p["fileNumber"]: p for p in projected}
    n = 0
    for fn, (parent_fn, _) in _EINZELLAGE_PARENT_BY_FILE_NUMBER.items():
        rec = by_file_number.get(fn)
        if rec is None:
            continue
        parent = by_file_number.get(parent_fn)
        if parent is None:
            continue
        rec["is_sub_denomination"] = True
        rec["parent_file_number"] = parent_fn
        rec["parent_id_eambrosia"] = parent["giIdentifier"]
        rec["parent_slug"] = parent["slug"]
        rec["parent_name"] = parent["name"]
        n += 1
    return n


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    full, etag = fetch_list()
    de_wines_all = [
        g for g in full
        if "DE" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    de_wines = [g for g in de_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(de_wines_all) - len(de_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in de_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside DE wines:",
            file=sys.stderr,
        )
        for s, ps in collisions.items():
            ids = ", ".join(p["fileNumber"] or p["giIdentifier"] for p in ps)
            print(f"  {s}: {ids}", file=sys.stderr)

    n_einzellagen = _annotate_einzellagen(projected)

    projected.sort(key=lambda p: p["slug"])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(
        json.dumps({"generated_at": now, "wines": projected},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    by_kind: dict[str, int] = {}
    for p in projected:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1

    n_with_pub = sum(1 for p in projected if p["publications"])
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_de_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "n_einzellagen": n_einzellagen,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} de_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"einzellagen={n_einzellagen} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )

    ble = fetch_ble_produktspezifikationen()
    n_cached = sum(1 for v in ble.values() if v.get("cached"))
    print(
        f"[done] BLE Produktspezifikationen: {len(ble)} PDFs "
        f"(new={len(ble)-n_cached}, cached={n_cached}) → "
        f"{BLE_PRODUKTSPEZIFIKATIONEN_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
