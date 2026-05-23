"""Commune-precise geometry for Austrian wine GIs.

The Bétard 2022 EU_PDO.gpkg draws PDO polygons at whole-municipality
resolution: where two appellations share or border a municipality it
assigns the entire municipality to both, so adjacent DACs overlap
(measured Südsteiermark ∩ Vulkanland Steiermark = 22 %). The Austrian
*Einziges Dokument* describes each appellation's area precisely — by
politischer Bezirk, by Gemeinde, with explicit `ausgenommen` exclusions
— and the DACs are disjoint by wine law.

`ATCommuneIndex` resolves an appellation's geometry from that
description: it joins three public sources —

  - Statistik Austria `polbezirke.csv`  (Bezirk name ↔ 3-digit code)
  - Statistik Austria `gemliste_knz.csv` (Gemeinde name ↔ Kennziffer)
  - Eurostat GISCO LAU                   (Gemeinde polygons, keyed by
                                          Kennziffer via `GISCO_ID`)

— and unions the Gemeinde polygons named (directly or via their Bezirk)
in the Einziges Dokument, minus the excluded Gemeinden. The result is
commune-precise and disjoint.

The Austrian Gemeindekennziffer is 5 digits: digit 1 = Bundesland,
digits 1–3 = politischer Bezirk, digits 1–5 = Gemeinde.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Bundesland name → leading Gemeindekennziffer digit.
_BUNDESLAND_DIGIT = {
    "burgenland": "1", "karnten": "2", "niederosterreich": "3",
    "oberosterreich": "4", "salzburg": "5", "steiermark": "6",
    "tirol": "7", "vorarlberg": "8", "wien": "9",
}


def _norm(s: str) -> str:
    """Aggressive normalisation for resilient name joins: ß→ss,
    Sankt/St.→st, diacritics stripped, only a–z0–9 kept."""
    s = (s or "").lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\bsankt\b", "st", s)
    s = re.sub(r"\bst\.?\b", "st", s)
    return re.sub(r"[^a-z0-9]+", "", s)


# Curated alias: a Gemeinde name as written in an Einziges Dokument →
# the current Statistik-Austria Gemeinde(n) it resolves to. Covers
# municipal mergers and spelling drift since the appellation documents
# were drafted (normalised keys; see `_norm`).
_GEMEINDE_ALIAS: dict[str, list[str]] = {
    "etsdorfhaitzendorf": ["grafenegg"],        # merged into Grafenegg (2008)
    "imbach": ["senftenberg"],                  # Katastralgemeinde of Senftenberg
    "stratzingdross": ["stratzing", "dross"],   # split into Stratzing + Droß
    "weissenkirchen": ["weissenkircheninderwachau"],
    "strassindersteiermark": ["strassinsteiermark"],
    "heiligenkreuzamwasen": ["heiligenkreuzamwaasen"],
}

# Keyword tokens that switch the active parse bucket.
_KW_BEZIRK = {"bezirk", "bezirke", "bezirken", "bezirkes", "bezirks"}
_KW_GEMEINDE = {"gemeinde", "gemeinden"}
_KW_STADT = {"stadt", "stadte", "freistadt", "freistadte", "statutarstadt"}
_KW_BUNDESLAND = {"bundesland", "bundeslander", "bundeslandes"}
_GERICHTSBEZIRK = "gerichtsbezirk"
_EXCL_SENTINEL = "\x01excl\x01"


class ATCommuneIndex:
    def __init__(
        self,
        polbezirke_csv: Path,
        gemliste_csv: Path,
        gisco_lau_zip: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        # --- politischer Bezirk: normalised name → [3-digit codes] ---
        self._bezirk_by_name: dict[str, list[tuple[str, str]]] = {}
        for row in self._read_csv(polbezirke_csv, header_row=2):
            code = (row.get("Kennziffer pol. Bezirk") or "").strip()
            name = (row.get("Politischer Bezirk") or "").strip()
            if not (code.isdigit() and name):
                continue
            full = _norm(name)
            bare = _norm(re.sub(r"\(.*?\)", "", name))
            for key in {full, bare}:
                self._bezirk_by_name.setdefault(key, []).append((code, name))

        # --- Gemeinde: normalised name → [Kennziffer] ---
        self._gemeinde_by_name: dict[str, list[str]] = {}
        for row in self._read_csv(gemliste_csv, header_row=2):
            knz = (row.get("Gemeindekennziffer") or "").strip()
            name = (row.get("Gemeindename") or "").strip()
            if len(knz) == 5 and knz.isdigit() and name:
                self._gemeinde_by_name.setdefault(_norm(name), []).append(knz)
        self._max_name_words = 6

        # --- GISCO LAU: Kennziffer → polygon ---
        self._geom_by_knz: dict[str, BaseGeometry] = {}
        if gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            at = gdf[gdf["CNTR_CODE"] == "AT"]
            if at.crs is None or at.crs.to_string() != target_crs:
                at = at.to_crs(target_crs)
            for _, r in at.iterrows():
                gid = str(r.get("GISCO_ID") or "")
                knz = gid.split("_", 1)[1] if "_" in gid else ""
                geom = r.geometry
                if len(knz) == 5 and knz.isdigit() and geom is not None and not geom.is_empty:
                    self._geom_by_knz[knz] = geom

    @staticmethod
    def _read_csv(path: Path, header_row: int) -> list[dict]:
        if not path.exists():
            return []
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines(),
                               delimiter=";"))
        if len(rows) <= header_row:
            return []
        header = rows[header_row]
        return [dict(zip(header, r)) for r in rows[header_row + 1:] if any(r)]

    @property
    def n_gemeinden(self) -> int:
        return len(self._geom_by_knz)

    # ── parsing ──────────────────────────────────────────────────────────

    def parse_geo_area(self, text: str) -> dict:
        """Parse a German Einziges-Dokument geo-area description into
        `{bundeslaender, bezirke, gemeinden, excluded}` name lists."""
        t = text or ""
        # "Gemeinden des Bezirkes X links der Mur (A, B, …)" — the named
        # Gemeinden follow in parens; the Bezirk here only *locates* them
        # and must not be read as a whole-Bezirk inclusion.
        t = re.sub(r"des\s+Bezirk\w*\b[^(.]*", " ", t, flags=re.I)
        # "in der Gemeinde X die Rieden …" — sub-commune Rieden can't be
        # resolved at Gemeinde precision; drop the clause (slight
        # under-coverage, documented).
        t = re.sub(r"in der Gemeinde\s+[^.]*?\bRieden\b[^.]*", " ", t, flags=re.I)
        # Collapse the exclusion lead-in to a single sentinel token.
        t = re.sub(r"(ausgenommen|mit\s+Ausnahme)(\s+(die|der)\s+Gemeinden?)?",
                   f" {_EXCL_SENTINEL} ", t, flags=re.I)
        t = re.sub(r"[„“”\"'»«()]", " ", t)

        out = {"bundeslaender": [], "bezirke": [], "gemeinden": [], "excluded": []}
        bucket = None
        words = t.split()
        i = 0
        while i < len(words):
            w = words[i]
            wn = _norm(w)
            if w == _EXCL_SENTINEL or wn == "excl":
                # The "ausgenommen die Gemeinden" lead-in is absorbed
                # into the sentinel, so excluded names follow directly.
                bucket = "_excl"; i += 1; continue
            if wn in _KW_BEZIRK:
                bucket = "bezirke"; i += 1; continue
            if wn in _KW_GEMEINDE or wn in _KW_STADT or wn == "gerichtsbezirk":
                bucket = "gemeinden"; i += 1; continue
            if wn in _KW_BUNDESLAND:
                bucket = "bundeslaender"; i += 1; continue
            matched = self._greedy_match(words, i, bucket)
            if matched is not None:
                name, span = matched
                key = "excluded" if bucket == "_excl" else bucket
                if key in out:
                    out[key].append(name)
                i += span
            else:
                i += 1
        # A Bundesland named alongside specific Bezirke/Gemeinden is
        # locational ("... im Bundesland Steiermark"), not a whole-state
        # inclusion — whole-Bundesland records never also list units.
        if out["bezirke"] or out["gemeinden"]:
            out["bundeslaender"] = []
        return out

    def _greedy_match(self, words: list[str], i: int, bucket: str | None):
        """Longest known name starting at words[i] for the active bucket."""
        if bucket == "bezirke":
            dicts = (self._bezirk_by_name,)
        elif bucket in ("gemeinden", "_excl"):
            dicts = (self._gemeinde_by_name, _GEMEINDE_ALIAS)
        elif bucket == "bundeslaender":
            dicts = (_BUNDESLAND_DIGIT,)
        else:
            return None
        for span in range(min(self._max_name_words, len(words) - i), 0, -1):
            cand = _norm("".join(words[i:i + span]))
            for d in dicts:
                if cand in d:
                    return cand, span
        return None

    # ── resolution ───────────────────────────────────────────────────────

    def _bezirk_kennziffern(self, bezirk_norm: str) -> list[str]:
        cands = self._bezirk_by_name.get(bezirk_norm) or []
        if not cands:
            return []
        # Ambiguous bare name (e.g. "Wiener Neustadt" → Stadt + Land):
        # a wine Bezirk is the rural (Land) one.
        code = cands[0][0]
        for c, full in cands:
            if "land" in full.lower():
                code = c
                break
        return [k for k in self._geom_by_knz if k.startswith(code)]

    def _gemeinde_kennziffern(self, name: str, bl_digit: str) -> list[str]:
        """Kennziffern for a (possibly aliased) Gemeinde name. When the
        name is ambiguous across Bundesländer (e.g. Mühldorf in Kärnten
        and Niederösterreich), keep only those in the appellation's
        Bundesland."""
        out: list[str] = []
        for real in _GEMEINDE_ALIAS.get(name, [name]):
            cands = [k for k in self._gemeinde_by_name.get(real, [])
                     if k in self._geom_by_knz]
            if len(cands) > 1 and bl_digit:
                filtered = [k for k in cands if k.startswith(bl_digit)]
                cands = filtered or cands
            out.extend(cands)
        return out

    def resolve(self, geo_area: str, bundesland: str = "") -> tuple[BaseGeometry | None, str, dict]:
        """Resolve one Austrian appellation's geometry from its geo-area
        text. `bundesland` (the record's German Bundesland name)
        disambiguates duplicate Gemeinde names. Returns (geometry,
        geom_source, stats)."""
        parsed = self.parse_geo_area(geo_area or "")
        bl_digit = _BUNDESLAND_DIGIT.get(_norm(bundesland), "")
        knz: set[str] = set()
        n_units = 0

        for bl in parsed["bundeslaender"]:
            digit = _BUNDESLAND_DIGIT.get(bl)
            if digit:
                knz |= {k for k in self._geom_by_knz if k.startswith(digit)}
                n_units += 1
        for bz in parsed["bezirke"]:
            ks = self._bezirk_kennziffern(bz)
            if ks:
                knz |= set(ks)
                n_units += 1
        for gm in parsed["gemeinden"]:
            ks = self._gemeinde_kennziffern(gm, bl_digit)
            knz |= set(ks)
            n_units += len(ks)
        for ex in parsed["excluded"]:
            for k in self._gemeinde_kennziffern(ex, bl_digit):
                knz.discard(k)

        if not knz:
            return None, "none", {"matched": 0, "unmatched": 0, "n_units": n_units}
        geom = unary_union([self._geom_by_knz[k] for k in knz])
        bundesland_only = bool(parsed["bundeslaender"]) and not (
            parsed["bezirke"] or parsed["gemeinden"]
        )
        source = "gisco-bundesland-union" if bundesland_only else "gisco-commune-union"
        return geom, source, {"matched": len(knz), "unmatched": 0, "n_units": n_units}
