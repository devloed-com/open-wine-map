"""Fetch the public reference datasets the Switzerland pipeline depends on.

Pipeline stage 00 (ch).

Sources:

1. **OFAG/BLW "Répertoire suisse des AOC"** (spine — the canonical list of
   Swiss wine AOCs). One trilingual (FR/DE/IT) PDF, 4 pages, ~376 KB,
   updated annually each 1 January. Published on `blw.admin.ch/fr/vin`.

   2026 edition URL:
   `https://www.blw.admin.ch/dam/fr/sd-web/bQQd5jj01Ivw/AOC_KUB-AOC_DOC_1er%20janvier%202026.pdf`

   Holds 63 entries (61 unique once intercantonal duplicates Vully VD/FR
   and Zürichsee ZH/SZ are deduped) across 26 cantons. Stage 02 parses
   it into the per-AOC spine record set.

   License: not explicitly stated on the page; treated as a public
   federal administrative document with attribution "© OFAG / BLW —
   Répertoire suisse des AOC vinicoles, 1er janvier 2026". Same
   justification as DE BLE §5 UrhG and ES MAPA.

2. **swisstopo swissBOUNDARIES3D 2026 GeoPackage** (commune polygons —
   the geometry-fallback layer). 2,121 communes + canton polygons +
   country boundary. ~150 MB zipped GPKG, EPSG:2056 (CH1903+ / LV95).

   Direct URL (via swisstopo STAC API):
   `https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/swissboundaries3d_2026-01/swissboundaries3d_2026-01_2056_5728.gpkg.zip`

   The Gemeinde polygon layer (`tlm_hoheitsgebiet`) carries `BFS_NUMMER`
   and `NAME` directly, so we don't need a separate BFS commune-register
   CSV. License: swisstopo OGD — open use, source attribution required.

3. **SITG Geneva — VIT_VIGNOBLE_AO** (parcel-precise GE AOC polygons,
   the cantonal-geoportal layer for Geneva). WFS endpoint, ~100 KB
   total for the 23 GE AOCs. License: SITG "accès libre".

   WFS URL: `https://vector.sitg.ge.ch/arcgis/services/VIT_VIGNOBLE_AO/MapServer/WFSServer`
   We download via OGR (GDAL) using the WFS driver, cached as GeoPackage.

4. **ASIT VD — Cadastre viticole** (commune-precise VD AOC polygons,
   the cantonal-geoportal layer for Vaud). Catalog entry at
   `viageo.ch/md/36bc73a7-5ac6-8364-25dc-cdb3f2c5895e`. The WFS layer
   name + endpoint require one-time metadata dereferencing — deferred
   to stage 04's geoportal_registry resolver (Phase 2 wiring); v1 uses
   swissBOUNDARIES3D commune-union for VD geometry.

Outputs:
- raw/ch/ofag/repertoire-aoc-{YYYY}.pdf            (canonical PDF)
- raw/ch/ofag/manifest.json                        (sha256 + license)
- raw/ch/swisstopo/swissboundaries3d_2026-01_2056_5728.gpkg
                                                   (extracted commune polygons)
- raw/ch/swisstopo/manifest.json                   (release + license)
- raw/ch/geoportals/sitg-vit-vignoble-ao.gpkg      (GE WFS dump)
- raw/ch/geoportals/manifest.json                  (per-layer license)
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OFAG_DIR = ROOT / "raw" / "ch" / "ofag"
SWISSTOPO_DIR = ROOT / "raw" / "ch" / "swisstopo"
GEOPORTAL_DIR = ROOT / "raw" / "ch" / "geoportals"

UA = (
    "open-wine-map/0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)

# OFAG répertoire — 2026 edition.
OFAG_PDF_URL = (
    "https://www.blw.admin.ch/dam/fr/sd-web/bQQd5jj01Ivw/"
    "AOC_KUB-AOC_DOC_1er%20janvier%202026.pdf"
)
OFAG_PDF_NAME = "repertoire-aoc-2026.pdf"
OFAG_LICENSE = (
    "© OFAG / BLW — Répertoire suisse des appellations d'origine "
    "contrôlée (AOC), 1er janvier 2026. Federal administrative "
    "document, public release with attribution."
)

# swissBOUNDARIES3D — 2026-01 edition, GeoPackage in EPSG:2056.
SWISSTOPO_RELEASE = "swissboundaries3d_2026-01"
SWISSTOPO_ZIP_NAME = f"{SWISSTOPO_RELEASE}_2056_5728.gpkg.zip"
SWISSTOPO_GPKG_NAME = f"{SWISSTOPO_RELEASE}_2056_5728.gpkg"
SWISSTOPO_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/"
    f"{SWISSTOPO_RELEASE}/{SWISSTOPO_ZIP_NAME}"
)
SWISSTOPO_LICENSE = (
    "© swisstopo — swissBOUNDARIES3D 2026-01. Open use, source "
    "attribution required (swisstopo OGD terms)."
)

# SITG VIT_VIGNOBLE_AO — Geneva cantonal cadastre of AOC perimeters.
SITG_VIT_VIGNOBLE_AO_LAYER_URL = (
    "https://vector.sitg.ge.ch/arcgis/services/VIT_VIGNOBLE_AO/MapServer/"
    "WFSServer?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=esri:VIT_VIGNOBLE_AO&srsName=EPSG:2056&outputFormat=GEOJSON"
)
SITG_GPKG_NAME = "sitg-vit-vignoble-ao.gpkg"
SITG_LICENSE = (
    "© SITG / République et Canton de Genève — accès libre, source à citer."
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _http_get(url: str, *, timeout: int = 300) -> requests.Response:
    print(f"[fetch] {url}", file=sys.stderr)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r


def fetch_ofag_pdf() -> dict:
    OFAG_DIR.mkdir(parents=True, exist_ok=True)
    dest = OFAG_DIR / OFAG_PDF_NAME
    if dest.exists():
        body = dest.read_bytes()
        print(f"[ofag] using cached {dest.relative_to(ROOT)} "
              f"({len(body):,} bytes)", file=sys.stderr)
    else:
        body = _http_get(OFAG_PDF_URL).content
        if not body.startswith(b"%PDF"):
            raise RuntimeError(
                f"OFAG fetch returned non-PDF content ({len(body)} bytes); "
                "URL may have rotated — check www.blw.admin.ch/fr/vin"
            )
        dest.write_bytes(body)
        print(f"[ofag] saved {dest.relative_to(ROOT)} ({len(body):,} bytes)",
              file=sys.stderr)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": OFAG_PDF_URL,
        "filename": OFAG_PDF_NAME,
        "sha256": _sha256(body),
        "bytes": len(body),
        "license": OFAG_LICENSE,
        "edition": "1er janvier 2026",
    }
    (OFAG_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def fetch_swissboundaries() -> dict:
    SWISSTOPO_DIR.mkdir(parents=True, exist_ok=True)
    gpkg_dest = SWISSTOPO_DIR / SWISSTOPO_GPKG_NAME
    zip_dest = SWISSTOPO_DIR / SWISSTOPO_ZIP_NAME
    if gpkg_dest.exists():
        body = gpkg_dest.read_bytes()
        print(f"[swisstopo] using cached {gpkg_dest.relative_to(ROOT)} "
              f"({len(body):,} bytes)", file=sys.stderr)
    else:
        zip_body = _http_get(SWISSTOPO_URL, timeout=900).content
        zip_dest.write_bytes(zip_body)
        print(f"[swisstopo] downloaded {SWISSTOPO_ZIP_NAME} "
              f"({len(zip_body):,} bytes)", file=sys.stderr)
        with zipfile.ZipFile(io.BytesIO(zip_body)) as zf:
            # Locate the .gpkg member inside (the zip may have a
            # subdirectory structure).
            gpkg_members = [n for n in zf.namelist() if n.endswith(".gpkg")]
            if not gpkg_members:
                raise RuntimeError(
                    f"No .gpkg found inside {SWISSTOPO_ZIP_NAME} "
                    f"(members: {zf.namelist()[:5]}…)"
                )
            inner = gpkg_members[0]
            with zf.open(inner) as src:
                gpkg_dest.write_bytes(src.read())
        # Free the zip — only the gpkg is needed downstream.
        zip_dest.unlink(missing_ok=True)
        body = gpkg_dest.read_bytes()
        print(f"[swisstopo] extracted {gpkg_dest.relative_to(ROOT)} "
              f"({len(body):,} bytes)", file=sys.stderr)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": SWISSTOPO_URL,
        "release": SWISSTOPO_RELEASE,
        "filename": SWISSTOPO_GPKG_NAME,
        "sha256": _sha256(body),
        "bytes": len(body),
        "crs": "EPSG:2056",
        "license": SWISSTOPO_LICENSE,
    }
    (SWISSTOPO_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def fetch_sitg_geneva() -> dict:
    """Fetch the SITG VIT_VIGNOBLE_AO WFS layer as GeoJSON-equivalent
    GeoPackage. ESRI ArcGIS WFS returns one giant GeoJSON in a single
    request; saving as .geojson keeps the dependency surface light
    (no GDAL/OGR needed for the fetch step)."""
    GEOPORTAL_DIR.mkdir(parents=True, exist_ok=True)
    geojson_dest = GEOPORTAL_DIR / "sitg-vit-vignoble-ao.geojson"
    if geojson_dest.exists():
        body = geojson_dest.read_bytes()
        print(f"[sitg] using cached {geojson_dest.relative_to(ROOT)} "
              f"({len(body):,} bytes)", file=sys.stderr)
    else:
        try:
            body = _http_get(SITG_VIT_VIGNOBLE_AO_LAYER_URL, timeout=180).content
        except requests.RequestException as e:
            print(f"[sitg] WARN GE WFS fetch failed: {e}; "
                  "Geneva geometry will fall back to swissBOUNDARIES3D commune-union",
                  file=sys.stderr)
            return {"status": "fetch-failed", "error": str(e)}
        if not body.lstrip().startswith(b"{"):
            print(f"[sitg] WARN unexpected response (first 80 bytes: {body[:80]!r})",
                  file=sys.stderr)
            return {"status": "unexpected-content"}
        geojson_dest.write_bytes(body)
        print(f"[sitg] saved {geojson_dest.relative_to(ROOT)} "
              f"({len(body):,} bytes)", file=sys.stderr)
    n_features = 0
    try:
        n_features = len(json.loads(body).get("features", []))
    except json.JSONDecodeError:
        pass
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layers": {
            "VIT_VIGNOBLE_AO": {
                "source_url": SITG_VIT_VIGNOBLE_AO_LAYER_URL,
                "filename": "sitg-vit-vignoble-ao.geojson",
                "sha256": _sha256(body),
                "bytes": len(body),
                "n_features": n_features,
                "crs": "EPSG:2056",
                "license": SITG_LICENSE,
            }
        },
    }
    (GEOPORTAL_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    fetch_ofag_pdf()
    fetch_swissboundaries()
    fetch_sitg_geneva()
    print("[done] stage 00 (ch) complete.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
