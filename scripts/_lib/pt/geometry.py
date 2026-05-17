"""PT-side geometry resolution — pull DOP polygons from Bétard 2022
Figshare and union concelho polygons from DGT CAOP 2025.

Two sources, one chain. Stage 04 resolves each PT record by:

  1. **figshare-pdo** — exact `file_number` (`PDO-PT-Axxxx`) → `PDOid`
     match against `raw/es/figshare/EU_PDO.gpkg` (the same Bétard 2022
     dataset the ES pipeline uses; it covers all EU PDOs). Expected
     hit-rate: ~30 of 30 PT DOPs.
  2. **caop-concelho-union** — union of CAOP 2025 município polygons
     matched against an enumerated commune list. Used for IGPs that
     don't have a Figshare row, and as a fallback for newer DOPs.
  3. **parent-appellation** — sub-região inherits the parent's
     polygon when no commune list is parsed.
  4. **none** — no polygon available (logged for the audit).

CAOP carries three levels (distrito → município → freguesia). For v1
we match at the município (concelho) level — sufficient for IGP-wide
fallback and the typical caderno commune-list precision. Freguesia-
level matching is a follow-up; the CAOP layer is loaded once and the
freguesia data lives alongside município.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _normalise_concelho(s: str) -> str:
    """Strip diacritics + leading articles, lowercase, collapse spaces."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Za-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Strip leading Portuguese articles
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in {"o", "a", "os", "as", "do", "da", "dos", "das"}:
        s = parts[1]
    return s


class _Concelho:
    __slots__ = ("geom", "name", "norm", "distrito")

    def __init__(
        self, geom: BaseGeometry, name: str, norm: str, distrito: str
    ) -> None:
        self.geom = geom
        self.name = name
        self.norm = norm
        self.distrito = distrito


class PTPolygonIndex:
    """In-memory polygon indexes for PT records.

    Lazy loader — pass paths in the constructor; reading + reprojecting
    the gpkgs takes a few seconds. Reuse one instance across all
    stage-04 PT iterations.
    """

    def __init__(
        self,
        figshare_gpkg: Path,
        caop_gpkgs: list[Path],
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # norm → list of concelho candidates
        self._concelho_by_norm: dict[str, list[_Concelho]] = {}
        # normalised distrito name → list of concelhos in that distrito
        self._concelhos_by_distrito: dict[str, list[_Concelho]] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            mask = gdf["PDOid"].astype(str).str.startswith(("PDO-PT", "PGI-PT"))
            gdf = gdf[mask]
            if not gdf.empty:
                if gdf.crs is None or gdf.crs.to_string() != target_crs:
                    gdf = gdf.to_crs(target_crs)
                for _, row in gdf.iterrows():
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        # CAOP gpkgs: Continente, RAA (Açores), RAM (Madeira). The
        # schema is consistent across all three: `*_municipios` layer
        # with `municipio` + `distrito_ilha` fields. We read the
        # município layer in each (~305 concelhos across all PT).
        for gpkg in caop_gpkgs:
            if not gpkg.exists():
                continue
            try:
                layers = gpd.list_layers(gpkg)["name"].tolist()
            except Exception:  # noqa: BLE001
                continue
            muni_layer = next(
                (name for name in layers
                 if name and "municipios" in name.lower()),
                None,
            )
            if muni_layer is None:
                continue
            try:
                gdf = gpd.read_file(gpkg, layer=muni_layer)
            except Exception:  # noqa: BLE001
                continue
            if gdf.empty:
                continue
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                name = (row.get("municipio") or "").strip()
                distrito = (row.get("distrito_ilha") or "").strip()
                geom = row.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                norm = _normalise_concelho(name)
                c = _Concelho(geom=geom, name=name, norm=norm, distrito=distrito)
                self._concelho_by_norm.setdefault(norm, []).append(c)
                if distrito:
                    dnorm = _normalise_concelho(distrito)
                    self._concelhos_by_distrito.setdefault(dnorm, []).append(c)
                    # Açores / Madeira distrito_ilha rows are prefixed
                    # with "Ilha de" / "Ilha do" / "Ilha da" — index a
                    # bare-name variant too so cadernos can say "Pico"
                    # (the ilha) and still match.
                    bare = re.sub(
                        r"^ilha\s+(?:de|do|da)\s+", "", dnorm, flags=re.IGNORECASE,
                    )
                    if bare and bare != dnorm:
                        self._concelhos_by_distrito.setdefault(bare, []).append(c)

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_concelhos(self) -> int:
        return sum(len(v) for v in self._concelho_by_norm.values())

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    @property
    def n_distritos(self) -> int:
        return len(self._concelhos_by_distrito)

    def union_concelhos(
        self, concelho_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union CAOP município polygons matched by normalised name.
        Returns (geom, stats={'matched','unmatched'}). Best-effort match —
        ambiguous names (rare for PT concelhos vs ES communes) take the
        first candidate."""
        geoms: list[BaseGeometry] = []
        matched = unmatched = 0
        for name in concelho_names:
            if not name:
                continue
            norm = _normalise_concelho(name)
            candidates = self._concelho_by_norm.get(norm)
            if not candidates:
                unmatched += 1
                continue
            geoms.append(candidates[0].geom)
            matched += 1
        if not geoms:
            return None, {"matched": matched, "unmatched": unmatched}
        return unary_union(geoms), {"matched": matched, "unmatched": unmatched}

    def union_distritos(
        self, distrito_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union every CAOP município that lives in one of the named
        distritos. Used for the "Todos os municípios dos distritos de
        X e Y" pattern (Vinho Verde: Braga + Viana do Castelo).
        Returns the same (geom, stats) shape as `union_concelhos`."""
        geoms: list[BaseGeometry] = []
        matched = unmatched = 0
        for name in distrito_names:
            if not name:
                continue
            norm = _normalise_concelho(name)
            concelhos = self._concelhos_by_distrito.get(norm)
            if not concelhos:
                unmatched += 1
                continue
            for c in concelhos:
                geoms.append(c.geom)
                matched += 1
        if not geoms:
            return None, {"matched": matched, "unmatched": unmatched}
        return unary_union(geoms), {"matched": matched, "unmatched": unmatched}

    def union_from_parsed(
        self, parsed: dict
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Combine `union_concelhos` + `union_distritos` into one call.
        Takes the dict returned by `commune_list.parse_commune_list`."""
        geoms: list[BaseGeometry] = []
        stats = {"concelhos_matched": 0, "concelhos_unmatched": 0,
                 "distritos_matched": 0, "distritos_unmatched": 0}
        if parsed.get("concelhos"):
            g, s = self.union_concelhos(parsed["concelhos"])
            stats["concelhos_matched"] = s["matched"]
            stats["concelhos_unmatched"] = s["unmatched"]
            if g is not None and not g.is_empty:
                geoms.append(g)
        if parsed.get("distritos"):
            g, s = self.union_distritos(parsed["distritos"])
            stats["distritos_matched"] = s["matched"]
            stats["distritos_unmatched"] = s["unmatched"]
            if g is not None and not g.is_empty:
                geoms.append(g)
        if not geoms:
            return None, stats
        return unary_union(geoms), stats
