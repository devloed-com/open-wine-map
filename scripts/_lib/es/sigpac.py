"""SIGPAC parcel-level geometry for Spanish wine appellations.

SIGPAC (Sistema de Información Geográfica de Parcelas Agrícolas) is the
Spanish regulator's parcel-level cadastral layer for agricultural land —
the analog of FR's INAO `parcellaire/` shapefile. Each row is a single
recinto (sub-parcel) with classification (`US` field: `VI`=vineyard,
`OV`=olives, `FO`=forest, `PR`=pasture, …), province + municipio
codes, polygon + parcela + recinto numbers, and the polygon geometry.

Two publications feed this module, both fetched by `scripts/es/00_fetch_data.py`:

  - Catalonia's per-comarca GeoPackages (`analisi.transparenciacatalunya.cat`,
    catalogue `scripts/_lib/es/sigpac_catalonia_urls.json`) — Catalan
    field names (`ID_MUN`, `MUNICIPI`, `ID_COM`, `POL`, `US`).
  - FEGA's national per-province GeoPackages (`sigpac-hubcloud.es`,
    CC BY 4.0, catalogue `scripts/_lib/es/sigpac_fega_urls.json`) —
    lowercase fields (`provincia`, `municipio`, `poligono`, `uso_sigpac`)
    and no municipio name; stage 00 writes a per-municipio extract that
    adds `municipio_nombre` from the catalogue. `_fega_frame_as_catalan`
    maps that schema onto the Catalan one, so the rest of the loader is
    shared and the Catalan path is untouched.

This module loads one or more such .gpkg files and exposes:

  - vineyard parcels filtered to `US == "VI"`
  - lookup by (commune INE, polygon number) so we can resolve pliego
    inclusion lists like "polígonos números 1, 4, 5, 6, 7, 21 y 25 del
    municipio de Falset" into a clean (Multi)Polygon.
  - the same lookup over every recinto of a polígono, any land use —
    the polígono's footprint (`polygon_footprints_in_municipi`).

A listed polígono can be read two ways, and `SIGPAC_INCLUSION_SEMANTICS`
pins which one a record gets:

  - `footprint` (the default): the cadastral polígono IS the delimited
    area — a plot inside it that is planted qualifies — so the whole
    polígono is drawn. Sierra Sur de Jaén's "zonas de sierra … polígonos
    catastrales actuales del 1 al 12" hold no vineyard today; the VI
    reading drew four plots and nothing of Alcaudete (2026-09-24).
  - `vineyard`: only the recintos in use VI, the parcels actually under
    vine. Priorat / Montsant delimit "las parcelas de viña situadas en
    …" and their polígonos are nearly all vines; that is the original
    design and both records are the project's ES smoke-test anchors.

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
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

SIGPAC_SEMANTICS_FOOTPRINT = "footprint"
SIGPAC_SEMANTICS_VINEYARD = "vineyard"

# Per-record reading of a polígono inclusion (see the module docstring).
# Unpinned records get the footprint; a pin is curated with its reason.
SIGPAC_INCLUSION_SEMANTICS: dict[str, str] = {
    # No record is pinned. Priorat and Montsant carried the `vineyard`
    # reading from 2026-05 to 2026-09-24 (their polígonos are nearly all
    # vines and Montsant's pliego says "las parcelas de viña situadas en
    # …"); the same logic that settled Sierra Sur applies to them — a
    # parcel that comes under vine inside a listed polígono qualifies, so
    # the polígono is the area (decision 2026-09-24). Pin a slug here only
    # with a reason the pliego's own wording supports.
}

# Attribution the panel shows per publication (`SigpacComarca.publication`).
# The Catalan portal's terms are recorded by stage 00 only as "free reuse
# with attribution" — no licence name or URL is on file, so none is shown.
SIGPAC_SOURCES: dict[str, dict[str, str]] = {
    "fega": {
        "attribution": "© FEGA / MAPA, SIGPAC",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/deed.es",
        "url": "https://sigpac-hubcloud.es/html/sdsigpac/descServicio.html",
    },
    "catalunya": {
        "attribution": "© Generalitat de Catalunya / DARP, SIGPAC",
        "licence": "",
        "licence_url": "",
        "url": "https://analisi.transparenciacatalunya.cat/",
    },
}


def inclusion_semantics(slug: str) -> str:
    return SIGPAC_INCLUSION_SEMANTICS.get(slug, SIGPAC_SEMANTICS_FOOTPRINT)


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
    # Every municipio in the file, vineyard or not, for the footprint
    # lookup, which re-reads the file on demand (`_FEGA_SCHEMA` decides
    # the filter's column names).
    source_path: Path | None = None
    schema: str = "catalan"
    publication: str = "catalunya"
    municipio_names: dict[str, str] | None = None  # ine_5digit → name


@dataclass
class _MunicipioSigpac:
    ine: str  # 5-digit INE municipi code (e.g. "43054" for Falset)
    name: str
    name_norm: str
    parcels_by_polygon: dict[int, list[BaseGeometry]]
    all_vineyards: BaseGeometry | None  # union of all VI parcels in this municipio


def _fega_frame_as_catalan(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Rename a FEGA recintos frame to the Catalan column set the loader
    indexes on. `ID_MUN` is province × 1000 + Catastro municipio code
    (the INE code for the provinces in the catalogue), zero-padded to the
    five digits of an INE code — Ávila's Órbita is "05176", never "5176";
    `MUNICIPI` is the extract's `municipio_nombre` (the INE name) or,
    absent, the code."""
    out = gdf.rename(columns={"poligono": "POL", "uso_sigpac": "US"})
    prov = gdf["provincia"].astype(int)
    out["ID_MUN"] = (prov * 1000 + gdf["municipio"].astype(int)).map("{:05d}".format)
    if "municipio_nombre" in gdf.columns:
        out["MUNICIPI"] = gdf["municipio_nombre"].fillna(out["ID_MUN"])
    else:
        out["MUNICIPI"] = out["ID_MUN"]
    out["ID_COM"] = "fega-" + prov.map("{:02d}".format)
    return out


_FEGA_SCHEMA = "fega"
_CATALAN_SCHEMA = "catalan"


def _polygon_where(schema: str, ine: str, polygon_numbers: Iterable[int]) -> str:
    """OGR filter for the recintos of one municipio's polígonos. The Catalan
    files key the municipio by the INE text; FEGA's by province + Catastro
    code (INE = province × 1000 + code)."""
    pols = ",".join(str(int(p)) for p in sorted(set(polygon_numbers)))
    if schema == _FEGA_SCHEMA:
        return (
            f"provincia = {int(ine) // 1000} AND municipio = {int(ine) % 1000}"
            f" AND poligono IN ({pols})"
        )
    return f"ID_MUN = '{ine}' AND POL IN ({pols})"


def load_sigpac_comarca(
    gpkg_path: Path, target_crs: str = "EPSG:4326",
) -> SigpacComarca:
    """Load one SIGPAC gpkg (a Catalan comarca, or a FEGA province
    extract), filter to vineyards, index by (municipio INE, polygon
    number).

    Returns SigpacComarca whose `municipios` dict is keyed by the
    5-digit INE code (e.g. "43054" for Falset)."""
    gdf = gpd.read_file(gpkg_path)
    schema = _CATALAN_SCHEMA
    if "MUNICIPI" not in gdf.columns and "municipio" in gdf.columns:
        gdf = _fega_frame_as_catalan(gdf)
        schema = _FEGA_SCHEMA
    if gdf.crs is None or gdf.crs.to_string() != target_crs:
        gdf = gdf.to_crs(target_crs)
    names = {
        str(ine): str(name)
        for ine, name in gdf.groupby(gdf["ID_MUN"].astype(str))["MUNICIPI"].first().items()
    }
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
    return SigpacComarca(
        comarca_codi=comarca_codi, municipios=municipios,
        source_path=gpkg_path, schema=schema,
        publication="fega" if schema == _FEGA_SCHEMA else "catalunya",
        municipio_names=names,
    )


class SigpacIndex:
    """Multi-file union of SIGPAC parcel data (Catalan comarques and
    FEGA province extracts alike). Construct with a list of .gpkg paths;
    query by municipi-name / INE + polygon list."""

    def __init__(self, comarca_paths: Iterable[Path], target_crs: str = "EPSG:4326"):
        self.target_crs = target_crs
        self._by_municipi_norm: dict[str, _MunicipioSigpac] = {}
        # Every municipio of every file, keyed like `_by_municipi_norm`, so
        # a municipio without a single vineyard (Alcaudete) still resolves
        # for the footprint reading.
        self._footprint_muni: dict[str, tuple[SigpacComarca, str]] = {}
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
            for ine, name in (comarca.municipio_names or {}).items():
                self._footprint_muni[_normalise_municipi(name)] = (comarca, ine)
                self._footprint_muni[ine] = (comarca, ine)

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

    def vineyard_polygons_present(
        self, name_or_ine: str, polygon_numbers: Iterable[int],
    ) -> set[int]:
        """The requested polygon numbers that hold at least one vineyard
        parcel — what `polygons_in_municipi` actually drew."""
        key = _normalise_municipi(name_or_ine) if not name_or_ine.isdigit() else name_or_ine
        muni = self._by_municipi_norm.get(key)
        if muni is None:
            return set()
        return set(polygon_numbers) & set(muni.parcels_by_polygon)

    def municipio_publication(self, name_or_ine: str) -> str | None:
        """Which publication (`SIGPAC_SOURCES` key) holds the municipio."""
        key = _normalise_municipi(name_or_ine) if not name_or_ine.isdigit() else name_or_ine
        hit = self._footprint_muni.get(key)
        return hit[0].publication if hit else None

    def polygon_footprints_in_municipi(
        self, name_or_ine: str, polygon_numbers: Iterable[int],
    ) -> tuple[BaseGeometry | None, set[int]]:
        """Union of the requested polígonos taken whole: every recinto of
        each, whatever its land use, dissolved into one geometry per
        polígono, then unioned. Returns (geometry, polygon numbers found).

        The file is re-read with an OGR filter rather than kept in memory:
        the vineyard index above stays exactly as it is, and the all-use
        recintos (111 k for the Priorat comarca) are needed by the few
        records read as footprints."""
        key = _normalise_municipi(name_or_ine) if not name_or_ine.isdigit() else name_or_ine
        hit = self._footprint_muni.get(key)
        wanted = {int(p) for p in polygon_numbers}
        if hit is None or not wanted:
            return None, set()
        comarca, ine = hit
        gdf = gpd.read_file(comarca.source_path, where=_polygon_where(comarca.schema, ine, wanted))
        if gdf.empty:
            return None, set()
        if comarca.schema == _FEGA_SCHEMA:
            gdf = _fega_frame_as_catalan(gdf)
        if gdf.crs is None or gdf.crs.to_string() != self.target_crs:
            gdf = gdf.to_crs(self.target_crs)
        # FEGA ships a few self-touching recintos; a union over them raises.
        geoms = shapely.make_valid(gdf.geometry.values)
        pols = gdf["POL"].astype(int).values
        found = sorted(set(pols.tolist()) & wanted)
        footprints = [unary_union(geoms[pols == pol]) for pol in found]
        return unary_union(footprints), set(found)
