"""PT-side geometry resolution — pull DOP polygons from Bétard 2022
Figshare and union concelho polygons from DGT CAOP 2025.

Two sources, one chain. Stage 04 resolves each PT record by:

  1. **figshare-pdo** — exact `file_number` (`PDO-PT-Axxxx`) → `PDOid`
     match against `raw/es/figshare/EU_PDO.gpkg` (the same Bétard 2022
     dataset the ES pipeline uses; it covers all EU PDOs). Expected
     hit-rate: ~30 of 30 PT DOPs.
  2. **caop-concelho-union** — union of CAOP 2025 município polygons
     matched against an enumerated commune list. Used for IGPs that
     don't have a Figshare row, and as a fallback for newer DOPs.
  3. **parent-appellation** — sub-região inherits the parent's
     polygon when no commune list is parsed.
  4. **none** — no polygon available (logged for the audit).

CAOP carries three levels (distrito → município → freguesia). For v1
we match at the município (concelho) level — sufficient for IGP-wide
fallback and the typical caderno commune-list precision. Freguesia-
level matching is a follow-up; the CAOP layer is loaded once and the
freguesia data lives alongside município.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Macro-region expansions: when the caderno declares the production
# area as the whole autonomous region (Açores or Madeira) rather than
# enumerating concelhos, expand the token into the constituent ilhas.
# The names below match the `_concelhos_by_distrito` bare-name keys
# (CAOP `distrito_ilha` stripped of "Ilha de/do/da"). Coverage:
#   - Açores: 7 ilhas → 16 municipios (Grupo Central + Oriental; the
#     Grupo Ocidental's Corvo + Flores are wine-free and not in the
#     CAOP gpkg we ship).
#   - Madeira: 2 ilhas → 11 municipios (RAM).
PT_MACRO_REGIONS: dict[str, list[str]] = {
    "acores": [
        "Santa Maria", "São Miguel", "Terceira", "Graciosa",
        "São Jorge", "Pico", "Faial",
    ],
    "madeira": ["Madeira", "Porto Santo"],
}


def _normalise_concelho(s: str) -> str:
    """Strip diacritics + leading articles, lowercase, collapse spaces."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Za-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Strip leading Portuguese articles
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in {"o", "a", "os", "as", "do", "da", "dos", "das"}:
        s = parts[1]
    return s


class _Concelho:
    __slots__ = ("geom", "name", "norm", "distrito")

    def __init__(
        self, geom: BaseGeometry, name: str, norm: str, distrito: str
    ) -> None:
        self.geom = geom
        self.name = name
        self.norm = norm
        self.distrito = distrito


class PTPolygonIndex:
    """In-memory polygon indexes for PT records.

    Lazy loader — pass paths in the constructor; reading + reprojecting
    the gpkgs takes a few seconds. Reuse one instance across all
    stage-04 PT iterations.
    """

    def __init__(
        self,
        figshare_gpkg: Path,
        caop_gpkgs: list[Path],
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        # Same-name concelho collisions resolved during `union_concelhos`.
        self.n_concelho_ambiguous_resolved = 0
        self.n_concelho_ambiguous_guessed = 0
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # norm → list of concelho candidates
        self._concelho_by_norm: dict[str, list[_Concelho]] = {}
        # normalised distrito name → list of concelhos in that distrito
        self._concelhos_by_distrito: dict[str, list[_Concelho]] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            mask = gdf["PDOid"].astype(str).str.startswith(("PDO-PT", "PGI-PT"))
            gdf = gdf[mask]
            if not gdf.empty:
                if gdf.crs is None or gdf.crs.to_string() != target_crs:
                    gdf = gdf.to_crs(target_crs)
                for _, row in gdf.iterrows():
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        # CAOP gpkgs: Continente, RAA (Açores), RAM (Madeira). The
        # schema is consistent across all three: `*_municipios` layer
        # with `municipio` + `distrito_ilha` fields. We read the
        # município layer in each (~305 concelhos across all PT).
        for gpkg in caop_gpkgs:
            if not gpkg.exists():
                continue
            try:
                layers = gpd.list_layers(gpkg)["name"].tolist()
            except Exception:  # noqa: BLE001
                continue
            muni_layer = next(
                (name for name in layers
                 if name and "municipios" in name.lower()),
                None,
            )
            if muni_layer is None:
                continue
            try:
                gdf = gpd.read_file(gpkg, layer=muni_layer)
            except Exception:  # noqa: BLE001
                continue
            if gdf.empty:
                continue
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                name = (row.get("municipio") or "").strip()
                distrito = (row.get("distrito_ilha") or "").strip()
                geom = row.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                norm = _normalise_concelho(name)
                c = _Concelho(geom=geom, name=name, norm=norm, distrito=distrito)
                self._concelho_by_norm.setdefault(norm, []).append(c)
                if distrito:
                    dnorm = _normalise_concelho(distrito)
                    self._concelhos_by_distrito.setdefault(dnorm, []).append(c)
                    # Açores / Madeira distrito_ilha rows are prefixed
                    # with "Ilha de" / "Ilha do" / "Ilha da" — and a
                    # bare "Ilha " for "Ilha Terceira" (no preposition).
                    # Index a bare-name variant too so cadernos can say
                    # "Pico" / "Terceira" and still match.
                    bare = re.sub(
                        r"^ilha\s+(?:de\s+|do\s+|da\s+)?", "", dnorm,
                        flags=re.IGNORECASE,
                    )
                    if bare and bare != dnorm:
                        self._concelhos_by_distrito.setdefault(bare, []).append(c)

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_concelhos(self) -> int:
        return sum(len(v) for v in self._concelho_by_norm.values())

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    @property
    def n_distritos(self) -> int:
        return len(self._concelhos_by_distrito)

    def union_concelhos(
        self, concelho_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union CAOP município polygons matched by normalised name, with
        distrito-context disambiguation for same-name concelhos.

        A few concelho names recur across distritos — most consequentially
        `Lagoa` (distrito de Faro, in the Algarve) and `Lagoa` (Ilha de São
        Miguel, in the Açores). Taking the first candidate unioned the wrong
        one: DOP Lagoa is an Algarve wine, and the Azores polygon dragged its
        resolved geometry ~1500 km out into the Atlantic.

        Pass 1 — every name that resolves to exactly one concelho is
        unambiguous; collect their distritos as the expected-distrito set.
        Pass 2 — for an ambiguous name, prefer the candidate whose distrito is
        in that set; failing that, the candidate nearest the centroid of the
        already-resolved polygons. Every disambiguation is logged to stderr —
        a wrong guess must be visible, never silent.

        Returns (geom, stats) with `matched`, `unmatched` and
        `ambiguous_resolved` counts.
        """
        per: list[tuple[str, list[_Concelho]]] = [
            (n, list(self._concelho_by_norm.get(_normalise_concelho(n), [])))
            for n in concelho_names
            if n and n.strip()
        ]
        expected_distritos = {
            _normalise_concelho(cands[0].distrito)
            for _name, cands in per
            if len(cands) == 1 and cands[0].distrito
        }

        geoms: list[BaseGeometry] = []
        matched = unmatched = ambiguous_resolved = 0
        for name, cands in per:
            if not cands:
                unmatched += 1
                continue
            if len(cands) == 1:
                geoms.append(cands[0].geom)
                matched += 1
                continue

            # Ambiguous — disambiguate by distrito context, then by spatial
            # proximity to the already-resolved cluster.
            in_distrito = [
                c for c in cands
                if _normalise_concelho(c.distrito) in expected_distritos
            ]
            if len(in_distrito) == 1:
                chosen, how = in_distrito[0], "distrito-context"
            elif geoms:
                ref = unary_union(geoms).centroid
                chosen = min(in_distrito or cands,
                             key=lambda c, ref=ref: c.geom.distance(ref))
                how = "nearest resolved cluster"
            else:
                chosen, how = cands[0], "first candidate — NO disambiguating context"
            geoms.append(chosen.geom)
            matched += 1
            ambiguous_resolved += 1
            if "NO disambiguating" in how:
                self.n_concelho_ambiguous_guessed += 1
            else:
                self.n_concelho_ambiguous_resolved += 1
            dropped = ", ".join(sorted(
                {c.distrito for c in cands if c is not chosen}
            ))
            print(
                f"  [pt-geom] ambiguous concelho '{name}': {len(cands)} "
                f"candidates → chose distrito de {chosen.distrito} "
                f"via {how} (rejected: {dropped})",
                file=sys.stderr,
            )

        if not geoms:
            return None, {"matched": matched, "unmatched": unmatched,
                          "ambiguous_resolved": ambiguous_resolved}
        return unary_union(geoms), {
            "matched": matched, "unmatched": unmatched,
            "ambiguous_resolved": ambiguous_resolved,
        }

    def union_distritos(
        self, distrito_names: Iterable[str]
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Union every CAOP município that lives in one of the named
        distritos. Used for the "Todos os municípios dos distritos de
        X e Y" pattern (Vinho Verde: Braga + Viana do Castelo).
        Returns the same (geom, stats) shape as `union_concelhos`."""
        geoms: list[BaseGeometry] = []
        matched = unmatched = 0
        for name in distrito_names:
            if not name:
                continue
            norm = _normalise_concelho(name)
            concelhos = self._concelhos_by_distrito.get(norm)
            if not concelhos:
                unmatched += 1
                continue
            for c in concelhos:
                geoms.append(c.geom)
                matched += 1
        if not geoms:
            return None, {"matched": matched, "unmatched": unmatched}
        return unary_union(geoms), {"matched": matched, "unmatched": unmatched}

    def union_from_parsed(
        self, parsed: dict
    ) -> tuple[BaseGeometry | None, dict[str, int]]:
        """Combine `union_concelhos` + `union_distritos` into one call.
        Takes the dict returned by `commune_list.parse_commune_list`.
        Expands `macro_regions` tokens (`acores` / `madeira`) into
        their constituent ilhas via `PT_MACRO_REGIONS`."""
        geoms: list[BaseGeometry] = []
        stats = {"concelhos_matched": 0, "concelhos_unmatched": 0,
                 "distritos_matched": 0, "distritos_unmatched": 0}
        macro_distritos: list[str] = []
        for token in parsed.get("macro_regions") or []:
            macro_distritos.extend(PT_MACRO_REGIONS.get(token, []))
        all_distritos = list(parsed.get("distritos") or []) + macro_distritos
        if parsed.get("concelhos"):
            g, s = self.union_concelhos(parsed["concelhos"])
            stats["concelhos_matched"] = s["matched"]
            stats["concelhos_unmatched"] = s["unmatched"]
            if g is not None and not g.is_empty:
                geoms.append(g)
        if all_distritos:
            g, s = self.union_distritos(all_distritos)
            stats["distritos_matched"] = s["matched"]
            stats["distritos_unmatched"] = s["unmatched"]
            if g is not None and not g.is_empty:
                geoms.append(g)
        if not geoms:
            return None, stats
        return unary_union(geoms), stats
