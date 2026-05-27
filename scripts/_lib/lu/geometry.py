"""LU-side polygon index — Bétard parent PDO + IVV Weinbaukartei
(per-parcel planted-vineyard polygons) + GISCO LAU admin-commune
polygons.

Three data sources, three roles:

  - **Bétard 2022 EU_PDO.gpkg** (CC0) — `PDO-LU-A0452` polygon covers
    the *regulatory* viticultural perimeter (245 km², the Mosel-strip
    declared by Règlement grand-ducal du 9 sept 2009). v1 uses this
    as the parent record's geometry — it matches eAmbrosia + the
    cahier des charges section d.

  - **IVV Weinbaukartei 2022** (``raw/lu/ivv/vineyards/weinberge-lu-2022/
    weinberge_lu_2022.shp``, 4 521 planted-vineyard parcels totalling
    11.9 km², CRS EPSG:2169 / LUREF). v1 dissolves these by their
    spatial intersection with the modern GISCO LAU commune polygons
    (via :func:`scripts._lib.lu.commune.MODERN_BY_NORM`) to render
    *planted-vineyard* per-commune geometry — far more honest than
    the full admin-commune polygon for a corpus where the actual
    vine area is < 10 % of the administrative footprint
    (Schengen ≈ 45 km² admin / ≈ 4.4 km² planted).

  - **Eurostat GISCO LAU 2024** (``raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip``,
    CC-BY 4.0) — 100 modern Luxembourg communes; serves as the
    spatial-intersection oracle for the IVV-parcel dissolve and as a
    fallback when the IVV layer is absent.

Stage 04 uses :meth:`LUPolygonIndex.resolve` per record:

  1. **ivv-commune-vineyard** — sub-denomination (per modern commune):
     IVV parcels whose representative point falls inside the modern
     commune, unioned. Planted-vineyard precision.
  2. **gisco-commune** — fallback when the IVV layer is missing for
     a commune. Full admin polygon, less honest but always available.
  3. **figshare-pdo** — parent record (Moselle Luxembourgeoise) →
     Bétard PDO-LU-A0452 polygon.
  4. **stub-no-geometry** — last resort. Not normally hit in v1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .commune import MODERN_BY_NORM, MODERN_WINE_COMMUNES, normalise_name


class LUPolygonIndex:
    """Bétard PDO + IVV vineyard parcels + GISCO LAU."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path,
        ivv_vineyards_shp: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        self._gisco_by_commune: dict[str, BaseGeometry] = {}
        self._ivv_by_commune: dict[str, BaseGeometry] = {}
        self._ivv_n_parcels: dict[str, int] = {}
        self._ivv_total: BaseGeometry | None = None
        self._ivv_total_n_parcels = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith("PDO-LU")]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip.exists():
            self._load_gisco(gisco_lau_zip)

        if ivv_vineyards_shp is not None and ivv_vineyards_shp.exists():
            self._load_ivv_vineyards(ivv_vineyards_shp)

    def _load_gisco(self, gisco_lau_zip: Path) -> None:
        gdf = gpd.read_file(gisco_lau_zip)
        lu = gdf[gdf["CNTR_CODE"] == "LU"]
        if lu.crs is None or lu.crs.to_string() != self.target_crs:
            lu = lu.to_crs(self.target_crs)
        for _, r in lu.iterrows():
            name = (r.get("LAU_NAME") or "").strip()
            geom = r.geometry
            if not name or geom is None or geom.is_empty:
                continue
            key = normalise_name(name)
            canonical = MODERN_BY_NORM.get(key)
            if canonical:
                self._gisco_by_commune[canonical] = geom

    def _load_ivv_vineyards(self, ivv_shp: Path) -> None:
        """Load IVV parcels, spatially join to modern commune polygons
        (using representative-point-in-polygon), dissolve per commune.

        Requires :meth:`_load_gisco` to have already populated the
        GISCO commune polygons; without them, the dissolve has no
        modern-commune key to group by.
        """
        if not self._gisco_by_commune:
            return
        ivv = gpd.read_file(ivv_shp)
        if ivv.crs is None or ivv.crs.to_string() != self.target_crs:
            ivv = ivv.to_crs(self.target_crs)
        # Spatial join via representative_point so edge-overlap parcels
        # bind to exactly one commune (the IVV `CODE_COM` codes use
        # pre-fusion historic communes; the modern fusion structure
        # changes the right answer for boundary parcels).
        ivv = ivv[ivv.geometry.notna() & (~ivv.geometry.is_empty)].copy()
        ivv["rep"] = ivv.geometry.representative_point()
        ivv_pts = gpd.GeoDataFrame(
            ivv.drop(columns="geometry"),
            geometry=ivv["rep"],
            crs=self.target_crs,
        ).drop(columns="rep")
        gisco_gdf = gpd.GeoDataFrame(
            [{"modern": k, "geometry": v} for k, v in self._gisco_by_commune.items()],
            crs=self.target_crs,
        )
        joined = gpd.sjoin(ivv_pts, gisco_gdf, how="left", predicate="within")
        for modern, group in joined.groupby("modern"):
            parcel_indices = group.index
            parcel_geoms = [ivv.loc[i].geometry for i in parcel_indices
                            if ivv.loc[i].geometry is not None
                            and not ivv.loc[i].geometry.is_empty]
            if not parcel_geoms:
                continue
            self._ivv_by_commune[str(modern)] = unary_union(parcel_geoms)
            self._ivv_n_parcels[str(modern)] = len(parcel_geoms)
        # Whole-AOP IVV polygon (informational; not used as parent
        # geometry by default — we keep Bétard for the parent so it
        # matches the regulatory perimeter referenced in the cahier).
        all_parcels = [g for g in ivv.geometry if g is not None and not g.is_empty]
        if all_parcels:
            self._ivv_total = unary_union(all_parcels)
            self._ivv_total_n_parcels = len(all_parcels)

    # ─── introspection ────────────────────────────────────────

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_gisco_communes(self) -> int:
        return len(self._gisco_by_commune)

    @property
    def n_ivv_communes(self) -> int:
        return len(self._ivv_by_commune)

    @property
    def n_ivv_parcels(self) -> int:
        return self._ivv_total_n_parcels

    def ivv_parcels_in_commune(self, modern_commune: str) -> int:
        return self._ivv_n_parcels.get(modern_commune, 0)

    # ─── lookups ──────────────────────────────────────────────

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def gisco_polygon(self, modern_commune: str) -> BaseGeometry | None:
        return self._gisco_by_commune.get(modern_commune)

    def ivv_vineyard_polygon(self, modern_commune: str) -> BaseGeometry | None:
        return self._ivv_by_commune.get(modern_commune)

    def ivv_total_polygon(self) -> BaseGeometry | None:
        return self._ivv_total

    def gisco_union(self, communes: Iterable[str]) -> BaseGeometry | None:
        polys = [self._gisco_by_commune[c] for c in communes
                 if c in self._gisco_by_commune]
        return unary_union(polys) if polys else None

    # ─── resolution chain ─────────────────────────────────────

    def resolve(self, record: dict) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one LU record.

        Returns ``(geometry, geom_source, stats)`` where ``geom_source``
        is one of ``ivv-commune-vineyard`` / ``gisco-commune`` /
        ``figshare-pdo`` / ``stub-no-geometry``.

        - **Sub-denominations** (``is_sub_denomination=True``): try the
          IVV planted-vineyard polygon for the record's ``commune``
          field, then fall back to the full GISCO admin polygon.
        - **Parent**: Bétard PDO-LU-A0452.
        """
        if record.get("is_sub_denomination"):
            commune = record.get("commune") or ""
            if commune in self._ivv_by_commune:
                return (
                    self._ivv_by_commune[commune],
                    "ivv-commune-vineyard",
                    {
                        "matched": 1,
                        "unmatched": 0,
                        "commune": commune,
                        "n_parcels": self._ivv_n_parcels.get(commune, 0),
                    },
                )
            if commune in self._gisco_by_commune:
                return (
                    self._gisco_by_commune[commune],
                    "gisco-commune",
                    {"matched": 1, "unmatched": 0, "commune": commune},
                )
            return (
                None, "stub-no-geometry",
                {"matched": 0, "unmatched": 1, "commune": commune},
            )

        # Parent record.
        fn = record.get("file_number") or ""
        geom = self._pdo_polygons.get(fn)
        if geom is not None:
            return geom, "figshare-pdo", {"matched": 1, "unmatched": 0,
                                          "file_number": fn}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 1,
                                          "file_number": fn}


def n_wine_communes() -> int:
    """Convenience: 11."""
    return len(MODERN_WINE_COMMUNES)
