"""BG-side geometry resolution — Bétard PDO + region-PGI-union +
GISCO commune-list fallback.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all EU PDOs including the 52 Bulgarian DOPs (`PDO-BG-*`).
    Bulgaria joined the EU in 2007; every BG PDO predates the
    Nov-2021 cutoff.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — ~265 Bulgarian obshtina polygons (CNTR_CODE='BG')
    used by the commune-list fallback when a record's commune list is
    parseable but its file_number isn't in Bétard.

Stage 04 resolves each BG record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Expected
     to cover all 52 BG DOPs.
  2. **gisco-commune-list** — the 2 BG PGIs (Дунавска равнина /
     Тракийска низина) delimit their area by obshtina, listed under
     „Област X:" headers (`commune.parse_area`); each name is matched
     among its oblast's GISCO obshtini (two are called Бяла), and the
     obshtini the text holds only in part are drawn whole and reported
     (2026-10-24). Also the fallback of any record with a commune list
     and no Bétard polygon.
  3. **region-pdo-union** — a PGI whose list does not resolve: the
     union of its member PDOs' Figshare polygons (north / south of Stara
     Planina, hand-verified against the 5-region classification). Those
     PDOs are settlement-scale, so the union under-draws the PGI.
  4. **stub-no-geometry** — no polygon resolvable (logged in audit).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# PGI file_number → the member-PDO file_numbers whose union forms the
# PGI's territory. North-of-Stara-Planina = Дунавска равнина PGI;
# south-of-Stara-Planina (Черноморски район + Розова долина + Тракийска
# низина + Долината на Струма) = Тракийска низина PGI. Hand-verified
# against `scripts/_lib/bg/region.py:_REGION_BY_FILE_NUMBER`.
BG_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    "PGI-BG-A1538": (  # Дунавска равнина — 20 northern PDOs
        "PDO-BG-A0952",  # Драгоево
        "PDO-BG-A1030",  # Хан Крум
        "PDO-BG-A0951",  # Лясковец
        "PDO-BG-A1441",  # Лом
        "PDO-BG-A0956",  # Ловеч
        "PDO-BG-A0360",  # Лозица
        "PDO-BG-A1314",  # Монтана
        "PDO-BG-A1031",  # Нови Пазар
        "PDO-BG-A0382",  # Ново село
        "PDO-BG-A0420",  # Павликени
        "PDO-BG-A1477",  # Плевен
        "PDO-BG-A1425",  # Русе
        "PDO-BG-A0997",  # Шумен
        "PDO-BG-A1018",  # Сухиндол
        "PDO-BG-A0957",  # Свищов
        "PDO-BG-A1439",  # Търговище
        "PDO-BG-A0370",  # Върбица
        "PDO-BG-A0885",  # Велики Преслав
        "PDO-BG-A1346",  # Видин
        "PDO-BG-A0955",  # Враца
    ),
    "PGI-BG-A1552": (  # Тракийска низина — 32 southern PDOs
        # Черноморски район (Black Sea coast) — 8
        "PDO-BG-A1392",  # Черноморски район
        "PDO-BG-A0881",  # Евксиноград
        "PDO-BG-A1347",  # Южно Черноморие
        "PDO-BG-A1175",  # Карнобат
        "PDO-BG-A0430",  # Поморие
        "PDO-BG-A1008",  # Славянци
        "PDO-BG-A1489",  # Сунгурларе
        "PDO-BG-A1032",  # Варна
        # Розова долина (Sub-Balkan / Rose Valley) — 2
        "PDO-BG-A1044",  # Карлово
        "PDO-BG-A1393",  # Хисаря
        # Тракийска низина (South-Central) — 18
        "PDO-BG-A0877",  # Асеновград
        "PDO-BG-A0985",  # Болярово
        "PDO-BG-A0944",  # Брестник
        "PDO-BG-A1179",  # Ямбол
        "PDO-BG-A1047",  # Ивайловград
        "PDO-BG-A1043",  # Хасково
        "PDO-BG-A1177",  # Любимец
        "PDO-BG-A1494",  # Нова Загора
        "PDO-BG-A1344",  # Оряховица — област Стара Загора (ИАЛВ spec §3), not Горна Оряховица
        "PDO-BG-A1182",  # Пазарджик
        "PDO-BG-A1474",  # Перущица
        "PDO-BG-A1297",  # Пловдив
        "PDO-BG-A0013",  # Сакар
        "PDO-BG-A1185",  # Септември
        "PDO-BG-A1391",  # Шивачево
        "PDO-BG-A1190",  # Сливен
        "PDO-BG-A1487",  # Стамболово
        "PDO-BG-A1394",  # Стара Загора
        # Долината на Струма (Struma Valley) — 4
        "PDO-BG-A1473",  # Долината на Струма
        "PDO-BG-A0946",  # Хърсово
        "PDO-BG-A1472",  # Мелник
        "PDO-BG-A1006",  # Сандански
    ),
}


# A PGI's commune list is drawn when at most this share of its names fail to
# resolve; above it the member-PDO union stays (a text that changed shape).
LIST_MAX_MISS_SHARE = 0.05


class BGPolygonIndex:
    """In-memory polygon index for BG records: Bétard PDO + PGI-union
    + GISCO obshtina-list fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # (normalised name, oblast code, polygon) per GISCO obshtina, indexed
        # by the name and by the name with its spaces closed ("Вълчидол" in
        # Дунавска равнина's text is GISCO's "Вълчи дол", "Бобовдол" its
        # "Бобов дол")
        self._lau: list[tuple[str, str, BaseGeometry]] = []
        self._lau_by_name: dict[str, list[int]] = {}
        self._lau_by_compact: dict[str, list[int]] = {}
        self._n_lau = 0

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-BG", "PGI-BG"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(gisco_lau_zip)
            bg = gdf[gdf["CNTR_CODE"] == "BG"]
            if bg.crs is None or bg.crs.to_string() != target_crs:
                bg = bg.to_crs(target_crs)
            for _, r in bg.iterrows():
                name = (r.get("LAU_NAME") or "").strip()
                geom = r.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                key = _normalise_commune(name)
                # BG_VAR09 → VAR, the oblast's EKATTE code (commune.OBLAST_CODES)
                self._lau.append((key, str(r.get("GISCO_ID") or "")[3:6], geom))
                self._lau_by_name.setdefault(key, []).append(len(self._lau) - 1)
                self._lau_by_compact.setdefault(key.replace(" ", ""), []).append(len(self._lau) - 1)
                self._n_lau += 1

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def pgi_union(
        self, pgi_file_number: str,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the member-PDO polygons for one of the 2 BG PGIs.
        Returns (geometry, stats) where stats records how many member
        PDOs resolved."""
        members = BG_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def _candidates(self, raw_name: str, oblast: str | None) -> tuple[list[int], str]:
        """The obshtini a name can denote, held to its oblast when the text
        gives one: the exact name, then the name with its spaces closed,
        then — for an abbreviated word ("Д. Митрополия" is Долна
        Митрополия) — the oblast's one name whose words the abbreviation
        begins. Returns (indices, how)."""
        from .commune import _normalise_commune
        key = _normalise_commune(raw_name)

        def scoped(idx: list[int]) -> list[int]:
            return [i for i in idx if not oblast or self._lau[i][1] == oblast]

        hits = scoped(self._lau_by_name.get(key, []))
        if hits:
            return hits, "exact"
        hits = scoped(self._lau_by_compact.get(key.replace(" ", ""), []))
        if hits:
            return hits, "compact"
        words = key.split()
        if oblast and any(w.endswith(".") for w in words):
            pat = re.compile(r"\s+".join(
                re.escape(w[:-1]) + r"\w*" if w.endswith(".") else re.escape(w) for w in words
            ) + r"$")
            hits = [i for i, (k, ob, _) in enumerate(self._lau) if ob == oblast and pat.match(k)]
            if len(hits) == 1:
                return hits, "abbreviation"
        if oblast and self._lau_by_name.get(key):
            return [], "outside-oblast"
        return [], "unmatched"

    def commune_union(
        self, commune_names: Iterable[str],
        scoped: Iterable[tuple[str, str]] | None = None,
        partial: Iterable[str] | None = None,
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons of the given obshtini. `scoped`
        pairs each name with the oblast code of the header it sits under
        (`commune.parse_area`); without it a bare name that matches several
        obshtini nationwide contributes nothing and is reported. `partial`
        names the obshtini the text holds only in part — drawn whole, and
        returned under stats["partial"] for the card to say so."""
        items = [(n, c or None) for n, c in scoped] if scoped else [(n, None) for n in commune_names]
        part = set(partial or [])
        polys: list[BaseGeometry] = []
        matched: list[str] = []
        unmatched: list[str] = []
        ambiguous: list[str] = []
        outside: list[str] = []
        folded: list[str] = []
        drawn_partial: list[str] = []
        from .commune import OBSHTINA_GROUPS, _normalise_commune
        for raw_name, oblast in items:
            group = OBSHTINA_GROUPS.get((_normalise_commune(raw_name), oblast or ""))
            if group:
                idx = [i for k in group for i in self._lau_by_name.get(k, []) if self._lau[i][1] == oblast]
                if len(idx) == len(group):
                    # every unit the name stands for, each counted (the card's
                    # header counts the units the polygon is the union of)
                    for i in idx:
                        polys.append(self._lau[i][2])
                        matched.append(self._lau[i][0])
                    folded.append(f"{raw_name} → {' + '.join(group)}")
                    if raw_name in part:
                        drawn_partial.append(raw_name)
                    continue
            hits, how = self._candidates(raw_name, oblast)
            if not hits:
                (outside if how == "outside-oblast" else unmatched).append(raw_name)
                continue
            if len(hits) > 1:
                # A bare name that matches several communes nationwide is
                # ambiguous; unioning all of them stretches the polygon
                # across the country instead of drawing the appellation
                # (see the GR / RO chains, where that shipped). It
                # contributes nothing and is reported instead.
                ambiguous.append(f"{raw_name} ({len(hits)})")
                continue
            polys.append(self._lau[hits[0]][2])
            matched.append(raw_name)
            if how != "exact":
                folded.append(f"{raw_name} → {self._lau[hits[0]][0]}")
            if raw_name in part:
                drawn_partial.append(raw_name)
        stats = {
            "matched": len(matched),
            "unmatched": len(unmatched),
            "n_ambiguous": len(ambiguous),
            "n_outside_oblast": len(outside),
            "names_unmatched": unmatched[:30],
            "names_ambiguous": ambiguous[:30],
            "names_outside_oblast": outside[:30],
            "names_folded": folded,
            "partial": drawn_partial,
            "scoped": bool(scoped),
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def resolve(
        self, file_number: str, commune_names: Iterable[str] | None = None,
        scoped: Iterable[tuple[str, str]] | None = None,
        partial: Iterable[str] | None = None,
    ) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one BG record. Returns (geometry,
        geom_source, stats). A PGI whose text lists its obshtini is drawn
        from them; a PGI without a usable list from the union of its member
        PDOs; a PDO from Bétard; anything else from its commune list."""
        fn = file_number or ""
        names = list(commune_names or [])
        scoped = [tuple(x) for x in scoped] if scoped else None
        if fn in BG_PGI_MEMBER_PDOS:
            # The ЕДИНЕН ДОКУМЕНТ / ИАЛВ spec of both PGIs delimits by
            # obshtina, under „Област X:" headers. Their member PDOs are
            # settlement-scale and cover a fraction of it: drawn as their
            # union, Дунавска равнина held 40 of the 118 obshtini its text
            # names (validator, 2026-10-23).
            list_stats: dict = {}
            if scoped:
                geom, list_stats = self.commune_union(names, scoped, partial)
                misses = (list_stats["unmatched"] + list_stats["n_ambiguous"]
                          + list_stats["n_outside_oblast"])
                if geom is not None and misses <= LIST_MAX_MISS_SHARE * len(scoped):
                    return geom, "gisco-commune-list", list_stats
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
                **({"list_rejected": list_stats} if list_stats else {}),
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        if fn in self._pdo_polygons:
            return (
                self._pdo_polygons[fn], "figshare-pdo",
                {"matched": -1, "unmatched": 0},
            )
        if names:
            geom, stats = self.commune_union(names, scoped, partial)
            if geom is not None:
                return geom, "gisco-commune-list", stats
            return None, "stub-no-geometry", stats
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
