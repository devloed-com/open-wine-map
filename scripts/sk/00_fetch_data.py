"""Fetch the public reference datasets the Slovakia pipeline depends on.

Pipeline stage 00 (sk).

Sources:

1. **eAmbrosia EU register** (spine — list of SK wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=SK + productType=WINE + status=registered
   → 10 wine GIs (9 PDO + 1 PGI). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU); we share the response with the
   ES + PT + IT + AT + SI + HR + HU + RO + BG + GR + DE pipelines via
   separate per-country index files.

   Coverage in eAmbrosia: 4 of 10 SK wines carry an EU-OJ publication
   URL (Vinohradnícka oblasť Tokaj, Stredoslovenská, Skalický rubín,
   TOKAJSKÉ VÍNO zo slovenskej oblasti). The other 6 are Art.107 /
   Reg.1308/2013 grandfathered names whose only eAmbrosia reference is
   a non-fetchable `Ares(...)` summary-sheet — they ship as content-
   stubs (IT/ES curator-queue pattern) and nonetheless appear on the
   map because Bétard 2022 covers 8 of 9 SK PDOs (and the 9th PDO,
   TOKAJSKÉ VÍNO, aliases the Vinohradnícka oblasť Tokaj polygon).

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   8 of 9 SK DOPs (`PDO-SK-A0120`, `PDO-SK-A1354..1360`, `PDO-SK-A1598`,
   `PDO-SK-01899`). Stage 04 uses this as the primary geometry source.
   The single SK PGI (`PGI-SK-A1361` "Slovenská") is not in Bétard
   (PDO-only by design); stage 04 resolves it as the union of all 8 SK
   PDO polygons.

Outputs:
- raw/sk/eambrosia/index.json — filtered SK-wine list with derived slug + kind
- raw/sk/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
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
OUT_DIR = ROOT / "raw" / "sk" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

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


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; the SK convention (same as ES/PT/IT/AT/
    SI/HR/HU/RO/BG/GR/DE) is `DOP`/`IGP`."""
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
    full, etag = fetch_list()
    sk_wines_all = [
        g for g in full
        if "SK" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    sk_wines = [g for g in sk_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(sk_wines_all) - len(sk_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in sk_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside SK wines:",
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
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_sk_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} sk_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
