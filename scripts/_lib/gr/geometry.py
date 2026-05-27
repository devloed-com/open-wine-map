"""GR-side geometry resolution — Bétard PDO + GISCO commune-list fallback.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 33 GR PDOs (`PDO-GR-*`). Greece joined the EU in 1981; every
    GR PDO predates the Nov-2021 cutoff.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — ~6,142 Greek δημοτική κοινότητα (community)
    polygons (CNTR_CODE='EL' — Greece's EU country code, *not* ISO
    `GR`) used by the commune-list fallback. Note: GISCO LAU is at
    community granularity in Greece (finer than the δήμος / dimos),
    so the parser-side normaliser must strip the tier prefix
    `Δημοτική Κοινότητα NAME` → `NAME`.

Stage 04 resolves each GR record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers
     all 33 GR DOPs.
  2. **gisco-commune-list** — parse the documento-unic geo-area body
     into δήμος / κοινότητα names (Greek-preserving) and union
     matching GISCO LAU polygons. Mirrors the RO / BG chains. v1 hit
     rate is small since only ~11 of 147 GR wines have a fetchable
     single document; the 114 PGIs are mostly content-stubs.
  3. **stub-no-geometry** — no polygon resolvable (the dominant case
     for the ~110 grandfathered Greek PGIs whose only eAmbrosia
     reference is an `Ares(...)` summary-sheet). Visible in the
     sidebar/search, absent from the map until curator-pinned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


class GRPolygonIndex:
    """In-memory polygon index for GR records: Bétard PDO match +
    GISCO κοινότητα-list fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # commune (LAU_NAME, normalised) → list of polygons.
        self._lau_by_name: dict[str, list[BaseGeometry]] = {}
        self._n_lau = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-GR", "PGI-GR"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(gisco_lau_zip)
            # GISCO uses CNTR_CODE='EL' for Greece (EU convention, not ISO).
            gr = gdf[gdf["CNTR_CODE"] == "EL"]
            if gr.crs is None or gr.crs.to_string() != target_crs:
                gr = gr.to_crs(target_crs)
            for _, r in gr.iterrows():
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
        """Union the GISCO LAU polygons matching the given δήμος /
        κοινότητα names (after Greek-preserving normalisation)."""
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
        """Resolve geometry for one GR record. Returns (geometry,
        geom_source, stats). Bétard PDO match first; GISCO commune-union
        fallback otherwise."""
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
