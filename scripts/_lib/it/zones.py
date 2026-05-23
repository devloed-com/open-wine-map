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


class ITZoneIndex:
    def __init__(self, zones_dir: Path, target_crs: str = "EPSG:4326") -> None:
        self._by_name: dict[str, list[tuple[BaseGeometry, str]]] = {}
        self._n_zones = 0
        self._regions: list[str] = []

        for region, spec in active_sources().items():
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
                    geom = row.geometry
                    raw = str(row.get(name_field) or "")
                    if strip_prefix:
                        raw = re.sub(r"^\s*(DOCG|DOC|IGT)\s+", "", raw, flags=re.I)
                    name = _norm(raw)
                    if not name or geom is None or geom.is_empty:
                        continue
                    self._by_name.setdefault(name, []).append((geom, region))
                    self._n_zones += 1
            if region_used:
                self._regions.append(region)

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
