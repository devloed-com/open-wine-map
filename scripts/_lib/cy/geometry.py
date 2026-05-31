"""CY-side geometry resolution — Bétard PDO + GISCO district-union.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 7 CY PDOs (`PDO-CY-A1622..A1628`). Cyprus joined the EU in 2004;
    every CY PDO predates the Nov-2021 cutoff.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — ~615 Cypriot community polygons (CNTR_CODE='CY')
    whose `GISCO_ID` prefix encodes the district:
        CY_1xxx → Λευκωσία (Nicosia)   CY_4xxx → Λάρνακα (Larnaca)
        CY_5xxx → Λεμεσός (Limassol)   CY_6xxx → Πάφος (Pafos)
    The 4 CY PGIs ARE those 4 wine districts, so each unions every
    GISCO community whose GISCO_ID carries its district digit.

Stage 04 resolves each CY record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers all
     7 CY PDOs.
  2. **gisco-district-union** — the 4 CY PGIs (Πάφος / Λεμεσός /
     Λάρνακα / Λευκωσία) are the island's wine districts; union the
     GISCO communities whose GISCO_ID carries the district digit.
  3. **stub-no-geometry** — last resort; not hit in v1 (all 11 resolve).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# The 4 CY PGIs → the leading GISCO_ID digit of their district communes.
CY_PGI_DISTRICT_DIGIT: dict[str, str] = {
    "PGI-CY-A1618": "6",  # Πάφος (Pafos)
    "PGI-CY-A1619": "5",  # Λεμεσός (Limassol)
    "PGI-CY-A1620": "4",  # Λάρνακα (Larnaca)
    "PGI-CY-A1621": "1",  # Λευκωσία (Nicosia)
}


class CYPolygonIndex:
    """In-memory polygon index for CY records: Bétard PDO match +
    GISCO district-union for the 4 PGIs."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # district digit ("1"/"4"/"5"/"6") → list of GISCO community polygons.
        self._lau_by_district: dict[str, list[BaseGeometry]] = {}
        self._n_lau = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-CY", "PGI-CY"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            cy = gdf[gdf["CNTR_CODE"] == "CY"]
            if cy.crs is None or cy.crs.to_string() != target_crs:
                cy = cy.to_crs(target_crs)
            for _, r in cy.iterrows():
                gid = (r.get("GISCO_ID") or "").strip()  # e.g. "CY_5000"
                geom = r.geometry
                if not gid.startswith("CY_") or geom is None or geom.is_empty:
                    continue
                digit = gid[3:4]
                self._lau_by_district.setdefault(digit, []).append(geom)
                self._n_lau += 1

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def district_union(self, file_number: str) -> tuple[BaseGeometry | None, dict]:
        digit = CY_PGI_DISTRICT_DIGIT.get(file_number or "")
        if not digit:
            return None, {"matched": 0, "unmatched": 0}
        polys = self._lau_by_district.get(digit) or []
        if not polys:
            return None, {"matched": 0, "unmatched": 0, "district_digit": digit}
        return unary_union(polys), {
            "matched": len(polys), "unmatched": 0, "district_digit": digit,
        }

    def resolve(
        self, file_number: str, commune_names: Iterable[str] | None = None,
        record: dict | None = None,
    ) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one CY record. Bétard PDO match first;
        then the GISCO district-union for the 4 PGIs."""
        fn = file_number or ""
        if fn in self._pdo_polygons:
            return self._pdo_polygons[fn], "figshare-pdo", {"matched": -1, "unmatched": 0}
        geom, stats = self.district_union(fn)
        if geom is not None:
            return geom, "gisco-district-union", stats
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
