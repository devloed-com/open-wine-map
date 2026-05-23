"""Regional geoportal sources for Italian wine production-zone polygons.

The commune-precision strategy for Italy: where a region publishes an
official, licence-clear GIS layer of its DOC/DOCG/IGT production-zone
boundaries, use that polygon directly; otherwise fall back to Bétard
2022 (`EU_PDO.gpkg`, whole-municipality resolution). Official zone
layers are the real delimited boundaries — consortium-validated —
rather than a municipality approximation.

This file is the harvest registry **and** the region to-do tracker.
Each entry has a `status`:
  - "active"   — endpoints + schema known; stage 00 fetches it, stage 04 uses it.
  - "todo"     — a layer exists (per the 2026-05-22 audit) but harvesting it
                 still needs work (bespoke fetch, unreachable endpoint…).
  - "fallback" — no open layer found; the region's wines stay on Bétard.

Per-region fields:
  - `name_field`        — the layer attribute carrying the appellation name.
  - `strip_kind_prefix` — drop a leading "DOC/DOCG/IGT " from the name
                          before matching (some layers prefix it).
  - `layers`            — list of `{url, filename, layer?}` to download;
                          `layer` names the sub-layer for multi-layer files.

Only "active" entries are fetched and indexed.
"""

from __future__ import annotations

_VENETO_WFS = (
    "https://idt2-geoserver.regione.veneto.it/geoserver/wfs"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames={t}&outputFormat=application/json"
)
_LAZIO_WFS = (
    "https://geoportale.regione.lazio.it/geoserver/wfs"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames={t}&outputFormat=application/json"
)
_LOMBARDIA_ARCGIS = (
    "https://www.cartografia.servizirl.it/expo/rest/services/gpt/"
    "Aree_Pregio_Viti_Vinicolo/MapServer/{i}/query"
    "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326"
    "&resultRecordCount=5000&f=geojson"
)


ZONE_SOURCES: dict[str, dict] = {
    "piemonte": {
        "status": "active",
        "label": "Regione Piemonte — Aree di produzione dei vini DOC/DOCG",
        "licence": "CC-BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Regione Piemonte — Direzione Agricoltura e Cibo",
        "name_field": "denominazi",
        "layers": [{
            "url": (
                "https://www.datigeo-piem-download.it/direct/Geoportale/"
                "RegionePiemonte/AGRICOLTURA/Aree_vini_DOC_DOCG/"
                "aree_produzione_vini.zip"
            ),
            "filename": "piemonte.zip",
        }],
    },
    "veneto": {
        "status": "active",
        "label": "Regione Veneto — ZONE DOC / DOCG / IGT",
        "licence": "IODL 2.0 / CC-BY",
        "attribution": "Regione del Veneto",
        "name_field": "denominazi",
        "layers": [
            {"url": _VENETO_WFS.format(t="rv:c1016231_doc"), "filename": "veneto-doc.geojson"},
            {"url": _VENETO_WFS.format(t="rv:c1016271_docg"), "filename": "veneto-docg.geojson"},
            {"url": _VENETO_WFS.format(t="rv:c1016261_igt"), "filename": "veneto-igt.geojson"},
        ],
    },
    "lazio": {
        "status": "active",
        "label": "Regione Lazio — Vini DOC / DOCG / IGT (ARSIAL)",
        "licence": "CC-BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Regione Lazio — ARSIAL",
        "name_field": "denominazi",
        "layers": [
            {"url": _LAZIO_WFS.format(t="geonode:Vini_DOC_Regione_Lazio"),
             "filename": "lazio-doc.geojson"},
            {"url": _LAZIO_WFS.format(t="geonode:Vini_DOCG_Regione_Lazio"),
             "filename": "lazio-docg.geojson"},
            {"url": _LAZIO_WFS.format(t="geonode:Vini_IGT_Regione_Lazio"),
             "filename": "lazio-igt.geojson"},
        ],
    },
    "lombardia": {
        "status": "active",
        "label": "Regione Lombardia — Aree di pregio vitivinicolo",
        "licence": "CC-BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Regione Lombardia",
        "name_field": "NOME_ZONA",
        "strip_kind_prefix": True,  # NOME_ZONA is "DOC <name>" / "DOCG <name>"
        "layers": [
            {"url": _LOMBARDIA_ARCGIS.format(i=0), "filename": "lombardia-docg.geojson"},
            {"url": _LOMBARDIA_ARCGIS.format(i=1), "filename": "lombardia-doc.geojson"},
            {"url": _LOMBARDIA_ARCGIS.format(i=2), "filename": "lombardia-igt.geojson"},
        ],
    },
    "toscana": {
        "status": "active",
        "label": "Regione Toscana — Zone di produzione vitivinicola DOP/IGP",
        "licence": "CC-BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Regione Toscana — GEOscopio",
        "name_field": "NOM_ZON",
        "layers": [{
            "url": (
                "https://www502.regione.toscana.it/geoscopio/download/"
                "tematici/zone_prod_vini/zone_prod_vini.zip"
            ),
            "filename": "toscana.zip",
            "layer": "zo_vin_nom_zon_2026_05",  # appellation-name zones (not subzones)
        }],
    },
    # ─────────────── to-do: layer exists, harvesting still needs work ───────────────
    "umbria": {
        "status": "todo",
        "label": "Regione Umbria — Zone di produzione vini (per-appellation)",
        "licence": "CC-BY 4.0",
        "note": "dati.regione.umbria.it CKAN — ~23 separate per-appellation "
                "datasets, each a .7z shapefile. Needs a CKAN-enumerate + "
                "7z-extract fetch (api/3/action/package_search?q=vini).",
    },
    "puglia": {
        "status": "todo",
        "label": "Regione Puglia — Vini DOC/DOCG/IGP (SIT Puglia)",
        "licence": "IODL 2.0",
        "note": "Endpoint not reachable as of 2026-05-22 — the SIT Puglia "
                "WFS/ArcGIS hosts probed returned 404 / empty; the cartography "
                "page is login-gated. Needs the live WFS layer name.",
    },
    # ─────────────── fallback: no open zone layer — wines stay on Bétard ───────────────
    "abruzzo": {
        "status": "fallback",
        "label": "Regione Abruzzo — Carta zone vitivinicole DOC",
        "licence": "custom 'Regione Abruzzo' — unconfirmed; portal SSL cert expired",
        "note": "Layer exists (ArcGIS WMS) but licence unverifiable — Bétard for now.",
    },
    "campania": {
        "status": "fallback",
        "label": "Regione Campania — Aree produzione vini DOC/DOCG",
        "licence": "unconfirmed",
        "note": "Layer exists on sit2.regione.campania.it but the dataset page "
                "404s and the licence is unconfirmed — Bétard for now.",
    },
}


def active_sources() -> dict[str, dict]:
    return {k: v for k, v in ZONE_SOURCES.items() if v.get("status") == "active"}
