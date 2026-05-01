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
- **Wikipedia is a bounded secondary source.** Stage 02b
  (`scripts/02b_fetch_grape_lexicon.py`) fetches one short summary per grape
  variety from Wikipedia (CC-BY-SA 4.0) for use in the map sidepanel tooltip.
  Cahier text, commune lists, region names, and INAO category codes continue to
  come exclusively from INAO/JORF. Each Wikipedia entry caches `revision_id`,
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
| 00_fetch_data.py | (network) | raw/inao/siqo-referentiel.csv, raw/ign/communes.geojson, raw/inao/parcellaire/*.shp |
| 01_scrape_cahiers.py | raw/inao/siqo-referentiel.csv | raw/inao/cahiers/*.pdf, raw/inao/cahiers/manifest.json |
| 02_extract_cahiers.py | raw/inao/cahiers/*.pdf | raw/inao/cahier-extracted/*.json + _index.json |
| 02b_fetch_grape_lexicon.py | raw/inao/cahier-extracted/*.json | raw/wikipedia/grapes/<lang>/*.json + manifest.json |
| 02c_translate_summaries.py | raw/inao/cahier-extracted/*.json | raw/translations/summaries/<lang>/*.json |
| 03_generate_wiki.py | raw/inao/cahier-extracted/*.json | wiki/*.md, wiki/_index.json |
| 04_build_maps.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/grapes/ + raw/translations/summaries/ + raw/ign/communes.geojson + raw/inao/parcellaire/ | wiki/map.{html,en.html,es.html,nl.html}, wiki/map-data/*.pmtiles |

## Internationalisation

The map UI chrome (sidebar labels, panel headings, link texts, style chip
names) is translated into `en` / `es` / `nl` via gettext. Stage 04 emits one
`map.<lang>.html` per locale; `map.html` is the French source.

**UI chrome is translated via gettext; the cahier summary paragraph is
translated via stage 02c (machine translation with cahier-source attribution
preserved — see the bounded-narrative-layer rule above).** All other per-AOC
content shown in the detail panel — appellation names, region names, commune
lists, grape varieties, and INAO category codes — stays in French because it
is verbatim cahier data and translating it would lose the public-source
provenance. Bassin (region) labels are an exception: their translations live
in the gettext catalog because the FR forms are well-known proper nouns with
public, stable translations.

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
