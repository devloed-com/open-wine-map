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
