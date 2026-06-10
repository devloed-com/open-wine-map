"""Shared state for the stage-04 national-spec augmenters.

The per-country augmenters (``_lib/augment/<cc>.py``) populate slug-keyed
provenance caches that ``_sources_for()`` and the panel-blob phase in
``04_build_maps.py`` read back later (the AOC-blob phase re-reads each
extracted JSON from disk, where the in-memory augmentation isn't persisted,
so these caches give it access to the same provenance the in-memory record
carries). Both the writer (the augmenter) and the readers (stage 04) MUST
reference the *same* dict object, so the caches live here and are imported by
both sides. The per-country sidecar directories live here too for the same
reason. Moved verbatim out of 04_build_maps.py — no behaviour change.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Per-country national-spec sidecar directories read by the augmenters.
NATIONAL_PLIEGOS_ES = ROOT / "raw" / "es" / "national-pliegos-extracted"
MASAF_DISCIPLINARI_IT = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
IT_REGIONAL_REGISTERS = ROOT / "raw" / "it" / "regional-variety-registers"
PRODUKTSPEZIFIKATION_DE = ROOT / "raw" / "de" / "produktspezifikationen-extracted"
SPECIFIKACIJE_SI = ROOT / "raw" / "si" / "specifikacije-extracted"
SPECIFIKACIJE_HR = ROOT / "raw" / "hr" / "specifikacije-extracted"
NATIONAL_SPECS_BG = ROOT / "raw" / "bg" / "national-specs-extracted"
NATIONAL_SPECS_GR = ROOT / "raw" / "gr" / "national-specs-extracted"
NATIONAL_SPECS_CY = ROOT / "raw" / "cy" / "national-specs-extracted"
NATIONAL_SPECS_RO = ROOT / "raw" / "ro" / "national-specs-extracted"
NATIONAL_SPECS_HU = ROOT / "raw" / "hu" / "national-specs-extracted"
NATIONAL_SPECS_SK = ROOT / "raw" / "sk" / "national-specs-extracted"
NATIONAL_SPECS_CZ = ROOT / "raw" / "cz" / "national-specs"

# Slug-keyed provenance caches. Populated by the per-country augmenter named
# in each comment; read by _sources_for() / the panel-blob phase in stage 04.
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
