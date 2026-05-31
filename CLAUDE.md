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

## Geometry-outlier overrides

A resolved appellation polygon occasionally carries a part detached far
from the main body — either a mis-attributed fragment in the upstream
Bétard 2022 `EU_PDO.gpkg` (Garda DOP ships a 29 km² sliver of Piedmont
inside the *Piemonte* DOC; Valdadige and the four Barbera/Monferrato
DOCs swap Piedmont ↔ Trentino fragments the same way), or a same-name
commune-union collision in a resolver (PT *Lagoa* unioned both the
Algarve concelho and the Açores concelho — fixed in
[scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py) by distrito-
context disambiguation, the PT analogue of the ES province-context
two-pass).

[scripts/audit_geometry_outliers.py](scripts/audit_geometry_outliers.py)
streams `wiki/map-data/appellations.geojson` (country-agnostic; tens of
MB of RAM), flags every detached part (gap > 25 km from the main body,
< 20 % of total area), reports which other appellation each part sits
inside (the triage signal — a part inside an unrelated DOC is plainly
mis-attributed), and buckets each finding as **CONFIRMED** /
**PENDING-REBUILD** / **STALE** / **ACCEPTED** / **UNREVIEWED**.

Confirmed-spurious parts are recorded in
[scripts/_lib/geometry_outlier_overrides.json](scripts/_lib/geometry_outlier_overrides.json)
(checked in): a `clip` section per slug listing each spurious part by
3035-centroid + area + a public-source reason, and a `whitelist`
section for appellations whose detached parts are legitimate
(archipelagos — Madeira, Islas Canarias, Sicilia — multi-region DOs
— Cava — and law-extended outposts like Saale-Unstrut's Werderaner
Wachtelberg, a Brandenburg vineyard ~150 km NE of the main
Sachsen-Anhalt body, legally part of the Anbaugebiet per BLE
Produktspezifikation §11.3). Stage 04 ([scripts/_lib/geometry_overrides.py](scripts/_lib/geometry_overrides.py))
drops a clipped part only when the override matches **exactly one** part
of the resolved geometry; zero or several matches leaves the geometry
untouched and logs a loud `STALE` warning — an override that no longer
matches means the upstream data drifted (or was fixed) and must be
re-verified. The audit re-derives every override against the source
`EU_PDO.gpkg` on each run, so a working clip stays visible as
`CONFIRMED` and is never silently hidden. Re-run stages 04 → audit
after editing the override file.

## Geometry-overlap audit

Appellation polygons overlap by design — a regional appellation
contains its village appellations, a sub-denomination sits inside its
parent, and whole DOC families (Chianti / Chianti Classico, the
Abruzzo varietal DOCs) genuinely share ground. The *suspicious* case
is the opposite: two appellations that are otherwise side by side
sharing only a thin sliver — typically one commune thick — because a
border commune was assigned to both commune lists (or a same-name
collision, or imprecise source polygons). Appellations built from
disjoint commune lists should *tile*, not overlap with real 2-D area.

[scripts/audit_geometry_overlaps.py](scripts/audit_geometry_overlaps.py)
streams `wiki/map-data/appellations-villages.geojson` (commune-level —
the right granularity for a one-commune sliver), reprojects to
EPSG:3035, lightly simplifies, and computes every pairwise polygon
overlap. It skips hierarchy pairs (parent ⊃ sub-denomination; siblings
of one appellation) and classifies the rest by `share` = overlap area
/ appellation area: **NESTED** (one near-contains the other),
**PARTIAL** / **WIDE** (a genuinely large or wide mutual overlap) —
all normal — versus **SLIVER**: a small overlap (1–50 km², < 10 % of
*both* appellations) between otherwise-disjoint appellations. Slivers
are the suspicious bucket; cross-country slivers are listed first
(appellations of different countries should share no ground). One
appellation overlapping a parent and all its sub-denominations
collapses to a single finding.

Reviewed-legitimate pairs go in
[scripts/_lib/geometry_overlap_overrides.json](scripts/_lib/geometry_overlap_overrides.json)
(`whitelist` of slug pairs) and report as ACCEPTED. The audit is a
detector only — it changes no geometry; fixing a real artifact means
correcting the upstream commune list / resolver. Thresholds are
CLI-configurable (`--sliver-max`, `--max-sliver-km2`, …); `--strict`
exits non-zero on unreviewed slivers.

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
   `SIGPAC_COMARCA_CODIS` in `scripts/es/00_fetch_data.py`). Parcel
   precision — runs first, ahead of the official MAPA zone.
2. **`mapa-zone`** — official MAPA national wine production-zone
   polygon, matched by appellation name (`scripts/_lib/es/zones.py`,
   `ESZoneIndex`). MAPA publishes one national layer — "Zonas de
   Calidad Diferenciada: Vinos", 96 DOP-side figures — fetched in
   stage 00 from the OGC API-Features endpoint. ~90 of the 106 ES
   DOPs resolve here; the 16 misses are newer Vinos de Pago that
   post-date the layer. Licence: CC-BY 4.0 (MAPA IDE metadata),
   attribution © MAPA. A small `_NAME_ALIAS` bridges regional-language
   vs. Castilian name forms (Empordà / Ampurdán, Priorat / Priorato,
   the bilingual Txakoli names).
3. **`figshare-pdo`** — exact `file_number` → `PDOid` match against
   Bétard 2022 EU_PDO.gpkg (CC0) — fallback for the newer DOPs the
   MAPA layer predates.
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
3. **`caop-concelho-union`** — parse the caderno's "Área Delimitada"
   section ([scripts/_lib/pt/commune_list.py](scripts/_lib/pt/commune_list.py))
   for an enumerated concelho list, a whole-distrito declaration, a
   bullet-list of concelhos, a bare "Distrito de X." sentence, or a
   whole-archipelago phrase (Arquipélago dos Açores / Região
   Autónoma da Madeira); union the matching DGT CAOP 2025 município
   polygons via `PTPolygonIndex.union_from_parsed`. Threshold: at
   least 2 concelho matches or 1 distrito expansion. Município-level
   precision — finer than Bétard's whole-município padding for
   polygons that don't share district boundaries with neighbours.
   Hit rate: 23 / 30 PT DOPs + 14 / 14 PT IGPs.
4. **`figshare-pdo`** — exact `file_number` (`PDO-PT-Axxxx`) →
   `PDOid` match against Bétard 2022 EU_PDO.gpkg (reuses
   `raw/es/figshare/EU_PDO.gpkg`; the dataset covers all EU PDOs).
   Fallback for DOPs whose caderno area text is too sparse for the
   CAOP parser. Hit rate: 7 / 30 PT DOPs.

Macro-region tokens (`acores` / `madeira`) emitted by the parser
expand into the constituent ilhas via `PT_MACRO_REGIONS` in
[scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py) (Açores =
7 ilhas / 16 municipios; Madeira = 2 ilhas / 11 municipios).

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
| it/02_extract_pliegos.py | raw/it/oj-pages/*.html + raw/es/gisco/LAU_*.shp.zip (commune→regione index) | raw/it/disciplinari-extracted/*.json + _index.json + raw/it/extraction-unknowns.json |
| it/02f_extract_masaf.py | raw/it/disciplinari-extracted/*.json + raw/it/masaf-disciplinari/bundles/*.7z + raw/it/masaf-disciplinari/manual_overrides.json + raw/es/gisco/LAU_*.shp.zip | raw/it/masaf-disciplinari/pdfs/*.pdf + raw/it/masaf-disciplinari-extracted/*.json (grapes + menzioni + sottozona-text) + raw/it/extraction-unknowns-masaf.json |
| it/02h_extract_regional_registers.py | raw/it/regional-variety-registers/sources.json | raw/it/regional-variety-registers/{umbria,lazio,sicilia,campania,calabria}.{pdf,json} |
| it/03_generate_wiki.py | raw/it/disciplinari-extracted/*.json | wiki/<slug>.md (per IT record) + merges IT entries into wiki/_index.json |
| audit_it_coverage.py | raw/it/eambrosia/ + raw/it/disciplinari-extracted/ + raw/it/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |
| audit_it_regions.py | raw/it/{eambrosia,disciplinari-extracted,masaf-disciplinari-extracted}/ + raw/es/figshare/EU_PDO.gpkg + raw/es/gisco/LAU_*.shp.zip | (stdout — regione vs polygon cross-check) |
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
  same data shape as FR DGCs / ES subzonas / PT sub-regiões. Detected
  by `scripts/_lib/it/sottozona.py` (Pattern A `Sottozona NAME:`
  prefix; Pattern B preamble-list `le seguenti sottozone: «Chianti
  Colli Aretini», … e «Chianti Rufina»`, with guillemet/smart-quote
  stripping, parent-name-prefix stripping, and trailing-prose
  truncation). The documento unico almost never names them, so they
  live in the **MASAF disciplinare Article 1** — `synthesize_it_
  sottozone_records()` in stage 04 runs the detector over the cached
  sidecar `article_bodies` and appends a child record per sottozona,
  inheriting the parent's grapes/styles/terroir; geometry resolves via
  `parent-appellation`. v1 yield: **38 sottozone across 10 DOPs**
  (Chianti 7, Vin Santo del Chianti 7, Valtellina Superiore 5, Bardolino
  3, Costa d'Amalfi 3, Cannonau di Sardegna 3, Penisola Sorrentina 3,
  Cinque Terre, Lambrusco Mantovano, Lago di Caldaro).
- **Menzioni / Unità Geografiche Aggiuntive** (MGA / UGA) — finer
  "cru" granularity (Chianti Classico's 11 UGAs, Barolo's 181 MGAs,
  Soave's 29 UGAs). Per 2024 wine-law reform, UGA is the new official
  term. **v1 scope** (with user): emit MGA/UGA as a flat
  `menzioni: []` chip list on parent panels only — **no per-cru
  polygons** (researched 2026-05-30: no licence-clear public GIS layer
  exists; every MGA boundary dataset is Consorzio-held / Masnaghetti-
  proprietary, so the public-sources rule forbids ingesting them).
  `scripts/_lib/it/menzione.py` harvests the names (numbered-list +
  comma-list patterns; the shape is chosen by yield, not marker count,
  so a comma list carrying stray "art. N" references isn't mis-routed
  to the numbered parser). Stage 02 harvests from the documento unico;
  **stage 02f additionally harvests from the full MASAF disciplinare
  text** (the MGA roster lives in Article 8, absent from the cached
  `article_bodies`), so Barolo's 169 + Barbaresco's 66 MGAs now land.
  Stored on the in-memory record's `menzioni`, snapshotted into
  `_IT_MENZIONI_BY_SLUG`, surfaced in the `aocs` panel blob, and
  rendered as a collapsible chip section (`renderMenzioni` in
  `map_template.py`).

### IT regional variety-register layer (stage 02h)

~19 regional IGTs (IGT Umbria/Lazio/Calabria/Campania/Sicilia + their
sub-IGTs) define their grape roster by reference — Article 2 says "i
vitigni idonei alla coltivazione nella Regione X … allegato 1" and the
annex is absent from the consolidated MASAF PDF. Each Region publishes
its authorised-variety register as an official act (public-domain under
art. 5 L. 633/1941). Stage 02h
([scripts/it/02h_extract_regional_registers.py](scripts/it/02h_extract_regional_registers.py))
fetches the 5 register PDFs pinned in
`raw/it/regional-variety-registers/sources.json` and parses them via
[scripts/_lib/it/regional_register.py](scripts/_lib/it/regional_register.py)
(three colour encodings: `suffix` N./B./G./RS. — Umbria/Sicilia/Calabria;
`columns` spelled colour — Lazio; `vbcode` V.B.N./V.B.B. — Campania).
Each region sidecar lists the IGT slugs (`igts`) that draw from it;
varietal IGTs (e.g. catalanesca-del-monte-somma) are deliberately
excluded. Stage 04 `augment_it_records_with_regional_registers()` fills
the roster only when the record still has no grapes; `_sources_for()`
surfaces `regional_register_*` provenance (panel link
`src_regional_register`). To-do (CURATOR_TODO): Molise (osco, rotae) +
Lombardia (quistello) registers not yet pinned.

### Cancelled IT GIs (filtered at stage 00)

The 7 Abruzzo IGTs (Colli Aprutini, Colli del Sangro, Colline Frentane,
Colline Pescaresi, Colline Teatine, del Vastese, Terre di Chieti) were
cancelled by Commission Implementing Regulations (EU) 2026/558–708
(spring 2026), consolidated into the regional IGP **Terre Abruzzesi**
(which stays). Like the AT `CANCELLED_PDOS` mechanism, the
`CANCELLED_GIS` registry in
[scripts/it/00_fetch_data.py](scripts/it/00_fetch_data.py) (keyed by
`giIdentifier` — these old IGTs carry no PDO/PGI fileNumber) filters
them out of the index, cites each cancellation regulation, and is
surfaced by `audit_it_coverage.py`. Corpus: **531 → 524** wines.

### IT regione derivation

Each IT record carries a `regione` (one of the 20) used by stage 03
(wiki frontmatter) and stage 04 (panel header + region facet +
gettext label). It is derived at extraction time — stage 02 for
documenti unici, stage 02f for MASAF-augmented stubs — by
[scripts/_lib/it/region.py](scripts/_lib/it/region.py)
`derive_regione`, grounded in
[scripts/_lib/it/province.py](scripts/_lib/it/province.py) (the 107
Italian provinces, each `(ISTAT code, sigla, name, regione)`; ISTAT
codes verified against the GISCO LAU 2024 `IT_*` prefixes).

Province → regione is unambiguous, so the area text's **provinces and
communes** are the signal — *not* a bare regione-name scan, which
latches onto a neighbouring regione the terroir / boundary prose
names first. `derive_regione` reads only the geo-area text (never the
terroir text), truncates the boundary-tracing prose
(`truncate_at_delimitation` — that prose names roads/hamlets that
collide with tiny commune names), and resolves in order: (1) province
sigle / "provincia di NAME" with a clear winner; (2) an explicit
"Regione X" statement (region-wide DOCs); (3) a province + commune
tally — every commune named in the enumeration votes, gated to
list-context so prose words are ignored, against a GISCO-derived
commune→regione index; (4) the curated
`regione_by_file_number.json` fallback (hand-verified, for DOPs whose
document names no parseable province); (5) a last-resort bare scan.
Interregional DOPs defer to the curated primary.

[scripts/audit_it_regions.py](scripts/audit_it_regions.py)
independently cross-checks every `regione` by reverse-geocoding the
Figshare polygon against GISCO comuni; `--strict` exits non-zero on a
mismatch.

### IT geometry resolution chain (stage 04)

Italian appellations genuinely overlap (a comune can sit in several
DOC zones), so the goal for IT geometry is *accurate polygons*, not
disjointness. Bétard 2022 draws polygons at whole-municipality
resolution and additionally has cross-attribution errors — the
preferred source is each region's **official production-zone GIS
layer** where one is published licence-clear. Registry + per-region
status: [scripts/_lib/it/zone_sources.py](scripts/_lib/it/zone_sources.py);
stage 00 fetches the `active` layers into `raw/it/regional-zones/`,
`scripts/_lib/it/zones.py` (`ITZoneIndex`) matches a wine's name
against them.

Per IT record, in priority order (each step records the chosen
source in `geom_source` so the panel can attribute correctly):

1. **`geoportal-zone:<region>`** — official regional-geoportal
   production-zone polygon, matched by appellation name. Five regions
   are harvested (Piemonte, Veneto, Lazio, Lombardia, Toscana — all
   CC-BY 4.0 / IODL 2.0); ~218 of 531 IT wines resolve here, including
   every flagship (Barolo, Soave, Valpolicella, Chianti, Brunello,
   Bolgheri, Franciacorta, Frascati). An appellation spanning regions
   is the union of its per-region pieces. Umbria + Puglia are tracked
   to-dos (see CURATOR_TODO.md).
2. **`parent-appellation`** — sottozone (sub-denominations) inherit
   the parent's polygon.
3. **`figshare-pdo`** — exact `file_number` (`PDO-IT-A*` /
   `PGI-IT-A*`) → `PDOid` match against Bétard 2022 EU\_PDO.gpkg —
   the fallback for wines in unharvested regions. Whole-municipality
   resolution; runs even for stub records (the polygon doesn't depend
   on the documento unico).
4. **`gisco-comune-union` / `gisco-provincia-union` /
   `gisco-regione-union`** — for IGTs (Bétard is PDO-only) and the few
   newer DOPs missing Bétard: `ITCommuneIndex`
   ([scripts/_lib/it/comune.py](scripts/_lib/it/comune.py)) parses the
   disciplinare's geo-area text (the MASAF `geo_area_brief`, "…comprende
   l'intero territorio amministrativo della regione/provincia di X" or a
   flat comune list) and unions the matching GISCO LAU `IT_*` comuni —
   the ES/RO IGP pattern. Resolves ~81 IGTs (44 comune-union, 33
   provincia-union, 4 regione-union) that previously dropped off the
   map; areas land within ~1 % of the true administrative km². Bilingual
   ISTAT province/region names ("Bolzano/Bozen", "Valle d'Aosta/Vallée
   d'Aoste") register each slash-part as an alias, and "Regione
   Siciliana" folds to "Sicilia" (`_REGION_NAME_ALIAS`). The earlier
   "shelved" note applied to per-commune-list parsing of complex DOC
   prose; for the province-/region-wide IGTs this resolver is reliable.
5. **`stub-no-geometry`** — last resort; in v1 only **Salemi** (no
   parseable source, pending cancellation) stays here. **523 / 524** IT
   wines resolve to a polygon.

Non-stub IGTs whose documento unico left `geo_area_brief` empty
(`terre-siciliane`, `terre-abruzzesi`, `ravenna`, `valdadige`) are
gap-filled from their MASAF sidecar's Article 3 body —
`02f_extract_masaf.py --include-nonstub` emits a sidecar for non-stubs
too, and stage 04's `_backfill_it_nonstub_from_masaf` fills *only* the
empty fields (geo_area_brief / grapes / link_to_terroir), never
overwriting canonical documento-unico data. The same gap-fill recovers
grapes for non-stub DOPs whose section-7 was empty (e.g. Abruzzo).

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

## Austria pipeline (`scripts/at/`)

Country #5. The cleanest corpus so far: **30 wine GIs (27 DOP + 3
IGP)** from eAmbrosia after filtering 2 cancelled PDOs (see "Cancelled
PDOs" below), and **every one of the 30 carries an OJ Series C
publication URL** — no curator queue, no no-publication bucket
(unlike ES 44 % / IT 74 %). Latin script + German language, so the
shared slug / normalisation helpers reuse untouched.

Spine: **eAmbrosia EU register** (filtered `country=AT` +
`productType=WINE` + `status=registered`, minus the `CANCELLED_PDOS`
registry in [scripts/at/00_fetch_data.py](scripts/at/00_fetch_data.py)).
Pliego source: the EU-OJ **"EINZIGES DOKUMENT"** published inline as
HTML, reached via each GI's `publications[].uri` (German-language URL
rewrite — `/legal-content/DE/TXT/HTML/`, `…01.DEU`). Structurally a
near-verbatim mirror of the IT pipeline **minus the MASAF / stage-02f
layer** — Austria needs no national-spec fallback because every wine
has its EU single document.

WAF caveat: same as ES / IT — EUR-Lex returns HTTP 202 + an AWS WAF
JavaScript challenge; all 30 AT wines hit it on the first pass.
`scripts/at/01b_solve_waf.py` clears them with headless Chromium
(Playwright, `bootstrap` dependency-group).

| Script | Reads | Writes |
|---|---|---|
| at/00_fetch_data.py | (network: eAmbrosia + Statistik Austria registry lists) | raw/at/eambrosia/index.json + manifest.json, raw/at/statistik/{polbezirke,gemliste_knz}.csv |
| at/01_fetch_pliegos.py | raw/at/eambrosia/index.json + raw/at/oj-pages/manual_overrides.json | raw/at/oj-pages/*.html (German EINZIGES-DOKUMENT HTMLs) + manifest.json |
| at/01b_solve_waf.py | raw/at/oj-pages/manifest.json | raw/at/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| at/02_extract_pliegos.py | raw/at/oj-pages/*.html | raw/at/dokumente-extracted/*.json + _index.json |
| at/02d_extract_terroir_facts.py | raw/at/dokumente-extracted/*.json + raw/wikipedia/aocs/de/ | raw/terroir-facts/*.json (country="at") + manifest-at.json |
| at/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="at") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| at/03_generate_wiki.py | raw/at/dokumente-extracted/*.json | wiki/<slug>.md (per AT record) + merges AT entries into wiki/_index.json |
| at/regen_manual_overrides_template.py | raw/at/eambrosia/index.json + raw/at/oj-pages/manifest.json | raw/at/oj-pages/manual_overrides.json (curator queue) |
| audit_at_coverage.py | raw/at/eambrosia/ + raw/at/dokumente-extracted/ + raw/at/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

AT-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT). `country`
  is `"at"`; `source_lang` is `"de"` — Austria is the first country
  whose country code differs from its language. The shared 02b / 02c
  stages key German config on `de` (`--lang de`, `--source-lang de`);
  stage 04 and the grape corpus key on the country dir `at`.
- The German EINZIGES-DOKUMENT template is parsed by
  `scripts/_lib/at/einziges_dokument.py` (German section-keyword role
  routing — *Name(n)*, *Abgegrenztes geografisches Gebiet*,
  *Wichtigste Keltertraubensorte(n)*, *Beschreibung des
  Zusammenhangs*…). The HTML-slice machinery (anchor regex, numbered
  `ti-grseq-1` headers) is identical to ES/IT.
- Section 7 ("Keltertraubensorten") lists varieties one per line as
  `Offizieller Name - Synonym, Synonym` — the canonical name is the
  segment before the dash. Austrian-only varieties (Zweigelt, Sankt
  Laurent, Neuburger, Scheurebe, Blauer Wildbacher, Bouvier,
  Goldburger, Rathay, Grauburgunder) are folded into the shared
  `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables in `grape_lexicon.py`.
- v1 models the 30 wine GIs as a **flat corpus** — no DAC sub-
  denominations (FR DGC / ES subzona / IT sottozona analogue). Most
  Austrian DACs use ripeness (Steinfeder / Federspiel / Smaragd) or
  single-vineyard (*Ried*) tiers rather than geographic sub-areas,
  and the single document does not enumerate them.
- Region facet = **Bundesland** (`scripts/_lib/at/region.py`). All 9
  wine Bundesländer appear in the corpus as generic regional PDOs;
  each of the 27 DOPs maps to exactly one Bundesland (curated
  file_number map). The 3 multi-state Landwein IGPs (Bergland,
  Weinland) are tagged `Österreich`; Steirerland is coextensive with
  Steiermark. Bundesland labels follow the IT/ES convention — shown
  in their native form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for AT
  (siblings of the ES/PT/IT pairs). Dual-source grounding (Einziges
  Dokument section 8 + de.wikipedia.org per-DOP page), German
  extraction prompt, fuzzy-coverage filter (≥ 0.6), per-bullet
  provenance, manual round-trip flow. 02e targets en/fr/es/nl.

### AT geometry resolution chain (stage 04)

AT geometry is **commune-precise**, not Bétard-derived. Bétard 2022
draws PDO polygons at whole-municipality resolution and assigns shared
municipalities to every appellation that touches them, so adjacent
Bétard polygons overlap (Südsteiermark ∩ Vulkanland Steiermark = 22 %).
The Austrian *Einziges Dokument* (section 6) instead defines each area
precisely — by politischer Bezirk, by Gemeinde, with explicit
`ausgenommen` exclusions — and the DACs are disjoint by wine law.

`scripts/_lib/at/gemeinde.py` (`ATCommuneIndex`) parses that German
description and unions the named Gemeinde polygons. It joins three
public sources: Statistik Austria `polbezirke.csv` (Bezirk name ↔
3-digit code) + `gemliste_knz.csv` (Gemeinde name ↔ 5-digit
Kennziffer) + Eurostat GISCO LAU (Gemeinde polygons, keyed by
Kennziffer via `GISCO_ID`). A whole Bezirk expands to every GISCO
Gemeinde whose Kennziffer carries its 3-digit prefix; named Gemeinden
resolve directly; exclusions are subtracted. `_GEMEINDE_ALIAS` folds
the handful of municipal mergers / spelling drift since the
appellation documents were drafted (Etsdorf-Haitzendorf → Grafenegg,
Weißenkirchen → Weißenkirchen in der Wachau, …).

Per AT record, in priority order (`geom_source` records the choice):

1. **`gisco-commune-union`** — Bezirk/Gemeinde description resolved to a
   disjoint union of GISCO municipality polygons. The 16 proper DACs
   are verified disjoint (0 % pairwise overlap).
2. **`gisco-bundesland-union`** — the 9 whole-Bundesland regional g.U.s
   and the 3 multi-Bundesland Landwein IGPs (Bergland / Weinland /
   Steirerland): union every GISCO Gemeinde of the named Bundesland/
   Bundesländer.
3. **`figshare-pdo`** — Bétard 2022 fallback, used only if a record's
   geo-area text fails to parse. Defensive; not normally hit. (The
   IGP-containing-DAC and Leithaberg ⊃ Ruster Ausbruch overlaps are
   legitimate regulatory containment, not errors.)
4. **`stub-no-geometry`** — last resort. Not normally hit in v1; all
   30 wines resolve.

Statistik Austria registry lists are CC BY 4.0 (fetched in stage 00);
GISCO LAU is the shared `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`,
Bétard `raw/es/figshare/EU_PDO.gpkg` — both already cached by ES.

### Cancelled PDOs (filtered at stage 00)

The Commission occasionally cancels a registered PDO via an OJ-L
Implementing Regulation, but eAmbrosia is not retroactively cleaned
up — cancelled names linger as `status: registered`. Stage 00's
`CANCELLED_PDOS` registry in
[scripts/at/00_fetch_data.py](scripts/at/00_fetch_data.py) filters
these out before they enter `raw/at/eambrosia/index.json`. Each entry
cites the cancellation regulation; the audit at
[scripts/audit_at_coverage.py](scripts/audit_at_coverage.py)
surfaces the registry so the decision is traceable.

Current entries (verified 2026-05 via the public OJ-L documents):

- `PDO-AT-A0220` Neusiedlersee-Hügelland — Commission Implementing
  Regulation (EU) 2021/1303 (OJ L 283/11, 6.8.2021). Territory mostly
  absorbed into Leithaberg.
- `PDO-AT-A0227` Südburgenland — Commission Implementing Regulation
  (EU) 2021/1294 (OJ L 282/1, 5.8.2021). Reorganised into Eisenberg.

Adding an entry: verify the OJ-L document's title literally says
"cancelling the protection of the designation of origin '<name>'"
(not "amending" — that's a modification, kept), then add the
`fileNumber → {name, regulation, oj_l, url}` quadruple. Re-run stage
00 → 02 → 04 to flush the cached extracted record and OJ-page
manifest entry. The same mechanism applies to other countries —
mirror the registry into the country's stage 00 when a cancellation
is verified.

## Slovenia pipeline (`scripts/si/`)

Country #6. **17 wine GIs (14 DOP + 3 IGP)** from eAmbrosia. Structurally
a clone of the Austria pipeline (EU-OJ single-document HTML, Latin
script, Bétard PDO geometry, PGI = region-union), but the *coverage*
reality is Italy's: only **1 of 17** wines (Cviček) carries a fetchable
EU single document. The other 16 are Art. 107 / Reg. 1308/2013
grandfathered names whose only eAmbrosia reference is a non-fetchable
`Ares(...)` summary-sheet — they ship as content-stubs (the IT/ES
curator-queue pattern). All 14 SI DOPs are nonetheless in Bétard 2022,
so every wine appears on the map with a polygon regardless.

Spine: **eAmbrosia EU register**, filtered `country=SI` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"ENOTNI DOKUMENT"** published inline as HTML, reached via each GI's
`publications[].uri` (Slovenian-language URL rewrite — `/oj/slv`,
`legal-content/SL/TXT/HTML/`, `…01.SLV`). Same AWS-WAF caveat as
ES/IT/AT — `scripts/si/01b_solve_waf.py` clears blocked URLs with
headless Chromium.

| Script | Reads | Writes |
|---|---|---|
| si/00_fetch_data.py | (network: eAmbrosia) | raw/si/eambrosia/index.json + manifest.json |
| si/01_fetch_pliegos.py | raw/si/eambrosia/index.json + raw/si/oj-pages/manual_overrides.json | raw/si/oj-pages/*.html + manifest.json |
| si/01b_solve_waf.py | raw/si/oj-pages/manifest.json | raw/si/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| si/01c_fetch_specifikacije.py | raw/si/oj-pages/manual_overrides.json | raw/si/specifikacije/*.{doc,html} + manifest.json |
| si/02_extract_pliegos.py | raw/si/oj-pages/*.html | raw/si/dokumenti-extracted/*.json + _index.json |
| si/02f_extract_specifikacije.py | raw/si/specifikacije/*.{doc,html} + Docker `owm-antiword` image | raw/si/specifikacije-extracted/*.json + _index.json + manifest.json |
| si/02d_extract_terroir_facts.py | raw/si/dokumenti-extracted/*.json + raw/wikipedia/aocs/sl/ | raw/terroir-facts/*.json (country="si") + manifest-si.json |
| si/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="si") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| si/03_generate_wiki.py | raw/si/dokumenti-extracted/*.json | wiki/<slug>.md (per SI record) + merges SI entries into wiki/_index.json |
| si/regen_manual_overrides_template.py | raw/si/eambrosia/index.json + raw/si/oj-pages/manifest.json | raw/si/oj-pages/manual_overrides.json (curator queue) |
| audit_si_coverage.py | raw/si/eambrosia/ + raw/si/dokumenti-extracted/ + raw/si/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

SI-specific notes:
- `kind` is `"DOP"` / `"IGP"`. `country` is `"si"`; `source_lang` is
  `"sl"` — like Austria, the country code differs from the language
  code. The shared 02b / 02c stages key Slovenian config on `sl`.
- The Slovenian ENOTNI-DOKUMENT template is parsed by
  `scripts/_lib/si/enotni_dokument.py` (Slovenian section-keyword role
  routing — *Ime ali imena*, *Razmejeno geografsko območje*, *Sorta ali
  sorte vinske trte*, *Povezava z geografskim območjem* …). HTML-slice
  machinery is identical to ES/IT/AT.
- The grape-variety section lists varieties as a single em-dash-bulleted
  line (`— bela žlahtnina — beli pinot - weissburgunder — …`); stage 02
  splits on the em-dash bullets, then on a plain hyphen for
  `Name - synonym`. Slovenian varieties (Žametovka, Kraljevina, Ranfol,
  Rumeni plavec, Refošk, …) are folded into the shared `GRAPE_ALIAS` /
  `DEFAULT_COLOUR` tables in `grape_lexicon.py`.
- v1 models the 17 wine GIs as a **flat corpus** — podokoliš (sub-
  district) sub-denominations are deferred to Phase 2 (gated on the
  national-specification research; see the curator workflow below).
- Region facet = vinorodna dežela (`scripts/_lib/si/region.py`):
  Podravje / Posavje / Primorska. The 3 IGPs are the regions themselves;
  each of the 14 DOPs maps to exactly one region (curated file_number
  map). Region labels follow the AT/IT/ES convention — native form, not
  gettext-translated.

### SI geometry resolution chain (stage 04)

Per SI record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-SI-*`) → `PDOid` match
   against Bétard 2022 EU_PDO.gpkg. Covers all 14 SI DOPs (and runs even
   for content-stubs, so well-known DOPs like Teran, Goriška Brda appear
   on the map though their ENOTNI DOKUMENT isn't accessible).
2. **`region-pdo-union`** — the 3 SI IGPs (Podravje / Posavje /
   Primorska) are the wine regions; Bétard is PDO-only, so each IGP is
   the union of the Figshare polygons of the DOPs inside that region
   (see `scripts/_lib/si/geometry.py` `SI_PGI_MEMBER_PDOS`). All 14
   DOPs are in Bétard, so every IGP resolves exactly.
3. **`stub-no-geometry`** — not normally hit (all 17 resolve in v1).

Bétard 2022 is the shared `raw/es/figshare/EU_PDO.gpkg` — no new fetch
in stage 00.

### SI national-spec augmentation (stage 02f)

Because 16 of 17 SI wines have no fetchable EU-OJ ENOTNI DOKUMENT
(every wine except Cviček is an Art.107 / Reg.1308/2013 grandfathered
name), the SI corpus would ship as 16 bare stubs without a national-
spec layer. Stage 02f
([scripts/si/02f_extract_specifikacije.py](scripts/si/02f_extract_specifikacije.py))
parses the canonical Slovenian regulator sources researched in
2026-05-29 via `/research-gaps` and pinned in
[raw/si/oj-pages/manual_overrides.json](raw/si/oj-pages/manual_overrides.json) —
two source patterns covering all 16 stubs:

- **MKGP per-wine `.doc`** (11 wines) — Microsoft Word 97-2003 binary
  format hosted at `gov.si/assets/ministrstva/MKGP/DOKUMENTI/HRANA/VINO/ZOP/`.
  Layout is the "SPECIFIKACIJA PROIZVODA v skladu s 118 c členom
  Uredbe Sveta 1234/2007" template — 9 numbered sections matching the
  EU template (1 Ime / 2 Opis vin / 3 Posebni enološki postopki /
  4 Opredelitev geografskega območja / 5 Največji donos / 6 Sorte /
  7 Povezava z geografskim območjem / 8 Veljavne zahteve / 9 Pregledi).
  Section 6 (Sorte) splits by colour markers `bele:` / `rdeče:` /
  `rose:` — flat list, no principal/accessory split (same shape as
  the EU template).
- **Uradni list RS pravilnik HTML** (5 wines, 2 distinct documents) —
  the Slovenian official gazette. 4 wines (bela-krajina + the 3 PGIs
  podravje / posavje / primorska) share **Uradni list RS št. 49/2007,
  predpis 2634** *Pravilnik o seznamu geografskih označb za vina in
  trsnem izboru*; Priloga 2 lists per-okoliš `priporočene sorte`
  (→ principal) + `dovoljene sorte` (→ accessory) — the only SI
  source that ships a real role split. 1 wine (belokranjec) is
  parsed from **Uradni list RS št. 112/2022, predpis 2690** the
  Metliška črnina + Belokranjec PTP Pravilnik; Article 5 paragraph 2
  enumerates the 10-variety Belokranjec list.

Pipeline (stages 01c + 02f):

1. **Stage 01c** ([scripts/si/01c_fetch_specifikacije.py](scripts/si/01c_fetch_specifikacije.py))
   fetches the 16 specs into `raw/si/specifikacije/<slug>.{doc,html}`
   keyed by `Content-Type` (msword → `.doc`, html → `.html`); writes
   `manifest.json` with sha256, source URL, fetched_at.
2. **Stage 02f** dispatches each cache file to one of two parser
   branches in [scripts/_lib/si/specifikacija.py](scripts/_lib/si/specifikacija.py):
   - **`mkgp-doc-v1`**: `.doc` files are converted via `antiword`
     running in a one-off Docker image
     ([scripts/si/Dockerfile.doc-converter](scripts/si/Dockerfile.doc-converter):
     ~120 KB on top of `debian:bookworm-slim`). Build once via
     `docker build -t owm-antiword:latest -f scripts/si/Dockerfile.doc-converter scripts/si/`;
     stage 02f shells out with `-w 0 -m UTF-8.txt` for unwrapped
     paragraphs + Slovenian diacritics. The output text feeds the
     9-section parser keyed on numbered SPECIFIKACIJA-PROIZVODA
     headers; style detection truncates at the `Tradicionalna imena`
     boilerplate (lists every predikat tier authorised in Slovenian
     wine law for the okoliš, not styles actually produced) so the
     resulting style tags reflect the wine's first-paragraph
     description rather than the regulatory roster.
   - **`uradni-list-pravilnik-2007`**: HTML pravilnik. Strips to plain
     text, then walks Article 5 paragraphs to identify the wine
     region's okoliši, then walks Priloga 2 to extract per-okoliš
     `priporočene sorte` / `dovoljene sorte`. PGI variant rolls every
     okoliš inside the wine region into one combined roster.
   - **`uradni-list-pravilnik-2022-ptp`**: HTML pravilnik. Strict
     `\b\d+\. člen\b` word-boundary regex avoids false-positives on
     genitive references (`5. člena`, `9. členu`); Article 2 ¶2 for
     description, Article 4 for area, Article 5 ¶2 for the enumerated
     Belokranjec variety list.

`augment_si_records_with_specifikacija()` in
[scripts/04_build_maps.py](scripts/04_build_maps.py) merges the
sidecar's summary / grapes / geo-area / link-to-terroir / styles /
section-roles into each in-memory SI stub record at load time; the
on-disk dokumenti-extracted JSON stays immutable. `_sources_for()`
surfaces `specifikacija_*` provenance for the panel (URL, sha256,
parser_template, format) so the map can attribute the data + link to
its source. The record's `stub_reason` is prefixed `specifikacija:`
so the audit can tell EU-OJ-extracted from spec-augmented wines.

Result: 16 / 16 SI stubs augmented; **236 principal + 54 accessory**
variety slugs added across the corpus (per-wine principal min=1 for
Teran, max=25 for Bizeljčan / Bizeljsko Sremič).

Re-runnable per slug or sweep:
```
.venv/bin/python scripts/si/01c_fetch_specifikacije.py
.venv/bin/python scripts/si/02f_extract_specifikacije.py --slug teran
.venv/bin/python scripts/si/02f_extract_specifikacije.py --all
.venv/bin/python scripts/04_build_maps.py
```

Cached `.doc` / `.html` files at `raw/si/specifikacije/<slug>.*` are
reused unless `--refresh` is passed.

Note: stage 02's HTML parser still only understands the EU-OJ ENOTNI
DOKUMENT template (the parsed-via-stage-02 path of stage 02 emits
`raw/si/dokumenti-extracted/<slug>.json` — the stub-or-extract
contract is unchanged). National-spec extraction is a parallel layer
that feeds stage 04 via the augmentation hook, not via the dokumenti-
extracted directory. The podokoliš (sub-district) sub-denomination
layer remains Phase 3 — recoverable from the same MKGP `.doc` files
(section 4 enumerates podokoliši for wines that have them) but
deferred so v1 sticks with the flat-corpus model.

### Teran — cross-border note (`appellation_notes.json`)

`Teran` is the SI PDO `PDO-SI-A1581` (Kras, Primorska). It is also a
grape name (Refošk / Refosco family — folded to
`refosco-dal-peduncolo-rosso` in `grape_lexicon.py`); appellation slugs
and grape slugs are separate namespaces, so there is no collision. When
Croatia (country #7) is added, do **not** mint a duplicate `teran`
appellation — "Teran" on a Croatian *Hrvatska Istra* label is a
permitted labelling term under Commission Delegated Reg. (EU) 2017/1353,
not a separate GI.

`scripts/_lib/appellation_notes.json` is a curated, source-cited
per-appellation note layer (a bounded narrative layer, same category as
terroir-facts). Keyed by slug → `{note: {en,fr,es,nl}, sources:
[{label,url}]}`; every note must cite a public, licence-clear source.
Stage 04 loads it into the `aocs` blob and the map detail panel renders
an "ⓘ" note block; per-country stage 03 renders a `## Opomba` / `##
Napomena` wiki section. The `teran` entry (rendered on the SI Teran
page) and the symmetric `hrvatska-istra` entry (rendered on the HR
Hrvatska Istra page) together cover the SI/HR labelling distinction.

## Croatia pipeline (`scripts/hr/`)

Country #7. The cleanest profile in the corpus: **18 wine PDOs (no
IGPs)** from eAmbrosia, **100 % Bétard 2022 geometry coverage** (every
HR PDO is in the Figshare gpkg), and a structurally simpler pipeline
than every prior country — no IGP region-union, no commune-list
fallback chain, no per-source national parser branch in v1.

Spine: **eAmbrosia EU register**, filtered `country=HR` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"JEDINSTVENI DOKUMENT"** published inline as HTML, reached via each
GI's `publications[].uri` (Croatian-language URL rewrite — `/oj/hrv`,
`legal-content/HR/TXT/HTML/`, `…01.HRV`). Same AWS-WAF caveat as
ES/IT/AT/SI — `scripts/hr/01b_solve_waf.py` clears blocked URLs with
headless Chromium (none were needed on the first stage-01 run).

Coverage in the corpus mirrors SI: only **2 of the 18** HR wines
(Muškat momjanski, Ponikve) carry a fetchable EU single document. The
other 16 are Art.107/Reg.1308/2013 grandfathered names whose only
eAmbrosia reference is a non-fetchable `Ares(...)` summary-sheet —
they ship as content-stubs (the IT/ES/SI curator-queue pattern). All
18 nonetheless appear on the map with a polygon because Bétard 2022
covers them all.

| Script | Reads | Writes |
|---|---|---|
| hr/00_fetch_data.py | (network: eAmbrosia) | raw/hr/eambrosia/index.json + manifest.json |
| hr/01_fetch_pliegos.py | raw/hr/eambrosia/index.json + raw/hr/oj-pages/manual_overrides.json | raw/hr/oj-pages/*.html + manifest.json |
| hr/01b_solve_waf.py | raw/hr/oj-pages/manifest.json | raw/hr/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| hr/01c_fetch_specifikacije.py | raw/hr/specifikacije/manual_overrides.json | raw/hr/specifikacije/*.{doc,docx,pdf} + manifest.json |
| hr/02_extract_pliegos.py | raw/hr/oj-pages/*.html | raw/hr/dokumenti-extracted/*.json + _index.json |
| hr/02f_extract_specifikacije.py | raw/hr/specifikacije/*.{doc,docx,pdf} + Docker `owm-antiword` image | raw/hr/specifikacije-extracted/*.json + _index.json + manifest.json |
| hr/02d_extract_terroir_facts.py | raw/hr/dokumenti-extracted/*.json + raw/wikipedia/aocs/hr/ | raw/terroir-facts/*.json (country="hr") + manifest-hr.json |
| hr/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="hr") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| hr/03_generate_wiki.py | raw/hr/dokumenti-extracted/*.json | wiki/<slug>.md (per HR record) + merges HR entries into wiki/_index.json |
| hr/regen_manual_overrides_template.py | raw/hr/eambrosia/index.json + raw/hr/oj-pages/manifest.json | raw/hr/oj-pages/manual_overrides.json (curator queue) |
| audit_hr_coverage.py | raw/hr/eambrosia/ + raw/hr/dokumenti-extracted/ + raw/hr/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

HR-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI), but
  every HR wine in eAmbrosia is a PDO — there are no Croatian wine IGPs.
  `country` is `"hr"`; `source_lang` is also `"hr"` (the country code
  matches the language code, like ES/PT/IT but unlike AT/SI).
- The Croatian JEDINSTVENI DOKUMENT template is parsed by
  `scripts/_lib/hr/jedinstveni_dokument.py` (Croatian section-keyword
  role routing — *Naziv koji je potrebno upisati u registar*,
  *Razgraničeno zemljopisno područje*, *Glavne sorte vinove loze*,
  *Opis povezanosti* …). HTML-slice machinery is identical to ES/IT/AT/SI.
- v1 models the 18 wine GIs as a **flat corpus** — the regulatory
  hierarchy (3 macro regions ⊃ sub-regions ⊃ positions like Dingač)
  is preserved via the `region` facet, not as parent/sub-denomination
  records. The 3 macro regions themselves appear as separate PDOs
  in eAmbrosia.
- Region facet = 3 Croatian wine macro regions (Primorska Hrvatska,
  Istočna kontinentalna Hrvatska, Zapadna kontinentalna Hrvatska),
  curated by file_number in `scripts/_lib/hr/region.py`. Each of the
  18 PDOs maps to exactly one macro region. Region labels follow the
  AT/IT/ES/SI convention — native form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for HR
  (siblings of the ES/PT/IT/AT/SI pairs). Dual-source grounding
  (Jedinstveni Dokument section 8 + hr.wikipedia.org per-DOP page),
  Croatian extraction prompt, fuzzy-coverage filter (≥ 0.6),
  per-bullet provenance, manual round-trip flow. 02e targets en/fr/es/nl.
- Cross-border note: `hrvatska-istra` carries the symmetric Teran-
  labelling note (see [Teran cross-border section](#teran--cross-border-note-appellation_notesjson)
  above). Both `teran` (SI side) and `hrvatska-istra` (HR side) cite
  the same source pair — Commission Delegated Reg. (EU) 2017/1353 and
  General Court Case T-626/17.

### HR geometry resolution chain (stage 04)

Per HR record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-HR-*`) → `PDOid`
   match against Bétard 2022 EU_PDO.gpkg. Covers all 18 HR PDOs (and
   runs even for content-stubs, so well-known PDOs like Dingač and
   Hrvatska Istra appear on the map though their JEDINSTVENI DOKUMENT
   isn't accessible). The shared `raw/es/figshare/EU_PDO.gpkg` —
   no new fetch in stage 00.
2. **`stub-no-geometry`** — not normally hit (all 18 resolve in v1).

Croatia has no IGPs (unlike SI's 3), so there is no region-union
branch — the simplest geometry chain of any country.

### HR national specifikacija augmentation (stage 01c + 02f)

The 16 grandfathered HR wines (everything except Muškat momjanski +
Ponikve) have no fetchable EU-OJ JEDINSTVENI DOKUMENT, so the corpus
would ship as 16 bare stubs without a national-spec layer. Their
canonical source is the **Ministarstvo poljoprivrede (MPS) per-wine
SPECIFIKACIJA PROIZVODA** "sukladno Uredbi 1308/2013, članak 94." —
all 16 published at
`poljoprivreda.gov.hr/UserDocsImages/dokumenti/hrana/zastita_oznaka_izvrsnosti_vina/na_razini_EU/`
(listing page
`/istaknute-teme/hrana-111/oznake-kvalitete/oznake-izvornosti-vina/229`)
in three formats: 14 legacy `.doc`, 1 `.docx` (Primorska Hrvatska),
1 PDF (Dingač). URLs are pinned in
[raw/hr/specifikacije/manual_overrides.json](raw/hr/specifikacije/manual_overrides.json) —
a **dedicated** overrides file, NOT `raw/hr/oj-pages/manual_overrides.json`:
HR stage 01 saves a PDF response as `ok` and stage 02's HTML parser
can't read `.doc`/`.docx`/`.pdf`, so the national specs ride a parallel
01c → 02f → stage-04-augment layer that never touches the EU-OJ path.

Stage 01c
([scripts/hr/01c_fetch_specifikacije.py](scripts/hr/01c_fetch_specifikacije.py))
fetches the 16 specs keyed by Content-Type. Stage 02f
([scripts/hr/02f_extract_specifikacije.py](scripts/hr/02f_extract_specifikacije.py))
converts each (`.doc` → `antiword` in the shared `owm-antiword` Docker
image, [scripts/si/Dockerfile.doc-converter](scripts/si/Dockerfile.doc-converter);
`.docx` → stdlib zip → `word/document.xml`; PDF → `pdftotext -layout`)
and parses via
[scripts/_lib/hr/specifikacija.py](scripts/_lib/hr/specifikacija.py).
The parser slices the lettered-section outline (a Naziv / b Opis
svojstava vina / c Enološki postupci / d Granice područja / e
Maksimalni urod / f Sorte vinove loze / g …povezane sa zemljopisnim
uvjetima / h Prihvatljivi zahtjevi). `\x0c` form-feeds are normalised
to `\n` (so a section starting a new PDF page is still anchored) and a
forward-only letter guard drops backward cross-reference anchors
("…točkom e) …" inside section c). Grapes come from the colour markers
`Bijele sorte:` / `Crne sorte:` (white→blanc, black→noir; a trailing-
colour-adjective fallback recovers `Croatina crna`→croatina); there is
no principal/accessory split in the MPS spec (same as PT/IT), so every
variety is `principal`. The `.docx` (Primorska) loses its lettered a–j
prefixes to Word auto-numbering, so it falls through to a keyword-title
slicer (`_keyword_sections`) that anchors on the role-keyword heading
lines instead — recovering grapes *and* the section-g terroir narrative
(the docx extractor strips `<w:pPr>` blocks so paragraph-property markup
can't leak into the text).

Stage 04's `augment_hr_records_with_specifikacija()`
([scripts/04_build_maps.py](scripts/04_build_maps.py)) merges the
sidecar's summary / grapes / geo_area / link_to_terroir / styles /
section_roles into each in-memory stub at load time; the on-disk
`dokumenti-extracted` JSON stays immutable. `_sources_for()` surfaces
`specifikacija_*` provenance (URL, sha256, parser_template, format) so
the panel attributes the data + links the source. The record's
`stub_reason` is prefixed `specifikacija:` so the audit can tell
EU-OJ-extracted from spec-augmented. HR 02d's
`_resolve_lien_and_source` reads the sidecar's `link_to_terroir`
(section g) so terroir-fact extraction grounds against the MPS spec.

Result: **16 / 16 stubs augmented; 689 principal varieties (after the
2026-05-29 autochthonous-variety lexicon pass — 44 native HR varieties
added with regulator-assigned colours + a research VIVC/identity pass);
16 / 16 with terroir source text**. Effective extraction = 18 / 18.
Terroir-fact extraction (02d/02e, Anthropic batch) then produced **213
bullets across all 18 HR wines**, translated into en/fr/es/nl. VIVC +
grape-Wikipedia enrichment is wired for the spec-only varieties:
`grape_corpus.py` + `02g_fetch_vivc.py` also scan
`raw/{hr,si}/specifikacije-extracted/` (the IT-MASAF sidecar
precedent), so 02g resolves 12 HR VIVC IDs (11 pinned in
`raw/vivc/slug_overrides.json`) and 02b lands tooltips for the
internationally-known varieties. ~44 autochthonous HR varieties the specs name
(Vranac, Dobričić, Trnjak, Kujundžuša, Crljenak viški = Tribidrag, …)
flow to `raw/hr/extraction-unknowns-specifikacije.json` for the same
`GRAPE_ALIAS` / `DEFAULT_COLOUR` vocab-curation pattern the other
countries use (see [CURATOR_TODO.md](CURATOR_TODO.md)).

Re-runnable per slug or sweep:
```
.venv/bin/python scripts/hr/01c_fetch_specifikacije.py
.venv/bin/python scripts/hr/02f_extract_specifikacije.py --slug dingac
.venv/bin/python scripts/hr/02f_extract_specifikacije.py --all
.venv/bin/python scripts/04_build_maps.py
```
Cached `.doc`/`.docx`/`.pdf` at `raw/hr/specifikacije/<slug>.*` are
reused unless `--refresh` is passed.

### Curator workflow for HR wines without an OJ publication

The 16 grandfathered names are all covered by the MPS specifikacija
layer above (researched 2026-05-29). If a new HR wine appears, or an
MPS URL rotates, add it to
`raw/hr/specifikacije/manual_overrides.json` (slug → `{url,
source_org, note, file_number}`) and re-run 01c → 02f → 04. The
EU-OJ `regen_manual_overrides_template.py` flow still applies if the
Commission later publishes a real JEDINSTVENI DOKUMENT (which would
add the EU-OJ narrative sections stage 02 parses directly).

## Hungary pipeline (`scripts/hu/`)

Country #8. **41 wine GIs (35 DOP + 6 PGI)** from eAmbrosia; the
profile sits between IT and SI/HR — 26 of 41 wines carry a fetchable
EUR-Lex EGYSÉGES DOKUMENTUM (63 % vs. SI's 6 %), and 38 of 41 land on
the map (92.7 %) via Bétard 2022 PDO match or PGI region-union.
Structurally the closest sibling to SI: documento-único HTML, Latin
script, Bétard PDO geometry, PGI = region-union; no national-spec
parser branch in v1.

Spine: **eAmbrosia EU register**, filtered `country=HU` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"EGYSÉGES DOKUMENTUM"** published inline as HTML, reached via each
GI's `publications[].uri` (Hungarian-language URL rewrite — `/oj/hun`,
`legal-content/HU/TXT/HTML/`, `…01.HUN`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR — `scripts/hu/01b_solve_waf.py` clears blocked URLs
with headless Chromium (none triggered on the first stage-01 run, but
the bootstrap remains available for re-fetches).

Coverage in the corpus: the 15 wines without a fetchable URL include
every historic flagship (Tokaj, Villány, Sopron, Szekszárd,
Pannonhalma, Pécs, Bükk, Somlói, Nagy-Somló, Balatonfüred-Csopak,
Csongrád, Balatonboglár, Káli, plus the Balatonmelléki and Zemplén
PGIs) — they're Art. 107 / Reg. 1308/2013 grandfathered names whose
only eAmbrosia reference is a non-fetchable `Ares(...)` summary-sheet.
They ship as content-stubs (the IT/ES/SI/HR curator-queue pattern)
and nonetheless appear on the map because their geometry resolves
independently via Bétard 2022.

| Script | Reads | Writes |
|---|---|---|
| hu/00_fetch_data.py | (network: eAmbrosia) | raw/hu/eambrosia/index.json + manifest.json |
| hu/01_fetch_pliegos.py | raw/hu/eambrosia/index.json + raw/hu/oj-pages/manual_overrides.json | raw/hu/oj-pages/*.html + manifest.json |
| hu/01b_solve_waf.py | raw/hu/oj-pages/manifest.json | raw/hu/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| hu/02_extract_pliegos.py | raw/hu/oj-pages/*.html | raw/hu/dokumentumok-extracted/*.json + _index.json |
| hu/02d_extract_terroir_facts.py | raw/hu/dokumentumok-extracted/*.json + raw/wikipedia/aocs/hu/ | raw/terroir-facts/*.json (country="hu") + manifest-hu.json |
| hu/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="hu") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| hu/03_generate_wiki.py | raw/hu/dokumentumok-extracted/*.json | wiki/<slug>.md (per HU record) + merges HU entries into wiki/_index.json |
| hu/regen_manual_overrides_template.py | raw/hu/eambrosia/index.json + raw/hu/oj-pages/manifest.json | raw/hu/oj-pages/manual_overrides.json (curator queue) |
| audit_hu_coverage.py | raw/hu/eambrosia/ + raw/hu/dokumentumok-extracted/ + raw/hu/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

HU-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR).
  `country` is `"hu"`; `source_lang` is also `"hu"` (country code
  matches the language code, like ES/PT/IT/HR but unlike AT/SI).
- The Hungarian EGYSÉGES DOKUMENTUM template is parsed by
  [scripts/_lib/hu/egyseges_dokumentum.py](scripts/_lib/hu/egyseges_dokumentum.py)
  (Hungarian section-keyword role routing — *A termék elnevezése*,
  *Körülhatárolt földrajzi terület*, *Fontosabb borszőlőfajták*, *A
  kapcsolat(ok) leírása*, …). The HTML-slice machinery is identical to
  ES/IT/AT/SI/HR, **but** Hungarian docs frequently re-use
  `<p class="ti-grseq-1">` for **wine-type subsections nested inside
  section 4** (description of wines) — "1. Bor – Rozé fajta és küvé",
  "2. Bor – Siller fajta és küvé", … then "5. Borkészítési eljárások"
  resumes the top-level numbering. A naive first-occurrence dedupe
  would shadow the real sections 5–9 with those wine-type subsection
  bodies. `extract_sections` therefore walks headers in document
  order with a monotonic state machine and skips any candidate
  top-level header whose title starts with a known nested-subsection
  prefix (`Bor -`, `Pezsgő`, `Classicus`, `Likőrbor`, …).
- The grape-variety section lists varieties one per line as
  `Canonical name – Synonym, Synonym` (with an en-dash); stage 02
  splits on the bullet, then on a plain hyphen for `Name - synonym`.
  Hungarian varieties (Furmint, Hárslevelű, Kékfrankos, Kadarka,
  Olaszrizling, Cserszegi Fűszeres, Irsai Olivér, Királyleányka,
  Leányka, Juhfark, Ezerjó, Tramini, Szürkebarát, plus dozens of
  native crossings — Zefír, Ezerfürtű, Zengő, Kabar, Cirfandli,
  Bakator family, Csabagyöngye, Zalagyöngye, Kunleány, Aletta,
  Medina, Generosa, Odysseus / Orpheus / Zeus, …) are folded into
  the shared `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables in
  [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).
- v1 models the 41 wine GIs as a **flat corpus** — the dűlő (named
  vineyard) layer that some Egységes Dokumentum docs enumerate (Eger
  Bikavér's named dűlők, Tokaj's classified positions) is deferred
  to Phase 2.
- Region facet = **borrégió** (`scripts/_lib/hu/region.py`): Tokaj /
  Felső-Magyarország / Duna / Balaton / Pannon / Felső-Pannon / Zemplén.
  The curated `_REGION_BY_FILE_NUMBER` map covers every wine
  (hand-verified against the Hungarian wine-law structure). Region
  labels follow the AT/IT/ES/SI/HR convention — native Hungarian
  form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for HU
  (siblings of the ES/PT/IT/AT/SI/HR pairs). Dual-source grounding
  (Egységes Dokumentum section 8 + hu.wikipedia.org per-borvidék page),
  Hungarian extraction prompt with terroir vocabulary (lösz, nyirok,
  riolittufa, andezit, bazalt, pannon klíma, botrytis, dűlő, …),
  fuzzy-coverage filter (≥ 0.6), per-bullet provenance, manual
  round-trip flow. 02e targets en/fr/es/nl. Cache files land in the
  shared `raw/terroir-facts/` directory with `country: "hu"` to
  distinguish them from FR/ES/PT/IT/AT/SI/HR records. The Hungarian
  source-locale wine-law / Predikat terms preserved verbatim by 02e
  include Aszú, Szamorodni, Eszencia, Fordítás, Máslás, Bikavér,
  Csillag, Siller, Klárét, Pezsgő, Gyöngyözőbor, Késői Szüretelésű,
  Jégbor, Töppedt, and Likőrbor. Run
  `scripts/02b_fetch_aoc_lexicon.py --lang hu --source raw/hu/dokumentumok-extracted`
  once before 02d so the Wikipedia salience hints exist (23/41 land
  on first run; 11 missing / 7 errors are curator-pinnable).

### HU geometry resolution chain (stage 04)

Per HU record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-HU-*`) → `PDOid`
   match against Bétard 2022 EU_PDO.gpkg. Covers 32 of 35 HU PDOs
   plus the Balaton PGI (Bétard mis-labels `PGI-HU-A1507` as
   `PDO-HU-A1507`; [scripts/_lib/hu/geometry.py](scripts/_lib/hu/geometry.py)
   bridges via `_FILE_NUMBER_BÉTARD_BRIDGE`). The shared
   `raw/es/figshare/EU_PDO.gpkg` — no new fetch in stage 00.
2. **`region-pdo-union`** — the 5 remaining HU PGIs (Balatonmelléki,
   Duna-Tisza-közi, Dunántúli, Felső-Magyarország, Zemplén) are
   umbrella territories; Bétard is PDO-only, so the PGI's polygon is
   the union of its member-PDO polygons (the SI PGI pattern). Member
   tables live in `HU_PGI_MEMBER_PDOS`, curated from the Hungarian
   wine-law region structure.
3. **`stub-no-geometry`** — the 3 newer PDOs (Etyeki Pezsgő, Kőszeg,
   Füred) post-date the Bétard 2022 snapshot. Phase 2: parse the
   Hungarian commune list from the Egységes Dokumentum + reuse
   Eurostat GISCO LAU for HU comune polygons.

### Curator workflow for HU wines without an OJ publication

Mirrors the ES/PT/IT/AT/SI/HR `regen_manual_overrides_template.py`
flow. 15 HU wines (13 DOPs + 2 PGIs) dominate the curator queue —
the historic flagships whose grandfathered registration carries only
an `Ares(...)` reference. The canonical source for those is the
national termékleírás published by the HNT (Hegyközségek Nemzeti
Tanácsa, National Council of Wine Communities) or in Magyar Közlöny;
researching a public, licence-clear URL pattern for it — and adding
a national-spec parser branch — is Phase 2 work (it also unlocks the
dűlő sub-denominations). For now:

```
.venv/bin/python scripts/hu/regen_manual_overrides_template.py
# edit raw/hu/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear specification (EUR-Lex OJ-C page, HNT / Magyar Közlöny
# national termékleírás).
.venv/bin/python scripts/hu/01_fetch_pliegos.py
.venv/bin/python scripts/hu/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML parser only understands the EU-OJ
EGYSÉGES DOKUMENTUM template; HNT / Magyar Közlöny national-
specification formats need a per-source parser (Phase 2, mirrors the
ES MAPA / IT MASAF pattern).

## Romania pipeline (`scripts/ro/`)

Country #9. **46 wine GIs (34 DOP + 12 IGP)** from eAmbrosia after
de-duplicating administrative re-registrations (the same wine — e.g.
Murfatlar, Dealu Mare, Panciu — has both its 2007-protected entry and
later modification entries, all `status=registered`; stage 00 keeps the
one with publications + the most recent modification date). **32 / 46
carry a fetchable `publications[].uri`**; the other 14 are Art.107 /
Reg.1308/2013 grandfathered names with only `Ares(…)` references —
**fully covered by the ONVPV national-spec layer** (stage 01c/02f, see
below). **v1 coverage: 46 / 46 on the map, 0 stubs.** Structurally a
near-verbatim clone of the HR template — EU-OJ single-document HTML in
Romanian, Latin script with diacritics, Bétard PDO geometry — with
**three real deltas**:

- **12 IGPs** (HR had zero, HU has 5 region-union ones). Bétard is
  PDO-only, so Romanian IGPs and the 3 newer PDOs missing from Bétard
  (Sebeș-Apold, Plaiurile Drâncei, Iana) resolve via a new
  `gisco-commune-list` step that parses the DOCUMENT UNIC section-6
  commune list and unions matching `RO_*` GISCO LAU polygons against
  the shared `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (3,181 RO
  communes). Same shape as the ES IGP-fallback chain.
- **DOCUMENT UNIC anchor + Romanian section keywords** —
  `scripts/_lib/ro/document_unic.py` carries the section-role keyword
  tables (*Denumire / Aria geografică delimitată / Soiul de struguri /
  Descrierea legăturii / Alte condiții esențiale*); the HTML-slice
  machinery is identical to HR/SI/AT. The newer Reg. 2024/1143
  template moves the area to section 9 ("Descrierea concisă a arealului
  geografic delimitat") behind a "Țara căreia îi aparține…" → "România"
  decoy (blocklisted); a density-based commune fallback in stage 02
  (`_harvest_communes_fallback`) recovers the list when the PDF→HTML
  conversion mangles section numbering.
- **ONVPV national-spec layer** (stage 01c/02f) — the 14 grandfathered
  wines are augmented from the Oficiul Național al Viei și Produselor
  Vitivinicole caiet de sarcini (see the dedicated section below). This
  is the RO analogue of the ES MAPA / IT MASAF / GR ΥΠΑΑΤ / HR–SI
  national-spec layer.

Spine: **eAmbrosia EU register**, filtered `country=RO` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"DOCUMENT UNIC"** (and older `DOCUMENTUL UNIC` modification-
preamble form) published inline as HTML, reached via each GI's
`publications[].uri` (Romanian-language URL rewrite — `/oj/ron`,
`legal-content/RO/TXT/HTML/`, `…01.RON`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR/HU — `scripts/ro/01b_solve_waf.py` clears blocked URLs
with headless Chromium.

| Script | Reads | Writes |
|---|---|---|
| ro/00_fetch_data.py | (network: eAmbrosia) | raw/ro/eambrosia/index.json + manifest.json |
| ro/01_fetch_pliegos.py | raw/ro/eambrosia/index.json + raw/ro/oj-pages/manual_overrides.json | raw/ro/oj-pages/*.html + manifest.json |
| ro/01b_solve_waf.py | raw/ro/oj-pages/manifest.json | raw/ro/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| ro/01c_fetch_specifikacije.py | raw/ro/national-specs/manual_overrides.json | raw/ro/national-specs/*.pdf + manifest.json (ONVPV caiete) |
| ro/02_extract_pliegos.py | raw/ro/oj-pages/*.html | raw/ro/dokumente-extracted/*.json + _index.json (+ `geo_communes` per record) |
| ro/02f_extract_national_specs.py | raw/ro/national-specs/*.pdf | raw/ro/national-specs-extracted/*.json + _index.json |
| ro/02d_extract_terroir_facts.py | raw/ro/dokumente-extracted/*.json + raw/wikipedia/aocs/ro/ | raw/terroir-facts/*.json (country="ro") + manifest-ro.json |
| ro/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="ro") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| ro/03_generate_wiki.py | raw/ro/dokumente-extracted/*.json | wiki/<slug>.md (per RO record) + merges RO entries into wiki/_index.json |
| ro/regen_manual_overrides_template.py | raw/ro/eambrosia/index.json + raw/ro/oj-pages/manifest.json | raw/ro/oj-pages/manual_overrides.json (curator queue) |
| audit_ro_coverage.py | raw/ro/eambrosia/ + raw/ro/dokumente-extracted/ + raw/ro/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + IGP commune-list coverage + curator queue) |

RO-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/HU).
  `country` is `"ro"`; `source_lang` is also `"ro"` (matches HR/ES/PT
  /IT — country code equals language code, unlike AT/SI which differ).
- The Romanian DOCUMENT UNIC template is parsed by
  `scripts/_lib/ro/document_unic.py` (Romanian section-keyword role
  routing — *Denumire / Aria geografică delimitată / Soiul de struguri
  / Descrierea legăturii / Alte condiții esențiale*). HTML-slice
  machinery is identical to ES/IT/AT/SI/HR/HU.
- The grape-variety section enumerates one variety per em-dash-bulleted
  line; the canonical Romanian name is the segment before a `-`
  synonym separator (`Fetească Albă - Mädchentraube` → *Fetească
  Albă*). Romanian native varieties (Fetească Albă/Regală/Neagră,
  Tămâioasă Românească, Grasă de Cotnari, Băbească Neagră, Negru de
  Drăgășani, Crâmpoșie Selecționată, Frâncușă, Plăvaie, Galbenă de
  Odobești, Zghihară de Huși, Șarbă, Mustoasă de Măderat, Busuioacă de
  Bohotin, Novac, …) are folded into the shared `GRAPE_ALIAS` /
  `DEFAULT_COLOUR` tables in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).
  Tămâioasă Românească folds to `muscat-blanc-a-petits-grains` per the
  VIVC synonym chain.
- v1 models the 46 wine GIs as a **flat corpus** — Romanian DOCs do
  not have a structured DGC / subzona / sottozona analogue (rare
  cru-like designations like Cotnari's "Grasă de Cotnari" are
  variety-restricted single-vineyards, not sub-denominations). The
  caiet de sarcini does enumerate *denumiri de plai viticol* per
  appellation (Aiud → CIUMBRUD, SÂNCRAI, …), harvestable as a future
  sub-denomination layer; deferred in v1.
- Region facet = **regiune viticolă**
  ([scripts/_lib/ro/region.py](scripts/_lib/ro/region.py)): the 8
  Romanian macro wine regions (*Moldova, Muntenia, Oltenia, Dobrogea,
  Transilvania, Banat, Crișana și Maramureș, Terasele Dunării*).
  Region labels follow the AT/IT/ES/SI/HR/HU convention — shown in
  the native form, not gettext-translated. The
  `_REGION_BY_FILE_NUMBER` map is incremental — added to as the audit
  surfaces wines whose region didn't resolve from the documento-unic
  text scan.
- Stage 02d/02e wire terroir-fact extraction + translation for RO
  (siblings of the ES/PT/IT/AT/SI/HR pairs). Dual-source grounding
  (DOCUMENT UNIC section 8 — or, for the 14 grandfathered stubs, the
  ONVPV caiet's §II *Legătura cu aria geografică* via the stage-02f
  sidecar, mirroring the GR/IT terroir backfill — plus
  ro.wikipedia.org per-DOP page when one exists), Romanian extraction
  prompt, fuzzy-coverage filter (≥ 0.6), per-bullet provenance, manual
  round-trip flow. 02e targets en/fr/es/nl. **ro.wikipedia coverage is
  thin** (the Switzerland situation): 43 of 46 appellations have no
  dedicated *Podgoria X* article — only the town/commune article (which
  `looks_like_aoc` rejects) or a redlink — so they're curator-pinned
  `missing` in `raw/wikipedia/aoc_overrides.json["ro"]` and RO facts
  ground on the cahier/caiet text. All 46 wines carry 7–10 facts.

### RO geometry resolution chain (stage 04)

Per RO record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-RO-*`) → `PDOid`
   match against Bétard 2022 EU_PDO.gpkg. Covers 33 of the 34 RO PDOs.
2. **`gisco-commune-list`** — fallback for the 12 RO IGPs (Bétard is
   PDO-only) and the newer PDOs missing from Bétard (Sebeș-Apold,
   Plaiurile Drâncei, Iana). [scripts/_lib/ro/commune.py](scripts/_lib/ro/commune.py)
   parses the area commune list (handling Romanian municipal-tier
   prefixes — *municipiul / orașul / comuna / satul* — *judeţul X:*
   headers, *X cu satele/localităţile componente Y, Z* descriptor
   tails, and parenthetical *(satele …)* sub-village groups);
   [scripts/_lib/ro/geometry.py](scripts/_lib/ro/geometry.py)
   `ROPolygonIndex.commune_union` unions the matching GISCO LAU
   polygons. The list comes from the DOCUMENT UNIC for non-stub wines
   and from the **ONVPV caiet de sarcini** (stage 02f sidecar, merged
   into `record["geo_communes"]` at load time) for the 2 grandfathered
   IGPs — Dealurile Transilvaniei + Viile Caraşului. Same shape as the
   ES IGP-fallback chain.
3. **`stub-no-geometry`** — not hit in v1; all 46 RO wines resolve.

The shared `raw/es/figshare/EU_PDO.gpkg` and
`raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` are re-used — no new
stage-00 download.

### RO national-spec layer (stages 01c + 02f)

The 14 grandfathered RO wines (eAmbrosia carries only a non-fetchable
`Ares(…)` reference — no EU-OJ DOCUMENT UNIC) would ship as bare stubs
without a national-spec layer. Their canonical source is the
**ONVPV** (Oficiul Național al Viei și Produselor Vitivinicole)
*caiet de sarcini*, published as a PDF on `onvpv.ro` (the regulator's
DOC + IG caiete-de-sarcini index pages). The host is plain HTTP/HTTPS
and **WAF-free** — no Playwright bootstrap needed.

- **Stage 01c** ([scripts/ro/01c_fetch_specifikacije.py](scripts/ro/01c_fetch_specifikacije.py))
  fetches each curator-pinned URL from
  `raw/ro/national-specs/manual_overrides.json` (slug → `{url,
  source_org: onvpv, file_number, format}`) into
  `raw/ro/national-specs/<slug>.pdf` + manifest (sha256, fetched_at).
- **Stage 02f** ([scripts/ro/02f_extract_national_specs.py](scripts/ro/02f_extract_national_specs.py))
  runs `pdftotext -layout` and parses via
  [scripts/_lib/ro/caiet.py](scripts/_lib/ro/caiet.py)
  (`onvpv-caiet-de-sarcini-v1`). The caiet is a uniform Roman-numeral
  outline (`I. Definiţie` → summary, `II. Legătura cu aria geografică`
  → terroir, `III. Delimitarea geografică` → commune list via the
  shared `parse_commune_list`, `IV. Soiurile de struguri` → grapes by
  colour header `Soiurile albe:` / `Soiuri roşii:`). Form-feeds are
  folded to newlines so a page-break before a section header doesn't
  let one section swallow the next, and colour segments are joined
  line-wise (not per-line) so a variety name wrapped across two
  pdftotext lines — `…Riesling\nItalian` — isn't sheared. Sidecars
  land in `raw/ro/national-specs-extracted/<slug>.json` with full
  provenance.
- **Stage 04** `augment_ro_records_with_national_specs()` merges the
  sidecar's summary / grapes / **geo_communes** / link_to_terroir /
  styles / section_roles into the in-memory stub record at load time
  (the on-disk DOCUMENT UNIC stub stays immutable); `stub_reason` is
  prefixed `national-spec:`; `_sources_for()` surfaces `national_spec_*`
  provenance. The geo_communes merge is the RO-specific delta vs.
  GR/HR — it drives the GISCO commune-union geometry for the 2
  grandfathered IGPs. **02d** grounds terroir-fact extraction on the
  sidecar's §II Legătura text when the on-disk record is a stub.

Result: **14 / 14 grandfathered wines augmented** — grapes (9–18 each),
commune geometry, 7–10 terroir facts. Re-runnable:
```
.venv/bin/python scripts/ro/01c_fetch_specifikacije.py
.venv/bin/python scripts/ro/02f_extract_national_specs.py --all
.venv/bin/python scripts/ro/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/ro/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/04_build_maps.py
```

### Curator workflow for new RO wines

If a new RO grandfathered wine appears, or an ONVPV URL rotates, add it
to `raw/ro/national-specs/manual_overrides.json` (slug → `{url,
source_org, file_number, format}`) and re-run 01c → 02f → 02d → 02e →
04. The EU-OJ `regen_manual_overrides_template.py` flow still applies
if the Commission later publishes a real DOCUMENT UNIC.

**Caveat**: the ONVPV caiet parser is PDF-only (`onvpv-caiet-de-
sarcini-v1`); a BOE-style / Monitorul-Oficial format would need its
own parser branch.

## Bulgaria pipeline (`scripts/bg/`)

Country #10. **The first Cyrillic-script country in the corpus.** 54
wine GIs from eAmbrosia: 52 PDOs + 2 macro PGIs (Дунавска равнина /
Тракийска низина — the two halves of the country, north vs south of
Stara Planina). Structurally a near-verbatim clone of the SI template
(Bétard PDO + region-pdo-union for the IGPs), but with a real delta —
**all string handling, slug generation, name matching, and grape
variety lookup pass through `unidecode`** so Cyrillic input romanises
deterministically to Latin-ASCII slugs. Slug examples: Мелник →
`melnik`, Тракийска низина → `trakiiska-nizina`, Долината на Струма →
`dolinata-na-struma`. Latin-script input is invariant under
`unidecode` — verified safe for the 9 pre-BG corpora.

Spine: **eAmbrosia EU register**, filtered `country=BG` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"ЕДИНЕН ДОКУМЕНТ"** published inline as HTML, reached via each GI's
`publications[].uri` (Bulgarian-language URL rewrite — `/oj/bul`,
`legal-content/BG/TXT/HTML/`, `…01.BUL`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR/HU/RO — `scripts/bg/01b_solve_waf.py` clears blocked
URLs with headless Chromium (none triggered on the first stage-01 run,
but the bootstrap remains available for re-fetches).

Coverage in the corpus mirrors SI/HR — only **3 of the 54** BG wines
(Мелник, Нова Загора, Дунавска равнина) carry a fetchable EU single
document. The other 51 are Art.107 / Reg.1308/2013 grandfathered names
with only `Ares(...)` summary-sheet references — they ship as content-
stubs (the IT/ES/SI/HR/HU/RO curator-queue pattern) and nonetheless
appear on the map because Bétard 2022 carries every BG PDO (Bulgaria
entered the EU in 2007; everything predates the dataset's Nov-2021
cutoff). v1 geometry coverage = **100 %** of records.

| Script | Reads | Writes |
|---|---|---|
| bg/00_fetch_data.py | (network: eAmbrosia) | raw/bg/eambrosia/index.json + manifest.json |
| bg/01_fetch_pliegos.py | raw/bg/eambrosia/index.json + raw/bg/oj-pages/manual_overrides.json | raw/bg/oj-pages/*.html + manifest.json |
| bg/01b_solve_waf.py | raw/bg/oj-pages/manifest.json | raw/bg/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| bg/02_extract_pliegos.py | raw/bg/oj-pages/*.html | raw/bg/dokumenti-extracted/*.json + _index.json |
| bg/01c_fetch_specifikacije.py | raw/bg/national-specs/manual_overrides.json | raw/bg/national-specs/*.pdf + manifest.json |
| bg/02f_extract_national_specs.py | raw/bg/national-specs/*.pdf + raw/bg/national-specs/manual_overrides.json | raw/bg/national-specs-extracted/*.json + _index.json + manifest.json + raw/bg/extraction-unknowns-specifikacije.json |
| bg/02d_extract_terroir_facts.py | raw/bg/dokumenti-extracted/*.json + raw/bg/national-specs-extracted/ + raw/wikipedia/aocs/bg/ | raw/terroir-facts/*.json (country="bg") + manifest-bg.json |
| bg/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="bg") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| bg/03_generate_wiki.py | raw/bg/dokumenti-extracted/*.json | wiki/<slug>.md (per BG record) + merges BG entries into wiki/_index.json |
| bg/regen_manual_overrides_template.py | raw/bg/eambrosia/index.json + raw/bg/oj-pages/manifest.json | raw/bg/oj-pages/manual_overrides.json (curator queue) |
| audit_bg_coverage.py | raw/bg/eambrosia/ + raw/bg/dokumenti-extracted/ + raw/bg/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

BG-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/HU/RO).
  `country` is `"bg"`; `source_lang` is also `"bg"` (matches HR/ES/PT/
  IT/HU/RO — country code equals language code, unlike AT/SI).
- The Bulgarian ЕДИНЕН ДОКУМЕНТ template is parsed by
  [scripts/_lib/bg/edinen_dokument.py](scripts/_lib/bg/edinen_dokument.py)
  (Bulgarian section-keyword role routing — *Наименование на продукта*,
  *Категории лозаро-винарски продукти*, *Описание на виното или вината*,
  *Винопроизводствени практики*, *Определен географски район*,
  *Винен(и) сорт(ове) грозде*, *Описание на връзката или връзките*,
  *Други специфични изисквания*). The HTML-slice machinery is identical
  to ES/IT/AT/SI/HR/HU/RO. Like HU, BG publications occasionally nest
  per-variety subsections inside section 4 (Описание) using the same
  `<p class="ti-grseq-1">` markup that real top-level sections use;
  the monotonic-number + section-role-keyword-match guard in
  `extract_sections` filters them so sections 5–9 don't get shadowed.
- The grape-variety section enumerates one variety per line as
  `Cyrillic name - Latin synonym`; stage 02 splits on hyphen for
  `Name - synonym`. Bulgarian native varieties (Мавруд, Широка
  мелнишка лоза, Памид, Димят, Червен Мискет, Тамянка, Сандански
  Мискет, Керацуда, Ркацители, Гъмза, Богдан, Рубин, Руен,
  Мелник 55 / Мелник 82, Мелнишки рубин, …) are folded into the
  shared `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables in
  [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) with
  their Latin-transliteration slugs (round-trip via `unidecode`).
  Гъмза folds to `kadarka` (same DNA), Тамянка folds to
  `muscat-blanc-a-petits-grains`.
- v1 models the 54 wine GIs as a **flat corpus** — Bulgarian wine law
  doesn't define sub-denominations within the PDOs.
- Region facet = **винарски район**
  ([scripts/_lib/bg/region.py](scripts/_lib/bg/region.py)): the 5
  traditional Bulgarian wine regions (Дунавска равнина, Черноморски
  район, Розова долина, Тракийска низина, Долината на Струма). The 2
  EU PGIs share names with two of the 5 wine regions — Дунавска
  равнина PGI = the entire Northern wine region of the same name;
  Тракийска низина PGI covers the four southern regions combined. Hand-
  verified curated `_REGION_BY_FILE_NUMBER` covers all 54 wines.
  Region labels follow the AT/IT/ES/SI/HR/HU/RO convention — native
  Cyrillic form, not gettext-translated.
- Cyrillic-preserving commune-name matching: [scripts/_lib/bg/commune.py](scripts/_lib/bg/commune.py)
  uses `.casefold()` (not NFKD-ASCII-encode — which would erase
  Cyrillic) so both sides of the GISCO `LAU_NAME` lookup stay in
  Cyrillic. Settlement-tier prefixes (`с.` / `гр.` / `село` / `град`)
  drop the chunk entirely so only the parent община survives.
  Province (област) markers are consumed with their trailing name so
  the 28 oblast-name capitals (which are themselves obshtini —
  Пловдив, Бургас, Варна, Сливен, …) survive as obshtina candidates.
- Stage 02d/02e wire terroir-fact extraction + translation for BG
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO pairs). Dual-source
  grounding (ЕДИНЕН ДОКУМЕНТ section 8 + bg.wikipedia.org per-PDO
  page), Bulgarian extraction prompt with terroir vocabulary
  (чернозем, канелена горска почва, смолница, льос, мергел, варовик,
  Стара планина, Родопи, Странджа, Черно море, понтийско влияние,
  фьон, …), fuzzy-coverage filter (≥ 0.6), per-bullet provenance,
  manual round-trip flow. 02e targets en/fr/es/nl. Bulgarian source-
  locale wine-law terms preserved verbatim include ЗНП / ЗГУ / ИАЛВ /
  продуктова спецификация / Държавен вестник.

### BG geometry resolution chain (stage 04)

Per BG record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-BG-*`) → `PDOid`
   match against Bétard 2022 EU_PDO.gpkg. Covers all 52 BG PDOs. The
   shared `raw/es/figshare/EU_PDO.gpkg` — no new fetch in stage 00.
2. **`region-pdo-union`** — the 2 BG PGIs (Дунавска равнина PGI =
   21 northern PDOs; Тракийска низина PGI = 31 southern PDOs) = union
   of member-PDO Figshare polygons (SI PGI pattern). Member tables
   live in `BG_PGI_MEMBER_PDOS`
   ([scripts/_lib/bg/geometry.py](scripts/_lib/bg/geometry.py)),
   hand-verified against the Bulgarian wine-law 5-region structure
   and the north/south Stara Planina partition.
3. **`gisco-commune-list`** — defensive fallback (rare in v1) parsing
   `geo_communes` from section 6 area body via
   [scripts/_lib/bg/commune.py](scripts/_lib/bg/commune.py) and
   unioning matching `BG_*` GISCO LAU polygons (~265 obshtini, shared
   `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`).
4. **`stub-no-geometry`** — last resort. Not hit in v1; all 54 wines
   resolve.

### BG national specifikacija layer (stages 01c + 02f)

Because only 3 of 54 BG wines carry a fetchable EU-OJ ЕДИНЕН ДОКУМЕНТ
(every other wine is an Art.107 / Reg.1308/2013 grandfathered name with
only an `Ares(...)` reference in eAmbrosia), the corpus would ship as 51
bare stubs without a national-spec layer. The canonical source —
resolved 2026-05-30 via `/research-gaps` — is the **ИАЛВ / IAVV
(Изпълнителна агенция по лозата и виното) per-wine продуктова
спецификация**, published as a PDF on the eavw.com WebSphere WCM store
and listed at
`…/legislation/wines.with.pdo.and.pgi/specifications.of.wines.with.pdo.and.pgi`.
Official act of a state administration body → ЗАПСП Art. 4 copyright
exemption; reuse with attribution to ИАЛВ. URLs are pinned in
[raw/bg/national-specs/manual_overrides.json](raw/bg/national-specs/manual_overrides.json)
(slug → `{url, source_org: "iavv", file_number, format: "pdf", note}`);
the UUID/CVID tokens are opaque (read off the listing page) — re-pull
the listing if a token rotates and a fetch 404s.

The spec is a stable numbered template (1–8), parsed by
[scripts/_lib/bg/specifikacija.py](scripts/_lib/bg/specifikacija.py)
over `pdftotext -layout` output:

  1. Наименование · 2. описание на вината · 3. район (commune list) ·
  4. максимален добив · **5. винени сортове грозде** (grapes, colour-split
  `за бели вина` / `за червени вина( и розе)` / `за розе`) ·
  **6. Връзка с географския район** (terroir: а) Природни / б) Човешки
  фактори) · 7. приложими изисквания · 8. контролен орган

Grapes resolve via the shared `_lib.grape_entity.match_variety`; all are
`principal` (no role split in BG, same as PT/IT/HR). String handling is
Cyrillic-preserving (`.casefold()`, never NFKD-ASCII). Unknown varieties
flow to
[raw/bg/extraction-unknowns-specifikacije.json](raw/bg/extraction-unknowns-specifikacije.json)
for the `GRAPE_ALIAS` / `DEFAULT_COLOUR` vocab-curation pattern — the
2026-05-30 pass added 18 BG breeding-station crossings / old natives
(Евмолпия, Тракийска слава, Шевка, Ахелой, Хеброс, Орфей, Кукленски
мавруд, Септемврийски рубин, the Black-Sea + Misket crossings, Ризлинг
български, …) with researched colours, plus 9 international folds
(Гъмза→kadarka, Юни блан→ugni-blanc, Сензо→cinsault, Мьоние→meunier,
Мюлер тюргао→muller-thurgau, Харш Лавелю→harslevelu, …). `ъ`/`ь`
render as an apostrophe under unidecode (Гъмза → `g'mza`), so those
alias keys carry the apostrophe rather than the slugify-hyphen form.

Stage 02f
([scripts/bg/02f_extract_national_specs.py](scripts/bg/02f_extract_national_specs.py))
writes one sidecar JSON per wine under `raw/bg/national-specs-extracted/`
with full provenance (URL, sha256, format, parser_template
`iavv-specifikacija-v1`). Stage 04's
`augment_bg_records_with_national_specs()`
([scripts/04_build_maps.py](scripts/04_build_maps.py)) merges the
sidecar's summary / grapes / geo_area / link_to_terroir / styles /
section_roles into each in-memory BG stub at load time (the on-disk
dokumenti-extracted JSON stays immutable); `stub_reason` is prefixed
`national-spec:` so the audit distinguishes EU-OJ-extracted from
spec-augmented wines, and `_sources_for()` surfaces `national_spec_*`
provenance. BG 02d's `_resolve_lien_and_source` reads the sidecar's
section-6 terroir text when the on-disk record's `link_to_terroir` is
empty, so terroir-fact extraction grounds against the IAVV spec.

Result: **51 / 51 stubs augmented; all 54 BG wines carry grapes (418
principal slugs) + section-6 terroir source text**. Terroir-fact
extraction (02d/02e, Anthropic batch) then grounds on that text.

Re-runnable per slug or sweep:
```
.venv/bin/python scripts/bg/01c_fetch_specifikacije.py
.venv/bin/python scripts/bg/02f_extract_national_specs.py --slug pomorie
.venv/bin/python scripts/bg/02f_extract_national_specs.py --all
.venv/bin/python scripts/04_build_maps.py
```
Cached PDFs at `raw/bg/national-specs/<slug>.pdf` are reused unless
`--refresh` is passed.

### Curator workflow for BG wines without an OJ publication

All 51 grandfathered names are covered by the ИАЛВ specifikacija layer
above (researched 2026-05-30). If a new BG wine appears, or an IAVV
UUID/CVID token rotates, add/refresh it in
`raw/bg/national-specs/manual_overrides.json` (slug → `{url, source_org,
file_number, format, note}`) and re-run 01c → 02f → 04. The EU-OJ
`regen_manual_overrides_template.py` flow still applies if the Commission
later publishes a real ЕДИНЕН ДОКУМЕНТ (which would add the EU-OJ
narrative sections stage 02 parses directly):

```
.venv/bin/python scripts/bg/regen_manual_overrides_template.py
# edit raw/bg/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear EUR-Lex OJ-C single-document page.
.venv/bin/python scripts/bg/01_fetch_pliegos.py
.venv/bin/python scripts/bg/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML parser only understands the EU-OJ ЕДИНЕН
ДОКУМЕНТ template; the IAVV PDF specs ride the parallel 01c/02f layer
(kept OUT of `raw/bg/oj-pages/manual_overrides.json` so a PDF never
enters the HTML path — the HR/SI lesson).

## Greece pipeline (`scripts/gr/`)

Country #11. **147 wine GIs (33 PDO + 114 PGI)** from eAmbrosia. The
most stub-heavy corpus to date — only **9 of 147** wines (Mantinia,
Naoussa, Santorini-mod, Tyrnavos, Epanomi, Evia, Plagies Paikou,
Ayio Oros, Robola Kefallinias) carry a fetchable EU single document.
The remaining 138 are Art.107 / Reg.1308/2013 grandfathered names
whose only eAmbrosia reference is a non-fetchable `Ares(...)`
summary-sheet. Nonetheless, **all 33 GR PDOs land on the map** via
Bétard 2022 (Greece joined the EU in 1981, so every PDO predates the
Nov-2021 cutoff). The 114 PGIs are not in Bétard (PDO-only dataset) but
all land on the map via the `gisco-nuts-region` fallback (112) + the
commune-list fallback (2) — every one of the 147 GR wines now carries a
polygon (0 `stub-no-geometry`; see the geometry chain below). The first
**non-Latin-script** country in the corpus —
eAmbrosia ships an EU-official Latin **`transcriptions[0]`** field
per record (`Ραψάνη` → `Rapsani`, `Σαντορίνη` → `Santorini`, …) which
the stage-00 slugifier uses as authoritative.

Spine: **eAmbrosia EU register**, filtered `country=GR` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ"** published inline as HTML, reached via each GI's
`publications[].uri` (Greek-language URL rewrite — `/oj/ell`,
`legal-content/EL/TXT/HTML/`, `…01.ELL`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR/HU/RO/BG — `scripts/gr/01b_solve_waf.py` clears blocked
URLs with headless Chromium (none blocked on first stage-01 run).

| Script | Reads | Writes |
|---|---|---|
| gr/00_fetch_data.py | (network: eAmbrosia + GISCO NUTS-3) | raw/gr/eambrosia/index.json + manifest.json, raw/gr/nuts/NUTS_RG_03M_2024_4326_LEVL_3.geojson |
| gr/01_fetch_pliegos.py | raw/gr/eambrosia/index.json + raw/gr/oj-pages/manual_overrides.json | raw/gr/oj-pages/*.html + manifest.json |
| gr/01b_solve_waf.py | raw/gr/oj-pages/manifest.json | raw/gr/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| gr/02_extract_pliegos.py | raw/gr/oj-pages/*.html | raw/gr/dokumenti-extracted/*.json + _index.json |
| gr/01c_fetch_specifikacije.py | raw/gr/national-specs/manual_overrides.json | raw/gr/national-specs/*.{pdf,doc,docx} + manifest.json |
| gr/02f_extract_national_specs.py | raw/gr/national-specs/*.{pdf,doc,docx} + owm-antiword Docker image | raw/gr/national-specs-extracted/*.json + _index.json |
| gr/02d_extract_terroir_facts.py | raw/gr/dokumenti-extracted/*.json + raw/gr/national-specs-extracted/ + raw/wikipedia/aocs/el/ | raw/terroir-facts/*.json (country="gr") + manifest-gr.json |
| gr/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="gr") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| gr/03_generate_wiki.py | raw/gr/dokumenti-extracted/*.json | wiki/<slug>.md (per GR record) + merges GR entries into wiki/_index.json |
| gr/regen_manual_overrides_template.py | raw/gr/eambrosia/index.json + raw/gr/oj-pages/manifest.json | raw/gr/oj-pages/manual_overrides.json (curator queue) |
| audit_gr_coverage.py | raw/gr/eambrosia/ + raw/gr/dokumenti-extracted/ + raw/gr/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

GR-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/HU
  /RO/BG). `country` is `"gr"`; `source_lang` is `"el"` — like AT
  (`at`/`de`) and SI (`si`/`sl`), GR's country code differs from its
  language code.
- The Greek ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ template is parsed by
  [scripts/_lib/gr/eniaio_engrafo.py](scripts/_lib/gr/eniaio_engrafo.py)
  (Greek section-keyword role routing — *Ονομασία προς καταχώριση*,
  *Οριοθετημένη γεωγραφική ζώνη*, *Κύρια οινοποιήσιμη ποικιλία ή
  ποικιλίες σταφυλιού*, *Περιγραφή του δεσμού*, *Άλλες ουσιώδεις
  προϋποθέσεις* …). The HTML-slice machinery is identical to
  ES/IT/AT/SI/HR/HU/RO/BG with one critical addition — a
  **`greek_norm`** comparator key that casefolds + strips diacritics
  (Greek polytonic + monotonic both decompose via NFKD; combining
  marks dropped) + folds the **final sigma** `ς` to `σ`. Without
  final-sigma folding, `.casefold()` of capital Σ produces medial σ
  while keywords typed with final ς never match — Mantinia's section
  7 (`Κυριότερες οινοποιήσιμες ποικιλίες`) was the first hit.
- The grape-variety section lists one variety per line with the
  international OIV colour code `Β` / `Ν` / `Rs` / `Rg` / `Γ`
  (Greek capitals glyph-identical to Latin `B` / `N` / `Rs` / `Rg`
  / `G`). [scripts/_lib/grape_entity.py](scripts/_lib/grape_entity.py)
  `_COLOUR_LETTER_RE` lookbehind allows Greek lowercase letters; the
  trailing letter alternation accepts both Greek (`Β`/`Ν`/`Γ`) and
  Latin forms. Native Greek varieties (Ασύρτικο/Assyrtiko,
  Ξινόμαυρο/Xinomavro, Αγιωργίτικο/Agiorgitiko, Μοσχοφίλερο/
  Moschofilero, Ροδίτης/Roditis, Ρομπόλα/Robola, Σαββατιανό/
  Savatiano, Μαλαγουζιά/Malagousia, Λημνιό/Limnio, Λημνιώνα/Limniona,
  Μαυροδάφνη/Mavrodaphne, Μανδηλαριά/Mandilaria, Κοτσιφάλι/Kotsifali,
  Λιάτικο/Liatiko, Βιδιανό/Vidiano, Βιλάνα/Vilana, Αθήρι/Athiri,
  Αηδάνι/Aidani, Θραψαθήρι/Thrapsathiri, Ντεμπίνα/Debina, Νεγκόσκα/
  Negoska, Σταυρωτό/Stavroto, Κρασάτο/Krasato, Μπατίκι/Batiki, …)
  are folded into the shared `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables
  in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) —
  both the Greek-script form and its `unidecode()` romanisation
  (`asurtiko`, `ksinomauro`, `rompola`, `maurodaphne`, …) map to the
  English canonical slug (the form VIVC + most wine-science refs use).
- v1 models the 147 wine GIs as a **flat corpus** — no sub-
  denomination layer.
- Region facet = **αμπελουργική ζώνη**
  ([scripts/_lib/gr/region.py](scripts/_lib/gr/region.py)): the 9
  Greek macro wine regions (*Μακεδονία, Θράκη, Θεσσαλία, Ήπειρος,
  Στερεά Ελλάδα, Πελοπόννησος, Ιόνια Νησιά, Νησιά Αιγαίου, Κρήτη*).
  The curated `_REGION_BY_FILE_NUMBER` map covers every PDO at v1;
  PGIs fall back to text scan + `Ελλάδα`. Region labels follow the
  AT/IT/ES/SI/HR/HU/RO/BG convention — shown in the native form (with
  monotonic accentuation), not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for GR
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG pairs). Dual-source
  grounding (Ενιαίο Έγγραφο section 8 + el.wikipedia.org per-PDO
  page), Greek extraction prompt with terroir vocabulary (καλντέρα,
  ηφαιστειακά εδάφη, ασβεστόλιθος, σχιστόλιθος, μάργες, αμμοχαλικώδες,
  μεσογειακό κλίμα, μελτέμια, κουλούρα, ξερολιθιές, …), fuzzy-coverage
  filter (≥ 0.6), per-bullet provenance, manual round-trip flow.
  02e targets en/fr/es/nl. Cache files land in the shared
  `raw/terroir-facts/` directory with `country: "gr"`. Greek
  wine-style traditional terms preserved verbatim by 02e include
  Vinsanto, Νυχτέρι, Λιαστός οίνος, οίνος γλυκός φυσικός (vin doux
  naturel), όψιμη συγκομιδή, αφρώδης οίνος.

### GR geometry resolution chain (stage 04)

Per GR record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-GR-*`) → `PDOid`
   match against Bétard 2022 EU\_PDO.gpkg. Covers all 33 GR PDOs.
   Runs even for content-stubs, so well-known PDOs like Σαντορίνη,
   Νεμέα, Νάουσα, Μαντινεία, Σάμος, and the 7 Cretan PDOs appear on
   the map though their ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ isn't accessible.
2. **`gisco-commune-list`** — parse the documento-unic section-6
   area body into δήμος / κοινότητα names (Greek-preserving) and
   union matching GISCO LAU `EL_*` polygons (CNTR_CODE='EL' — the
   EU country code for Greece, *not* ISO `GR`). Only the 2 EU-OJ
   PGIs with an enumerated list resolve here. ~6,142 Greek δημοτική
   κοινότητα polygons in GISCO LAU 2024.
3. **`gisco-nuts-region`** — the PGI fallback. The national-spec
   "Οριοθετημένη περιοχή" section does NOT enumerate δήμοι — it
   delimits the area by reference to the founding ministerial decrees
   plus a NUTS code + regional-unit / region name (`GR232 Αχαΐα`,
   `GR30 Αττική`). So the honest geometry is the GISCO NUTS polygon
   for that unit — exactly what the spec legally delimits.
   [scripts/_lib/gr/nuts.py](scripts/_lib/gr/nuts.py) resolves it:
   curated `slug → [NUTS_ID]` override → the spec's cited NUTS name →
   appellation name → region facet, matched (Greek-normalised,
   island-list-token-aware) against GISCO NUTS-3 (52 EL regional
   units) + NUTS-2 (13 EL regions). `GRPolygonIndex` unions the
   matched NUTS polygons. The curated override carries the residual
   that strict name-match misses — the Attica retsina/town cluster
   (→ EL30 Αττική), the Cyclades / Dodecanese (NUTS-3 labelled by
   island list), and Μακεδονία (→ EL51+EL52+EL53 unioned). Resolves
   **112 of 114 PGIs**; honest precision is regional-unit-level, not
   commune-level.
4. **`stub-no-geometry`** — last resort. Not hit in v1; all 147 GR
   wines resolve to a polygon.

The shared `raw/es/figshare/EU_PDO.gpkg`,
`raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`, and the NL pipeline's
NUTS-2 GeoJSON are re-used; only the GISCO NUTS-3 layer
(`raw/gr/nuts/NUTS_RG_03M_2024_4326_LEVL_3.geojson`, © European Union
/ Eurostat GISCO) is newly fetched in stage 00.

### Curator workflow for GR wines without an OJ publication

138 of 147 GR wines are grandfathered names with only an `Ares(...)`
reference. Their canonical source is the national **προδιαγραφή
προϊόντος** / **τεχνικός φάκελος** published by ΥΠΑΑΤ (Greek Ministry
of Rural Development and Food) on minagric.gr. A `/research-gaps gr
stubs` sweep (2026-05-29) resolved **132 of 138** to that source
(0 EUR-Lex single documents exist — every file_number search returns
only the unrelated EU-Kosovo SAA annex); the 6 unresolved are in the
Greece section of [CURATOR_TODO.md](CURATOR_TODO.md).

### GR national-spec layer (stages 01c + 02f)

Because the EU-OJ path covers only 9 of 147 wines, the bulk of the GR
corpus is filled from the ΥΠΑΑΤ national spec via a parallel layer
(the ES MAPA / IT MASAF / DE BLE / HR–SI specifikacije pattern):

- **Host caveat**: the canonical reachable host is the legacy four-w
  host `http://wwww.minagric.gr/greek/data/pop-pge/` (four w's, plain
  HTTP) — `https://www.minagric.gr` and `minagric.gov.gr` are
  Akamai-WAF-blocked (HTTP 403) to non-browser clients; a VPN can
  re-trigger the WAF. URLs are pinned in
  `raw/gr/national-specs/manual_overrides.json` (slug-keyed: `url`,
  `source_org: ypaat`, `file_number`, `format`).
- **Stage 01c** ([scripts/gr/01c_fetch_specifikacije.py](scripts/gr/01c_fetch_specifikacije.py))
  fetches the 132 specs into `raw/gr/national-specs/<slug>.{pdf,doc,docx}`
  (87 PDF, 43 .doc, 2 .docx) + manifest with sha256.
- **Stage 02f** ([scripts/gr/02f_extract_national_specs.py](scripts/gr/02f_extract_national_specs.py))
  parses each via [scripts/_lib/gr/specifikacija.py](scripts/_lib/gr/specifikacija.py):
  one role-keyword section splitter (reuses the `eniaio_engrafo`
  tables + `greek_norm`) over `pdftotext -layout` (PDF), the shared
  `owm-antiword` Docker image (.doc), or zip/XML (.docx). Grapes come
  from the §6 ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ list (PDF) or a capitalised-Greek
  prose scan scoped to that section (.doc) with a first-char-guarded
  fuzzy filter (a cross-first-char fuzzy hit on a place name is the
  dominant false positive — `Νάουσα`→xinomavro, `Σεπτέμβρη`→
  chasselas-rose). Sidecars land in `raw/gr/national-specs-extracted/`
  (132: 127 with grapes, 131 with terroir text).
- **Stage 04** `augment_gr_records_with_national_specs()` merges the
  sidecar grapes / terroir text / styles / geo-area into the in-memory
  stub record (on-disk JSON stays immutable); `stub_reason` is prefixed
  `national-spec:`; `_sources_for()` surfaces `national_spec_*`
  provenance. **02d** grounds terroir-fact extraction on the sidecar's
  §7 ΔΕΣΜΟΣ text when the on-disk record's `link_to_terroir` is empty.

Re-runnable:
```
.venv/bin/python scripts/gr/01c_fetch_specifikacije.py
.venv/bin/python scripts/gr/02f_extract_national_specs.py --all
.venv/bin/python scripts/gr/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/gr/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/04_build_maps.py
```

For a curator-pinned EUR-Lex single document (the only path that
promotes a wine to a full EU-OJ extraction), use the original flow:
`scripts/gr/regen_manual_overrides_template.py` → edit
`raw/gr/oj-pages/manual_overrides.json` → `gr/01_fetch_pliegos.py` →
`gr/02_extract_pliegos.py` → `04_build_maps.py`. Stage 02's HTML
parser only understands the EU-OJ ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ template; national
PDF/.doc specs ride the 01c/02f layer above instead.

## Germany pipeline (`scripts/de/`)

Country #12. **The first country sharing its source language with a prior
country (AT — both Germanic-language corpora use `source_lang="de"`).**
46 wine GIs (19 PDO + 27 PGI) from eAmbrosia. Structurally a clone of
the Austria pipeline (identical EU-OJ EINZIGES DOKUMENT template, German
section keywords, same `_lib.at.einziges_dokument`-style parser at
`_lib/de/einziges_dokument.py`), with one structural delta: the **6
Einzellage PDOs are modelled as sub-denominations** of their parent
Anbaugebiet — the first time a country in this corpus has emitted
eAmbrosia-sourced sub-denominations rather than catalog-sourced ones
(FR DGCs / ES subzonas / IT sottozone / PT sub-regiões all come from
the cahier / pliego / caderno's own subdivision tables).

Spine: **eAmbrosia EU register**, filtered `country=DE` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"EINZIGES DOKUMENT"** published inline as HTML, reached via each GI's
`publications[].uri` (German-language URL rewrite — `/oj/deu`,
`legal-content/DE/TXT/HTML/`, `…01.DEU`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR/HU/RO/BG/GR — `scripts/de/01b_solve_waf.py` clears
blocked URLs with headless Chromium (none triggered on the first stage-01
run, but the bootstrap remains available for re-fetches).

Coverage in the corpus: 27 of 46 DE wines carry a fetchable EU single
document (~59 %, better than IT's 26 % but worse than AT's 100 %). The
remaining 19 are Art.107 / Reg.1308/2013 grandfathered names whose only
eAmbrosia reference is a non-fetchable `Ares(...)` summary-sheet — they
ship as content-stubs (the IT/ES/SI curator-queue pattern) and
nonetheless appear on the map because Bétard 2022 covers every
traditional Anbaugebiet (Germany was an EU founding member; everything
predates the dataset's Nov-2021 cutoff). v1 geometry coverage = **100 %
of PDOs** + the Landwein PGIs whose territories union to one-or-more
Anbaugebiete.

| Script | Reads | Writes |
|---|---|---|
| de/00_fetch_data.py | (network: eAmbrosia + BLE Produktspezifikationen) | raw/de/eambrosia/index.json + manifest.json, raw/de/produktspezifikationen/*.pdf + manifest.json |
| de/01_fetch_pliegos.py | raw/de/eambrosia/index.json + raw/de/oj-pages/manual_overrides.json | raw/de/oj-pages/*.html + manifest.json |
| de/01b_solve_waf.py | raw/de/oj-pages/manifest.json | raw/de/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| de/02_extract_pliegos.py | raw/de/oj-pages/*.html | raw/de/dokumente-extracted/*.json + _index.json |
| de/02d_extract_terroir_facts.py | raw/de/dokumente-extracted/*.json + raw/wikipedia/aocs/de/ | raw/terroir-facts/*.json (country="de") + manifest-de.json |
| de/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="de") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| de/02f_extract_produktspezifikation.py | raw/de/produktspezifikationen/*.pdf + manifest.json | raw/de/produktspezifikationen-extracted/*.json + _index.json + manifest.json |
| de/03_generate_wiki.py | raw/de/dokumente-extracted/*.json | wiki/<slug>.md (per DE record) + merges DE entries into wiki/_index.json |
| de/regen_manual_overrides_template.py | raw/de/eambrosia/index.json + raw/de/oj-pages/manifest.json | raw/de/oj-pages/manual_overrides.json (curator queue) |
| audit_de_coverage.py | raw/de/eambrosia/ + raw/de/dokumente-extracted/ + raw/de/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

DE-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/HU/
  RO/BG/GR). `country` is `"de"`; `source_lang` is also `"de"` — shared
  with Austria. The shared 02b / 02c stages key German config on `de`,
  and Germany's source_dir is added as a second path to the existing AT
  config (a tuple of dirs; see `SOURCE_CONFIG["de"]` in
  [scripts/02c_translate_summaries.py](scripts/02c_translate_summaries.py)).
  Stage 02b can be invoked twice with `--source raw/at/dokumente-extracted`
  and `--source raw/de/dokumente-extracted` — both write to the shared
  `raw/wikipedia/aocs/de/` cache, and slugs are globally unique.
- The German EINZIGES DOKUMENT parser at
  [scripts/_lib/de/einziges_dokument.py](scripts/_lib/de/einziges_dokument.py)
  is structurally identical to AT's; tables ship as a sibling so future
  German-specific quirks land in the right country namespace without
  churning AT code.
- The section-7 body lists varieties one per line as `Canonical name -
  Synonym, …` (e.g. `Spätburgunder - Pinot Noir, Blauburgunder`). The
  German wine corpus has the most prolific set of **breeding-station
  crossings** of any country (Geilweilerhof / Geisenheim / Weinsberg /
  Würzburg) — Phoenix, Regent, Solaris, Souvignier Gris, Cabernet
  Mitos/Cortis/Carbon/Dorsa/Dorio, Dornfelder, Helfensteiner, Heroldrebe,
  Acolon, Dunkelfelder, Faberrebe, Ortega, Optima, Reichensteiner,
  Schönburger, Siegerrebe, Würzer, Huxelrebe, Ehrenfelser, Kerner,
  Bacchus, Scheurebe, plus dozens more. Named releases are folded
  into the shared `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables in
  [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).
  Anonymous breeder codes (`GM 643-10`, `WE 94-26-36`, `VB 91-26-5`,
  `GF 84-58-988`) are unreleased / experimental varieties with no
  VIVC or Wikipedia presence — they remain raw candidates in v1.
- **Einzellage sub-denominations** — 6 single-vineyard PDOs (Bürgstadter
  Berg + Würzburger Stein-Berg in Franken, Monzinger Niederberg in
  Nahe, Uhlen Blaufüsser Lay + Uhlen Laubach + Uhlen Roth Lay in Mosel)
  are first-class sub-denomination records with `is_sub_denomination=true`
  + `parent_slug` + `parent_id_eambrosia`, same data shape as FR DGCs /
  ES subzonas / IT sottozone. The parent map lives in
  `_EINZELLAGE_PARENT_BY_FILE_NUMBER` in
  [scripts/de/00_fetch_data.py](scripts/de/00_fetch_data.py) (hand-
  verified against the EU-OJ Einziges Dokument of each Einzellage,
  which names its Anbaugebiet in section 6).
- **Großlagen** (the larger Weingesetz-defined wine collectivities like
  Bocksbeutel, Niersteiner Gutes Domtal) are NOT in eAmbrosia. They are
  conceptually sub-denominations of their parent Anbaugebiet but live
  exclusively in the **Weinverordnung Anhang 1** PDF (national wine
  law) and the BLE Weinlagen-Verzeichnis. v1 omits them; Phase 2 adds a
  per-source parser branch (mirrors the IT MASAF / ES MAPA pattern) to
  emit Großlagen as parent/sub records. See [CURATOR_TODO.md](CURATOR_TODO.md).
- **Principal vs accessory grape split** — the EU Einziges Dokument's
  section 7 is a flat list (no role split for German wines, same as
  IT/PT). Stage 02f
  ([scripts/de/02f_extract_produktspezifikation.py](scripts/de/02f_extract_produktspezifikation.py))
  derives a principal/accessory split from the **BLE Produktspezifikation
  PDF** per Anbaugebiet — the national specification document published
  by the Bundesanstalt für Landwirtschaft und Ernährung as *Amtliches
  Werk §5 UrhG*. The federal Weinverordnung's variety Anlagen (formerly
  the canonical source) were *repealed* in the 2022 wine-law reform;
  the BLE Produktspezifikation is the post-2022 canonical source. URL
  pattern: `https://www.ble.de/SharedDocs/Downloads/DE/Ernaehrung-
  Lebensmittel/EU-Qualitaetskennzeichen/Wein/Antraege/Bestimmte_Anbau-
  gebiete/01_Produktspezifiaktion_Anbaugebiete/Produktspezifikation_<REGION>.pdf`
  (with the Hessische-Bergstraße filename truncated to `_Hessisch.pdf`).
  Parser in
  [scripts/_lib/de/produktspezifikation.py](scripts/_lib/de/produktspezifikation.py).
  Strategy: §3.2 (Mindestmostgewicht) names individual varieties with
  their own threshold (Mosel → Riesling, Elbling, Müller Thurgau,
  Dornfelder); those are PRINCIPAL. Everything else in §8 (Zugelassene
  Keltertraubensorten) is "alle übrigen Rebsorten" → ACCESSORY. Same
  pattern as ES MAPA / IT MASAF where the regulator's production-rules
  section yields the de-facto principal varieties.

  Coverage: all 13 BLE PDFs parse via one of four template branches in
  [scripts/_lib/de/produktspezifikation.py](scripts/_lib/de/produktspezifikation.py):

  - **Template A** (post-2022 reform): numbered §8 + §3.2 Mostgewicht
    per-variety. Mosel, Pfalz, Nahe, Mittelrhein, Rheinhessen, Franken,
    Württemberg, Saale-Unstrut (the last with a "Kellertraubensorten"
    typo handled by the regex).
  - **Template B**: "Zugelassene Keltertraubensorten:" un-numbered +
    bullet `• Weißwein` / `• Rot- und Roséwein`. Ahr, Sachsen. Sachsen
    additionally has §5.1.X named-principal subsections ("5.1.1.
    Weißwein - Ruländer, Traminer, Weißburgunder") that yield an
    explicit split; Ahr's §5.1 is flat-by-colour so no principal.
  - **Template C**: §7. Rebsorten with bullet markers `• Rebsorten für
    Weißwein` (Rheingau) or `Weißweinsorten:` (Hessische Bergstraße).
    Principal heuristics: inline "insbes. {variety} mit rd. X %"
    (Rheingau), tabular "Spätburgunder Rotwein 8,4 66°" §5.1.X named-
    Mostgewicht rows, and "vorwiegend die Rebsorten X (NN % der
    Rebfläche), Y (NN %)" cultivation statistics (Hessische
    Bergstraße).
  - **Template D** (Baden): multi-Bereich §3.2.X with tiered Mostgewicht
    rows. The lowest-threshold row per (Bereich, colour) names the
    Leitsorten → principal. Baden also has a flat §8 with the
    comprehensive authorised list — the parser combines: Template D
    for the principal/accessory split, Template A's §8 for the full
    variety roster.

  Of the 13: 9 produce a `section-3.2-principal` role split (Mosel,
  Pfalz, Nahe, Mittelrhein, Rheinhessen, Baden, Rheingau, Hessische
  Bergstraße, Sachsen); 4 use `section-8-flat-no-split` because their
  §3.2 / §5.1 doesn't enumerate per-variety (Ahr, Franken, Württemberg,
  Saale-Unstrut).

  `augment_de_records_with_produktspezifikation()` in
  [scripts/04_build_maps.py](scripts/04_build_maps.py) merges the
  sidecar's role split into the in-memory parent-Anbaugebiet record at
  load time; the on-disk dokumente-extracted JSON stays immutable.
  `_sources_for()` surfaces `ble_produktspezifikation_*` provenance for
  the panel. Einzellage sub-denominations and Landwein PGIs are not
  augmented (the sidecar's variety list is for the parent Anbaugebiet
  only).

  Re-runnable per slug or in sweep mode:
  ```
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --slug mosel
  .venv/bin/python scripts/de/02f_extract_produktspezifikation.py --all
  ```

  **BLE terroir backfill**: stage 02f also extracts the BLE PDF's §8
  / §9 "Angaben, aus denen sich der Zusammenhang … ergibt" block as
  plain text (`zusammenhang_text` in the sidecar). Six DE Anbaugebiete
  carry NO `link_to_terroir` in their EU Einziges Dokument (Ahr, Baden,
  Hessische Bergstraße, Rheingau, Sachsen, Saale-Unstrut — all
  grandfathered names without an EU-OJ publication). For those, 02d
  (`_resolve_lien_and_source` in
  [scripts/de/02d_extract_terroir_facts.py](scripts/de/02d_extract_terroir_facts.py))
  reads the BLE sidecar's `zusammenhang_text` as the terroir-source
  fallback; provenance flips to `kind: "ble-produktspezifikation"` and
  the panel attribution links to the BLE PDF URL. Stage 04's
  `augment_de_records_with_produktspezifikation()` mirrors the same
  fold for in-memory rendering. After this, every traditional German
  Anbaugebiet (13 of 13) has 7-10 terroir facts.

  **Landwein g.g.A. extension (Phase 2)**: the same stage 02f also
  augments the **15 Landwein PGIs** that ship as stubs (no fetchable EU
  Einziges Dokument): Ahrtaler, Badischer, Bayerischer Bodensee, Branden-
  burger, Landwein Main / Neckar / Oberrhein / Rhein / Rhein-Neckar,
  Mitteldeutscher, Regensburger, Rheingauer, Schwäbischer, Starkenburger,
  Taubertäler. Their BLE national Produktspezifikation lives in a
  parallel directory
  (`…/Wein/Antraege/Landweingebiete/01_Produktspezifikationen_Landweine/Landwein_<Fragment>.pdf`,
  fetched by stage 00 alongside the Anbaugebiete PDFs into the shared
  `raw/de/produktspezifikationen/` dir, tagged `category: "landwein"` in
  the manifest). The Landwein layout is heterogeneous — the variety
  roster sits at §6 / §7 / §8 depending on the document, grouped by
  colour subheader OR by per-Bundesland prose paragraph — so section
  numbers aren't reliable anchors. A dedicated parser
  ([scripts/_lib/de/landwein_spezifikation.py](scripts/_lib/de/landwein_spezifikation.py))
  locates the variety section by KEYWORD ("N. Rebsorten" / "N. Zugelassene
  Keltertraubensorten"), slices to the next top-level numbered header, and
  runs the shared grape lexicon over the candidate phrases (the same
  whole-section scan the CH règlement parser uses). Landwein has no
  principal/accessory split, so every variety resolves as `principal`
  (the sidecar lands as `section-8-flat-no-split`); per-grape colour comes
  from the lexicon matcher. The §-Zusammenhang terroir text (title variant
  "N. Angaben, aus denen sich der Zusammenhang … ergibt" OR "N. Zusammen-
  hang mit dem geografischen Gebiet") is extracted the same way. Result:
  **15 / 15 Landwein stubs augmented — 38-160 varieties each + 1.3-4.3 KB
  of terroir source text**, feeding stage 04's grape fold + 02d's terroir
  extraction. Geometry was already resolved via `region-pdo-union`
  (DE_PGI_MEMBER_PDOS), so these PGIs now carry full panels.
- Region facet = **Anbaugebiet** for PDOs (the 13 traditional German
  wine regions: Ahr, Baden, Franken, Hessische Bergstraße, Mittelrhein,
  Mosel, Nahe, Pfalz, Rheingau, Rheinhessen, Saale-Unstrut, Sachsen,
  Württemberg) and **Bundesland-scale territory** for Landwein PGIs
  (Rheinland-Pfalz, Bayern, Baden-Württemberg, Hessen, Sachsen,
  Sachsen-Anhalt, Mecklenburg-Vorpommern, Brandenburg, Schleswig-
  Holstein, Saarland) plus a "Deutschland" catch-all for nationwide
  collective brands. Curated `_REGION_BY_FILE_NUMBER` covers every wine
  ([scripts/_lib/de/region.py](scripts/_lib/de/region.py)). Region
  labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR convention — shown in
  the native German form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for DE
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR pairs). Dual-source
  grounding (Einziges Dokument section 8 + de.wikipedia.org per-PDO
  page — shares the AT Wikipedia cache at `raw/wikipedia/aocs/de/`),
  German extraction prompt with German terroir vocabulary
  (Buntsandstein, Muschelkalk, Keuper, Schiefer, Devon, Löss, Lehm,
  Mergel, Basalt, Porphyr, Granit, Steillagenweinbau, Klosterweinbau,
  VDP-Klassifikation, …), fuzzy-coverage filter (≥ 0.6), per-bullet
  provenance, manual round-trip flow. 02e targets en/fr/es/nl.
  Cache files land in the shared `raw/terroir-facts/` directory with
  `country: "de"`. Einzellage sub-denominations are skipped — they
  inherit the parent Anbaugebiet's bullets at the rendering layer.

### DE geometry resolution chain (stage 04)

Per DE record, in priority order (`geom_source` records the choice):

1. **`parent-appellation`** — Einzellage sub-denominations (Bürgstadter
   Berg → Franken, Monzinger Niederberg → Nahe, the three Uhlen →
   Mosel, Würzburger Stein-Berg → Franken) inherit the parent
   Anbaugebiet's polygon. The Einzellage's own commune-precise polygon
   isn't in Bétard or any public dataset we currently consume; without
   per-vineyard cadastral parcels, the honest precision is parent-
   Anbaugebiet-level. (`DE_EINZELLAGE_PARENT_PDO` in
   [scripts/_lib/de/geometry.py](scripts/_lib/de/geometry.py).)
2. **`figshare-pdo`** — exact `file_number` (`PDO-DE-*`) → `PDOid`
   match against Bétard 2022 EU\_PDO.gpkg. Covers all 13 traditional
   Anbaugebiete + a handful of newer regional PDOs. The shared
   `raw/es/figshare/EU_PDO.gpkg` — no new fetch in stage 00.
3. **`region-pdo-union`** — most of the 27 DE Landwein PGIs are NOT
   in Bétard (PDO-only dataset). Where the PGI's territory is
   coextensive with one Anbaugebiet (Badischer Landwein → Baden,
   Pfälzer Landwein → Pfalz, Sächsischer Landwein → Sachsen, …) or
   the union of several (Landwein Rhein = Mosel + Mittelrhein + Nahe +
   Pfalz + Rheingau + Rheinhessen + Ahr; Rheinischer Landwein =
   Rheinhessen + Nahe + Pfalz + Mittelrhein), we use the union of the
   member-PDO Figshare polygons (the SI / HU / BG pattern). Mappings
   in `DE_PGI_MEMBER_PDOS` in [scripts/_lib/de/geometry.py](scripts/_lib/de/geometry.py).
4. **`gisco-commune-union`** — for multi-Bundesland Landwein PGIs that
   are NOT coextensive with one Anbaugebiet (so step 3 can't union a
   parent PDO) and aren't in Bétard (PDO-only). The area is transcribed
   from the BLE Produktspezifikation §3 "Abgrenzung des Gebietes" into
   the curated `DE_LANDWEIN_AREA` in
   [scripts/_lib/de/geometry.py](scripts/_lib/de/geometry.py) as whole
   Landkreise / kreisfreie Städte (unioned by 5-digit AGS Kreis prefix
   against the GISCO_ID) plus named Gemeinden (single-commune name match
   scoped to their Kreis; the `spec` field records the regulator's
   wording when the GISCO commune differs — e.g. the Ortsteil Meseberg
   resolves to its Stadt Gransee). Shipped for **Brandenburger Landwein**
   (PGI-DE-A1281 — 6 Landkreise + 4 kreisfreie Städte + 7 Gemeinden =
   188 GISCO communes, 13,093 km²). Same pattern as the RO IGP / BG
   commune-list fallback; extend `DE_LANDWEIN_AREA` for the other
   multi-Bundesland Landweine (Mitteldeutscher, Mecklenburger,
   Schleswig-Holsteinischer) as they're transcribed.
5. **`stub-no-geometry`** — last resort; no longer hit for Brandenburger.

### Curator workflow for DE wines without an OJ publication

Mirrors the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR
`regen_manual_overrides_template.py` flow. 19 DE wines have no
fetchable single-document URL. The canonical source for those is the
Weingesetz / Weinverordnung (national wine law) and the BMEL
(Bundesministerium für Ernährung und Landwirtschaft) /
Bundessortenamt publications; researching a public, licence-clear URL
pattern for it — and adding a national-spec parser branch — is Phase
2 work (it also unlocks the Großlagen). For now:

```
.venv/bin/python scripts/de/regen_manual_overrides_template.py
# edit raw/de/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear specification (EUR-Lex OJ-C page, or BMEL /
# Weinverordnung national specification PDF).
.venv/bin/python scripts/de/01_fetch_pliegos.py
.venv/bin/python scripts/de/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML parser only understands the EU-OJ
EINZIGES DOKUMENT template; BMEL / Weinverordnung national-
specification formats need a per-source parser (Phase 2, mirrors the
ES MAPA / IT MASAF pattern). Until then, only EUR-Lex single-document
URLs promote a wine out of stub state.

## Switzerland pipeline (`scripts/ch/`)

Country #13. **The first non-EU country in the corpus.** 63 AOC
entries (61 unique after intercantonal dedupe — Vully VD/FR and
Zürichsee ZH/SZ appear under both) across 26 cantons, sourced from
the OFAG/BLW federal repertoire. Multi-language at the country level
— per-record `source_lang` ∈ `{fr, de, it}` depending on canton.
Geometry mix: SITG Geneva geoportal (parcel-precise for 22 GE premier
crus) + swisstopo swissBOUNDARIES3D commune/canton union (the bulk).

Spine: **OFAG/BLW "Répertoire suisse des AOC"** — one trilingual
(FR/DE/IT) PDF, 4 pages, ~376 KB, updated annually each 1 January.
Published on `blw.admin.ch/fr/vin`. The PDF has three tiered columns:
*cantonale* (28 entries), *régionale* (13), and *locale* (22 — all
22 Geneva premier crus). The parser uses column-position thresholds
to classify tier and emits one record per entry; intercantonal AOCs
(Vully VD/FR, Zürichsee ZH/SZ) are deduped to a single record with
`cantons: [primary, secondary]`. The OFAG PDF has one known typo
(`BL Basel-Stadt` instead of `BS Basel-Stadt`) which is fixed at
parse time by canton-name lookup.

Per-AOC body: **cantonal wine règlement / Reglement / regolamento**
fetched from each canton's official legal portal (lex.<XX>.ch /
recueil systématique). All 26 cantons have URLs registered in
[scripts/_lib/ch/reglement_index.py](scripts/_lib/ch/reglement_index.py)
(researched + verified 2026-05). The 5 top wine cantons (VS/VD/GE/TI
/NE) have their canonical règlements as direct HTML/PDF; the other
21 use the **LexWork** SPA template (a shared cantonal legislation
product by ASIT Cyberadmin — same JS shell on AG/AI/AR/BL/BS/FR/GL/
GR/LU/NW/OW/SG/SH/SO/TG/ZG portals). Stage 01 detects LexWork SPAs
and re-fetches the canonical PDF via the API at
`/api/<lang>/texts_of_law/<shelf>` → `pdf_link`.

| Script | Reads | Writes |
|---|---|---|
| ch/00_fetch_data.py | (network: OFAG + swisstopo + SITG GE) | raw/ch/ofag/repertoire-aoc-2026.pdf, raw/ch/swisstopo/swissboundaries3d_2026-01_2056_5728.gpkg, raw/ch/geoportals/sitg-vit-vignoble-ao.geojson |
| ch/01_fetch_reglements.py | scripts/_lib/ch/reglement_index.py + raw/ch/reglements/manual_overrides.json | raw/ch/reglements/<canton>/reglement.{pdf,html} + manifest.json |
| ch/02_extract_reglements.py | raw/ch/ofag/repertoire-aoc-2026.pdf + raw/ch/reglements/<canton>/reglement.* + raw/ch/swisstopo/*.gpkg | raw/ch/dokumente-extracted/*.json + _index.json + raw/ch/dokumente-extracted-manifest.json + raw/ch/extraction-unknowns.json |
| ch/02d_extract_terroir_facts.py | raw/ch/dokumente-extracted/*.json + raw/wikipedia/aocs/{fr,de,it}/ | raw/terroir-facts/*.json (country="ch") + manifest-ch.json |
| ch/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="ch") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| ch/03_generate_wiki.py | raw/ch/dokumente-extracted/*.json | wiki/<slug>.md (per CH record) + merges CH entries into wiki/_index.json |
| audit_ch_coverage.py | raw/ch/ofag/ + raw/ch/reglements/ + raw/ch/dokumente-extracted/ + raw/ch/geoportals/ | (stdout — per-canton coverage table) |

CH-specific notes:
- `kind` is `"AOC"` (Swiss convention — same as France). `country`
  is `"ch"`; `source_lang` is **per-record** (`fr` / `de` / `it`
  depending on the AOC's primary canton — the first time in the
  corpus that source-language varies *within* a country rather than
  *between* countries. The existing stage 04 src_lang machinery is
  extended to read `record["source_lang"]` directly when
  `country == "ch"`).
- Canton table at
  [scripts/_lib/ch/canton.py](scripts/_lib/ch/canton.py) holds all 26
  cantons with their BFS canton id (1-26, matching swissBOUNDARIES3D
  `KANTONSNUMMER`), official languages, and per-canton default
  source_lang. Bilingual / trilingual cantons (BE FR-DE, FR FR-DE, VS
  FR-DE, GR DE-IT-RM) use the first listed language as default — wine
  production in those cantons is overwhelmingly on the FR side (or DE
  side for GR), so the default reflects the wine corpus.
- The OFAG répertoire is parsed by
  [scripts/_lib/ch/ofag_register.py](scripts/_lib/ch/ofag_register.py)
  via `pdftotext -layout`. Column thresholds: pos 30-60 = cantonale,
  pos 60-85 = régionale, pos 85-110 = locale. Two-table layout (page
  1 summary + page 2-3 AOC names) handled via a `seen_first_data_block`
  state flag that skips to after the first "Total" line.
- The per-canton règlement parser at
  [scripts/_lib/ch/reglement.py](scripts/_lib/ch/reglement.py) uses
  a **whole-document grape-lexicon scan** rather than section-scoped
  extraction. The shared `_lib.grape_entity.match_variety` is robust
  enough (lexicon-based + per-token rejection) to scan ~50 KB of
  règlement text without false positives, and cantonal règlements
  frequently bury the variety list in an annex or refer to an
  external annex by article — section-scoped extraction missed most
  of the recall. Commune extraction stays section-scoped because
  whole-document commune scans generate huge false-positive lists.
  Variety extraction recall: 20 of 26 cantons return non-zero
  varieties; AG (29), GE (47), VD (16), VS (25), FR (66), NE (18),
  TI (14), JU (4), LU (7), BL (8), GR (5), SG (5), OW (4), TG (4),
  ZH (3), SH (2), SO (1), BE (1), GL (1), ZG (1). Cantons with 0
  varieties (AI, AR, BS, NW, SZ, UR) defer to federal OVin without
  cataloguing varieties locally (BS defers to BL via inter-cantonal
  Vereinbarung; the others are tiny corpora ~5 ha each).
- For the 5 multi-AOC cantons (VD has 10 AOCs, GE has 23, TI has 4,
  BE has 3, FR has 2), the canton-wide règlement body is the v1
  default for variety lists. Per-AOC commune-list carving (Phase 2.5)
  runs for **VD / BE / FR** via
  [scripts/_lib/ch/per_aoc_carving.py](scripts/_lib/ch/per_aoc_carving.py):
  - **VD**: parses Art. 7 (Chablais), Art. 8 (Lavaux), Art. 9 (La
    Côte) and emits per-AOC text blocks; stage 02 scans each block
    with the shared `CHCommuneIndex.scan_text()` to resolve BFS-keyed
    commune lists. Result: 70 commune resolutions across 4 sub-AOCs
    (Chablais 10 communes, Lavaux 23, La Côte 77, Bonvillars 1).
    The smaller régionale AOCs (Côtes-de-l'Orbe, Bonvillars, Vully,
    Dézaley, Calamin) declare themselves as "single lieu de
    production" without commune enumeration and fall through to
    parent-inheritance for geometry.
  - **BE**: Art. 2 commune lists hardcoded (the article is short,
    stable, and uses post-merger BFS canonical names: Twann-Tüscherz,
    Biel/Bienne, Oberhofen am Thunersee).
  - **FR**: Art. 16 commune lists hardcoded (Vully: Mont-Vully +
    Vully-les-Lacs cross-canton; Cheyres: post-2017-merger
    Cheyres-Châbles).
  - **GE**: skipped — SITG VIT_VIGNOBLE_AO geoportal already gives
    parcel-precise polygons for all 22 premier crus.
  - **TI**: skipped — the 3 colour-tier sub-DOCs share the canton-
    wide production area; per-AOC carving adds nothing.

  Per-AOC variety carving (VD's Lavaux-only Chasselas split, GE's
  per-premier-cru annex) is still deferred — would need per-region
  Art. 18 / Art. 14 parsing for each variety/yield rule.
- Sub-denomination model: tier "régionale" and "locale" entries are
  tagged `is_sub_denomination=true` with `parent_slug` = the same
  canton's "cantonale" AOC slug (when one exists). Orphan régionale
  (FR's Cheyres + Vully — FR has no cantonale entry) stay flat. The
  GE premier crus (22 records, tier="locale") all carry
  `parent_slug=geneve`. Same data shape as FR DGCs / ES subzonas /
  IT sottozone / DE Einzellage.
- **VS Grand Cru per-commune sub-records (Phase 2.5)**: 12 communes
  identified with sources (Vinum Montis + grandcrusion.ch + Thomas
  Vino historical reportage, researched 2026-05). The roster lives
  in `VS_GRAND_CRU` in
  [scripts/_lib/ch/per_aoc_carving.py](scripts/_lib/ch/per_aoc_carving.py).
  Stage 02 emits these as sub-denomination records of
  `valais-wallis`:

  | commune | grand cru name | year | confidence |
  |---------|----------------|------|-----------|
  | Salquenen (Salgesch) | Salquenen Grand Cru | 1988 | confirmed |
  | Vétroz | Vétroz Grand Cru | 1993 | confirmed |
  | Saint-Léonard | Saint-Léonard Grand Cru | 1994 | confirmed |
  | Fully | Fully Grand Cru | 1996 | confirmed |
  | Conthey | Conthey Grand Cru | 1999 | confirmed |
  | Chamoson | Chamoson Grand Cru | 2011 | confirmed |
  | Sion | Grand Cru Ville de Sion | 2012 | confirmed |
  | Saillon | Saillon Grand Cru | n/a | association-member |
  | Leytron | Leytron Grand Cru | n/a | association-member |
  | Sierre | Sierre Grand Cru | 2015 | confirmed |
  | Savièse | Savièse Grand Cru | n/a | to-verify |
  | Visperterminen | Visperterminen Grand Cru | n/a | to-verify |

  Each entry resolves to a single-commune polygon via
  swissBOUNDARIES3D `BFS_NUMMER`. Per OVV Art. 86, each commune
  homologates its own communal Grand Cru règlement — the OVV itself
  does NOT enumerate them, so the roster requires external research
  + occasional re-verification. The 2 "to-verify" entries (Savièse,
  Visperterminen) are catalogued by Vinum Montis (Sierre regional
  tourism office) but their Conseil d'État homologation decrees
  weren't located in the public record; they ship under the same
  data shape with `confidence: "to-verify"`.

  Phase 3 follow-up: extract the individual homologation decrees from
  the Bulletin officiel du canton du Valais archive to confirm dates
  + fill in any missing communes.
- **VD ASIT cadastre viticole — gated**: the viageo.ch metadata
  entry `36bc73a7-5ac6-8364-25dc-cdb3f2c5895e` describes a cantonal
  AOC-perimeter layer but distribution is access-gated ("Freigabe
  erforderlich" via DGAV order desk `info.diffusion@vd.ch`). The
  federal `geodienste.ch` Rebbaukataster (MGDM 151.1) is freely
  available for ~half of cantons but is a *parcel cadastre* (planted-
  vines or eligible-parcel land use) with **no AOC-name attribute** —
  not useful for per-AOC polygon matching. v1 / Phase 2.5 VD geometry
  therefore stays on the per-AOC règlement carving + swissBOUNDARIES3D
  commune-union path. Phase 3 candidate: file a DGAV order for the
  cantonal AOC-perimeter shapefile under "Utilisation libre.
  Obligation d'indiquer la source".
- Region facet = **Swiss wine region** (6 regions per Swiss Wine
  Promotion: Valais, Vaud, Genève, Trois-Lacs, Ticino,
  Deutschschweiz). Curated canton → region map in
  [scripts/_lib/ch/region.py](scripts/_lib/ch/region.py) covers
  every canton. Trois-Lacs encompasses NE + the FR side of Vully +
  BE's Bielersee + JU (geographically clustered). Region labels
  follow the AT/IT/ES/SI/HR/HU/RO/BG/GR convention — shown in
  the native form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for CH —
  with one big structural delta vs. every prior country: cantonal
  règlements are **regulatory** texts (variety lists, yields, area
  definitions) and do NOT carry a "Beschreibung des Zusammenhangs" /
  "lien au terroir" narrative section like EU single documents do. CH
  02d therefore uses **Wikipedia as the primary terroir source**, with
  règlement context (canton, varieties, communes, règlement summary)
  as secondary grounding. Records without a usable Wikipedia article
  are skipped (no narrative fallback). Per-record `source_lang`
  (fr/de/it) drives both the extraction prompt and the Wikipedia
  source — 02d picks `raw/wikipedia/aocs/<source_lang>/<slug>.json`.
  The 4-subsection structure + JSON schema match AT/DE exactly so
  stage 04 renders CH facts through the same code path. 02e targets
  `{en,fr,es,nl} - {source_lang}` per record.

  Wikipedia salience coverage is genuinely thin: only **3 of 30**
  CH parent AOCs have a dedicated wine article that isn't the canton
  Wikipedia page. Confirmed coverage (researched 2026-05, pinned in
  `raw/wikipedia/aoc_overrides.json`):

  | slug          | lang | wikipedia title              |
  |---------------|------|------------------------------|
  | vaud          | fr   | Vignoble du canton de Vaud   |
  | valais-wallis | fr   | Vignoble du Valais           |
  | ticino        | it   | Ticino (vino)                |

  The remaining 27 CH parents per language are pinned `missing` in
  `aoc_overrides.json` so the cascade doesn't keep retrying the canton
  article (which is rejected by `looks_like_aoc`). DE-Wikipedia has
  `Weinbau am Zürichsee` but Zürichsee is an OFAG sub-denomination
  (parent = Schwyz), which 02d skips by design.

  Operationally:
  ```
  # Wikipedia sweep — once before 02d
  uv run scripts/02b_fetch_aoc_lexicon.py --lang fr --source raw/ch/dokumente-extracted
  uv run scripts/02b_fetch_aoc_lexicon.py --lang de --source raw/ch/dokumente-extracted
  uv run scripts/02b_fetch_aoc_lexicon.py --lang it --source raw/ch/dokumente-extracted

  # Terroir extraction + translation via Anthropic batch (~$0.05 total)
  uv run scripts/ch/02d_extract_terroir_facts.py --batch --provider anthropic
  uv run scripts/ch/02e_translate_terroir_facts.py --batch --provider anthropic
  ```

  Phase 2 result: 11 well-grounded facts across the 3 covered records
  (Vaud 2, Valais 6, Ticino 3) translated into 10 (record × target-lang)
  pairs. Cache files land in the shared `raw/terroir-facts/` directory
  with `country: "ch"`. The Rumantsch (rm) source-language is excluded
  — the rm.wikipedia.org corpus is too thin for AOC pages and rm-canton
  AOCs (only relevant for parts of GR) defer to DE.

  Long-tail unlock for CH terroir coverage requires either (1) writing
  Wikipedia articles for the missing 27 cantons' wine regions (out of
  scope), (2) using a different grounding source — national wine-
  classification publications, books, or regional tourist-board content
  whose licenses permit verbatim quotation — or (3) accepting that CH's
  primary narrative surface is the cantonal règlement attribution
  (already shown in the panel's source block) rather than LLM-extracted
  bullets.

### CH geometry resolution chain (stage 04)

Per CH record, in priority order (`geom_source` records the choice):

1. **`geoportal-canton:ge`** — SITG VIT_VIGNOBLE_AO parcel-precise
   polygon, matched by AOC slug. Active for 23 GE AOCs (the 22
   premier crus + Genève cantonale). Parcel resolution (≤ 2 m
   precision); each AOC may be a multi-part polygon (e.g. Coteaux de
   Dardagny has 13 parcels). License: SITG "accès libre".
2. **`parent-aoc`** — sub-denominations (régionale + locale tiers)
   inherit the parent's polygon when their commune list is empty
   (the bulk of VD's sub-denominations + some BE/FR/SZ/ZH entries).
3. **`swissboundaries-commune-union`** — parse the canton règlement
   for commune mentions (via `CHCommuneIndex.scan_text`) and union
   the matching swissBOUNDARIES3D Gemeinde polygons by BFS_NUMMER.
   Hit rate: VD (100), TG (50), SG (48), SH (16), BE (10), NE (5),
   FR (3), several cantons with 1 (just the seat-of-government
   commune named in the preamble — geometry is downgraded to
   canton-union by step 4).
4. **`swissboundaries-canton-union`** — for whole-canton AOCs (the
   bulk of the smaller German-CH cantons + canton-level umbrellas):
   union every Gemeinde whose `KANTONSNUMMER == BFS canton id`. The
   honest precision for cantons with no parseable commune list.
5. **`stub-no-geometry`** — last resort. Not hit in v1; every Swiss
   AOC resolves to at least canton-level geometry.

The swissBOUNDARIES3D GeoPackage is native EPSG:2056 (CH1903+ /
LV95); `CHCommuneIndex` reprojects to EPSG:4326 at load time. Layer:
`tlm_hoheitsgebiet` filtered to `objektart == "Gemeindegebiet"` —
yields 2,123 Swiss Gemeinden (matches BFS 2,121 plus 2 exclaves:
Büsingen DE-administered, Campione IT-administered).

### Curator workflow for CH wines with broken règlement URLs

Mirrors the FR `manual_overrides.json` flow. If a cantonal-règlement
URL rotates or the canton publishes a new edition outside the
LexWork API, drop a replacement URL into
`raw/ch/reglements/manual_overrides.json` (gitignored):

```json
{
  "vd": {"url": "https://www.vd.ch/.../REG_NEW.pdf", "format": "pdf",
         "lang": "fr", "note": "2026 amendment"}
}
```

Then re-run stages 01 → 02 → 04.

## Slovakia pipeline (`scripts/sk/`)

Country #13. **10 wine GIs (9 PDO + 1 PGI)** from eAmbrosia — the
smallest corpus to date, but with surprisingly good coverage: 4 of 10
SK wines carry a fetchable EU single document (Vinohradnícka oblasť
Tokaj, Stredoslovenská, Skalický rubín, TOKAJSKÉ VÍNO zo slovenskej
oblasti), and all 10 land on the map via Bétard 2022 — 8 of 9 SK
DOPs sit in Bétard directly, the 9th PDO (`PDO-SK-02856` TOKAJSKÉ
VÍNO, post-Bétard) aliases the Vinohradnícka oblasť Tokaj polygon
(same Tokaj zone, different brand registration), and the single SK
PGI (`PGI-SK-A1361` "Slovenská") resolves as the union of all 8 SK
PDOs. Structurally the closest sibling to Slovenia — EU-OJ single-
document HTML in Slovak, Bétard PDO geometry, PGI = region-union.

Spine: **eAmbrosia EU register**, filtered `country=SK` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"JEDNOTNÝ DOKUMENT"** published inline as HTML, reached via each
GI's `publications[].uri` (Slovak-language URL rewrite — `/oj/slk`,
`legal-content/SK/TXT/HTML/`, `…01.SLK`). Same AWS-WAF caveat as
ES/IT/AT/SI/HR/HU/RO/BG — `scripts/sk/01b_solve_waf.py` clears
blocked URLs with headless Chromium (none triggered on the first
stage-01 run, but the bootstrap remains available).

| Script | Reads | Writes |
|---|---|---|
| sk/00_fetch_data.py | (network: eAmbrosia) | raw/sk/eambrosia/index.json + manifest.json |
| sk/01_fetch_pliegos.py | raw/sk/eambrosia/index.json + raw/sk/oj-pages/manual_overrides.json | raw/sk/oj-pages/*.html + manifest.json |
| sk/01b_solve_waf.py | raw/sk/oj-pages/manifest.json | raw/sk/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| sk/02_extract_pliegos.py | raw/sk/oj-pages/*.html | raw/sk/dokumenty-extracted/*.json + _index.json |
| sk/01c_fetch_specifikacije.py | raw/sk/national-specs/manual_overrides.json | raw/sk/national-specs/*.pdf + manifest.json (ÚPV SR špecifikácie) |
| sk/02f_extract_national_specs.py | raw/sk/national-specs/*.pdf | raw/sk/national-specs-extracted/*.json + _index.json + raw/sk/extraction-unknowns-specifikacije.json |
| sk/02d_extract_terroir_facts.py | raw/sk/dokumenty-extracted/*.json + raw/sk/national-specs-extracted/ + raw/wikipedia/aocs/sk/ | raw/terroir-facts/*.json (country="sk") + manifest-sk.json |
| sk/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="sk") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| sk/03_generate_wiki.py | raw/sk/dokumenty-extracted/*.json | wiki/<slug>.md (per SK record) + merges SK entries into wiki/_index.json |
| sk/regen_manual_overrides_template.py | raw/sk/eambrosia/index.json + raw/sk/oj-pages/manifest.json | raw/sk/oj-pages/manual_overrides.json (curator queue) |
| audit_sk_coverage.py | raw/sk/eambrosia/ + raw/sk/dokumenty-extracted/ + raw/sk/national-specs-extracted/ + raw/terroir-facts/ + raw/sk/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + national-spec + terroir + curator queue) |

SK-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/
  HU/RO/BG/GR/DE). `country` is `"sk"`; `source_lang` is also `"sk"`
  (matches FR/ES/PT/IT/HR/HU/RO/BG — country code equals language
  code, unlike AT/SI/GR where they differ).
- The Slovak JEDNOTNÝ DOKUMENT template is parsed by
  [scripts/_lib/sk/jednotny_dokument.py](scripts/_lib/sk/jednotny_dokument.py)
  (Slovak section-keyword role routing — *Názov*, *Vymedzená
  zemepisná oblasť* / *Vymedzená oblasť*, *Hlavné muštové odrody*,
  *Opis súvislostí* / *Údaje potvrdzujúce spojitosť*, …). HTML-slice
  machinery is identical to ES/IT/AT/SI/HR/HU/RO/BG/DE. Older SK
  templates use shorter section titles ("Vymedzená oblasť" vs. the
  newer "Vymedzená zemepisná oblasť"), and the link section is
  sometimes titled "Údaje potvrdzujúce spojitosť" instead of "Opis
  súvislostí" — both variants are wired into the keyword tables.
- The grape-variety section enumerates one variety per line as
  `Canonical Slovak name` (no synonym suffix in v1). Slovak native
  varieties (Furmint, Lipovina = Hárslevelű, Muškát žltý = Muscat
  blanc, Kabar, Kövérszőlő, Zéta, Devín, Dunaj, Hron, Rimava, Váh,
  Nitria, Hetera, Veltlínske zelené, Rizling rýnsky, Rizling
  vlašský, Tramín červený, Rulandské biele/šedé/modré, Svätovavrinecké,
  Pesecká leánka = HU Leányka — distinct from Romanian Fetească
  Regală despite the literature confusion, Modrý Portugal,
  Frankovka modrá, …) are folded into the shared `GRAPE_ALIAS` /
  `DEFAULT_COLOUR` tables in
  [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).
  The Slovak crossings (Devín, Dunaj, Hron, …) bred at VÚVV
  Bratislava in the 1960s-90s get their own slugs (no foreign-
  cultivar equivalent).
- v1 models the 10 wine GIs as a **flat corpus** — vinohradnícke
  rajóny (sub-districts of an oblasť) are deferred to Phase 2.
- Region facet = **vinohradnícka oblasť**
  ([scripts/_lib/sk/region.py](scripts/_lib/sk/region.py)): the 5
  Slovak wine regions (Malokarpatská / Južnoslovenská / Nitrianska /
  Stredoslovenská / Východoslovenská) plus the **Tokaj** oblasť
  (treated as its own facet — it has its own PDOs distinct from the
  other 5). The single SK PGI (Slovenská) is "Slovensko". Curated
  `_REGION_BY_FILE_NUMBER` covers every wine. Region labels follow
  the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE convention — native Slovak form,
  not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for SK
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR/DE pairs). Dual-
  source grounding (Jednotný dokument section 8 + sk.wikipedia.org
  per-DOP page), Slovak extraction prompt with Slovak terroir
  vocabulary (spraš, černozem, ílovica, vápenec, dolomit, andezit,
  ryolit, vulkanická pôda, panónske podnebie, kontinentálne
  podnebie, vplyv Karpát, …), fuzzy-coverage filter (≥ 0.6),
  per-bullet provenance, manual round-trip flow. 02e targets
  en/fr/es/nl. Cache files land in the shared `raw/terroir-facts/`
  directory with `country: "sk"`. Slovak wine-law / Tokaj-predikát
  terms preserved verbatim by 02e include CHOP, CHZO, neskorý zber,
  výber z hrozna, bobuľový výber, hrozienkový výber, ľadové víno,
  slamové víno, tokajský výber, tokajská esencia, samorodné.

### SK national-spec layer (stages 01c + 02f)

All 6 grandfathered SK stubs are augmented from a Slovak regulator
per-wine **špecifikácia výrobku** — the SK analogue of the ES MAPA / IT
MASAF / BG IAVV / HR–SI national-spec layer. Resolved 2026-05-30/31 via
`/research-gaps national-spec sk` (the MPRV SR / slov-lex.sk Phase-2 lead
was the WAF-blocked mirror; the WAF-free register is **ÚPV SR**, Úrad
priemyselného vlastníctva SR / Slovak Industrial Property Office,
indprop.gov.sk). Two source shapes / parser templates:

- **5 modern specs** (Východoslovenská, Južnoslovenská, Nitrianska,
  Malokarpatská + the Slovenská PGI) — the lettered a–i ÚPV template,
  `upv-sr-specifikacia-v1` (described below).
- **1 old prihláška** (Karpatská perla, `PDO-SK-A1598`) — not on the ÚPV
  register, but its canonical spec is public on the **mpsr.sk** mirror
  (`https://www.mpsr.sk/download.php?fID=15089`): the 1996 ÚPV
  *Prihláška označenia pôvodu* (application 0005-96), an OCR-scanned PDF
  with a numbered `03.N` template and a flat §03.5 variety list. A
  second parser branch `upv-sr-prihlaska-v1` handles it (numbered slicer
  + flat-list extractor + targeted OCR repairs for the scan noise);
  terroir is the §03.2/03.3/03.4 narrative (granite-weathering soils,
  climate, the Karpáti-Deutsch history). mpsr.sk WAF-blocks bot UAs, so
  SK 01c presents a browser UA (indprop.gov.sk accepts it too).

- **Stage 01c** ([scripts/sk/01c_fetch_specifikacije.py](scripts/sk/01c_fetch_specifikacije.py))
  fetches each curator-pinned URL from
  `raw/sk/national-specs/manual_overrides.json` (slug → `{url,
  source_org: upv-sr, file_number, format: pdf}`) into
  `raw/sk/national-specs/<slug>.pdf` + manifest (sha256, fetched_at).
  Listing page `…/OPVAZOV/specifikacie-op-zo/vina-a-liehoviny`; URL
  pattern `…/swift_data/source/pdf/specifikacie_op_oz/<slug>.pdf`.
- **Stage 02f** ([scripts/sk/02f_extract_national_specs.py](scripts/sk/02f_extract_national_specs.py))
  runs `pdftotext -layout` and parses via
  [scripts/_lib/sk/specifikacija.py](scripts/_lib/sk/specifikacija.py)
  (`upv-sr-specifikacia-v1`). The spec is a uniform lettered a–i outline
  (`a` názov · `b` opis vína → styles · `d` vymedzenie zemepisnej oblasti
  → geo area · `f` označenie odrody/odrôd → grapes · `g` údaje
  potvrdzujúce spojitosť → terroir). Section f is a two-column table —
  `Odroda` (canonical Slovak name) left, `Synonymum` (foreign synonyms)
  right — grouped under `MUŠTOVÉ BIELE` (white → blanc) / `MUŠTOVÉ MODRÉ`
  (blue-black → noir) bucket labels. The parser takes **only the left
  Odroda column** (Title-Case, comma-free; the column gutter is the
  ≥ 2-space gap), so the Pesecká leánka ↔ Feteasca regala synonym
  confusion never reaches the matcher and synonym-continuation lines
  don't pollute the unknowns queue. No principal/accessory split (same as
  PT/IT/HR/BG) — every variety is `principal`.
- **Stage 04** `augment_sk_records_with_national_specs()` merges the
  sidecar's summary / grapes / geo_area / link_to_terroir / styles /
  section_roles into the in-memory stub record at load time (the on-disk
  dokumenty-extracted JSON stays immutable); `stub_reason` is prefixed
  `national-spec:`; `_sources_for()` surfaces `national_spec_*`
  provenance. **02d** grounds terroir-fact extraction on the sidecar's
  §g text when the on-disk record's `link_to_terroir` is empty.

Result: **6 / 6 stubs augmented** — the 5 modern specs carry 41–42
principal varieties + §g terroir (2.8–14.8 KB) each; Karpatská perla
carries 31 varieties + §03.2/03.3/03.4 terroir (6.9 KB). Terroir-fact
extraction (02d/02e, Anthropic batch) then produced 9–10 bullets per
modern-spec wine and 4 for Karpatská perla, translated en/fr/es/nl. **SK
effective coverage = 10 / 10 wines with grapes + terroir.** Six
VÚVV/Pospíšilová crossings named in §f were folded into
`grape_lexicon.py` (Breslava, Mília, Noria → blanc; Nitranka, Rudava,
Torysa → noir; all VIVC-anchored, distinct, own slugs). Licence: official
act (úradné dielo, §3 Autorský zákon) — attribution to ÚPV SR / MPRV SR.

Re-runnable per slug or sweep:
```
.venv/bin/python scripts/sk/01c_fetch_specifikacije.py
.venv/bin/python scripts/sk/02f_extract_national_specs.py --slug nitrianska
.venv/bin/python scripts/sk/02f_extract_national_specs.py --all
.venv/bin/python scripts/04_build_maps.py
```
Cached PDFs at `raw/sk/national-specs/<slug>.pdf` are reused unless
`--refresh` is passed.

### SK geometry resolution chain (stage 04)

Per SK record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-SK-*`) → `PDOid`
   match against Bétard 2022 EU\_PDO.gpkg. Covers 8 of 9 SK DOPs.
2. **`figshare-pdo-alias`** — the post-Bétard TOKAJSKÉ VÍNO PDO
   (`PDO-SK-02856`) borrows the Vinohradnícka oblasť Tokaj polygon
   (`PDO-SK-A0120`) — same physical Tokaj wine region, different
   brand registration. `geom_source` records the alias so the panel
   can attribute it correctly.
3. **`region-pdo-union`** — the single SK PGI (`PGI-SK-A1361`
   "Slovenská") is the whole-Slovakia wine territory; Bétard is
   PDO-only, so the PGI is the union of all 8 SK PDO polygons (SI
   pattern).
4. **`stub-no-geometry`** — not normally hit in v1; all 10 SK wines
   resolve.

The shared `raw/es/figshare/EU_PDO.gpkg` — no new fetch in stage 00.

### Curator workflow for SK wines without an OJ publication

5 of the 6 grandfathered SK wines are now covered by the ÚPV SR
national-spec layer above (researched 2026-05-30; see "SK national-spec
layer"). If a new SK wine appears, or an ÚPV URL rotates, add/refresh it
in `raw/sk/national-specs/manual_overrides.json` (slug → `{url,
source_org: upv-sr, file_number, format: pdf}`) and re-run 01c → 02f →
02d → 02e → 04. The only remaining stub is **Karpatská perla**
(no standalone ÚPV spec — see the layer note above).

If the Commission later publishes a real EU-OJ JEDNOTNÝ DOKUMENT for any
SK wine, the original `regen_manual_overrides_template.py` flow still
applies (it adds the EU-OJ narrative sections stage 02 parses directly):

```
.venv/bin/python scripts/sk/regen_manual_overrides_template.py
# edit raw/sk/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear EUR-Lex OJ-C single-document page.
.venv/bin/python scripts/sk/01_fetch_pliegos.py
.venv/bin/python scripts/sk/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML parser only understands the EU-OJ JEDNOTNÝ
DOKUMENT template; the ÚPV SR PDF specs ride the parallel 01c/02f layer
(kept OUT of `raw/sk/oj-pages/manual_overrides.json` so a PDF never
enters the HTML path — the HR/SI lesson).

## Czech Republic pipeline (`scripts/cz/`)

Country #14. **13 wine GIs (11 PDO + 2 PGI)** from eAmbrosia — the
**worst single-document coverage of any country** (0 of 13 SK wines
have a fetchable EU-OJ URL; every Czech wine is an Art.107 /
Reg.1308/2013 grandfathered name). All 13 nonetheless land on the
map: Bétard 2022 covers all 11 CZ DOPs (Czechia joined the EU in 2004;
everything predates Bétard's Nov-2021 cutoff), and the 2 macro PGIs
(`PGI-CZ-A0900` "české" / `PGI-CZ-A0902` "moravské") resolve as the
union of their constituent macro-PDO polygon (Čechy / Morava — same
territory, different name).

Structurally a near-clone of the Slovak pipeline (the word "JEDNOTNÝ
DOKUMENT" is identical in both languages), but **every CZ wine ships
as a content-stub** in v1 — the scaffolding (URL rewrite to
`/legal-content/CS/TXT/HTML/`, Czech section keywords, parse_grapes,
parse_styles) is pre-wired so a single curator-pinned EU-OJ URL or a
future MZE / NIPI national-specification parser branch unlocks
parsing without code changes.

| Script | Reads | Writes |
|---|---|---|
| cz/00_fetch_data.py | (network: eAmbrosia) | raw/cz/eambrosia/index.json + manifest.json |
| cz/01_fetch_pliegos.py | raw/cz/eambrosia/index.json + raw/cz/oj-pages/manual_overrides.json | raw/cz/oj-pages/*.html + manifest.json |
| cz/01b_solve_waf.py | raw/cz/oj-pages/manifest.json | raw/cz/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| cz/02_extract_pliegos.py | raw/cz/oj-pages/*.html | raw/cz/dokumenty-extracted/*.json + _index.json |
| cz/02f_extract_national_specs.py | (network: zakonyprolidi.cz decrees + SZPI CHZO PDFs) | raw/cz/national-specs/{varieties,communes/*,chzo-*,manifest}.json |
| cz/02d_extract_terroir_facts.py | raw/cz/dokumenty-extracted/*.json + raw/cz/national-specs/chzo-*.json + raw/wikipedia/aocs/cs/ | raw/terroir-facts/*.json (country="cz") + manifest-cz.json |
| cz/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="cz") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| cz/03_generate_wiki.py | raw/cz/dokumenty-extracted/*.json | wiki/<slug>.md (per CZ record) + merges CZ entries into wiki/_index.json |
| cz/regen_manual_overrides_template.py | raw/cz/eambrosia/index.json + raw/cz/oj-pages/manifest.json | raw/cz/oj-pages/manual_overrides.json (curator queue) |
| audit_cz_coverage.py | raw/cz/eambrosia/ + raw/cz/dokumenty-extracted/ + raw/cz/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

CZ-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as SK). `country` is
  `"cz"`; `source_lang` is `"cs"` — like AT/SI/GR/DE-shared-with-AT,
  the Czech country code (`cz`) differs from its language code (`cs`).
  The shared 02b / 02c stages key Czech config on `cs`.
- The Czech JEDNOTNÝ DOKUMENT template is parsed by
  [scripts/_lib/cz/jednotny_dokument.py](scripts/_lib/cz/jednotny_dokument.py)
  (Czech section-keyword role routing — *Název*, *Vymezená zeměpisná
  oblast*, *Hlavní moštové odrůdy*, *Popis souvislostí*, …). HTML-slice
  machinery is identical to the Slovak parser; only the keyword tables
  differ. In v1 the parser is not exercised (no fetchable EU
  document), but it is the foundation for the curator workflow.
- The grape-variety section is expected to enumerate Czech varieties
  one per line as `Canonical Czech name - synonym, synonym` (Ryzlink
  rýnský / Ryzlink vlašský / Tramín červený / Müller Thurgau /
  Rulandské bílé/šedé/modré / Veltlínské zelené / Frankovka /
  Svatovavřinecké / Modrý Portugal / Zweigeltrebe / André / Pálava /
  Aurelius / Cabernet Moravia / Neronet / Hibernal / …). All folded
  into the shared `GRAPE_ALIAS` / `DEFAULT_COLOUR` tables — the Czech
  crossings bred at Lednice / Velké Bílovice / Polášek (André,
  Pálava, Aurelius, Cabernet Moravia, Neronet) get their own slugs.
- v1 models the 13 wine GIs as a **flat corpus** — vinařské
  podoblasti (sub-regions of an oblast) are deferred to Phase 2.
  The 9 sub-region / district / single-vineyard PDOs (Litoměřická,
  Mělnická, Slovácká, Znojemská, Velkopavlovická, Mikulovská,
  Znojmo, Šobes, Novosedelské Slámové víno) are themselves first-
  class PDOs in eAmbrosia (not DGCs of the macro PDOs), so they sit
  as siblings of Čechy / Morava in the corpus rather than children.
- Region facet = **vinařská oblast**
  ([scripts/_lib/cz/region.py](scripts/_lib/cz/region.py)): the 2
  Czech wine macro regions (Čechy / Morava). Curated
  `_REGION_BY_FILE_NUMBER` covers all 13 wines — the 4 Bohemian
  PDOs/PGI map to Čechy, the 9 Moravian PDOs/PGI to Morava. Region
  labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK convention —
  native Czech form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for CZ
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR/DE/SK pairs). Dual-
  source grounding (Jednotný dokument section 8 + cs.wikipedia.org
  per-DOP page), Czech extraction prompt with Czech terroir
  vocabulary (spraš, černozem, jíl, vápenec, opuka, slínovec, žula,
  čedič, hadec, hnědozem, panonské podnebí, kontinentální podnebí,
  vliv Karpat, vliv Alp, …), fuzzy-coverage filter (≥ 0.6),
  per-bullet provenance, manual round-trip flow. 02e targets
  en/fr/es/nl. Cache files land in the shared `raw/terroir-facts/`
  directory with `country: "cz"`. Czech wine-law / predikát terms
  preserved verbatim by 02e include CHOP, CHZO, viniční trať,
  pozdní sběr, výběr z hroznů, výběr z bobulí, výběr z cibéb,
  ledové víno, slámové víno.

### CZ national-spec extraction (stage 02f)

Because 0 of 13 CZ wines carry a fetchable EU-OJ Jednotný dokument
(every CZ wine is an Art.107 / Reg.1308/2013 grandfathered name with
only `Ares(...)` references in eAmbrosia), the CZ corpus would ship as
13 bare stubs without a national-spec layer. Stage 02f
([scripts/cz/02f_extract_national_specs.py](scripts/cz/02f_extract_national_specs.py))
parses the **two Czech wine-law implementing decrees** that, together,
pin every CZ wine's authorised varieties and delimited area:

- **Vyhláška č. 88/2017 Sb. Příloha č. 2** — the national variety
  table (3 colour blocks: 35 white + 26 red + 6 zemské-víno =
  **67 varieties total**). The same list authorises every Czech
  jakostní víno regardless of podoblast — CZ wine law does not
  restrict varieties per appellation.
- **Vyhláška č. 254/2010 Sb. Příloha** — the per-podoblast obec list
  as a 3-column HTML table (`Vinařská obec / Katastrální území /
  Název viniční trati`) with `<td rowspan="N">` cells for the
  obec → KÚ → trať hierarchy. Stage 02f's
  [`parse_commune_tree`](scripts/_lib/cz/national_spec.py) walks
  `<tr>` rows with a rowspan-tracking state machine, extracting the
  obec name (column 0) per podoblast — 50/35/119/90/71/30 obce
  across the 6 podoblasti = **395 obce total**.

Fetch source: zakonyprolidi.cz (eSbírka is a JS SPA; the Sbírka PDF
is image-scanned and would require OCR). Canonical attribution:
Sbírka zákonů částka 32/2017 + částka 92/2010. Czech law text is
public per **§3(d) of the Czech Copyright Act** (úřední dílo); the
zakonyprolidi.cz layout is © AION CS but we only extract the law
text, not the layout.

Stage 02f ALSO fetches + parses the **two SZPI CHZO product
specifications** (terroir + styles — see "CZ CHZO terroir + style layer"
below).

Outputs:
- `raw/cz/national-specs/varieties.json` — national variety roster
  with colour bucket, ordinal, abbreviation, and resolved lexicon slug
- `raw/cz/national-specs/communes/<podoblast-slug>.json` — 6 files,
  one per podoblast
- `raw/cz/national-specs/chzo-{moravske,ceske}.{pdf,json}` — the two
  SZPI CHZO specs (cached PDF + parsed sidecar: region terroir text +
  style roster + provenance)
- `raw/cz/national-specs/manifest.json` — provenance (sha256, fetched_at,
  Sbírka + SZPI attribution) for stage 04's `_sources_for()`

Stage 04 consumes the sidecars via two paths:

1. **`augment_cz_records_with_national_specs()`** — merges the
   67-variety national list into every CZ wine's `grapes.principal`
   (deduplicated against the existing record — yields 66 unique
   canonical slugs after one synonym fold). The augmentation is
   in-memory only; the on-disk extracted JSON stays as a stub. Mirrors
   the ES MAPA / IT MASAF / DE BLE pattern.
2. **`CZPolygonIndex`** loads the per-podoblast obec lists at
   construction time and uses them via the new
   `gisco-commune-union-podoblast` step in the geometry chain (see
   below) — commune-precision via shared GISCO LAU 2024.

Re-runnable: cached HTMLs at `raw/cz/national-specs/*.html` are reused
unless `--refresh`; the sidecars regenerate every run.

```
.venv/bin/python scripts/cz/02f_extract_national_specs.py
.venv/bin/python scripts/04_build_maps.py
```

### CZ CHZO terroir + style layer (SZPI specs)

Czech wine law publishes no per-appellation CHOP (PDO) terroir/style
narrative — but the **SZPI** (Státní zemědělská a potravinářská
inspekce) publishes the two **CHZO** ("zemské víno" / PGI) product
specifications as licence-clear PDFs (úřední dílo, §3(d) Czech
Copyright Act), and these *are* full EU-template specs carrying both
narrative layers (researched 2026-05-31, after the user pushed to find
a regulator source before any Wikipedia fallback):

- `szpi.gov.cz/soubor/specifikace-chzo-moravske.aspx` → Morava region
- `szpi.gov.cz/soubor/specifikace-chzo-ceske.aspx` → Čechy region

[scripts/_lib/cz/chzo_spec.py](scripts/_lib/cz/chzo_spec.py)
(`parser_template: szpi-chzo-specifikace-v1`) parses the
`pdftotext -layout` output:

- **Section 1 (Popis vinařského regionu)** → `region_terroir_text`:
  the regulator's description of the *physical* wine region — 1.1
  meteorology (ČHMÚ 30-year normals, Huglin index) + 1.2 geology/soils
  with per-bioregion prose. This is **tier-agnostic**, so it grounds
  the terroir of *every* CZ wine sitting in that region, not just the
  PGI: **Morava covers 9 wines** (morava, moravske, the 4 Moravian
  podoblasti, znojmo, sobes, novosedelske-slamove-vino); **Čechy
  covers 4** (cechy, ceske, litomericka, melnicka) — all 13.
- **Section 2 (Druhy výrobků — popis vín)** → `styles`: still
  (white/red/rose), Likérové (vin-de-liqueur), Šumivé (sparkling),
  Perlivé (semi-sparkling).

Stage 04 `augment_cz_records_with_national_specs()` merges the CHZO
sidecars: the 2 PGIs gain the real style roster (sparkling /
semi-sparkling / vin-de-liqueur on top of the colour bases), and ALL
13 CZ records carry the region spec's provenance (`chzo_spec_*` in
`_sources_for()`, panel link `src_chzo_spec`). The CHOPs + podoblasti
keep grape-colour-inferred styles (white/red/rose from the national
67-variety roster; the straw-wine PDO Novosedelské Slámové víno
additionally → vin-de-paille).

**Terroir facts**: `cz/02d`'s `_resolve_lien_and_source` grounds each
CZ wine on its region's CHZO `region_terroir_text` (provenance
`kind: cz-chzo-specifikace`, attribution → SZPI PDF), with the
per-podoblast cs.wikipedia article kept as a secondary salience hint
(differentiates the podoblasti — e.g. Šobes's meander microclimate
comes from the wiki hint). Result: **7–10 terroir facts on all 13 CZ
wines** (Anthropic batch), translated into en/fr/es/nl by `cz/02e`.
The macro CHOP + its PGI share the region text → near-identical
bullets (honest: same regional terroir); the podoblasti differentiate
via the wiki salience hint.

```
.venv/bin/python scripts/cz/02f_extract_national_specs.py
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang cs --source raw/cz/dokumenty-extracted
.venv/bin/python scripts/cz/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/cz/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/04_build_maps.py
```

### CZ geometry resolution chain (stage 04)

Per CZ record, in priority order (`geom_source` records the choice):

1. **`gisco-commune-union-podoblast`** — for the 6 podoblasti
   (Litoměřická / Mělnická / Slovácká / Znojemská / Velkopavlovická /
   Mikulovská), union the GISCO LAU 2024 polygons matching the obce
   enumerated in Vyhláška 254/2010 Sb. Příloha (parsed by stage 02f
   into `raw/cz/national-specs/communes/<slug>.json`). **Czech obec
   names repeat across okresy** (dozens of "Lhota", "Nové Sady", …) and
   the Vyhláška lists no okres, so a bare-name match against the
   national GISCO set pulls in same-named communes country-wide — each
   polygon scattered 300–450 km across all of Czechia. Bétard 2022 has
   a correct **per-podoblast** PDO polygon for each (it is NOT
   macro-aggregated for CZ), so the union is **masked by the podoblast's
   own Bétard polygon** (`CZPolygonIndex.commune_union_for_podoblast`,
   centroid-in-mask + ~3 km buffer): the correct commune is kept, the
   distant homonyms dropped. Result: mikulovská 32×35 km (was 301×223),
   znojemská 52×45, slovácká 117/119 obce — matching the official
   Wines-of-Czech-Republic subregion map. Falls back to step 2 if
   < 60 % of obce match or the Bétard mask is unavailable.
2. **`figshare-pdo`** — exact `file_number` (`PDO-CZ-*`) → `PDOid`
   match against Bétard 2022 EU\_PDO.gpkg. Used for the 4 macro names
   (Čechy / Morava — and the 3 single-vineyard / single-varietal
   PDOs Znojmo / Šobes / Novosedelské Slámové víno that aren't
   podoblasti).
3. **`region-pdo-union`** — the 2 CZ PGIs (`PGI-CZ-A0900` "české" /
   `PGI-CZ-A0902` "moravské") are the whole-Bohemia / whole-Moravia
   wine territories; Bétard is PDO-only, so each PGI is the union of
   the member-PDO polygons in that macro region. Both macro PDOs
   (Čechy / Morava) are themselves in Bétard, so the PGI union is a
   single-member fold (one macro PDO each — the territory is
   coextensive with the macro PDO of the same name).
4. **`stub-no-geometry`** — not normally hit in v1; all 13 CZ wines
   resolve.

The shared `raw/es/figshare/EU_PDO.gpkg` + `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`
are reused — no new fetch in stage 00.

### Curator workflow for CZ wines without an OJ publication

Mirrors the SK / SI / HR / BG / GR `regen_manual_overrides_template.py`
flow. All 13 CZ wines are grandfathered names with no fetchable
single-document URL. The variety roster + commune lists are recovered
from the national decrees via stage 02f (see above), so the curator
queue's remaining role is purely:

1. **Find an EUR-Lex JEDNOTNÝ DOKUMENT** if the Commission later
   publishes one (would replace the stub with a real cahier-style
   record + terroir text — see "structural limitation" below).
2. **Add an updated decree URL** to `scripts/cz/02f_extract_national_specs.py`'s
   `SOURCES` dict when Vyhláška 88/2017 or 254/2010 are amended.

For curator-pinned EU-OJ URLs:

```
.venv/bin/python scripts/cz/regen_manual_overrides_template.py
# edit raw/cz/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear specification (EUR-Lex OJ-C page if the Commission
# later publishes one, or the ÚKZÚZ / MZe national specifikace
# výrobku from the Czech Ministry of Agriculture).
.venv/bin/python scripts/cz/01_fetch_pliegos.py
.venv/bin/python scripts/cz/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Terroir text — solved via the SZPI CHZO specs (2026-05-31)**: Czech
wine law publishes no per-appellation CHOP (PDO) terroir narrative —
the EU JEDNOTNÝ DOKUMENT "Popis souvislostí" section is missing for all
13 grandfathered names, and even the 3 newer 2011 PDOs (Znojmo, Šobes,
Novosedelské Slámové víno) publish no documento unic publicly. The
earlier conclusion (zero terroir bullets, `/research-gaps
cz-specification` 2026-05-24, [tmp/cz-specification-research-results.md](tmp/cz-specification-research-results.md))
was correct *for the CHOP tier and the EU register*. But the **SZPI
publishes the two CHZO (PGI) product specifications** — full
EU-template specs whose section-1 region description is the regulator's
own terroir narrative for the Morava / Čechy wine region, covering all
13 CZ wines. See "CZ CHZO terroir + style layer" above; every CZ wine
now carries 7–10 regulator-grounded terroir facts (+ real styles for
the 2 PGIs). The lesson: hunt for the member-state inspectorate's
product specification before treating a country as a terroir stub.

## Luxembourg pipeline (`scripts/lu/`)

Country #15. **The smallest corpus to date — 1 wine GI** (`PDO-LU-A0452`
"Moselle Luxembourgeoise"), but the most fine-grained sub-denomination
expansion: 1 parent + **11 modern-commune sub-denominations** modelled
from the cahier's 15-commune perimeter list (collapsed via the post-
2011/2018/2023 fusion table).

Spine: **eAmbrosia EU register**, filtered `country=LU` +
`productType=WINE` + `status=registered`. The lone PDO's only
publication reference is the Ares numeric `58323` — no fetchable
EU-OJ Document Unique. Canonical source is the **IVV 2020 Cahier des
charges AOP Moselle luxembourgeoise** (French, ~14 pp, stable URL at
agriculture.public.lu) — sandbox curl/python-requests get HTTP 000
against agriculture.public.lu's WAF, so stage 01 documents a manual-
download workflow into `raw/lu/ivv/cahiers/2020-cahier.pdf`. The
cahier has 10 lettered sections (a-j):

  a) La dénomination à protéger
  b) La description du vin (5 wine-type subsections)
  c) Pratiques spécifiques (mention particulière)
  d) La délimitation de la zone géographique concernée
  e) Les rendements maximaux à l'hectare
  f) L'indication des variétés (14 varieties, each with prose)
  g) Lien avec l'aire géographique (climat / terroir / facteurs)
  h-j) Autorité de contrôle / Étiquetage / Pratiques culturales

Parsed by [scripts/_lib/lu/cahier.py](scripts/_lib/lu/cahier.py)
([line-anchored section splitter + form-feed strip; non-greedy
numbered-subsection matcher that uses lookbehind so consecutive
markers don't get eaten by the previous match's `\\n` consumption]).

| Script | Reads | Writes |
|---|---|---|
| lu/00_fetch_data.py | (network: eAmbrosia) | raw/lu/eambrosia/index.json + manifest.json |
| lu/01_fetch_cahier.py | raw/lu/ivv/cahiers/2020-cahier.pdf (manual download) + raw/lu/ivv/vineyards/weinberge-lu-2022/ | raw/lu/ivv/cahiers/2020-cahier.txt (pdftotext sidecar) + raw/lu/ivv/manifest.json |
| lu/02_extract_cahier.py | raw/lu/eambrosia/index.json + raw/lu/ivv/cahiers/2020-cahier.txt | raw/lu/cahier-extracted/*.json (1 parent + 11 sub-denominations) + _index.json |
| lu/02d_extract_terroir_facts.py | raw/lu/cahier-extracted/*.json + raw/wikipedia/aocs/fr/moselle-luxembourgeoise.json | raw/terroir-facts/moselle-luxembourgeoise.json (country="lu") + manifest-lu.json |
| lu/02e_translate_terroir_facts.py | raw/terroir-facts/moselle-luxembourgeoise.json (country="lu") | raw/translations/terroir-facts/<en\|es\|nl>/moselle-luxembourgeoise.json |
| lu/03_generate_wiki.py | raw/lu/cahier-extracted/*.json | wiki/<slug>.md (per LU record) + merges LU entries into wiki/_index.json |

LU-specific notes:
- `kind` is `"DOP"` (same convention as ES/PT/IT/AT/SI/HR/HU/RO/BG/GR/
  DE/SK/CZ). `country` is `"lu"`; **`source_lang` is `"fr"`** — like
  AT (`at`/`de`), SI (`si`/`sl`), GR (`gr`/`el`), CZ (`cz`/`cs`),
  the country code differs from the source language. The shared 02c
  stage already has `fr` as its default source language; stage 04
  treats LU as falling through to the `"fr"` default in the src_lang
  allowlists.
- The Luxembourg labelling tiers in RGD 17-déc-2015 are **predicate
  designations**, not curated rosters:
  - **Art. 8** — bare `section/commune/canton` name on labels
    (yield ≤100 hl/ha, 115 for Elbling/Rivaner)
  - **Art. 9 "Coteaux de"** — `+ section/commune/canton`, yield
    ≤75 hl/ha, hand-harvested
  - **Art. 10 "Lieu-dit"** — `+ section de commune`, yield ≤75 hl/ha,
    hand-harvested, no rosé/gris
  - Mentions traditionnelles (Art. 11-13): premier cru, grand premier
    cru, vendanges tardives, vin de paille, vin de glace, Crémant de
    Luxembourg

  v1 models the per-commune tier as 11 first-class sub-denomination
  records (one per modern wine commune), keyed by
  `slug=moselle-luxembourgeoise-<commune-slug>` and
  `parent_slug=moselle-luxembourgeoise`. Each inherits the parent's
  varieties + terroir + style list and carries a `historic_communes`
  alias array (Schengen ← Burmerange + Wellenstein; Bous-Waldbredimus
  ← Bous + Waldbredimus; Rosport - Mompach ← Rosport + Mompach).
- The cahier section f lists 14 varieties: Elbling, Rivaner (=Müller-
  Thurgau), Sylvaner, Auxerrois, Pinot blanc, Chardonnay, Pinot gris,
  Riesling, Gewürztraminer, Muscat-Ottonel, Pinot noir, Pinot noir
  précoce, Saint Laurent, Gamay. All resolve via the shared
  `grape_lexicon.py` (Pinot noir précoce added as alias for
  `frueburgunder` = DE Frühburgunder, same cultivar).
- Region facet = a single value, "Moselle Luxembourgeoise"
  ([scripts/_lib/lu/region.py](scripts/_lib/lu/region.py)) — the whole
  LU corpus shares one region in v1. Native form, not gettext-translated.
- **Lieu-dit tier (Art. 10) is deferred to Phase 2.** The cahier's
  section d points to a `geoportail.lu` IVV layer
  (`node_ivv_kleinlagen1`) for the named-single-vineyard polygons,
  but data.public.lu / agriculture.public.lu are sandbox-unreachable
  for programmatic fetch; the lieu-dit polygon dataset needs a
  separate manual-download step + license verification. v1 stops at
  the parent + per-commune-tier expansion.
- Stage 02d/02e wire terroir-fact extraction + translation for LU
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR/SK pairs). Dual-source
  grounding (cahier section g + fr.wikipedia.org umbrella
  `Viticulture au Luxembourg` article — LU has no dedicated per-AOP
  Wikipedia entry, so the umbrella article is pinned via
  `raw/wikipedia/aoc_overrides.json["fr"]["moselle-luxembourgeoise"]`
  pointing to `wiki_title="Viticulture au Luxembourg"`), French
  extraction prompt (preserves "Marque Nationale", IVV, Canton de
  Remich/Grevenmacher, marnes keupériennes, calcaire conchylien, …),
  fuzzy-coverage filter (≥ 0.6), per-bullet provenance (`cahier`/
  `wiki`/`both`), manual round-trip flow. v1 LU output: **10 bullets**
  across the 4 sub-section buckets (5 facteurs_naturels, 2
  facteurs_humains, 2 produit, 1 interactions); provenance mix `both` (3)
  / `cahier` (2) / `wiki` (5). The 11 commune sub-denominations inherit
  the parent's bullets at the rendering layer; 02d skips them.
  02e targets en/es/nl (fr is the source language, not a target).
  Cache files land in the shared `raw/terroir-facts/` directory with
  `country: "lu"` to distinguish them from the other corpora.

### LU geometry resolution chain (stage 04)

Per LU record, in priority order ([scripts/_lib/lu/geometry.py](scripts/_lib/lu/geometry.py)
`LUPolygonIndex.resolve`; `geom_source` records the choice):

1. **`ivv-commune-vineyard`** — for the 11 sub-denominations: union of
   IVV Weinbaukartei 2022 parcels whose representative point falls
   inside the modern GISCO LAU commune polygon. 4 521 parcels total
   (11.9 km² planted area across the 11 communes — Schengen 4.34 km²
   / 1971 parcels, Wormeldange 3.34 km² / 1142 parcels, …). Planted-
   vineyard precision; far more honest than the full GISCO admin
   polygon (Schengen admin ≈ 45 km² vs. 4.34 km² actually planted).
2. **`gisco-commune`** — defensive fallback when an IVV parcel
   dissolve returns empty for a commune. Full admin polygon, less
   precise but always available.
3. **`figshare-pdo`** — for the parent record: Bétard 2022
   `PDO-LU-A0452` polygon (245 km², the regulatory viticultural
   perimeter declared by Règlement grand-ducal du 9 sept 2009 — the
   superset of the IVV planted parcels). Matches the cahier's "zone
   géographique concernée" definition.
4. **`stub-no-geometry`** — last resort. Not normally hit in v1.

The shared `raw/es/figshare/EU_PDO.gpkg` + `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip`
are reused — no new fetch in stage 00 for those two. The IVV vineyard
shapefile at `raw/lu/ivv/vineyards/weinberge-lu-2022/weinberge_lu_2022.shp`
is the only LU-specific geodata asset (native EPSG:2169 / LUREF,
reprojected to EPSG:4326 at index load). License: Open Data
Luxembourg (CC-BY 4.0 / CC0 — pending curator confirmation of the
exact dataset page metadata).

### Curator workflow for LU

The cahier PDF needs a one-off manual download (sandbox can't reach
agriculture.public.lu); the IVV vineyard shapefile likewise needs a
manual download from data.public.lu. Both are sha-pinned in
`raw/lu/ivv/manifest.json` after stage 01 runs. The Phase 2
lieu-dit / `kleinlagen` layer needs the same manual-download flow
against the LU national geoportal (URL pinned in
[scripts/lu/01_fetch_cahier.py](scripts/lu/01_fetch_cahier.py) as a
curator hint).

## Belgium pipeline (`scripts/be/`)

Country #16. **10 wine GIs (7 PDOs + 2 PGIs + 1 cross-border BE+NL
PDO)** from eAmbrosia. Belgium is the **second country with per-record
`source_lang`** (Switzerland was the first) and the **first to use
`nl` as a source language** (until now `nl` was only a translation
TARGET locale). Flemish wines (5 records — the 3 Flemish DOPs +
Vlaamse landwijn + Vlaamse mousserende kwaliteitswijn) plus the
cross-border Maasvallei use `nl`; the 4 Walloon wines use `fr`.

Spine: **eAmbrosia EU register**, filtered `country=BE` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"ENIG DOCUMENT"** (Dutch) or **"DOCUMENT UNIQUE"** (French)
published inline as HTML, reached via each GI's `publications[].uri`
with a per-record language URL rewrite (`/legal-content/NL/TXT/HTML/`
or `/legal-content/FR/TXT/HTML/`; `…01.NLD` / `…01.FRA`; `/oj/nld` /
`/oj/fra`). Same AWS-WAF caveat as ES/IT/AT/SI/HR/HU/RO/BG/GR —
`scripts/be/01b_solve_waf.py` clears blocked URLs with headless
Chromium.

Coverage in the corpus: 4 of 10 BE wines have a fetchable EU-OJ URL
(the 3 Flemish DOPs Hagelandse / Haspengouwse / Heuvellandse plus
Maasvallei Limburg). The other 6 (the 4 Walloon DOPs + the 2 Flemish
PGIs) are Art.107 / Reg.1308/2013 grandfathered names with only a
non-fetchable `Ares(...)` summary-sheet in eAmbrosia. All 6 are now
recovered from public PDF specs pinned in `manual_overrides.json` (see
"BE PDF-source extension" below) — the **4 Walloon wines from their
eAmbrosia EU-register fiche technique** (the official EU single document,
carrying varieties + terroir), the **2 Flemish wines from Vlaamse-overheid
productdossiers** — so **all 10 BE wines extract (0 stubs), with terroir
text on all 10**. Every BE wine appears on the map: Bétard 2022 covers
each BE PDO + the cross-border Maasvallei polygon, and the 2 PGIs resolve
via region-pdo-union.

**Cross-border Maasvallei Limburg** (`PDO-BE+NL-02172`): emitted as a
single BE record (BE-primary by file_number ordering). The NL pipeline
(country #17) skips this file_number — the cross-border GI shows up
exactly once on the map, on the BE side. The detail panel surfaces
the cross-border nature via `country_aliases`: stage 04 reads the
`_CROSS_BORDER_COUNTRY_ALIASES` table in
[scripts/04_build_maps.py](scripts/04_build_maps.py) (keyed by
file_number → list of secondary country codes) and attaches `["nl"]`
to the Maasvallei record so the panel header renders both country
chips: `🇧🇪 Belgique · 🇳🇱 Pays-Bas · DOP · Vlaanderen · …`.
Adding another cross-border PDO later is a one-line entry in that
table.

| Script | Reads | Writes |
|---|---|---|
| be/00_fetch_data.py | (network: eAmbrosia) | raw/be/eambrosia/index.json + manifest.json |
| be/01_fetch_pliegos.py | raw/be/eambrosia/index.json + raw/be/oj-pages/manual_overrides.json | raw/be/oj-pages/*.html + manifest.json |
| be/01b_solve_waf.py | raw/be/oj-pages/manifest.json | raw/be/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| be/02_extract_pliegos.py | raw/be/oj-pages/*.html | raw/be/dokumenten-extracted/*.json + _index.json |
| be/02d_extract_terroir_facts.py | raw/be/dokumenten-extracted/*.json + raw/wikipedia/aocs/{nl,fr}/ | raw/terroir-facts/*.json (country="be") + manifest-be.json |
| be/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="be") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| be/03_generate_wiki.py | raw/be/dokumenten-extracted/*.json | wiki/<slug>.md (per BE record) + merges BE entries into wiki/_index.json |
| be/regen_manual_overrides_template.py | raw/be/eambrosia/index.json + raw/be/oj-pages/manifest.json | raw/be/oj-pages/manual_overrides.json (curator queue) |
| audit_be_coverage.py | raw/be/eambrosia/ + raw/be/dokumenten-extracted/ + raw/be/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table + curator queue) |

BE-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/AT/SI/HR/
  HU/RO/BG/GR/DE/SK/CZ). `country` is `"be"`; **`source_lang` is
  per-record** (`"nl"` for the 6 Flemish + Maasvallei, `"fr"` for the
  4 Walloon).
- The combined NL + FR template parser lives at
  [scripts/_lib/be/document.py](scripts/_lib/be/document.py) — one
  module, two keyword tables keyed by `source_lang`. The anchor regex
  tolerates the older `<span class="bold">`-wrapped variant of the
  ENIG-DOCUMENT / DOCUMENT-UNIQUE header (Maasvallei's 2017 OJ:C
  publication uses this form; the 2024 amendments use the bare form).
- The EU OJ template describes wine styles per-variety, not in
  whole-wine bucket sentences, so the section-text colour scan rarely
  matches; `parse_styles` falls back to inferring base styles from
  the grape-colour distribution (still-wine baseline). The
  STYLE_MARKERS table additionally covers Belgian-relevant
  categories: `Likeurwijn` → `vin-de-liqueur`, `Wijn uit overrijpe
  druiven` → `vendanges-tardives`, `Mousserende kwaliteitswijn` →
  `sparkling-quality`, `Parelwijn` → `semi-sparkling`, `Crémant`
  (Wallonie) → `cremant`.
- v1 models the 10 BE wine GIs as a **flat corpus** — no sub-
  denomination layer. Belgian wine law is too small to support
  sub-zones in v1.
- Region facet = **language community**
  ([scripts/_lib/be/region.py](scripts/_lib/be/region.py)):
  `Vlaanderen` (the 5 Flemish PDOs/PGIs — Dutch, the region's
  native language) and `Wallonie` (the 4 Walloon records — French,
  the region's native language). Each label is in the language
  actually spoken in that region, not in a single language imposed
  across the country. The cross-border Maasvallei Limburg PDO has
  no region label — both BE and NL sides were one duchy of Limburg
  until the 1839 partition, and "Vlaanderen" is only the Belgian
  federal region name, not a region of the appellation itself.
  The panel still surfaces the cross-border nature via the country
  chip (BE + NL — see [Cross-border PDOs](#cross-border-maasvallei-limburg-pdo-benl-02172) below).
  Region labels follow the AT/IT/ES/SI/HR/HU/RO/BG/GR/DE/SK/CZ
  convention — shown in their native form, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for BE
  (siblings of the ES/PT/IT/AT/SI/HR/HU/RO/BG/GR/DE/SK/CH/LU pairs).
  Dual-source grounding (ENIG DOCUMENT / DOCUMENT UNIQUE section 8 +
  per-record Wikipedia — `nl.wikipedia.org` for Flemish wines,
  `fr.wikipedia.org` for Walloon). Per-record source language drives
  the extraction prompt (Dutch or French versions both live in 02d).
  Fuzzy-coverage filter (≥ 0.6), per-bullet provenance, manual
  round-trip flow. Target locales per record = `{en,fr,es,nl} -
  {source_lang}` — so Flemish bullets translate to `{en,fr,es}` and
  Walloon bullets translate to `{en,nl,es}`. Cache files land in the
  shared `raw/terroir-facts/` directory with `country: "be"`.

### BE geometry resolution chain (stage 04)

Per BE record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-BE-*` or
   `PDO-BE+NL-*`) → `PDOid` match against Bétard 2022 EU\_PDO.gpkg.
   Covers all 8 BE+ PDOs. Reuses `raw/es/figshare/EU_PDO.gpkg`.
2. **`region-pdo-union`** — the 2 BE PGIs union their member-PDO
   polygons (the SI/HU/BG/DE PGI pattern). Members listed in
   `BE_PGI_MEMBER_PDOS` in
   [scripts/_lib/be/geometry.py](scripts/_lib/be/geometry.py):
   `PGI-BE-A1429` Vlaamse landwijn = the 5 Flemish PDOs (Hagelandse,
   Haspengouwse, Heuvellandse, Vlaamse mousserende kwaliteitswijn,
   Maasvallei); `PGI-BE-A0010` Vin de pays des jardins de Wallonie =
   the 3 Walloon still/sparkling PDOs.
3. **`stub-no-geometry`** — last resort. Not normally hit in v1; all
   10 BE wines resolve.

### BE PDF-source extension (EU register + Flemish PDF) — stage 02 text-mode parsers

6 BE wines have no fetchable EU-OJ HTML single document but do have a
public PDF spec; with all wired, **every BE wine extracts — 10/10,
0 stubs, terroir text on all 10**. Two source families:

**(a) eAmbrosia EU-register fiche technique — the 4 Walloon wines.** The
register (`ec.europa.eu/geographical-indications-register`) serves, per
GI, the official EU *fiche technique* PDF whose `I. DOCUMENT UNIQUE`
block is the standard single-document template (1 Dénomination … 5 Zone
délimitée, 6 Cépages principaux, 7 Description du ou des liens [terroir],
8 Autres conditions; numbering RESTARTS under `II. AUTRES INFORMATIONS`).
This is the canonical EU source even for the grandfathered `Ares(...)`-only
wines, and carries the varieties + terroir narrative the (now-abrogated)
Walloon WALLEX ministerial decrees lacked. Pinned URLs (the
`singleDocTechFile` attachment): Côtes de Sambre et Meuse #11689, Vin de
pays des Jardins de Wallonie #10993, Vin mousseux de qualité de Wallonie
#10994, Crémant de Wallonie #10434. Parsed by `parse_fiche_technique_text`
(slices the `I. DOCUMENT UNIQUE` block; monotonic 1→8 headers, so the
"1. Vin" / "4. Vin mousseux" sub-items under section 2 are dropped; strips
`label.*` i18n-key + per-page furniture noise; the §6 list is
`* Name COLOUR (OIV|OTHER)`, so the `*`/`**` prefixes and origin tags are
stripped). Yields CSM 25 / Jardins 21 / mousseux 7 / crémant 4 principal
varieties (richer than the abrogated WALLEX decrees) + 8-9 terroir-fact
bullets each (en/es/nl). Jardins went 0→21 grapes: the WALLEX decree said
only "Vitis vinifera ou croisement", but the fiche §6 enumerates the
principal cépages.

**(b) Vlaamse-overheid PDFs — the 2 Flemish wines.** Vlaamse mousserende
kwaliteitswijn (`lv.vlaanderen.be/media/9156/download`, geconsolideerd
enig document) and Vlaamse landwijn
(`lv.vlaanderen.be/sites/default/files/attachments/productdossier_bga_vlaamse_landwijn.pdf`,
productdossier BGA). Both EU-enig-document shape (numbered 1..9), parsed
by `parse_enig_document_text`. Vlaamse landwijn §7 is the broad-IGP rule
→ 0 grapes, but §8 *verband* → 8 terroir bullets.

All URLs are pinned via `raw/be/oj-pages/manual_overrides.json` and
fetched by stage 01 (`Content-Type: application/pdf` → `.pdf` cache).
Stage 02's `_extract_from_pdf` routes by source_lang: **fr →
`parse_fiche_technique_text`**, **nl → `parse_enig_document_text`**
([scripts/_lib/be/text_parser.py](scripts/_lib/be/text_parser.py)). Both
emit a synthetic sections dict keyed against the FR/NL
`SECTION_ROLE_KEYWORDS` (the FR `description` / `link_to_terroir` tables
gained the "description du ou des vin/lien" variants the fiche titles
use), so route_sections / parse_grapes / parse_styles / build_record run
unchanged. The earlier WALLEX chapter / standalone parsers were **retired**
when the 4 Walloon wines moved to the EU register.

Grape-matcher note: the fiche §6 roster includes a bare "Seibel" (the
French-American hybridiser *family* name, not a determinate cultivar)
which fuzzy-matched the Tempranillo VIVC synonym "Sensibel" (85.7, same
first char → passed the sanity guard). Bare `seibel` is therefore in
`_BANNED_SURFACES` in
[scripts/_lib/grape_entity.py](scripts/_lib/grape_entity.py) — only the
numbered "Seibel NNNN" cultivars (which keep their release number) resolve.

(No abrogation note is shown for the Walloon wines: the data now comes
from the valid EU-register fiche technique, not the abrogated national
WALLEX decree, so the earlier `appellation_notes.json` caveat was removed.)

### eAmbrosia register attachment endpoint (corpus-wide lead — deferred)

`ec.europa.eu/geographical-indications-register/eambrosia-public-api`
(OpenAPI at `/v3/api-docs`) exposes, per GI, both the **fiche technique /
single document** (`singleDocTechFile[].uri`) and the **full national
cahier des charges** (`productSpecifications[].uri`) as
`/api/v1/attachments/<uri>` PDFs — reachable for the whole grandfathered
`Ares(...)`-only population, not just BE. Discovery chain:

```
giIdentifier "EUGI0000000NNNN" → strip prefix → /api/gi-applications/id/<NNNN>
  → singleDocTechFile[].uri → /api/v1/attachments/<uri>   (EU single document, uniform template)
  → productSpecifications[].uri → /api/v1/attachments/<uri> (full national cahier, varied layout)
```

Gotchas: the GI detail is `GET /api/gi-applications/id/<n>` where `<n>` is
the integer part of the EUGI id (the `POST /api/gi-applications/filter`
body shape is finicky — an empty `{"filters":[]}` returns all rows with
`id` / `appUniqueId`); and the attachment endpoint is **browser-gated** —
it serves an HTML stub unless the request sends a real browser UA **and an
Accept WITHOUT `application/pdf`** (an explicit pdf Accept trips the gate),
and answers **HTTP 202 with the PDF body**. Stage 01 special-cases the
register host (`_BROWSER_HEADERS`) and accepts 202-with-pdf. This is
plausibly the canonical EU source for the corpus-wide stub population that
currently relies on bespoke national-spec parsers
(ES MAPA / IT MASAF / SI–HR–BG IAVV-style / RO ONVPV / SK ÚPV / CZ SZPI /
HU termékleírás). Migration is **deferred** — a spike (sample a few
countries, confirm coverage + parser cost) is a CURATOR_TODO item.

### Curator workflow for BE wines without an OJ publication

Mirrors the SK / SI / HR / BG / GR / HU / RO
`regen_manual_overrides_template.py` flow. All 6 BE wines without a
fetchable single-document URL are **already recovered** via the PDF
parsers above (the 4 Walloon wines from the eAmbrosia EU-register fiche
technique; the 2 Flemish wines from Vlaamse-overheid productdossiers on
vlaanderen.be) — BE is at 0 stubs. The flow below is for a *new* BE
wine, a rotated URL, or a curator-pinned EUR-Lex single document:

```
.venv/bin/python scripts/be/regen_manual_overrides_template.py
# edit raw/be/oj-pages/manual_overrides.json: fill `url` with a public,
# licence-clear specification (EUR-Lex OJ-C page, or the regional
# ministry's national specification).
.venv/bin/python scripts/be/01_fetch_pliegos.py
.venv/bin/python scripts/be/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

**Caveat**: stage 02's HTML path only understands the EU-OJ
ENIG-DOCUMENT / DOCUMENT-UNIQUE template; PDF specs need a per-source
text-mode parser (the `parse_fiche_technique_text` [FR EU fiche] and
`parse_enig_document_text` [Flemish] branches in
[scripts/_lib/be/text_parser.py](scripts/_lib/be/text_parser.py) are
the existing examples; mirrors the ES MAPA / IT MASAF / DE BLE
pattern).

## Netherlands pipeline (`scripts/nl/`)

Country #17. **21 wine GIs (9 standalone PDOs + 12 province-PGIs)**
from eAmbrosia. The cross-border BE+NL PDO Maasvallei Limburg ships
on the BE side; NL stage 00 explicitly skips it. The Netherlands is
the **first single-source-lang NL pipeline** in the corpus (Belgium
introduced `nl` as a source language but per-record); NL re-uses the
Dutch downstream infrastructure (02b Wikipedia cache
`raw/wikipedia/aocs/nl/`, 02e translation glossary, locale catalog)
that BE put in place.

Coverage in the corpus: all 22 NL wines (counting Maasvallei) have a
fetchable EU-OJ URL — the best ratio after Austria (100 %). The 12
PGIs ARE the 12 Dutch provincies (Limburg, Gelderland, Zeeland,
Noord-Brabant, Zuid-Holland, Noord-Holland, Utrecht, Overijssel,
Flevoland, Drenthe, Groningen, Friesland), each defined to allow the
full Dutch national variety roster (~97-107 grapes per PGI). The 9
PDOs are commune- or single-vineyard scale (Mergelland, Vijlen, Oolde,
Ambt Delden, Achterhoek - Winterswijk, Rivierenland, Schouwen-
Duiveland, De Voerendaalse Bergen, Twente).

Spine: **eAmbrosia EU register**, filtered `country=NL` +
`productType=WINE` + `status=registered`, minus the cross-border
Maasvallei. Pliego source: the EU-OJ **"ENIG DOCUMENT"** published
inline as HTML, reached via each GI's `publications[].uri` (Dutch-
language URL rewrite — `/legal-content/NL/TXT/HTML/`, `…01.NLD`,
`/oj/nld`). Same AWS-WAF caveat as the other EU-OJ-template
countries — `scripts/nl/01b_solve_waf.py` clears blocked URLs with
headless Chromium.

Edge case (resolved 2026-05-31): Ambt Delden (`PDO-NL-02169`) has no
published Dutch translation of its single document — EUR-Lex serves the
2018 Commission Implementing Decision (CELEX 32018D0316(02)) which
embeds the full **English** SINGLE DOCUMENT, and the 2024 Dutch
publication eAmbrosia now lists (OJ C/2024/2046) is AWS-WAF-blocked
(202 / empty), so it can't be used. Stage 02 handles this with a
self-contained **English-template fallback**: when the Dutch
`ENIG DOCUMENT` anchor misses, `_extract_from_html` re-anchors on
`SINGLE DOCUMENT`, slices with `extract_sections_en` (a monotonic
top-level-number extractor — skip nested `5.x` and repeated
"Wine category …" sub-headers, keep only a strictly increasing 1→N
run, the Malta/HU/BG idiom), and routes with a local English keyword
table. A self-guarding merged-cell splitter (`_merged_cell_matches`)
recovers two varieties packed into one table cell ("Solaris Regent" →
solaris + regent), splitting only when every whitespace token
independently resolves so multi-word names never split. No manual
override and no Playwright are needed — the 2018 CELEX is the index's
own source. ambt-delden = 5 varieties, geo area, 6.8 KB
link-to-terroir (9 terroir facts). v1: **21/21 NL wines extract,
0 stubs.**

| Script | Reads | Writes |
|---|---|---|
| nl/00_fetch_data.py | (network: eAmbrosia + Eurostat NUTS-2) | raw/nl/eambrosia/index.json + manifest.json + raw/nl/nuts/NUTS_RG_03M_2024_4326_LEVL_2.geojson |
| nl/01_fetch_pliegos.py | raw/nl/eambrosia/index.json + raw/nl/oj-pages/manual_overrides.json | raw/nl/oj-pages/*.html + manifest.json |
| nl/01b_solve_waf.py | raw/nl/oj-pages/manifest.json | raw/nl/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| nl/02_extract_pliegos.py | raw/nl/oj-pages/*.html | raw/nl/dokumenten-extracted/*.json + _index.json |
| nl/02d_extract_terroir_facts.py | raw/nl/dokumenten-extracted/*.json + raw/wikipedia/aocs/nl/ | raw/terroir-facts/*.json (country="nl") + manifest-nl.json |
| nl/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="nl") | raw/translations/terroir-facts/<en\|fr\|es>/*.json |
| nl/03_generate_wiki.py | raw/nl/dokumenten-extracted/*.json | wiki/<slug>.md (per NL record) + merges NL entries into wiki/_index.json |
| nl/regen_manual_overrides_template.py | raw/nl/eambrosia/index.json + raw/nl/oj-pages/manifest.json | raw/nl/oj-pages/manual_overrides.json (curator queue) |
| audit_nl_coverage.py | raw/nl/eambrosia/ + raw/nl/dokumenten-extracted/ + raw/nl/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg + raw/nl/nuts/ | (stdout — coverage table) |

NL-specific notes:
- `kind` is `"DOP"` / `"IGP"`. `country` is `"nl"`; `source_lang` is
  also `"nl"` (matches the prior convention where country code
  equals language code, like ES/PT/IT/HR/HU/RO/BG).
- The Dutch ENIG DOCUMENT template is parsed by
  [scripts/_lib/nl/enig_document.py](scripts/_lib/nl/enig_document.py)
  (sibling of the BE NL table; kept separate so NL-only parser quirks
  land in the right country namespace). Anchor regex tolerates the
  older `<span class="bold">`-wrapped variant.
- Region facet = **provincie**
  ([scripts/_lib/nl/region.py](scripts/_lib/nl/region.py)): each of
  the 12 provincies (Limburg, Gelderland, Zeeland, Noord-Brabant,
  Zuid-Holland, Noord-Holland, Utrecht, Overijssel, Flevoland,
  Drenthe, Groningen, Friesland). Each PGI ARE its province; each
  PDO maps to exactly one province (curated file_number map).
  Native Dutch labels, not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for NL
  (siblings of the BE/CH pairs). Dutch extraction prompt + dual-
  source grounding (ENIG DOCUMENT + nl.wikipedia.org). Fuzzy-coverage
  filter (≥ 0.6), per-bullet provenance, manual round-trip flow.
  Target locales = `{en,fr,es}` (nl excluded — it's the source).
  Cache files land in the shared `raw/terroir-facts/` directory with
  `country: "nl"`.

### NL geometry resolution chain (stage 04)

Per NL record, in priority order (`geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` (`PDO-NL-*`) → `PDOid`
   match against Bétard 2022 EU\_PDO.gpkg. Covers 6 of 10 NL PDOs:
   Mergelland (`PDO-NL-02114`), Vijlen (`PDO-NL-02168`), Ambt Delden
   (`PDO-NL-02169`), Oolde (`PDO-NL-02230`), Achterhoek-Winterswijk
   (`PDO-NL-02402`), Maasvallei (`PDO-BE+NL-02172` — owned by BE).
2. **`nuts2-province`** — the 12 NL PGIs are coextensive with the 12
   Dutch provinces; each resolves to the matching Eurostat NUTS-2
   polygon (NL11 Groningen, NL12 Friesland, NL13 Drenthe, NL21
   Overijssel, NL22 Gelderland, NL23 Flevoland, NL32 Noord-Holland,
   NL34 Zeeland, NL35 Utrecht, NL36 Zuid-Holland, NL41 Noord-Brabant,
   NL42 Limburg). Mapping in
   [scripts/_lib/nl/geometry.py](scripts/_lib/nl/geometry.py)
   `PGI_FILE_NUMBER_TO_NUTS2`. Fetched once at stage 00 (~4 MB).
3. **`stub-no-geometry`** — the 4 newer PDOs that post-date the Bétard
   2022 snapshot (`PDO-NL-02774` Rivierenland, `PDO-NL-02775`
   Schouwen-Duiveland, `PDO-NL-02776` De Voerendaalse Bergen,
   `PDO-NL-02873` Twente). Visible in the sidebar/search, absent
   from the map until Phase 2 parses commune lists from their
   ENIG DOCUMENT against shared GISCO LAU (the RO IGP / BG fallback
   pattern).

The shared `raw/es/figshare/EU_PDO.gpkg` is re-used. The
NL-specific NUTS-2 GeoJSON (`raw/nl/nuts/`) is the only new geodata
asset; it is licensed © European Union, Eurostat / GISCO (permitted
commercial use with attribution).

### Curator workflow for NL

All 21 NL wines now extract (0 stubs) — Ambt Delden via the
English-template fallback (see the edge-case note above). If a future
NL wine is published English-only it extracts the same way; the
standard `regen_manual_overrides_template.py` flow remains for pinning
a corrected EU-OJ URL or — Phase 2 — the RVO national productdossier.

## Malta pipeline (`scripts/mt/`)

Country #18 and the **first English-source corpus**. 3 wine GIs from
eAmbrosia: 2 PDOs (Malta `PDO-MT-A1630`, Gozo `PDO-MT-A1629`) + 1 PGI
(Maltese Islands `PGI-MT-A1631`). Structurally the simplest EU-OJ
single-document pipeline after Croatia — Bétard PDO geometry + a single
PGI region-union, no national-spec layer.

Spine: **eAmbrosia EU register**, filtered `country=MT` +
`productType=WINE` + `status=registered`. Pliego source: the EU-OJ
**"SINGLE DOCUMENT"** published inline as HTML in **English** (Malta is
bilingual mt/en and the EU-OJ Maltese-wine documents are issued in
English), reached via each GI's `publications[].uri` (`/legal-content/
EN/TXT/HTML/`, `…01.ENG`). Same AWS-WAF caveat as the other EU-OJ
countries — `scripts/mt/01b_solve_waf.py` is the Chromium bootstrap
(neither Malta wine triggered it on the first run).

| Script | Reads | Writes |
|---|---|---|
| mt/00_fetch_data.py | (network: eAmbrosia) | raw/mt/eambrosia/index.json + manifest.json |
| mt/01_fetch_pliegos.py | raw/mt/eambrosia/index.json + raw/mt/oj-pages/manual_overrides.json | raw/mt/oj-pages/*.html + manifest.json |
| mt/01b_solve_waf.py | raw/mt/oj-pages/manifest.json | raw/mt/oj-pages/*.html (WAF-blocked subset, via headless Chromium) |
| mt/02_extract_pliegos.py | raw/mt/oj-pages/*.html | raw/mt/dokumente-extracted/*.json + _index.json |
| mt/02d_extract_terroir_facts.py | raw/mt/dokumente-extracted/*.json + raw/wikipedia/aocs/en/ | raw/terroir-facts/*.json (country="mt") + manifest-mt.json |
| mt/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="mt") | raw/translations/terroir-facts/<fr\|es\|nl>/*.json |
| mt/03_generate_wiki.py | raw/mt/dokumente-extracted/*.json | wiki/<slug>.md (per MT record) + merges MT entries into wiki/_index.json |
| mt/regen_manual_overrides_template.py | raw/mt/eambrosia/index.json + raw/mt/oj-pages/manifest.json | raw/mt/oj-pages/manual_overrides.json (curator queue) |
| audit_mt_coverage.py | raw/mt/eambrosia/ + raw/mt/dokumente-extracted/ + raw/mt/oj-pages/manifest.json + raw/es/figshare/EU_PDO.gpkg + raw/terroir-facts/ | (stdout — coverage table) |

MT-specific notes:
- `kind` is `"DOP"` / `"IGP"` (same convention as ES/PT/IT/…). `country`
  is `"mt"`; **`source_lang` is `"en"`** — Malta is the first corpus
  whose source language is English. EN is also the canonical rendered
  surface (`/`), so the extracted narrative needs no machine translation
  for the homepage; stage 02e only produces fr/es/nl. The stage-04
  src_lang resolvers (`_src_lang_for` + the summary/facts overlay) map
  `country=="mt"` → `"en"` explicitly, the way `lu`→`fr` is handled.
- The English SINGLE-DOCUMENT template is parsed by
  [scripts/_lib/mt/single_document.py](scripts/_lib/mt/single_document.py)
  (English section-keyword role routing — *Name(s)*, *Demarcated
  geographical area*, *Main wine grapes variety(ies)*, *Description of
  the link(s)*, …). Both Malta documents are **STANDARD AMENDMENT**
  communications, so `extract_sections` uses the HU/BG monotonic-number
  state machine: sections 4 & 5 nest `<p class="ti-grseq-1">`
  subsections that restart numbering at 1 (per-wine-type descriptions,
  per-variety oenological practices — "1. Passito", "1. Malbec"), and
  the `last_top + 1` guard keeps those from shadowing the real top-level
  sections.
- The section-7 variety list is flat (no principal/accessory split) →
  all `principal`. The two indigenous varieties **Ġellewża** (red) and
  **Girgentina** (white) are folded into the shared `GRAPE_ALIAS` /
  `DEFAULT_COLOUR` tables in
  [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) (both
  round-trip through unidecode, so the diacritic and plain spellings
  fold to one slug); the other ~30 are international varieties already
  in the lexicon.
- Region facet = the wine island
  ([scripts/_lib/mt/region.py](scripts/_lib/mt/region.py)): "Malta" /
  "Gozo" for the two PDOs, "Maltese Islands" for the archipelago-wide
  PGI. Native form, not gettext-translated.
- v1 models the 3 wine GIs as a **flat corpus** — no sub-denominations.

### MT terroir facts — Wikipedia-primary (the CH/LU model)

The STANDARD AMENDMENT documents restate only *changed* sections, so
section 8 ("Description of the link(s)") reads literally "No amendments
are to be carried out in this section." for both PDOs — there is no
link-to-terroir narrative in the regulator source. Exactly as for
Switzerland's règlements, MT terroir facts therefore ground on the
**English Wikipedia "Maltese wine" article** (pinned for all three GIs
via `raw/wikipedia/aoc_overrides.json["en"]` — the CH/LU umbrella-
article pattern), with the regulator data (region, varieties,
demarcated area) as secondary context. `scripts/02b_fetch_aoc_lexicon.py`
gained an `"en"` `LANG_CONFIG` entry (`--lang en` → en.wikipedia.org).
02d/02e are siblings of the CH pair (English prompt, single source_lang
"en", same 4-subsection schema + fuzzy-coverage filter); 02e targets
fr/es/nl. v1 yield: 2 facts each for Malta/Gozo/Maltese-Islands.

### MT geometry resolution chain (stage 04)

Per MT record, in priority order
([scripts/_lib/mt/geometry.py](scripts/_lib/mt/geometry.py)
`MTPolygonIndex.resolve`; `geom_source` records the choice):

1. **`figshare-pdo`** — exact `file_number` → `PDOid` match against
   Bétard 2022 EU_PDO.gpkg. Covers both MT PDOs (Malta, Gozo). The
   shared `raw/es/figshare/EU_PDO.gpkg` — no new fetch in stage 00.
2. **`region-pdo-union`** — the single MT PGI ("Maltese Islands") is the
   whole archipelago; Bétard is PDO-only, so it is the union of the two
   MT PDO polygons (the SI/CZ/HU/BG pattern).
3. **`stub-no-geometry`** — not hit in v1; all 3 MT wines resolve.

### Curator workflow for MT

Both PDOs carry a fetchable English SINGLE DOCUMENT; only the "Maltese
Islands" PGI is a no-publication grandfathered name, and it still
appears on the map via `region-pdo-union`. `regen_manual_overrides_
template.py` writes a 1-entry queue for it — the curator's only job is
to pin a public, licence-clear EU-OJ English SINGLE-DOCUMENT page if
the Commission ever publishes one, then re-run mt/01 → mt/02 → stage 04.

## Batch API (02b-grapes / 02c / 02d / 02e)

The LLM stages — `02b_translate_grapes` (grape-tooltip translation),
`02c` (summary translation), `02d` (terroir-fact extraction) and `02e`
(bullet translation), every country — accept a `--batch` flag. With
`--provider anthropic` or `--provider mistral` it submits the whole
eligible corpus to that provider's Batch API as one job (~50 % cheaper
than synchronous calls) instead of looping `provider.chat()`. (Note:
the synchronous `--provider anthropic` path reads the key from the
environment only, so `02b_translate_grapes --provider anthropic`
without `--batch` needs `ANTHROPIC_API_KEY` exported; the `--batch`
path loads `.env` itself.)

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
- **No silent dict-key overrides.** Python keeps the *last* value when a dict
  literal repeats a key, so a key re-bound to a different value is a silent
  override — it once split VIVC #4121 (Fetească regală / Királyleányka) across
  two grape slugs in `grape_lexicon.py`. The guard
  [scripts/audit_dup_keys.py](scripts/audit_dup_keys.py) scans every dict
  literal under `scripts/` and exits non-zero on any such *clash* (it also lists
  benign same-value dups without failing); `tests/test_no_duplicate_keys.py`
  runs it under `pytest`. Run `.venv/bin/python scripts/audit_dup_keys.py` (or
  `pytest`) after editing `grape_lexicon.py` or any other large lookup table.
