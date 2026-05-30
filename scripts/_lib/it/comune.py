"""Commune-precise geometry for Italian wine GIs.

Bétard 2022 EU_PDO.gpkg draws PDO polygons at whole-municipality
resolution and assigns shared comuni to every appellation that touches
them — measured Barbera d'Asti ∩ Dolcetto d'Asti = 100 %, Soave ∩
Valpolicella = 53 %. The Italian *documento unico* / MASAF disciplinare
instead names the production area precisely: a list of comuni, a list
of province, or a region.

`ITCommuneIndex` parses that description and unions the named comune
polygons. It joins two public sources:

  - ISTAT `Elenco-comuni-italiani.csv` — comune name ↔ 6-digit code ↔
    provincia ↔ regione
  - Eurostat GISCO LAU — comune polygons, keyed by the same 6-digit
    code (`GISCO_ID = IT_<code>`)

The code joins the two exactly (no name-matching between them), so the
only fuzzy step is matching the disciplinare's free-text comune /
provincia / regione names against the ISTAT registry.

Resolution precedence: an explicit comune list wins; a province list is
used only when no comuni are named (province headers like "provincia
di Verona: i comuni di …" are locational, not inclusions, and are
dropped when comuni are present — mirroring the AT "im Bundesland X"
rule); a region is the last resort.

Caveat: docs that say "in tutto o in parte" (whole *or partial*
territory) are resolved as whole comuni — slight boundary over-cover,
but far better than Bétard's gross overlap.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# ISTAT CSV column indices (Elenco-comuni-italiani.csv, cp1252, ';').
_COL_CODE = 4        # Codice Comune formato alfanumerico — "001001"
_COL_NAME = 6        # Denominazione in italiano
_COL_REGION = 10     # Denominazione Regione
_COL_PROVINCE = 11   # Denominazione dell'Unità territoriale sovracomunale

_KW_COMUNE = {"comune", "comuni"}
_KW_PROVINCE = {"provincia", "province"}
_KW_REGION = {"regione", "regioni"}
_MAX_NAME_WORDS = 6

# Adjectival / official region-name forms a disciplinare may use that the
# ISTAT registry doesn't carry: "Regione Siciliana" (vs ISTAT "Sicilia").
# Keyed by _norm(ISTAT name) → extra _norm aliases.
_REGION_NAME_ALIAS = {
    "sicilia": ("siciliana",),
}


def _norm(s: str) -> str:
    """Diacritics stripped, only a–z0–9. The Italian hagionym prefix is
    folded — San / Sant' / Santo / Santa / abbreviated "S." all collapse
    to "san" — so a disciplinare's "S. Alfio" matches ISTAT "Sant'Alfio"."""
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"['’`]", " ", s)
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"\bs(?:anto|anta|ante|ant|an)?\.?\s+", "san ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _name_variants(raw: str) -> set[str]:
    """Normalised forms of a province/region name, including each
    slash-separated bilingual part on its own ("Bolzano/Bozen" →
    {bolzanobozen, bolzano, bozen})."""
    parts = [raw] + (raw.split("/") if "/" in raw else [])
    return {v for v in (_norm(p) for p in parts) if v}


class ITCommuneIndex:
    def __init__(
        self,
        istat_csv: Path,
        gisco_lau_zip: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self._comune_by_name: dict[str, list[str]] = {}
        self._codes_by_province: dict[str, set[str]] = {}
        self._codes_by_region: dict[str, set[str]] = {}
        self._geom_by_code: dict[str, BaseGeometry] = {}

        if istat_csv.exists():
            raw = istat_csv.read_bytes()
            for enc in ("cp1252", "latin-1", "utf-8-sig"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            rows = list(csv.reader(io.StringIO(text), delimiter=";"))
            for r in rows[1:]:
                if len(r) <= _COL_PROVINCE:
                    continue
                code = (r[_COL_CODE] or "").strip()
                name = (r[_COL_NAME] or "").strip()
                if not (len(code) == 6 and code.isdigit() and name):
                    continue
                self._comune_by_name.setdefault(_norm(name), []).append(code)
                # Bilingual ISTAT province/region names carry both forms
                # slash-joined ("Bolzano/Bozen", "Valle d'Aosta/Vallée
                # d'Aoste"); a disciplinare names just one ("provincia di
                # Bolzano"), so register each slash-part as an alias too.
                for prov in _name_variants(r[_COL_PROVINCE]):
                    self._codes_by_province.setdefault(prov, set()).add(code)
                for reg in _name_variants(r[_COL_REGION]):
                    self._codes_by_region.setdefault(reg, set()).add(code)
                    for alias in _REGION_NAME_ALIAS.get(reg, ()):  # adjectival/official forms
                        self._codes_by_region.setdefault(alias, set()).add(code)

        if gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            it = gdf[gdf["CNTR_CODE"] == "IT"]
            if it.crs is None or it.crs.to_string() != target_crs:
                it = it.to_crs(target_crs)
            for _, row in it.iterrows():
                gid = str(row.get("GISCO_ID") or "")
                code = gid.split("_", 1)[1] if "_" in gid else ""
                geom = row.geometry
                if len(code) == 6 and code.isdigit() and geom is not None \
                        and not geom.is_empty:
                    self._geom_by_code[code] = geom

    @property
    def n_comuni(self) -> int:
        return len(self._geom_by_code)

    # ── parsing ──────────────────────────────────────────────────────────

    def parse_geo_area(self, text: str) -> dict:
        """Parse an Italian disciplinare geo-area description into
        `{comuni, province, regioni}` name lists."""
        t = re.sub(r"[„“”\"'`]", " ", text or "")
        out = {"comuni": [], "province": [], "regioni": []}
        bucket = None
        miss_run = 0
        words = t.split()
        i = 0
        while i < len(words):
            wn = _norm(words[i])
            if wn in _KW_COMUNE:
                bucket = "comuni"; miss_run = 0; i += 1; continue
            if wn in _KW_PROVINCE:
                bucket = "province"; miss_run = 0; i += 1; continue
            if wn in _KW_REGION:
                bucket = "regioni"; miss_run = 0; i += 1; continue
            matched = self._greedy_match(words, i, bucket)
            if matched is not None:
                name, span = matched
                out[bucket].append(name)
                miss_run = 0
                i += span
            else:
                # A name list runs name–connector–name; once prose
                # resumes, several non-name words pile up — close the
                # bucket so comune-homonyms in the prose ("Roma", "Monti",
                # "Ponte") aren't scooped into the list.
                miss_run += 1
                if miss_run >= 4:
                    bucket = None
                i += 1
        # A province / region named alongside an explicit comune list is
        # locational ("… in provincia di Livorno", "provincia di Verona:
        # i comuni di …") — not an inclusion.
        if out["comuni"]:
            out["province"] = []
            out["regioni"] = []
        return out

    def _greedy_match(self, words: list[str], i: int, bucket: str | None):
        """Longest known name starting at words[i] for the active bucket."""
        if bucket == "comuni":
            index = self._comune_by_name
        elif bucket == "province":
            index = self._codes_by_province
        elif bucket == "regioni":
            index = self._codes_by_region
        else:
            return None
        for span in range(min(_MAX_NAME_WORDS, len(words) - i), 0, -1):
            # Join with a space so `_norm`'s hagionym-fold sees word
            # boundaries ("S. Maria" → "san maria") before the final
            # alnum strip.
            cand = _norm(" ".join(words[i:i + span]))
            if cand in index:
                return cand, span
        return None

    # ── resolution ───────────────────────────────────────────────────────

    def resolve(self, geo_area: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve one Italian appellation's geometry from its geo-area
        text. Returns (geometry, geom_source, stats)."""
        parsed = self.parse_geo_area(geo_area or "")
        codes: set[str] = set()
        source = "none"
        n_units = 0

        if parsed["comuni"]:
            source = "gisco-comune-union"
            for nm in parsed["comuni"]:
                for c in self._comune_by_name.get(nm, []):
                    if c in self._geom_by_code:
                        codes.add(c)
                        n_units += 1
        elif parsed["province"]:
            source = "gisco-provincia-union"
            for nm in parsed["province"]:
                hit = self._codes_by_province.get(nm, set()) & self._geom_by_code.keys()
                codes |= hit
                if hit:
                    n_units += 1
        elif parsed["regioni"]:
            source = "gisco-regione-union"
            for nm in parsed["regioni"]:
                hit = self._codes_by_region.get(nm, set()) & self._geom_by_code.keys()
                codes |= hit
                if hit:
                    n_units += 1

        if not codes:
            return None, "none", {"matched": 0, "unmatched": 0, "n_units": n_units}
        geom = unary_union([self._geom_by_code[c] for c in codes])
        return geom, source, {"matched": len(codes), "unmatched": 0, "n_units": n_units}
