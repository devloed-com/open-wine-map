# Plan — validator skills

Status (2026-10-23): **built** — all five skills, their scripts and tests
landed the same day the plan was approved; the first runs are written up in
[review-validators-2026-10-23.md](review-validators-2026-10-23.md) and their
findings queued in CURATOR_TODO.md ("validators, first runs"). Nothing below
changes the build: every validator is a detector that routes its findings into
the existing override / feedback / CURATOR_TODO mechanisms.

| skill | what it answers | built as |
|---|---|---|
| `/validate-sources` | is every source a card cites still the newest the regulator (EU · national · regional · trade body) publishes? | `scripts/audit_source_freshness.py` + `scripts/_lib/freshness/` (eambrosia, datagouv, inao, govuk, layers, generic, wikipedia probes); `--counts` reconciliation; `.claude/skills/validate-sources/` |
| `/validate-cards` | would an independent reader of the sources find the card wrong or incomplete? | `scripts/_lib/card_packet.py` + `scripts/audit_cards_llm.py` (Opus judge, sources + rendered card only, quotes re-grounded); `.claude/skills/validate-cards/` |
| `/validate-geometry` | does the polygon we draw match the area the regulator wrote? | `scripts/audit_geometry_vs_text.py` + `scripts/_lib/geometry_text_overrides.json` (named vs drawn units, containment, `--llm`); `.claude/skills/validate-geometry/` |
| `/validate-release` | is this build fit to deploy? | `scripts/validate_release.py` (the gate registry) + `scripts/diff_records.py`; `.claude/skills/validate-release/` |
| `/triage-feedback` | what do the visitor flags mean, isolated or broader? | `.claude/skills/triage-feedback/` over `feedback_report.py` and the three validators |

Tests: `tests/test_card_packet.py`, `test_cards_llm.py`, `test_freshness.py`,
`test_geometry_vs_text.py`, `test_diff_records.py`, `test_validator_skills.py`
(the wiring lint). The CLAUDE.md section "Validators" is the operating
reference; the per-skill SKILL.md the procedure.

## Principles every validator follows

Taken from the rules the repo already enforces on its audits:

- **A detector, never an editor.** Nothing under `wiki/` or `raw/` is changed
  by a validator. A finding is routed: a parser fix, an override file with a
  cited source, a feedback sidecar, a CURATOR_TODO row, a stage re-run with
  `--only`. The routing is part of the finding.
- **Every finding quotes a public source** (the regulator text, the upstream
  listing, the layer's attribute table) and names its **failure mode**, then
  the validator sweeps for siblings and reports *isolated* or *N more*
  (the 2026-10-22 rule).
- **Buckets, with a REVIEWED tier.** OK / SUSPECT / REVIEWED (an override
  entry with a reason, so a cleared finding stays visible and re-fires when
  the data drifts) / UNVERIFIABLE (with the reason). `--strict` exits non-zero
  on unreviewed SUSPECT only.
- **Country-agnostic from day one.** The validators read the record (`country`,
  `geom_source`, `sources`, `section_roles`) and the shared resolvers
  (`_lib/terroir_sources`, `_sources_for`, each country's unit parser); the
  US and AU corpora under `raw/` will arrive while these are being built.
- **Reports in two shapes.** Machine: `tmp/validation/<validator>-<run>.json`
  (gitignored, every verdict). Human: a Markdown summary, and for a full review
  a dated `docs/review-<validator>-<date>.md` like the two reviews we have.
- **Every LLM run prices itself** through `batch.run_batch` and the
  `raw/.batch/costs.jsonl` ledger; a run states its spend ceiling up front.
- **Independence is the point of the LLM validators.** A different model
  *family* from the extractor (Sonnet 5.5 extracts; Opus 5.5 / Fable judges),
  and the judge sees **sources + rendered card only** — never the pipeline's
  grounding quotes, prompts or sidecars (the current LLM audit feeds the
  quotes; the validator must not, or it grades the extractor's own evidence).

## 1 · `/validate-sources` — source freshness across tiers

### What it checks

For each record, every source the card cites (`_sources_for`) is classed by
tier and probed for a newer upstream version:

| tier | examples | how we learn "newer" |
|---|---|---|
| EU | eAmbrosia (`modification_date`, `publications`, `removedFlag`), EUR-Lex OJ C/L single documents and regulations, the register's `singleDocTechFile` / `productSpecifications` attachments | one ~4k-row API GET diffed against every `raw/<cc>/eambrosia/index.json`; attachment sha256 against the cached PDF (content-addressed, so a re-download is cheap and exact) |
| national | INAO product page + Textes JO index, BO Agri, SIQO on data.gouv.fr; MASAF bundles; MAPA listado + national pliegos; IVV; BLE; ΥΠΑΑΤ; ONVPV; IAVV; ÚPV SR; SZPI; MKGP; MPS; HNT; OFAG; GOV.UK + DEFRA | stage 01's own `resolve_cahier` (dated `show_texte` title, not the URL — 51 same-text relinks on 2026-09-20); listing-page dates (MASAF `ServeAttachment`, MAPA release date, BLE `?v=`); data.gouv.fr dataset API (`static.data.gouv.fr` ETag = md5, a HEAD suffices); GOV.UK content API dates |
| regional | IT regione geoportals, ES comunidades' pliegos (JCCM, INCAVI, AGACAL, ITACyL …), DE Länder, CH cantonal lex portals (LexWork API `pdf_link`), Xunta IET, SITG | HEAD / Last-Modified where the host gives one, else sha of a re-fetch of the small documents; a geoportal layer by its feature count + bbox digest |
| geometry layers | INAO parcellaire + aires CSV release, GISCO LAU / NUTS vintage, CAOP, swissBOUNDARIES, ONS, Bétard 2022 (frozen), cadastre lieux-dits | release labels in the manifests vs the publisher's current release; Bétard reported as *snapshot by design* and handed to `audit_betard_delta` |
| trade bodies | interprofession / consorzio / consejo / ODG sites (`appellation_urls.py`) | a **signal, not a source**: their réglementation / news page announcing a modification tells us where to look; nothing is ever ingested from them (public-sources rule) |
| narrative / reference | Wikipedia `revision`, VIVC passport | revision id per cached entry (02b already stores it); VIVC passport re-fetch for pinned ids |

Held vintage comes from what the record already carries: `homologation_date`
/ `source.homologated_at` (FR), the OJ ELI year (`C/2026/565`), the spec's
`fetched_at` + sha256, the manifest's release label.

### Verdicts

CURRENT · NEWER-UPSTREAM (with the upstream date / act title / URL and the
re-run recipe) · RELINKED (same sha, new URL — noise, but the manifest should
follow) · GONE (404 / host retired — link rot on the card) · UNREACHABLE
(geo-fence, WAF; the probe says which host and the known workaround — BO Agri
needs a French exit node, minagric the four-w host, mpsr.sk a browser UA) ·
SNAPSHOT (Bétard 2022; GISCO by vintage) · IN-OPPOSITION (INAO PNO notice:
a new arrêté follows; eAmbrosia `amendmentsInProgressFlag`).

A second mode, `--counts`, is the VERIFICATION.md practice made repeatable:
per country, our record count and file-number set against the independent
authority's listing (MAPA listado, MASAF elenchi, GOV.UK register, OFAG
répertoire, INAO's aire shapefile orphan rows), appended to VERIFICATION.md.

### Mechanics

- `scripts/audit_source_freshness.py` + `scripts/_lib/freshness/` — one probe
  module per host family (`eambrosia.py`, `inao.py`, `datagouv.py`,
  `govuk.py`, `eurlex.py`, `generic_http.py` …), each returning
  `{held, upstream, upstream_url, method, confidence}`. Probe results cached
  per URL for a day under `raw/cache/freshness/` so a re-run after a fix is
  free; one request at a time per host, the existing per-host headers reused
  (`_BROWSER_HEADERS`, the register's 202-with-PDF).
- Reuses: the register-drift method (steps 1–2 of the 2026-09-20 doc),
  `audit_betard_delta`, stage 01 `resolve_cahier`,
  `_lib/eambrosia_register.py`, the data.gouv.fr one-call release check
  (memory `reference_inao_datagouv_datasets`).
- Not in CI (network); a monthly routine or a pre-deploy run. Output
  `tmp/validation/sources-<date>.{json,md}`; NEWER-UPSTREAM rows go to
  CURATOR_TODO under the country with the recipe (`01 --only`, a
  `manual_overrides.json` pin, `00` for a layer).
- Later option (not in scope): a card line "Specification of 27 April 2026 ·
  checked against INAO on <date>" from the same data.

## 2 · `/validate-cards` — independent LLM reading of the whole card

### What it checks

One request per record. The judge receives (a) the **card as rendered** in a
locale — name, classification + scheme, region, styles, grapes with roles and
the bracketed VIVC prime, the area line (source kind, commune count, km²),
sub-denomination relation, terroir facts or summary, notes, sources list —
built from `wiki/data/d/<locale>/<slug>.json` + the startup fields, and (b)
the **sources**: the full regulator text (every routed section of the
extracted record, not the lien alone), the national-spec sidecar and the
register fiche where they exist (second source), the Wikipedia page used.
It returns, per card section:

- **error** — the card states what a source contradicts (quote);
- **omission** — a source states it prominently and the card lacks it (a
  grape, a style, a sub-denomination, a restriction such as a DGC's colour);
- **unsupported** — the card states what no source states;
- **stale** — the sources disagree with each other on a dated point (hands
  the record to `/validate-sources`);
- a severity (misleads / defective / cosmetic), a failure-mode tag from a
  fixed list (the 16 tags of the LLM audit plus header tags: `wrong-role`,
  `missing-grape`, `extra-grape`, `missing-style`, `sibling-leak`,
  `wrong-region`, `wrong-scheme`, `area-mismatch`, `source-not-cited`), and a
  one-line fix.

Deterministic checks run first and are passed to the judge as *already
known* so it spends its attention elsewhere: the empty-grapes classifier,
VIVC pin state, the style floor, `audit_gi_terms`, the feedback sidecar's
`do_not_claim` entries.

### Independence

- Judge model from a different family than every extractor that touched the
  record (`providers.STAGE_DEFAULTS["audit"]`, Opus 5.5 today; `--model` for
  Fable; `--provider mistral|ollama` for a second opinion when one is
  needed).
- The judge sees sources + card, nothing from the pipeline (no grounding
  quotes, no prompts, no gate verdicts). This is stricter than
  `audit_terroir_facts_llm.py`, which stays as the bullet-level measure.
- `--second-opinion` grades the SUSPECT records again with another model; a
  finding both judges make is reported first.

### Scope and cost

`--sample N` stratified by country × `geom_source`; `--top-viewed N`
(Plausible, the top-200 pattern); `--only`, `--country`; `--changed-since
<snapshot>` for the records a build or re-run touched; `--locale` (EN by
default, the locale readers see; the four locales for a release review).
Batch API with the system prompt cached. Order of magnitude per card at the
Opus 5.5 batch rate: ~20k input + ~1.5k output tokens ≈ $0.10, so 200 cards
≈ $20, the corpus ≈ $300 — sample and stratify, sweep only before a release.

### Routing

- facts → `build_terroir_feedback.py` sidecars (`do_not_claim`,
  `capture_if_present`, `record_cautions`), then the scoped re-run; the audit
  measures `feedback_recurrence`.
- header / grapes / styles / area / sources → a CURATOR_TODO row naming the
  failure mode and the sweep result (the 2026-09-20 review's "header
  contradictions by class" is the model).
- `--compare A B` paired before / after (reuse the LLM audit's) — the
  acceptance measure for a parser fix.
- Build on `audit_terroir_facts_llm.py`: same loading, batch, report and
  compare code; a new packet builder (`_lib/card_packet.py`: the rendered
  card in a locale from the panel payload + startup record, reusable by the
  MCP server's `get_appellation` tests) and a new prompt. Working name
  `scripts/audit_cards_llm.py`.

## 3 · `/validate-geometry` — the polygon against the text

### What is missing today

`audit_geometry_outliers`, `_overlaps`, `_betard_delta`,
`audit_parcellaire_gaps`, `audit_vineyard_envelopes`, `audit_climats`,
`audit_it_regions` compare polygons with polygons (or a label with a
polygon). None asks whether the shape covers the units the regulator
**wrote** and no others. That is the one independent geographic check, and
the Monterrei (seven excluded parishes drawn, six added ones missing),
Montpeyroux (2 of 4 communes), Côtes du Lot (6 of 340), Calvados Domfrontais
(1,573 communes for 112) and Cévennes (no Lozère) cases were all of that
kind, each found by a visitor or by hand.

### `audit_geometry_vs_text.py`

Per record with an area text:

1. **Named units** — the administrative units the delimitation text names:
   the country's own reader first (`aires.py`, ES/IT/RO/BG/GR `commune.py`,
   PT `area_units.py`, AT `gemeinde.py`, CH `scan_text`, DE
   `DE_LANDWEIN_AREA`); then, because comparing our own parse with our own
   polygon is a tautology for a commune-union record, an **independent
   read** of the same text — an LLM asked for the list of units named as
   members, excluded, or named only as a holder of parishes / lieux-dits,
   each with its quote, verified against the layer's name index before it
   counts. Whole-unit statements ("the whole département", "intero
   territorio della provincia") expand through the layer.
2. **Drawn units** — the resolved polygon reverse-geocoded against the
   layer the country draws from (GISCO LAU; swissBOUNDARIES; CAOP
   freguesias; ONS; IGN communes): covered ≥ 95 %, drawn in part, grazed
   ≤ 5 % (the `municipios_covered` thresholds).
3. **Compare**, read through `geom_source`: MISSING (named, not drawn),
   EXTRA (drawn whole or mostly, not named — the Bétard padding and
   mis-attribution signal), PART (named, drawn in part — expected for a
   parcellaire, zone or parish record; suspect for a commune union). A
   zone or Bétard record with EXTRA units beyond the named set is a vintage
   or attribution question; a commune-union record with any MISSING / EXTRA
   is a parser defect.
4. **Containment** — a sub-denomination with its own polygon lies inside
   its parent (the overlap audit skips hierarchy pairs, so nobody checks
   this; Monterrei Ladera spilled out of its parent for months); a record
   lies inside its region's / country's boundary.
5. **Stated area** — where the spec states a delimited area in hectares
   (Darnibole's 5 ha, some single documents), order-of-magnitude only;
   planted hectares are never compared with a delimitation.

Buckets OK / SUSPECT / REVIEWED (`scripts/_lib/geometry_text_overrides.json`,
slug → reason + source, the whitelist pattern) / NO-TEXT / NO-UNITS.
`--strict` on unreviewed SUSPECT. The LLM read is optional (`--llm`), batch,
cached per text sha; without it the audit still runs the cross-source
comparison for records whose text another document also describes (EU
single document vs national spec).

### Two more geographic modes

- **Reference QA** (`--reference URL --slug …`): a Playwright side-by-side
  of our polygon and a third-party map the user points at, for a visual
  check of completeness — QA only, nothing copied (the standing rule on
  external maps).
- **Layer drift** — INAO's aire-géographique shapefile orphan rows and the
  parcellaire release diff (memory `reference_inao_datagouv_datasets`) as a
  FR signal that a record's delimitation moved; lands in `/validate-sources`
  as the geometry tier, reported here per record.

## 4 · Other validators worth having

Ranked by reader-facing value over effort.

1. **Grape-roster validator** — the varieties section vs the rendered roster:
   missing, extra, wrong role, colour against VIVC. The 2026-10-22 sweep (358
   cards changed) shows the long tail. Deterministic pre-pass from the
   unknowns queues + `audit_grape_identity`, then the `/validate-cards` judge
   on the grapes section (`--section grapes`). A mode of `/validate-cards`,
   not a skill of its own.
2. **Cross-source consistency** — where a record has two regulator documents
   (EU single document + national spec; register fiche + national; BO Agri +
   register attachment: 352 FR records already shadowed), diff the
   structured extraction of both (grapes, styles, area units, dates). A
   disagreement is a vintage gap (→ `/validate-sources`) or a parser defect.
   Deterministic, cheap, the shadow-report pattern generalised to the eight
   countries with register-fiche sidecars.
3. **`/validate-release`** (pre-deploy umbrella) — runs every `--strict`
   audit, `detect_untranslated_terroir_facts`, the NL article check, the
   gettext catalog completeness, the headless SSR / JS parity check, the
   About-page date, then a `/validate-cards --changed-since` sample on the
   records the build changed. No new detector; one command and one report
   before `deploy.sh`.
4. **`/triage-feedback`** — `feedback_report.py` → for each flagged slug the
   deterministic checks + `/validate-cards --only` + the "isolated or
   broader" sweep by failure mode → a dated triage doc and the CURATOR_TODO
   rows. The six triage sessions since 2026-09-22 all followed this shape by
   hand.
5. **Record regression diff** — `diff_records.py`: snapshot → run →
   per-record diff of grapes / styles / area / facts / geometry provenance,
   the step every validator's fix-then-verify loop needs (done ad hoc on
   2026-10-22). Belongs to `/validate-release` and the parser skills.
6. **Link-rot check** — every URL on every card, HEAD with the host quirks;
   the GONE bucket of `/validate-sources`, not a separate tool.

## Build order (recommendation)

1. **`/validate-cards`** — the largest blind spot (header, roster and style
   defects reach readers unchecked; the hand review found them on a quarter
   of the top 200) and the infrastructure is 80 % there (`terroir_sources`,
   `batch`, `llm_json`, the LLM audit's loading / report / compare).
   Deliverables: `scripts/_lib/card_packet.py`, `scripts/audit_cards_llm.py`,
   `.claude/skills/validate-cards/SKILL.md` (+ `reference/tags.md`,
   `reference/routing.md`), tests for the packet builder and the verdict
   schema, a first 200-record run with its `docs/review-cards-<date>.md`.
2. **`/validate-sources`** — the recipe is proven; the new work is the
   per-tier probe registry and the cache. Deliverables:
   `scripts/_lib/freshness/*.py`, `scripts/audit_source_freshness.py`
   (`--counts` mode), the skill, fixture tests per probe (recorded responses),
   a first corpus run reconciled into CURATOR_TODO and VERIFICATION.md.
3. **`/validate-geometry`** — `scripts/audit_geometry_vs_text.py`, the
   overrides file, the containment check, the skill; the `--llm` read last.
4. **`/validate-release`** and **`/triage-feedback`** — orchestration of the
   above; `diff_records.py` alongside.

Each skill follows the house shape (`research-gaps`, `national-spec-layer`):
preconditions, inputs, procedure, what stays manual, a wiring lint in
`tests/`, a changelog.

## Decisions taken at build time (the open questions, answered by default)

- Locale: EN by default (`--locale` for the other three); a release review grades all four.
- Judge: `STAGE_DEFAULTS["audit"]` (Opus 5.5); `--second-opinion` for a second model; `--max-usd 25` ceiling, `--yes` above it.
- Cadence: on demand and before a deploy; the corpus-level sources run is cheap enough for a monthly routine.
- CURATOR_TODO rows are *emitted* (`--emit-curator-md`), appended by hand after the sweep cell is filled — never written by a script.
- Trade bodies: liveness only (one HEAD), no content probe.

## Open questions (as written before the build)

- Locale(s) to grade in `/validate-cards`: EN only by default, all four for a
  release review?
- Judge model and spend: Opus 5.5 by default, Fable for the second opinion?
  A ceiling per run (the skill asks above it, as `research-gaps` does above
  60 items)?
- `/validate-sources` cadence: on demand, or a monthly routine that writes
  its report and the CURATOR_TODO rows?
- Should validators write CURATOR_TODO rows directly (staged, like
  `research-gaps`) or only print them?
- Trade-body probes: worth the maintenance, or leave the local tier to the
  regulator's own index pages?
