"""AU-side geometry resolution — pull GI polygons from Wine Australia register.

Source: Wine Australia GI Register (official, publicly available)
  https://www.wineaustralia.com/labelling/register-of-protected-gis
  Download: SHP or KML from the Wine Australia website.
  Expected file: raw/au/wine_australia/gi.shp  (or gi.kml)

The register covers the full three-level AU GI hierarchy:
  Zone → Region → Subregion (≈ 65 registered GIs as of 2024).

Stage 04 resolves each AU record by:

  1. **wine-australia-gi** — GI name → polygon from the official register.
     Name matching is slug-based (ASCII, lowercase, hyphens) so minor
     spelling variants in source data still resolve.
  2. **stub-no-geometry** — no polygon available (logged in the audit).

Note: the Bétard 2022 EU_PDO.gpkg (CC0) does **not** cover Australia —
there is no Figshare fallback for AU records.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _slugify(name: str) -> str:
    """ASCII slug: lowercase, hyphens, no diacritics."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


class AUPolygonIndex:
    """In-memory polygon index for AU GI records, backed by Wine Australia."""

    def __init__(
        self,
        wine_au_path: Path,
        name_field: str = "NAME",
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        # Two keys per record: slug form and lower-stripped raw name.
        self._gi_polygons: dict[str, BaseGeometry] = {}

        if wine_au_path.exists():
            gdf = gpd.read_file(wine_au_path)
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            # Fall back to first object column if name_field is absent.
            if name_field not in gdf.columns:
                name_field = next(
                    (c for c in gdf.columns if gdf[c].dtype == object), None
                )
            for _, row in gdf.iterrows():
                raw_name = str(row.get(name_field) or "").strip()
                if not raw_name:
                    continue
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                self._gi_polygons[_slugify(raw_name)] = geom
                self._gi_polygons[raw_name.lower()] = geom

    @property
    def n_pdo_polygons(self) -> int:
        """Number of distinct GI polygons loaded (mirrors ATPolygonIndex contract)."""
        # Each record inserts two keys; divide for the true count.
        return len(self._gi_polygons) // 2

    def _lookup(self, gi_name: str) -> BaseGeometry | None:
        name = (gi_name or "").strip()
        return self._gi_polygons.get(_slugify(name)) or self._gi_polygons.get(
            name.lower()
        )

    def resolve(self, gi_name: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one AU record by GI name.

        Returns ``(geometry, geom_source, stats)``.  ``stats`` always
        carries ``matched`` / ``unmatched``; ``matched == -1`` means the
        polygon was resolved whole (stage-04 contract, same as AT).
        """
        geom = self._lookup(gi_name)
        if geom is not None:
            return geom, "wine-australia-gi", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, gi_names: Iterable[str]) -> BaseGeometry | None:
        """Union polygons for a set of GI names; skips unresolved names."""
        polys = [g for name in gi_names if (g := self._lookup(name)) is not None]
        return unary_union(polys) if polys else None
