"""MT-side geometry resolution — Bétard PDO + region-PGI-union.

The simplest geometry chain after Croatia: Malta has no sub-regions and
no IGP commune lists. Reuses the shared Bétard artifact the ES pipeline
already caches:

  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers both
    Maltese DOPs (`PDO-MT-A1629` Gozo, `PDO-MT-A1630` Malta). Malta joined
    the EU in 2004; both PDOs predate Bétard's Nov-2021 snapshot.

Stage 04 resolves each MT record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022. Covers the 2 PDOs (Malta, Gozo).
  2. **region-pdo-union** — the single MT PGI (`PGI-MT-A1631` "Maltese
     Islands") is the whole archipelago; Bétard is PDO-only, so the PGI
     is the union of the two MT PDO polygons (the SI/CZ/HU/BG pattern).
  3. **stub-no-geometry** — not normally hit; all 3 MT wines resolve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
FIGSHARE_GPKG = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory.
MT_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-MT-A1631": (  # Maltese Islands — the whole archipelago
        "PDO-MT-A1630",  # Malta
        "PDO-MT-A1629",  # Gozo
    ),
}


class MTPolygonIndex:
    """In-memory polygon index for MT records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        gpkg = figshare_gpkg or FIGSHARE_GPKG
        if gpkg.exists():
            gdf = gpd.read_file(gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-MT", "PGI-MT"))]
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

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        members = MT_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one MT record by file_number.
        Returns (geometry, geom_source, stats)."""
        fn = file_number or ""
        if fn in MT_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {"matched": -1 if geom is not None else 0, "unmatched": 0, **union_stats}
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        geom = self._pdo_polygons.get(fn)
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [self._pdo_polygons[fn] for fn in file_numbers if fn in self._pdo_polygons]
        return unary_union(polys) if polys else None
