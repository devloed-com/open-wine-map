# Re-fetch recipes per tier and country

| finding | recipe |
|---|---|
| eAmbrosia NEWER (new publication) | `scripts/<cc>/01_fetch_pliegos.py --only <slug> --refresh` (then `01b_solve_waf.py` if the page is a WAF challenge) → `02_extract_pliegos.py --only <slug>` → `04_build_maps.py` |
| eAmbrosia GONE / removedFlag | read the regulation title on EUR-Lex (`legal-content/EN/TXT/HTML/?uri=CELEX:3YYYYRNNNN`); if it cancels, add the GI to `scripts/_lib/cancelled_gis.json` (stays on the map, marked); if it is a renumbering, update the index |
| eAmbrosia NEW registered GI | `scripts/<cc>/00_fetch_data.py` → 01 → 02; a `_REGION_BY_FILE_NUMBER` entry; geometry (post-Bétard → commune list) → 04 |
| INAO NEWER (newer arrêté) | pin the BO Agri URL in `raw/inao/cahiers/manual_overrides.json`, or `scripts/01_scrape_cahiers.py` behind a French exit node → `02_extract_cahiers.py --only «name»` → 04 |
| INAO IN-OPPOSITION | nothing yet; re-check after the PNO closes |
| data.gouv.fr parcellaire NEWER | `scripts/00_fetch_data.py` → 04; then `audit_parcellaire_gaps.py --strict` and re-verify `parcellaire_carry_forward.json` / `parcellaire_gap_fills.json` |
| data.gouv.fr SIQO NEWER | 00 → 01 → 02 (the drop guard refuses a vanished denomination: decide with a cited act) → 04 |
| national-spec document NEWER / GONE | the country's `01c_fetch_specifikacije.py` (`--refresh`) → `02f_…` → 04; ES `02f_extract_national_pliegos.py --slug <slug> --refresh`; IT `02f_extract_masaf.py --slug <slug>`; DE `00` → `02f_extract_produktspezifikation.py --slug <slug>`; a 404 → the layer's `manual_overrides.json` |
| GOV.UK NEWER | `scripts/gb/00_fetch_data.py` → `01_fetch_specs.py` → `02_extract_specs.py` → 04 (a new GI also needs `_FILE_NUMBER_BY_SLUG`) |
| GISCO / swisstopo NEWER | bump the vintage in the stage-00 fetchers and geometry indexes → 04 → the geometry audits |
| trade body GONE | fix the entry in `scripts/_lib/appellation_urls.py` (or `null` it: a wrong body is worse than none) |
| Wikipedia NEWER | `scripts/02b_fetch_aoc_lexicon.py --lang <lang> --only <slug>` (then 02d sees the new hint on its next run) |
