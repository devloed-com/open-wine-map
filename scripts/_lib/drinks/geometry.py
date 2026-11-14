"""The polygon of a drink GI.

A technical file delimits its area in one sentence more often than not —
"the whole of the national territory", "the Autonomous Province of Trento",
"the island of Mallorca", a handful of municipalities, or the area of the
wine appellation the spirit is distilled from — and the e-form adds the
NUTS units it lies in (section 4b). Three sources, in this order, each
recorded as the record's `geom_source`:

1. **`drinks-area-pin`** — a curator pin of `areas.json`: the units the
   area text names, as NUTS codes, whole countries, GISCO LAU municipalities
   or the polygon of another record (the wine appellation a marc or wine
   spirit shares its delimitation with), each pin quoting the sentence it
   reads (tests/test_drinks_areas.py checks the quote against the extracted
   record). A pin is how a text finer or other than its NUTS rows is drawn:
   Brandy de Jerez is three municipalities where its NUTS field says Cádiz.
2. **`gisco-nuts-union`** — the NUTS units of section 4b, at the finest
   level listed (the rows give a unit and its ancestors: ES612 / ES61 / ES6
   / ES — the leaves are the area). A code the 2024 layer no longer carries
   (the technical files are of 2015–2018: Croatia, Portugal and Sardinia
   were re-cut since) is looked up by its name; one found neither way is
   reported and the record is drawn without it only when nothing else is
   missing more than a fifth of the rows — else it is left to a pin.
3. nothing: the record is not drawn, and `audit_drinks_coverage.py` lists it.

NUTS-3 and NUTS-2 polygons are the GISCO layers already on disk
(raw/gr/nuts, raw/nl/nuts, © EuroGeographics / Eurostat GISCO); NUTS-1 and
whole countries are unions of NUTS-3 units by code prefix, which the code
hierarchy allows. Municipalities are GISCO LAU 2024.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from unidecode import unidecode

from _lib.drinks.region import region_of_nuts

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AREAS_PATH = HERE / "areas.json"
NUTS3_PATH = ROOT / "raw" / "gr" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_3.geojson"
NUTS2_PATH = ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
LAU_ZIP = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"
# ONS Open Geography boundaries of the United Kingdom (GISCO's 2024 layers no
# longer carry it): the four countries and the counties / unitary authorities
# the UK pins name, fetched by scripts/drinks/00_fetch_index.py.
ONS_DIR = ROOT / "raw" / "drinks" / "ons"

# the register's country code → the NUTS country prefix
NUTS_COUNTRY = {"gr": "EL", "gb": "UK"}


def nuts_prefix(country: str) -> str:
    return NUTS_COUNTRY.get(country.lower(), country.upper())


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unidecode(text or "").lower()).strip()


@dataclass
class DrinkGeom:
    geom: object = None
    source: str = "stub-no-geometry"
    # what the card discloses: the units drawn, by kind
    units: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    pin: dict | None = None


def load_areas(path: Path = AREAS_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def nuts_leaves(codes: list[str]) -> list[str]:
    """The finest units a NUTS row list names: the codes that are no
    ancestor of another listed code."""
    codes = sorted({c for c in codes if c})
    return [c for c in codes if not any(o != c and o.startswith(c) for o in codes)]


class DrinksGeometry:
    def __init__(self, nuts3_path: Path = NUTS3_PATH, nuts2_path: Path = NUTS2_PATH,
                 lau_zip: Path = LAU_ZIP, areas: dict | None = None):
        self._nuts3: dict[str, object] = {}
        self._nuts2: dict[str, object] = {}
        self._names: dict[tuple[str, str], list[str]] = {}
        self._label: dict[str, str] = {}
        self._lau_zip = lau_zip
        self._lau: dict[str, dict[str, list]] = {}
        self._lau_ids: dict[str, dict[str, object]] = {}
        self._lau_names: dict[str, str] = {}
        self._ons: dict[str, dict[str, object]] = {}
        self._prefix_cache: dict[str, object] = {}
        self.areas = load_areas() if areas is None else areas
        for path, store in ((nuts3_path, self._nuts3), (nuts2_path, self._nuts2)):
            if not path.exists():
                continue
            for feat in json.loads(path.read_text(encoding="utf-8"))["features"]:
                p = feat["properties"]
                code = p["NUTS_ID"]
                store[code] = shape(feat["geometry"])
                self._label.setdefault(code, p.get("NAME_LATN") or p.get("NUTS_NAME") or code)
                for name in (p.get("NAME_LATN"), p.get("NUTS_NAME")):
                    if name:
                        self._names.setdefault((code[:2], _norm(name)), []).append(code)

    # --- NUTS -----------------------------------------------------------------

    def has_nuts(self, code: str) -> bool:
        return code in self._nuts3 or code in self._nuts2 or (
            len(code) <= 3 and any(c.startswith(code) for c in self._nuts3)
        )

    def nuts_geom(self, code: str):
        """The polygon of a NUTS unit of any level, or None."""
        if code in self._nuts3:
            return self._nuts3[code]
        if code in self._nuts2:
            return self._nuts2[code]
        if len(code) > 3:
            return None
        if code not in self._prefix_cache:
            parts = [g for c, g in self._nuts3.items() if c.startswith(code)]
            self._prefix_cache[code] = unary_union(parts) if parts else None
        return self._prefix_cache[code]

    def nuts3_of(self, geom) -> str:
        """The NUTS-3 unit a municipality lies in ("" when none holds its
        representative point) — what files a drink drawn from municipalities
        under its region."""
        point = geom.representative_point()
        for code, unit in self._nuts3.items():
            if unit.contains(point):
                return code
        return ""

    def nuts_by_name(self, country_prefix: str, name: str, level: int | None = None) -> str | None:
        """The one unit of a country whose name is `name` (at `level` when
        given), or None."""
        hits = sorted(set(self._names.get((country_prefix, _norm(name)), [])))
        if level is not None:
            hits = [h for h in hits if len(h) - 2 == level]
        return hits[0] if len(hits) == 1 else None

    def resolve_nuts_rows(self, rows: list[dict]) -> tuple[list[str], list[str]]:
        """(codes drawn, rows not found) for the NUTS rows of a technical
        file: the leaves, each by its code, else by its name."""
        by_code = {r["code"]: r.get("name", "") for r in rows if r.get("code")}
        drawn: list[str] = []
        missing: list[str] = []
        for code in nuts_leaves(list(by_code)):
            if self.has_nuts(code):
                drawn.append(code)
                continue
            other = self.nuts_by_name(code[:2], by_code[code]) if by_code[code] else None
            if other:
                drawn.append(other)
            else:
                missing.append(f"{code} {by_code[code]}".strip())
        return sorted(set(drawn)), missing

    # --- LAU ------------------------------------------------------------------

    def _lau_table(self, country_prefix: str) -> dict[str, list]:
        """normalised LAU name → [(gisco id, geometry in EPSG:4326)] for one
        country, read once from the GISCO LAU 2024 archive."""
        if country_prefix not in self._lau:
            import geopandas as gpd

            table: dict[str, list] = {}
            ids = self._lau_ids.setdefault(country_prefix, {})
            if self._lau_zip.exists():
                gdf = gpd.read_file(
                    f"zip://{self._lau_zip}", where=f"CNTR_CODE = '{country_prefix}'"
                ).to_crs(4326)
                for _, row in gdf.iterrows():
                    ids[row["GISCO_ID"]] = row.geometry
                    self._lau_names[row["GISCO_ID"]] = row["LAU_NAME"] or ""
                    # "Bolzano/Bozen" answers to either half; "Haselünne, Stadt"
                    # (the German layer appends the municipal rank) to its name
                    for part in re.split(r"\s*/\s*", row["LAU_NAME"] or ""):
                        table.setdefault(_norm(part), []).append((row["GISCO_ID"], row.geometry))
                        head, _, tail = part.partition(",")
                        table.setdefault(_norm(head), []).append((row["GISCO_ID"], row.geometry))
                        if tail and len(tail.strip()) <= 4:
                            # the Spanish layer postposes the article:
                            # "Puerto de Santa María, El"
                            table.setdefault(_norm(f"{tail} {head}"), []).append(
                                (row["GISCO_ID"], row.geometry)
                            )
                    table.setdefault(_norm(row["LAU_NAME"] or ""), []).append(
                        (row["GISCO_ID"], row.geometry)
                    )
            self._lau[country_prefix] = table
        return self._lau[country_prefix]

    def lau_geom(self, country_prefix: str, name: str, within: str = ""):
        """(gisco id, geometry) of the one municipality of a country named
        `name` — inside the NUTS unit `within` when the name is not unique —
        or None."""
        hits = {gid: geom for gid, geom in self._lau_table(country_prefix).get(_norm(name), [])}
        if len(hits) > 1:
            # two names that differ only by their accents (Kömörő, Komoró):
            # the one spelled as asked
            exact = {gid for gid in hits if self._lau_names.get(gid, "").split(",")[0].strip() == name}
            if exact:
                hits = {gid: hits[gid] for gid in exact}
        if within and len(hits) > 1:
            scope = self.nuts_geom(within)
            if scope is not None:
                hits = {gid: g for gid, g in hits.items() if scope.contains(g.representative_point())}
        if len(hits) != 1:
            return None
        gid, geom = next(iter(hits.items()))
        return gid, geom

    def lau_prefix_geom(self, country_prefix: str, id_prefix: str):
        """The union of the municipalities whose GISCO id starts with
        `id_prefix` after the country code — the unit above the LAU row that
        the id encodes: a Greek δήμος (4 digits) or δημοτική ενότητα (6), a
        Portuguese município (4 digits of the freguesia code) — or None."""
        self._lau_table(country_prefix)
        want = f"{country_prefix}_{id_prefix}"
        parts = {gid: geom for gid, geom in self._lau_ids.get(country_prefix, {}).items()
                 if gid.startswith(want)}
        return unary_union(list(parts.values())) if parts else None

    def ons_geom(self, level: str, name: str):
        """A UK country ("Scotland") or county / unitary authority
        ("Somerset") of the ONS layers, or None."""
        if level not in self._ons:
            table: dict[str, object] = {}
            path = ONS_DIR / ("countries.geojson" if level == "country" else "counties.geojson")
            if path.exists():
                for feat in json.loads(path.read_text(encoding="utf-8")).get("features") or []:
                    label = next((v for k, v in feat["properties"].items() if k.endswith("NM")), "")
                    if label:
                        table[_norm(label)] = shape(feat["geometry"])
            self._ons[level] = table
        return self._ons[level].get(_norm(name))

    # --- pins -----------------------------------------------------------------

    def resolve_units(self, units: list[str], geom_by_slug: dict | None = None) -> DrinkGeom:
        """Draw the units of a pin: `country:XX`, `nuts:CODE`,
        `lau:XX:Name[@NUTS]`, `lauid:XX:PREFIX=Label`, `uk:country:Name` /
        `uk:county:Name` (ONS), `ref:slug`; a unit
        written `minus:<unit>` is cut out of the union of the others ("the
        island of Lesbos, except the municipal unit of Plomari")."""
        out = DrinkGeom(source="drinks-area-pin")
        parts = []
        cuts = []
        for unit in units:
            minus = unit.startswith("minus:")
            if minus:
                sub = self.resolve_units([unit[len("minus:"):]], geom_by_slug)
                if sub.geom is None:
                    out.unresolved.append(unit)
                else:
                    cuts.append(sub.geom)
                continue
            kind, _, rest = unit.partition(":")
            geom = None
            if kind == "country":
                geom = self.nuts_geom(nuts_prefix(rest))
                out.units.append({"kind": "country", "code": rest.lower()})
            elif kind == "nuts":
                geom = self.nuts_geom(rest)
                out.units.append({"kind": "nuts", "code": rest})
            elif kind == "lau":
                cc, _, name = rest.partition(":")
                name, _, within = name.partition("@")
                hit = self.lau_geom(nuts_prefix(cc), name, within)
                unit_d = {"kind": "lau", "name": name, "country": cc.lower()}
                if hit:
                    geom = hit[1]
                    unit_d["nuts"] = self.nuts3_of(geom)
                out.units.append(unit_d)
            elif kind == "lauid":
                cc, _, spec = rest.partition(":")
                prefix, _, label = spec.partition("=")
                geom = self.lau_prefix_geom(nuts_prefix(cc), prefix)
                unit_d = {"kind": "lauid", "name": label or prefix, "country": cc.lower()}
                if geom is not None:
                    unit_d["nuts"] = self.nuts3_of(geom)
                out.units.append(unit_d)
            elif kind == "uk":
                level, _, name = rest.partition(":")
                name, _, label = name.partition("=")
                geom = self.ons_geom(level, name)
                out.units.append({"kind": "uk", "level": level, "name": label or name})
            elif kind == "ref":
                geom = (geom_by_slug or {}).get(rest)
                out.units.append({"kind": "ref", "slug": rest})
            if geom is None or geom.is_empty:
                out.unresolved.append(unit)
            else:
                parts.append(geom)
        if parts and not out.unresolved:
            geom = unary_union(parts)
            for cut in cuts:
                geom = geom.difference(cut)
            out.geom = geom if not geom.is_empty else None
        return out

    # --- entry point ----------------------------------------------------------

    def resolve(self, record: dict, geom_by_slug: dict | None = None) -> DrinkGeom:
        slug = record.get("slug") or ""
        pin = self.areas.get(slug)
        if pin and pin.get("units"):
            out = self.resolve_units(pin["units"], geom_by_slug)
            out.pin = pin
            if out.geom is not None and pin.get("largest_part"):
                # an island without the islets its parishes also hold
                parts = list(getattr(out.geom, "geoms", [out.geom]))
                out.geom = max(parts, key=lambda g: g.area)
            if out.geom is not None:
                return out
            # a pin that no longer resolves is reported, never half-drawn
            return DrinkGeom(source="stub-no-geometry", unresolved=out.unresolved, pin=pin)
        rows = record.get("geo_nuts") or []
        if rows:
            drawn, missing = self.resolve_nuts_rows(rows)
            leaves = nuts_leaves([r["code"] for r in rows if r.get("code")])
            if drawn and len(missing) * 5 <= len(leaves):
                geoms = [self.nuts_geom(c) for c in drawn]
                geoms = [g for g in geoms if g is not None]
                if geoms:
                    return DrinkGeom(
                        geom=unary_union(geoms), source="gisco-nuts-union",
                        units=[{"kind": "nuts", "code": c} for c in drawn], unresolved=missing,
                    )
            return DrinkGeom(source="stub-no-geometry", unresolved=missing or leaves)
        return DrinkGeom(source="stub-no-geometry")

    def unit_label(self, unit: dict) -> str:
        """A display name for a drawn unit: the layer's own Latin-script name
        for a NUTS-2 / NUTS-3 unit, the region table's for a NUTS-1 one, the
        pin's spelling for a municipality. A country and a referenced record
        are named per locale by `localise`."""
        if unit["kind"] == "nuts":
            code = unit["code"]
            return self._label.get(code) or region_of_nuts(code) or code
        return unit.get("name") or ""


def localise(geom_drinks: dict, lang: str, country_labels: dict[str, str],
             record_names: dict[str, str], ref_template: str) -> dict:
    """The panel's `geom_drinks` for one locale: a country unit named in the
    locale, a referenced record by its name inside `ref_template` ("the area
    of the {name} appellation"), and the pin's disclosure sentence of that
    locale as `precision` (English when the pin has no other)."""
    units = []
    for unit in geom_drinks.get("units") or []:
        if unit.get("kind") == "country":
            unit = {**unit, "label": country_labels.get(unit["code"]) or unit["code"].upper()}
        elif unit.get("kind") == "ref":
            name = record_names.get(unit["slug"]) or unit["slug"]
            unit = {**unit, "label": ref_template.replace("{name}", name)}
        units.append(unit)
    out = {k: v for k, v in geom_drinks.items() if k != "disclose"}
    out["units"] = units
    disclose = geom_drinks.get("disclose") or {}
    note = disclose.get(lang) or disclose.get("en")
    if note:
        out["precision"] = note
    return out
