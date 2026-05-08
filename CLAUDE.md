# open wine map — curation guide for Claude

This project is a reference wiki + map of French wine appellations, generated
mechanically from public INAO and IGN data. It is **not** a hand-curated
narrative wiki.

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
  Wikipedia FR (CC-BY-SA 4.0):
  - Stage 02b/grapes (`scripts/02b_fetch_grape_lexicon.py`) — one short
    summary per grape variety, used in the map sidepanel grape-pill tooltip.
  - Stage 02b/aocs (`scripts/02b_fetch_aoc_lexicon.py`) — per-AOC page
    (lead, section headings, full plaintext), used in stage 02d as a
    salience hint for terroir-fact extraction (see the bounded-narrative-
    layer rule below).
  - Stage 02b/styles (`scripts/02b_fetch_style_lexicon.py`) — one short
    summary per *distinctive* French wine style (vin jaune, crémant, vin
    doux naturel, vin de paille, sélection de grains nobles, vendanges
    tardives, clairet, primeur, vin de liqueur), used in the map
    sidepanel style-pill tooltip. The curated subset and per-locale
    Wikipedia titles live in
    `raw/wikipedia/style_overrides.json`; generic categories (red /
    white / rosé / dry / sweet / sparkling / tranquille) are
    intentionally excluded — their Wikipedia pages read as general wine
    education, not a meaningful tooltip.
  Cahier text, commune lists, region names, and INAO category codes continue to
  come exclusively from INAO/JORF. Each Wikipedia entry caches `revision`,
  `fetched_at`, `page_url`, and `license`; the UI must render attribution
  ("via Wikipedia · CC BY-SA 4.0") next to any extract it shows.
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

## Denomination model (DGCs)

The unit of generation is the **denomination** (`id_denomination_geo` in the
SIQO referentiel), not the appellation. Most appellations have a single
denomination — their own name — but some carry several Dénominations
Géographiques Complémentaires (DGCs):

- *Muscadet Sèvre et Maine* (id_appellation=100) has 7 DGCs: Clisson,
  Gorges, Le Pallet, Château-Thébaud, Goulaine, Monnières-Saint-Fiacre,
  Mouzillon-Tillières.
- *Côtes du Rhône Villages*, *Coteaux du Layon*, *Alsace grand cru*, *Côtes
  du Roussillon Villages* and others follow the same pattern.

Stage 02 emits one JSON per (id_appellation, id_denomination_geo) pair. The
parent denomination (where `denomination == appellation`) gets the canonical
slug; each DGC gets `slug(denomination)` and carries `is_dgc=true` plus
`parent_id_appellation`, `parent_slug`, `parent_name`. DGCs share the
parent's cahier text — INAO publishes one cahier des charges per
appellation, and DGC sub-sections inside it are not parsed in v1, so DGC
records inherit `sections` / `aire` / `grapes` / `styles` from the parent.

Stage 04 resolves DGC geometry by `id_denomination_geo` against the INAO
parcellaire shapefile (the shapefile carries `id_denom` on every parcel
row); when a DGC has no parcellaire row (~150 of ~1080 SIQO DGCs) it falls
back to the parent appellation's polygon, so the DGC is still on the map
and findable. DGCs ride the same `appellations` MVT layer — they're
filterable through the existing region/style/grape facets like any other
appellation.

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
| 02b_fetch_grape_lexicon.py | raw/inao/cahier-extracted/*.json | raw/wikipedia/grapes/<lang>/*.json + manifest.json |
| 02b_fetch_aoc_lexicon.py | raw/inao/cahier-extracted/*.json | raw/wikipedia/aocs/fr/*.json + manifest.json |
| 02b_fetch_style_lexicon.py | raw/wikipedia/style_overrides.json | raw/wikipedia/styles/<lang>/*.json + manifest.json |
| 02c_translate_summaries.py | raw/inao/cahier-extracted/*.json | raw/translations/summaries/<lang>/*.json |
| 02d_extract_terroir_facts.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/aocs/fr/ | raw/terroir-facts/*.json + manifest.json |
| 02e_translate_terroir_facts.py | raw/terroir-facts/*.json | raw/translations/terroir-facts/<lang>/*.json |
| 03_generate_wiki.py | raw/inao/cahier-extracted/*.json + raw/terroir-facts/ | wiki/*.md, wiki/_index.json |
| 04_build_maps.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/grapes/ + raw/wikipedia/styles/ + raw/wikipedia/aocs/ + raw/translations/summaries/ + raw/translations/terroir-facts/ + raw/terroir-facts/ + raw/ign/communes.geojson + raw/inao/parcellaire/ + raw/cadastre/lieux-dits/ | wiki/index.html (EN canonical = homepage), wiki/{fr,es,nl}/index.html, wiki/map-data/*.pmtiles, wiki/robots.txt, wiki/sitemap.xml (homepage × 4 locales) |

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
hand-editable. The extraction surface is `scripts/_lib/map_template.py` (the
`build_labels` and `build_style_labels` functions). Stage 04 calls
`scripts/_lib/i18n.py:compile_catalogs()` at the start of each run; it rebuilds
`messages.mo` only when the `.po` is newer (no-op on rerun).

```
uv run pybabel extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/map_template.py
uv run pybabel update -i locale/messages.pot -d locale     # after adding a new msgid
uv run pybabel init   -i locale/messages.pot -d locale -l <lang>   # to add a new locale
```

After editing a `.po`, just rerun `uv run scripts/04_build_maps.py`.

## Code style

- Python 3.12, ruff line length 100.
- Single-purpose scripts; share helpers via `scripts/_lib/`.
- No comments unless the *why* is non-obvious. Identifiers carry the *what*.
- Logs to stderr, structured progress (per-AOC) so reruns are debuggable.
