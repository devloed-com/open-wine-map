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

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from _lib.es.commune_list import _content_words, _normalise_commune_name, _same_name


def _name_forms(name: str) -> list[str]:
    """Every co-official form of a GISCO name, normalised: "Elvillar /
    Bilar" is reachable as `elvillar` and as `bilar`, since a pliego may
    use either language."""
    forms: list[str] = []
    for part in name.split("/"):
        norm = _normalise_commune_name(part)
        if norm and norm not in forms:
            forms.append(norm)
    return forms


# First words that carry no identity of their own: a pliego's "San Pedro
# de Muro" (a parish of Porto do Son) must never bind to San Sadurniño
# because both open with "san". The identifying head of such a name is
# its first two words.
_GENERIC_FIRST_WORDS = frozenset({
    "san", "santa", "santo", "sant", "santiago", "villa", "vila", "val", "puebla",
})

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


# Former municipios a pliego still names — the Costers del Segre Pallars
# list has ten villages that were municipios until the 1970s — mapped to
# the municipio that absorbed them, each with the public page stating the
# merger. Consulted only after the name matching above has given up.
_MUNICIPIO_MERGERS_PATH = Path(__file__).with_name("municipio_mergers.json")


def _load_municipio_mergers(path: Path = _MUNICIPIO_MERGERS_PATH) -> dict[str, tuple[str, str]]:
    """norm(former name or alias) → (current GISCO name, INE code)."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for former, entry in doc.get("mergers", {}).items():
        target = (entry["current"], entry["ine"])
        for alias in (former, *entry.get("aliases", ())):
            out[_normalise_commune_name(alias)] = target
    return out


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
      pliego's commune list. Only exact matches vote: a first-word
      fallback hit is a guess, and letting it widen the province set is
      how "Salinillas de Buradón" (a village of Labastida, Álava) once
      pulled Salinillas de Bureba and the whole of Burgos into Rioja
      Alavesa.

      Pass 2 — re-match every commune. For ambiguous names, prefer
      candidates whose province is in the expected set. A first-word
      fallback candidate is accepted only inside the expected set, and a
      multi-word name must match into its second word. Among ties, pick
      the candidate with the closest name (longest common prefix).

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
        self._mergers = _load_municipio_mergers()
        self._stale_mergers: set[str] = set()
        self._n_municipios: int = 0
        self.n_unmatched_communes_seen: int = 0
        self.n_ambiguous_resolved: int = 0
        self.n_ambiguous_unresolved: int = 0
        self.n_merged_resolved: int = 0

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
                self._add_municipio(geom, ine, name)

    def _add_municipio(self, geom: BaseGeometry, ine: str, name: str) -> None:
        """Register one GISCO LAU row under every co-official form of its
        name (full-norm index) and every form's first word."""
        forms = _name_forms(name)
        if not forms:
            return
        cand = _MuniCandidate(geom=geom, ine=ine, full_norm=forms[0], full_name=name)
        self._n_municipios += 1
        for form in forms:
            self._munis_by_full_norm.setdefault(form, []).append(cand)
            by_first = self._munis_by_first_word.setdefault(form.split(" ", 1)[0], [])
            if cand not in by_first:
                by_first.append(cand)
        if ine:
            self._munis_by_ine[ine] = cand

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_municipios(self) -> int:
        return self._n_municipios

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

    def municipio_name(self, ine: str) -> str | None:
        cand = self._munis_by_ine.get(ine)
        return cand.full_name if cand is not None else None

    def municipios_covered(
        self, geom: BaseGeometry, *, whole: float = 0.95, graze: float = 0.05,
    ) -> tuple[list[str], list[str]]:
        """INE codes of the GISCO municipios `geom` covers whole (at least
        `whole` of the municipio's area) and of those it covers in part
        (more than `graze`, less than `whole`). A municipio grazed below
        `graze` — the far side of a shared border digitised twice — is
        neither. Tells a zone drawn at whole-municipio resolution from a
        real sub-municipal delimitation."""
        minx, miny, maxx, maxy = geom.bounds
        whole_ines: list[str] = []
        partial_ines: list[str] = []
        for ine, cand in self._munis_by_ine.items():
            bx0, by0, bx1, by1 = cand.geom.bounds
            if bx0 > maxx or bx1 < minx or by0 > maxy or by1 < miny:
                continue
            area = cand.geom.area
            if not area:
                continue
            share = cand.geom.intersection(geom).area / area
            if share >= whole:
                whole_ines.append(ine)
            elif share > graze:
                partial_ines.append(ine)
        return whole_ines, partial_ines

    def union_communes(
        self, commune_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Two-pass commune matching with province-context disambiguation.

        Pass 1 — every commune name whose *exact* lookup yields one
        candidate is "unambiguous". Collect their province codes (first
        2 digits of INE) → that's the *expected province set* for this
        pliego's commune list. First-word fallback hits never vote.

        Pass 2 — for each ambiguous or fallback lookup, prefer a
        candidate whose province is in the expected set; a fallback
        candidate outside it is refused rather than guessed. Among ties,
        pick the candidate whose full normalised name has the longest
        common prefix with the requested name (so "Albelda" prefers
        "albelda de iregua" over "albelda" when both start with the
        same word but the longer-name one signals a more specific
        match).

        Last resort — a name neither pass could bind is looked up in
        `municipio_mergers.json`: a former municipio binds to the one that
        absorbed it, inside the expected provinces when there are any.

        Returns (geom, stats) with `matched`, `unmatched`,
        `ambiguous_resolved` and `merged` counts. Wines whose communes
        legitimately span multiple provinces (Cava across 7) lose nothing —
        every unambiguous match contributes to the expected-province set.
        """
        names = [n for n in commune_names if n.strip()]
        if not names:
            return None, {"matched": 0, "unmatched": 0, "ambiguous_resolved": 0, "merged": 0}

        # Per-commune candidate lookup. Each element is (commune-name,
        # normalised name, candidate-list, exact?); empty list → no match
        # found at all.
        per_commune: list[tuple[str, str, list[_MuniCandidate], bool]] = []
        for name in names:
            cands, exact = self._lookup_candidates(name)
            per_commune.append((name, _normalise_commune_name(name), cands, exact))

        # Pass 1: province votes from the unambiguous exact matches.
        votes = self._province_votes(per_commune)
        # An exact hit that is the only name in its province while the
        # list established others is re-read before it can bind — the
        # pliego's spelling, not the homonym elsewhere (see the method).
        reread = self._reread_out_of_context(per_commune, votes)
        if reread is not per_commune:
            per_commune = reread
            votes = self._province_votes(per_commune)
        expected_provinces = set(votes)

        # Pass 2: pick a polygon per commune. Use province context for
        # ambiguous matches; fall back to the longest-prefix candidate.
        polys: list[BaseGeometry] = []
        matched = unmatched = ambiguous_resolved = merged = 0
        for _name, requested_norm, cands, exact in per_commune:
            pick, outcome = self._pick(requested_norm, cands, exact, expected_provinces, votes)
            if pick is None:
                pick = self._merged_municipio(requested_norm, expected_provinces)
                if pick is not None:
                    outcome = "merged"
            if pick is None:
                unmatched += 1
                if outcome == "none":
                    self.n_unmatched_communes_seen += 1
                else:
                    self.n_ambiguous_unresolved += 1
                continue
            polys.append(pick.geom)
            matched += 1
            if outcome in ("extension", "ambiguous"):
                ambiguous_resolved += 1
                self.n_ambiguous_resolved += 1
            elif outcome == "guess":
                self.n_ambiguous_unresolved += 1
            elif outcome == "merged":
                merged += 1
                self.n_merged_resolved += 1

        if not polys:
            return None, {"matched": 0, "unmatched": unmatched,
                          "ambiguous_resolved": ambiguous_resolved, "merged": merged}
        return unary_union(polys), {
            "matched": matched, "unmatched": unmatched,
            "ambiguous_resolved": ambiguous_resolved, "merged": merged,
        }

    @staticmethod
    def _province_votes(per_commune: list[tuple[str, str, list[_MuniCandidate], bool]]) -> Counter[str]:
        votes: Counter[str] = Counter()
        for _name, _norm, cands, exact in per_commune:
            if exact and len(cands) == 1 and cands[0].province:
                votes[cands[0].province] += 1
        return votes

    def _reread_out_of_context(
        self,
        per_commune: list[tuple[str, str, list[_MuniCandidate], bool]],
        votes: Counter[str],
    ) -> list[tuple[str, str, list[_MuniCandidate], bool]]:
        """Re-read an exact single hit whose province no other listed name
        supports, when the list has established at least two provinces.
        Two readings are tried, each accepted only inside a province with
        two or more votes:

        - the name with its spaces closed — Ribera del Gállego-Cinco Villas
          writes "Los Corrales" for GISCO's Huesca "Loscorrales", and the
          article-stripped key "corrales" is Sevilla's "Corrales, Los"
          (636 km away) instead;
        - the name split on its conjunction — "Toril y Masegoso" is one
          Teruel municipio, but "Toril" (Cáceres) and "Masegoso" (Albacete)
          listed side by side in a list of those provinces are two, and the
          compound merge upstream cannot know the provinces.

        Anything less clear-cut keeps the exact hit: a Cava-style list does
        span provinces with a single municipio each."""
        if len(votes) < 2:
            return per_commune
        out: list[tuple[str, str, list[_MuniCandidate], bool]] = []
        changed = False
        for entry in per_commune:
            name, norm, cands, exact = entry
            if not (exact and len(cands) == 1 and votes[cands[0].province] == 1):
                out.append(entry)
                continue
            fused = _normalise_commune_name(re.sub(r"\s+", "", name))
            alt = [c for c in self._munis_by_full_norm.get(fused, []) if votes[c.province] >= 2] \
                if fused and fused != norm else []
            if len(alt) == 1:
                out.append((name, fused, alt, True))
                changed = True
                continue
            pieces = [p.strip() for p in re.split(r"\s+(?:y|i|e)\s+", name) if p.strip()]
            if len(pieces) >= 2:
                piece_entries = []
                for piece in pieces:
                    pc, pexact = self._lookup_candidates(piece)
                    if not (pexact and len(pc) == 1 and votes[pc[0].province] >= 2):
                        break
                    piece_entries.append((piece, _normalise_commune_name(piece), pc, True))
                else:
                    out.extend(piece_entries)
                    changed = True
                    continue
            out.append(entry)
        return out if changed else per_commune

    def _pick(
        self,
        requested_norm: str,
        cands: list[_MuniCandidate],
        exact: bool,
        expected_provinces: set[str],
        votes: Counter[str],
    ) -> tuple[_MuniCandidate | None, str]:
        """One commune's pass-2 decision: the candidate and how it was
        reached — `exact`, `extension` (an exact hit replaced by its
        in-province extension), `ambiguous` (settled by province context),
        `guess` (no context; the closest name), `refused` (a guess the
        guards would not take) or `none` (no candidate at all)."""
        if not cands:
            return None, "none"
        if exact and len(cands) == 1:
            pick = self._prefer_extension(requested_norm, cands[0], votes)
            return pick, "exact" if pick is cands[0] else "extension"
        in_province = [c for c in cands if c.province in expected_provinces]
        if exact:
            # The same name in several provinces. Without province
            # context a multi-word name is left unmatched rather than
            # guessed; a single word is tried as-is.
            if not in_province and " " in requested_norm:
                return None, "refused"
            shortlist = in_province or cands
        else:
            shortlist = _fallback_shortlist(requested_norm, cands, expected_provinces)
            if not shortlist:
                return None, "refused"
        # A name that agrees once the particles are dropped outranks a
        # longer shared prefix, which a particle alone can supply: "pobra
        # de " ties A Pobra de Brollón closer to Pobra de Trives than to
        # Pobra do Brollón.
        shortlist.sort(
            key=lambda c, rn=requested_norm: (
                not _same_name(c.full_norm, rn),
                -_common_prefix_len(c.full_norm, rn),
                -len(c.full_norm),  # tiebreak by longer GISCO name
            ),
        )
        return shortlist[0], "ambiguous" if in_province else "guess"

    def _merged_municipio(
        self, requested_norm: str, expected_provinces: set[str],
    ) -> _MuniCandidate | None:
        """The current municipio of a former one, per `municipio_mergers.json`.
        The pin is only as good as its number: a target whose INE is not in
        the index, or whose GISCO name no longer matches the pinned one, is
        reported STALE and refused; so is one outside the provinces the
        list's exact matches established."""
        entry = self._mergers.get(requested_norm)
        if entry is None:
            return None
        current, ine = entry
        cand = self._munis_by_ine.get(ine)
        if cand is None or not _same_name(cand.full_norm, _normalise_commune_name(current)):
            if ine not in self._stale_mergers:
                self._stale_mergers.add(ine)
                found = cand.full_name if cand else "no GISCO row"
                print(
                    f"[STALE] municipio_mergers.json: {requested_norm!r} → {current!r} "
                    f"(INE {ine}) but the index has {found!r}; ignored",
                    file=sys.stderr,
                )
            return None
        if expected_provinces and cand.province not in expected_provinces:
            return None
        return cand

    def _prefer_extension(
        self, requested_norm: str, cand: _MuniCandidate, votes: Counter[str],
    ) -> _MuniCandidate:
        """The abbreviation case from the class docstring. An exact hit
        whose province no other listed commune supports, while the same
        words open a longer GISCO name in a province the list does
        support, is the pliego abbreviating: Rioja Oriental's "Albelda" is
        Albelda de Iregua (La Rioja), not the Huesca village that happens
        to carry the bare name, and Campo de Cartagena's "Fuente Álamo" is
        Fuente Álamo de Murcia, not Albacete's Fuente-Álamo. Anything less
        clear-cut keeps the exact hit."""
        if votes[cand.province] != 1 or len(votes) < 2:
            return cand
        first_word = requested_norm.split(" ", 1)[0]
        extensions = [
            c for c in self._munis_by_first_word.get(first_word, [])
            if c is not cand
            and c.full_norm.startswith(requested_norm + " ")
            and c.province != cand.province
            and votes[c.province] >= 2
        ]
        return extensions[0] if len(extensions) == 1 else cand

    def _lookup_candidates(self, name: str) -> tuple[list[_MuniCandidate], bool]:
        """Return (candidates, exact) for `name`. Two attempts in order:
          1. Exact full-norm match (most reliable; what works for
             "Albelda de Iregua" if the pliego uses the full name) —
             `exact` is True.
          2. First-word match (handles pliegos that abbreviate; finds
             both "Albelda" and "Albelda de Iregua" candidates so
             pass 2 can disambiguate) — `exact` is False, and the caller
             treats the list as guesses to be checked, never as evidence.
        An empty list means no candidates at all.
        """
        norm = _normalise_commune_name(name)
        if not norm:
            return [], False
        cands = list(self._munis_by_full_norm.get(norm, []))
        if cands:
            return cands, True
        first_word = norm.split(" ", 1)[0]
        return list(self._munis_by_first_word.get(first_word, [])), False

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


def _fallback_shortlist(
    requested_norm: str, cands: list[_MuniCandidate], expected_provinces: set[str],
) -> list[_MuniCandidate]:
    """Narrow a first-word fallback to the candidates that could really be
    the requested commune. A fallback is a guess, so it is only accepted
    inside the provinces the exact matches established — Alcocer de
    Planes (Alicante, GISCO "Alcosser") must not become Guadalajara's
    Alcocer — and a multi-word name must then match in one of three ways:
    the first word after the head, particles skipped, is the same word or a
    spelling of it (the pliego's "Vélez Banco" is Vélez-Blanco, while the
    bare "san " shared by San Pedro de Muro and San Sadurniño proves
    nothing, and neither does a particle — "sant marti de" does not make
    Sant Martí de Barcedana, a village of Gavet de la Conca, into Sant
    Martí de Riucorb); the GISCO name is a whole-word prefix of the
    pliego's longer form ("Polop de la Marina" → Polop, "Elvillar de
    Álava" → Elvillar); or the two names agree once the particles are
    dropped or the spaces ignored ("Cogollos Vega" → Cogollos de la Vega,
    "Lapuebla de La barca" → Lapuebla de Labarca). A generic-headed
    abbreviation ("San Andrés" for San Andrés del Congosto) is accepted only
    when exactly one candidate extends it — two Guadalajara San Andrés would
    otherwise be settled by name length, which is not evidence. With no
    exact match anywhere there is no province context, and a multi-word
    name would bind to every same-first-word commune in Spain, so only a
    single word is tried."""
    first_word, _, rest = requested_norm.partition(" ")
    if expected_provinces:
        cands = [c for c in cands if c.province in expected_provinces]
    elif rest:
        return []
    if not rest:
        # "Tarragona" picks "Tarragona", not "Tarragona-something".
        exact_first = [c for c in cands if c.full_norm.split(" ", 1)[0] == requested_norm]
        return exact_first or cands
    words = _content_words(requested_norm)
    n_head = 2 if first_word in _GENERIC_FIRST_WORDS else 1
    kept = [
        c for c in cands
        if _next_word_agrees(words, _content_words(c.full_norm), n_head)
        or requested_norm.startswith(c.full_norm + " ")
        or _same_name(c.full_norm, requested_norm)
    ]
    if kept:
        return kept
    extensions = [c for c in cands if c.full_norm.startswith(requested_norm + " ")]
    return extensions if len(extensions) == 1 else []


def _next_word_agrees(req: tuple[str, ...], cand: tuple[str, ...], n_head: int) -> bool:
    """Same head words, and the first content word after them is the same
    word or a spelling of it. Sharing an opening letter is not enough: on
    the 2026-09-24 corpus every such spelling scored ≥ 0.8 ("banco" /
    "blanco", "carvajal" / "carbajal") and every village it wrongly bound
    ≤ 0.62 ("tres" / "trigueros": Quintanilla de Tres Barrios, a village
    of San Esteban de Gormaz, is not Quintanilla de Trigueros)."""
    return (
        len(req) > n_head and len(cand) > n_head
        and req[:n_head] == cand[:n_head]
        and SequenceMatcher(None, req[n_head], cand[n_head]).ratio() >= 0.75
    )


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


