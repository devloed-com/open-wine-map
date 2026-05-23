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
import hashlib
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
from _lib.es.baleares import ines_for_island
from _lib.es.commune_list import (
    parse_ccaa_wide,
    parse_commune_list,
    parse_island_wide,
    parse_province_wide_list,
    parse_whole_commune_prefix,
)
from _lib.es.geometry import ESPolygonIndex
from _lib.es.zones import ESZoneIndex, MAPA_ZONES_FILE
from _lib.es.pliego_parcels import parse_polygon_inclusions
from _lib.es.region import (
    CCAA_TO_PROVINCE_INES,
    PROVINCE_TO_INE,
    derive_ccaa as derive_es_ccaa,
)
from _lib.es.sigpac import SigpacIndex
from _lib.fr_wine_region import derive_wine_region as derive_fr_wine_region
from _lib.geometry_overrides import ClipResult, GeometryOverrides
from _lib.pt.commune_list import parse_commune_list as parse_pt_commune_list
from _lib.pt.geometry import PTPolygonIndex
from _lib.pt.region import derive_region as derive_pt_region
from _lib.it.geometry import ITPolygonIndex
from _lib.it.zones import ITZoneIndex
from _lib.it.region import derive_regione as derive_it_regione
from _lib.at.geometry import ATPolygonIndex
from _lib.at.gemeinde import ATCommuneIndex
from _lib.at.region import derive_bundesland as derive_at_bundesland
from _lib.si.geometry import SIPolygonIndex
from _lib.si.region import derive_region as derive_si_region
from _lib.i18n import LOCALES, compile_catalogs
from _lib.lieu_dit import LieuDitIndex, derive_climat_name
from _lib.map_template import render as render_map_html
from _lib.parcellaire import build_aoc_polygons
from _lib.style_taxonomy import (
    all_slugs as _taxonomy_all_slugs,
    descendants as _taxonomy_descendants,
    descendants_map as _taxonomy_descendants_map,
    simple_bucket as _taxonomy_simple_bucket,
    taxonomy_dfs_order as _taxonomy_dfs_order,
)
from _lib.summaries import derive_summary, summary_sha
from _lib.wiki import is_grape_summary

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
EXTRACTED_ES = ROOT / "raw" / "es" / "pliegos-extracted"
NATIONAL_PLIEGOS_ES = ROOT / "raw" / "es" / "national-pliegos-extracted"
ES_FIGSHARE_GPKG = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
ES_GISCO_LAU_ZIP = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"
ES_SIGPAC_DIR = ROOT / "raw" / "es" / "sigpac"
EXTRACTED_PT = ROOT / "raw" / "pt" / "cadernos-extracted"
PT_CAOP_DIR = ROOT / "raw" / "pt" / "caop"
EXTRACTED_IT = ROOT / "raw" / "it" / "disciplinari-extracted"
MASAF_DISCIPLINARI_IT = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
EXTRACTED_AT = ROOT / "raw" / "at" / "dokumente-extracted"
AT_STATISTIK_DIR = ROOT / "raw" / "at" / "statistik"
EXTRACTED_SI = ROOT / "raw" / "si" / "dokumenti-extracted"
COMMUNES_GEOJSON = ROOT / "raw" / "ign" / "communes.geojson"
WIKI = ROOT / "wiki"
SITE_BASE_URL = "https://www.openwinemap.com"
MAP_DATA = WIKI / "map-data"
ASSETS_SRC = ROOT / "raw" / "assets"
ASSETS_OUT = WIKI / "assets"
GEOJSON_OUT = MAP_DATA / "appellations.geojson"
PMTILES_OUT = MAP_DATA / "appellations.pmtiles"
GEOJSON_VILLAGES_OUT = MAP_DATA / "appellations-villages.geojson"
PMTILES_VILLAGES_OUT = MAP_DATA / "appellations-villages.pmtiles"
LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes"
GRAPE_TRANSLATIONS_DIR = ROOT / "raw" / "translations" / "grapes"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"
STYLE_LEXICON_DIR = ROOT / "raw" / "wikipedia" / "styles"
STYLE_TRANSLATIONS_DIR = ROOT / "raw" / "translations" / "styles"


_DISAMBIG_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


# Slug-keyed cache of national-pliego provenance, populated by
# augment_es_records_with_national_pliegos() and read by _sources_for()
# later in the build. Needed because the AOC-blob phase re-reads each
# extracted JSON from disk (where the augmentation isn't persisted) —
# this lookup gives that phase access to the same provenance the
# in-memory record carries.
_ES_NATIONAL_PLIEGO_BY_SLUG: dict[str, dict] = {}


# Slug-keyed cache of MASAF disciplinare provenance + augmented payload,
# populated by augment_it_records_with_masaf() and read by _sources_for()
# / the AOC-blob phase (which re-reads each on-disk extracted JSON,
# bypassing in-memory augmentation).
_IT_MASAF_BY_SLUG: dict[str, dict] = {}


def augment_es_records_with_national_pliegos(records: list[dict]) -> int:
    """In-place merge of national-pliego sidecar varieties into each ES
    record's `grapes` field. Returns the number of records augmented.

    Mutations per record:
      - new variety slugs (those NOT already in principal ∪ accessory) are
        appended to `grapes.accessory`
      - matching entries are appended to `grapes.details` with
        `role="accessory"` and `source="national-pliego"` so the UI can
        distinguish doc-único-canonical varieties from pliego-augmented ones
      - a top-level `national_pliego` block carries provenance for
        `_sources_for()` to surface in the panel
    """
    _ES_NATIONAL_PLIEGO_BY_SLUG.clear()
    if not NATIONAL_PLIEGOS_ES.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "es":
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_PLIEGOS_ES / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        sidecar = json.loads(sidecar_path.read_text())
        new_slugs = list(sidecar.get("delta_vs_oj", {}).get("new_slugs") or [])
        if not new_slugs:
            # Still stamp provenance — the pliego was parsed even if it
            # added nothing new. Skip the merge but keep attribution
            # consistent for the audit.
            nat_provenance = {
                "url": sidecar.get("source", {}).get("url", ""),
                "sha256": sidecar.get("source", {}).get("sha256", ""),
                "fetched_at": sidecar.get("source", {}).get("fetched_at", ""),
                "parser_template": sidecar.get("parser_template", ""),
                "added_slugs": [],
            }
            record["national_pliego"] = nat_provenance
            _ES_NATIONAL_PLIEGO_BY_SLUG[slug] = nat_provenance
            continue
        grapes = dict(record.get("grapes") or {})
        principal = list(grapes.get("principal") or [])
        accessory = list(grapes.get("accessory") or [])
        details = list(grapes.get("details") or [])
        existing = set(principal) | set(accessory)
        added: list[str] = []
        slug_to_detail = {d.get("slug"): d for d in sidecar.get("varieties", [])}
        for s in new_slugs:
            if s in existing:
                continue
            accessory.append(s)
            existing.add(s)
            added.append(s)
            detail = dict(slug_to_detail.get(s) or {"slug": s, "name": s, "colour": ""})
            detail["role"] = "accessory"
            detail["source"] = "national-pliego"
            details.append(detail)
        grapes["accessory"] = accessory
        grapes["details"] = details
        record["grapes"] = grapes
        nat_provenance = {
            "url": sidecar.get("source", {}).get("url", ""),
            "sha256": sidecar.get("source", {}).get("sha256", ""),
            "fetched_at": sidecar.get("source", {}).get("fetched_at", ""),
            "parser_template": sidecar.get("parser_template", ""),
            "added_slugs": added,
        }
        record["national_pliego"] = nat_provenance
        _ES_NATIONAL_PLIEGO_BY_SLUG[slug] = nat_provenance
        if added:
            augmented += 1
    return augmented


def augment_it_records_with_masaf(records: list[dict]) -> int:
    """In-place merge of MASAF disciplinare sidecar data into IT stub
    records. Only stubs are touched — wines whose documento unico was
    extracted in stage 02 already carry canonical EUR-Lex data and
    shouldn't be overwritten.

    For each IT stub with a matching sidecar at
    raw/it/masaf-disciplinari-extracted/<slug>.json the following
    fields are merged:
      - summary           ← Article 1 first paragraph
      - regione           ← derived from Article 3 / 9 text
      - grapes            ← parsed from Article 2 (principal-only)
      - geo_area_brief    ← Article 3 body
      - link_to_terroir   ← Article 9 body
      - section_roles     ← {grape_varieties, geo_area, link_to_terroir, ...}
      - stub_reason       ← prefixed "masaf:" so the audit can tell
                            doc-unico-extracted from masaf-augmented
      - masaf             ← provenance block (url, sha256, fetched_at,
                            parser_template, bundle_key, archive_path)

    `record["stub"]` stays True — the record is still NOT a documento
    unico extraction, just augmented. Stage 03 / 04 callers use the
    `masaf` block to distinguish.

    Returns the number of records augmented.
    """
    _IT_MASAF_BY_SLUG.clear()
    if not MASAF_DISCIPLINARI_IT.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "it":
            continue
        if not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = MASAF_DISCIPLINARI_IT / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text())
        except (ValueError, OSError):
            continue

        # Build the provenance block (also cached for the AOC-blob phase).
        src = sidecar.get("source") or {}
        match_info = sidecar.get("match") or {}
        provenance = {
            "filename": src.get("filename") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "parser_template": sidecar.get("parser_template") or "",
            "bundle_key": src.get("bundle_key") or "",
            "archive_path": src.get("archive_path") or "",
            "match_how": match_info.get("how") or "",
            "pdf_filename": match_info.get("pdf_filename") or "",
            # When an override pinned the URL, surface it for the panel.
            "override_url": src.get("url") or "",
            "override_source_org": src.get("source_org") or "",
        }

        # Merge augmented fields onto the record. Replace rather than
        # union — the record was a stub so there's nothing to lose.
        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("regione") and not record.get("regione"):
            record["regione"] = sidecar["regione"]
        if sidecar.get("grapes"):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        section_roles = dict(record.get("section_roles") or {})
        if sidecar.get("grapes"):
            section_roles.setdefault("grape_varieties", "")
        if sidecar.get("geo_area_brief"):
            section_roles["geo_area"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            section_roles["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("summary"):
            section_roles["description"] = sidecar["summary"]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("masaf:"):
            record["stub_reason"] = f"masaf:{record['stub_reason']}"
        record["masaf"] = provenance
        _IT_MASAF_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


# Simple-mode style buckets: collapses the fine-grained style tags into the
# six top-level buckets the default view shows. Derived from the canonical
# taxonomy in scripts/_lib/style_taxonomy so adding a new tag in one place
# propagates here automatically.
SIMPLE_STYLE_BUCKETS: dict[str, str] = {
    s: _taxonomy_simple_bucket(s) for s in _taxonomy_all_slugs()
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
    """Legacy FR-fallback merge. Retained for the styles path which still
    uses it; the grapes path now goes through `build_grapes_info()`."""
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


_VIVC_BY_SLUG_CACHE: dict[str, dict] | None = None


def _load_vivc_by_slug() -> dict[str, dict]:
    """`{slug: {canonical_name, vivc_id, vivc_url}}` from raw/vivc/by-slug/."""
    global _VIVC_BY_SLUG_CACHE
    if _VIVC_BY_SLUG_CACHE is not None:
        return _VIVC_BY_SLUG_CACHE
    out: dict[str, dict] = {}
    if not VIVC_BY_SLUG.exists():
        _VIVC_BY_SLUG_CACHE = out
        return out
    for f in VIVC_BY_SLUG.glob("*.json"):
        rec = json.loads(f.read_text())
        prime = (rec.get("prime_name") or "").strip()
        vid = rec.get("vivc_id")
        if not prime or not isinstance(vid, int):
            continue
        # str.title() handles apostrophes correctly ("D'AUNIS" → "D'Aunis"),
        # which a per-token .capitalize() does not ("D'aunis").
        canonical = prime.title()
        out[rec["slug"]] = {
            "canonical_name": canonical,
            "vivc_id": vid,
            "vivc_url": rec.get("source_url"),
        }
    _VIVC_BY_SLUG_CACHE = out
    return out


def _load_native_grape(lang: str, slug: str, max_chars: int = 280) -> dict | None:
    """Native Wikipedia entry for (slug, lang), or None when missing/empty.
    Returns the trimmed entry with name, extract, page_url, revision_id,
    thumbnail, matched_via."""
    f = LEXICON_DIR / lang / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    if d.get("missing") or d.get("error"):
        return None
    title = (d.get("wikipedia_title") or "").strip()
    extract = (d.get("extract") or "").strip()
    if not extract or not is_grape_summary(lang, d.get("description", ""), extract):
        return None
    display = _DISAMBIG_SUFFIX.sub("", title).strip() if title else slug
    if len(extract) > max_chars:
        cut = extract[:max_chars].rsplit(". ", 1)[0]
        extract = cut + ("." if not cut.endswith(".") else "") + " […]"
    out: dict = {
        "name": display or slug,
        "extract": extract,
        "page_url": d.get("page_url"),
        "revision_id": d.get("revision_id"),
        "matched_via": d.get("matched_via") or "primary",
    }
    if d.get("thumbnail"):
        out["thumbnail"] = d["thumbnail"]
    return out


def _load_translated_grape(lang: str, slug: str, max_chars: int = 280) -> dict | None:
    f = GRAPE_TRANSLATIONS_DIR / lang / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    extract = (d.get("extract") or "").strip()
    if not extract:
        return None
    if len(extract) > max_chars:
        cut = extract[:max_chars].rsplit(". ", 1)[0]
        extract = cut + ("." if not cut.endswith(".") else "") + " […]"
    return {
        "extract": extract,
        "source_lang": d.get("source_lang"),
        "page_url": d.get("source_page_url"),
        "name": (d.get("source_wikipedia_title") or slug).strip() or slug,
        "translator": d.get("translator"),
        "translator_kind": d.get("translator_kind"),
    }


def _corpus_grape_names() -> dict[str, str]:
    """Per-slug regulator spelling from the FR+ES+PT corpus, e.g.
    `cot → 'cot'`, `malbec → 'malbec'`, `mancin → 'mancin'`. Used as the
    canonical sidebar / pill label so three different slugs sharing a
    Wikipedia article (Cot ↔ Malbec via vivc, plus a misattributed
    Mancin) read as their three distinct cahier names — not three
    identical "Malbec" rows."""
    from _lib.grape_corpus import collect_grape_slugs as _c  # noqa: PLC0415
    return {slug: entry["name"] for slug, entry in _c().items() if entry.get("name")}


_CORPUS_GRAPE_NAMES: dict[str, str] | None = None


def _corpus_name_for(slug: str) -> str | None:
    global _CORPUS_GRAPE_NAMES
    if _CORPUS_GRAPE_NAMES is None:
        _CORPUS_GRAPE_NAMES = _corpus_grape_names()
    return _CORPUS_GRAPE_NAMES.get(slug)


def _override_name_with_corpus(entry: dict, slug: str) -> None:
    """Replace `entry['name']` (which after `_load_native_grape` is the
    Wikipedia article title) with the regulator's cahier spelling when
    one exists. Keeps `wikipedia_title` intact for the tooltip header so
    attribution stays accurate."""
    cahier = _corpus_name_for(slug)
    if not cahier:
        return
    if "wikipedia_title" not in entry and entry.get("name"):
        entry["wikipedia_title"] = entry["name"]
    entry["name"] = cahier


def build_grapes_info(target_locale: str) -> dict:
    """Per-slug grape data for the target locale's map page.

    Resolution per (slug, target_locale):
      1. Native target-locale Wikipedia entry → `is_translated=false`,
         `source_lang=target_locale`.
      2. Translated cache (`02b_translate_grapes.py`) →
         `is_translated=true`, `source_lang` from the cache record.
      3. Neither → emit `{canonical_name, vivc_id, vivc_url}` only when
         a VIVC record exists; the pill still renders (cahier name +
         optional canonical bracket + VIVC link), just without a tooltip
         body.

    VIVC `canonical_name`/`vivc_id`/`vivc_url` ride alongside the
    Wikipedia entry for every slug that has a resolved VIVC record;
    unresolved/missed slugs simply lack those fields.
    """
    vivc = _load_vivc_by_slug()
    slugs: set[str] = set()
    if (LEXICON_DIR / target_locale).exists():
        slugs.update(p.stem for p in (LEXICON_DIR / target_locale).glob("*.json"))
    if (GRAPE_TRANSLATIONS_DIR / target_locale).exists():
        slugs.update(p.stem for p in (GRAPE_TRANSLATIONS_DIR / target_locale).glob("*.json"))
    slugs.update(vivc.keys())
    # Keep only slugs that the *current* corpus actually emits. Stale
    # Wikipedia / translation cache entries for slugs that no longer
    # appear in the FR/ES/PT extracted JSONs (e.g. `tempranillo-cencibel`
    # after the ES EU-OJ splitter fix) otherwise leak into GRAPES_INFO
    # and reappear in the chip-filter index as ghost entries.
    corpus_slugs = set(_corpus_grape_names().keys()) | set(vivc.keys())
    slugs &= corpus_slugs

    out: dict[str, dict] = {}
    for slug in slugs:
        vivc_fields = vivc.get(slug) or {}
        native = _load_native_grape(target_locale, slug)
        if native is not None:
            entry = {
                **vivc_fields,
                **native,
                "source_lang": target_locale,
                "is_translated": False,
            }
            _override_name_with_corpus(entry, slug)
            out[slug] = entry
            continue
        translated = _load_translated_grape(target_locale, slug)
        if translated is not None:
            entry = {
                **vivc_fields,
                **translated,
                "is_translated": True,
                "matched_via": "translation",
            }
            _override_name_with_corpus(entry, slug)
            out[slug] = entry
            continue
        if vivc_fields:
            out[slug] = {**vivc_fields, "is_translated": False, "source_lang": None}
    return out


def _truncate_extract(extract: str, max_chars: int) -> str:
    extract = (extract or "").strip()
    if not extract or len(extract) <= max_chars:
        return extract
    cut = extract[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "") + " […]"


def load_style_lexicon(lang: str, max_chars: int = 320) -> dict:
    """Load wine-style data for a locale; returns
    {slug: {extract, page_url, revision_id, thumbnail?, translation?}}
    for each curated entry that has usable text.

    Native Wikipedia fetches (raw/wikipedia/styles/<lang>/) are preferred.
    When a slug has no native entry in `lang` but a translated entry exists
    (raw/translations/styles/<lang>/), the translation is used and a
    `translation` metadata block is attached so the UI can render the
    "translated from <source-locale> Wikipedia" attribution."""
    out: dict[str, dict] = {}
    lang_dir = STYLE_LEXICON_DIR / lang
    if lang_dir.exists():
        for f in lang_dir.glob("*.json"):
            d = json.loads(f.read_text())
            if d.get("missing") or d.get("error"):
                continue
            extract = _truncate_extract(d.get("extract") or "", max_chars)
            if not extract:
                continue
            entry: dict = {
                "extract": extract,
                "page_url": d.get("page_url"),
                "revision_id": d.get("revision_id"),
            }
            if d.get("thumbnail"):
                entry["thumbnail"] = d.get("thumbnail")
            out[d["slug"]] = entry

    tx_dir = STYLE_TRANSLATIONS_DIR / lang
    if tx_dir.exists():
        for f in tx_dir.glob("*.json"):
            d = json.loads(f.read_text())
            slug = d.get("slug") or f.stem
            if slug in out:
                continue  # native fetch wins
            extract = _truncate_extract(d.get("extract") or "", max_chars)
            if not extract:
                continue
            out[slug] = {
                "extract": extract,
                "page_url": d.get("source_page_url") or "",
                "revision_id": d.get("source_revision_id"),
                "translation": {
                    "source_lang": d.get("source_lang") or "",
                    "source_page_url": d.get("source_page_url") or "",
                    "source_wikipedia_title": d.get("source_wikipedia_title") or "",
                    "translator": d.get("translator") or "",
                    "translator_kind": d.get("translator_kind") or "",
                },
            }
    return out


def merge_style_lexicon(lang_lex: dict, fr_lex: dict) -> dict:
    """FR-fallback for slugs the target locale lacks entirely — both as a
    native fetch and as a translation. Used as a last resort so the UI still
    renders something rather than an empty pill."""
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
    copy_brand_assets()

    features: list[dict] = []
    village_features: list[dict] = []
    skipped = 0
    coverage: list[tuple[str, int, int]] = []
    parcel_hits = aires_hits = commune_hits = 0
    dgc_hits: Counter[str] = Counter()
    village_aires_hits = village_commune_hits = village_skipped = 0
    # Geometry-outlier clips (curator-reviewed spurious parts dropped from
    # resolved polygons). Every applied clip and every stale override is
    # collected here and logged after the union loop — nothing is hidden.
    geom_clip_results: list[ClipResult] = []

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
    # Multi-country: also iterate ES extracted records (raw/es/pliegos-
    # extracted/). Stubs are skipped at the geometry-resolution step
    # (no commune list / no Figshare polygon) but kept in the AOCS
    # blob so the wine remains searchable.
    if EXTRACTED_ES.exists():
        for json_path in sorted(EXTRACTED_ES.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text()))
    # Multi-country: also iterate PT extracted records
    # (raw/pt/cadernos-extracted/). Same stub semantics as ES.
    if EXTRACTED_PT.exists():
        for json_path in sorted(EXTRACTED_PT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text()))
    # Multi-country: also iterate IT extracted records
    # (raw/it/disciplinari-extracted/). Same stub semantics as ES/PT.
    if EXTRACTED_IT.exists():
        for json_path in sorted(EXTRACTED_IT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text()))
    # Multi-country: also iterate AT extracted records
    # (raw/at/dokumente-extracted/). Same stub semantics as ES/PT/IT.
    if EXTRACTED_AT.exists():
        for json_path in sorted(EXTRACTED_AT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text()))
    # Multi-country: also iterate SI extracted records
    # (raw/si/dokumenti-extracted/). Same stub semantics as ES/PT/IT/AT.
    if EXTRACTED_SI.exists():
        for json_path in sorted(EXTRACTED_SI.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text()))
    # Augment ES records with national-pliego sidecar data — adds the
    # accessory varieties that the EU-OJ documento único omits. The
    # sidecar carries provenance (URL + sha256 + fetched_at) which
    # propagates through _sources_for() so the panel can attribute the
    # extra varieties to their national pliego PDF.
    n_aug = augment_es_records_with_national_pliegos(extracted_records)
    if n_aug:
        print(
            f"[load] ES national-pliego augmentation: {n_aug} records enriched",
            file=sys.stderr,
        )
    # MASAF disciplinare augmentation for IT stub records — pulls in
    # the full disciplinare text (articles 1/2/3/9) for the ~395 wines
    # whose eAmbrosia entry lacks a documento unico URL. The sidecar
    # provenance (sha256 + URL) flows through _sources_for() so the
    # panel can attribute the data to its MASAF source.
    n_aug_it = augment_it_records_with_masaf(extracted_records)
    if n_aug_it:
        print(
            f"[load] IT MASAF augmentation: {n_aug_it} stub records enriched",
            file=sys.stderr,
        )
    # PT cadernos enumerate every authorised casta as `principal` —
    # the IVV documento-único format we parse doesn't carry a
    # principal/accessory split, and an investigation into the
    # national Portarias on dre.pt confirmed the role distinction
    # isn't published at the regulator level for most DOPs. The PT
    # map detail panel surfaces this caveat inline so the rendering
    # reflects the data we actually have.
    # Process parents first, DGCs second — lets DGCs reuse the parent
    # geometry that was just resolved (same logic for FR DGCs and ES
    # subzonas).
    extracted_records.sort(key=lambda r: (bool(r.get("is_sub_denomination")), r["name"].lower()))

    # Pre-load ES geometry indexes once. ~3 sec; reused across every
    # ES record's resolution.
    es_polygons = ESPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    # Official MAPA national wine production-zone polygons — preferred
    # ES geometry source, used in front of the Bétard fallback.
    es_zones = ESZoneIndex(ROOT / "raw" / "es" / "mapa-zonas" / MAPA_ZONES_FILE)
    print(
        f"[load] ES polygons: {es_polygons.n_pdo_polygons} Figshare PDOs / "
        f"{es_polygons.n_municipios} GISCO municipios / "
        f"{es_zones.n_zones} MAPA zones",
        file=sys.stderr,
    )
    # SIGPAC parcel-precision index for ES wines whose pliegos enumerate
    # polygon inclusions inside shared communes (Priorat ↔ Montsant).
    # Skipped silently if no SIGPAC gpkg files are present.
    es_sigpac = SigpacIndex(
        list(ES_SIGPAC_DIR.glob("SIGPAC_*.gpkg")) if ES_SIGPAC_DIR.exists() else []
    )
    if es_sigpac.n_comarques:
        print(
            f"[load] SIGPAC: {es_sigpac.n_comarques} comarques / "
            f"{es_sigpac.n_municipios} municipios with vineyards",
            file=sys.stderr,
        )
    # Curator-supplied geometry research at raw/es/geometry_research.json.
    # Lets the curator pin an ES wine's geometry by listing INE codes
    # (and SIGPAC parcels for the future) when the auto-resolution chain
    # below can't find a polygon — e.g. single-estate Pagos (Abadía Retuerta,
    # Bolandin, Tharsys, Urbezo) and multi-municipal IGPs whose pliego
    # commune-list parser doesn't pick up (Campo de Calatrava, Terras do Navia).
    es_geom_research: dict[str, dict] = {}
    geom_research_path = ROOT / "raw" / "es" / "geometry_research.json"
    if geom_research_path.exists():
        for it in json.loads(geom_research_path.read_text()):
            es_geom_research[(it.get("name") or "").lower()] = it
        print(
            f"[load] ES geometry_research: {len(es_geom_research)} curator entries",
            file=sys.stderr,
        )
    es_hits: Counter[str] = Counter()
    es_region_by_parent_slug: dict[str, str] = {}

    # PT polygon index: Bétard 2022 (re-uses ES Figshare gpkg, which
    # covers all EU PDOs) + DGT CAOP 2025 (Continente + Açores + Madeira)
    pt_caop_gpkgs = (
        sorted(PT_CAOP_DIR.glob("*.gpkg")) if PT_CAOP_DIR.exists() else []
    )
    pt_polygons = PTPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        caop_gpkgs=pt_caop_gpkgs,
    )
    print(
        f"[load] PT polygons: {pt_polygons.n_pdo_polygons} Figshare PT-PDOs / "
        f"{pt_polygons.n_concelhos} CAOP concelhos",
        file=sys.stderr,
    )
    pt_hits: Counter[str] = Counter()

    # IT polygon index: Bétard 2022 (re-uses ES Figshare gpkg, which
    # covers all EU PDOs including ~412 IT DOPs) + GISCO LAU (filtered
    # to IT comuni for IGT commune-list fallback).
    it_polygons = ITPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    # Official regional-geoportal wine-zone polygons — the preferred IT
    # geometry source, used in front of the Bétard fallback.
    it_zones = ITZoneIndex(ROOT / "raw" / "it" / "regional-zones")
    print(
        f"[load] IT polygons: {it_polygons.n_pdo_polygons} Figshare IT-PDOs / "
        f"{it_polygons.n_comuni} GISCO comuni / "
        f"{it_zones.n_zones} geoportal zones ({len(it_zones.regions)} regions)",
        file=sys.stderr,
    )
    it_hits: Counter[str] = Counter()

    # AT geometry: primary path is commune-precise — ATCommuneIndex
    # resolves each appellation's Einziges-Dokument Bezirk/Gemeinde
    # description into a disjoint union of GISCO municipality polygons
    # (Statistik Austria registry + GISCO LAU). ATPolygonIndex (Bétard
    # 2022) stays loaded only as a defensive fallback for any record
    # whose geo-area text fails to parse.
    at_communes = ATCommuneIndex(
        polbezirke_csv=AT_STATISTIK_DIR / "polbezirke.csv",
        gemliste_csv=AT_STATISTIK_DIR / "gemliste_knz.csv",
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    at_polygons = ATPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] AT geometry: {at_communes.n_gemeinden} GISCO Gemeinden / "
        f"{at_polygons.n_pdo_polygons} Figshare AT-PDOs (fallback)",
        file=sys.stderr,
    )

    # SI polygon index: Bétard 2022 (re-uses ES Figshare gpkg) for the
    # 14 SI DOPs; the 3 SI PGIs (Podravje / Posavje / Primorska) resolve
    # as the union of their constituent region-PDO polygons (see
    # SIPolygonIndex).
    si_polygons = SIPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] SI polygons: {si_polygons.n_pdo_polygons} Figshare SI-PDOs",
        file=sys.stderr,
    )
    si_hits: Counter[str] = Counter()
    at_hits: Counter[str] = Counter()

    # Curator-reviewed geometry-outlier overrides — clips confirmed-spurious
    # parts (upstream-data errors) out of resolved polygons. See
    # scripts/_lib/geometry_outlier_overrides.json and
    # scripts/audit_geometry_outliers.py.
    geom_overrides = GeometryOverrides()
    print(
        f"[load] geometry-outlier overrides: {len(geom_overrides.clip_specs)} clip, "
        f"{len(geom_overrides.whitelist)} whitelist",
        file=sys.stderr,
    )

    for record in tqdm(extracted_records, desc="union", leave=False):
        is_sub_denomination = bool(record.get("is_sub_denomination"))
        country = record.get("country") or "fr"
        # Defaulted here so every geometry branch (and the FR else-branch)
        # can leave it untouched; only the SI branch flips it True.
        _emit_si_features = False

        # ES branch — Figshare PDO polygon → GISCO commune-union → parent
        # fallback. Stubs (`stub: True`) skip geometry; they appear in the
        # AOCS sidebar but not as polygons.
        if country == "es":
            geom = None
            stats = {"matched": 0, "unmatched": 0}
            geom_source = "none"
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            if record.get("stub"):
                geom_source = "stub-no-geometry"
            elif is_sub_denomination and record.get("subzona_communes"):
                geom, stats = es_polygons.union_communes(record["subzona_communes"])
                if geom is not None and not geom.is_empty:
                    geom_source = "gisco-commune-union-subzona"
                else:
                    parent_slug = record.get("parent_slug") or ""
                    parent_geom = parent_geom_by_slug.get(parent_slug)
                    if parent_geom is not None:
                        geom = parent_geom
                        geom_source = "parent-appellation"
                        stats = {"matched": -1, "unmatched": 0}
            else:
                # Curator-research override (geometry_research.json) takes
                # precedence over the auto-resolution chain. For now we union
                # GISCO municipios by INE code from the research entry —
                # parcel-level SIGPAC resolution is a follow-up once the
                # relevant comarca data is fetched.
                research = es_geom_research.get((record.get("name") or "").lower())
                if research:
                    ines = [
                        str(m.get("ine_code", "")).strip()
                        for m in (research.get("municipios") or [])
                        if m.get("ine_code")
                    ]
                    if ines:
                        rgeom, rstats = es_polygons.union_by_ines(ines)
                        if rgeom is not None and not rgeom.is_empty:
                            geom = rgeom
                            geom_source = "geometry-research-municipios"
                            stats = rstats
                # Fall through to the auto-resolution chain only when the
                # research override didn't yield a polygon.
                sigpac_geom = (
                    _resolve_es_sigpac(record, es_sigpac, es_polygons)
                    if geom is None or geom.is_empty
                    else None
                )
                if sigpac_geom is not None and not sigpac_geom.is_empty:
                    # Parcel-precision (Priorat ↔ Montsant) — beats the
                    # municipality-resolution MAPA zone, so it runs first.
                    geom = sigpac_geom
                    geom_source = "sigpac-hybrid-pliego"
                    stats = {"matched": -1, "unmatched": 0}
                if geom is None or geom.is_empty:
                    # Official MAPA national zone polygon, matched by name.
                    mgeom, msrc, mstats = es_zones.resolve(record.get("name") or "")
                    if mgeom is not None and not mgeom.is_empty:
                        geom = mgeom
                        geom_source = msrc
                        stats = mstats
                if geom is None or geom.is_empty:
                    fig = es_polygons.figshare_polygon(record.get("file_number") or "")
                    if fig is not None and not fig.is_empty:
                        geom = fig
                        geom_source = "figshare-pdo"
                        stats = {"matched": -1, "unmatched": 0}
                    else:
                        # IGP fallback chain (Figshare is PDO-only by
                        # design, so all 43 IGPs miss it). Try the
                        # province-wide pattern (Extremadura: "all
                        # municipios of provinces X and Y") then the
                        # explicit commune-list pattern (Ribeiras do
                        # Morrazo, Barbanza e Iria, etc.).
                        igp_geom, igp_source, igp_stats = _resolve_es_igp_fallback(
                            record, es_polygons,
                        )
                        if igp_geom is not None and not igp_geom.is_empty:
                            geom = igp_geom
                            geom_source = igp_source
                            stats = igp_stats
            es_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            # Stash parent geometry for subzona/DGC fallback.
            if not is_sub_denomination and geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_es_features = True
            _emit_pt_features = False
        elif country == "pt":
            # PT branch — Bétard Figshare PDO match → parent fallback.
            # CAOP município-list union is reserved for IGPs in a follow-
            # up; v1 relies on Bétard for the 30 DOPs and falls through
            # to parent inheritance for sub-regiões + no-geometry for the
            # ~14 IGPs that aren't in Bétard.
            geom = None
            stats = {"matched": 0, "unmatched": 0}
            geom_source = "none"
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            if record.get("stub"):
                geom_source = "stub-no-geometry"
            elif is_sub_denomination:
                # Sub-regiões inherit the parent's polygon — they share
                # the parent's Bétard file_number, but `parent-appellation`
                # is the more honest attribution (the polygon's precision
                # is parent-level, not sub-região-level).
                parent_slug = record.get("parent_slug") or ""
                parent_geom = parent_geom_by_slug.get(parent_slug)
                if parent_geom is not None:
                    geom = parent_geom
                    geom_source = "parent-appellation"
                    stats = {"matched": -1, "unmatched": 0}
            else:
                # 1) CAOP commune-list union (preferred — município-level
                #    precision avoids Bétard's whole-município padding
                #    that causes adjacent-DOP polygons to overlap on the
                #    boundary).
                area_text = (record.get("sections") or {}).get("area", "")
                parsed = parse_pt_commune_list(area_text)
                caop_geom, caop_stats = pt_polygons.union_from_parsed(parsed)
                cm = caop_stats["concelhos_matched"]
                dm = caop_stats["distritos_matched"]
                # Threshold: accept CAOP when at least 2 concelho matches
                # or 1 distrito expansion. Single-concelho caches (Pico
                # caderno mentions "São Roque" only — but São Roque do
                # Pico didn't match) fall through to Bétard.
                if caop_geom is not None and not caop_geom.is_empty and (
                    cm >= 2 or dm >= 1
                ):
                    geom = caop_geom
                    geom_source = "caop-concelho-union"
                    stats = {"matched": cm + dm, "unmatched": (
                        caop_stats["concelhos_unmatched"]
                        + caop_stats["distritos_unmatched"]
                    )}
                else:
                    # 2) Bétard 2022 PDO polygon (covers all 30 PT DOPs
                    #    but not IGPs; coarser precision than CAOP).
                    fig = pt_polygons.figshare_polygon(record.get("file_number") or "")
                    if fig is not None and not fig.is_empty:
                        geom = fig
                        geom_source = "figshare-pdo"
                        stats = {"matched": -1, "unmatched": 0}
            pt_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if not is_sub_denomination and geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_es_features = False
            _emit_pt_features = True
            _emit_it_features = False
        elif country == "it":
            # IT branch — geometry precedence:
            #   1. geoportal-zone — official regional production-zone
            #      polygon (consortium-validated), the preferred source.
            #   2. figshare-pdo — Bétard 2022 fallback (whole-municipality
            #      resolution; covers ~408 of the 412 IT DOPs).
            #   3. parent-appellation — sottozone inherit the parent.
            #   4. stub-no-geometry — IGTs / newer DOPs missing Bétard.
            geom = None
            stats = {"matched": 0, "unmatched": 0}
            geom_source = "none"
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            zgeom, zsrc, zstats = it_zones.resolve(record.get("name") or "")
            if zgeom is not None and not zgeom.is_empty:
                geom = zgeom
                geom_source = zsrc
                stats = zstats
            elif is_sub_denomination:
                # Sottozone inherit the parent's polygon — same model
                # as FR DGCs and PT sub-regiões. Precision is parent-
                # level, not sottozona-level.
                parent_slug = record.get("parent_slug") or ""
                parent_geom = parent_geom_by_slug.get(parent_slug)
                if parent_geom is not None:
                    geom = parent_geom
                    geom_source = "parent-appellation"
                    stats = {"matched": -1, "unmatched": 0}
            else:
                fig = it_polygons.figshare_polygon(record.get("file_number") or "")
                if fig is not None and not fig.is_empty:
                    geom = fig
                    geom_source = "figshare-pdo"
                    stats = {"matched": -1, "unmatched": 0}
                elif record.get("stub"):
                    geom_source = "stub-no-geometry"
            # Collapse the per-region geoportal-zone tag for the hit
            # counter so the summary stays readable.
            it_hits["geoportal-zone" if geom_source.startswith("geoportal-zone")
                     else geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if not is_sub_denomination and geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_es_features = False
            _emit_pt_features = False
            _emit_it_features = True
            _emit_at_features = False
        elif country == "at":
            # AT branch — commune-precise: resolve the appellation's
            # Einziges-Dokument Bezirk/Gemeinde description into a
            # disjoint union of GISCO municipality polygons. Falls back
            # to the Bétard Figshare polygon only if the geo-area text
            # fails to parse (content-stubs have no geo-area at all →
            # stub-no-geometry). Austria has no sub-denominations in v1.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = at_communes.resolve(
                record.get("geo_area_brief") or "",
                record.get("bundesland") or "",
            )
            if geom is None or geom.is_empty:
                geom, geom_source, stats = at_polygons.resolve(
                    record.get("file_number") or ""
                )
            at_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_es_features = False
            _emit_pt_features = False
            _emit_it_features = False
            _emit_at_features = True
        elif country == "si":
            # SI branch — Bétard Figshare PDO match for the 14 SI DOPs;
            # the 3 SI PGIs (Podravje / Posavje / Primorska) resolve as
            # the union of their constituent region-PDO polygons (see
            # SIPolygonIndex.resolve). Slovenia has no sub-denominations
            # in v1 — podokoliši are Phase 2 — so there is no parent
            # fallback step.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = si_polygons.resolve(
                record.get("file_number") or ""
            )
            si_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_es_features = False
            _emit_pt_features = False
            _emit_it_features = False
            _emit_at_features = False
            _emit_si_features = True
        else:
            _emit_es_features = False
            _emit_pt_features = False
            _emit_it_features = False
            _emit_at_features = False
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None

        if (_emit_es_features or _emit_pt_features or _emit_it_features
                or _emit_at_features or _emit_si_features):
            # Geometry already resolved above; skip the FR-specific chain.
            pass
        elif is_sub_denomination:
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
        # ES + PT records already had v_geom assigned in their branch above
        # (using the same geom for both detail + village), so skip the
        # FR-specific village resolution.
        if (_emit_es_features or _emit_pt_features or _emit_it_features
                or _emit_at_features or _emit_si_features):
            pass
        elif is_sub_denomination:
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

        # Drop curator-reviewed spurious parts (geometry-outlier overrides).
        # Applied to both the detail and village geometries; for ES/PT/IT/AT
        # they are the same object, so one clip covers both. A stale override
        # (no longer matches) is kept in the ledger and logged loudly below —
        # the geometry is left untouched, never silently altered.
        _pre_clip_geom = geom
        clip_res = geom_overrides.clip(record["slug"], geom)
        geom = clip_res.geom
        if v_geom is _pre_clip_geom:
            v_geom = clip_res.geom
        elif v_geom is not None and not v_geom.is_empty:
            v_geom = geom_overrides.clip(record["slug"], v_geom).geom
        if clip_res.dropped or clip_res.stale:
            geom_clip_results.append(clip_res)

        if geom is None or geom.is_empty:
            skipped += 1
            continue
        if not is_sub_denomination:
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
        # ES + PT + IT + AT + SI records have no `categorie` — every entry
        # is filtered to productType=WINE upstream in stage 00, so they're
        # all wines.
        if record.get("country") in ("es", "pt", "it", "at", "si"):
            is_wine = "1"
        else:
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
        # ES records have `file_number` (e.g. PDO-ES-A0117) instead of FR's
        # numeric id_appellation; we coalesce so the MVT property carries
        # *some* stable identifier regardless of country.
        # Region for ES = Comunidad Autónoma (CCAA), derived from pliego
        # text + curated overrides (see scripts/_lib/es/region.py). For ES
        # subzonas (DGCs), inherit the parent's CCAA — looked up from the
        # already-resolved parent geometry's slug.
        if record.get("country") == "es":
            if is_sub_denomination:
                # Subzonas inherit parent CCAA (already computed when parent
                # was processed earlier in the loop, since records are
                # sorted parents-first).
                parent_slug = record.get("parent_slug") or ""
                region_value = es_region_by_parent_slug.get(parent_slug, "España")
            else:
                region_value = derive_es_ccaa(record)
                es_region_by_parent_slug[record["slug"]] = region_value
        elif record.get("country") == "pt":
            region_value = derive_pt_region(record)
        elif record.get("country") == "it":
            # IT regione (Toscana, Veneto, Piemonte, …). Sub-records
            # inherit the parent's regione — looked up via the
            # already-resolved parent's geometry slug (records are
            # sorted parents-first).
            if is_sub_denomination:
                parent_slug = record.get("parent_slug") or ""
                region_value = es_region_by_parent_slug.get(
                    f"it::{parent_slug}", record.get("regione") or "Italia"
                )
            else:
                region_value = record.get("regione") or derive_it_regione(
                    record,
                    record.get("section_roles", {}).get("geo_area", ""),
                    record.get("name", ""),
                ) or "Italia"
                es_region_by_parent_slug[f"it::{record['slug']}"] = region_value
        elif record.get("country") == "at":
            # AT region = Bundesland (Niederösterreich, Burgenland,
            # Steiermark, …). The 3 multi-state Landwein PGIs are tagged
            # "Österreich". Austria has no sub-denominations in v1.
            region_value = record.get("bundesland") or derive_at_bundesland(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Österreich"
        elif record.get("country") == "si":
            # SI region = vinorodna dežela (Podravje / Posavje /
            # Primorska). The 3 PGIs are the regions themselves.
            # Slovenia has no sub-denominations in v1.
            region_value = record.get("region") or derive_si_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Slovenija"
        else:
            region_value = derive_fr_wine_region(record)
        common_props = {
            "country": record.get("country") or "fr",
            "id_appellation": (
                record.get("id_appellation")
                or record.get("file_number")
                or record.get("id_eambrosia")
                or ""
            ),
            "id_denomination_geo": record.get("id_denomination_geo") or "",
            "slug": record["slug"],
            "name": record["name"],
            "kind": mvt_kind,
            "region": region_value,
            "categorie": categorie,
            "is_wine": is_wine,
            "is_sub_denomination": "1" if is_sub_denomination else "0",
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
    n_clipped = sum(len(r.dropped) for r in geom_clip_results)
    n_stale = sum(len(r.stale) for r in geom_clip_results)
    if geom_clip_results:
        print(
            f"[geo] geometry-outlier overrides: clipped {n_clipped} spurious "
            f"part(s) across {sum(1 for r in geom_clip_results if r.dropped)} "
            f"appellation(s); {n_stale} stale override(s)",
            file=sys.stderr,
        )
        for r in geom_clip_results:
            for line in r.log_lines():
                print(f"[geo]{line}", file=sys.stderr)
    if n_stale:
        print(
            f"[geo] WARNING: {n_stale} geometry-outlier override(s) no longer "
            f"match the source data — re-verify scripts/_lib/"
            f"geometry_outlier_overrides.json and re-run "
            f"scripts/audit_geometry_outliers.py",
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
                layer_url=_fingerprint("/map-data/appellations.pmtiles", PMTILES_OUT),
                villages_layer_url=_fingerprint("/map-data/appellations-villages.pmtiles", PMTILES_VILLAGES_OUT),
                source_type="pmtiles",
                use_translations=not args.no_translations,
            )
        else:
            emit_html(
                features, village_features,
                layer_url=_fingerprint("/map-data/appellations.geojson", GEOJSON_OUT),
                villages_layer_url=_fingerprint("/map-data/appellations-villages.geojson", GEOJSON_VILLAGES_OUT),
                source_type="geojson",
                use_translations=not args.no_translations,
            )
        return 0

    if shutil.which("tippecanoe") is None:
        print("warn: tippecanoe not on PATH (brew install tippecanoe) — skipping pmtiles", file=sys.stderr)
        emit_html(
            features, village_features,
            layer_url=_fingerprint("/map-data/appellations.geojson", GEOJSON_OUT),
            villages_layer_url=_fingerprint("/map-data/appellations-villages.geojson", GEOJSON_VILLAGES_OUT),
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
        layer_url=_fingerprint("/map-data/appellations.pmtiles", PMTILES_OUT),
        villages_layer_url=_fingerprint("/map-data/appellations-villages.pmtiles", PMTILES_VILLAGES_OUT),
        source_type="pmtiles",
        use_translations=not args.no_translations,
    )
    return 0


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


def _sources_for(record: dict) -> dict:
    """Pull authoritative source URLs from the extracted record. The keys
    are country-specific: FR records carry BO Agri / show_texte / product
    URLs; ES records carry the EUR-Lex final URL + the original
    eAmbrosia publication URL; PT records carry the IVV caderno PDF URL.
    The UI branches on `country` to render the right attribution wording."""
    src = record.get("source") or {}
    if record.get("country") == "pt":
        return {
            "country": "pt",
            "ivv_caderno_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "pdf_sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
        }
    if record.get("country") == "it":
        # MASAF disciplinare provenance, if the stage 02f sidecar
        # augmentation kicked in for this slug. The AOC-blob phase
        # re-reads the on-disk JSON (which doesn't carry the
        # augmentation), so fall back to the slug-keyed cache.
        masaf = record.get("masaf") or _IT_MASAF_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "it",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            # MASAF national disciplinare (populated for stubs that
            # stage 02f augmented). Empty for wines already extracted
            # from EUR-Lex documento unico.
            "masaf_filename": masaf.get("filename", ""),
            "masaf_pdf_filename": masaf.get("pdf_filename", ""),
            "masaf_sha256": masaf.get("sha256", ""),
            "masaf_fetched_at": masaf.get("fetched_at", ""),
            "masaf_match_how": masaf.get("match_how", ""),
            "masaf_bundle_key": masaf.get("bundle_key", ""),
            "masaf_archive_path": masaf.get("archive_path", ""),
            "masaf_parser_template": masaf.get("parser_template", ""),
            "masaf_override_url": masaf.get("override_url", ""),
        }
    if record.get("country") == "at":
        # Austria: every wine carries an EUR-Lex Einziges-Dokument URL —
        # no national-pliego fallback layer (unlike ES / IT).
        return {
            "country": "at",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
        }
    if record.get("country") == "si":
        # Slovenia: only Cviček carries a fetchable EUR-Lex single
        # document; the other 16 are content-stubs awaiting the national
        # specification (Phase 2). eAmbrosia + file number always resolve.
        return {
            "country": "si",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
        }
    if record.get("country") == "es":
        # The AOC-blob phase re-reads the on-disk extracted JSON (which
        # doesn't carry the augmentation), so fall back to the slug-keyed
        # cache populated by augment_es_records_with_national_pliegos().
        nat = record.get("national_pliego") or _ES_NATIONAL_PLIEGO_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "es",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_pliego_url": nat.get("url", ""),
            "national_pliego_sha256": nat.get("sha256", ""),
            "national_pliego_fetched_at": nat.get("fetched_at", ""),
            "national_pliego_added_slugs": nat.get("added_slugs") or [],
        }
    return {
        "country": "fr",
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


def _fingerprint(url: str, file: Path) -> str:
    """Suffix `url` with `?v=<sha8>` derived from `file`'s bytes.

    Pmtiles + geojson assets are served with a 30-day browser cache
    (Bunny default). The HTML is short-cached separately, but its
    references to map-data assets would otherwise pin clients to stale
    polygon / grape data across rebuilds. A content-derived suffix
    bypasses the cache exactly when the file changes."""
    if not file.exists():
        return url
    h = hashlib.sha256()
    with file.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return f"{url}?v={h.hexdigest()[:8]}"


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

    # Curated, source-cited per-appellation notes (a bounded narrative
    # layer — e.g. the Teran SI/HR cross-border labelling note). Keyed by
    # slug; `__`-prefixed keys are the file's own documentation.
    appellation_notes: dict[str, dict] = {}
    _notes_path = ROOT / "scripts" / "_lib" / "appellation_notes.json"
    if _notes_path.exists():
        try:
            appellation_notes = {
                k: v for k, v in json.loads(_notes_path.read_text()).items()
                if not k.startswith("__")
            }
        except (ValueError, OSError) as exc:
            print(f"[warn] appellation_notes.json: {exc}", file=sys.stderr)

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
        # Try the FR path first, then the ES path, then the PT path. Slugs
        # are globally unique across countries (see each stage 02's slug
        # derivation), so at most one path matches.
        country = p.get("country") or "fr"
        ext_dir = {
            "es": EXTRACTED_ES,
            "pt": EXTRACTED_PT,
            "it": EXTRACTED_IT,
            "at": EXTRACTED_AT,
            "si": EXTRACTED_SI,
        }.get(country, EXTRACTED)
        ext_path = ext_dir / f"{slug}.json"
        summary = ""
        sources: dict = {}
        grape_names: dict[str, str] = {}
        parent_slug_for_facts = p.get("parent_slug", "") or ""
        if ext_path.exists():
            rec = json.loads(ext_path.read_text())
            summary = derive_summary(rec)
            sources = _sources_for(rec)
            # Per-appellation cahier spelling per slug — drives the pill
            # label so the rendered name matches what the regulator
            # actually published (PT Douro shows "Aragonez", ES Rioja
            # shows "Tempranillo", FR Bandol shows "mourvèdre"), with
            # the VIVC canonical name added in brackets when distinct.
            for d in (rec.get("grapes") or {}).get("details") or []:
                s_slug = d.get("slug")
                s_name = (d.get("name") or "").strip()
                if s_slug and s_name and s_name.lower() != s_slug:
                    grape_names[s_slug] = s_name
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
            "is_sub_denomination": p.get("is_sub_denomination", "0") == "1",
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
            "grape_names": grape_names,
            "summary": summary,
            "sources": sources,
            "terroir_facts": terroir_facts,
            "note": appellation_notes.get(slug),
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

    # Advanced-mode style facet is a taxonomy-driven tree. Per node we emit
    # `(slug, parent, depth, count)` in declared DFS order; `count` aggregates
    # the slug itself plus every descendant, so checking a parent reflects
    # what selecting the whole subtree would yield. Nodes with zero aggregate
    # count drop out (along with their entire subtree, by definition).
    taxonomy_order = _taxonomy_dfs_order()
    descendant_sets = {slug: _taxonomy_descendants(slug) for slug, _, _ in taxonomy_order}
    panel_only = set(_taxonomy_all_slugs()) - {s for s, _, _ in taxonomy_order}
    for slug, dset in descendant_sets.items():
        descendant_sets[slug] = dset - panel_only
    agg_style_counts: dict[str, int] = {slug: 0 for slug in descendant_sets}
    for rec in aocs.values():
        record_styles = set(rec.get("styles") or [])
        if not record_styles:
            continue
        for slug, dset in descendant_sets.items():
            if record_styles & dset:
                agg_style_counts[slug] += 1
    facet_styles_tree = [
        {"slug": slug, "parent": parent, "depth": depth,
         "count": agg_style_counts.get(slug, 0)}
        for slug, parent, depth in taxonomy_order
        if agg_style_counts.get(slug, 0) > 0
    ]
    style_descendants = _taxonomy_descendants_map()

    facets = dict(
        layer_url=layer_url,
        villages_layer_url=villages_layer_url,
        source_type=source_type,
        aocs=aocs,
        facet_styles_tree=facet_styles_tree,
        style_descendants=style_descendants,
        facet_styles_simple=facet_styles_simple,
        facet_regions=sort_facet(region_counts),
        area_quartiles=(area_q1, area_q3),
        vivc_by_slug=_load_vivc_by_slug(),
    )
    fr_styles_lex = load_style_lexicon("fr")
    for lang in LOCALES:
        lex = build_grapes_info(lang)
        if lang == "fr":
            styles_lex = fr_styles_lex
        else:
            styles_lex = merge_style_lexicon(load_style_lexicon(lang), fr_styles_lex)
        translations = load_summary_translations(lang) if use_translations else {}
        # The translation overlay is source-language-aware: a record's
        # canonical text stays untouched only when the current locale matches
        # its source language (FR for INAO cahiers, ES for EU pliegos).
        # Otherwise the per-locale 02c cache wins and a `summary_translation`
        # marker is attached so the panel renders the "machine translated"
        # attribution. FR also uses its own cache for hand-rewritten
        # summaries that fix extraction quirks — same provenance as the
        # cahier, so no marker.
        aocs_for_lang = {}
        for slug, rec in aocs.items():
            rec_country = rec.get("country")
            src_lang = rec_country if rec_country in ("es", "pt", "it", "at", "si") else "fr"
            t = translations.get(slug)
            if not t:
                new_rec = rec
            else:
                new_rec = {**rec, "summary": t["summary"]}
                if lang != src_lang:
                    new_rec["summary_translation"] = {
                        "translator": t["translator"],
                        "source_pdf_url": t["source_pdf_url"],
                        "source_pdf_filename": t["source_pdf_filename"],
                    }
            # Resolve the curated cross-border note to the current locale
            # (en fallback). Only the handful of records in
            # appellation_notes.json carry one; the rest have note=None.
            note_obj = rec.get("note")
            if note_obj:
                by_locale = note_obj.get("note") or {}
                note_text = by_locale.get(lang) or by_locale.get("en") or ""
                if note_text:
                    new_rec = {
                        **new_rec,
                        "note": {"text": note_text,
                                 "sources": note_obj.get("sources") or []},
                    }
            aocs_for_lang[slug] = new_rec
        # Overlay translated terroir-fact bullets only for records whose
        # source language differs from the current locale (canonical bullets
        # are already in the source language). The per-locale cache covers
        # both FR-source records (for en/es/nl) and ES-source records (for
        # en/fr/nl); we filter the overlay set per-record.
        facts_translations: dict[str, dict] = {}
        if use_translations:
            all_facts_translations = load_terroir_facts_translations(lang)
            def _src_lang_for(slug: str) -> str:
                c = (aocs.get(slug, {}) or {}).get("country")
                return c if c in ("es", "pt", "it", "at", "si") else "fr"
            facts_translations = {
                slug: t for slug, t in all_facts_translations.items()
                if lang != _src_lang_for(slug)
            }
            if facts_translations:
                aocs_for_lang = overlay_translated_facts(aocs_for_lang, facts_translations)
        out = (WIKI / "index.html") if lang == "en" else (WIKI / lang / "index.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Pass a swapped facets dict so the per-locale `aocs` is what gets serialised.
        per_locale_facets = {**facets, "aocs": aocs_for_lang}
        out.write_text(render_map_html(
            **per_locale_facets, locale=lang, grapes_info=lex, styles_info=styles_lex,
        ))
        translated_n = sum(1 for v in lex.values() if v.get("is_translated"))
        with_vivc_n = sum(1 for v in lex.values() if v.get("vivc_id"))
        styles_fallback_n = sum(1 for v in styles_lex.values() if v.get("lang_fallback"))
        print(
            f"[html] {out.relative_to(ROOT)} "
            f"(locale={lang}, grape_info={len(lex)}, translated={translated_n}, "
            f"vivc_linked={with_vivc_n}, "
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


_WEBMANIFEST = {
    "name": "Open Wine Map",
    "short_name": "Open Wine Map",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#1a1a1a",
    "theme_color": "#7A1F2B",
    "icons": [
        {"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/assets/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}


def copy_brand_assets() -> None:
    """Mirror raw/assets/ into wiki/assets/ and emit /site.webmanifest.

    Source-of-truth assets live in raw/assets/ (gitignored alongside other
    raw inputs). Stage 04 copies them into the published wiki/ tree on each
    run so deploy.sh ships them. Skips files that are byte-identical to the
    existing destination to keep reruns no-op.
    """
    if not ASSETS_SRC.exists():
        print(f"[assets] {ASSETS_SRC.relative_to(ROOT)} missing; skipping", file=sys.stderr)
        return
    ASSETS_OUT.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(ASSETS_SRC.iterdir()):
        if not src.is_file():
            continue
        dst = ASSETS_OUT / src.name
        if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.read_bytes() == src.read_bytes():
            continue
        shutil.copy2(src, dst)
        copied += 1

    manifest_path = WIKI / "site.webmanifest"
    manifest_bytes = (json.dumps(_WEBMANIFEST, indent=2) + "\n").encode()
    if not manifest_path.exists() or manifest_path.read_bytes() != manifest_bytes:
        manifest_path.write_bytes(manifest_bytes)
        copied += 1
    print(f"[assets] mirrored {ASSETS_SRC.relative_to(ROOT)} → {ASSETS_OUT.relative_to(ROOT)} ({copied} updated)", file=sys.stderr)


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
