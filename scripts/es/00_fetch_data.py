"""Fetch the public reference datasets the Spain pipeline depends on.

Pipeline stage 00 (es).

Sources:

1. **eAmbrosia EU register** (spine — list of ES wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=ES + productType=WINE + status=registered
   → 149 wine GIs (106 DOP + 43 IGP). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU).

2. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB)
   `https://ndownloader.figshare.com/files/35955185` (Figshare article 19312094
   in collection 5877659). Wine PDO polygons at commune precision, EPSG:3035,
   single-table GeoPackage with `PDOid` + `geometry`. Covers 99 of the 106 ES
   PDOs (all pre-Nov-2021 PDOs); newer PDOs and all 43 IGPs are absent and
   need a fallback. Snapshot is frozen at Nov 2021 — a strict improvement
   over MAPA's frozen-2014 shapefile, which is also gated for non-browser
   clients (manual download path documented in CLAUDE.md).

3. **CNIG Líneas Límite Municipales** — gated for non-browser clients;
   document manual download in CLAUDE.md (Phase 4 work).

Outputs:
- raw/es/eambrosia/index.json — filtered ES-wine list with derived slug + kind
- raw/es/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
- raw/es/figshare/EU_PDO.gpkg — Bétard 2022 wine-PDO polygons
- raw/es/figshare/manifest.json — fetch metadata + license + sha for the gpkg

Each ES wine GI record carries:
- giIdentifier (e.g. EUGI00000003061) — internal EU id, unstable
- fileNumber (e.g. PDO-ES-A0117) — stable EU GI catalogue id
- name — protectedNames[0]
- slug — kebab-case derived from name (the unit of identity downstream)
- kind — DOP or IGP
- producer_group — {name, url, email, address} for sidebar attribution
- publications — array of {text, uri} OJ citations (input to stage 01)
- raw — the full eAmbrosia record (preserved for traceability)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.es.zones import (  # noqa: E402
    MAPA_LICENCE,
    MAPA_ZONES_FILE,
    MAPA_ZONES_URL,
)

OUT_DIR = ROOT / "raw" / "es" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# MAPA national wine production-zone polygons — the preferred ES
# geometry source (stage 04), consumed via scripts/_lib/es/zones.py.
MAPA_ZONES_DIR = ROOT / "raw" / "es" / "mapa-zonas"

FIGSHARE_OUT_DIR = ROOT / "raw" / "es" / "figshare"
FIGSHARE_GPKG_PATH = FIGSHARE_OUT_DIR / "EU_PDO.gpkg"
FIGSHARE_MANIFEST_PATH = FIGSHARE_OUT_DIR / "manifest.json"
FIGSHARE_GPKG_URL = "https://ndownloader.figshare.com/files/35955185"
FIGSHARE_ARTICLE = "https://figshare.com/articles/dataset/19312094"
FIGSHARE_LICENSE = "CC0 (public domain). Bétard et al. 2022."

# Eurostat GISCO LAU dataset — covers all EU local administrative units
# (LAU2 = municipios in Spain, communes in France, comuni in Italy, etc.).
# We fetch the SHP zip (smallest of the three formats Eurostat publishes
# at 1:1M scale). At the EU level the file is 116 MB; stage 04 will read
# and filter to just ES rows, but we don't carve out an ES-only subset
# in stage 00 — keeping the upstream artifact intact makes adding more
# countries cheap.
GISCO_OUT_DIR = ROOT / "raw" / "es" / "gisco"
GISCO_LAU_PATH = GISCO_OUT_DIR / "lau-eu-2024-01m.shp.zip"
GISCO_LAU_MANIFEST_PATH = GISCO_OUT_DIR / "manifest.json"
GISCO_LAU_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/download/"
    "ref-lau-2024-01m.shp.zip"
)
GISCO_LICENSE = (
    "© European Union, Eurostat / GISCO. Free reuse with attribution."
)

# SIGPAC (Spanish parcel-level cadastre) for selected Catalan comarques.
# Used by stage 04 to compute parcel-precision geometry for wines that
# share communes with neighbouring DOPs (Priorat ↔ Montsant) — the
# pliegos split shared communes at SIGPAC-polygon level.
# URL catalog: scripts/_lib/es/sigpac_catalonia_urls.json
SIGPAC_OUT_DIR = ROOT / "raw" / "es" / "sigpac"
SIGPAC_MANIFEST_PATH = SIGPAC_OUT_DIR / "manifest.json"
SIGPAC_URLS_JSON = ROOT / "scripts" / "_lib" / "es" / "sigpac_catalonia_urls.json"
SIGPAC_LICENSE = (
    "© Generalitat de Catalunya / DARP, SIGPAC. Free reuse with "
    "attribution. Source: analisi.transparenciacatalunya.cat."
)
# v1 fetches only the comarques whose municipios are claimed by ES wine
# DOPs in our corpus AND whose pliegos use polygon-level inclusion
# patterns (Priorat ↔ Montsant). Adding more comarques later is one
# entry in this list.
SIGPAC_COMARCA_CODIS = (
    "29",  # Priorat (Falset, El Molar, … — covers Priorat DOQ + most of Montsant)
)

EAMBROSIA_LIST_URL = (
    "https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications"
)
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)
LICENSE = (
    "© European Union, eAmbrosia register. Reuse authorised with attribution."
)


def slugify(s: str) -> str:
    """Same shape as scripts/02_extract_cahiers.py:slug — strip diacritics,
    keep [A-Za-z0-9], collapse separators to single hyphens, lowercase."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; Spanish convention is `DOP`/`IGP`. We render
    the Spanish form because the surface UI uses it."""
    return {"PDO": "DOP", "PGI": "IGP"}.get(gi_type, gi_type)


def project(rec: dict) -> dict:
    """Reduce one full eAmbrosia record to the fields downstream stages need.
    The full record is retained under `raw` for traceability + future use
    (transcriptions, sustainability reports, control authorities, ...)."""
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
    """Returns the full eAmbrosia GI list + the response ETag (for cache
    validation on the next run, when the API supports it)."""
    print(f"[fetch] {EAMBROSIA_LIST_URL}", file=sys.stderr)
    r = requests.get(
        EAMBROSIA_LIST_URL,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json(), r.headers.get("etag") or ""


def _fetch_binary_with_manifest(
    *,
    label: str,
    url: str,
    out_path: Path,
    manifest_path: Path,
    extra_manifest: dict,
) -> None:
    """Download a binary artifact (gpkg, zip, …) once and cache by sha. Re-uses
    the cached file as long as the on-disk sha matches the manifest's recorded
    sha. To force re-fetch, delete the artifact OR the manifest. Same idiom
    used for FR `parcellaire.zip` style artifacts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
        if existing.get("sha256"):
            cur_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            if cur_sha == existing["sha256"]:
                print(f"[{label}] cached → {out_path.relative_to(ROOT)}",
                      file=sys.stderr)
                return
    print(f"[{label}] fetching {url}", file=sys.stderr)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=600)
    r.raise_for_status()
    out_path.write_bytes(r.content)
    sha = hashlib.sha256(r.content).hexdigest()
    manifest_path.write_text(json.dumps({
        **extra_manifest,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": url,
        "bytes": len(r.content),
        "sha256": sha,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[{label}] {len(r.content) // (1<<20)} MB → "
        f"{out_path.relative_to(ROOT)}",
        file=sys.stderr,
    )


def fetch_figshare_gpkg() -> None:
    """Bétard 2022 EU_PDO.gpkg — wine PDO polygons (CC0, ~42 MB)."""
    _fetch_binary_with_manifest(
        label="figshare",
        url=FIGSHARE_GPKG_URL,
        out_path=FIGSHARE_GPKG_PATH,
        manifest_path=FIGSHARE_MANIFEST_PATH,
        extra_manifest={
            "article_url": FIGSHARE_ARTICLE,
            "license": FIGSHARE_LICENSE,
        },
    )


def fetch_sigpac_comarques() -> None:
    """Fetch SIGPAC parcel-level data for the curated Catalan comarques
    (see SIGPAC_COMARCA_CODIS). Each comarca is a ~50 MB zip → ~130 MB
    gpkg after extraction. Skipped on cache hit (sha-pinned)."""
    if not SIGPAC_URLS_JSON.exists():
        print(f"[sigpac] URL catalog missing at {SIGPAC_URLS_JSON} — skipping",
              file=sys.stderr)
        return
    catalog = json.loads(SIGPAC_URLS_JSON.read_text(encoding="utf-8"))
    SIGPAC_OUT_DIR.mkdir(parents=True, exist_ok=True)
    overall: dict[str, dict] = {}
    if SIGPAC_MANIFEST_PATH.exists():
        try:
            overall = json.loads(SIGPAC_MANIFEST_PATH.read_text(encoding="utf-8")).get("comarques", {})
        except (ValueError, OSError):
            overall = {}
    for codi in SIGPAC_COMARCA_CODIS:
        entry = catalog.get(codi)
        if entry is None:
            print(f"[sigpac] comarca {codi}: not in URL catalog", file=sys.stderr)
            continue
        url = entry["url_2025_gpkg"]
        zip_name = entry["filename"]
        zip_path = SIGPAC_OUT_DIR / zip_name
        # Manifest entry per comarca for sha tracking.
        sub_manifest_path = SIGPAC_OUT_DIR / f"manifest-{codi}.json"
        _fetch_binary_with_manifest(
            label=f"sigpac/{codi}",
            url=url,
            out_path=zip_path,
            manifest_path=sub_manifest_path,
            extra_manifest={
                "comarca": entry["comarca"],
                "comarca_codi": codi,
                "license": SIGPAC_LICENSE,
            },
        )
        # Unzip the gpkg. The inner gpkg filename comes from the zip's
        # own listing (e.g. SIGPAC_29_Priorat.gpkg — without year).
        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            inner_names = zf.namelist()
            gpkg_inner = next(
                (n for n in inner_names if n.endswith(".gpkg")),
                None,
            )
            if gpkg_inner is None:
                print(f"[sigpac/{codi}] no .gpkg in zip", file=sys.stderr)
                continue
            gpkg_path = SIGPAC_OUT_DIR / gpkg_inner
            if not gpkg_path.exists():
                zf.extract(gpkg_inner, SIGPAC_OUT_DIR)
                print(f"[sigpac/{codi}] extracted → {gpkg_path.relative_to(ROOT)}",
                      file=sys.stderr)
        overall[codi] = {
            "comarca": entry["comarca"],
            "zip": zip_name,
            "gpkg": gpkg_inner,
        }
    SIGPAC_MANIFEST_PATH.write_text(json.dumps({
        "license": SIGPAC_LICENSE,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "analisi.transparenciacatalunya.cat (Generalitat de Catalunya)",
        "comarques": overall,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def fetch_gisco_lau() -> None:
    """Eurostat GISCO LAU 1:1M shapefile — EU local administrative units
    including Spanish municipios (~116 MB). Used by stage 04 to resolve
    commune-list-union polygons for ES wines (and subzonas) that lack a
    direct shapefile in the Figshare PDO dataset.

    The download is a "zip-of-zips" — the outer zip contains three inner
    zips, one per CRS (3035 EU-LAEA, 3857 Web Mercator, 4326 WGS84). We
    extract the EU-LAEA inner zip to a flat shapefile bundle so stage 04
    can read it through pyogrio without nested-zip gymnastics."""
    _fetch_binary_with_manifest(
        label="gisco",
        url=GISCO_LAU_URL,
        out_path=GISCO_LAU_PATH,
        manifest_path=GISCO_LAU_MANIFEST_PATH,
        extra_manifest={"license": GISCO_LICENSE},
    )
    # Unpack the EU-LAEA (EPSG:3035) inner zip — same CRS as Figshare.
    import zipfile
    inner_zip_name = "LAU_RG_01M_2024_3035.shp.zip"
    flat_zip_path = GISCO_OUT_DIR / inner_zip_name
    if not flat_zip_path.exists():
        with zipfile.ZipFile(GISCO_LAU_PATH) as outer:
            outer.extract(inner_zip_name, GISCO_OUT_DIR)
        print(f"[gisco] extracted inner zip → {flat_zip_path.relative_to(ROOT)}",
              file=sys.stderr)


def fetch_mapa_zones() -> None:
    """MAPA national wine production-zone polygons — "Zonas de Calidad
    Diferenciada: Vinos". Fetched via the OGC API-Features endpoint as
    GeoJSON (the `.aspx` shapefile download is reCAPTCHA-gated)."""
    _fetch_binary_with_manifest(
        label="mapa-zones",
        url=MAPA_ZONES_URL,
        out_path=MAPA_ZONES_DIR / MAPA_ZONES_FILE,
        manifest_path=MAPA_ZONES_DIR / "manifest.json",
        extra_manifest={"license": MAPA_LICENCE},
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetch_figshare_gpkg()
    fetch_gisco_lau()
    fetch_sigpac_comarques()
    fetch_mapa_zones()
    full, etag = fetch_list()
    es_wines_all = [
        g for g in full
        if "ES" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    # status=applied entries are pending registrations (e.g. Viñedos de Álava
    # 2024 carve-out from Rioja Alavesa) or stale duplicates of a registered
    # GI (Tharsys PDO-ES-02086 vs. PDO-ES-02980). They have no publications
    # to feed stage 01 and would clobber slugs, so we skip them. They reappear
    # automatically on the next run if they get registered.
    es_wines = [g for g in es_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(es_wines_all) - len(es_wines)

    # Slug collisions inside ES wines would clobber on disk in stage 01/02.
    # Pre-flight check: warn loudly so a curator can disambiguate (same idiom
    # as the FR stage 02 _disambiguate_slugs guard).
    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in es_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside ES wines:",
            file=sys.stderr,
        )
        for s, ps in collisions.items():
            ids = ", ".join(p["fileNumber"] or p["giIdentifier"] for p in ps)
            print(f"  {s}: {ids}", file=sys.stderr)

    # Sort by name for stable output ordering across runs (eAmbrosia returns
    # in registration-date order, which is noisy under amendments).
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

    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_es_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} es_wines={len(projected)} "
        f"by_kind={by_kind} → {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
