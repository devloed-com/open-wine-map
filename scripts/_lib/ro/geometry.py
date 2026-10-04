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

import sys
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Romania's 41 județe + Bucharest — the NUTS-3 units the county masks use.
N_JUDETE = 42


class ROPolygonIndex:
    """In-memory polygon index for RO records: Bétard PDO match +
    GISCO commune-union fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        nuts3_geojson: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # commune (LAU_NAME, normalised) → list of polygons. Multiple
        # Romanian communes can share a name (e.g. "Cernavodă" town vs.
        # any neighbouring "Cernavodă" rural unit); we keep all candidates
        # and union them all when the commune list mentions the bare name.
        # Keyed on the bare commune name, so a name that repeats across
        # județe lands several polygons. That is resolved at union time
        # against the record's declared județe (`commune_union`), not
        # here — the index keeps every candidate.
        self._lau_by_name: dict[str, list[BaseGeometry]] = {}
        # județ (NUTS-3) polygons, keyed by the `_JUDET_NAMES` form —
        # the disambiguator for a commune name that repeats nationwide.
        self._judet_by_name: dict[str, BaseGeometry] = {}
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

        if nuts3_geojson is not None and nuts3_geojson.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(nuts3_geojson)
            ro = gdf[gdf["CNTR_CODE"] == "RO"]
            if ro.crs is None or ro.crs.to_string() != target_crs:
                ro = ro.to_crs(target_crs)
            # Romania's 41 județe + Bucharest ARE the NUTS-3 units, so the
            # GISCO NUTS-3 layer is the județ boundary set. NUTS_NAME
            # matches `_JUDET_NAMES` after the shared normaliser.
            for _, r in ro.iterrows():
                nm = _normalise_commune((r.get("NUTS_NAME") or "").strip())
                if nm and r.geometry is not None and not r.geometry.is_empty:
                    self._judet_by_name[nm] = r.geometry
        # Without the masks commune_union still runs, unmasked: homonyms are
        # skipped but prose-scraped names 400 km away are unioned again, and
        # nothing else would say so. The file is fetched by the GR stage 00.
        if nuts3_geojson is not None and len(self._judet_by_name) < N_JUDETE:
            why = ("missing" if not nuts3_geojson.exists()
                   else f"has {len(self._judet_by_name)} of {N_JUDETE} RO județe")
            print(
                f"[warn] RO county masks: {nuts3_geojson} {why} — RO commune-list "
                f"unions will be UNMASKED and may span the country "
                f"(fetch it with scripts/gr/00_fetch_data.py)",
                file=sys.stderr,
            )

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    @property
    def n_judete(self) -> int:
        return len(self._judet_by_name)

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def commune_union(
        self, commune_names: Iterable[str], judete: Iterable[str] | None = None,
        scoped: Iterable[tuple[str, list[str]]] | None = None,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons that match the given commune
        names (after normalisation). Returns (geometry, stats) where
        stats counts matched / unmatched / ambiguous commune names.

        Romanian commune names repeat heavily across județe — `Izvoarele`
        is 5 communes, `Fântânele` 7, `Ștefan cel Mare` 6 — so a bare
        name match can pull in a polygon 400 km from the appellation.
        When the spec's declared `judete` disambiguate the candidates
        down to one, that one is used; otherwise the name contributes
        nothing and is reported. Never a blind union of every homonym:
        that drew Colinele Dobrogei, a Black Sea appellation, across the
        full width of the country."""
        from .commune import _SPELLING_ALIASES, _normalise_commune
        record_masks = [
            self._judet_by_name[j]
            for j in (judete or [])
            if j in self._judet_by_name
        ]
        # `scoped` pairs each name with the județe of the section header it
        # sits under; a name whose section is unknown uses the record-wide
        # mask. Griviţa is a commune in both Galaţi and Vaslui and Dealurile
        # Moldovei lists it under each — record-wide, that is an ambiguity;
        # section-scoped, it is two matches.
        items: list[tuple[str, list[BaseGeometry]]]
        if scoped is not None:
            items = []
            for raw_name, own in scoped:
                own_masks = [self._judet_by_name[j] for j in own if j in self._judet_by_name]
                items.append((raw_name, own_masks or record_masks))
        else:
            items = [(n, record_masks) for n in commune_names]
        polys: list[BaseGeometry] = []
        matched: list[str] = []
        unmatched: list[str] = []
        ambiguous: list[str] = []
        outside: list[str] = []
        for raw_name, masks in items:
            key = _normalise_commune(raw_name)
            if not key:
                continue
            key = _SPELLING_ALIASES.get(key, key)
            cands = self._lau_by_name.get(key)
            if not cands:
                unmatched.append(raw_name)
                continue
            if masks:
                # Every candidate is held to the declared județe, not just
                # the ambiguous ones: the commune parser also scrapes
                # place names out of surrounding prose, and those land
                # far outside the area (Colinele Dobrogei, on the Black
                # Sea, was picking up Abrud and Hațeg, ~400 km west).
                inside = [
                    g for g in cands
                    if any(m.intersects(g.representative_point()) for m in masks)
                ]
                if not inside:
                    outside.append(raw_name)
                    continue
                if len(inside) > 1:
                    ambiguous.append(f"{raw_name} ({len(inside)} in-județ)")
                    continue
                cands = inside
            elif len(cands) > 1:
                # No declared județ to disambiguate with, so a name that
                # matches several communes contributes nothing rather
                # than all of them.
                ambiguous.append(f"{raw_name} ({len(cands)})")
                continue
            polys.extend(cands)
            matched.append(raw_name)
        stats = {
            "matched": len(matched),
            "unmatched": len(unmatched),
            "n_ambiguous": len(ambiguous),
            "n_outside_judet": len(outside),
            "names_unmatched": unmatched,
            "names_ambiguous": ambiguous,
            "names_outside_judet": outside,
            "judete": list(judete or []),
            "scoped": scoped is not None,
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def resolve(
        self, file_number: str, commune_names: Iterable[str] | None = None,
        judete: Iterable[str] | None = None,
        scoped: Iterable[tuple[str, list[str]]] | None = None,
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
            geom, stats = self.commune_union(commune_names, judete, scoped)
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
