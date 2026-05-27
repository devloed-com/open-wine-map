"""HU-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    32 of the 35 HU PDOs (`PDO-HU-*`) plus the Balaton PGI (stored
    under `PDO-HU-A1507` — Bétard mis-labelled the file_number kind
    for that one entry; we accept the mapping rather than fight it).

Stage 04 resolves each HU record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match (with the
     Balaton PGI bridged via `PGI-HU-A1507 → PDO-HU-A1507`). Covers 32
     of 35 HU PDOs + the Balaton PGI.
  2. **region-pdo-union** — the 5 remaining HU PGIs (Balatonmelléki,
     Duna-Tisza-közi, Dunántúli, Felső-Magyarország, Zemplén) are
     umbrella territories; Bétard is PDO-only, so we union the Figshare
     polygons of the member PDOs by curated mapping (the SI PGI
     pattern). Member tables are stable and hand-verified.
  3. **stub-no-geometry** — 3 newer PDOs (Etyeki Pezsgő, Kőszeg, Füred)
     post-date the Bétard snapshot; they show in the sidebar with no
     polygon in v1. (Phase 2: parse the Hungarian commune list from
     the Egységes Dokumentum + reuse Eurostat GISCO LAU.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


# Bétard 2022 mis-labelled the Balaton PGI as `PDO-HU-A1507` (it is a
# registered PGI in eAmbrosia under `PGI-HU-A1507`). We bridge the two
# rather than carry forward the upstream typo.
_FILE_NUMBER_BÉTARD_BRIDGE: dict[str, str] = {
    "PGI-HU-A1507": "PDO-HU-A1507",
}


# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. Mirrors the SI pattern (SI_PGI_MEMBER_PDOS). Curated
# from the Hungarian wine-law region structure + eAmbrosia memberships.
HU_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-HU-A1508": (  # Balatonmelléki PGI (Balaton-adjacent subset)
        "PDO-HU-A1506",  # Badacsony
        "PDO-HU-A1509",  # Balaton-felvidék
        "PDO-HU-A1516",  # Balatonfüred-Csopak
        "PDO-HU-02378",  # Csopak
        "PDO-HU-A1503",  # Tihany
        "PDO-HU-A1505",  # Káli
        "PDO-HU-A1378",  # Balatonboglár
        "PDO-HU-A1502",  # Zala
    ),
    "PGI-HU-A1342": (  # Duna-Tisza-közi PGI
        "PDO-HU-A1332",  # Kunság
        "PDO-HU-A1388",  # Hajós-Baja
        "PDO-HU-A1383",  # Csongrád
        "PDO-HU-A1345",  # Duna
        "PDO-HU-02171",  # Soltvadkerti
        "PDO-HU-A1341",  # Izsáki Arany Sárfehér
        "PDO-HU-N1638",  # Monor
    ),
    "PGI-HU-A1351": (  # Dunántúli PGI (Transdanubia umbrella)
        "PDO-HU-A1349",  # Szekszárd
        "PDO-HU-A1353",  # Tolna
        "PDO-HU-A1380",  # Pannon
        "PDO-HU-A1381",  # Villány
        "PDO-HU-A1385",  # Pécs
        "PDO-HU-A1333",  # Mór
        "PDO-HU-A1335",  # Neszmély
        "PDO-HU-A1338",  # Pannonhalma
        "PDO-HU-A1350",  # Etyek-Buda
        "PDO-HU-A1504",  # Sopron
        "PDO-HU-A1378",  # Balatonboglár (also in Dunántúli umbrella)
        "PDO-HU-A1506",  # Badacsony
        "PDO-HU-A1509",  # Balaton-felvidék
        "PDO-HU-A1516",  # Balatonfüred-Csopak
        "PDO-HU-02378",  # Csopak
        "PDO-HU-A1503",  # Tihany
        "PDO-HU-A1505",  # Káli
        "PDO-HU-A1501",  # Nagy-Somló
        "PDO-HU-A1376",  # Somlói
        "PDO-HU-A1502",  # Zala
    ),
    "PGI-HU-A1329": (  # Felső-Magyarország PGI
        "PDO-HU-A1328",  # Eger
        "PDO-HU-A1368",  # Mátra
        "PDO-HU-A1500",  # Bükk
        "PDO-HU-A1373",  # Debrői Hárslevelű (sits in the Felső-Magyarország umbrella)
    ),
    "PGI-HU-A1375": (  # Zemplén PGI (Tokaj-area umbrella)
        "PDO-HU-A1254",  # Tokaj
    ),
}


class HUPolygonIndex:
    """In-memory polygon index for HU records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-HU", "PGI-HU"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        bridged = _FILE_NUMBER_BÉTARD_BRIDGE.get(file_number, file_number)
        return self._pdo_polygons.get(bridged)

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        """Union the member-PDO polygons for one HU PGI. Returns
        (geometry, stats) where stats records how many member PDOs
        resolved."""
        members = HU_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
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
        """Resolve geometry for one HU record by file_number. Returns
        (geometry, geom_source, stats). `matched == -1` is the project
        convention for a polygon resolved whole rather than commune-counted."""
        fn = file_number or ""
        bridged = _FILE_NUMBER_BÉTARD_BRIDGE.get(fn, fn)
        if bridged in self._pdo_polygons:
            return self._pdo_polygons[bridged], "figshare-pdo", {"matched": -1, "unmatched": 0}
        if fn in HU_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[_FILE_NUMBER_BÉTARD_BRIDGE.get(fn, fn)]
            for fn in file_numbers
            if _FILE_NUMBER_BÉTARD_BRIDGE.get(fn, fn) in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
