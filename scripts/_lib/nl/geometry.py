"""NL-side geometry resolution — Bétard PDO + Eurostat NUTS-2 province
polygons.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers 6
    of the 10 NL PDOs (`PDO-NL-02114`, `PDO-NL-02168`, `PDO-NL-02230`,
    `PDO-NL-02169`, `PDO-NL-02402`). The 4 newer PDOs (`PDO-NL-02774`
    Rivierenland, `PDO-NL-02775` Schouwen-Duiveland, `PDO-NL-02776`
    De Voerendaalse Bergen, `PDO-NL-02873` Twente) post-date Bétard
    and ship as `stub-no-geometry` in v1.

  - `raw/nl/nuts/NUTS_RG_03M_2024_4326_LEVL_2.geojson` (Eurostat,
    permitted commercial use with attribution) — covers the 12 Dutch
    provinces (NUTS-2 = exactly the 12 provincies). Each NL PGI is
    coextensive with one province (Limburg, Gelderland, …), so each
    PGI resolves directly to the NUTS-2 polygon for its province.

Stage 04 resolves each NL record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022 EU_PDO.gpkg. Covers 6 of 10 NL PDOs.
  2. **nuts2-province** — for the 12 NL PGIs, look up the NUTS-2
     polygon for the province the PGI is coextensive with.
  3. **stub-no-geometry** — for the 4 newer PDOs missing from Bétard.
     Visible in the sidebar/search, absent from the map until Phase 2
     parses commune lists.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


# Province name (native Dutch) → NUTS-2 code. The NUTS-2 layer labels
# Limburg and Friesland with " (NL)" disambiguators since both names
# also appear elsewhere in Europe; we resolve by NUTS_ID, not name.
PROVINCE_TO_NUTS2: dict[str, str] = {
    "Groningen": "NL11",
    "Friesland": "NL12",
    "Drenthe": "NL13",
    "Overijssel": "NL21",
    "Gelderland": "NL22",
    "Flevoland": "NL23",
    "Noord-Holland": "NL32",
    "Zeeland": "NL34",
    "Utrecht": "NL35",
    "Zuid-Holland": "NL36",
    "Noord-Brabant": "NL41",
    "Limburg": "NL42",
}


# File-number → NUTS-2 code, derived from `_lib/nl/region.py` mapping +
# PROVINCE_TO_NUTS2. PGIs only — PDOs resolve via Bétard.
PGI_FILE_NUMBER_TO_NUTS2: dict[str, str] = {
    "PGI-NL-A0961": "NL42",   # Limburg
    "PGI-NL-A0962": "NL22",   # Gelderland
    "PGI-NL-A0963": "NL34",   # Zeeland
    "PGI-NL-A0964": "NL41",   # Noord-Brabant
    "PGI-NL-A0965": "NL36",   # Zuid-Holland
    "PGI-NL-A0966": "NL32",   # Noord-Holland
    "PGI-NL-A0967": "NL35",   # Utrecht
    "PGI-NL-A0968": "NL21",   # Overijssel
    "PGI-NL-A0380": "NL23",   # Flevoland
    "PGI-NL-A0969": "NL13",   # Drenthe
    "PGI-NL-A0970": "NL11",   # Groningen
    "PGI-NL-A0972": "NL12",   # Friesland
}


class NLPolygonIndex:
    """In-memory polygon index for NL records, backed by Bétard PDO +
    Eurostat NUTS-2."""

    def __init__(
        self,
        figshare_gpkg: Path,
        nuts2_geojson: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        self._nuts2_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith("PDO-NL")]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if nuts2_geojson.exists():
            ndf = gpd.read_file(nuts2_geojson)
            ndf = ndf[ndf["CNTR_CODE"] == "NL"]
            if ndf.crs is None or ndf.crs.to_string() != target_crs:
                ndf = ndf.to_crs(target_crs)
            for _, row in ndf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._nuts2_polygons[row["NUTS_ID"]] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_nuts2_polygons(self) -> int:
        return len(self._nuts2_polygons)

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one NL record by file_number.
        Returns (geometry, geom_source, stats)."""
        fn = file_number or ""
        nuts = PGI_FILE_NUMBER_TO_NUTS2.get(fn)
        if nuts:
            geom = self._nuts2_polygons.get(nuts)
            if geom is not None:
                return geom, "nuts2-province", {
                    "matched": -1, "unmatched": 0, "nuts": nuts,
                }
            return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}
        geom = self._pdo_polygons.get(fn)
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}
