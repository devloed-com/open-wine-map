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

from _lib.aires import load_aires
from _lib.aires import lookup as lookup_aire
from _lib.aoc_translations import (
    load_summary_translations,
    load_terroir_facts_translations,
)
from _lib.appellation_urls import load as load_appellation_urls
from _lib.appellation_urls import resolve as resolve_appellation_url
from _lib.at.gemeinde import ATCommuneIndex
from _lib.at.geometry import ATPolygonIndex
from _lib.at.region import derive_bundesland as derive_at_bundesland
from _lib.be.geometry import BEPolygonIndex
from _lib.be.region import derive_region as derive_be_region
from _lib.bg.geometry import BGPolygonIndex
from _lib.bg.region import derive_region as derive_bg_region
from _lib.ch.geometry import CHCommuneIndex, GESitgIndex
from _lib.ch.geometry import resolve as ch_resolve_geometry
from _lib.ch.region import derive_region as derive_ch_region
from _lib.cy.geometry import CYPolygonIndex
from _lib.cy.region import derive_region as derive_cy_region
from _lib.cz.geometry import CZPolygonIndex
from _lib.cz.region import derive_region as derive_cz_region
from _lib.de.geometry import DEPolygonIndex
from _lib.de.region import derive_region as derive_de_region
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
from _lib.es.region import (
    CCAA_TO_PROVINCE_INES,
    PROVINCE_TO_INE,
)
from _lib.es.region import (
    derive_ccaa as derive_es_ccaa,
)
from _lib.es.sigpac import SigpacIndex
from _lib.es.zones import MAPA_ZONES_FILE, ESZoneIndex
from _lib.fr_wine_region import derive_wine_region as derive_fr_wine_region
from _lib.geometry_overrides import ClipResult, GeometryOverrides
from _lib.gr.geometry import GRPolygonIndex
from _lib.gr.region import derive_region as derive_gr_region
from _lib.hr.geometry import HRPolygonIndex
from _lib.hr.region import derive_region as derive_hr_region
from _lib.hu.geometry import HUPolygonIndex
from _lib.hu.region import derive_region as derive_hu_region
from _lib.i18n import LOCALES, compile_catalogs
from _lib.it.comune import ITCommuneIndex
from _lib.it.geometry import ITPolygonIndex
from _lib.it.region import derive_regione as derive_it_regione
from _lib.it.sottozona import extract_sottozone as extract_it_sottozone
from _lib.it.zones import ITZoneIndex
from _lib.lieu_dit import LieuDitIndex, derive_climat_name
from _lib.lu.geometry import LUPolygonIndex
from _lib.lu.region import derive_region as derive_lu_region
from _lib.map_template import render as render_map_html
from _lib.mt.geometry import MTPolygonIndex
from _lib.nl.geometry import NLPolygonIndex
from _lib.nl.region import derive_region as derive_nl_region
from _lib.parcellaire import build_aoc_polygons
from _lib.pt.commune_list import parse_commune_list as parse_pt_commune_list
from _lib.pt.geometry import PTPolygonIndex
from _lib.pt.region import derive_region as derive_pt_region
from _lib.ro.geometry import ROPolygonIndex
from _lib.ro.region import derive_region as derive_ro_region
from _lib.si.geometry import SIPolygonIndex
from _lib.si.region import derive_region as derive_si_region
from _lib.sk.geometry import SKPolygonIndex
from _lib.sk.region import derive_region as derive_sk_region
from _lib.style_taxonomy import (
    all_slugs as _taxonomy_all_slugs,
)
from _lib.style_taxonomy import (
    descendants as _taxonomy_descendants,
)
from _lib.style_taxonomy import (
    descendants_map as _taxonomy_descendants_map,
)
from _lib.style_taxonomy import (
    simple_bucket as _taxonomy_simple_bucket,
)
from _lib.style_taxonomy import (
    taxonomy_dfs_order as _taxonomy_dfs_order,
)
from _lib.summaries import derive_summary
from _lib.wiki import is_grape_summary
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from tqdm import tqdm
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
EXTRACTED_ES = ROOT / "raw" / "es" / "pliegos-extracted"
NATIONAL_PLIEGOS_ES = ROOT / "raw" / "es" / "national-pliegos-extracted"
ES_FIGSHARE_GPKG = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
ES_GISCO_LAU_ZIP = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"
ES_SIGPAC_DIR = ROOT / "raw" / "es" / "sigpac"
# GISCO NUTS for the GR PGI region fallback: NUTS-3 (regional units) +
# NUTS-2 (regions, shared with the NL pipeline's LEVL_2 file).
GR_NUTS3_GEOJSON = ROOT / "raw" / "gr" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_3.geojson"
GR_NUTS2_GEOJSON = ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
EXTRACTED_PT = ROOT / "raw" / "pt" / "cadernos-extracted"
PT_CAOP_DIR = ROOT / "raw" / "pt" / "caop"
EXTRACTED_IT = ROOT / "raw" / "it" / "disciplinari-extracted"
MASAF_DISCIPLINARI_IT = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
IT_REGIONAL_REGISTERS = ROOT / "raw" / "it" / "regional-variety-registers"
EXTRACTED_AT = ROOT / "raw" / "at" / "dokumente-extracted"
AT_STATISTIK_DIR = ROOT / "raw" / "at" / "statistik"
EXTRACTED_DE = ROOT / "raw" / "de" / "dokumente-extracted"
PRODUKTSPEZIFIKATION_DE = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
EXTRACTED_SI = ROOT / "raw" / "si" / "dokumenti-extracted"
SPECIFIKACIJE_SI = ROOT / "raw" / "si" / "specifikacije-extracted"
EXTRACTED_HR = ROOT / "raw" / "hr" / "dokumenti-extracted"
SPECIFIKACIJE_HR = ROOT / "raw" / "hr" / "specifikacije-extracted"
EXTRACTED_HU = ROOT / "raw" / "hu" / "dokumentumok-extracted"
EXTRACTED_RO = ROOT / "raw" / "ro" / "dokumente-extracted"
EXTRACTED_BG = ROOT / "raw" / "bg" / "dokumenti-extracted"
NATIONAL_SPECS_BG = ROOT / "raw" / "bg" / "national-specs-extracted"
EXTRACTED_GR = ROOT / "raw" / "gr" / "dokumenti-extracted"
NATIONAL_SPECS_GR = ROOT / "raw" / "gr" / "national-specs-extracted"
EXTRACTED_CY = ROOT / "raw" / "cy" / "dokumenti-extracted"
NATIONAL_SPECS_CY = ROOT / "raw" / "cy" / "national-specs-extracted"
NATIONAL_SPECS_RO = ROOT / "raw" / "ro" / "national-specs-extracted"
NATIONAL_SPECS_HU = ROOT / "raw" / "hu" / "national-specs-extracted"
EXTRACTED_SK = ROOT / "raw" / "sk" / "dokumenty-extracted"
NATIONAL_SPECS_SK = ROOT / "raw" / "sk" / "national-specs-extracted"
EXTRACTED_CZ = ROOT / "raw" / "cz" / "dokumenty-extracted"
NATIONAL_SPECS_CZ = ROOT / "raw" / "cz" / "national-specs"
EXTRACTED_CH = ROOT / "raw" / "ch" / "dokumente-extracted"
CH_SWISSTOPO_GPKG = ROOT / "raw" / "ch" / "swisstopo" / "swissboundaries3d_2026-01_2056_5728.gpkg"
CH_SITG_GEOJSON = ROOT / "raw" / "ch" / "geoportals" / "sitg-vit-vignoble-ao.geojson"
EXTRACTED_LU = ROOT / "raw" / "lu" / "cahier-extracted"
LU_IVV_VINEYARDS_SHP = (
    ROOT / "raw" / "lu" / "ivv" / "vineyards" / "weinberge-lu-2022" / "weinberge_lu_2022.shp"
)
EXTRACTED_BE = ROOT / "raw" / "be" / "dokumenten-extracted"
EXTRACTED_NL = ROOT / "raw" / "nl" / "dokumenten-extracted"
EXTRACTED_MT = ROOT / "raw" / "mt" / "dokumente-extracted"
NL_NUTS_GEOJSON = ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
COMMUNES_GEOJSON = ROOT / "raw" / "ign" / "communes.geojson"
WIKI = ROOT / "wiki"
SITE_BASE_URL = "https://www.openwinemap.com"
MAP_DATA = WIKI / "map-data"
ASSETS_SRC = ROOT / "raw" / "assets"
ASSETS_OUT = WIKI / "assets"
VENDOR_SRC = ROOT / "scripts" / "_lib" / "vendor"
GEOJSON_OUT = MAP_DATA / "appellations.geojson"
PMTILES_OUT = MAP_DATA / "appellations.pmtiles"
GEOJSON_VILLAGES_OUT = MAP_DATA / "appellations-villages.geojson"
PMTILES_VILLAGES_OUT = MAP_DATA / "appellations-villages.pmtiles"
LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes"
GRAPE_TRANSLATIONS_DIR = ROOT / "raw" / "translations" / "grapes"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"
WIKIDATA_QIDS = ROOT / "raw" / "wikidata" / "qids-by-slug.json"
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
# populated by augment_de_records_with_produktspezifikation() and read
# by _sources_for() / panel rendering — same shape as the IT/ES caches.
_DE_PRODUKTSPEZIFIKATION_BY_SLUG: dict[str, dict] = {}

# populated by augment_it_records_with_masaf() and read by _sources_for()
# / the AOC-blob phase (which re-reads each on-disk extracted JSON,
# bypassing in-memory augmentation).
_IT_MASAF_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of CZ national-spec provenance, populated by
# augment_cz_records_with_national_specs(). Mirrors the ES/IT/DE caches.
# Czech wine law publishes one national variety roster (Vyhláška 88/2017
# Sb. Příloha č. 2) that applies to every jakostní víno regardless of
# podoblast, so every augmented CZ wine carries the same provenance
# block — but per-record so _sources_for() can surface it uniformly.
_CZ_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of CZ CHZO-spec provenance (the SZPI „moravské“ /
# „české“ product specifications). Every CZ wine sits in one of the two
# regions (Morava / Čechy), so all 13 carry the region spec's provenance
# — the terroir bullets (02d) ground on its section-1 region description.
# Populated by augment_cz_records_with_national_specs().
_CZ_CHZO_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of SI specifikacija provenance + augmented payload,
# populated by augment_si_records_with_specifikacija(). Two source
# patterns feed it (MKGP per-wine .doc, Uradni list RS pravilnik HTML);
# the sidecar's `parser_template` distinguishes them for attribution.
_SI_SPECIFIKACIJA_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of HR specifikacija provenance, populated by
# augment_hr_records_with_specifikacija(). The 16 grandfathered HR wines
# whose EU-OJ JEDINSTVENI DOKUMENT was never published are augmented from
# the Ministarstvo poljoprivrede per-wine SPECIFIKACIJA PROIZVODA (stage
# 02f). `parser_template` distinguishes the lettered .doc/.pdf path
# (mps-specifikacija-v1) from the docx fallback (mps-specifikacija-docx).
_HR_SPECIFIKACIJA_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of GR national-spec provenance, populated by
# augment_gr_records_with_national_specs(). 132 of the 138 grandfathered
# GR wines are augmented from the ΥΠΑΑΤ national προδιαγραφή / τεχνικός
# φάκελος (stage 02f) — 87 structured-PDF ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ, 43 `.doc`,
# 2 `.docx`. `parser_template` (gr-national-{pdf,doc,docx}) distinguishes.
_GR_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}
# Slug-keyed cache of CY national-spec provenance, populated by
# augment_cy_records_with_national_specs(). All 11 CY wines are
# grandfathered names augmented from the moa.gov.cy τεχνικός φάκελος
# (stage 02f) — a Greek ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ PDF, OCR'd when image-only.
_CY_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of RO national-spec provenance, populated by
# augment_ro_records_with_national_specs(). The 14 grandfathered RO wines
# (only an Ares(...) reference in eAmbrosia, no EU-OJ DOCUMENT UNIC) are
# augmented from the ONVPV caiet de sarcini (stage 02f, onvpv-caiet-de-
# sarcini-v1 parser). Unlike GR/HR, the merge also carries `geo_communes`
# so the 2 grandfathered IGPs resolve via the GISCO commune-union chain.
_RO_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of HU national-spec provenance, populated by
# augment_hu_records_with_national_specs(). The 15 grandfathered HU wines
# (only an Ares(...) reference in eAmbrosia, no EU-OJ EGYSÉGES DOKUMENTUM)
# are augmented from the Agrárminisztérium termékleírás PDF (stage 02f,
# hu-termekleiras-v1 parser). The merge carries grapes + terroir text +
# geo_communes so the panel + 02d ground on the national spec.
_HU_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of BG national-spec provenance, populated by
# augment_bg_records_with_national_specs(). The 51 grandfathered BG wines
# (only an Ares(...) reference in eAmbrosia, no EU-OJ ЕДИНЕН ДОКУМЕНТ) are
# augmented from the ИАЛВ / IAVV per-wine продуктова спецификация (stage
# 02f, iavv-specifikacija-v1 parser — eavw.com PDF, numbered 1–8 template:
# 5 сортове / 6 Връзка с географския район / 3 район).
_BG_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}

# Slug-keyed cache of SK national-spec provenance, populated by
# augment_sk_records_with_national_specs(). The 5 grandfathered SK wines
# (only an Ares(...) reference in eAmbrosia, no EU-OJ JEDNOTNÝ DOKUMENT) are
# augmented from the ÚPV SR per-wine špecifikácia výrobku (stage 02f,
# upv-sr-specifikacia-v1 parser — indprop.gov.sk PDF, lettered a–i template:
# f) označenie odrôd / g) údaje potvrdzujúce spojitosť / d) zemepisná oblasť).
_SK_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}


# Cross-border PDOs that physically extend across more than one country.
# Keyed by eAmbrosia file_number → list of secondary country codes (the
# primary country sits in `record.country` from stage 02). The map shows
# one polygon (BE-side ownership for PDO-BE+NL-02172), but the panel
# meta line renders flags + names for every country the appellation
# spans so users can find it from either side.
_CROSS_BORDER_COUNTRY_ALIASES: dict[str, list[str]] = {
    # Maasvallei Limburg — straddles the BE/NL Limburg border in the Maas
    # valley. BE-primary by eAmbrosia file_number ordering; the NL side
    # is the southern tip of the Dutch province of Limburg.
    "PDO-BE+NL-02172": ["nl"],
}


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
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
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


def augment_si_records_with_specifikacija(records: list[dict]) -> int:
    """In-place merge of SI national-spec sidecar data into stub records.

    Sibling of `augment_it_records_with_masaf`. The 16 grandfathered SI
    wines (every wine except Cviček) ship as content-stubs because their
    eAmbrosia entry has no fetchable EU-OJ ENOTNI DOKUMENT URL. Stage
    02f (`scripts/si/02f_extract_specifikacije.py`) extracts the
    canonical Slovenian regulator source — either an MKGP per-wine
    `.doc` specifikacija proizvoda or an Uradni list RS pravilnik HTML —
    into a sidecar at `raw/si/specifikacije-extracted/<slug>.json`.

    For each SI stub with a matching sidecar:
      - summary           ← MKGP §2 (opis vin) or pravilnik §2
      - grapes            ← MKGP §6 (sorte) or pravilnik Article-5 +
                            priloga 2 (priporočene → principal,
                            dovoljene → accessory)
      - geo_area_brief    ← MKGP §4 (opredelitev geografskega območja)
      - link_to_terroir   ← MKGP §7 (povezava z geografskim območjem)
                            (pravilnik-derived records have empty
                            link_to_terroir — pravilniki are regulatory
                            lists, not narrative documents)
      - styles            ← MKGP-derived colour/sparkling/predikat tags
      - section_roles     ← unified role dict so 02d can read terroir
                            text uniformly
      - stub_reason       ← prefixed `specifikacija:` so the audit can
                            tell EU-OJ-extracted from spec-augmented
      - specifikacija     ← provenance block (url, sha256, fetched_at,
                            parser_template, source_org, license)

    `record["stub"]` stays True — the record is still NOT an EU-OJ
    extraction, just augmented with the canonical Slovenian regulator
    source. Stage 03 / 04 callers use the `specifikacija` block to
    distinguish and to render attribution.

    Returns the number of records augmented.
    """
    _SI_SPECIFIKACIJA_BY_SLUG.clear()
    if not SPECIFIKACIJE_SI.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "si":
            continue
        if not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = SPECIFIKACIJE_SI / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "final_url": src.get("final_url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "",
            "license": src.get("license") or "",
            "parser_template": sidecar.get("parser_template") or "",
            "matched_okoliši": sidecar.get("matched_okoliši") or [],
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes"):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            existing_styles = set(record.get("styles") or [])
            record["styles"] = sorted(existing_styles | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("specifikacija:"):
            record["stub_reason"] = f"specifikacija:{record['stub_reason']}"
        record["specifikacija"] = provenance
        _SI_SPECIFIKACIJA_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_hr_records_with_specifikacija(records: list[dict]) -> int:
    """In-place merge of HR national-spec sidecar data into stub records.

    Sibling of `augment_si_records_with_specifikacija`. The 16
    grandfathered HR wines (everything except Muškat momjanski + Ponikve)
    ship as content-stubs because their eAmbrosia entry has no fetchable
    EU-OJ JEDINSTVENI DOKUMENT URL. Stage 02f
    (`scripts/hr/02f_extract_specifikacije.py`) extracts the canonical
    Ministarstvo poljoprivrede per-wine SPECIFIKACIJA PROIZVODA (14
    `.doc`, 1 `.docx`, 1 PDF) into a sidecar at
    `raw/hr/specifikacije-extracted/<slug>.json`.

    For each HR stub with a matching sidecar:
      - summary           ← lettered section b) (opis svojstava vina)
      - grapes            ← section f) (sorte vinove loze; colour-grouped,
                            all principal — the MPS spec has no
                            principal/accessory split, same as PT/IT)
      - geo_area_brief    ← section d) (granice područja)
      - link_to_terroir   ← section g) (…povezane sa zemljopisnim
                            uvjetima); empty for the Primorska docx
      - styles            ← colour/sparkling/dessert/liqueur tags
      - section_roles     ← unified role dict so 02d reads terroir text
      - stub_reason       ← prefixed `specifikacija:` so the audit can
                            tell EU-OJ-extracted from spec-augmented
      - specifikacija     ← provenance block (url, sha256, fetched_at,
                            parser_template, source_org, license)

    `record["stub"]` stays True — the record is still NOT an EU-OJ
    extraction, just augmented with the canonical Croatian regulator
    source. Returns the number of records augmented.
    """
    _HR_SPECIFIKACIJA_BY_SLUG.clear()
    if not SPECIFIKACIJE_HR.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "hr":
            continue
        if not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = SPECIFIKACIJE_HR / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "final_url": src.get("final_url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "",
            "license": src.get("license") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            existing_styles = set(record.get("styles") or [])
            record["styles"] = sorted(existing_styles | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("specifikacija:"):
            record["stub_reason"] = f"specifikacija:{record['stub_reason']}"
        record["specifikacija"] = provenance
        _HR_SPECIFIKACIJA_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_gr_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of GR national-spec sidecar data into stub records.

    Sibling of `augment_si_records_with_specifikacija`. 138 of 147 GR
    wines ship as content-stubs (no fetchable EU-OJ ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ).
    Stage 02f (`scripts/gr/02f_extract_national_specs.py`) parses the
    ΥΠΑΑΤ national προδιαγραφή / τεχνικός φάκελος fetched by stage 01c
    into `raw/gr/national-specs-extracted/<slug>.json` (132 of 138; the
    other 6 are unresolved — see CURATOR_TODO.md).

    For each GR stub with a matching sidecar:
      - grapes            ← §6 ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ (PDF list) or the
                            grape section's capitalised-token scan (.doc prose)
      - link_to_terroir   ← §7 ΔΕΣΜΟΣ ΜΕ ΤΗΝ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:` so the audit can tell
                            EU-OJ-extracted from spec-augmented wines
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True — still NOT an EU-OJ extraction, just
    augmented with the canonical ΥΠΑΑΤ source. Returns count augmented.
    """
    _GR_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_GR.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "gr" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_GR / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("source_url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "ypaat",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _GR_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_cy_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of CY national-spec sidecar data into stub records.

    Sibling of `augment_gr_records_with_national_specs`. All 11 CY wines
    ship as content-stubs (no fetchable EU-OJ ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ). Stage 02f
    (`scripts/cy/02f_extract_national_specs.py`) parses the moa.gov.cy
    Department-of-Agriculture τεχνικός φάκελος (Greek single-document
    PDF, OCR'd when image-only) into `raw/cy/national-specs-extracted/
    <slug>.json`; this merges grapes / terroir text / styles / geo-area
    into the in-memory stub. `record["stub"]` stays True. Returns the
    count augmented."""
    _CY_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_CY.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "cy" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_CY / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("source_url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "moa-cy",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _CY_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_bg_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of BG national-spec sidecar data into stub records.

    Sibling of `augment_gr_records_with_national_specs`. 51 of 54 BG wines
    ship as content-stubs (no fetchable EU-OJ ЕДИНЕН ДОКУМЕНТ). Stage 02f
    (`scripts/bg/02f_extract_national_specs.py`) parses the ИАЛВ / IAVV
    per-wine продуктова спецификация PDF fetched by stage 01c into
    `raw/bg/national-specs-extracted/<slug>.json` (51 of 51).

    For each BG stub with a matching sidecar:
      - grapes            ← section 5 (Винени сортове грозде, colour-split)
      - link_to_terroir   ← section 6 (Връзка с географския район)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:` so the audit can tell
                            EU-OJ-extracted from spec-augmented wines
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True — still NOT an EU-OJ extraction, just
    augmented with the canonical ИАЛВ source. Returns count augmented.
    """
    _BG_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_BG.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "bg" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_BG / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "iavv",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _BG_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_sk_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of SK national-spec sidecar data into stub records.

    Sibling of `augment_bg_records_with_national_specs`. 5 of the SK
    content-stubs (no fetchable EU-OJ JEDNOTNÝ DOKUMENT) are augmented from
    the ÚPV SR (indprop.gov.sk) per-wine špecifikácia výrobku. Stage 02f
    (`scripts/sk/02f_extract_national_specs.py`) parses each text-layer PDF
    fetched by stage 01c into `raw/sk/national-specs-extracted/<slug>.json`.

    For each SK stub with a matching sidecar:
      - grapes            ← section f) označenie odrody alebo odrôd
      - link_to_terroir   ← section g) údaje potvrdzujúce spojitosť
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:` so the audit can tell
                            EU-OJ-extracted from spec-augmented wines
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True — still NOT an EU-OJ extraction, just
    augmented with the canonical ÚPV SR source. Returns count augmented.
    """
    _SK_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_SK.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "sk" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_SK / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "upv-sr",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _SK_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_ro_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of RO national-spec sidecar data into stub records.

    Sibling of `augment_gr_records_with_national_specs`. The 14
    grandfathered RO wines (eAmbrosia carries only a non-fetchable
    `Ares(...)` reference — no EU-OJ DOCUMENT UNIC) ship as content-stubs.
    Stage 02f (`scripts/ro/02f_extract_national_specs.py`) parses the
    ONVPV caiet de sarcini fetched by stage 01c into
    `raw/ro/national-specs-extracted/<slug>.json`.

    For each RO stub with a matching sidecar:
      - grapes            ← §IV Soiurile de struguri (colour-grouped)
      - link_to_terroir   ← §II Legătura cu aria geografică
      - geo_communes      ← §III Delimitarea geografică (drives the GISCO
                            commune-union geometry for the 2 grandfathered
                            IGPs — the RO-specific delta vs. GR/HR)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:`
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True. Returns count augmented.
    """
    _RO_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_RO.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "ro" or not record.get("stub"):
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_RO / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("source_url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "onvpv",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        if sidecar.get("summary"):
            record["summary"] = sidecar["summary"]
        if sidecar.get("grapes") and (sidecar["grapes"].get("principal")
                                      or sidecar["grapes"].get("accessory")):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("geo_communes"):
            record["geo_communes"] = sidecar["geo_communes"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        for role in ("geo_area", "grape_varieties", "link_to_terroir"):
            sidecar_roles = sidecar.get("section_roles") or {}
            if sidecar_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub_reason") and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _RO_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_hu_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of HU national-spec sidecar data into stub records.

    Sibling of `augment_ro_records_with_national_specs`. The 15
    grandfathered HU wines (eAmbrosia carries only a non-fetchable
    `Ares(...)` reference — no EU-OJ EGYSÉGES DOKUMENTUM) ship as
    content-stubs. Stage 02f (`scripts/hu/02f_extract_national_specs.py`)
    parses the Agrárminisztérium termékleírás PDF fetched by stage 01c
    into `raw/hu/national-specs-extracted/<slug>.json`.

    For each HU stub with a matching sidecar:
      - grapes            ← VI. ENGEDÉLYEZETT SZŐLŐFAJTÁK
      - link_to_terroir   ← VII. KAPCSOLAT A FÖLDRAJZI TERÜLETTEL
      - geo_communes      ← IV. KÖRÜLHATÁROLT TERÜLET (commune-precision;
                            geometry still prefers the Bétard polygon
                            these wines already have, so this is a record)
      - geo_area_brief / summary / styles ← matching sections
      - section_roles     ← unified role dict so 02d reads terroir uniformly
      - stub_reason       ← prefixed `national-spec:`
      - national_spec     ← provenance block (url, sha256, format, …)

    `record["stub"]` stays True. Returns count augmented.
    """
    _HU_NATIONAL_SPEC_BY_SLUG.clear()
    if not NATIONAL_SPECS_HU.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "hu":
            continue
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = NATIONAL_SPECS_HU / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("source_url") or "",
            "sha256": src.get("sha256") or "",
            "fetched_at": src.get("fetched_at") or "",
            "format": src.get("format") or "",
            "source_org": src.get("source_org") or "agrarminiszterium",
            "filename": src.get("filename") or "",
            "parser_template": sidecar.get("parser_template") or "",
        }

        # Fill-if-empty: a stub is fully empty so this fills everything;
        # a non-stub with a thin EU extraction (e.g. Badacsony, whose
        # awkward doc structure left the grape section unrouted) gets only
        # its EMPTY fields filled — good EUR-Lex data is never clobbered.
        cur_grapes = record.get("grapes") or {}
        if (sidecar.get("summary") and not record.get("summary")):
            record["summary"] = sidecar["summary"]
        if (sidecar.get("grapes")
                and (sidecar["grapes"].get("principal") or sidecar["grapes"].get("accessory"))
                and not (cur_grapes.get("principal") or cur_grapes.get("accessory"))):
            record["grapes"] = sidecar["grapes"]
        if sidecar.get("geo_area_brief") and not record.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("geo_communes") and not record.get("geo_communes"):
            record["geo_communes"] = sidecar["geo_communes"]
        if sidecar.get("dulok") and not record.get("dulok"):
            record["dulok"] = sidecar["dulok"]
        if sidecar.get("link_to_terroir") and not record.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))

        section_roles = dict(record.get("section_roles") or {})
        sidecar_roles = sidecar.get("section_roles") or {}
        for role in ("geo_area", "grape_varieties", "link_to_terroir"):
            if sidecar_roles.get(role) and not section_roles.get(role):
                section_roles[role] = sidecar_roles[role]
        record["section_roles"] = section_roles

        if record.get("stub") and record.get("stub_reason") \
                and not record["stub_reason"].startswith("national-spec:"):
            record["stub_reason"] = f"national-spec:{record['stub_reason']}"
        record["national_spec"] = provenance
        _HU_NATIONAL_SPEC_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def _backfill_it_nonstub_from_masaf(record: dict, sidecar: dict) -> bool:
    """Fill ONLY the empty fields of a non-stub IT record from its MASAF
    sidecar — the documento unico is canonical, but some OJ docs omit the
    geo area or variety list, and the national disciplinare carries them.
    Never overwrites populated docunico data. Returns True if anything
    was filled."""
    filled = False
    g = record.get("grapes") or {}
    if sidecar.get("grapes") and not (g.get("principal") or g.get("accessory")):
        record["grapes"] = sidecar["grapes"]
        filled = True
    if sidecar.get("menzioni") and not record.get("menzioni"):
        record["menzioni"] = sidecar["menzioni"]
        filled = True
    section_roles = dict(record.get("section_roles") or {})
    if sidecar.get("geo_area_brief") and not (record.get("geo_area_brief") or "").strip():
        record["geo_area_brief"] = sidecar["geo_area_brief"]
        section_roles["geo_area"] = sidecar["geo_area_brief"]
        filled = True
    if sidecar.get("link_to_terroir") and not (record.get("link_to_terroir") or "").strip():
        record["link_to_terroir"] = sidecar["link_to_terroir"]
        section_roles["link_to_terroir"] = sidecar["link_to_terroir"]
        filled = True
    if filled:
        record["section_roles"] = section_roles
        record["masaf_backfill"] = True
    return filled


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
        slug = record.get("slug")
        if not slug:
            continue
        sidecar_path = MASAF_DISCIPLINARI_IT / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        # Non-stub records carry canonical EUR-Lex documento-unico data —
        # only BACKFILL fields the documento unico left empty (some OJ
        # docs omit the area or variety list), never overwrite. Stubs get
        # the full merge below.
        if not record.get("stub"):
            if _backfill_it_nonstub_from_masaf(record, sidecar):
                augmented += 1
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
        if sidecar.get("menzioni") and not record.get("menzioni"):
            record["menzioni"] = sidecar["menzioni"]
        if sidecar.get("geo_area_brief"):
            record["geo_area_brief"] = sidecar["geo_area_brief"]
        if sidecar.get("link_to_terroir"):
            record["link_to_terroir"] = sidecar["link_to_terroir"]
        # IT MASAF is the last national-spec layer to carry styles; merge them
        # the same way every other augment does (union, never clobber). The
        # disciplinare's tipologie + organoleptic articles supply the markers
        # (spumante / passito / vin santo / dolce) the grape-colour floor can't
        # infer; the floor still backfills any colour the scan missed.
        if sidecar.get("styles"):
            record["styles"] = sorted(set(record.get("styles") or []) | set(sidecar["styles"]))
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


_IT_REGISTER_BY_SLUG: dict[str, dict] = {}
# Slug → menzioni (MGA/UGA cru name list) for the panel chip section.
# Populated after the IT augments (menzioni live on the in-memory record,
# not in the feature props or the on-disk stub) and read by the aocs blob.
_IT_MENZIONI_BY_SLUG: dict[str, list] = {}


def augment_it_records_with_regional_registers(records: list[dict]) -> int:
    """Fill the grape roster of regional-IGT records whose disciplinare
    defers to the Region's authorised-variety register (the annex is
    absent from the MASAF PDF). Each region sidecar at
    raw/it/regional-variety-registers/<region>.json lists the IGT slugs
    (`igts`) that draw from it. Only applied when the record still has no
    grapes, so a varietal IGT (e.g. catalanesca-del-monte-somma, excluded
    from the `igts` lists) is never given a whole regional roster.

    Returns the number of records given a roster."""
    _IT_REGISTER_BY_SLUG.clear()
    sources = IT_REGIONAL_REGISTERS / "sources.json"
    if not sources.exists():
        return 0
    by_slug: dict[str, dict] = {}
    for region in json.loads(sources.read_text(encoding="utf-8")):
        if region.startswith("_"):
            continue
        sidecar_path = IT_REGIONAL_REGISTERS / f"{region}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for igt in sidecar.get("igts", []):
            by_slug[igt] = sidecar

    augmented = 0
    for record in records:
        if record.get("country") != "it":
            continue
        slug = record.get("slug")
        sidecar = by_slug.get(slug)
        if not sidecar:
            continue
        g = record.get("grapes") or {}
        if g.get("principal") or g.get("accessory"):
            continue
        slugs = [v["slug"] for v in sidecar.get("varieties", [])]
        if not slugs:
            continue
        record["grapes"] = {
            "principal": slugs,
            "accessory": [],
            "observation": [],
            "details": [
                {"slug": v["slug"], "name": v["name"], "role": "principal",
                 "colour": v.get("colour", ""),
                 "source": "regional-variety-register"}
                for v in sidecar["varieties"]
            ],
        }
        src = sidecar.get("source") or {}
        provenance = {
            "region": sidecar.get("region", ""),
            "url": src.get("url", ""),
            "source_org": src.get("source_org", ""),
            "note": src.get("note", ""),
            "sha256": src.get("sha256", ""),
            "n_varieties": len(slugs),
        }
        record["regional_register"] = provenance
        _IT_REGISTER_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def synthesize_it_sottozone_records(records: list[dict]) -> int:
    """Emit first-class sub-denomination records for Italian sottozone
    detected in the MASAF disciplinare (Chianti's 7, Valtellina's 5,
    Bardolino's 3, …). The EU documento unico rarely names them, so
    stage 02 emits none — they live in the national disciplinare's
    Article 1, which 02f cached in the sidecar's `article_bodies`.

    Each sottozona becomes a child record mirroring the ES subzona /
    FR DGC model: `is_sub_denomination=True`, `parent_slug`,
    `parent_name`, `parent_id_eambrosia`, inheriting the parent's
    grapes / styles / terroir / regione. Geometry resolves via the
    stage-04 `parent-appellation` inheritance step. Appended to
    `records` (processed after every parent, so parent geometry is
    available). Returns the number of sottozona records created."""
    if not MASAF_DISCIPLINARI_IT.exists():
        return 0
    existing = {r.get("slug") for r in records if r.get("country") == "it"}
    new_records: list[dict] = []
    for record in list(records):
        if record.get("country") != "it" or record.get("is_sub_denomination"):
            continue
        slug = record.get("slug")
        sidecar_path = MASAF_DISCIPLINARI_IT / f"{slug}.json"
        if not slug or not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        bodies = sidecar.get("article_bodies") or {}
        text = " ".join(
            [sidecar.get("geo_area_brief") or "", bodies.get("1", ""), bodies.get("3", "")]
        )
        parent_name = record.get("name") or slug
        for sz in extract_it_sottozone(text, parent_name):
            sz_slug = f"{slug}-{sz['slug']}"
            if not sz["slug"] or sz_slug in existing:
                continue
            existing.add(sz_slug)
            child = dict(record)
            child.update({
                "slug": sz_slug,
                "name": f"{parent_name} {sz['name']}",
                "is_sub_denomination": True,
                "parent_slug": slug,
                "parent_name": parent_name,
                "parent_id_eambrosia": record.get("id_eambrosia") or "",
                "menzioni": [],
                "sottozona_source": "masaf-disciplinare-article-1",
            })
            new_records.append(child)
    records.extend(new_records)
    return len(new_records)


def augment_de_records_with_produktspezifikation(records: list[dict]) -> int:
    """In-place merge of BLE-Produktspezifikation sidecar data into DE
    parent-Anbaugebiet records.

    The EU Einziges Dokument for German wines doesn't carry a principal/
    accessory split — section 7 is a flat list. The BLE national
    Produktspezifikation (Amtliches Werk §5 UrhG) names individual
    varieties with their own Mindestmostgewicht threshold in §3.2 (Mosel
    → Riesling/Elbling/Müller-Thurgau/Dornfelder). Stage 02f extracts
    that split into raw/de/produktspezifikationen-extracted/<slug>.json;
    this augment re-tags the in-memory record's grapes block accordingly.

    Two sidecar categories are merged (both written by stage 02f):
      - the 13 Anbaugebiete (regional PDOs), with a principal/accessory
        split from §3.2 Mindestmostgewicht; and
      - the 15 Landwein g.g.A. that ship as stubs (no EU Einziges
        Dokument). Their BLE spec has no role split, so they arrive as
        `section-8-flat-no-split` (all-principal) and fold their full
        roster + §-Zusammenhang terroir text into the stub record.
    Einzellage sub-denominations are still skipped (they inherit the
    parent Anbaugebiet's varieties at render time).

    For records with `role_split_method == "section-3.2-principal"`:
      - re-tag existing record["grapes"]["details"] items as
        principal/accessory based on the sidecar's slug sets
      - rebuild record["grapes"]["principal"] / ["accessory"] lists
      - fold any new sidecar slugs not already in the EU record

    For records with `role_split_method == "section-8-flat-no-split"`
    (Anbaugebiete whose §3.2 doesn't enumerate per-variety thresholds —
    Franken, Württemberg in v1): the existing all-principal default
    stands; the sidecar just records the BLE source as provenance.

    Stage 04 reads the cached provenance later in the AOC-blob phase
    via `_DE_PRODUKTSPEZIFIKATION_BY_SLUG`.

    Returns the number of records augmented.
    """
    _DE_PRODUKTSPEZIFIKATION_BY_SLUG.clear()
    if not PRODUKTSPEZIFIKATION_DE.exists():
        return 0
    augmented = 0
    for record in records:
        if record.get("country") != "de":
            continue
        if record.get("is_sub_denomination"):
            continue
        slug = record.get("slug") or ""
        sidecar_path = PRODUKTSPEZIFIKATION_DE / f"{slug}.json"
        if not sidecar_path.exists():
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue

        method = sidecar.get("role_split_method") or ""
        src = sidecar.get("source") or {}
        provenance = {
            "url": src.get("url") or "",
            "sha256": src.get("sha256") or "",
            "bytes": src.get("bytes") or 0,
            "fetched_at": src.get("fetched_at") or "",
            "source_org": src.get("source_org") or "BLE",
            "license": src.get("license") or "Amtliches Werk §5 UrhG",
            "role_split_method": method,
            "n_principal": sidecar.get("n_principal") or 0,
            "n_accessory": sidecar.get("n_accessory") or 0,
        }

        # BLE §8/§9 "Zusammenhang" terroir backfill — when the EU
        # Einziges Dokument is sparse (stub or no link_to_terroir), use
        # the BLE PDF's terroir block so 02d can extract facts from it.
        # Affects Ahr, Baden, Hessische Bergstraße, Rheingau, Sachsen,
        # Saale-Unstrut in v1. We also record the BLE PDF URL as the
        # cahier_source for downstream provenance.
        bz = (sidecar.get("zusammenhang_text") or "").strip()
        eu_terroir = (record.get("link_to_terroir") or "").strip()
        if bz and len(eu_terroir) < 400:
            record["link_to_terroir"] = bz
            section_roles = dict(record.get("section_roles") or {})
            section_roles["link_to_terroir"] = bz
            record["section_roles"] = section_roles
            # Surface the BLE PDF as the canonical terroir source so the
            # panel + 02d attribute it correctly.
            rec_src = dict(record.get("source") or {})
            rec_src["terroir_source_url"] = src.get("url") or ""
            rec_src["terroir_source_org"] = "BLE"
            record["source"] = rec_src
            provenance["terroir_backfilled"] = True

        # For both role-split methods, fold the sidecar's variety roster
        # into the in-memory record. The default fold tags non-sidecar
        # EU slugs as `accessory` (the BLE PDF's §3.2 is the principal
        # allowlist); the flat-no-split method instead tags everything
        # as principal because the document doesn't enumerate a split.
        if method in ("section-3.2-principal", "section-8-flat-no-split"):
            # Build slug → role from the sidecar.
            sidecar_role: dict[str, str] = {}
            sidecar_details: list[dict] = []
            for g in sidecar.get("grapes") or []:
                s = g.get("slug")
                if s:
                    sidecar_role[s] = g.get("role") or "principal"
                    sidecar_details.append(g)

            # Re-tag the EU-record's existing details. Keep the EU
            # record's display name (matches the wine's own
            # Einziges-Dokument spelling). When the sidecar has an
            # authoritative §3.2 split, slugs NOT named in the sidecar
            # default to "accessory" — the BLE PDF's §3.2 is the
            # principal-allowlist, so anything outside it is
            # implicitly "alle übrigen Rebsorten". When the sidecar is
            # flat-no-split, every slug is principal (the regulator
            # didn't enumerate a split).
            unmatched_default = (
                "principal" if method == "section-8-flat-no-split" else "accessory"
            )
            grapes = dict(record.get("grapes") or {})
            details_in = grapes.get("details") or []
            new_details: list[dict] = []
            eu_slugs: set[str] = set()
            for d in details_in:
                new_d = dict(d)
                s = new_d.get("slug")
                if s:
                    new_d["role"] = sidecar_role.get(s, unmatched_default)
                new_details.append(new_d)
                if s:
                    eu_slugs.add(s)

            # Fold in any sidecar varieties that the EU record missed
            # (the §8 list is more complete than the EU section 7 for
            # some Anbaugebiete).
            for g in sidecar_details:
                s = g.get("slug")
                if s and s not in eu_slugs:
                    new_details.append({
                        "slug": s,
                        "name": g.get("name", s),
                        "role": g.get("role", "accessory"),
                        "colour": g.get("colour", ""),
                        "source": "ble-produktspezifikation",
                    })

            # Rebuild principal / accessory lists from the re-tagged
            # details (deterministic + dedup-by-first-seen).
            principal: list[str] = []
            accessory: list[str] = []
            seen_p: set[str] = set()
            seen_a: set[str] = set()
            for d in new_details:
                s = d.get("slug")
                if not s:
                    continue
                if d.get("role") == "accessory":
                    if s in seen_a:
                        continue
                    seen_a.add(s)
                    accessory.append(s)
                else:
                    if s in seen_p:
                        continue
                    seen_p.add(s)
                    principal.append(s)
            grapes["principal"] = principal
            grapes["accessory"] = accessory
            grapes["details"] = new_details
            record["grapes"] = grapes

        record["produktspezifikation"] = provenance
        _DE_PRODUKTSPEZIFIKATION_BY_SLUG[slug] = provenance
        augmented += 1
    return augmented


def augment_cz_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of the Czech national variety roster (Vyhláška
    č. 88/2017 Sb. Příloha č. 2) into every CZ wine record.

    Czech wine law publishes one national variety list (35 white + 26
    red + 6 zemské-víno = 67 varieties) that applies to every jakostní
    víno regardless of podoblast — no per-appellation restriction. So
    every CZ wine that *should* carry a variety list (10 of 13, all
    except 3 newer single-vineyard / single-varietal PDOs whose
    Vyhláška-88 status is undocumented) gets the same fold:

      - white-wine PDOs/PGIs → all 35 white varieties as `principal`
      - red-wine PDOs/PGIs → all 26 red varieties as `principal`
      - mixed (most macros + podoblasti) → both lists folded;
        zemské-víno-only varieties go under `accessory` (they apply
        only to the lower zemské-víno PGI tier).

    Since the Vyhláška doesn't enumerate a per-appellation principal/
    accessory split (it's a flat national authorisation), we mark
    everything `principal` and let the panel render "All Czech
    jakostní vína authorise these 67 varieties — see Vyhláška č.
    88/2017 Sb." in the provenance.

    Stage 04 reads the cached provenance later via
    `_CZ_NATIONAL_SPEC_BY_SLUG`.

    Returns the number of records augmented.
    """
    _CZ_NATIONAL_SPEC_BY_SLUG.clear()
    _CZ_CHZO_BY_SLUG.clear()
    if not NATIONAL_SPECS_CZ.exists():
        return 0

    # Load the two SZPI CHZO region specs (terroir source + style roster +
    # provenance), keyed by region. Both PGIs are the spec's own subject;
    # the macro CHOPs + podoblasti in that region share its section-1
    # terroir description (rendered by 02d) and cite the same SZPI PDF.
    chzo_by_region: dict[str, dict] = {}
    for key in ("chzo-moravske", "chzo-ceske"):
        p = NATIONAL_SPECS_CZ / f"{key}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("region"):
            chzo_by_region[d["region"]] = d
    # The 2 PGI slugs whose own product specification this is (they
    # inherit the spec's per-style roster; the CHOPs/podoblasti keep
    # grape-colour-inferred styles only).
    chzo_pgi_slugs = {"moravske", "ceske"}

    varieties_path = NATIONAL_SPECS_CZ / "varieties.json"
    manifest_path = NATIONAL_SPECS_CZ / "manifest.json"
    if not varieties_path.exists():
        return 0
    try:
        spec = json.loads(varieties_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except (ValueError, OSError):
        manifest = {}
    src_meta = (manifest.get("sources") or {}).get("vyhlaska-88-2017") or {}

    # Build a slug → match details index for the lexicon match.
    from _lib.grape_entity import match_variety, set_pliego_context  # noqa: E402
    sidecar_details: list[dict] = []
    set_pliego_context("vyhlaska-88-2017")
    for v in spec.get("varieties") or []:
        m = match_variety(v.get("name") or "")
        if m is None:
            continue
        sidecar_details.append({
            "slug": m.slug,
            "name": v.get("name"),
            "role": "principal",
            "colour": m.colour or _COLOUR_FROM_CZ_BLOCK.get(v.get("colour", ""), ""),
            "source": "vyhlaska-88-2017",
        })
    set_pliego_context(None)

    provenance_base = {
        "url": src_meta.get("canonical_url") or src_meta.get("fetch_url") or "",
        "fetch_url": src_meta.get("fetch_url") or "",
        "title": src_meta.get("title") or "",
        "sbirka_castka": src_meta.get("sbirka_castka") or "",
        "sha256": src_meta.get("sha256") or "",
        "fetched_at": (src_meta.get("fetched_at") or "")
                       if isinstance(src_meta, dict) else "",
        "source_org": "sbirka",
        "license": "Czech law text per §3(d) of the Czech Copyright Act",
        "n_varieties": spec.get("n_total") or 0,
        "n_white": spec.get("n_white") or 0,
        "n_red": spec.get("n_red") or 0,
        "n_zemske": spec.get("n_zemske") or 0,
    }

    augmented = 0
    for record in records:
        if record.get("country") != "cz":
            continue
        slug = record.get("slug") or ""
        # Build the per-record details list. Start from the sidecar
        # (the national variety roster) since the EU-OJ extracted record
        # has no grapes (every CZ wine is a stub in v1). Folding by
        # role: everything `principal` because the Vyhláška doesn't
        # split.
        grapes = dict(record.get("grapes") or {})
        existing_slugs = {d.get("slug") for d in (grapes.get("details") or []) if d.get("slug")}
        new_details = list(grapes.get("details") or [])
        for d in sidecar_details:
            if d["slug"] in existing_slugs:
                continue
            existing_slugs.add(d["slug"])
            new_details.append(d)
        principal = [d["slug"] for d in new_details if d["slug"] and d.get("role") != "accessory"]
        accessory = [d["slug"] for d in new_details if d["slug"] and d.get("role") == "accessory"]
        # Dedup while preserving order.
        principal_seen: set[str] = set()
        principal_ordered = [s for s in principal if not (s in principal_seen or principal_seen.add(s))]
        accessory_seen: set[str] = set()
        accessory_ordered = [s for s in accessory if not (s in accessory_seen or accessory_seen.add(s))]
        grapes["principal"] = principal_ordered
        grapes["accessory"] = accessory_ordered
        grapes["details"] = new_details
        record["grapes"] = grapes
        # Czech wine law publishes no per-appellation wine-description
        # section, so styles can't be read from a spec the way HR/SI/BG
        # do. Infer the base colour styles from the authorised variety
        # roster instead (the BE colour-distribution fallback): a
        # blanc/gris variety authorises white, a noir variety authorises
        # red + rosé. Every CZ wine carries the national roster, so all
        # carry white/red/rosé — honest (any CZ jakostní víno appellation
        # may be made in any colour) and it makes CZ wines findable in the
        # style facet instead of invisible. The single straw-wine PDO
        # (Novosedelské Slámové víno) additionally carries vin-de-paille,
        # evident from its own name.
        colours = {d.get("colour") for d in new_details if d.get("colour")}
        styles = set(record.get("styles") or [])
        if colours & {"blanc", "gris"}:
            styles.add("white")
        if "noir" in colours:
            styles.add("red")
            styles.add("rose")
        if slug == "novosedelske-slamove-vino":
            styles.add("vin-de-paille")
        # The 2 PGIs ("zemské víno") additionally carry the real style
        # roster from their SZPI CHZO spec section 2 (sparkling /
        # semi-sparkling / vin-de-liqueur on top of the colour bases).
        chzo = chzo_by_region.get(record.get("region") or "")
        if chzo and slug in chzo_pgi_slugs:
            styles |= set(chzo.get("styles") or [])
        record["styles"] = sorted(styles)
        # All CZ wines cite the region's CHZO spec as their terroir
        # source (02d grounds on its section-1 region description), so
        # surface its provenance uniformly for the panel source block.
        if chzo:
            chzo_prov = {
                "url": chzo.get("source_url") or "",
                "title": chzo.get("source_title") or "",
                "region": chzo.get("region") or "",
                "source_org": chzo.get("source_org") or "szpi",
                "sha256": chzo.get("source_sha256") or "",
                "parser_template": chzo.get("parser_template") or "",
            }
            record["chzo_spec"] = chzo_prov
            _CZ_CHZO_BY_SLUG[slug] = chzo_prov
        record["national_spec"] = provenance_base
        _CZ_NATIONAL_SPEC_BY_SLUG[slug] = provenance_base
        augmented += 1
    return augmented


# CZ variety-block colour → grape-entity colour mapping. The Vyhláška
# 88/2017 block headers are "Bílé moštové odrůdy" (blanc) / "Modré
# moštové odrůdy" (noir) / "Odrůdy pro výrobu zemských vín" (mixed
# colours, kept as `zemske` here — falls back via match_variety()).
_COLOUR_FROM_CZ_BLOCK: dict[str, str] = {
    "blanc": "blanc",
    "noir": "noir",
    "zemske": "",  # mixed; let match_variety supply the per-variety colour
}


# Simple-mode style buckets: collapses the fine-grained style tags into the
# six top-level buckets the default view shows. Derived from the canonical
# taxonomy in scripts/_lib/style_taxonomy so adding a new tag in one place
# propagates here automatically.
SIMPLE_STYLE_BUCKETS: dict[str, str] = {
    s: _taxonomy_simple_bucket(s) for s in _taxonomy_all_slugs()
}


# Several non-FR stage-02 pipelines tag wine colour with the FR colour word
# (blanc / noir / rouge / gris) rather than the canonical style-taxonomy slug
# (white / red / rose). Those leak straight through the STYLE_LABELS lookup in
# the UI untranslated, rendering "Blanc" / "Rouge" / "Noir" in every locale.
# Canonicalise here — line ~3276 is the single point every record's styles flow
# through into the map, so this corrects the whole corpus uniformly regardless
# of which country emitted the tag.
_COLOUR_WORD_TO_STYLE_SLUG: dict[str, str] = {
    "blanc": "white",
    "noir": "red",
    "rouge": "red",
    "gris": "white",
    "rose": "rose",
}


# `tranquille` (still wine) and `dry` (sec) are the assumed defaults for every
# appellation — a still, dry wine is the baseline — so rendering them as style
# pills is noise. Drop them corpus-wide on the map. This is map-only: stage-03
# wiki pages read the raw `styles` field, not this.
_DROP_STYLES: frozenset[str] = frozenset({"tranquille", "dry"})


def _canonical_styles(values: list[str]) -> list[str]:
    """Map legacy colour-word style tags to canonical taxonomy slugs, drop the
    assumed-default `tranquille`, dedupe, and keep the order stable so the MVT
    `in` filter strings stay clean."""
    seen: dict[str, None] = {}
    for s in values or ():
        canon = _COLOUR_WORD_TO_STYLE_SLUG.get(s, s)
        if canon in _DROP_STYLES:
            continue
        seen.setdefault(canon, None)
    return list(seen)


# Berry colour -> wine-style FLOOR. blanc / gris / rose-berried grapes (Pinot
# Gris, Gewürztraminer, …) all make WHITE wine; noir makes RED. Rosé WINE is a
# vinification choice, never inferred from grape colour. Applied at the single
# style chokepoint, and only when a wine record carries no colour style of its
# own (see the call site) — so it is a floor that never overrides real data.
_BERRY_COLOUR_TO_WINE_STYLE: dict[str, str] = {
    "blanc": "white", "gris": "white", "rose": "white", "noir": "red",
}
_COLOUR_STYLES: frozenset[str] = frozenset({"white", "red", "rose"})
_SPARKLING_FAMILY: frozenset[str] = frozenset({"sparkling", "semi-sparkling", "cremant"})


def _base_colour_styles_from_grapes(grapes: dict, existing_styles: set[str]) -> set[str]:
    """Wine-colour styles implied by the authorised varieties' berry colour.
    Per slug, first hit wins: (1) the record's own `details[].colour`, (2) the
    curated DEFAULT_COLOUR, (3) VIVC's `color` (which covers slugs DEFAULT_COLOUR
    misses, e.g. nebbiolo / chasselas). Returns the colours to ADD (white / red);
    never invents rosé. The caller gates on no-colour-style + is_wine."""
    from _lib.grape_lexicon import DEFAULT_COLOUR  # noqa: E402
    vivc_colour = _load_vivc_colour_by_slug()
    detail_colour = {
        d.get("slug"): (d.get("colour") or "").strip()
        for d in (grapes.get("details") or [])
        if d.get("slug") and (d.get("colour") or "").strip()
    }
    slugs = (set(grapes.get("principal") or [])
             | set(grapes.get("accessory") or [])
             | set(grapes.get("observation") or []))
    add: set[str] = set()
    for s in slugs:
        berry = detail_colour.get(s) or DEFAULT_COLOUR.get(s) or vivc_colour.get(s)
        style = _BERRY_COLOUR_TO_WINE_STYLE.get(berry or "")
        if style:
            add.add(style)
    # Sparkling-only refinement: don't assert a still `red` from a noir grape
    # when the record's only declared styles are sparkling-family — those reds
    # are for blanc-de-noirs / rosé sparkling, not still red (Franciacorta,
    # Crémant d'Alsace, …).
    if "red" in add and existing_styles and existing_styles <= _SPARKLING_FAMILY:
        add.discard("red")
    return add


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
        d = json.loads(f.read_text(encoding="utf-8"))
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
        rec = json.loads(f.read_text(encoding="utf-8"))
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


_VIVC_COLOUR_BY_SLUG_CACHE: dict[str, str] | None = None


def _load_vivc_colour_by_slug() -> dict[str, str]:
    """`{slug: 'blanc'|'gris'|'noir'|'rose'}` from raw/vivc/by-slug/<slug>.json
    `color` (UPPERCASE NOIR/BLANC/GRIS/ROSE). Berry colour — not a wine style.
    VIVC carries colours absent from the curated DEFAULT_COLOUR table
    (nebbiolo, chasselas, …), so it is the gap-filler for the style floor.
    Kept separate from `_load_vivc_by_slug` so that function's return shape
    (consumed by `facets`) is untouched."""
    global _VIVC_COLOUR_BY_SLUG_CACHE
    if _VIVC_COLOUR_BY_SLUG_CACHE is not None:
        return _VIVC_COLOUR_BY_SLUG_CACHE
    out: dict[str, str] = {}
    _MAP = {"NOIR": "noir", "BLANC": "blanc", "GRIS": "gris", "ROSE": "rose"}
    if VIVC_BY_SLUG.exists():
        for f in VIVC_BY_SLUG.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            colour = _MAP.get((rec.get("color") or "").strip().upper())
            slug = rec.get("slug")
            if colour and slug:
                out[slug] = colour
    _VIVC_COLOUR_BY_SLUG_CACHE = out
    return out


def _load_native_grape(lang: str, slug: str, max_chars: int = 280) -> dict | None:
    """Native Wikipedia entry for (slug, lang), or None when missing/empty.
    Returns the trimmed entry with name, extract, page_url, revision_id,
    thumbnail, matched_via."""
    f = LEXICON_DIR / lang / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
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
    d = json.loads(f.read_text(encoding="utf-8"))
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


def _latin_form_or_empty(name: str) -> str:
    # Cyrillic / Greek / other non-Latin display strings get an
    # informational ASCII transliteration so the grape-pill renderer can
    # fall back to it when no VIVC canonical name is available (e.g.
    # native BG varieties like `mavrud` that VIVC hasn't catalogued).
    latin = unidecode(name or "").strip()
    return latin if latin and latin != (name or "").strip() else ""


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
    latin = _latin_form_or_empty(cahier)
    if latin:
        entry["name_latin"] = latin


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
            d = json.loads(f.read_text(encoding="utf-8"))
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
            d = json.loads(f.read_text(encoding="utf-8"))
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
        extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate ES extracted records (raw/es/pliegos-
    # extracted/). Stubs are skipped at the geometry-resolution step
    # (no commune list / no Figshare polygon) but kept in the AOCS
    # blob so the wine remains searchable.
    if EXTRACTED_ES.exists():
        for json_path in sorted(EXTRACTED_ES.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate PT extracted records
    # (raw/pt/cadernos-extracted/). Same stub semantics as ES.
    if EXTRACTED_PT.exists():
        for json_path in sorted(EXTRACTED_PT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate IT extracted records
    # (raw/it/disciplinari-extracted/). Same stub semantics as ES/PT.
    if EXTRACTED_IT.exists():
        for json_path in sorted(EXTRACTED_IT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate AT extracted records
    # (raw/at/dokumente-extracted/). Same stub semantics as ES/PT/IT.
    if EXTRACTED_AT.exists():
        for json_path in sorted(EXTRACTED_AT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate DE extracted records
    # (raw/de/dokumente-extracted/). Same stub semantics as ES/PT/IT/AT —
    # ~19 of 46 DE wines are Art.107 / Reg.1308/2013 grandfathered names
    # with no fetchable single document. All 13 Anbaugebiete (PDOs)
    # land on the map via Bétard 2022 regardless; the 6 Einzellage PDOs
    # inherit their parent Anbaugebiet polygon (parent/sub model).
    if EXTRACTED_DE.exists():
        for json_path in sorted(EXTRACTED_DE.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate SI extracted records
    # (raw/si/dokumenti-extracted/). Same stub semantics as ES/PT/IT/AT.
    if EXTRACTED_SI.exists():
        for json_path in sorted(EXTRACTED_SI.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate HR extracted records
    # (raw/hr/dokumenti-extracted/). Same stub semantics as ES/PT/IT/AT/SI.
    if EXTRACTED_HR.exists():
        for json_path in sorted(EXTRACTED_HR.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate HU extracted records
    # (raw/hu/dokumentumok-extracted/). Same stub semantics as the
    # other countries.
    if EXTRACTED_HU.exists():
        for json_path in sorted(EXTRACTED_HU.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate RO extracted records
    # (raw/ro/dokumente-extracted/). Same stub semantics as the
    # other countries.
    if EXTRACTED_RO.exists():
        for json_path in sorted(EXTRACTED_RO.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate BG extracted records
    # (raw/bg/dokumenti-extracted/). Same stub semantics as the
    # other countries.
    if EXTRACTED_BG.exists():
        for json_path in sorted(EXTRACTED_BG.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate GR extracted records
    # (raw/gr/dokumenti-extracted/). Same stub semantics as the
    # other countries — ~136 of 147 GR wines are content-stubs.
    if EXTRACTED_GR.exists():
        for json_path in sorted(EXTRACTED_GR.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate CY extracted records
    # (raw/cy/dokumenti-extracted/). All 11 CY wines are content-stubs
    # augmented from the moa.gov.cy τεχνικός φάκελος.
    if EXTRACTED_CY.exists():
        for json_path in sorted(EXTRACTED_CY.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate SK extracted records
    # (raw/sk/dokumenty-extracted/). 4 of 10 SK wines have a fetchable
    # EUR-Lex Jednotný dokument; the other 6 ship as content-stubs.
    if EXTRACTED_SK.exists():
        for json_path in sorted(EXTRACTED_SK.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate CZ extracted records
    # (raw/cz/dokumenty-extracted/). 0 of 13 CZ wines have a fetchable
    # EU-OJ single document in v1 — they all ship as content-stubs.
    # Multi-country: also iterate CH extracted records
    # (raw/ch/dokumente-extracted/). 63 entries from OFAG (61 unique
    # after intercantonal dedupe) across 26 cantons. Source language is
    # per-record (fr / de / it depending on canton).
    if EXTRACTED_CH.exists():
        for json_path in sorted(EXTRACTED_CH.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    if EXTRACTED_CZ.exists():
        for json_path in sorted(EXTRACTED_CZ.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate LU extracted records
    # (raw/lu/cahier-extracted/). 1 parent (Moselle Luxembourgeoise) +
    # 11 modern-commune sub-denominations (predicate labels under Art. 8
    # / Art. 9 of RGD 17-déc-2015). Source language is fr.
    if EXTRACTED_LU.exists():
        for json_path in sorted(EXTRACTED_LU.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate BE extracted records
    # (raw/be/dokumenten-extracted/). 10 wine GIs (7 PDOs + 2 PGIs + 1
    # cross-border BE+NL PDO). Per-record source_lang: nl for the 5
    # Flemish wines + Maasvallei; fr for the 4 Walloon wines.
    if EXTRACTED_BE.exists():
        for json_path in sorted(EXTRACTED_BE.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate NL extracted records
    # (raw/nl/dokumenten-extracted/). 21 wine GIs (9 standalone PDOs +
    # 12 province-PGIs); the cross-border Maasvallei Limburg ships on
    # the BE side. Source language is nl.
    if EXTRACTED_NL.exists():
        for json_path in sorted(EXTRACTED_NL.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
    # Multi-country: also iterate MT extracted records
    # (raw/mt/dokumente-extracted/). 3 wine GIs (2 PDOs + 1 PGI). Source
    # language is en — Malta's EU single documents are published in
    # English (its co-official language), which is also the canonical
    # rendered surface.
    if EXTRACTED_MT.exists():
        for json_path in sorted(EXTRACTED_MT.glob("*.json")):
            if json_path.name == "_index.json":
                continue
            extracted_records.append(json.loads(json_path.read_text(encoding="utf-8")))
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
    n_aug_reg = augment_it_records_with_regional_registers(extracted_records)
    if n_aug_reg:
        print(
            f"[load] IT regional-register augmentation: {n_aug_reg} annex-IGT "
            "records given their region's variety roster",
            file=sys.stderr,
        )
    n_sz_it = synthesize_it_sottozone_records(extracted_records)
    if n_sz_it:
        print(
            f"[load] IT sottozone: {n_sz_it} sub-denomination records "
            "synthesized from MASAF disciplinari",
            file=sys.stderr,
        )
    # Snapshot the in-memory menzioni (documento-unico + MASAF-allegato
    # harvested) for the panel chip section — they ride neither the
    # feature props nor the on-disk stub.
    _IT_MENZIONI_BY_SLUG.clear()
    for _r in extracted_records:
        if _r.get("country") == "it" and _r.get("menzioni"):
            _IT_MENZIONI_BY_SLUG[_r["slug"]] = [
                m.get("name") for m in _r["menzioni"] if m.get("name")
            ]
    # DE Produktspezifikation augmentation — derives a principal/
    # accessory split from the BLE national PDF's §3.2 thresholds.
    # The EU Einziges Dokument is flat (no role split); the BLE PDF
    # names Leitsorten by their own Mindestmostgewicht.
    n_aug_de = augment_de_records_with_produktspezifikation(extracted_records)
    if n_aug_de:
        print(
            f"[load] DE BLE-Produktspezifikation augmentation: {n_aug_de} Anbaugebiete enriched",
            file=sys.stderr,
        )
    # CZ national-spec augmentation — every Czech wine inherits the
    # national variety roster (67 varieties from Vyhláška č. 88/2017 Sb.
    # Příloha č. 2). Czech wine law doesn't restrict varieties per
    # podoblast, so the same fold runs for all 13 records (the 3 newer
    # 2011 single-vineyard PDOs are also covered — they authorise the
    # standard roster).
    n_aug_cz = augment_cz_records_with_national_specs(extracted_records)
    if n_aug_cz:
        print(
            f"[load] CZ national-spec augmentation: {n_aug_cz} records enriched",
            file=sys.stderr,
        )
    # SI specifikacija augmentation — 16 grandfathered SI wines (everything
    # except Cviček) ship as stubs because their eAmbrosia entry has no
    # fetchable EU-OJ Enotni dokument URL. Stage 02f extracts the
    # canonical Slovenian regulator source (MKGP per-wine .doc or
    # Uradni list RS pravilnik HTML); this augment merges it in.
    n_aug_si = augment_si_records_with_specifikacija(extracted_records)
    if n_aug_si:
        print(
            f"[load] SI specifikacija augmentation: {n_aug_si} stub records enriched",
            file=sys.stderr,
        )
    # HR specifikacija augmentation — 16 grandfathered HR wines (everything
    # except Muškat momjanski + Ponikve) ship as stubs because their
    # eAmbrosia entry has no fetchable EU-OJ Jedinstveni dokument URL.
    # Stage 02f extracts the canonical MPS SPECIFIKACIJA PROIZVODA
    # (.doc/.docx/.pdf); this augment merges it in.
    n_aug_hr = augment_hr_records_with_specifikacija(extracted_records)
    if n_aug_hr:
        print(
            f"[load] HR specifikacija augmentation: {n_aug_hr} stub records enriched",
            file=sys.stderr,
        )
    # GR national-spec augmentation — 138 grandfathered GR wines ship as
    # stubs (no fetchable EU-OJ Ενιαίο Έγγραφο). Stage 02f parses the ΥΠΑΑΤ
    # national προδιαγραφή / τεχνικός φάκελος (minagric.gr) into per-wine
    # sidecars; this augment merges grapes / terroir text / styles in.
    n_aug_gr = augment_gr_records_with_national_specs(extracted_records)
    if n_aug_gr:
        print(
            f"[load] GR national-spec augmentation: {n_aug_gr} stub records enriched",
            file=sys.stderr,
        )
    # CY national-spec augmentation — all 11 grandfathered CY wines ship
    # as stubs (no fetchable EU-OJ Ενιαίο Έγγραφο). Stage 02f parses the
    # moa.gov.cy Department-of-Agriculture τεχνικός φάκελος (Greek
    # single-document PDF, OCR'd when image-only) into per-wine sidecars.
    n_aug_cy = augment_cy_records_with_national_specs(extracted_records)
    if n_aug_cy:
        print(
            f"[load] CY national-spec augmentation: {n_aug_cy} stub records enriched",
            file=sys.stderr,
        )
    # RO: the 14 grandfathered wines (only an Ares(...) ref in eAmbrosia)
    # are augmented from the ONVPV caiet de sarcini (stage 01c/02f). The
    # merge carries geo_communes too, so the 2 grandfathered IGPs
    # (Dealurile Transilvaniei, Viile Caraşului) resolve via commune-union.
    n_aug_ro = augment_ro_records_with_national_specs(extracted_records)
    if n_aug_ro:
        print(
            f"[load] RO national-spec augmentation: {n_aug_ro} stub records enriched",
            file=sys.stderr,
        )
    # HU: the 15 grandfathered wines (only an Ares(...) ref in eAmbrosia)
    # are augmented from the Agrárminisztérium termékleírás PDF (stage
    # 01c/02f, hu-termekleiras-v1). The merge carries grapes (VI) +
    # terroir text (VII) + geo_communes (IV) so the panel + 02d ground
    # on the national spec.
    n_aug_hu = augment_hu_records_with_national_specs(extracted_records)
    if n_aug_hu:
        print(
            f"[load] HU national-spec augmentation: {n_aug_hu} records enriched "
            f"(15 grandfathered stubs filled; non-stubs get dűlő harvest + "
            f"national-spec source + empty-field backfill)",
            file=sys.stderr,
        )
    # BG: the 51 grandfathered wines (only an Ares(...) ref in eAmbrosia)
    # are augmented from the ИАЛВ / IAVV per-wine продуктова спецификация
    # (stage 01c/02f, eavw.com PDFs). The merge carries grapes (section 5)
    # + terroir text (section 6) + styles so the panel + 02d ground on it.
    n_aug_bg = augment_bg_records_with_national_specs(extracted_records)
    if n_aug_bg:
        print(
            f"[load] BG national-spec augmentation: {n_aug_bg} stub records enriched",
            file=sys.stderr,
        )
    n_aug_sk = augment_sk_records_with_national_specs(extracted_records)
    if n_aug_sk:
        print(
            f"[load] SK national-spec augmentation: {n_aug_sk} stub records enriched",
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
        for it in json.loads(geom_research_path.read_text(encoding="utf-8")):
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
    # GISCO commune-union fallback for IGTs (Bétard is PDO-only) and the
    # few newer DOPs missing Bétard: resolves the disciplinare's geo-area
    # text ("…l'intero territorio della regione/provincia di X" or a flat
    # comune list) into a union of GISCO LAU IT comuni — the ES/RO IGP
    # pattern. Runs after figshare-pdo, before stub-no-geometry.
    it_communes = ITCommuneIndex(
        istat_csv=ROOT / "raw" / "it" / "istat" / "Elenco-comuni-italiani.csv",
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
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

    # DE polygon index: Bétard 2022 covers all 13 traditional German
    # Anbaugebiete + Bayerischer Bodensee-Landwein (Germany was an EU
    # founding member; everything predates Bétard's Nov-2021 cutoff).
    # The 6 Einzellage PDOs inherit the parent Anbaugebiet polygon
    # (parent/sub model). Most Landwein PGIs union the regional
    # Anbaugebiet polygons that make up their territory.
    de_polygons = DEPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    print(
        f"[load] DE polygons: {de_polygons.n_pdo_polygons} Figshare DE-PDOs",
        file=sys.stderr,
    )
    de_hits: Counter[str] = Counter()

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
    # HR polygon index: Bétard 2022 only — every HR PDO is in the
    # Figshare gpkg (no IGPs in the Croatian corpus, so no region-union
    # branch needed). Cleanest profile of any country.
    hr_polygons = HRPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] HR polygons: {hr_polygons.n_pdo_polygons} Figshare HR-PDOs",
        file=sys.stderr,
    )
    hr_hits: Counter[str] = Counter()
    # HU polygon index: Bétard 2022 PDO-HU + PGI-HU (Balaton entry is
    # mis-labelled by Bétard as PDO-HU-A1507; we bridge it back to its
    # PGI-HU-A1507 file_number). 5 HU PGIs not in Bétard resolve as the
    # union of their constituent PDO polygons (SI PGI pattern).
    hu_polygons = HUPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    print(
        f"[load] HU polygons: {hu_polygons.n_pdo_polygons} Figshare HU-PDOs/PGIs / "
        f"{hu_polygons.n_lau} GISCO HU communes",
        file=sys.stderr,
    )
    hu_hits: Counter[str] = Counter()
    # RO polygon index: Bétard 2022 (re-uses ES Figshare gpkg) for the
    # 38 RO PDOs in the dataset; the 13 IGPs + the 3 newer PDOs (Sebeș-
    # Apold, Plaiurile Drâncei, Iana) resolve via commune-list union
    # against the shared GISCO LAU (raw/es/gisco/, 3,181 RO communes).
    ro_polygons = ROPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    print(
        f"[load] RO polygons: {ro_polygons.n_pdo_polygons} Figshare RO-PDOs / "
        f"{ro_polygons.n_lau} GISCO RO communes",
        file=sys.stderr,
    )
    ro_hits: Counter[str] = Counter()
    # BG polygon index: Bétard 2022 (re-uses ES Figshare gpkg) covers
    # all 52 BG PDOs since Bulgaria entered the EU in 2007. The 2 macro
    # PGIs (Дунавска равнина / Тракийска низина) resolve via the
    # member-PDO union (SI pattern). GISCO LAU (raw/es/gisco/, ~265 BG
    # obshtini) feeds the commune-list fallback.
    bg_polygons = BGPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    print(
        f"[load] BG polygons: {bg_polygons.n_pdo_polygons} Figshare BG-PDOs/PGIs / "
        f"{bg_polygons.n_lau} GISCO BG obshtini",
        file=sys.stderr,
    )
    bg_hits: Counter[str] = Counter()
    # GR polygon index: Bétard 2022 covers all 33 GR PDOs (Greece
    # joined the EU in 1981; every GR PDO predates Bétard). The 114
    # GR PGIs are not in Bétard (PDO-only dataset) and currently fall
    # through to stub-no-geometry — only ~11 of 147 wines have a
    # fetchable single document with parseable commune list. GISCO
    # LAU (CNTR_CODE='EL', ~6,142 communities) feeds the commune-list
    # fallback when available.
    gr_polygons = GRPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
        nuts3_geojson=GR_NUTS3_GEOJSON,
        nuts2_geojson=GR_NUTS2_GEOJSON,
    )
    print(
        f"[load] GR polygons: {gr_polygons.n_pdo_polygons} Figshare GR-PDOs/PGIs / "
        f"{gr_polygons.n_lau} GISCO EL communities",
        file=sys.stderr,
    )
    gr_hits: Counter[str] = Counter()
    # CY polygon index: Bétard 2022 covers all 7 CY PDOs (Cyprus joined
    # the EU in 2004). The 4 CY PGIs are the island's wine districts
    # (Πάφος / Λεμεσός / Λάρνακα / Λευκωσία) and resolve as the union of
    # the GISCO CY communities carrying the district's GISCO_ID digit.
    cy_polygons = CYPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
    )
    print(
        f"[load] CY polygons: {cy_polygons.n_pdo_polygons} Figshare CY-PDOs / "
        f"{cy_polygons.n_lau} GISCO CY communities",
        file=sys.stderr,
    )
    cy_hits: Counter[str] = Counter()
    # SK polygon index: Bétard 2022 covers 8 of 9 SK DOPs; the 9th
    # (TOKAJSKÉ VÍNO, PDO-SK-02856) post-dates the snapshot and aliases
    # the Vinohradnícka oblasť Tokaj polygon (PDO-SK-A0120). The single
    # SK PGI (Slovenská) resolves as the union of all 8 SK DOPs (SI
    # PGI pattern).
    sk_polygons = SKPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] SK polygons: {sk_polygons.n_pdo_polygons} Figshare SK-PDOs",
        file=sys.stderr,
    )
    sk_hits: Counter[str] = Counter()
    # CZ polygon index: Bétard 2022 covers all 11 CZ DOPs (Czechia
    # joined the EU in 2004). The 2 macro PGIs (české / moravské) =
    # union of their constituent macro-PDO polygon (Čechy / Morava).
    # For the 6 podoblasti, the resolver first attempts a commune-union
    # against the obec list in Vyhláška 254/2010 Sb. (parsed by
    # scripts/cz/02f_extract_national_specs.py) using shared GISCO LAU
    # — commune-precision, more honest than Bétard's macro-region
    # aggregation for these sub-regions.
    cz_polygons = CZPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
        national_specs_dir=NATIONAL_SPECS_CZ,
    )
    print(
        f"[load] CZ polygons: {cz_polygons.n_pdo_polygons} Figshare CZ-PDOs / "
        f"{cz_polygons.n_lau} GISCO CZ obce / "
        f"{cz_polygons.n_podoblasti_with_communes} podoblasti with commune lists",
        file=sys.stderr,
    )
    cz_hits: Counter[str] = Counter()
    # CH polygon index: swisstopo swissBOUNDARIES3D (2,110 Swiss
    # Gemeinden across 26 cantons) for commune-union / canton-union
    # fallback + SITG VIT_VIGNOBLE_AO (parcel-precise GE premier crus,
    # 23 polygonised AOCs). swissBOUNDARIES3D is native EPSG:2056;
    # the CHCommuneIndex reprojects to EPSG:4326 at load time.
    ch_commune_idx: CHCommuneIndex | None = None
    ch_ge_sitg: GESitgIndex | None = None
    if CH_SWISSTOPO_GPKG.exists():
        ch_commune_idx = CHCommuneIndex(CH_SWISSTOPO_GPKG)
        print(
            f"[load] CH commune index: {ch_commune_idx.n_communes} Swiss "
            f"Gemeinden across {ch_commune_idx.n_cantons} cantons",
            file=sys.stderr,
        )
    if CH_SITG_GEOJSON.exists():
        ch_ge_sitg = GESitgIndex(CH_SITG_GEOJSON)
        print(
            f"[load] CH GE SITG: {ch_ge_sitg.n_aocs} parcel-precise GE AOCs",
            file=sys.stderr,
        )
    ch_hits: Counter[str] = Counter()
    at_hits: Counter[str] = Counter()
    # LU polygon index: Bétard 2022 covers the 1 LU PDO + IVV
    # Weinbaukartei 2022 parcel-precise vineyard polygons dissolved per
    # modern wine commune (planted-vineyard precision; ~12 km² total
    # across 11 communes, vs. ~250 km² Bétard regulatory perimeter).
    # The 11 commune sub-denominations use the IVV-dissolved polygon;
    # the parent uses Bétard.
    lu_polygons = LUPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        gisco_lau_zip=ES_GISCO_LAU_ZIP,
        ivv_vineyards_shp=LU_IVV_VINEYARDS_SHP if LU_IVV_VINEYARDS_SHP.exists() else None,
    )
    print(
        f"[load] LU polygons: {lu_polygons.n_pdo_polygons} Figshare LU-PDOs / "
        f"{lu_polygons.n_gisco_communes} GISCO LU wine-communes / "
        f"{lu_polygons.n_ivv_communes} IVV-vineyard communes ({lu_polygons.n_ivv_parcels} parcels)",
        file=sys.stderr,
    )
    lu_hits: Counter[str] = Counter()
    # BE polygon index: Bétard 2022 covers all 8 BE+ PDOs (the 7 BE PDOs
    # + the cross-border PDO-BE+NL-02172 Maasvallei Limburg). The 2 BE
    # PGIs (Vlaamse landwijn, Vin de pays des jardins de Wallonie)
    # resolve as the union of their member-PDO polygons.
    be_polygons = BEPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] BE polygons: {be_polygons.n_pdo_polygons} Figshare BE-PDOs",
        file=sys.stderr,
    )
    be_hits: Counter[str] = Counter()
    # NL polygon index: Bétard 2022 covers 6 of 10 NL PDOs (the 4
    # post-Bétard PDOs ship as stub-no-geometry in v1). Eurostat NUTS-2
    # supplies one polygon per Dutch province — each of the 12 NL PGIs
    # is coextensive with one province and resolves via NUTS_ID.
    nl_polygons = NLPolygonIndex(
        figshare_gpkg=ES_FIGSHARE_GPKG,
        nuts2_geojson=NL_NUTS_GEOJSON,
    )
    print(
        f"[load] NL polygons: {nl_polygons.n_pdo_polygons} Figshare NL-PDOs / "
        f"{nl_polygons.n_nuts2_polygons} NUTS-2 NL provinces",
        file=sys.stderr,
    )
    nl_hits: Counter[str] = Counter()
    mt_polygons = MTPolygonIndex(figshare_gpkg=ES_FIGSHARE_GPKG)
    print(
        f"[load] MT polygons: {mt_polygons.n_pdo_polygons} Figshare MT-PDOs",
        file=sys.stderr,
    )
    mt_hits: Counter[str] = Counter()

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
        # can leave it untouched; only the SI / HR / HU branches flip them True.
        _emit_si_features = False
        _emit_hr_features = False
        _emit_hu_features = False
        _emit_ro_features = False
        _emit_bg_features = False
        _emit_gr_features = False
        _emit_cy_features = False
        _emit_de_features = False
        _emit_sk_features = False
        _emit_cz_features = False
        _emit_ch_features = False
        _emit_lu_features = False
        _emit_be_features = False
        _emit_nl_features = False
        _emit_mt_features = False

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
                else:
                    # IGTs (Bétard is PDO-only) + newer DOPs: union the
                    # GISCO comuni named in the disciplinare's geo-area
                    # text. gisco-comune-union / -provincia-union /
                    # -regione-union per how the area is delimited.
                    cgeom, csrc, cstats = it_communes.resolve(
                        record.get("geo_area_brief") or ""
                    )
                    if cgeom is not None and not cgeom.is_empty:
                        geom = cgeom
                        geom_source = csrc
                        stats = cstats
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
        elif country == "hr":
            # HR branch — Bétard Figshare PDO match for all 18 HR DOPs.
            # Croatia has no IGPs (every wine GI is a PDO) and Bétard
            # 2022 covers every one, so this is a single-step resolve
            # with no fallback chain. Sub-denominations are deferred to
            # v2 — the regulatory hierarchy is preserved via the region
            # facet, not as parent/child records.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = hr_polygons.resolve(
                record.get("file_number") or ""
            )
            hr_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = True
        elif country == "hu":
            # HU branch — Bétard Figshare PDO match for 33 HU PDOs/PGIs
            # (Balaton PGI bridged via the Bétard mis-label); 5 remaining
            # HU PGIs resolve as the union of their constituent PDO
            # polygons (SI PGI pattern). Three newer PDOs (Etyeki Pezsgő,
            # Kőszeg, Füred) post-date Bétard and fall to stub-no-geometry.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = hu_polygons.resolve(
                record.get("file_number") or "",
                record.get("geo_communes") or [],
            )
            hu_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = True
        elif country == "ro":
            # RO branch — Bétard Figshare PDO match for ~38 of 41 RO
            # PDOs; the 13 RO IGPs and the 3 newer PDOs missing from
            # Bétard (Sebeș-Apold, Plaiurile Drâncei, Iana) resolve via
            # the GISCO commune-list fallback against the documento-unic
            # `geo_communes` extracted in stage 02 (ES IGP-fallback
            # pattern). Grandfathered IGPs without a parseable single
            # document remain `stub-no-geometry`.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = ro_polygons.resolve(
                record.get("file_number") or "",
                record.get("geo_communes") or [],
            )
            ro_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = True
        elif country == "bg":
            # BG branch — Bétard Figshare PDO match covers all 52 BG
            # PDOs (Bulgaria entered the EU in 2007; everything predates
            # Bétard's Nov-2021 cutoff). The 2 macro BG PGIs (Дунавска
            # равнина / Тракийска низина) resolve as the union of their
            # member-PDO polygons (SI PGI pattern). GISCO BG commune-list
            # is a defensive fallback that should not normally be hit.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = bg_polygons.resolve(
                record.get("file_number") or "",
                record.get("geo_communes") or [],
            )
            bg_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = True
        elif country == "gr":
            # GR branch — Bétard Figshare PDO match covers all 33 GR
            # PDOs (Greece joined the EU in 1981). The 114 GR PGIs are
            # NOT in Bétard (PDO-only dataset) and fall through to
            # `stub-no-geometry` in v1 — only ~11 of 147 GR wines have
            # a fetchable single document, so the commune-list fallback
            # is rarely exercised.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = gr_polygons.resolve(
                record.get("file_number") or "",
                record.get("geo_communes") or [],
                record=record,
            )
            gr_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = True
        elif country == "cy":
            # CY branch — Bétard Figshare PDO match covers all 7 CY PDOs
            # (Cyprus joined the EU in 2004). The 4 CY PGIs are the
            # island's wine districts and resolve as the GISCO
            # district-union (by GISCO_ID digit). All 11 CY wines resolve.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = cy_polygons.resolve(
                record.get("file_number") or "",
            )
            cy_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_cy_features = True
        elif country == "de":
            # DE branch — Bétard Figshare PDO match for the 13 traditional
            # German Anbaugebiete (PDO-DE-A12xx + PDO-DE-A0867 = Ahr);
            # the 6 Einzellage PDOs (Bürgstadter Berg, Würzburger Stein-
            # Berg, Monzinger Niederberg, Uhlen Blaufüsser Lay / Laubach
            # / Roth Lay) inherit their parent Anbaugebiet polygon via
            # the parent/sub-denomination model. The 27 Landwein PGIs
            # are not in Bétard (PDO-only dataset) — most resolve via
            # member-PDO union (the SI/HU/BG pattern); a handful of
            # multi-Bundesland Landweine remain `stub-no-geometry` (the
            # Phase-2 Weingesetz / commune-list parser will fill those in).
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = de_polygons.resolve(
                record.get("file_number") or ""
            )
            de_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = False
            _emit_de_features = True
        elif country == "sk":
            # SK branch — Bétard Figshare PDO match for 8 of 9 SK DOPs;
            # the 9th (TOKAJSKÉ VÍNO, PDO-SK-02856) aliases the
            # Vinohradnícka oblasť Tokaj polygon (PDO-SK-A0120). The
            # single SK PGI (Slovenská) resolves as the union of all 8
            # SK DOPs. Slovakia has no sub-denominations in v1.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = sk_polygons.resolve(
                record.get("file_number") or ""
            )
            sk_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = False
            _emit_de_features = False
            _emit_sk_features = True
        elif country == "ch":
            # CH branch — swisstopo swissBOUNDARIES3D commune/canton
            # union for the bulk + SITG VIT_VIGNOBLE_AO for the 22
            # parcel-precise GE premier crus + parent inheritance for
            # the 13 régionale / 22 locale sub-denominations whose
            # commune list isn't enumerated. Non-EU country — no
            # Bétard polygons in EU_PDO.gpkg.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            if ch_commune_idx is None:
                geom, geom_source, stats = None, "stub-no-geometry", {"matched": 0}
            else:
                geom, geom_source, stats = ch_resolve_geometry(
                    record,
                    commune_index=ch_commune_idx,
                    ge_sitg=ch_ge_sitg,
                    parent_geom_by_slug=parent_geom_by_slug,
                )
            ch_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = False
            _emit_de_features = False
            _emit_sk_features = False
            _emit_cz_features = False
            _emit_ch_features = True
        elif country == "cz":
            # CZ branch — Bétard Figshare PDO match covers all 11 CZ
            # DOPs; the 2 macro PGIs (české / moravské) resolve as the
            # macro-PDO union (Čechy / Morava). Czechia has no sub-
            # denominations as first-class records in v1 — the sub-
            # region PDOs (Litoměřická, Mělnická, Slovácká, Znojemská,
            # …) are themselves PDOs in eAmbrosia, not DGCs.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = cz_polygons.resolve(
                record.get("file_number") or ""
            )
            cz_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = False
            _emit_de_features = False
            _emit_sk_features = False
            _emit_cz_features = True
        elif country == "lu":
            # LU branch — 1 PDO (Moselle Luxembourgeoise) + 11 per-commune
            # sub-denominations. Parent uses Bétard PDO-LU-A0452 (245 km²
            # regulatory perimeter); sub-records use the IVV
            # Weinbaukartei vineyard polygons dissolved per modern
            # commune (planted-vineyard precision). The 4 821 IVV parcels
            # total ~12 km², which is the actual planted vineyard area
            # (vs. ~75 km² of modern admin-commune polygons that
            # contain those parcels).
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = lu_polygons.resolve(record)
            lu_hits[geom_source] += 1
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
            _emit_si_features = False
            _emit_hr_features = False
            _emit_hu_features = False
            _emit_ro_features = False
            _emit_bg_features = False
            _emit_gr_features = False
            _emit_de_features = False
            _emit_sk_features = False
            _emit_cz_features = False
            _emit_lu_features = True
        elif country == "be":
            # BE branch — Bétard 2022 covers all 8 BE+ PDOs (the 7 BE
            # PDOs + the cross-border PDO-BE+NL-02172 Maasvallei Limburg
            # owned by BE). The 2 BE PGIs resolve as the union of their
            # member-PDO polygons (SI/HU/BG/DE PGI pattern).
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = be_polygons.resolve(
                record.get("file_number") or ""
            )
            be_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_be_features = True
        elif country == "nl":
            # NL branch — Bétard 2022 covers 6 of 10 NL PDOs; the 12 NL
            # PGIs each resolve to one Eurostat NUTS-2 province polygon
            # (the 12 NUTS-2 regions of NL ARE the 12 provincies). The
            # 4 newer PDOs (post-Bétard) ship as stub-no-geometry in v1.
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = nl_polygons.resolve(
                record.get("file_number") or ""
            )
            nl_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_nl_features = True
        elif country == "mt":
            # MT branch — Bétard 2022 covers both MT PDOs (Malta, Gozo);
            # the "Maltese Islands" PGI resolves as the union of the two
            # PDO polygons (region-pdo-union).
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None
            geom, geom_source, stats = mt_polygons.resolve(
                record.get("file_number") or ""
            )
            mt_hits[geom_source] += 1
            v_geom = geom
            v_source = geom_source
            v_stats = stats
            if geom is not None and not geom.is_empty:
                parent_geom_by_slug[record["slug"]] = geom
                parent_village_geom_by_slug[record["slug"]] = geom
            _emit_mt_features = True
        else:
            _emit_es_features = False
            _emit_pt_features = False
            _emit_it_features = False
            _emit_at_features = False
            sib_v_geom = sib_name = sib_slug = None
            cadastre_match = None

        if (_emit_es_features or _emit_pt_features or _emit_it_features
                or _emit_at_features or _emit_si_features or _emit_hr_features
                or _emit_hu_features or _emit_ro_features or _emit_bg_features
                or _emit_gr_features or _emit_cy_features or _emit_de_features
                or _emit_sk_features or _emit_cz_features
                or _emit_ch_features or _emit_lu_features
                or _emit_be_features or _emit_nl_features
                or _emit_mt_features):
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
                or _emit_at_features or _emit_si_features or _emit_hr_features
                or _emit_hu_features or _emit_ro_features or _emit_bg_features
                or _emit_gr_features or _emit_cy_features or _emit_de_features
                or _emit_sk_features or _emit_cz_features
                or _emit_ch_features or _emit_lu_features
                or _emit_be_features or _emit_nl_features
                or _emit_mt_features):
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
        clip_res = geom_overrides.clip(record["slug"], geom, geom_source)
        geom = clip_res.geom
        if v_geom is _pre_clip_geom:
            v_geom = clip_res.geom
        elif v_geom is not None and not v_geom.is_empty:
            v_geom = geom_overrides.clip(record["slug"], v_geom, geom_source).geom
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
        styles = _canonical_styles(record.get("styles") or [])
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
        if record.get("country") in ("es", "pt", "it", "at", "de", "si", "hr", "hu", "ro", "bg", "gr", "cy", "sk", "cz", "ch", "lu", "be", "nl", "mt"):
            is_wine = "1"
        else:
            is_wine = "1" if categorie.startswith("Vin") else "0"
        # Grape-colour style floor: many regulator specs enumerate varieties but
        # describe colour as prose ("colore giallo paglierino") instead of the
        # keyword, or are stubs whose grapes are merged only here — so the
        # text-scan parse_styles left no colour. When a wine has no colour style
        # at all, derive the base colour(s) from its grapes' berry colour so it
        # gets a Styles section + is findable in the style facet. Additive only
        # (never overrides a real colour); skips spirits and grape-less records.
        if is_wine == "1" and not (set(styles) & _COLOUR_STYLES):
            extra = _base_colour_styles_from_grapes(grapes, set(styles))
            if extra:
                styles = _canonical_styles(list(styles) + sorted(extra))
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
        elif record.get("country") == "de":
            # DE region = Anbaugebiet (the 13 traditional regional PDOs)
            # for PDOs, or Bundesland-scale territory (Rheinland-Pfalz,
            # Bayern, Baden-Württemberg, …) for Landwein PGIs. Einzellage
            # sub-denominations inherit the parent Anbaugebiet's region.
            if is_sub_denomination:
                parent_slug = record.get("parent_slug") or ""
                region_value = es_region_by_parent_slug.get(
                    f"de::{parent_slug}", record.get("region") or "Deutschland"
                )
            else:
                region_value = record.get("region") or derive_de_region(
                    record,
                    record.get("section_roles", {}).get("geo_area", ""),
                    record.get("section_roles", {}).get("link_to_terroir", ""),
                    record.get("name", ""),
                ) or "Deutschland"
                es_region_by_parent_slug[f"de::{record['slug']}"] = region_value
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
        elif record.get("country") == "hr":
            # HR region = wine macro region (Primorska Hrvatska /
            # Istočna kontinentalna Hrvatska / Zapadna kontinentalna
            # Hrvatska). The 3 macro regions themselves appear as PDOs
            # in the corpus. Croatia has no sub-denominations in v1.
            region_value = record.get("region") or derive_hr_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Hrvatska"
        elif record.get("country") == "hu":
            # HU region = borrégió (Tokaj / Felső-Magyarország / Duna /
            # Balaton / Pannon / Felső-Pannon / Zemplén). The curated
            # file_number map covers every wine. No sub-denominations in v1.
            region_value = record.get("region") or derive_hu_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Magyarország"
        elif record.get("country") == "ro":
            # RO region = regiune viticolă (Moldova / Muntenia / Oltenia
            # / Dobrogea / Transilvania / Banat / Crișana și Maramureș /
            # Terasele Dunării). The curated file_number map is
            # incremental; text scan + "România" fallback otherwise.
            # No sub-denominations in v1.
            region_value = record.get("region") or derive_ro_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "România"
        elif record.get("country") == "bg":
            # BG region = винарски район (Дунавска равнина / Черноморски
            # район / Розова долина / Тракийска низина / Долината на
            # Струма). The curated file_number map covers every wine.
            # No sub-denominations in v1.
            region_value = record.get("region") or derive_bg_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "България"
        elif record.get("country") == "gr":
            # GR region = αμπελουργική ζώνη (Μακεδονία / Θράκη / Θεσσαλία
            # / Ήπειρος / Στερεά Ελλάδα / Πελοπόννησος / Ιόνια Νησιά /
            # Νησιά Αιγαίου / Κρήτη). The curated file_number map covers
            # every PDO at v1; PGIs fall back to text scan + "Ελλάδα".
            # No sub-denominations in v1.
            region_value = record.get("region") or derive_gr_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Ελλάδα"
        elif record.get("country") == "cy":
            # CY region = wine district (επαρχία): Πάφος / Λεμεσός /
            # Λάρνακα / Λευκωσία. The curated file_number map covers
            # every wine (4 PGIs ARE the districts; the 7 PDOs sit
            # inside one). No sub-denominations in v1.
            region_value = record.get("region") or derive_cy_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Κύπρος"
        elif record.get("country") == "sk":
            # SK region = vinohradnícka oblasť (Malokarpatská /
            # Južnoslovenská / Nitrianska / Stredoslovenská /
            # Východoslovenská / Tokaj). The single SK PGI is "Slovensko".
            # No sub-denominations in v1.
            region_value = record.get("region") or derive_sk_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Slovensko"
        elif record.get("country") == "cz":
            # CZ region = vinařská oblast (Čechy / Morava). The curated
            # file_number map covers every wine — the 2 macro PDOs, the 2
            # macro PGIs, and the 9 sub-region / district / single-vineyard
            # PDOs (Šobes, Znojmo, Litoměřická, …) all inherit one of the
            # 2 macro regions. No sub-denominations as first-class records
            # in v1.
            region_value = record.get("region") or derive_cz_region(
                record,
                record.get("section_roles", {}).get("geo_area", ""),
                record.get("section_roles", {}).get("link_to_terroir", ""),
                record.get("name", ""),
            ) or "Česko"
        elif record.get("country") == "ch":
            # CH region = Swiss wine region (Valais / Vaud / Genève /
            # Trois-Lacs / Ticino / Deutschschweiz) — the Swiss Wine
            # Promotion 6-region scheme. Curated canton → region map
            # covers every wine. Sub-denominations inherit the parent
            # canton's region.
            region_value = derive_ch_region(record) or "Schweiz"
        elif record.get("country") == "lu":
            # LU has a single wine region (Moselle Luxembourgeoise) —
            # both the parent record and the 11 commune sub-denominations
            # share it. No facet variation in v1.
            region_value = derive_lu_region(record) or "Moselle Luxembourgeoise"
        elif record.get("country") == "be":
            # BE region = Vlaanderen / Wallonie (the two language
            # communities). Curated file_number map covers every wine.
            # Cross-border Maasvallei intentionally has no region —
            # both BE/NL Limburg sides were one duchy until the 1839
            # partition; the panel surfaces the dual country via the
            # country chip instead. Skip the "België" fallback for
            # any record listed in _CROSS_BORDER_COUNTRY_ALIASES.
            region_value = derive_be_region(record)
            if record.get("file_number", "") not in _CROSS_BORDER_COUNTRY_ALIASES:
                region_value = region_value or "België"
        elif record.get("country") == "nl":
            # NL region = one of the 12 provincies, hand-mapped per
            # file_number. PGI = its own province; each PDO sits in
            # exactly one province.
            region_value = derive_nl_region(record) or "Nederland"
        elif record.get("country") == "mt":
            # MT region = the wine island (Malta / Gozo) or "Maltese
            # Islands" for the archipelago-wide PGI. Carried on the
            # record from stage 02.
            region_value = record.get("region") or "Maltese Islands"
        else:
            region_value = derive_fr_wine_region(record)
        common_props = {
            "country": record.get("country") or "fr",
            "source_lang": record.get("source_lang") or "",
            "id_appellation": (
                record.get("id_appellation")
                or record.get("file_number")
                or record.get("id_eambrosia")
                or ""
            ),
            "id_denomination_geo": record.get("id_denomination_geo") or "",
            "slug": record["slug"],
            "name": record["name"],
            "name_latin": record.get("name_latin") or "",
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
    GEOJSON_OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    village_fc = {"type": "FeatureCollection", "features": village_features}
    GEOJSON_VILLAGES_OUT.write_text(json.dumps(village_fc, ensure_ascii=False), encoding="utf-8")
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
        reg = record.get("regional_register") or _IT_REGISTER_BY_SLUG.get(
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
            # Regional authorised-variety register (the annex an IGT's
            # disciplinare defers to). Populated for the ~19 regional IGTs.
            "regional_register_url": reg.get("url", ""),
            "regional_register_source_org": reg.get("source_org", ""),
            "regional_register_region": reg.get("region", ""),
            "regional_register_n_varieties": reg.get("n_varieties", 0),
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
    if record.get("country") == "de":
        # Germany: 27 of 46 wines carry a fetchable EUR-Lex Einziges
        # Dokument. The 13 Anbaugebiete are additionally backed by the
        # BLE Produktspezifikation (national specification, §5 UrhG) —
        # that's where the principal/accessory variety split comes from
        # (the EU document is flat). Provenance surfaces the BLE URL +
        # sha so the panel can attribute the role split correctly.
        de_spec = record.get("produktspezifikation") or _DE_PRODUKTSPEZIFIKATION_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "de",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "ble_produktspezifikation_url": de_spec.get("url", ""),
            "ble_produktspezifikation_sha256": de_spec.get("sha256", ""),
            "ble_produktspezifikation_fetched_at": de_spec.get("fetched_at", ""),
            "ble_role_split_method": de_spec.get("role_split_method", ""),
            "ble_n_principal": de_spec.get("n_principal", 0),
            "ble_n_accessory": de_spec.get("n_accessory", 0),
        }
    if record.get("country") == "si":
        # Slovenia: only Cviček carries a fetchable EUR-Lex single
        # document. The other 16 are content-stubs whose canonical
        # source is the Slovenian national specifikacija (stage 02f) —
        # 11 are MKGP per-wine `.doc` files, 5 are Uradni list RS
        # pravilnik HTMLs. Provenance surfaces the spec URL + sha so
        # the panel can attribute the variety roster + summary.
        si_spec = record.get("specifikacija") or _SI_SPECIFIKACIJA_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "si",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "specifikacija_url": si_spec.get("url", ""),
            "specifikacija_final_url": si_spec.get("final_url", ""),
            "specifikacija_sha256": si_spec.get("sha256", ""),
            "specifikacija_fetched_at": si_spec.get("fetched_at", ""),
            "specifikacija_format": si_spec.get("format", ""),
            "specifikacija_source_org": si_spec.get("source_org", ""),
            "specifikacija_parser_template": si_spec.get("parser_template", ""),
        }
    if record.get("country") == "hr":
        # Croatia: only Muškat momjanski + Ponikve carry a fetchable
        # EUR-Lex single document; the other 16 are content-stubs whose
        # canonical source is the Ministarstvo poljoprivrede per-wine
        # SPECIFIKACIJA PROIZVODA (stage 02f) — 14 `.doc`, 1 `.docx`
        # (Primorska Hrvatska), 1 PDF (Dingač). Provenance surfaces the
        # spec URL + sha so the panel can attribute the variety roster +
        # terroir text. All 18 resolve to Bétard PDO geometry regardless.
        hr_spec = record.get("specifikacija") or _HR_SPECIFIKACIJA_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "hr",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "specifikacija_url": hr_spec.get("url", ""),
            "specifikacija_final_url": hr_spec.get("final_url", ""),
            "specifikacija_sha256": hr_spec.get("sha256", ""),
            "specifikacija_fetched_at": hr_spec.get("fetched_at", ""),
            "specifikacija_format": hr_spec.get("format", ""),
            "specifikacija_source_org": hr_spec.get("source_org", ""),
            "specifikacija_parser_template": hr_spec.get("parser_template", ""),
        }
    if record.get("country") == "hu":
        # Hungary: 26 of 41 wines carry a fetchable EUR-Lex EGYSÉGES
        # DOKUMENTUM; the remaining 15 (Tokaj, Villány, Sopron, …) are
        # Art.107 / Reg.1308/2013 grandfathered names augmented from the
        # Agrárminisztérium termékleírás PDF (stage 01c/02f,
        # hu-termekleiras-v1 — boraszat.kormany.hu). All 41 now resolve
        # to a polygon: 33 via Bétard PDO match, 5 PGIs via region-union,
        # the 3 newer PDOs via GISCO commune-union. eAmbrosia + file
        # number always resolve.
        hu_spec = record.get("national_spec") or _HU_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "hu",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": hu_spec.get("url", ""),
            "national_spec_sha256": hu_spec.get("sha256", ""),
            "national_spec_fetched_at": hu_spec.get("fetched_at", ""),
            "national_spec_format": hu_spec.get("format", ""),
            "national_spec_source_org": hu_spec.get("source_org", ""),
            "national_spec_parser_template": hu_spec.get("parser_template", ""),
        }
    if record.get("country") == "ro":
        # Romania: 32 of 46 wines carry a fetchable EUR-Lex DOCUMENT
        # UNIC; the remaining 14 are Art.107 / Reg.1308/2013
        # grandfathered names augmented from the ONVPV caiet de sarcini
        # (stage 01c/02f, onvpv-caiet-de-sarcini-v1). 33 PDOs resolve to
        # a Bétard polygon; the IGPs + newer PDOs resolve via the GISCO
        # commune-list fallback (including the 2 grandfathered IGPs whose
        # commune list comes from the national caiet). eAmbrosia + file
        # number always resolve.
        ro_spec = record.get("national_spec") or _RO_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "ro",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": ro_spec.get("url", ""),
            "national_spec_sha256": ro_spec.get("sha256", ""),
            "national_spec_fetched_at": ro_spec.get("fetched_at", ""),
            "national_spec_format": ro_spec.get("format", ""),
            "national_spec_source_org": ro_spec.get("source_org", ""),
            "national_spec_parser_template": ro_spec.get("parser_template", ""),
        }
    if record.get("country") == "bg":
        # Bulgaria: ~3 of 54 wines carry a fetchable EUR-Lex Единен
        # документ; the remaining 51 are Art.107 / Reg.1308/2013
        # grandfathered names augmented from the ИАЛВ / IAVV per-wine
        # продуктова спецификация (stage 02f — eavw.com). All 52 PDOs
        # resolve to a Bétard polygon; both PGIs resolve via member-PDO
        # union. eAmbrosia + file_number always resolve. The national-spec
        # provenance surfaces the IAVV PDF URL + sha so the panel can
        # attribute the variety roster + terroir text correctly.
        bg_spec = record.get("national_spec") or _BG_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "bg",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": bg_spec.get("url", ""),
            "national_spec_sha256": bg_spec.get("sha256", ""),
            "national_spec_fetched_at": bg_spec.get("fetched_at", ""),
            "national_spec_format": bg_spec.get("format", ""),
            "national_spec_source_org": bg_spec.get("source_org", ""),
            "national_spec_parser_template": bg_spec.get("parser_template", ""),
        }
    if record.get("country") == "gr":
        # Greece: only ~11 of 147 wines carry a fetchable EUR-Lex Ενιαίο
        # Έγγραφο; the remaining ~136 are Art.107 / Reg.1308/2013
        # grandfathered names awaiting a curator-pinned URL or the
        # ΥΠΑΑΤ / ΦΕΚ national προδιαγραφή προϊόντος (Phase 2). All 33
        # PDOs resolve to a Bétard polygon; PGIs land as
        # stub-no-geometry in v1. eAmbrosia + file_number always resolve.
        gr_spec = record.get("national_spec") or _GR_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "gr",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": gr_spec.get("url", ""),
            "national_spec_sha256": gr_spec.get("sha256", ""),
            "national_spec_fetched_at": gr_spec.get("fetched_at", ""),
            "national_spec_format": gr_spec.get("format", ""),
            "national_spec_source_org": gr_spec.get("source_org", ""),
            "national_spec_parser_template": gr_spec.get("parser_template", ""),
        }
    if record.get("country") == "cy":
        # Cyprus: none of the 11 wines carry a fetchable EU-OJ Ενιαίο
        # Έγγραφο — all are augmented from the moa.gov.cy Department of
        # Agriculture τεχνικός φάκελος (Greek single-document PDF, OCR'd
        # when image-only). All 7 PDOs resolve to a Bétard polygon; the
        # 4 PGIs to a GISCO district-union. eAmbrosia + file_number always
        # resolve.
        cy_spec = record.get("national_spec") or _CY_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "cy",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": cy_spec.get("url", ""),
            "national_spec_sha256": cy_spec.get("sha256", ""),
            "national_spec_fetched_at": cy_spec.get("fetched_at", ""),
            "national_spec_format": cy_spec.get("format", ""),
            "national_spec_source_org": cy_spec.get("source_org", ""),
            "national_spec_parser_template": cy_spec.get("parser_template", ""),
        }
    if record.get("country") == "sk":
        # Slovakia: 4 of 10 wines carry a fetchable EUR-Lex Jednotný
        # dokument (Vinohradnícka oblasť Tokaj, Stredoslovenská,
        # Skalický rubín, TOKAJSKÉ VÍNO zo slovenskej oblasti). 5 of the
        # other 6 are augmented from the ÚPV SR per-wine špecifikácia
        # výrobku (stage 02f — indprop.gov.sk PDF); Karpatská perla has
        # no standalone ÚPV spec and stays a content-stub. All 10 land
        # on the map via Bétard (8 direct PDO matches + the Tokaj alias
        # for PDO-SK-02856 + the single PGI's all-PDO union). The
        # national-spec provenance surfaces the ÚPV PDF URL + sha so the
        # panel attributes the variety roster + terroir text correctly.
        sk_spec = record.get("national_spec") or _SK_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "sk",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": sk_spec.get("url", ""),
            "national_spec_sha256": sk_spec.get("sha256", ""),
            "national_spec_fetched_at": sk_spec.get("fetched_at", ""),
            "national_spec_format": sk_spec.get("format", ""),
            "national_spec_source_org": sk_spec.get("source_org", ""),
            "national_spec_parser_template": sk_spec.get("parser_template", ""),
        }
    if record.get("country") == "cz":
        # Czech Republic: 0 of 13 wines carry a fetchable EUR-Lex
        # Jednotný dokument — every CZ wine is an Art.107 /
        # Reg.1308/2013 grandfathered name with only Ares(...) refs.
        # All 13 land on the map via Bétard / GISCO commune-union (11
        # PDO matches + each macro PGI = its macro PDO's polygon + 6
        # podoblasti commune-precision via Vyhláška 254/2010 Sb.). The
        # variety roster comes from Vyhláška 88/2017 Sb. Příloha č. 2
        # (national-spec layer, 67 varieties applied to all 10 wines —
        # CZ wine law does not restrict varieties per podoblast).
        ns = record.get("national_spec") or _CZ_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        # CHZO spec — the SZPI „moravské“ / „české“ product specification
        # whose section-1 region terroir description grounds the wine's
        # terroir bullets (02d). Surfaced for every CZ wine in the region.
        chzo = record.get("chzo_spec") or _CZ_CHZO_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "cz",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": ns.get("url", ""),
            "national_spec_fetch_url": ns.get("fetch_url", ""),
            "national_spec_title": ns.get("title", ""),
            "national_spec_sbirka_castka": ns.get("sbirka_castka", ""),
            "national_spec_sha256": ns.get("sha256", ""),
            "national_spec_n_varieties": ns.get("n_varieties", 0),
            "chzo_spec_url": chzo.get("url", ""),
            "chzo_spec_title": chzo.get("title", ""),
            "chzo_spec_region": chzo.get("region", ""),
            "chzo_spec_source_org": chzo.get("source_org", ""),
            "chzo_spec_sha256": chzo.get("sha256", ""),
        }
    if record.get("country") == "lu":
        # Luxembourg: 1 AOP (Moselle Luxembourgeoise) — no fetchable
        # EU-OJ Document Unique (eAmbrosia's only publication ref is
        # the Ares numeric `58323`). The canonical source is the IVV
        # 2020 Cahier des charges PDF hosted on agriculture.public.lu.
        # The 11 modern-commune sub-denominations are predicate labels
        # under Art. 8 / Art. 9 of RGD 17-déc-2015; they share the
        # parent's source.
        reglements = src.get("reglements") or []
        return {
            "country": "lu",
            "cahier_url": src.get("source_url") or "",
            "cahier_publisher": src.get("publisher") or "",
            "cahier_filename": src.get("filename") or "",
            "cahier_sha256": src.get("sha256") or "",
            "cahier_kind": src.get("kind") or "ivv-cahier-des-charges",
            "reglements": reglements,
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "commune": record.get("commune") or "",
            "historic_communes": record.get("historic_communes") or [],
        }
    if record.get("country") == "ch":
        # Switzerland: OFAG/BLW repertoire + cantonal règlement. The
        # spine source is the OFAG PDF; per-record source is the
        # canton's wine règlement / Reglement / regolamento. Non-EU
        # country — no EUR-Lex single document.
        sources_list = record.get("sources") or []
        ofag = next((s for s in sources_list
                     if s.get("kind") == "ofag-repertoire"), {})
        reglement = next((s for s in sources_list
                          if s.get("kind") == "cantonal-reglement"), {})
        return {
            "country": "ch",
            "canton": record.get("canton") or "",
            "source_lang": record.get("source_lang") or "",
            "ofag_repertoire_url": ofag.get("url", ""),
            "ofag_repertoire_label": ofag.get("label", ""),
            "ofag_repertoire_sha256": ofag.get("sha256", ""),
            "cantonal_reglement_url": reglement.get("url", ""),
            "cantonal_reglement_shelf": reglement.get("shelf", ""),
            "cantonal_reglement_label": reglement.get("label", ""),
            "cantonal_reglement_sha256": reglement.get("sha256", ""),
            "cantonal_reglement_license": reglement.get("license", ""),
        }
    if record.get("country") == "be":
        # Belgium: EU-OJ ENIG DOCUMENT (Flemish) or DOCUMENT UNIQUE
        # (Walloon). Per-record source_lang drives both the URL rewrite
        # at fetch time and the panel attribution label.
        return {
            "country": "be",
            "source_lang": record.get("source_lang") or "",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
        }
    if record.get("country") == "nl":
        # Netherlands: EU-OJ ENIG DOCUMENT (single source_lang "nl").
        return {
            "country": "nl",
            "source_lang": "nl",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
        }
    if record.get("country") == "mt":
        # Malta: EU-OJ SINGLE DOCUMENT published in English (co-official).
        return {
            "country": "mt",
            "source_lang": "en",
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


# Curator-pinned terroir-facts inheritance for wines whose canonical
# regulator source has no narrative section, when a parent / containing
# region exists with a regulator-grade narrative that honestly applies.
#
# Used by `load_terroir_facts` and `overlay_translated_facts` to fall
# through to the regional source. Always paired with a curated entry in
# `scripts/_lib/appellation_notes.json` so the panel renders an explicit
# inheritance disclosure to the user.
#
# Cases (added 2026-05-29):
#   - SI `bela-krajina` (DOP/PDO-SI-A0878) — okoliš in Posavje wine
#     region; the 2007 Pravilnik defines it regulatorily but carries no
#     terroir narrative; the per-region MKGP Posavje ZGO spec covers
#     it geographically.
#   - SI `belokranjec` (DOP/PDO-SI-A1576) — PTP white-wine style
#     produced exclusively inside Bela krajina; the 2022 PTP Pravilnik
#     carries no terroir narrative; chains through bela-krajina to
#     posavje at the regional level.
_TERROIR_INHERIT_OVERRIDES = {
    "bela-krajina": "posavje",
    "belokranjec": "posavje",
}


def load_terroir_facts(slug: str, parent_slug: str = "") -> dict | None:
    """Per-AOC terroir-facts payload for the sidepanel; falls back to parent
    for DGCs (which inherit the parent appellation's bullets).

    Two modes: bullet-mode (LLM-extracted `facts[]`) and verbatim mode
    (`mode: "verbatim"` with the source `link_to_terroir` quoted as-is,
    emitted by 02d when the lien is below MIN_LIEN_CHARS — see
    `_lib/terroir_verbatim.py`).

    Additionally honours `_TERROIR_INHERIT_OVERRIDES` for curator-pinned
    inheritance (always paired with an appellation_notes entry that
    discloses the inheritance to the user)."""
    cache_dir = ROOT / "raw" / "terroir-facts"
    p = cache_dir / f"{slug}.json"
    if not p.exists() and parent_slug:
        p = cache_dir / f"{parent_slug}.json"
    if not p.exists() and slug in _TERROIR_INHERIT_OVERRIDES:
        p = cache_dir / f"{_TERROIR_INHERIT_OVERRIDES[slug]}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if d.get("mode") == "verbatim":
        if not d.get("verbatim_text"):
            return None
        return {
            "mode": "verbatim",
            "verbatim_text": d.get("verbatim_text") or "",
            "validation_flag": d.get("validation_flag") or "",
            "source_lang": d.get("source_lang") or "",
            "wiki_source_url": d.get("wiki_source_url") or "",
            "cahier_source_pdf_url": d.get("cahier_source_pdf_url") or "",
        }
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
        if not t and slug in _TERROIR_INHERIT_OVERRIDES:
            t = translations.get(_TERROIR_INHERIT_OVERRIDES[slug])
        if not tf or not t:
            out[slug] = rec
            continue
        if tf.get("mode") == "verbatim":
            translated_text = t.get("verbatim_text") or ""
            if not translated_text:
                out[slug] = rec
                continue
            out[slug] = {
                **rec,
                "terroir_facts": {
                    **tf,
                    "verbatim_text": translated_text,
                },
            }
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
                k: v for k, v in json.loads(_notes_path.read_text(encoding="utf-8")).items()
                if not k.startswith("__")
            }
        except (ValueError, OSError) as exc:
            print(f"[warn] appellation_notes.json: {exc}", file=sys.stderr)

    # Wikidata QIDs (stage 02i) → JSON-LD `sameAs` entity reconciliation.
    # Slug-keyed `{slug: {qid, via, …}}`; absent file / unresolved slug → "".
    wikidata_qids: dict[str, dict] = {}
    if WIKIDATA_QIDS.exists():
        try:
            wikidata_qids = json.loads(WIKIDATA_QIDS.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"[warn] wikidata qids-by-slug.json: {exc}", file=sys.stderr)

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
            "de": EXTRACTED_DE,
            "si": EXTRACTED_SI,
            "hr": EXTRACTED_HR,
            "hu": EXTRACTED_HU,
            "ro": EXTRACTED_RO,
            "bg": EXTRACTED_BG,
            "gr": EXTRACTED_GR,
            "cy": EXTRACTED_CY,
            "sk": EXTRACTED_SK,
            "cz": EXTRACTED_CZ,
            "ch": EXTRACTED_CH,
            "lu": EXTRACTED_LU,
            "be": EXTRACTED_BE,
            "nl": EXTRACTED_NL,
            "mt": EXTRACTED_MT,
        }.get(country, EXTRACTED)
        ext_path = ext_dir / f"{slug}.json"
        summary = ""
        sources: dict = {}
        grape_names: dict[str, str] = {}
        # For BG / GR (and any other non-Latin-script corpus added later)
        # the cahier spelling lives in native script. The grape-pill
        # canonical-bracket falls through to this per-record latin form
        # when GRAPES_INFO has neither a VIVC canonical name nor a
        # corpus-wide latin form — covers native varieties without
        # Wikipedia + without VIVC (e.g. BG `shiroka-melnishka-loza`).
        grape_names_latin: dict[str, str] = {}
        is_stub = False
        parent_slug_for_facts = p.get("parent_slug", "") or ""
        file_number = ""
        # Dűlők (HU named single-vineyards) live in the national-spec
        # sidecar (parsed by stage 02f); the on-disk extracted record is
        # immutable, so read the sidecar directly here (Tokaj → 427).
        dulok: list = []
        if country == "hu":
            _ns = NATIONAL_SPECS_HU / f"{slug}.json"
            if _ns.exists():
                try:
                    dulok = json.loads(_ns.read_text(encoding="utf-8")).get("dulok") or []
                except (ValueError, OSError):
                    dulok = []
        if ext_path.exists():
            rec = json.loads(ext_path.read_text(encoding="utf-8"))
            file_number = rec.get("file_number") or ""
            summary = derive_summary(rec)
            sources = _sources_for(rec)
            # IT records augmented via MASAF and ES records augmented via
            # the national pliego have an effective source document — the
            # disciplinare di produzione / pliego de condiciones — even
            # though the on-disk doc-único stub wasn't populated. Don't
            # flag those as "not yet found".
            stub_raw = bool(rec.get("stub")) or rec.get("kind") == "STUB"
            has_augmented_source = (
                (country == "it" and slug in _IT_MASAF_BY_SLUG)
                or (country == "es" and slug in _ES_NATIONAL_PLIEGO_BY_SLUG)
                or (country == "de" and slug in _DE_PRODUKTSPEZIFIKATION_BY_SLUG)
                or (country == "si" and slug in _SI_SPECIFIKACIJA_BY_SLUG)
                or (country == "hr" and slug in _HR_SPECIFIKACIJA_BY_SLUG)
                or (country == "gr" and slug in _GR_NATIONAL_SPEC_BY_SLUG)
                or (country == "cy" and slug in _CY_NATIONAL_SPEC_BY_SLUG)
                or (country == "ro" and slug in _RO_NATIONAL_SPEC_BY_SLUG)
                or (country == "hu" and slug in _HU_NATIONAL_SPEC_BY_SLUG)
                or (country == "bg" and slug in _BG_NATIONAL_SPEC_BY_SLUG)
                or (country == "sk" and slug in _SK_NATIONAL_SPEC_BY_SLUG)
                or (country == "cz" and slug in _CZ_NATIONAL_SPEC_BY_SLUG)
            )
            is_stub = stub_raw and not has_augmented_source
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
                    latin = _latin_form_or_empty(s_name)
                    if latin:
                        grape_names_latin[s_slug] = latin
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
            "country_aliases": _CROSS_BORDER_COUNTRY_ALIASES.get(file_number, []),
            "source_lang": p.get("source_lang") or "",
            "name": p["name"],
            "name_latin": p.get("name_latin") or "",
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
            "grape_names_latin": grape_names_latin,
            "summary": summary,
            "sources": sources,
            "wikidata_qid": (wikidata_qids.get(slug) or {}).get("qid", ""),
            "terroir_facts": terroir_facts,
            "dulok": dulok,
            "menzioni": _IT_MENZIONI_BY_SLUG.get(slug, []),
            "note": appellation_notes.get(slug),
            "is_stub": is_stub,
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

    # --- Phase 3 pilot: gated per-appellation entity pages ----------------
    # gate_classify decides which records earn an indexable, crawlable page.
    # v1 FOLDS every sub-denomination (its narrative/grapes are parent-
    # inherited at render time — CLAUDE.md) and any stub / no-geometry record;
    # an indexable record needs resolved geometry plus its own grapes / summary
    # / terroir. The pilot emits only a small hand-picked allowlist (intersected
    # with the gate) so indexation + demand can be validated before a corpus-
    # wide rollout. Slugs absent from the corpus are silently dropped.
    def gate_classify(rec: dict) -> tuple[str, str | None]:
        if rec.get("is_sub_denomination"):
            return ("fold", rec.get("parent_slug"))
        if rec.get("is_stub") or rec.get("geom_source") == "stub-no-geometry" or not rec.get("bbox"):
            return ("fold", None)
        has_own = bool(
            rec.get("terroir_facts") or rec.get("summary") or (rec.get("grapes_principal") or [])
        )
        return ("index", None) if has_own else ("fold", None)

    # Full-corpus gate: every record gets a pre-rendered file (so the CDN can
    # serve any /<locale>/<slug> deep-link). index slugs get a full, indexable
    # entity page; fold slugs (sub-denominations, stubs, no-geometry, thin) get a
    # lightweight noindex page that canonicalises to the parent — on the map for
    # the deep-link, kept out of the index as a near-duplicate of the parent.
    index_slugs: list[str] = []
    fold_slugs: list[str] = []
    for _slug, _rec in aocs.items():
        (index_slugs if gate_classify(_rec)[0] == "index" else fold_slugs).append(_slug)
    print(
        f"[entity] gate: {len(index_slugs)} index + {len(fold_slugs)} fold "
        f"= {len(index_slugs) + len(fold_slugs)}/{len(aocs)} records",
        file=sys.stderr,
    )

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
            if rec_country in ("ch", "be"):
                # CH + BE source-language is per-record (per canton for
                # CH; per language community for BE — Flemish=nl,
                # Walloon=fr).
                src_lang = rec.get("source_lang") or "fr"
            elif rec_country == "nl":
                src_lang = "nl"
            elif rec_country == "mt":
                # MT's country code is "mt" but its source language is "en"
                # (Malta's EU single documents are published in English).
                src_lang = "en"
            else:
                # LU's country code is "lu" but its source language is "fr" — fall through to the "fr" default.
                src_lang = rec_country if rec_country in ("es", "pt", "it", "at", "de", "si", "hr", "hu", "ro", "bg", "gr", "cy", "sk", "cz") else "fr"
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
                rec = aocs.get(slug, {}) or {}
                c = rec.get("country")
                if c in ("ch", "be"):
                    return rec.get("source_lang") or "fr"
                if c == "nl":
                    return "nl"
                if c == "mt":
                    return "en"
                # LU (country "lu") uses source_lang "fr" — falls through to the "fr" default.
                return c if c in ("es", "pt", "it", "at", "de", "si", "hr", "hu", "ro", "bg", "gr", "cy", "sk", "cz") else "fr"
            facts_translations = {
                slug: t for slug, t in all_facts_translations.items()
                if lang != _src_lang_for(slug)
            }
            if facts_translations:
                aocs_for_lang = overlay_translated_facts(aocs_for_lang, facts_translations)
        out = (WIKI / "index.html") if lang == "en" else (WIKI / lang / "index.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Pass a swapped facets dict so the per-locale `aocs` is the data bundle.
        per_locale_facets = {**facets, "aocs": aocs_for_lang}
        # EN entities live under /en/<slug>, fr/es/nl under /<lang>/<slug>.
        entity_out_dir = WIKI / ("en" if lang == "en" else lang)
        html_out, assets, n_index, n_fold = render_map_html(
            **per_locale_facets, locale=lang, grapes_info=lex, styles_info=styles_lex,
            index_slugs=index_slugs, fold_slugs=fold_slugs, entity_out_dir=entity_out_dir,
        )
        out.write_text(html_out, encoding="utf-8")
        # Three external, content-hashed bundles every page of this locale
        # references: the data bundle (AOCS + grape tooltips) under /data/, the
        # shared stylesheet and the per-locale app script under /assets/. Prune
        # stale hashes (keeping the current one) so the dirs don't accumulate
        # across rebuilds; deploy prunes the remote, this keeps the tree clean.
        data_dir = WIKI / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = WIKI / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        data_filename, data_bytes = assets["data"]
        style_filename, style_bytes = assets["style"]
        app_filename, app_bytes = assets["app"]
        for _old in data_dir.glob(f"aocs.{lang}.*.js"):
            if _old.name != data_filename:
                _old.unlink()
        (data_dir / data_filename).write_bytes(data_bytes)
        for _old in assets_dir.glob("style.*.css"):
            if _old.name != style_filename:
                _old.unlink()
        (assets_dir / style_filename).write_bytes(style_bytes)
        for _old in assets_dir.glob(f"app.{lang}.*.js"):
            if _old.name != app_filename:
                _old.unlink()
        (assets_dir / app_filename).write_bytes(app_bytes)
        # Per-appellation pages are streamed straight to disk by render (to
        # entity_out_dir/<slug>/index.html) so the whole corpus never sits in
        # memory at once.
        print(f"[entity] {lang}: wrote {n_index} index + {n_fold} fold pages", file=sys.stderr)
        # EN's home stays at / (canonical), but its appellation deep-links live
        # under /en/<slug> so a single CDN rewrite ( /<lang>/<slug> →
        # /<lang>/index.html ) covers all four locales. Emit the same page at
        # /en/index.html as the origin those paths resolve to.
        if lang == "en":
            en_alias = WIKI / "en" / "index.html"
            en_alias.parent.mkdir(parents=True, exist_ok=True)
            en_alias.write_text(html_out, encoding="utf-8")
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

    write_seo_files(index_slugs)


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

    # Self-hosted runtime libs (maplibre-gl, pmtiles) — tracked git inputs
    # under scripts/_lib/vendor/, mirrored to /assets/vendor/ so the map has
    # no third-party CDN dependency. Versioned filenames = immutable; only
    # .js/.css ship (README.md stays out of the published tree).
    if VENDOR_SRC.exists():
        vendor_out = ASSETS_OUT / "vendor"
        vendor_out.mkdir(parents=True, exist_ok=True)
        for src in sorted(VENDOR_SRC.iterdir()):
            if src.suffix not in (".js", ".css"):
                continue
            dst = vendor_out / src.name
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


def write_seo_files(entity_slugs: list[str] | None = None) -> None:
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

    # Indexable per-appellation entity pages: one <url> per locale per slug
    # (en under /en/<slug>), each carrying the slug's hreflang cluster
    # (x-default -> EN). Folded (noindex) slugs are deliberately excluded.
    n_entity = 0
    for slug in entity_slugs or []:
        ent_paths = {lang: f"/{lang}/{slug}" for lang in LOCALES}
        ent_alts = _hreflang_alternates(ent_paths)
        for lang in LOCALES:
            url_blocks.append(
                _sitemap_url_block(f"{SITE_BASE_URL}{ent_paths[lang]}", today, ent_alts)
            )
            n_entity += 1

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(url_blocks)
        + "\n</urlset>\n"
    )
    (WIKI / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /map-data/\n"
        f"Sitemap: {SITE_BASE_URL}/sitemap.xml\n"
    )
    (WIKI / "robots.txt").write_text(robots, encoding="utf-8")
    print(
        f"[seo] wrote {WIKI.relative_to(ROOT)}/robots.txt and sitemap.xml "
        f"({len(url_blocks)} URLs: {len(LOCALES)} home + {n_entity} entity)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
