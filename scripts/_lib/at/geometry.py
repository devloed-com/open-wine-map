"""AT-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all EU PDOs including the 29 Austrian DOPs (`PDO-AT-*`). Filter is
    applied at load time.

Stage 04 resolves each AT record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers the
     29 AT DOPs (pre-Nov-2021 registrations are all in Bétard 2022).
  2. **bundesland-pdo-union** — the 3 AT PGIs (Bergland, Weinland,
     Steirerland) are Landwein categories spanning whole Bundesländer.
     Bétard is PDO-only, so a PGI has no polygon of its own; instead we
     union the Figshare polygons of the regional PDOs coextensive with
     the Bundesländer the PGI covers. Each of the 9 wine Bundesländer
     has its own generic PDO in the corpus, so this is exact.
  3. **stub-no-geometry** — no polygon available (logged in the audit).

The PGI → member-PDO mapping is structural (defined by Austrian wine
law and each PGI's Einziges-Dokument geo section); it is stable and
hand-verified here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# PGI file_number → the regional-PDO file_numbers whose union forms the
# PGI's territory. Bergland = Oberösterreich + Salzburg + Tirol +
# Vorarlberg + Kärnten; Weinland = Niederösterreich + Burgenland + Wien;
# Steirerland = Steiermark.
AT_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-AT-A0211": (  # Bergland
        "PDO-AT-A0223",  # Oberösterreich
        "PDO-AT-A0224",  # Salzburg
        "PDO-AT-A0230",  # Tirol
        "PDO-AT-A0231",  # Vorarlberg
        "PDO-AT-A0218",  # Kärnten
    ),
    "PGI-AT-A0212": (  # Weinland
        "PDO-AT-A0221",  # Niederösterreich
        "PDO-AT-A0207",  # Burgenland
        "PDO-AT-A0235",  # Wien
    ),
    "PGI-AT-A0213": (  # Steirerland
        "PDO-AT-A0225",  # Steiermark
    ),
}


class ATPolygonIndex:
    """In-memory polygon index for AT records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].str.startswith(("PDO-AT", "PGI-AT"))]
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
        """Union the member-PDO polygons for one of the 3 AT PGIs.
        Returns (geometry, stats) where stats records how many member
        PDOs resolved."""
        members = AT_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
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
        """Resolve geometry for one AT record by file_number.
        Returns (geometry, geom_source, stats). `stats` always carries
        `matched` / `unmatched` (stage-04 contract); `matched == -1` is
        the project convention for a polygon resolved whole rather than
        commune-counted."""
        fn = file_number or ""
        if fn in AT_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "bundesland-pdo-union", stats
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
