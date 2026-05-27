"""RO-side geometry resolution — Bétard PDO + GISCO commune-list fallback.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    38 of the 41 RO PDOs (`PDO-RO-*`). 3 newer registrations
    (`PDO-RO-01182` Sebeș-Apold, `PDO-RO-02854` Plaiurile Drâncei,
    `PDO-RO-03446` Iana) post-date the dataset.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — 3,181 Romanian commune polygons used by the
    commune-list fallback for IGPs (Bétard is PDO-only) and for the
    3 newer PDOs not in Bétard.

Stage 04 resolves each RO record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers
     ~38 of 41 RO PDOs.
  2. **gisco-commune-list** — parse the documento-unic
     `geo_area_brief` / `aria_delimitata` text, normalise commune
     names (Romanian diacritics + `municipiul/orașul/comuna` prefix
     strip), union matching GISCO LAU polygons. Used for the 13 RO
     IGPs and the 3 newer PDOs missing from Bétard. Mirrors the ES
     IGP-fallback chain (and the AT Gemeinde-union pattern).
  3. **stub-no-geometry** — neither resolved nor a documento-unic
     with a parseable commune list (the 20 grandfathered IGPs and
     unparseable-pliego cases).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


class ROPolygonIndex:
    """In-memory polygon index for RO records: Bétard PDO match +
    GISCO commune-union fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # commune (LAU_NAME, normalised) → list of polygons. Multiple
        # Romanian communes can share a name (e.g. "Cernavodă" town vs.
        # any neighbouring "Cernavodă" rural unit); we keep all candidates
        # and union them all when the commune list mentions the bare name.
        # The ES pattern uses a (province, name) tuple as the key when
        # province context is known, but Romania's documento-unic
        # commune lists usually disambiguate by județ prefix in prose;
        # the simple-name-keyed index is enough for v1, and ambiguous
        # cases land in the audit's `unmatched`/`ambiguous` bucket.
        self._lau_by_name: dict[str, list[BaseGeometry]] = {}
        self._n_lau = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-RO", "PGI-RO"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(gisco_lau_zip)
            ro = gdf[gdf["CNTR_CODE"] == "RO"]
            if ro.crs is None or ro.crs.to_string() != target_crs:
                ro = ro.to_crs(target_crs)
            for _, r in ro.iterrows():
                name = (r.get("LAU_NAME") or "").strip()
                geom = r.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                self._lau_by_name.setdefault(_normalise_commune(name), []).append(geom)
                self._n_lau += 1

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def commune_union(
        self, commune_names: Iterable[str],
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons that match the given commune
        names (after normalisation). Returns (geometry, stats) where
        stats counts matched / unmatched commune names."""
        from .commune import _normalise_commune
        polys: list[BaseGeometry] = []
        matched: list[str] = []
        unmatched: list[str] = []
        for raw_name in commune_names:
            key = _normalise_commune(raw_name)
            if not key:
                continue
            cands = self._lau_by_name.get(key)
            if not cands:
                unmatched.append(raw_name)
                continue
            polys.extend(cands)
            matched.append(raw_name)
        stats = {
            "matched": len(matched),
            "unmatched": len(unmatched),
            "names_unmatched": unmatched[:30],
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def resolve(
        self, file_number: str, commune_names: Iterable[str] | None = None,
    ) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one RO record. Returns (geometry,
        geom_source, stats). Bétard PDO match first; commune-union
        fallback for IGPs and the 3 newer PDOs missing from Bétard."""
        fn = file_number or ""
        if fn in self._pdo_polygons:
            return (
                self._pdo_polygons[fn], "figshare-pdo",
                {"matched": -1, "unmatched": 0},
            )
        if commune_names:
            geom, stats = self.commune_union(commune_names)
            if geom is not None:
                return geom, "gisco-commune-list", stats
            return None, "stub-no-geometry", stats
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
