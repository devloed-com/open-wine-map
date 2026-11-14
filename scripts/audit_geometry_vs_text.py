#!/usr/bin/env python3
"""The polygon against the text — do we draw the administrative units the
regulator's delimitation names, and no others? The `/validate-geometry`
validator (docs/plan-validators.md § 3).

The six existing geometry audits compare polygons with polygons. This one
reads, per record:

  named units   the municipalities the delimitation text names as members
                (each country's own reader: the INAO aires CSV + the cahier's
                section IV for France, the parsed commune lists of RO / BG /
                HU, the IT and AT parsers, the Swiss record's BFS communes;
                the GR / PT disclosure fields stage 04 writes), and with
                `--llm` an independent reading of the same text by a model,
                verified name by name against the layer;
  drawn units   the resolved polygon (wiki/map-data/appellations.geojson,
                streamed) reverse-geocoded against the layer the country is
                drawn from — GISCO LAU, IGN communes, swissBOUNDARIES, CAOP,
                ONS: covered whole (≥ 95 %), in part (> 5 %), or grazed.

and compares them through `geom_source`: for a commune-union record every
MISSING (named, not drawn) or EXTRA (drawn whole, not named) unit is a
parser defect; for a zone / Bétard / parcellaire record EXTRA units beyond
the named set are a vintage or attribution question and MISSING units are
expected to be parts. It also checks that a sub-denomination drawn from its
own units lies inside its parent (CHILD-OUTSIDE-PARENT — the overlap audit
skips hierarchy pairs, so nothing else does).

Buckets: OK / SUSPECT / REVIEWED (scripts/_lib/geometry_text_overrides.json)
/ PINNED (a drink's curated area: units beyond the parser's reading are no
finding, a named unit the polygon lacks is) / NO-TEXT / NO-UNITS / NO-GEOM.
`--strict` exits 1 on an unreviewed SUSPECT.
Read-only. Streams the 300 MB GeoJSON once (~1 min), loads only the layers
of the countries in scope.

    .venv/bin/python scripts/audit_geometry_vs_text.py --country ro --country bg --country hu
    .venv/bin/python scripts/audit_geometry_vs_text.py --country fr --only pauillac --only cevennes
    .venv/bin/python scripts/audit_geometry_vs_text.py --country es --llm --batch
    .venv/bin/python scripts/audit_geometry_vs_text.py --strict --json tmp/validation/geometry-text.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyogrio
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import card_packet  # noqa: E402

GEOJSON = ROOT / "wiki" / "map-data" / "appellations.geojson"
LAU_ZIP = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"
IGN_COMMUNES = ROOT / "raw" / "ign" / "communes.geojson"
SWISS_GPKG = sorted((ROOT / "raw" / "ch" / "swisstopo").glob("swissboundaries3d_*.gpkg"))
CAOP_CONT = ROOT / "raw" / "pt" / "caop" / "Continente_CAOP2025.gpkg"
ONS_COUNTIES = ROOT / "raw" / "gb" / "ons" / "counties.geojson"
OVERRIDES = ROOT / "scripts" / "_lib" / "geometry_text_overrides.json"
NUTS3 = ROOT / "raw" / "gr" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_3.geojson"
REPORT_DIR = ROOT / "tmp" / "validation"
LLM_CACHE = ROOT / "raw" / "cache" / "geometry-text-llm"

WHOLE, GRAZE = 0.95, 0.05
# country code → GISCO CNTR_CODE (EL for Greece); FR / CH / GB / PT draw from other layers
LAU_CC = {"es": "ES", "it": "IT", "at": "AT", "de": "DE", "be": "BE", "nl": "NL", "lu": "LU", "hu": "HU", "ro": "RO",
          "bg": "BG", "gr": "EL", "cy": "CY", "sk": "SK", "cz": "CZ", "si": "SI", "hr": "HR", "mt": "MT", "pt": "PT"}
COMMUNE_UNION_SOURCES = ("gisco-", "aires-csv", "communes", "swissboundaries-", "caop-", "iet-parroquia-union",
                         "dgc-village-override", "ons-", "nuts2-province", "region-pdo-union", "gisco-nuts-region")
PARCEL_OR_ZONE_SOURCES = ("parcellaire", "mapa-zone", "geoportal-", "figshare-pdo", "sigpac-", "cadastre-lieu-dit",
                          "ivv-commune-vineyard", "pdo-plan-parcel-hull-approx", "geometry-research-municipios")
# the drinks pipeline's two sources: a quote-checked pin, the technical file's NUTS rows
CURATED_AREA_SOURCES = ("drinks-area-pin", "gisco-nuts-union")
# a parent drawn from the communes a règlement scan happened to name is not a
# delimitation a child can be tested against (the CH cantonal AOCs)
PARTIAL_PARENT_SOURCES = ("swissboundaries-commune-union", "communes", "parent-appellation", "sibling-dgc", "stub-no-geometry")
# containment is tested only between polygons of one kind: a whole-commune DGC
# lies outside its parent's parcels by construction, a cadastral lieu-dit is
# approximate by design; and only above a floor (the tiled geometries are
# simplified, a 0.04 km² climat shows 40 % "outside" from vertex rounding)
CONTAINMENT_FLOOR_M2 = 250_000.0


def source_family(gs: str) -> str:
    if gs.startswith("parcellaire"):
        return "parcel"
    if gs.startswith(("cadastre-lieu-dit", "pdo-plan", "ivv-")):
        return "approx"
    if gs.startswith(("figshare", "mapa-zone", "geoportal", "sigpac")):
        return "zone"
    return "commune"
_to_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform


def log(msg: str) -> None:
    print(f"[geom-text] {msg}", file=sys.stderr)


# "Mercurol-Veaunes pour le seul territoire de la commune déléguée de Mercurol":
# the commune, and the fact that the text takes only part of it (so its
# parcels may cover less than the 5 % that counts as drawn in part).
_FR_PARTIAL_RE = re.compile(r"\s+pour le (?:seul )?territoire\b.*$", re.I | re.S)


def fr_token(name: str) -> tuple[str, bool]:
    base = _FR_PARTIAL_RE.sub("", name or "").strip(" ,;.")
    return base, base != (name or "").strip(" ,;.")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"^(le|la|les|l|el|los|las|il|lo|gli|le|der|die|das|de|du|des|d|a|o|os|as)\s+", "", s.strip())
    # administrative-tier prefixes the layers print and the texts do not
    # ("Oraş Babadag", "Municipiul Tulcea", "Comuna X", "Община Y", "Obec Z")
    s = re.sub(r"^(oras|orasul|municipiul|comuna|obshtina|община|obec|mesto|město|gemeinde|stadt|markt|comune di|comune)\s+", "", s)
    return " ".join(s.split())


# ────────────────────────────────────────────────────────────── layers ──


class Layer:
    """Administrative units of one layer in EPSG:3035 with an STRtree, a
    name index and reverse geocoding."""

    def __init__(self, label: str):
        self.label = label
        self.ids: list[str] = []
        self.names: list[str] = []
        self.geoms: list = []
        self.extra: list[dict] = []
        self._by_norm: dict[str, list[int]] = defaultdict(list)
        self._tree = None

    def add(self, uid: str, name: str, geom, **extra) -> None:
        if geom is None or geom.is_empty:
            return
        self.ids.append(uid)
        self.names.append(name)
        self.geoms.append(geom)
        self.extra.append(extra)
        self._by_norm[norm(name)].append(len(self.ids) - 1)

    def build(self) -> None:
        self._tree = STRtree(self.geoms)

    def by_name(self, name: str, *, within: dict | None = None) -> list[int]:
        cands = self._by_norm.get(norm(name), [])
        if within:
            cands = [i for i in cands if all(self.extra[i].get(k) == v for k, v in within.items())]
        return cands

    def covered(self, geom) -> tuple[list[int], list[int]]:
        whole, part = [], []
        for i in self._tree.query(geom):
            g = self.geoms[i]
            a = g.area
            if not a:
                continue
            try:
                share = g.intersection(geom).area / a
            except Exception:  # noqa: BLE001
                share = g.buffer(0).intersection(geom.buffer(0)).area / a
            if share >= WHOLE:
                whole.append(int(i))
            elif share > GRAZE:
                part.append(int(i))
        return whole, part


def load_lau(countries: set[str]) -> Layer:
    codes = {LAU_CC[c] for c in countries if c in LAU_CC}
    layer = Layer("GISCO LAU 2024")
    if not codes:
        layer.build() if layer.geoms else None
        return layer
    df = pyogrio.read_dataframe(str(LAU_ZIP), where="CNTR_CODE IN (" + ",".join(f"'{c}'" for c in sorted(codes)) + ")")
    for row in df.itertuples(index=False):
        layer.add(row.GISCO_ID, row.LAU_NAME or "", row.geometry, cntr=row.CNTR_CODE)
    layer.build()
    log(f"LAU: {len(layer.ids)} units for {sorted(codes)}")
    if "RO" in codes:
        _tag_ro_judete(layer)
    return layer


def _tag_ro_judete(layer: Layer) -> None:
    """Each RO unit's județ, read off the GISCO NUTS-3 polygons — the county
    masks stage 04's resolver holds a header's names to."""
    if not NUTS3.exists():
        log(f"{NUTS3} missing — RO names are scoped by distance only")
        return
    from _lib.ro.commune import _normalise_commune as ro_norm
    from shapely.prepared import prep
    masks = []
    for f in json.loads(NUTS3.read_text(encoding="utf-8"))["features"]:
        p = f.get("properties") or {}
        if p.get("CNTR_CODE") == "RO" and f.get("geometry"):
            masks.append((ro_norm(p.get("NUTS_NAME") or ""), prep(shp_transform(_to_3035, shape(f["geometry"])))))
    for i, ex in enumerate(layer.extra):
        if ex.get("cntr") != "RO":
            continue
        pt = layer.geoms[i].representative_point()
        for key, m in masks:
            if m.contains(pt):
                ex["judet"] = key
                break
    layer.ro_judete = True


def load_ign() -> Layer:
    layer = Layer("IGN communes")
    df = pyogrio.read_dataframe(str(IGN_COMMUNES))
    df["geometry"] = df["geometry"].apply(lambda g: shp_transform(_to_3035, g))
    for row in df.itertuples(index=False):
        layer.add(row.code, row.nom or "", row.geometry, dept=str(row.codeDepartement))
    layer.build()
    log(f"IGN: {len(layer.ids)} communes")
    return layer


def load_swiss() -> Layer:
    layer = Layer("swissBOUNDARIES3D")
    if not SWISS_GPKG:
        return layer
    tr = Transformer.from_crs("EPSG:2056", "EPSG:3035", always_xy=True).transform
    df = pyogrio.read_dataframe(str(SWISS_GPKG[-1]), layer="tlm_hoheitsgebiet", where="objektart = 'Gemeindegebiet'",
                                columns=["bfs_nummer", "name", "kantonsnummer"])
    import math
    for row in df.itertuples(index=False):
        bfs, kt = row.bfs_nummer, row.kantonsnummer
        if bfs is None or (isinstance(bfs, float) and math.isnan(bfs)):
            continue  # the two foreign exclaves (Büsingen, Campione) carry no BFS number
        kanton = -1 if kt is None or (isinstance(kt, float) and math.isnan(kt)) else int(kt)
        layer.add(str(int(bfs)), row.name or "", shp_transform(tr, row.geometry), kanton=kanton)
    layer.build()
    log(f"CH: {len(layer.ids)} Gemeinden")
    return layer


def load_caop() -> Layer:
    layer = Layer("CAOP 2025 freguesias")
    if not CAOP_CONT.exists():
        return layer
    for p in [CAOP_CONT] + sorted((ROOT / "raw" / "pt" / "caop").glob("Arq*CAOP2025.gpkg")):
        layer_names = [row[0] for row in pyogrio.list_layers(str(p))]
        fl = next((name for name in layer_names if name.endswith("freguesias")), None)
        if not fl:
            continue
        info = pyogrio.read_info(str(p), layer=fl)
        crs = info.get("crs") or "EPSG:3763"
        t = Transformer.from_crs(crs, "EPSG:3035", always_xy=True).transform if crs != "EPSG:3035" else None
        df = pyogrio.read_dataframe(str(p), layer=fl)
        for row in df.itertuples(index=False):
            g = shp_transform(t, row.geometry) if t else row.geometry
            layer.add(str(row.dtmnfr), row.freguesia or "", g, municipio=norm(row.municipio or ""))
    layer.build()
    log(f"PT: {len(layer.ids)} freguesias")
    return layer


def load_ons() -> Layer:
    layer = Layer("ONS counties / UAs")
    if ONS_COUNTIES.exists():
        df = pyogrio.read_dataframe(str(ONS_COUNTIES))
        for row in df.itertuples(index=False):
            layer.add(row.CTYUA25CD, row.CTYUA25NM or "", shp_transform(_to_3035, row.geometry))
    if layer.geoms:
        layer.build()
    return layer


# ─────────────────────────────────────────────────────── named units ──


def _ro_bg_hu_names(country: str, text: str) -> list[str]:
    try:
        if country == "ro":
            from _lib.ro.commune import parse_commune_list
        elif country == "bg":
            from _lib.bg.commune import parse_commune_list
        else:
            from _lib.hu.commune import parse_commune_list
        return list(parse_commune_list(text or ""))
    except Exception as e:  # noqa: BLE001
        log(f"{country} parser failed: {e!r}")
        return []


_IT_INDEX = None
_AT_INDEX = None


def _it_names(text: str) -> tuple[list[str], list[str]]:
    global _IT_INDEX
    if _IT_INDEX is None:
        from _lib.it.comune import ITCommuneIndex
        _IT_INDEX = ITCommuneIndex(istat_csv=ROOT / "raw" / "it" / "istat" / "Elenco-comuni-italiani.csv", gisco_lau_zip=LAU_ZIP)
    parsed = _IT_INDEX.parse_geo_area(text or "")
    above = list(parsed.get("province") or []) + list(parsed.get("regioni") or [])
    return list(parsed.get("comuni") or []), above


def _at_names(text: str) -> tuple[list[str], list[str]]:
    global _AT_INDEX
    if _AT_INDEX is None:
        from _lib.at.gemeinde import ATCommuneIndex
        d = ROOT / "raw" / "at" / "statistik"
        _AT_INDEX = ATCommuneIndex(polbezirke_csv=d / "polbezirke.csv", gemliste_csv=d / "gemliste_knz.csv", gisco_lau_zip=LAU_ZIP)
    parsed = _AT_INDEX.parse_geo_area(text or "")
    return list(parsed.get("gemeinden") or []), list(parsed.get("bezirke") or []) + list(parsed.get("bundeslaender") or [])


def area_text(country: str, rec: dict) -> str:
    """The delimitation text of a record: the routed geo-area section, the
    national-spec sidecar's, or the FR aire section."""
    for key in ("geo_area_brief", "geo_area"):
        if isinstance(rec.get(key), str) and rec[key].strip():
            return rec[key]
    roles = rec.get("section_roles") or {}
    for k in ("geo_area", "aire", "area"):
        if isinstance(roles.get(k), str) and roles[k].strip():
            return roles[k]
    return ""


HU_COUNTIES = {norm(n) for n in (
    "Bács-Kiskun", "Baranya", "Békés", "Borsod-Abaúj-Zemplén", "Csongrád-Csanád", "Csongrád", "Fejér",
    "Győr-Moson-Sopron", "Hajdú-Bihar", "Heves", "Jász-Nagykun-Szolnok", "Komárom-Esztergom", "Nógrád", "Pest",
    "Somogy", "Szabolcs-Szatmár-Bereg", "Tolna", "Vas", "Veszprém", "Zala", "Budapest")}
HOMONYM_KM = 25.0


def _pick_near(layer: Layer, hits: list[int], geom) -> list[int]:
    """Of several same-named units keep those within HOMONYM_KM of the
    record's polygon: a delimitation names its own neighbourhood, and a
    homonym three counties away is the layer's, not the text's."""
    if geom is None or len(hits) <= 1:
        return hits
    near = geom.buffer(HOMONYM_KM * 1000)
    return [i for i in hits if layer.geoms[i].intersects(near)]


def _bg_oblast_hits(layer: Layer, name: str, prefix: str) -> list[int]:
    """A BG obshtina name among one oblast's units: exact, then with the
    spaces closed ("Вълчидол" / Вълчи дол), then a one-letter abbreviation
    ("Д. Митрополия" / Долна Митрополия) when it names one unit only."""
    pool = [i for i, uid in enumerate(layer.ids) if uid.startswith(prefix)]
    key = norm(name)
    hits = [i for i in pool if norm(layer.names[i]) == key]
    if hits:
        return hits
    hits = [i for i in pool if norm(layer.names[i]).replace(" ", "") == key.replace(" ", "")]
    if hits:
        return hits
    words = key.split()
    if any(len(w) == 1 for w in words):
        pat = re.compile(r"\s+".join(re.escape(w) + (r"\w*" if len(w) == 1 else "") for w in words) + "$")
        hits = [i for i in pool if pat.match(norm(layer.names[i]))]
        if len(hits) == 1:
            return hits
    return []


def with_national_spec(country: str, slug: str, rec: dict) -> dict:
    """A national-spec stub's area as stage 04 draws it: the augmenter copies
    the sidecar's commune list onto the record (BG Тракийска низина, the RO
    caiet stubs), so the audit reads it from there too."""
    if rec.get("geo_communes"):
        return rec
    for kind, _label, d in card_packet.SIDECAR_DIRS.get(country, ()):
        if kind != "national-spec":
            continue
        sc = card_packet.load_json(d / f"{slug}.json") or {}
        if sc.get("geo_communes"):
            rec = dict(rec)
            for k in ("geo_communes", "geo_communes_scoped", "geo_communes_partial", "geo_communes_villages",
                      "geo_area_brief"):
                if sc.get(k):
                    rec[k] = sc[k]
            return rec
    return rec


_FR_FORMER: dict = {}


def _fr_former(current: set[str]) -> dict:
    if not _FR_FORMER:
        from _lib.fr import former_communes as fc
        former = fc.load(current, log=False)
        chef = {}
        if fc.FORMER_GEOJSON.exists():
            chef = {f["properties"]["code"]: f["properties"]["chefLieu"]
                    for f in json.loads(fc.FORMER_GEOJSON.read_text(encoding="utf-8"))["features"]}
        _FR_FORMER.update(successor=former.successor, chef=chef, former=former, resolve=fc.resolve)
    return _FR_FORMER


def _fr_dead_codes(insee: set[str], current: set[str]) -> set[str]:
    """The codes of an aire whose ground left its département before the
    cahiers and lies outside the aire (Chassieu, 38088, in IGP Isère's rows):
    not rows of the aire, nothing of them is drawn."""
    table = _fr_former(current)
    return set(table["resolve"](set(insee), current, table["former"]).elsewhere)


def _fr_commune_of_today(code: str, current: set[str]) -> str | None:
    """The commune of today that holds a pre-merger INSEE code of INAO's rows."""
    table = _fr_former(current)
    end = table["successor"].get(code) or table["chef"].get(code)
    return end if end in current else None


def named_units(country: str, slug: str, rec: dict, startup: dict, payload: dict, layer: Layer | None,
                fr_aires=None, dept_codes: dict | None = None, geom=None) -> dict:
    """{ids, unresolved, above_commune, far, method} — the units the text
    names, resolved to the layer's ids. A unique hit farther than HOMONYM_KM
    from the polygon is listed under `far` and not counted as named."""
    out = {"ids": set(), "unresolved": [], "above_commune": [], "far": [], "method": "", "partial": set()}
    if layer is None or not layer.geoms:
        return out
    if country == "fr":
        from _lib import aires as aires_mod
        from _lib.geom_chain import dept_code_for
        if startup.get("is_sub_denomination"):
            # a DGC shares the parent's cahier: its section IV and the CSV row
            # the name lookup falls back to describe the parent, not the DGC
            out["method"] = "sub-denomination: parent aire not applicable"
            return out
        name = startup.get("name") or rec.get("name") or ""
        cahier_ids: set[str] = set()
        ag = ((rec.get("aire") or {}).get("aire_geographique") or {})
        if isinstance(ag, dict):
            for dept, names in ag.items():
                code = (dept_codes or {}).get(norm(dept)) or dept_code_for(dept)
                for n in names or []:
                    base, partial = fr_token(n)
                    hits = layer.by_name(base, within={"dept": code} if code else None)
                    if len(hits) > 1:
                        hits = _pick_near(layer, hits, geom)
                    if len(hits) == 1:
                        cahier_ids.add(layer.ids[hits[0]])
                        if partial:
                            out["partial"].add(layer.ids[hits[0]])
                    elif not hits:
                        out["unresolved"].append(f"{n} ({dept})")
        insee = None
        try:
            # the cahier's own communes choose the aire where a name has two
            # (IDA 2375 the Calvados spirit, 1993 the Calvados wine IGP) — the
            # hint stage 04 passes; without it the two were pooled and each
            # record "named" the other's communes
            insee = aires_mod.lookup(fr_aires, name, cahier_ids or None)
        except Exception:  # noqa: BLE001
            insee = None
        if insee:
            current = set(layer.ids)
            out["ids"] |= {i for i in insee if i in current}
            # a row written before a merger names the commune of today in
            # part: stage 04 draws the former commune's own outline where one
            # exists (scripts/_lib/fr/former_communes.py)
            dead = _fr_dead_codes(insee, current)
            for code in insee:
                end = None if code in current or code in dead else _fr_commune_of_today(code, current)
                if end and end not in insee:
                    out["ids"].add(end)
                    out["partial"].add(end)
            # the seat of a commune nouvelle the cahier names by its former
            # name, or restricts to named former communes: drawn as those
            # (scripts/_lib/fr/seat_communes.py), the commune of today in part
            from _lib.fr.seat_communes import narrowed_seats
            out["partial"] |= set(narrowed_seats(
                rec, set(insee), dict(zip(layer.ids, layer.names)), _fr_former(current)["former"]))
            out["method"] = "inao-aires-csv"
        out["ids"] |= cahier_ids
        # a commune the curator's pin records as named in part, or named and
        # excluded (`not_drawn` in aires_supplements.json — Pommeau de
        # Normandie's « Communes incluses en partie »): a decided difference
        pin = aires_mod.load_aire_supplements().get(slug) or {}
        out["partial"] |= {c for c in pin.get("not_drawn") or {} if c in out["ids"]}
        if ag:
            out["method"] = (out["method"] + "+cahier-iv").strip("+")
        for d in (rec.get("aire") or {}).get("aire_departements") or rec.get("aire_departements") or []:
            out["above_commune"].append(d)
        return out
    if country == "ch":
        for gc in rec.get("geo_communes") or []:
            if isinstance(gc, dict) and gc.get("bfs_id") is not None:
                out["ids"].add(str(int(gc["bfs_id"])))
        out["method"] = "record-geo_communes"
        return out
    text = area_text(country, rec)
    names: list[str] = []
    gc = rec.get("geo_communes")
    if isinstance(gc, list) and gc and country in ("ro", "bg", "hu", "gr", "cy"):
        # the pipeline's own parse of the commune list (the sidecar's for a
        # national-spec stub); `--llm` is the independent reading
        names = [x.get("name") if isinstance(x, dict) else str(x) for x in gc]
        names = [n for n in names if n]
        out["method"] = "record-geo_communes"
    elif country in ("ro", "bg", "hu"):
        names = _ro_bg_hu_names(country, text)
        out["method"] = f"{country}-parse_commune_list"
    elif country == "it":
        names, out["above_commune"] = _it_names(text)
        out["method"] = "it-parse_geo_area"
    elif country == "at":
        names, out["above_commune"] = _at_names(text)
        out["method"] = "at-parse_geo_area"
    elif country in ("gr", "pt"):
        out["method"] = "stage-04-disclosure"
        out["unresolved"] = list(payload.get("geom_units_unmatched") or [])
        if not names:
            return out
    if not text and not names:
        out["method"] = out["method"] or "none"
        return out
    cc = LAU_CC.get(country)
    near = geom.buffer(HOMONYM_KM * 1000) if geom is not None else None
    scoped = rec.get("geo_communes_scoped") if out["method"] == "record-geo_communes" else None
    if scoped and country == "ro" and getattr(layer, "ro_judete", False):
        # a name the text lists under "Judeţul X" is X's: the village Oneşti
        # of comuna Plugari (Iaşi) is not Municipiul Oneşti (Bacău), however
        # close; names under no header take the record's declared județe —
        # stage 04's rule (ROPolygonIndex.commune_union), the spellings of
        # its checked alias table included
        from _lib.ro.commune import _SPELLING_ALIASES, judet_source_text, parse_judet_list
        from _lib.ro.commune import _normalise_commune as ro_norm
        record_judete = set(parse_judet_list(judet_source_text(rec)))

        def ro_hits(name: str, own: set[str]) -> list[int]:
            key = ro_norm(name)
            key = _SPELLING_ALIASES.get(key, key)
            hits = [i for i in layer._by_norm.get(norm(key), []) if layer.extra[i].get("cntr") == "RO"]
            if own:
                return [i for i in hits if layer.extra[i].get("judet") in own]
            return _pick_near(layer, hits, geom) if len(hits) > 1 else hits

        # a name the text gives only as a village names a commune only where
        # that commune touches the village's own (a 2004 split) — the
        # resolver's rule, `ROPolygonIndex.commune_union`
        village_of: dict[str, list[str]] = defaultdict(list)
        for v, h in rec.get("geo_communes_villages") or []:
            village_of[norm(ro_norm(v))].append(h)
        for n, judete in scoped:
            own = set(judete or []) or record_judete
            hits = ro_hits(n, own)
            if len(hits) == 1 and norm(ro_norm(n)) in village_of:
                heads = [h for hn in village_of[norm(ro_norm(n))] for h in ro_hits(hn, own)[:1]]
                if not any(layer.geoms[hits[0]].distance(layer.geoms[h]) < 200 for h in heads):
                    continue
            if len(hits) == 1:
                out["ids"].add(layer.ids[hits[0]])
            elif hits:
                out["unresolved"].append(f"{n} (×{len(hits)} in-județ)")
            else:
                out["unresolved"].append(n)
        out["method"] += "+judet-scoped"
        return out
    if scoped and country == "bg":
        # the text's own oblast header scopes each name (BG_VAR… = област
        # Варна): two obshtini are called Бяла, and a named obshtina far
        # from the polygon is the text's, so it counts as missing, not far
        from _lib.bg.commune import OBSHTINA_GROUPS
        from _lib.bg.commune import _normalise_commune as bg_norm
        for n, code in scoped:
            group = OBSHTINA_GROUPS.get((bg_norm(n), code or ""))
            if group:
                # one name the regulator writes for several obshtini (Добрич)
                for m in group:
                    out["ids"].update(layer.ids[i] for i in _bg_oblast_hits(layer, m, f"BG_{code}")[:1])
                continue
            hits = _bg_oblast_hits(layer, n, f"BG_{code}") if code else layer.by_name(n, within={"cntr": cc})
            if len(hits) == 1:
                out["ids"].add(layer.ids[hits[0]])
            else:
                out["unresolved"].append(n + (f" (×{len(hits)})" if hits else ""))
        out["method"] += "+oblast-scoped"
        return out
    for n in names:
        if country == "hu" and norm(n) in HU_COUNTIES:
            out["above_commune"].append(n)
            continue
        hits = layer.by_name(n, within={"cntr": cc} if cc else None)
        if len(hits) > 1:
            hits = _pick_near(layer, hits, geom)
        if len(hits) == 1:
            if near is not None and not layer.geoms[hits[0]].intersects(near):
                out["far"].append(n)
            else:
                out["ids"].add(layer.ids[hits[0]])
        elif len(hits) > 1:
            out["unresolved"].append(f"{n} (×{len(hits)} homonyms nearby)")
        else:
            out["unresolved"].append(n)
    return out


# ───────────────────────────────────────────────────────── LLM read ──

LLM_SYSTEM = """You read a wine appellation's delimitation text (the regulator's own words) and list the administrative units it names. Return JSON only:
{"members": [{"name": "", "level": "municipality|parish|village|district|province|region|department|canton|other", "parent": "", "quote": ""}], "excluded": [{"name": "", "level": "", "parent": "", "quote": ""}], "holders": [{"name": "", "level": "", "parent": "", "quote": ""}]}
- members: units whose whole territory is included. A unit named as a whole ("the whole of the province of X", "l'intero territorio comunale di X") is a member at its level.
- A municipality listed with its villages ("Comuna X, satele X, A, B", "X cu satele …") is one member at municipality level; do not list its villages. A village named on its own, without its municipality, is a member at village level.
- parent: the county / province / oblast / district heading or phrase the text files the unit under ("Judeţul Iaşi", "Област Варна"), else "".
- excluded: units the text excludes.
- holders: units named only as the container of smaller units ("the parishes A and B of the municipality X" → X is a holder, A and B members at parish level; "the parcels of section C in commune Y" → Y is a holder).
Boundary prose (roads, rivers, ridges, "follows the line from A to B") names landmarks, not members — skip it. Keep the regulator's spelling; one quote (≤ 120 chars) per unit. No text before or after the JSON."""


def _llm_scope(country: str, layer: Layer, hits: list[int], parent: str, geom) -> list[int]:
    """Hold an LLM-named unit to the county / oblast it reported, as the
    deterministic side does; without one, a homonym is taken within
    HOMONYM_KM of the polygon."""
    if parent and country == "ro" and getattr(layer, "ro_judete", False):
        from _lib.ro.commune import _county_prefix
        key, _n = _county_prefix(re.sub(r"(?i)^\s*(?:\d[\d.]*\s*)?(?:jude[țţt](?:ul|ului)?|jud\.)\s*", "", parent))
        if key:
            return [i for i in hits if layer.extra[i].get("judet") == key]
    if parent and country == "bg":
        from _lib.bg.commune import oblast_code
        code = oblast_code(re.sub(r"(?i)^\s*област\s+", "", parent))
        if code:
            return [i for i in hits if layer.ids[i].startswith(f"BG_{code}")]
    return _pick_near(layer, hits, geom) if len(hits) > 1 else hits


def llm_named_units(country: str, slug: str, text: str, layer: Layer, provider, model: str, cache_dir: Path,
                    geom=None) -> dict:
    import hashlib

    from _lib import llm_json
    from _lib.prompt_cache import mark_cached
    key = hashlib.sha256(f"{model}|{LLM_SYSTEM}|{text}".encode("utf-8")).hexdigest()[:24]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = cache_dir / f"{key}.json"
    data = None
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
        except ValueError:
            data = None
    if data is None:
        # the answer lists every unit with a quote: a 10,000-character
        # commune list (Dealurile Moldovei, ~200 communes) needs room for it
        # beside the model's thinking, or the JSON comes back cut off — and
        # a Cyrillic or Greek text costs about three times the tokens
        # (Дунавска равнина's 3,500 characters name ~300 units)
        per_char = 1 if text.isascii() or country not in ("bg", "gr", "cy") else 3
        raw = provider.chat(system=mark_cached(LLM_SYSTEM), user=f"COUNTRY: {country}\nRECORD: {slug}\n\nDELIMITATION TEXT:\n{text[:40000]}",
                            max_tokens=min(32000, 6000 + per_char * len(text[:40000])))
        s = llm_json.strip_fences(raw or "")
        try:
            data = json.loads(s)
        except ValueError:
            m = re.search(r"\{.*\}", s, re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except ValueError:
                data = {}
        if raw and data:
            # never cache a truncated or unparsed answer as "names nothing"
            cp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        elif raw:
            log(f"{slug}: LLM answer did not parse ({len(raw)} chars) — not cached")
    out = {"ids": set(), "unresolved": [], "above_commune": [], "below_commune": [], "excluded_ids": set(), "holders": []}
    cc = LAU_CC.get(country)
    for m in data.get("members") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        if (m.get("level") or "") in ("province", "region", "department", "district", "canton"):
            out["above_commune"].append(m["name"])
            continue
        if (m.get("level") or "") == "village" and country in ("ro", "bg", "hu"):
            # below the LAU tier of these layers: no unit to compare
            out["below_commune"].append(m["name"])
            continue
        hits = layer.by_name(m["name"], within={"cntr": cc} if cc else None)
        if country == "bg" and not hits and m.get("parent"):
            from _lib.bg.commune import oblast_code
            code = oblast_code(re.sub(r"(?i)^\s*област\s+", "", m["parent"]))
            hits = _bg_oblast_hits(layer, m["name"], f"BG_{code}") if code else []
        hits = _llm_scope(country, layer, hits, m.get("parent") or "", geom)
        if len(hits) == 1:
            out["ids"].add(layer.ids[hits[0]])
        else:
            out["unresolved"].append(m["name"] + (f" (×{len(hits)})" if hits else ""))
    for m in data.get("excluded") or []:
        if isinstance(m, dict) and m.get("name"):
            for i in layer.by_name(m["name"], within={"cntr": cc} if cc else None):
                out["excluded_ids"].add(layer.ids[i])
    out["holders"] = [m.get("name") for m in data.get("holders") or [] if isinstance(m, dict)]
    return out


# ───────────────────────────────────────────────────────── compare ──


def classify(geom_source: str, named: set[str], drawn_whole: set[str], drawn_part: set[str],
             *, named_above: list[str]) -> tuple[str, dict]:
    gs = geom_source or ""
    union = any(gs.startswith(p) for p in COMMUNE_UNION_SOURCES)
    detail = {"missing": sorted(named - drawn_whole - drawn_part), "part": sorted(named & drawn_part),
              "extra": sorted(drawn_whole - named) if named else [], "named": len(named),
              "drawn_whole": len(drawn_whole), "drawn_part": len(drawn_part)}
    if not named:
        return ("NO-UNITS" if not named_above else "ABOVE-COMMUNE"), detail
    n = len(named)
    if named_above and n < 0.5 * max(len(drawn_whole), 1):
        # the text delimits by a tier the layer does not carry (counties,
        # provinces); the few communes it also names cannot judge the polygon
        return "ABOVE-COMMUNE", detail
    miss, extra, part = len(detail["missing"]), len(detail["extra"]), len(detail["part"])
    if union:
        bad = miss + extra
        if bad and ((bad >= 2 and bad / n >= 0.03) or bad >= 6):
            return "SUSPECT", detail
        if part and part / n > 0.3 and not gs.startswith(("caop-freguesia", "iet-", "dgc-village")):
            return "SUSPECT", detail
        return "OK", detail
    # parcel / zone sources: parts are expected; whole extra units are the signal
    if extra and (extra >= 2 and extra / max(n, 1) >= 0.1):
        return "SUSPECT", detail
    if miss == n and n >= 2 and not gs.startswith("parcellaire"):
        return "SUSPECT", detail
    return "OK", detail


def curated_area_bucket(bucket: str, geom_source: str, detail: dict) -> str:
    """A drink's area is a curator pin (every quote and unit checked by
    tests/test_drinks_areas.py) or the register's NUTS rows. The country
    parsers were written for wine texts and read fewer names from a drink's
    (a county taken for a commune, "Krems" for Krems an der Donau), so whole
    units beyond their reading are no finding: PINNED. A name they did read
    that the polygon lacks stays SUSPECT."""
    if (bucket == "SUSPECT" and geom_source in CURATED_AREA_SOURCES
            and not detail.get("missing") and not detail.get("child_outside_parent")):
        return "PINNED"
    return bucket


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geojson", type=Path, default=GEOJSON)
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--llm", action="store_true", help="also read the delimitation text with a model and compare")
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral", "ollama"))
    ap.add_argument("--model", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()

    aocs, _ = card_packet.load_startup("en")
    if not aocs:
        sys.exit("no built site")
    scope = [s for s, r in aocs.items() if (not args.country or r.get("country") in set(args.country))
             and (not args.only or s in set(args.only))]
    if args.sample and len(scope) > args.sample:
        import random
        random.Random(args.seed).shuffle(scope)
        scope = scope[:args.sample]
    scope_set = set(scope)
    countries = {aocs[s]["country"] for s in scope}
    log(f"scope {len(scope)} records, countries {sorted(countries)}")

    layers: dict[str, Layer] = {}
    lau_cc = {c for c in countries if c in LAU_CC}
    if lau_cc:
        lau = load_lau(lau_cc)
        for c in lau_cc:
            layers[c] = lau
    if "fr" in countries:
        layers["fr"] = load_ign()
    if "ch" in countries:
        layers["ch"] = load_swiss()
    if "pt" in countries:
        layers["pt"] = load_caop()
    if "gb" in countries:
        layers["gb"] = load_ons()
    fr_aires = None
    dept_codes: dict[str, str] = {}
    if "fr" in countries:
        from _lib import aires as aires_mod
        fr_aires = aires_mod.load_aires()
        # the resolver's spirit guard, as stage 04 sets it (Marc de Champagne
        # is not the wine Champagne's aire)
        aires_mod.register_product_names(
            (r.get("name") for r in aocs.values()
             if r.get("country", "fr") == "fr" and r.get("product_class") == "spirit"),
            (r.get("name") for r in aocs.values()
             if r.get("country", "fr") == "fr" and r.get("is_wine", True) is not False),
        )
        import csv
        with (ROOT / "raw" / "inao" / "aoc-aop-aires-communes.csv").open(encoding="latin-1") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                ci = row.get("CI") or ""
                code = ci[:2] if not ci.startswith("97") else ci[:3]
                if ci[:2] == "20":
                    code = "2A" if ci[:3] <= "202" else "2B"
                dept_codes.setdefault(norm(row.get("Département") or row.get("D�partement") or ""), code)

    # geometries, streamed once; parents of scoped children are needed for containment
    want = set(scope_set)
    for s in scope:
        p = aocs[s].get("parent_slug")
        if p and p in aocs:
            want.add(p)
    spec = importlib.util.spec_from_file_location("owm_outliers", ROOT / "scripts" / "audit_geometry_outliers.py")
    outl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(outl)
    geoms: dict[str, object] = {}
    log(f"streaming {args.geojson.name} …")
    for ft in outl.stream_features(args.geojson):
        slug = (ft.get("properties") or {}).get("slug")
        if slug in want:
            try:
                geoms[slug] = shp_transform(_to_3035, shape(ft["geometry"]))
            except Exception as e:  # noqa: BLE001
                log(f"{slug}: geometry unreadable: {e!r}")
    log(f"{len(geoms)} geometries in scope")

    overrides = {k: v for k, v in json.loads(OVERRIDES.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    provider = model = None
    if args.llm:
        from _lib import providers
        from _lib.env import load_dotenv
        load_dotenv()
        provider, model = providers.make_provider(args.provider, model=args.model, stage="audit")

    rows: list[dict] = []
    for slug in sorted(scope):
        rec_s = aocs[slug]
        cc = rec_s["country"]
        layer = layers.get(cc)
        geom = geoms.get(slug)
        payload = card_packet.load_payload("en", slug) or {}
        rp = card_packet.record_path(cc, slug)
        rec = card_packet.load_json(rp) if rp else None
        if rec is None and rec_s.get("parent_slug"):
            prp = card_packet.record_path(cc, rec_s["parent_slug"])
            rec = card_packet.load_json(prp) if prp else None
        rec = with_national_spec(cc, slug, rec or {})
        row = {"slug": slug, "country": cc, "name": rec_s.get("name"), "geom_source": rec_s.get("geom_source"),
               "is_sub_denomination": bool(rec_s.get("is_sub_denomination")), "parent_slug": rec_s.get("parent_slug") or ""}
        if geom is None:
            row.update(bucket="NO-GEOM", detail={})
            rows.append(row)
            continue
        if layer is None or not layer.geoms:
            row.update(bucket="NO-LAYER", detail={})
            rows.append(row)
            continue
        whole, part = layer.covered(geom)
        drawn_whole = {layer.ids[i] for i in whole}
        drawn_part = {layer.ids[i] for i in part}
        nu = named_units(cc, slug, rec, rec_s, payload, layer, fr_aires=fr_aires, dept_codes=dept_codes, geom=geom)
        # a commune the text takes in part only is not missing when its few
        # parcels fall under the drawn-in-part threshold
        partial_undrawn = (nu.get("partial") or set()) - drawn_whole - drawn_part
        bucket, detail = classify(rec_s.get("geom_source") or "", nu["ids"] - partial_undrawn, drawn_whole, drawn_part,
                                  named_above=nu["above_commune"])
        detail["method"] = nu["method"]
        if partial_undrawn:
            detail["partial_undrawn"] = sorted(partial_undrawn)
        detail["unresolved"] = nu["unresolved"][:20]
        detail["far_homonyms"] = nu.get("far", [])[:10]
        detail["above_commune"] = nu["above_commune"][:10]
        if not area_text(cc, rec) and cc not in ("fr", "ch") and not nu["ids"]:
            bucket = "NO-TEXT"
        if args.llm and provider is not None:
            text = area_text(cc, rec) if cc != "fr" else ((rec.get("section_roles") or {}).get("aire") or "")
            if text.strip():
                lu = llm_named_units(cc, slug, text, layer, provider, model, LLM_CACHE, geom=geom)
                lb, ld = classify(rec_s.get("geom_source") or "", lu["ids"], drawn_whole, drawn_part, named_above=lu["above_commune"])
                detail["llm"] = {"bucket": lb, "named": len(lu["ids"]), "missing": ld["missing"][:20], "extra": ld["extra"][:20],
                                 "unresolved": lu["unresolved"][:20], "above_commune": lu["above_commune"][:10],
                                 "villages": len(lu["below_commune"]),
                                 "parser_only": sorted(nu["ids"] - lu["ids"])[:30], "llm_only": sorted(lu["ids"] - nu["ids"])[:30],
                                 "agrees_with_parser": lu["ids"] == nu["ids"] if nu["ids"] else None}
                if bucket in ("NO-UNITS", "ABOVE-COMMUNE", "NO-TEXT") and lu["ids"]:
                    bucket = lb
                    detail["method"] = (detail["method"] or "") + "+llm"
        # containment of a child drawn from its own units
        parent = rec_s.get("parent_slug")
        parent_src = (aocs.get(parent) or {}).get("geom_source") or "" if parent else ""
        child_src = rec_s.get("geom_source") or ""
        if (parent and parent in geoms and not child_src.startswith(("parent-appellation", "sibling-dgc"))
                and parent_src not in PARTIAL_PARENT_SOURCES
                and source_family(child_src) == source_family(parent_src) and source_family(child_src) != "approx"):
            pg = geoms[parent]
            try:
                outside_area = geom.difference(pg).area
            except Exception:  # noqa: BLE001
                outside_area = geom.buffer(0).difference(pg.buffer(0)).area
            outside = outside_area / geom.area if geom.area else 0.0
            detail["outside_parent_share"] = round(outside, 4)
            detail["outside_parent_km2"] = round(outside_area / 1e6, 3)
            if outside > 0.05 and outside_area >= CONTAINMENT_FLOOR_M2:
                detail["child_outside_parent"] = True
                if bucket in ("OK", "NO-UNITS", "ABOVE-COMMUNE", "NO-TEXT"):
                    bucket = "SUSPECT"
        bucket = curated_area_bucket(bucket, rec_s.get("geom_source") or "", detail)
        if bucket == "SUSPECT" and slug in overrides:
            ov = overrides[slug]
            if set(ov.get("missing") or []) >= set(detail.get("missing") or []) and set(ov.get("extra") or []) >= set(detail.get("extra") or []):
                bucket = "REVIEWED"
                detail["override"] = ov.get("reason")
            else:
                detail["override_stale"] = "the override pins fewer units than the audit finds now — re-verify"
        # readable names
        detail["missing_names"] = [layer.names[layer.ids.index(i)] for i in detail.get("missing", [])[:12]] if detail.get("missing") else []
        detail["extra_names"] = [layer.names[layer.ids.index(i)] for i in detail.get("extra", [])[:12]] if detail.get("extra") else []
        row.update(bucket=bucket, detail=detail)
        rows.append(row)
        if bucket == "SUSPECT":
            log(f"SUSPECT {slug:40} {cc} {rec_s.get('geom_source'):28} named={detail['named']} missing={len(detail['missing'])} extra={len(detail['extra'])} part={len(detail['part'])}"
                + (" child-outside-parent" if detail.get("child_outside_parent") else ""))

    buckets = Counter(r["bucket"] for r in rows)
    by_cc: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_cc[r["country"]][r["bucket"]] += 1
    summary = {"records": len(rows), "buckets": dict(buckets), "by_country": {c: dict(v) for c, v in sorted(by_cc.items())},
               "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "llm": bool(args.llm)}
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = Path(args.json) if args.json else REPORT_DIR / f"geometry-text-{stamp}.json"
    jp.write_text(json.dumps({"summary": summary, "records": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = [f"# validate-geometry (text vs polygon) — {stamp}", "", f"Records: {len(rows)} · buckets {dict(buckets)}", "",
          "| slug | country | geom_source | bucket | named | drawn whole / part | missing | extra | note |",
          "|---|---|---|---|---:|---|---|---|---|"]
    cell = lambda s: str(s or "").replace("|", "\\|")  # noqa: E731
    for r in sorted(rows, key=lambda r: ({"SUSPECT": 0, "REVIEWED": 1}.get(r["bucket"], 2), r["country"], r["slug"])):
        if r["bucket"] not in ("SUSPECT", "REVIEWED"):
            continue
        d = r["detail"]
        note = []
        if d.get("child_outside_parent"):
            note.append(f"{d['outside_parent_share'] * 100:.0f} % outside parent {r['parent_slug']}")
        if d.get("override"):
            note.append(f"reviewed: {d['override']}")
        if d.get("unresolved"):
            note.append(f"unresolved names: {', '.join(d['unresolved'][:5])}")
        if d.get("llm"):
            note.append(f"LLM read: {d['llm']['bucket']} ({d['llm']['named']} named)")
        md.append(f"| `{r['slug']}` | {r['country']} | {r['geom_source']} | **{r['bucket']}** | {d.get('named', 0)} | {d.get('drawn_whole', 0)} / {d.get('drawn_part', 0)} | "
                  f"{cell(', '.join(d.get('missing_names') or []))} | {cell(', '.join(d.get('extra_names') or []))} | {cell('; '.join(note))} |")
    md += ["", "## Per country", "", "| country | " + " | ".join(sorted(buckets)) + " |", "|---|" + "---|" * len(buckets)]
    for c, v in sorted(by_cc.items()):
        md.append(f"| {c} | " + " | ".join(str(v.get(b, 0)) for b in sorted(buckets)) + " |")
    mp = Path(args.md) if args.md else jp.with_suffix(".md")
    mp.write_text("\n".join(md) + "\n", encoding="utf-8")
    log(f"report → {jp}\nmarkdown → {mp}")
    if args.strict and buckets.get("SUSPECT"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
