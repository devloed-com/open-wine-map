"""US-side geometry resolution — pull AVA polygons from UCDavis AVA corpus.

Source: UCDavis Library AVA project (CC0)
  https://github.com/UCDavisLibrary/ava
  Expected file: raw/us/ucavis/avas.geojson
  (download: gh release / direct clone of the UCDavis repo)

Each feature carries an `ava_id` property (e.g. "alexander_valley_19841123")
that is the canonical identifier used throughout the TTB/CFR corpus.

Stage 04 resolves each US record by:

  1. **ucavis-ava** — exact `ava_id` → AVA polygon. Covers all 245 TTB
     American Viticultural Areas with geometries in the UCDavis corpus
     (as of the 2024 corpus freeze).
  2. **stub-no-geometry** — no polygon available (logged in the audit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


class USPolygonIndex:
    """In-memory polygon index for US AVA records, backed by UCDavis AVA."""

    def __init__(
        self,
        ucavis_geojson: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._ava_polygons: dict[str, BaseGeometry] = {}

        if ucavis_geojson.exists():
            gdf = gpd.read_file(ucavis_geojson)
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                ava_id = (row.get("ava_id") or "").strip()
                if ava_id and row.geometry is not None and not row.geometry.is_empty:
                    self._ava_polygons[ava_id] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        """Number of AVA polygons loaded (mirrors ATPolygonIndex contract)."""
        return len(self._ava_polygons)

    def resolve(self, ava_id: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one US record by ava_id.

        Returns ``(geometry, geom_source, stats)``.  ``stats`` always
        carries ``matched`` / ``unmatched``; ``matched == -1`` means the
        polygon was resolved whole (stage-04 contract, same as AT).
        """
        aid = (ava_id or "").strip()
        geom = self._ava_polygons.get(aid)
        if geom is not None:
            return geom, "ucavis-ava", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, ava_ids: Iterable[str]) -> BaseGeometry | None:
        """Union polygons for a set of ava_ids; skips unknown ids."""
        polys = [
            self._ava_polygons[aid.strip()]
            for aid in ava_ids
            if aid.strip() in self._ava_polygons
        ]
        return unary_union(polys) if polys else None
