---
name: national-spec-layer
description: >-
  Scaffold + wire the national-spec augmentation layer for an open-wine-map
  country whose wines are content-stubs (no fetchable EU-OJ single document).
  Generates the stage 01c fetch script, the _lib/<cc>/specifikacija.py parser,
  and the stage 02f extractor by copying the closest sibling country, then
  applies the six stage-04 wiring hooks + the 02d terroir-source fallback at
  their known anchors, and runs a wiring-lint so a forgotten hook fails loudly
  (a missing hook silently hides the country from the map). Use when adding a
  national / regulator product-specification fallback for a country that
  already has stages 00–03 + stub records — e.g. "add the national-spec layer
  for Slovakia", "wire SK/HU/CZ national specs into stage 04", or after
  /research-gaps national-spec resolves a per-wine spec source.
---

# national-spec-layer

Nine countries already carry this layer (ES MAPA, IT MASAF, DE BLE, SI, HR,
GR, RO, HU, BG) plus CZ's two-decree variant. Each is the same shape; only
~4 things vary. This skill scaffolds the per-country files and applies the
**six stage-04 hooks + the 02d fallback** at their exact anchors, then lints
that every hook references the new country code — because the project's own
memory warns that *missing one of stage 04's country-code allowlists silently
hides the country from the map* (the failure is silent: the wine renders as a
bare stub even though the spec was parsed).

This skill **does not** research the source (use `/research-gaps national-spec
<cc>` first) and **does not** invent parser keywords (it leaves a clear TODO —
the section-keyword table is the one part that needs human/LLM eyes per
country).

## Preconditions (verify first, stop if unmet)

1. The country already has stages 00–03 and a stub corpus:
   `raw/<cc>/<extracted-dir>/*.json` records with `stub: true`. If not, this
   is a new-country task, not a spec-layer task — stop and say so.
2. A resolved, licence-clear source with **per-wine spec text incl. a terroir
   / link-to-region section** (or the CZ-style national document). If the
   source is unresolved, run `/research-gaps national-spec <cc>` first and
   come back. Confirm the source carries terroir narrative — the layer is
   only worth it if 02d can ground bullets.
3. The country is already in stage 04's three base allowlists (it must be, if
   00–03 shipped). The wiring-lint checks this and warns if not.

## Inputs to gather (ask the user if unset)

- `cc` — 2-letter country code (e.g. `sk`).
- `source_lang` — extraction language (often `== cc`; differs for at/si/gr/cz/lu — `de/sl/el/cs/fr`).
- `source_org` — short tag for provenance + the override `source_org` field (e.g. `iavv`, `mprv`, `onvpv`, `masaf`).
- `extracted_dir` — the country's stub dir under `raw/<cc>/` (varies:
  `dokumenti-extracted`, `dokumente-extracted`, `dokumenty-extracted`,
  `dokumentumok-extracted`, `dokumenten-extracted`, `cahier-extracted`).
- `source_format` — `pdf-numbered` / `doc-lettered` / `mixed` / `national-tables`.
  Drives sibling selection (see `reference/parser-templates.md`).

## Procedure

### 1 — Pick the sibling template

Read `reference/parser-templates.md` and choose the closest existing country
by `source_format`. Read that sibling's three files end-to-end before copying
— they are the source of truth, not this skill's prose.

### 2 — Scaffold the three per-country files

Copy the sibling, substituting `cc`, `source_lang`, `source_org`, paths,
licence string, and parser_template id:

- `scripts/<cc>/01c_fetch_specifikacije.py` — fetch layer. Reads
  `raw/<cc>/national-specs/manual_overrides.json` (the /research-gaps output),
  writes `raw/<cc>/national-specs/<slug>.<ext>` + `manifest.json`. The
  Content-Type→ext routing + sha256 manifest are reused verbatim.
- `scripts/_lib/<cc>/specifikacija.py` — parser. Keep the slicing /
  grape-colour / styles / summary skeleton; **replace the section-keyword
  tables** with the new language (leave a `# TODO: tune section keywords
  against a sample spec` marker). For Cyrillic/Greek, reuse `.casefold()` and
  the `ъ`/`ь`→apostrophe alias caveat (see `[[project_cyrillic_handling]]`).
- `scripts/<cc>/02f_extract_national_specs.py` — extractor. The format
  dispatch (`pdftotext`/`owm-antiword`/docx-zip/html) + sidecar schema +
  `flush_unknowns_queue` are reused verbatim; swap the parser import + paths
  + country/source_lang in `_sidecar_for`.

### 3 — Apply the six stage-04 hooks + 02d fallback

Follow `reference/wiring-contract.md` exactly — it gives the grep to locate
each anchor (line numbers drift) and the model block to insert (copy the BG or
GR block, swap `cc`/`XX`). The six hooks in `scripts/04_build_maps.py`:

1. `NATIONAL_SPECS_XX` constant (constants block)
2. `_XX_NATIONAL_SPEC_BY_SLUG` cache dict
3. `augment_xx_records_with_national_specs()` function
4. its call site in the load flow (after the last `n_aug_*`)
5. the `_sources_for()` `country == "xx"` branch (surfaces `national_spec_*`)
6. the `has_augmented_source` gate clause

Plus `scripts/<cc>/02d_extract_terroir_facts.py`: add the `NATIONAL_SPECS`
constant + the `_resolve_lien_and_source` sidecar fallback (model on BG/GR).

### 4 — Run the wiring-lint (must pass before proceeding)

**Self-test first:** run the lint against an already-wired country (`bg` or
`hu`) — it must print **1** for hooks 1–7. If it doesn't, the anchors in
`reference/wiring-contract.md` have drifted against the current
`04_build_maps.py`; fix the contract (and note it in the Changelog) before
trusting the lint on the new country. Then run it for the new `cc`: every
hook must print 1. Any site missing the code is a silent-failure bug (hook 6
especially — the wine renders as a bare stub despite a parsed spec) — fix
before running the pipeline.

### 5 — Hand back the run sequence (do not run unprompted)

```
.venv/bin/python scripts/<cc>/01c_fetch_specifikacije.py
.venv/bin/python scripts/<cc>/02f_extract_national_specs.py --all
# fold extraction-unknowns via the grape-colour-researcher agent, re-run 02f
.venv/bin/python scripts/<cc>/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/<cc>/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_<cc>_coverage.py
```

After 02f's first sweep, the `raw/<cc>/extraction-unknowns-specifikacije.json`
queue feeds the `grape-colour-researcher` agent (native-variety colour +
identity), whose findings the curator folds into
`scripts/_lib/grape_lexicon.py` before the final 02f re-run.

### 6 — Docs (mechanical)

- Add a "<CC> national specifikacija layer" subsection + the 01c/02f stage-table
  rows to the country's section in `CLAUDE.md` (mirror the BG/HR wording).
- Reconcile the country's `CURATOR_TODO.md` section.
- Append a dated `VERIFICATION.md` entry (sidecar count, grape slugs, terroir
  bullets, the independent source + re-run recipe).
- Extend `scripts/audit_<cc>_coverage.py` with the national-spec + terroir
  coverage rows (model on `audit_bg_coverage.py`).

### 7 — Calibration (close the loop — do this while the friction is fresh)

This skill only improves if each run's divergences are written back into it
*now*, not remembered later. Before finishing, if any of these happened,
update the skill files and add a dated `## Changelog` line:

- A wiring anchor had moved / the self-test failed → fix `wiring-contract.md`.
- The chosen sibling didn't fit, or you used a **new source format** (e.g. a
  national gazette HTML, an OCR-only scan) → add a row to
  `parser-templates.md` so the next country starts from it.
- The lint passed but the layer still mis-rendered → the lint missed a hook;
  add the new check to `wiring-contract.md`.
- A grape-fold or Cyrillic/script gotcha recurred → it belongs in
  **project memory** (cross-cutting), not just here — note it there too.

Also record the outcome scorecard (sidecars / grapes / terroir bullets from
`audit_<cc>_coverage.py`) in the VERIFICATION.md entry — that's the signal
that tells the next run whether the instructions held (51/51 = good; a partial
count = something in this skill needs tightening).

## What this skill deliberately leaves manual

- The parser's section-keyword tables (country-specific; TODO + sample-check).
- Grape-fold correctness + native-variety colours (use the agent, then a
  human pass).
- Licence verification (the /research-gaps step must confirm public + clear).

## Changelog

Append a dated line per run that taught the skill something (anchor drift, a
new source format, a missed lint check). Keep it terse.

- 2026-05-30 — created. Distilled from the ES/IT/DE/SI/HR/GR/RO/HU/BG layers;
  BG is the canonical copy target. Lint validated all-1s on bg/hu, all-0s on
  sk. zsh-portable uppercasing; hook-5 greps `_XX_NATIONAL_SPEC_BY_SLUG.get`
  (not the bare `country == "xx"` string, which over-counts the geometry
  branch).
