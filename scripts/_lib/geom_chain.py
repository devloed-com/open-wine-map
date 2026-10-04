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
    parse_parroquia_inclusions,
    parse_province_wide_list,
    parse_whole_commune_prefix,
)
from _lib.es.geometry import ESPolygonIndex
from _lib.es.parroquia import GALICIA_PROVINCES, ESParroquiaIndex
from _lib.es.pliego_parcels import parse_polygon_inclusions
from _lib.es.region import CCAA_TO_PROVINCE_INES, PROVINCE_TO_INE
from _lib.es.sigpac import (
    SIGPAC_SEMANTICS_FOOTPRINT,
    SIGPAC_SOURCES,
    SigpacIndex,
    inclusion_semantics,
)
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


# Slug-keyed provenance of the SIGPAC polígonos drawn for a record, written
# by `_resolve_es_sigpac` and read by `_sources_for()` in stage 04, the way
# `ES_PARROQUIA_PROVENANCE` is: which reading applied, the polígonos listed
# and found per municipio, the whole municipios beside them, and the
# publication's attribution for the panel line.
ES_SIGPAC_PROVENANCE: dict[str, dict] = {}


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
         21, 25 enteros) → per `inclusion_semantics(slug)`, the union of
         the SIGPAC vineyard parcels inside those polígonos (Priorat /
         Montsant) or of the polígonos taken whole (the default: a plot
         planted inside a listed polígono qualifies, so Sierra Sur de
         Jaén's vine-less sierra polígonos are drawn, not four plots).

    Returns None when there are no polygon-list inclusions or when no
    inclusion resolves against the loaded SIGPAC data: the result is
    labelled parcel-precise, so a whole-commune union alone (a pliego
    whose polígonos sit in a province that is not fetched) must fall
    through to the zone / commune-list resolvers instead."""
    if not sigpac.n_comarques:
        return None
    geo = record.get("geo_area_brief") or ""
    if not geo:
        return None

    inclusions = parse_polygon_inclusions(geo)
    if not inclusions:
        return None

    slug = record.get("slug") or ""
    semantics = inclusion_semantics(slug)
    polys = []

    # Whole-commune prefix → GISCO union (supplements polygon-list when
    # the pliego mixes both patterns).
    whole_communes = parse_whole_commune_prefix(geo)
    whole_matched = 0
    if whole_communes:
        gc_geom, gc_stats = es_polygons.union_communes(whole_communes)
        if gc_geom is not None and not gc_geom.is_empty:
            polys.append(gc_geom)
            whole_matched = gc_stats.get("matched", 0)

    # Polygon-list inclusions → SIGPAC union
    sigpac_hits = 0
    municipios = []
    publications: set[str] = set()
    for inc in inclusions:
        if semantics == SIGPAC_SEMANTICS_FOOTPRINT:
            g, found = sigpac.polygon_footprints_in_municipi(
                inc.municipio_norm, inc.polygon_numbers,
            )
        else:
            g = sigpac.polygons_in_municipi(inc.municipio_norm, inc.polygon_numbers)
            found = sigpac.vineyard_polygons_present(inc.municipio_norm, inc.polygon_numbers)
        if g is not None and not g.is_empty:
            polys.append(g)
            sigpac_hits += 1
            publications.add(sigpac.municipio_publication(inc.municipio_norm) or "")
        municipios.append({
            "name": inc.municipio,
            "listed": len(inc.polygon_numbers),
            "found": len(found),
        })

    if not sigpac_hits:
        return None
    ES_SIGPAC_PROVENANCE[slug] = {
        "semantics": semantics,
        "municipios": municipios,
        "whole": list(whole_communes),
        "whole_matched": whole_matched,
        "sources": [dict(SIGPAC_SOURCES[k]) for k in sorted(publications) if k in SIGPAC_SOURCES],
    }
    print(
        f"[sigpac] {slug}: {semantics} — "
        + ", ".join(f"{m['name']} {m['found']}/{m['listed']} polígonos" for m in municipios)
        + (f", {whole_matched}/{len(whole_communes)} whole municipios" if whole_communes else ""),
        file=sys.stderr,
    )
    return unary_union(polys)


# ---------------------------------------------------------------------------
# ES parroquia inclusions (Galicia) — sub-municipal step after the
# whole-municipio union.
# ---------------------------------------------------------------------------

# Slug-keyed provenance of the parishes drawn for a record, written by
# `apply_es_parroquias` and read by `_sources_for()` in stage 04 (the
# panel-blob phase re-reads the on-disk JSON, which carries no geometry
# provenance) — the same shape as the augmenters' caches in
# `_lib/augment/_shared.py`. The IET attribution is rendered from it.
ES_PARROQUIA_PROVENANCE: dict[str, dict] = {}

# Whole-municipio sources a parish inclusion refines. A Bétard polygon or
# a sub-municipal MAPA zone is left alone: it is a delimitation, not a
# commune union (a whole-municipio MAPA zone is the exception, below).
# `parent-appellation` / `none` are the sub-denominations and records that
# had no polygon of their own — their parishes become the polygon.
_ES_PARROQUIA_BASE_SOURCES = frozenset({
    "gisco-commune-list", "gisco-commune-union-subzona", "geometry-research-municipios",
})
_ES_PARROQUIA_EMPTY_SOURCES = frozenset({"none", "parent-appellation"})
ES_PARROQUIA_ONLY_SOURCE = "iet-parroquia-union"

# A MAPA zone drawn at whole-municipio resolution — every GISCO municipio it
# touches covered whole or barely grazed — is a commune union in the
# ministry's hand and carries nothing the pliego lacks; where the pliego
# names parishes, they are the finer statement of the same delimitation, so
# the zone is redrawn from them (whole municipios from GISCO, parishes from
# the IET). Monterrei, 2026-09-27 (visitor boundary flag): the layer painted
# six whole municipios where the 2025 pliego names 59 parishes of eight —
# seven mountain parishes of Castrelo do Val and Riós it excludes (~111 km²)
# were drawn, the six of Cualedro and Laza that amendment PDO-ES-A1114-AM03
# added (~79 km²) were missing, and the Ladera subzona spilled outside its
# parent. The redraw needs the text to account for every municipio of the
# zone, to name no unit below the parish (Ribeiro's "lugares" of Toén and
# Ourense would turn over-drawing into under-drawing) and every parish to
# resolve; a zone with a partially covered municipio is a real delimitation.
# Otherwise the zone is kept and the reason logged.
_ES_PARROQUIA_ZONE_SOURCES = frozenset({"mapa-zone"})
_ZONE_WHOLE_SHARE = 0.95
_ZONE_GRAZE_SHARE = 0.05
_SUB_PARISH_UNIT_RE = re.compile(
    r"\b(?:lugar(?:es)?|pueblos?|aldeas?|n[úu]cleos?|entidad(?:es)? singular(?:es)?)\b",
    re.IGNORECASE,
)

_es_parroquia_index_default: ESParroquiaIndex | None = None
_es_parroquia_missing_logged = False


def _es_parroquia_index() -> ESParroquiaIndex:
    global _es_parroquia_index_default
    if _es_parroquia_index_default is None:
        _es_parroquia_index_default = ESParroquiaIndex()
    return _es_parroquia_index_default


_SUBZONA_HEADER_RE = r"(?:^|\n)\s*(?:[—\-]\s*|[a-z]\)\s*)?Subzona\s+(?:de\s+)?"


def _es_subzona_geo_text(record: dict) -> str:
    """The subzona's own block of the parent's delimitation ("Subzona ladera
    de Monterrei: … ." up to the next "Subzona"). A subzona record's
    `geo_area_brief` is the extractor's comma-split commune list, which
    drops the holder phrases, so the parishes are read from the parent
    text the record still carries in `sections`."""
    name = re.escape((record.get("name") or "").strip())
    if not name:
        return ""
    for text in _es_geo_texts(record, include_brief=False):
        m = re.search(_SUBZONA_HEADER_RE + name + r"\s*:", text, re.IGNORECASE)
        if not m:
            continue
        rest = text[m.end():]
        nxt = re.search(_SUBZONA_HEADER_RE + r"\S", rest, re.IGNORECASE)
        return rest[: nxt.start()] if nxt else rest
    return ""


def _es_geo_texts(record: dict, *, include_brief: bool = True) -> list[str]:
    """The record's delimitation texts, most canonical first: the routed
    `geo_area_brief`, the full routed section, then section 9 (the same
    chain `_resolve_es_igp_fallback` walks)."""
    out: list[str] = []
    if include_brief:
        out.append(record.get("geo_area_brief") or "")
    sections = record.get("sections") or {}
    role = (record.get("section_roles") or {}).get("geo_area")
    if isinstance(role, str):
        out.append(sections.get(role) or "")
    out.append(sections.get("9") or "")
    seen: set[str] = set()
    texts: list[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            texts.append(t)
    return texts


def _es_municipio_ine(
    es_polygons: ESPolygonIndex, index: ESParroquiaIndex, slug: str, name: str,
) -> str | None:
    """INE of a pliego municipio, exact match only — never the first-word
    fallback, which is a guess. A name that GISCO carries in several
    provinces (Sada: A Coruña / Navarra) is kept only when exactly one
    lies in Galicia; then the layer's own `CONCELLO` spelling; then a
    curator `_municipios` pin (a merged municipio's old name)."""
    cands, exact = es_polygons._lookup_candidates(name)
    if exact:
        ines = [c.ine for c in cands if c.province in GALICIA_PROVINCES]
        if len(ines) == 1 and index.has_concello(ines[0]):
            return ines[0]
    ine = index.ine_for_concello(name)
    if ine:
        return ine
    ine = index.municipio_override(slug, name)
    if ine and index.has_concello(ine):
        return ine
    return None


def apply_es_parroquias(
    record: dict,
    es_polygons: ESPolygonIndex,
    geom,
    geom_source: str,
    stats: dict,
    *,
    index: ESParroquiaIndex | None = None,
):
    """Refine a resolved ES geometry with the parishes its pliego names
    ("las parroquias de Iria Flavia y Padrón, del término municipal de
    Padrón"): each named parish is drawn from the IET Mapa de Parroquias
    inside its municipio (resolved to an INE exactly), a municipio named
    only as a parish holder is never kept whole (it is subtracted from a
    curator / subzona union that carried it), and a whole-municipio
    inclusion written beside the parishes ("la totalidad del municipio de
    Negueira de Muñiz") is unioned from GISCO. Returns (geom, geom_source,
    stats) — unchanged when the record is not a commune union, names no
    parishes, or the layer is absent. `geom_source` is kept; a record that
    had no polygon of its own becomes `iet-parroquia-union`, and so does a
    MAPA zone drawn at whole-municipio resolution that the parishes restate
    (`_ES_PARROQUIA_ZONE_SOURCES`). Provenance goes to
    `ES_PARROQUIA_PROVENANCE[slug]` for the panel attribution."""
    global _es_parroquia_missing_logged
    if record.get("country") != "es" or record.get("stub"):
        return geom, geom_source, stats
    has_geom = geom is not None and not geom.is_empty
    has_base = has_geom and geom_source in _ES_PARROQUIA_BASE_SOURCES
    zone = has_geom and geom_source in _ES_PARROQUIA_ZONE_SOURCES
    if not has_base and not zone and geom_source not in _ES_PARROQUIA_EMPTY_SOURCES:
        return geom, geom_source, stats
    slug = record.get("slug") or "?"
    if record.get("is_sub_denomination"):
        texts = [_es_subzona_geo_text(record)]
    else:
        texts = _es_geo_texts(record)
    inclusions: list[dict] = []
    used_text = ""
    for text in texts:
        inclusions = parse_parroquia_inclusions(text)
        if inclusions:
            used_text = text
            break
    if not inclusions:
        return geom, geom_source, stats
    index = index or _es_parroquia_index()
    if not index.has_data:
        if not _es_parroquia_missing_logged:
            _es_parroquia_missing_logged = True
            print(
                f"[parroquias] {index.zip_path} missing — run "
                "scripts/es/00_fetch_data.py; parish inclusions left undrawn",
                file=sys.stderr,
            )
        return geom, geom_source, stats

    matched: list[str] = []
    unmatched: list[str] = []
    municipios_unmatched: list[str] = []
    whole: list[str] = []
    holder_geoms = []
    whole_geoms = []
    parts = []
    named_ines: set[str] = set()
    for inc in inclusions:
        muni = inc["municipio"]
        ine = _es_municipio_ine(es_polygons, index, slug, muni)
        if ine is None:
            municipios_unmatched.append(muni)
            continue
        named_ines.add(ine)
        if inc.get("whole"):
            cand = es_polygons._munis_by_ine.get(ine)
            if cand is not None:
                parts.append(cand.geom)
                whole_geoms.append(cand.geom)
                whole.append(muni)
            continue
        pgeom, pstats = index.union_parroquias(ine, inc["parroquias"], slug)
        matched.extend(f"{muni}: {n}" for n in pstats["matched"])
        unmatched.extend(f"{muni}: {n}" for n in pstats["unmatched"])
        if pgeom is not None and not pgeom.is_empty:
            parts.append(pgeom)
            cand = es_polygons._munis_by_ine.get(ine)
            if cand is not None:
                holder_geoms.append(cand.geom)
    zone_municipios: list[str] = []
    if zone:
        keep = _es_zone_keep_reason(
            es_polygons, geom, used_text, named_ines, municipios_unmatched, unmatched,
        )
        if keep is not None:
            print(f"[parroquias] {slug}: MAPA zone kept — {keep}", file=sys.stderr)
            return geom, geom_source, stats
        zone_municipios, _partial = es_polygons.municipios_covered(
            geom, whole=_ZONE_WHOLE_SHARE, graze=_ZONE_GRAZE_SHARE,
        )
    ES_PARROQUIA_PROVENANCE[slug] = {
        "matched": matched,
        "unmatched": unmatched,
        "municipios_unmatched": municipios_unmatched,
        "whole_municipios": whole,
    }
    if zone:
        ES_PARROQUIA_PROVENANCE[slug]["zone_superseded"] = geom_source
        print(
            f"[parroquias] {slug}: {geom_source} drawn at whole-municipio resolution "
            f"({len(zone_municipios)} municipios) redrawn from the pliego",
            file=sys.stderr,
        )
    print(
        f"[parroquias] {slug}: {len(matched)} parish(es) drawn, {len(unmatched)} unmatched"
        + (f" ({'; '.join(unmatched)})" if unmatched else "")
        + (f", municipio(s) unresolved: {', '.join(municipios_unmatched)}"
           if municipios_unmatched else ""),
        file=sys.stderr,
    )
    if not parts:
        return geom, geom_source, stats
    parts = [_drop_islets(g) for g in parts]
    new_stats = dict(stats)
    new_stats["parroquias"] = {"matched": len(matched), "unmatched": len(unmatched)}
    # A subzona delimited by parishes: its `subzona_communes` are the
    # comma-split of this same block, so every whole municipio that union
    # yielded is a holder phrase or a fragment ("San Cibrao del ayuntamiento
    # de Oímbra" bound San Cibrao das Viñas, 60 km away). The block's own
    # whole inclusions and parishes replace it.
    if has_base and record.get("is_sub_denomination"):
        has_base = False
    if zone:
        new_stats["matched"] = len(whole)
        new_stats["unmatched"] = 0
        return unary_union(parts), ES_PARROQUIA_ONLY_SOURCE, new_stats
    if has_base:
        # `matched` stays the count of whole municipios drawn: a holder the
        # base carried whole leaves it, a whole inclusion it lacked joins it.
        in_base = [g for g in holder_geoms if _mostly_inside(g, geom)]
        n_whole_new = sum(1 for g in whole_geoms if not _mostly_inside(g, geom))
        base = geom.difference(unary_union(in_base)) if in_base else geom
        new_stats["matched"] = (
            max(int(stats.get("matched") or 0), 0) - len(in_base) + n_whole_new
        )
        return unary_union([base, *parts]), geom_source, new_stats
    new_stats["matched"] = len(whole)
    new_stats["unmatched"] = 0
    return unary_union(parts), ES_PARROQUIA_ONLY_SOURCE, new_stats


def _mostly_inside(part, whole_geom) -> bool:
    return part.area > 0 and part.intersection(whole_geom).area > 0.5 * part.area


def _es_zone_keep_reason(
    es_polygons: ESPolygonIndex,
    zone_geom,
    text: str,
    named_ines: set[str],
    municipios_unmatched: list[str],
    unmatched: list[str],
) -> str | None:
    """Why a MAPA zone stays as drawn instead of being redrawn from the
    parishes its pliego names — None when the redraw is safe: the text
    names nothing below the parish, every municipio and parish resolved,
    the zone covers no municipio in part, and every municipio it covers
    whole is one the text names (as a parish holder or whole)."""
    m = _SUB_PARISH_UNIT_RE.search(text)
    if m:
        return f"the text names a unit below the parish ({m.group(0)!r})"
    if municipios_unmatched:
        return f"municipio(s) unresolved: {', '.join(municipios_unmatched)}"
    if unmatched:
        return f"parish(es) unmatched: {'; '.join(unmatched)}"
    whole, partial = es_polygons.municipios_covered(
        zone_geom, whole=_ZONE_WHOLE_SHARE, graze=_ZONE_GRAZE_SHARE,
    )

    def names(ines: list[str]) -> str:
        return ", ".join(es_polygons.municipio_name(i) or i for i in ines)

    if partial:
        return f"the zone covers {names(partial)} in part — finer than the municipio"
    if not whole:
        return "the zone covers no municipio whole"
    unnamed = [i for i in whole if i not in named_ines]
    if unnamed:
        return f"municipio(s) of the zone the text does not name: {names(unnamed)}"
    return None


# The IET coastline (1:5,000) carries every offshore rock of a coastal
# parish as its own polygon — Porto do Son's six parishes bring a dozen
# parts under 100 m². Parts under a hectare are dropped so the record's
# outline paint (`parts`) is not driven by them; nothing a vine grows on.
_MIN_PART_DEG2 = 0.01 / 12_000  # ~1 ha at Galicia's latitude, in deg²


def _drop_islets(geom):
    if not hasattr(geom, "geoms"):
        return geom
    kept = [g for g in geom.geoms if g.area >= _MIN_PART_DEG2]
    if not kept or len(kept) == len(geom.geoms):
        return geom
    return unary_union(kept)
