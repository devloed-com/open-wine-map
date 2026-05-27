"""CZ-side geometry resolution — Bétard PDO + region-PGI-union +
GISCO commune-union for the 6 podoblasti.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 11 Czech DOPs (`PDO-CZ-*`). Czechia joined the EU in 2004; all
    PDOs predate Bétard's Nov-2021 snapshot.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — 6,258 Czech obce (CNTR_CODE='CZ') used for the
    podoblast commune-union resolver.

Stage 04 resolves each CZ record by:

  1. **gisco-commune-union-podoblast** — for the 6 podoblasti
     (Litoměřická / Mělnická / Slovácká / Znojemská / Velkopavlovická /
     Mikulovská), union the GISCO LAU polygons matching the obce
     enumerated in Vyhláška č. 254/2010 Sb., Příloha (parsed by
     `scripts/cz/02f_extract_national_specs.py` into
     `raw/cz/national-specs/communes/<slug>.json`). The Vyhláška names
     each obec exactly; matches against `LAU_NAME` after diacritic +
     case folding (see `_lib/cz/commune._normalise_commune`). Returns
     a commune-precision polygon — more honest than Bétard's
     macro-region-aggregated PDO polygon for these sub-regions.
  2. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022. Used for the 4 macro names (Čechy / Morava / Šobes /
     Znojmo / Novosedelské and a few others) where the Vyhláška
     either doesn't enumerate a list (whole region) or the wine is a
     single-vineyard PDO.
  3. **region-pdo-union** — the 2 CZ PGIs (`PGI-CZ-A0900` "české" /
     `PGI-CZ-A0902` "moravské") = the matching macro PDO's polygon
     (single-member union, since the territory is coextensive with
     the macro PDO of the same name).
  4. **stub-no-geometry** — no polygon available (logged in audit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .commune import _normalise_commune

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. Each Czech PGI maps to a single macro PDO (the
# territory is coextensive with the macro PDO of the same name).
CZ_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-CZ-A0900": (  # české — whole Bohemia
        "PDO-CZ-A0888",  # Čechy
    ),
    "PGI-CZ-A0902": (  # moravské — whole Moravia
        "PDO-CZ-A0899",  # Morava
    ),
}

# CZ wine GIs that are vinařské podoblasti — these have an enumerated
# obec list in Vyhláška 254/2010 Sb., Příloha. Resolved via
# gisco-commune-union-podoblast (more precise than Bétard's
# macro-region-aggregated polygon).
CZ_PODOBLAST_PDOS: dict[str, str] = {
    # file_number → podoblast slug (matches raw/cz/national-specs/communes/<slug>.json)
    "PDO-CZ-A0894": "litomericka",
    "PDO-CZ-A0895": "melnicka",
    "PDO-CZ-A0890": "slovacka",
    "PDO-CZ-A0892": "znojemska",
    "PDO-CZ-A0896": "velkopavlovicka",
    "PDO-CZ-A0897": "mikulovska",
}


class CZPolygonIndex:
    """In-memory polygon index for CZ records, backed by Bétard 2022 +
    GISCO LAU 2024 + Vyhláška 254/2010 Sb. commune lists."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        national_specs_dir: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        self._lau_by_name: dict[str, list[BaseGeometry]] = {}
        self._n_lau = 0
        self._communes_by_podoblast: dict[str, list[str]] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-CZ", "PGI-CZ"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            cz = gdf[gdf["CNTR_CODE"] == "CZ"]
            if cz.crs is None or cz.crs.to_string() != target_crs:
                cz = cz.to_crs(target_crs)
            for _, r in cz.iterrows():
                name = (r.get("LAU_NAME") or "").strip()
                geom = r.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                self._lau_by_name.setdefault(_normalise_commune(name), []).append(geom)
                self._n_lau += 1

        if national_specs_dir is not None and (national_specs_dir / "communes").exists():
            import json
            for jp in sorted((national_specs_dir / "communes").glob("*.json")):
                d = json.loads(jp.read_text(encoding="utf-8"))
                self._communes_by_podoblast[jp.stem] = d.get("communes") or []

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    @property
    def n_podoblasti_with_communes(self) -> int:
        return len(self._communes_by_podoblast)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        members = CZ_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def commune_union_for_podoblast(
        self, podoblast_slug: str,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons matching the obce of one
        podoblast (as enumerated in Vyhláška 254/2010 Sb. Příloha)."""
        communes = self._communes_by_podoblast.get(podoblast_slug, [])
        polys: list[BaseGeometry] = []
        matched: list[str] = []
        unmatched: list[str] = []
        for name in communes:
            key = _normalise_commune(name)
            if not key:
                continue
            cands = self._lau_by_name.get(key)
            if not cands:
                unmatched.append(name)
                continue
            polys.extend(cands)
            matched.append(name)
        stats = {
            "matched": len(matched),
            "unmatched": len(unmatched),
            "names_unmatched": unmatched[:30],
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one CZ record by file_number.
        Returns (geometry, geom_source, stats).

        Order: podoblast commune-union → Bétard PDO → PGI member union →
        stub-no-geometry. The podoblast commune-union runs first for the
        6 podoblasti because it's commune-precise; Bétard is a coarser
        macro-region-aggregated polygon for those (still a valid
        fallback if the commune-union returns nothing)."""
        fn = file_number or ""
        # 1. Per-podoblast commune-union (the 6 sub-region DOPs).
        pod_slug = CZ_PODOBLAST_PDOS.get(fn)
        if pod_slug and pod_slug in self._communes_by_podoblast:
            geom, ustats = self.commune_union_for_podoblast(pod_slug)
            if geom is not None and not geom.is_empty:
                stats = {
                    "matched": ustats["matched"],
                    "unmatched": ustats["unmatched"],
                    "podoblast_slug": pod_slug,
                    "names_unmatched": ustats.get("names_unmatched") or [],
                }
                return geom, "gisco-commune-union-podoblast", stats
            # fall through to Bétard

        # 2. PGIs — member union.
        if fn in CZ_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats

        # 3. Direct Bétard PDO match.
        geom = self._pdo_polygons.get(fn)
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
