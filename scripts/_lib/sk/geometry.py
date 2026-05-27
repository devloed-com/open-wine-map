"""SK-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    8 of the 9 Slovak DOPs (`PDO-SK-*`). The 9th, TOKAJSKÉ VÍNO zo
    slovenskej oblasti (`PDO-SK-02856`), post-dates the Bétard snapshot
    and is approximated by the Vinohradnícka oblasť Tokaj PDO
    (`PDO-SK-A0120`) — same physical territory, different brand name.

Stage 04 resolves each SK record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022 EU_PDO.gpkg. Covers 8 of 9 SK DOPs.
  2. **figshare-pdo-alias** — the post-Bétard TOKAJSKÉ VÍNO PDO
     (`PDO-SK-02856`) borrows the Vinohradnícka oblasť Tokaj polygon
     (`PDO-SK-A0120`) — same Tokaj zone, different brand registration.
  3. **region-pdo-union** — the single SK PGI (`PGI-SK-A1361`
     "Slovenská") is the whole-country wine territory; Bétard is
     PDO-only, so the PGI is the union of every SK PDO polygon
     (SI/HU/BG/DE PGI pattern).
  4. **stub-no-geometry** — no polygon available (logged in the audit).
     Not normally hit in v1; all 10 SK wines resolve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Post-Bétard PDOs whose territory is coextensive with an earlier PDO —
# Bétard covers the source PDO and we borrow its polygon for the alias.
SK_PDO_BETARD_ALIAS: dict[str, str] = {
    # TOKAJSKÉ VÍNO zo slovenskej oblasti = the Slovak Tokaj wine PDO,
    # rebranded from the older Vinohradnícka oblasť Tokaj PDO (same
    # physical Tokaj wine region).
    "PDO-SK-02856": "PDO-SK-A0120",
}

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. SK has one country-wide PGI.
SK_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-SK-A1361": (  # Slovenská — every Slovak DOP
        "PDO-SK-A1354",  # Východoslovenská
        "PDO-SK-A1355",  # Stredoslovenská
        "PDO-SK-A1356",  # Južnoslovenská
        "PDO-SK-A1357",  # Nitrianska
        "PDO-SK-A1360",  # Malokarpatská
        "PDO-SK-A1598",  # Karpatská perla
        "PDO-SK-A0120",  # Vinohradnícka oblasť Tokaj
        "PDO-SK-01899",  # Skalický rubín
    ),
}


class SKPolygonIndex:
    """In-memory polygon index for SK records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-SK", "PGI-SK"))]
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
        members = SK_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
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
        """Resolve geometry for one SK record by file_number.
        Returns (geometry, geom_source, stats)."""
        fn = file_number or ""
        if fn in SK_PGI_MEMBER_PDOS:
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
        alias = SK_PDO_BETARD_ALIAS.get(fn)
        if alias is not None:
            geom = self._pdo_polygons.get(alias)
            if geom is not None:
                return geom, "figshare-pdo-alias", {
                    "matched": -1, "unmatched": 0, "alias_of": alias,
                }
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
