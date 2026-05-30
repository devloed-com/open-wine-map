# Gap-type registry

Each gap type is a recurring class of missing curation data. Per entry:
**detect** (command that lists open items), **triage** (how to filter to the
actionable subset), **search** (public sources, priority order),
**WAF risk** (does the agent path work, or is the browser needed),
**overrides target** (where confirmed findings land), **re-run** (stage that
consumes the file).

All paths are relative to the repo root. The `raw/` tree is gitignored.

---

## `grape-wikipedia` — missing Wikipedia tooltip card for a grape

A grape pill's tooltip extract is fetched from `<locale>.wikipedia.org`. When
the slug-derived title misses, the per-locale record is `missing` (no page) or
`error: not_grape_topic` (resolved to a homonym place/person).

- **Parameter:** locale ∈ `en | fr | es | nl`. Default `es`.
- **Detect:**
  ```
  jq -r 'select(.missing or .error) | [.slug, (.error // "missing"), (.rejected_title // "-")] | @tsv' raw/wikipedia/grapes/<locale>/*.json
  ```
- **Triage:** the raw scan over-counts — most `missing` rows are non-Iberian
  varieties with genuinely no article in that locale. Keep only slugs that
  are actually **cited in that country's corpus**. Cross-reference
  `scripts/audit_es_grape_aliases.py` (ES) / `scripts/audit_grape_coverage.py`.
  The actionable ES set is ~39, not ~744.
- **Search:** (1) `<locale>.wikipedia.org` — try `(uva)` / `(vino)`
  disambiguators, accent and Catalan/Castilian spelling variants;
  (2) VIVC (`vivc.de`) for the prime name + synonyms to derive alternate
  titles and to confirm DNA identity.
- **WAF risk:** low — agents handle Wikipedia and VIVC fine.
- **Overrides target:** `raw/wikipedia/grape_overrides.json`, shape
  `{ "<locale>": { "<slug>": "<exact Wikipedia page title>" } }`, keys sorted
  alphabetically within each locale.
- **Re-run:** `02b_fetch_grape_lexicon.py` → `04_build_maps.py`.

## `style-wikipedia` — missing Wikipedia card for a wine-style slug

Same mechanism as `grape-wikipedia`, for style-taxonomy slugs.

- **Parameter:** locale ∈ `en | fr | es | nl`.
- **Detect:** scan `raw/wikipedia/styles/<locale>/*.json` for `missing`/`error`.
- **Triage:** the curated set covers every node in
  `scripts/_lib/style_taxonomy.py`; missing entries are the genuine gap.
  A locale gap with no native article is filled by stage 02b-translate, not
  this skill — confirm with the user before researching.
- **Search:** `<locale>.wikipedia.org`.
- **WAF risk:** low.
- **Overrides target:** `raw/wikipedia/style_overrides.json` (per-locale
  slug → Wikipedia title).
- **Re-run:** `02b_fetch_style_lexicon.py` → `04_build_maps.py`.

## `aoc-wikipedia` — missing Wikipedia page for an appellation

Used by stage 02d as a salience hint and by the panel tooltip.

- **Parameter:** locale ∈ `fr | es | it | pt`.
- **Detect:** records under `raw/wikipedia/aocs/<locale>/` marked `missing`
  or `not_aoc_topic`.
- **Search:** `<locale>.wikipedia.org`, cascading through `(vino)` / `(DOP)` /
  `(denominación de origen)` style disambiguators.
- **WAF risk:** low.
- **Overrides target:** `raw/wikipedia/aoc_overrides.json` — richer schema
  (`wiki_title`, `page_url`, `verification_quote`); see
  `raw/wikipedia/aoc_overrides.README.md`.
- **Re-run:** `02b_fetch_aoc_lexicon.py` → `04_build_maps.py`.

## `vivc-ambiguous` — grape slug with multiple candidate VIVC entries

Stage 02g could not resolve a slug to one VIVC variety number.

- **Detect:**
  ```
  jq -r '.entries | to_entries[] | select(.value.vivc_id==null) | .key' raw/vivc/slug_overrides.json
  ```
- **Search:** `vivc.de` passport pages for each candidate; cross-check
  Robinson/Harding/Vouillamoz *Wine Grapes* and the cited appellations'
  consejo regulador to pick the variety the pliego actually means.
- **WAF risk:** low.
- **Overrides target:** `raw/vivc/slug_overrides.json` — set the integer
  `vivc_id` on the entry (leave `_candidates` for provenance).
- **Re-run:** `02g_fetch_vivc.py` → `04_build_maps.py`.

## `it-disciplinare` — Italian wine with no source document

IT wine renders as a bare stub: name in the sidebar, no grapes / no terroir.

- **Detect:** `scripts/audit_it_coverage.py` — read the curator queue at the
  bottom (`no-publication` and `not-single-document` buckets).
- **Search:** (1) MASAF (`masaf.gov.it`) per-wine disciplinare PDF;
  (2) Gazzetta Ufficiale (`gazzettaufficiale.it`) approving DM; (3) regional
  gazette (BUR Veneto/Abruzzo/…); (4) consorzio di tutela site. A URL counts
  only if the document names the GI, carries the production rules (grape
  list + link-to-terroir), and is current.
- **WAF risk:** medium — EUR-Lex is WAF-blocked; MASAF / Gazzetta / consorzi
  are usually agent-reachable. Route EUR-Lex-only items to the browser.
- **Overrides target:** `raw/it/masaf-disciplinari/manual_overrides.json`
  (MASAF/regional/consorzio/gazzetta PDF) or
  `raw/it/oj-pages/manual_overrides.json` (EU-OJ documento-unico HTML), shape
  `{ "<slug>": { "pdf_url": ..., "source_org": ..., "verification_note": ... } }`.
- **Re-run:** `it/02f_extract_masaf.py` (or `it/01`+`it/02`) → `04_build_maps.py`.

## `es-pliego` — Spanish wine with no OJ publication

ES wine appears in the sidebar with no polygon and no rules.

- **Detect:** `scripts/audit_es_coverage.py` — curation queue at the bottom;
  `scripts/es/regen_manual_overrides_template.py` writes the editable file.
- **Search:** (1) EUR-Lex OJ documento único (Series C preferred over L);
  (2) BOE PDF; (3) regional gazette HTML; (4) consejo regulador site.
- **WAF risk:** medium — EUR-Lex CloudFront blocks agents; BOE / regional
  gazettes are usually fine.
- **Overrides target:** `raw/es/oj-pages/manual_overrides.json` (doc-único
  URL) or `raw/es/national-pliegos/manual_overrides.json` (national pliego
  PDF for variety augmentation).
- **Re-run:** `es/01_fetch_pliegos.py` → `es/02_extract_pliegos.py` →
  `04_build_maps.py`.

## `pt-caderno` — Portuguese wine with no IVV caderno

- **Detect:** `scripts/audit_pt_coverage.py`;
  `scripts/pt/regen_manual_overrides_template.py` writes the editable file.
- **Search:** alternate IVV path, BOE-style national gazette PDF, consejo
  regulador site. PT IVV first-run scrape usually matches 44/44, so this gap
  is rare.
- **WAF risk:** low.
- **Overrides target:** `raw/pt/ivv/cadernos/manual_overrides.json`,
  `pdf_url` field.
- **Re-run:** `pt/01_fetch_cadernos.py` → `pt/02_extract_cadernos.py` →
  `04_build_maps.py`.

## `fr-cahier` — French AOC cahier stub

AOC flagged a stub by `scripts/audit_coverage.py`.

- **Detect:** `scripts/audit_coverage.py` — stub list. Reconcile against the
  France section of `CURATOR_TODO.md`.
- **Search:** (1) BO Agri search UI
  (`https://info.agriculture.gouv.fr/gedei/site/bo-agri/recherche`);
  (2) Légifrance LODA; (3) professional-organisation mirrors (CAVB, FGVB,
  lr-origine, …) for 2011-era cahiers.
- **WAF risk:** high — BO Agri search is a JavaScript SPA that agents cannot
  drive. Route `fr-cahier` straight to the browser-extension prompt.
- **Overrides target:** `raw/inao/cahiers/manual_overrides.json`, keyed by
  `id_appellation`, shape `{ "<id>": { "name": ..., "boagri_urls": [...],
  "note": ... } }`. Template: `scripts/manual_overrides.example.json`.
- **Re-run:** `01_scrape_cahiers.py` → `02_extract_cahiers.py` →
  `03_generate_wiki.py` → `04_build_maps.py`.

## `synonym-pairs` — disputed grape synonym pair (ad-hoc)

A pliego writes two names on one line (`MACABEO - VIURA`) and VIVC is
ambiguous about whether they are one variety or two. Not auto-detected — the
user supplies the pair list. Output is a fold decision (`slug_X → slug_Y`),
not an overrides file; stage as a `CURATOR_TODO.md` note plus a proposed
`GRAPE_ALIAS` edit in `scripts/_lib/grape_lexicon.py` for the user to apply.

## `it-consorzio-url` — Italian appellation with no DO-organisation link

The map card links the body that administers the denominazione (FR
*interprofession*, ES *consejo regulador*, IT *consorzio di tutela*). FR and
ES are curated; IT had zero coverage in `appellation_urls.json`.

- **Detect:** IT wine slugs in `raw/it/eambrosia/index.json` (`wines[].slug`)
  that are absent from `by_slug` in `scripts/_lib/appellation_urls.json`.
- **Triage:** dedupe by eAmbrosia `producer_group.name` — it names a
  consorzio for ~307 of 531 wines (~131 distinct consorzi); research those
  by consorzio name. The other ~224 wines have no consorzio in eAmbrosia —
  research by appellation name (more `NONE`s — small IGTs often have no
  consorzio). One consorzio URL covers every wine it administers.
- **Search:** (1) the consorzio's own website; (2) Federdoc
  (`federdoc.com`) members directory; (3) MASAF (`masaf.gov.it`) recognised-
  consorzi list; (4) regional institute (e.g. Istituto Marchigiano di
  Tutela Vini). Reject winery / e-commerce / tourism-portal sites.
- **WAF risk:** low — consorzio sites, Federdoc and MASAF are agent-reachable.
- **Overrides target:** `scripts/_lib/appellation_urls.json` → `by_slug`,
  shape `{ "<slug>": { "url": ..., "label": "<organisation name>" } }`.
- **Re-run:** `04_build_maps.py`.

## `national-spec` — country's wines have no EU-OJ single document (generic)

The umbrella gap for any country whose wines are Art.107 / Reg.1308/2013
grandfathered names with only a non-fetchable `Ares(...)` reference in
eAmbrosia — so there is no EU-OJ single document and we need the country's
**national regulator product specification** instead. `cz-specification` and
`hr-specification` below are worked instances; this entry is the parameterised
form for the next country (`/research-gaps national-spec <cc>`). Pairs with
the **`national-spec-layer`** skill, which scaffolds + wires the 01c/02f layer
once this returns a source.

- **Parameter:** `cc` — 2-letter country code.
- **Detect:** `scripts/audit_<cc>_coverage.py` — the `no-publication` /
  stub bucket. The actionable set is every stub wine (usually all of them).
- **Triage:** typically all stubs are in scope (small corpora). Confirm the
  count with the user only if > 60.
- **Dispatch (discovery-first, the BG pattern):** spawn **two** agents in
  parallel rather than chunking per-wine, because the source structure is
  unknown until found:
  1. **national-source scout** — find the regulator's per-wine spec listing
     (agency site / national gazette / ministry), the per-wine URL pattern,
     the document format, and — critically — whether the spec carries a
     **terroir / link-to-region section** (quote one). Report fetchability
     (HTTP 200 vs WAF/JS/404) and licence (official-act exemption / open data).
  2. **EUR-Lex negative-check** — confirm 0 (or few) of the wines actually
     have a published EU-OJ single document, so the national source is the
     right path. (For BG this returned a clean 0/51.)
  Once the source + URL pattern are confirmed, a third pass enumerates the
  per-wine URLs (often transcribed from one listing page; validate a sample
  fetch — the famous-region URLs are the ones most likely mistyped).
- **Gate before building:** the source must be public + licence-clear AND
  carry terroir narrative. If only a variety/area roster exists (the CZ
  reality), warn the user — 02d will produce few/no bullets and the
  acceptance bar may not be met from this source alone.
- **WAF risk:** medium — EUR-Lex is WAF-prone for agents; national regulator
  sites vary (IAVV/eavw.com was agent-reachable for BG; some ministry portals
  are JS/WAF-gated and need the browser fallback or the user's VPN).
- **Overrides target:** a **dedicated** `raw/<cc>/national-specs/manual_overrides.json`
  (slug → `{url, source_org, file_number, format, note}`) — NOT the country's
  `oj-pages/manual_overrides.json` (a PDF/.doc there breaks stage 02's HTML
  single-document parser; the national specs ride the parallel 01c/02f layer).
- **Re-run:** `<cc>/01c_fetch_specifikacije.py` →
  `<cc>/02f_extract_national_specs.py --all` → 02d/02e → `04_build_maps.py`.
  Build the parser/extractor first via the `national-spec-layer` skill.
- **Calibrate:** if a country's source had a shape this entry didn't predict
  (no terroir section, a new host/format, a WAF that needed the browser),
  amend this entry while it's fresh so the next country starts from reality.

## `cz-specification` — Czech wine with no EU-OJ single document

All 13 CZ wines are Art.107 / Reg.1308/2013 grandfathered names whose
only eAmbrosia reference is a non-fetchable `Ares(...)` summary-sheet.
The canonical alternative is the Czech national implementing decree
(Vyhláška č. 88/2017 Sb. for varieties + Vyhláška č. 254/2010 Sb. for
the per-podoblast obec list, both implementing Zákon č. 321/2004 Sb.).

- **Detect:** `scripts/audit_cz_coverage.py` — every wine in the
  `no-publication` bucket. `scripts/cz/regen_manual_overrides_template.py`
  writes the editable file.
- **Triage:** 13 wines, all actionable. The 6 podoblasti + 4 macro
  names share two consolidated decrees; the 3 newer 2011 single-vineyard
  PDOs (Znojmo, Šobes, Novosedelské Slámové víno) are likely genuine
  `NONE`s — verified 2026-05-24.
- **Search:** (1) EUR-Lex Czech-language search by file_number AND
  protected name (most CZ wines have nothing — but the post-2009
  ones might); (2) Sbírka zákonů via zakonyprolidi.cz mirror (the
  Sbírka PDF is image-scanned, eSbírka is a JS SPA); (3)
  ukzuz.gov.cz / eagri.cz / mze.gov.cz / vinarskecentrum.cz / svcr.cz
  for per-PDO specifikace PDFs (these don't exist for most wines).
- **WAF risk:** medium — EUR-Lex AWS WAF; agents can handle
  zakonyprolidi.cz fine.
- **Overrides target (active fetch):** `raw/cz/oj-pages/manual_overrides.json`
  keyed by slug, `{ "url": "<EUR-Lex Jednotný-dokument HTML>" }` —
  **only** EUR-Lex single-document URLs will parse with the stage-02
  EU-OJ template. National-spec URLs (sbirka, ukzuz, eagri) go in the
  **documentation** field with `url: ""` (the regen template's
  `__doc__` says empty url is ignored).
- **National-spec extraction (already shipped 2026-05-24):**
  `scripts/cz/02f_extract_national_specs.py` parses Vyhláška 88/2017
  + 254/2010 into `raw/cz/national-specs/` sidecars (variety roster +
  per-podoblast obec lists). Stage 04 augments every CZ wine with the
  67-variety national list. Re-run that script if you find an updated
  decree URL.
- **Re-run:** `cz/01_fetch_pliegos.py` → `cz/02_extract_pliegos.py` →
  `04_build_maps.py` (after editing `manual_overrides.json` with an
  EUR-Lex URL); OR `cz/02f_extract_national_specs.py --refresh` →
  `04_build_maps.py` (after a decree update).

## `hr-specification` — Croatian wine with no EU-OJ single document

16 of 18 HR wine PDOs are Art.107 / Reg.1308/2013 grandfathered names
whose only eAmbrosia reference is a non-fetchable `Ares(...)` summary-
sheet. The canonical alternative is the Croatian national
*specifikacija proizvoda* (per Reg. 1308/2013 art. 94) published by the
Ministarstvo poljoprivrede (poljoprivreda.gov.hr).

- **Detect:** `scripts/audit_hr_coverage.py` — `no-publication` stubs.
  `scripts/hr/regen_manual_overrides_template.py` writes the EU-OJ queue.
- **Triage:** 16 wines, all actionable; all resolved 2026-05-29.
- **Search:** (1) MPS listing page
  `poljoprivreda.gov.hr/istaknute-teme/hrana-111/oznake-kvalitete/oznake-izvornosti-vina/229`
  → per-wine `.doc`/`.docx`/PDF in
  `…/UserDocsImages/dokumenti/hrana/zastita_oznaka_izvrsnosti_vina/na_razini_EU/`;
  (2) Narodne novine (narodne-novine.nn.hr); (3) EUR-Lex Croatian
  single document (none exist for the grandfathered names).
- **WAF risk:** low — poljoprivreda.gov.hr is agent-reachable.
- **Overrides target:** `raw/hr/specifikacije/manual_overrides.json`
  (NOT `raw/hr/oj-pages/...` — the .doc/.pdf specs ride the parallel
  01c/02f layer; a spec URL in the oj-pages `url` field would let stage
  01 save the Dingač PDF as `ok` and stage 02 can't parse it). Shape:
  `{ "<slug>": { "url": ..., "source_org": "mps", "note": ...,
  "file_number": ... } }`.
- **Re-run:** `hr/01c_fetch_specifikacije.py` →
  `hr/02f_extract_specifikacije.py` → `04_build_maps.py`. National-spec
  parser branch already shipped (`scripts/_lib/hr/specifikacija.py`,
  lettered sections a–j; `.doc` via the shared `owm-antiword` Docker
  image).

## `at-weinkomitee-url` — Austrian appellation with no DO-organisation link

Austrian analogue of `it-consorzio-url`. The administering body of a DAC is
its **Regionales Weinkomitee**; the public web presence is usually the
regional/Bundesland wine board (Wein Burgenland, Wein Steiermark, …) or a
per-DAC `.wine` site. eAmbrosia carries **no** producer-group name for any
AT wine, so research is by appellation name.

- **Detect:** AT wine slugs in `raw/at/eambrosia/index.json` (`wines[].slug`)
  absent from `by_slug` in `scripts/_lib/appellation_urls.json`.
- **Triage:** 32 wines, no sub-denominations — a flat list. Many share an
  org (all Burgenland DACs ≈ Wein Burgenland; the 5 generic western
  regions ≈ ÖWM); still write one `by_slug` entry each.
- **Search:** (1) the Regionales Weinkomitee / per-DAC regional site;
  (2) the Bundesland wine board; (3) Österreich Wein Marketing (ÖWM) —
  oesterreichwein.at / austrianwine.com — national fallback + region
  directory. Reject winery / shop / tourism-portal sites.
- **WAF risk:** low — Austrian wine-board sites are agent-reachable
  (weinniederoesterreich.at serves a SiteGround bot-CAPTCHA but is live).
- **Overrides target:** `scripts/_lib/appellation_urls.json` → `by_slug`,
  shape `{ "<slug>": { "label": "<organisation name>", "url": ... } }`.
- **Re-run:** `04_build_maps.py`.

---

## Adding a new gap type

When `/research-gaps <free-form description>` names an unlisted gap, work out
with the user: the detect command, the public-source search priority, the
WAF risk, and the overrides target — then append an entry here in the same
shape so the next run is one command.
