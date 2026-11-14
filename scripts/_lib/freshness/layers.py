"""Geometry tier — the administrative and vineyard layers the polygons are
drawn from, against the publishers' release listings.

  GISCO LAU / NUTS   datasets.json of the distribution API (the latest year)
  swisstopo          the STAC collection's items (swissboundaries3d_<yyyy-mm>)
  Bétard 2022        SNAPSHOT by design — handed to audit_betard_delta.py
  CAOP, ONS, IGN, cadastre, IET, SIGPAC, regional geoportals: no release
                     listing is fetched by stage 00 → UNVERIFIABLE with the
                     publisher page to check by hand
"""
from __future__ import annotations

import re

from . import CURRENT, NEWER, ROOT, SNAPSHOT, UNREACHABLE, UNVERIFIABLE, Http, Probe

GISCO_LAU = "https://gisco-services.ec.europa.eu/distribution/v2/lau/datasets.json"
GISCO_NUTS = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/datasets.json"
SWISSTOPO_STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissboundaries3d/items?limit=100"

HELD_LAU_YEAR = 2024       # raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip
HELD_NUTS_YEAR = 2024      # raw/gr/nuts/NUTS_RG_03M_2024_4326_LEVL_3.geojson, raw/nl/nuts/…LEVL_2
HAND_CHECKED = {
    "CAOP (DGT, Portugal)": ("raw/pt/caop/*CAOP2025.gpkg", "https://geo2.dgterritorio.gov.pt/caop/"),
    "ONS Open Geography (GB)": ("raw/gb/ons/*.geojson", "https://geoportal.statistics.gov.uk/"),
    "IGN AdminExpress communes (FR)": ("raw/ign/communes.geojson", "https://geo.api.gouv.fr/communes"),
    "IGN communes associées et déléguées (FR)": (
        "raw/ign/communes-associees-deleguees.geojson", "https://geo.api.gouv.fr/communes_associees_deleguees"),
    "INSEE commune movements (COG, FR)": ("raw/insee/v_mvt_commune.csv", "https://www.insee.fr/fr/information/2560452"),
    "Cadastre Etalab lieux-dits (FR)": ("raw/cadastre/lieux-dits/", "https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/"),
    "IET parroquias (Galicia)": ("raw/es/xunta/parroquias/", "https://abertos.xunta.gal/"),
    "SIGPAC (Catalonia, FEGA)": ("raw/es/sigpac/", "https://sigpac-hubcloud.es/"),
    "MAPA Zonas de Calidad Diferenciada: Vinos": ("raw/es/mapa/", "https://servicio.mapa.gob.es/"),
    "Italian regional geoportals": ("raw/it/regional-zones/", "scripts/_lib/it/zone_sources.py"),
    "SITG Geneva VIT_VIGNOBLE_AO": ("raw/ch/geoportals/", "https://ge.ch/sitg/"),
    "IVV Weinbaukartei (LU)": ("raw/lu/ivv/vineyards/", "https://data.public.lu/"),
}


def _held_swisstopo() -> str:
    for p in (ROOT / "raw" / "ch" / "swisstopo").glob("swissboundaries3d_*.gpkg"):
        m = re.search(r"swissboundaries3d_(\d{4}-\d{2})", p.name)
        if m:
            return m.group(1)
    return ""


def probe(http: Http) -> list[Probe]:
    out: list[Probe] = []
    for label, url, held in (("GISCO LAU", GISCO_LAU, HELD_LAU_YEAR), ("GISCO NUTS", GISCO_NUTS, HELD_NUTS_YEAR)):
        data = http.get_json(url)
        if isinstance(data, str):
            out.append(Probe(tier="geometry", source_key=label, url=url, verdict=UNREACHABLE, method="api", reason=data))
            continue
        years = sorted(int(m.group(1)) for k in data for m in [re.search(r"(\d{4})", k)] if m)
        latest = years[-1] if years else None
        if latest is None:
            out.append(Probe(tier="geometry", source_key=label, url=url, verdict=UNVERIFIABLE, method="api", reason="no dated dataset keys"))
        elif latest > held:
            out.append(Probe(tier="geometry", source_key=label, url=url, verdict=NEWER, held=str(held), upstream=str(latest), method="api",
                             reason=f"GISCO publishes {label} {latest}; the build draws {held}",
                             recipe="update the vintage in the stage-00 fetchers (es/gr/nl) and the per-country geometry indexes; re-run 04 and the geometry audits"))
        else:
            out.append(Probe(tier="geometry", source_key=label, url=url, verdict=CURRENT, held=str(held), upstream=str(latest), method="api"))
    data = http.get_json(SWISSTOPO_STAC)
    held = _held_swisstopo()
    if isinstance(data, str):
        out.append(Probe(tier="geometry", source_key="swissBOUNDARIES3D", url=SWISSTOPO_STAC, verdict=UNREACHABLE, method="api", reason=data))
    else:
        ids = sorted(m.group(1) for f in data.get("features") or [] for m in [re.search(r"swissboundaries3d_(\d{4}-\d{2})", f.get("id") or "")] if m)
        latest = ids[-1] if ids else ""
        if latest and held and latest > held:
            out.append(Probe(tier="geometry", source_key="swissBOUNDARIES3D", url=SWISSTOPO_STAC, verdict=NEWER, held=held, upstream=latest, method="api",
                             reason="swisstopo published a newer release", recipe="scripts/ch/00_fetch_data.py → 04"))
        else:
            out.append(Probe(tier="geometry", source_key="swissBOUNDARIES3D", url=SWISSTOPO_STAC, verdict=CURRENT if latest else UNVERIFIABLE, held=held, upstream=latest, method="api"))
    out.append(Probe(tier="geometry", source_key="Bétard 2022 EU_PDO.gpkg", url="https://doi.org/10.6084/m9.figshare.19352069",
                     verdict=SNAPSHOT, held="2022 (data cut Nov-2021)", method="-",
                     reason="a frozen research dataset: never newer by design; GIs registered or amended after the cut are listed by scripts/audit_betard_delta.py"))
    for label, (local, page) in HAND_CHECKED.items():
        out.append(Probe(tier="geometry", source_key=label, url=page, verdict=UNVERIFIABLE, held=local, method="-",
                         reason="no release listing is fetched for this layer; check the publisher page by hand when a boundary is questioned"))
    return out
