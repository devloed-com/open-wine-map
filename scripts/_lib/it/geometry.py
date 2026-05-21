"""IT-side geometry resolution — pull DOP polygons from Figshare and
union comune polygons from GISCO LAU.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all EU PDOs including ~420 Italian DOPs (`PDO-IT-A*`,
    `PGI-IT-A*`). Filter is applied at load time.
  - `raw/es/gisco/lau-eu-2024-01m.shp.zip` (Eurostat GISCO) — covers
    all EU LAU2 units including ~7900 Italian comuni. Filter on
    `CNTR_CODE == 'IT'` at load time.

Stage 04 resolves each IT record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Highest
     hit rate for the ~412 IT DOPs.
  2. **gisco-province-wide** — IGT fallback: disciplinare enumerates
     "tutti i comuni delle province di X e Y". Union by NUTS3 / LAU
     province prefix.
  3. **gisco-commune-list** — IGT fallback: enumerated comune list.
  4. **parent-appellation** — sub-record inherits parent polygon.
  5. **none** — no polygon available (logged in audit).

Italian commune-name matching: GISCO `LAU_NAME` carries the official
ISTAT spelling (e.g. "Castelnuovo Berardenga"). Disciplinari use the
same spelling. Normalise to lowercase + diacritic-strip for resilient
matching.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _normalise_commune_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Za-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Strip leading Italian articles
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in {"il", "la", "lo", "i", "gli", "le", "l"}:
        s = parts[1]
    return s


class _MuniCandidate:
    __slots__ = ("geom", "lau_id", "full_norm", "full_name")

    def __init__(self, geom: BaseGeometry, lau_id: str, full_norm: str, full_name: str):
        self.geom = geom
        self.lau_id = lau_id
        self.full_norm = full_norm
        self.full_name = full_name


class ITPolygonIndex:
    """In-memory polygon indexes for IT records. Lazy loader."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        self._munis_by_norm: dict[str, list[_MuniCandidate]] = {}
        self._munis_by_lau_id: dict[str, _MuniCandidate] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].str.startswith(("PDO-IT", "PGI-IT"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            it = gdf[gdf["CNTR_CODE"] == "IT"]
            if it.crs is None or it.crs.to_string() != target_crs:
                it = it.to_crs(target_crs)
            for _, row in it.iterrows():
                name = (row.get("LAU_NAME") or "").strip()
                gisco_id = row.get("GISCO_ID") or ""
                lau_id = gisco_id.split("_", 1)[1] if "_" in gisco_id else ""
                geom = row.geometry
                if geom is None or geom.is_empty or not name:
                    continue
                norm = _normalise_commune_name(name)
                cand = _MuniCandidate(
                    geom=geom, lau_id=lau_id, full_norm=norm, full_name=name,
                )
                self._munis_by_norm.setdefault(norm, []).append(cand)
                if lau_id:
                    self._munis_by_lau_id[lau_id] = cand

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_comuni(self) -> int:
        return sum(len(v) for v in self._munis_by_norm.values())

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def union_communes(
        self, commune_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        polys: list[BaseGeometry] = []
        matched = unmatched = 0
        seen_lau: set[str] = set()
        for name in commune_names:
            norm = _normalise_commune_name(name or "")
            if not norm:
                continue
            cands = self._munis_by_norm.get(norm, [])
            if not cands:
                unmatched += 1
                continue
            # If duplicates exist (rare for IT — distinct comuni have
            # distinct names in ISTAT), accept all matching candidates.
            for cand in cands:
                if cand.lau_id in seen_lau:
                    continue
                seen_lau.add(cand.lau_id)
                polys.append(cand.geom)
            matched += 1
        if not polys:
            return None, {"matched": matched, "unmatched": unmatched}
        return unary_union(polys), {"matched": matched, "unmatched": unmatched}
