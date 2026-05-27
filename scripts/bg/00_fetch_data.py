"""Fetch the public reference datasets the Bulgaria pipeline depends on.

Pipeline stage 00 (bg).

Sources:

1. **eAmbrosia EU register** (spine — list of BG wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=BG + productType=WINE + status=registered.
   Bulgaria entered the EU in 2007 with national appellations in flight,
   so most BG PDOs are Art.107 / Reg.1308/2013 grandfathered names whose
   only eAmbrosia reference is a non-fetchable `Ares(...)` summary-sheet
   (the SI / HR / HU stub pattern). The 2 macro PGIs (Дунавска равнина /
   Тракийска низина) sit alongside the ~52 PDOs.

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Bulgaria
   joined the EU in 2007; every BG PDO predates the Nov-2021 cutoff and
   is expected to be in the gpkg under `PDO-BG-*` file numbers.

3. **Eurostat GISCO LAU 2024** (CC-BY 4.0, ~30 MB) — *already cached*
   by the ES pipeline at `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`.
   Carries Bulgarian obshtina polygons (CNTR_CODE = "BG") used by the
   commune-list geometry fallback in stage 04.

Bulgaria is the first Cyrillic-script country in the corpus. Slugs are
produced via the shared `slugify` in `_lib/grape_lexicon.py` which
prepends `unidecode(...)` to romanise Cyrillic before NFKD; this script
mirrors that one-liner inline so it has no _lib import dependency.

Outputs:
- raw/bg/eambrosia/index.json — filtered BG-wine list with derived slug + kind
- raw/bg/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
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
OUT_DIR = ROOT / "raw" / "bg" / "eambrosia"
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
    s = unidecode(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
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
    bg_wines_all = [
        g for g in full
        if "BG" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    bg_wines = [g for g in bg_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(bg_wines_all) - len(bg_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in bg_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    n_dropped_duplicates = 0
    deduped: list[dict] = []
    for slug, ps in by_slug.items():
        if len(ps) == 1:
            deduped.append(ps[0])
            continue
        ps_sorted = sorted(
            ps,
            key=lambda p: (
                -1 if p.get("publications") else 0,
                -(int(p.get("modification_date", "")[:4] or 0)),
                -(int(p.get("modification_date", "")[5:7] or 0)),
                -(int(p.get("modification_date", "")[8:10] or 0)),
            ),
        )
        deduped.append(ps_sorted[0])
        n_dropped_duplicates += len(ps) - 1
    if collisions:
        print(
            f"[dedupe] {len(collisions)} slug collisions, "
            f"dropped {n_dropped_duplicates} duplicate registration(s):",
            file=sys.stderr,
        )
        for s, ps in collisions.items():
            kept = next(d for d in deduped if d["slug"] == s)
            others = [p["fileNumber"] for p in ps if p["fileNumber"] != kept["fileNumber"]]
            print(f"  {s}: kept {kept['fileNumber']}, dropped {', '.join(others)}",
                  file=sys.stderr)

    projected = deduped
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
        "n_bg_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} bg_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
