"""Gemarkungen outside Baden-Württemberg — the Länder's open cadastral districts.

Several German delimitations name Gemarkungen (cadastral districts), not
Gemeinden: Mittelrhein's part in Nordrhein-Westfalen ("der Stadt Bonn mit der
Gemarkung Kessenich"), Saale-Unstrut throughout (Sachsen-Anhalt, Thüringen,
Brandenburg), and the Rheinland-Pfalz regions, which print each Gemarkung's
land-register number ("Bacharach (3503)"). Bétard 2022 drew them as whole
municipalities — Bonn's 141 km² for Kessenich. Every Land concerned
publishes its Gemarkung boundaries as open data (read 2026-11-24):

  nw  Geobasis NRW, ALKIS vereinfacht `ave:KatasterBezirk`   dl-de/zero-2-0
  bb  LGB Brandenburg, the same layer                        dl-de/by-2-0
  st  LVermGeo Sachsen-Anhalt, "Gemarkung_Flur_OpenData"     dl-de/by-2-0
  th  TLBG Thüringen, the layer in schema version 1.0        CC BY 4.0
  rp  LVermGeo Rheinland-Pfalz, `vermkv:gemarkungen_rlp`     dl-de/by-2-0

(Baden-Württemberg's layer has its own module, `gemarkung.py`.) Stage 00
fetches the Gemarkungen of the Kreise the corpus names (`SERVICES[…]["kreise"]`;
a Land whose layer cannot be filtered by Kreis is read whole) into
`raw/de/katasterbezirke/<land>.gpkg`, one schema for all:

  land        the two-letter code above
  schluessel  the Land's Gemarkung key, as published
  number      its last four digits — the number a Rhineland text prints
  name        the Gemarkung
  gemeinde    the Gemeinde it lies in
  ags         that Gemeinde's 8-digit key (the layer's, else the GISCO commune
              the Gemarkung's inner point falls in)

The services change daily, so nothing is sha-pinned: the manifest records
when each layer was read and how many Gemarkungen it held.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

STORE_CRS = "EPSG:25832"
AVE_2 = "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/2.0"
AVE_1 = "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/1.0"
DL_BY = "Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)"
DL_BY_URL = "https://www.govdata.de/dl-de/by-2-0"

# `kreise`: the 5-digit Kreis keys read (None = the whole Land).
SERVICES: dict[str, dict] = {
    "nw": {
        "land": "Nordrhein-Westfalen", "ags2": "05", "kind": "ave", "namespace": AVE_2,
        "url": "https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht",
        "kreise": ["05314", "05382"],  # Bonn, Rhein-Sieg-Kreis (Mittelrhein)
        "publisher": "Geobasis NRW", "publisher_url": "https://www.bezreg-koeln.nrw.de/geobasis-nrw",
        "licence": "Datenlizenz Deutschland – Zero – Version 2.0 (dl-de/zero-2-0)",
        "licence_url": "https://www.govdata.de/dl-de/zero-2-0",
        "credit": "Geobasis NRW ({year})", "licence_short": "dl-de/zero-2-0",
    },
    "bb": {
        "land": "Brandenburg", "ags2": "12", "kind": "ave", "namespace": AVE_2,
        "url": "https://isk.geobasis-bb.de/ows/alkis_vereinf_wfs",
        "kreise": ["12069"],  # Potsdam-Mittelmark (Saale-Unstrut's Werder)
        "publisher": "LGB Brandenburg", "publisher_url": "https://geobasis-bb.de",
        "licence": DL_BY, "licence_url": DL_BY_URL,
        "credit": "© GeoBasis-DE/LGB ({year})", "licence_short": "dl-de/by-2-0",
    },
    "st": {
        "land": "Sachsen-Anhalt", "ags2": "15", "kind": "ave", "namespace": AVE_2,
        "url": ("https://www.geodatenportal.sachsen-anhalt.de/wss/service/"
                "ST_LVermGeo_ALKIS_WFS_Gemarkung_Flur_OpenData/guest"),
        # Burgenlandkreis, Harz, Mansfeld-Südharz, Saalekreis, Salzlandkreis
        "kreise": ["15084", "15085", "15087", "15088", "15089"],
        "publisher": "LVermGeo Sachsen-Anhalt",
        "publisher_url": "https://www.lvermgeo.sachsen-anhalt.de",
        "licence": DL_BY, "licence_url": DL_BY_URL,
        "credit": "© GeoBasis-DE / LVermGeo ST ({year})", "licence_short": "dl-de/by-2-0",
    },
    "th": {
        "land": "Thüringen", "ags2": "16", "kind": "ave", "namespace": AVE_1,
        "url": "https://www.geoproxy.geoportal-th.de/geoproxy/services/adv_alkis_wfs",
        "kreise": None,  # schema 1.0 carries no Gemeinde key to filter on
        "publisher": "TLBG Thüringen", "publisher_url": "https://www.geoportal-th.de",
        "licence": "Creative Commons Namensnennung 4.0 (CC BY 4.0)",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/deed.de",
        "credit": "© GDI-Th ({year})", "licence_short": "CC BY 4.0",
    },
    "rp": {
        "land": "Rheinland-Pfalz", "ags2": "07", "kind": "rlp",
        "url": ("https://www.geoportal.rlp.de/spatial-objects/314/collections/"
                "vermkv:gemarkungen_rlp/items"),
        "kreise": None,
        "publisher": "LVermGeo Rheinland-Pfalz", "publisher_url": "https://lvermgeo.rlp.de",
        "licence": DL_BY, "licence_url": DL_BY_URL,
        "credit": "© GeoBasis-DE / LVermGeoRP ({year})", "licence_short": "dl-de/by-2-0",
    },
}

USER_AGENT = "openwinemap-curation/1.0 (+https://www.openwinemap.com)"
COLUMNS = ["land", "schluessel", "number", "name", "gemeinde", "ags", "geometry"]


def norm_name(s: str) -> str:
    """Name key: ß → ss, diacritics and punctuation folded, a bracketed gloss
    kept as words ("Werder (Havel)" = "werder havel")."""
    s = (s or "").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ───────────────────────────────────────────────────────── fetch ──

def _get(url: str, params: dict, *, timeout: int = 240, log=print):
    import requests

    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == 3:
                raise
            log(f"[katasterbezirk] retry {attempt + 1}: {exc}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _ave_filter(namespace: str, kreis: str | None) -> str:
    art = ("<fes:PropertyIsEqualTo><fes:ValueReference>ave:art</fes:ValueReference>"
           "<fes:Literal>Gemarkung</fes:Literal></fes:PropertyIsEqualTo>")
    if kreis is None:
        body = art
    else:
        body = ("<fes:And>" + art
                + '<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="\\">'
                  "<fes:ValueReference>ave:gmdschl</fes:ValueReference>"
                  f"<fes:Literal>{kreis}*</fes:Literal></fes:PropertyIsLike></fes:And>")
    return (f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:ave="{namespace}">'
            f"{body}</fes:Filter>")


def _read_gml(content: bytes):
    import geopandas as gpd

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "page.gml"
        path.write_bytes(content)
        return gpd.read_file(path)


def _fetch_ave(cfg: dict, log) -> "object":
    """The Gemarkungen (`art` = Gemarkung, never the Fluren) of an AdV
    "ALKIS vereinfacht" service: one request per Kreis, or the whole Land in
    pages where the layer carries no Gemeinde key."""
    import pandas as pd

    base = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": "ave:KatasterBezirk",
            "NAMESPACES": f"xmlns(ave,{cfg['namespace']})"}
    frames = []
    if cfg["kreise"]:
        for kreis in cfg["kreise"]:
            r = _get(cfg["url"], {**base, "FILTER": _ave_filter(cfg["namespace"], kreis)}, log=log)
            gdf = _read_gml(r.content)
            log(f"[katasterbezirk] {cfg['land']} {kreis}: {len(gdf)} Gemarkungen")
            frames.append(gdf)
            time.sleep(1.0)
    else:
        start, page = 0, 500
        while True:
            r = _get(cfg["url"], {**base, "FILTER": _ave_filter(cfg["namespace"], None),
                                  "COUNT": str(page), "STARTINDEX": str(start)}, log=log)
            gdf = _read_gml(r.content)
            if len(gdf) == 0:
                break
            frames.append(gdf)
            start += len(gdf)
            log(f"[katasterbezirk] {cfg['land']}: {start} Gemarkungen")
            if len(gdf) < page:
                break
            time.sleep(1.0)
    if not frames:
        raise RuntimeError(f"{cfg['land']}: the service returned no Gemarkung")
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gdf[gdf["art"] == "Gemarkung"].drop_duplicates(subset="schluessel")
    out = gdf[["name", "schluessel", "gemeinde", "geometry"]].copy()
    out["ags"] = gdf["gmdschl"].astype(str) if "gmdschl" in gdf.columns else ""
    return out.set_crs(frames[0].crs, allow_override=True)


def _fetch_rlp(cfg: dict, log) -> "object":
    """Rheinland-Pfalz serves its Gemarkungen as an OGC API Features
    collection (GeoJSON, WGS 84): `gmkgnr` is 07 + the four-digit number the
    specifications print, `ags` the Gemeinde key without its leading zero."""
    import geopandas as gpd
    import pandas as pd

    frames, offset, total, page = [], 0, None, 500
    while total is None or offset < total:
        r = _get(cfg["url"], {"f": "json", "limit": str(page), "offset": str(offset)}, log=log)
        data = r.json()
        total = int(data.get("numberMatched") or 0)
        feats = data.get("features") or []
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
        offset += len(feats)
        log(f"[katasterbezirk] {cfg['land']}: {offset}/{total} Gemarkungen")
        time.sleep(1.0)
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    gdf = gdf.drop_duplicates(subset="gmkgnr")
    if total and len(gdf) != total:
        raise RuntimeError(f"Rheinland-Pfalz: {len(gdf)} Gemarkungen read, service reports {total}")
    out = gdf[["geometry"]].copy()
    out["name"] = gdf["gemarkung"].astype(str)
    out["schluessel"] = gdf["gmkgnr"].astype(int).map(lambda n: f"{n:06d}")
    out["gemeinde"] = gdf["gemeinde"].astype(str)
    out["ags"] = gdf["ags"].astype(int).map(lambda n: f"{n:08d}")
    return out


def _fill_ags(gdf, lau_zip: Path, ags2: str):
    """The Gemeinde key of a layer that publishes none: the GISCO commune
    each Gemarkung's inner point falls in."""
    import geopandas as gpd

    if not (gdf["ags"] == "").any() or not lau_zip.exists():
        return gdf
    lau = gpd.read_file(f"zip://{lau_zip}", where="CNTR_CODE = 'DE'")
    lau = lau[lau["GISCO_ID"].astype(str).str[3:5] == ags2][["GISCO_ID", "geometry"]]
    pts = gpd.GeoDataFrame({"i": range(len(gdf))},
                           geometry=gdf.geometry.representative_point().values, crs=gdf.crs)
    hit = gpd.sjoin(pts.to_crs(lau.crs), lau, how="left", predicate="within")
    hit = hit.drop_duplicates(subset="i").set_index("i")["GISCO_ID"]
    gdf = gdf.reset_index(drop=True)
    gdf["ags"] = [str(hit.get(i) or "")[3:] if gdf.at[i, "ags"] == "" else gdf.at[i, "ags"]
                  for i in range(len(gdf))]
    return gdf


def fetch_land(code: str, dest_dir: Path, lau_zip: Path, *, log=print) -> dict:
    """Read one Land's Gemarkungen into `<dest_dir>/<code>.gpkg` and record
    the read in `<dest_dir>/manifest.json`."""
    cfg = SERVICES[code]
    gdf = _fetch_rlp(cfg, log) if cfg["kind"] == "rlp" else _fetch_ave(cfg, log)
    gdf = gdf.to_crs(STORE_CRS)
    gdf = _fill_ags(gdf, lau_zip, cfg["ags2"])
    gdf["land"] = code
    gdf["schluessel"] = gdf["schluessel"].astype(str)
    gdf["number"] = gdf["schluessel"].str[-4:].astype(int)
    gdf = gdf[COLUMNS]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{code}.gpkg"
    tmp = dest.with_suffix(".tmp.gpkg")
    gdf.to_file(tmp, driver="GPKG", layer="gemarkungen")
    tmp.replace(dest)
    fetched = datetime.now(timezone.utc)
    entry = {
        "land": cfg["land"],
        "source": f"{cfg['publisher']} — ALKIS Katasterbezirke, Gemarkungen",
        "service": cfg["url"],
        "kreise": cfg["kreise"],
        "licence": cfg["licence"],
        "licence_url": cfg["licence_url"],
        "publisher": cfg["publisher"],
        "publisher_url": cfg["publisher_url"],
        "credit": cfg["credit"].format(year=fetched.year),
        "licence_short": cfg["licence_short"],
        "attribution": f"{cfg['credit'].format(year=fetched.year)}, {cfg['licence_short']}",
        "crs": STORE_CRS,
        "n_gemarkungen": int(len(gdf)),
        "filename": dest.name,
        "bytes": dest.stat().st_size,
        "fetched_at": fetched.isoformat(timespec="seconds"),
    }
    manifest_path = dest_dir / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})
    manifest[code] = entry
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return entry


# ───────────────────────────────────────────────────────── layer ──

class Gemarkungen:
    """The Gemarkungen of every Land on disk, with their attributes in memory
    and the geometry in `target_crs`. Lookups return row dicts {land,
    schluessel, number, name, gemeinde, ags, geometry}."""

    def __init__(self, directory: Path, target_crs: str = "EPSG:4326") -> None:
        import geopandas as gpd

        self.directory = Path(directory)
        manifest = self.directory / "manifest.json"
        self.manifest: dict = (json.loads(manifest.read_text(encoding="utf-8"))
                               if manifest.exists() else {})
        self.rows: list[dict] = []
        self._by_number: dict[tuple[str, int], dict] = {}
        self._by_name: dict[tuple[str, str], list[dict]] = {}
        for code in SERVICES:
            path = self.directory / f"{code}.gpkg"
            if not path.exists():
                continue
            gdf = gpd.read_file(path, layer="gemarkungen")
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for rec in gdf.to_dict("records"):
                if rec["geometry"] is None or rec["geometry"].is_empty:
                    continue
                row = {k: rec[k] for k in COLUMNS}
                row["number"] = int(row["number"])
                row["ags"] = str(row["ags"] or "")
                self.rows.append(row)
                self._by_number[(code, row["number"])] = row
                self._by_name.setdefault((code, norm_name(row["name"])), []).append(row)

    @property
    def lands(self) -> set[str]:
        return {r["land"] for r in self.rows}

    def by_number(self, land: str, number: int) -> dict | None:
        return self._by_number.get((land, int(number)))

    def by_name(self, land: str, name: str, *, kreis: str = "", gemeinde: str = "") -> list[dict]:
        """The Gemarkungen of a Land called `name`, inside a Kreis (its
        5-digit key) and / or a Gemeinde (by name) when given."""
        hits = self._by_name.get((land, norm_name(name)), [])
        if kreis:
            hits = [r for r in hits if r["ags"].startswith(kreis)]
        if gemeinde:
            key = norm_name(gemeinde)
            hits = [r for r in hits
                    if norm_name(r["gemeinde"]) == key or norm_name(r["gemeinde"]).startswith(key + " ")]
        return hits

    def of_gemeinde(self, land: str, gemeinde: str) -> list[dict]:
        key = norm_name(gemeinde)
        return [r for r in self.rows if r["land"] == land
                and (norm_name(r["gemeinde"]) == key or norm_name(r["gemeinde"]).startswith(key + " "))]

    def attribution(self, lands) -> list[str]:
        """The credit line of each Land's layer, in the order given."""
        return [self.manifest[c]["attribution"] for c in lands if c in self.manifest]
