"""Build the appellation map.

Pipeline stage 04.

For every extracted appellation (`raw/inao/cahier-extracted/*.json`), look up
each commune in the IGN AdminExpress geojson and union their polygons into a
single feature. Write the resulting FeatureCollection to
`wiki/map-data/appellations.geojson`, run tippecanoe to produce
`appellations.pmtiles`, and emit `wiki/index.html` (EN canonical = the
homepage; the map is the front door) plus `wiki/<lang>/index.html` for
`lang ∈ {fr, es, nl}`, rendering them with MapLibre + the PMTiles protocol.

Re-runnable: outputs are overwritten; intermediate results (per-appellation
geometry sha) could be cached, but the full pass takes <1 minute on a
modern machine and isn't worth memoising for now.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from tqdm import tqdm

from _lib.aires import load_aires, lookup as lookup_aire
from _lib.aoc_translations import (
    load_summary_translations,
    load_terroir_facts_translations,
)
from _lib.appellation_urls import load as load_appellation_urls, resolve as resolve_appellation_url
from _lib.dgc_village_overrides import DGC_VILLAGE_INSEE
from _lib.i18n import LOCALES, compile_catalogs
from _lib.lieu_dit import LieuDitIndex, derive_climat_name
from _lib.map_template import render as render_map_html
from _lib.parcellaire import build_aoc_polygons
from _lib.summaries import derive_summary, summary_sha
from _lib.wiki import is_grape_summary

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
COMMUNES_GEOJSON = ROOT / "raw" / "ign" / "communes.geojson"
WIKI = ROOT / "wiki"
SITE_BASE_URL = "https://www.openwinemap.com"
MAP_DATA = WIKI / "map-data"
GEOJSON_OUT = MAP_DATA / "appellations.geojson"
PMTILES_OUT = MAP_DATA / "appellations.pmtiles"
GEOJSON_VILLAGES_OUT = MAP_DATA / "appellations-villages.geojson"
PMTILES_VILLAGES_OUT = MAP_DATA / "appellations-villages.pmtiles"
LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes"
STYLE_LEXICON_DIR = ROOT / "raw" / "wikipedia" / "styles"


_DISAMBIG_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")

# Simple-mode style buckets: collapses the 16 fine-grained INAO style tags into
# the 6 buckets the default view shows. Keys are fine-grained slugs (matches
# the set in scripts/_lib/map_template.build_style_labels); values are the
# simplified bucket. Anything not listed here falls into "other".
SIMPLE_STYLE_BUCKETS: dict[str, str] = {
    "red": "red",
    "clairet": "red",
    "primeur": "red",
    "white": "white",
    "rose": "rose",
    "sparkling": "sparkling",
    "cremant": "sparkling",
    "sweet": "sweet",
    "vdn": "sweet",
    "vin-de-liqueur": "sweet",
    "vin-jaune": "sweet",
    "vin-de-paille": "sweet",
    "vendanges-tardives": "sweet",
    "grains-nobles": "sweet",
}


def load_grape_lexicon(lang: str, max_chars: int = 280) -> dict:
    """Load Wikipedia grape data for a locale; returns {slug: {name, extract?,
    page_url?, revision_id?, thumbnail?}} for any entry that has at least a
    `wikipedia_title` (so a localised display name is available even when
    the article summary is filtered out). Truncates `extract` to ~max_chars
    at the nearest sentence boundary when present.

    Wikipedia titles often include a parenthetical disambiguator —
    "Pinot noir (cépage)", "Mauzac (grape)" — which is article-DB hygiene,
    not how the variety is referenced in the wine world. Strip it for
    display so the chip reads cleanly."""
    lang_dir = LEXICON_DIR / lang
    if not lang_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for f in lang_dir.glob("*.json"):
        d = json.loads(f.read_text())
        if d.get("missing") or d.get("error"):
            continue
        title = (d.get("wikipedia_title") or "").strip()
        if not title:
            continue
        display_name = _DISAMBIG_SUFFIX.sub("", title).strip() or title
        entry: dict = {
            "name": display_name,
            "page_url": d.get("page_url"),
        }
        extract = (d.get("extract") or "").strip()
        if extract and is_grape_summary(lang, d.get("description", ""), extract):
            if len(extract) > max_chars:
                cut = extract[:max_chars].rsplit(". ", 1)[0]
                extract = cut + ("." if not cut.endswith(".") else "") + " […]"
            entry["extract"] = extract
            entry["revision_id"] = d.get("revision_id")
            if d.get("thumbnail"):
                entry["thumbnail"] = d.get("thumbnail")
        out[d["slug"]] = entry
    return out


def merge_grape_lexicon(lang_lex: dict, fr_lex: dict) -> dict:
    """For any slug in `fr_lex` missing from `lang_lex`, fill in the FR
    entry and tag it with `lang_fallback=True` so the UI can render a
    "(français)" hint. The localised name is preserved when the entry was
    already present (even if its `extract` was missing — a partial
    fallback is marked via the FR extract being copied in)."""
    if lang_lex is fr_lex:
        return lang_lex
    out: dict[str, dict] = {}
    for slug, fr_entry in fr_lex.items():
        local = lang_lex.get(slug)
        if local is None:
            merged = dict(fr_entry)
            merged["lang_fallback"] = True
            out[slug] = merged
        else:
            merged = dict(local)
            if "extract" not in merged and "extract" in fr_entry:
                merged["extract"] = fr_entry["extract"]
                if "thumbnail" not in merged and "thumbnail" in fr_entry:
                    merged["thumbnail"] = fr_entry["thumbnail"]
                merged["lang_fallback"] = True
            out[slug] = merged
    for slug, local in lang_lex.items():
        out.setdefault(slug, local)
    return out


def load_style_lexicon(lang: str, max_chars: int = 320) -> dict:
    """Load Wikipedia style data for a locale; returns
    {slug: {extract, page_url, revision_id, thumbnail?}} for each curated
    style entry that successfully fetched. Truncates `extract` to ~max_chars
    at the nearest sentence boundary.

    Unlike the grape lexicon there is no positive-keyword filter: each slug
    is bound by hand to a Wikipedia title in `style_overrides.json`, so a
    successful fetch is by construction the right article."""
    lang_dir = STYLE_LEXICON_DIR / lang
    if not lang_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for f in lang_dir.glob("*.json"):
        d = json.loads(f.read_text())
        if d.get("missing") or d.get("error"):
            continue
        extract = (d.get("extract") or "").strip()
        if not extract:
            continue
        if len(extract) > max_chars:
            cut = extract[:max_chars].rsplit(". ", 1)[0]
            extract = cut + ("." if not cut.endswith(".") else "") + " […]"
        entry: dict = {
            "extract": extract,
            "page_url": d.get("page_url"),
            "revision_id": d.get("revision_id"),
        }
        if d.get("thumbnail"):
            entry["thumbnail"] = d.get("thumbnail")
        out[d["slug"]] = entry
    return out


def merge_style_lexicon(lang_lex: dict, fr_lex: dict) -> dict:
    """Same FR-fallback pattern as `merge_grape_lexicon`."""
    if lang_lex is fr_lex:
        return lang_lex
    out: dict[str, dict] = {}
    for slug, fr_entry in fr_lex.items():
        local = lang_lex.get(slug)
        if local is None:
            merged = dict(fr_entry)
            merged["lang_fallback"] = True
            out[slug] = merged
        else:
            out[slug] = dict(local)
    for slug, local in lang_lex.items():
        out.setdefault(slug, local)
    return out


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
    fc = json.loads(path.read_text())
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


def _join_set(values: list[str]) -> str:
    """Encode a slug list as ';value1;value2;' for MapLibre `in` filtering."""
    if not values:
        return ""
    return ";" + ";".join(values) + ";"


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


def _geojson_bounds(g: dict) -> tuple[float, float, float, float]:
    """Pure-Python bbox over a GeoJSON geometry — avoids parsing into a
    shapely object just to read its envelope. Used for cheap bbox
    pre-filtering when scanning all 34k communes for a needle polygon."""
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    def walk(o):
        nonlocal minx, miny, maxx, maxy
        if isinstance(o[0], (int, float)):
            x, y = o[0], o[1]
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
        else:
            for c in o:
                walk(c)

    walk(g["coordinates"])
    return minx, miny, maxx, maxy


def communes_containing(needle, insee_idx: dict[str, dict]) -> set[str]:
    """Return the INSEE codes of every IGN commune intersecting `needle`.

    Used as a fallback when the INAO aires-CSV INSEE codes resolve to
    zero IGN matches — usually a sign of an INSEE commune merger that
    INAO hasn't picked up. Bbox-prefilters before paying for the full
    polygon intersect.
    """
    px0, py0, px1, py1 = needle.bounds
    out: set[str] = set()
    for code, gd in insee_idx.items():
        cx0, cy0, cx1, cy1 = _geojson_bounds(gd)
        if cx1 < px0 or cx0 > px1 or cy1 < py0 or cy0 > py1:
            continue
        if shape(gd).intersects(needle):
            out.add(code)
    return out


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


def main() -> int:
    if not COMMUNES_GEOJSON.exists():
        print("error: IGN communes geojson missing — run scripts/00_fetch_data.py", file=sys.stderr)
        return 1
    if not EXTRACTED.exists():
        print("error: extracted cahiers missing — run scripts/02_extract_cahiers.py", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-tippecanoe", action="store_true", help="skip pmtiles generation (geojson only)")
    ap.add_argument("--no-parcellaire", action="store_true", help="skip parcellaire shapefile (commune unions only)")
    ap.add_argument(
        "--rebuild-parcellaire", action="store_true",
        help="rebuild the parcellaire AOC-polygon cache from the source shapefile",
    )
    ap.add_argument(
        "--no-translations", action="store_true",
        help="ignore raw/translations/summaries/<lang>/ and render every locale with the FR summary + (français) marker",
    )
    args = ap.parse_args()

    commune_idx, insee_idx, insee_name_idx = load_commune_index(COMMUNES_GEOJSON)
    print(
        f"[load] commune index: {len(commune_idx)} (name) / {len(insee_idx)} (INSEE) entries",
        file=sys.stderr,
    )

    aires_by_app = load_aires()
    print(
        f"[load] INAO aires-communes: {len(aires_by_app)} appellations, "
        f"{sum(len(v) for v in aires_by_app.values())} commune-rows",
        file=sys.stderr,
    )

    parcels_by_app: dict[str, dict] = {}
    parcels_by_denom: dict[str, dict] = {}
    if not args.no_parcellaire:
        print("[load] parcellaire shapefile…", file=sys.stderr)
        parcels_by_app, parcels_by_denom = build_aoc_polygons(force=args.rebuild_parcellaire)
        print(
            f"[load] parcellaire: {len(parcels_by_app)} AOC polygons / "
            f"{len(parcels_by_denom)} denomination polygons",
            file=sys.stderr,
        )

    lieu_dit_index = LieuDitIndex()
    print(
        f"[load] cadastre lieux-dits: {lieu_dit_index.total_lieux_dits} polygons "
        f"across {len(lieu_dit_index.communes)} communes",
        file=sys.stderr,
    )

    MAP_DATA.mkdir(parents=True, exist_ok=True)

    features: list[dict] = []
    village_features: list[dict] = []
    skipped = 0
    coverage: list[tuple[str, int, int]] = []
    parcel_hits = aires_hits = commune_hits = 0
    dgc_hits: Counter[str] = Counter()
    village_aires_hits = village_commune_hits = village_skipped = 0

    # Pre-load the parent appellation polygons so DGCs can fall back to the
    # parent's geometry when the parcellaire has nothing keyed under their
    # id_denom (parcellaire publishes ~929 of the ~1079 SIQO DGCs).
    parent_geom_by_slug: dict[str, object] = {}
    parent_village_geom_by_slug: dict[str, object] = {}
    # Sibling-DGC index per id_appellation. Some appellations carry an
    # umbrella DGC plus named lieux-dits inside it (Chablis premier cru +
    # ~40 named crus, Alsace grand cru + ~50 lieux-dits). The SIQO model
    # only links each lieu-dit to the appellation, not to the umbrella;
    # without this index a lieu-dit with no parcellaire row would fall
    # back to the *appellation* polygon (entire Chablis), not the umbrella
    # (Chablis premier cru). We pick the longest sibling whose name
    # prefixes the lieu-dit's — only siblings with real (non-fallback)
    # geometry are recorded.
    sibling_geom_by_id_app: dict[int, list[tuple[str, object, object, str]]] = {}

    extracted_records = []
    for json_path in sorted(EXTRACTED.glob("*.json")):
        if json_path.name == "_index.json":
            continue
        extracted_records.append(json.loads(json_path.read_text()))
    # Process parents first, DGCs second — lets DGCs reuse the parent
    # geometry that was just resolved.
    extracted_records.sort(key=lambda r: (bool(r.get("is_dgc")), r["name"].lower()))

    for record in tqdm(extracted_records, desc="union", leave=False):
        is_dgc = bool(record.get("is_dgc"))
        # Detailed geometry priority:
        #   Parents: parcellaire → INAO aires-communes CSV → commune-text
        #     extraction (fallback union from cahier-named communes).
        #   DGCs (7-level chain — see resolve_dgc_geometry()):
        #     parcellaire-dgc → village-override → cadastre-lieu-dit
        #     → aires-csv-dgc → sibling umbrella → parent → none.
        if is_dgc:
            dgc_result = resolve_dgc_geometry(
                record,
                parcels_by_denom=parcels_by_denom,
                aires_by_app=aires_by_app,
                insee_idx=insee_idx,
                commune_idx=commune_idx,
                lieu_dit_index=lieu_dit_index,
                parent_geom_by_slug=parent_geom_by_slug,
                sibling_geom_by_id_app=sibling_geom_by_id_app,
            )
            geom = dgc_result.geom
            geom_source = dgc_result.source
            stats = dgc_result.stats
            sib_v_geom = dgc_result.sib_v_geom
            sib_name = dgc_result.sib_name
            sib_slug = dgc_result.sib_slug
            cadastre_match = dgc_result.cadastre_match
            dgc_hits[geom_source] += 1
        else:
            parcel_feat = parcels_by_app.get(record["name"])
            if parcel_feat is not None:
                geom = shape(parcel_feat["geometry"])
                stats = {"matched": -1, "unmatched": 0}
                geom_source = "parcellaire"
                parcel_hits += 1
            else:
                cahier_hint = cahier_insee(record, commune_idx)
                insee_codes = lookup_aire(aires_by_app, record["name"], cahier_hint)
                if insee_codes:
                    geom, stats = union_from_insee(insee_codes, insee_idx)
                    if geom is not None and not geom.is_empty:
                        geom_source = "aires-csv"
                        aires_hits += 1
                    else:
                        geom, stats = union_for_appellation(record, commune_idx)
                        geom_source = "communes"
                        commune_hits += 1 if geom is not None and not geom.is_empty else 0
                else:
                    geom, stats = union_for_appellation(record, commune_idx)
                    geom_source = "communes"
                    commune_hits += 1 if geom is not None and not geom.is_empty else 0
        coverage.append((record["name"], stats["matched"], stats["unmatched"]))

        # Village geometry: always commune-level (skip parcellaire), so the
        # simplified default view matches the wine-wiki choice — wider
        # commune-blocks instead of parcel-precise outlines. DGCs typically
        # don't have their own row in the aires CSV, so we let them fall
        # back to the parent's village geometry (already computed).
        if is_dgc:
            # Prefer DGC's own parcellaire polygon as the village geometry —
            # it's what makes Clisson visible at low zoom. If none, reuse
            # the commune-level geometry we just resolved (override or
            # aires-CSV-DGC), which is already at village resolution.
            # Failing all three, reuse the parent's village geom so the
            # DGC is still on the map.
            if geom_source == "parcellaire-dgc":
                v_geom = geom
                v_source = "parcellaire-dgc"
                v_stats = stats
            elif geom_source in ("dgc-village-override", "aires-csv-dgc", "cadastre-lieu-dit-dgc"):
                v_geom = geom
                v_source = geom_source
                v_stats = stats
            elif geom_source == "sibling-dgc" and sib_v_geom is not None:
                v_geom = sib_v_geom
                v_source = "sibling-dgc"
                v_stats = {"matched": -1, "unmatched": 0}
            else:
                parent_slug = record.get("parent_slug") or ""
                v_geom = parent_village_geom_by_slug.get(parent_slug)
                v_source = "parent-appellation" if v_geom is not None else "none"
                v_stats = {"matched": -1, "unmatched": 0} if v_geom is not None else {"matched": 0, "unmatched": 0}
        else:
            v_insee_codes = lookup_aire(
                aires_by_app, record["name"], cahier_insee(record, commune_idx)
            )
            # When parcellaire is available, narrow the aires-CSV commune
            # set to communes that actually contain parcels. Most AOCs are
            # unaffected (every aires-CSV commune holds parcels), but for
            # appellations whose aires-CSV row enumerates the legal aire
            # géographique rather than the production area — Alsace grand
            # cru rows list all 47 Alsace wine communes for every climat —
            # this collapses the village geometry to the actual cru-bearing
            # commune(s) instead of the whole region.
            if (
                v_insee_codes
                and geom_source == "parcellaire"
                and geom is not None
                and not geom.is_empty
            ):
                narrowed = {
                    c for c in v_insee_codes
                    if c in insee_idx and shape(insee_idx[c]).intersects(geom)
                }
                if not narrowed:
                    # aires-CSV INSEE codes can pre-date a commune merger
                    # (e.g. Kientzheim → Kaysersberg Vignoble in 2016) and
                    # so resolve to nothing in IGN AdminExpress. Scan the
                    # IGN index directly for the current commune(s).
                    narrowed = communes_containing(geom, insee_idx)
                if narrowed and len(narrowed) < len(v_insee_codes):
                    v_insee_codes = narrowed
            if v_insee_codes:
                v_geom, v_stats = union_from_insee(v_insee_codes, insee_idx)
                v_source = "aires-csv"
                if v_geom is None or v_geom.is_empty:
                    v_geom, v_stats = union_for_appellation(record, commune_idx)
                    v_source = "communes"
            else:
                v_geom, v_stats = union_for_appellation(record, commune_idx)
                v_source = "communes"

        if geom is None or geom.is_empty:
            skipped += 1
            continue
        if not is_dgc:
            parent_geom_by_slug[record["slug"]] = geom
            if v_geom is not None and not v_geom.is_empty:
                parent_village_geom_by_slug[record["slug"]] = v_geom
        elif geom_source not in ("sibling-dgc", "parent-appellation", "none"):
            # Record this DGC as a possible umbrella for later sibling
            # lookups within the same id_appellation. Only DGCs with their
            # own concrete geometry (parcellaire / override / aires-csv)
            # qualify — fallbacks must not propagate.
            sibling_geom_by_id_app.setdefault(record.get("id_appellation"), []).append(
                (record["name"], geom, v_geom, record["slug"])
            )
        # Geometry is in EPSG:4326 (lat/lon). Raw degree² is enough for
        # within-France relative area sort (all polygons share roughly the
        # same projection distortion), and it's far cheaper than reprojecting
        # every polygon to a planar CRS.
        area_deg2 = float(geom.area)
        minx, miny, maxx, maxy = geom.bounds
        bbox = [float(minx), float(miny), float(maxx), float(maxy)]
        grapes = record.get("grapes") or {}
        principal = grapes.get("principal") or []
        accessory = grapes.get("accessory") or []
        observation = grapes.get("observation") or []
        all_grapes = sorted(set(principal) | set(accessory) | set(observation))
        styles = record.get("styles") or []
        categories = record.get("categories") or []
        categorie = record.get("categorie", "") or ""
        # Wine vs. non-wine split: every INAO `categorie` value beginning with
        # "Vin" (Vin tranquille, Vin mousseux, Vin de liqueur, Vin doux
        # naturel) is a wine. Spirits (Eaux-de-vie, Rhum, Calvados,
        # Pommeau, etc.) and ciders fall outside that set. The map hides
        # non-wine appellations by default — see `showSpirits` in the
        # template for the toggle.
        is_wine = "1" if categorie.startswith("Vin") else "0"
        # When the geometry came from a sibling-DGC umbrella, surface the
        # umbrella's slug/name so the panel can explain "approximate area
        # — within {umbrella}".
        fallback_slug = ""
        fallback_name = ""
        if geom_source == "sibling-dgc":
            fallback_slug = sib_slug or ""
            fallback_name = sib_name or ""
        cadastre_lieu_dit = ""
        cadastre_commune = ""
        cadastre_score = 0.0
        if geom_source == "cadastre-lieu-dit-dgc" and cadastre_match is not None:
            cadastre_lieu_dit = cadastre_match.get("lieu_dit", "") or ""
            insee_codes_str = cadastre_match.get("commune", "") or ""
            cadastre_commune = "; ".join(
                insee_name_idx.get(c.strip(), c.strip())
                for c in insee_codes_str.split(";")
                if c.strip()
            )
            cadastre_score = float(cadastre_match.get("score", 0.0))
        # MVT properties must be scalar; we encode arrays as ;-padded
        # strings so MapLibre's `in` expression can substring-match.
        # The parsed `kind` is a layout heuristic, not the regulatory
        # category — stage 02 occasionally mis-stamps an IGP as AOC (or
        # vice versa) when the cahier's bundle layout misleads the
        # parser, and STUBs are unparsed. The SIQO referentiel
        # (signe_fr / signe_ue) is the source of truth, so we re-derive
        # the AOC/IGP label here for the map's filter and panel header.
        # EDV (eau-de-vie) is layout-only and is preserved as-is.
        raw_kind = record.get("kind", "AOC")
        if raw_kind == "EDV":
            mvt_kind = "EDV"
        else:
            sfr = (record.get("signe_fr") or "").strip().upper()
            sue = (record.get("signe_ue") or "").strip().upper()
            if sfr == "AOC" or sue == "AOP":
                mvt_kind = "AOC"
            elif sue == "IGP":
                mvt_kind = "IGP"
            else:
                mvt_kind = raw_kind if raw_kind != "STUB" else "AOC"
        common_props = {
            "country": record.get("country") or "fr",
            "id_appellation": record["id_appellation"],
            "id_denomination_geo": record.get("id_denomination_geo") or "",
            "slug": record["slug"],
            "name": record["name"],
            "kind": mvt_kind,
            "region": record.get("comite_regional", ""),
            "categorie": categorie,
            "is_wine": is_wine,
            "is_dgc": "1" if is_dgc else "0",
            "parent_slug": record.get("parent_slug") or "",
            "parent_name": record.get("parent_name") or "",
            "geom_fallback_slug": fallback_slug,
            "geom_fallback_name": fallback_name,
            "cadastre_lieu_dit": cadastre_lieu_dit,
            "cadastre_commune": cadastre_commune,
            "cadastre_score": cadastre_score,
            "categories": _join_set(categories),
            "styles": _join_set(styles),
            "grapes_principal": _join_set(principal),
            "grapes_accessory": _join_set(accessory),
            "grapes_observation": _join_set(observation),
            "grapes_all": _join_set(all_grapes),
            "communes_matched": stats["matched"],
            "communes_unmatched": stats["unmatched"],
            "geom_source": geom_source,
            "area": area_deg2,
            "bbox": ",".join(f"{v:.5f}" for v in bbox),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": common_props,
            }
        )
        if v_geom is not None and not v_geom.is_empty:
            v_minx, v_miny, v_maxx, v_maxy = v_geom.bounds
            v_bbox = [float(v_minx), float(v_miny), float(v_maxx), float(v_maxy)]
            village_props = dict(common_props)
            village_props["geom_source"] = v_source
            village_props["area"] = float(v_geom.area)
            village_props["bbox"] = ",".join(f"{v:.5f}" for v in v_bbox)
            village_features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(v_geom),
                    "properties": village_props,
                }
            )
            if v_source == "aires-csv":
                village_aires_hits += 1
            else:
                village_commune_hits += 1
        else:
            village_skipped += 1

    fc = {"type": "FeatureCollection", "features": features}
    GEOJSON_OUT.write_text(json.dumps(fc, ensure_ascii=False))
    village_fc = {"type": "FeatureCollection", "features": village_features}
    GEOJSON_VILLAGES_OUT.write_text(json.dumps(village_fc, ensure_ascii=False))
    print(
        f"[geo] villages: {len(village_features)} polygons → {GEOJSON_VILLAGES_OUT.relative_to(ROOT)} "
        f"({GEOJSON_VILLAGES_OUT.stat().st_size // (1<<20)} MB), "
        f"aires-csv={village_aires_hits} commune-text={village_commune_hits} skipped={village_skipped}",
        file=sys.stderr,
    )
    print(
        f"[geo] {len(features)} appellation polygons → {GEOJSON_OUT.relative_to(ROOT)} "
        f"({GEOJSON_OUT.stat().st_size // (1<<20)} MB), "
        f"parcellaire={parcel_hits} aires-csv={aires_hits} commune-text={commune_hits} skipped={skipped}",
        file=sys.stderr,
    )
    print(
        f"[geo] DGC resolution: parcellaire={dgc_hits['parcellaire-dgc']} "
        f"village-override={dgc_hits['dgc-village-override']} "
        f"cadastre-lieu-dit={dgc_hits['cadastre-lieu-dit-dgc']} "
        f"aires-csv={dgc_hits['aires-csv-dgc']} "
        f"sibling-fallback={dgc_hits['sibling-dgc']} "
        f"parent-fallback={dgc_hits['parent-appellation']} "
        f"skipped={dgc_hits['none']}",
        file=sys.stderr,
    )

    # Top 10 worst commune coverage as a quick QA hint.
    coverage.sort(key=lambda c: (-c[2], c[0]))
    print("[coverage] worst commune-match rates:", file=sys.stderr)
    for name, matched, unmatched in coverage[:10]:
        if unmatched == 0:
            break
        total = matched + unmatched
        print(f"  {name}: {unmatched}/{total} unmatched", file=sys.stderr)

    if args.no_tippecanoe:
        # Skip the slow tippecanoe pass but still re-emit the HTML so
        # template/metadata changes propagate. Use the existing pmtiles
        # if it's on disk, otherwise fall back to the geojson source.
        if PMTILES_OUT.exists() and PMTILES_VILLAGES_OUT.exists():
            emit_html(
                features, village_features,
                layer_url="/map-data/appellations.pmtiles",
                villages_layer_url="/map-data/appellations-villages.pmtiles",
                source_type="pmtiles",
                use_translations=not args.no_translations,
            )
        else:
            emit_html(
                features, village_features,
                layer_url="/map-data/appellations.geojson",
                villages_layer_url="/map-data/appellations-villages.geojson",
                source_type="geojson",
                use_translations=not args.no_translations,
            )
        return 0

    if shutil.which("tippecanoe") is None:
        print("warn: tippecanoe not on PATH (brew install tippecanoe) — skipping pmtiles", file=sys.stderr)
        emit_html(
            features, village_features,
            layer_url="/map-data/appellations.geojson",
            villages_layer_url="/map-data/appellations-villages.geojson",
            source_type="geojson",
            use_translations=not args.no_translations,
        )
        return 0

    for src_geojson, dst_pmtiles, layer_id in (
        (GEOJSON_OUT, PMTILES_OUT, "appellations"),
        (GEOJSON_VILLAGES_OUT, PMTILES_VILLAGES_OUT, "appellations"),
    ):
        if dst_pmtiles.exists():
            dst_pmtiles.unlink()
        cmd = [
            "tippecanoe",
            "-o", str(dst_pmtiles),
            "-l", layer_id,
            "--minimum-zoom=4",
            "--maximum-zoom=12",
            "--coalesce-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--no-feature-limit",
            "--no-tile-size-limit",
            str(src_geojson),
        ]
        print(f"[tippe] {' '.join(cmd)}", file=sys.stderr)
        subprocess.run(cmd, check=True)
        print(
            f"[pmtiles] {dst_pmtiles.relative_to(ROOT)} "
            f"({dst_pmtiles.stat().st_size // (1<<20)} MB)",
            file=sys.stderr,
        )

    emit_html(
        features, village_features,
        layer_url="/map-data/appellations.pmtiles",
        villages_layer_url="/map-data/appellations-villages.pmtiles",
        source_type="pmtiles",
        use_translations=not args.no_translations,
    )
    return 0


def _sources_for(record: dict) -> dict:
    """Pull authoritative source URLs from the extracted record."""
    src = record.get("source") or {}
    return {
        "boagri": src.get("boagri_url") or "",
        "show_texte": src.get("show_texte_url") or "",
        "product": src.get("product_url") or "",
        "filename": src.get("filename") or "",
        "pdf_sha256": src.get("pdf_sha256") or "",
        "fetched_at": src.get("fetched_at") or "",
        "homologation_date": (record.get("header") or {}).get("homologation_date") or "",
        "jorf_date": (record.get("header") or {}).get("jorf_date") or "",
    }


def load_terroir_facts(slug: str, parent_slug: str = "") -> dict | None:
    """Per-AOC terroir-facts payload for the sidepanel; falls back to parent
    for DGCs (which inherit the parent appellation's bullets)."""
    cache_dir = ROOT / "raw" / "terroir-facts"
    p = cache_dir / f"{slug}.json"
    if not p.exists() and parent_slug:
        p = cache_dir / f"{parent_slug}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    facts = d.get("facts") or []
    if not facts:
        return None
    return {
        "facts": [
            {
                "bullet": f.get("bullet", ""),
                "subsection": f.get("subsection", "facteurs_naturels"),
                "provenance": f.get("provenance", "cahier"),
            }
            for f in facts
        ],
        "wiki_source_url": d.get("wiki_source_url") or "",
        "cahier_source_pdf_url": d.get("cahier_source_pdf_url") or "",
    }


def overlay_translated_facts(
    aocs: dict[str, dict], translations: dict[str, dict]
) -> dict[str, dict]:
    """Return a new aocs dict where each AOC's `terroir_facts.facts[i].bullet`
    is replaced by the translated bullet (when both the AOC and the index
    exist in `translations`). Provenance / subsection / wiki_source_url
    metadata stay from the FR cache.

    DGCs whose FR facts come from the parent (parent-fallback in
    `load_terroir_facts`) look up the translation under the parent slug too."""
    out: dict[str, dict] = {}
    for slug, rec in aocs.items():
        tf = rec.get("terroir_facts")
        t = translations.get(slug)
        if not t:
            parent = rec.get("parent_slug") or ""
            if parent:
                t = translations.get(parent)
        if not tf or not t:
            out[slug] = rec
            continue
        translated = t.get("facts") or []
        fr_facts = tf.get("facts") or []
        if len(translated) != len(fr_facts):
            out[slug] = rec
            continue
        new_facts = [
            {
                **fr_facts[i],
                "bullet": translated[i].get("bullet") or fr_facts[i].get("bullet", ""),
            }
            for i in range(len(fr_facts))
        ]
        out[slug] = {
            **rec,
            "terroir_facts": {
                **tf,
                "facts": new_facts,
            },
        }
    return out


def emit_html(
    features: list[dict],
    village_features: list[dict],
    *,
    layer_url: str,
    villages_layer_url: str,
    source_type: str,
    use_translations: bool = True,
) -> None:
    """Build the per-AOC metadata blob + facet histograms, then render."""
    aocs: dict[str, dict] = {}
    style_counts: dict[str, int] = {}
    principal_counts: dict[str, int] = {}
    accessory_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {}
    grapes_all_counts: dict[str, int] = {}
    simple_style_counts: dict[str, int] = {}
    village_bbox_by_slug: dict[str, list[float]] = {}
    for feat in village_features:
        p = feat["properties"]
        bbox_str = p.get("bbox") or ""
        if bbox_str:
            village_bbox_by_slug[p["slug"]] = [float(v) for v in bbox_str.split(",")]

    appellation_urls = load_appellation_urls()

    for feat in features:
        p = feat["properties"]
        slug = p["slug"]
        # Recover slug arrays from the ;-padded MVT-friendly strings.
        styles = [s for s in p.get("styles", "").split(";") if s]
        principal = [s for s in p.get("grapes_principal", "").split(";") if s]
        accessory = [s for s in p.get("grapes_accessory", "").split(";") if s]
        observation = [s for s in p.get("grapes_observation", "").split(";") if s]
        categories = [s for s in p.get("categories", "").split(";") if s]
        all_grapes = sorted(set(principal) | set(accessory) | set(observation))
        simple_styles = sorted({SIMPLE_STYLE_BUCKETS.get(s, "other") for s in styles}) if styles else []

        # Extracted JSON has a richer summary + source URLs; pull them.
        ext_path = EXTRACTED / f"{slug}.json"
        summary = ""
        sources: dict = {}
        parent_slug_for_facts = p.get("parent_slug", "") or ""
        if ext_path.exists():
            rec = json.loads(ext_path.read_text())
            summary = derive_summary(rec)
            sources = _sources_for(rec)
        syndicate = resolve_appellation_url(
            slug, parent_slug_for_facts, p.get("region", "") or "", appellation_urls
        )
        if syndicate:
            sources["syndicate"] = syndicate
        terroir_facts = load_terroir_facts(slug, parent_slug_for_facts)

        bbox_str = p.get("bbox") or ""
        bbox = [float(v) for v in bbox_str.split(",")] if bbox_str else None
        bbox_villages = village_bbox_by_slug.get(slug)

        aocs[slug] = {
            "country": p.get("country") or "fr",
            "name": p["name"],
            "kind": p["kind"],
            "region": p["region"],
            "is_wine": p.get("is_wine", "1") == "1",
            "is_dgc": p.get("is_dgc", "0") == "1",
            "parent_slug": p.get("parent_slug", "") or "",
            "parent_name": p.get("parent_name", "") or "",
            "communes_matched": p["communes_matched"],
            "geom_source": p.get("geom_source", "communes"),
            "geom_fallback_slug": p.get("geom_fallback_slug", "") or "",
            "geom_fallback_name": p.get("geom_fallback_name", "") or "",
            "cadastre_lieu_dit": p.get("cadastre_lieu_dit", "") or "",
            "cadastre_commune": p.get("cadastre_commune", "") or "",
            "area": p.get("area", 0),
            "bbox": bbox,
            "bbox_villages": bbox_villages,
            "categories": categories,
            "styles": styles,
            "styles_simple": simple_styles,
            "grapes_principal": principal,
            "grapes_accessory": accessory,
            "grapes_observation": observation,
            "grapes_all": all_grapes,
            "summary": summary,
            "sources": sources,
            "terroir_facts": terroir_facts,
        }
        for s in styles:
            style_counts[s] = style_counts.get(s, 0) + 1
        for s in simple_styles:
            simple_style_counts[s] = simple_style_counts.get(s, 0) + 1
        for s in principal:
            principal_counts[s] = principal_counts.get(s, 0) + 1
        for s in accessory:
            accessory_counts[s] = accessory_counts.get(s, 0) + 1
        for s in all_grapes:
            grapes_all_counts[s] = grapes_all_counts.get(s, 0) + 1
        if p["region"]:
            region_counts[p["region"]] = region_counts.get(p["region"], 0) + 1

    def sort_facet(d: dict[str, int]) -> list[tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))

    updated = compile_catalogs()
    if updated:
        print(f"[i18n] recompiled .mo for: {', '.join(updated)}", file=sys.stderr)

    # Polygon-area quartiles drive the fill-opacity / outline-weight
    # interpolation in the map paint. Computed per build over the
    # current feature set — visual encoding shifts slightly when the
    # corpus changes, which is the right behaviour.
    areas = sorted(float(f["properties"].get("area") or 0.0) for f in features)
    if areas:
        n = len(areas)
        area_q1 = areas[max(0, n // 4 - 1)]
        area_q3 = areas[min(n - 1, (3 * n) // 4)]
        if area_q3 <= area_q1:
            area_q3 = area_q1 + 1e-9
    else:
        area_q1, area_q3 = 0.0, 1.0

    # Simple-mode style facet uses the 6-bucket order white/rose/red/
    # sparkling/sweet/other, regardless of frequency, so chips read like a
    # canonical wine-style legend.
    simple_style_order = ["white", "rose", "red", "sparkling", "sweet", "other"]
    facet_styles_simple = [
        (s, simple_style_counts.get(s, 0)) for s in simple_style_order
        if simple_style_counts.get(s, 0) > 0
    ]

    facets = dict(
        layer_url=layer_url,
        villages_layer_url=villages_layer_url,
        source_type=source_type,
        aocs=aocs,
        facet_styles=sort_facet(style_counts),
        facet_styles_simple=facet_styles_simple,
        facet_principal=sort_facet(principal_counts),
        facet_accessory=sort_facet(accessory_counts),
        facet_grapes_all=sort_facet(grapes_all_counts),
        facet_regions=sort_facet(region_counts),
        area_q1=area_q1,
        area_q3=area_q3,
    )
    fr_lex = load_grape_lexicon("fr")
    fr_styles_lex = load_style_lexicon("fr")
    for lang in LOCALES:
        if lang == "fr":
            lex = fr_lex
            styles_lex = fr_styles_lex
        else:
            lex = merge_grape_lexicon(load_grape_lexicon(lang), fr_lex)
            styles_lex = merge_style_lexicon(load_style_lexicon(lang), fr_styles_lex)
        translations = load_summary_translations(lang) if use_translations else {}
        # Locale-specific summary takes precedence; FR summary stays as the
        # fallback the panel renders with the "(français)" marker. FR uses
        # the same cache for hand-rewritten summaries but without the
        # "translation" attribution (it is the canonical language).
        if lang == "fr":
            aocs_for_lang = {
                slug: ({**rec, "summary": translations[slug]["summary"]}
                       if slug in translations else rec)
                for slug, rec in aocs.items()
            }
        else:
            aocs_for_lang = {
                slug: ({**rec, "summary": translations[slug]["summary"],
                       "summary_translation": {
                           "translator": translations[slug]["translator"],
                           "source_pdf_url": translations[slug]["source_pdf_url"],
                           "source_pdf_filename": translations[slug]["source_pdf_filename"],
                       }} if slug in translations else rec)
                for slug, rec in aocs.items()
            }
        # Overlay translated terroir-fact bullets when the locale is non-FR
        # and a per-locale 02e cache exists. FR keeps its native bullets.
        facts_translations: dict[str, dict] = {}
        if use_translations and lang != "fr":
            facts_translations = load_terroir_facts_translations(lang)
            if facts_translations:
                aocs_for_lang = overlay_translated_facts(aocs_for_lang, facts_translations)
        out = (WIKI / "index.html") if lang == "en" else (WIKI / lang / "index.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Pass a swapped facets dict so the per-locale `aocs` is what gets serialised.
        per_locale_facets = {**facets, "aocs": aocs_for_lang}
        out.write_text(render_map_html(
            **per_locale_facets, locale=lang, grapes_info=lex, styles_info=styles_lex,
        ))
        fallback_n = sum(1 for v in lex.values() if v.get("lang_fallback"))
        styles_fallback_n = sum(1 for v in styles_lex.values() if v.get("lang_fallback"))
        print(
            f"[html] {out.relative_to(ROOT)} "
            f"(locale={lang}, grape_info={len(lex)}, fr_fallback={fallback_n}, "
            f"style_info={len(styles_lex)}, style_fr_fallback={styles_fallback_n}, "
            f"summary_translations={len(translations)}, "
            f"facts_translations={len(facts_translations)})",
            file=sys.stderr,
        )
    print(
        f"[html] {len(aocs)} AOCs, {len(style_counts)} styles, "
        f"{len(principal_counts)} principal grapes, {len(accessory_counts)} accessory grapes, "
        f"{len(region_counts)} regions",
        file=sys.stderr,
    )

    write_seo_files()


def _hreflang_alternates(paths_by_lang: dict[str, str]) -> str:
    """Build the `<xhtml:link rel="alternate">` block for one URL group.

    `x-default` points at the EN canonical (the bare path with no locale
    prefix), since EN is now the site's default language.
    """
    out = "\n".join(
        f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{SITE_BASE_URL}{path}"/>'
        for lang, path in paths_by_lang.items()
    )
    return out + (
        f'\n    <xhtml:link rel="alternate" hreflang="x-default" '
        f'href="{SITE_BASE_URL}{paths_by_lang["en"]}"/>'
    )


def _sitemap_url_block(loc: str, lastmod: str, alternates: str) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"{alternates}\n"
        f"  </url>"
    )


def write_seo_files() -> None:
    """Emit wiki/robots.txt and wiki/sitemap.xml.

    The map IS the homepage: `/` (EN canonical), `/fr/`, `/es/`, `/nl/`. The
    sitemap covers those four URLs, each carrying the full hreflang alternate
    set so search engines can pair locale variants. Updated whenever stage 04
    reruns; lastmod is today.
    """
    today = dt.date.today().isoformat()

    home_paths = {lang: ("/" if lang == "en" else f"/{lang}/") for lang in LOCALES}
    home_alternates = _hreflang_alternates(home_paths)

    url_blocks = [
        _sitemap_url_block(f"{SITE_BASE_URL}{home_paths[lang]}", today, home_alternates)
        for lang in LOCALES
    ]

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap-0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(url_blocks)
        + "\n</urlset>\n"
    )
    (WIKI / "sitemap.xml").write_text(sitemap)

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /map-data/\n"
        f"Sitemap: {SITE_BASE_URL}/sitemap.xml\n"
    )
    (WIKI / "robots.txt").write_text(robots)
    print(
        f"[seo] wrote {WIKI.relative_to(ROOT)}/robots.txt and sitemap.xml "
        f"({len(LOCALES)} URLs)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
