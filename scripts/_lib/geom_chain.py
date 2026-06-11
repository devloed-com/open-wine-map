"""Commune-index + DGC/ES geometry resolution chain (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. Self-contained:
no stage-04 function dependencies. The names the main build loop calls
(union_from_insee, DGCGeomResult, resolve_dgc_geometry, union_for_appellation,
cahier_insee, load_commune_index, normalize_commune, _find_sibling_umbrella,
_resolve_es_igp_fallback, _resolve_es_sigpac, DEPT_NAME_TO_CODE) are imported
back into stage 04.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

from _lib.aires import lookup as lookup_aire
from _lib.dgc_village_overrides import DGC_VILLAGE_INSEE
from _lib.es.baleares import ines_for_island
from _lib.es.commune_list import (
    parse_ccaa_wide,
    parse_commune_list,
    parse_island_wide,
    parse_province_wide_list,
    parse_whole_commune_prefix,
)
from _lib.es.geometry import ESPolygonIndex
from _lib.es.pliego_parcels import parse_polygon_inclusions
from _lib.es.region import CCAA_TO_PROVINCE_INES, PROVINCE_TO_INE
from _lib.es.sigpac import SigpacIndex
from _lib.lieu_dit import LieuDitIndex, derive_climat_name

ROOT = Path(__file__).resolve().parents[2]


# INSEE 2-digit département code → canonical name as written in cahiers.
# Used for resolving "Côte-d'Or" → "21" so commune lookup stays inside the
# correct département (avoids Saint-Pierre homonym collisions).
DEPT_NAME_TO_CODE: dict[str, str] = {
    "Ain": "01", "Aisne": "02", "Allier": "03", "Alpes-de-Haute-Provence": "04",
    "Hautes-Alpes": "05", "Alpes-Maritimes": "06", "Ardèche": "07", "Ardennes": "08",
    "Ariège": "09", "Aube": "10", "Aude": "11", "Aveyron": "12",
    "Bouches-du-Rhône": "13", "Calvados": "14", "Cantal": "15", "Charente": "16",
    "Charente-Maritime": "17", "Cher": "18", "Corrèze": "19", "Corse-du-Sud": "2A",
    "Haute-Corse": "2B", "Côte-d'Or": "21", "Côte-d’Or": "21",
    "Côtes-d'Armor": "22", "Côtes-d’Armor": "22", "Creuse": "23",
    "Dordogne": "24", "Doubs": "25", "Drôme": "26", "Eure": "27", "Eure-et-Loir": "28",
    "Finistère": "29", "Gard": "30", "Haute-Garonne": "31", "Gers": "32",
    "Gironde": "33", "Hérault": "34", "Ille-et-Vilaine": "35", "Indre": "36",
    "Indre-et-Loire": "37", "Isère": "38", "Jura": "39", "Landes": "40",
    "Loir-et-Cher": "41", "Loire": "42", "Haute-Loire": "43", "Loire-Atlantique": "44",
    "Loiret": "45", "Lot": "46", "Lot-et-Garonne": "47", "Lozère": "48",
    "Maine-et-Loire": "49", "Manche": "50", "Marne": "51", "Haute-Marne": "52",
    "Mayenne": "53", "Meurthe-et-Moselle": "54", "Meuse": "55", "Morbihan": "56",
    "Moselle": "57", "Nièvre": "58", "Nord": "59", "Oise": "60", "Orne": "61",
    "Pas-de-Calais": "62", "Puy-de-Dôme": "63", "Pyrénées-Atlantiques": "64",
    "Hautes-Pyrénées": "65", "Pyrénées-Orientales": "66", "Bas-Rhin": "67",
    "Haut-Rhin": "68", "Rhône": "69", "Haute-Saône": "70", "Saône-et-Loire": "71",
    "Sarthe": "72", "Savoie": "73", "Haute-Savoie": "74", "Paris": "75",
    "Seine-Maritime": "76", "Seine-et-Marne": "77", "Yvelines": "78",
    "Deux-Sèvres": "79", "Somme": "80", "Tarn": "81", "Tarn-et-Garonne": "82",
    "Var": "83", "Vaucluse": "84", "Vendée": "85", "Vienne": "86",
    "Haute-Vienne": "87", "Vosges": "88", "Yonne": "89", "Territoire de Belfort": "90",
    "Essonne": "91", "Hauts-de-Seine": "92", "Seine-Saint-Denis": "93",
    "Val-de-Marne": "94", "Val-d'Oise": "95", "Val-d’Oise": "95",
    "Guadeloupe": "971", "Martinique": "972", "Guyane": "973",
    "La Réunion": "974", "Mayotte": "976",
}


def normalize_commune(s: str) -> str:
    """Loose match key for commune names — strip diacritics, casing, spacing,
    leading articles, parenthetical notes."""
    s = re.sub(r"\(.*?\)", "", s)  # drop "(uniquement pour la partie ...)"
    s = re.sub(r"^(?:Le|La|Les|L['’])\s+", "", s, flags=re.IGNORECASE)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[\W_]+", "", s).lower()


def load_commune_index(
    path: Path,
) -> tuple[dict[tuple[str, str], tuple[dict, str]], dict[str, dict], dict[str, str]]:
    """Build three indexes over IGN AdminExpress communes.

    The first is `(dept_code, normalized_name) → (geometry, insee)`, used
    by the legacy cahier-text resolver. The second is `insee → geometry`,
    used when we resolve communes via the INAO authoritative aires CSV
    (which gives INSEE codes directly, avoiding name-fuzzy-match work).
    The third is `insee → commune name`, used to render attribution
    strings for cadastre lieu-dit matches.
    """
    print(f"[load] {path.relative_to(ROOT)} ({path.stat().st_size // (1<<20)} MB)", file=sys.stderr)
    fc = json.loads(path.read_text(encoding="utf-8"))
    name_idx: dict[tuple[str, str], tuple[dict, str]] = {}
    insee_idx: dict[str, dict] = {}
    insee_to_name: dict[str, str] = {}
    for feat in fc["features"]:
        p = feat["properties"]
        name_idx[(p["codeDepartement"], normalize_commune(p["nom"]))] = (
            feat["geometry"], p["code"],
        )
        insee_idx[p["code"]] = feat["geometry"]
        insee_to_name[p["code"]] = p["nom"]
    return name_idx, insee_idx, insee_to_name


def cahier_insee(record: dict, commune_idx: dict) -> set[str]:
    """Resolve the cahier-extracted commune list to INSEE codes.

    Used as a hint for `lookup_aire` to disambiguate aires-CSV name
    collisions (Valençay wine vs chèvre): the wine cahier's commune set
    overlaps the wine IDA strongly and the cheese IDA barely. Returns
    an empty set when the cahier didn't list communes (Champagne and
    similar legal-deferred AOCs).
    """
    out: set[str] = set()
    by_dept = record.get("aire", {}).get("aire_geographique", {}) or {}
    for dept_name, communes in by_dept.items():
        dept_code = DEPT_NAME_TO_CODE.get(dept_name.replace("’", "'"))
        if not dept_code:
            continue
        for commune in communes:
            hit = commune_idx.get((dept_code, normalize_commune(commune)))
            if hit is not None:
                out.add(hit[1])
    return out


def union_for_appellation(record: dict, commune_idx: dict) -> tuple[object | None, dict]:
    """Resolve commune names → polygons → union (cahier-text path).

    Used as a fallback when neither parcellaire nor INAO aires CSV give
    us a direct geometry/INSEE list for this appellation.
    """
    matched = unmatched = 0
    geoms = []
    by_dept = record["aire"]["aire_geographique"]
    for dept_name, communes in by_dept.items():
        dept_code = DEPT_NAME_TO_CODE.get(dept_name.replace("’", "'"))
        if not dept_code:
            unmatched += len(communes)
            continue
        for commune in communes:
            key = (dept_code, normalize_commune(commune))
            hit = commune_idx.get(key)
            if hit is None:
                unmatched += 1
                continue
            geoms.append(shape(hit[0]))
            matched += 1
    if not geoms:
        return None, {"matched": matched, "unmatched": unmatched}
    return unary_union(geoms), {"matched": matched, "unmatched": unmatched}


def union_from_insee(insee_codes: set[str], insee_idx: dict[str, dict]) -> tuple[object | None, dict]:
    """Resolve INSEE codes (from the INAO aires CSV) → polygons → union."""
    matched = unmatched = 0
    geoms = []
    for code in insee_codes:
        geom = insee_idx.get(code)
        if geom is None:
            unmatched += 1
            continue
        geoms.append(shape(geom))
        matched += 1
    if not geoms:
        return None, {"matched": matched, "unmatched": unmatched}
    return unary_union(geoms), {"matched": matched, "unmatched": unmatched}


def _find_sibling_umbrella(
    name: str,
    siblings: list[tuple[str, object, object, str]] | None,
) -> tuple[object | None, object | None, str, str]:
    """Find the longest sibling DGC whose name strictly prefixes `name`.

    Returns (geom, village_geom, sibling_name, sibling_slug) — all blank
    when no match. Used to walk a Chablis premier cru lieu-dit up to the
    "Chablis premier cru" umbrella DGC's polygon, instead of the entire
    Chablis appellation.
    """
    if not siblings:
        return None, None, "", ""
    best: tuple[object, object, str, str] | None = None
    best_len = 0
    for sib_name, sib_geom, sib_v_geom, sib_slug in siblings:
        prefix = sib_name + " "
        if name.startswith(prefix) and len(sib_name) > best_len:
            best = (sib_geom, sib_v_geom, sib_name, sib_slug)
            best_len = len(sib_name)
    if best is None:
        return None, None, "", ""
    return best


@dataclass
class DGCGeomResult:
    """Outcome of `resolve_dgc_geometry()`. `source` is the wining strategy's
    label (`parcellaire-dgc`, `dgc-village-override`, `cadastre-lieu-dit-dgc`,
    `aires-csv-dgc`, `sibling-dgc`, `parent-appellation`, or `none`).
    `sib_*` and `cadastre_match` are populated only by their respective
    strategies; downstream consumers (v_geom resolution and MVT
    fallback_*/cadastre_* properties) read them keyed on `source`."""
    geom: object | None
    source: str
    stats: dict
    sib_v_geom: object | None = None
    sib_name: str = ""
    sib_slug: str = ""
    cadastre_match: dict | None = None


def resolve_dgc_geometry(
    record: dict,
    *,
    parcels_by_denom: dict,
    aires_by_app: dict,
    insee_idx: dict,
    commune_idx: dict,
    lieu_dit_index: LieuDitIndex,
    parent_geom_by_slug: dict,
    sibling_geom_by_id_app: dict,
) -> DGCGeomResult:
    """Resolve a DGC's detailed geometry by walking the priority chain:

      1. parcellaire-dgc — parcel-precise polygon keyed on id_denomination_geo
      2. dgc-village-override — hand-curated DGC_VILLAGE_INSEE table
      3. cadastre-lieu-dit-dgc — sub-commune climat in cadastre lieux-dits
         (Chablis premier-cru climats, Givry / Santenay premier cru, …)
      4. aires-csv-dgc — DGC's own row in INAO aires-communes CSV
      5. sibling-dgc — longest-prefix sibling DGC umbrella (Chablis premier
         cru X → "Chablis premier cru" umbrella, not whole Chablis)
      6. parent-appellation — inherit parent's polygon
      7. none — no geometry available

    Returns the first matching strategy's result; later strategies are
    not evaluated. Adding a fallback = inserting a guarded block at the
    right priority slot. Behavior matches the original 7-level cascade
    in main() exactly.
    """
    id_denom = record.get("id_denomination_geo") or ""
    parent_name = record.get("parent_name") or ""
    cahier_hint = cahier_insee(record, commune_idx)
    siblings = sibling_geom_by_id_app.get(record.get("id_appellation"))
    sib_geom, sib_v_geom, sib_name, sib_slug = _find_sibling_umbrella(record["name"], siblings)

    # 1. parcellaire-dgc
    parcel_feat = parcels_by_denom.get(id_denom) if id_denom else None
    if parcel_feat is not None:
        return DGCGeomResult(
            geom=shape(parcel_feat["geometry"]),
            source="parcellaire-dgc",
            stats={"matched": -1, "unmatched": 0},
        )

    # 2. dgc-village-override
    override_insee = DGC_VILLAGE_INSEE.get(id_denom)
    if override_insee:
        geom, stats = union_from_insee(override_insee, insee_idx)
        if geom is not None and not geom.is_empty:
            return DGCGeomResult(geom=geom, source="dgc-village-override", stats=stats)

    parent_aires_insee = (
        lookup_aire(aires_by_app, parent_name, cahier_hint) if parent_name else None
    )

    # 3. cadastre-lieu-dit-dgc — sub-commune climat resolution. Strip the
    #    parent / sibling-umbrella prefix before matching so "Chablis premier
    #    cru Vaillons" looks up as "Vaillons" inside Chablis.
    climat_name = derive_climat_name(
        record["name"], parent_name=parent_name, umbrella_name=sib_name,
    )
    cadastre_match = lieu_dit_index.resolve(
        climat_name, parent_aires_insee, id_denom=id_denom,
    )
    if cadastre_match is not None:
        return DGCGeomResult(
            geom=cadastre_match["geom"],
            source="cadastre-lieu-dit-dgc",
            stats={"matched": -1, "unmatched": 0},
            cadastre_match=cadastre_match,
        )

    # 4. aires-csv-dgc — but first drop substring matches that round-trip
    #    to the parent or to the sibling umbrella (those are not informative;
    #    they signal the DGC has no row of its own and the lookup_aire
    #    len≥6 fallback latched onto a containing row instead).
    dgc_aires_insee = lookup_aire(aires_by_app, record["name"], cahier_hint)
    if dgc_aires_insee and parent_aires_insee == dgc_aires_insee:
        dgc_aires_insee = None
    if dgc_aires_insee and sib_name:
        sib_aires_insee = lookup_aire(aires_by_app, sib_name, cahier_hint)
        if sib_aires_insee == dgc_aires_insee:
            dgc_aires_insee = None
    if dgc_aires_insee:
        geom, stats = union_from_insee(dgc_aires_insee, insee_idx)
        if geom is not None and not geom.is_empty:
            return DGCGeomResult(geom=geom, source="aires-csv-dgc", stats=stats)

    # 5. sibling-dgc — umbrella DGC's polygon, when one exists.
    if sib_geom is not None:
        return DGCGeomResult(
            geom=sib_geom,
            source="sibling-dgc",
            stats={"matched": -1, "unmatched": 0},
            sib_v_geom=sib_v_geom,
            sib_name=sib_name,
            sib_slug=sib_slug,
        )

    # 6. parent-appellation — inherit. Parents are processed before DGCs,
    #    so parent_geom_by_slug already holds it.
    parent_slug = record.get("parent_slug") or ""
    parent_geom = parent_geom_by_slug.get(parent_slug)
    if parent_geom is not None:
        return DGCGeomResult(
            geom=parent_geom,
            source="parent-appellation",
            stats={"matched": -1, "unmatched": 0},
        )

    # 7. none
    return DGCGeomResult(geom=None, source="none", stats={"matched": 0, "unmatched": 0})


def _resolve_es_igp_fallback(record: dict, es_polygons: ESPolygonIndex):
    """Resolve geometry for ES wines that miss Figshare (mostly IGPs +
    a handful of post-Nov-2021 PDOs). Patterns tried in order:

      1. **Province-wide** — pliego says "todos los términos municipales
         de las provincias de X y Y" (Extremadura). Union all GISCO
         municipios in those provinces.
      2. **CCAA-wide** — "totalidad de los municipios de la Comunidad
         Autónoma de Castilla y León". Union all province INEs of that
         CCAA.
      3. **Island-wide** — "toda la isla de Mallorca" (Balearic IGPs
         like Mallorca / Menorca / Serra de Tramuntana).
      4. **Commune-list** — pliego enumerates a flat commune list
         (Ribeiras do Morrazo, Barbanza e Iria, Bajo Aragón). Union the
         matching GISCO municipios.

    Each pattern is tried against a chain of candidate texts:
    `geo_area_brief` first (the canonical stage-02 routed field), then
    `sections["9"]` (the EU 2024 single-document "Definición breve de
    la zona geográfica delimitada" section — sometimes mis-routed by
    stage 02 when section titles collide, e.g. Mallorca / Ribeiras do
    Morrazo).

    LAST RESORT — **wine-name → province**: when nothing else fires,
    look up the wine's `name` (and the bracketed-form fallback strip)
    against `PROVINCE_TO_INE`. Spanish-national-format pliegos for
    province-named IGPs (Castelló) sometimes describe the geographic
    area in pure prose without listing communes or saying "todos los
    municipios de la provincia" — the IGP-covers-the-whole-province
    relationship is implicit in the name. The wine's name must match
    a known Spanish province (or co-official alias) exactly.

    Returns (geom, source_label, stats) or (None, "none", {}) when
    nothing fires."""
    geo = record.get("geo_area_brief") or ""
    sec9 = (record.get("sections") or {}).get("9") or ""

    # Try the routed field first, then section 9. Stop on the first
    # candidate that actually returns a non-empty polygon.
    candidates = [c for c in (geo, sec9) if c]
    if not candidates:
        slug = record.get("slug", "?")
        print(f"[no-commune-match] {slug}: empty geo_area_brief and section 9", file=sys.stderr)
        return None, "none", {"matched": 0, "unmatched": 0}

    for text in candidates:
        provinces = parse_province_wide_list(text)
        if provinces:
            ines = [PROVINCE_TO_INE.get(p) for p in provinces if PROVINCE_TO_INE.get(p)]
            if ines:
                geom, stats = es_polygons.union_provinces(ines)
                if geom is not None and not geom.is_empty:
                    return geom, "gisco-province-wide", {
                        "matched": stats.get("n_municipios", -1), "unmatched": 0,
                    }

        ccaa = parse_ccaa_wide(text)
        if ccaa:
            ines = list(CCAA_TO_PROVINCE_INES.get(ccaa, ()))
            if ines:
                geom, stats = es_polygons.union_provinces(ines)
                if geom is not None and not geom.is_empty:
                    return geom, "gisco-ccaa-wide", {
                        "matched": stats.get("n_municipios", -1), "unmatched": 0,
                    }

        # Balearic islands: pliego says "toda la isla de Mallorca" /
        # "todos los municipios de la isla de Menorca" / etc. GISCO LAU
        # has no per-island metadata, so we lean on the curated INE-list-
        # per-island in `_lib/es/baleares.py` (bbox-classified once from
        # the LAU geometry).
        island = parse_island_wide(text)
        if island:
            island_ines = list(ines_for_island(island))
            if island_ines:
                polys = []
                for ine in island_ines:
                    cand = es_polygons._munis_by_ine.get(ine)
                    if cand and not cand.geom.is_empty:
                        polys.append(cand.geom)
                if polys:
                    return unary_union(polys), "gisco-island-wide", {
                        "matched": len(polys), "unmatched": 0,
                    }

        communes = parse_commune_list(text)
        if communes:
            geom, stats = es_polygons.union_communes(communes)
            if geom is not None and not geom.is_empty:
                return geom, "gisco-commune-list", stats

    # Last resort: wine-name → province. The IGP/DOP covers the whole
    # province by name (Castelló = Castellón province). Matched against
    # PROVINCE_TO_INE's full alias list (Spanish + co-official forms).
    name = (record.get("name") or "").strip()
    ine = PROVINCE_TO_INE.get(name)
    if ine:
        geom, stats = es_polygons.union_provinces([ine])
        if geom is not None and not geom.is_empty:
            slug = record.get("slug", "?")
            print(
                f"[gisco-province-by-name] {slug}: name={name!r} → INE {ine} "
                f"(no commune list anywhere; province-wide by name)",
                file=sys.stderr,
            )
            return geom, "gisco-province-by-name", {
                "matched": stats.get("n_municipios", -1), "unmatched": 0,
            }

    slug = record.get("slug", "?")
    print(
        f"[no-commune-match] {slug}: "
        f"geo_area_brief={len(geo)} chars, section9={len(sec9)} chars, "
        f"no province/ccaa/island/commune-list/name-province pattern fired",
        file=sys.stderr,
    )
    return None, "none", {"matched": 0, "unmatched": 0}


def _resolve_es_sigpac(
    record: dict, sigpac: SigpacIndex, es_polygons: ESPolygonIndex,
):
    """Hybrid SIGPAC + GISCO whole-commune resolver for ES wine records
    that have polygon-list inclusions in their pliego.

    The hybrid is **only invoked when polygon-list inclusions exist**
    (Priorat / Montsant pattern: pliego enumerates SIGPAC polygon
    numbers within shared communes). Wines without polygon-list
    inclusions fall through to Figshare which is more reliable for the
    PDO commune-precision polygon — running our whole-commune-prefix
    parser unconditionally would over-trigger on noisy text (Rioja's
    subzona ALL-CAPS headers parsed as commune names, etc.).

    When polygon-list inclusions ARE present, two passes union into one
    appellation footprint:

      1. **Whole-commune prefix** (the 9 fully-included Priorat
         communes / 12 fully-included Montsant communes) → union of
         GISCO LAU commune polygons.
      2. **Polygon-list inclusions** (Falset: polígonos 1, 4, 5, 6, 7,
         21, 25 enteros) → union of SIGPAC vineyard parcels at
         polygon-precision.

    Returns None when there are no polygon-list inclusions or when
    SIGPAC isn't loaded for the relevant comarca."""
    if not sigpac.n_comarques:
        return None
    geo = record.get("geo_area_brief") or ""
    if not geo:
        return None

    inclusions = parse_polygon_inclusions(geo)
    if not inclusions:
        return None

    polys = []

    # Whole-commune prefix → GISCO union (supplements polygon-list when
    # the pliego mixes both patterns).
    whole_communes = parse_whole_commune_prefix(geo)
    if whole_communes:
        gc_geom, _ = es_polygons.union_communes(whole_communes)
        if gc_geom is not None and not gc_geom.is_empty:
            polys.append(gc_geom)

    # Polygon-list inclusions → SIGPAC union
    for inc in inclusions:
        g = sigpac.polygons_in_municipi(inc.municipio_norm, inc.polygon_numbers)
        if g is not None and not g.is_empty:
            polys.append(g)

    if not polys:
        return None
    return unary_union(polys)
