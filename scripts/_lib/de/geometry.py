"""DE-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    EU PDOs registered before Nov-2021, including the 13 traditional
    German Anbaugebiete (`PDO-DE-A12xx`, `PDO-DE-A0867`).

Stage 04 resolves each DE record by:

  1. **parent-appellation** — Einzellage sub-denominations (Bürgstadter
     Berg → Franken, Monzinger Niederberg → Nahe, the three Uhlen → Mosel,
     Würzburger Stein-Berg → Franken) inherit the parent Anbaugebiet's
     polygon. The Einzellage's own commune-level polygon is not in
     Bétard; without a per-site dataset (cadastral parcels), the
     honest precision is parent-Anbaugebiet.
  2. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers
     the 13 regional PDOs.
  3. **region-pdo-union** — the 27 DE Landwein PGIs are not in Bétard
     (PDO-only dataset). For PGIs whose territory equals one of the 13
     Anbaugebiete (Badischer Landwein = Baden, Pfälzer Landwein = Pfalz,
     Nahegauer Landwein = Nahe, Sächsischer Landwein = Sachsen, …),
     we use the parent PDO's polygon as the IGP geometry — same
     approach the SI / HU / BG pipelines use for their region-equal
     PGIs.
  4. **stub-no-geometry** — no polygon available. The remaining ~10
     PGIs span multi-Bundesland territories that don't equal any single
     Anbaugebiet (Brandenburger Landwein, Mitteldeutscher Landwein,
     Schleswig-Holsteinischer Landwein, Mecklenburger Landwein, …).
     Phase 2: parse the commune list out of the Einziges Dokument and
     union the GISCO LAU DE polygons (same pattern as RO IGPs).

Recently-registered PDOs not in Bétard 2022 (the 6 Einzellage PDOs and
a couple of newer regional ones) fall through to the parent-appellation
inheritance step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Landwein PGI file_number → the regional-PDO file_number whose polygon
# matches the PGI's territory. Conservative — only included where the
# PGI explicitly covers the same Anbaugebiet (the EU-OJ Einziges Dokument
# describes the area as the same wine region). Multi-Bundesland IGPs
# (Mitteldeutscher Landwein, Schleswig-Holsteinischer Landwein, etc.)
# are deliberately left out: their territory does not coincide with one
# Anbaugebiet, and a future commune-list parser will resolve them.
DE_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    # ── Anbaugebiet-aligned Landwein PGIs ─────────────────────────────
    "PGI-DE-A1278": ("PDO-DE-A0867",),   # Ahrtaler Landwein → Ahr
    "PGI-DE-A1279": ("PDO-DE-A1264",),   # Badischer Landwein → Baden
    "PGI-DE-A1285": ("PDO-DE-A1264",),   # Landwein Oberrhein → Baden (Oberrhein-Anteil)
    "PGI-DE-A1283": ("PDO-DE-A1270",),   # Landwein der Mosel → Mosel
    "PGI-DE-A1288": ("PDO-DE-A1270",),   # Landwein der Ruwer → Mosel (Ruwer-Teilgebiet)
    "PGI-DE-A1289": ("PDO-DE-A1270",),   # Landwein der Saar → Mosel (Saar-Teilgebiet)
    "PGI-DE-A1293": ("PDO-DE-A1271",),   # Nahegauer Landwein → Nahe
    "PGI-DE-A1294": ("PDO-DE-A1272",),   # Pfälzer Landwein → Pfalz
    "PGI-DE-A1299": ("PDO-DE-A1273",),   # Rheingauer Landwein → Rheingau
    "PGI-DE-A1303": ("PDO-DE-A1277",),   # Sächsischer Landwein → Sachsen
    "PGI-DE-A1305": ("PDO-DE-A1276",),   # Schwäbischer Landwein → Württemberg
    "PGI-DE-A1284": ("PDO-DE-A1276",),   # Landwein Neckar → Württemberg (Neckar-Teilgebiet)
    "PGI-DE-A1307": ("PDO-DE-A1276",),   # Taubertäler Landwein → Württemberg (Tauberfranken-Teilgebiet)
    "PGI-DE-A1306": ("PDO-DE-A1268",),   # Starkenburger Landwein → Hessische Bergstraße
    # ── Multi-Anbaugebiet Landwein PGIs (river-basin unions) ──────────
    # Landwein Rhein covers the Rhine-side German Anbaugebiete (Mosel,
    # Mittelrhein, Nahe, Pfalz, Rheingau, Rheinhessen, Ahr). Public
    # source: BMEL Weinverordnung Anlage 2.
    "PGI-DE-A1286": (
        "PDO-DE-A1270",  # Mosel
        "PDO-DE-A1269",  # Mittelrhein
        "PDO-DE-A1271",  # Nahe
        "PDO-DE-A1272",  # Pfalz
        "PDO-DE-A1273",  # Rheingau
        "PDO-DE-A1274",  # Rheinhessen
        "PDO-DE-A0867",  # Ahr
    ),
    "PGI-DE-A1298": (   # Rheinburgen-Landwein — Mittelrhein + Ahr + parts of Mosel
        "PDO-DE-A1269",  # Mittelrhein
        "PDO-DE-A0867",  # Ahr
    ),
    "PGI-DE-A1301": (   # Rheinischer Landwein — Rheinhessen + Nahe + Pfalz + Mittelrhein
        "PDO-DE-A1274",  # Rheinhessen
        "PDO-DE-A1271",  # Nahe
        "PDO-DE-A1272",  # Pfalz
        "PDO-DE-A1269",  # Mittelrhein
    ),
    "PGI-DE-A1287": (   # Landwein Rhein-Neckar — Rheinhessen + Pfalz + Württemberg + Baden
        "PDO-DE-A1274",  # Rheinhessen
        "PDO-DE-A1272",  # Pfalz
        "PDO-DE-A1276",  # Württemberg
        "PDO-DE-A1264",  # Baden
    ),
    "PGI-DE-A1282": (   # Landwein Main — Franken + Baden (Tauberfranken) + Württemberg
        "PDO-DE-A1267",  # Franken
        "PDO-DE-A1264",  # Baden
        "PDO-DE-A1276",  # Württemberg
    ),
    "PGI-DE-A1280": (   # Bayerischer Bodensee-Landwein — Baden (Bodensee corner)
        "PDO-DE-A1264",  # Baden
    ),
    "PGI-DE-A1296": (   # Regensburger Landwein — Franken / Bayern
        "PDO-DE-A1267",  # Franken
    ),
    # Sächsischer Landwein already covered above; Mitteldeutscher
    # Landwein spans Sachsen-Anhalt + Thüringen + parts of Brandenburg —
    # not coextensive with the Saale-Unstrut + Sachsen PDOs but
    # overlaps; we approximate as their union here.
    "PGI-DE-A1291": (   # Mitteldeutscher Landwein
        "PDO-DE-A1275",  # Saale-Unstrut
        "PDO-DE-A1277",  # Sachsen
    ),
}


# Einzellage PDO → parent Anbaugebiet PDO file_number. Used for the
# `parent-appellation` step; the Einzellage's commune-precise polygon
# isn't in Bétard, so we honestly fall back to the parent Anbaugebiet.
DE_EINZELLAGE_PARENT_PDO: dict[str, str] = {
    "PDO-DE-N1822": "PDO-DE-A1267",   # Bürgstadter Berg → Franken
    "PDO-DE-02403": "PDO-DE-A1267",   # Würzburger Stein-Berg → Franken
    "PDO-DE-02363": "PDO-DE-A1271",   # Monzinger Niederberg → Nahe
    "PDO-DE-02081": "PDO-DE-A1270",   # Uhlen Blaufüsser Lay → Mosel
    "PDO-DE-02082": "PDO-DE-A1270",   # Uhlen Laubach → Mosel
    "PDO-DE-02083": "PDO-DE-A1270",   # Uhlen Roth Lay → Mosel
}


class DEPolygonIndex:
    """In-memory polygon index for DE records, backed by Bétard 2022."""

    def __init__(
        self,
        figshare_gpkg: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].str.startswith(("PDO-DE", "PGI-DE"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        """Union the member-PDO polygons for one of the DE PGIs.
        Returns (geometry, stats)."""
        members = DE_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def einzellage_parent(self, file_number: str) -> tuple[BaseGeometry | None, str]:
        """Resolve an Einzellage PDO via its parent Anbaugebiet polygon.
        Returns (geometry, parent_file_number) or (None, '')."""
        parent_fn = DE_EINZELLAGE_PARENT_PDO.get(file_number or "")
        if not parent_fn:
            return None, ""
        return self._pdo_polygons.get(parent_fn), parent_fn

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one DE record by file_number.
        Returns (geometry, geom_source, stats). `matched == -1` is the
        project convention for a polygon resolved whole rather than
        commune-counted."""
        fn = file_number or ""
        # 1. Einzellage sub-denominations inherit parent Anbaugebiet.
        if fn in DE_EINZELLAGE_PARENT_PDO:
            geom, parent_fn = self.einzellage_parent(fn)
            if geom is not None:
                return geom, "parent-appellation", {
                    "matched": -1, "unmatched": 0, "parent_fn": parent_fn,
                }
            # Even if parent missing, fall through — but this shouldn't happen
            return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}
        # 2. PGI region-union.
        if fn in DE_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        # 3. Direct Figshare PDO match.
        geom = self._pdo_polygons.get(fn)
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        # 4. Stub.
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
