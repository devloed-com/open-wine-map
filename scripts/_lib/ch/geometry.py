"""Swiss-record geometry resolution (stage 04).

Chain (per CH record, in priority order):

1. **`geoportal-canton:<canton>`** — official cantonal-geoportal
   AOC-perimeter polygon, matched by AOC slug. Active on day-1 for
   GE (SITG `VIT_VIGNOBLE_AO` — parcel-precise). VD pending one-time
   ASIT VD WFS endpoint dereferencing. Other cantons: deferred.

2. **`parent-aoc`** — sub-denominations inherit the parent AOC's
   polygon when no geoportal layer covers them. Mirrors the FR DGC
   / DE Einzellage pattern.

3. **`swissboundaries-commune-union`** — parse the règlement's
   "aire de production" / "Produktionsgebiet" body into a commune
   list; union the matching swissBOUNDARIES3D `tlm_hoheitsgebiet`
   Gemeinde polygons via `CHCommuneIndex.union_from_bfs_ids`.
   BFS_NUMMER is the canonical commune join key. Bilingual-canton
   name aliases (FR/DE for BE/VS/FR/GR) are bridged via
   `_GEMEINDE_ALIAS`.

4. **`swissboundaries-canton-union`** — for whole-canton AOCs (the
   bulk of the smaller German-CH cantons + canton-level umbrellas
   like Ticino, Neuchâtel, Schaffhausen, Valais): union every
   swissBOUNDARIES3D Gemeinde whose `KANTONSNUMMER == BFS canton id`.

5. **`stub-no-geometry`** — last resort. Should not be hit in v1.

The swissBOUNDARIES3D GeoPackage is downloaded by stage 00 to
`raw/ch/swisstopo/swissboundaries3d_<YEAR>-01_2056_5728.gpkg`.
Layer names: `tlm_hoheitsgebiet` (Gemeinde polygons) +
`tlm_kantonsgebiet` (canton polygons). Native CRS EPSG:2056
(LV95); stage 04 reprojects to EPSG:4326 / EPSG:3035 as needed.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _lib.ch.canton import CANTON_BFS_ID, CANTON_CODE_BY_BFS  # noqa: E402

# Curated commune-name aliases for bilingual-canton spelling drift
# (Bern/Berne, La Chaux-de-Fonds, etc.). Keys are normalised; values
# are canonical (normalised) BFS-side names.
_GEMEINDE_ALIAS: dict[str, str] = {
    # Bilingual BE — French side spellings → official German side.
    "biennelacdebienne": "biel",
    "bienne": "biel",
    "laneuveville": "laneuveville",
}


def _norm(s: str) -> str:
    """Aggressive normalisation for commune name joins: lowercase,
    diacritics stripped, ß→ss, non-alphanumeric removed."""
    s = (s or "").lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)


class CHCommuneIndex:
    """Index of swissBOUNDARIES3D Gemeinde polygons keyed by BFS_NUMMER
    and (normalised) NAME. Provides:

      - `lookup(name)` → list of `{bfs_id, name, canton}` candidates
      - `scan_text(text)` → iter of commune hits found in a free-text
        block (greedy multi-word matching, max 5 tokens)
      - `polygon_for_bfs_id(bfs)` → shapely geometry in target_crs
      - `union_from_bfs_ids(bfs_ids)` → unary_union of the matching
        polygons
      - `union_for_canton(canton_code)` → union of every Gemeinde of
        the given canton (the canton-level fallback)
    """

    def __init__(self, gpkg_path: Path, target_crs: str = "EPSG:4326") -> None:
        if not gpkg_path.exists():
            raise FileNotFoundError(
                f"swissBOUNDARIES3D GPKG not found at {gpkg_path}. "
                "Run scripts/ch/00_fetch_data.py first."
            )
        gdf = gpd.read_file(gpkg_path, layer="tlm_hoheitsgebiet")
        # Filter to actual Gemeindegebiet polygons — drops the 11
        # Liechtenstein Kantonsgebiet entries and 2 Kommunanz.
        gdf = gdf[gdf["objektart"] == "Gemeindegebiet"]
        if gdf.crs is None or gdf.crs.to_string() != target_crs:
            gdf = gdf.to_crs(target_crs)
        # swissBOUNDARIES3D ships Polygon Z (height-as-third-coordinate);
        # flatten to 2D so the stage-04 GeoJSON output is tippecanoe-clean.
        from shapely import force_2d  # noqa: PLC0415
        gdf["geometry"] = gdf.geometry.apply(force_2d)

        self._by_bfs: dict[int, dict] = {}
        self._bfs_by_name: dict[str, list[int]] = defaultdict(list)
        self._bfs_by_canton: dict[str, list[int]] = defaultdict(list)
        # Geometry index by BFS id.
        for _, row in gdf.iterrows():
            bfs = row.get("bfs_nummer")
            name = row.get("name", "")
            kt_bfs = row.get("kantonsnummer")
            geom = row.geometry
            if bfs is None or geom is None or geom.is_empty:
                continue
            try:
                bfs_int = int(bfs)
                kt_int = int(kt_bfs) if kt_bfs is not None else 0
            except (TypeError, ValueError):
                continue
            canton_code = CANTON_CODE_BY_BFS.get(kt_int, "")
            entry = {
                "bfs_id": bfs_int,
                "name": name,
                "canton": canton_code,
                "geom": geom,
            }
            self._by_bfs[bfs_int] = entry
            self._bfs_by_name[_norm(name)].append(bfs_int)
            if canton_code:
                self._bfs_by_canton[canton_code].append(bfs_int)
        # Apply commune aliases.
        for src_norm, target_norm in _GEMEINDE_ALIAS.items():
            if target_norm in self._bfs_by_name:
                self._bfs_by_name[src_norm].extend(self._bfs_by_name[target_norm])

    # ── lookup helpers ──────────────────────────────────────────────

    @property
    def n_communes(self) -> int:
        return len(self._by_bfs)

    @property
    def n_cantons(self) -> int:
        return len(self._bfs_by_canton)

    def lookup(self, name: str) -> list[dict]:
        """Return all (BFS-id, canton) candidates for the given commune
        name. Empty list if no match."""
        bfs_ids = self._bfs_by_name.get(_norm(name), [])
        return [
            {"bfs_id": b, "name": self._by_bfs[b]["name"],
             "canton": self._by_bfs[b]["canton"]}
            for b in bfs_ids
        ]

    def scan_text(self, text: str, *, max_tokens: int = 5) -> Iterable[dict]:
        """Greedy multi-token scan: walk word boundaries and try the
        longest candidate (up to `max_tokens` words) against the
        commune-name index. Each hit is reported once at its first
        occurrence; the scan resumes past the match."""
        words = re.findall(r"[A-Za-zÀ-ÿ\-]+", text)
        i = 0
        while i < len(words):
            matched = False
            for span in range(min(max_tokens, len(words) - i), 0, -1):
                cand = " ".join(words[i:i + span])
                bfs_ids = self._bfs_by_name.get(_norm(cand), [])
                if bfs_ids:
                    for b in bfs_ids:
                        e = self._by_bfs[b]
                        yield {"bfs_id": b, "name": e["name"],
                               "canton": e["canton"]}
                    i += span
                    matched = True
                    break
            if not matched:
                i += 1

    def polygon_for_bfs_id(self, bfs_id: int) -> BaseGeometry | None:
        entry = self._by_bfs.get(bfs_id)
        return entry["geom"] if entry else None

    def union_from_bfs_ids(self, bfs_ids: Iterable[int]) -> BaseGeometry | None:
        geoms = [self._by_bfs[b]["geom"] for b in bfs_ids if b in self._by_bfs]
        if not geoms:
            return None
        return unary_union(geoms)

    def union_for_canton(self, canton_code: str) -> BaseGeometry | None:
        bfs_ids = self._bfs_by_canton.get(canton_code, [])
        return self.union_from_bfs_ids(bfs_ids)


# ── GE SITG geoportal layer ─────────────────────────────────────────

def _sitg_slug(name: str) -> str:
    """Slug-normalise an APPELATION field from the SITG layer for
    matching against OFAG slugs."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


class GESitgIndex:
    """Index of GE SITG VIT_VIGNOBLE_AO parcels by AOC-name slug.

    The SITG layer carries 110 parcels covering 30 distinct
    APPELATION values, classified by `AOR_AOC` ('1 cru' = premier
    cru = OFAG locale; 'AOR' = appellation d'origine régionale,
    not in OFAG). v1 indexes both tiers; downstream picks 1-cru
    polygons for OFAG locale records.
    """

    def __init__(self, geojson_path: Path, target_crs: str = "EPSG:4326") -> None:
        self._by_slug: dict[str, BaseGeometry] = {}
        if not geojson_path.exists():
            return
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
        if not data.get("features"):
            return
        gdf = gpd.read_file(geojson_path)
        if gdf.crs is None or gdf.crs.to_string() != target_crs:
            gdf = gdf.to_crs(target_crs)
        slug_geoms: dict[str, list[BaseGeometry]] = defaultdict(list)
        for _, row in gdf.iterrows():
            name = row.get("APPELATION") or ""
            tier = (row.get("AOR_AOC") or "").lower()
            if not name or tier == "aor":
                # AOR-tier polygons aren't in OFAG; skip.
                continue
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            slug_geoms[_sitg_slug(name)].append(geom)
        for slug, geoms in slug_geoms.items():
            self._by_slug[slug] = unary_union(geoms)

    def polygon_for_slug(self, slug: str) -> BaseGeometry | None:
        return self._by_slug.get(slug)

    @property
    def n_aocs(self) -> int:
        return len(self._by_slug)


# ── top-level resolver ─────────────────────────────────────────────


def resolve(
    record: dict,
    *,
    commune_index: CHCommuneIndex,
    ge_sitg: GESitgIndex | None,
    parent_geom_by_slug: dict[str, BaseGeometry],
) -> tuple[BaseGeometry | None, str, dict]:
    """Resolve geometry for one CH record. Returns (geom, geom_source, stats).

    `record` carries `slug`, `canton`, `is_sub_denomination`,
    `parent_slug`, `tier` (cantonale | régionale | locale), and
    `geo_communes` (list of `{bfs_id, ...}` from stage 02 commune
    extraction)."""
    canton = (record.get("canton") or "").lower()
    slug = record.get("slug") or ""

    # Step 1: cantonal geoportal — GE only in v1.
    if canton == "ge" and ge_sitg is not None:
        g = ge_sitg.polygon_for_slug(slug)
        if g is not None and not g.is_empty:
            return g, "geoportal-canton:ge", {"matched": 1, "unmatched": 0}

    # Step 2: sub-denomination → parent inheritance (when commune
    # list is empty).
    if record.get("is_sub_denomination") and not record.get("geo_communes"):
        parent_slug = record.get("parent_slug") or ""
        parent = parent_geom_by_slug.get(parent_slug)
        if parent is not None and not parent.is_empty:
            return parent, "parent-aoc", {"matched": 1, "unmatched": 0}

    # Step 3: commune-union from règlement-extracted commune list.
    bfs_ids = [c.get("bfs_id") for c in (record.get("geo_communes") or [])
               if c.get("bfs_id")]
    if bfs_ids:
        g = commune_index.union_from_bfs_ids(bfs_ids)
        if g is not None and not g.is_empty:
            return g, "swissboundaries-commune-union", {"matched": len(bfs_ids), "unmatched": 0}

    # Step 4: whole-canton union (fallback for canton-wide AOCs).
    if canton and canton in CANTON_BFS_ID:
        g = commune_index.union_for_canton(canton)
        if g is not None and not g.is_empty:
            return g, "swissboundaries-canton-union", {"matched": -1, "unmatched": 0}

    return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}
