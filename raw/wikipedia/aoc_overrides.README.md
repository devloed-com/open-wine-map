# aoc_overrides.json

Curator-supplied per-locale Wikipedia title overrides for AOC slugs that the
title-cascade in [scripts/02b_fetch_aoc_lexicon.py](../../scripts/02b_fetch_aoc_lexicon.py)
fails to resolve. Models the existing `grape_overrides.json` pattern but
carries the verification quote and full URL alongside the title so future
re-runs can re-validate the page is still about the AOC.

Schema:

```json
{
  "<lang>": {
    "<slug>": {
      "wiki_title": "<canonical Wikipedia page title>",
      "page_url": "https://<lang>.wikipedia.org/wiki/<urlencoded>",
      "verification_quote": "<one sentence from the page lead confirming AOC topic>"
    }
  }
}
```

Current contents:

- **fr** — 101 entries: 88 pinned, 7 `missing`, 6 `not_aoc_topic`. 44 from
  the original Alsace grand-cru series (each lieu-dit AOC); the cascade
  failed because it appends `(AOC)` / `(IGP)` parenthetical suffixes and
  FR Wikipedia titles those climats either bare (`Mambourg`, `Hengst`)
  or with `(grand cru)` disambiguation (`Brand (grand cru)`,
  `Schoenenbourg (grand cru)`). +51 from the 2026-05-14 batch covering
  cascade-failures across Bourgogne, Loire, Languedoc-Roussillon, Rhône,
  Sud-Ouest, cidres/eaux-de-vie, and multi-name AOCs whose slug encodes
  `-ou-` synonyms (e.g. `hermitage-ou-ermitage-ou-l-hermitage-ou-l-ermitage`,
  `cognac-ou-eau-de-vie-de-cognac-ou-eau-de-vie-des-charentes`). +5
  `not_aoc_topic` stubs (domfront, franche-comte, pays-de-brive,
  pommeau-de-normandie, aveyron) tidying-in the inventory previously held
  only in CURATOR_TODO.md. +1 single-slug top-up (`vin-de-savoie-ou-savoie`
  → `Savoie (AOC)`, the canonical title after a `Vin de Savoie (AOC)`
  redirect) to close out the FR Wikipedia override research.
- **es** — 29 entries: 8 pinned, 11 `missing`, 10 `not_aoc_topic`. 20 from
  the 2026-05-14 first ES batch (txakolinas, `jerez-xeres-sherry` →
  "Jerez", `3-riberas`, `campo-de-la-guardia`,
  `ribera-del-gallego-cinco-villas`,
  `sierras-de-las-estancias-y-los-filabres` pinned; 11 missing — mostly
  Vinos de Pago; `tharsys` → bodega-only). +9 `not_aoc_topic` stubs
  (urueña, ayles, campo-de-calatrava, bolandin, dehesa-penalba,
  abadia-retuerta, rio-negro, rosalejo, islas-canarias) tidying-in the
  inventory previously held only in CURATOR_TODO.md.

Both batches researched via Claude Chrome extension against the live
Wikipedia titles in their respective locales. `not_aoc_topic` stubs
record "page exists but is about something tangential (place, bodega,
disambig)" so future audit doesn't re-research them; specific
verification quotes were not captured for these — re-research to upgrade.

Consumer status: stage 02b reads this file at import time
(`LANG_OVERRIDES` in [scripts/02b_fetch_aoc_lexicon.py](../../scripts/02b_fetch_aoc_lexicon.py)).
`fetch_aoc()` checks `LANG_OVERRIDES[lang][slug]` before the title cascade
and short-circuits via `_record_from_override`: positive pins fetch the
curator's `wiki_title` directly (skipping the `looks_like_aoc` keyword
filter since the curator already validated via `verification_quote`) and
emit the full record (`lead_extract` / `sections` / `full_text`) plus an
`override_source: "curator"` marker; `missing` and `not_aoc_topic` entries
emit the same record shapes the cascade uses (`missing: True` /
`error: "not_aoc_topic"`) without any network call. Edits to this file
require `--refresh` to invalidate previously-cached cascade results for
the affected slugs.

Gitignored along with the rest of `raw/`.
