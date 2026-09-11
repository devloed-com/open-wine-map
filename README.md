# Open Wine Map

A reference wiki + map of European wine appellations, generated mechanically
from public regulator data. France (INAO + JORF) is the canonical pipeline;
the other 20 countries, the United Kingdom included, each have a sibling
pipeline under `scripts/<cc>/` sourced from the eAmbrosia EU register, the
national regulator, the Swiss federal repertoire or the UK GI register. The
per-country list, coverage and mechanics live in `CLAUDE.md`. Every
per-record fact traces back to a public-source document — nothing here is
hand-written narrative.

## Status

The FR pipeline runs end-to-end across the full AOC/AOP/IGP corpus, emitting
per-denomination markdown pages (one per appellation plus one per DGC —
Muscadet sub-crus, Côtes du Rhône Villages, Alsace grands crus, Chablis
premier-cru climats, etc.). The other 20 country pipelines follow the same
stage layout (00 fetch → 01 fetch documents → 02 extract → 02d/02e terroir
facts → 03 wiki), each with its own document source and geometry chain;
coverage per country is a function of which wines have a fetchable
specification, and `CLAUDE.md` documents every country's sources, coverage
and curator workflow. Stage 04 merges all 21 streams into a single
four-locale interactive map (EN / FR / ES / NL). The site is deployed at
<https://www.openwinemap.com>.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

For LLM-driven stages (machine translation in 02c/02e, terroir-fact
extraction in 02d), set:

```
export ANTHROPIC_API_KEY=...
```

Each of those stages also supports `--provider=ollama` (local Ollama HTTP
API) and `--provider=manual` (round-trip flow — see below).

## Running the pipeline

Stages are independent and re-runnable. Each writes a manifest, so reruns
are no-ops when nothing upstream changed. Run them in order from a clean
checkout to rebuild `wiki/` from scratch.

For the unattended happy path, `scripts/run_pipeline.py` drives FR + ES
end-to-end (then stage 04). It forwards `--provider` / `--workers` /
`--model` / `--ollama-url` to the LLM stages (02c / 02d / 02e), and
supports slicing with `--fr` / `--es` / `--from=STAGE` / `--to=STAGE`.
Stage names are the script path under `scripts/` minus `.py` (e.g.
`02_extract_cahiers`, `es/02_extract_pliegos`). Use `--list` to preview
the resolved plan. The PT pipeline is run directly (see below) — it's
not yet wired into the driver.

```
.venv/bin/python scripts/run_pipeline.py --provider=ollama --workers=2
.venv/bin/python scripts/run_pipeline.py --fr --from=02_extract_cahiers --provider=ollama
.venv/bin/python scripts/run_pipeline.py --es --from=02_extract_pliegos --list
```

Caveat for stage 01: PDF downloads are content-addressed and skip when the
sha is already on disk, but the INAO product-page → `show_texte` → BO Agri
*resolution walk* runs on every invocation (thousands of HTTP requests at
`--delay 0.8`). This is intentional — it's how newly-published modifying
arrêtés get discovered — so a rerun against a fully-populated manifest is
still chatty, just bandwidth-light.

FR pipeline:

```
uv run scripts/00_fetch_data.py               # public datasets       → raw/
uv run scripts/01_scrape_cahiers.py           # cahier PDFs           → raw/inao/cahiers/
uv run scripts/01b_solve_legifrance.py        # Legifrance-only AOCs via headless Chromium (optional)
uv run scripts/02_extract_cahiers.py          # PDF → JSON            → raw/inao/cahier-extracted/
uv run scripts/02b_fetch_grape_lexicon.py     # Wikipedia (grapes)    → raw/wikipedia/grapes/
uv run scripts/02b_fetch_aoc_lexicon.py       # Wikipedia (AOCs, fr)  → raw/wikipedia/aocs/fr/
uv run scripts/02b_fetch_style_lexicon.py     # Wikipedia (styles)    → raw/wikipedia/styles/
uv run scripts/02b_translate_grapes.py        # grape-tooltip i18n    → raw/translations/grapes/
uv run scripts/02b_translate_styles.py        # style-tooltip i18n    → raw/translations/styles/
uv run scripts/02g_fetch_vivc.py              # VIVC IDs + prime names → raw/vivc/
uv run scripts/02d_extract_terroir_facts.py   # cahier+wiki bullets   → raw/terroir-facts/
uv run scripts/02c_translate_summaries.py     # FR → en/es/nl         → raw/translations/summaries/
uv run scripts/02e_translate_terroir_facts.py # FR → en/es/nl         → raw/translations/terroir-facts/
uv run scripts/03_generate_wiki.py            # markdown pages        → wiki/*.md
```

ES pipeline (run before stage 04 so its records merge into the map):

```
uv run scripts/es/00_fetch_data.py             # eAmbrosia + GISCO + SIGPAC → raw/es/
uv run scripts/es/01_fetch_pliegos.py          # EU-OJ HTML pliegos → raw/es/oj-pages/
uv run scripts/es/01b_solve_waf.py             # WAF-blocked subset via headless Chromium
uv run scripts/es/02_extract_pliegos.py        # HTML → JSON        → raw/es/pliegos-extracted/
uv run scripts/es/02f_extract_national_pliegos.py --all  # national-pliego variety augmentation
uv run scripts/02b_fetch_aoc_lexicon.py --lang es --source raw/es/pliegos-extracted/
uv run scripts/es/02d_extract_terroir_facts.py
uv run scripts/es/02e_translate_terroir_facts.py
uv run scripts/es/03_generate_wiki.py          # markdown pages     → wiki/*.md
```

PT pipeline (run before stage 04 so its records merge into the map):

```
uv run scripts/pt/00_fetch_data.py             # eAmbrosia + IVV + CAOP 2025 → raw/pt/
uv run scripts/pt/01_fetch_cadernos.py         # IVV caderno PDFs   → raw/pt/ivv/cadernos/
uv run scripts/pt/02_extract_cadernos.py       # PDF → JSON         → raw/pt/cadernos-extracted/
uv run scripts/02b_fetch_aoc_lexicon.py --lang pt --source raw/pt/cadernos-extracted/
uv run scripts/pt/02d_extract_terroir_facts.py
uv run scripts/pt/02e_translate_terroir_facts.py
uv run scripts/pt/03_generate_wiki.py          # markdown pages     → wiki/*.md
```

Then build the combined map:

```
uv run scripts/04_build_maps.py             # map + tiles (FR + ES + PT merged) → wiki/index.html, wiki/{fr,es,nl}/, wiki/map-data/
```

To preview the built site locally:

```
uv run scripts/serve.py
```

### Optional: BO Agri historique recovery (stage 01c)

INAO's product page links one BO Agri PDF per AOC, often a *modification
arrêté* that doesn't carry the cahier text. Stage 01c walks the BO Agri
weekly archives and downloads any wine-cahier PDFs INAO's resolver missed;
stage 02's cross-bundle rescue then promotes matching stubs to full
extracts.

```
uv run scripts/01c_crawl_boagri_historique.py     # then re-run stages 02 → 04
```

Persistent stubs can also be patched by hand via
`raw/inao/cahiers/manual_overrides.json` (template at
`scripts/manual_overrides.example.json`); see `CLAUDE.md` for the keying
convention.

### LLM stages without API access (02c / 02d / 02e)

Stages 02c, 02d, and 02e all accept `--provider=anthropic` (default,
needs `ANTHROPIC_API_KEY`), `--provider=ollama` (local HTTP API), or
`--provider=manual`. The manual round-trip flow lets a third party
translate / extract offline:

```
uv run scripts/02c_translate_summaries.py --emit-todo todo.json
# hand-translate or pipe through another tool, then:
uv run scripts/02c_translate_summaries.py --import todo.json --translator-id <id> --translator-kind manual
```

Same `--emit-todo` / `--import` flags apply to 02d and 02e.

### Internationalisation (map UI chrome)

Sidebar labels, panel headings, and style chip names are translated via
gettext. Catalogs live under `locale/<lang>/LC_MESSAGES/messages.po`, are
committed to the repo, and are hand-editable. Stage 04 recompiles
`messages.mo` automatically when the `.po` is newer.

```
.venv/bin/python -m babel.messages.frontend extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/
.venv/bin/python -m babel.messages.frontend update  -i locale/messages.pot -d locale --no-fuzzy-matching
.venv/bin/python -m babel.messages.frontend init    -i locale/messages.pot -d locale -l <lang>   # new locale
```

Always extract from the directory, not a single file — `style_taxonomy.py`
carries msgid anchors that are silently dropped otherwise (and pybabel
update will mark them obsolete). Always pass `--no-fuzzy-matching` to
`update`: without it pybabel fills every new msgid with a guess borrowed from
an unrelated existing entry and marks it fuzzy, which is harder to spot than
an empty msgstr. Then set the new msgstrs by hand in each locale.

## Public data sources

All sources are public and licence-clear. Per-record facts (commune lists,
grape varieties, yield thresholds, terroir text) come exclusively from the
regulator: INAO/JORF for France, EUR-Lex + MAPA/CCAA national pliegos for
Spain, IVV cadernos for Portugal. Wikipedia and machine translation are
bounded narrative layers used only for the map sidepanel — see `CLAUDE.md`
for the full rules.

| Source | Used for | Licence |
|---|---|---|
| **INAO *cahiers des charges*** — `extranet.inao.gouv.fr` (per-AOC PDFs) | Canonical legal definition of every AOC/AOP/IGP — communes, cépages, rendements, lien au terroir | Public domain (JORF) |
| **INAO SIQO referentiel** — [data.gouv.fr](https://www.data.gouv.fr/datasets/referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo) | Master list of appellations + cahier URLs | Licence Ouverte 2.0 |
| **INAO parcellaire viticole** — [data.gouv.fr](https://www.data.gouv.fr/datasets/delimitation-parcellaire-des-aoc-viticoles-de-linao) | Delimited AOC parcels (shapefile) | Licence Ouverte 2.0 |
| **BO Agri** — `info.agriculture.gouv.fr` (weekly archives) | Recovery source for cahiers INAO's resolver doesn't link directly (stage 01c + `manual_overrides.json`) | Public domain (JORF) |
| **IGN AdminExpress (communes)** — via [geo.api.gouv.fr](https://geo.api.gouv.fr/communes) | Commune polygons for the base map | Licence Ouverte 2.0 |
| **Cadastre Etalab (lieux-dits)** — [cadastre.data.gouv.fr](https://cadastre.data.gouv.fr/) | Named cadastral parcels per commune; resolves Chablis premier-cru / Givry premier cru / Santenay sub-commune climat geometry where INAO publishes no parcellaire (stages 00 + 04) | Licence Ouverte 2.0 |
| **eAmbrosia EU GI register** — `webgate.ec.europa.eu/eambrosia-api` | Master list of ES + PT wine GIs (file number, kind, producer group, publication URLs) — drives both ES and PT pipelines | EU public sector information |
| **EUR-Lex — OJ single documents** — `eur-lex.europa.eu` (HTML) | Canonical pliego de condiciones (documento único) for ES wines: zona geográfica, variedades, vínculo, rendimientos. Stage 01 fetches each wine's `publications[0].uri`; stage 01b uses headless Chromium to solve the CloudFront WAF challenge on the blocked subset | EU public sector information |
| **MAPA + CCAA national pliegos** — `mapa.gob.es`, JCCM, INCAVI, AGACAL, ITACyL, Aragón, Navarra, GVA, Canarias, Andalucía, Euskadi, Madrid, Extremadura (per-region PDFs) | Secondary/accessory grape varieties not published in the EU-OJ documento único (stage 02f) | Public domain (national/regional gazettes) |
| **SIGPAC vineyard parcels** — `fega.es` (per-comarca shapefiles) | Pliego-cited polygon inclusions for fine-grained ES geometry (e.g. Priorat vs Montsant overlap resolution) | Licence-clear under MAPA terms |
| **GISCO LAU 2024** — Eurostat | EU-wide municipality polygons for the commune-list / province-wide / region-wide geometry fallbacks (ES IGPs and the other eAmbrosia countries) | © EuroGeographics for the administrative boundaries (free reuse) |
| **Bétard 2022 EU PDO geometry** — [Figshare](https://figshare.com/) (`EU_PDO.gpkg`) | Pre-Nov-2021 EU PDO polygons; covers ~99 of 106 ES DOPs and all 30 PT DOPs | CC0 |
| **IVV cadernos de especificações** — `ivv.gov.pt` (per-DOP/IGP PDFs) | Canonical legal definition of every Portuguese wine GI — área delimitada, castas, rendimentos, relação com a área geográfica | Public domain (Portuguese state) |
| **DGT CAOP 2025** — `geo2.dgterritorio.gov.pt` (Continente + RAA + RAM GPKGs) | Portuguese commune-precision boundaries for future PT IGP commune-list geometry | CC BY 4.0 |
| **Wikipedia** — `<lang>.wikipedia.org` REST API | Sidepanel tooltips for grape varieties and distinctive styles (stages 02b/grapes, 02b/styles); per-AOC pages used as a sommelier-vocabulary salience hint for terroir-fact extraction (stage 02b/aocs → 02d) | CC BY-SA 4.0 |
| **VIVC** — [Vitis International Variety Catalogue](https://www.vivc.de/), Julius Kühn-Institut Geilweilerhof | Canonical grape-variety names + VIVC variety numbers driving the per-AOC pill's "canonical bracket" (e.g. *Aragonez (Tempranillo Tinto)*), and synonym-aware Wikipedia search (stage 02g + 02b/grapes). Cite: Röckel et al., Vitis International Variety Catalogue — www.vivc.de | Factual citation only — JKI publishes no explicit data licence. We ship VIVC IDs + prime names; verbatim synonym strings are *not* republished pending JKI confirmation. |
| **MASAF *Elenco alfabetico dei vini DOP*** — `masaf.gov.it` | Source of the Italian traditional term attached to each DOP as a whole (DOCG vs DOC) | Italian public-sector information (MASAF) |
| **MAPA *Listado de DOP e IGP de vinos*** — `mapa.gob.es` | Source of the Spanish traditional term attached to each GI as a whole (DOCa / DOQ, DO, Vino de Pago, Vino de Calidad, Vino de la Tierra) | Spanish public-sector information (MAPA) |
| **Reg. (EC) 607/2009 Annex XII** — [legislation.gov.uk copy](https://www.legislation.gov.uk/eur/2009/607/annex/XII/adopted/data.xht) | Reference list of the traditional terms registered per member state (Reg. 1308/2013 Art. 112(a)); backs the definition and source shown when hovering a term | EU public sector information |
| **Anthropic Messages API** — `claude-sonnet-4-6` (default model) | Terroir-fact extraction from the regulator's terroir text + Wikipedia (02d) and terroir-fact translation (02e); cahier-summary translation (02c) and grape/style-tooltip translation (02b/grapes-translate, 02b/styles-translate) can run here too, but in practice 02c goes through the manual round-trip (a human translator) and the tooltips run mostly on Ollama with Mistral Small 3.2, with a Claude residual; each stage can be swapped to Ollama, Mistral or manual round-trip | n/a — outputs are derivatives of the regulator text (public sector) and Wikipedia (CC BY-SA 4.0) |

The map UI displays attribution alongside any Wikipedia extract ("via
Wikipedia · CC BY-SA 4.0"), any translated summary ("Machine translated
from the cahier des charges", linked to the source PDF on `extranet.inao.gouv.fr`),
and any cadastre-derived climat polygon ("Aire issue du lieu-dit
cadastral … (commune de …, cadastre.data.gouv.fr)"). Terroir-fact bullets
carry per-bullet provenance (`cahier` / `wiki` / `both`); bullets grounded
in Wikipedia render the CC BY-SA 4.0 attribution inline, the rest default
to the cahier-PDF footer link.

### Appellation names: traditional term and legal scheme

Every appellation carries two names, and they mean two different things:
the **traditional term** the country's regulator attaches to the GI as a
whole (DOCG, DOQ, AOC, Vinho Regional, …; Reg. 1308/2013 Art. 112(a),
registered in Reg. (EC) 607/2009 Annex XII) and the **scheme** it is
registered under (the EU's PDO / PGI). The map shows them as
`TERM (SCHEME)`, for example "DOCG (PDO)" or "DOQ (PDO)", with the scheme
word localised per UI language ("DOCG (AOP)" in French, "DOCG (BOB)" in
Dutch). Where a country has no term of its own (Germany's Mosel, the UK),
only the scheme is shown. Swiss AOCs sit outside the EU scheme and carry no
bracket; the United Kingdom registers under its own GI scheme, which keeps
the words PDO and PGI; French eaux-de-vie are spirit-drink GIs, not wine
PDOs. Lot-level quality grades (Qualitätswein, Prädikatswein, kakovostno
vino) are not terms in this sense and are not shown, and neither are scheme
abbreviations (ΠΟΠ, CHOP, ЗНП, BOB). Hovering a term in the panel shows its
definition and source. The stored `kind` token (AOC / DOP / IGP / EDV) is
unchanged; both axes (`eu_scheme`, `national_term`) are derived at stage 04.

## Licence

- **Code** (`scripts/`, `pyproject.toml`, etc.) — MIT, see `LICENSE`.
- **Generated content** (`wiki/`) — CC BY-SA 4.0, see `LICENSE-CONTENT`.
- Source datasets retain their upstream licences (see the "Public data
  sources" table above): INAO / IGN / cadastre Etalab under Licence
  Ouverte 2.0, eAmbrosia / EUR-Lex / MAPA / IVV under public-sector
  reuse, GISCO under EuroGeographics free-reuse, Bétard 2022 under CC0,
  DGT CAOP under CC BY 4.0, Wikipedia extracts under CC BY-SA 4.0.
