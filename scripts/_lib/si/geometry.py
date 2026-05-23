"""SI-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all EU PDOs including the 14 Slovenian DOPs (`PDO-SI-*`).

Stage 04 resolves each SI record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers the
     14 SI DOPs (all are in Bétard 2022).
  2. **region-pdo-union** — the 3 SI PGIs (Podravje, Posavje, Primorska)
     are the 3 Slovenian wine regions; Bétard is PDO-only, so a PGI has
     no polygon of its own. Instead we union the Figshare polygons of
     the member PDOs that lie inside that region. Every member PDO is in
     Bétard, so this is exact.
  3. **stub-no-geometry** — no polygon available (logged in the audit).

The PGI → member-PDO mapping is structural (the 3 PGIs partition the 14
PDOs by Slovenian wine region); it is stable and hand-verified here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. The 3 PGIs are the 3 vinorodne dežele.
SI_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-SI-A0995": (  # Podravje
        "PDO-SI-A0639",  # Štajerska Slovenija
        "PDO-SI-A0769",  # Prekmurje
    ),
    "PGI-SI-A1061": (  # Posavje
        "PDO-SI-A0772",  # Bizeljsko Sremič
        "PDO-SI-A0871",  # Dolenjska
        "PDO-SI-A0878",  # Bela krajina
        "PDO-SI-A1520",  # Bizeljčan
        "PDO-SI-A1561",  # Cviček
        "PDO-SI-A1576",  # Belokranjec
        "PDO-SI-A1579",  # Metliška črnina
    ),
    "PGI-SI-A1094": (  # Primorska
        "PDO-SI-A0270",  # Goriška Brda
        "PDO-SI-A0448",  # Vipavska dolina
        "PDO-SI-A0616",  # Kras
        "PDO-SI-A0609",  # Slovenska Istra
        "PDO-SI-A1581",  # Teran
    ),
}


class SIPolygonIndex:
    """In-memory polygon index for SI records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-SI", "PGI-SI"))]
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
        """Union the member-PDO polygons for one of the 3 SI PGIs.
        Returns (geometry, stats) where stats records how many member
        PDOs resolved."""
        members = SI_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
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
        """Resolve geometry for one SI record by file_number.
        Returns (geometry, geom_source, stats). `stats` always carries
        `matched` / `unmatched` (stage-04 contract); `matched == -1` is
        the project convention for a polygon resolved whole rather than
        commune-counted."""
        fn = file_number or ""
        if fn in SI_PGI_MEMBER_PDOS:
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
