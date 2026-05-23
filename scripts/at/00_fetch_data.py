"""Fetch the public reference datasets the Austria pipeline depends on.

Pipeline stage 00 (at).

Sources:

1. **eAmbrosia EU register** (spine — list of AT wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=AT + productType=WINE + status=registered
   → 32 wine GIs (29 PDO + 3 PGI). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU); we share the response with the
   ES + PT + IT pipelines via separate per-country index files.

   Austria is the cleanest country in the corpus: every one of the 32
   wines carries an OJ Series C publication URL — no curator queue, no
   no-publication stub bucket (unlike ES 44 % / IT 74 %).

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   all EU PDOs including the 29 Austrian DOPs (`PDO-AT-*` file numbers).
   Used as the geometry fallback (the Bundesland-level regional g.U.s).

3. **Statistik Austria registry lists** — the official Gemeinde ↔
   politischer Bezirk reference, published as stable CSVs at
   `statistik.at/verzeichnis/reglisten/`. Two small files:
   - `polbezirke.csv` — politischer Bezirk name ↔ 3-digit code
   - `gemliste_knz.csv` — Gemeinde name ↔ 5-digit Gemeindekennziffer
   Stage 04 joins these against the Eurostat GISCO LAU municipality
   polygons (whose `GISCO_ID` carries the Kennziffer) to resolve each
   Austrian DAC by its Einziges-Dokument Bezirk/Gemeinde description —
   commune-precise and disjoint, instead of Bétard's overlapping
   whole-municipality polygons. Licence: Statistik Austria open data,
   CC BY 4.0.

4. **Eurostat GISCO LAU** — *already cached* by the ES pipeline at
   `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (covers all EU LAU2
   units including ~2 100 Austrian Gemeinden).

Outputs:
- raw/at/eambrosia/index.json — filtered AT-wine list with derived slug + kind
- raw/at/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
- raw/at/statistik/polbezirke.csv, gemliste_knz.csv — registry lists

Each AT wine GI record carries:
- giIdentifier (e.g. EUGI00000003500) — internal EU id, unstable
- fileNumber (e.g. PDO-AT-A0205) — stable EU GI catalogue id
- name — protectedNames[0]
- slug — kebab-case derived from name (the unit of identity downstream)
- kind — DOP or IGP (same convention as ES/PT/IT)
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
OUT_DIR = ROOT / "raw" / "at" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Shared upstream artifacts already fetched by the ES pipeline. Asserted
# here so a fresh AT-only checkout fails loudly rather than silently
# producing geometry-less records downstream.
FIGSHARE_GPKG_PATH = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_LAU_PATH = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"

# Statistik Austria registry lists — Gemeinde ↔ politischer Bezirk.
STATISTIK_DIR = ROOT / "raw" / "at" / "statistik"
STATISTIK_FILES = (
    ("polbezirke.csv",
     "https://www.statistik.at/verzeichnis/reglisten/polbezirke.csv"),
    ("gemliste_knz.csv",
     "https://www.statistik.at/verzeichnis/reglisten/gemliste_knz.csv"),
)
STATISTIK_LICENSE = (
    "© STATISTIK AUSTRIA. Open data, CC BY 4.0 — reuse with attribution."
)

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
    """eAmbrosia uses `PDO`/`PGI`; the AT convention (same as ES/PT/IT)
    is `DOP`/`IGP`."""
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


def fetch_statistik_austria() -> dict:
    """Download the Statistik Austria Gemeinde ↔ Bezirk registry lists.
    Cached by content — re-runs only re-fetch when the upstream file
    changes (the lists carry a Gebietsstand year, stable within a year)."""
    STATISTIK_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict] = {}
    for filename, url in STATISTIK_FILES:
        dest = STATISTIK_DIR / filename
        print(f"[statistik] fetch {url}", file=sys.stderr)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        body = r.content
        if b";" not in body[:200]:
            raise RuntimeError(
                f"Statistik Austria returned non-CSV content for {filename} "
                f"({len(body)} bytes) — URL may have rotated."
            )
        dest.write_bytes(body)
        out[filename] = {"url": url, "bytes": len(body)}
        print(f"[statistik] saved {filename} ({len(body):,} bytes)", file=sys.stderr)
    (STATISTIK_DIR / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": STATISTIK_LICENSE,
        "files": out,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    full, etag = fetch_list()
    at_wines_all = [
        g for g in full
        if "AT" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    at_wines = [g for g in at_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(at_wines_all) - len(at_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in at_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside AT wines:",
            file=sys.stderr,
        )
        for s, ps in collisions.items():
            ids = ", ".join(p["fileNumber"] or p["giIdentifier"] for p in ps)
            print(f"  {s}: {ids}", file=sys.stderr)

    projected.sort(key=lambda p: p["slug"])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(
        json.dumps({"generated_at": now, "wines": projected},
                   ensure_ascii=False, indent=2)
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
        "n_at_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    print(
        f"[done] eAmbrosia: total_eu={len(full)} at_wines={len(projected)} "
        f"by_kind={by_kind} with_publication={n_with_pub} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )

    stat = fetch_statistik_austria()
    print(
        f"[done] Statistik Austria: {len(stat)} registry lists "
        f"→ {STATISTIK_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
