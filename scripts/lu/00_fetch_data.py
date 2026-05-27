"""Fetch the public reference datasets the Luxembourg pipeline depends on.

Pipeline stage 00 (lu).

Sources:

1. **eAmbrosia EU register** (spine — list of LU wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=LU + productType=WINE + status=registered
   → 1 wine GI (PDO-LU-A0452, "Moselle Luxembourgeoise"). The endpoint
   returns the full register (~6.5 MB, ~4000 GIs across all EU); we
   share the response with the ES + PT + IT + AT + SI + HR + HU + RO
   + BG + GR + DE + SK + CZ + CH pipelines via separate per-country
   index files.

   Coverage in eAmbrosia: 0 of 1 LU wines carry a fetchable EU-OJ
   publication URL — the lone PDO's only publication reference is the
   Ares numeric `58323`. The canonical specification is the **IVV 2020
   *Cahier des charges AOP Moselle luxembourgeoise*** (French, ~14 pp,
   stable URL at agriculture.public.lu), fetched in stage 01.

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   PDO-LU-A0452 with a single 245 km² polygon along the Moselle
   river (Schengen → Wasserbillig). Stage 04 uses this as the parent's
   geometry fallback when no commune-precise union is available.

3. **Eurostat GISCO LAU 2024** — *already cached* by the ES pipeline at
   `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`. Covers 100 Luxembourg
   modern communes (CNTR_CODE='LU'); the cahier's 15-commune
   perimeter list resolves through this index for tier-2 (per-commune
   Coteaux de + section/commune mentions) sub-denomination geometry.
   The historic pre-fusion communes (Burmerange, Wellenstein,
   Mompach, Waldbredimus) are folded into their post-fusion successors
   (Schengen, Schengen, Rosport-Mompach, Bous-Waldbredimus) via the
   alias table in `_lib/lu/commune.py`.

Outputs:
- raw/lu/eambrosia/index.json — filtered LU-wine list with derived slug + kind
- raw/lu/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
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
OUT_DIR = ROOT / "raw" / "lu" / "eambrosia"
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
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; the LU convention (same as ES/PT/IT/AT/
    SI/HR/HU/RO/BG/GR/DE/SK/CZ) is `DOP`/`IGP`."""
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
        print(
            "[error] shared artifacts missing — run scripts/es/00_fetch_data.py "
            "first to populate:",
            file=sys.stderr,
        )
        for p in missing:
            print(f"  - {p.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    full, etag = fetch_list()
    lu_wines_all = [
        g for g in full
        if "LU" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    lu_wines = [g for g in lu_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(lu_wines_all) - len(lu_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in lu_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside LU wines:",
            file=sys.stderr,
        )
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
    n_with_fetchable_uri = sum(
        1 for p in projected
        if any((pub.get("uri") or "").startswith(("http://", "https://"))
               for pub in p["publications"])
    )
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_lu_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "n_with_fetchable_uri": n_with_fetchable_uri,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} lu_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"with_fetchable_uri={n_with_fetchable_uri} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
