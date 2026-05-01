# open wine map

A reference wiki + map of French wine appellations, generated mechanically from
public INAO and IGN data. Every per-AOC fact traces back to a JORF-published
*cahier des charges* — nothing here is hand-written narrative.

## Status

v0 — pipeline bootstrap. End-to-end smoke test on Côtes du Jura before scaling
to the full ~700 wine appellations.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

For machine translation of cahier summaries (stage 02c, optional), set:

```
export ANTHROPIC_API_KEY=...
```

Without it, run stage 02c in `--provider=manual` mode (see below).

## Running the pipeline

Stages are independent and re-runnable. Each writes a manifest, so reruns
are no-ops when nothing upstream changed. Run them in order from a clean
checkout to rebuild `wiki/` from scratch.

```
uv run scripts/00_fetch_data.py             # public datasets → raw/
uv run scripts/01_scrape_cahiers.py         # cahier PDFs    → raw/inao/cahiers/
uv run scripts/02_extract_cahiers.py        # PDF → JSON     → raw/inao/cahier-extracted/
uv run scripts/02b_fetch_grape_lexicon.py   # Wikipedia      → raw/wikipedia/grapes/
uv run scripts/02c_translate_summaries.py   # FR → en/es/nl  → raw/translations/summaries/
uv run scripts/03_generate_wiki.py          # markdown pages → wiki/*.md
uv run scripts/04_build_maps.py             # map + tiles    → wiki/map*.html, wiki/map-data/
```

To preview the built site locally:

```
uv run scripts/serve.py
```

### Stage 02c without API access

Forks running the pipeline without an Anthropic key can use the round-trip
flow:

```
uv run scripts/02c_translate_summaries.py --emit-todo todo.json
# hand-translate or pipe through another tool, then:
uv run scripts/02c_translate_summaries.py --import todo.json --translator-id <id> --translator-kind manual
```

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
| **IGN AdminExpress (communes)** — via [geo.api.gouv.fr](https://geo.api.gouv.fr/communes) | Commune polygons for the base map | Licence Ouverte 2.0 |
| **Wikipedia** — `<lang>.wikipedia.org` REST API | One short summary per grape variety, shown in the map sidepanel tooltip (stage 02b) | CC BY-SA 4.0 |
| **Anthropic Messages API** — `claude-haiku-4-5` | Machine translation of the FR cahier summary paragraph into en/es/nl for the map detail panel (stage 02c) | n/a — the *output* is a derivative of the cahier (public domain) |

The map UI displays attribution alongside any Wikipedia extract ("via
Wikipedia · CC BY-SA 4.0") and any translated summary ("Machine translated
from the cahier des charges", linked to the source PDF on `extranet.inao.gouv.fr`).

## Licence

- **Code** (`scripts/`, `pyproject.toml`, etc.) — MIT, see `LICENSE`.
- **Generated content** (`wiki/`) — CC BY-SA 4.0, see `LICENSE-CONTENT`.
- The INAO and IGN source datasets are licensed under Licence Ouverte 2.0;
  their terms apply to anything in `raw/`. Wikipedia extracts in
  `raw/wikipedia/` remain under CC BY-SA 4.0.
