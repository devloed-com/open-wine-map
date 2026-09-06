"""GB-side geometry resolution — ONS administrative boundaries.

The UK left the EU before Bétard 2022's snapshot logic applies to it, and
the dataset the other countries lean on (`raw/es/figshare/EU_PDO.gpkg`) is
an **EU** PDO layer — it carries no `PDO-GB-*` rows. GB therefore resolves
entirely against ONS Open Geography boundaries (Open Government Licence
v3.0), which is a better fit anyway: every UK wine GI is demarcated to
whole administrative units named in its product specification.

  - `raw/gb/ons/countries.geojson` — Countries (December 2025) UK BGC.
    England and Wales, the `DEMARCATION` of four of the six GIs.
  - `raw/gb/ons/counties.geojson` — Counties and Unitary Authorities
    (December 2025) UK BGC. Sussex's specification demarcates "the
    administrative boundaries of the counties of East and West Sussex";
    Brighton and Hove is a unitary authority carved out of East Sussex in
    1997 and sits between the two, so the union of the three CTYUAs
    reconstructs the ceremonial Sussex the specification's own map shows.

Stage 04 resolves each GB record by:

  1. **ons-country** — England / Wales whole-country polygon, for the
     English + Welsh PDOs and their Regional PGI counterparts.
  2. **ons-county-union** — Sussex: East Sussex ∪ West Sussex ∪ Brighton
     and Hove.
  3. **pdo-plan-parcel-hull-approx** — Darnibole, reconstructed from the
     parcel references on its specification's plan. Approximate by
     construction; see `_lib/gb/darnibole.py` for the derivation and the
     three-way anchor check. Carries `approximate=True` so the panel can
     disclose it.
  4. **stub-no-geometry** — last resort; not hit in v1, all 6 resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from _lib.gb.darnibole import GEOM_SOURCE as DARNIBOLE_GEOM_SOURCE
from _lib.gb.darnibole import boundary_bng as darnibole_boundary_bng

ROOT = Path(__file__).resolve().parents[3]
COUNTRIES_GEOJSON = ROOT / "raw" / "gb" / "ons" / "countries.geojson"
COUNTIES_GEOJSON = ROOT / "raw" / "gb" / "ons" / "counties.geojson"

# file_number → the ONS country whose polygon is the GI's territory.
GB_COUNTRY_TERRITORY: dict[str, str] = {
    "PDO-GB-A1585": "England",  # English PDO
    "PGI-GB-A1589": "England",  # English Regional PGI
    "PDO-GB-A1587": "Wales",    # Welsh PDO
    "PGI-GB-A1590": "Wales",    # Welsh Regional PGI
}

# file_number → the ONS counties/unitary authorities whose union is the
# GI's territory.
GB_COUNTY_TERRITORY: dict[str, tuple[str, ...]] = {
    "PDO-GB-02365": ("East Sussex", "West Sussex", "Brighton and Hove"),
}

# file_number → GIs whose boundary is reconstructed rather than published.
GB_APPROXIMATE: tuple[str, ...] = ("PDO-GB-N1636",)  # Darnibole


def _load_by_name(path: Path, name_field: str) -> dict[str, BaseGeometry]:
    if not path.exists():
        return {}
    fc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, BaseGeometry] = {}
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        name = props.get(name_field)
        geom = feat.get("geometry")
        if not name or not geom:
            continue
        g = shape(geom)
        if g is not None and not g.is_empty:
            out[str(name)] = g
    return out


class GBPolygonIndex:
    """In-memory polygon index for GB records, backed by ONS boundaries."""

    def __init__(
        self,
        countries_geojson: Path | None = None,
        counties_geojson: Path | None = None,
    ) -> None:
        cpath = countries_geojson or COUNTRIES_GEOJSON
        ypath = counties_geojson or COUNTIES_GEOJSON
        # ONS publishes these layers with a year-suffixed name field
        # (CTRY25NM / CTYUA25NM); accept whichever suffix is cached so a
        # boundary refresh to a later vintage doesn't need a code change.
        self._countries = self._load_any(cpath, "CTRY", "NM")
        self._counties = self._load_any(ypath, "CTYUA", "NM")
        self._darnibole_4326: BaseGeometry | None = None

    @staticmethod
    def _load_any(path: Path, prefix: str, suffix: str) -> dict[str, BaseGeometry]:
        if not path.exists():
            return {}
        fc = json.loads(path.read_text(encoding="utf-8"))
        feats = fc.get("features") or []
        field = ""
        for feat in feats:
            for key in (feat.get("properties") or {}):
                if key.startswith(prefix) and key.endswith(suffix) and not key.endswith("NMW"):
                    field = key
                    break
            if field:
                break
        return _load_by_name(path, field) if field else {}

    @property
    def n_countries(self) -> int:
        return len(self._countries)

    @property
    def n_counties(self) -> int:
        return len(self._counties)

    def darnibole_polygon(self) -> BaseGeometry | None:
        """Approximate Darnibole boundary, reprojected BNG → WGS84."""
        if self._darnibole_4326 is None:
            try:
                from pyproj import Transformer
            except ImportError:  # pragma: no cover - pyproj is a hard dep of stage 04
                return None
            tr = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
            self._darnibole_4326 = transform(
                lambda x, y, z=None: tr.transform(x, y), darnibole_boundary_bng()
            )
        return self._darnibole_4326

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one GB record by file_number.
        Returns (geometry, geom_source, stats)."""
        fn = (file_number or "").strip()

        country = GB_COUNTRY_TERRITORY.get(fn)
        if country:
            geom = self._countries.get(country)
            if geom is not None and not geom.is_empty:
                return geom, "ons-country", {"matched": -1, "unmatched": 0, "unit": country}
            return None, "stub-no-geometry", {"matched": 0, "unmatched": 1, "unit": country}

        counties = GB_COUNTY_TERRITORY.get(fn)
        if counties:
            polys = [
                self._counties[name] for name in counties
                if name in self._counties and not self._counties[name].is_empty
            ]
            stats = {
                "matched": -1 if polys else 0,
                "unmatched": len(counties) - len(polys),
                "members": len(counties),
                "resolved": len(polys),
            }
            if polys:
                return unary_union(polys), "ons-county-union", stats
            return None, "stub-no-geometry", stats

        if fn in GB_APPROXIMATE:
            geom = self.darnibole_polygon()
            if geom is not None and not geom.is_empty:
                return geom, DARNIBOLE_GEOM_SOURCE, {
                    "matched": -1, "unmatched": 0, "approximate": True,
                }
            return None, "stub-no-geometry", {"matched": 0, "unmatched": 1}

        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}


def is_approximate(file_number: str) -> bool:
    """True when the GI's boundary is a reconstruction, not a published one."""
    return (file_number or "").strip() in GB_APPROXIMATE
