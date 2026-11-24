"""Baden-Württemberg Gemarkungen — the unit Baden and Württemberg are delimited in.

The EU single document of Württemberg (section 6) and the BLE
Produktspezifikationen of Baden and Württemberg (§ 4 "Abgrenzung des
Gebiets") list "die Rebflächen folgender Gemeinden (Gemarkungen) und deren
Ortsteile" as `Name (number)` — "Oberstenfeld (920), Gronau (921)". The
number is the Gemarkungsnummer of the Baden-Württemberg land register, which
the state survey (LGL) publishes with its boundaries as `gemarkung_id` of the
ALKIS layer `nora:v_al_gemarkung` (dl-de/by-2-0). Bétard 2022 drew both
regions as whole Landkreise — Württemberg with all of the Rhein-Neckar-Kreis
and without Leonberg, Ravensburg or Oberderdingen (visitor flag, 2026-11-16)
— so the listed Gemarkungen are drawn instead.

Three pieces, no geometry decided here beyond the union:

  parse_area(text)        the numbered units of a delimitation text, with the
                          Bereich a block is headed by, and the Bavarian
                          units Württemberg names without a number;
  fetch_layer(dest)       the whole LGL layer, paged from the WFS, written as
                          one GeoPackage (stage 00);
  GemarkungLayer(path)    geometry by number, read on demand.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

WFS_URL = "https://owsproxy.lgl-bw.de/owsproxy/wfs/WFS_LGL-BW_ALKIS_VGr_KatGr_E"
WFS_LAYER = "nora:v_al_gemarkung"
LICENCE = "Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)"
LICENCE_URL = "https://www.govdata.de/dl-de/by-2-0"
PUBLISHER_URL = "https://www.lgl-bw.de"
LAYER_CRS = "EPSG:25832"

# A unit is drawn only when its printed name agrees with the layer's name for
# that number (the Gemarkung's, or its Gemeinde's — Baden prints the Gemeinde
# beside each Gemarkung number): a mistyped number would otherwise draw a
# district at the other end of the state.
NAME_MATCH_MIN = 0.8

_NUMBERED = re.compile(r"\((\d{2,5})\)")
_BEREICH = re.compile(r"im\s+Bereich\s+(.+?)\s+die\s+Rebfl[äa]chen", re.DOTALL)
_BAYERN_HEAD = re.compile(r"Bundesland\s+Bayern\s*:?", re.IGNORECASE)
_BW_HEAD = re.compile(r"Bundesland\s+Baden-W[üu]rttemberg\s*:?", re.IGNORECASE)
_LIST_INTRO = re.compile(r"Gemeinden\s*\(Gemarkungen\)\s*und\s+deren\s+Ortsteilen?\s*:?",
                         re.IGNORECASE)
# "4. Abgrenzung des Gebiets" (Baden) / "4 Abgrenzung des Gebietes"
# (Württemberg), to the next top-level heading.
_SECTION_4 = re.compile(
    r"^\s*4\.?\s+Abgrenzung\s+des\s+Gebiete?s\s*$(.*?)(?=^\s*5\.?\s+[A-ZÄÖÜ])",
    re.MULTILINE | re.DOTALL,
)
# "Die Gemeinden Nonnenhorn, Wasserburg und Bodholz und die Gemarkungen
# Hoyren und Aeschach der Großen Kreisstadt Lindau."
_BY_GEMEINDEN = re.compile(r"Die\s+Gemeinden\s+(.+?)\s+und\s+die\s+Gemarkungen\s+(.+?)\s+der\s+"
                           r"(?:Gro(?:ß|ss)en\s+Kreisstadt|Stadt|Gemeinde)\s+([A-ZÄÖÜ][\wäöüß-]+)",
                           re.DOTALL)
_PAGE_FURNITURE = re.compile(r"^\s*(?:Seite\s+\d+(?:\s+von\s+\d+)?|\d+|Stand:.*)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Unit:
    number: int
    name: str            # as printed before the number
    bereich: str = ""


@dataclass
class Area:
    units: list[Unit] = field(default_factory=list)
    # Bavarian units, named without a number: whole Gemeinden, and Gemarkungen
    # of a town (drawn as the town, disclosed as partial).
    by_gemeinden: list[str] = field(default_factory=list)
    by_partial: list[tuple[str, list[str]]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.units)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ,;.:")


def _strip_furniture(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _PAGE_FURNITURE.match(line))


def section_4(spec_text: str) -> str:
    """§ 4 "Abgrenzung des Gebiets" of a BLE Produktspezifikation
    (`pdftotext -layout`), page furniture dropped; '' when the specification
    has none in that form."""
    m = _SECTION_4.search(spec_text or "")
    return _strip_furniture(m.group(1)) if m else ""


def _numbered_units(block: str, bereich: str) -> list[Unit]:
    out: list[Unit] = []
    pos = 0
    for m in _NUMBERED.finditer(block):
        name = _clean(block[pos:m.start()])
        pos = m.end()
        if name:
            out.append(Unit(int(m.group(1)), name, bereich))
    return out


def parse_area(text: str) -> Area:
    """The numbered Gemarkungen of a delimitation text and its Bavarian
    units. Reads every "Gemeinden (Gemarkungen) und deren Ortsteile:" list;
    a list under "Bundesland Bayern" carries no number and is read as
    prose."""
    text = text or ""
    area = Area()
    by = _BAYERN_HEAD.search(text)
    bw_text, by_text = (text[:by.start()], text[by.end():]) if by else (text, "")
    # Each list runs from its intro to the next intro (Baden: one per Bereich)
    # or the closing sentence.
    intros = list(_LIST_INTRO.finditer(bw_text))
    for i, m in enumerate(intros):
        end = intros[i + 1].start() if i + 1 < len(intros) else len(bw_text)
        block = bw_text[m.end():end]
        block = re.split(r"Die\s+genaue\s+Abgrenzung|Zur\s+gesch[üu]tzten\s+Ursprungsbezeichnung",
                         block)[0]
        head = bw_text[intros[i - 1].end() if i else 0:m.start()]
        bm = list(_BEREICH.finditer(head))
        bereich = _clean(bm[-1].group(1)) if bm else ""
        area.units += _numbered_units(block, bereich)
    seen: set[int] = set()
    area.units = [u for u in area.units if not (u.number in seen or seen.add(u.number))]
    m = _BY_GEMEINDEN.search(by_text)
    if m:
        area.by_gemeinden = [_clean(n) for n in re.split(r",|\bund\b", m.group(1)) if _clean(n)]
        marks = [_clean(n) for n in re.split(r",|\bund\b", m.group(2)) if _clean(n)]
        area.by_partial = [(_clean(m.group(3)), marks)]
    return area


def norm_name(s: str) -> str:
    """Name key: "Heidelberg, Stadt" / "Konstanz, Universitätsstadt" lose the
    municipal title, ß → ss, diacritics and punctuation folded."""
    s = re.sub(r",\s*(?:Stadt|Universit[äa]tsstadt|Landeshauptstadt|Gro(?:ß|ss)e Kreisstadt)\b", "",
               s or "")
    s = s.replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def name_agreement(printed: str, *layer_names: str) -> float:
    """1.0 when the printed name is the layer's (Gemarkung or Gemeinde), or
    its head ("Kressbronn" / "Kreßbronn am Bodensee", "Wimpfen" / "Bad
    Wimpfen"); else the best similarity ratio."""
    from rapidfuzz import fuzz

    p = norm_name(printed)
    best = 0.0
    for raw in layer_names:
        n = norm_name(raw or "")
        if not n or not p:
            continue
        if p == n or n.startswith(p + " ") or n.endswith(" " + p) or p.startswith(n + " "):
            return 1.0
        # "Hirschberg an der Bergstraße" / the layer's "Hirschberg a.d.B."
        if len(p.split()[0]) >= 5 and p.split()[0] == n.split()[0]:
            best = max(best, 0.9)
        best = max(best, fuzz.ratio(p, n) / 100.0)
    return best


# ────────────────────────────────────────────────── pins and sources ──

PINS_PATH = Path(__file__).with_name("gemarkung_pins.json")

# A delimitation is read from the record's own EU single document when that
# lists numbered Gemarkungen, else from § 4 of its BLE Produktspezifikation
# (the stage-02f sidecar's `area_text`).
MIN_UNITS = 10


def load_pins(path: Path = PINS_PATH) -> dict[str, dict[int, dict]]:
    """{file_number: {printed number: {number, printed, reason, source,
    verified}}} — a number the documents print that the land register does
    not carry, bound to the Gemarkung it names."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {fn: {int(k): v for k, v in pins.items()}
            for fn, pins in data.items() if not fn.startswith("__")}


def load_areas(extracted_dir: Path, sidecar_dir: Path) -> dict[str, dict]:
    """{file_number: {area, source_kind, slug}} for the DE parent records
    whose delimitation lists numbered Gemarkungen."""
    out: dict[str, dict] = {}
    for path in sorted(Path(extracted_dir).glob("*.json")):
        if path.name.startswith("_"):
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        fn = rec.get("file_number") or ""
        if not fn or rec.get("is_sub_denomination"):
            continue
        area = parse_area((rec.get("section_roles") or {}).get("geo_area") or "")
        kind = "eu-single-document"
        if len(area.units) < MIN_UNITS:
            side = Path(sidecar_dir) / f"{rec.get('slug')}.json"
            if not side.exists():
                continue
            area = parse_area(json.loads(side.read_text(encoding="utf-8")).get("area_text") or "")
            kind = "ble-produktspezifikation"
        if len(area.units) >= MIN_UNITS:
            out[fn] = {"area": area, "source_kind": kind, "slug": rec.get("slug") or ""}
    return out


# ───────────────────────────────────────────────────────── fetch ──

def fetch_layer(dest: Path, manifest_path: Path, *, page: int = 400, pause: float = 0.5,
                user_agent: str = "openwinemap-curation/1.0 (+https://www.openwinemap.com)",
                log=print) -> dict:
    """Download the whole Gemarkung layer from the LGL WFS (GeoJSON pages,
    EPSG:25832) into one GeoPackage. The service is refreshed daily, so the
    file is not sha-pinned: the manifest records when it was read and how
    many Gemarkungen it held."""
    import geopandas as gpd
    import pandas as pd
    import requests

    frames = []
    start, total = 0, None
    while total is None or start < total:
        params = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": WFS_LAYER, "OUTPUTFORMAT": "application/json",
            "COUNT": str(page), "STARTINDEX": str(start), "SORTBY": "gemarkung_id",
        }
        for attempt in range(4):
            try:
                r = requests.get(WFS_URL, params=params, timeout=180,
                                 headers={"User-Agent": user_agent})
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as exc:
                if attempt == 3:
                    raise
                log(f"[lgl] retry {attempt + 1} at {start}: {exc}")
                time.sleep(5 * (attempt + 1))
        total = int(data.get("numberMatched") or data.get("totalFeatures") or 0)
        feats = data.get("features") or []
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs=LAYER_CRS))
        start += len(feats)
        log(f"[lgl] {start}/{total} Gemarkungen")
        time.sleep(pause)
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=LAYER_CRS)
    gdf = gdf.drop_duplicates(subset="gemarkung_id")
    if total and len(gdf) != total:
        raise RuntimeError(f"LGL layer: {len(gdf)} Gemarkungen read, service reports {total}")
    keep = ["gemarkung_id", "gemarkung_name", "gemeinde_id", "gemeinde_name",
            "kreis_id", "kreis_name", "geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.gpkg")
    gdf.to_file(tmp, driver="GPKG", layer="gemarkungen")
    tmp.replace(dest)
    fetched = datetime.now(timezone.utc)
    manifest = {
        "source": "LGL Baden-Württemberg — ALKIS Verwaltungs- und Katasterbezirksgrenzen, "
                  "Gemarkungen",
        "service": WFS_URL,
        "layer": WFS_LAYER,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "attribution": f"LGL-BW ({fetched.year}) Datenlizenz Deutschland – Namensnennung – "
                       "Version 2.0, www.lgl-bw.de",
        "crs": LAYER_CRS,
        "n_gemarkungen": int(len(gdf)),
        "filename": dest.name,
        "bytes": dest.stat().st_size,
        "fetched_at": fetched.isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return manifest


# ───────────────────────────────────────────────────────── layer ──

class GemarkungLayer:
    """Gemarkung geometry by number, read on demand from the GeoPackage."""

    def __init__(self, path: Path, target_crs: str = "EPSG:4326") -> None:
        self.path = path
        self.target_crs = target_crs
        manifest = path.parent / "manifest.json"
        self.manifest: dict = (json.loads(manifest.read_text(encoding="utf-8"))
                               if manifest.exists() else {})

    @property
    def available(self) -> bool:
        return self.path.exists()

    def rows(self, numbers) -> dict[int, dict]:
        """{number: {name, gemeinde, gemeinde_id, kreis, geometry}} for the
        numbers the layer carries."""
        import geopandas as gpd

        wanted = sorted({int(n) for n in numbers})
        if not wanted or not self.available:
            return {}
        gdf = gpd.read_file(
            self.path, layer="gemarkungen",
            where=f"gemarkung_id IN ({', '.join(str(n) for n in wanted)})",
        )
        if gdf.crs is None or gdf.crs.to_string() != self.target_crs:
            gdf = gdf.to_crs(self.target_crs)
        out: dict[int, dict] = {}
        for _, row in gdf.iterrows():
            if row.geometry is None or row.geometry.is_empty:
                continue
            out[int(row["gemarkung_id"])] = {
                "name": str(row.get("gemarkung_name") or ""),
                "gemeinde": str(row.get("gemeinde_name") or ""),
                "gemeinde_id": str(row.get("gemeinde_id") or ""),
                "kreis": str(row.get("kreis_name") or ""),
                "geometry": row.geometry,
            }
        return out
