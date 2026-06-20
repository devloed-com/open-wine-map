"""Official regional-geoportal wine-zone geometry for Italian wine GIs.

`ITZoneIndex` loads the regional production-zone layers harvested by
stage 00 (see `zone_sources.py`) — each an official, consortium-
validated GIS layer of DOC/DOCG/IGT boundaries — and resolves a wine's
geometry by matching its name against the layer's appellation field.

This is the preferred geometry source for Italy: a real delimited zone
polygon, used by stage 04 in front of the Bétard 2022 fallback. An
appellation that spans regions (and appears in more than one regional
layer) is resolved as the union of its per-region pieces.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from _lib.it.zone_sources import active_sources

# Italian connector words dropped before matching — regional layers
# spell appellations inconsistently ("Amarone della Valpolicella" vs the
# Veneto layer's "AMARONE VALPOLICELLA"; "Recioto di Soave" vs "RECIOTO
# SOAVE"). Dropping them on both sides bridges the gap; the distinguishing
# words remain, so genuinely different appellations stay distinct.
_CONNECTORS = frozenset({
    "della", "dello", "delle", "degli", "dei", "del", "di", "da",
    "d", "in", "e", "ed", "la", "il", "lo", "l",
})


def _norm(s: str) -> str:
    """Diacritics + punctuation stripped, connector words dropped,
    lowercased — applied identically to the eAmbrosia name and the
    geoportal appellation field."""
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return "".join(w for w in s.split() if w not in _CONNECTORS)


# A leading Italian quality-tier abbreviation in the Umbria `ZONE` field —
# "D.O.C.", "D.O.C.G.", "I.G.T.", or a combined "D.O.C. e D.O.C.G." — with
# the dataset's irregular dot/space placement ("D.O.C .", "D.O.C.G.Torgiano",
# undotted "DOC Rosso Orvietano"). Anchored at the start and repeated to eat
# the combined form; every Umbria appellation name begins with a non-D/I
# letter, so this never bites into a real name.
_DOTTED_TIER_RE = re.compile(
    r"^\s*(?:[DI][.\s]*[OG][.\s]*[CT][.\s]*(?:G[.\s]*)?(?:e[.\s]+)?)+",
    re.IGNORECASE,
)
# Italian "o" (alternate-name separator) as a standalone word, e.g.
# "Rosso Orvietano o Orvietano Rosso".
_ALT_NAME_RE = re.compile(r"\s+o\s+", re.IGNORECASE)


def _strip_tier(raw: str, spec: dict) -> str:
    if spec.get("tier_prefix") == "dotted":
        return _DOTTED_TIER_RE.sub("", raw).strip()
    return raw


def _name_variants(base: str, spec: dict) -> list[str]:
    """Expand one stripped `ZONE` name into every appellation name it should
    index under: the alternate-name halves of an "X o Y" string, plus any
    curated `extra_names` (a combined DOC+DOCG dataset covers the DOCG too)."""
    parts = _ALT_NAME_RE.split(base) if spec.get("alt_name_split") else [base]
    extra = spec.get("extra_names") or {}
    out = list(parts)
    for p in parts:
        out.extend(extra.get(_norm(p), []))
    return out


class ITZoneIndex:
    def __init__(self, zones_dir: Path, target_crs: str = "EPSG:4326") -> None:
        self._by_name: dict[str, list[tuple[BaseGeometry, str]]] = {}
        self._n_zones = 0
        self._regions: list[str] = []

        for region, spec in active_sources().items():
            if spec.get("fetch_type") == "ckan_shapefiles":
                if self._load_ckan(region, spec, zones_dir, target_crs):
                    self._regions.append(region)
                continue
            if self._load_layers(region, spec, zones_dir, target_crs):
                self._regions.append(region)

    def _add(self, name: str, geom: BaseGeometry, region: str) -> None:
        if not name or geom is None or geom.is_empty:
            return
        self._by_name.setdefault(name, []).append((geom, region))
        self._n_zones += 1

    def _load_layers(
        self, region: str, spec: dict, zones_dir: Path, target_crs: str
    ) -> bool:
        """Default WFS/ArcGIS/zip layers with a per-feature `name_field`."""
        name_field = spec["name_field"]
        strip_prefix = spec.get("strip_kind_prefix", False)
        region_used = False
        for layer in spec["layers"]:
            path = zones_dir / layer["filename"]
            if not path.exists():
                continue
            read_kwargs = {"layer": layer["layer"]} if layer.get("layer") else {}
            try:
                gdf = gpd.read_file(path, **read_kwargs)
            except Exception:  # noqa: BLE001
                continue
            if gdf.crs is None or name_field not in gdf.columns:
                continue
            if gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            region_used = True
            for _, row in gdf.iterrows():
                raw = str(row.get(name_field) or "")
                if strip_prefix:
                    raw = re.sub(r"^\s*(DOCG|DOC|IGT)\s+", "", raw, flags=re.I)
                self._add(_norm(raw), row.geometry, region)
        return region_used

    def _load_ckan(
        self, region: str, spec: dict, zones_dir: Path, target_crs: str
    ) -> bool:
        """CKAN per-appellation shapefiles (Umbria): glob the extracted `.shp`,
        assign the declared CRS (the files carry no `.prj`), strip the dotted
        tier prefix off `ZONE`, and index every name variant."""
        name_field = spec["name_field"]
        src_crs = spec.get("crs")
        base_dir = zones_dir / spec.get("extract_dir", region)
        if not base_dir.exists():
            return False
        region_used = False
        for shp in sorted(base_dir.glob("**/*.shp")):
            try:
                gdf = gpd.read_file(shp)
            except Exception:  # noqa: BLE001
                continue
            if name_field not in gdf.columns:
                continue
            if gdf.crs is None and src_crs:
                gdf = gdf.set_crs(src_crs)
            if gdf.crs is None:
                continue
            if gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            region_used = True
            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                base = _strip_tier(str(row.get(name_field) or ""), spec)
                for variant in _name_variants(base, spec):
                    self._add(_norm(variant), geom, region)
        return region_used

    @property
    def n_zones(self) -> int:
        return self._n_zones

    @property
    def regions(self) -> list[str]:
        return list(self._regions)

    def resolve(self, name: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve a wine's geometry from the official regional layers.
        Returns (geometry, geom_source, stats); geom_source names the
        region(s) the polygon came from."""
        hits = self._by_name.get(_norm(name)) or []
        if not hits:
            return None, "none", {"matched": 0, "unmatched": 0}
        geoms = [g for g, _ in hits]
        regions = sorted({r for _, r in hits})
        geom = geoms[0] if len(geoms) == 1 else unary_union(geoms)
        source = f"geoportal-zone:{'+'.join(regions)}"
        return geom, source, {"matched": len(geoms), "unmatched": 0}
