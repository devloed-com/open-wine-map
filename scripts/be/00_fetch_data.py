"""Fetch the public reference datasets the Belgium pipeline depends on.

Pipeline stage 00 (be).

Sources:

1. **eAmbrosia EU register** (spine — list of BE wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=BE + productType=WINE + status=registered
   → 10 wine GIs (7 PDO + 2 PGI + 1 cross-border BE+NL PDO,
   "Maasvallei Limburg"). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU); we share the response with the
   ES + PT + IT + AT + SI + HR + HU + RO + BG + GR + DE + SK + CZ + CH
   + LU + NL pipelines via separate per-country index files.

   Coverage in eAmbrosia: 4 of 10 BE wines carry an EU-OJ publication
   URL (the 3 Flemish DOPs Hagelandse / Haspengouwse / Heuvellandse,
   plus the cross-border Maasvallei Limburg). The other 6 are
   Art.107 / Reg.1308/2013 grandfathered names with only a
   non-fetchable `Ares(...)` summary-sheet — they ship as content-
   stubs (the IT/ES/SI curator-queue pattern) and nonetheless appear
   on the map because Bétard 2022 covers every BE PDO.

   **Per-record source_lang**: Flemish wines (5 records — 3 DOPs +
   Vlaamse landwijn + Vlaamse mousserende kwaliteitswijn) + Maasvallei
   use `nl`; Walloon wines (4 records) use `fr`. Belgium is the
   second country in the corpus with per-record source_lang (CH was
   the first) and the first to introduce `nl` as a source language
   (until now `nl` was only a translation TARGET locale).

   **Cross-border Maasvallei Limburg** (`PDO-BE+NL-02172`): emitted as
   a single BE record (BE-primary by file_number ordering). The
   parallel NL pipeline (country #17) skips this file_number — the
   cross-border GI shows up exactly once on the map, on the BE side.
   When NL ships, a `cross-border` reference surface on the NL panel
   is a Phase 2 follow-up.

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   all 8 BE+ PDOs (`PDO-BE-A0009`, `PDO-BE-A0011`, `PDO-BE-A0012`,
   `PDO-BE-A1426`, `PDO-BE-A1430`, `PDO-BE-A1492`, `PDO-BE-A1499`,
   `PDO-BE+NL-02172`). Stage 04 uses this as the primary geometry
   source. The 2 BE PGIs (`PGI-BE-A1429` Vlaamse landwijn,
   `PGI-BE-A0010` Vin de pays des jardins de Wallonie) are not in
   Bétard; stage 04 resolves them as a union of their member-PDO
   polygons (the SI/HU/BG/DE PGI pattern).

Outputs:
- raw/be/eambrosia/index.json — filtered BE-wine list with derived slug +
  kind + source_lang
- raw/be/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
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
OUT_DIR = ROOT / "raw" / "be" / "eambrosia"
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


# Per-record source_lang map — Flemish wines use `nl`, Walloon use `fr`,
# cross-border Maasvallei takes the Flemish side. Hand-verified against
# the eAmbrosia register and the Belgian wine-law region structure.
_SOURCE_LANG_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-BE-A1492": "nl",          # Haspengouwse wijn
    "PDO-BE-A1499": "nl",          # Hagelandse wijn
    "PDO-BE-A1426": "nl",          # Heuvellandse wijn
    "PGI-BE-A1429": "nl",          # Vlaamse landwijn
    "PDO-BE-A1430": "nl",          # Vlaamse mousserende kwaliteitswijn
    "PDO-BE-A0009": "fr",          # Côtes de Sambre et Meuse
    "PGI-BE-A0010": "fr",          # Vin de pays des jardins de Wallonie
    "PDO-BE-A0011": "fr",          # Vin mousseux de qualité de Wallonie
    "PDO-BE-A0012": "fr",          # Crémant de Wallonie
    "PDO-BE+NL-02172": "nl",       # Maasvallei Limburg (BE-primary; nl-side)
}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; the BE convention (same as ES/PT/IT/AT/
    SI/HR/HU/RO/BG/GR/DE/SK/CZ) is `DOP`/`IGP`."""
    return {"PDO": "DOP", "PGI": "IGP"}.get(gi_type, gi_type)


def project(rec: dict) -> dict:
    name = (rec.get("protectedNames") or [""])[0]
    file_number = rec.get("fileNumber") or ""
    return {
        "giIdentifier": rec["giIdentifier"],
        "fileNumber": file_number,
        "name": name,
        "slug": slugify(name),
        "kind": normalise_kind(rec.get("giType") or ""),
        "source_lang": _SOURCE_LANG_BY_FILE_NUMBER.get(file_number, "nl"),
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
    be_wines_all = [
        g for g in full
        if "BE" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    be_wines = [g for g in be_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(be_wines_all) - len(be_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in be_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside BE wines:",
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
    by_lang: dict[str, int] = {}
    for p in projected:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1
        by_lang[p["source_lang"]] = by_lang.get(p["source_lang"], 0) + 1

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
        "n_be_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_with_publication": n_with_pub,
        "n_with_fetchable_uri": n_with_fetchable_uri,
        "by_kind": by_kind,
        "by_source_lang": by_lang,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} be_wines={len(projected)} "
        f"by_kind={by_kind} by_source_lang={by_lang} "
        f"with_publication={n_with_pub} "
        f"with_fetchable_uri={n_with_fetchable_uri} "
        f"→ {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
