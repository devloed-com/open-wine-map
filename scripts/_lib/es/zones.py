"""Official MAPA wine-zone geometry for Spanish wine GIs.

MAPA (Ministerio de Agricultura, Pesca y Alimentación) publishes a
single national GIS layer of every Spanish wine quality figure's
production-zone polygon — "Zonas de Calidad Diferenciada: Vinos",
96 zones (DO, DOCa, VCIG, Vino de Pago). It is the preferred geometry
source for Spain, used by stage 04 in front of the Bétard 2022
fallback — real delimited zone boundaries rather than Bétard's
whole-municipality approximation.

Source: the MAPA OGC API-Features endpoint (the `.aspx` shapefile
download is reCAPTCHA-gated; the API is open GeoJSON).
Licence: the MAPA IDE metadata record declares CC BY 4.0 ("Sin
limitaciones al acceso público"); attribution "© Ministerio de
Agricultura, Pesca y Alimentación (MAPA)". (The download landing page
carries softer non-commercial wording — see CURATOR_TODO; the
machine-readable metadata is the citable licence and the project is
non-commercial regardless.)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

MAPA_ZONES_URL = (
    "https://wmts.mapama.gob.es/sig-api/ogc/features/v1/collections/"
    "alimentacion:CDZ_Vinos/items?f=json&limit=1000"
)
MAPA_ZONES_FILE = "calidaddiferenciada_vinos.geojson"
MAPA_LICENCE = "CC BY 4.0 — © Ministerio de Agricultura, Pesca y Alimentación (MAPA)"

_NAME_FIELD = "zon_ds_nombre"

# Spanish/Catalan/Galician connector words dropped before matching, so a
# DO name spelled slightly differently between eAmbrosia and the MAPA
# layer still joins. The distinguishing words remain.
_CONNECTORS = frozenset({
    "de", "del", "la", "las", "los", "el", "y", "e", "da", "do", "i",
})


def _norm(s: str) -> str:
    """Diacritics + punctuation stripped, connector words dropped,
    lowercased — applied identically to the eAmbrosia name and the
    MAPA `zon_ds_nombre` field."""
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return "".join(w for w in s.split() if w not in _CONNECTORS)


# eAmbrosia name → MAPA `zon_ds_nombre` for figures the two registers
# spell differently: regional-language vs Castilian forms (Empordà /
# Ampurdán, Priorat / Priorato), the bilingual Txakoli names, and the
# "Pago …" / "VC …" prefixes MAPA adds. Verified by eyeballing the 96
# MAPA names against the unmatched ES corpus.
_NAME_ALIAS: dict[str, str] = {
    "Priorat": "Priorato, Comunidad de Cataluña",
    "Penedès": "Penedés, Comunidad de Cataluña",
    "Empordà": "Ampurdán-Costa Brava",
    "Arabako Txakolina": "Arabako Txakolina-Txakolí de Álava",
    "Bizkaiko Txakolina": "Chacolí de Bizkaia-Bizkaiko Txakolina",
    "Getariako Txakolina": "Chacolí de Getaria-Getariako Txakolina",
    "Binissalem": "Binissalem-Mallorca",
    "León": "Tierra de León",
    "Manzanilla de Sanlúcar": "Manzanilla Sanlúcar de Barrameda",
    "Cangas": "VC Cangas",
    "Lebrija": "VC Lebrija",
    "Aylés": "Vino de Pago Aylés",
    "Calzadilla": "Pago de Calzadilla",
    "Los Balagueses": "Pago Los Balagueses",
}


class ESZoneIndex:
    def __init__(self, geojson_path: Path, target_crs: str = "EPSG:4326") -> None:
        self._by_name: dict[str, list[BaseGeometry]] = {}
        self._alias = {_norm(k): _norm(v) for k, v in _NAME_ALIAS.items()}
        self._n_zones = 0
        if not geojson_path.exists():
            return
        try:
            gdf = gpd.read_file(geojson_path)
        except Exception:  # noqa: BLE001
            return
        if gdf.crs is None:
            return
        if gdf.crs.to_string() != target_crs:
            gdf = gdf.to_crs(target_crs)
        if _NAME_FIELD not in gdf.columns:
            return
        for _, row in gdf.iterrows():
            geom = row.geometry
            name = _norm(str(row.get(_NAME_FIELD) or ""))
            if not name or geom is None or geom.is_empty:
                continue
            self._by_name.setdefault(name, []).append(geom)
            self._n_zones += 1

    @property
    def n_zones(self) -> int:
        return self._n_zones

    def resolve(self, name: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve a Spanish wine's geometry from the MAPA national
        layer. Returns (geometry, geom_source, stats)."""
        key = _norm(name)
        hits = self._by_name.get(key) or []
        if not hits and key in self._alias:
            hits = self._by_name.get(self._alias[key]) or []
        if not hits:
            return None, "none", {"matched": 0, "unmatched": 0}
        geom = hits[0] if len(hits) == 1 else unary_union(hits)
        return geom, "mapa-zone", {"matched": len(hits), "unmatched": 0}
