"""HR-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 18 Croatian PDOs (`PDO-HR-*`).

Stage 04 resolves each HR record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers all
     18 HR PDOs (every Croatian wine GI is a PDO; there are no IGPs).
  2. **stub-no-geometry** — not normally hit (every HR record is in
     Bétard, even the 16 grandfathered stubs).

Croatia is structurally simpler than every prior country: there are no
IGPs to union-resolve, no commune-list fallback chain, and Bétard 2022
coverage is exhaustive. The clean profile means every wine — including
the 16 Article-107 grandfathered names with no fetchable single
document — appears on the map with a polygon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


class HRPolygonIndex:
    """In-memory polygon index for HR records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith("PDO-HR")]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one HR record by file_number. Returns
        (geometry, geom_source, stats). `matched == -1` is the project
        convention for a polygon resolved whole rather than commune-counted."""
        geom = self._pdo_polygons.get(file_number or "")
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
