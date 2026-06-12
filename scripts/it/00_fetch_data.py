"""Fetch the public reference datasets the Italy pipeline depends on.

Pipeline stage 00 (it).

Sources:

1. **eAmbrosia EU register** (spine — list of IT wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=IT + productType=WINE + status=registered
   → ~540 wine GIs (DOP + IGP). The endpoint returns the full register
   (~6.5 MB, ~4000 GIs across all EU); we share the response with the
   ES + PT pipelines via separate per-country index files.

2. **MASAF disciplinari di produzione bundles** (~100 MB total). The
   ministry publishes 4 7-Zip archives at the master disciplinari page
   (`https://www.masaf.gov.it/.../IDPagina/4625`) containing every
   Italian wine DOP + IGT consolidated disciplinare. The bundles are
   the spine for stage 02f-MASAF: ~98 % of eAmbrosia IT wines (521 of
   531) match a PDF inside one of these archives.

3. **Figshare EU_PDO.gpkg** (Bétard et al. 2022, CC0, ~42 MB) — *already
   cached* by the ES pipeline at `raw/es/figshare/EU_PDO.gpkg`. Covers
   all EU PDOs including ~420 Italian DOPs (`PDO-IT-A*` file numbers).
   No new fetch — stage 04 reads the shared artifact via
   `ITPolygonIndex`.

4. **Eurostat GISCO LAU** — also cached by ES at
   `raw/es/gisco/lau-eu-2024-01m.shp.zip`. Country-agnostic (LAU2 covers
   Italian comuni); stage 04 filters to IT rows for IGT commune-list
   geometry resolution.

Outputs:
- raw/it/eambrosia/index.json — filtered IT-wine list with derived slug + kind
- raw/it/eambrosia/manifest.json — fetch metadata for the eAmbrosia call
- raw/it/masaf-disciplinari/bundles/*.7z — 4 disciplinari archives
- raw/it/masaf-disciplinari/bundles/manifest.json — per-bundle sha256 + URL

Each IT wine GI record carries:
- giIdentifier (e.g. EUGI00000003500) — internal EU id, unstable
- fileNumber (e.g. PDO-IT-A1234) — stable EU GI catalogue id
- name — protectedNames[0]
- slug — kebab-case derived from name (the unit of identity downstream)
- kind — DOP or IGP (Italian convention, same as ES/PT)
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
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.it.zone_sources import active_sources  # noqa: E402

OUT_DIR = ROOT / "raw" / "it" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

MASAF_BUNDLES_DIR = ROOT / "raw" / "it" / "masaf-disciplinari" / "bundles"
MASAF_BUNDLES_MANIFEST = MASAF_BUNDLES_DIR / "manifest.json"

# GIs the Commission has formally cancelled via an OJ-L Implementing
# Regulation but which linger in eAmbrosia as status="registered" (the
# register is not retroactively cleaned). Mirror of the AT
# `CANCELLED_PDOS` mechanism — filtered out of the index before the
# corpus is built, with the cancellation regulation cited so the
# decision is traceable. The audit surfaces this registry.
#
# The seven Abruzzo IGTs below were cancelled in spring 2026 as part of
# a regional consolidation into IGP "Terre Abruzzesi" (recognised 2020),
# which remains in the corpus. Keyed by giIdentifier (these old IGTs
# carry no PDO/PGI fileNumber in eAmbrosia). Verified 2026-05-30 via the
# per-IGP OJ-L cancellation regulations (euroconsulting.be mirror +
# disciplinare.it; eff. dates are the reclassification cut-offs).
CANCELLED_GIS: dict[str, dict] = {
    "EUGI00000003031": {
        "name": "Colli Aprutini",
        "regulation": "Commission Implementing Regulation (EU) 2026/558",
        "effective": "2026-04",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003040": {
        "name": "Colli del Sangro",
        "regulation": "Commission Implementing Regulation (EU) 2026/573",
        "effective": "2026-04-07",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003046": {
        "name": "Colline Frentane",
        "regulation": "Commission Implementing Regulation (EU) 2026/604",
        "effective": "2026-04-09",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003223": {
        "name": "Colline Pescaresi",
        "regulation": "Commission Implementing Regulation (EU) 2026/615",
        "effective": "2026-04-09",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003227": {
        "name": "Colline Teatine",
        "regulation": "Commission Implementing Regulation (EU) 2026/707",
        "effective": "2026-04-14",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003230": {
        "name": "del Vastese (o Histonium)",
        "regulation": "Commission Implementing Regulation (EU) 2026/703",
        "effective": "2026-04-13",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
    "EUGI00000003282": {
        "name": "Terre di Chieti",
        "regulation": "Commission Implementing Regulation (EU) 2026/708",
        "effective": "2026-04-14",
        "note": "Abruzzo IGT consolidation into IGP Terre Abruzzesi",
    },
}

# IDPagina/4625 on www.masaf.gov.it. Bundle URLs taken from the link
# blob on that page; the BLOB hashes are reasonably stable across
# revisions (each ServeAttachment URL is content-addressed by sha) but
# do rotate when the ministry republishes a bundle. If a fetch returns
# 404 or non-7z content, re-scrape the index page for the current
# attachment URL and update this list.
MASAF_BUNDLES = (
    {
        "key": "dop-AD",
        "label": "Disciplinari DOP (A-D)",
        "filename": "disciplinari-dop-AD.7z",
        "url": (
            "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/"
            "D/1%252F9%252Ff%252FD.01d31681c6712bc7da76/P/BLOB%3AID%3D4625/E/7z"
            "?mode=download"
        ),
    },
    {
        "key": "dop-EN",
        "label": "Disciplinari DOP (E-N)",
        "filename": "disciplinari-dop-EN.7z",
        "url": (
            "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/"
            "D/1%252F6%252F8%252FD.a7602712efcb761013e5/P/BLOB%3AID%3D4625/E/7z"
            "?mode=download"
        ),
    },
    {
        "key": "dop-OZ",
        "label": "Disciplinari DOP (O-Z)",
        "filename": "disciplinari-dop-OZ.7z",
        "url": (
            "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/"
            "D/1%252F3%252F3%252FD.8d7a8b212b2774f7eb37/P/BLOB%3AID%3D4625/E/7z"
            "?mode=download"
        ),
    },
    {
        "key": "igp",
        "label": "Disciplinari IGP / IGT",
        "filename": "disciplinari-igp.7z",
        "url": (
            "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/"
            "D/1%252F0%252F8%252FD.80c31f0c0a116455addf/P/BLOB%3AID%3D4625/E/7z"
            "?mode=download"
        ),
    },
)
MASAF_LICENSE = (
    "© Ministero dell'agricoltura, della sovranità alimentare e delle "
    "foreste (MASAF). Re-distribution permitted with attribution."
)

# Shared upstream artifacts already fetched by the ES pipeline. Asserted
# here so a fresh IT-only checkout fails loudly rather than silently
# producing geometry-less records downstream.
FIGSHARE_GPKG_PATH = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_LAU_PATH = ROOT / "raw" / "es" / "gisco" / "lau-eu-2024-01m.shp.zip"

# ISTAT official comune registry — comune ↔ 6-digit code ↔ provincia ↔
# regione. The code joins exactly to GISCO LAU (`GISCO_ID = IT_<code>`),
# so stage 04 can resolve each disciplinare's comune / provincia /
# regione description into a commune-precise polygon union instead of
# Bétard's overlapping whole-municipality polygons.
ISTAT_COMUNI_DIR = ROOT / "raw" / "it" / "istat"
ISTAT_COMUNI_URL = (
    "https://www.istat.it/storage/codici-unita-amministrative/"
    "Elenco-comuni-italiani.csv"
)
ISTAT_LICENSE = (
    "© ISTAT. Open data, CC BY 4.0 — reuse with attribution."
)

# Regional geoportal wine production-zone layers — official delimited
# DOC/DOCG/IGT boundaries, used by stage 04 in preference to Bétard.
# Registry + region to-do tracker: scripts/_lib/it/zone_sources.py.
REGIONAL_ZONES_DIR = ROOT / "raw" / "it" / "regional-zones"

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
    """eAmbrosia uses `PDO`/`PGI`; Italian convention (same as ES/PT) is
    `DOP`/`IGP`."""
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


def fetch_masaf_bundles() -> dict:
    """Download the 4 MASAF disciplinari archives (~100 MB total),
    caching by sha256 — re-runs are a no-op unless MASAF republishes
    a bundle. Returns a manifest dict written alongside the cache."""
    MASAF_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    if MASAF_BUNDLES_MANIFEST.exists():
        try:
            existing = json.loads(MASAF_BUNDLES_MANIFEST.read_text(encoding="utf-8")).get("bundles", {})
        except (ValueError, OSError):
            existing = {}

    by_key: dict[str, dict] = {}
    for spec in MASAF_BUNDLES:
        key = spec["key"]
        dest = MASAF_BUNDLES_DIR / spec["filename"]
        cached = existing.get(key) or {}
        if dest.exists() and cached.get("sha256"):
            body = dest.read_bytes()
            sha = hashlib.sha256(body).hexdigest()
            if sha == cached["sha256"]:
                by_key[key] = {**cached, "from_cache": True}
                print(
                    f"[masaf] cache hit  {spec['filename']:30s} "
                    f"({len(body):>10,} bytes)",
                    file=sys.stderr,
                )
                continue
        print(f"[masaf] fetch     {spec['url']}", file=sys.stderr)
        resp = requests.get(
            spec["url"],
            headers={"User-Agent": UA},
            timeout=300,
            allow_redirects=True,
        )
        resp.raise_for_status()
        body = resp.content
        if not body.startswith(b"7z\xbc\xaf'\x1c"):
            raise RuntimeError(
                f"MASAF returned non-7z content for {key} "
                f"({len(body)} bytes, ct={resp.headers.get('content-type')}). "
                "URL may have rotated; re-scrape IDPagina/4625."
            )
        dest.write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()
        by_key[key] = {
            "label": spec["label"],
            "filename": spec["filename"],
            "url": spec["url"],
            "sha256": sha,
            "bytes": len(body),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "from_cache": False,
        }
        print(
            f"[masaf] saved     {spec['filename']:30s} "
            f"({len(body):>10,} bytes, sha256={sha[:12]}…)",
            file=sys.stderr,
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_page": "https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/4625",
        "license": MASAF_LICENSE,
        "bundles": by_key,
    }
    MASAF_BUNDLES_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def assert_shared_artifacts() -> None:
    missing = []
    if not FIGSHARE_GPKG_PATH.exists():
        missing.append(str(FIGSHARE_GPKG_PATH.relative_to(ROOT)))
    if not GISCO_LAU_PATH.exists():
        missing.append(str(GISCO_LAU_PATH.relative_to(ROOT)))
    if missing:
        print(
            "[error] shared artifacts missing — run scripts/es/00_fetch_data.py "
            f"first to populate: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)


def fetch_istat_comuni() -> dict:
    """Download the ISTAT official comune registry (comune ↔ code ↔
    provincia ↔ regione). One ~1 MB CSV; re-fetched every run (ISTAT
    revises it as comuni merge — the file carries a Gebietsstand date)."""
    ISTAT_COMUNI_DIR.mkdir(parents=True, exist_ok=True)
    dest = ISTAT_COMUNI_DIR / "Elenco-comuni-italiani.csv"
    print(f"[istat] fetch {ISTAT_COMUNI_URL}", file=sys.stderr)
    r = requests.get(ISTAT_COMUNI_URL, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    body = r.content
    if b";" not in body[:200]:
        raise RuntimeError(
            f"ISTAT returned non-CSV content ({len(body)} bytes) — URL rotated."
        )
    dest.write_bytes(body)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": ISTAT_COMUNI_URL,
        "license": ISTAT_LICENSE,
        "bytes": len(body),
    }
    (ISTAT_COMUNI_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[istat] saved Elenco-comuni-italiani.csv ({len(body):,} bytes)",
          file=sys.stderr)
    return manifest


def fetch_ckan_shapefiles(region: str, spec: dict) -> dict:
    """Harvest a CKAN per-appellation shapefile catalog (Umbria): enumerate
    the catalog, then download + extract each "Zona/Zone di produzione vin…"
    dataset's `.zip`/`.7z` shapefile into
    `raw/it/regional-zones/<extract_dir>/<dataset>/`.

    `.zip` is extracted with the stdlib; `.7z` needs `py7zr` (the `bootstrap`
    dependency group). py7zr is imported lazily — if it is absent the `.7z`
    datasets are skipped with a loud warning (the `.zip` ones still harvest),
    mirroring the Playwright-gated WAF bootstrap. Cached by presence of an
    extracted `.shp`; delete the dataset dir to re-fetch."""
    extract_root = REGIONAL_ZONES_DIR / spec.get("extract_dir", region)
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        import py7zr
        have_7z = True
    except ImportError:
        py7zr = None
        have_7z = False

    datasets: dict[str, dict] = {}
    for q in spec.get("ckan_queries") or ["vini"]:
        url = f"{spec['ckan_base']}?q={quote(q)}&rows=500"
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"},
                         timeout=120)
        r.raise_for_status()
        for p in r.json().get("result", {}).get("results", []):
            title = p.get("title") or ""
            if not title.lower().startswith(
                ("zona di produzione vin", "zone di produzione vin")
            ):
                continue
            res = next((rs for rs in p.get("resources", [])
                        if (rs.get("url") or "").lower().endswith((".zip", ".7z"))), None)
            if res:
                datasets[p["name"]] = {"title": title, "url": res["url"]}

    files: list[dict] = []
    skipped_7z: list[str] = []
    for name, meta in sorted(datasets.items()):
        url = meta["url"]
        is_7z = url.lower().endswith(".7z")
        dest_dir = extract_root / name
        if list(dest_dir.glob("**/*.shp")):
            print(f"[zones] cache hit  {region}/{name}", file=sys.stderr)
            files.append({"dataset": name, "title": meta["title"], "url": url,
                          "from_cache": True})
            continue
        if is_7z and not have_7z:
            skipped_7z.append(name)
            continue
        print(f"[zones] fetch {region}/{name}", file=sys.stderr)
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=300)
        resp.raise_for_status()
        archive = extract_root / (name + (".7z" if is_7z else ".zip"))
        archive.write_bytes(resp.content)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            if is_7z:
                with py7zr.SevenZipFile(archive) as z:
                    z.extractall(dest_dir)
            else:
                with zipfile.ZipFile(archive) as z:
                    z.extractall(dest_dir)
        finally:
            archive.unlink(missing_ok=True)
        print(f"[zones] saved {region}/{name} ({len(resp.content):,} b)", file=sys.stderr)
        files.append({"dataset": name, "title": meta["title"], "url": url,
                      "from_cache": False})

    if skipped_7z:
        print(
            f"[zones] WARNING py7zr missing — skipped {len(skipped_7z)} .7z "
            f"{region} datasets; install the `bootstrap` group to harvest them: "
            f"{', '.join(skipped_7z)}",
            file=sys.stderr,
        )
    return {"licence": spec.get("licence", ""),
            "attribution": spec.get("attribution", ""),
            "fetch_type": "ckan_shapefiles",
            "files": files, "skipped_7z": skipped_7z}


def fetch_regional_zones() -> dict:
    """Download each active regional wine production-zone layer. A region
    may have several layers (DOC / DOCG / IGT). Cached by presence —
    re-runs skip an already-downloaded file; delete the file to re-fetch."""
    REGIONAL_ZONES_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict] = {}
    for region, spec in active_sources().items():
        if spec.get("fetch_type") == "ckan_shapefiles":
            out[region] = fetch_ckan_shapefiles(region, spec)
            continue
        files = []
        for layer in spec["layers"]:
            dest = REGIONAL_ZONES_DIR / layer["filename"]
            if dest.exists():
                files.append({"filename": layer["filename"],
                              "bytes": dest.stat().st_size, "from_cache": True})
                print(f"[zones] cache hit  {region}/{layer['filename']} "
                      f"({dest.stat().st_size:,} b)", file=sys.stderr)
                continue
            print(f"[zones] fetch {region}/{layer['filename']}", file=sys.stderr)
            r = requests.get(layer["url"], headers={"User-Agent": UA}, timeout=300)
            r.raise_for_status()
            dest.write_bytes(r.content)
            files.append({"filename": layer["filename"], "bytes": len(r.content),
                          "from_cache": False})
            print(f"[zones] saved {region}/{layer['filename']} "
                  f"({len(r.content):,} b)", file=sys.stderr)
        out[region] = {"licence": spec.get("licence", ""),
                       "attribution": spec.get("attribution", ""),
                       "files": files}
    (REGIONAL_ZONES_DIR / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regions": out,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert_shared_artifacts()
    full, etag = fetch_list()
    it_wines_all = [
        g for g in full
        if "IT" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    it_wines = [g for g in it_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(it_wines_all) - len(it_wines)

    it_registered = it_wines
    it_wines = [g for g in it_registered if g.get("giIdentifier") not in CANCELLED_GIS]
    n_skipped_cancelled = len(it_registered) - len(it_wines)
    for gi in (g.get("giIdentifier") for g in it_registered):
        meta = CANCELLED_GIS.get(gi)
        if meta:
            print(
                f"[filter] cancelled: {gi} {meta['name']} — {meta['regulation']} "
                f"(eff. {meta['effective']})",
                file=sys.stderr,
            )

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in it_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside IT wines:",
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

    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "source_url": EAMBROSIA_LIST_URL,
        "license": LICENSE,
        "etag": etag,
        "n_total_eu": len(full),
        "n_it_wines": len(projected),
        "n_skipped_applied": n_skipped_applied,
        "n_skipped_cancelled": n_skipped_cancelled,
        "cancelled_gis": CANCELLED_GIS,
        "by_kind": by_kind,
        "n_slug_collisions": len(collisions),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] eAmbrosia: total_eu={len(full)} it_wines={len(projected)} "
        f"by_kind={by_kind} → {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )

    masaf = fetch_masaf_bundles()
    total_bytes = sum(b.get("bytes", 0) for b in masaf["bundles"].values())
    print(
        f"[done] MASAF: {len(masaf['bundles'])} bundles ({total_bytes:,} bytes) "
        f"→ {MASAF_BUNDLES_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )

    fetch_istat_comuni()
    print(
        f"[done] ISTAT comuni registry → {ISTAT_COMUNI_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )

    zones = fetch_regional_zones()
    print(
        f"[done] regional zone layers: {len(zones)} active "
        f"→ {REGIONAL_ZONES_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
