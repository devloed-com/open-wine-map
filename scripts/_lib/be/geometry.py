"""BE-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 7 Belgian PDOs (`PDO-BE-*`) plus the cross-border BE+NL PDO
    (`PDO-BE+NL-02172` "Maasvallei Limburg"). The 2 BE PGIs are NOT in
    Bétard (PDO-only dataset).

Stage 04 resolves each BE record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022 EU_PDO.gpkg. Covers all 8 BE+ PDOs.
  2. **region-pdo-union** — the 2 BE PGIs are whole-Vlaanderen /
     whole-Wallonië wine territories; each is the union of the member-
     PDO Figshare polygons (the SI/HU/BG/DE PGI pattern):
       - Vlaamse landwijn = 3 Flemish DOPs (Hagelandse / Haspengouwse /
         Heuvellandse — Vlaamse mousserende kwaliteitswijn and
         Maasvallei are excluded as they are PDOs of a different style
         tier, not the still-wine PDOs the landwijn umbrella implies).
       - Vin de pays des jardins de Wallonie = 4 Walloon PDOs (Côtes
         de Sambre et Meuse, Vin mousseux de qualité de Wallonie,
         Crémant de Wallonie — its narrower still-wine geometry comes
         from Sambre-Meuse plus its sparkling sister polygons).
  3. **stub-no-geometry** — no polygon available (logged in the audit).
     Not normally hit in v1; all 10 BE wines resolve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. The two BE PGIs each union the PDO polygons of their
# language community.
BE_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-BE-A1429": (  # Vlaamse landwijn — all 5 Flemish PDOs
        "PDO-BE-A1492",   # Haspengouwse wijn
        "PDO-BE-A1499",   # Hagelandse wijn
        "PDO-BE-A1426",   # Heuvellandse wijn
        "PDO-BE-A1430",   # Vlaamse mousserende kwaliteitswijn (region-wide)
        "PDO-BE+NL-02172",  # Maasvallei Limburg
    ),
    "PGI-BE-A0010": (  # Vin de pays des jardins de Wallonie — all 4 Walloon PDOs
        "PDO-BE-A0009",   # Côtes de Sambre et Meuse
        "PDO-BE-A0011",   # Vin mousseux de qualité de Wallonie
        "PDO-BE-A0012",   # Crémant de Wallonie
    ),
}


class BEPolygonIndex:
    """In-memory polygon index for BE records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            # Belgian PDOs are tagged either PDO-BE-* or the cross-border
            # PDO-BE+NL-*; PGI-BE-* is not present (Bétard is PDO-only).
            gdf = gdf[
                gdf["PDOid"].astype(str).str.contains("BE", na=False)
            ]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                pid = row["PDOid"]
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[pid] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        members = BE_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
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
        """Resolve geometry for one BE record by file_number.
        Returns (geometry, geom_source, stats)."""
        fn = file_number or ""
        if fn in BE_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        geom = self._pdo_polygons.get(fn)
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
