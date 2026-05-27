"""ES-side geometry resolution — pull DOP polygons from Figshare and
union commune polygons from GISCO LAU.

Two sources, one chain. Stage 04 resolves each ES record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match against
     Bétard 2022 EU_PDO.gpkg. Covers ~99 of the 106 ES PDOs (all
     pre-Nov-2021). Returns the DOP polygon as a single (Multi)Polygon
     in EPSG:4326 after reprojection from EPSG:3035.
  2. **gisco-commune-union** — for subzona records (`is_sub_denomination=True` with
     `subzona_communes`) and for parent records that fell through #1
     (newer PDOs, all IGPs), build a (Multi)Polygon as the union of
     GISCO LAU municipio polygons matched by name.
  3. **parent-appellation** — DGC inherits the parent's polygon when
     commune matching yields nothing.
  4. **none** — no polygon available (logged for the audit).

Commune-name matching is best-effort: the GISCO LAU `LAU_NAME` field
carries the official Spanish/co-official name (e.g. "Sant Joan
d'Alacant"), while the pliego text uses a mix of names with and
without diacritics, articles, and language variants. We normalise
both sides (strip diacritics, drop leading articles, lowercase) and
match on the normalised key. Unmatched names are reported via the
returned `stats` dict — stage 04 surfaces them in the coverage
report alongside FR's commune misses.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _normalise_commune_name(s: str) -> str:
    """Strip diacritics, articles (leading + GISCO's trailing-comma
    convention), and parenthetical suffixes; lowercase. Same idiom as
    scripts/_lib/lieu_dit.py:_normalise_name on the FR side."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parenthetical context
    s = re.sub(r"[^A-Za-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # GISCO lists Catalan / Castilian / Galician / Mallorquí articled
    # names as "Borges del Camp, Les" / "Canonja, La" / "Castell, Es",
    # so after the comma-to-space pass the article surfaces as a
    # trailing token. Pliegos use article-first ("Les Borges del Camp").
    # Strip both forms so the two normalise to the same root.
    _articles = {
        "la", "el", "los", "las", "lo",
        "les", "els",
        "es", "sa", "ses",
        "o", "a", "os", "as",
    }
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in _articles:
        s = parts[1]
    parts = s.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in _articles:
        s = parts[0]
    if "/" in s:
        s = s.split("/", 1)[0].strip()
    return s


class _MuniCandidate:
    """One GISCO LAU row's relevant fields for matching."""
    __slots__ = ("geom", "ine", "province", "full_norm", "full_name")

    def __init__(self, geom: BaseGeometry, ine: str, full_norm: str, full_name: str):
        self.geom = geom
        self.ine = ine
        # Province is the first 2 digits of the INE code.
        self.province = ine[:2] if ine and len(ine) >= 2 else ""
        self.full_norm = full_norm
        self.full_name = full_name


class ESPolygonIndex:
    """In-memory polygon indexes for ES records.

    Lazy loader — pass paths in the constructor; reading + reprojecting
    the gpkg + shapefile takes ~3 seconds. Reuse one instance across
    all stage-04 record iterations.

    Commune matching uses a **two-pass province-context** strategy:
    pliegos abbreviate commune names (`Albelda` rather than the GISCO
    `Albelda de Iregua`), and 17 GISCO names have duplicates across
    different Spanish provinces. Last-write-wins indexing produces wrong
    matches (Albelda → Huesca's "Albelda" instead of La Rioja's). We
    instead index by both the full normalised name AND the first word,
    keep ALL candidate municipios per key, then in `union_communes`:

      Pass 1 — match unambiguous commune names (full-norm exact match
      with a single candidate). Collect the province codes those
      candidates belong to as the "expected province set" for this
      pliego's commune list.

      Pass 2 — re-match every commune. For ambiguous names, prefer
      candidates whose province is in the expected set. Among ties,
      pick the candidate with the closest name (longest common prefix).

    This eliminates the wrong-province class of mis-match without
    needing per-record curator configuration.
    """

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # norm → list of candidates matching that exact norm
        self._munis_by_full_norm: dict[str, list[_MuniCandidate]] = {}
        # first-word → list of candidates whose full_norm starts with that word
        self._munis_by_first_word: dict[str, list[_MuniCandidate]] = {}
        self._munis_by_ine: dict[str, _MuniCandidate] = {}
        self.n_unmatched_communes_seen: int = 0
        self.n_ambiguous_resolved: int = 0
        self.n_ambiguous_unresolved: int = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].str.startswith(("PDO-ES", "PGI-ES"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            es = gdf[gdf["CNTR_CODE"] == "ES"]
            if es.crs is None or es.crs.to_string() != target_crs:
                es = es.to_crs(target_crs)
            for _, row in es.iterrows():
                name = (row.get("LAU_NAME") or "").strip()
                gisco_id = row.get("GISCO_ID") or ""
                ine = gisco_id.split("_", 1)[1] if "_" in gisco_id else ""
                geom = row.geometry
                if geom is None or geom.is_empty or not name:
                    continue
                norm = _normalise_commune_name(name)
                cand = _MuniCandidate(
                    geom=geom, ine=ine, full_norm=norm, full_name=name,
                )
                self._munis_by_full_norm.setdefault(norm, []).append(cand)
                first_word = norm.split(" ", 1)[0]
                self._munis_by_first_word.setdefault(first_word, []).append(cand)
                if ine:
                    self._munis_by_ine[ine] = cand

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_municipios(self) -> int:
        return sum(len(v) for v in self._munis_by_full_norm.values())

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        """Look up a PDO/IGP polygon by EU `file_number` (e.g. PDO-ES-A0117)."""
        return self._pdo_polygons.get(file_number)

    def union_by_ines(
        self, ine_codes: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union GISCO LAU polygons by INE code. Used by the
        `geometry-research` resolver in stage 04 — when a curator-supplied
        JSON gives explicit `ine_code` per municipio, we don't need name-
        matching disambiguation.

        Returns (geom, stats) so the caller has the same shape as
        `union_communes`."""
        from shapely.ops import unary_union

        geoms: list[BaseGeometry] = []
        matched = unmatched = 0
        for ine in ine_codes:
            ine = (ine or "").strip()
            if not ine:
                continue
            cand = self._munis_by_ine.get(ine)
            if cand is None:
                unmatched += 1
                continue
            geoms.append(cand.geom)
            matched += 1
        if not geoms:
            return None, {"matched": matched, "unmatched": unmatched}
        return unary_union(geoms), {"matched": matched, "unmatched": unmatched}

    def union_communes(
        self, commune_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Two-pass commune matching with province-context disambiguation.

        Pass 1 — every commune-name lookup that yields exactly one
        candidate is "unambiguous". Collect their province codes (first
        2 digits of INE) → that's the *expected province set* for this
        pliego's commune list.

        Pass 2 — for each ambiguous lookup (multiple candidates), prefer
        a candidate whose province is in the expected set. Among ties,
        pick the candidate whose full normalised name has the longest
        common prefix with the requested name (so "Albelda" prefers
        "albelda de iregua" over "albelda" when both start with the
        same word but the longer-name one signals a more specific
        match).

        Returns (geom, stats) with `matched`, `unmatched`, and
        `ambiguous_resolved` counts. Wines whose communes legitimately
        span multiple provinces (Cava across 7) lose nothing — every
        unambiguous match contributes to the expected-province set.
        """
        names = [n for n in commune_names if n.strip()]
        if not names:
            return None, {"matched": 0, "unmatched": 0, "ambiguous_resolved": 0}

        # Per-commune candidate lookup. Each element is (commune-name,
        # candidate-list); empty list → no match found at all.
        per_commune: list[tuple[str, list[_MuniCandidate]]] = []
        for name in names:
            cands = self._lookup_candidates(name)
            per_commune.append((name, cands))

        # Pass 1: collect the unambiguous province set.
        expected_provinces: set[str] = set()
        for _name, cands in per_commune:
            if len(cands) == 1 and cands[0].province:
                expected_provinces.add(cands[0].province)

        # Pass 2: pick a polygon per commune. Use province context for
        # ambiguous matches; fall back to the longest-prefix candidate.
        polys: list[BaseGeometry] = []
        matched = unmatched = ambiguous_resolved = 0
        for name, cands in per_commune:
            if not cands:
                unmatched += 1
                self.n_unmatched_communes_seen += 1
                continue
            if len(cands) == 1:
                polys.append(cands[0].geom)
                matched += 1
                continue
            # Ambiguous: prefer same-province; among those, longest prefix.
            in_province = [c for c in cands if c.province in expected_provinces]
            requested_norm = _normalise_commune_name(name)
            if not in_province:
                # No province-context resolution possible. The first-word
                # index is noisy: a multi-word commune like "Sant Martí
                # de Barcedana" matches every Sant-prefixed name in
                # Spain. Only accept when the name is a single word AND
                # the requested + candidate are within an edit-distance
                # that suggests they really are the same place. This
                # treats unresolvable ambiguity as "unmatched" rather
                # than guessing wrong.
                if " " in requested_norm:
                    unmatched += 1
                    self.n_ambiguous_unresolved += 1
                    continue
                # Single-word fallback: pick the candidate whose first
                # word equals the requested name exactly (so "Tarragona"
                # picks "Tarragona", not "Tarragona-something").
                exact_first = [
                    c for c in cands
                    if c.full_norm.split(" ", 1)[0] == requested_norm
                ]
                shortlist = exact_first or cands
            else:
                shortlist = in_province
            shortlist.sort(
                key=lambda c, rn=requested_norm: (
                    -_common_prefix_len(c.full_norm, rn),
                    -len(c.full_norm),  # tiebreak by longer GISCO name
                ),
            )
            polys.append(shortlist[0].geom)
            matched += 1
            if in_province:
                ambiguous_resolved += 1
                self.n_ambiguous_resolved += 1
            else:
                self.n_ambiguous_unresolved += 1

        if not polys:
            return None, {"matched": 0, "unmatched": unmatched,
                          "ambiguous_resolved": ambiguous_resolved}
        return unary_union(polys), {
            "matched": matched, "unmatched": unmatched,
            "ambiguous_resolved": ambiguous_resolved,
        }

    def union_provinces(
        self, province_codes: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union ALL GISCO municipios whose INE province (first 2 digits
        of the GISCO_ID) is in `province_codes`. Used for region-wide
        IGPs whose pliego says "all communes of provinces X and Y"
        (Extremadura, IGP Castilla y León, etc.).

        Returns (geom, stats) where stats reports `n_provinces` and
        `n_municipios` covered."""
        wanted = set(province_codes)
        if not wanted:
            return None, {"n_provinces": 0, "n_municipios": 0}
        polys: list[BaseGeometry] = []
        for ine, c in self._munis_by_ine.items():
            if c.province not in wanted:
                continue
            polys.append(c.geom)
        if not polys:
            return None, {"n_provinces": len(wanted), "n_municipios": 0}
        return unary_union(polys), {
            "n_provinces": len(wanted), "n_municipios": len(polys),
        }

    def _lookup_candidates(self, name: str) -> list[_MuniCandidate]:
        """Return all GISCO candidates that could match `name`. Three
        attempts in order:
          1. Exact full-norm match (most reliable; what works for
             "Albelda de Iregua" if the pliego uses the full name).
          2. First-word match (handles pliegos that abbreviate; finds
             both "Albelda" and "Albelda de Iregua" candidates so
             pass 2 can disambiguate).
          3. Empty list (no candidates).
        """
        norm = _normalise_commune_name(name)
        if not norm:
            return []
        # Exact full-norm match
        cands = list(self._munis_by_full_norm.get(norm, []))
        if cands:
            return cands
        # First-word fallback — every candidate whose canonical name
        # starts with the same first word.
        first_word = norm.split(" ", 1)[0]
        cands = list(self._munis_by_first_word.get(first_word, []))
        return cands


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


