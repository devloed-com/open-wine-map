"""BG-side geometry resolution — Bétard PDO + region-PGI-union +
GISCO commune-list fallback.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all EU PDOs including the 52 Bulgarian DOPs (`PDO-BG-*`).
    Bulgaria joined the EU in 2007; every BG PDO predates the
    Nov-2021 cutoff.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — ~265 Bulgarian obshtina polygons (CNTR_CODE='BG')
    used by the commune-list fallback when a record's commune list is
    parseable but its file_number isn't in Bétard.

Stage 04 resolves each BG record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Expected
     to cover all 52 BG DOPs.
  2. **region-pdo-union** — the 2 BG PGIs (Дунавска равнина /
     Тракийска низина) are the 2 macro Bulgarian wine territories
     (north of Stara Planina vs south). Bétard is PDO-only, so a PGI
     has no polygon of its own; we union the Figshare polygons of the
     member PDOs that lie inside that macro region. The mapping is
     structural and hand-verified against the Bulgarian wine-law
     5-region classification.
  3. **gisco-commune-list** — parse the documento-unic geo-area body
     into obshtina names (Cyrillic-preserving) and union matching
     GISCO LAU polygons (CNTR_CODE='BG'). Mirrors the RO chain.
  4. **stub-no-geometry** — no polygon resolvable (logged in audit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. North-of-Stara-Planina = Дунавска равнина PGI;
# south-of-Stara-Planina (Черноморски район + Розова долина + Тракийска
# низина + Долината на Струма) = Тракийска низина PGI. Hand-verified
# against `scripts/_lib/bg/region.py:_REGION_BY_FILE_NUMBER`.
BG_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-BG-A1538": (  # Дунавска равнина — 21 northern PDOs
        "PDO-BG-A0952",  # Драгоево
        "PDO-BG-A1030",  # Хан Крум
        "PDO-BG-A0951",  # Лясковец
        "PDO-BG-A1441",  # Лом
        "PDO-BG-A0956",  # Ловеч
        "PDO-BG-A0360",  # Лозица
        "PDO-BG-A1314",  # Монтана
        "PDO-BG-A1031",  # Нови Пазар
        "PDO-BG-A0382",  # Ново село
        "PDO-BG-A1344",  # Оряховица
        "PDO-BG-A0420",  # Павликени
        "PDO-BG-A1477",  # Плевен
        "PDO-BG-A1425",  # Русе
        "PDO-BG-A0997",  # Шумен
        "PDO-BG-A1018",  # Сухиндол
        "PDO-BG-A0957",  # Свищов
        "PDO-BG-A1439",  # Търговище
        "PDO-BG-A0370",  # Върбица
        "PDO-BG-A0885",  # Велики Преслав
        "PDO-BG-A1346",  # Видин
        "PDO-BG-A0955",  # Враца
    ),
    "PGI-BG-A1552": (  # Тракийска низина — 31 southern PDOs
        # Черноморски район (Black Sea coast) — 8
        "PDO-BG-A1392",  # Черноморски район
        "PDO-BG-A0881",  # Евксиноград
        "PDO-BG-A1347",  # Южно Черноморие
        "PDO-BG-A1175",  # Карнобат
        "PDO-BG-A0430",  # Поморие
        "PDO-BG-A1008",  # Славянци
        "PDO-BG-A1489",  # Сунгурларе
        "PDO-BG-A1032",  # Варна
        # Розова долина (Sub-Balkan / Rose Valley) — 2
        "PDO-BG-A1044",  # Карлово
        "PDO-BG-A1393",  # Хисаря
        # Тракийска низина (South-Central) — 17
        "PDO-BG-A0877",  # Асеновград
        "PDO-BG-A0985",  # Болярово
        "PDO-BG-A0944",  # Брестник
        "PDO-BG-A1179",  # Ямбол
        "PDO-BG-A1047",  # Ивайловград
        "PDO-BG-A1043",  # Хасково
        "PDO-BG-A1177",  # Любимец
        "PDO-BG-A1494",  # Нова Загора
        "PDO-BG-A1182",  # Пазарджик
        "PDO-BG-A1474",  # Перущица
        "PDO-BG-A1297",  # Пловдив
        "PDO-BG-A0013",  # Сакар
        "PDO-BG-A1185",  # Септември
        "PDO-BG-A1391",  # Шивачево
        "PDO-BG-A1190",  # Сливен
        "PDO-BG-A1487",  # Стамболово
        "PDO-BG-A1394",  # Стара Загора
        # Долината на Струма (Struma Valley) — 4
        "PDO-BG-A1473",  # Долината на Струма
        "PDO-BG-A0946",  # Хърсово
        "PDO-BG-A1472",  # Мелник
        "PDO-BG-A1006",  # Сандански
    ),
}


class BGPolygonIndex:
    """In-memory polygon index for BG records: Bétard PDO + PGI-union
    + GISCO obshtina-list fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        self._lau_by_name: dict[str, list[BaseGeometry]] = {}
        self._n_lau = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-BG", "PGI-BG"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(gisco_lau_zip)
            bg = gdf[gdf["CNTR_CODE"] == "BG"]
            if bg.crs is None or bg.crs.to_string() != target_crs:
                bg = bg.to_crs(target_crs)
            for _, r in bg.iterrows():
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

    def pgi_union(
        self, pgi_file_number: str,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the member-PDO polygons for one of the 2 BG PGIs.
        Returns (geometry, stats) where stats records how many member
        PDOs resolved."""
        members = BG_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def commune_union(
        self, commune_names: Iterable[str],
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons matching the given obshtina
        names (after Cyrillic-preserving normalisation)."""
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
        """Resolve geometry for one BG record. Returns (geometry,
        geom_source, stats). Bétard PDO match first; PGI-union for the
        2 macro PGIs; GISCO commune-union fallback otherwise."""
        fn = file_number or ""
        # PGIs first — they're not in Bétard, resolve via member union.
        if fn in BG_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            # Fall through to commune-list if PGI member union returned
            # nothing (should not happen with the hand-verified map).
            if commune_names:
                geom, stats = self.commune_union(commune_names)
                if geom is not None:
                    return geom, "gisco-commune-list", stats
            return None, "stub-no-geometry", stats
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
