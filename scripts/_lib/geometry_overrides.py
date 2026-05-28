"""Geometry-outlier overrides — apply curator-reviewed clips to resolved
appellation polygons, transparently.

`scripts/audit_geometry_outliers.py` flags detached polygon parts; a curator
records the parts confirmed to be spurious (an upstream-data error) in
`geometry_outlier_overrides.json`. Stage 04 calls `clip()` on every resolved
geometry. The contract is deliberately strict so a clip can never silently
hide the wrong thing:

  * a `drop` spec must match EXACTLY ONE part, by 3035-centroid proximity AND
    area. One match → the part is removed and recorded in `ClipResult.dropped`.
  * zero matches OR several matches → nothing is removed; the spec is recorded
    in `ClipResult.stale`. A stale spec means the upstream geometry drifted (or
    was fixed) and the override must be re-verified — the caller logs it loudly.
  * a clip that would remove every part is refused (recorded as stale).

The helper itself is pure: it returns the verdict, it does not log. Stage 04
logs every dropped/stale spec; the audit re-derives the same verdict against
the source data on every run. Nothing is hidden.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pyproj import Transformer
from shapely.geometry import MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

DEFAULT_OVERRIDES_PATH = Path(__file__).with_name("geometry_outlier_overrides.json")

_EQ_AREA = "EPSG:3035"
_WGS84 = "EPSG:4326"
_to_3035: Callable = Transformer.from_crs(_WGS84, _EQ_AREA, always_xy=True).transform
_to_4326: Callable = Transformer.from_crs(_EQ_AREA, _WGS84, always_xy=True).transform


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parts(geom: BaseGeometry) -> list[BaseGeometry]:
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return [geom]


def part_signature(part_3035: BaseGeometry) -> tuple[float, float, float]:
    """(centroid_lat, centroid_lon, area_km2) for a polygon already in
    EPSG:3035 — the same basis the override file's signatures are recorded
    in, so a curator can read a flagged outlier straight into a `drop` spec."""
    c = part_3035.centroid
    lon, lat = _to_4326(c.x, c.y)
    return lat, lon, part_3035.area / 1e6


@dataclass
class ClipResult:
    """Outcome of clipping one appellation. `geom` is the result (clipped, or
    the original when nothing matched). `dropped` / `stale` are the per-spec
    ledger the caller must surface."""

    slug: str
    geom: BaseGeometry | None
    dropped: list[dict] = field(default_factory=list)
    stale: list[dict] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.dropped)

    def log_lines(self) -> list[str]:
        lines: list[str] = []
        for d in self.dropped:
            lat, lon = d["centroid_latlon"]
            lines.append(
                f"  clipped {self.slug}: dropped part @({lat:.4f},{lon:.4f}) "
                f"~{d['area_km2']:.1f} km2 — {d['reason']}"
            )
        for s in self.stale:
            lat, lon = s.get("centroid_latlon", (0.0, 0.0))
            n = s.get("n_matches", 0)
            why = (
                "matched no current part"
                if n == 0
                else f"matched {n} parts (ambiguous)"
            )
            lines.append(
                f"  WARNING stale override for {self.slug}: drop spec "
                f"@({lat:.4f},{lon:.4f}) ~{s.get('area_km2', 0):.1f} km2 {why} "
                f"— re-verify against current source data ({s.get('reason', '')})"
            )
        return lines


class GeometryOverrides:
    """Loaded `geometry_outlier_overrides.json`. Re-usable across a stage-04 run."""

    def __init__(self, path: Path = DEFAULT_OVERRIDES_PATH) -> None:
        self.path = Path(path)
        data: dict = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        self._clip: dict[str, dict] = data.get("clip", {}) or {}
        self._whitelist: dict[str, str] = data.get("whitelist", {}) or {}
        self.match_tol_km: float = float(data.get("_match_tol_km", 1.5))
        self.area_tol_pct: float = float(data.get("_area_tol_pct", 20.0))

    @property
    def whitelist(self) -> dict[str, str]:
        return dict(self._whitelist)

    @property
    def clip_specs(self) -> dict[str, dict]:
        return dict(self._clip)

    def is_whitelisted(self, slug: str) -> bool:
        return slug in self._whitelist

    def clip(
        self,
        slug: str,
        geom: BaseGeometry | None,
        geom_source: str | None = None,
    ) -> ClipResult:
        """Return a ClipResult for `slug`. When `slug` has no clip spec, or
        `geom` is empty, the geometry is returned unchanged with empty
        ledgers.

        `geom_source` is the resolved geometry's provenance tag (e.g.
        `figshare-pdo`, `geoportal-zone:piemonte`). When the clip spec
        carries a `geom_source` field, the clip applies only to that
        source; if a higher-priority resolver (a regional geoportal,
        say) replaced the Bétard polygon, the spec is silently inactive
        — it remains a valid record of the Bétard error but doesn't
        warn on every build."""
        spec = self._clip.get(slug)
        if spec is None or geom is None or geom.is_empty:
            return ClipResult(slug=slug, geom=geom)
        target_source = spec.get("geom_source")
        if target_source and geom_source and target_source != geom_source:
            return ClipResult(slug=slug, geom=geom)

        drops = spec.get("drop", []) or []
        g3035 = shp_transform(_to_3035, geom)
        parts = _parts(g3035)
        sigs = [part_signature(p) for p in parts]
        keep = [True] * len(parts)
        dropped: list[dict] = []
        stale: list[dict] = []

        for d in drops:
            tol_km = float(d.get("match_tol_km", self.match_tol_km))
            tol_pct = float(d.get("area_tol_pct", self.area_tol_pct))
            clat, clon = d["centroid_latlon"]
            target_area = float(d["area_km2"])
            matches: list[int] = []
            for i, (plat, plon, parea) in enumerate(sigs):
                if not keep[i]:
                    continue
                if _haversine_km(clat, clon, plat, plon) > tol_km:
                    continue
                if target_area <= 0:
                    continue
                if abs(parea - target_area) / target_area > tol_pct / 100.0:
                    continue
                matches.append(i)
            entry = {
                "centroid_latlon": [clat, clon],
                "area_km2": target_area,
                "reason": d.get("reason", ""),
            }
            if len(matches) == 1:
                keep[matches[0]] = False
                entry["matched_area_km2"] = round(sigs[matches[0]][2], 3)
                dropped.append(entry)
            else:
                entry["n_matches"] = len(matches)
                stale.append(entry)

        if not dropped:
            return ClipResult(slug=slug, geom=geom, stale=stale)

        kept = [parts[i] for i in range(len(parts)) if keep[i]]
        if not kept:
            # Refuse to empty a geometry — surface as stale, keep original.
            stale.append({"reason": "clip would remove every part — refused"})
            return ClipResult(slug=slug, geom=geom, stale=stale)

        new_3035 = kept[0] if len(kept) == 1 else MultiPolygon(kept)
        new_4326 = shp_transform(_to_4326, new_3035)
        return ClipResult(slug=slug, geom=new_4326, dropped=dropped, stale=stale)
