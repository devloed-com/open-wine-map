"""Fetch the public reference datasets the Netherlands pipeline depends on.

Pipeline stage 00 (nl).

Sources:

1. **eAmbrosia EU register** (spine — list of NL wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=NL + productType=WINE + status=registered
   → 22 wine GIs (10 PDO + 12 PGI). The cross-border BE+NL PDO
   `PDO-BE+NL-02172` (Maasvallei Limburg) is **excluded** here — it
   ships on the BE side as the primary record. We share the full
   eAmbrosia response with every other country pipeline via separate
   per-country index files.

   Coverage in eAmbrosia: all 22 NL wines carry an EU-OJ publication
   URL (better than every prior country except AT). Both PGIs (the
   12 province-wide IGPs) and PDOs (4 of 10 in Bétard, 6 post-2022)
   resolve.

   **Source language**: `"nl"` for every record. The Netherlands is
   the first single-source-lang NL pipeline in the corpus; Belgium
   (`be`) introduced `"nl"` as a source language for its 5 Flemish
   wines + Maasvallei, but per-record. NL re-uses the Dutch downstream
   infrastructure (02b Wikipedia cache `raw/wikipedia/aocs/nl/`,
   02e translation glossary, locale catalog) that BE put in place.

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   6 of the 10 NL PDOs (`PDO-NL-02114` Mergelland, `PDO-NL-02168`
   Vijlen, `PDO-NL-02230` Oolde, `PDO-NL-02169` Ambt Delden,
   `PDO-NL-02402` Achterhoek-Winterswijk, plus the cross-border
   Maasvallei — owned by BE). The 4 newer PDOs (Rivierenland,
   Schouwen-Duiveland, De Voerendaalse Bergen, Twente) post-date the
   Bétard snapshot and ship as `stub-no-geometry` in v1 (Phase 2
   parses their commune lists via GISCO LAU). The 12 NL PGIs are
   resolved via the NUTS-2 layer below.

3. **Eurostat NUTS-2 GeoJSON** (~4 MB) — fetched into
   `raw/nl/nuts/NUTS_RG_03M_2024_4326_LEVL_2.geojson`. The 12 Dutch
   NUTS-2 regions are exactly the 12 Dutch provinces, each NL PGI is
   coextensive with one province (Limburg, Gelderland, Zeeland, …),
   so stage 04 resolves each PGI by NUTS-2 code lookup. License:
   © European Union, Eurostat / GISCO. Permitted commercial use with
   attribution. NUTS code → province name mapping is hard-coded in
   `_lib/nl/geometry.py`.

Outputs:
- raw/nl/eambrosia/index.json — filtered NL-wine list with derived slug + kind
- raw/nl/eambrosia/manifest.json — fetch metadata
- raw/nl/nuts/NUTS_RG_03M_2024_4326_LEVL_2.geojson — Eurostat NUTS-2 polygons
- raw/nl/nuts/manifest.json — NUTS fetch metadata
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
OUT_DIR = ROOT / "raw" / "nl" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

NUTS_DIR = ROOT / "raw" / "nl" / "nuts"
NUTS_PATH = NUTS_DIR / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
NUTS_MANIFEST = NUTS_DIR / "manifest.json"
NUTS_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
)

FIGSHARE_GPKG_PATH = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"

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
NUTS_LICENSE = (
    "© European Union, Eurostat / GISCO 2024. Reuse with attribution."
)


# File numbers that are cross-border with another country and primary-
# owned elsewhere. Skipped here to avoid duplicate records on the map.
_CROSS_BORDER_OWNED_ELSEWHERE: frozenset[str] = frozenset({
    "PDO-BE+NL-02172",  # Maasvallei Limburg — BE-primary
})


def slugify(s: str) -> str:
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
        "source_lang": "nl",
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


def fetch_eambrosia() -> tuple[list[dict], str]:
    print(f"[fetch] {EAMBROSIA_LIST_URL}", file=sys.stderr)
    r = requests.get(
        EAMBROSIA_LIST_URL,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json(), r.headers.get("etag") or ""


def fetch_nuts() -> None:
    NUTS_DIR.mkdir(parents=True, exist_ok=True)
    if NUTS_PATH.exists() and NUTS_MANIFEST.exists():
        print(f"[cache] NUTS-2 GeoJSON already at {NUTS_PATH.relative_to(ROOT)}",
              file=sys.stderr)
        return
    print(f"[fetch] {NUTS_URL}", file=sys.stderr)
    r = requests.get(NUTS_URL, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    NUTS_PATH.write_bytes(r.content)
    NUTS_MANIFEST.write_text(json.dumps({
        "source_url": NUTS_URL,
        "license": NUTS_LICENSE,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(r.content),
        "etag": r.headers.get("etag") or "",
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def assert_shared_artifacts() -> None:
    if not FIGSHARE_GPKG_PATH.exists():
        print(
            "[error] shared artifact missing — run scripts/es/00_fetch_data.py "
            f"first to populate: {FIGSHARE_GPKG_PATH.relative_to(ROOT)}",
            file=sys.stderr,
        )
        sys.exit(2)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    fetch_nuts()
    full, etag = fetch_eambrosia()
    nl_wines_all = [
        g for g in full
        if "NL" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    nl_wines = [g for g in nl_wines_all if g.get("status") == "registered"]
    n_skipped_status = len(nl_wines_all) - len(nl_wines)

    projected = []
    n_skipped_xborder = 0
    for rec in nl_wines:
        fn = rec.get("fileNumber") or ""
        if fn in _CROSS_BORDER_OWNED_ELSEWHERE:
            n_skipped_xborder += 1
            continue
        projected.append(project(rec))

    by_slug: dict[str, list[dict]] = {}
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(f"[warn] {len(collisions)} slug collisions inside NL wines:",
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
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_nl_wines": len(projected),
        "n_skipped_status": n_skipped_status,
        "n_skipped_cross_border": n_skipped_xborder,
        "cross_border_owned_elsewhere": sorted(_CROSS_BORDER_OWNED_ELSEWHERE),
        "n_with_publication": n_with_pub,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[done] eAmbrosia: total_eu={len(full)} nl_wines={len(projected)} "
          f"by_kind={by_kind} with_publication={n_with_pub} "
          f"x_border_skipped={n_skipped_xborder} → {INDEX_PATH.relative_to(ROOT)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
