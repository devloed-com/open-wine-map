"""SIGPAC parcel-level geometry for Spanish wine appellations.

SIGPAC (Sistema de Información Geográfica de Parcelas Agrícolas) is the
Spanish regulator's parcel-level cadastral layer for agricultural land —
the analog of FR's INAO `parcellaire/` shapefile. Each row is a single
recinto (sub-parcel) with classification (`US` field: `VI`=vineyard,
`OV`=olives, `FO`=forest, `PR`=pasture, …), province + municipio
codes, polygon + parcela + recinto numbers, and the polygon geometry.

The data is published per-province by the regional FEGA mirrors. For
Catalonia the per-comarca breakdown lives at
`analisi.transparenciacatalunya.cat` (Socrata API). URL catalog under
`scripts/_lib/es/sigpac_catalonia_urls.json`.

This module loads one or more comarca .gpkg files and exposes:

  - vineyard parcels filtered to `US == "VI"`
  - lookup by (commune INE, polygon number) so we can resolve pliego
    inclusion lists like "polígonos números 1, 4, 5, 6, 7, 21 y 25 del
    municipio de Falset" into a clean (Multi)Polygon.

Pliegos for Spanish wines that share communes with neighbours (e.g.
Priorat ↔ Montsant share Falset, El Molar, Garcia, Mora la Nova,
Tivissa, splitting them at SIGPAC-polygon level) need this granularity
to avoid the commune-precision overlap that Figshare 2022 produces.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _normalise_municipi(s: str) -> str:
    """Strip diacritics, leading articles, lowercase. SIGPAC writes
    Catalan municipi names in lowercase-after-article form (`el Molar`,
    `la Vilella Alta`); pliegos write them in titlecase or with the
    article prefix. We normalise both sides for matching."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    for art in ("el ", "la ", "els ", "les ", "lo ", "los ", "las "):
        if s.startswith(art):
            s = s[len(art):]
    return s


@dataclass
class SigpacComarca:
    """One Catalan comarca's SIGPAC layer loaded into memory. Reading
    the full ~130 MB gpkg + reprojecting takes ~5 sec — instantiate
    once per comarca and reuse."""
    comarca_codi: str  # e.g. "29" for Priorat
    municipios: dict[str, "_MunicipioSigpac"]  # ine_5digit → parcels


@dataclass
class _MunicipioSigpac:
    ine: str  # 5-digit INE municipi code (e.g. "43054" for Falset)
    name: str
    name_norm: str
    parcels_by_polygon: dict[int, list[BaseGeometry]]
    all_vineyards: BaseGeometry | None  # union of all VI parcels in this municipio


def load_sigpac_comarca(
    gpkg_path: Path, target_crs: str = "EPSG:4326",
) -> SigpacComarca:
    """Load one Catalan comarca's SIGPAC gpkg, filter to vineyards,
    index by (municipio INE, polygon number).

    Returns SigpacComarca whose `municipios` dict is keyed by the
    5-digit INE code (e.g. "43054" for Falset)."""
    gdf = gpd.read_file(gpkg_path)
    if gdf.crs is None or gdf.crs.to_string() != target_crs:
        gdf = gdf.to_crs(target_crs)
    vi = gdf[gdf["US"] == "VI"].copy()
    # ID_MUN is the 5-digit INE code (province*1000 + municipio).
    vi["ID_MUN"] = vi["ID_MUN"].astype(str)

    municipios: dict[str, _MunicipioSigpac] = {}
    comarca_codi = ""
    for ine, group in vi.groupby("ID_MUN"):
        name = group["MUNICIPI"].iloc[0]
        if not comarca_codi:
            comarca_codi = str(group["ID_COM"].iloc[0])
        by_polygon: dict[int, list[BaseGeometry]] = {}
        for _, row in group.iterrows():
            pol = int(row["POL"])
            by_polygon.setdefault(pol, []).append(row.geometry)
        union_all = unary_union([g for polys in by_polygon.values() for g in polys])
        municipios[ine] = _MunicipioSigpac(
            ine=ine,
            name=name,
            name_norm=_normalise_municipi(name),
            parcels_by_polygon=by_polygon,
            all_vineyards=union_all,
        )
    return SigpacComarca(comarca_codi=comarca_codi, municipios=municipios)


class SigpacIndex:
    """Multi-comarca union of SIGPAC parcel data. Construct with a list
    of comarca .gpkg paths; query by municipi-name + polygon list."""

    def __init__(self, comarca_paths: Iterable[Path], target_crs: str = "EPSG:4326"):
        self.target_crs = target_crs
        self._by_municipi_norm: dict[str, _MunicipioSigpac] = {}
        self._n_comarques = 0
        for p in comarca_paths:
            if not p.exists():
                continue
            comarca = load_sigpac_comarca(p, target_crs=target_crs)
            self._n_comarques += 1
            for ine, muni in comarca.municipios.items():
                # Index by both INE and normalised name; pliegos cite the
                # name, but the INE is the authoritative join key.
                self._by_municipi_norm[muni.name_norm] = muni
                self._by_municipi_norm[ine] = muni

    @property
    def n_comarques(self) -> int:
        return self._n_comarques

    @property
    def n_municipios(self) -> int:
        # Each municipi appears in the index under both name + INE, so divide
        return len({m.ine for m in self._by_municipi_norm.values()})

    def municipi_vineyards(self, name_or_ine: str) -> BaseGeometry | None:
        """Union of ALL vineyard parcels in a municipi. Returns None if
        the municipi isn't loaded (i.e. its comarca isn't in our paths)."""
        key = _normalise_municipi(name_or_ine) if not name_or_ine.isdigit() else name_or_ine
        muni = self._by_municipi_norm.get(key)
        return muni.all_vineyards if muni else None

    def polygons_in_municipi(
        self, name_or_ine: str, polygon_numbers: Iterable[int],
    ) -> BaseGeometry | None:
        """Union of vineyard parcels in the named municipi limited to
        the given SIGPAC polygon numbers (the `POL` column). Used by
        the pliego inclusion-list resolver to compute the actual area
        a wine appellation claims within a shared commune."""
        key = _normalise_municipi(name_or_ine) if not name_or_ine.isdigit() else name_or_ine
        muni = self._by_municipi_norm.get(key)
        if muni is None:
            return None
        wanted = set(polygon_numbers)
        polys = [g for pol, gs in muni.parcels_by_polygon.items() if pol in wanted for g in gs]
        if not polys:
            return None
        return unary_union(polys)
