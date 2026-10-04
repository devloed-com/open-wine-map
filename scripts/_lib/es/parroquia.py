"""Galician parroquias (civil parishes) — the sub-municipal unit the
Galician pliegos delimit with.

Several Galician appellations name only *some* parishes of a municipio
("las parroquias de Iria Flavia y Padrón, del término municipal de
Padrón" — Barbanza e Iria). Parroquias are not administrative units in
Spanish law, so neither GISCO LAU nor SIGPAC carries them; the one public
polygon layer is the IET's **Mapa de Parroquias de Galicia**
(Instituto de Estudos do Territorio, Xunta de Galicia — 3,785 polygons
over the 313 concellos, EPSG:25829), fetched by `scripts/es/00_fetch_data.py`
into `raw/es/xunta/parroquias/Parroquias.zip`. The boundaries are the
IET's cartographic parroquias, not legally official limits.

Join key: `CODIGOINE` (5-character INE municipio code) = GISCO LAU
`ES_<CODIGOINE>`, so a pliego's municipio name resolves to an INE through
`ESPolygonIndex` and the parish is then looked up inside that municipio
only. `PARROQUIA` is written "Name (patron saint)" — the parenthetical is
dropped before matching; `CONCELLO` carries the Galician article ("O Porto
do Son").

Matching is exact after normalisation (the same fold as
`_lib/es/geometry.py`: diacritics, leading / trailing articles, the
"(saint)" suffix, hyphen = space), plus a spaceless key so a PDF
line-break hyphen ("Tama-guelos") still reaches "Tamaguelos", and — only
when the pliego itself writes a San / Santa / Santo / Santiago prefix — the
prefix-less form. A parish the data cannot match is left out and reported,
never guessed; the curator pins the pliego's spelling to the dataset's in
`parroquia_overrides.json` (see `load_overrides`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from _lib.es.geometry import _normalise_commune_name

ROOT = Path(__file__).resolve().parents[3]

PARROQUIAS_URL = "https://visorgis.cmati.xunta.es/cdix/descargas/visor_basico/Parroquias.zip"
PARROQUIAS_DIR = ROOT / "raw" / "es" / "xunta" / "parroquias"
PARROQUIAS_ZIP = PARROQUIAS_DIR / "Parroquias.zip"
PARROQUIAS_MANIFEST = PARROQUIAS_DIR / "manifest.json"
PARROQUIAS_SHP = "Parroquias.shp"
PARROQUIAS_DATASET = "Mapa de Parroquias de Galicia — layer «Parroquias»"
PARROQUIAS_PUBLISHER = (
    "Xunta de Galicia – Instituto de Estudos do Territorio (IET), Consellería de Medio "
    "Ambiente, Territorio e Infraestruturas, via Información Xeográfica de Galicia "
    "(mapas.xunta.gal) / IDEG (ideg.xunta.gal); abertos.xunta.gal dataset 0343 "
    "«Límites administrativos de Galicia»"
)
PARROQUIAS_DATASET_URL = (
    "https://abertos.xunta.gal/catalogo/territorio-vivienda-transporte/-/dataset/0343/"
    "limites-administrativos-galicia"
)
PARROQUIAS_LICENCE_URL = "https://mapas.xunta.gal/es/aviso-legal"
PARROQUIAS_ATTRIBUTION = (
    "© Xunta de Galicia – Instituto de Estudos do Territorio (IET), Mapa de Parroquias"
)
PARROQUIAS_LICENCE_SHORT = "CC BY 4.0"
# The governing licence is the publisher's aviso legal (Decreto 14/2017),
# quoted verbatim, the way the MAPA layer cites its IDE metadata.
PARROQUIAS_LICENCE = (
    "Open. Publisher's legal notice (https://mapas.xunta.gal/es/aviso-legal): «La "
    "información disponible en este Portal, salvo indicación expresa en contrario, es "
    "susceptible de reutilización, quedando autorizada su reproducción total o parcial, "
    "modificación, distribución y comunicación, para usos comerciales y no comerciales, "
    "con sujeción a las siguientes condiciones: El usuario queda obligado a citar la "
    "fuente de los documentos objecto de la reutilización.» For IET geodata: «En razón "
    "de ello, y de la política de datos determinada por la Xunta de Galicia, establecida "
    "en el Decreto 14/2017 y especificada en el Plan Galego de Cartografía e Información "
    "Xeográfica, el uso de la información de los productos y servicios de datos "
    "geográficos definidos en ella, así como sus derivados, conlleva la aceptación "
    "implícita por el usuario de las condiciones generales de dicha orden, concretada en "
    "una licencia de uso compatible con CC-BY 4.0 INT.»"
)
PARROQUIAS_LICENCE_CONFLICT = (
    "«Condicions de Uso.pdf» inside Parroquias.zip (file date 2015-06-18, predating "
    "Decreto 14/2017) says «A cesión da información xeográfica é exclusivamente para "
    "usos non comerciais … copyright Xunta de Galicia»; abertos.xunta.gal dataset 0343 "
    "lists the same service as «Creative Commons BY SA 4.0»; the ISO metadata says «No "
    "caso de publicación … deberá facerse referencia ao SITGA como o produtor dos "
    "datos.» The current aviso legal (Decreto 14/2017, CC-BY 4.0 compatible) is cited "
    "as the governing licence."
)


def parroquias_dataset(zip_path: Path = PARROQUIAS_ZIP) -> dict[str, str]:
    """Manifest fields naming the layer the zip holds, dated from its own
    `Parroquias.shp` entry. The URL is unversioned and the zip is
    republished in place (Parroquias.shp and Parroquias_linea.shp already
    carry different dates), so a date written as a constant would outlive
    the bytes it described."""
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        try:
            info = zf.getinfo(PARROQUIAS_SHP)
        except KeyError:
            return {"dataset": f"{PARROQUIAS_DATASET} (no {PARROQUIAS_SHP} in the zip)",
                    "dataset_date": ""}
    date = "{:04d}-{:02d}-{:02d}".format(*info.date_time[:3])
    return {"dataset": f"{PARROQUIAS_DATASET} (shapefile dated {date})", "dataset_date": date}


# The four Galician provinces (INE prefix) — the only municipios the layer
# can hold. A pliego municipio whose exact GISCO match lands elsewhere
# (Sada: A Coruña 15075 / Navarra 31212) is disambiguated by this set.
GALICIA_PROVINCES = frozenset({"15", "27", "32", "36"})

OVERRIDES_PATH = Path(__file__).with_name("parroquia_overrides.json")

_SAINT_PREFIX_RE = re.compile(r"^(?:san|santa|santo|santiago)\s+(?=\S)")


def normalise_parroquia_name(name: str) -> str:
    """The ES commune fold, applied to a parish name: "Iria Flavia (Santa
    María)" → "iria flavia", "A Rasela (Santa María)" → "rasela"."""
    return _normalise_commune_name(name)


def load_overrides(path: Path = OVERRIDES_PATH) -> dict:
    """Curator pins, keyed by record slug. Inside a slug entry a 5-digit
    INE key maps the pliego's spelling of a parish to the dataset's
    (`{"15001": {"Vilacoba": "Vilacova"}}`); the `_municipios` key maps a
    pliego municipio name to its INE when GISCO's name differs (a merged
    municipio: "Oza dos Ríos" → 15902 Oza-Cesuras). Other `_`-prefixed keys
    are notes. Missing file → no pins."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


class ESParroquiaIndex:
    """Polygons of the IET Mapa de Parroquias, indexed by (INE, normalised
    parish name). Lazy: the shapefile (~20 MB zipped) is read on first
    lookup, so a build without the download pays nothing."""

    def __init__(
        self,
        zip_path: Path = PARROQUIAS_ZIP,
        target_crs: str = "EPSG:4326",
        overrides_path: Path = OVERRIDES_PATH,
    ) -> None:
        self.zip_path = zip_path
        self.target_crs = target_crs
        self.overrides = load_overrides(overrides_path)
        self._loaded = False
        # ine → norm → [geoms]; a parish split into several rows unions.
        self._by_ine: dict[str, dict[str, list[BaseGeometry]]] = {}
        # ine → spaceless norm → norm (the hyphen-artefact key)
        self._nospace_by_ine: dict[str, dict[str, str]] = {}
        # ine → norm → dataset name without the "(saint)" suffix
        self._display_by_ine: dict[str, dict[str, str]] = {}
        self._ine_by_concello: dict[str, str] = {}
        self._n_parroquias = 0

    # ------------------------------------------------------------ loading

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.zip_path.exists():
            return
        import geopandas as gpd

        gdf = gpd.read_file(f"zip://{self.zip_path}!{PARROQUIAS_SHP}")
        if gdf.crs is None or gdf.crs.to_string() != self.target_crs:
            gdf = gdf.to_crs(self.target_crs)
        for _, row in gdf.iterrows():
            geom = row.geometry
            ine = str(row.get("CODIGOINE") or "").strip()
            name = str(row.get("PARROQUIA") or "").strip()
            if geom is None or geom.is_empty or len(ine) != 5 or not name:
                continue
            self._add(ine, name, str(row.get("CONCELLO") or ""), geom)

    def _add(self, ine: str, name: str, concello: str, geom: BaseGeometry) -> None:
        """Register one parish row. Public so tests can build a synthetic
        index without the shapefile."""
        self._loaded = True
        norm = normalise_parroquia_name(name)
        if not norm:
            return
        self._by_ine.setdefault(ine, {}).setdefault(norm, []).append(geom)
        self._nospace_by_ine.setdefault(ine, {}).setdefault(norm.replace(" ", ""), norm)
        self._display_by_ine.setdefault(ine, {}).setdefault(norm, _strip_saint_suffix(name))
        self._n_parroquias += 1
        if concello:
            self._ine_by_concello.setdefault(_normalise_commune_name(concello), ine)

    # ------------------------------------------------------------ queries

    @property
    def has_data(self) -> bool:
        self._ensure_loaded()
        return bool(self._by_ine)

    @property
    def n_parroquias(self) -> int:
        self._ensure_loaded()
        return self._n_parroquias

    @property
    def n_concellos(self) -> int:
        self._ensure_loaded()
        return len(self._by_ine)

    def has_concello(self, ine: str) -> bool:
        self._ensure_loaded()
        return ine in self._by_ine

    def ine_for_concello(self, name: str) -> str | None:
        """INE of a municipio by its Galician `CONCELLO` name (article
        folded). Second chance after the GISCO exact match — the same
        exact rule, on the layer's own spelling."""
        self._ensure_loaded()
        return self._ine_by_concello.get(_normalise_commune_name(name))

    def municipio_override(self, slug: str, name: str) -> str | None:
        """Curator-pinned INE for a pliego municipio name (`_municipios`)."""
        pins = (self.overrides.get(slug) or {}).get("_municipios") or {}
        for pliego_name, ine in pins.items():
            if _normalise_commune_name(pliego_name) == _normalise_commune_name(name):
                return str(ine)
        return None

    def _lookup(self, ine: str, name: str, slug: str | None) -> str | None:
        """Normalised dataset key for a pliego parish name inside `ine`,
        or None. Exact first; then the spaceless key; then, only when the
        pliego wrote the saint prefix, the prefix-less form; then the
        curator pin."""
        table = self._by_ine.get(ine) or {}
        norm = normalise_parroquia_name(name)
        if not norm:
            return None
        if norm in table:
            return norm
        nospace = self._nospace_by_ine.get(ine, {}).get(norm.replace(" ", ""))
        if nospace is not None:
            return nospace
        stripped = _SAINT_PREFIX_RE.sub("", norm)
        if stripped != norm and stripped in table:
            return stripped
        pins = (self.overrides.get(slug) or {}).get(ine) or {} if slug else {}
        for pliego_name, dataset_name in pins.items():
            if normalise_parroquia_name(pliego_name) == norm:
                pinned = normalise_parroquia_name(dataset_name)
                if pinned in table:
                    return pinned
                print(
                    f"[parroquias] STALE override {slug}/{ine}: {pliego_name!r} → "
                    f"{dataset_name!r} is not in the layer",
                    file=sys.stderr,
                )
        return None

    def union_parroquias(
        self, ine: str, names: Iterable[str], slug: str | None = None,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the parishes `names` of municipio `ine`. Returns (geom,
        stats) with `matched` (dataset spellings, saint suffix dropped)
        and `unmatched` (the pliego's spellings). A name the layer lacks
        is reported, not approximated."""
        self._ensure_loaded()
        matched: list[str] = []
        unmatched: list[str] = []
        geoms: list[BaseGeometry] = []
        table = self._by_ine.get(ine) or {}
        for name in names:
            name = name.strip()
            if not name:
                continue
            key = self._lookup(ine, name, slug)
            if key is None:
                unmatched.append(name)
                continue
            geoms.extend(table[key])
            matched.append(self._display_by_ine[ine][key])
        geom = unary_union(geoms) if geoms else None
        return geom, {"matched": matched, "unmatched": unmatched}


def _strip_saint_suffix(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
