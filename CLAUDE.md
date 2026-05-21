# Open Wine Map — curation guide for Claude

This project is a reference wiki + map of European wine appellations,
generated mechanically from public regulator data. It is **not** a
hand-curated narrative wiki.

The corpus is multi-country: France (canonical, INAO + JORF) is the
primary pipeline at `scripts/`; Spain (eAmbrosia + EUR-Lex single
documents) is the second country, with parallel scripts under
`scripts/es/`. Each per-record JSON carries a top-level `country`
field (`"fr"` / `"es"`) so stage 04 can merge both streams into a
single unified map. See "Spain pipeline" below for ES-specific
details and "Hard rules" for invariants that apply to every country.

## Hard rules

- **Public sources only.** Every fact in `wiki/` must trace to a file in `raw/`
  that was fetched from a public, licence-clear source (INAO, IGN, JORF,
  data.gouv.fr). No proprietary teaching material, no scraped third-party
  narrative wikis. If you cannot point at a public-source provenance, do not
  write it down.
- **Generation, not authorship.** Pages in `wiki/` are produced by
  `scripts/03_generate_wiki.py`. Do not hand-edit per-AOC pages — fix the
  generator instead. Hand-authored content is restricted to `wiki/concepts/`
  (a small fixed set of overview pages on terroir, the AOC system, etc.).
- **Reproducible.** A fresh checkout, `uv sync`, and a sequential run of
  `scripts/00_fetch_data.py` → `scripts/04_build_maps.py` must rebuild
  everything in `wiki/` from scratch. Anything that breaks that contract is a
  bug.
- **Wikipedia is a bounded secondary source.** Three stages fetch from
  Wikipedia (CC-BY-SA 4.0), plus a translation sidecar:
  - Stage 02b/grapes (`scripts/02b_fetch_grape_lexicon.py`) — one short
    summary per grape variety, used in the map sidepanel grape-pill tooltip.
  - Stage 02b/aocs (`scripts/02b_fetch_aoc_lexicon.py`) — per-AOC page
    (lead, section headings, full plaintext), used in stage 02d as a
    salience hint for terroir-fact extraction (see the bounded-narrative-
    layer rule below).
  - Stage 02b/styles (`scripts/02b_fetch_style_lexicon.py`) — one short
    summary per wine-style slug, used in the map sidepanel style-pill
    tooltip. The curated set covers **every node** in
    `scripts/_lib/style_taxonomy.py`: top-level buckets (red / white /
    rosé / sparkling / sweet / other), interior groups (fortified /
    sparkling-quality / semi-sparkling / late-harvest / raisin-wine /
    oxidative / generoso), distinctive leaves (vin jaune, crémant, vdn,
    vin de paille, grains nobles, vendanges tardives, clairet, primeur,
    vin de liqueur, fino, manzanilla, amontillado, oloroso, palo
    cortado, rancio, mistela), and the generic leaves (tranquille,
    dry). Per-locale Wikipedia titles live in
    `raw/wikipedia/style_overrides.json`. When a target locale has no
    native Wikipedia article for a slug, the gap is filled by stage
    02b-translate rather than left blank.
  - Stage 02b/styles-translate (`scripts/02b_translate_styles.py`) —
    for every (slug, target-locale) without a native Wikipedia fetch,
    picks the best source-locale extract (preference EN > FR > ES > NL),
    translates it into the target locale, and caches the result under
    `raw/translations/styles/<lang>/<slug>.json` with full source
    attribution (`source_lang`, `source_page_url`,
    `source_wikipedia_title`, `source_sha`, `translator`,
    `translator_kind`). Providers mirror 02c / 02e: `anthropic`,
    `ollama` (default), or `manual` via `--emit-todo PATH` +
    `--import PATH --translator-id …`. Cache invalidates per (slug,
    locale) when the source extract's sha256 changes. The UI renders
    translated tooltips with "Traduit de Wikipédia en &lt;source&gt; ·
    CC BY-SA 4.0" (linked to the source article) in place of the
    `(français)` fallback marker.
  - Stage 02b/grapes-translate (`scripts/02b_translate_grapes.py`) —
    sister stage to 02b/styles-translate, for grape Wikipedia extracts.
    The source-locale preference is *per-slug*, derived from the
    `per_slug_dominant_lang()` index in
    `scripts/_lib/grape_corpus.py` (the country whose corpus mentions
    the slug most frequently): the chain is
    `dominant-cahier-lang → fr → en → any-other`. Identical
    provider trio, manual round-trip flags, and sha-keyed cache
    invalidation. Stage 04 surfaces the translated extract in the
    pill tooltip with the same "Traduit de Wikipédia en &lt;source&gt;"
    attribution.
  Cahier text, commune lists, region names, and INAO category codes continue to
  come exclusively from INAO/JORF. Each Wikipedia entry caches `revision`,
  `fetched_at`, `page_url`, and `license`; the UI must render attribution
  ("via Wikipedia · CC BY-SA 4.0") next to any extract it shows.
- **VIVC is a third-party grape-taxonomy reference (factual citation).**
  Stage 02g (`scripts/02g_fetch_vivc.py`) resolves every distinct grape
  slug in the FR/ES/PT corpora to a VIVC variety number (Vitis
  International Variety Catalogue, Julius Kühn-Institut Geilweilerhof —
  https://www.vivc.de/). The resolved record carries the VIVC prime
  name, berry colour, country of origin, parentage, and full synonym
  list with per-country "Official name in X" flags. Three uses:
  (1) the **canonical-bracket** on each grape pill — the cahier's
  spelling is shown verbatim with the VIVC prime name in brackets when
  distinct (e.g. *Aragonez (Tempranillo Tinto)* on a PT pill, suppressed
  when normalisation collapses to the same name); (2) **synonym-aware
  Wikipedia search** in stage 02b/grapes (when the slug-derived title
  misses, the chain walks VIVC's prime + synonyms in
  country-official-name-priority order); (3) **VIVC #&lt;id&gt;** link
  in the tooltip source-block alongside the Wikipedia attribution.
  JKI publishes no explicit data licence — the codebase therefore ships
  VIVC IDs + prime names (factual citation) and does **not** republish
  verbatim synonym strings in the UI pending JKI confirmation. Citation:
  Röckel et al., Vitis International Variety Catalogue — www.vivc.de.
  Ambiguous slugs (multiple candidate VIVC entries) get pinned via
  `raw/vivc/slug_overrides.json` (template at `slug_overrides.example.json`).
- **Machine-translated summaries are a bounded narrative layer.** Stage 02c
  (`scripts/02c_translate_summaries.py`) translates the FR cahier summary
  paragraph into `en` / `es` / `nl` for the map detail panel only. FR remains
  the canonical source — every cache entry carries `source_summary`,
  `source_summary_sha`, `source_pdf_filename`, `source_pdf_url`, `translator`
  (model id), `translator_kind` (e.g. `anthropic-api` or `manual`), and
  `fetched_at`. The UI must render an attribution line ("Machine translated
  from the cahier des charges", linked to `source_pdf_url`) wherever a
  translation appears, in lieu of the `(français)` marker. When the FR
  summary changes (`source_summary_sha` mismatch), stage 02c re-translates;
  forks running the pipeline without API access can use the round-trip flow:
  `--emit-todo todo.json` dumps every untranslated FR summary into a single
  JSON (all locales keyed at the top, or single-locale via `--lang`); after
  hand or third-party translation, `--import todo.json --translator-id <id>`
  writes the cache entries with `translator_kind=manual` (or whatever
  `--translator-kind` you supply, e.g. `deepl-api`). Other per-AOC content
  (appellation names, region names, commune lists, grape variety names,
  INAO category strings) is **not** machine-translated — it stays French.
  **The summary is a fallback, off by default.** Stages 02c (translate),
  03 (wiki `## Summary` section) and 04 (map panel) produce / translate /
  render it only for records that have **no** extracted terroir facts
  (02d) — a record with facts shows the facts and no summary. In a corpus
  with broad 02d coverage 02c therefore translates only the residual
  no-facts records.
- **Terroir-fact extraction is a bounded narrative layer (dual-source).**
  Stage 02d (`scripts/02d_extract_terroir_facts.py`) extracts a short
  bullet list of noteworthy facts per AOC from the cahier section X
  ("Lien au terroir"), grounded in TWO sources: the cahier (regulator
  authority) and the per-AOC Wikipedia page from 02b/aocs (sommelier-
  aligned vocabulary). Each bullet returns both `cahier_quote` and
  `wiki_quote` (either may be empty); a fuzzy-coverage filter (≥ 0.6
  longest-contiguous-match against the respective source) keeps the
  bullet if at least one quote grounds. Per-bullet `provenance` is one
  of `both` / `cahier` / `wiki`. The UI renders "via Wikipedia · CC
  BY-SA 4.0" beside `wiki`-only bullets; `both` and `cahier` default to
  the footer attribution linking to the cahier PDF. Cache invalidates
  per AOC when EITHER `cahier_source_sha` OR `wiki_source_revision`
  changes. Providers: `anthropic` / `ollama` / `manual`. The manual
  round-trip mirrors 02c (`--emit-todo` + `--import`). Stage 02e
  (`scripts/02e_translate_terroir_facts.py`) translates FR bullets into
  `en` / `es` / `nl` (same provider trio + round-trip), with cache
  invalidation keyed on `source_facts_sha` (sha256 of the FR bullet
  list joined). DGCs inherit the parent appellation's bullets at the
  rendering layer; stage 02d skips them. Both stages support
  `--workers N` for concurrent processing (Ollama needs
  `OLLAMA_NUM_PARALLEL >= N`; Anthropic respects account limits).
  `scripts/audit_terroir_facts.py` recomputes coverage against the
  current sources and flags drift / erosion.

## Denomination model (sub-denominations)

The unit of generation is the **denomination** (`id_denomination_geo` in the
SIQO referentiel), not the appellation. Most appellations have a single
denomination — their own name — but some carry several. Two distinct
regulatory concepts share the same data shape here, and the codebase
treats them uniformly via the `is_sub_denomination` flag:

- **AOC DGCs (Dénominations Géographiques Complémentaires)** — strictly an
  AOC/AOP concept. *Muscadet Sèvre et Maine* (id_appellation=100) has 7
  DGCs: Clisson, Gorges, Le Pallet, Château-Thébaud, Goulaine, Monnières-
  Saint-Fiacre, Mouzillon-Tillières. *Côtes du Rhône Villages*, *Coteaux
  du Layon*, *Alsace grand cru*, *Côtes du Roussillon Villages* and
  others follow the same pattern.
- **IGP sub-denominations** — *not* DGCs in regulatory terms (IGPs have no
  DGCs). *IGP Val de Loire* carries department-keyed sub-denominations
  (Indre-et-Loire, Maine-et-Loire, Sarthe, Vendée, Vienne, Allier, …);
  several other IGPs do similar. In SIQO they appear as distinct
  `id_denomination_geo` rows under one `id_appellation`, identical in
  structure to AOC DGCs, so we lump them together internally.

Stage 02 emits one JSON per (id_appellation, id_denomination_geo) pair. The
parent denomination (where `denomination == appellation`) gets the canonical
slug; each sub-denomination gets `slug(denomination)` and carries
`is_sub_denomination=true` plus `parent_id_appellation`, `parent_slug`,
`parent_name`. Sub-denominations share the parent's cahier text — INAO
publishes one cahier des charges per appellation, and sub-sections inside
it are not parsed in v1, so sub-denomination records inherit `sections` /
`aire` / `grapes` / `styles` from the parent.

Stage 04 resolves sub-denomination geometry by `id_denomination_geo`
against the INAO parcellaire shapefile (the shapefile carries `id_denom`
on every parcel row); when a sub-denomination has no parcellaire row
(~150 of ~1080 SIQO denominations) it falls back to the parent
appellation's polygon, so the sub-denomination is still on the map and
findable. Sub-denominations ride the same `appellations` MVT layer —
they're filterable through the existing region/style/grape facets like
any other appellation.

## Manual override mechanism

INAO's product page links one BO Agri PDF per AOC, often the latest
*modification arrêté* — which may not contain that AOC's cahier text
(e.g. the Montrachet grand-cru cluster). When the audit
(`scripts/audit_coverage.py`) flags a stub for an AOC whose cahier you
can find by hand on the BO Agri search UI
(`https://info.agriculture.gouv.fr/gedei/site/bo-agri/recherche`), drop
the URL into `raw/inao/cahiers/manual_overrides.json` (gitignored
alongside the rest of `raw/`) keyed by `id_appellation`:

```json
{
  "130": {
    "name": "Bâtard-Montrachet",
    "boagri_urls": [
      "https://info.agriculture.gouv.fr/.../document_administratif-<UUID>/telechargement"
    ],
    "note": "BO n°XX du JJ mois AAAA, p. NNNN"
  }
}
```

A starter template lives at `scripts/manual_overrides.example.json`.
Stage 01 reads the file (no-op when missing), downloads the override
PDFs into the cahiers directory, and points the manifest at the first
override URL. Stage 02's cross-bundle rescue then matches the cahier
header by name across the corpus, so overrides automatically promote
matching stubs to full extracts. Re-run stages 01 → 04 after edits.

## Cadastre lieux-dits (sub-commune climat geometry)

Cadastre Etalab (`cadastre.data.gouv.fr`, Licence Ouverte 2.0) publishes
per-commune GeoJSON of named cadastral parcels (lieux-dits). For DGCs
that sit as named lieux-dits inside the parent appellation's communes
but have no INAO parcellaire row — Chablis premier-cru climats
(Vaillons, Beugnons, Berdiot, …), Givry premier cru, Santenay premier
cru — stage 00 fetches one `cadastre-<INSEE>-lieux_dits.json.gz` per
parent-appellation commune (URL pattern
`https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson/communes/<DD>/<INSEE>/cadastre-<INSEE>-lieux_dits.json.gz`)
into `raw/cadastre/lieux-dits/<INSEE>.json.gz`. The parent allowlist
is `CADASTRE_PARENTS` in [scripts/00_fetch_data.py](scripts/00_fetch_data.py).

Stage 04 inserts a `cadastre-lieu-dit-dgc` step in the DGC geometry
chain, between the village-INSEE override and the aires-CSV fallback.
[scripts/_lib/lieu_dit.py](scripts/_lib/lieu_dit.py) normalises both
sides (strip diacritics + leading articles), exact-matches first, then
falls through to substring + Levenshtein at threshold 0.85; ties at
the top score get unioned (a climat split across two cadastral
polygons reassembles correctly). The map panel renders attribution
"Aire issue du lieu-dit cadastral « LES VAILLONS » (commune de Chablis,
cadastre.data.gouv.fr)" alongside the polygon.

Curators can pin a DGC to specific lieu-dit names via
[scripts/_lib/cadastre_lieu_dit_overrides.json](scripts/_lib/cadastre_lieu_dit_overrides.json),
keyed by `id_denomination_geo` → `{commune_insee, lieu_dit_names: [...]}`.
Run [scripts/audit_climats.py](scripts/audit_climats.py) after rerunning
stage 04 to surface accept / review / reject buckets per cluster DGC.

## Page format (per-AOC pages)

```
---
title: <Appellation name>
type: aoc | aop | igp
region: <bassin>
slug: <kebab-case>
sources:
  - cahier: raw/inao/cahiers/<id>.pdf
  - jorf: <arrêté reference if extracted>
last_updated: <ISO date>
---

# <Appellation name>

## Summary
<1–3 sentences derived from cahier section I + III>

## Aire géographique
<commune list, grouped by département>

## Cépages
<principal / accessory, with thresholds>

## Styles & couleurs
<from section III>

## Rendements
<from sections VI–IX>

## Lien au terroir
<verbatim section X>

## Sources
<JORF + cahier filename>
```

Wiki-link syntax `[[grape-slug]]` and `[[region-slug]]` is resolved by the
generator against `wiki/_index.json`.

## Scripts contract

Each script is independently re-runnable and writes a manifest. Running stage N
twice with no changes upstream must be a no-op (cache hits).

| Script | Reads | Writes |
|---|---|---|
| 00_fetch_data.py | (network) | raw/inao/siqo-referentiel.csv, raw/ign/communes.geojson, raw/inao/parcellaire/*.shp, raw/cadastre/lieux-dits/*.json.gz |
| 01_scrape_cahiers.py | raw/inao/siqo-referentiel.csv | raw/inao/cahiers/*.pdf, raw/inao/cahiers/manifest.json |
| 02_extract_cahiers.py | raw/inao/cahiers/*.pdf | raw/inao/cahier-extracted/*.json + _index.json |
| 02b_fetch_grape_lexicon.py | raw/inao/cahier-extracted/*.json + raw/vivc/by-slug/ | raw/wikipedia/grapes/<lang>/*.json + manifest.json |
| 02b_fetch_aoc_lexicon.py | raw/inao/cahier-extracted/*.json | raw/wikipedia/aocs/fr/*.json + manifest.json |
| 02b_fetch_style_lexicon.py | raw/wikipedia/style_overrides.json | raw/wikipedia/styles/<lang>/*.json + manifest.json |
| 02b_translate_styles.py | raw/wikipedia/styles/<lang>/*.json | raw/translations/styles/<lang>/*.json + manifest.json |
| 02b_translate_grapes.py | raw/wikipedia/grapes/<lang>/*.json + grape-corpus dominant-lang | raw/translations/grapes/<lang>/*.json + manifest.json |
| 02c_translate_summaries.py | raw/inao/cahier-extracted/*.json | raw/translations/summaries/<lang>/*.json |
| 02d_extract_terroir_facts.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/aocs/fr/ | raw/terroir-facts/*.json + manifest.json |
| 02e_translate_terroir_facts.py | raw/terroir-facts/*.json | raw/translations/terroir-facts/<lang>/*.json |
| 02g_fetch_vivc.py | raw/inao/cahier-extracted/*.json + raw/es/pliegos-extracted/ + raw/pt/cadernos-extracted/ + raw/vivc/slug_overrides.json | raw/vivc/{search,passport,by-slug}/*.html\|json + manifest.json + slug_overrides.example.json |
| 03_generate_wiki.py | raw/inao/cahier-extracted/*.json + raw/terroir-facts/ | wiki/*.md, wiki/_index.json |
| 04_build_maps.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/grapes/ + raw/translations/grapes/ + raw/vivc/by-slug/ + raw/wikipedia/styles/ + raw/translations/styles/ + raw/wikipedia/aocs/ + raw/translations/summaries/ + raw/translations/terroir-facts/ + raw/terroir-facts/ + raw/ign/communes.geojson + raw/inao/parcellaire/ + raw/cadastre/lieux-dits/ | wiki/index.html (EN canonical = homepage), wiki/{fr,es,nl}/index.html, wiki/map-data/*.pmtiles, wiki/robots.txt, wiki/sitemap.xml (homepage × 4 locales) |

## Spain pipeline (`scripts/es/`)

The Spanish pipeline mirrors the French one numerically (00, 01, 02, …) but
the data sources differ enough that the scripts are siblings, not
parameterisations. Common helpers live in `scripts/_lib/`; ES-specific
helpers under `scripts/_lib/es/` (added as needed).

Spine: **eAmbrosia EU register**
(`https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`).
Filter `country=ES` + `productType=WINE` + `status=registered` →
~149 wine GIs (106 DOP + 43 IGP). The corpus is *much* smaller than
the FR ~390 AOCs — Spanish IGPs (Vinos de la Tierra) often have no
EU-OJ amendment publications.

Pliego source: **EUR-Lex single-document HTML**, *not* a PDF.
eAmbrosia's `singleDocument` field is null for every ES wine (verified
2026-05). The canonical pliego is the EU-OJ "documento único"
published inline as HTML and reachable via each GI's
`publications[0].uri` (after Spanish-language URL rewrite — `/oj/spa`,
or `legal-content/ES/TXT/HTML/?uri=…SPA`). Both the older
`ti-grseq-1` (sections 1–9) and newer `oj-ti-grseq-1` (sections 1–10)
templates are parsed; semantic role routing by Spanish title keyword
(`zona geográfica`, `vínculo`, `variedad`) keeps downstream consumers
indifferent to which template a given page used. Section 9 (older)
or 6 (newer) frequently carries the **full subzona-grouped commune
list** (Rioja Alta / Alavesa / Oriental + commune names), so subzona
extraction is achievable from this single source — no separate full-
pliego fetch needed.

WAF caveat: EUR-Lex (CloudFront) returns HTTP 202 + an AWS WAF
JavaScript challenge for high-volume non-browser clients. Stage 01
handles ~24 % of wines on first run before the IP gets sticky-
flagged. The bootstrap script `scripts/es/01b_solve_waf.py` uses
headless Chromium (Playwright, in the `bootstrap` dependency-group)
to navigate the remaining URLs — Chromium runs the JS challenge
automatically. After 01b populates `raw/es/oj-pages/`, the rest of
the pipeline never touches Playwright.

| Script | Reads | Writes |
|---|---|---|
| es/00_fetch_data.py | (network: eAmbrosia + Figshare + GISCO + curated SIGPAC comarques) | raw/es/eambrosia/, raw/es/figshare/, raw/es/gisco/, raw/es/sigpac/ |
| es/01_fetch_pliegos.py | raw/es/eambrosia/index.json + raw/es/oj-pages/manual_overrides.json | raw/es/oj-pages/*.html (ES single-document HTMLs) + manifest.json |
| es/01b_solve_waf.py | raw/es/oj-pages/manifest.json | raw/es/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| es/02_extract_pliegos.py | raw/es/oj-pages/*.html | raw/es/pliegos-extracted/*.json + _index.json (parents + DGC subzonas) |
| es/02f_extract_national_pliegos.py | raw/es/pliegos-extracted/*.json + national-pliego PDF URLs from section 9 | raw/es/national-pliegos/*.pdf + raw/es/national-pliegos-extracted/*.json (variety augmentation) |
| es/03_generate_wiki.py | raw/es/pliegos-extracted/*.json | wiki/<slug>.md (per ES record) + merges ES entries into wiki/_index.json |
| es/regen_manual_overrides_template.py | raw/es/eambrosia/index.json + raw/es/oj-pages/manifest.json | raw/es/oj-pages/manual_overrides.json (curator queue, preserves filled-in URLs) |

ES-specific notes:
- `kind` is `"DOP"` / `"IGP"` (Spanish convention), not `"AOC"`.
- ~44 % of wine GIs have no `publications` URL in eAmbrosia (mostly
  pre-2014 IGPs and a handful of newer DOPs). They're emitted as
  stubs (`stub_reason: "no-publication"`) — the same stub mechanism
  the FR side uses for unparsed cahiers, with a curator workflow
  documented below.
- The shared `scripts/02b_fetch_aoc_lexicon.py` is generalised:
  invoke as `--lang es --source raw/es/pliegos-extracted/` to fetch
  per-DOP es.wikipedia.org pages (cascades through `(vino)` → `(DOP)`
  → `(denominación de origen)`).

### National-pliego variety augmentation (stage 02f)

The EU-OJ documento único's section 7 lists only the **principal**
varieties; secondary/accessory varieties live exclusively in the
**national pliego de condiciones** PDF linked from section 9 of the
documento único. Méntrida is the canonical example: doc-único shows
just *Garnacha Tinta*, while the JCCM national pliego section 6 lists
17 varieties (Tempranillo, Cabernet Sauvignon, Garnacha Blanca, …).

Stage 02f fetches each section-9 PDF URL, runs a generic Spanish-
pliego parser ([scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py))
on `pdftotext -layout` output, and writes one sidecar JSON per record
under `raw/es/national-pliegos-extracted/`. The parser handles the
heading variants seen across JCCM, INCAVI, AGACAL, ITACyL, Aragón,
Navarra, GVA, Canarias, Andalucía, Euskadi, Madrid, Extremadura, MAPA
(numbered or letter-prefixed sections, "Variedades de uvas de
vinificación" / "Variedad o variedades de uva" / "Variedades de Vitis
Vinifera" / "Variedades viníferas" / colour-bullet vs bullet-list vs
two-column layouts). Sidecars carry full provenance (source URL,
sha256, fetched_at, parser_template).

Stage 04 merges the sidecar's `new_slugs` into each ES record's
`grapes.accessory` at load time
(`augment_es_records_with_national_pliegos` in
[scripts/04_build_maps.py](scripts/04_build_maps.py)); the
augmentation is in-memory only (the on-disk doc-único record stays
immutable) and propagates via a slug-keyed cache into
`_sources_for()`. The map panel renders a "Pliego de condiciones
(national, PDF)" source link with the count of pliego-added varieties.

Re-runnable per slug or in sweep mode:
```
uv run scripts/es/02f_extract_national_pliegos.py --slug mentrida
uv run scripts/es/02f_extract_national_pliegos.py --all
```
Cached PDFs at `raw/es/national-pliegos/<slug>.pdf` are reused unless
`--refresh` is passed.

When the doc-único's section-9 URL is dead (404, GVA backend timeout,
BOE-modification-not-pliego, pdftotext-broken PDF), the curator pins a
working replacement in `raw/es/national-pliegos/manual_overrides.json`
(slug-keyed: `{pliego_url, source_org, verification_note}`). Stage 02f
checks this file before the section-9 URL and takes precedence; when an
override is present the slug-keyed PDF cache is invalidated automatically
if the existing sidecar's `source.url` disagrees with the override
(or if no sidecar exists at all, since the cache vintage is unknown).
Mirrors the FR pattern at `raw/inao/cahiers/manual_overrides.json`.

### ES geometry resolution chain (stage 04)

Per ES record, in priority order (each step records the chosen source
in `geom_source` so the panel can attribute correctly):

1. **`sigpac-pliego-inclusions`** — for wines whose pliego enumerates
   SIGPAC polygon inclusions inside one or more municipios (Priorat ↔
   Montsant: `Falset: polígonos números 1, 4, 5, 6, 7, 21 y 25 enteros`).
   Resolved by `scripts/_lib/es/pliego_parcels.py` + `scripts/_lib/es/sigpac.py`
   against per-comarca SIGPAC vineyard parcels (currently only the
   Priorat comarca is downloaded; add more by editing
   `SIGPAC_COMARCA_CODIS` in `scripts/es/00_fetch_data.py`). This
   path eliminates the commune-precision overlap that Figshare 2022
   produces for shared communes.
2. **`figshare-pdo`** — exact `file_number` → `PDOid` match against
   Bétard 2022 EU_PDO.gpkg (CC0). Covers ~99 of the 106 ES PDOs
   (all pre-Nov-2021 PDOs).
3. **`gisco-province-wide`** — IGP-fallback A: pliego says "todos los
   términos municipales de las provincias de X y Y". Union all GISCO
   municipios in those provinces.
4. **`gisco-ccaa-wide`** — IGP-fallback B: pliego says "todos los
   términos municipales del territorio de [CCAA]". Union all GISCO
   municipios in the CCAA's provinces.
5. **`gisco-commune-list`** — IGP-fallback C: pliego enumerates a flat
   commune list. Union the matching GISCO municipios.
6. **`gisco-commune-union-subzona`** — for ES subzona DGCs, union
   the per-subzona commune list.
7. **`parent-appellation`** — DGC inherits parent polygon when
   commune matching yields nothing.
8. **`stub-no-geometry`** — wine appears in the AOCS sidebar but no
   polygon (most pre-2014 IGPs).

### Curator workflow for ES wines without an OJ publication

When eAmbrosia has no `publications` URL for a wine (the dominant
cause of `stub-no-geometry`), the wine appears in the curation queue
written by `scripts/es/regen_manual_overrides_template.py` to
`raw/es/oj-pages/manual_overrides.json`. The file is gitignored.

Workflow:

```
uv run scripts/es/regen_manual_overrides_template.py
# → writes raw/es/oj-pages/manual_overrides.json with one entry per
#   wine that needs a URL, preserving any existing curator inputs.
uv run scripts/audit_es_coverage.py
# → prints the curation queue at the bottom of the report.
# Edit raw/es/oj-pages/manual_overrides.json: for each high-priority
# entry, find a public, licence-clear pliego URL (BOE PDF, EUR-Lex
# OJ page, regional gazette HTML, consejo regulador site) and put
# it in the `url` field. Add a `note` if the source is unusual.
uv run scripts/es/01_fetch_pliegos.py
# → re-fetches with the curator URLs taking precedence.
uv run scripts/es/02_extract_pliegos.py
uv run scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML parser currently only understands the
EU-OJ "documento único" template. BOE PDFs / regional-gazette
formats won't yield a polygon yet — they need per-source parsers.
Curator effort still produces value though: the wine moves out of
the stub bucket, sources become traceable, and the audit shows
real provenance instead of "no URL anywhere".

## Portugal pipeline (`scripts/pt/`)

Country #3. Structurally simpler than ES: the **IVV (Instituto da
Vinha e do Vinho)** publishes every PT DOP/IGP caderno de
especificações as a stable PDF directly from its master index pages,
so no AWS WAF, no Playwright bootstrap. ~44 wine GIs (30 DOP + 14
IGP) — about a third the size of ES.

Spine: **eAmbrosia + IVV cadernos master indexes**. eAmbrosia
(filtered to `country=PT + productType=WINE + status=registered`)
provides the wine list with `fileNumber` (`PDO-PT-Axxxx` /
`PGI-PT-Axxxx`), kind, producer group, and publication-URL
provenance. IVV's HTML pages at `/np4/8617.html` (DOP) and
`/np4/8616.html` (IGP) enumerate the actual caderno PDFs behind the
NP4 templating literal `{$clientServletPath}` (URL-encoded
`%7B%24clientServletPath%7D` — resolves server-side). Names match
1:1 between eAmbrosia and IVV with the normaliser in
[scripts/_lib/pt/name_match.py](scripts/_lib/pt/name_match.py).

Caderno structure: PT cadernos come in three variants — "Roman +
Arabic" (Douro, Alentejo, Madeira, Porto — sections I..VI with V.
DOCUMENTO ÚNICO carrying numbered subsections 1–9 inside), "Arabic
only / documento único first" (Vinho Verde, Pico — sections 1–9
directly), and "Arabic short / older format" (Dão — sections 1–9
without the DOCUMENTO ÚNICO wrapper).
[scripts/_lib/pt/caderno_sections.py](scripts/_lib/pt/caderno_sections.py)
finds section bodies by Portuguese keyword anchors (`área
delimitada` / `zona geográfica demarcada`, `relação com a área
geográfica`, `castas` / `uvas de vinho`, `rendimentos máximos`,
etc.) and carves up the text between them — independent of the
variant.

Sub-regiões (the FR DGC / ES subzona analogue) are detected by
[scripts/_lib/pt/subregiao.py](scripts/_lib/pt/subregiao.py) with
two patterns: **Pattern A** (`Sub-região NAME`) covers Vinho Verde
+ Alentejo + variants; **Pattern B** (Douro-style `NAME: no
distrito de X` colon-prefix with a `três áreas geográficas` /
`área das sub-regiões` preamble) covers Douro/Porto + Trás-os-
Montes. Wines without a matched pattern emit parent-only — those
sub-regiões exist in regulatory documents but aren't in the caderno
text. Sub-região records carry `is_sub_denomination=true`,
`parent_slug`, `parent_id_eambrosia`, `parent_name` (same data
model as FR DGCs and ES subzonas) and share the parent's
`file_number` / sections / grapes (parent inherited at the
rendering layer).

| Script | Reads | Writes |
|---|---|---|
| pt/00_fetch_data.py | (network) | raw/pt/eambrosia/index.json, raw/pt/ivv/cadernos-index.json, raw/pt/caop/CAOP_{Continente,RAA,RAM}_2025.gpkg |
| pt/01_fetch_cadernos.py | raw/pt/eambrosia/index.json + raw/pt/ivv/cadernos-index.json + raw/pt/ivv/cadernos/manual_overrides.json | raw/pt/ivv/cadernos/*.pdf + manifest.json |
| pt/02_extract_cadernos.py | raw/pt/ivv/cadernos/*.pdf | raw/pt/cadernos-extracted/*.json + _index.json (parents + sub-regiões + stubs) |
| pt/02d_extract_terroir_facts.py | raw/pt/cadernos-extracted/*.json + raw/wikipedia/aocs/pt/ | raw/terroir-facts/*.json (country="pt") + manifest-pt.json |
| pt/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="pt") | raw/translations/terroir-facts/<en|fr|es|nl>/*.json |
| pt/03_generate_wiki.py | raw/pt/cadernos-extracted/*.json | wiki/<slug>.md (per PT record) + merges PT entries into wiki/_index.json |
| pt/regen_manual_overrides_template.py | raw/pt/eambrosia/index.json + raw/pt/ivv/cadernos/manifest.json | raw/pt/ivv/cadernos/manual_overrides.json (curator queue, preserves filled-in URLs) |

PT-specific notes:
- `kind` is `"DOP"` / `"IGP"` (Portuguese convention, same as ES).
- The shared stages 02b/02c are extended to PT: grape lexicon
  (`02b_fetch_grape_lexicon.py`) iterates `raw/pt/cadernos-extracted/`;
  AOC lexicon (`02b_fetch_aoc_lexicon.py`) supports `--lang pt`;
  translation summaries (`02c_translate_summaries.py`) supports
  `--source-lang pt` with target locales `en/fr/es/nl`.
- Terroir-fact extraction (02d/02e) is wired for PT via
  `scripts/pt/02d_extract_terroir_facts.py` +
  `scripts/pt/02e_translate_terroir_facts.py` (siblings of the ES
  pair). Same dual-source grounding (caderno section 7 +
  pt.wikipedia.org per-DOP page), same fuzzy-coverage filter (≥ 0.6),
  same per-bullet provenance (`cahier` / `wiki` / `both`), same
  manual round-trip flow. PT 02e targets en/fr/es/nl (FR + ES are
  translation targets, not sources). Cache files land in the shared
  `raw/terroir-facts/` directory with `country: "pt"` to distinguish
  them from FR/ES records. Sub-regiões are skipped — they inherit
  the parent's bullets at the rendering layer.

### PT grape role classification — not published by the regulator

The IVV documento-único caderno enumerates every authorised casta
in a single block, without a principal-vs-acessória split. An
investigation (2026-05-18, see [CURATOR_TODO.md](CURATOR_TODO.md))
audited 33 curator-pinned national-regulamento PDFs from dre.pt and
found **zero** of them carry a structured role split: most are
amendment Portarias, recognition decrees, or PRT-tabular castas
annexes without role markers. The role distinction simply isn't
published at the PT regulator level for the wines in the corpus.
The map detail panel therefore renders every PT grape as
`principal`, with an inline disclaimer noting the limitation, and
the stage-02f pipeline that previously attempted to recover roles
has been removed.

### PT geometry resolution chain (stage 04)

Per PT record, in priority order (each step records the chosen
source in `geom_source` so the panel can attribute correctly):

1. **`stub-no-geometry`** — stubs (no caderno) short-circuit.
2. **`parent-appellation`** — sub-regiões inherit the parent's
   polygon. Honest attribution: precision is parent-level, not
   sub-região-level. v2 follow-up will refine via CAOP município
   commune lists when the caderno enumerates them per-sub-região.
3. **`figshare-pdo`** — exact `file_number` (`PDO-PT-Axxxx`) →
   `PDOid` match against Bétard 2022 EU_PDO.gpkg (reuses
   `raw/es/figshare/EU_PDO.gpkg`; the dataset covers all EU PDOs).
   Hit rate: 30 / 30 PT DOPs.
4. **`none`** — the 14 PT IGPs (which Bétard 2022 doesn't carry
   by design — it's PDO-only) appear in the sidebar with no
   polygon in v1. Helper [scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py)
   exposes `PTPolygonIndex.union_concelhos` against DGT CAOP 2025
   for the future IGP commune-list parser.

Bétard 2022 + CAOP 2025 are CC-licensed and re-distributable with
attribution. CAOP 2025 (Continente + RAA + RAM) is fetched once in
stage 00 and cached at `raw/pt/caop/`. Re-runnable: stage 04 reads
the cached gpkg on every run.

### Curator workflow for PT wines without an IVV match

Mirrors the ES `regen_manual_overrides_template.py` flow. After a
stage 01 run that left `no-caderno` rows in the manifest:

```
.venv/bin/python scripts/pt/regen_manual_overrides_template.py
# writes raw/pt/ivv/cadernos/manual_overrides.json with one entry
# per wine that needs a URL. Edit, fill the `pdf_url` field with a
# public, licence-clear caderno PDF (alternate IVV path, BOE-style
# national gazette PDF, consejo regulador site).
.venv/bin/python scripts/pt/01_fetch_cadernos.py
.venv/bin/python scripts/pt/02_extract_cadernos.py
.venv/bin/python scripts/04_build_maps.py
```

In practice the first-run IVV scrape matches 44 / 44 wines, so the
overrides file is empty by default.

## Italy pipeline (`scripts/it/`)

Country #4. Largest EU wine producer; 531 wine GIs (412 DOP + 119 IGP)
sourced from eAmbrosia. Structurally closest to the ES pipeline — same
EU-OJ documento-unico HTML template (just Italian instead of Spanish),
same Bétard 2022 Figshare gpkg for DOP polygons, same Eurostat GISCO
LAU for comune unions. Both upstream artifacts are reused from the
already-cached ES paths (`raw/es/figshare/EU_PDO.gpkg`,
`raw/es/gisco/lau-eu-2024-01m.shp.zip`) — no re-fetch in IT stage 00.

Spine: **eAmbrosia EU register**, filtered to `country=IT +
productType=WINE + status=registered`. Of the 531 IT wines:

- **139** have at least one EUR-Lex publication URL → stage 01 (EUR-Lex
  fetch) succeeds for ~130 of these after the 01b WAF bootstrap.
- **62** have only Commission-internal `Ares(YYYY)NNNNNN` references
  with numeric URIs (not directly fetchable from the public web).
  Stub status until a curator URL is supplied via
  `raw/it/oj-pages/manual_overrides.json`.
- **330** have no publications at all. Same curator-queue path.

So ~74 % of IT wines (vs 44 % for ES) need the curator path or stage
02f-MASAF overlay. The architecture supports both via the
manual_overrides flow.

| Script | Reads | Writes |
|---|---|---|
| it/00_fetch_data.py | (network: eAmbrosia + MASAF disciplinari bundles) | raw/it/eambrosia/ + raw/it/masaf-disciplinari/bundles/*.7z + manifest.json |
| it/01_fetch_pliegos.py | raw/it/eambrosia/index.json + raw/it/oj-pages/manual_overrides.json | raw/it/oj-pages/*.html + manifest.json |
| it/01b_solve_waf.py | raw/it/oj-pages/manifest.json | raw/it/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| it/02_extract_pliegos.py | raw/it/oj-pages/*.html | raw/it/disciplinari-extracted/*.json + _index.json + raw/it/extraction-unknowns.json |
| it/02f_extract_masaf.py | raw/it/disciplinari-extracted/*.json + raw/it/masaf-disciplinari/bundles/*.7z + raw/it/masaf-disciplinari/manual_overrides.json | raw/it/masaf-disciplinari/pdfs/*.pdf + raw/it/masaf-disciplinari-extracted/*.json + raw/it/extraction-unknowns-masaf.json |
| it/03_generate_wiki.py | raw/it/disciplinari-extracted/*.json | wiki/<slug>.md (per IT record) + merges IT entries into wiki/_index.json |
| audit_it_coverage.py | raw/it/eambrosia/ + raw/it/disciplinari-extracted/ + raw/it/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |
| it/02d_extract_terroir_facts.py | raw/it/disciplinari-extracted/*.json + raw/it/masaf-disciplinari-extracted/*.json + raw/wikipedia/aocs/it/ | raw/terroir-facts/*.json (country="it") + manifest-it.json |
| it/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="it") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |

IT-specific notes:
- `kind` is `"DOP"` / `"IGP"` (Italian convention, same as ES/PT).
- The shared `scripts/02b_fetch_aoc_lexicon.py` accepts `--lang it` and
  cascades through `(vino)` → `(DOCG)` → `(DOC)` →
  `(denominazione di origine)`.
- The shared `scripts/02c_translate_summaries.py` accepts
  `--source-lang it` with target locales `en/fr/es/nl`.
- The shared `scripts/02g_fetch_vivc.py` and
  `scripts/_lib/grape_corpus.py` walk
  `raw/it/disciplinari-extracted/` alongside the FR / ES / PT corpora.
  Italian local-name aliasing (Sangiovese ↔ Brunello / Prugnolo Gentile,
  Nebbiolo ↔ Chiavennasca, Vermentino ↔ Pigato, Trebbiano cluster)
  flows through VIVC's synonym index. Ambiguous slugs pinned via
  `raw/vivc/slug_overrides.json` as the audit surfaces them.
- Grape role classification is not split in the EUR-Lex documento
  unico for most Italian DOPs — section 7 lists varieties without
  principal/accessory markers. Stage 02 defaults all matches to
  `principal`. Full role splits live in the national disciplinare
  allegato (Gazzetta Ufficiale PDFs), which is stage-02f territory
  (deferred; mirrors the ES MAPA / PT Portaria pattern).
- Terroir-fact extraction (02d/02e) is wired for IT via
  `scripts/it/02d_extract_terroir_facts.py` +
  `scripts/it/02e_translate_terroir_facts.py` (siblings of the ES/PT
  pairs). Same dual-source grounding (documento-unico / MASAF
  disciplinare section 8–9 + it.wikipedia.org per-DOP page), same
  fuzzy-coverage filter (≥ 0.6), same per-bullet provenance
  (`cahier` / `wiki` / `both`), same manual round-trip flow. IT 02d
  reads `link_to_terroir` directly from EUR-Lex extractions for the
  ~125 non-stub wines, and merges the MASAF sidecar's Article 9
  body in-memory for the ~385 MASAF-augmented stubs (mirrors stage
  04's `augment_it_records_with_masaf`), so both paths feed a single
  Italian-language extraction prompt. IT 02e targets en/fr/es/nl (FR
  + ES are translation targets, not sources). Cache files land in
  the shared `raw/terroir-facts/` directory with `country: "it"` to
  distinguish them from FR/ES/PT records. Sottozone are skipped —
  they inherit the parent's bullets at the rendering layer.

### Sottozone and Menzioni / Unità Geografiche Aggiuntive

Italy has two layers of sub-denomination granularity:

- **Sottozone** — strict regulatory sub-areas with their own
  production rules (Chianti's 7: Colli Aretini, Colli Fiorentini,
  Colli Senesi, Colline Pisane, Montalbano, Rufina, Montespertoli).
  Modelled as first-class sub-denomination records with
  `is_sub_denomination=true` + `parent_slug` + `parent_id_eambrosia`,
  same data shape as FR DGCs / ES subzonas / PT sub-regiões. Stage 02
  detects them via `scripts/_lib/it/sottozona.py` (two regex
  patterns: explicit `Sottozona NAME:` prefix and preamble-list
  `Le sottozone X, Y, Z e W`).
- **Menzioni / Unità Geografiche Aggiuntive** (MGA / UGA) — finer
  "cru" granularity (Chianti Classico's 11 UGAs, Barolo's 181 MGAs,
  Soave's 29 UGAs). Per 2024 wine-law reform, UGA is the new official
  term. **v1 scope** (with user): emit MGA/UGA as a flat
  `menzioni: []` chip list on parent panels only — no per-cru
  polygons, no per-cru records. Stage 02 harvests them via
  `scripts/_lib/it/menzione.py` (numbered-list and comma-list
  patterns inside the documento unico). The complete MGA list for
  Barolo / Barbaresco lives in the national disciplinare allegato
  and is stage-02f-MASAF territory.

### IT geometry resolution chain (stage 04)

Per IT record, in priority order (each step records the chosen
source in `geom_source` so the panel can attribute correctly):

1. **`parent-appellation`** — sottozone (sub-denominations) inherit
   the parent's polygon. Precision is parent-level, not
   sottozona-level.
2. **`figshare-pdo`** — exact `file_number` (`PDO-IT-A*` /
   `PGI-IT-A*`) → `PDOid` match against Bétard 2022 EU\_PDO.gpkg.
   Hit rate: 408 / 412 IT DOPs (~99 %). The 4 missing DOPs are
   newer 2024+ registrations not in the 2022 snapshot. **Figshare
   lookup runs even when the record is a stub** (no documento
   unico fetched) — the polygon doesn't depend on the documento
   unico, and most IT DOPs have valid eAmbrosia file numbers that
   match Bétard's PDOid. So well-known DOPs like Barolo, Brunello,
   Aglianico del Vulture appear on the map with their full
   polygon even though the documento unico isn't accessible.
3. **`stub-no-geometry`** — IGTs (Bétard is PDO-only by design) and
   the 4 newer DOPs that miss Bétard. They appear in the sidebar
   with no polygon (same status as ~14 PT IGPs). Future v2:
   commune-list union via GISCO LAU when the documento unico
   enumerates comuni.

### MASAF disciplinare fallback for no-publication wines (stage 02f)

MASAF (the Italian Ministry of Agriculture) publishes the
consolidated *disciplinare di produzione* for every wine DOP + IGT
as 4 7-Zip archives on
[IDPagina/4625](https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/4625)
("Disciplinari DOP A-D / E-N / O-Z" and "Disciplinari IGP"). Stage 00
downloads the 4 bundles (~100 MB total) into
[raw/it/masaf-disciplinari/bundles/](raw/it/masaf-disciplinari/bundles/);
stage 02f
([scripts/it/02f_extract_masaf.py](scripts/it/02f_extract_masaf.py))
augments IT STUB records (wines whose eAmbrosia entry lacks a
documento unico URL — ~395 of 531) by parsing those disciplinari.

Pipeline per stub:
1. Index every PDF inside the 4 archives (521 distinct filenames).
2. Match each eAmbrosia wine to one PDF via
   [scripts/_lib/it/masaf.py](scripts/_lib/it/masaf.py)
   `match_wines_to_pdfs` — exact-after-normalisation on alt-name slugs
   from "X o Y o Z" splits, then substring, then rapidfuzz token-ratio
   ≥ 90. One-to-one assignment (a PDF claimed by an earlier wine
   isn't a fuzzy candidate for later ones). Hit rate: 521 / 531 wines
   (98 %).
3. Extract the PDF on-demand from the archive into
   [raw/it/masaf-disciplinari/pdfs/<slug>.pdf](raw/it/masaf-disciplinari/pdfs/)
   and run `pdftotext -layout`.
4. Carve the layout-text into a `{article_num: body}` dict via
   `extract_articles` (anchor regex tolerates the form-feed page
   breaks pdftotext emits between articles), then parse:
   - **Article 1** → summary (first paragraph, ≤ 600 chars)
   - **Article 2** → grape varieties via `match_variety` on
     line/colon/comma-split candidates + `vitigno NAME` regex scan
   - **Article 3** → geo area / commune list
   - **Article 9** → link to terroir
5. Emit a sidecar JSON under
   [raw/it/masaf-disciplinari-extracted/<slug>.json](raw/it/masaf-disciplinari-extracted/)
   with full provenance (`bundle_key`, `archive_path`, sha256, match
   method).

Stage 04's `augment_it_records_with_masaf()` merges the sidecar into
the in-memory stub record at load time (summary / regione / grapes /
geo_area_brief / link_to_terroir / section_roles); the on-disk stub
JSON stays immutable. `_sources_for()` surfaces `masaf_*` provenance
fields so the panel can attribute the data and link to the archived
PDF. The record's `stub_reason` is prefixed `masaf:` so the audit
can tell doc-unico-extracted from MASAF-augmented wines.

The 10 wines without a bundle hit (mostly newer IGTs not yet in
MASAF's archives + a couple of DOPs whose PDF lives under a different
name) use the same `manual_overrides.json` flow as ES + PT:
```json
{
  "<slug>": {
    "pdf_url": "https://...",
    "source_org": "masaf|regione|consorzio|gazzetta",
    "verification_note": "..."
  }
}
```
at `raw/it/masaf-disciplinari/manual_overrides.json`. The override
URL takes precedence over the bundle match and re-fetches when the
sidecar's `source.url` disagrees.

Re-runnable per slug or sweep:
```
.venv/bin/python scripts/it/02f_extract_masaf.py --slug barolo
.venv/bin/python scripts/it/02f_extract_masaf.py --all
```
Unknown-variety candidates flow to
[raw/it/extraction-unknowns-masaf.json](raw/it/extraction-unknowns-masaf.json)
for vocab curation (Cesanese di Affile, regional Sardinian varieties,
etc. — the curator pattern adds them to `DEFAULT_COLOUR` /
`GRAPE_ALIAS` rather than the MASAF parser).

### Curator workflow for IT wines without an OJ publication

Mirrors the ES + PT `regen_manual_overrides_template.py` flow.
Wines in the `no-publication` bucket (~330) or `not-single-document`
bucket (~9) appear in the audit at the bottom. Per high-priority
wine, find a public, licence-clear pliego URL (MASAF detail-page
HTML, Gazzetta Ufficiale PDF, regional gazette) and put it in
`raw/it/oj-pages/manual_overrides.json` keyed by `slug` or
`giIdentifier`:

```json
{
  "barolo": {"url": "https://...documento-unico.html", "note": "MASAF detail page"}
}
```

Then re-run `scripts/it/01_fetch_pliegos.py` → `02_extract_pliegos.py`
→ `04_build_maps.py`. Caveat: stage 02's HTML parser only
understands the EU-OJ documento-unico template; MASAF detail pages
need a per-source parser (stage 02f-MASAF, deferred).

## Batch API (02c / 02d / 02e)

The three LLM stages — `02c` (summary translation), `02d` (terroir-fact
extraction) and `02e` (bullet translation), every country — accept a
`--batch` flag. With `--provider anthropic` or `--provider mistral` it
submits the whole eligible corpus to that provider's Batch API as one
job (~50 % cheaper than synchronous calls) instead of looping
`provider.chat()`.

Mechanics (`scripts/_lib/batch.py`): the stage's normal processing loop
runs twice — pass 1, a `CollectingProvider` records every prompt the
stage would send (returns `""`, so nothing is parsed or cached); the
batch is submitted and polled to completion; pass 2, a `ReplayProvider`
feeds the answers back in the same call order so the stage parses and
writes caches unchanged. The command blocks until the batch finishes;
the batch id is written to `raw/.batch/<stage>.json`, so an interrupted
run, re-run, **resumes** the in-flight batch instead of resubmitting
(and re-paying). Each request's `custom_id` is a hash of its prompt, so
`--batch` is **incremental** — it enumerates only the stale / missing
entries and never resubmits an already-processed one — and pass 2 matches
answers by content, not call order (runs are single-threaded all the
same).

Default models (`scripts/_lib/providers.py`): `claude-sonnet-4-6` for
anthropic, `mistral-medium-latest` for mistral — used by `--batch` and by
synchronous `--provider` runs alike; override per run with `--model`. API
keys are read from the environment or a repo-root `.env`. Anthropic
batches use the Messages Batches SDK; Mistral batches use a file-upload /
poll / download REST flow (no `mistralai` SDK dependency).

## Internationalisation

The map UI chrome (sidebar labels, panel headings, link texts, style chip
names) is translated into `fr` / `es` / `nl` via gettext (EN is the canonical
default). Stage 04 emits the map as the homepage: `wiki/index.html` (EN at
`/`) plus `wiki/<lang>/index.html` for `lang ∈ {fr, es, nl}` (served at
`/fr/`, `/es/`, `/nl/`). The map is the front door — there is no separate
`/map/` URL or homepage anymore. Pmtiles assets are referenced by absolute
path (`/map-data/...`) so they resolve correctly from any URL depth, and
`<link rel="alternate" hreflang>` tags between the four locale variants
surface them to crawlers (`x-default` points at `/`, the EN canonical).
FR is still the source language for gettext msgids (the cahier and the
extraction layer are FR-canonical); the translation flows just go FR → EN
for the canonical-rendered surface.

**UI chrome is translated via gettext; the cahier summary paragraph is
translated via stage 02c (machine translation with cahier-source attribution
preserved); terroir-fact bullets are translated via stage 02e (per-bullet
provenance preserved, dual-source attribution — see the bounded-narrative-
layer rule above).** All other per-AOC content shown in the detail panel —
appellation names, region names, commune lists, grape varieties, and INAO
category codes — stays in French because it is verbatim cahier data and
translating it would lose the public-source provenance. Bassin (region)
labels are an exception: their translations live in the gettext catalog
because the FR forms are well-known proper nouns with public, stable
translations.

Catalogs live under `locale/<lang>/LC_MESSAGES/messages.po` and are
hand-editable. The extraction surface is the whole of `scripts/_lib/` —
`map_template.py` carries `build_labels` and `build_style_labels`, and
`style_taxonomy.py` carries the style-taxonomy msgid anchors
(`_msgid_anchors_for_babel`) for every node in the slug tree. Always
extract from the directory, not a single file, or new msgids will be
silently dropped from `.pot` and pybabel update will mark them obsolete.
Stage 04 calls `scripts/_lib/i18n.py:compile_catalogs()` at the start of
each run; it rebuilds `messages.mo` only when the `.po` is newer (no-op
on rerun).

```
uv run pybabel extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/
uv run pybabel update -i locale/messages.pot -d locale     # after adding a new msgid
uv run pybabel init   -i locale/messages.pot -d locale -l <lang>   # to add a new locale
```

After editing a `.po`, just rerun `uv run scripts/04_build_maps.py`.

## Code style

- Python 3.12, ruff line length 100.
- Single-purpose scripts; share helpers via `scripts/_lib/`.
- No comments unless the *why* is non-obvious. Identifiers carry the *what*.
- Logs to stderr, structured progress (per-AOC) so reruns are debuggable.
