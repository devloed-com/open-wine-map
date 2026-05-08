# open wine map

A reference wiki + map of French wine appellations, generated mechanically from
public INAO and IGN data. Every per-AOC fact traces back to a JORF-published
*cahier des charges* — nothing here is hand-written narrative.

## Status

The pipeline runs end-to-end across the full French AOC/AOP/IGP corpus,
emitting per-denomination markdown pages (one per appellation plus one per
DGC — Muscadet sub-crus, Côtes du Rhône Villages, Alsace grands crus, Chablis
premier-cru climats, etc.) and a four-locale interactive map (FR / EN / ES /
NL). The site is deployed at <https://www.openwinemap.com>.

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

```
uv run scripts/00_fetch_data.py             # public datasets    → raw/
uv run scripts/01_scrape_cahiers.py         # cahier PDFs        → raw/inao/cahiers/
uv run scripts/02_extract_cahiers.py        # PDF → JSON         → raw/inao/cahier-extracted/
uv run scripts/02b_fetch_grape_lexicon.py   # Wikipedia (grapes) → raw/wikipedia/grapes/
uv run scripts/02b_fetch_aoc_lexicon.py     # Wikipedia (AOCs)   → raw/wikipedia/aocs/
uv run scripts/02b_fetch_style_lexicon.py   # Wikipedia (styles) → raw/wikipedia/styles/
uv run scripts/02c_translate_summaries.py   # FR → en/es/nl      → raw/translations/summaries/
uv run scripts/02d_extract_terroir_facts.py # cahier+wiki bullets → raw/terroir-facts/
uv run scripts/02e_translate_terroir_facts.py # FR → en/es/nl    → raw/translations/terroir-facts/
uv run scripts/03_generate_wiki.py          # markdown pages     → wiki/*.md
uv run scripts/04_build_maps.py             # map + tiles        → wiki/map*.html, wiki/map-data/
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
gettext. Catalogs live under `locale/<lang>/LC_MESSAGES/messages.po` and are
hand-editable. Stage 04 recompiles `messages.mo` automatically when the `.po`
is newer.

```
uv run pybabel extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/map_template.py
uv run pybabel update  -i locale/messages.pot -d locale
uv run pybabel init    -i locale/messages.pot -d locale -l <lang>   # new locale
```

## Public data sources

All sources are public and licence-clear. Per-AOC facts (commune lists, grape
varieties, yield thresholds, terroir text) come exclusively from INAO/JORF.
Wikipedia and machine translation are bounded narrative layers used only for
the map sidepanel — see `CLAUDE.md` for the full rules.

| Source | Used for | Licence |
|---|---|---|
| **INAO *cahiers des charges*** — `extranet.inao.gouv.fr` (per-AOC PDFs) | Canonical legal definition of every AOC/AOP/IGP — communes, cépages, rendements, lien au terroir | Public domain (JORF) |
| **INAO SIQO referentiel** — [data.gouv.fr](https://www.data.gouv.fr/datasets/referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo) | Master list of appellations + cahier URLs | Licence Ouverte 2.0 |
| **INAO parcellaire viticole** — [data.gouv.fr](https://www.data.gouv.fr/datasets/delimitation-parcellaire-des-aoc-viticoles-de-linao) | Delimited AOC parcels (shapefile) | Licence Ouverte 2.0 |
| **BO Agri** — `info.agriculture.gouv.fr` (weekly archives) | Recovery source for cahiers INAO's resolver doesn't link directly (stage 01c + `manual_overrides.json`) | Public domain (JORF) |
| **IGN AdminExpress (communes)** — via [geo.api.gouv.fr](https://geo.api.gouv.fr/communes) | Commune polygons for the base map | Licence Ouverte 2.0 |
| **Cadastre Etalab (lieux-dits)** — [cadastre.data.gouv.fr](https://cadastre.data.gouv.fr/) | Named cadastral parcels per commune; resolves Chablis premier-cru / Givry premier cru / Santenay sub-commune climat geometry where INAO publishes no parcellaire (stages 00 + 04) | Licence Ouverte 2.0 |
| **Wikipedia** — `<lang>.wikipedia.org` REST API | Sidepanel tooltips for grape varieties and distinctive styles (stages 02b/grapes, 02b/styles); per-AOC pages used as a sommelier-vocabulary salience hint for terroir-fact extraction (stage 02b/aocs → 02d) | CC BY-SA 4.0 |
| **Anthropic Messages API** — `claude-haiku-4-5` | Cahier-summary translation (02c), terroir-fact extraction from cahier section X + Wikipedia (02d), and terroir-fact translation (02e); each stage can be swapped to Ollama or to manual round-trip | n/a — outputs are derivatives of the cahier (public domain) and Wikipedia (CC BY-SA 4.0) |

The map UI displays attribution alongside any Wikipedia extract ("via
Wikipedia · CC BY-SA 4.0"), any translated summary ("Machine translated
from the cahier des charges", linked to the source PDF on `extranet.inao.gouv.fr`),
and any cadastre-derived climat polygon ("Aire issue du lieu-dit
cadastral … (commune de …, cadastre.data.gouv.fr)"). Terroir-fact bullets
carry per-bullet provenance (`cahier` / `wiki` / `both`); bullets grounded
in Wikipedia render the CC BY-SA 4.0 attribution inline, the rest default
to the cahier-PDF footer link.

## Licence

- **Code** (`scripts/`, `pyproject.toml`, etc.) — MIT, see `LICENSE`.
- **Generated content** (`wiki/`) — CC BY-SA 4.0, see `LICENSE-CONTENT`.
- The INAO, IGN, and cadastre Etalab source datasets are licensed under
  Licence Ouverte 2.0; their terms apply to anything in `raw/`.
  Wikipedia extracts in `raw/wikipedia/` remain under CC BY-SA 4.0.
