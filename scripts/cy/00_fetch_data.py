"""Fetch the public reference datasets the Cyprus pipeline depends on.

Pipeline stage 00 (cy).

Sources:

1. **eAmbrosia EU register** (spine — list of CY wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=CY + productType=WINE + status=registered.
   → 11 wine GIs (7 PDO + 4 PGI). None carry a fetchable EU-OJ single
   document — Commandaria's only `publications` entry is a non-fetchable
   `Ref. Ares(...)` summary-sheet, and the other 10 are bare Art.107 /
   Reg.1308/2013 grandfathered names. So all 11 ship as content-stubs
   (the GR/SI/HR pattern) and are augmented from the national technical
   file via stages 01c/02f (moa.gov.cy).

   Cyprus is a Greek-script country (like Greece). eAmbrosia ships an
   EU-official Latin **transcriptions** field per record
   (`transcriptions[0]` — `Κουμανδαρία` → `Koumandaria`, `Πιτσιλιά` →
   `Pitsilia`, …) which the slugifier uses as authoritative, so the URL
   paths and internal identifiers stay ASCII. `country` is `"cy"`;
   `source_lang` is `"el"` — like AT/SI/GR, the country code differs from
   the language code.

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Cyprus
   joined the EU in 2004; all 7 CY PDOs are in the dataset under
   `PDO-CY-A162x`. The 4 CY PGIs (the island's wine districts — Πάφος /
   Λεμεσός / Λάρνακα / Λευκωσία) are NOT in Bétard (PDO-only dataset)
   and resolve via the GISCO district-union fallback.

3. **Eurostat GISCO LAU 2024** (CC-BY 4.0, ~30 MB) — *already cached*
   by the ES pipeline at `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`.
   Carries ~615 Cypriot community polygons under CNTR_CODE='CY' whose
   `GISCO_ID` prefix encodes the district (`CY_6xxx`=Πάφος, `CY_5xxx`=
   Λεμεσός, `CY_4xxx`=Λάρνακα, `CY_1xxx`=Λευκωσία); the 4 PGI districts
   union the matching communities.

Outputs:
- raw/cy/eambrosia/index.json — filtered CY-wine list with derived slug + kind
- raw/cy/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from unidecode import unidecode

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "raw" / "cy" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

FIGSHARE_GPKG_PATH = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_LAU_PATH = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"

EAMBROSIA_LIST_URL = (
    "https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications"
)
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
LICENSE = (
    "© European Union, eAmbrosia register. Reuse authorised with attribution."
)


def slugify(s: str) -> str:
    """Latin-ASCII slug (via unidecode for Greek → Latin)."""
    s = unidecode(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def derive_slug(rec: dict) -> str:
    """Slug source priority: eAmbrosia transcription → unidecoded name."""
    transcriptions = rec.get("transcriptions") or []
    if transcriptions:
        return slugify(transcriptions[0])
    name = (rec.get("protectedNames") or [""])[0]
    return slugify(name)


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; the multi-country convention here is
    `DOP`/`IGP` (same as ES/PT/IT/AT/SI/HR/HU/RO/BG/GR)."""
    return {"PDO": "DOP", "PGI": "IGP"}.get(gi_type, gi_type)


def project(rec: dict) -> dict:
    name = (rec.get("protectedNames") or [""])[0]
    transcriptions = rec.get("transcriptions") or []
    return {
        "giIdentifier": rec["giIdentifier"],
        "fileNumber": rec.get("fileNumber") or "",
        "name": name,
        "name_latin": transcriptions[0] if transcriptions else "",
        "transcriptions": transcriptions,
        "slug": derive_slug(rec),
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
    missing = []
    if not FIGSHARE_GPKG_PATH.exists():
        missing.append(FIGSHARE_GPKG_PATH)
    if not GISCO_LAU_PATH.exists():
        missing.append(GISCO_LAU_PATH)
    if missing:
        for p in missing:
            print(
                "[error] shared artifact missing — run scripts/es/00_fetch_data.py "
                f"first to populate: {p.relative_to(ROOT)}",
                file=sys.stderr,
            )
        sys.exit(2)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    full, etag = fetch_list()
    cy_wines_all = [
        g for g in full
        if "CY" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    cy_wines = [g for g in cy_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(cy_wines_all) - len(cy_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in cy_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(f"[warn] {len(collisions)} slug collisions inside CY wines:",
              file=sys.stderr)
        for s, ps in collisions.items():
            ids = ", ".join(p["fileNumber"] or p["giIdentifier"] for p in ps)
            print(f"  {s}: {ids}", file=sys.stderr)

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
    n_with_trans = sum(1 for p in projected if p["transcriptions"])
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_cy_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "n_with_transcription": n_with_trans,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} cy_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"with_transcription={n_with_trans} → {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
