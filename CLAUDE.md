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
Since 2026-11-12 the map also holds the spirit drinks, aromatised wines and
ciders with a protected name — see "Spirits and other alcoholic drinks".

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
    A 429 / 5xx answer is retried with backoff and never cached: before
    2026-10-22 any non-200 read as "no article", and a throttled run cached
    1,108 of 1,113 pairs as `missing`, a negative entry only a VIVC change
    revalidates. Three throttled slugs in a row stop the locale (`_TRANSIENT_ABORT`), so a sustained 429 is not paid as a backoff on every remaining slug. Run one process; the candidate walk (title, then every VIVC
    synonym) draws Wikimedia's 429 within minutes when parallelised.
  - Stage 02b/aocs (`scripts/02b_fetch_aoc_lexicon.py`) — per-AOC page
    (lead, section headings, full plaintext), used in stage 02d as a
    salience hint for terroir-fact extraction (see the bounded-narrative-
    layer rule below).
  - Stage 02b/styles (`scripts/02b_fetch_style_lexicon.py`) — one short
    summary per wine-style slug, used in the map sidepanel style-pill
    tooltip. The curated set covers **every node** in
    `scripts/_lib/style_taxonomy.py`: top-level buckets (red / white /
    rosé / sparkling / sweet / fortified / oxidative / other), interior
    groups (sparkling-quality / semi-sparkling / late-harvest /
    raisin-wine / generoso), distinctive leaves (vin jaune, crémant, vdn,
    vin de paille, grains nobles, vendanges tardives, clairet, primeur,
    vin de liqueur, fino, manzanilla, amontillado, oloroso, palo
    cortado, rancio, mistela, skin-contact white), and the generic
    leaves (tranquille, dry). `skin-contact-white` (under white, 2026-10-30)
    is the OIV's "white wine with maceration" (OIV-ECO 647-2020, Code I.4.9,
    adopted on Georgia's proposal), which names neither colour: the label is
    "skin-contact white" / "blanc de macération" / "blanco de maceración" /
    "wit met schilcontact", "orange" and "amber" are its search names, and
    the tooltip is the "Orange wine" article (es "Vino brisado" — es "Vino
    naranja" is a disambiguation page that includes the orange-peel wine of
    Condado de Huelva). Readers: ES "vino naranja" / "brisado" (Manchuela,
    Arribes, Pla de Bages, Conca de Barberà, Empordà, Tarragona), HU
    "narancsbor" (Somló), DE "maischevergorene Weißweine" (six Landweine);
    PT "curtimenta" is fermentation on the skins in general and IT "ramato"
    a synonym of rosato, neither the type. Per-locale Wikipedia titles live in
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
    attribution. `--only SLUG` scopes a run. Source locales beyond the UI
    four are fetched only for varieties with no fr / en / es / nl article
    (`02b_fetch_grape_lexicon.py --locales de --only …`) and sit last in
    `SOURCE_LOCALES`, so no cached translation moves; `hu` joined on
    2026-10-23 (Zala gyöngye's only article; `wiki.GRAPE_KEYWORDS["hu"]`,
    label `wiki_lang_hu`) — `grape_overrides.json["hu"]` pins 24 more
    Hungarian titles that have not been fetched. 02b builds its title
    candidates from the ASCII slug and Title-Cased VIVC synonyms, capped at
    20, so an article such as fr "Perle de Csaba" is found only by a pin.
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
  verbatim synonym strings in the UI pending JKI confirmation (a draft
  licence-query email to JKI is staged at
  [docs/vivc-jki-licence-query.md](docs/vivc-jki-licence-query.md) for a
  human to send; record the reply there). Citation:
  Röckel et al., Vitis International Variety Catalogue — www.vivc.de.
  Ambiguous slugs (multiple candidate VIVC entries) get pinned via
  `raw/vivc/slug_overrides.json` (template at `slug_overrides.example.json`).
  A pin is only as good as its number: `scripts/audit_vivc_coverage.py
  --strict` (and `tests/test_vivc_pins.py`) fails when a pin's `_prime`
  is neither the fetched passport's prime name nor one of its synonyms,
  when the passport came back blank, or when the by-slug cache no longer
  matches the pin. Visitor feedback on Navarra (2026-09-20: the pill read
  "Oneca (Galvani)") exposed 33 pins written from memory that landed on
  unrelated or non-existent passports; every pin now records the
  verification date and the previous id. Verify a number against the
  live passport before pinning it; when VIVC has no entry or folds the
  name under several primes, pin `false` with the reason — an empty
  bracket is never wrong.
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
  BY-SA 4.0" beside `wiki`-only bullets and beside a `both` bullet part of
  whose claim only Wikipedia makes (`wiki_part`,
  [scripts/_lib/terroir_wiki_part.py](scripts/_lib/terroir_wiki_part.py):
  a number, a proper noun or two word stems its `wiki_quote` carries and
  the whole regulator record — lien, other sections, national and register
  sidecars — lacks; written by `recompute_terroir_provenance.py`, which
  `rerun_terroir_facts.py` runs after the gate; a `both` fact the pass has
  not read counts as carrying one, and the gate drops the field from a bullet
  it rewrites, so a verdict read on the old text never stands; a German bullet
  (`source_lang` de) has no proper-noun shortcut, every noun being capitalised,
  and needs a number or two stems. 2026-10-30: 119 of 1,556 `both` facts —
  Manchuela's "13 °C … 600 l/m²", Somontano's Roman clause); the other
  `both` and the `cahier` bullets default to the footer attribution linking
  to the cahier PDF. Cache invalidates
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
  current sources and flags drift / erosion. The grounding test itself is
  the shared [scripts/_lib/terroir_coverage.py](scripts/_lib/terroir_coverage.py)
  — ellipsis-aware: a quote that joins two source spans with "[…]" is
  graded span by span, so it no longer fails the single-contiguous-match
  test and flips to `wiki` — and block-aware: the verbatim blocks (≥ 12
  chars) of a quote are summed, so one pdftotext artefact inside a
  quote ("gradi- giorno") no longer halves its coverage (2026-09-13:
  Montepulciano d'Abruzzo had lost 8 of 9 true facts to it); the 0.6
  threshold is unchanged — and typography-folding (2026-09-14): both
  sides are NFKC-normalised, every quote / apostrophe / dash variant
  folded (a cahier's `’` against the model's `'`, „low-9" and
  « guillemets »), soft hyphens and zero-width characters dropped and
  hyphenated line breaks closed before matching — on the r1 corpus 51 %
  of the FR quotes and 8.5 % of the others scored higher, none crossed
  the threshold downwards. Every 02d script plus the audit import
  it. The fourth sub-section is earned deterministically
  ([scripts/_lib/terroir_interactions.py](scripts/_lib/terroir_interactions.py)):
  after its four calls a 02d script drops an `interactions` fact whose
  grounding quote carries no causal connective of the source language
  (15-language table; cap 2 per record), and the gate demotes such a
  fact to the natural factors — the connective is looked for in the
  *quote*, never only in the bullet, because a bullet adding the "thanks
  to" the source lacks is the failure mode. No fact is ever promoted into
  the sub-section. 02d also normalises bullets at write time
  (`normalize_facts`), so the normalise post-pass is a no-op on a fresh
  cache. Italy: stage 02f emits the whole MASAF Art. 9 as
  `link_to_terroir_full` next to the 4,000-character panel cut
  (`link_to_terroir`, unchanged); IT 02d, the gate and the audits read
  the full text (469 of 522 disciplinari are longer than the cut). Two **cache post-passes** apply fixes without an LLM call:
  [scripts/recompute_terroir_provenance.py](scripts/recompute_terroir_provenance.py)
  re-grades the existing caches with that rule (loading each country's
  02d module for the exact source text it graded against; stale caches
  are skipped, never dropped) and syncs the per-fact `provenance` into
  the 02e caches; [scripts/dedupe_terroir_facts.py](scripts/dedupe_terroir_facts.py)
  collapses facts restated across the four sub-section calls
  ([scripts/_lib/terroir_dedupe.py](scripts/_lib/terroir_dedupe.py):
  near-identical bullets, or same/contained source quote + substantial
  bullet overlap; never two bullets with different numbers, never two
  bullets leading with different sub-denomination names — stage 04's
  sibling filter depends on those; one `_leads_with_name` serves both, and
  a name behind a wrapper leads too, "L'appellation Bonvillars …", "Le
  vignoble de Chablais …" — 2026-10-25, the Vaud sub-appellation cards had
  shown every sibling's bullet) and prunes the same indices from the
  index-aligned 02e caches, updating their `source_facts_sha`, so no
  translation is lost or redone. Both take `--dry-run` / `--only` and
  write a JSON report under `tmp/terroir-facts-review/`. Two more
  post-passes of the same shape: [scripts/normalize_terroir_facts.py](scripts/normalize_terroir_facts.py)
  applies the deterministic clean-up of
  [scripts/_lib/terroir_normalize.py](scripts/_lib/terroir_normalize.py)
  (regulatory colour codes after a grape name — "Pinot noir N" — VT /
  SGN expansion, terminal period, and in the four target locales the
  Latinisation of residual Greek / Cyrillic script: homoglyphs mapped,
  gloss tokens transliterated — an all-caps token stays upper case,
  "ΘΑΣΙΩΝ" is THASION and not ThASION, and a gloss that transliterates
  to the very word it glosses, "tines (τίνες)", loses its bracket
  (2026-10-24, the nine Greek residues of the `gr-anchor` run); the
  non-Latin class covers Greek Extended too, so a polytonic quotation —
  Rosso Conero's Strabo, «σφόδρα δ'εὔοινος» — comes out whole as
  "sphodra d'euoinos" rather than keeping its "ὔ" (the audit's and the
  untranslated detector's classes match it) —
  chemical prefixes such as "α-terpineol" (also after an elided article,
  "l'α-terpinéol")
  and predominantly non-Latin bullets left alone; and in every language the
  cut of a **reference to the document itself** — the regulator text or
  Wikipedia — at the opening, at the end or alone in brackets, the claim
  kept and re-capitalised: "Según el pliego, se cree que …", "According to
  the production specification, …", "Il disciplinare afferma che …", "The
  production regulations state that …", "A Wikipedia szerint …", "…,
  selon Wikipédia.", "(según el pliego)" (2026-10-25,
  `strip_document_reference`; the noun list covers 02e's renderings,
  "productiereglement", "reglamento de producción"). A Dutch or German
  fronted reference ("Volgens het productdossier zijn de …", "Het
  productiereglement stelt dat …") is not cut — the verb would precede the
  subject — and goes back to 02e; a subjunctive complement ("stabilisce che
  le uve provengano") and two sources compared in one bullet ("…, mientras
  que Wikipedia …") are left too. The source's own attributions — "according
  to Strabo", "Σύμφωνα με τον μύθο", "según el estudio de …" — name no
  document and are never touched, nor is the document as an object of
  history ("il disciplinare fu approvato nel 1967"). `audit_terroir_facts.py`
  counts the cuttable forms as the strict `document_reference` (its summary
  prints the 02e command for what the cut cannot reach) and the rewording
  cases — a mid-sentence "como señala el pliego", "Il disciplinare descrive i
  vini come …", the document as the setter of a rule ("le tipologie previste
  dal disciplinare", "definidos no caderno de especificações"), any other
  Wikipedia mention, inflected or not ("podľa Wikipédie") — as the
  report-only `document_reference_mid`, the gate's rewrite case: drop the
  reference, keep the claim, a rule stays a rule, and where a bullet sets
  the source text beside Wikipedia keep the source's statement and
  Wikipedia's only where it adds a detail that does not contradict it (run
  `docref-mid-2026-10-25` cleared 244 of 246 that way, 68 records re-gated;
  Vaud kept its two). `rewrite_ok` refuses a rewrite that adds a reference) to source and
  translation caches in step, and stage 04 applies the same normaliser at
  render time;
  [scripts/filter_terroir_boilerplate.py](scripts/filter_terroir_boilerplate.py)
  drops facts whose quote is a tautology pattern
  ([scripts/_lib/terroir_boilerplate.py](scripts/_lib/terroir_boilerplate.py))
  quoted by ≥ 3 records of one country ("the wines' uniqueness is due to
  soil, climate and summer winds" — most Greek PGI specs), never a
  record's only fact and never a bullet carrying a number. Stage 02d
  itself now dedupes after its four sub-section calls, appends one shared
  English style block to every country's extraction prompt
  ([scripts/_lib/terroir_prompts.py](scripts/_lib/terroir_prompts.py):
  full sentences, no arrows, no colour codes, expand VT / SGN, never
  mention the document, keep hedges, skip tautologies) and, for a cahier
  shared by several appellations (the 51 Alsace grands crus), grades
  each record against its own chapter only
  ([scripts/_lib/terroir_chapters.py](scripts/_lib/terroir_chapters.py))
  — a cru without an own chapter is skipped, never grounded on another
  cru's text. On the translation side every 02e script builds its prompt
  through `translation_system_prompt` in the same module: appellation,
  commune, vineyard, grape and institution names stay verbatim; common
  nouns (generic soils, climates, harvest categories, scheme
  abbreviations) are translated; geography takes the target language's
  established exonym (Vosges → Vogezen, Rhin → Rijn, Piemonte →
  Piedmont; verbatim only as an appellation name); Greek and Bulgarian
  sources must come out in Latin script. `scripts/_lib/exonyms.py` holds
  the exonym table and
  [scripts/detect_untranslated_terroir_facts.py](scripts/detect_untranslated_terroir_facts.py)
  lists the (slug, locale) pairs still carrying non-Latin script, a
  leaked common noun or a source-form geographic name, with the exact
  `02e --refresh --only … --lang …` command per country; every 02e
  script takes `--only`. It does not flag (2026-10-25: 320 → 120 pairs, the
  dropped ones read one by one, none a translation error): a form that is
  already the target's ("mar Egeo" in Spanish, "Karpaten" in Dutch), one
  inside a longer proper name ("Magliano in Toscana", "Alto Piemonte"), a
  quoted title or formation («Bacco in Toscana», «Argille Varicolori»), one
  inside the record's own longer appellation name ("Cannonau di Sardegna" —
  whatever the apostrophe or the case since 2026-11-13: the record is
  « Kirsch d’Alsace », the Spanish bullet writes "el Kirsch d'Alsace", a
  Dutch one "de marc d'Alsace Gewurztraminer"; nine rows on the re-run French
  spirits),
  a source term glossed in brackets after its translation ("lieu-dit (dűlő)")
  and a capitalised term opening a name ("Podgoria Crucilor"). A record named
  after the region alone still reads it as a place ("Upper Kärnten").
- **Per-record review feedback is a constraint layer for the next
  extraction, never content.** A quality review's verified findings are
  kept per record in `raw/terroir-facts-feedback/<slug>.json`
  ([scripts/_lib/terroir_feedback.py](scripts/_lib/terroir_feedback.py)):
  `do_not_claim` (verified misleading claims with the failure mode, the
  stage — `extraction` / `translation` / `both` — and the verifier's
  source-quoting reason), `capture_if_present` (what the source describes
  prominently and no bullet captured), `record_cautions` (sibling text
  inside the source, a wrong binding, a source typo, a wrong Wikipedia
  article), `reviews` and a `history` list for later gate runs. Every
  02d script calls `with_feedback(system, slug)` right after formatting
  its system prompt (live call and `--emit-todo` alike; the wiring lint
  in `tests/test_terroir_feedback.py` fails when a script drops it):
  the block phrases each negative as "do not assert … unless the source
  states it explicitly (then state it plainly, without naming the source)"
  — the bare escape had been answered "Según el pliego, …" (2026-10-25) —,
  never carries the reviewer's corrected text,
  and includes only the `extraction` / `both` entries — `translation`
  entries are for a 02e back-check. A `capture_if_present` hint is a
  **priority, not a slot** (2026-10-24): the sub-section cap stands, and a
  hinted fact the text states takes a slot ahead of an unhinted one —
  phrased "If the text describes it, capture: …" until then, the hint
  had no standing against the cap, and Tokajské's four raised
  human-factor slots all went to unhinted facts on the first re-run. Two failure modes are claims a source
  *does* state, so that escape would let them through (`ESCAPE_BY_MODE`,
  2026-10-23): `source-vintage` (an outdated statement — a Wikipedia
  article older than the regulator text in force: Alicante's two subzonas,
  Monterrei's six municipalities) may be asserted only from the regulator
  text, `sibling-or-subzone-confusion` only where the source says it of
  this appellation; the gate's constraint lines carry the same notes.
  `audit_terroir_facts.py` reports
  `feedback_recurrence`: a do-not-claim entry whose source-language
  bullet still matches a current bullet (the known error is still there
  before a re-run, or came back after one). Sidecars are built and
  merged from a review's evidence directory by
  [scripts/build_terroir_feedback.py](scripts/build_terroir_feedback.py)
  (review 2026-09-12: 384 do-not-claim entries in 346 records, 1,133
  hints, 96 cautions over 1,238 records — see
  [docs/review-terroir-facts-2026-09-12.md](docs/review-terroir-facts-2026-09-12.md)).
  A card-level review (`audit_cards_llm.py --emit-feedback`) grades the
  rendered card in one locale: its row is filed under the record that owns
  the facts (the row's `owner`, else the slug's own cache, else its
  parent's — a sub-denomination card shows its parent's bullets, so
  `alicante-lalcoia`'s findings land in `alicante.json`), and the fact
  index and source-language bullet are recovered from the owner's caches,
  without which the recurrence check compared an English claim with
  Spanish bullets and never fired. The card judge sees one locale only, so
  the stage of a non-English record's finding is the curator's call when
  merging (`where` in the evidence row).
  Like the other `raw/` caches the sidecars are gitignored; a checkout
  without them extracts exactly as before.
- **Every terroir-fact write is snapshotted; the chain is one rollback
  unit.** Stage 02d, the gate, stage 02e, the back-check and the four
  post-passes write the caches only through
  `terroir_cache.write_source_cache` / `write_translation_cache`
  ([scripts/_lib/terroir_cache.py](scripts/_lib/terroir_cache.py); the
  wiring lint in `tests/test_terroir_backup.py` fails on a direct
  `cache.write_json`). The first write to a slug in a run copies its
  source cache AND its four translation caches to
  `raw/terroir-facts-backup/<run>/` ([scripts/_lib/terroir_backup.py](scripts/_lib/terroir_backup.py):
  one entry file per slug, so parallel per-country processes share a run
  id without racing); the run id is `OWM_TERROIR_RUN`, else a
  per-process timestamp. `scripts/rollback_terroir_facts.py --list` /
  `--run <id> [--only slug] [--dry-run]` restores every file the run
  overwrote and deletes every file it created, source and translations
  together (a rollback is itself snapshotted, so it can be undone); then
  rebuild with stage 04. [scripts/rerun_terroir_facts.py](scripts/rerun_terroir_facts.py)
  runs a scoped re-run under one id — it marks the scoped caches stale
  (`cahier_source_sha` prefixed `stale:`, written through the backup) and
  then chains `02d --batch` per country (parallel) → `02d_verify --batch`
  → `02e --batch` per country → `02e_verify --batch` → the audit, logs
  under `/tmp/owm-<run>/`. A scoped slug with no cache yet (a new
  appellation) is placed by its extracted record's `country` so
  `--scoped-02d` still reaches it (before 2026-10-04 it was logged and
  dropped from the pass-down).
- **The claim-support gate is part of the pipeline (review 2026-09-12,
  R2 / R3 / R7 / R8).** Stage 02d's coverage test only proves the *quote*
  exists; [scripts/02d_verify_terroir_facts.py](scripts/02d_verify_terroir_facts.py)
  ([scripts/_lib/terroir_gate.py](scripts/_lib/terroir_gate.py)) grades,
  per record in ONE request, every bullet's *claim* against the exact
  source text 02d graded against (`terroir_sources`), the Wikipedia
  hints and the record's feedback sidecar (verified-misleading claims
  become explicit checks, record cautions disqualify pasted or mis-bound
  text). Verdicts are applied deterministically: `supported` stays;
  `rewrite` replaces the bullet with the model's narrower rewrite
  (guarded — no number absent from bullet + source, no arrow, sane
  length; a refused rewrite keeps the original and is listed by the audit
  as `rewrite_rejected`; a rewrite that came back empty keeps the
  original as `supported` with `rewrite_missing`, and a *cosmetic* one —
  ratio ≥ 95 and no differing word of 4+ letters, so an added hedge is
  never cosmetic — keeps the original as `supported` with
  `cosmetic_rewrite`, `gate-v2`); `drop` removes it (unsupported,
  foreign, tautology, or `restates` another bullet — the semantic
  dedupe); `subsection` moves a clearly misfiled bullet. An
  `interactions` bullet is supported only when the source sentence
  states the causal link, and after the verdicts the deterministic
  connective test demotes any that still lacks one.
  Each kept fact carries `support` ({verdict, note[, original_bullet][,
  moved_from]}); the cache carries a `gate` block (shas it keyed on,
  counts, the dropped bullets) and the feedback sidecar a `history`
  entry. Translations: index-aligned prune for pure drops; a rewrite
  re-keys them `pending:<sha>` so 02e re-translates. Incremental — a
  record is due (`terroir_gate.needs_gate`, shared with the audit's
  `gate_pending`) when any fact carries no gate verdict, or the gate
  block predates the record's source sha or `GATE_VERSION`; deliberately
  not an exact sha of the bullets, so the normalise / dedupe /
  boilerplate post-passes no longer re-fire the gate corpus-wide. The 21
  extraction prompts share the same rules through `STYLE_RULES` in
  [scripts/_lib/terroir_prompts.py](scripts/_lib/terroir_prompts.py),
  which opens with the claim-support rule — the gate's own over-claim
  catalogue (a causal wrapper on a co-occurrence, a narrowed en-bloc
  attribution, an invented qualifier, a sibling's statement, a
  strengthened hedge) — so the extractor does the gate's job first; then
  one full sentence of ~120–220 characters (the 140-character cap that
  produced the "Label:" fragments is gone), named entities and figures
  first, an earned `interactions` sub-section. **The sub-section caps are
  set by the code, not weighed by the model** (`sub_section_cap` in the
  same module, 2026-10-24): the base caps are natural factors 5, human
  factors 2, product 2, interactions 1; a regulator text over 4,000
  characters — measured once per record on the cached leading document
  block, the lien (the CH / GB / MT context block), never the Wikipedia
  hint — raises them to 7 / 4 / 3 / 1, and `interactions` is never
  widened. Until then the allowance was a sentence of the style block
  ("you may return up to two extra bullets") set against each call's
  hard "Maximum N": Sonnet 5.5 never used it (phase D of the 2026-10-23
  review — 25 re-extractions, none over the base cap, Tokajské's 8.6 k
  characters of history held to 2 human-factor bullets) while the older
  models overshot freely (948 of 1,644 caches), so every scoped re-run
  trimmed a richer cache (Tokajské 13 → 9). 1,275 of the 1,622
  measurable liens are over the threshold, so the rule is close to a
  base-cap raise. A cap change re-stales nothing — freshness keys on the
  source sha and the Wikipedia revision — it applies when a record is
  next re-run; `tests/test_terroir_prompts.py` lints that every 02d
  script sets its cap through the helper. A descriptive sub-section can
  also come back `{"facts": []}` from a text that states its facts —
  Alicante's product call twice (its picks restated the natural factors and
  the dedupe removed them), and in the `gr-anchor-2026-10-24` run 107 of
  the 115 Greek product calls, 43 of them explaining that the text holds
  "no organoleptic profile" while it states the wine's colour or sweetness,
  three that the user turn carried only the title (since the caching
  refactor the document is the leading system block and the 20 prompts
  still said "in the user message below"); the same prompt re-sent
  synchronously returned the facts, so the class is sampling variance on a
  narrowly read sub-section. Three things in
  [scripts/_lib/terroir_prompts.py](scripts/_lib/terroir_prompts.py) since
  2026-10-24, used by all 20 non-FR scripts: `product_topics(lang)` names
  the wine *types* the text says are made, a variety's colour range,
  sweetness, ageing and the traditional methods, and says a colour /
  sweetness / type statement is a product fact without a tasting note (the
  ES wording generalised; GB and LU keep their own specifics as a lead);
  `ask_line(lang, label)` is the one-line user turn and points at the
  document block, as does every script's "SOURCE 2" header; and
  `should_retry` asks for one **second reading** (`ask_line(…, retry=True)`:
  the first answer was an empty list, yet the text carries statements on
  these topics — an empty list only if there is truly none) when the
  natural-factors or product call returns [] on a text carrying ≥ 3
  distinct stems of that sub-section's vocabulary (`RETRY_VOCAB`, 15
  languages) — never `interactions` (earned) or the human factors (no
  empties in 115). The cache lists the sub-sections read twice
  (`retried_subsections`). In batch mode the second reading is a
  **follow-up round** (`batch.run_two_pass(..., follow_ups=True)`, see the
  Batch API section). First probe, chios: its product call answered []
  again and the second reading returned 2 facts. The audit's `feedback_recurrence` counts a
  do-not-claim entry as resolved when the matched fact's
  `support.original_bullet` is the claim and the gate's rewrite was not
  cosmetic.
- **The translation back-check follows 02e (R6).**
  [scripts/02e_verify_terroir_facts.py](scripts/02e_verify_terroir_facts.py)
  ([scripts/_lib/terroir_backcheck.py](scripts/_lib/terroir_backcheck.py))
  compares, per (record, locale) in one request, each translated bullet
  with its source bullet — changed numbers, dropped or upgraded hedges,
  wrong entities and back-formed names, the watch-list false friends
  (generoso → generous, tirage → disgorgement, Burgundian climat →
  climate, Lehm → clay, Pintes → Pinot, Немски ризлинг ↔
  Welschriesling), untranslated common nouns, missing exonyms
  (`exonyms.exonym_hits` feeds the model its hits), and in NL an article
  that does not agree with its noun ("Het wijngaard" for *le vignoble* —
  the article copies the source noun's gender; 42 bullets in 36 records on
  2026-10-09; [scripts/_lib/nl_articles.py](scripts/_lib/nl_articles.py)
  feeds the model its hits and `detect_untranslated_terroir_facts.py`
  lists them as `article:`) — and applies the corrected translation under
  the same guards (a fix may be up to 115 % of the bullet it replaces,
  360 characters at least); every checked bullet
  carries `check`, the cache a `backcheck` block keyed on both shas. The
  glossary ([scripts/_lib/translation_glossary.py](scripts/_lib/translation_glossary.py))
  and the exonym table carry the same terms so 02e gets them right
  first time.
- **The LLM audit is the acceptance measure.**
  [scripts/audit_terroir_facts_llm.py](scripts/audit_terroir_facts_llm.py)
  grades a sample of records' rendered EN bullets against the full source
  with an adversarial verifier on a *different* model
  (Opus — `STAGE_DEFAULTS["audit"]` — vs the Sonnet extractor) and reports the
  reader-misled share with a Wilson interval; `--from-backup <run>`
  grades the same records' pre-run state and `--compare A B` prints the
  paired before / after. A record written in the graded locale (MT and GB
  in English) is graded on its source bullets — the card renders them;
  until 2026-10-23 it was skipped as `no-translation`, so no English-source
  record had ever been measured. Run it after every scoped re-run; the review's
  target is < 1.5 % misleading. Every Batch-API run prices itself:
  `batch.run_batch` sums the per-result usage, prices it at the batch
  rate (`BATCH_PRICES_USD_PER_M`) and appends one row per batch to
  `raw/.batch/costs.jsonl`; the gate and back-check reports carry it
  under `batch`, and `rerun_terroir_facts.py` logs the run's spend per
  stage at the end.

## Decisions of 2026-11-07 — interpretations the card discloses

Eight questions the curator queue had left to Boris were settled on
2026-11-07. The rule that came with them: **where the card interprets or
departs from the regulator's letter, the card says so** — a disclosure line
under the pills, a pill tooltip, a Sources row or a cited per-record note in
[scripts/_lib/appellation_notes.json](scripts/_lib/appellation_notes.json)
(the ⓘ block). Decision by decision:

- **A FR per-record grape pin.** Saint-Mont's rosé clause lists "manseng B"
  beside "petit manseng B"; the bare alias binds Manseng noir, the record's
  adaptation variety ("manseng N"). [scripts/_lib/fr/grape_context_overrides.json](scripts/_lib/fr/grape_context_overrides.json)
  (record slug → "surface code" → slug, reason, source, verified; the ES / IT
  pattern) reads it as Gros Manseng on that record only
  (`grape_lexicon._fr_context_pin`, applied inside the FR roster reader when
  stage 02 has set the pliego context); no other cahier writes a bare
  "manseng B". The card carries a note saying it is a reading of the letter.
  `tests/test_fr_grape_context.py`.
- **The colour floor for a liqueur-only record** (`wine_categories.liqueur_only`:
  liqueur wine declared, no still or sparkling category): a floor colour only
  from a roster of one colour. Jerez, Manzanilla, Samos, Malvasia Paros,
  Moschato Rodou and Rio Patras keep White; Madeira, Koumandaria, Grand
  Roussillon and Condado de Huelva lose the Red and White their mixed rosters
  had inferred (the feature property `styles_floor_off`, which
  `audit_styles.py` honours). **Every floor-inferred colour is disclosed**: the
  feature property `styles_inferred` reaches the panel payload and the card
  prints "Colours inferred from the berry colour of the authorised varieties;
  the regulator's text names no colour" under the style pills
  (`styles_inferred_line`). The GR and CY national-spec augmenters merge the
  spec's `category` role since the same day (they had merged four roles and
  not the category list, so Koumandaria declared nothing and kept its floor
  colours); the three Greek liqueur records already state their colour.
- **Semi-dry** joins Semi-sweet and Sweet under the same type-list rule in
  the ES, GR, HU and BG readers ("secos, semisecos, semidulces y dulces";
  ημίξηρος; félszáraz; "полусухи вина") — never from an IT "sapore: da secco
  ad abboccato" taste range or a FR "demi-sec" labelling mention (IT and FR
  unchanged). Dry stays unrendered (`_DROP_STYLES`).
- **A § 4 varietal wine type is a principal variety** (`section_varieties.py`:
  `section-4-type` → principal, `section-5-rule` → accessory), the reading of
  the MASAF Article 1 reader; this revises the 2026-10-24 "accessory" call
  after the card validator graded Piemonte's Sauvignon misleading. The card
  says it: "{names} shown as principal: the single document names them as
  varietal wine types (section 4, at least 85 % of the variety), not in its
  list of varieties (section 7)" (`grapes_section4` in the payload, from the
  details' source tag; `grapes_section4_one` / `_many`). 15 ES / IT records.
- **A Wikipedia Sources row** wherever a rendered terroir bullet is
  Wikipedia-marked (`provenance` wiki or `wiki_part`): `sources.wikipedia_url`
  is the facts cache's `wiki_source_url`, the row "Wikipedia article (CC BY-SA
  4.0)" (`src_wikipedia`). The inline marker stays.
- **Per-colour grape roles on the pill.** The FR reader records, per grape,
  its role in each colour clause (`_COLOUR_CLAUSE_RE` / `_clause_colours`:
  the last "Vins blancs" / "a) - Les vins rouges" / "Vins rouges et rosés"
  header before the role chunk, the record's own clauses only) and
  `parse_grapes` returns `roles_by_colour` for the grapes whose roles differ;
  stage 02 stores it on the record (parent and DGC), the payload carries
  `grape_roles_by_colour`, and the pill — which keeps the stronger role — gets
  `data-roles` + `title` and a tooltip line "principal for white wines ·
  accessory for red wines" (`rbc_*` labels; `roleByColourText` /
  `_role_by_colour_text`). 179 FR parents have such a grape (Crozes's
  Marsanne, Arbois's Poulsard).
- **Bela krajina keeps the 2007 pravilnik's role split** over the fiche's MAIN
  tags and the fiche's "4. Peneče vino" as a category — a house decision the
  card now states in a note citing both documents.
- **"Alsace suivi d'un nom de lieu-dit" stays listed** as SIQO lists it, with a
  note saying the cahier treats the lieu-dit mention apart from the DGCs.
- Two more notes of the same kind: Stredoslovenská (the roster is the 2013
  technical file's where the 2020 single document's § 7 names Furmint alone)
  and Saint-Mont (above).

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
publishes one cahier des charges per appellation — and inherit `sections`
/ `aire` from the parent. Their `styles` and `grapes` are the parent's
unless the cahier singles the DGC out ([scripts/_lib/fr/dgc_rules.py](scripts/_lib/fr/dgc_rules.py),
`_apply_dgc_rules` in stage 02, 2026-10-04): a section III reservation rule
naming it ("La dénomination géographique complémentaire « Puy-Notre-Dame »
est réservée aux vins tranquilles rouges", or its row of the colour table)
sets its colours with the DGC's own SIQO categories; its section V rows or
clauses set its roster — a two-column `pdftotext -layout` table is read by
column, a centred or full-width heading scoping the rows below it, a left
label pairing with the value block it overlaps (a name wrapped over two
lines, a value printed above its label); and a DGC section V does not name
keeps the parent's roster minus the clauses / rows of a colour it is not
allowed (Côtes de Bordeaux Cadillac drops "b)- Les vins blancs"). In prose
only a reservation sentence counts (an IGP's description "Pour l'unité
géographique « Coteaux du Grésivaudan », les vins blancs présentent …" is
not a rule), "hormis / sauf / à l'exception de « X »" excepts X, and a
clause ending "… la liste suivante :" takes the list after it (Var
Correns). The record carries `dgc_rules` ({types, encepagement} → own /
colour) where it applied. First run: 78 of 1,074 DGCs changed — Touraine
Oisly is white Sauvignon, Saumur Puy-Notre-Dame red Cabernet franc, the
Languedoc and Côtes du Rhône Villages red-only DGCs lost white and rosé,
Mâcon Fuissé / Loché / Vinzelles white Chardonnay. Known residue: a grape
both accessory in one colour row and principal in another takes the first
role read (Fiefs Vendéens Vix's rosé Gamay).

The table reader was settled on the Alsace and Savoie cahiers on 2026-11-07
(CURATOR_TODO row of 2026-10-30: Klevener de Heiligenstein inherited the 21
Alsace varieties while its row reads "savagnin rose Rs"): `dgc_keys` strips
*every* " ou " alias of the parent as a prefix, not only the whole name
("Alsace Klevener de Heiligenstein" under "Alsace ou Vin d'Alsace" yields
"klevener de heiligenstein"; until then no DGC of Alsace, Corse or Savoie ever
matched its own row), and folds the hyphen SIQO writes where the row reads
« Saint Hippolyte »; a « quoted name » opening a left line starts a row label
of its own when the label above already holds a whole quoted name and does
not run on into it (the Alsace table lists one DGC per row, one blank line
apart, and read as one block the rows pooled into one roster — Bergheim had
the union of every row; "Dénomination géographique complémentaire / « Abymes
»" and "« Apremont », « Cruet », / « Montmélian »" continue); a value block
running across several labels is cut at their first lines (`_cut`); a row is
serialised as its label then the right-column text of its value lines, the
columns apart, so a label line inside a wrapped value ("mondeuse / grise G")
or a quoted name wrapping around the value cell ("« Saint-Jean-de- mondeuse N
exclusivement / la-Porte »") no longer cuts the grape — and the names are
tested column by column, so that wrapped name still names its row; a value
cell merely naming the DGC counts only where no row label does (the parent's
white row restricts savagnin rose to the Klevener parcels; the DGC's own row
is its roster); and a heading's scope ends at the next row labelled with
another DGC (the Savoie heading « Chautagne », « Chignin », « Jongieux » had
swallowed Chignin-Bergeron's and Crépy's rows). 28 of 1,063 DGC records
changed, every one read against its cahier: the 13 Alsace DGCs (Bergheim
Gewurztraminer, Ottrott / Rodern / Saint-Hippolyte Pinot noir, Côte de
Rouffach four, their colours from the section III label blocks; the VT / SGN
on Val Saint Grégoire, Vallée Noble and Wolxheim are their SIQO categories)
and the 15 Savoie DGCs (Apremont Jacquère with its accessories, Arbin and
Saint-Jean-de-la-Porte Mondeuse "exclusivement", Ayze Gringet, Chignin-
Bergeron Roussanne, Crépy Chasselas). The full FR re-extraction of the same
afternoon changed six more DGC records the sweep had not predicted — it had
compared the old and new `dgc_keys` with the other reader changes present on
both sides, so the row-label split's own effect was invisible; compare against
the on-disk records next time. All six follow their cahier's rows: Mâcon
Serrières is "Vins tranquilles rouges et rosés" (its white and primeur
gone), Mâcon Solutré-Pouilly white only, Côtes du Roussillon Villages
Caramany and Lesquerde without Mourvèdre, Les Aspres and Tautavel without
Lledoner pelut. `tests/test_fr_dgc_rules.py` carries both tables.

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

The opposite failure — BO Agri serves a PDF that downloads fine but is
verifiably *another* appellation's cahier (Pierrevert carried
Saint-Pourçain's lien; L'Étoile and Grands-Echezeaux carried Bourgogne
Passe-tout-grains') — is pinned in the **checked-in**
[scripts/_lib/fr/register_overrides.json](scripts/_lib/fr/register_overrides.json)
with `prefer_cahier: true`: stage 01 then binds the eAmbrosia register's
cahier attachment ahead of BO Agri (full `eambrosia-register` provenance,
`boagri_url` left empty), bypassing the has-usable-cahier guard that
otherwise protects working resolutions from INAO outages. The audit's FR
name guard (`audit_terroir_facts.py`, strict) flags a lien that never
names its appellation, so a recurrence cannot go unnoticed. A register name
that lists its aliases ("X ou Y ou Z") is named when any alias is: Fine du
Languedoc's longest token was "originaire", a word its cahier of 9 December
2025 no longer writes.

## Stage 02: homologation dates, the unnumbered 2024 layout, the aire table, the 2026 eau-de-vie template

Stage-02 rules added 2026-10-04 — the first two while binding the
Montpeyroux cahier, the rest while closing the Saumur / Côtes du Lot / Marc
d'Alsace items of the same day:

- **`homologation_date(segment, before)`** reads "homologué par arrêté du …"
  (no article — 150 cahiers), INAO's own typo "homologué pa l'arrêté"
  (Montpeyroux), "du 1er septembre", and, when the segment's head carries
  no date, the 600 characters *before* the segment — the BO Agri cover line
  "Cahier des charges de l'AOC « X » homologué par … du DATE" sits above the
  title the bundle splitter cuts at. 583 → 1,477 dated records; the same
  function dates the rescue index, so a newer cahier of the same name now
  wins the rescue (Saint-Joseph 2011 → 2024). The record's `source.
  homologated_at` feeds the panel's "homologué le" line.
- **`extract_unnumbered_sections`**: the 2024 Saumur cahier prints the XII
  section titles as bare centred lines (pdftotext never sees the "I. -" the
  PDF draws as list numbering), so the Roman splitter found nothing and the
  record was silently served the superseded 2019 cahier through the rescue.
  When the Roman read yields < 3 sections and the canonical titles match ≥ 6
  whole lines, the titles are numbered by their canonical position; routing
  is unchanged. A normal cahier matches one such line at most, so the gate
  never fires on it.
- **The aire table** (`strip_table_label_column`): some 266 cahiers print
  section IV as a table — a label column ("Vins tranquilles blancs et /
  rosés", "Dénomination géographique complémentaire « Puy-Notre-Dame »")
  beside the commune column — and pdftotext -layout interleaves the label
  words with the commune lines of the same row, so Saumur read
  "Doué-en-Anjou (… de Doué-la-Vins tranquilles blancs et Fontaine …)" and
  listed every commune once per wine type (9,213 duplicate tokens over the
  corpus). When the section carries the table header ("COULEUR DES VINS" /
  "TYPE DE VIN" / "DÉNOMINATION(S) GÉOGRAPHIQUE(S)" … "COMMUNES"), each row
  block is cut at the commune column — where the block's "Département de
  X :" lines start, else the indent most of its indented lines share — a
  margin line keeping only what it has at that column past a space, and
  `by_dept` lists a commune once per département. A block qualifies as a
  row when it is mostly indented cell lines, or when its indented
  "Département" lines all carry the colon of a cell ("Département de
  l'Hérault : Cabrières.") beside a line that has both a label and cell
  text; a centred "Département de l'Aude" header over a list at the margin
  (Saint-Chinian's proximity zone) is neither and is left alone. Nothing is
  cut in a cahier without the header. Hyphenated line breaks are joined
  after the cut ("Saône-et-\nLoire" had been a département "Saône-et").
- **The proximity sentence** (`_PROX_SENTENCE_RE`): where section IV has no
  numbered sub-blocks (the IGP template) the text from "La zone de
  proximité immédiate définie par dérogation …" on is the proximity zone,
  never the aire — Côtes du Lot's six out-of-département *cantons*
  (Fumel, Tournon-d'Agenais; Lauzerte, Molières, Montaigu-de-Quercy,
  Montpezat-de-Quercy) were its aire until then, and some forty IGPs
  (Gard, Aude, Pays d'Hérault, Cité de Carcassonne, Haute-Marne,
  Île-de-France …) carried their neighbours' communes as their own. The
  CSV row already drew the right polygon; the record's aire and the wiki did
  not say so.
- **A whole département** (`whole_departements` → `aire_departements`):
  "La récolte des raisins, la vinification et l'élaboration des vins … sont
  réalisées dans le département du Lot" / "sur le territoire du département
  de la Haute-Marne" / "sur la totalité du territoire du département de la
  Drôme" / "dans toutes les communes du département des Bouches-du-Rhône" /
  "l'ensemble des communes des départements de l'Aude, de l'Hérault, du Gard
  et des Pyrénées-Orientales" name no commune. The sentence is anchored, the
  window after it is read item by item (article dropped, list ended by the
  first item that is not a département — "à l'exclusion des communes de …",
  "ainsi que sur les communes suivantes …", "correspondant aux communes") and
  every item must be a whole name of the département table (so
  "Lot-et-Garonne", "Territoire de Belfort" and an article-less "Hautes-Alpes,
  Alpes-Maritimes, Var" come out right). A sentence-form commune the same
  text names for such a département is a DGC's zone (Rocamadour) and is
  dropped; a list-form one (an exclusion list, a DGC's) stays on the record
  and the wiki shows the département whole in its place. A storage rule
  ("Le stockage … doivent être réalisés dans les départements du Haut-Rhin et
  du Bas-Rhin") is not the récolte and never matches.
- **A list cut by the page**: the BO Agri running header after a comma
  ("Houssen,\n\fPublié au BO Agri …\n\nHunawihr") folds into the list
  (Marc d'Alsace's Haut-Rhin read 17 of 53 communes; the 51 Alsace grands
  crus' proximity zone 45 of 79), and a "Département de X :" header whose
  list starts after a blank line ("de la Meuse :\n\nBilly-sous-les-Côtes, …";
  "de l'Ardèche : 96 communes\n\nAlboussière, …") takes the next paragraph
  when it reads as a list — mostly capitalised, comma-separated tokens — the
  count token dropped.
- **The 2026 eau-de-vie template** (`is_spiritueux_2026_template`,
  `extract_spiritueux_2026_sections`): Marc d'Alsace Gewurztraminer's cahier
  of the arrêté du 2 septembre 2026 opens "Chapitre Ier : Conditions de
  production et lien à l'origine" with Arabic "N. - Title" sections — Nom,
  Description de la boisson spiritueuse, Définition de la zone géographique
  concernée, Description de la méthode d'obtention, Lien à l'origine
  géographique, Règles de présentation — then Chapitre II (declarations) and
  Chapitre III, whose control-plan rows "A. - RÈGLES STRUCTURELLES / B. -
  RÈGLES ANNUELLES / C. – PRODUIT" are letter headers: the EU documento-único
  branch took them (A/B/C present) and the record came out with no aire, no
  lien and no grape. The branch is tested after the Partie-I spirits
  template and before the Roman splitter; it slices Chapitre Ier only, on
  headers *with* the dash ("1. Description des facteurs du lien au terroir"
  inside section 5 is a sub-item), routes by title keyword (the Partie-I
  table plus `encepagement` → the méthode d'obtention, narrowed to its
  "Matière première" sub-block), and the record is `kind: EDV`. A grape-
  derived spirit (`is_grape_spirit`: marc, eau-de-vie de vin) with that
  block gets its grapes parsed — gewurztraminer Rs — where every other EDV
  record keeps none; styles stay empty.
- **`DEPT_HEADER_RE` is linear now**: its "up to four lines before the
  colon" group ended each line on an optional newline, so a header with no
  colon (Saint-Chinian's centred "Département de l'Aude" over a margin list)
  was tried every way four lines can be split — 40 s on a 4 KB section, and
  the minutes-long JO-issue case of the register shadow report. Each line
  now ends on its newline. A département name no longer spans a line
  ("Département de l'Hérault\nAutignac, …" had read "Hérault Autignac"), a
  sub-item "b) Pour la dénomination …" ends a list, and a list token that
  runs into a sentence keeps its first sentence.
- **Lists that cross a page, and what ends a list (2026-11-13).** Re-sourcing
  the spirits from BO Agri showed the aire reader losing the tail of long
  lists: the page number and the BO running header inside a list — "Saint-Loup,
  Saint-\n   2/8\n\fPublié au BO du MASA …\n\nMaigrin" (Cassis de Saintonge
  lost 89 communes there; the break inside a hyphenated name is joined), with
  or without a blank line before the page number (the Gard list of the Rhône
  spirits) — is folded by `_BO_PAGE_HEADER_RE`; a header no longer takes the
  next "Département …" line into its own ("Département des Bouches-du-Rhône,
  toutes les communes." had been given the Drôme's list); a département
  named whole **in list form** ("Département du Var, toutes les communes." /
  ": l'ensemble des communes", Marc de Provence, Côtes Catalanes, the
  Normandy perry spirit) and "Territoire français : départements des …"
  (Génépi des Alpes) join `aire_departements`; and a list ends where a
  sentence starts — "… Varennes-sur-Loire.\nLes documents cartographiques …
  de l'origine et de la qualité." had left a commune « de la qualité » on some
  twenty records (Fixin, Mercurey, Muscadet, Savennières …). Full FR runs
  against a snapshot after each fix: every changed record changed in `aire`
  only (48 parents, then 28 more) — Bordeaux 146 → 495 communes read, Cognac 303 → 733, Calvados 914 →
  1,418, Pommeau de Normandie 1,022 → 1,530, Mirabelle de Lorraine 578 → 964,
  Atlantique 1,480 → 1,667; Pays d'Oc 37 → 6 (the lists of its two smaller
  units and three junk tokens gone: four départements whole and six Lozère
  communes are its aire). No wine polygon reads these lists; the two records
  drawn from the cahier text do (below). The spirit template is also read in
  its 2013 layout ("A/ FICHE TECHNIQUE", sections "a." to "h.": Absinthe de
  Pontarlier), "Partie I. Fiche technique" with its full stop, and the date
  of "homologué l'arrêté du …" (Kirsch d'Alsace: no "par").
  `union_for_appellation(record, commune_idx, insee_idx)` draws a
  département of `aire_departements` whole — only Marc de Provence (three
  départements whole and the communes of four more) and Euskal Sagardoa are
  drawn from the cahier text. `tests/test_fr_cahier_parser.py`.
- **A département heading with no colon, a département the cahier spells its
  own way (2026-11-13, later the same day).** "Département des Côtes-d'Armor"
  alone on its line with the communes on the lines below is a heading
  (`_BARE_DEPT_HEAD_RE`): it must name a département of the table and the
  paragraph under it must read as a list (`_list_paragraph_after`); in the
  aire's own text it counts only up to the first mention of the proximity
  zone (Saint-Chinian prints "3o Aire de proximité immédiate" — a letter o,
  no block header the splitter knows — over a centred "Département de
  l'Aude"). Lists are kept in text order whichever form reads them.
  `_canonical_dept` keys a département as the table spells it when the
  cahier does not: « Pyrénées Orientales », « Maine-et Loire », « Puy-deDôme »,
  and a name the header pattern cut at a lower-case particle, completed from
  the text after it (« Côte » d'Or, « Bouches » du Rhône, « Ille » et Vilaine,
  « Saône » et Loire); the table's own spellings stay as written, and two
  spellings of one département share one key (Crémant de Bourgogne had
  « Côte-d’Or » and a cut « Côte »). Full FR run against a snapshot: 168
  records changed (30 parents and their sub-denominations), `aire` only —
  the six drinks, Roussette de Savoie's proximity zone (empty until then),
  and département keys of 22 wines (Côtes Catalanes' 223 communes and Coteaux
  de l'Auxois's 192 resolve for the first time; both match INAO's rows).
- **A shared cahier is read per appellation** (`shared_cahier.own_text` /
  `own_encepagement`, [scripts/_lib/fr/shared_cahier.py](scripts/_lib/fr/shared_cahier.py),
  2026-10-04): where section I declares several appellations, the colour
  (section III) and the roster (section V 1°) are read from the units that
  name the record — a lettered clause, a table row block opening on its
  « name », a sentence — else from the general units that name no other
  appellation; "à l'exception de « X »" excepts X, a "X ou Y" register name
  answers to either alias, and "pour les vins rouges / rosés" items drop
  when the record's own colour lacks them. Before, every Alsace grand cru
  carried Pinot noir, red, Sylvaner, Chasselas and Pinot blanc (a grape
  filter returned all 51; found through the MCP server); now red is Hengst,
  Kirchberg de Barr and Vorbourg only, Sylvaner Zotzenberg only, the
  accessories Altenberg de Bergheim's and Kaefferkopf's. The same rule split
  Anjou / Cabernet d'Anjou / Rosé d'Anjou and Pouilly-Fumé (Sauvignon) /
  Pouilly-sur-Loire (Chasselas). A SIQO product named "… vendanges tardives
  …" / "… sélection de grains nobles …" adds that category even when its
  `categorie` column says "Vin tranquille" (Kaefferkopf had lost VT / SGN).
- **A table label inside a wrapped variety name**
  ([scripts/_lib/fr/roster_table.py](scripts/_lib/fr/roster_table.py),
  2026-11-07): `pdftotext -layout` centres a two-column roster table's row
  labels ("Vins blancs", the adaptation clause) on the row's value lines, so
  a label line can sit between the halves of a wrapped name — Coteaux
  Varois's "… semillon B, ugni / Vins blancs / blanc B, vermentino B.", whose
  card lacked Ugni blanc — and a label's prose can run up to one space
  before the values on the same line — Alsace's "… l'ODG et Voltis B, …,
  Johanniter / les opérateurs habilités concernés, d'une convention B, Chenin
  B", whose Johanniter was lost (card re-grade of 2026-10-30).
  `repair_label_interleave`, called on the parent's roster text right before
  `parse_grapes`, cuts each line at the value column (`dgc_rules`'
  `_value_column`; the run splitter would read a one-space gap as one run)
  and moves such a left-column stretch above the value line it interrupts —
  only when the two halves form an exact lexicon surface closed by a colour
  code (`grape_entity.exact_match`); everywhere else the text is returned
  as printed. Corpus diff: 2 of 448 parents change (Ugni blanc principal on
  Coteaux Varois, Johanniter observation on Alsace). The DGC path reads its
  rows through `dgc_rules`' own column serialisation and needs no repair.
- **The record name follows the referentiel, not the fetch cache.** Stage
  02 overlays each manifest entry's `name` with the `appellation` the
  referentiel gives through `siqo.siqo_rows()` (`[name]` log line per
  change), so a supplement, a pinned name or a renamed row does not wait for
  a stage-01 re-run — see "The FR corpus follows INAO's catalogue".

## eAmbrosia register — second source for the FR cahier

BO Agri is the FR pipeline's primary cahier source, and its long tail is
expensive: hand-curated URLs in `manual_overrides.json`, a Légifrance
cookie-injection fetcher ([scripts/01b_solve_legifrance.py](scripts/01b_solve_legifrance.py)),
and OCR over professional-org mirrors for the 2011 Burgundy cohort. The
**eAmbrosia EU GI register** serves the *same INAO cahier PDF* per GI as an
attachment — `productSpecifications[0]`, whose filenames are literally
`CDC_Batard-Montrachet.pdf` / `CDC IGP Haute-Marne.pdf` — with none of that.
It is wired as a **self-service fallback tier**, not a replacement: BO Agri and
the curator overrides still resolve first, so every currently-canonical
resolution stays canonical.

**BO Agri answers French IPs only** (since at least 2026-09-20; verified
2026-10-01 — `info.agriculture.gouv.fr`, 185.24.186.182, connects from Paris
and times out from BE / DE / NL / CH / ES, VPN or not). Stage 01 from outside
France therefore stalls on every download and, because of the
has-usable-cahier guard, changes nothing; run it through a French VPN
endpoint. The resolve-only part (INAO product pages, `www2.inao.gouv.fr`) and
the register tier are not fenced. INAO's product page can also lag INAO's own
*Textes JO* index by months (Crémant de Bordeaux, Mâcon, Côte de
Nuits-Villages, L'Etoile on 2026-10-01: the index listed a 2026 arrêté the
page did not link, or the page was in PNO state with no cahier link at all),
so a drift check reads the index
(`www2.inao.gouv.fr/Textes-officiels/Textes-JO?textjo_type[keyword]=…`) and
pins the newer BO Agri URL in `manual_overrides.json` when the page lags.

The register attachment is the same document already in the build, not a
different vintage: for Bâtard-Montrachet (`PDO-FR-A0571`) and IGP Puy-de-Dôme
(`PGI-FR-A1211`) the extracted `lien_au_terroir` is byte-identical to the
in-build record. See the shadow report below for the corpus-wide picture.

### The join key — stage 01d

France is the one country sourced from INAO rather than eAmbrosia, so its
records carry **no `id_eambrosia`**. [scripts/01d_resolve_register.py](scripts/01d_resolve_register.py)
supplies the missing link by matching the SIQO appellation name against the
register's `protectedName`, and writes `raw/inao/register/resolved.json`
(id_appellation → GI binding) plus `raw/inao/register/unresolved.json` (the
curator queue, one `reason` per entry).

A wrong bind attaches another appellation's cahier, which is worse than a gap,
so [scripts/_lib/fr/register_match.py](scripts/_lib/fr/register_match.py)
refuses rather than guesses. Three guards:

- **Product-type partition.** The candidate pool is split by the register's
  `qualityProductType` (Wine / Spirit drink / Food), keyed off the SIQO
  `categorie` via `CATEGORIE_PRODUCT_TYPE`. *Calvados* is both a Wine PGI (the
  Normandy IGP wine) and a Spirit-drink PGI (the eau-de-vie); without the
  partition either could claim the other's cahier. A SIQO row carrying no
  `categorie` searches every partition instead and must come back with a
  single GI.
- **No fuzzy matching.** Keys are the exact normalised alias parts of both
  names — the shared `candidate_keys()` in
  [scripts/_lib/fr/naming.py](scripts/_lib/fr/naming.py) (splitting SIQO's
  `" ou "` / `" et "` / commas) plus a `/` split on the register side, which
  is how the register writes synonym lists (`Bourg / Côtes de Bourg /
  Bourgeais`). Exact matching alone would miss ~20 appellations; fuzzy
  matching would risk a wrong bind, so the alias fold does the work. A key
  hitting more than one GI resolves to nothing.
- **One-to-one.** Two appellations claiming the same file number means at
  least one bind is wrong, so both go back to the queue.

The residue is pinned in
[scripts/_lib/fr/register_overrides.json](scripts/_lib/fr/register_overrides.json)
(checked in — curator input a fresh checkout needs), keyed by
`id_appellation` → `{file_number, register_name, note}`. An empty
`file_number` records a verified absence and drops the appellation from the
queue. v1 needs two pins: *Calvados Domfontais* (SIQO spelling; the register
and the cahier both say *Domfrontais*) and *Marc d'Alsace Gewurztraminer*
(SIQO leaves `categorie` empty on the manifest row).

Result: **466 / 466 parents resolved, 0 unresolved** — 444 on the full name,
20 on an alias, 2 pinned. Sub-denominations are not resolved: they have no
register entry of their own and inherit the parent cahier exactly as they do
today.

### The fallback tier — stage 01

`RegisterTier` in [scripts/01_scrape_cahiers.py](scripts/01_scrape_cahiers.py)
runs only after BO Agri **and** the curator overrides have failed to produce a
PDF — all three miss paths in `_process_app` funnel through `_register_tier`.
Today that is 0 of 466 appellations, so a re-run is a no-op. Disable with
`--no-register`; `--register-delay` sets the inter-request pause.

Register attachments are cached by sha256 under `raw/inao/register/cahiers/`,
**deliberately outside `raw/inao/cahiers/`**: stage 02's
`build_global_segment_index` indexes every PDF in that directory and feeds each
record's `source.latest_known_pdf`, so dumping a few hundred register cahiers
there would silently rewrite unrelated records. Only a cahier that actually
wins a resolution is promoted into the cahiers directory.

Provenance is written **only for entries the register won**, so an appellation
still served by BO Agri keeps a byte-identical manifest entry: `source_kind:
"eambrosia-register"`, `register_file_number`, `register_attachment_uri`,
`register_attachment_name`, `register_protected_name`, `register_matched_via`.
Stage 02 passes the same keys into `record["source"]` under the same guard.
`fetched_at` comes from the register cache manifest, not from the clock, so a
cache hit does not churn the manifest.

Endpoint mechanics live in
[scripts/_lib/eambrosia_register.py](scripts/_lib/eambrosia_register.py) (see
the cross-country endpoint section for the gotchas: the internal `id` is not
derivable from `giIdentifier`, the detail path has no `/v1/`, the attachment
path does, and an explicit `Accept: application/pdf` trips the anti-bot gate).
`load_gi_rows()` caches the register's GI listing — `protectedName`, country,
product type, status — to `raw/eambrosia-register/gi-index.json` from the same
single ~4 MB POST that backs the id map.

### Shadow report

[scripts/audit_fr_register_shadow.py](scripts/audit_fr_register_shadow.py)
compares the register cahier against the in-build record **without writing
into the build**: it extracts both with the unchanged stage-02 parser in
memory and reports three columns per appellation — `build` (the record on
disk), `self` (re-extracting the build's own PDF now, as a determinism
control) and `register`. `lien_au_terroir` is the headline comparison, with
section / commune counts and the homologation date alongside so a *vintage*
difference is distinguishable from a *parse* difference. Output:
`raw/inao/register/shadow-report.{json,md}`.

    .venv/bin/python scripts/01d_resolve_register.py
    .venv/bin/python scripts/audit_fr_register_shadow.py

v1 sweep (2026-08-29, all 466 parents):

| step | count | share |
|---|---:|---:|
| resolved to a register file number | 464 | 99.6 % |
| register serves a cahier attachment | 361 | 77.5 % |
| register cahier extracts | 352 | 75.5 % |
| `lien_au_terroir` byte-identical to the build | 92 | 26 % of extracted |
| differs cosmetically (word-overlap ≥ 0.99) | 45 | |
| differs substantively (< 0.99) | 215 | |

The determinism control came back **356 / 356 byte-identical**, so every
difference below is a real difference between the two documents, not
extractor noise.

**The register is systematically the older vintage.** Of the 215
substantively-different records, the newer text is on the **BO Agri** side in
**199**, the register side in 4, the same year in 7, undated in 5 (max year
mentioned in each `lien`). The differences are real regulatory ones, not
typography: BO Agri's Anjou Villages cahier reads "43 communes du
Maine-et-Loire et 3 communes des Deux-Sèvres" where the register's reads "24"
and "2"; Anjou and Arbois carry 2022–2023 republications the register has not
picked up. That settles the open question in the brief — **the register must
stay a last tier and must not be promoted to a primary source.**

Three records where the register is nonetheless materially *richer* than the
build are queued in [CURATOR_TODO.md](CURATOR_TODO.md) as targeted re-source
candidates: Collioure (315 → 14,412 chars), Pouilly-Loché (255 → 8,261),
Franche-Comté (4,062 → 7,583). The first two are among the only six parents
whose build `lien` is under 1,000 chars — the register closes the tail of the
PNOCDC short-lien backlog.

Two things the shadow report exists to surface, both live findings:

- **Vintage.** The register attachment is not always the newest publication.
  Bâtard-Montrachet and IGP Puy-de-Dôme are byte-identical to the build, but
  Chablis's BO Agri PDF is a 2025 republication (with typo corrections —
  *au-dessus*, *Ces vallons*) that the register has not picked up. That is the
  argument for keeping the register a *last* tier rather than promoting it.
- **A pre-existing extractor defect.** For some GIs the register serves the
  whole *Journal officiel* issue (`joe_20110630_0060.pdf` for Pouilly-Fumé)
  instead of a standalone `CDC_*.pdf`. `extract_aire`'s department-header
  regex backtracks pathologically on that layout — minutes on a 2 KB section.
  The audit bounds it (`--extract-timeout`, default 20 s → verdict
  `register-extract-timeout`); the regex was fixed on 2026-10-04 with the
  corpus-wide diff that entry asked for (the "up to four lines before the
  colon" group now ends each line on its newline — see the stage-02
  section), and the Pouilly-Fumé reproducer runs in half a second.

Licence / attribution: the register is the European Commission's own
publication of the member state's product specification; the served PDF is the
INAO cahier des charges. Public-source rule satisfied. The map panel and the
wiki label a register-sourced cahier as such — `boagri_url` stays empty and
the attachment URL rides its own `register_attachment_url` field, so nothing
attributes an EU-register document to BO Agri.

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

## INAO parcellaire gaps (curator fills)

The INAO parcel layer is not complete. A commune of an appellation's aire
géographique (the aires-communes CSV; the cahier's section IV) can carry no
parcel row at all — for any AOC, its delimitation not digitised
(Vaison-la-Romaine, Saint-Marcellin-lès-Vaison, Saint-Romain-en-Viennois,
Mollans-sur-Ouvèze in the 2026-05-11 release) — or rows for other
appellations only (Visan, Sérignan-du-Comtat and Sorgues hold Côtes du
Rhône parcels and no Villages row). The dissolved `parcellaire` polygon then
has a hole where the appellation's best-known villages are: a visitor
flagged the Côtes du Rhône Villages boundary at z8.8 on 2026-09-29, with
Vaison-la-Romaine on bare basemap at the eastern edge of the footprint.

The layer does not say which of the two it means, and for a regional
appellation a vineless aire commune is genuinely not on the wine map
(Bourgogne: 45 of 315; the Alsace grand cru CSV rows list all 47 wine
communes for every climat; the Corton and Givry climat rows list three
communes for a one-commune cru), so **nothing is filled automatically and no
corpus-wide card line is rendered**. Two mechanisms instead
([scripts/_lib/parcellaire_gaps.py](scripts/_lib/parcellaire_gaps.py)):

- [scripts/audit_parcellaire_gaps.py](scripts/audit_parcellaire_gaps.py)
  lists, per parcellaire record (parents by appellation name, DGCs by
  `id_denomination_geo`), the aire communes without a parcel row, each
  classed `not-digitised` (no row for any AOC) / `other-aoc` (rows for other
  appellations only), marked `dgc-named` when a DGC aire of the same
  appellation lists it, with the pre-merger CSV codes IGN no longer carries
  reported apart (Coteaux-sur-Loire, Valloire-sur-Cisse — not gaps). The
  coverage index is the shapefile's attribute table (patched like the
  polygons), cached under `raw/cache/parcellaire-coverage/<release>.json`.
  167 records carried a gap on the first run; the list is a curator queue,
  not a defect count.
- [scripts/_lib/parcellaire_gap_fills.json](scripts/_lib/parcellaire_gap_fills.json)
  (checked in) pins the communes a curator verified against the cahier:
  `communes` {INSEE: name}, `donors` (appellation slugs tried in order),
  `reason`, `source`, `verified`. Stage 04 fills each pinned commune with a
  donor's parcels clipped to the commune **only where the coverage index
  says the donor has a row there** — a geometric intersection alone cuts a
  boundary sliver from the neighbouring commune's parcels and calls it the
  vineyard (Vaison against Villedieu's Côtes du Rhône parcels) — else with
  the whole commune polygon (IGN AdminExpress, as `aires-csv` records draw).
  A donor's parcels are a superset of the missing delimitation (the Villages
  parcels lie inside the Côtes du Rhône ones) but the vineyard's shape
  rather than the commune's. The fill runs after resolution and before the
  outlier clip and the footprint, so the footprint and the villages layer
  carry it; `geom_source` stays `parcellaire` / `parcellaire-dgc` (the
  footprint, the audits and the paint key on it). The card discloses it —
  `geom_parcel_fill` (which communes, drawn whole or from which donor) and
  `geom_parcel_gaps` (a pinned record's gaps still open) in the panel
  payload, one line per kind (`geom_parcel_fill_commune` /
  `geom_parcel_fill_donor` / `geom_parcel_gaps` labels; `_parcel_fill_line`
  in content_block.py, `parcelFillLine` in app.js). A pinned commune that
  carries a parcel row again is **STALE**: nothing is filled for it, stage 04
  says so on its `[geo] parcellaire gap fill` line, and the audit's
  `--strict` fails — re-verify the pin against the new release.
  `tests/test_parcellaire_gap_fills.py` checks the table and that every
  pinned commune is in the record's aire.

v1 pins (2026-09-29, the Rhône cluster of the flag): Côtes du Rhône
Villages (7 communes: 426 → 538 km²), Côtes du Rhône (5, whole: 1,323 →
1,377 km²), the Vaison-la-Romaine DGC (3: 2.2 → 35 km²), Massif d'Uchaux
(2), Puyméras (2), Sainte-Cécile (1). Visan's own DGC stays `aires-csv-dgc`
(the whole commune, already disclosed). Candidates the audit surfaces for a
later pass are in [CURATOR_TODO.md](CURATOR_TODO.md).

### Rows carried forward from an earlier release

A release can also drop rows that nothing retires. The 2026-09-28 release
(adopted 2026-10-04: 11,773 → 11,751 rows, 357 → 356 appellations) has no
row for AOC Saint-Sardos — 23 communes, 36.4 km² in the 2026-05-11 release —
while no act in the JORF, INAO's Textes JO index or eAmbrosia touches the
appellation, and no row for the DGC Languedoc Montpeyroux (id_denom 1313),
promoted to AOC Montpeyroux before INAO shipped the new appellation's
parcels. The same rule as for the catalogue applies: a record is never
redrawn from a commune union because an export stopped listing it. The
checked-in [scripts/_lib/parcellaire_carry_forward.json](scripts/_lib/parcellaire_carry_forward.json)
names each case — `match` (`{"app": …}` for a whole appellation,
`{"id_denom": n}` for one denomination), the `release` the rows come from,
the extract `file`, the row count, the public state that makes the absence
a data state rather than a withdrawal, a verification date — and the rows
themselves are a checked-in extract under
`scripts/_lib/parcellaire_carry_forward/` (gzipped GeoJSON in EPSG:2154,
attributes and coordinates exactly as INAO published them: a 1 cm rounding
already made one Saint-Sardos polygon invalid), because data.gouv.fr serves
the latest resource only and the earlier zip can no longer be fetched.
`parcellaire.carry_forward_frames` appends them to the current release's
table in `build_aoc_polygons` (geometry) and `parcellaire_gaps.load_coverage`
(attributes) alike, so the polygon, the gap audit and the gap fills agree;
an entry whose rows are back in the current release is **STALE** — nothing
is appended, stage 04 and `audit_parcellaire_gaps.py` say so, `--strict`
fails, and `tests/test_parcellaire_carry_forward.py` checks that the current
release still lacks the rows, that each extract is exactly its entry's rows
and, with the earlier release on disk, a faithful copy of it. The card says
where the polygon comes from (`geom_parcel_carry` in the panel payload —
"Parcel delimitation from the INAO release of 2026-05-11; the release of
2026-09-28 carries no rows for this denomination"; `_parcel_fill_line` /
`parcelFillLine`). `wiki/map-data/aoc-parcels.meta.json` records the
release and the entries the two parcel caches were built from, so a cache
built from another release or before an entry was added is rebuilt rather
than silently served. `scripts/extract_parcellaire_carry_forward.py
--release 2026-05-11 --app "Saint-Sardos"` (or `--id-denom 1313`) writes an
extract from a release on disk. The same release moved Côtes de Provence la
Londe (id_denom 1839) from `aires-csv-dgc` to `parcellaire-dgc` with a null
`insee` on its four rows (`insee2011` filled): the coverage index reads a
code only from a string field, so a float NaN never becomes a commune
"nan", and a field carrying two codes ("49078,49115", a merged commune)
counts both.

The 2026-10-19 release (adopted 2026-10-24: 11,751 → 11,764 rows) brought
AOC Montpeyroux its own parcels (id_denom 2951: Arboras, Lagamas,
Montpeyroux, Saint-Jean-de-Fos, 5.9 km²), so the record left its
four-commune union for `parcellaire`; both carry-forward entries stay —
Saint-Sardos still has no row, and the DGC Languedoc Montpeyroux's own two
rows are still absent (the successor's parcels are another denomination,
so they do not make the entry STALE). It also re-digitised Ladoix with
null-`insee` rows, three of which duplicate a climat's existing row (the
union does not move; CURATOR_TODO). The newest
`<date>_delim-parcellaire-aoc-shp.shp` under `raw/inao/parcellaire/` is the
release built (`resolve_shapefile`).

## The FR corpus follows INAO's catalogue, not the export's vintage

The SIQO referentiel on data.gouv.fr is republished about once a year
(2025-12-31 was still the live file on 2026-10-01) while INAO recognises,
re-labels and retires products all year. Two rules, both enforced in code:

- **A GI the export predates is added by a supplement row.** Every FR reader
  of the referentiel — stage 01, 01d, 02, the coverage audit — reads it
  through `siqo.siqo_rows()` ([scripts/_lib/fr/siqo.py](scripts/_lib/fr/siqo.py)),
  which appends the rows of the checked-in
  [scripts/_lib/fr/siqo_supplements.json](scripts/_lib/fr/siqo_supplements.json)
  in the CSV's own 22 columns, so downstream nothing knows they are
  supplements. A row is `added` (a recognised GI with no export row yet —
  Montpeyroux, arrêté du 11 août 2026, INAO product 23354; its
  `id_appellation` / `id_denomination_geo` are the provisional `p<idproduit>`
  until the export publishes INAO's numbers, and the real `idproduit` lets
  stage 01 walk the real product page) or `retained` (a row the export
  dropped that the corpus keeps; skipped again when the export carries the
  `idproduit` once more). Each row cites the public act and a verification
  date; a row colliding with a CSV row of another appellation raises.
  A provisional id is also accepted by the register-override table
  (`register_overrides.json`, `file_number: ""` = verified absence until
  the Commission publishes the application) and by `_SLUG_BUCKET` in
  `fr_wine_region.py` when the aires CSV has no row to place the record by.
- **A record is never removed because an export stopped listing it.** A
  full stage-02 run compares the previous `_index.json` with the keys this
  run can emit (`dropped_denominations`) *before* it deletes anything and
  refuses (exit 2, every record listed) when a previously emitted
  denomination would vanish; `--allow-drop` is the explicit decision. The
  denomination stays by a `retained` supplement row, and what became of it
  is said by a registry with a cited act: `cancelled_gis.json` below for a
  cancelled registration, `promoted_gis.json` for a name that moved up a
  tier. Visible, dated, linked — never silently gone.
- **A record carries the GI's registered name when the export's catalogue
  label is shorter.** `name_overrides` in the same `siqo_supplements.json`
  (id_appellation → `appellation`, `_reason`, `_source`, `_verified`) renames
  the row — and the parent denomination row with it — inside `siqo_rows()`,
  so stage 01, 01d, 02 and the audits agree. v1 pin: 1091, whose
  `appellation` column reads "Marc d'Alsace" while its own `produit` column,
  the INAO product page, the EU register (PGI-FR-01836) and the cahier
  ("enregistrée sous la dénomination « Marc d'Alsace Gewurztraminer » au
  registre des Indications Géographiques") say *Marc d'Alsace
  Gewurztraminer* — the record, slug and URL every pin and the live site
  key on. The 2026-10-01 manifest refresh had re-read the column and
  silently renamed the record `marc-d-alsace`; stage 02 now takes the name
  from the referentiel, not the manifest. A pin whose row already reads the
  pinned name (or has no row) is STALE: `siqo_rows()` says so on stderr and
  `tests/test_fr_siqo_supplements.py` fails — drop it.

## Promoted denominations stay in the corpus, marked

A DGC that becomes an appellation of its own is not cancelled: the name is
still on older labels and in teaching material, and the record should say
where it went. [scripts/_lib/promoted_gis.json](scripts/_lib/promoted_gis.json)
is keyed by the former record's slug — `name`, `country`, `promoted_on` (the
national act's date), `successor_slug` + `successor_name` (the new
appellation's record, which must exist — via the export or a supplement
row), `national_act` + `national_url` (Légifrance ELI / INAO text page),
optional `cahier_url`. Stage 04 attaches it as `promoted` (a startup field);
the panel renders a green *Promoted* badge after the classification and a
dated line under the header linking the successor's panel, the act and the
new cahier (`promotedBadge` / `promotedLine` in app.js,
`promoted_badge_html` / `promoted_line_html` in content_block.py; the
sidebar tree and search suggestions carry the compact badge).
`tests/test_promoted_gis.py` checks the table and that no slug is in both
registries. v1 entry: Languedoc Montpeyroux → Montpeyroux (arrêté du 11 août
2026; the Languedoc cahier of the same day lists nine DGCs without it).

## Cancelled GIs stay in the corpus, marked

A GI whose registration the Commission cancels is **not** removed from the
map: bottles, labels and older teaching material still carry the name, so
the record stays findable and says plainly that it is cancelled. The
checked-in registry
[scripts/_lib/cancelled_gis.json](scripts/_lib/cancelled_gis.json) is keyed
by slug — `name`, `country`, `file_number`, `cancelled_on` (the date the
cancellation regulation applies), `regulation` + `regulation_url` (the EU
implementing regulation, cited by title and ELI), optional `national_act` +
`national_url` (the member-state act / regulator page), optional
`successor_slug` + `successor_name`. Stage 04 attaches the entry to the
record as `cancelled` (a startup field, so the sidebar sees it before the
panel payload loads); the map panel renders a *Cancelled* badge after the
classification and a dated, source-linked line under the header
(`cancelledBadge` / `cancelledLine` in app.js, `cancelled_badge_html` /
`cancelled_line_html` in content_block.py for the SSR card), the sidebar
tree and the search suggestions carry the compact badge. Wording is the
EU register's own status word (*cancelled* / *annulée* / *cancelada* /
*geannuleerd*), never "deprecated". This is the opposite of the AT
`CANCELLED_PDOS` / IT `CANCELLED_GIS` stage-00 registries, which drop a GI
from the index outright (used for the names that were consolidated into
another GI, e.g. the 7 Abruzzo IGTs). Detect new cancellations with the
register-drift check ([docs/register-drift-2026-09-20.md](docs/register-drift-2026-09-20.md):
live eAmbrosia `removedFlag` + the regulation title on EUR-Lex); every
entry must cite the public act. v1 entries: Cité de Carcassonne, Coteaux de
Narbonne (FR IGPs, Reg. 2025/2538 / 2025/2536), Salemi (IT IGP, Reg.
2026/1043), Ambt Delden (NL PDO, Reg. 2026/1068). Adding earlier
cancellations is a curator task.

## An appellation spanning several regions is listed under each

The region level of the listing rule of 2026-10-25 (Maasvallei under BE and
NL — `country_aliases`; Vully and Zürichsee under each canton — `co_parents`):
a record whose area spans several regions of its country's sidebar hierarchy
is listed under every one of them (`region_aliases`, a sparse startup field),
stays one record (one slug, one polygon), keeps its primary `region` for the
title, the description, JSON-LD and `seo_display_name`, and the card's meta
line names every region ("Lombardia, Veneto"), with one "All appellations in
…" link each. [scripts/_lib/region_aliases.py](scripts/_lib/region_aliases.py)
derives the list in `emit_html` from three sources:

- the curated [scripts/_lib/region_aliases.json](scripts/_lib/region_aliases.json):
  per slug the regions, a verbatim quote of the record's own area text
  (`evidence`: file, field, quote — `tests/test_region_aliases.py` checks each
  against the extracted record, whitespace folded) and a reason. IT (Garda,
  Lugana, San Martino della Battaglia, Valdadige, Terradeiforti, Delle
  Venezie, Trevenezie, Prosecco, Vigneti delle Dolomiti, Colli di Luni,
  Orvieto, Lison, Lison-Pramaggiore, Alto Livenza, Vallagarina — found by the
  provinces each area text names), ES (Cava, whose record has no region of
  its own and now sits in its seven comunidades only; Rioja with Castilla y
  León for El Ternero; Jumilla; Ribera del Queiles), AT (Weinland, Bergland,
  filed under "Österreich"), BG (the two PGIs, by the oblasts their obshtini
  lists name), CY (Pitsilia, whose villages straddle two districts). An entry
  with `regions: []` suppresses the derivations (Bayerischer
  Bodensee-Landwein, whose member table draws the whole Baden Anbaugebiet).
- an umbrella PGI drawn as the union of member PDOs (`region-pdo-union`):
  the regions of its members, from the same `*_PGI_MEMBER_PDOS` table that
  draws its polygon (DE Landweine under their Anbaugebiete, HU Dunántúli,
  Zemplén, SK Slovenská, MT Maltese Islands).
- FR: the wine-region buckets whose own AOCs share communes with the
  record's aire in the INAO aires-communes CSV — at least 5 communes, and 3 %
  of the record's aire or 25 % of the bucket's; an AOC holding two other
  AOCs (the Bourgogne regionals, Côtes du Rhône, Champagne) is left out of
  its bucket's communes, and ARMAGNAC (the brandy's and Floc's bucket over
  the same Gascon ground as SUD-OUEST) is neither source nor target. First
  build: Atlantique (Cognac, Sud-Ouest), Méditerranée (Provence, Corse), Pays
  d'Oc and Terres du Midi (Roussillon, Rhône), the Gard IGPs and Cévennes
  (Rhône — the Duché d'Uzès, Costières de Nîmes and Lirac communes),
  Languedoc (Roussillon), the three Rivesaltes AOCs (Languedoc — Fitou's
  communes), the Bourgogne regionals (Beaujolais — the crus' communes),
  Beaujolais (Bourgogne — Saint-Véran's), Comtés Rhodaniens (Savoie,
  Beaujolais).

The sidebar pushes the record into each alias region's group and counts it
once per country; its sub-denominations stay in their own region (a Bourgogne
DGC is no Beaujolais record, Rioja Alta no Basque one), so a parent's row in
an alias group carries no children there; the
query core's `filter({region})` and `facets()` read every region
(`regionsOf`), so the MCP server answers the same after its next deploy.
[scripts/sweep_region_aliases.py](scripts/sweep_region_aliases.py) is the
detector: a region's footprint is the union of its own PDO polygons
(umbrellas left out, all its parents when it has none), a record spans it
when ≥ 20 km² of it lies there and that is 10 % of the record or 25 % of the
footprint; each candidate is ACCEPTED (the build lists it), REJECTED (the
table's `rejected` section: a polygon overlap — Bétard in DE / HU / SI / BG —
or a neighbour's filing, each with its reason) or NEW, and a listed region
the geometry no longer reaches is STALE (Prosecco's and Delle Venezie's
polygons miss their Friuli and Trentino parts — CURATOR_TODO). Two filings
the sweep exposed were wrong, not multi-region, and were fixed at the
source: Debrői hárslevelű (Heves county, the Eger district) and Monor (a
Kunság municipality) were filed under Tokaj and Felső-Magyarország;
Nizza, Garda Colli Mantovani and Terre Siciliane had no regione and fell
back to "Italia" (`regione_by_file_number.json`).

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
MB of RAM), flags every detached part — parts no more than 25 km apart
form one cluster, transitively; the main body is the cluster holding the
most area, and a part outside it is an outlier when its *cluster* holds
< 20 % of the total (a larger detached cluster is a second lobe, however
many parcels it is drawn in; since 2026-09-24 — the earlier area-rank body
absorbed large detached parts and never tested them) — reports which
other appellation each part sits inside (the triage signal — a part inside an unrelated DOC is plainly
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
re-verified. The audit re-derives every override against the source on
each run — the Bétard polygon for a `figshare-pdo` clip, and for a clip
whose `geom_source` is `gisco-nuts-region` (a Greek PGI drawn from NUTS
units: Gavdos off Κρήτη, the Strofades off Ζάκυνθος) the union of the
NUTS polygons stage 04 wrote on the record as `geom_nuts_ids` (panel
payload `wiki/data/d/en/<slug>.json`; a build that predates the field
reports the clip STALE until rebuilt) — so a working clip stays visible
as `CONFIRMED` and is never silently hidden. A whitelist entry cites the
same evidence: Skyros stays for ΠΓΕ Εύβοια ("Περιφερειακής Ενότητας
Ευβοίας", of which Skyros is part), Samothrace for ΠΓΕ Θράκη and ΠΓΕ
Έβρος. Ρετσίνα Ευβοίας and Ρετσίνα Χαλκίδας are drawn from LAU unions
that never held Skyros, and Ρετσίνα Καρύστου's union (the former
επαρχία Καρυστίας, which held Skyros) chains the island to the Euboean
body under the 25 km rule — none of the three needs an override. The
2026-09-25 review cleared the 57 unreviewed findings the same way, each
entry citing what makes the part legitimate: for a `parcellaire` record
the INAO delimitation *is* the source, so a lobe is whitelisted when the
cahier's aire names the département (the Yonne lobe of the six Bourgogne
regionals, the northern Rhône of Côtes du Rhône, Ripaille, the
Wissembourg outpost, Sierck, Villars-sur-Var, Bossay-sur-Claise); for an
`aires-csv` record the CSV row is quoted (the Pays de Bray communes of
Calvados and Pommeau, Les Fourgs for Marc du Jura, La Roche-Chalais for
the Cognac Bois ordinaires, the Eure-et-Loir communes of IGP
Île-de-France); NUTS-drawn Greek PGIs follow the ΥΠΑΑΤ wording —
"νομού Χανίων" (the prefecture) keeps Gavdos for Χανιά where "νήσου
Κρήτης" clips it for Κρήτη — and a national spec settles a Bétard part
(Barabás is a Bükk település per the termékleírás; Kojetice is in the
Znojemská list of Vyhláška 254/2010). Four findings were defects, fixed
upstream instead: Calvados Domfrontais drawn as the whole Calvados aire
(the aires-CSV name lookup, see below), Cinco Villas' "Los Corrales"
bound to Sevilla, Valle Belice and Costa Toscana collapsed to whole
provinces (the IT comune parser), and Πλαγιές Αίνου's mainland parts
turned out to be the Echinades islets of Δ.Κ. Αγίας Ευφημίας — GISCO's
own geometry, whitelisted. Re-run stages 04 → audit after editing the
override file.

**INAO aires-communes binding** ([scripts/_lib/aires.py](scripts/_lib/aires.py)):
a commune-union record finds its CSV rows by normalised name — exact,
then *near-exact* (rapidfuzz ratio ≥ 95 against names of similar
length, one candidate only), then — for a SIQO "X ou Y" register name —
the exact row of one of its aliases ("Moulis ou Moulis-en-Médoc" →
"Moulis"; 2026-09-26, 22 Burgundy and Layon AOCs bound their row for the
first time), then the substring fallback that serves "Champagne grand cru"
→ "Champagne", in which a CSV name shorter than six characters binds only
as a whole word of the record name ("anjou" in "Rosé d'Anjou", never
"gard" in "Euskal Sagardoa", which drew the Basque cider over the Gard),
and in which the other direction — the record name inside a *longer* CSV
label — binds only when the record (or each of its own " ou " parts) is an
alias part of that label ("Pouilly-sur-Loire" and "Pouilly-Fumé ou Blanc
Fumé de Pouilly" in the combined CSV label "Pouilly-Fumé ou Blanc Fumé de
Pouilly et Pouilly-sur-Loire"; `_CSV_ALIAS_KEYS`, filled by `load_aires`),
never when it is a trailing word of another appellation — the new AOC
"Montpeyroux" took the DGC aire "Languedoc Montpeyroux" (2 communes against
the cahier's 4) until 2026-10-04. The same sweep bound IGP Côtes du Lot to
its IGP CSV aire "Lot" (340 communes of the Lot) where the cahier-text
parser had drawn only the 6 named communes outside the département.
The same ladder (`_resolve_key`) serves `lookup_departements`, the
département profile behind the FR wine region. The near-exact step exists because
SIQO spells "Calvados Domfontais" where the CSV, the cahier and the EU
register say "Domfrontais": the substring rule handed that record the
1,573 communes of "Calvados" (2026-09-25) for a 112-commune appellation.
`tests/test_aires_lookup.py` pins the order.

**INAO aires-communes supplements** ([scripts/_lib/aires_supplements.json](scripts/_lib/aires_supplements.json),
checked in): the CSV rows of an aire can be a decade older than the cahier
in force, and nothing in the CSV says so. A visitor flagged the IGP Cévennes
boundary on 2026-09-29 (fr, z7.2): its 236 rows date from 14 September 2012
and are Gard only, while the cahier published in the BO on 8 August 2024
lists 40 Lozère communes beside them ("Le vignoble des Cévennes est situé
dans les départements du Gard et de la Lozère") — the map drew a Cévennes
without the Cévennes lozériennes. A pin per record (`aire` + `ida` — the CSV
label and bucket — `communes` {INSEE: name} the homologated cahier lists
and the CSV lacks, `not_drawn` for a commune included only in part, `reason`,
`source`, `verified`) is folded into the index by `aires.apply_supplements`
inside `load_aires()`, so stage 04, the parcellaire-gap audit and every
other consumer read the same aire; the record stays `aires-csv` and the
card's commune-union line counts the added communes. Only a cahier
published in the Bulletin officiel is pinned, never a PNOCDC draft (Thézac-
Perricard's three Lot communes wait for that reason). A pinned commune the
CSV carries again is **STALE**: it is not added twice, stage 04 says so on
its `[geo] aires supplement` line and `tests/test_aires_supplements.py`
fails (it also checks that every pinned name is a current IGN commune the
cahier's zone text names). Nothing is parsed automatically — a cahier lists
the vinification zone, exclusions and the proximity zone in the same prose
(Alpilles names 29 communes for vinification and 19 for the grapes). v1
pins: Cévennes (+39 Lozère communes, 3,482 → 4,952 km²; Massegros Causses
Gorges is in the aire for the commune déléguée Les Vignes only, and was not
drawn — Le Rozier and Saint-Pierre-des-Tripiers a detached lobe — until the
former-commune layer of 2026-11-13 gave Les Vignes an outline: pinned under
its own code 48195, 4,981 km², one polygon), Côtes de Thau (+9 communes around the Étang de Thau, cahier of 24
August 2023 against rows of 2015; 181 → 422 km²), Maures (+3, cahier of 11
December 2025; 2,193 → 2,313 km²). A CSV aire can also be **cut short**:
the IG Cassis de Saintonge carries 36 rows — the head of the Charente list,
Angeduc to Guizengeard — where its cahier (BO Agri, 22 January 2015) lists
some four hundred communes of the Charente and the Charente-Maritime; the
polygon-versus-text audit found it on 2026-11-13 and the pin adds the 363
names that are current communes of their département (`names_not_current`
keeps the 24 that merged or were renamed since, not drawn — the fate of any
pre-merger code). The scoped audit run of the same day (the 273 drink
polygons) found three more aires whose rows lack communes a later cahier
lists whole — Calvados Pays d'Auge +6, Pommeau de Bretagne +9, Pommeau de
Normandie +11 (Cormes, included in part, `not_drawn`) — pinned. Four more
had rows dated later than the cahier in the build; Boris's ruling of the same
day settles the class — **the cahier is the delimitation and wins over
INAO's data publication; first check that the build holds the newest
published cahier** (see "The cahier wins" below).
The row-count sweep (CSV rows against the cahier's own list, every French
parent) found no other aire cut short; among the wines Alpilles
and Thézac-Perricard are the known cases, Bellet's list is the lieux-dits of
Nice, and the cancelled IGP Coteaux de Narbonne has 5 rows for the 11
communes its cahier names (CURATOR_TODO).
Candidates for a later pass are in [CURATOR_TODO.md](CURATOR_TODO.md).

**The cahier wins (2026-11-13).** The check for a newer cahier found the
build behind, not INAO's rows: the EU register's `productSpecificationLink`,
through which 30 French spirits had been bound the day before, points at the
cahiers of 2014–2015, and BO Agri's own title search
(`https://info.agriculture.gouv.fr/boagri/recherche/resultat_recherche_rapide?titre=<name>`
— it answers from outside France when INAO's product site does not; results
in `<ul id="liste-resultat">`: the document type, the BO date, the
homologation act) lists a newer one for 28 of the 59 French drink parents —
the arrêtés of 10 September 2021 (the five overseas rums), 20 June 2022 (the
three Champagne spirits), 15 July 2024 (Cassis de Saintonge, Marc de Savoie),
27 March, 10 April, 1 July and 1 September 2025 (Marc d'Auvergne, Fine
Bordeaux, Cassis de Bourgogne, the Alsace fruit spirits), 9 December 2025
(the Rhône, Languedoc, Provence and Bugey spirits), 17 January 2026 (the Pays
d'Auge cider, bound to a PNO draft until then), 4 February 2026 (Cassis de
Dijon) and 10 June 2026 (Cognac) — and a cahier for the three stubs (Absinthe
de Pontarlier 2013, Génépi des Alpes 2014, Cassis de Dijon). Each is pinned in
`raw/inao/cahiers/manual_overrides.json` with its act, its header read; stage
01's override path keeps the product page of an earlier run and drops the
text trail of the cahier it replaces (`_CATALOGUE_META_KEYS`). Calvados has
none newer than the arrêté of 17 December 2021.

With the right cahiers in the build,
[scripts/audit_aires_vs_cahier.py](scripts/audit_aires_vs_cahier.py) reads
every French parent that binds an aire of the CSV and whose cahier lists
communes: the communes the cahier names that the rows lack, each classed by
its place in the zone text — `whole` (an item of a commune list under its
département; a commune of today the cahier names by every one of its former
communes), `partial` (a qualifier in brackets, an "en partie" sub-list, a
name inside an exclusion clause — Armagnac lists Losse, Mont-de-Marsan,
Roquefort, Saint-Martin-d'Oney and Houeillès and excludes them from the
vineyard and the still in the next sentence), `unclear` (a canton heading,
another name: the cahier's « Les Salles » is Les Salles-de-Castillon, not
Salles) — and, report only, the rows whose commune the zone text does not
name, with the **neighbouring codes**: INAO's file carries Gignac (84048)
where the cahier lists Gigondas (84049), Saint-Alban-de-Roche (38352) for
Saint-Alban-du-Rhône, Les Fourgs (25254) for Fourg (25253: the detached
Haut-Doubs lobe of Marc du Jura, whitelisted as "the CSV's own statement" on
2026-09-25, was a wrong row), La Cassaigne (11072) for Cassaignes,
Saint-Christophe-sur-Avre for Saint-Christophe-sur-Condé, Pionsat (63281)
for Pignols (63280: Marc d'Auvergne's lobe 27 km off, whitelisted on
2026-11-12, likewise). A detached part of a commune-union record is a
question for the cahier before it is a whitelist entry. The pin table
gained what the rule needs: `remove` (a row the cahier does not list —
`apply_supplements` takes it out; a row to remove that the CSV no longer
carries is STALE), a **former commune pinned under its own code** (drawn by
its own outline, below), `not_drawn` as a decision (a commune named and not
part of the production area), `whole_departements` (Génépi des Alpes: the
cahier names six départements whole and the rows carry no commune of Savoie —
273 communes pinned; the Haute-Savoie lobe is attached again), and a pin
binds the aire the record resolves to, per IDA (INAO cuts a long label
short; « Calvados » is the spirit's aire and the wine IGP's). 21 drink
records are pinned from their cahier (898 communes added, 10 rows removed,
28 named and not drawn); `--drinks --strict` is a release gate
(`aires-vs-cahier`), `--bare --emit-pins` rebuilds a pin from scratch. The
same audit over the wines lists 28 NEW, 9 UNCLEAR and 4 UNREAD records — a
curator queue (most wines are drawn from parcels, so their polygon does not
move): CURATOR_TODO. Fine-Faugères shows the rule at its smallest: seven
communes in the cahier, seven rows, Pézènes-les-Mines where the cahier has
Autignac.

**The audit says what it could not read.** Its first cut compared only the
records whose cahier list stage 02 had read, and skipped the others without
a word — so "OK 12, PINNED 16 of 28" hid six drink records whose list the
reader had lost: the cider spirits of Bretagne and the Maine and the two
Bugey spirits print one "Département de X" heading per département with no
colon (0 of 366 and 0 of 141 communes read), and Marc d'Auvergne's PDF lost
its non-breaking hyphens (88 communes under « Puy-deDôme », a département no
table knew). The polygon-versus-text audit caught Marc d'Auvergne (three
communes "missing") and the trail led to the rest. Since then: stage 02
reads the bare heading and keys a département as the table spells it (see
the stage-02 list rules); `geom_chain.dept_code_for` finds a département
whatever its hyphens and spaces, for every consumer of a cahier list; a
record whose list resolves no name is bucketed **UNREAD** and fails
`--strict` from five names up; `written_names` lets the audit find a commune
under the name its cahier writes (`commune_name_pins.json`: Marc d'Auvergne's
« Saint-Maurice-ès-Allier » is Saint-Maurice, 63378). What it found: INAO's
rows of **Eau-de-vie de cidre du Maine are cut short** like Cassis de
Saintonge's — 62 rows, to Épineux-le-Seguin, for the 141 communes of the
décret of 13 February 2015 (+71 pinned: the polygon was half the aire);
Eau-de-vie de cidre de Bretagne +19 (Saint-Grégoire, named only in the
exception for apple growing, not drawn); Marc d'Auvergne +Champeix,
+Pignols, +Saint-Maurice and −Pionsat (63281, the row beside Pignols'
63280); Marc du Bugey +Serrières-de-Briord. The polygon-versus-text audit
reads a pin's `not_drawn` communes as named in part, so Pommeau de
Normandie's fifteen « Communes incluses en partie » are a decided
difference, not a suspect one.

## Former French communes (pre-merger codes in INAO's rows)

INAO's aires-communes rows keep the commune code of the day each row was
written. A commune merged since is not in IGN's commune layer, and until
2026-11-13 its code was simply skipped — the "vintage drift" of the coverage
log. Counting skipped codes overstates the loss (24 of the 141 French parents
drawn from the CSV skipped 10 % of their codes or more): INAO usually writes
the commune of today beside its former communes, and the ground was lost only
where the rows carry the former communes alone — with the layer,
Eau-de-vie de cidre du Maine gained 23 % of area, Cidre Cotentin 8 %,
Pommeau du Maine 7 %, Domfront 6 %, Calvados 3 % (its pin of 20 communes
included), and 23 wine records 1.4 % or less. Boris's "ok"
of the same day settled it, with a rule that never draws ground the
delimitation did not hold ([scripts/_lib/fr/former_communes.py](scripts/_lib/fr/former_communes.py),
`union_from_insee(codes, insee_idx, former)` in geom_chain.py). Over every
aire of the two CSVs, 31,845 row codes are not in the commune layer:

- **its own outline** (21,754) — the merger kept the former commune as a
  commune déléguée or associée and geo.api.gouv.fr
  (`/communes_associees_deleguees`, IGN AdminExpress, Licence Ouverte 2.0)
  still serves its outline under its old code, or under the code a change of
  département gave it on the way (Le Fresne-sur-Loire 44060 → 49382, Freigné
  49144 → 44225): drawn exactly. 1,999 outlines;
- **its commune of today is in the aire** (9,700) — INSEE's movements table
  (`v_mvt_commune_2026.csv`, "Code officiel géographique au 1er janvier
  2026", https://www.insee.fr/fr/information/8740222) gives the commune each
  code ended in; where the aire's rows carry that commune it is drawn whole
  already and the former commune lies inside it: nothing to add. A commune
  **suppressed and shared out** (event 30: Creusy, 1965, between Chevilly and
  Sougy) is covered when the rows carry every commune that took a part;
- **a new code for the same ground** — a commune of today whose every former
  commune is in the rows (a change of code, MOD 41 / 50): drawn whole. No row
  of today's CSVs falls here (the 1967 cases are the next class); the rule
  stands for a commune that changes code after the cahiers. A merger's
  commune always counts among its own former communes (INSEE gives it a row
  of its own in all but one of 2,081 mergers), so a former commune fused into
  a commune the aire does not list never draws that commune;
- **left its département before the cahiers** (156, `Resolution.elsewhere`) —
  INAO's commune table still holds the code a commune lost when it passed to
  another département: Chassieu, Meyzieu and 22 more under the `38…` codes of
  1967 (the Rhône since), six communes of the Ain likewise, Frettes
  (Haute-Marne until 1974, a part of Champlitte in Haute-Saône since). The
  rows of IGP Isère, IGP Coteaux de l'Ain, IGP Haute-Marne and Génépi des
  Alpes carry them, and each cahier says "le département de …": **the cahier
  wins**, the code is neither drawn nor named. Two tests, both needed: the
  date (`OLDEST_CAHIER`, 2009-01-01: no cahier in force is older; a commune
  that crossed a border after it — Pont-Farcy, 2018 — is resolved like any
  other) and the aire itself — the class holds only where the rows carry no
  commune of today in the département the ground went to. Antorpe left the
  Jura for the Doubs in 1974 and IGP Franche-Comté spans both, so its code
  is resolved like any other (107 row codes of that kind over the two CSVs).
  The first build of the day drew the 24 Rhône communes for IGP Isère and
  Frettes for IGP Haute-Marne; the overlap audit caught the second (a new
  17 km² sliver against IGP Franche-Comté);
- **the rest** (235: fused without trace into a commune outside the aire) has
  no outline in any public layer: not drawn, and named on the card —
  `geom_units_former_undrawn` in the panel payload, "Former commune(s) of the
  area, since merged into a commune outside it and with no outline of their
  own, not drawn: …" (both renderers' unit lines).

INAO's table also keeps communes INSEE calls "périmées" (the IGP file's
`Actual` column: 1 commune, 2 associée, 3 périmée, 4 old code after a change
of département, 6 déléguée). A Corsican commune merged before 1976 stands in
INSEE's table under its `20…` code and in INAO's rows under the `2A…` /
`2B…` code it never bore: read through the `20…` one (the split of 1976 is no
change of département). One that ceased **before 1943**, where INSEE's table
begins, is pinned to the commune that took it in
[scripts/_lib/fr/former_commune_pins.json](scripts/_lib/fr/former_commune_pins.json)
(Lompnes and « Hauteville-Lompnés » → 01185, Palalda and Amélie-les-Bains →
66003; each pin quotes its source). Unpinned, such a code prints as a bare
number on the card.

Stage 00 fetches both files (`raw/ign/communes-associees-deleguees.geojson`,
`raw/insee/v_mvt_commune.csv`, sha in `raw/manifest.json`); with either
missing the module resolves nothing and every record draws what it drew
before. The INSEE index stage 04 hands the parcel-gap logic and the village
narrowing stays the communes of today — a former code is drawn only through
the union. The **name** index does carry the former communes (never over a
commune of today of the same name in its département), so a cahier that
still names one resolves ("Saint-Maudez", "La Benâte"); `find_commune` reads
a name as written before the article-stripped key (« La Vergne » and
« Vergné », Charente-Maritime, shared one key and one of them was lost), and
`normalize_commune` spells out the ligature (IGN's « Dœuil-sur-le-Mignon »,
a cahier's « Doeuil »). A supplement pin may carry a former commune's own
code. `audit_geometry_vs_text.py` reads a pre-merger row as naming today's
commune in part. `tests/test_fr_former_communes.py`.

Three more things the name index and the union learnt the same day. A
commune **renamed** since its cahier was written is found by its old name
(`former_names`, INSEE event 10: « Céreste » for Céreste-en-Luberon,
« Clara » for Clara-Villerach, « Roquestéron-Grasse » for La
Roque-en-Provence). A name the cahier spells unlike any table is pinned per
record in [scripts/_lib/fr/commune_name_pins.json](scripts/_lib/fr/commune_name_pins.json)
(Euskal Sagardoa's « Alciette-Bascassan » → Ahaxe-Alciette-Bascassan), each
with its reason. And the card's **commune count is communes of today**
(`stats["matched"]` in `union_from_insee`): INAO's rows carry a commune
nouvelle and its former communes side by side, and counting codes counts
that ground twice — Armagnac's 289 row codes are 284 communes of today
(Cannet, Gueyze, Meylan, Labarrère and Villeneuve-de-Mézin are former
communes of four of them), Calvados's 1,592 are 1,238.

**The seat of a commune nouvelle (2026-11-14).** The mirror case: a commune
nouvelle keeps the code of its seat, so a row written for « Putanges-Pont-
Écrepin » (61339) reads today as Putanges-le-Lac, nine former communes, and
IGN's polygon under the code is all of them. Put to Boris as a choice, his
answer was "Is there any clear legal interpretation about this? We should
follow that reality vs deciding ourselves" — and there is one, in the texts.
268 of the 500 French parent cahiers date their commune list ("sur la base du
code officiel géographique de l'année 2020"); the Official Journal notice of
such a redraft says why — the reference "permet de référencer l'aire
géographique par rapport à la version en vigueur en 2019 du code officiel
géographique, édité par l'INSEE et de sécuriser juridiquement la délimitation
de l'aire géographique. Le périmètre de l'aire géographique reste strictement
identique", "afin que celle-ci ne soit pas impactée ultérieurement par des
fusions ou scissions de communes ou de parties de communes, ou des
changements de nom" (Marsannay, PDO-FR-A0175-AM01, OJ C 89 of 16.3.2021,
p. 11, items 1 and 3); and a commune nouvelle that is only partly inside is
written "Tuffalun (pour le seul territoire de la commune déléguée
d'Ambillou-Château)" — 521 such restrictions in the build's cahiers. **A
merger never moves an aire; a commune named in a list is the commune of the
list's day.** [scripts/_lib/fr/seat_communes.py](scripts/_lib/fr/seat_communes.py)
(`narrowed_seats`, handed to `union_from_insee(…, seats)` by stage 04 for the
parent, its village geometry and the `aires-csv-dgc` path) lets the cahier's
wording decide, on positive evidence only: it names the commune of today and
**restricts** it → the former communes the restriction names ("Lamballe-Armor
(pour le seul territoire des communes déléguées de Lamballe, Meslin,
Planguenoual)"; the seat is not among them for Terres du Midi's Massegros
Causses Gorges → Les Vignes); it names the seat **by its former name** and
nowhere the commune of today → the seat's former outline, with any other
former commune of it the text names (Calvados Pays d'Auge's Mézidon-Canon
and Grandchamp-le-Château); the commune **kept its name** and the list is
dated before the merger — its code officiel géographique year, else the
cahier's homologation (`reference_date`; a décret of February 2015 cannot
name the Montsûrs of 2019) → the seat's former outline; it names the commune
of today **without restriction**, names neither, or lists no commune → the
whole commune, as before. The seat's outline is the commune déléguée
geo.api.gouv.fr serves under the commune's own code (`FormerCommunes.seats` /
`seat_names`, 584 of them; `merged_on` holds the merger dates); a name is
read only under its own département's heading (« Conteville » in the Eure's
list is not Conteville, Calvados, a former commune of Valambray); a seat is
narrowed only when every part has an outline and no former commune the rows
carry would lose its ground, and not at all when the parts and the rows'
former communes are the whole commune again (`_SEAT_WHOLE_SHARE`). Build of
2026-11-14: 49 seats in 18 records drawn from INAO's rows — 14 drinks, three
wine IGPs (Comtés Rhodaniens, Terres du Midi, Vin des Allobroges) and one
DGC; 19 records changed (Calvados Domfrontais inherits its parent's
polygon), `area` only: Muscadet Sèvre et Maine Mouzillon-Tillières −59 % (it
was drawn as all of Sèvremoine, ten former communes, for the two its row of
the cahier names), Calvados Pays d'Auge −3.9 %, Calvados Domfrontais −2.1 %,
Eau-de-vie de cidre du Maine −1.5 %, the two Bugey spirits −1.4 %, Calvados
−1.0 %, Pommeau de Normandie −0.9 %, Pommeau de Bretagne −0.8 %, the rest
under 0.6 %. 102 more seat rows the rule narrows sit in records drawn from
parcels (only their audit-only village geometry follows), and 25 in
rows-drawn records change nothing, the rows carrying the other former
communes. Left whole, the text being silent (CURATOR_TODO): 102 rows of
rows-drawn records the cahier names in neither form, 34 of them rows where
INAO's own row carries the old name, and 5 where a commune kept its name and
the cahier, homologated after the merger, dates its list nowhere. A sub-denomination reads the restrictions of its parent's whole
text, so it can keep a former commune a sibling's row names.
`audit_geometry_vs_text.py` reads a narrowed seat as named in part.
`tests/test_fr_seat_communes.py`.

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
the right granularity for a one-commune sliver; since the zoom-LOD split
this file is written for the audit only and is no longer tiled), reprojects to
EPSG:3035, lightly simplifies, and computes every pairwise polygon
overlap. It skips hierarchy pairs (parent ⊃ sub-denomination; siblings
of one appellation) and classifies the rest by `share` = overlap area
/ appellation area: **NESTED** (one near-contains the other),
**PARTIAL** / **WIDE** (a genuinely large or wide mutual overlap) —
all normal — versus **SLIVER**: a small overlap (1–50 km², < 10 % of
*both* appellations) between otherwise-disjoint appellations. One
appellation overlapping a parent and all its sub-denominations
collapses to a single finding, named after the member with the largest
overlap; a review keyed on the parents holds whichever member that is (a
sub-denomination that inherits the parent's geometry can come first by the
last digits of an area — Périgord / Comté tolosan went unreviewed that way
on 2026-11-13).

The first corpus-wide review (2026-09-25, 520 slivers) showed that the
double-assigned-commune premise holds for one class of pair only, so
every sliver is now **classified** (`classify()`; every class is listed
in full, nothing is hidden) and only the last class is SUSPICIOUS:
**BORDER** — two countries, a band under `--thin-km` (0.3 km) wide: the
two national layers digitise the state border differently (77 pairs,
all ≤ 0.24 km wide); **TIER** — a PGI / IGP or spirit-drink GI over a
PDO / AOC of the same country: the broader tier shares ground with the
narrower one by design (226); **GENERALISATION** — same tier, a thin
band, the two records drawn from different geometry sources (Bétard vs
a GISCO union, a geoportal zone vs a commune list — 107);
**SOURCE-DRAWN** — same tier, both polygons from an official zone layer
(regional geoportal, MAPA, INAO parcellaire) or Bétard: the overlap is
the publisher's own statement (Tuscany's DOCs share ground; Bétard pads
municipalities) and no commune list of ours can fix it (86);
**SUSPICIOUS** — same tier, at least one side drawn from a commune list
of ours, and either wide or from the same source (24 on that review).
A sub-denomination that inherits its polygon is classified through its
parent's provenance (`root_source`). `--json PATH` writes every row with
its class.

Reviewed-legitimate pairs go in
[scripts/_lib/geometry_overlap_overrides.json](scripts/_lib/geometry_overlap_overrides.json)
(`whitelist` of slug pairs) and report as ACCEPTED — the 24 suspicious
pairs of the 2026-09-25 review were all the regulator's own doing and are
whitelisted with the evidence in the reason: for the French pairs the
shared communes are named and sit in BOTH appellations' rows of the INAO
aires-communes CSV (Beaujolais and the Bourgogne regionals share the
eight Mâconnais–Beaujolais communes; Cheverny and Touraine share
Monthou-sur-Bièvre; Agenais and Côtes du Lot both list Fumel), the
Blaye / Bourg band is INAO parcels against an INAO commune list, and the
three Greek pairs are a LAU-vs-NUTS generalisation band. The audit is a
detector only — it changes no geometry; fixing a real artifact means
correcting the upstream commune list / resolver. Thresholds are
CLI-configurable (`--sliver-max`, `--max-sliver-km2`, `--thin-km`, …);
`--strict` exits non-zero on unreviewed SUSPICIOUS slivers only.

## Bétard-snapshot delta audit

[scripts/audit_betard_delta.py](scripts/audit_betard_delta.py) flags
appellations whose geometry comes from Bétard 2022 (`geom_source`
`figshare-pdo` / `figshare-pdo-alias`) but whose GI was **registered or
amended after the dataset's data snapshot** (Nov-2021 cutoff) — those
polygons may not reflect a post-snapshot boundary change, and a brand-new GI
may only be on the map via an incidental file-number match. It reads the
compact `wiki/data/aocs.en.*.js` startup blob (geom_source is a startup
field) cross-referenced against each `raw/<cc>/eambrosia/index.json`'s
`eu_protection_date` / `modification_date`, and buckets each record
**FLAGGED** / **REVIEWED** / **OK** / **NO-DATE** (the sibling-audit pattern).
Curator-confirmed-unchanged boundaries go in
[scripts/_lib/betard_delta_overrides.json](scripts/_lib/betard_delta_overrides.json)
(slug → `{reason, source}`) and report as REVIEWED. Read-only detector —
changes no geometry; a real FLAGGED finding is fixed upstream (a newer Bétard
release, a regional zone layer, or a commune-list resolver). `--strict` exits
non-zero on any unreviewed FLAGGED finding; `--cutoff` overrides the snapshot
date.

## Empty grape-list audit

A wine card that renders with no grape pills is a silent failure: a
cahier layout the section parser did not read (Costières de Nîmes' 2025
republication buries `1°- Encépagement` behind a conformity paragraph;
Picpoul de Pinet's section V is missing from the extraction), a
national-spec sidecar that did not bind, or a sub-denomination that
inherits nothing from a parent that does carry grapes (the 12 Valais
grands crus). [scripts/_lib/grape_gaps.py](scripts/_lib/grape_gaps.py)
classifies every grape-less record of a build — **FLAGGED** (wine
parent, not a stub, not reviewed; sub-denominations of an empty parent
are counted on the parent's line, so Saint-Aubin's 32 premiers crus are
one finding), **INHERIT** (stage-04 gap), **REVIEWED** (slug in
[scripts/_lib/empty_grapes_overrides.json](scripts/_lib/empty_grapes_overrides.json):
the regulator names no variety — Vlaamse landwijn's broad IGP rule, the
CH cantons whose règlement defers to the federal OVin), **STUB**,
**NON-WINE**. Stage 04 prints the one-line `[grapes]` summary on every
build; [scripts/audit_empty_grapes.py](scripts/audit_empty_grapes.py) is
the full report and the gate (`--strict` exits non-zero on FLAGGED or
INHERIT; `--all` lists stubs and spirits). `tests/test_empty_grapes.py`
pins the classifier and, when a build is present, that the INHERIT
bucket never grows. The 2026-09-20 sweep found 39 FLAGGED parents (+39
sub-denominations) and 12 INHERIT; after the parser fixes of the same day
(FR encépagement sub-block / repeated-numeral / page-top header / keyword
routing, PT `Principais Uvas de Vinho` anchor, ES PDF-pliego branch, IT
letter-spaced MASAF PDFs + catalogoviti registers, AT fuzzy title, CH
grand-cru inheritance, Saint-Aubin's full cahier pinned from the BIVB
mirror) the FLAGGED bucket is empty and `--strict` passes; the per-record
record of that sweep is in [CURATOR_TODO.md](CURATOR_TODO.md). A FLAGGED finding is fixed upstream
(stage 02 / 02f parser or a manual override), never by editing the
build; a genuine absence is pinned in the overrides file with its
source.

## Grape pill labels: verbatim, with one per-record escape hatch

A grape pill shows the regulator's own spelling (`details[].name`) with
the VIVC prime in brackets, so a cahier typo renders as written ("Muscat À
Petit Grains Blancs (Muscat A Petits Grains Blancs)") — the slug is folded
by `GRAPE_ALIAS`, the label is not. When the verbatim surface is a *source
defect* rather than a spelling — the Haute-Marne cahier drops a comma and
the candidate comes out as "petit grains blancs muscat ottonel" —
[scripts/_lib/grape_display_overrides.json](scripts/_lib/grape_display_overrides.json)
(record slug → grape slug → `{name, reason, source}`) relabels it for that
record only; stage 04 applies it in the `grape_names` block
([scripts/_lib/grape_display_overrides.py](scripts/_lib/grape_display_overrides.py)),
sub-denominations inherit the parent's entries, and an entry whose grape
the record no longer carries is ignored with a STALE warning.
`tests/test_grape_display_overrides.py` validates the table. Never use it
to translate or "improve" a real spelling.

The bracket is left out when spelling and prime are the same name after
`_canon_norm` (content_block.py; `canonicalEqualsCahier` in app.js,
`tests/test_content_block.py` runs both on the same pairs): diacritics
dropped, the trailing OIV colour code removed — with the period MASAF writes
("Cabernet Sauvignon N.") — the VIVC colour word removed, and VIVC's German
umlaut spelling folded (ue / oe / ae, both sides). Until 2026-10-23 the code
needed no period and the umlaut was not folded: 1,288 pills read
"Gewürztraminer (Gewuerztraminer)", "Hárslevelű (Harslevelue)" or
"Trebbiano Toscano B. (Trebbiano Toscano)". A typo keeps its bracket
("Cabertnet Sauvignon (Cabernet Sauvignon)"). The fold deletes an "e" after
any a / o / u, so it also touches every genuine vowel + e sequence (piquepoul,
jacquère, Jaen, Blauer …): a pair it alone collapses must be an umlaut pair,
and `audit_grape_identity.py` sweeps the extracted corpus for them (its `fold`
list, `content_block.fold_only_bracket_class`) — each (prime, spelling) pair
equal only with the fold is `umlaut` (the spelling's umlaut is the digraph the
prime writes), `umlaut-sibling` (no umlaut in this spelling, but another
spelling of the slug carries one — the Iberian "gewurztraminer", GB's
"Schonburger") or `review` (none does: the fold collapsed something else);
`--strict` fails on a `review` pair and the release gate runs it
(`grape-brackets`). First run, 2026-10-23: 18 umlaut, 8 sibling and one
`review` — MASAF's vitigno scan had read "dal vitigno Brachetto e per il
restante 3%" as "Brachetto e" (Asti's "Moscato bianco e" likewise), a
conjunction the fold hid behind "Brachetto"; the scan drops a trailing
conjunction now (`_TRAILING_CONJUNCTION_RE`), both sidecars re-extracted.
`tests/test_grape_bracket_fold.py` pins the classes.

**The corpus-wide label is a vote, not the first file read.** The name a
grape carries outside a record — the filter chip, the omnisearch row, the
prose lines, the pill of a record without a spelling of its own
(`grapes_info[slug].name`, from `grape_corpus.collect_grape_slugs`) — is
chosen by `pick_label` ([scripts/_lib/grape_corpus.py](scripts/_lib/grape_corpus.py))
from every spelling the records give the slug, each cleaned by
`label_surface` (extraction debris, the "- synonym" tail and the OIV colour
code dropped, a line-break hyphen closed): the spelling group that writes
the slug — the lexicon's canonical, as some regulator writes it — wins
(Bouvier over a more frequent Findling); without one, the records whose
name is the slug itself (the FR extractor writes the key back for half its
rows) settle for the slug, else the most frequent group, capitals-only
groups last; inside the group the most frequent casefold form decides
accents and punctuation (Cabernet Sauvignon over the cahiers'
Cabernet-Sauvignon, Sémillon over Semillon, a tie keeping the accents) and
its mixed-case spelling is taken; a Latin label left in capitals is
lower-cased for the client's Title Case, a Greek one keeps them. Until
2026-10-23 the label was the first surface met in filesystem order, raw:
Reinier Broeks' Druivenatlas link for Cabernet Sauvignon opened a chip
reading "Cabernet- Sauvignon" (one Hérault IGP's pdftotext line break) and
189 labels carried a colour code ("Barbera N."). The per-record pill keeps
its document's spelling; the one thing it shares with the label is
`clean_name`'s repair of a hyphen pdftotext broke across a line ("cabernet-
sauvignon" → "cabernet-sauvignon", a dash spaced on both sides staying a
separator), so the Côtes de Thau pill no longer shows the line break either.
The FR roster reader stores an elided article with its apostrophe
(`_with_source_apostrophes` in `grape_lexicon.py`: its word splitter takes
the apostrophe for a separator, and until 2026-10-30 Muscat d'Alexandrie,
Pineau d'Aunis, Roussette d'Ayze, Len de l'El, Nero d'Avola and Rayon d'Or
were stored as "muscat d alexandrie" etc. on 233 records — the pills and the
corpus label read "Muscat D Alexandrie"); the words it matches stay
space-joined. Title Case (`toTitleCase` in query_core.mjs, `to_title_case` in
content_block.py, `tests/test_content_block.py` runs both) keeps an elided
d' / l' lower case: "Muscat d'Alexandrie", "Nero d'Avola".
`tests/test_grape_corpus_labels.py`, `tests/test_grape_labels.py` and
`tests/test_fr_grape_apostrophes.py` pin the rules.

## Grape identity: lexicon gaps, fuzzy look-alikes, restated names

A visitor flag on Piemonte (2026-10-22: Albarossa, listed in the single
document's § 7 and named by the card's own fact, was missing) turned out to be
one case of four failure modes, swept corpus-wide the same day:

- **Lexicon gaps.** A variety the regulator lists that no lexicon entry
  matches is dropped silently and lands in `raw/<cc>/extraction-unknowns*.json`.
  The Ruchè di Castagnole Monferrato DOCG showed Barbera and Brachetto without
  Ruchè; Colli Tortonesi had no Timorasso, Trentino no Nosiola, Franciacorta
  no Erbamat. 161 entries were added to `grape_lexicon.py` (one dated
  block per table), every id resolved on the live VIVC search that day and
  pinned in `raw/vivc/slug_overrides.json` (`_resolved_via:
  curator-2026-10-22`); the colour is the regulator's OIV code where it gives
  one (Garda's "Bellagna B." and Paros' "Stavrochiotis B" against a VIVC noir
  / rouge are noted in the block).
- **Fuzzy look-alikes.** A name the lexicon lacks can fuzzy-match a different
  cultivar: Caloria → Pelaverga (39 Tuscan cards), Baron → Cabernet franc
  (21), Karát → Cinsault (18), Rubinet → the white Jacquère (17), Blauer
  Silvaner → Pinot noir (14), Verdiso → the Greek Lagorthi (11), Fokiano →
  Fiano, Pinela / Pinella → Tempranillo. Each got its own VIVC-verified entry
  (an exact entry always beats a fuzzy one); style, colour and place words got
  `_BANNED_SURFACES` (Siller, Csillag, Kretzer, piros, blanc, gentile, rosa,
  Lacryma, Κάβα, Πάτρα, Μοναστήρι, Για, Ρετσίνα), beside the "rosé" ban of
  the same day (VIVC lists ROSE as a Nebbiolo synonym, so a bare "rosé" had
  bound Nebbiolo to Prosecco, Franciacorta and Alto Adige); and
  `_fuzzy_passes_sanity` refuses two names
  that both carry numbers when the digits differ ("Incrocio Manzoni 2-14" is
  not 2-15; "6.013" and "6.0.13" join to the same number).
- **Restated appellation names (IT MASAF).** Article 2 restates the DOP name,
  and VIVC keeps place names as synonyms: «Valtellina Superiore» bound
  Veltliner rot on nine cards, the IGT «Avola» Ribolla gialla (which then kept
  the Sicilian register from filling an otherwise empty roster),
  «Cesanese di Olevano Romano» the Burgundian César through "Romano".
  `masaf.parse_grapes_with` now lets a phrase that restates the name, wholly
  or as a run of its words, bind a grape only when `is_curated_surface` vouches
  for it (a corpus slug, a GRAPE_ALIAS key, a VIVC prime or a synonym VIVC
  flags as a country's official name — so Cesanese di Affile stays), and a
  grape first met in such a phrase takes its label from the genuine phrase
  (Barolo's pill had read "Barolo", Lugana's "Lugana").
- **One passport per berry colour (2026-10-23).** A cahier lists "muscat à
  petits grains B", "… Rg" and "… Rs" as three entries and VIVC files them
  apart (#8193 BLANCS, #8248 ROUGES, #8186 ROSES), the way `veltliner-rot` is
  distinct from the Frühroter: `COLOUR_QUALIFIED_SLUGS` in `grape_lexicon.py`
  gives a colour-coded entry its colour's passport slug, the name carrying the
  code's colour word ("muscat à petits grains rouges" — the cahier's own
  legend, so the two pills differ and the corpus label is the slug's). Read by
  the FR reader and by `match_variety` on an explicit code only, never on a
  block colour; 53 FR records gained the pink or red muscat as a second pill
  (Méditerranée Comté de Grignan, validator finding).
- **A colour word that is a cultivar binds only as a roster cell (2026-10-23).**
  "Rosa" (VIVC #22422, the VÚVV Bratislava crossing the SK §f tables list) is
  a banned colour surface everywhere; `grape_entity.match_roster_cell` binds
  the `COLOUR_WORD_VARIETIES` of the lexicon when the reader knows its token is
  a whole cell of a variety table (the SK Odroda column). `exact_match` is the
  matcher's silent exact-only form, for a reader testing a hypothesis (two
  halves of a wrapped name joined, an Article 1 varietal type) where a miss is
  the expected answer, not a lexicon gap.
- **A VIVC name under two primes is pinned `false`.** BLANCA DE MONTERREI is a
  synonym of SIRIA #2742 and of CARREGA BRANCO #2124; the Monterrei pliego
  lists it beside Doña Blanca (= Síria), and the pill carries no bracket rather
  than a prime VIVC cannot settle (2026-10-23; it had been pinned to #2742 from
  memory). The Cypriot single documents' bare "Malvasia Grossa" sits under four
  primes (Síria, Malvasia Dubrovačka, Vermentino and a black passport of its own
  name, #7268): its own slug, pinned `false`, with no colour (2026-10-24). The bare Italian adjective "aromatico" and its inflections are
  `_BANNED_SURFACES`: Muscat bleu's passport (#16002, pinned for the NL
  provincie PGIs) lists AROMATO, and the MASAF clauses' "non aromatici" tokens
  fuzzy-matched it at 87.
- **Elided articles.** A slug writes "bianco-d-alessano", a token keeps
  "Bianco d'Alessano"; the vocabulary registers both forms.
- **Agudelo is Chenin blanc (2026-10-24).** The 2026-05-19 research had
  folded `agudelo` into Godello and called the OJ's "AGUDELO - CHENIN BLANC" an
  ampelographic error; MAPA's own variety list (RD 684/2026, printed
  2026-09-08) gives "Agudelo (B.)" the synonym Chenin Blanc in ARA / CAT / GAL
  and Godello none, VIVC flags AGUDELO as Spain's official name on Chenin
  blanc #2527, the Betanzos microsatellite study (OENO One 2011) found
  Agudelo = Chenin Blanc, and the Galician documents themselves list Godello
  *beside* "Chenín blanco (Agudelo)". The alias is `chenin`; the Catalan cards
  lost a wrong Godello, the Galician keep theirs from their own entry.
  Merseguera ↔ Sumoll blanc stays split (VIVC #7660 / #12073, MAPA lists
  Sumoll Blanco as Merseguera's Catalan synonym, INCAVI names Sumoll blanc
  only), but the one roster line "MERSEGUERA - SUMOLL BLANCO" is one pill on
  the three Catalan documents that write it: the ES reader applies a
  per-record pin from [scripts/_lib/es/grape_context_overrides.json](scripts/_lib/es/grape_context_overrides.json)
  (the IT `grape_context_overrides` pattern — `context_pins` /
  `_apply_context_pin` in `es/02`, keyed by the record slug, a subzona
  inheriting through its parent's deep copy; `tests/test_es_grape_context.py`).
- **Malvasia bianca under two slugs (2026-10-24).** `malvasia-bianca` and
  `malvasia-bianca-lunga` both resolved to VIVC #7262. The spellings #7262
  vouches for — Malvasia del Chianti, Malvasia toscana, Malvasia lunga, the
  Greek "Pavlos B" (PAVLOS / PAULOS) — fold into `malvasia-bianca-lunga`; the
  bare "Malvasia bianca" keeps a slug of its own with no bracket, pinned
  `false` in VIVC: the name is a synonym of both #7262 and Malvasia bianca di
  Candia #23555, and the Italian register carries "Malvasia bianca" as an
  entry beside "Malvasia bianca lunga" (the Calabria, Campania and Sicilia
  registers list it; 33 southern MASAF rosters write it bare, Puglia 14) —
  the Veltlínské červenobílé precedent. The Cypriot documents' "Malvasia
  Bianca" and "Malvasia Lunga" (the Cypriot official name on #7262) stay two
  pills. Withdrawing a VIVC fold can expose the typo splitter: `malvasia-grossa`
  (pinned `false` in phase F) had split into Malvasia + the Portuguese Grossa
  on the Tarragona sidecar — `_split_concatenated` keeps a curated canonical
  slug whole.
- **Varieties outside §7 (2026-10-24).** An EU single document names
  varieties beyond its §7 roster: §4 as a varietal type ("Piemonte bianco,
  con specificazione di vitigno Cortese, Chardonnay, Sauvignon" — C 91/2020's
  §7 has no Sauvignon), §5 in a production rule (Eger's Turán and Cabernet
  dorsa, Prosecco's Chardonnay and the three Pinots up to 15 %). The corpus
  sweep over the 16 EU-document readers found 38 such records (ES 21, IT 20,
  HU 3, RO 1, BE 1), about half of them bare family words.
  [scripts/_lib/section_varieties.py](scripts/_lib/section_varieties.py)
  (`add_section_varieties`, called right after `parse_grapes` in the ES, IT,
  HU and BE readers) adds them as **accessories** tagged `section-4-type` /
  `section-5-rule` — the RO yield-table precedent — under four guards: an
  exact *curated* lexicon surface (`is_curated_surface`), never a bare family
  word (`FAMILY_WORDS`: lambrusco, albillo, moscato, listan, groppello,
  raboso …, and the family words the lexicon folds onto one member —
  canaiolo, malvasia nera, refosco, magliocco, nerello, verduzzo — which
  `audit_grape_surfaces` lists as TRUNCATED; the first run had read Maremma
  Toscana's "Canaiolo" as Canaiolo nero), never a variety name that is an
  everyday word (`PROSE_WORDS`:
  the first run read "óptima maduración" as Optima, "sol y serena" as
  Serena, "frutti di bosco" as Bosco, "vitigni a bacca bianca" as Bianca,
  "halvány rubin" as Rubin), and capitalised in the document or introduced
  by a variety word within 30 characters ("las variedades garnacha blanca y
  macabeo"), never after a toponym lead ("El Molar"). Result: 32 parents —
  ES 12 (Montsant's §4 list of 11, the Vinos de Pago estate lists, El
  Hierro, La Gomera, Granada), IT 16 (Sicilia's 29 varietal types, Maremma
  Toscana and Val d'Arno di Sopra 15 each, Prosecco ×3, Piemonte's
  Sauvignon, Rosso Orvietano, Vallagarina, Ravenna), HU 3 (Eger, Badacsony,
  Kunság), BE 1 (Maasvallei's Madeleine Angevine). `tests/test_section_varieties.py`.
  Residue: Dealurile Vrancei's §5 yield table names seven varieties the RO
  yield-table rule does not read.
- **A new passport claims old names.** Fetching a passport registers every
  legacy synonym it lists, so the second re-extraction found new wrong
  bindings: "Malvasia bianca" → Agostenga (#107 lists it too; 29 Italian
  cards), Geneva's "m 2" → Karmin's breeder code "M. 2", the Vaud commune
  "Roche" → Ruchè, the Alto Adige comune "Montagna" → Paolina (#7937's prime).
  A canonical slug now keeps its own name against another record's unflagged
  synonym (`_load_vocabulary`, between the official and the unflagged tier —
  it moved exactly that one key); the place words are banned.
- **Family names are not one cultivar.** The automatic VIVC resolution had
  pinned the slug `lambrusco` to Lambrusco Marani (#6695) and `groppello` to
  Groppello di Revò (#25971), so a bare "Lambrusco" (11 cards) read as Marani
  and "Lambrusco Benetti", "Groppello di Mocasina" folded into them. Both are
  pinned `false`; the named members carry their own slugs. A bare
  "Asprouda" / "Μοσχάτο" (VIVC folds them under several cultivars) binds
  nothing.
- **Short words and colour codes.** Below 95 a fuzzy match needs five
  letters ("doña" had scored 88 against Razaki's synonym "Donna"). The colour
  code is stripped after any letter: the per-script allowlist had left out
  the Croatian ć ("Babić N" matched nothing), the Italian ò and the Greek
  capitals.
- **Bare colour words.** A block header or an adjective reaches the matcher
  as a token, and VIVC's unflagged synonyms include FEHER (Majarcă albă #11866:
  pinned on 2026-10-22, it put Majarcă on six Hungarian cards within the
  hour), NERA (Pinot noir), ROTER (Roter Veltliner), BILA (Okatica bijela);
  the Valais règlement's "blanche" had bound Mondeuse blanche. The colour
  words of every corpus language are `_BANNED_SURFACES` (96 keys, the
  `_normalise` forms); a variety that is a colour word — Bianca, Nero — is
  not. The same goes for the Spanish season word "verano" (2026-10-24):
  Sciacarello's passport (#10837) lists VERANO, and a climate sentence the
  Valencia pliego parser read with its varieties put Sciacarello on Valencia
  and its four subzonas for two months. Pinning a passport claims its
  synonyms: check what a new passport binds before and after.
- **One cultivar, one slug.** `fruhroter-veltliner` (CZ, HU) and
  `velteliner-rouge-precoce` carried the same VIVC 16157; the first folds
  into the second. `Veltlínské červenobílé`, which VIVC files under the same
  number while the Czech decree lists it as a variety of its own, keeps its
  own slug without a bracket (pinned `false`, CURATOR_TODO). `lemberger`
  (RO, SI, DE, AT, GB, BE, PT, ES) and `blaufrankisch` (HU, HR, SK, CZ, GB)
  carried VIVC 1459: the AT and DE spelling "Blaufränkisch" bound to
  `lemberger` through the VIVC synonym tier, so no record spelled the slug
  `blaufrankisch`, the GB roster put the variety on one card twice and the
  corpus vote labelled `?grape=blaufrankisch` "Kékfrankos" (2026-10-23);
  `lemberger` folds into `blaufrankisch`, the VIVC prime's slug, which now
  carries `noir` in `DEFAULT_COLOUR` and reads "Blaufränkisch". `franconia`
  (Friuli) keeps its own slug by an explicit lexicon decision; the
  VIVC-sibling expansion unites the three in the grape filter.
- **An alias poisons the VIVC record too.** `perle-von-zala`, `zala-gyoengye`
  and `zala-gyongye` folded into `csabagyongye` ("alternate German name") —
  Perle von Zala is Zalagyöngye (#13374), Csabagyöngye's offspring — and 02g,
  which queries VIVC with a corpus surface of the slug, resolved
  `csabagyongye` through "Perle von Zala" to #13374, so 15 HU / DE / GB pills
  read "Csabagyöngye (Zala Gyoengye)" and opened the *Pearl of Csaba*
  tooltip (validators, 2026-10-23). The keys fold into `zalagyongye` and both
  slugs are pinned on the live passports (#9166, #13374). Before trusting an
  alias comment, check the target's by-slug `query`; and diff every surface's
  binding before and after a pin (a new passport's synonyms are claimable:
  #9166 carries 96).
- **Wrapped names in the parsers.** The MASAF annex reader rebuilds a register
  row whose name wrapped around its code line, by the name column
  (`_wrapped_rows`: Castelfranco Emilia's "Lambrusco del ⏎ Pellegrino" had
  bound Sauvignon and four Lambruschi were missing; Esino's "Malvasia bianca
  di ⏎ Candia" read as the aromatic Candia); `_VITIGNO_RE` no longer stops at
  the dot of "Incrocio Manzoni 2.15"; the ES pliego reader takes a line that
  opens on a colour word for a heading only when it reads as one
  (`_colour_heading`: "Doña ⏎ Blanca o Cigüente" had lost Doña Blanca,
  "Negramoll" its own name); the CH variety guard knows a commune without the
  canton its official name carries (`is_commune_name`: "Roche (VD)"). The SK §f reader joins a wrapped
  Odroda name ("Veltlínske červené ⏎ skoré"): read line by line the row was
  Roter Veltliner, and an alias had patched the wrap.
- **One VIVC number, two pills on a card (2026-10-25, phase H).** The re-grade
  found 118 parent cards showing two slugs VIVC files under one number. Each
  pair was settled one of three ways, recorded in the lexicon's 2026-10-25
  block, the VIVC pins and
  [scripts/_lib/vivc_shared_pills.json](scripts/_lib/vivc_shared_pills.json):
  **a fold** where the regulator writes one variety with its synonym or MAPA's
  list (RD 684/2026, printed 2026-09-08) gives the synonym — Nielluccio and
  Prugnolo gentile into Sangiovese, Inzolia into Ansonica ("Ansonica o
  Inzolia"), Rolle into Vermentino ("rolle B ou vermentino B"), Crujidera into
  Moravia dulce, Cariñena blanca into Carignan blanc, Embolicaire into
  Bonicaire, Exquitsagos into Merseguera, Tintorera into Alicante Bouschet,
  Planta Angort into Planta fina de Pedralba, Bastardillo Chico into Trousseau;
  **own slug, no bracket** (pinned `false`) where VIVC's number belongs to
  another entry the regulator lists beside it — Greco bianco, Palomino, bare
  Raboso and Malvasia (family words), Bonicaire, Tijonera, Verdoncho,
  Bratkovina crvena, Μοσχάτο Κύπρου — or **own slug on its own passport** —
  Piros bakator (#905, beside Kék bakator #25053), Albillo Dorado (#23429),
  Tinto de la Pámpana Blanca (#22848), Cariñena gris (#2097, it had been
  Carignan noir's); **keep** where the regulator lists both as rows (the PT
  cadernos' castas, a country rule; Castelfranco's Mostosa and Spergola;
  Tintilla de Rota). Two traps it showed: `_vivc_canonical_by_id` ranks a
  number's slugs by record count, so the Corsican cahiers' 87 "Nielluccio"
  records made the Corsican name Sangiovese's canonical slug and every Italian
  synonym of Sangiovese bound it; and layout debris of two-column cahiers
  slugifies into a pill ("suivie de la manseng", "gris pineau d aunis",
  folded in GRAPE_ALIAS). Readers fixed the same day: the ES pliego reader
  splits a token that matches nothing into two curated exact names when a
  comma is missing ("Listán Prieto Moscatel negro", El Hierro's wrapped
  "Malvasía volcánica ⏎ Moscatel de Alejandría"; `_missing_comma_entries`);
  the CY reader reads an em dash inside a content line as the name–synonym
  separator when the bullets stand on lines of their own (Larnaka's "Malvasia
  di Candia — Malvasia Aromatica"); the PT reader rejoins a PRT-code row whose
  name wraps inside its cell ("PRT52915 Moscatel- Branco ⏎ GalegoBranco").
  `audit_grape_identity.py` lists the class from the build (`shared`, report
  only); a pair the table does not rule is `review`.

Against the cards of the morning, the sweep changed the grape roster of 358
cards in 17 countries (IT 175, DE 36, GR 36, CH 29, HU 17, NL 15); every
re-extraction ran as snapshot → run → per-record grape diff, one step at a
time, and every diff was read.

[scripts/audit_grape_identity.py](scripts/audit_grape_identity.py) is the
repeatable check: the colour-coded names no entry resolves, every distinct
fuzzy binding in the corpus (most are spellings — "Mourverdre", "Cabertnet
Sauvignon" — the rest go to CURATOR_TODO), the brackets the card's umlaut
fold alone suppresses (`--strict` fails on one no umlaut spelling explains;
see "Grape pill labels") and the shared-VIVC pairs of the build
(`tests/test_vivc_shared_pills.py`). **02g re-resolves every slug on every
run** from the first corpus spelling it meets, against a search cached by
slug: after the Cypriot re-extraction of 2026-10-25 a full run wrote a miss
over 17 resolved slugs (Blaufränkisch queried as "blauer limberger",
Catarratto, the Greek and Cypriot natives by their Greek spelling); they are
pinned back on the live passports, a miss no longer replaces a resolution
("kept-resolved"), and a partial run leaves the manifest and the curator queue
alone. Before trusting a full 02g run, compare its by-slug ids with the last
build's `grapes_info`. `tests/test_grape_identity_guards.py`
pins the guards. Adding entries changes bindings in other countries, so the
affected stage 02 / 02f runs are re-extracted with a snapshot and a per-record
grape diff (the GR 02f drift of 2026-10-11 is why).

## Style pills: what the readers state, what the floor adds

A card's styles are its stage-02 reader's (with the national-spec or
register-fiche sidecar merged at stage 04), stage 04's prose scan (icewine,
vin santo, fondillón, the sparkling methods) and the grape-colour floor. The
rules, settled on the validator findings of 2026-10-23 (phase C):

- **A reader states what the text states.** Colours, the EU product
  categories ("1. Vin / 4. Vin mousseux / 15. Wine from raisined grapes") and
  the category words are read from the document; a missing pill is a reader
  gap, fixed in the reader. PT had no reader until then (every card showed the
  floor's red and white; `pt/02` `parse_styles`); SI reads the register's
  single document beside its national text, which states no rosé
  (`extract_register_fiches.py` keeps the fiche's `categories` and whole
  `description`; `si/02f` adds what they state, the card cites the fiche); MT
  reads the register's single document beside the amendment it publishes. FR
  routes a section titled "Types de produit" as `couleur` (the one cahier
  without a DGC section numbers it II, so the legacy fallback had read
  Crémant d'Alsace's aire for its colours); the IT documento-unico reader
  reads the section titles, because its slicer takes a description's
  per-type headers ("Franciacorta Rosé", "Vino Roma rosato", "Valcalepio
  Moscato passito") for sections whose bodies it does not read, and the
  accented "rosé" / "rosè" that `\brose\b` never matched. Every IT reader
  (EU document, MASAF article 1 + 6, sottozona annex) reads the head word of
  the organoleptic colour field (`documento_unico._COLOUR_FIELD_RE`: after
  "da" / "dal" / "tra" and at most one adjective) — "colore: giallo
  paglierino" is a white wine, "colore: dal rubino al granato" a red one —
  because a white type is named by its variety ("Offida Pecorino",
  "Riviera ligure di Ponente Pigato"), not "bianco": IT's floor-only cards
  went from 51 to 2, and Prosecco's newly read Rosé no longer hides its
  White. A pink head is not read ("colore: dal rosa all'ambrato" is the Vin
  Santo Occhio di Pernice of five Tuscan DOCs), nor a reflection; a golden or
  amber head is white (Marsala's Oro and Ambra, "Colore dorato più o meno
  intenso oppure giallo ambrato", whose first single document had lost its
  White, 2026-10-24). When a document gives its link section the description's
  title (Terre Tollesi, C 396/2021: §8 titled like §4), `route_sections`
  takes §8 as the link.
- **A sweetness level a document lists as a wine type is a style** — "Οίνος
  λευκός ξηρός, ημίξηρος, ημίγλυκος, γλυκός" (`gr.eniaio_engrafo.
  sweetness_type_styles`), "száraz, félédes vagy édes" (`hu.egyseges_dokumentum.
  sweetness_styles`), "за полусладки вина … за сладки вина", IT "amabile" /
  "dolce", ES "Vinos Semisecos, Semidulces y Dulces" / "se clasifican en
  secos, dulces, semisecos y semidulces" / a limit set "para semisecos,
  semidulces y dulces" (`es/02` `sweetness_type_styles`, 2026-10-30: a list of
  two levels or more outside the link section and its sub-sections — Rosalejo's
  "8.3" compares the IGP Castilla's types with its own dry wine — read within one
  section body or title, and never a list its own sentence introduces as
  labelling terms, the EU sugar-term rule restated: "podrán emplearse las
  indicaciones seco, semiseco, semidulce y dulce", "Según la legislación vigente
  se podrán denominar: secos, semisecos …" (`_sweetness_list_is_labelling`;
  Castilla y León's analytical footnote was its only source, Bailén's heading
  "Vinos semisecos, semidulces y dulces" states the types anyway); 30 ES records):
  Semi-sweet / Sweet. Semi-dry is not added.
- **A liqueur wine is fortified, not sweet; a generoso is not oxidative by
  itself (ES, 2026-11-14).** Boris's question on Manzanilla de Sanlúcar: the
  card showed Sweet and Oxidative where the single document (C/2026/4513)
  reads "Sabor: Seco … azúcar inferior a 4 g/L" and "aromas propios de la
  crianza biológica". The ES reader alone coupled the category to both pills
  — `vino de licor` → `sweet`, `generoso` / `fino` / `manzanilla` →
  `oxidative` — where every other reader maps a liqueur wine to
  `vin-de-liqueur` alone (PT: 0 of 20 fortified parents carried Sweet; ES: 46
  of 46). Now `vino de licor` states `fortified` + `vin-de-liqueur`
  (`generoso de licor` adds `generoso`), a generoso states `generoso`, and
  `oxidative` comes with the three types whose definition is an oxidative
  ageing (amontillado, oloroso, palo cortado). Sweetness is read where the
  text states it (`liqueur_sweetness_styles`): a type header that says
  "dulce" ("6. Vinos de licor dulces (categoría 3)", Montilla-Moriles; "7.
  Vinos Rosados (Jumilla Dulce)"; "5. VINO - VINOS DULCES", Cigales; "2. Vino
  Blanco y Rosado, dulce", Ribera del Júcar — the last two had no Sweet at
  all), a predicate of the wine in the liqueur wine's own block ("En boca
  dulce y golosa", Valencia; "El dulzor predomina sobre la acidez", Jumilla;
  "Vinos de licor: … En boca será dulce", Valdejalón) or in a section titled
  for it ("caracterizados por un elevado contenido en azúcar", Navarra's link
  sub-section) — never "taninos dulces", "fruta dulce", "sin dulzor marcado",
  nor grapes rich in sugar (Costers del Segre, Utiel-Requena). Full ES run
  against a snapshot: 14 records, styles only — Sweet off Manzanilla and
  Rueda ("Vino Dorado, vino de licor, seco") and off Cataluña, Costers del
  Segre and its five subzonas, Pla i Llevant, Utiel-Requena (text silent);
  Oxidative off Manzanilla and Lebrija ("vino generoso: vino de licor
  elaborado bajo velo de flor, proceso biológico"); Sweet on Cigales and
  Ribera del Júcar. `tests/test_es_liqueur_styles.py`.
- **The style taxonomy is a graph with a tree drawn over it (2026-11-14).**
  The facet had filed the same wines where the pills no longer put them:
  `fortified` was a child of `sweet` and `generoso` (with fino and manzanilla)
  a child of `oxidative`, so "Sweet / dessert" returned 33 parents only
  because they are fortified (Douro, Madeira, Rueda, Manzanilla …) and
  "Oxidative" two only because they are generosos. Styles are several axes —
  colour, effervescence, sweetness, fortification, ageing — and
  [scripts/_lib/style_taxonomy.py](scripts/_lib/style_taxonomy.py) says so now:
  every slug has one primary parent, where the sidebar tree shows it once,
  and `extra_parents` for the other axes it sits on, which filtering follows
  (the vin-santo mechanism). `fortified` is a bucket of its own (`BUCKETS` /
  `FACET_BUCKET_ORDER`: white, rosé, red, sparkling, sweet, fortified,
  oxidative, other, drinks; its row carries the node's own label, no second
  msgid); `vdn` and `mistela` are sweet by definition and keep `sweet` as an
  extra parent, a `vin-de-liqueur` is sweet where its record states it;
  `generoso` sits under `fortified`; `amontillado`, `oloroso` and
  `palo-cortado` keep `oxidative` as an extra parent, `fino` and `manzanilla`
  do not. `styles_simple` follows (a full build), the entity description's
  reading order gained "fortified" (`_STYLE_ORDER`), and the ES label of the
  sweet row reads "dulce / de postre" ("licoroso" named the wines that left
  it). The MCP context carries the new bucket as data — its keys are
  unchanged. A fortified wine whose reader states no sweetness is found
  under "Fortified", not "Sweet / dessert" — the next bullet covers the five
  a curator pinned; the rest are in CURATOR_TODO.
  `tests/test_style_taxonomy_axes.py`.
- **A curator's cited style where the reader has no rule yet (2026-11-14).**
  [scripts/_lib/style_overrides.json](scripts/_lib/style_overrides.json)
  (record slug → `add`, `basis`, `evidence`, `reason`, `source`, `verified`;
  [scripts/_lib/style_overrides.py](scripts/_lib/style_overrides.py)) adds
  styles to one record at stage 04's style chokepoint, after the reader's
  styles and the prose scan; a sub-denomination takes its parent's entry.
  Two bases. **`stated`**: the record's own text names the level as a type
  and the reader does not read it — Porto's «Doçura» table ("Meio Seco …
  Doce … Muito doce ou Lágrima": semi-dry, sweet), Madeira's "tipos:
  extra-seco; seco; meio-seco; meio-doce e doce" (semi-dry, semi-sweet,
  sweet); the PT reader has no sweetness rule. The card states what the text
  states and discloses nothing. **`method`**: the text names no level and
  the style follows from the method it lays down — Pineau des Charentes,
  Floc de Gascogne and Macvin du Jura are grape must (over 170, at least 170
  and at least 153 g/l of sugar) muted with Cognac, Armagnac or Marc du
  Jura, and their cahiers set no sugar content for the finished wine. That
  is an interpretation, so the entry carries a `disclose` sentence in en /
  fr / es / nl and the card prints it under the style pills ("Sweet inferred
  from the method: grape must fortified with Cognac while it still holds
  over 170 g/l of sugar; the regulator's text names no sweetness level" —
  the feature property `styles_override` names the entry, the panel payload
  carries `styles_note` only for a `method` entry; `styles_note_line` in
  content_block.py, `stylesNoteLine` in app.js). Every `evidence` quote is a
  verbatim passage of the extracted record (file, dotted field, quote), and
  an entry whose record already carries every style it adds is **STALE** —
  the reader states it now: stage 04 says so and
  `tests/test_style_overrides.py` fails, so a pin retires when its reader
  arrives. Never a style no public text supports, never a removal. First
  build: 10 records, styles only (the five parents, Porto's three
  sub-regiões, Pineau's two island denominations). Not pinned, each read:
  Clairette du Languedoc's vin de liqueur is 9 to 40 g/l of sugar; Setúbal
  and Carcavelos state no sweetness word (an analytical table, a 150 g/l
  ceiling); Douro's Moscatel is muted "de acordo com o grau de doçura
  desejado"; Algarve names "vinhos licorosos brancos doces" beside "brancos
  secos" and Graciosa "entre o seco e o meio doce" — the PT reader's job.
- **Sweet, dessert, ice and straw wine are not a late harvest.** Sweet and
  dessert wine words map to `sweet`, ice wine to `icewine`, straw wine to
  `vin-de-paille`, a wine of dried grapes to `raisin-wine`, the berry
  selections to `grains-nobles`; `vendanges-tardives` only for a late harvest
  the text names (pozna trgatev, késői szüret, neskorý zber, kasna berba,
  cules târziu, όψιμη συγκομιδή …).
- **Rosé comes from the text, never from a berry** (NL / BE / SK / HU / BG in
  phase B; GB and MT in phase C — the DEFRA specs state their colours only in
  their analytical limits, "white and rosé wines", which `gb.spec` keeps as an
  `analytical` role; the RO caiet backstop since 2026-10-25, which had made a
  rosé of Traminer roz and Pinot gris on three ONVPV records).
- **Romanian colours are read as a list sharing one noun (2026-10-25)** —
  `document_unic.colour_styles`: "Vinuri albe, roze", "vinurile albe și
  roze", "Vinuri albe/roze", "la vinurile roșii, roze, aromate", the cedilla
  letters older documents print folded to the comma ones ("Vinurile liniştite
  roze") — and the practices section's yield table counts ("producție de vin
  - vinuri roșii, roze"; Dealurile Sătmarului and Dealurile Zarandului state
  their rosé nowhere else) — and the link section, sub-sections included
  ("8.2 Detalii privind produsul": Coteşti's "Vinurile roşii au culori
  intense"; a description that is a per-variety list, "Fetească neagră – …
  culoare roşu violet", never writes "vinuri roșii", and once the yield
  table stated white and rosé the grape-colour floor switched off and the
  card lost Red — the trap the style-floor rule names, caught on the record
  diff of the closing build). Twelve RO records gained the rosé their text
  states (the seven the phase H re-grade named, and Coteşti, Dealurile
  Moldovei, Dealurile Vrancei, Odobeşti, Recaş); Coteşti keeps its Red and
  Dealurile Crişanei states its white and red from the link.
- **Greek colour words are matched as tokens beside a wine word** — or at the
  head of a list of colours sharing one ("για ερυθρούς και 10% vol. για
  λευκούς και ερυθρωπούς οίνους") — in all four GR / CY parsers
  (`gr.eniaio_engrafo.colour_styles`); the EU-OJ ones had matched substrings.
  The sparkling words likewise, in any inflection and case, with a wine word at
  most two tokens before or three after (`sparkling_type_styles`: "Οίνος
  λευκός ημιαφρώδης ξηρός", "ημιαφρωδών οίνων", "ΟΙΝΟΣ ΗΜΙΑΦΡΩΔΗΣ"); a
  mention with no wine word beside it is no type.
- **A sweetness level the disciplinare states crosses to a non-stub IT card
  (2026-10-24).** Marsala's first single document (C/2026/5127) gives its
  sugar thresholds without the words secco / semisecco / dolce, while the
  MASAF disciplinare's Article 6 names them; stage 04 fills only empty fields
  of a non-stub record, so the card had lost Dry and Sweet when it stopped
  being a stub. `_backfill_it_nonstub_from_masaf` now adds the sidecar's
  `SWEETNESS_STYLES` (dry / semi-dry / semi-sweet / sweet) when the record
  carries none of the four — colours and categories stay the EU document's,
  and a record whose EU document states one level keeps it (Maremma
  Toscana, Val d'Arno di Sopra and Venezia state "secco", so their Art. 6
  dolce does not cross). Four records take a level — Marsala and Valcalepio
  dry + sweet, Falerio and Rosso Piceno dry — but `dry` is a generic leaf
  stage 04 never renders (`_DROP_STYLES`), so the visible change is the
  Sweet pill on Marsala and Valcalepio; `masaf_sweetness` on the record,
  the MASAF provenance in its sources. The 128 non-stub sidecars were
  re-extracted the same day (`02f --all --include-nonstub`: Article 6 kept
  on all 128, 25 sidecar style lists changed, two rosters — Castelfranco
  Emilia's annex Malvasia di Schierano, Vicenza's Raboso).
  `tests/test_it_nonstub_sweetness.py`.
- **Slovak colours listed sharing one noun, or after "Farba:"** —
  `jednotny_dokument.colour_list_styles` (2026-11-07): "Farba: biela, ružová
  a červená", "biele, ružové a červené vína"; never the EU sulphite ceilings
  ("najviac 150 mg/l pre červené a 200 mg/l pre biele a ružové vína").
  Stredoslovenská gained its White; Vinohradnícka oblasť Tokaj's two sekt
  types ("Sekt V. O.", "Pestovateľský sekt") state "biela, ružová a červená"
  in their own organoleptic description, so the card gained Red and Rosé —
  the text's statement, not a guess.
- **The floor reads the declared categories** ([scripts/_lib/wine_categories.py](scripts/_lib/wine_categories.py)).
  A wine without a colour style gets white / red from its grapes' berry colour,
  except a record that declares sparkling categories only (Crémant d'Alsace,
  Franciacorta, Vlaamse mousserende kwaliteitswijn — a noir grape makes a blanc
  de noirs; their colours are the ones their text names, or none). A record
  that declares still wine keeps the floor's red even when every style it
  states is sparkling (Dealu Mare); the old styles-based guess (drop red when
  every style is sparkling) stays only where no category list is declared. The
  BE reader's own grape fallback follows the same rule. `audit_styles.py`
  mirrors the floor and counts sparkling styles without a colour as by design.
  A stated colour switches the floor off, so a reader that starts stating one
  colour can take away the others the floor supplied (Prosecco's newly read
  Rosé had hidden its White): before a build, diff every card's styles, not
  only the sidecars — a stage-04 load + augment + style-chokepoint run without
  geometry does it in a minute.

## Grape tooltips: the article must be the pill's own

Stage 02b accepts a Wikipedia article when it is about *a* grape
(`is_grape_summary`), not when it is about *this* one, and an `ok` cache
entry is never re-fetched. Boris's question on Manzanilla de Sanlúcar
(2026-11-13: its Palomino and Palomino Fino pills opened one extract, the
bare one beginning "Palomino Fino is …") turned out to be one case of three
([scripts/_lib/grape_wiki_identity.py](scripts/_lib/grape_wiki_identity.py)):

- **A match made through a VIVC passport the slug no longer has**
  (`passport_match_is_stale`): the article was found by the passport's prime
  name, a synonym or a donor slug of the same number (`matched_via`
  `vivc-prime` / `vivc-synonym:*` / `shared-vivc:*`), and the slug's pin was
  corrected or withdrawn since. Pugnitello (pinned `false` on 2026-10-25)
  still opened the Montepulciano article on 53 pills, Tijonera Tempranillo,
  Picardan (now #527) Bourboulenc in Dutch; 13 slugs in the four UI locales.
  Stage 04 withholds such an entry (`_load_native_grape`), and a translated
  extract whose source entry is stale, missing or another title
  (`_translation_source_stands`); the 02b fetcher treats it as due
  (`_cache_is_fresh`) and never uses it as a donor. A match by the slug's own
  title (`primary`, a legacy entry) or a curator pin (`override`) is never
  stale by this rule, and a slug with no resolution and no withdrawn pin
  keeps its entry — a gap, not a decision. The 13 were re-fetched the same
  day (`--only`, four locales): wrong articles gone, Blanca de Monterrei,
  Bonicaire (fr), Mollard (nl) and Picardan (nl) on their own.
- **A name Wikipedia redirects to another cultivar** (`article_is_anothers`):
  the article's title is none of the slug's own names (slug, VIVC prime and
  synonyms, or the family its name extends — "Grenache" for grenache-gris)
  and is the slug or prime of another slug with a different number.
  Chenanson's synonym VAALBLAAR STEIN is a name of Chenin blanc, Raffiat de
  Moncade's ROUSSELET redirects to Gewürztraminer, Gamay de Chaudenay's PLANT
  GRIS to Aligoté, "Mollard" to Carignan. The fetcher rejects such a
  candidate on every route but `override` and records
  `error: other_cultivar_article`, so no new entry of the kind is cached; the
  existing ones were read one by one the same day
  ([docs/grape-wikipedia-redirects-2026-11-14.md](docs/grape-wikipedia-redirects-2026-11-14.md):
  the two VIVC passports, the article's own text, the rosters): of 108
  entries 9 are right (a colour mutation under its parent's article —
  Sauvignon gris, Lledoner pelut — or a family article naming the member), 72
  wrong (VIVC gives different parents or colours, the article says the two
  differ, or it never names the pill) — pinned `null` per (slug, language) in
  `raw/wikipedia/grape_overrides.json`, a pin that now takes effect on a
  cached article without `--refresh` (`_null_pin_unapplied`) — and 27
  unsettled (the article lists the name as its subject's while VIVC keeps two
  passports with nothing to tell them apart; a checklist in CURATOR_TODO). A
  hit is not a verdict: Vinhão's "Sezão" article itself says the two "are two
  distinct varieties".
  [scripts/audit_grape_wikipedia.py](scripts/audit_grape_wikipedia.py) lists
  STALE-PASSPORT / OTHER-CULTIVAR (96 slugs on 2026-11-14) / UNVERIFIED (73:
  a title none of the slug's names and no other slug's — a local name, a
  family article or another wrong binding), report only; a wrong one is fixed
  by a title or `null` pin in `raw/wikipedia/grape_overrides.json` and a
  `02b_fetch_grape_lexicon.py --only SLUG` run.
- **A name under two primes whose article describes one of them.** The bare
  `palomino` is pinned `false` (VIVC files the name under Palomino Fino #8888
  and under Palomino de Jerez #8887, "PALOMINO FINO MUTATION", passports read
  live 2026-11-14), and Wikipedia's Palomino article is Palomino Fino's. The
  curator-note table of the page emitter (`_GRAPE_NOTES` / `apply_grape_notes`
  in map_template.py, the Bianchello precedent) gives the bare pill a note
  that *replaces* the article ("The VIVC catalogue files the name Palomino
  under two varieties …", `palomino_note`, sources VIVC #8888 and #8887); the
  article stays on the Palomino Fino pill. 22 cards carry the bare pill, four
  both (Jerez, Manzanilla, Lebrija, Villaviciosa de Córdoba). The single
  documents list "PALOMINO" and "PALOMINO FINO — LISTÁN BLANCO" as two rows;
  no public text read so far names the bare one, so its identity is not
  pinned.

`tests/test_grape_wiki_identity.py`.

## Grape roles from the EU register fiche

Where a national source lists its varieties without a principal / accessory
split — the SI MKGP `.doc` and the 2007 pravilnik's PGI roll-up, the SK ÚPV
§ f table, the HU termékleírás and single documents, the BG ИАЛВ spec, the
GR ΥΠΑΑΤ spec and single documents, the RO caiet and single documents, MT,
HR — every variety read "principal" on the card. Since 2026-10-23 (validator
phase E, decision B) [scripts/_lib/augment/fiche_roles.py](scripts/_lib/augment/fiche_roles.py)
gives those records the roles of the EU register's technical file
(`raw/<cc>/register-fiches-extracted/`, `extract_register_fiches.py`): a
variety the fiche tags MAIN (named in the single document) is principal,
OTHER (the rest of the product specification's authorised list) accessory,
and a card variety the fiche does not list — added to the national roster
after the state's filing, not a main variety then — is accessory and counted
on the card's source line ("Grape roles (EU GI register, single document,
PDF) — 11 principal, 19 accessory per the single document · 2 added to the
national roster since, shown as accessory"; `src_register_fiche_roles*`
labels, `register_fiche_roles_*` source keys, `_REGISTER_FICHE_ROLES_BY_SLUG`,
the record's `register_fiche_roles`). **Membership stays the national
roster** — the newer, legally binding list — and the overlay needs the fiche
to cover at least 80 % of it (`COVERAGE_MIN`): a fiche of another vintage
(Somlói's names 5 varieties where the termékleírás names 43, Sopron's 23
against 44, Duna-Tisza közi 41 against 67) would otherwise demote the national
list wholesale; it is skipped and logged on the `[load] register-fiche
roles` line. A record whose national source splits roles itself (Bela
krajina's pravilnik, the GR 15 % caps) is left alone, CZ keeps its own rule
(the fiche *is* the roster where it is narrower than the decree), and HR's
fiches carry no split. The RO yield-table split is not a role statement — a
variety §7 omits and the yield table names is accessory by that rule only —
so since 2026-10-25 (decision on the phase H re-grade) the fiche roles apply
there too, and a yield-table variety the fiche tags MAIN is listed under the
principal pills in an amber line: "Roles follow the EU GI register's single
document, which names Merlot as a main variety; the single document published
in the Official Journal lists it only in its yield table"
(`register_fiche_roles_yield_conflict` in the sources, `role_conflict_yield_*`
labels, `_role_conflict_line` / `roleConflictLine`). Four records: Coteşti,
Dealurile Olteniei, Drăgăşani, Ştefăneşti (Lechinţa and Sebeş-Apold stay
under the coverage gate). The overlay runs after
every national-spec augmenter, so it sees the merged roster; the card judge
reports a fiche-only split as `defective` only where it is still missing.
First build (2026-10-23): 134 records, 1,616 varieties to accessory, 61
of them not listed by the fiche; 18 fiches skipped for coverage, 6 national
splits kept, 163 fiches without a split; no roster changed membership. The
re-judge of the four cards the validator had flagged took their 13 misleading
findings to 5, none of them about roles on a fiche-governed card (Bela
krajina keeps its pravilnik split and the judge's disagreement with it).
`tests/test_fiche_roles.py` pins the gate, the flips, the unlisted count and
the skips.

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
twice with no changes upstream must be a no-op (cache hits). Stage 02's
`--only NAME` (repeatable substring) re-extracts just the matching records and
merges their entries into `_index.json`; it never rewrites the unselected
records (a partial run used to stub the whole corpus). Every other country's
stage 02 writes its index through `write_index` / `is_partial` in
[scripts/_lib/extract_index.py](scripts/_lib/extract_index.py) (2026-10-22): a
`--only` / `--limit` run merges its entries into the index on disk —
`it/02 --only piemonte` had left a 7-record `_index.json` for a 524-record
corpus (stage 04 reads the per-record files and did not notice; stage 03 and
the coverage audits read the index); PT merges its `by_slug` map and recounts
its envelope; `tests/test_extract_index.py` lints the wiring. A parser change
that touches many records still wants a full run. Stage 03 is the same one
level up (2026-10-24): all 21 generators merge into the shared
`wiki/_index.json` through `wiki_index_kept` (same module) — a full run
replaces its country's entries, a `--only` run only the selected ones, and the
FR `--only` run leaves `wiki/index.md` / `log.md` alone. Until then `03
--only collioure` left one French entry of 1,541; stage 04 does not read the
index, but the untranslated detector's appellation-name exemption and
`terroir_roster` (the dedupe pass, the 02d / 02e prompts) do — the detector
went from 307 to 413 flagged pairs on "Alsace", "Bourgogne" inside
appellation names.

| Script | Reads | Writes |
|---|---|---|
| 00_fetch_data.py | (network) | raw/inao/siqo-referentiel.csv, raw/ign/communes.geojson, raw/ign/communes-associees-deleguees.geojson, raw/insee/v_mvt_commune.csv, raw/inao/parcellaire/*.shp, raw/cadastre/lieux-dits/*.json.gz |
| 01_scrape_cahiers.py | raw/inao/siqo-referentiel.csv + scripts/_lib/fr/siqo_supplements.json + raw/inao/cahiers/manual_overrides.json + raw/inao/register/resolved.json | raw/inao/cahiers/*.pdf, raw/inao/cahiers/manifest.json, raw/inao/register/{cahiers/*.pdf,manifest.json} |
| 01d_resolve_register.py | raw/inao/cahiers/manifest.json (or raw/inao/siqo-referentiel.csv + scripts/_lib/fr/siqo_supplements.json) + raw/eambrosia-register/gi-index.json + scripts/_lib/fr/register_overrides.json | raw/inao/register/{resolved,unresolved}.json |
| 02_extract_cahiers.py | raw/inao/cahiers/*.pdf + raw/inao/siqo-referentiel.csv + scripts/_lib/fr/siqo_supplements.json (+ the previous _index.json for the drop guard) | raw/inao/cahier-extracted/*.json + _index.json |
| audit_fr_register_shadow.py | raw/inao/cahiers/manifest.json + raw/inao/cahier-extracted/ + raw/inao/register/resolved.json | raw/inao/register/{shadow-report.json,shadow-report.md,cahiers/*.pdf,manifest.json} |
| 02b_fetch_grape_lexicon.py | raw/inao/cahier-extracted/*.json + raw/vivc/by-slug/ | raw/wikipedia/grapes/<lang>/*.json + manifest.json |
| 02b_fetch_aoc_lexicon.py | raw/inao/cahier-extracted/*.json | raw/wikipedia/aocs/fr/*.json + manifest.json |
| 02b_fetch_style_lexicon.py | raw/wikipedia/style_overrides.json | raw/wikipedia/styles/<lang>/*.json + manifest.json |
| 02b_translate_styles.py | raw/wikipedia/styles/<lang>/*.json | raw/translations/styles/<lang>/*.json + manifest.json |
| 02b_translate_grapes.py | raw/wikipedia/grapes/<lang>/*.json + grape-corpus dominant-lang | raw/translations/grapes/<lang>/*.json + manifest.json |
| 02c_translate_summaries.py | raw/inao/cahier-extracted/*.json | raw/translations/summaries/<lang>/*.json |
| 02d_extract_terroir_facts.py | raw/inao/cahier-extracted/*.json + raw/wikipedia/aocs/fr/ + raw/terroir-facts-feedback/*.json (optional) | raw/terroir-facts/*.json + manifest.json |
| 02e_translate_terroir_facts.py | raw/terroir-facts/*.json | raw/translations/terroir-facts/<lang>/*.json |
| recompute_terroir_provenance.py | raw/terroir-facts/*.json + each country's 02d source resolver | raw/terroir-facts/*.json (coverage + provenance, in place) + raw/translations/terroir-facts/<lang>/*.json (provenance) |
| dedupe_terroir_facts.py | raw/terroir-facts/*.json + wiki/_index.json + wiki/data/aocs.en.*.js (sub-denomination roster) | raw/terroir-facts/*.json (facts pruned, `n_deduped`) + raw/translations/terroir-facts/<lang>/*.json (same indices pruned, `source_facts_sha` updated) |
| normalize_terroir_facts.py | raw/terroir-facts/*.json + raw/translations/terroir-facts/<lang>/*.json | same files (bullets normalised in place, translation caches re-keyed) |
| filter_terroir_boilerplate.py | raw/terroir-facts/*.json | raw/terroir-facts/*.json (facts pruned, `n_boilerplate`) + raw/translations/terroir-facts/<lang>/*.json (same indices pruned) |
| build_terroir_feedback.py | a review evidence dir (`confirmed-misleading.json`, `merged.json`) + raw/terroir-facts/*.json (graded-against shas) | raw/terroir-facts-feedback/<slug>.json + manifest.json (merged, never overwritten) |
| 02d_verify_terroir_facts.py | raw/terroir-facts/*.json + each country's 02d source resolver + raw/terroir-facts-feedback/*.json | raw/terroir-facts/*.json (facts gated, `support` per fact, `gate` block) + raw/translations/terroir-facts/<lang>/*.json (pruned / re-keyed `pending:`) + feedback `history` + manifest-gate.json + tmp/terroir-facts-review/gate-<run>.json |
| 02e_verify_terroir_facts.py | raw/translations/terroir-facts/<lang>/*.json + raw/terroir-facts/*.json + raw/terroir-facts-feedback/*.json | raw/translations/terroir-facts/<lang>/*.json (fixed bullets, `check` per fact, `backcheck` block) + feedback `history` + manifest-backcheck.json + tmp/terroir-facts-review/backcheck-<run>.json |
| rerun_terroir_facts.py | a scope (slug list) | raw/terroir-facts-backup/<run>/ (snapshots) → the chain above; logs /tmp/owm-<run>/ |
| rollback_terroir_facts.py | raw/terroir-facts-backup/<run>/ | raw/terroir-facts/*.json + raw/translations/terroir-facts/<lang>/*.json (restored / deleted) |
| audit_terroir_facts_llm.py | raw/terroir-facts/ + raw/translations/terroir-facts/en/ (or a backup run) + each country's 02d source resolver | tmp/terroir-facts-review/llm-audit-<stamp>.json (read-only) |
| 02g_fetch_vivc.py | raw/inao/cahier-extracted/*.json + raw/es/pliegos-extracted/ + raw/pt/cadernos-extracted/ + raw/vivc/slug_overrides.json | raw/vivc/{search,passport,by-slug}/*.html\|json + manifest.json + slug_overrides.example.json |
| 02i_fetch_wikidata_qids.py | raw/*/*-extracted/*.json (slug + id_eambrosia) + raw/wikipedia/aocs/<lang>/ + raw/wikidata/slug_overrides.json | raw/wikidata/qids-by-slug.json + p9854.json + manifest.json + slug_overrides.example.json |
| 03_generate_wiki.py | raw/inao/cahier-extracted/*.json + raw/terroir-facts/ | wiki/*.md, wiki/_index.json |
| audit_grape_wikipedia.py | raw/wikipedia/grapes/<lang>/*.json + raw/vivc/by-slug/ + raw/vivc/slug_overrides.json + the extracted corpora (grape slugs) | (stdout — grape tooltips whose article is not the pill's: STALE-PASSPORT / OTHER-CULTIVAR / UNVERIFIED, report only; `--langs`, `--all`, `--json PATH`) |
| audit_empty_grapes.py | wiki/data/aocs.en.*.js + wiki/data/d/en/*.json + scripts/_lib/empty_grapes_overrides.json | (stdout — FLAGGED / INHERIT / REVIEWED / STUB / NON-WINE buckets; `--strict`, `--json PATH`) |
| audit_aires_vs_cahier.py | raw/inao/cahier-extracted/*.json (zone sections) + raw/inao/aoc-aop-aires-communes.csv + igp-aires-communes.csv + scripts/_lib/aires_supplements.json + raw/ign/communes.geojson + communes-associees-deleguees.geojson + raw/insee/v_mvt_commune.csv | (stdout — per French parent: communes the cahier lists that INAO's rows lack, classed whole / partial / unclear; rows the zone text does not name; neighbouring codes; OK / PINNED / NEW / UNCLEAR; `--drinks`, `--bare`, `--emit-pins PATH`, `--strict`, `--json PATH`) |
| audit_parcellaire_gaps.py | raw/inao/parcellaire/*.shp (attribute table, cached to raw/cache/parcellaire-coverage/) + scripts/_lib/parcellaire_carry_forward.json (+ its extracts) + raw/inao/aoc-aop-aires-communes.csv + raw/ign/communes.geojson + raw/inao/cahier-extracted/*.json + scripts/_lib/parcellaire_gap_fills.json | (stdout — aire communes without a parcel row per parcellaire record, classed; gap-fill pins and carried-forward rows APPLIED / STALE; `--strict`, `--json PATH`) |
| extract_parcellaire_carry_forward.py | raw/inao/parcellaire/<release>_delim-parcellaire-aoc-shp.shp | scripts/_lib/parcellaire_carry_forward/<label>-<release>.geojson.gz (rows of one appellation or denomination, unchanged) |
| 04_build_maps.py (`--shell-only`: re-emit from raw/cache/stage04-shell-snapshot.pkl) | raw/inao/cahier-extracted/*.json + raw/wikipedia/grapes/ + raw/translations/grapes/ + raw/vivc/by-slug/ + raw/wikidata/qids-by-slug.json + raw/wikipedia/styles/ + raw/translations/styles/ + raw/wikipedia/aocs/ + raw/translations/summaries/ + raw/translations/terroir-facts/ + raw/terroir-facts/ + raw/ign/communes.geojson + raw/inao/parcellaire/ + raw/cadastre/lieux-dits/ | wiki/index.html (EN canonical = homepage), wiki/{fr,es,nl}/index.html, wiki/{en,fr,es,nl}/<slug>/index.html (per-appellation entity pages), wiki/{en,fr,es,nl}/appellations/index.html (browse-index hub linking every indexable slug, grouped by country — fixes the entity-page link-graph orphan problem), wiki/map-data/*.pmtiles, wiki/robots.txt, wiki/sitemap.xml (4 home + 4 browse + 1,638 index slugs × 4 locales), wiki/llms.txt (AI-crawler index), wiki/404.html, the files of scripts/_lib/site_root/ (search-console verification pages) |

### Stage 04 `--shell-only`

A template, JS, CSS or catalog change re-renders every page (hashed asset
names, and every page embeds the sidebar server-side), but nothing the page
emitter *consumes* has changed. The emitter reads the two feature lists —
their properties only; the geometry is tiled, never rendered into a page —
and 28 runtime caches that main() fills while loading, augmenting and
resolving the records (`_shell_state()` in 04: the local `*_BY_SLUG`
dicts, those of `_lib/augment/_shared.py`, the two ES provenance dicts of
`_lib/geom_chain.py` — the first shell-only run lost the Galician records'
IET attribution without those — and, since 2026-11-13, `_FR_PRODUCT_NAMES`:
the French record names by product class, which both paths register with
the aire resolver's spirit guard, `aires.register_product_names`. That
guard is module state the emitter's region-alias derivation reads through
`lookup_aire`; a shell-only run without it gave Fine du Languedoc a wine's
aire and dropped its Roussillon alias — found because the four MCP context
files came out 34 bytes smaller than the full build's. State the emitter
reads that is neither a feature property nor in this map is a shell-only
bug waiting; compare the `[mcp]` byte counts of the two logs). Every
full build pickles exactly those at the emit boundary
([scripts/_lib/shell_snapshot.py](scripts/_lib/shell_snapshot.py) →
`raw/cache/stage04-shell-snapshot.pkl`, a raw cache), and
`04_build_maps.py --shell-only` restores them in place (the augmenters,
`_sources_for()` and the emitter hold the same dict objects) and calls the
emitter — pages, bundles, panel JSON, MCP context, sitemap, llms.txt, 404,
robots — skipping the minutes the full build spends producing identical
inputs. The tile fingerprints (`?v=`) are recomputed from the pmtiles on
disk. The snapshot is valid for the shell files (`SHELL_PATHS`:
map_template.py, content_block.py, assets/, vendor/, i18n.py, gi_terms.py
and the curated JSON tables the emitter reads; the locale catalogs are
compiled by the emitter itself); the flag warns, file by file, when any
other file under `scripts/` or an extracted-corpus `_index.json` is newer
than the snapshot — a change to a record or its geometry needs a full
build. Without a snapshot the flag exits 2. `tests/test_shell_snapshot.py`
pins the round trip, the in-place restore, the staleness check and the
wiring; the proof of equivalence is the golden comparator: a shell-only run
after a full build must produce byte-identical output.

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
published inline as HTML and reachable via the GI's newest OJ C
publication (after Spanish-language URL rewrite — `/oj/spa`,
or `legal-content/ES/TXT/HTML/?uri=…SPA`). **Which publication, in every
EUR-Lex country** ([scripts/_lib/oj_publications.py](scripts/_lib/oj_publications.py),
2026-10-24): eAmbrosia lists publications untyped and unordered, and "the
first OJ C listed" had left 45 records on a superseded single document
whose own list named the newer one; every stage 01 / 01b now takes the
newest non-corrigendum OJ C by the date the register prints (else the ELI
/ Formex number), corrigenda and OJ L after it. `amendmentsInProgressFlag`
does not choose: an approved standard amendment is followed by no OJ L, so
only the document's heading tells an application under opposition from an
amendment in force (the ten flagged records of 2026-10-24 were all
approved standard amendments). A newest OJ C that carries no single
document — a cancellation request (Ambt Delden's C/2025/6054), a temporary
amendment — is pinned per record in `raw/<cc>/oj-pages/manual_overrides.json`.
The 2024/1143 template ends on "11. Otros requisitos aplicables" (GR
"Περαιτέρω εφαρμοστέες απαιτήσεις", BG "Други основни условия", RO "Alte
cerințe specifice"): each reader recognises it, or the link section runs
into it and the EUR-Lex footer. Both the older
`ti-grseq-1` (sections 1–9) and newer `oj-ti-grseq-1` (sections 1–10)
templates are parsed; semantic role routing by Spanish title keyword
(`zona geográfica`, `vínculo`, `variedad`) keeps downstream consumers
indifferent to which template a given page used. **The slicer keeps the
template's own titles** (`_template_headers`, 2026-11-08, visitor flags on
Bullas): the description nests one numbered header per wine type ("1. Vino
blanco … 5. Vino espumoso aromático de calidad blanco", Valencia) and the
categories section lists its items the same way, and read last-wins those
headers shadowed the real sections — 85 of the 90 EUR-Lex records had no
categories section, Valencia's sparkling type sat under a "5" that "5.
Prácticas vitivinícolas" overwrote, Montsant's `description` role was its
link text. A top-level header is a section when its title is one of the
template's (`_TEMPLATE_TITLE_KEYWORDS`; never a title opening on "vino"),
its number higher than the last section's; a sub-number belongs to the open
section; everything else stays in the body, where `parse_styles_es` reads
the numbered type lines as the titles they were (`_NUMBERED_TITLE_LINE_RE`:
"4. Rías Baixas Tinto", "3. Vinos generosos (categoría 1)"). The same day the
style reader learnt the types a national pliego states once with the word
"vino" — the type-list sentence ("son los siguientes: blancos, rosados,
tintos, de licor y espumosos"; `_TYPE_LIST_SENTENCE_RE` + `_TYPE_PHRASE_PATTERNS`),
a dash- or Wingdings-bulleted "- Vino de licor" line, the EU category cited
by number ("a la categoría 3 "Vino de licor"", "de la categoría 5: espumosos
de calidad") or listed ("Categorías de productos vitícolas: vino, vino de
licor, …"), and a type as a capitals heading of the link section ("VINO DE
LICOR") — and the roster reader three things: the singular "principal:"
header (`principales?` never matched it, so Valtiendas' Tempranillo kept the
accessory role of the line before), "secundarias" as the accessory list
(Castilla y León's 40), and the sentence after the roster that names the
principal varieties (`_apply_principal_designation`: "se considera como
principal la Monastrell en tintas y la Macabeo entre las blancas" — Bullas,
Lebrija, Málaga's "las «Moscateles»", Valle del Miño-Ourense's list form),
the rest becoming accessory; a name opened with « and wrapped over the line
continues ("«Pero ⏎ Ximén»"), a roster token splits at a sentence end before
a capital, a guillemet name is read out of an introductory sentence, and
after " o " an alternative that binds another cultivar ("Picapoll Blanco o
Extra" — EXTRA is a Clairette synonym) is the pliego's synonym, not a pill.
Full run against the snapshot: 91 records changed, no section shorter, 46
style lists grew (29 parents), 8 rosters changed roles or membership.
`tests/test_es_roles_and_types.py`. Section 9 (older)
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
A subzona reads its DO's pliego (2026-10-04: Rioja Alta had lacked the
Malvasía the Rioja pliego adds), and where the pliego names a subzona's
principal varieties — Vinos de Madrid's "Principales Subzona de Arganda —
Blancas: Malvar. — Tintas: Tinto Fino (Tempranillo)." — those are its
principal grapes and the rest of the DO's roster its accessory
(`_apply_subzona_principals`). Rías Baixas' ≥ 70 % rules for its white
subzona labels (a three-column table) are not read yet; the other
subzonas (Rioja, Ribeira Sacra, Monterrei, Costers del Segre, Alicante,
Valencia) are named only for their area and terroir.

Re-runnable per slug or in sweep mode:
```
uv run scripts/es/02f_extract_national_pliegos.py --slug mentrida
uv run scripts/es/02f_extract_national_pliegos.py --all
```
Cached PDFs at `raw/es/national-pliegos/<slug>.pdf` are reused unless
`--refresh` is passed.

**The pliego's §7 vínculo grounds the terroir facts of a summary-only
record (2026-10-24).** A single document on the 2024/1143 template carries
only a "Resumen del vínculo" (540–760 characters on the four records that
left their MAPA pliego for it in phase F; 50 ES parents carry a summary or a
link under 1,000 characters), while the national pliego's "7. VÍNCULO CON
LA ZONA GEOGRÁFICA" is the full text. `parse_link_section` in
[scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py)
reads it (the heading forms of 57 of the 60 cached PDFs — "7) VÍNCULO …",
"7.- Vínculo …", "7. Vínculo con el medio", "G. VÍNCULO ENTRE …", "6.-
Vínculo existente entre …"; the body ends at the next heading of the same
kind or a post-link title, a lettered sub-item or a prose line opening on a
number never ends it, page furniture dropped; Pla de Bages' bare "Vínculo",
Catalunya and Condado de Huelva have none) and stage 02f writes it to the
sidecar as `link_to_terroir`. ES 02d's `_resolve_lien_and_source` and stage
04's `_carry_link` prefer it under the shared rule of
[scripts/_lib/summary_link.py](scripts/_lib/summary_link.py)
(`prefer_national_link`): the OJ lien `is_summary_link` (the "Resumen del
vínculo" / "Sintesi del legame" marker in its head, or under 1,000
characters) and the national text is at least 1.5× longer and at least
1,000 characters — a text of the same size under a template heading never
replaces the EU one. 48 records (29 parents, their subzonas with them —
Rioja, Cava, Rías Baixas, Ribeiro, Monterrei …) now ground on the national
text, the cache carrying `cahier_source_kind: national-pliego` and the PDF
as `cahier_source_pdf_url` (the card's footer attribution), the record
`national_pliego.link_used`. The former MAPA pliegos of 3 Riberas and Pago
de Otazu are pinned in `manual_overrides.json`. The same rule serves Italy
(the MASAF Article 9 against a "Sintesi del legame", see the IT 02d note).
`tests/test_es_national_pliego_link.py`, `tests/test_summary_link.py`.

When the doc-único's section-9 URL is dead (404, GVA backend timeout,
BOE-modification-not-pliego, pdftotext-broken PDF), the curator pins a
working replacement in `raw/es/national-pliegos/manual_overrides.json`
(slug-keyed: `{pliego_url, source_org, verification_note}`). Stage 02f
checks this file before the section-9 URL and takes precedence; when an
override is present the slug-keyed PDF cache is invalidated automatically
if the existing sidecar's `source.url` disagrees with the override
(or if no sidecar exists at all, since the cache vintage is unknown).
Mirrors the FR pattern at `raw/inao/cahiers/manual_overrides.json`.
Since 2026-10-24 (phase F): a link labelled as the pliego wins over the
first PDF of the section (Condado de Huelva's document cites a map of its
pagos first); a section-9 URL on a host that moved is relocated
(`_RELOCATED_PREFIXES`: JCCM's `pagina.jccm.es/agricul/…` →
`ficheroscomunes.castillalamancha.es/agricultura-dop/`) and a cached PDF
whose sidecar URL disagrees is re-fetched; an `SSLError` falls back to
curl (Python's certifi lacks the intermediate certificate
`www.mapa.gob.es` serves). INCAVI moved its files from
`.content/005-normativa/…` to `content/dam/incavi/home/normativa/plecs-de-condicions-de-les-do-catalanes/<do>/`
while every Catalan single document still cites the old path: the nine
Catalan DOs (Cataluña, Conca de Barberà, Costers del Segre, Empordà,
Montsant, Penedès, Pla de Bages, Priorat, Tarragona) are pinned on the new
location. A 2024/1143 single document lists every authorised variety, so
for those records the sidecar adds no pill — it is the cited source; ten
records find no PDF at all (Arlanza cites ITACyL's listing page).

### ES geometry resolution chain (stage 04)

Per ES record, in priority order (each step records the chosen source
in `geom_source` so the panel can attribute correctly):

1. **`sigpac-pliego-inclusions`** — for wines whose pliego enumerates
   SIGPAC polygon inclusions inside one or more municipios (Priorat ↔
   Montsant: `Falset: polígonos números 1, 4, 5, 6, 7, 21 y 25 enteros`;
   Sierra Sur de Jaén: `Martos (polígonos catastrales actuales del 33 al
   42)`). Resolved by `scripts/_lib/es/pliego_parcels.py` +
   `scripts/_lib/es/sigpac.py` against SIGPAC vineyard parcels from two
   publications, both fetched by stage 00: Catalonia's per-comarca
   GeoPackages (`SIGPAC_COMARCA_CODIS` + `sigpac_catalonia_urls.json`;
   the Priorat comarca) and, since 2026-09-24, FEGA's national
   per-province download (`sigpac-hubcloud.es`, CC BY 4.0 —
   `sigpac_fega_urls.json`; the 456 MB Jaén zip is sha-pinned and a
   per-municipio extract is what the loader reads; `_fega_frame_as_catalan`
   maps the FEGA schema onto the Catalan column set so the loader is
   shared). Add a province or comarca by editing the catalogue. Parcel
   precision — runs first, ahead of the official MAPA zone, **but only
   when at least one inclusion actually resolves against loaded SIGPAC
   data**: a pliego whose polígonos sit in an unfetched province falls
   through to the zone / commune-list resolvers instead of shipping a
   whole-commune union labelled parcel-precise (Arribes and Tarragona did,
   before the gate). A listed polígono is read one of two ways,
   pinned per record in `SIGPAC_INCLUSION_SEMANTICS`
   ([scripts/_lib/es/sigpac.py](scripts/_lib/es/sigpac.py)): **`footprint`**,
   the default — the cadastral polígono *is* the delimited area, any plot
   planted inside it qualifies, so every recinto of it (any land use) is
   dissolved and drawn (Sierra Sur de Jaén: the 34 listed polígonos hold
   no registered vineyard per SIGPAC 2026, 0 ha in Alcaudete and 0.14 ha in
   Martos; the vineyard reading drew four plots, the footprint reading
   draws 98.7 + 33.2 km² and the record is one 862 km² polygon) — and
   **`vineyard`**, the original 2026-05 design (recintos in use `VI` only),
   which no record uses since 2026-09-24: Priorat and Montsant moved to the
   footprint reading by the same logic (Priorat 150.9 → 167.1 km², Montsant
   297.8 → 317.8 km², each one polygon instead of 354 / 373 vineyard
   patches; Montsant's Falset 17/18 → 18/18). The table stays for a pin
   whose reason the pliego's own wording supports. Every
   `sigpac-hybrid-pliego` record now discloses its reading in the panel's
   area line (`geom_sigpac_footprint` / `geom_sigpac_vineyard` +
   `geom_sigpac_whole`: polígonos found/listed per municipio, the whole
   municipios, and the publication's attribution — FEGA CC BY 4.0, or the
   Generalitat's portal).
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
   commune list. Union the matching GISCO municipios. Two checked-in
   tables keep the list whole (2026-09-24): every GISCO municipio whose
   name carries a conjunction —
   [scripts/_lib/es/compound_municipios.json](scripts/_lib/es/compound_municipios.json),
   74 rows — so "Los Palacios y Villafranca" or "Gimenells y Pla de la
   Font" are not split on the "y" / "i" (the splitter re-joins adjacent
   pieces only when the whole normalised text is one of them), and
   [scripts/_lib/es/municipio_mergers.json](scripts/_lib/es/municipio_mergers.json),
   former municipios a pliego still names bound to the municipio that
   absorbed them (the Pallars agregados → Tremp, Castell de Mur, Gavet de
   la Conca, Isona i Conca Dellà; each with its ca.wikipedia source and
   INE code, taken only inside the provinces the list established). A
   lower-case Galician / Catalan article no longer rejects a name ("a
   Pobra de Trives"), nor the Castilian plurals ("los Villares"), and a
   piece that is only an article is never fused into a compound ("Vielha
   e Mijaran, Les y Bossòst" keeps Les, the one municipio whose whole
   name is an article). A Castilian "ñ" name that GISCO spells with the
   Valencian / Catalan "ny" is retried in that spelling (Valencia
   Valentino's "Picaña" is GISCO's "Picanya", 2026-10-24). In the resolver
   ([scripts/_lib/es/geometry.py](scripts/_lib/es/geometry.py)
   `_reread_out_of_context`, 2026-09-25) an exact hit that is the only
   name in its province while the list established two or more others is
   re-read before it binds — with its spaces closed (Ribera del
   Gállego-Cinco Villas' "Los Corrales" is GISCO's Huesca "Loscorrales";
   the article-stripped key was Sevilla's "Corrales, Los", 636 km away)
   or split on its conjunction ("Toril y Masegoso" between Cáceres and
   Albacete names is Toril + Masegoso) — and accepted only inside a
   province with two or more votes, so a Cava-style list keeps its lone
   municipios.
6. **`gisco-commune-union-subzona`** — for ES subzona DGCs, union
   the per-subzona commune list.
7. **`parent-appellation`** — DGC inherits parent polygon when
   commune matching yields nothing.
8. **`stub-no-geometry`** — wine appears in the AOCS sidebar but no
   polygon (most pre-2014 IGPs).

A refinement runs across steps 3–7 for the Galician records
([scripts/_lib/geom_chain.py](scripts/_lib/geom_chain.py)
`apply_es_parroquias`, since 2026-09-24): where the pliego includes only
named **parroquias** of a municipio ("las parroquias de Iria Flavia y
Padrón, del término municipal de Padrón"; the `- Amoeiro: las parroquias
de …` line form of Valle del Miño-Ourense; the Monterrei holder-first
form), those parishes are drawn from the **IET Mapa de Parroquias de
Galicia** (Xunta de Galicia, 3,785 polygons, EPSG:25829, fetched sha-pinned
by ES stage 00 into `raw/es/xunta/parroquias/`; licence CC BY 4.0 per the
publisher's aviso legal citing Decreto 14/2017 — the licence conflict
with the 2015 PDF bundled in the zip and the abertos CC BY-SA listing is
recorded verbatim in the manifest and in
[GEOMETRY_SOURCES.md](GEOMETRY_SOURCES.md)) and unioned into the record's
commune union. A municipio named only as a parish holder is never kept
whole — it is subtracted from a curator or subzona union that carried it
(Terras do Navia 755 → 242 km²) — and a record with no polygon of its own
becomes `iet-parroquia-union` (the two Monterrei subzonas). A **MAPA zone
drawn at whole-municipio resolution** is treated the same way (2026-09-27,
after a visitor flagged Monterrei's boundary): when every GISCO municipio
the zone touches is covered ≥ 95 % or grazed ≤ 5 %
(`ESPolygonIndex.municipios_covered`), the zone is a commune union in the
ministry's hand and the pliego's parishes are the finer statement of the
same delimitation, so it is redrawn from them — whole municipios from
GISCO, parishes from the IET — and becomes `iet-parroquia-union` with
`zone_superseded` in its provenance. Monterrei's zone was its six
municipios whole (674 km²): seven mountain parishes of Castrelo do Val and
Riós the pliego excludes were drawn (~111 km²) and the six of Cualedro and
Laza that amendment PDO-ES-A1114-AM03 (12 September 2025) added were
missing (~79 km²), so the Ladera subzona spilled outside its parent; it is
now Vilardevós plus 49 parishes, 640 km², one polygon. The redraw needs
the text to account for every municipio of the zone (as a parish holder
or a whole inclusion), to name no unit below the parish — Ribeiro's
"lugares" of Toén and Ourense would turn over-drawing into under-drawing,
so its zone is kept — and every parish to resolve; a zone with a
partially covered municipio is a real delimitation and is left alone,
each kept zone with its reason on the stage-04 log line. Parish names
match on (INE, name) after the `(patron saint)` suffix and articles are
folded; spelling drift is pinned per record in
[scripts/_lib/es/parroquia_overrides.json](scripts/_lib/es/parroquia_overrides.json)
with both spellings, never fuzzy-matched; parts under 1 ha (the 1:5k
coastline's offshore rocks) are dropped. Every record using parish
polygons carries the IET attribution in the panel's area line and its
Sources list (`geom_parroquias_line` / `src_parroquias`); when the same
inclusion list names a municipio whole (Monterrei's Vilardevós beside its 49
parishes) the record's sources carry `parroquias_whole_municipios` and the
line ends with them (`geom_parroquias_whole`, 2026-10-23). Barbanza e Iria:
Padrón is now its two parishes (12.3 of 48.6 km²); Valle del Miño-Ourense
725 → 379 km² (all 14 municipios are holders); Ourense city's Cabeza de
Vaca, Santiago das Caldas and Tras do Hospital are not in the IET layer and
are left out, reported. Cangas (Asturias) names parroquias only in its
terroir prose and is untouched.

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
`file_number` / sections. Their grapes are the parent's unless the
caderno's grapes section has a table under "Sub-região de X"
(`subregion_grapes` in stage 02, 2026-10-04): Vinho Verde's "os vinhos …
com indicação de sub-região devem ser exclusivamente obtidos a partir das
castas enumeradas nos quadros seguintes" — Monção e Melgaço is seven
varieties with Alvarinho, not the DOC's 46; a two-word row whose words
both resolve is a name and its lost-";" synonym ("Vinhão Sousão"). The
other cadernos name their sub-regiões for area and terroir only.

| Script | Reads | Writes |
|---|---|---|
| pt/00_fetch_data.py | (network) + scripts/_lib/pt/subregiao_areas.json | raw/pt/eambrosia/index.json, raw/pt/ivv/cadernos-index.json, raw/pt/caop/CAOP_{Continente,RAA,RAM}_2025.gpkg, raw/pt/dre/*.pdf + manifest-*.json (the acts that delimit sub-regiões) |
| pt/01_fetch_cadernos.py | raw/pt/eambrosia/index.json + raw/pt/ivv/cadernos-index.json + raw/pt/ivv/cadernos/manual_overrides.json | raw/pt/ivv/cadernos/*.pdf + manifest.json |
| pt/02_extract_cadernos.py | raw/pt/ivv/cadernos/*.pdf | raw/pt/cadernos-extracted/*.json + _index.json (parents + sub-regiões + stubs) |
| pt/02d_extract_terroir_facts.py | raw/pt/cadernos-extracted/*.json + raw/wikipedia/aocs/pt/ | raw/terroir-facts/*.json (country="pt") + manifest-pt.json |
| pt/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="pt") | raw/translations/terroir-facts/<en|fr|es|nl>/*.json |
| pt/03_generate_wiki.py | raw/pt/cadernos-extracted/*.json | wiki/<slug>.md (per PT record) + merges PT entries into wiki/_index.json |
| pt/regen_manual_overrides_template.py | raw/pt/eambrosia/index.json + raw/pt/ivv/cadernos/manifest.json | raw/pt/ivv/cadernos/manual_overrides.json (curator queue, preserves filled-in URLs) |

PT-specific notes:
- `kind` is `"DOP"` / `"IGP"` (Portuguese convention, same as ES).
- **Styles (2026-10-23).** `pt/02` `parse_styles` reads the caderno's
  category list ("1. Vinho / 3. Vinho licoroso / 4. Vinho espumante de
  qualidade"; the anchor takes a header glued to its number, Alentejo's and
  Bucelas' "1.CATEGORIA") and the description's masculine colour words
  ("vinhos brancos", "Porto brancos e tintos", "Vinho (Branco, Rosado e
  Tinto)" — never "uvas tintas"), "fermentação clássica em garrafa" as the
  traditional method; a sub-região takes its parent's. Until then PT records
  carried no styles and every card showed the stage-04 floor's red and white.
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
2. **Sub-regiões** — a sub-região the caderno delimits by its own units
   is drawn from them, at the same bar as a parent (step 3): Douro's and
   Porto's Baixo Corgo / Cima Corgo / Douro Superior, Trás-os-Montes'
   Chaves / Planalto Mirandês / Valpaços, Do Tejo's six, Alentejo's
   Vidigueira. One the caderno names but does not delimit is drawn from
   the national act that does, transcribed in the checked-in
   [scripts/_lib/pt/subregiao_areas.json](scripts/_lib/pt/subregiao_areas.json)
   ([scripts/_lib/pt/subregiao_areas.py](scripts/_lib/pt/subregiao_areas.py),
   2026-10-13): Vinho Verde's caderno lists its nine sub-regiões and gives
   each a grape table, but its area section delimits the DO only — the
   sub-regiões are Portaria n.º 668/2010, Artigo 3.º n.º 1 and Anexo I
   ("Área geográfica de produção com indicação de sub-região"), as
   republished by Portaria n.º 152/2015: whole municípios, and freguesias
   where one is shared (Cinfães between Baião and Paiva, Vizela between Ave
   and Sousa, Valongo's Campo e Sobrado in Sousa, Resende without Barrô).
   The table rows are the act's as printed (a row without freguesias is
   "(*) Todo o concelho"; the Baião table's "São João." / "Fontoura." is
   one freguesia, `printed_as`), drawn through the same resolver as step 3;
   the card cites the act (`geom_src_national_act`, a Sources entry
   `src_area_act`; the record's `area_act_*` source fields), and stage 00
   fetches the PDF into `raw/pt/dre/` against its pinned sha256. The entry
   lists every act read for its effect on the table (`reviewed_acts`: the
   two rectifications and Portaria 333/2016 touch yields and labelling,
   Avisos 7945/2022, 14002/2024/2 and 21430/2026/2 are IVV specifications,
   none changes Artigo 3.º n.º 1 or Anexo I); a caderno whose legal
   reference (9.8 b) cites an act not listed — read in any citation form
   (`cited_acts`: plural and list forms, a number without "n.º", a
   two-digit year) — makes the entry STALE on the `[pt-geom]` line
   and fails `tests/test_pt_subregiao_areas.py`, which also checks every
   name as an entry of its own sub-região's table in the PDF (read column
   by column, entry and "(*)" counts equal), that Artigo 3.º's prose draws the same units as
   the table (the republication's "Santa Eulália em de Santo Adrião" read
   as the 2010 "e de"), and that the nine lie inside the DO without
   overlapping: 7,083 km² of its 8,398 — the rest is Caminha, Paredes de
   Coura, Valença, Vila Nova de Cerveira, Gondomar, Maia, Matosinhos, most
   of Valongo, Arouca, Vale de Cambra and Ossela, in no sub-região. A
   sub-região whose section is boundary prose (the other seven of
   Alentejo's — `prose_cut_subregions`) inherits the parent's polygon as
   **`parent-appellation`**. The record's `name` is the section header
   ("Baixo Corgo", "Granja/Amareleja").
3. **`caop-freguesia-union` / `caop-concelho-union`** — the caderno's
   "Área geográfica delimitada" read clause by clause
   ([scripts/_lib/pt/area_units.py](scripts/_lib/pt/area_units.py)) and
   drawn from DGT CAOP 2025 at freguesia precision
   ([scripts/_lib/pt/freguesias.py](scripts/_lib/pt/freguesias.py),
   `PTPolygonIndex.resolve_area_units`; 2026-10-13, after a Vinho Verde
   boundary flag). A município named whole is drawn as its CAOP polygon,
   minus the freguesias its clause excludes ("Resende, com exceção da
   freguesia de Barrô", "Figueira de Castelo Rodrigo (excluída a
   freguesia de Escalhão)", "O distrito de Aveiro, com exceção dos
   municípios de … e, do município de Oliveira de Azeméis, a freguesia
   de Ossela"); a município the text restricts to freguesias ("Loulé
   (freguesias de …)", "Do concelho de Cascais, as freguesias de …", "as
   freguesias de …, do concelho de Vila Real", "• Armamar: …") is drawn
   as those freguesias; a distrito named as a member ("todos os
   concelhos dos distritos de …", "Todas as freguesias de todos os
   concelhos do distrito de …", "O distrito de X") whole. The area is the
   union of every clause, sub-região sections included (a sub-região
   lies inside its appellation; Terras do Dão's Couto de Esteves is
   named only there), and an exclusion removes units from its own clause
   only. Boundary prose — a clause from its first lower-case boundary
   word on ("limite", "estrada", "ribeira", "segue", "linha",
   "confinante", …) and Carcavelos' "Os limites da região são os
   seguintes:" — names landmarks, never members. CAOP's 3,259
   freguesias carry the 2013 Uniões (Lei n.º 11-A/2013); a name is
   matched inside its município against each unit's CAOP name, its
   former freguesias ("Travassô e Óis da Ribeira" → Óis da Ribeira;
   "Lamego (Almacave e Sé)" → Sé) and every run of them — a
   "Town (Saint)" unit also as "Saint de Town" ("Vizela (São Paio)" is
   the Portaria's "São Paio de Vizela") — then with the
   connectors or the spaces dropped, a whole-word prefix / suffix
   ("Santa Catarina" → Santa Catarina da Fonte do Bispo, "Rua" → Vila da
   Rua), a one-letter typo ("Frechos", "Argeriz", "Alvar") and the
   checked-in [scripts/_lib/pt/freguesia_overrides.json](scripts/_lib/pt/freguesia_overrides.json)
   (`unions`: a renamed union whose name lists no parts — Vila Real,
   Viseu, Coutos de Viseu, São Gonçalo de Lagos, Armamar — with its
   former freguesias; `names`: Graciosa's "Praia" = São Mateus, Torres
   Vedras' "São Miguel" / "São Mamede", Sobral's "São Salvador"; each
   cites the act in the Diário da República; a pin CAOP no longer
   carries, or whose unit already names its parts, prints STALE). A name
   written "União das freguesias de A e B" is that union while CAOP carries
   it, else its former freguesias — CAOP 2025 re-created some (Valongo's
   Campo and Sobrado, Vizela's Tagilde and São Paio), and read whole the
   name matched one part by suffix and lost the other; an exclusion so
   named gathers its parts per unit, so a union whose every part it names
   goes whole. A name
   none of these reaches is reported, never guessed; a container written
   short ("Santa Cruz", "São Roque", "Lajes") is the município in which
   the clause's freguesias resolve, an exact name before a longer one
   ("Paredes" ≠ Paredes de Coura). What the card says (`_units_line` /
   `unitsLine`, panel fields): a freguesia the text includes only in part
   ("parte das freguesias de", "(parte)", "lugares de", "as Quintas …",
   "as propriedades …", an altitude limit, "excluindo as propriedades
   …") is drawn whole and listed under `geom_units_partial`; a former
   freguesia whose União holds parishes the text does not name draws the
   union, listed under `geom_units_proxied`; a name the layer does not
   carry under `geom_units_unmatched`. A município the record draws
   entirely keeps its município polygon; `caop-concelho-union` when no
   município is drawn in part. Accepted when the unmatched names are no
   more than the units drawn.
4. **`figshare-pdo`** — exact `file_number` (`PDO-PT-Axxxx`) →
   `PDOid` match against Bétard 2022 EU_PDO.gpkg (reuses
   `raw/es/figshare/EU_PDO.gpkg`; the dataset covers all EU PDOs).
   Used for a DOP with sub-regiões delimited only by boundary prose
   (`prose_subregions`: Alentejo's Borba, Moura, Redondo, Reguengos —
   the units the text names would leave them out, and Bétard's polygon
   covers Évora, Borba, Redondo and Reguengos de Monsaraz whole), and as
   the fallback when the clause reader takes no unit from a text.
5. **`caop-concelho-union`** (legacy) — the município-level reading
   ([scripts/_lib/pt/commune_list.py](scripts/_lib/pt/commune_list.py),
   `union_from_parsed`) for a text the clause reader takes nothing from;
   logged "no unit read at freguesia level". Not hit on the current
   corpus.

Macro-region tokens (`acores` / `madeira`) emitted by the parser
expand into the constituent ilhas via `PT_MACRO_REGIONS` in
[scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py): Açores =
"todas as ilhas do Arquipélago dos Açores", 9 ilhas / 19 municípios (the
western group, Flores + Corvo, is the second gpkg of the CAOP RAA zip;
stage 00 extracts every gpkg of a zip since 2026-10-13 — the IG had
lacked both islands); Madeira = the Região Demarcada "abrangendo as
ilhas da Madeira e do Porto Santo", 2 ilhas / 11 municípios, the parts
more than 10 km offshore dropped (`MACRO_ISLANDS_ONLY`, `ISLAND_KEEP_M`:
CAOP files the uninhabited Desertas and Selvagens under Santa Cruz and
Funchal; the three Madeira records had drawn them).

Bétard 2022 + CAOP 2025 are CC-licensed and re-distributable with
attribution. CAOP 2025 (Continente + RAA + RAM) is fetched once in
stage 00 and cached at `raw/pt/caop/`. Re-runnable: stage 04 reads
the cached gpkg on every run. CAOP 2012.1, the last map before the 2013
mergers, would draw a former freguesia exactly instead of its União, but
DGT states no licence for the historical versions — not used.
`tests/test_pt_area_units.py` pins the parser and the resolver,
`tests/test_pt_subregiao_areas.py` the act tables of step 2.

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
  Italian-language extraction prompt. **A non-stub whose single document
  carries only the "Sintesi del legame" grounds on the Article 9 too**
  (2026-10-24, the IT sibling of the ES decision of the same day):
  `_resolve_lien_and_source` and stage 04's
  `_backfill_it_nonstub_from_masaf` take the sidecar's text under
  `summary_link.prefer_national_link` (the marker or under 1,000
  characters, the Article 9 at least 1.5× longer; the record carries
  `masaf_link`). The 2024/1143 template had left 39 non-stub records on a
  600–1,500-character summary — Marsala (1,286 against 4,522; three
  facts), Etna (702 against 13,671), Montefalco Sagrantino (625 against
  17,852), Friuli Colli Orientali (738 against 26,646) — and 15 more with
  an empty EU link already read the Article 9; Terre Abruzzesi's
  15 k-character "Sintesi" against a 19 k Article 9 stays the EU text.
  IT 02e targets en/fr/es/nl (FR + ES are translation targets, not
  sources). Cache files land in the shared `raw/terroir-facts/` directory
  with `country: "it"` to distinguish them from FR/ES/PT records.
  Sottozone are skipped — they inherit the parent's bullets at the
  rendering layer.

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
  inheriting the parent's grapes/styles/terroir — except where the PDF
  binds the sottozona's own sub-disciplinare (2026-10-04, parser v5): 02f
  records each annex's `sottozone` (the quoted names after the title's
  last "sottozona"), its Article 2 roster when that article is a variety
  article (`masaf.annex_grapes`; the sottozona's own name never reads as
  a grape — "Tinella" had fuzzy-matched Grenache) and its styles when it
  has an organoleptic article (found by its opening, annexes renumber);
  stage 04 gives them to the sottozona the annex names
  (`sottozona_rules` on the record). 42 of 78 sottozone have an annex
  and 37 take its roster — Pignolo di Rosazzo is Pignolo, Romagna Cesena
  Sangiovese, Valtènesi Groppello first; Riviera Ligure di Ponente's five
  annexes carry no variety article and keep the parent's, as does the
  detector's merged "Schioppettino di Prepotto» «Savorgnano" record. Annex sottozone with no record yet
  (Montepulciano d'Abruzzo's 9, Trentino's 5, …) are not emitted — some
  are DOCGs or cancelled IGTs now. `chiaretto` reads as rosé.
  Geometry resolves via `parent-appellation`. v1 yield: **38 sottozone across 10 DOPs**
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
  to the numbered parser; since 2026-10-24 also a dash-bulleted annex,
  read across its "nel comune di X:" sub-headers and page numbers —
  the Tuscan Allegati A). A trigger followed by a 2024/1143 field label
  ("Quadro di riferimento giuridico:") before its colon is a condition
  title, and one whose sentence ends before the colon introduces nothing:
  until then "Nella legislazione unionale" was Roero's, Etna's and three
  more records' one cru, and kept Etna's MASAF contrade off the card; a
  comma list ends with its sentence ("…, Vicenziana. Le suddette …").
  Stage 02 harvests from the documento unico;
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
`src_regional_register`). Molise (osco, rotae) and Lombardia (quistello,
bergamasca — added 2026-10-22, when «Bergamasca» stopped binding Marzemino and
the card had no other grape) read the CREA catalogoviti register.

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
   production-zone polygon, matched by appellation name. Six regions
   are harvested (Piemonte, Veneto, Lazio, Lombardia, Toscana, Umbria —
   all CC-BY 4.0 / IODL 2.0); ~237 of 531 IT wines resolve here,
   including every flagship (Barolo, Soave, Valpolicella, Chianti,
   Brunello, Bolgheri, Franciacorta, Frascati, Sagrantino di
   Montefalco). An appellation spanning regions is the union of its
   per-region pieces (e.g. Orvieto = `lazio+umbria`). Umbria is harvested
   via a bespoke CKAN per-appellation `.zip`/`.7z` shapefile fetch
   (`fetch_type: ckan_shapefiles` in `zone_sources.py`); Puglia is the
   remaining tracked to-do (see CURATOR_TODO.md).
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
   Siciliana" folds to "Sicilia" (`_REGION_NAME_ALIAS`). A whole province
   named beside a comune list ("l'intero territorio amministrativo delle
   province di Forlì-Cesena, Ravenna e Rimini e dei comuni di … della
   provincia di Bologna" — Rubicone, Daunia, Murgia) is a member, not a
   qualifier: the quantifier (intero / tutto + territorio + provincia)
   marks it and the result is `gisco-comune-provincia-union` (2026-09-24;
   a province inside a winemaking clause — "le operazioni di vinificazione
   … nell'intero territorio della provincia di Alessandria" — never
   promotes). Since 2026-09-25 the parser also reads what the review of
   the 2026-09-24 rule had listed as latent gaps: an **exclusion clause**
   ("esclusi i comuni di Pantelleria, Favignana ed Alcamo" — Marsala;
   "con l'esclusione dei territori comunali di Cellarengo d'Asti" —
   Freisa d'Asti; "dell'intero comune di Bellaria Igea Marina" — Rimini)
   subtracts its units from the union (`excluded_comuni` /
   `excluded_province`, `stats["excluded"]`) — but only a WHOLE unit:
   the corpus's other exclusions are parts of a comune ("le tre isole
   amministrative … del comune di Atella", "i fondi valle … di
   Senigallia", "Roma ad esclusione dell'area interna al GRA") and a
   partial marker anywhere in the clause keeps every name of the clause;
   the adverb "esclusivamente" is never an exclusion, a bracketed clause
   ends at its ")", and a province inside an exclusion is never promoted
   to a member. A bare **"Provincia di X:" header** opens the comune list
   that follows its colon with or without the word "comuni" (Costa
   Toscana, Carso, Asolo, Alta Langa), an unresolved multi-word name is
   **one miss**, not one per word (Valle Belice's "Santa Margherita
   Belice" — ISTAT "… di Belice" — used to close the bucket and turn four
   comuni into two whole provinces), a list **resumes after a locational
   province** ("Menfi, in provincia di Agrigento e Contessa Entellina"),
   "art." / "n." never end the winemaking-clause lookback, and two folds
   meet ISTAT's spelling: connector-less forms on both sides ("Concordia
   sul Secchia" / "sulla", "Santa Teresa di Gallura" / ISTAT "Santa
   Teresa Gallura", elided "d'") and j → i ("Gioiosa Jonica" / "Ionica").
   The change moved 129 of 524 parses, 16 of them build-affected (Valle
   Belice 125 → 4 comuni, Casauria, Roccamonfina, Tharros, Emilia-Romagna
   IGT from whole provinces to their comune lists); an independent
   read-through of those 16 texts found 15 better and none worse. The
   earlier "shelved" note applied to per-commune-list parsing of complex
   DOC prose; for the province-/region-wide IGTs this resolver is reliable.
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
   breaks pdftotext emits between articles). A consolidated
   disciplinare appends one sub-disciplinare per sottozona (ALLEGATO N —
   SOTTOZONA «…», Trentino's TITOLO II), each restarting at Art. 1:
   `extract_article_runs` splits the header sequence into runs at every
   restart, drops a table of contents (every body a title line) and a
   decree preamble bound in front (an Art. 1 that never *reserves* the
   name), keeps the parent's own run as `article_bodies` and the later
   runs as the sidecar's `annexes` (`{title, article_bodies}`). Before
   2026-09-13 the last occurrence of each article number won, so a parent
   with annexes took its summary, roster, area and Art. 9 lien from its
   last sottozona (Montepulciano d'Abruzzo → San Martino sulla Marrucina;
   20 parents affected, review R4) — and, as the parent's real Art. 1 now
   names them, the stage-04 sottozona detector finds 77 sottozone in 17
   parents (was 38 in 10). Then parse:
   - **Article 1** → summary (first paragraph, ≤ 600 chars)
   - **Article 2** → grape varieties via `match_variety` on
     line/colon/comma-split candidates + `vitigno NAME` regex scan,
     then the **in-PDF variety annex** (`grapes_with_annex` in
     `masaf.py`, 2026-10-04). Many disciplinari keep a roster out of
     the article: "Allegato 1 – Elenco vitigni complementari …" at the
     end of the PDF (or a bare "Elenco vitigni/varietà … idonei" line),
     as a numbered list, bare colour-coded rows ("AGLIANICO N."), a
     register table with a code column, two columns, or "(N)" brackets;
     the list runs to the next "Allegato" / "Articolo" heading. Three
     readings, decided by Article 2's wording: no variety named → the
     annex is the roster (the regional-IGT case, `principal`); "da uno
     o più vitigni idonei … riportati nell'allegato 1" → the roster
     again, merged as `principal` beside the names the article singles
     out for labelling (Terre Siciliane, Basilicata, Isola dei Nuraghi,
     Alpi Retiche, Calabria); "Cabernet Sauvignon: almeno l'80 %;
     possono concorrere altri vitigni … riportati nell'allegato 1" →
     the annex is the complement, merged as `accessory` with the
     article's names never repeated (Bolgheri Sassicaia, Chianti
     Classico, the Tuscan DOCs). An Article 2 that names varieties and
     never says "allegato" leaves the annex alone (Roero attaches the
     whole Piedmont register, aromatic varieties its own rule excludes
     included). Annex entries carry `source:
     masaf-disciplinare-allegato`. Until 2026-10-04 the annex was read
     only when Article 2 named nothing, so Sassicaia's card listed
     Cabernet Sauvignon alone while its own terroir fact named the
     Cabernet Franc (visitor flag 2026-10-03); 58 sidecars changed, 25 of them stubs that now carry an accessory roster and five regional IGTs (Terre Siciliane, Calabria, Basilicata, Isola dei Nuraghi, Alpi Retiche) whose card had shown the one or two varieties Article 2 names.
     Since 2026-10-22 (the Romagna Oriolo annex) **the clause names the
     role** (`clause_roles`): a variety named after a clause's *concorrere*
     marker ("può / possono / possono inoltre / deve concorrere",
     "concorrono alla produzione") or its "complementari / accessori:" label
     is `accessory`, one named after "principali:" or before any marker is
     `principal`; a clause runs between semicolons, sentence ends and blank
     lines, never a list bullet, so a complement list on its own lines
     belongs to the clause that opened it; a variety named in several
     clauses is principal when any makes it one (Prosecco restates its
     complement varieties as base-wine vineyards), and an all-accessory
     roster is no split. Oriolo's "può concorrere … il vitigno Albana fino
     ad un massimo del 30 %" made Albana a principal before. **A variety the
     article names only to exclude it is not in the roster**
     (`exclusion_drops`): "con l'esclusione della Malvasia Nera, Malvasia
     Nera di Brindisi e Aleatico" (Montecucco), "con esclusione del vitigno
     Traminer aromatico" (Picolit) — 32 rosters carried such a name. Not an
     exclusion: the sentence that reserves a varietal *label* ("con la
     specificazione di uno dei vitigni … con l'esclusione dei vitigni
     Cannonau, …", the Sardinian and Basilicata IGTs, whose blends may hold
     them), a concession on the name ("per il quale è consentita la presenza
     fino al 3%"), and "ad eccezione di X", which in this corpus excepts X
     from a limit; a name is dropped only when every mention is an
     exclusion (Friuli Isonzo's bianco excludes «Moscato giallo», its
     Moscato giallo type is made of it), never the whole roster. **A bare
     family word is pinned per record, never folded by rule**
     ([scripts/_lib/it/grape_context_overrides.json](scripts/_lib/it/grape_context_overrides.json),
     MASAF record slug → normalised surface → slug, reason, source; a
     sottozona annex reads its parent's entry): Romagna's Article 2 names
     "Trebbiano Romagnolo" in full and writes "Trebbiano" for the same
     variety elsewhere and in the Oriolo annex, where the lexicon's bare
     alias gives Trebbiano toscano (both cards carried Ugni blanc). A
     generic fold ("X" beside "X Y" in one document is "X Y") was tried the
     same day and rebound 130 entries: "Alicante" to Alicante Bouschet in 41
     Tuscan rosters, "Riesling" to Riesling italico in 21, Barbera to
     Barbera bianca, Canaiolo to Canaiolo bianco, Merlot to Merlot Khorus —
     the pattern means two varieties as often as a shorthand, and VIVC
     itself lists bare TREBBIANO under Trebbiano toscano. The matcher's
     `set_pliego_context` / `current_pliego_context` carries the record
     slug; `tests/test_masaf_roles.py` pins the rule and the table.
     Stage 04's non-stub backfill adds the annex `accessory` entries
     to a documento-unico record that carries none (the EU single
     document lists only the main varieties) and records the MASAF
     provenance on any record that took something from the sidecar.
   - **Article 1** also names the varietal types the name is reserved to
     ("«Colli Altotiberini» Cabernet Sauvignon", "… Merlot riserva") — a
     wine of ≥ 85 % of that variety, the rule Article 2 states without
     naming them. `masaf.article1_varietal_types` (2026-10-23) reads the
     tail of each «NAME» line up to its first comma, type words stripped,
     and adds the variety as `principal` (`source:
     masaf-disciplinare-art1`) when it is an exact *and curated* lexicon
     surface — never a bare family word ("Pinot", "Malvasia"), never the
     wine's own name ("San Colombano" had bound Verdea), never a legacy VIVC
     synonym ("Rossetto" Grignolino). Colli Altotiberini, Colli Romagna
     Centrale and Ischia changed; 519 did not.
   - **Article 3** → geo area / commune list
   - **Article 9** → link to terroir — `link_to_terroir` is the
     4,000-character panel cut, `link_to_terroir_full` the whole article
     (what 02d, the gate and the audits read; `terroir_article` records
     which article it came from)
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
near-verbatim mirror of the IT pipeline. Every wine has its EU single
document, so no record is a stub; since 2026-11-08 the **BML
Produktspezifikation** — the national specification filed under Art. 94 —
rides a stage 01c / 02f layer of its own that adds the authorised roster the
single document's § 7 leaves out (see "AT national-spec layer" below).

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
| at/01c_fetch_produktspezifikationen.py | (network: the BML Weinherkunft page) + raw/at/eambrosia/index.json + scripts/_lib/at/produktspezifikation_pins.json + raw/at/produktspezifikationen/manual_overrides.json | raw/at/produktspezifikationen/<slug>.pdf + weinherkunft.html + manifest.json |
| at/02f_extract_produktspezifikationen.py | raw/at/produktspezifikationen/*.pdf + manifest.json | raw/at/produktspezifikationen-extracted/*.json + _index.json + manifest.json, raw/at/extraction-unknowns-produktspezifikation.json |
| at/02d_extract_terroir_facts.py | raw/at/dokumente-extracted/*.json + raw/at/produktspezifikationen-extracted/ (the § g text where the EU link is short) + raw/wikipedia/aocs/de/ | raw/terroir-facts/*.json (country="at") + manifest-at.json |
| at/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="at") | raw/translations/terroir-facts/<en\|fr\|es\|nl>/*.json |
| at/03_generate_wiki.py | raw/at/dokumente-extracted/*.json | wiki/<slug>.md (per AT record) + merges AT entries into wiki/_index.json |
| at/regen_manual_overrides_template.py | raw/at/eambrosia/index.json + raw/at/oj-pages/manifest.json | raw/at/oj-pages/manual_overrides.json (curator queue) |
| audit_at_coverage.py | raw/at/eambrosia/ + raw/at/dokumente-extracted/ + raw/at/oj-pages/manifest.json + raw/at/produktspezifikationen-extracted/ + raw/terroir-facts/ + raw/es/figshare/EU_PDO.gpkg | (stdout — coverage table, the Produktspezifikation layer's added varieties per record, terroir-fact counts, curator queue) |

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
- Section 7 ("Wichtigste Keltertraubensorten") lists the **main**
  varieties one per line as `Offizieller Name - Synonym, Synonym` — the
  canonical name is the segment before the dash; they are the card's
  principal grapes. The whole authorised roster comes from the BML
  Produktspezifikation (below). Austrian-only varieties (Zweigelt, Sankt
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

### AT national-spec layer — the BML Produktspezifikation (stages 01c + 02f)

A visitor flagged Wachau's two-grape roster on 2026-11-07. The card stated
what its cited document states — the EU Einziges Dokument's § 7 "Wichtigste
Keltertraubensorten" names Grüner Veltliner and Riesling — while the
specification in force, the BML Produktspezifikation that the corrigendum
C/2025/90060 links, calls the two the "Hauptsorten" and allows a Wachau
Gebietswein from 17 varieties. 17 of 30 AT cards carried two grapes or fewer
for the same reason. The layer is the DE BLE pattern (a non-stub record
augmented, not a stub filled), not the BG / GR stub pattern:

- **Stage 01c** ([scripts/at/01c_fetch_produktspezifikationen.py](scripts/at/01c_fetch_produktspezifikationen.py))
  reads the BML "Weinherkunft" page, where every specification is linked as
  `/dam/jcr:<uuid>/<Name> Produktspezifikation.pdf` (the 2025 template
  `Produktspezifikation_<Name>.pdf`), maps the filename to the AT slug and
  downloads 30 PDFs into `raw/at/produktspezifikationen/`. The jcr uuid is
  opaque and never pinned: a cached PDF is kept while the page links the
  same URL, a rotated URL is re-fetched and a changed sha256 logged as a new
  edition. A slug the page lists twice is settled by the checked-in
  [scripts/_lib/at/produktspezifikation_pins.json](scripts/_lib/at/produktspezifikation_pins.json)
  (Eisenberg: the 2025 file, whose § f allows Blaufränkisch and Welschriesling
  as the EU document in force does, over the Blaufränkisch-only one) — an
  unpinned duplicate is skipped and reported, never guessed.
  `manual_overrides.json` in the same directory is the curator path.
  Licence: amtliches Werk (§ 7 UrhG), attribution to the BML.
- **The parser** ([scripts/_lib/at/produktspezifikation.py](scripts/_lib/at/produktspezifikation.py))
  finds the a)–i) sections by their **title words**, a letter accepted where
  printed: pdftotext glued Kärnten's "g)" title to the roster's last line
  ("Rotburger).Angaben über Güte …") and the 2025 template prints the terroir
  title without a letter. Section f) comes in five shapes, every one of the
  31 PDFs one of them: the national roster in two numbered colour blocks
  (35 varieties, synonyms in brackets) with or without a closing "Die
  Hauptsorten des Weinbaugebiets X sind …" sentence; the DAC rule with the
  Hauptsorten sentence and the Gebietswein / Ortswein / Riedenwein lists in
  „quotes" (Wachau); an exclusive prose list (Kamptal's five); one or two
  varieties (Weinviertel, Rosalia); an open reference alone ("Alle weißen
  Qualitätsweinrebsorten", Ruster Ausbruch). Names are read by a
  longest-first window over the words of each separator-bounded segment
  through the lexicon's **exact** matcher only; bracket contents are the
  regulator's synonyms and are dropped. Three Austrian pins: a bare
  "Morillon" is Chardonnay (the lexicon's unpinned surface is the French
  Pinot noir synonym; the Steiermark DACs list it bare), the bare family
  words "Burgunder" / "Veltliner" never bind (VIVC files BURGUNDER under
  Blaufränkisch), and the designation and Bundesland names never bind
  ("Steiermark" is a VIVC synonym of Furmint). "Gemischter Satz" is a field
  blend, not a variety. A quoted name without a colour block takes the
  national roster's colour class (`ROSTER_COLOURS`, the two blocks every
  Bundesland specification prints). The § g text is kept whole as
  `zusammenhang_text`.
- **Stage 02f** ([scripts/at/02f_extract_produktspezifikationen.py](scripts/at/02f_extract_produktspezifikationen.py))
  writes one sidecar per wine with the roles: a Hauptsorten sentence makes
  its varieties principal and the rest accessory (`role_rule: hauptsorten`
  — Wachau, Wien, Burgenland, Niederösterreich, Steiermark); the national
  roster without one makes every variety accessory, the EU § 7 being the
  principal list (`national-roster` — the Bundesland PDOs, the three
  Landwein PGIs, Wiener Gemischter Satz's white half); a closed list makes
  every variety principal, as the EU document lists them (`exclusive-list`);
  an open reference leaves the EU roster alone (`open`). First run: 30 of 30
  sidecars, no roster name the lexicon lacks (the 2025 Eisenberg file's
  "Welschrielsing" is a `GRAPE_ALIAS` entry).
- **Stage 04** ([scripts/_lib/augment/at.py](scripts/_lib/augment/at.py),
  called after the DE augmenter) adds every sidecar variety the EU record
  lacks with the sidecar's role, tagged `source: bml-produktspezifikation`;
  an EU variety keeps its role and spelling, nothing is demoted or removed.
  Where the EU link text is under 400 characters (Oberösterreich's 347) the
  § g text becomes `link_to_terroir`, and AT 02d reads the same sidecar
  (`cahier_source_kind: bml-produktspezifikation`, the PDF as the card's
  footer attribution) — Oberösterreich carries 9 facts since, where it had
  the 02c summary fallback. The card discloses the layer in its Sources
  row, "National product specification (BML, PDF) — +N varieties added"
  (`bml_produktspezifikation_*` in the panel payload and `_sources_for`,
  `src_bml_produktspezifikation`; the provenance line stays the EU single
  document's, whose § 7 names the principal grapes). First build: 368
  varieties added on 15 records — the Bundesland PDOs and the PGIs 2 → 35,
  Wachau 2 → 16, Weststeiermark 1 → 9, Oberösterreich 19 → 35 — and nothing
  on the 15 whose EU document already lists the closed roster (Kamptal,
  Thermenregion, Wagram …); Weinviertel stays Grüner Veltliner by its own
  rule. `tests/test_at_produktspezifikation.py` (fixtures `at_bml_*.txt`),
  `audit_at_coverage.py` prints the per-record additions.
- **Colours the specification states** (`stated_colour_styles`, the EU
  reader's own colour table over sections b) and g): "Rund 2/3 der
  Anbaufläche sind mit Weißwein bepflanzt, ein Drittel mit Rotwein", "Die
  Rotweine werden aus den Sorten …", "Rot- und Roséweine spielen eine sehr
  untergeordnete Rolle") ride the sidecar as `styles_stated` with the
  sentence, and the augmenter **completes** a colour list the EU text
  already started — never starts one: a record whose EU text states no
  colour keeps the berry-colour floor, because one stated colour would
  switch the floor off and lose the others (Eisenberg's § g names "Eisenberg
  Rotwein" and not the Welschriesling whites it also allows; the trap the
  style-floor rule names). The card validator had graded Oberösterreich
  "caution" for a missing Red on a red-heavy roster (its EU text states
  white, its specification "Die Rotweine werden aus den Sorten Blauer
  Burgunder, Zweigelt …"). Four cards change: Carnuntum and Oberösterreich
  gain Red, Wachau Rosé, Weinland Red and Rosé, each from a quoted
  sentence (`styles_evidence` in the provenance).
- **The card packet carries the sidecar** (`card_packet.SIDECAR_DIRS["at"]`,
  the `description_text` / `geo_area_text` keys, a list-shaped roster —
  the DE sidecar's too, which the judge had never seen): on the first
  rebuilt card the validator read Oberösterreich's grounded facts as
  "in no supplied document".

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
- **Styles from the register's single document too (2026-10-23).** The 2007
  pravilnik is a variety list and an MKGP `.doc` gives its colours from the
  grapes, so no SI card had a rosé and Bela krajina showed only the floor's
  white and red. `si/02f` adds what the fiche's category list and description
  state (`specifikacija.fiche_styles`, inflected: "17 g/l za bela in rose vina
  ter 20 g/l za rdeča vina", "od pozne trgatve do suhega jagodnega izbora in
  ledenega vina", "4. Peneče vino"); the sidecar records `styles_source` and
  the card cites the fiche (`register_fiche_url`). Run
  `extract_register_fiches.py --country si --all` before `si/02f`.

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

Country #8. **43 wine GIs (37 DOP + 6 PGI)** from eAmbrosia (41 at
first; Mura / Murai joined on 2026-09-20, Nivegy-völgy / Nivegy-völgyi,
PDO-HU-02816, Reg. (EU) 2026/2105, on 2026-10-24); the profile sits
between IT and SI/HR — 30 of 43 wines carry a fetchable EUR-Lex
EGYSÉGES DOKUMENTUM, and every one lands on the map via Bétard 2022
PDO match, PGI region-union or the single document's település list.
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
  prefix (`Bor -`, `Pezsgő`, `Classicus`, `Likőrbor`, `Siller`,
  `Fehérbor`, …). The 2024/1143 template (2026-10-24, phase F) adds a
  "3. Az az ország, amelyhez …" decoy the area routing now skips, and
  names its wine types "Bor – Fehér" / "Bor – Vörös" / "Bor – Rozé", read
  as colours (`_TYPE_COLOUR_RE`); a template whose types carry no colour
  word (Nivegy-völgy's "Hegybor", "Dűlős bor", described as yellow) gets
  the floor's colours from its roster.
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
  The termékleírás roster reader (`_lib/hu/termekleiras.parse_grapes`,
  2026-10-23) joins a name the PDF wraps across two lines — "Irsai ⏎ Olivér",
  "Cabernet ⏎ franc", "Pinot ⏎ 2. rozé ⏎ noir", "Hamburgi ⏎ muskotály" and a
  dozen more — by trying the pending last item of a line joined to the next
  line's first and keeping the join only when the lexicon knows the whole
  name exactly (a row boundary "Viognier ⏎ Alibernet" stays two); the
  wine-type labels ("2. rozé", "Classicus") and the Wingdings bullet are
  skipped. Read apart, "Olivér" had bound Plăvaie (an OLIVER synonym) on
  Balatonmelléki, Eger and Monor. `keknyelu` is VIVC #16421, which VIVC also
  lists on Furmint — the fuzzy hit the dedupe had swallowed.
  The area reader (`_lib/hu/commune.parse_commune_list`) reads every
  "… település(ek)(nek)" group of a text, not only the first (2026-10-24):
  Monor's termékleírás names one group per hill ("Monor településen a
  Strázsa-hegy, Monor, Monorierdő és Bénye településen a Száraz-hegy, Gomba
  településen …") and had read Monor alone, Tolna's opens on the heading
  "Települések:" and had read nothing; headings ("CLASSICUS:", "Csongrádi
  borvidék:") and the map-exclusion clause are dropped.
  Run `scripts/02b_fetch_aoc_lexicon.py --lang hu --source raw/hu/dokumentumok-extracted`
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
3. **`gisco-commune-union`** — the PDOs that post-date the Bétard 2022
   snapshot (Etyeki Pezsgő, Kőszeg, Füred, Mura, Nivegy-völgy): the
   single document's area section names the települések
   ([scripts/_lib/hu/commune.py](scripts/_lib/hu/commune.py)), unioned
   from Eurostat GISCO LAU 2024 `HU_*` polygons (the RO / BG commune-list
   pattern).
4. **`stub-no-geometry`** — last resort; not hit.

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
  conversion mangles section numbering. The yield table (5.2 "Producții
  maxime") names varieties section 7 omits — "Merlot, Băbească Neagră,
  Burgund Mare / 17 000 kilograme …" on Dealurile Olteniei; 14 of the 46
  documents carry one — and `add_yield_table_varieties` adds them as
  accessories, exact lexicon names only, the row's prose never reported as an
  unknown (2026-10-23: Olteniei + 3, Colinele Dobrogei + 8, Sebeș-Apold + 2;
  Colinele Dobrogei's 2025 document lists its eight in § 7 itself, so they
  are principal since 2026-10-24). The 2024/1143 template prints the table
  as the sub-block "(b) Producții maxime" of a section 5 titled "Practici
  oenologice", and the table is found by that heading too (11 documents;
  Drăgășani's of 2026 names Sauvignon, Merlot, Pinot noir, Burgund mare and
  Tămâioasă românească only there, 2026-10-24). The slicer is forward-only and keeps the
  first header of each number whose title is a role title (2026-10-24):
  Cotnari's C/2025/821 nests "1. Vin alb …" blocks and yield rows "6. cules
  târziu …" that the last-wins reading had let overwrite sections 1–6, and
  the 2024/1143 template's "Alte cerințe specifice" now ends the link. The
  commune list splits before a dash + "com." / "comuna" ("Oraş Cernavodă -
  comuna Cernavodă", Colinele Dobrogei and Murfatlar).
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
   ES IGP-fallback chain. A name is held to the județ of the header it
   sits under (`geo_communes_scoped`), so the village Oneşti of comuna
   Plugari (Iaşi) is never Municipiul Oneşti (Bacău). **A name the text
   gives only as a village** ("Comuna Cetariu, satele Şişterea, Paleu";
   `commune.village_heads` → `geo_communes_villages`, a name the text also
   lists as a commune of its own excluded) binds a commune only when that
   commune touches its head (2026-10-24, validator finding): the texts
   list villages by the communes of before the 2004 splits, so Paleu
   (from Cetariu), Boghiş (Nuşfalău), Saligny (Mircea Vodă), Pogoneşti
   (Iveşti) and twenty more are the communes they became and stay drawn,
   while a same-named commune elsewhere in the județ is a coincidence and
   is reported (`names_village_homonyms`): Pănceşti (Sascut), Tansa
   (Belceşti), Cristeşti (Brăeşti), Fântânele (Andrieşeni) on Dealurile
   Moldovei, Cotmeana (Stolnici) on Dealurile Munteniei, Măldăreşti
   (Măciuca) on Dealurile Olteniei — 6 communes, ≈ 300 km² no longer
   drawn. The parser also drops a quoted name — a sub-denomination's
   („BIHARIA”, „IANA”), which had shadowed the commune's own item in the
   dedupe — a lower-case chunk (prose: "în funcţie de interesul
   producătorilor", "cu localităţile"; no resolving name starts
   lower-case), "astfel" and the "Subdenumirea / Denumirea …" headers, and
   reads "localitatea componentă a comunei Y" as Y.
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
  A column header glued to an entry ("Сорт грозде Viognier", the one
  Latin-script line of Дунавска равнина's §7) keeps its name; a bare header
  line is still dropped (2026-10-23). Oblast markers are consumed with their
  trailing name so
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
2. **`gisco-commune-list`** — the 2 BG PGIs, drawn from the obshtini
   their text lists per oblast (2026-10-24, validator finding): Дунавска
   равнина's ЕДИНЕН ДОКУМЕНТ §6 and Тракийска низина's ИАЛВ spec §3
   (read from the whole `section_roles.geo_area`; the sidecar's
   `geo_area_brief` is cut at 2,000 characters, before the exclusion
   clause) both list obshtini under „Област X:" headers, then the villages
   cut out of them. `commune.parse_area` reads that template into
   `geo_communes_scoped` ([name, EKATTE oblast code] — the three letters
   GISCO prints in `BG_VAR09`) and `geo_communes_partial` (the obshtini held
   only in part: "Баните - само землищата на с. …", and those the
   "се изключват" clause cuts villages out of); a PDO's settlement list
   gets neither. The resolver matches each name among its oblast's
   obshtini only — two are called Бяла (Русе, Варна) and the text names
   both — then with its spaces closed ("Вълчидол" / Вълчи дол, "Бобовдол")
   and an abbreviation that names one obshtina of the oblast ("Д.
   Митрополия" / Долна Митрополия); "Септември" (област Пазарджик) is no
   longer dropped as a month inside a header's list. A partial obshtina is
   drawn whole (GISCO has no unit below it) and the card lists it
   (`geom_units_partial`). The list is drawn when at most 5 % of its names
   miss (`LIST_MAX_MISS_SHARE`). One name the regulator writes for two obshtini
   is grouped (`commune.OBSHTINA_GROUPS`, scoped to its oblast): "Добрич" is
   the city (BG_DOB28) and the rural obshtina it is an enclave of
   (Добрич-селска / Добричка, BG_DOB15) — the ИАЛВ's Черноморски район spec
   files "гр. Добрич" and Добричка's villages under one "Община Добрич".
   Дунавска равнина: 119 units, 17,316 → 47,445 km² (21 partial);
   Тракийска низина: 93, 55,220 → 43,393 km² (21 partial) — its
   member-PDO union had drawn all of north-east Bulgaria (Bétard's
   Черноморски район PDO), which Дунавска равнина's text claims; the two
   PGIs no longer overlap.
3. **`region-pdo-union`** — a PGI whose list does not resolve: the union
   of its member-PDO Figshare polygons (`BG_PGI_MEMBER_PDOS` in
   [scripts/_lib/bg/geometry.py](scripts/_lib/bg/geometry.py),
   hand-verified against the 5-region structure and the north/south
   Stara Planina partition). Not hit since 2026-10-24.
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
2. **`gisco-commune-list`** — the units the area text names, drawn from
   GISCO LAU `EL_*` polygons (CNTR_CODE='EL' — the EU country code for
   Greece, *not* ISO `GR`; ~6,142 δημοτικές κοινότητες in LAU 2024).
   Since 2026-09-24 this is the **area-units layer**
   ([scripts/_lib/gr/commune.py](scripts/_lib/gr/commune.py)
   `parse_area_units` + [scripts/_lib/gr/geometry.py](scripts/_lib/gr/geometry.py)
   `units_union`), which reads the ΥΠΑΑΤ spec's delimitation prose as
   well as the EU-OJ commune list — 60 PGIs draw from it (`how:
   area-units`) and 14 more from a curated prefix pin, against 2 before. What the parser separates:
   *communities* (Δ.Δ. / Τοπικές Κοινότητες, one LAU row each);
   *δήμοι and δημοτικές ενότητες named as members*, expanded to the
   GISCO unit that carries them (the 9-character prefix = the pre-2011
   Kapodistrian municipality; the 7-character Kallikratis municipality
   for a text from 2011 on whose δήμος is the seat's; "τα Δ.Δ. του
   Δήμου X" always); *containers* — the unit a list hangs from ("Δ.Δ.
   Λευκών του Δήμου Πάρου", "Τοπικές Κοινότητες … της Δημοτικής
   Ενότητας Αταλάντης", a δήμος followed by "και συγκεκριμένα" / "(") —
   which are never members, unless a conjunction joins them ("καθώς και
   της Δημοτικής Ενότητας Ερυθρών"); *localities* below the community
   tier ("την περιοχή Ριτσώνα του Δήμου Αυλίδας", "την περιοχή με
   τοπωνύμιο «Πύργος Βασιλίσσης» στο Ίλιον Αττικής"), drawn as the
   container that holds them and reported as a proxy; *former επαρχίες*
   ("τέως επαρχίας Θηβών" — a tier GISCO never carried, resolved only
   through the `eparchies` table of the pin file, and the area even when
   the sentence also names the prefecture); a *boundary traced through
   named places* ("οριοθετείται από την διαχωριστική γραμμή Δροσιά-
   Άνοιξη- Άγιος Στέφανος- …", Πλαγιές Πεντελικού), drawn as the polygon
   those places outline, in the text's order, each place at the point
   [scripts/_lib/gr/landmarks.json](scripts/_lib/gr/landmarks.json) gives
   it (Wikidata CC0 items, cited; GeoNames CC BY 4.0 as the second
   gazetteer, the GR dump cached under `raw/geonames/`) — so the interior
   the line encloses (Σταμάτα, Ροδόπολη) is drawn, a place no gazetteer
   locates is listed as not drawn and the line runs straight between its
   neighbours, and the card says the polygon is approximate
   (`geom_units_boundary`; with fewer than four located places the units
   the located ones lie in are drawn instead, `geom_units_boundary_units`);
   and the *whole-unit* texts ("το σύνολο του νομού", "στα διοικητικά
   όρια του νομού Ηλείας", "ευρύτερη περιοχή του Ν. Γρεβενών"), which are
   left to the NUTS step — "της νήσου Κεφαλληνίας" after a named περιοχή
   only says where it is. Exclusions ("Εξαιρούνται …") end the parse; the
   boilerplate tail (the NUTS line, "Νομικό πλαίσιο") is cut; former-tier
   glosses "(πρώην …)", "(προ Καλλικράτη)" and settlement parentheticals
   "(οικισμοί …)" are dropped; a decree's abbreviations ("Δ.Δ", "Κ.
   Τιθορέας", "Αγ. Άννης", "Αρχ. Ολυμπίας"), a Latin letter typed inside
   a Greek word ("Μυρoδάτου") and a hyphenated line break ("Πύρ-γου")
   are read as written, and so is a stray full stop after a tier word
   ("… και Δένδρων Τυρνάβου της Δημοτικής Ενότητας. Τυρνάβου …", Τύρναβος'
   2026 document, which had cost it the community — `_STRAY_TIER_STOP_RE`,
   Ενότητας / Κοινότητας only). Name matching: exact on the normalised name; a
   trailing qualifier ("Μαρκοπούλου Αττικής", "Παλλήνη Αττικής" — the
   NUTS name in any case); then, inside the spec's NUTS unit, a
   **phonetic** key (η ι υ ει οι → ι, ο ω → ο, αι → ε, double consonants
   collapsed — Κομήτου / Κομίτου, Ρογών / Ρωγών) and a **stem** key (the
   inflection ending removed — Κερασίτσας / Κερασίτσης, Πυθαγόρειο /
   Πυθαγορείου, Παιανία / Παιανίας; Άγιος / Αγίου is the one word
   stemmed below four letters); the head of a compound GISCO name
   ("Σπάτα" → Σπάτων - Λούτσας); the tail of a two-word item, as a proxy
   ("Μοναστήρια Μεταξάτων" → Δ.Κ. Μεταξάτων); a former δήμος whose
   seat's name ends in it (Δήμος Αιδηψού → Λουτρών Αιδηψού); and, only
   inside a unit the text itself names as a container, a typo-tolerant
   match (rapidfuzz ≥ 88 on the phonetic key, runner-up ≥ 8 behind —
   Κοιλάδα Αταλάντης' "Καλοποδίου" / "Μεγαπλατάντου" against Καλαποδίου
   / Μεγαπλατάνου of Δ.Ε. Αταλάντης). **Scope**: the spec's NUTS line
   bounds every name ("a. Περιοχή NUTS GR242 Εύβοια"), and a spec with
   no NUTS line is bounded by its curated NUTS pin; a row outside it is
   kept only where the text names the unit it lies in (Πλαγιές
   Κιθαιρώνα: Βοιωτία and Αττική), and a nationwide homonym is kept
   only in a δήμος the unambiguous names already established. The union
   is used only when at least as many items resolved as failed. Names GISCO does not carry as such — a spelling the fold
   cannot reach (Αμυγδαλιάς / Αμυγδαλέας, Βασιλικών / Βασιλικού), a
   renamed village (Μιράκα → Αρχαία Πίσα, ΦΕΚ 145Α/1997), a former
   δήμος whose seat has another name (Δήμος Νέστορος, seat Χώρα) — are
   pinned per record in
   [scripts/_lib/gr/commune_overrides.json](scripts/_lib/gr/commune_overrides.json)
   (slug → name as written → GISCO id or unit prefix, each with the
   el.wikipedia article of the former unit whose community list matches
   the prefix's rows, or the GISCO row checked against the spec; every
   pin confirmed by two independent reviews — a pin may name several
   ids where one spec name covers several rows, Ελασσόνα's nine Δ.Δ.; a
   pin on a list's container widens the record, so only a unit the spec
   itself draws whole gets one; an empty pin keyed "επαρχία X" marks a
   source defect — Ρετσίνα Κορωπίου's spec pastes Καρύστου's
   delimitation — and draws nothing). The file's `eparchies` section
   holds the former επαρχίες as the 9-character prefixes of their
   1997–2010 δήμοι (Θηβών, Μεγάρων, Χαλκίδας, Καρυστίας), from the
   el.wikipedia article of the eparchy with each δήμος article's
   community list matched to the prefix's rows and the 1991 ΕΣΥΕ census
   as the tie-breaker (Μετόχι Διρφύων is Χαλκίδας, not Καρυστίας). A
   record drawn from LAU units reads its region facet from the NUTS
   unit the spec cites, else from the NUTS-3 units its polygon lies in
   (`nuts_ids_covering`).
   Curated whole-unit pins live in `_GR_PGI_PREFIX`
   ([scripts/_lib/gr/nuts.py](scripts/_lib/gr/nuts.py)): Σιθωνία, Κως,
   Λέσβος, Μακεδονία (its single document's twelve regional units by
   prefecture prefix plus the ten Κιλκίς communities it names — Thasos
   and the rest of Κιλκίς excluded), the whole prefectures and islands
   whose NUTS-3 unit pairs them with a neighbour (Γρεβενά EL_15 and
   Κοζάνη EL_14 in EL531, Αργολίδα EL_41 and Αρκαδία EL_40 in EL651,
   Καρδίτσα EL_23 in EL611, Λακωνία EL_43 and Μεσσηνία EL_44 in EL653,
   Θάσος EL_0401 in EL515, Ικαρία EL_5401 in EL412 — a completeness
   screen of every NUTS-level record, 2026-09-24, each refuted twice)
   and the island of Euboea for Ρετσίνα Ευβοίας (the prefecture's units
   without Σκύρος and the two Boeotian-shore units Ανθηδόνος / Αυλίδος). The record carries what the text
   named that could not be drawn (`geom_units_unmatched`), the
   localities drawn as their container (`geom_units_proxied`) and the
   places a boundary line names (`geom_units_boundary`, the polygon they
   outline; `geom_units_boundary_units` when only their units could be
   drawn); the panel and the SSR card render all of them (labels of the
   same names), so a partial or approximate union is never silent.
3. **`gisco-nuts-region`** — the PGI fallback for a whole-unit text
   ("όλες τις περιοχές του νομού", "τη νήσο Θάσο"), a text that names
   no unit GISCO carries, or a parse the guard refused. The spec's
   "Οριοθετημένη περιοχή" section cites a NUTS code + regional-unit /
   region name (`GR232 Αχαΐα`, `GR30 Αττική`), so the honest geometry is
   the GISCO NUTS polygon for that unit.
   [scripts/_lib/gr/nuts.py](scripts/_lib/gr/nuts.py) resolves it:
   curated `slug → [NUTS_ID]` override → the spec's cited NUTS name →
   appellation name, matched (Greek-normalised, island-list-token-aware)
   against GISCO NUTS-3 (52 EL regional units) + NUTS-2 (13 EL regions).
   The curated override carries the residual that strict name-match
   misses — the Attica retsinas whose text names only "Αττική", the
   Cyclades / Dodecanese (NUTS-3 labelled by island list), Θράκη (its
   three regional units, not "Ανατολική Μακεδονία, Θράκη") and Αιγαίο
   Πέλαγος (both Aegean NUTS-2 regions). The record carries its NUTS ids
   (`geom_nuts_ids`, panel payload) so
   [scripts/audit_geometry_outliers.py](scripts/audit_geometry_outliers.py)
   can re-derive a clip on such a union (Gavdos off Κρήτη, the
   Strofades off Ζάκυνθος). Precision is regional-unit-level; the panel
   says so. Three umbrella PGIs whose text is a cross-reference to their
   member GIs' zones (Ήπειρος, Στερεά Ελλάδα, Πελοπόννησος) still draw
   the NUTS-2 region — see CURATOR_TODO.
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
  chasselas-rose). A malformed .doc antiword rejects (Σιάτιστα) is
  salvaged from its UTF-16 stream; with no header lines the area
  paragraph is windowed by anchor (`_geo_window`, "ΟΡΙΟΘΕΤΗΜΕΝΗ
  ΠΕΡΙΟΧΗ" → the next heading) the way the terroir narrative already
  was. Sidecars land in `raw/gr/national-specs-extracted/`
  (132: 127 with grapes, 131 with terroir text). Two header passes since
  2026-10-23: the strict one folds the U+2206 Delta a PDF heading font pads
  ("8. ∆ ΕΣΜΟΣ …", Malvasia Χάνδακας-Candia — its link header was never
  recognised and the grape body ran through the history), takes no line that
  starts lowercase, ends on a comma, holds a sentence boundary or ends on an
  article, and re-opens no pre-link role after the link; the lenient one is
  the reading of 2026-05 unchanged, and wins unless it hung the grape
  section on a line the strict rules reject while the strict pass found a
  real header (`read_sections_and_grapes`, shared with the CY parser) — a
  count never decides between a precise reading and a loose one. 21 records
  switched to the strict sections (their link narrative whole instead of cut
  at a sub-heading; re-extracted in phase D). **The link ends at the
  template's trailing sections** (2026-10-24, `POST_LINK_ROLE`): "8. ΑΛΛΕΣ
  ΠΡΟΫΠΟΘΕΣΕΙΣ", "9. ΕΦΑΡΜΟΣΤΕΕΣ ΑΠΑΙΤΗΣΕΙΣ", the control authorities, the
  application form ("ΔΙΚΑΙΟΛΟΓΗΤΙΚΑ", "ΓΛΩΣΣΑ ΑΙΤΗΣΗΣ", "ΣΥΝΔΕΣΜΟΣ ΜΕ ΤΗΝ
  E-BACCHUS") and the ministry letterhead carried no role, so the link ran
  to the end of the document in 123 of the 151 GR / CY sidecars (41 by more
  than 1,000 characters), and the form's "Δεσμός: http://…" re-opened it by
  the bare link keyword. A capitalised header of those sections — tested
  before the role keywords once the link has opened, under the strict
  header rules in both passes — opens a post-link role that no reader
  consumes (`parse_styles` reads `additional_conditions` for the categories
  a labelling rule names, and the phase C styles stay as settled), and
  after it nothing re-opens a role. Every link change was a pure prefix
  cut; no roster, style or area unit moved (27 area texts lost the legal
  block a re-opened area header had swallowed — only their `decree_year`
  shifted, all still before the 2011 tier threshold) and the stage-04
  prose scan loses no slug; the terroir caches of the 123 were re-run
  (`gr-anchor-2026-10-24`). The salvage window's end anchors carry the same
  headers in folded form — its "προϋποθεσεισ" anchor had kept its
  dialytika and could never match. `tests/test_gr_spec_link_end.py`. A
  grape section written as sentences is read as enumerations ("… των
  ποικιλιών Ασύρτικο, Αθήρι, … και Malvasia di Candia aromatica", every one
  in the section, the trailing clause cut, a parenthetical synonym taken for
  the cultivar — "Αθήρι μαύρο (Μαυράθηρο)" —, a missing comma split, a
  candidate always capitalised), ahead of the capitalised-word scan whenever
  it reads three names; "εκτός των δύο τελευταίων … μέχρι 15 %" and "εκτός
  της ποικιλίας X που … μέχρι 20 %" make accessories. The colour table
  carries the inflected forms the specs use (ερυθρούς, ερυθρωπούς, λευκούς
  …), a one-word form counts only as a whole token beside a wine word (οίνος
  / κρασί within three tokens) — "λευκά" is not Λευκάδα, an aged red's
  "ερυθρωπές αποχρώσεις" not a rosé — and the style scan reads the
  winemaking-practices section, where a spec states the categories it makes
  (Ήπειρος's sparkling, Paros's yield "για τον ερυθρό και ερυθρωπό οίνο").
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
  churning AT code. The first such quirk (2026-10-24): the 2024/1143
  template opens each wine of section 6 on a product line, "Weinbauerzeugnis"
  then "Wein, weiß" / "Qualitätswein rot" / "Perlwein rosé, Blanc de
  Noir(s)", whose colour adjective `PRODUCT_COLOUR_WORDS` reads (Rheinhessen
  and Landwein Main had read none); and a style word its own sentence
  negates with "kein" is not a style ("darf keine Perlage … entwickeln, der
  den Wein in die Kategorie Perlwein einordnet"; "nicht" negates the verb —
  Rheinburgen's "nicht den für die Angabe „lieblich“ höchstzulässigen Wert
  übersteigen" allows a lieblich wine). The AT table has neither yet; no AT
  record is on that template. The second (2026-11-07): Bürgstadter Berg's only publication is the
  2016 Commission decision (OJ C 384, CELEX 32016D1018(01)), which prints the
  anchor as `doc-ti` paragraphs ("ANHANG", "EINZIGES DOKUMENT") and heads § 7
  "Wichtigste Keltertrauben"; `DOC_ANCHOR_RE` accepts the class and the role
  table the heading, so the Einzellage left its May stub (eight varieties,
  its own link text) instead of inheriting Franken's card.
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
  collective brands. A Landwein coextensive with one Anbaugebiet keeps
  that name (Badischer → Baden, Landwein Neckar and Schwäbischer →
  Württemberg); one that straddles several takes its Bundesland
  (Taubertäler → Baden-Württemberg, 2026-09-24). Curated `_REGION_BY_FILE_NUMBER` covers every wine
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
  extraction, because cantonal règlements frequently bury the variety
  list in an annex or refer to an external annex by article —
  section-scoped extraction missed most of the recall. Scanning ~50 KB
  of regulatory prose is noise-prone, though, so `extract_varieties`
  guards the shared `match_variety` three ways (2026-06): a
  **commune-name guard** (a chunk that is a Swiss commune — Genève,
  Sion, Cortaillod — is area prose, not a grape), a **fuzzy floor**
  (`_CH_FUZZY_FLOOR`=95: weak fuzzy hits matched common words / place
  fragments to obscure non-Swiss grapes — `vigne`→viognier,
  `Nein`→durif), and a small **`_CH_STOP_SURFACES`** set for prose
  words that are exact grape aliases out of context (`canton`→chenin,
  `Säure`→calitor, `weisse`→valente). Candidate cleaning strips
  leading FR/IT/DE determiners (`il Merlot`, `la Bondola`), `a)`/`°`
  ordinal markers, and footnote tails, and adds a name-before-number
  variant to recover must-weight (Mostgewicht) lines
  (`a) Blauburgunder 19,4 °Brix`). The Swiss Agroscope crossings +
  natives the scan surfaces (Garanoir, Mara, Galotta, Doral, Divico,
  Carminoir, Diolinoir, Bondola, Completer, Gouais→heunisch) live in
  the shared `grape_lexicon.py`; Cornalin / Humagne are deliberately
  NOT folded yet (Valais Cornalin = Rouge du Pays vs Humagne Rouge =
  Cornalin d'Aoste is an identity tangle that needs a VIVC pass).
  Commune extraction stays section-scoped because
  whole-document commune scans generate huge false-positive lists.
  Variety extraction recall (post-2026-06 FP cleanup — counts dropped
  because the prior figures double-counted prose/place false positives
  that the new guards remove, and rose where Mostgewicht recall recovers
  real lists): 11 cantons return non-zero cantonale-tier varieties;
  AG (65), GE (51), VS (44), VD (38), LU (25), TI (22), NE (15), BL (7),
  SG (4), OW (4), GR (2). The other cantons (AI, AR, BE, BS, GL, JU, NW,
  SH, SO, SZ, TG, UR, ZG, ZH) now return 0 at the cantonale tier:
  some defer to federal OVin without cataloguing varieties locally
  (AI/AR/BS/NW/SZ/UR; BS defers to BL via inter-cantonal Vereinbarung;
  tiny corpora ~5 ha each), and the rest (BE, GL, JU, SH, SO, TG, ZG,
  ZH) DO grow wine but either publish a règlement too sparse to parse
  (ZH/SO are ~3 KB with no variety list) or enumerate varieties in a
  Mostgewicht / annex form the scan doesn't yet recover — a known
  recall gap, not a regression (their prior non-zero counts were
  entirely prose/place false positives now removed).
  **Roster annex and rosters by reference (2026-10-13, visitor flag on
  Basel-Stadt).** Basel-Landschaft's Verordnung über den Pflanzenbau
  (SGS 516.31) keeps its AOC roster in a two-column "Anhang 1 –
  Zugelassene Rebsorten" (§ 16 Abs. 1); `annex_roster_block` /
  `table_varieties` in `_lib/ch/reglement.py` read that table down each
  column, one variety per cell (a cell's synonyms, breeder codes and
  bracketed glosses only help it match; "Versuchssorten" / "Interspezifische"
  are placeholders), instead of the whole-document scan, which had read
  the § 5 altitude rule's "bis und mit Riesling-Silvaner" as a Sylvaner.
  The same ordinance names «AOC Basel-Stadt» and «AOC Solothurn» (§ 11
  Abs. 2), and both cantons apply it by agreement (BS SG 911.200 § 1 lit. b
  "… die Ursprungsbezeichnungen"; SO BGS 516.34 § 1 Abs. 2 "… Kapitel C.
  Weinbau"), so `ROSTER_BY_REFERENCE` in `ch/02_extract_reglements.py`
  gives them BL's roster with a `cantonal-reglement-roster` source that
  carries the applying clause; the panel lists it as a second règlement
  row (`cantonal_roster_*`). Before, both cards showed no grape and the
  empty-grapes audit had pinned them REVIEWED. AI / AR / GL / TG delegate
  their roster to a separate act (Standeskommission, Regierungsrat,
  Fachstelle list) that is not fetched — the remaining recall gap. VIVC
  lists HEIDA and PAÏEN on both Savagnin blanc and Gewürztraminer; the
  Swiss texts mean Savagnin blanc (Valais OVV "Savagnin blanc (Païen ou
  Heida)"), pinned in `GRAPE_ALIAS`.
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

  Per-AOC varieties (2026-10-04): the TI regolamento's art. 23 splits the
  DOC roster by grape colour ("a) per le uve rosse: … b) per le uve
  bianche: …") and art. 20 reserves «Rosso - Bianco - Rosato del Ticino»
  to blends of one colour, so each tier takes its colour's list and an
  explicit style (`colour_blocks` + `list_varieties` in
  `_lib/ch/reglement.py`); the DOC Ticino takes both lists (the
  whole-document scan had added Alphonse Lavallée, Léon Millot and
  Plantet from the list of varieties barred from blending). The VS
  Grands Crus take OVV art. 88's list (`grand_cru_block`). The other
  règlements carry no per-sub-AOC variety rule: GE has one annex for every
  AOC Genève wine, VD's Dézaley / Calamin Grand cru have must weights for
  whites, Gamay and other reds, BE / SZ / FR use one cantonal list.
- Sub-denomination model: tier "régionale" and "locale" entries are
  tagged `is_sub_denomination=true` with `parent_slug` = the same
  canton's "cantonale" AOC slug (when one exists). Orphan régionale
  (FR's Cheyres — FR has no cantonale entry) stay flat. The
  GE premier crus (22 records, tier="locale") all carry
  `parent_slug=geneve`. Same data shape as FR DGCs / ES subzonas /
  IT sottozone / DE Einzellage.
- **An intercantonal AOC belongs to every canton it spans**
  (2026-10-25, the Maasvallei rule one level down): no sub-denomination,
  no parent; `co_parents` = the cantonal AOC of each canton that has one
  (`_co_parents_for` in CH stage 02). Vully → Vaud (Fribourg has none, so
  it also stays a top-level row in Trois-Lacs); Zürichsee → Schwyz and
  Zürich — until then Schwyz's sub-denomination, drawn as Schwyz alone. Stage
  04 lists the record under each co-parent (`children_by_parent`: the
  related-appellations list, the sibling filter, the entity nav), the sidebar
  nests it under every co-parent in that co-parent's region group and counts
  it once per country, the card says "Also part of" with links
  (`co_parent_of`, `co_parent_names`), and it inherits nothing: no facts, no
  parent polygon — without a commune list the whole-canton fallback draws
  every canton it spans. `co_parents` is sparse and pipeline-agnostic; any
  stage 02 may set it. Zürichsee's area is each canton's own ruling,
  transcribed in `INTERCANTONAL_AREAS` (`_lib/ch/per_aoc_carving.py`,
  `resolve_intercantonal_area`, every name held to its canton): the seven ZH
  Bezirke of the Strickhof Verfügung of 26 June 2020 Ziff. III (Meilen,
  Horgen, Uster, Pfäffikon, Hinwil, Affoltern, Zürich — expanded through the
  swissBOUNDARIES Bezirk layer, `CHCommuneIndex.in_bezirk`) and the ten SZ
  communes of the Allgemeinverfügung of 28 July 2025 Ziff. 2.1 (Freienbach,
  Wollerau, Feusisberg, Altendorf, Lachen, Galgenen, Wangen, Schübelbach,
  Tuggen, Reichenburg): 76 communes, `swissboundaries-commune-union`, both
  rulings in its sources (`cantonal-area-ruling`, card rows
  `cantonal_area_rulings`).
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

  Their roster is OVV art. 88's ("L'appellation Grand Cru est réservée aux
  cépages suivants": ten whites, five reds — Amigne, Humagne blanc, Rèze,
  Cornalin du Valais and Humagne rouge are not in the grape lexicon yet,
  pending a VIVC pass), not the Valais AOC list; a communal règlement may
  narrow it again. Each entry resolves to a single-commune polygon via
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
2. **`parent-appellation`** — sub-denominations (régionale + locale tiers)
   inherit the parent's polygon when their commune list is empty
   (the bulk of VD's sub-denominations + some BE/FR/SZ/ZH entries). The
   source string was `parent-aoc` until 2026-10-22; the shared spelling
   lets the hover hit test, the card's approximate-area note and the
   audits treat Calamin, Dézaley, Dézaley-Marsens, Côtes-de-l'Orbe and
   Zürichsee like every other inheritor.
3. **`swissboundaries-commune-union`** — parse the canton règlement
   for commune mentions (via `CHCommuneIndex.scan_text`) and union
   the matching swissBOUNDARIES3D Gemeinde polygons by BFS_NUMMER.
   Hit rate: VD (100), TG (50), SG (48), SH (16), BE (9), NE (5),
   FR (1). A cantonal AOC whose scan finds only the seat of government
   (`CANTON_CAPITAL` in `_lib/ch/canton.py` — the title or signature
   line, "Kanton Zürich", "Delémont, le …") gets no commune list and
   falls to step 4: until 2026-10-13 nine AOCs (AI, BS, GL, JU, LU, SO,
   SZ, ZG, ZH) were drawn as their capital town — Zürich without the
   Weinland, Basel-Stadt without Riehen — though this paragraph already
   said they were not.
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
  don't pollute the unknowns queue. A name that wraps onto a lower-case
  second line at the Odroda column ("Veltlínske červené ⏎ skoré", the five
  modern specs) is joined before matching (2026-10-22): read line by line
  the row was "Veltlínske červené", Roter Veltliner, and an alias had patched
  the wrap instead of the reader. A cell that is a colour word and a
  registered cultivar — "Rosa", VIVC #22422, in the five modern specs — binds
  through `grape_entity.match_roster_cell` (2026-10-23). No principal/accessory split (same as
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

### SK register-fiche roster for a non-stub with a narrow § 7 (2026-11-07)

Stredoslovenská's EU single document (OJ C 122/2020) names one variety in
§ 7 — Furmint — where the register's 2013 technical file lists ten MAIN and
thirty OTHER varieties; the card carried one pill (CURATOR_TODO,
`/validate-cards` 2026-10-23). `augment_sk_records_with_register_fiche`
([scripts/_lib/augment/sk.py](scripts/_lib/augment/sk.py), after the
national-spec augmenter, before the roles overlay) gives a non-stub SK parent
whose document roster is under half the fiche's (`fiche_roster_is_wider`) the
fiche's roster: the document's own § 7 varieties stay principal, the fiche's
MAIN join them, its OTHER are the accessories (details carry `source:
eambrosia-register-fiche`), the record and the shared
`_REGISTER_FICHE_ROSTER_BY_SLUG` (renamed from `_CZ_FICHE_ROSTER_BY_SLUG` —
the CZ pattern in reverse, there the fiche is the narrower list) carry the
provenance, and the card's Sources list the fiche
(`src_register_fiche`). `fiche_roles.overlay` returns `fiche-roster` for such
a record (its roles are already the fiche's). Only Stredoslovenská qualifies
(Skalický rubín's and the two Tokaj fiches carry no split).
`tests/test_sk_fiche_roster.py`.

The same session read the SK colour statement "Farba: biela, ružová a
červená" and a list sharing one noun ("biele, ružové a červené vína") —
`jednotny_dokument.colour_list_styles`, the RO rule of 2026-10-25; the
compound table had matched "ružové vína" alone, so Stredoslovenská's white
never read. A list inside an analytical limit ("najviac 150 mg/l pre červené
a 200 mg/l pre biele a ružové vína", the EU sulphite ceilings every document
restates) states no colour and is skipped (`_is_analytical`).

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
Sbírka zákonů částka 32/2017 + částka 92/2010, linked on the card as
`https://e-sbirka.gov.cz/sb/2017/88` and `…/sb/2010/254` (`SOURCES`
`canonical_url`; the old `aplikace.mv.gov.cz` viewer has answered 404 since
the e-Sbírka migration, 2026-10-24). Czech law text is
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
   the ES MAPA / IT MASAF / DE BLE pattern. **Except where the EU-register
   fiche names the appellation's own roster** (2026-10-22, after a visitor
   flag on Znojmo): a fiche § 6 naming fewer than half the decree's
   varieties (`FICHE_OWN_ROSTER_MAX_SHARE` in
   [scripts/_lib/augment/cz.py](scripts/_lib/augment/cz.py)) is the
   record's roster — VOC Znojmo's three white varieties (a víno originální
   certifikace under § 27 of Act 321/2004 takes its varieties from the VOC
   association's rules, not the decree; the card had listed 67, reds
   included), Novosedelské slámové víno's five — carried as `principal`
   with `register_fiche_roster` provenance (panel source line
   `src_register_fiche`, the Vyhláška line omitted); a podoblast fiche
   reproduces the decree's list of its day (55) and keeps the current
   decree's 67; a fiche that opens its roster ("všechny další odrůdy
   uznané …", the sidecar's `open_roster`) takes the decree's remainder as
   its accessory list (Litoměřická: 19 principal + 48), a closed one does
   not (Šobes: 8 + Pálava, which its § 6 lists under "b." only). Šobes and
   Litoměřická are the 2011 technical-file template — § 6 "Hrozny" in
   a. / b. / c. blocks, headers indented past the parser's 6-space guard —
   read since the same day by [scripts/extract_register_fiches.py](scripts/extract_register_fiches.py)
   (`extra_kw` "hrozny" / "vymezená oblast"; block a. → principal, b. / c.
   → accessory; in the newer template a bulleted line's "(MAIN)" / "(OIV)" /
   "(OTHER)" tag decides, never the bullet — Hungary writes "** Hárslevelű
   (MAIN)" — and an "(OIV)"-tagged variety is read, not stoplisted;
   `tests/test_register_fiche_roles.py`) and
   [scripts/_lib/fiche_technique.py](scripts/_lib/fiche_technique.py), whose
   header chain is built twice, at 6 and at 12 spaces, the deeper pass
   taken only when it extends the shallow chain without changing it (six
   Greek fiches carry an indented "7. ASSYRTIKO" variety line; of 332
   cached fiches only Šobes and HU Etyek-Buda change; no HU stage reads
   the fiches, Etyek-Buda's card comes from its EU single document).
   Šobes's facts ground on its own § 7 from then on,
   not the shared Morava text. `tests/test_cz_fiche_roster.py` and
   `tests/test_fiche_sections_chain.py` pin it. The same flag
   added the participle stems `ovlivn` / `ovplyvn` to the cs / sk
   connective tables: "Barevnost je ovlivněná … slunečním zářením" had been
   demoted to the natural factors as an unearned interaction.
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
- **The slicer is monotonic (2026-10-23).** `extract_sections` accepts a
  top-level header only as the next integer, or a sub-number of the last
  accepted one, and never a nested item (a title starting lowercase, "Een
  gemiddelde maximum gemeten …", a yield row): the Flemish amendments nest
  per-wine-type blocks "1.", "2.", "3." inside section 4 and nine yield rows
  inside 6, which read first-come had overwritten the real sections and left
  Hagelandse, Haspengouwse and Heuvellandse wijn without a description — so
  their "Rosé-wijnen: fijn, elegant …" was never read. The fiche's
  "DESCRIPTION DU OU DES VINS" title and the bare "rosé" / "rosés" of both
  languages are in the style tables.
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
fileNumber  →  POST /api/gi-applications/filter {"first":0,"rows":5000,"showTSGs":"false","filters":[]}
            →  map row.fileName → row.id          (cache the one ~4 MB response)
id          →  GET /api/gi-applications/id/<id>    (NOTE: no /v1/ in this path)
            →  singleDocTechFile[].uri → /api/v1/attachments/<uri>   (EU single document, uniform template)
            →  productSpecifications[].uri → /api/v1/attachments/<uri> (full national cahier, varied layout)
```

Gotchas (verified 2026-06-01 spike): the internal `id` is **not**
`int(giIdentifier[4:])` — that 500s for ~1/3 of GIs (e.g. PDO-CZ-A0888 =
appUniqueId EUGI…2821 but real id 8225), so resolve it from the bulk
filter listing above (the per-wine fileNumber filter's operation enum is
finicky; the empty `{"filters":[]}` list is reliable). The GI-detail path
is `/api/gi-applications/id/<id>` with **no `/v1/`** (the attachment
endpoint DOES use `/api/v1/`). The attachment endpoint is **browser-gated**
— it serves an HTML stub unless the request sends a real browser UA **and an
Accept WITHOUT `application/pdf`** (an explicit pdf Accept trips the gate),
and answers **HTTP 202 with the PDF body**. Stage 01 special-cases the
register host (`_BROWSER_HEADERS`) and accepts 202-with-pdf.

**Spike result (2026-06-01, `tmp/eambrosia-spike-findings.md`):** 47/47
sampled grandfathered/stub wines across ES/IT/SI/HR/BG/GR/HU/RO/CZ/SK/LU
resolved to a fetchable `singleDocTechFile`; all inspected (10, across 9
languages/scripts) were text-layer, uniform EU template, with terroir +
variety sections. **Viable as the primary stub fallback behind one
per-language fiche-technique parser** (role keywords already exist in the
per-country parsers); keep the bespoke national-spec scrapers (ES MAPA /
IT MASAF / SI–HR–BG / RO ONVPV / SK ÚPV / CZ SZPI / HU termékleírás) as
secondary. Implementation pending — **CZ is the recommended first build**
(today its terroir is shared-region only; the per-DOP fiche would give
per-DOP terroir + varieties). Tracked in CURATOR_TODO (cross-country).

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
0 stubs.** Since its cancellation (Reg. (EU) 2026/1068) the register's
newest OJ C for Ambt Delden is the cancellation request C/2025/6054, which
the newest-OJ-C rule would fetch: the 2018 document is pinned in
`raw/nl/oj-pages/manual_overrides.json` (2026-10-24).

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
- **Rosé comes from the text, never from a berry (2026-10-23).** The
  `_GRAPE_COLOUR_TO_STYLE` floor maps a gris / rose berry to white in the NL,
  BE, SK, HU and BG parsers (a Pinot gris makes white wine; Drenthe and the
  other provincie PGIs had shown Rosé their single document never names), and
  the NL text test reads the rosé the documents write — bare "rosé",
  "roséwijn(en)", "rosékleur", the English template's "Rosé" — in the
  description, category, winemaking and "Wijncategorie" sections and their
  titles (Twente numbers one section per category and names it in the
  title). GB and MT follow the same rule since phase C (see "Style pills").
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
   `PDO-NL-02873` Twente). Not on the map and not in the sidebar
   either: stage 04 skips a record without a polygon before the
   feature list is built, and the startup blob is built from the
   features (verified 2026-11-09; the four German Landwein PGIs on this
   step are absent the same way). Until Phase 2 parses commune lists
   from their ENIG DOCUMENT against shared GISCO LAU (the RO IGP / BG
   fallback pattern).

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
| extract_register_fiches.py --country mt | (network: the eAmbrosia register) | raw/mt/register-fiches/*.pdf + raw/mt/register-fiches-extracted/*.json (the 2011 single documents) |
| mt/02_extract_pliegos.py | raw/mt/oj-pages/*.html + raw/mt/register-fiches-extracted/ | raw/mt/dokumente-extracted/*.json + _index.json |
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
- **Styles read the register's single document too (2026-10-23).** The OJ
  documents are amendments that restate only the sections they change; the
  2011 single document they leave in force ("Red, white and rosé wines are
  produced …", "Sweet wines", categories 1 / 4 / 15 / 16) is extracted with
  `extract_register_fiches.py --country mt` and read by `mt/02` beside the
  amendment (its 5.1 practices included: "1. Passito", "DOK 'Riżerva' white
  wines"); the card cites it. A red grape no longer adds a rosé. The
  Maltese Islands stub is not wired to its fiche yet (CURATOR_TODO).

### The Maltese Islands IĠT is built from its register fiche (2026-11-07)

The PGI has no OJ publication, so it had been a stub with no roster, colour
or area on its card, although the register's 2011 single document carries
them all (`extract_register_fiches.py --country mt`, 2026-10-23). `mt/02`
`build_record_from_fiche` makes the record of a wine with no HTML cache but a
fiche sidecar with a roster: the fiche's varieties with their MAIN / OTHER
tags (10 principal, 46 accessory), its description ("Red, white and rosé
wines are produced …") and categories read by `parse_styles`, its demarcated
area and link text; `source.kind` is `eambrosia-register-fiche`, the record
is not a stub, and stage 04's MT source block emits no EUR-Lex key for it,
only `register_fiche_url`. `tests/test_mt_fiche_record.py`.

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

## United Kingdom pipeline (`scripts/gb/`)

Country #19, and the first **post-Brexit** register in the corpus: the
UK is no longer part of the EU GI scheme, so *both* of the spines every
other country leans on are unavailable. eAmbrosia still lists the UK's
pre-2021 names as legacy rows, but Sussex — registered in 2022 under the
UK scheme — is not an EU registration at all; and Bétard 2022 is an **EU**
PDO layer that carries no `PDO-GB-*` geometry. Both are replaced by
UK-domestic sources.

Corpus: **6 registered wine GIs** — 4 PDO (English, Welsh, Sussex,
Darnibole) + 2 PGI (English Regional, Welsh Regional). The country code
is `gb` (ISO 3166-1 alpha-2, matching the register's own `PDO-GB-*`
identifiers); `source_lang` is `"en"`, so GB joins Malta as an
English-source corpus needing no translation for the canonical `/`
surface.

**The UK has no stub tier.** Every registered wine ships a public
product specification, which makes it the only country in the corpus at
6/6 extraction with no national-spec fallback layer, no curator queue
for missing documents, and no `01b_solve_waf.py` — GOV.UK serves the
register and its attachments without a WAF, a cookie gate or a
JavaScript challenge.

Spine: the **GOV.UK "protected food and drink names" register**. DEFRA
publishes the UK GI schemes as a structured GOV.UK *finder*, queryable
through the site's own search API:

    https://www.gov.uk/api/search.json
       ?filter_format=protected_food_drink_name
       &filter_register=wines
       &filter_country_of_origin=united-kingdom

Each hit resolves to a per-GI content-API document
(`/api/content/protected-food-drink-names/<slug>`) carrying typed
metadata — protection type, status, application and UK/EU registration
dates, reason for protection — plus the **product specification** as an
attachment. A 7th name, *The Crouch Valley* (PDO, applied 2023-03-06),
is still in assessment and is filtered out by `status=registered` the
way the eAmbrosia countries filter theirs; `audit_gb_coverage.py`
reports it so the queue stays visible.

The register publishes **no GI file number** (only Sussex's
specification states one, in its own text: "PDO GB number: W0006").
Since the rest of the corpus keys on `PDO-xx-*` / `PGI-xx-*`, stage 00
bridges slug → file number via `_FILE_NUMBER_BY_SLUG`, verified against
`raw/eambrosia-register/gi-index.json` (all six UK wines are also listed
in the EU register — the five pre-Brexit names under the Withdrawal
Agreement, Sussex added 2025-01-31 under the UK-EU agreement).

| Script | Reads | Writes |
|---|---|---|
| gb/00_fetch_data.py | (network: GOV.UK search + content API, ONS Open Geography) | raw/gb/gov-uk/{index,manifest}.json, raw/gb/ons/{countries,counties}.geojson + manifest.json |
| gb/01_fetch_specs.py | raw/gb/gov-uk/index.json | raw/gb/specs/*.{pdf,docx} + manifest.json |
| gb/02_extract_specs.py | raw/gb/specs/*.{pdf,docx} | raw/gb/specs-extracted/*.json + _index.json + raw/gb/extraction-unknowns.json |
| gb/02d_extract_terroir_facts.py | raw/gb/specs-extracted/*.json + raw/wikipedia/aocs/en/ | raw/terroir-facts/*.json (country="gb") + manifest-gb.json |
| gb/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (country="gb") | raw/translations/terroir-facts/<fr\|es\|nl>/*.json |
| gb/03_generate_wiki.py | raw/gb/specs-extracted/*.json | wiki/<slug>.md (per GB record) + merges GB entries into wiki/_index.json |
| audit_gb_coverage.py | raw/gb/{gov-uk,specs,specs-extracted}/ + raw/terroir-facts/ | (stdout — coverage table + curator queue) |

GB-specific notes:

- `kind` is `"DOP"` / `"IGP"`. The UK register spells these out in
  English ("Protected Designation of Origin (PDO)"), but the corpus
  convention is the DOP/IGP pair — and concretely, the map's
  polygon-colour expression keys on `kind == 'IGP'`, so a literal
  "PGI" would silently mis-colour both UK PGIs as PDOs.
- **Three parser templates**, because the six specifications were
  written under three regimes
  ([scripts/_lib/gb/spec.py](scripts/_lib/gb/spec.py)):
  - **`defra-pfn-2011`** (4 records) — the December-2011 DEFRA
    specifications. A `PROTECTED NAME:` / `DEMARCATION:` header block,
    then one `PART n: <WINE CATEGORY>` block per grapevine category
    (`STILL WINE`, `QUALITY SPARKLING WINE`, plus a closing `GENERAL
    PROVISIONS` part that carries no wine). Each wine part opens with
    the link narrative, then `SPECIFICATION` and a run of upper-case
    subsections, of which `VINE VARIETIES` and `MAXIMUM YIELDS` are
    read. These carry the corpus's longest single variety rosters —
    81-85 resolved slugs each.
  - **`defra-pfn-application`** (Darnibole) — the 2017 EU application
    form: a numbered outline (`1. Details of protection` … `7.
    Demarcated area`) with lettered sub-items. It has **no link
    section** — the document stops after the demarcated area and its
    plan — so the terroir narrative is taken from `7 b) Definition of
    the demarcated area`, which is where the slate subsoil, the slope
    and the aspect are actually described.
  - **`uk-gi-single-document`** (Sussex) — the only post-Brexit
    UK-scheme registration, and the only `.docx`. A numbered EU-style
    single document with a proper `9. Link` section (9.1 natural + human
    factors, 9.2 characteristics, 9.3 causal link); varieties live in
    `7.2 Viticulture practices`, listed separately for sparkling and
    still. Parsed via the stdlib zip → `word/document.xml` route the HR
    pipeline already uses.
- **Roster parsing.** The still-wine rosters are semicolon-separated and
  wrap across PDF lines; the sparkling ones are bulleted one-per-line
  (`pdftotext` renders the Wingdings bullet as U+F0B7); Sussex's are
  comma-separated with a trailing "X and Y". `grape_candidates` groups
  contiguous roster lines into *runs* and picks the join per run — a
  space where the lines already carry separators (so "Black Hamburg;
  Blau\nPortugueser" is not split into "Blau" + "Portugueser"), a
  separator where they do not. Prose lines are classified out by the
  shape of their split items, so Sussex's record-keeping and
  yield-dispensation paragraphs never reach the matcher.
- **Two source typos are repaired structurally**, not via `GRAPE_ALIAS`,
  because a stray comma and a line break split one variety name into two
  before any alias could apply: Sussex's roster reads "… Pinot Noir,
  Pinot Noir, Précoce, Regent …" for *Pinot Noir Précoce*, and the DEFRA
  rosters drop the semicolon between *Gamay* and *Garanoir* (their own
  alphabetical order — Gamaret, Gamay, Garanoir, Gewurztraminer — proves
  these are two entries).
- **New lexicon entries.** The UK rosters spell several varieties in
  forms no other country uses; VIVC ids verified 2026-09: Cascade
  (#2139, noir), Madeleine Angevine (#7062, blanc), Madeleine Sylvaner
  (#7070, blanc), Roter Veltliner (#12931 VELTLINER ROT, rose — a
  *distinct* cultivar from Frühroter Veltliner, which the fuzzy matcher
  scores at 88), Frühgipfler (#4269, blanc — the UK lists it under its
  synonym *Senator*), Triomphe d'Alsace (#12650, noir), plus aliases for
  "Blau Portugueser" (#9620) and "Elbling White" (#3865). *Gagarin Blue*
  has no VIVC accession — a black Russian/Caucasus cultivar grown
  outdoors in the UK, colour from the RHS plant register.
- Grape roles: no UK specification splits principal from accessory, so
  every match resolves as `principal` (the PT/IT/HR/BG/SK convention).
- v1 models the 6 wine GIs as a **flat corpus**. Sussex and Darnibole
  sit geographically inside the English PDO's territory but are
  first-class PDOs on the register rather than sub-denominations of it —
  Darnibole's own specification makes the point explicitly ("It
  qualified under the 'English' PDO last year, but is considered unique
  and sufficiently different so as to merit its own PDO") — so they are
  siblings, the way the CZ podoblasti are siblings of Čechy / Morava.
- Region facet = the **home nation** the specification demarcates the GI
  to (England / Wales), which is the register's own `DEMARCATION` tier
  ([scripts/_lib/gb/region.py](scripts/_lib/gb/region.py)). Native form,
  not gettext-translated.
- Stage 02d/02e wire terroir-fact extraction + translation for GB. Unlike
  Malta — the other English-source corpus, whose amendment
  communications carry no link section — every UK specification carries a
  real terroir narrative, so GB uses the **standard cahier-primary**
  dual-source model rather than the Wikipedia-primary CH/MT one. A
  missing Wikipedia article is not disqualifying: the specification's own
  link text grounds the record. 02e targets fr/es/nl.

### GB geometry resolution chain (stage 04)

Bétard 2022 carries no `PDO-GB-*` rows, so GB resolves entirely against
**ONS Open Geography** boundaries (Open Government Licence v3.0; "Source:
Office for National Statistics"; "Contains OS data © Crown copyright and
database right"). That is a better fit than Bétard would have been
anyway: every UK wine GI is demarcated to whole administrative units
named in its own specification. BGC ("generalised, clipped to the
coastline") is the generalisation fetched — full-resolution BFC is
several times larger with no visible gain at the zooms this corpus
renders.

Per GB record, in priority order
([scripts/_lib/gb/geometry.py](scripts/_lib/gb/geometry.py); `geom_source`
records the choice):

1. **`ons-country`** — the England / Wales whole-country polygon, for the
   four national GIs (English + Welsh PDO, English + Welsh Regional PGI),
   whose `DEMARCATION` field is literally `ENGLAND` / `WALES`.
2. **`ons-county-union`** — Sussex, whose specification demarcates "the
   administrative boundaries of the counties of East and West Sussex".
   Brighton and Hove is a unitary authority carved out of East Sussex in
   1997 and sits between the two, so the union of the three CTYUAs
   reconstructs the ceremonial Sussex the specification's own map shows.
3. **`pdo-plan-parcel-hull-approx`** — Darnibole (see below).
4. **`stub-no-geometry`** — last resort; not hit in v1, all 6 resolve.

### Darnibole — a boundary reconstructed from the specification's plan

`PDO-GB-N1636` Darnibole is a single-vineyard PDO at Camel Valley,
Nanstallon (Cornwall). Its specification defines the area **narratively**
— "bordered to the West by a marked soil change to alluvial sand (the old
River Camel river bed) … The disused railway (now the Camel Trail)
demarcates the Southern boundary" — with no coordinates, and no public
polygon of it exists anywhere.

What the specification *does* carry is a **"Plan of demarcated area"**
(page 5): an OS-based Rural Payments Agency land-parcel map with the PDO
boundary drawn in red over numbered field parcels, each labelled "Vines
planted" / "Not yet planted". Those parcel numbers are not arbitrary ids
— under the OS/RPA convention a field parcel is identified by the
**four-figure National Grid reference of its centroid within its 1 km
grid square** (two digits of easting then two of northing, each in units
of 10 m), so parcel `7985` sits at 790 m E, 850 m N inside its square.

[scripts/_lib/gb/darnibole.py](scripts/_lib/gb/darnibole.py) reconstructs
an approximate boundary from that: the convex hull of the centroids of
the seven parcels the red line encloses. Anchoring the square (SX 03 67 →
BNG base E 203000 / N 67000) was verified three ways:

1. **Internal consistency.** The decoded north→south and west→east order
   reproduces the plan's layout exactly, including the 1 km grid line
   visible on the plan between parcels 5107/8101 (N 68xxx) and 5095
   (N 67950).
2. **Terrain.** An elevation transect north from the block (EU-DEM 25 m)
   puts the valley floor at 11–14 m over N 67300–67400 and climbs
   steadily to 96 m by N 68100. The seven parcels sit at 47–80 m on a
   ~13 % south-facing slope immediately above the old river bed —
   precisely the specification's "steep south facing slope", bounded
   south by the River Camel's old bed and north by land "above the
   optimum thermal band".
3. **Address.** The ONS centroid of Camel Valley's postcode (PL30 5LG) is
   E 203164 N 67751 — on the same slope, ~330 m west of the block.

The hull spans E 203490–203890 / N 67680–67950 and measures **6.1 ha**
against the specification's declared "whole 5 hectare area" — the right
size in the right place, with no arbitrary buffer parameter. It remains a
reconstruction: it interpolates between parcel centroids rather than
tracing the red line, so its edges fall inside the true boundary by up to
roughly half a field. The record carries `geom_approximate: True`, and
the map panel discloses it ("Aire approchée — reconstituée à partir des
références parcellaires du plan de l'aire délimitée annexé au cahier des
charges ; ce n'est pas une limite officielle.") through the same
`approx-line` mechanism the FR cadastre-lieu-dit DGCs use.

### Curator workflow for the UK

There is no missing-document queue. The two things that can need
attention:

1. **A new registration.** When a pending application is granted (The
   Crouch Valley is the one in flight), re-running stage 00 picks it up
   automatically — except for its file number, which must be added to
   `_FILE_NUMBER_BY_SLUG` in
   [scripts/gb/00_fetch_data.py](scripts/gb/00_fetch_data.py); stage 00
   warns loudly when a registered wine has none, because region and
   geometry both key on it. A new PDO will also need a geometry entry in
   `GB_COUNTRY_TERRITORY` / `GB_COUNTY_TERRITORY`.
2. **A rotated attachment URL.** GOV.UK asset URLs carry an opaque media
   id; stage 00 re-reads them from the register on every run, so a
   rotation is picked up by re-running 00 → 01 → 02.

```
.venv/bin/python scripts/gb/00_fetch_data.py
.venv/bin/python scripts/gb/01_fetch_specs.py
.venv/bin/python scripts/gb/02_extract_specs.py
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang en --source raw/gb/specs-extracted
.venv/bin/python scripts/gb/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/gb/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/gb/03_generate_wiki.py
.venv/bin/python scripts/04_build_maps.py
```

## Spirits and other alcoholic drinks (`scripts/drinks/`, 2026-11-12)

Since 2026-11-12 the corpus holds the **spirit drinks, aromatised wines,
ciders and perries** with a protected name beside the wines (Boris's
decisions of 2026-11-09: spirit-drink GIs in general; the EU register for the
EU countries, the GOV.UK register for the United Kingdom, OFAG's federal
register for Switzerland; one non-wine class under the umbrella "spirits and
other alcoholic drinks" with the EU product category as the facet beneath;
off by default on the map). 268 drink records: 59 French (INAO's referentiel,
the French stages; 13 sub-denominations beside them — the Cognac crus, the
Armagnac districts) and 209 of the drinks pipeline — 189 of the EU register
in 15 countries, 16 of the UK register, 4 Swiss. 273 are on the map (the 72
French ones and 201 of the 209; eight have no area that can be drawn yet).

**Class model** ([scripts/_lib/product_class.py](scripts/_lib/product_class.py)).
A record carries `product_class` (`spirit` / `aromatised-wine` / `cider`;
absent = wine — the field is sparse, no wine record changed) and
`drink_category`, one of fifteen slugs that are the leaves of the `drinks`
style bucket (`style_taxonomy.py`): wine-spirit, brandy, grape-marc,
fruit-spirit, cider-spirit, rum, whisky, grain-spirit, juniper, aniseed,
liqueur, bitter, other-spirit, aromatised-wine, cider. A spirit's category is
the Annex I number of Reg. (EU) 2019/787 the register prints (`_ANNEX_CATEGORY`;
an unlisted number — vodka, the residual "45. Spirit drinks" — is
`other-spirit`); the UK register keeps the 110/2008 numbering, so its
category slug is read by its words (`uk_register.category_of`). A drink's
`styles` is its category alone and it never runs a wine reader (no colour,
no floor, no grape roster). `is_wine` stays the tile / startup flag. The
stored `kind` is `EDV` for every spirit, `DOP` / `IGP` for a cider or an
aromatised wine. Schemes (`gi_terms.py`): `spirit-gi`, `uk-spirit-gi`, `pdo` /
`pgi` / `uk-pgi` for ciders and aromatised wines, `none` for Switzerland. A
drink takes **no wine traditional term** — Sidra da Madeira is no "Vinho
Regional" — except the French AOC sign (Cognac, Calvados, the Pays d'Auge
ciders) and a cited pin: the four Swiss spirits are `AOP`
(`traditional_terms.json` `pins.ch`, `terms["ch:AOP"]`, RS 910.12).

**France** stays with the French stages. `siqo.CORPUS_SIGNS` now holds `IG`
(34 IG-only spirits joined the 26 AOC / IGP ones; one of the 60, Genièvre /
Jenever / Genever, is a drinks-pipeline record — below), `siqo.classify_categorie`
maps INAO's `categorie` to the class, `CATEGORY_PINS` corrects it where the
register's Annex I category differs (Genièvre Flandre-Artois is juniper,
Absinthe de Pontarlier other-spirit). INAO's site resets connections from
outside France, so stage 01 gained a **specification-link tier**
(`RegisterTier.spec_link_for`): the register's detail record carries
`productSpecificationLink`, a BO Agri URL, for 30 of the 34 — the manifest
records `spec_link_source: "eambrosia-register"`. Stage 02 reads the
Partie-I spirit template more widely (lettered `A)` and `1 -` headers, the
all-capitals headings of Armagnac, "détails corroborant le lien", the read-on
past an in-text cahier reference): Armagnac, Calvados, Calvados Pays d'Auge
and Pommeau du Maine regained their lien. `aires._resolve_key` refuses to
hand a spirit the aire of a wine appellation by a contained name (the spirit
guard, `register_product_names`); the three Champagne spirits, whose cahier
delimits "les territoires délimités par l'article V de la loi du 22 juillet
1927 relative à l'AOC « Champagne »", take the Champagne aire by the cited
[scripts/_lib/aire_references.json](scripts/_lib/aire_references.json). A
shared GI is the record of the first country of its file number (the
Maasvallei rule): Génépi des Alpes (PGI-FR+IT-01909) is French, Genièvre /
Jenever / Genever (PGI-BE+NL+FR+DE-01962) is a drinks record of Belgium with
France among its aliases although INAO lists it (`siqo.DRINKS_PIPELINE_IDS`).
The register's link turned out to point at the cahiers of 2014–2015: on
2026-11-13 the 28 French drinks BO Agri lists a newer cahier for were
re-sourced from it, the three stubs among them (Absinthe de Pontarlier,
Cassis de Dijon, Génépi des Alpes — no French drink is a stub since), and
their aires checked against the cahier — "The cahier wins" under "INAO
aires-communes supplements". **Two French records cross the border**
([scripts/_lib/fr/cross_border.py](scripts/_lib/fr/cross_border.py),
`cross_border_areas.json`; Boris: the Maasvallei pattern): Euskal Sagardoa —
the Basque cider, whose cahier delimits named districts of Bizkaia, Gipuzkoa
and Álava beside the 148 French communes — and Génépi des Alpes (Piemonte
and Valle d'Aosta beside six départements). Each stays one French record
(INAO's cahier is the document in the build), carries `country_aliases`
(written by stage 02, so it is listed under Spain / Italy too), and stage 04
unions the foreign units (the drinks unit grammar, `nuts:ES213` …) into its
polygon and names them on the commune-union line with the entry's
disclosure — the Spanish part is drawn as the three provinces whole where
the cahier names districts inside them, in Álava four of them (CURATOR_TODO).
IGN's communes and GISCO's NUTS units draw the state border at two
resolutions, which left 223 slivers of empty ground along the Alpine crest
in Génépi des Alpes's first union: `_fill_seam_holes` closes the holes of
the union that touch the foreign part and are under `_SEAM_HOLE_MAX_DEG2`
(2e-4 deg², about 2 km²) — a lake or an enclave is larger and stays open.
`tests/test_fr_cross_border.py` checks each quote against the record and
each unit against the NUTS layers.

**The drinks pipeline** — one set of stages for every other country, records
under `raw/drinks/extracted/` with `pipeline: "drinks"`, their own `country`
and `source_lang`:

| Script | Reads | Writes |
|---|---|---|
| drinks/00_fetch_index.py | the EU register listing (`eambrosia_register.load_gi_rows`), GOV.UK search API, scripts/_lib/drinks/{cider_gis,name_pins,ch_register,areas}.json, raw/inao/register/resolved.json, ONS Open Geography | raw/drinks/eambrosia/{index,manifest}.json, raw/drinks/ons/{countries,counties}.geojson |
| drinks/01_fetch_technical_files.py | the index, the register's detail records, GOV.UK content API, blw.admin.ch, raw/drinks/manual_overrides.json | raw/drinks/register-detail/*.json, raw/drinks/technical-files/<slug>.<lang>.pdf + manifest.json, raw/drinks/national-specs/* |
| drinks/01b_fetch_oj_pages.py | the manifest's OJ publications (records with no technical file) | raw/drinks/oj-pages/*.html + manifest.json (headless Chromium, the EUR-Lex WAF) |
| drinks/02_extract_technical_files.py | the three document directories | raw/drinks/extracted/*.json + _index.json |
| drinks/02d_extract_terroir_facts.py | raw/drinks/extracted/ (+ raw/wikipedia/aocs/<lang>/ when cached) | raw/terroir-facts/*.json (`country: "drinks"`) |
| drinks/02e_translate_terroir_facts.py | raw/terroir-facts/*.json (`country: "drinks"`) | raw/translations/terroir-facts/<lang>/*.json |
| drinks/03_generate_wiki.py | raw/drinks/extracted/ | wiki/<slug>.md + the `pipeline: "drinks"` entries of wiki/_index.json |
| audit_drinks_coverage.py | the register listing, the index, the extracted records, the French non-wine records, the build | (stdout — register vs corpus per country, stubs, geometry by source, the undrawn queue; `--strict`, `--json`) |

- **Which rows** ([scripts/_lib/drinks/index.py](scripts/_lib/drinks/index.py)):
  Registered rows that are a spirit drink, an aromatised wine (register
  classes 2.21 / 2.22) or a cider of the curated
  [cider_gis.json](scripts/_lib/drinks/cider_gis.json) (a cider is a
  Food-class GI in class 1.8, among spices and salts). Left out: the rows the
  French stages hold, and the UK's — read from GOV.UK instead
  ([uk_register.py](scripts/_lib/drinks/uk_register.py): the `spirit-drinks`
  register and the cider / perry names of the food register; the three
  all-island Irish names carry `country_aliases: ["ie"]`, Ireland being an
  alias country with a label and a flag and no record of its own). The Swiss
  four are the curated transcription of OFAG's register page
  ([ch_register.json](scripts/_lib/drinks/ch_register.json)). `name` is the
  first registered alias, `name_latin` the first Latin one of a Greek or
  Cyrillic name, the other aliases search keys; a slug that another corpus
  uses stops stage 00.
- **Which document.** A spirit registered before 2019 has a *technical file*
  (`singleDocTechFile` — the application language and, often, the
  Commission's English copy, which the English card shows as an official
  translation: `official_en`, "European Commission translation"); an
  aromatised wine has its technical file in `summarySheets` (English only);
  a spirit registered since, and a cider, has only the Official Journal
  single document (01b); a UK name its GOV.UK product specification; a Swiss
  AOP its cahier des charges plus the "Résumé de la demande
  d'enregistrement", whose sections 7 and 8 are the only history and link
  text. All 209 extract (no stub).
- **The readers**
  ([technical_file.py](scripts/_lib/drinks/technical_file.py),
  [single_document.py](scripts/_lib/drinks/single_document.py)): the
  Commission's e-form (numbered `1.`–`9.` under `I.`, two-column label /
  value tables whose labels are learnt per language from four files or more —
  `learn_labels` — and the NUTS rows of 4b), its decimal variant, and a member
  state's own document, read by heading words in fifteen languages
  (`ROLE_HEADINGS`: description, area, method, link, labelling, stop). What
  the form reader guards against, each found on a real file: a table of
  contents (a run of headings ending on a page number or a range, entries
  wrapped over two lines — `_contents_zone`; never a table of analytical
  values), a cross-reference in brackets or quotes, small capitals printed
  letter by letter (Irish Poteen), a file laid out as one two-column table
  (the Glühwein files — `_decolumn`, only where value lines outnumber rows, so
  a page of two prose columns is not taken for one), a page printed in two
  columns (Grappa's decree in the Gazzetta Ufficiale: read again in reading
  order when the layout parse yields under three text sections). A single
  document is its numbered top-level headings, each given its role by its
  title (the heading words may stand at its end). A parser change is checked
  by re-extracting and diffing every record's role lengths.
- **Geometry** ([geometry.py](scripts/_lib/drinks/geometry.py)), in this
  order: **`drinks-area-pin`** — a curator pin of
  [areas.json](scripts/_lib/drinks/areas.json) (151): the units the area text
  names as `country:`, `nuts:`, `lau:CC:Name[@NUTS]`, `lauid:CC:PREFIX=Label`
  (every LAU row under a GISCO id prefix: a Greek δήμος or δημοτική ενότητα,
  a Portuguese município), `uk:country:` / `uk:county:` (ONS), `minus:<unit>`
  or `ref:<slug>` (the polygon of the wine record whose delimitation the text
  cites — Aguardente de Vinho Douro, Vinars Murfatlar), each with the
  verbatim sentence it reads (`tests/test_drinks_areas.py` checks every quote
  against the record and every unit against the layers) and, where the
  drawing departs from the letter, a `disclose` sentence in the four UI
  languages that the card prints (a part of a municipality drawn as the
  municipality, village lands drawn as their obshtini, an island as its
  NUTS unit); **`gisco-nuts-union`** — the leaves of the technical file's
  NUTS rows, a retired code found by its name; else the record is **not
  drawn** and must be listed with its reason in
  [area_queue.json](scripts/_lib/drinks/area_queue.json) (a radius, a
  boundary in prose, a tier no layer carries). A pin that no longer resolves
  is never half-drawn. The card names the units drawn (up to twelve).
- **Region** ([region.py](scripts/_lib/drinks/region.py)): the pin's, else
  the referenced wine record's, else the administrative region its units
  lie in where the country's wine facet is administrative
  ([nuts_regions.json](scripts/_lib/drinks/nuts_regions.json): ES, IT, AT,
  DE, BE, NL; the UK's home nation), else the country's own name.
- **Stage 04** treats `pipeline == "drinks"` before any country branch
  (geometry, region, sources — `technical_file_url`, `technical_file_en_url`,
  `national_spec_url`, `national_link_url`, `gov_uk_register_url`); the
  snapshot carries `_DRINKS_GEOM_BY_SLUG`; `wiki_index_kept` keeps the drinks
  entries apart from each country's.
- **Terroir facts.** One 02d / 02e pair for fourteen languages: English
  instructions that name the language the bullets are written in (the
  document's), the grounding text is the area, description, method and link
  together, the cache's `country` is `"drinks"` — the stage that owns the
  source text, which the gate, the audits and the provenance pass load
  through `terroir_sources` — with the record's country in `record_country`.
  No Wikipedia hint yet (no article is cached for a drink). First corpus
  run, `drinks-2026-11-12` (the 209 drinks records and the 34 French spirits
  new to the corpus): 2,930 facts extracted, 49 dropped and 333 narrowed by
  the gate, translated and back-checked, $36.60 at the batch rate;
  `drinks-2026-11-13` re-ran Irish Whiskey and Irish Poteen after a parser
  fix. 2,883 facts on 243 records. Two things the run taught: a Greek or
  Cyrillic drink name came back in its own script in the fr / es / nl
  bullets (25, Latinised by `normalize_terroir_facts.py`; the 02e prompt
  now asks for Latin script only, and the normaliser drops a gloss that
  repeats its word, "Ouzo (Ouzo)"), and the exonym detector took "am Rhein"
  / "an der Donau" inside a town's name for the river (`_IN_PROPER_NAME`).
  The **French** drinks go through the French 02d, and that one sliced a
  link text by the numerals of the AOC wine template ("1° - … a) … b) … 2° -
  … 3° - …"). A spirit or cider cahier is headed by titles ("5.1 Les
  facteurs physiques du lien", "5.2 Les facteurs humains", "5.3 Les
  spécificités du produit", "5.4 Lien causal"; "a) Éléments historiques
  concernant les facteurs du lien au terroir"), as is every IGP wine cahier
  ("7.1 – Spécificité de la zone géographique", "7.2 – Spécificité du
  produit", "7.3 – Lien causal …"): the whole text went through the one
  natural-factors call, and 50 of the 58 French drinks carried natural
  factors only, history and product filed under them.
  [scripts/_lib/fr/lien_titles.py](scripts/_lib/fr/lien_titles.py)
  (`slice_by_titles`, tried when `slice_section_x` finds fewer than two
  sub-sections) reads the headings by their words. Two runs on 2026-11-13:
  `drinks-cahiers-2026-11-13` (the 28 records whose cahier changed; 169
  facts, 12 narrowed, none dropped, $3.14) and `drinks-cahiers-2026-11-13b`
  (57 French drinks, sub-section by sub-section: 691 facts — 330 natural,
  180 human, 137 product, 44 interactions — 44 narrowed, none dropped,
  $6.53; no record is left with natural factors only). The **75 IGP wines**
  in the same case keep their facts until Boris decides (CURATOR_TODO,
  ≈ $11).

**Audits and validators.** `audit_drinks_coverage.py --strict` is a quick
release gate (`validate_release.py`: `drinks-coverage`). The overlap audit
classes any pair with a drink as **DRINK** (another product, its own
delimitation — never SUSPICIOUS: Korn is Germany, Austria and the
German-speaking Community of Belgium; a marc shares the communes of its wine
appellation); the outlier audit lists a drink drawn from whole named units as
**ADMINISTRATIVE** (a detached part is an island of the unit itself), while a
French spirit drawn from INAO's aire is whitelisted like any other record
(the overseas rum's four territories) — after its cahier has been read:
three such lobes turned out to be wrong rows on 2026-11-13 (Marc du Jura,
Marc des Côtes du Rhône, Marc d'Auvergne), and Génépi des Alpes' Haute-Savoie
lobe closed when Savoie, missing from its rows, was pinned.
The polygon-versus-text audit reads a drink's area text with the country
parsers written for wine texts, which read fewer names than the curator did
(a county taken for a commune, "Krems" for Krems an der Donau): a drink
drawn from a pin or from NUTS rows is **PINNED** when the only difference is
whole units beyond the parser's reading, and stays SUSPECT when a unit the
parser read is not drawn (`curated_area_bucket`). Run scoped on the 273
drink polygons (2026-11-13: 70 OK, 8 PINNED, 175 without units, 12 above the
commune tier), it found the French spirits whose INAO rows lack communes
their cahier lists — Cassis de Saintonge's 36 rows for some four hundred
communes — see "INAO aires-communes supplements". A full-corpus run is
hours long (the Italian zone records); scope it with `--only` / `--country`.
`diff_records.py` snapshots `product_class`, `drink_category` and
`country_aliases`; the card packet finds a drinks record's document
(`card_packet.DRINKS_DIR`); `rerun_terroir_facts.py` routes an uncached
drinks slug to the drinks stage. An untranslated drink summary names its
own source language (`src_lang_marker_aria`, the endonym in brackets — the
old marker assumed French for every country but Spain and Portugal).

**Acceptance, 2026-11-13.** The adversarial facts audit on a seeded sample
(40 records, 492 English bullets): 2 misleading, 0.41 % (0.11–1.47 %), both
translation slips — PT "vinhas estremes" is a pure-stand vineyard, not a
single-variety one (now in the EN glossary), BG "допринася" is "contributes
to" — fixed by a scoped back-check and filed as feedback. The card validator
on 20 drink cards (`audit_cards_llm.py --all-products --slugs-file …`; the
judge prompt says how a drink card differs: one category pill, no colour, no
roster, no wine term, the first registered name as title): 19 trust, 1
caution — Euskal Sagardoa, a French record of long standing whose cahier
delimits a Spanish-French area while the card draws the French communes; it
carries a cited note since (`appellation_notes.json`), the rest of that
question is in CURATOR_TODO. `mcp/test/parity_webmcp.py` asks four drink
questions. The polygon-versus-text audit passes its cahier communes to the
aire lookup as stage 04 does, so a name with two INAO aires (Calvados: the
spirit's and the wine IGP's) is no longer read as both.

**On the map.** The legend's third pill is the umbrella ("Spirits & other
drinks", tooltip key `drinks`); the three pills partition the records — the
PGI pill is a wine pill, so a cider or aromatised-wine PGI sits behind the
drinks pill alone (`isIgpRec`). Ticking a drink category in the Style tree
turns the pill on (`Kind Toggled {via: 'style-pick'}`); the `drinks` rows are
counted while it is off. `?spirits=1` in a shared URL as before.

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
same). A stage that asks a second question on reading an answer — the 20
non-FR 02d scripts' second reading of an empty sub-section
(`terroir_prompts.should_retry`) — passes `follow_ups=True` (2026-10-24):
the answers are replayed first through a probe provider of kind
`collecting` (the stage writes to its scratch dir, as in pass 1), the
`chat(..., follow_up=True)` requests the stage issues on reading them are
submitted as one more batch (sidecar `<stage>.r1.json`), and the merged
answers feed the replay that writes; the main batch's answers wait in
`<stage>.results.json` meanwhile, so an interruption during the follow-up
batch resumes without resubmitting them (`tests/test_batch_follow_ups.py`).
A `follow_up=True` request with no answer returns `""` instead of raising,
so the stage's first answer stands; without the flag nothing changes.

Default models are **per stage** (`providers.STAGE_DEFAULTS`; the split
decided 2026-09-14 after the paired experiments in
[docs/review-terroir-facts-2026-09-12.md](docs/review-terroir-facts-2026-09-12.md),
always the newest model of each family since 2026-10-09 unless a run
names another): 02d extraction `claude-sonnet-5-5` with thinking off; the
gate (`02d_verify`) and the LLM audit `claude-opus-5-5` with adaptive
thinking at effort `high` (Opus 5.5 defaults to `medium`; Opus 5, on
which the gate was calibrated, defaulted to `high` — `_EFFORT_PINS`);
the back-check `claude-opus-5-5` too (2026-10-09: a corpus-wide Sonnet 5.5
back-check changed 20 % of the NL / FR / ES bullets and a blind judge
found ~17 % of its edits worse; on those bullets Opus left 22 of 30 alone
and fixed the French agreement errors Sonnet missed, at 3.3× the cost —
the Sonnet run was rolled back, `MAX_TOKENS` raised to 16,000 because
Opus always thinks); 02e and 02c `claude-sonnet-5-5`. Bumping a default
re-runs nothing: the corpus keeps the model that wrote each cache (its
`translator` / `model` field) — 1,515 of the 1,617 NL caches are
Sonnet 4.6's. Mistral `mistral-medium-latest`. Before any job a default
is checked against the account's model list
([scripts/_lib/model_check.py](scripts/_lib/model_check.py), Models API
`GET /v1/models`, cached in `raw/cache/anthropic-models.json` for a day):
when its family (sonnet / opus / haiku / fable) has a newer model the run
stops before submitting anything and says what to bump — never a silent
switch, because a new model can change the request surface (Sonnet 5.5's
400 on `disabled` thinking). An explicit `--model` is not checked (a
deliberate older model, or resuming an in-flight batch); an unreachable
API warns and runs on a stale cache or unchecked; `OWM_SKIP_MODEL_CHECK=1`
turns it off (the test suite sets it). Used by `--batch` and by synchronous `--provider`
runs alike (`batch.default_model(provider, stage)` /
`default_thinking()`, `providers.make_provider(..., stage=)`); override
per run with `--model` / `--thinking`, or `OWM_BATCH_THINKING` for an
experiment. `tests/test_stage_defaults.py` pins the configuration. API
keys are read from the environment or a repo-root `.env`. The Claude 5
family runs adaptive thinking when `thinking` is omitted and every
stage's `max_tokens` is sized for the JSON reply alone, so
`providers.effective_thinking` turns thinking off for a Claude 5 model on
a stage that sets no mode (2026-09-15: Sonnet 5 on 02e had 64 % of its
replies truncated by thinking and rejected) — spelled per model: `disabled`
(Sonnet 5, Opus 5), `between_tools` (Sonnet 5.5, which answers `disabled`
with a 400), and no thinking field with effort `low` on the models that
always think (Opus 5.5, Fable). No server-side refusal fallback is sent:
the Batch API rejects the parameter.

**Prompt caching** ([scripts/_lib/prompt_cache.py](scripts/_lib/prompt_cache.py),
Anthropic only; Mistral / Ollama get the flat text). Text sent more than
once is placed *first* in the system prompt as its own block with
`cache_control`, so every request after the first reads it at 0.1× the
input price: in the 20 non-FR 02d scripts the lien is the leading cached
block (`cached_system(_document_block(lien), instructions)` — the four
sub-section calls of a record each resent the whole lien; the user turn
now carries only the sub-section request; FR slices section X per call
and shares nothing, so it is left alone), and the gate, the back-check,
the LLM audit and the 21 × 02e scripts cache their static system prompt
(`mark_cached`, shared by every record of a batch — 02e's is ≈ 3 K
tokens per locale). A block below the model's minimum (Sonnet 5 / 4.6
1,024 tokens, Opus 5 512) silently does not cache and costs nothing; the
Batch API processes concurrently, so hits are best-effort (Anthropic
quotes 30–98 %) — the four calls of a record are submitted adjacently and
the ledger's `cache_creation_input_tokens` / `cache_read_input_tokens`
show the achieved rate per batch. `OWM_CACHE_TTL` = `5m` (default; write
1.25×, the four-call pattern breaks even at a 29 % hit rate), `1h` (write
2×, break-even 70 %) or `off`. Inside one large batch a record's four
calls are processed concurrently, so most of them write instead of read
(13–47 % hits on the cfg-2026-09-14 run — break-even, not a saving);
the 20 scripts therefore tag each call with its sub-section
(`cache_phase`) and `batch.run_two_pass` submits **one batch per phase,
in order** (`run_phased`, per-phase sidecars, `OWM_BATCH_PHASED=0`
disables): the first phase writes the lien, the next three read it, and
the lien block carries the 1-hour TTL in that mode (a read refreshes the
timer, so each phase only has to finish within an hour). The trade-off
is wall-clock — four sequential batches per country instead of one. The next
steps — migrating the corpus to this configuration and the remaining
review recommendations — are in
[docs/handoff-terroir-facts-2026-09-14.md](docs/handoff-terroir-facts-2026-09-14.md). Anthropic
batches use the Messages Batches SDK; Mistral batches use a file-upload /
poll / download REST flow (no `mistralai` SDK dependency).

## Appellation names: traditional term + legal scheme

Every record carries two naming axes, derived at stage 04 and never
hand-edited ([scripts/_lib/gi_terms.py](scripts/_lib/gi_terms.py)):

- **`eu_scheme`** — the legally precise scheme: `pdo` / `pgi` (EU wine,
  Reg. 1308/2013), `spirit-gi` (the 28 FR eaux-de-vie + Marc d'Alsace:
  spirit-drink GIs under Reg. 2019/787, SIQO `signe_ue = IG`), `uk-pdo` /
  `uk-pgi` (the six UK wines, GOV.UK register) and `none` (the 75 Swiss
  cantonal AOCs, outside the EU scheme). FR comes from `signe_ue` with the
  derived `mvt_kind` as fallback; everyone else from the eAmbrosia kind.
- **`national_term`** — the EU-registered *traditional term* (Reg. 1308/2013
  Art. 112(a), Reg. 607/2009 Annex XII) the regulator attaches to the GI as
  a whole: AOC, DOCG / DOC / IGT, DOCa / DOQ / DO / Vino de Pago / Vino de
  Calidad / Vino de la Tierra, DOC / Vinho Regional, DOC / IG, DAC /
  Landwein, DOK / IĠT. The regulator's own string, never gettext-translated
  (the region-name rule). Admission needs all three: registered in Annex
  XII, GI-wide (lot-level grades — Qualitätswein, Prädikatswein, kakovostno
  — are excluded), attached by a public regulator document or a cited pin.
  Local abbreviations of PDO/PGI (OEM, ZOP, ΠΟΠ, BOB …) are the scheme, not
  a term; the table loader refuses them.
- **`class_key`** (`;pdo;it:docg;`) is the `;`-padded MVT property the
  "Appellation type" facet filters on; **`class_label`** is the per-locale
  rendered string, composed once in Python (`classification_label`) so the
  JS panel, `docTitleFor`, the SSR card, entity `<title>` / meta description,
  browse list and children nav all read the same value.

Rendering is **`TERM (SCHEME)`** with the scheme word in the UI locale —
`DOQ (PDO)` / `DOQ (AOP)` / `DOQ (DOP)` / `DOQ (BOB)`, `AOC (PDO)`, `IGT
(PGI)`, `AOC (spirit-drink GI)`; term only when there is no scheme (Swiss
`AOC`), scheme only when the country has no term (`PDO` for Mosel or
Sussex, `PGI` for a French IGP — never `IGP (IGP)`). Both tokens are
hover/focus targets of the pill tooltip (definition + regulator source from
the term table); the SSR card carries the same text as an `<abbr title>`.
The stored **`kind`** token (AOC/DOP/IGP/EDV) is untouched — it stays the
paint and filter key (map_template.py paint expression + the six `'IGP'`
gates in app.js).

Sources, all sha-pinned and joined on the EU file number:

| country | source | result |
|---|---|---|
| IT | MASAF *Elenco alfabetico dei vini DOP* (+ IGP elenco), scraped from IDPagina/4625 by `it/00_fetch_data.py` into `raw/it/masaf-elenchi/`, parsed by [scripts/_lib/it/national_term.py](scripts/_lib/it/national_term.py); IGT constant for IT PGIs | 79 DOCG / 333 DOC / 112 IGT, 524/524; residue pinned in [scripts/_lib/it/national_term_overrides.json](scripts/_lib/it/national_term_overrides.json) (Cirò Classico → DOCG, Reg. 2025/1518; Valtènesi → DOC, Reg. 2026/572; Casauria → DOCG, Reg. 2025/2261). The known static elenco URL serves a 2014 build — the scraper takes the dated `ServeAttachment` link. |
| ES | MAPA *Listado de DOP e IGP de vinos* (Término tradicional column), fetched by `es/00_fetch_data.py` into `raw/es/mapa/`, parsed by [scripts/_lib/es/national_term.py](scripts/_lib/es/national_term.py) | DO 69 / Vino de la Tierra 43 / Vino de Pago 28 / Vino de Calidad 7 / DOQ 1 / DOCa 1, 149/149; [scripts/_lib/es/national_term_overrides.json](scripts/_lib/es/national_term_overrides.json) pins Priorat → `DOQ` (`castilian_form: DOCa`; Llei 2/2020 art. 4(e) — the regional-language legal form wins when the autonomous community's wine law defines it), Tharsys (file-number bridge, VP per its pliego), Urbezo (VP per the MAPA 2024-10-25 release; the listado still prints DO). No PGI ever receives a PDO-only term (asserted). |
| FR / CH / PT / RO / AT / DE / MT / rest | the checked-in ruling table [scripts/_lib/traditional_terms.json](scripts/_lib/traditional_terms.json): per-(country, kind) constants with a cited ruling per country, the 18 Austrian DAC pins by file number (BML DAC-Verordnungen + RIS, `since_vintage`), the `marc-d-alsace-gewurztraminer` slug pin, and the per-scheme / per-term tooltip definitions in en/fr/es/nl with sources | FR AOC (incl. EDV), CH AOC, PT DOC / Vinho Regional, RO DOC / IG, AT DAC / Landwein, DE Landwein (PDO none), MT DOK / IĠT; GB / LU / BE / NL / SI / HR / HU / BG / GR / CZ / SK / CY empty with a recorded reason. |

Deferred to a curator pin pass (empty renders scheme-only, never wrong):
GR ΟΠΑΠ / ΟΠΕ, CZ VOC (Znojmo), CH Grand Cru / premier cru sub-tiers, NL
Landwijn, SI vino PTP, HU Tájbor, BG Регионално вино, CY ΟΕΟΠ / Τοπικός
Οίνος — see [CURATOR_TODO.md](CURATOR_TODO.md). Wikipedia extracts for the
term tooltips are a follow-up (the 02b style-lexicon pattern).

Sub-denominations resolve through their own `file_number` / `signe` (ES
subzonas and IT sottozone carry the parent's number) with a parent-slug
fallback in the parents-first record loop; `scripts/audit_gi_terms.py`
asserts every child equals its parent, that every term's registered scheme
matches the record's, that no `class_label` is empty, and reports the
per-country distribution against the rosters. Run it after every stage-04
build (`--strict` in CI).

The facet is its own two-level tree ("Appellation type" — withheld from the
sidebar since 2026-10-18, its `<details>` the only thing removed; the tree
code is dormant, to return with the AVAs):
scheme rows over flag + term rows, built with `buildTreeFacet` over
`class_key`; counts are parents-only and wines-only, so DOCG = the roster
count, not roster + sottozone.

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
translating it would lose the public-source provenance. Region labels are
an exception: their translations live in the gettext catalog because the
FR forms are well-known proper nouns with public, stable translations. The
FR `region` value is a **wine region**, not the INAO comité
([scripts/_lib/fr_wine_region.py](scripts/_lib/fr_wine_region.py)): the
comité is kept on the record (`comite_regional`) and passes through where
it names one region (VAL DE LOIRE, CHAMPAGNE, COGNAC…; TOULOUSE-PYRENEES
is SUD-OUEST); BOURGOGNE is split by slug (Jura / Savoie / Bugey /
Beaujolais); the comités that span two regions or three (SUD-OUEST held the
36 Gironde AOCs — Pauillac was titled "South-West, France" until
2026-09-26 — LANGUEDOC-ROUSSILLON, PROVENCE-CORSE, ALSACE ET EST, the VDN
and cider product comités) and the 81 comité-less IGPs are placed by the
dominant département of their INAO aire (`aires.load_aires_departements`,
the same public CSV the polygon is drawn from) through a département →
region table, with a pinned residue (`_SLUG_BUCKET`: the whole-region
IGPs, names the CSV spells otherwise). Buckets: BORDEAUX, SUD-OUEST,
LANGUEDOC, ROUSSILLON, PROVENCE, CORSE, ALSACE, LORRAINE, NORMANDIE,
BRETAGNE, MAINE, ILE-DE-FRANCE plus the unchanged ones; a DGC takes its
parent's. `tests/test_fr_wine_region.py` pins the rules.

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
.venv/bin/python -m babel.messages.frontend extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/
.venv/bin/python -m babel.messages.frontend update -i locale/messages.pot -d locale --no-fuzzy-matching
.venv/bin/python -m babel.messages.frontend init -i locale/messages.pot -d locale -l <lang>   # to add a new locale
```

After editing a `.po`, just rerun `uv run scripts/04_build_maps.py`. The French-named
style nodes carry the EU English term in EN and its Dutch equivalent in NL
since 2026-11-07 — "liqueur wine" / "likeurwijn" (Reg. 1308/2013 Annex VII
Part II point 3), "straw wine" / "strowijn"; the card judge had read "Vin De
Liqueur" on Moravské and Východoslovenská as untranslated. *Vin doux naturel*
is a protected traditional term and keeps its French name in every locale.

## Search: the regulator's string on screen, derived keys in the index

The name shown anywhere — sidebar row, suggestion row, panel header, entity
`<h1>`, JSON-LD `name` — is the regulator's own string, with the EU /
official Latin transcription (`name_latin`) in brackets for a Greek or
Cyrillic name. The surfaces that address a search engine in the UI language
are the one exception (2026-09-26, `seo_display_name`): the `<title>`, the
meta description, `og:title`, the browse-hub anchor and the llms.txt link
lead with the Latin form and keep the native string in brackets — "Naoussa
(Νάουσα) — PDO · Macedonia, Greece" — because Google says a title should be
in the page's writing system and a Latin query never matched the
native-only title (212 pages per locale). JSON-LD carries the Latin form as
`alternateName`. The same surfaces render a Greek / Cypriot / Bulgarian
region through the Wikidata-cited exonyms of
[scripts/_lib/region_exonyms.json](scripts/_lib/region_exonyms.json)
(`title_region_labels`, mirrored to app.js as `TITLE_REGION_LABELS`); the
card, facet tree and sidebar keep the native label. What the search box *matches* is wider, and none of it is
displayed except the one echo noted under region forms (decided 2026-09-25
after the Άγιο Όρος / "agio oros" case):

- **Normalisation** (`searchNormalize` in app.js): NFD, combining marks
  dropped, lower-cased, and every run of punctuation or whitespace folded
  to one space on both the query and the index, so "aloxe corton" finds
  Aloxe-Corton and "d alba" finds d'Alba (727 of 2,954 records were
  unfindable by their own full name before the fold).
- **Derived forms** ([scripts/_lib/romanise.py](scripts/_lib/romanise.py)):
  stage 04 emits a sparse startup field `search_forms` — for GR / CY the
  ELOT 743 romanisation of the name plus its unidecode form, for BG the
  unidecode form (and the official form, when the bracket differs) — every
  one a deterministic transformation of the regulator's string, so no
  source or attribution is involved. The EU register's transcriptions
  follow no system (Κάρυστος is "Karystos" in one record and "Karistou" in
  another; the OJ's own English text writes "Agio Oros" where the register
  says "Ayio Oros"), which is why the national standard is derived rather
  than curated. Each form is matched on its own (prefix 100 / substring
  80); a query never spans two forms. `fold_confusables` repairs the one
  homoglyph in the register (Αργολίδα's "Αrgolida" carries a Greek capital
  Alpha) before the bracket is emitted.
- **Region forms** ([scripts/_lib/region_search_terms.py](scripts/_lib/region_search_terms.py)):
  the region suggestion group and the tree filter also match the curated
  [scripts/_lib/region_search_terms.json](scripts/_lib/region_search_terms.json)
  (Wikidata labels and filtered aliases in en / fr / es / nl, CC0, one item
  URL per entry, descriptor words stripped — "Vignoble de Franconie" ships
  as "Franconie"; regenerated by `scripts/refresh_region_search_terms.py`,
  whose `--check` re-fetches and fails on drift), the romanisations of a
  Greek / Cyrillic label, and — for the French bassins, whose label *is*
  localised through gettext — every locale's label plus the INAO key. The
  row keeps the native label. The one echo: when a Wikidata or gettext
  *label* matched, it goes in the row's sub-line ("Μακεδονία · Macedonia",
  "Burgundy · Bourgogne"); a matched alias or derived romanisation is never
  shown. The tree keeps a whole region group only on a word-prefix hit, so
  "ria" does not open Bayern through "Bavaria".
- **Bulgarian bracket**: `name_latin` for BG is the official Streamlined
  System (Transliteration Act 2009 — Търговище → Targovishte, Ямбол →
  Yambol), no longer unidecode (T'rgovishche); slugs are unaffected (BG
  stage 00 has its own slugify) and the old spelling stays a search form.
- **Not built** (assessed 2026-09-25, kept as options): a curated,
  per-record exonym table ("Athos", "Mount Athos") — the only path to a
  name no regulator or EU text uses for the GI, and the one that needs a
  cited source per entry and an "area" marker on screen; a Wikidata /
  Wikipedia harvest (P9854 has no GR / BG / CY items, sitelink QIDs cover
  8 of 147 GR); tracking zero-result query text in Plausible (a privacy
  reversal — 329 of 1,327 omnisearch queries returned nothing as of
  2026-09-24, text unknown); a fuzzy "did you mean" fallback.

## Data bundle: startup blob + lazy panel detail

The map's per-appellation data ships in two tiers so the front page is light
(the corpus is ~2,900 records). The render-blocking startup bundle
`wiki/data/aocs.<locale>.<hash>.js` (`window.__OWM_DATA`) carries only
`STARTUP_AOCS_FIELDS` ([scripts/_lib/map_template.py](scripts/_lib/map_template.py))
— the fields every startup path reads: the sidebar appellation list, search,
facet filtering (`matchesClient`/`matchesExceptFacets`), fly-to
(`fitToFiltered`/`localityRank`), the active-filter chips
(`renderActiveFilters`→`grapeName`→`grapes_info`), and the map-click stack
dedup (`geom_source`). It is **the contract between the Python emitter and the
JS app**: a field read by any of those paths MUST be in the set, or the
sidebar/map silently breaks (there is no golden-diff guard here — Phase 3
deliberately changes this bundle).

Everything else on a record (summary, terroir facts, sources, grape
display-names, dűlők, menzioni, notes, attribution/geometry-provenance fields)
is the **panel payload**, emitted per slug per locale as
`wiki/data/d/<locale>/<slug>.json` (the complement of `STARTUP_AOCS_FIELDS`;
write-if-changed + stale-prune in `emit_html`). The JS fetches it on first
panel open (`hydratePanel` → `Object.assign` into `AOCS[slug]`, deduped while
in flight, graceful degrade on failure), showing a skeleton placeholder
meanwhile; repeat opens are instant. This cut the startup bundle from ~13.2 MB
raw / 1.9 MB gz to ~3.2 MB / ~0.4 MB. `grapes_info` stays inline — it is a
startup dependency via the active-filter chips. The full record is still used
for the server-rendered entity cards (SSR is unchanged), so crawlers see the
same content; only the JS map lazy-loads. The per-slug JSON is not
content-hashed (stable path, fetched at runtime, not referenced from cacheable
HTML) and never enters the sitemap.

### Map app JS source

The map application JS lives in
[scripts/_lib/assets/app.js](scripts/_lib/assets/app.js) — a real, lint-able
`.js` file, not an escaped Python string. `_render_app_js` in
[scripts/_lib/map_template.py](scripts/_lib/map_template.py) injects the
per-locale build values by replacing `__OWM_<slot>__` tokens (one per former
`{slot}` format field) and emits `wiki/assets/app.<locale>.<hash>.js` exactly
as before — byte-for-byte equivalent to the old `_APP_JS.format(**kwargs)`
(verified by the golden comparator). `eslint.config.js` (flat config, advisory)
lints it: `npx --yes eslint@9 scripts/_lib/assets/app.js`; the OWM token
identifiers are declared as globals there, and a non-blocking `eslint` CI job
runs it. Edit app.js directly; do not move the JS back into the template. The
CSS still ships inline in `_TEMPLATE` and is lifted to the shared
`style.<hash>.css` by `_split_template`.

### Basemap (CARTO raster, keyed) and its successor

The basemap under the polygons is CARTO raster — Voyager (light) + dark_all
(dark), both added up front and switched by layer *visibility*, never by
`setStyle` (which would reorder layers above the appellation polygons and drop
their selection feature-state).

In **2026-08 CARTO retired key-less access**: an unkeyed tile still returns
HTTP 200, but with "API KEY REQUIRED" stamped into the PNG — a failure that is
invisible to any status-code check and only shows up by looking at the image.
The tile URLs now carry `?key=`, injected at build time from
**`CARTO_BASEMAP_KEY`** in the repo-root `.env` (the same file
[scripts/deploy.sh](scripts/deploy.sh) sources) via
[scripts/_lib/env.py](scripts/_lib/env.py) → the `__OWM_carto_key_json__`
token. The key is public once the map ships (the browser makes the tile
request); `.env` keeps it rotatable and out of git history. Unset ⇒ no `?key=`
and a watermarked basemap, so stage 04 warns loudly on stderr. A second
environment gets its own key through `CARTO_BASEMAP_KEYS=<host>=<key>` (same
shape as `PLAUSIBLE_SITES`): app.js picks the entry by hostname at runtime and
falls back to the default, so one build serves every host. Free tier is 5M
tile requests/month, **conditional on keeping the CARTO + OpenStreetMap
attribution visible** — it is set on both raster sources in `app.js`; do not
drop it.

CARTO is retiring raster altogether in favour of vector. The staged successor
is vendored at `scripts/_lib/vendor/openfreemap-{positron,dark}.json` — key-free
OpenStreetMap vector tiles that merge into one style and keep the same
visibility toggle. See [scripts/_lib/vendor/README.md](scripts/_lib/vendor/README.md).

## Zoom-dependent level of detail (vineyard footprints)

Zoom decides which geometry the map draws (branch `feat/zoom-lod`,
2026-09-23; until then a Simple / Advanced toggle did). Two vector sources, one
`source-layer` (`appellations`) and one `promoteId: 'slug'` each, built by
`_build_source_block` in
[scripts/_lib/map_template.py](scripts/_lib/map_template.py); the constants
live in [scripts/_lib/vineyard_envelope.py](scripts/_lib/vineyard_envelope.py)
(`lod_config()`) and reach app.js as the `LOD` object, so Python and JS
never disagree about the zoom bands:

- **`appellations-overview`** (`wiki/map-data/appellations-overview.pmtiles`,
  tippecanoe z3–z11, layers `maxzoom: 11.9` = the end of the crossfade, so
  the layers are neither drawn nor hit-testable once the parcels are at
  full opacity). For the ~1,260 French records
  whose detail geometry is the INAO parcellaire (`geom_source` `parcellaire`
  / `parcellaire-dgc`) it carries a **generalised vineyard footprint**: a
  morphological closing of the parcels — buffer +250 m then −250 m in
  EPSG:3035, simplify 30 m — `geom_source = parcellaire-envelope`. Parcels
  closer than 500 m merge into one silhouette, holes narrower than that
  fill, and the result never leaves the parcels' 250 m dilation; median
  area 1.3× the parcels, against 5–8× for the commune union it replaces
  (which painted the Gironde estuary for Saint-Estèphe). A sub-denomination
  that inherits its polygon (`parent-appellation` / `sibling-dgc`) inherits
  the donor's footprint (`overview_by_slug`), so a child never draws a
  larger low-zoom shape than its parent. Every other record — the other
  countries' zones, Champagne and the IGPs (commune unions), the
  lieux-dits — draws the same polygon in both sources.
- **`appellations`** (`appellations.pmtiles`, tippecanoe z11–z12 with
  `--no-tiny-polygon-reduction-at-maximum-zoom`, layers `minzoom: 11`,
  overzoomed to the client's maxZoom 14): the parcels, exactly as the
  Advanced mode of the former toggle drew them.
- **Crossfade z11.0 → z11.9**: both sources drawn with complementary
  `fill-opacity` / `line-opacity`; the selection halos fade with their
  fills and sit above both fills (layer order: fill-overview, fill,
  halo-overview, halo, outline-overview, outline). Single-record fits cap
  at z12 so "show me this appellation" lands on parcels; `fitToFiltered`
  stays at z10.
- **Feature properties.** `area` is the detail polygon's area on *both*
  features (fill-sort-key and the paint ramps read it; it must not step at
  the crossfade); the overview feature adds `area_drawn`. `parts` and
  `frag` (perimeter/area in m⁻¹, measured on the tiled geometry by
  `shape_metrics`) drive the outline: from z10, `line-width =
  min(area ramp, max(W_min, K_z / frag))` with `K_z = 0.35·2^z / 108747`
  — constant ink per fill area, so a 112-parcel record gets a 0.4–0.8 px
  edge at z11–z12 where a single-part record keeps the area ramp, with
  floors (0.25 / 0.35 / 0.5 / 0.7 px at z10 / z11 / z12 / z14) so a small
  compact climat stays visible — and below the crossfade a `line-opacity`
  ramp on `parts` (scale-free; perimeter/area would dim every small climat)
  removes the stroke of the shapes that survive generalisation in hundreds
  of patches (a sub-half-pixel width still renders as a hairline; only
  opacity removes it). At the continental overview footprints stack five to
  ten deep per region, so `parcellaire-envelope` features draw with no
  outline below z6.5 and a fill scaled ×0.5 at z3 → ×1 at z8.
- **Radius.** 250 m is the closing for a record of one square kilometre
  and above; below that the radius scales with the record —
  `r = clamp(0.25·√area, 30 m, 250 m)` (`adaptive_radius`, 2026-09-25) —
  because 790 of the 1,259 footprint records are smaller than 1 km² and
  a 250 m closing of a Burgundy premier-cru climat of 0.01–0.1 km²
  lapped across the neighbouring climat (Les Gaudichots' footprint was
  65 % La Tâche parcels; 78 records bridged more than 5 % on the
  2026-09-24 audit): √area is the record's own length scale, so a
  0.05 km² climat closes at 56 m and follows its parcels. The record
  carries `geom_lod_radius_m` (inherited with the footprint by a
  sub-denomination) and the card's footprint line prints that radius;
  the cache directory is per radius, so the rule change invalidated no
  250 m entry.
- **Build.** Stage 04 computes the footprint after the geometry-outlier
  clip on the tile-simplified parcels; the parcellaire is split into
  connected components first (STRtree over the r-dilated part bounds +
  union-find — exact, a closing cannot merge parts more than 2r apart),
  which takes Languedoc's 31,488 parts from 832 s to ~30 s. Results are
  cached under `raw/cache/vineyard-envelopes/v<N>-r<r>/` keyed on the
  input geometry's digest, so a warm build costs nothing, a new
  parcellaire release invalidates exactly the records that changed, and
  the fresh-build rule holds; bump `ENVELOPE_VERSION` whenever the
  parameters change. Fatal gates: every slug in both tilesets (before the
  split, Crozes-Hermitage and Fiefs Vendéens had no low-zoom feature at
  all), the footprint bbox inside the parcels' bbox + r + simplify
  (`_check_envelope`), no empty geometry; a footprint above 3× its parcels
  is reported. A sub-denomination that inherits its footprint still gets
  its own geometry-outlier clip applied to it. The commune-level
  `appellations-villages.geojson` is still
  written — not tiled — because
  [scripts/audit_geometry_overlaps.py](scripts/audit_geometry_overlaps.py)
  is calibrated on commune borders; the old
  `appellations-villages.pmtiles` is unlinked.
- **Disclosure** (same commit as the geometry, JS and SSR in step:
  `renderAocCard` in app.js and `_approx_line` in
  [scripts/_lib/content_block.py](scripts/_lib/content_block.py)): the
  zoom-reactive footprint line (`geom_lod_footprint`, shown below z12,
  patched in place on `zoomend` — never re-render the card from a zoom, it
  would wipe pressed feedback chips and a half-typed note; since 2026-11-07
  the parcels band has a line of its own, `geom_lod_parcels` — "INAO parcel
  delimitation; at overview zooms a silhouette generalised at {radius} m" —
  one node per band, `data-lod-band`, the other hidden, because a
  parcellaire record's fold held only the footprint line and opened on
  nothing at z12: Margaux, a visitor's report of the same day); the
  commune-union line `geom_approx_aires_union` ("réunion des {n}
  communes de l'aire délimitée (INAO) ; pas de délimitation parcellaire")
  for plain `aires-csv` / `dgc-village-override` / `communes` records —
  every French IGP and Champagne, which said nothing before. A disclosure
  line states what the polygon is and where it comes from and stops
  there: the "plans d'eau et terres non viticoles compris" / "may include
  non-vineyard land" clauses were dropped on 2026-09-25 — nobody takes a
  commune-wide area for vineyard, and a caveat that states the obvious
  makes the lines that matter noisy; a zone-source line for the other
  countries (`geom_src_geoportal` / `_mapa` / `_betard` / `_pdo_union` /
  `_admin_union`); an About paragraph. `Feedback Flagged / Retracted /
  Note` and `Appellation Viewed` carry `lod` (`footprint` / `parcels` /
  `zone` — the band boundary is `footprint_max_zoom` = 11.9, where the
  overview layers stop) and `zoom` — see [docs/analytics.md](docs/analytics.md).
- **The Simple / Advanced toggle is gone (2026-10-17): one sidebar.** After
  the LOD change it only swapped the style facet (7 bucket chips vs the
  taxonomy tree), hid the Classification and Appellation type trees and
  gated spirits; 6.5 % of visitors ever touched it (Plausible, 90 days). Now
  the style facet is the taxonomy tree alone — depth-0 rows in
  `FACET_BUCKET_ORDER` (white, rosé, red, sparkling, sweet / dessert,
  fortified — since 2026-11-14 — oxidative, other; `BUCKETS` keeps the
  membership order the MCP context keys on), sub-styles folded behind a chevron (`buildTreeFacet`: the
  checkbox's label and the chevron button are siblings in a `.tree-row`,
  the subtree a hidden sibling `.tree-children` wrapper;
  `revealCheckedTreeRows` opens the branches above a ticked row). That also
  fixed a bug the chips had carried: their expansion table
  (`bucket_descendants`) drops the bucket slug itself, so the white and
  rosé chips filtered nothing and "red" matched only clairet / primeur; the
  tree path (`STYLE_DESCENDANTS`, self included) matches the records that
  carry the bucket slug. Classification and Appellation type are collapsed
  sections, always present. Spirits are gated by the `show_spirits`
  checkbox alone — since 2026-10-18 the Spirits legend pill on the map
  (2026-10-17 → 10-18: the sidebar's `#scope` row); `localStorage.view_mode`
  is removed on load; `Feedback *` no longer
  carry `view_mode` (`lod` + `zoom` say what was on screen) and `View Mode
  Switched` is retired. The appellation tree's → button moved out of the
  row's label for the same accessibility reason (`.aoc-row`).
  `bbox_villages` on the startup record is the overview feature's bbox;
  `drawnBbox` / `fitBbox` in app.js read it by zoom.
- **Audit.** [scripts/audit_vineyard_envelopes.py](scripts/audit_vineyard_envelopes.py):
  parity, containment (within `containment_tolerance_m`, the polygonal
  buffer's corner shave plus the simplify), bbox, inflation, and
  **bridging** — the share of the footprint's *added* area that lies on
  another appellation's parcels, umbrellas whose parcels cover the
  record's, its parent / children and its sibling DGCs excluded, and a
  bridge under `--bridge-min-km2` (0.05 km², under four pixels at the last
  footprint zoom) never failing `--strict`; `--water` fetches IGN BD TOPO
  `surface_hydrographique` (every nature, rivers included) per record into
  `raw/ign/bdtopo-hydro/` and measures the water inside the added area.
  Run it with `--strict` after any stage-04 build that touches geometry;
  the golden comparator does not see geometry (only the four app bundles
  go red on a tileset change, through the `?v=` fingerprint).

## Map chrome and panel (the 2026-10-17 UX pass)

One sidebar, one set of affordances, the same on every page. What the map
page is made of since 2026-10-17 (branch `feat/unified-sidebar`), with the
code that owns each piece:

- **Sidebar** (`_LAB_HEAD_TOP` / `_SIDEBAR` in map_template.py; reshaped by
  the 2026-10-18 review, see the Miro mockups in the memory of that
  session): the **head** — brand + the ‹ button that folds the sidebar to
  a 48 px **rail** (`#sidebar-rail`: pin, a magnifier that unfolds with
  the search focused, ›; the state is `html.sidebar-collapsed`, restored
  before first paint from `localStorage.sidebar_collapsed`, desktop only —
  the phone media query ignores it; `setSidebarCollapsed`) → the
  **omnisearch first** (a taller field with a magnifier and a × clear
  button; its results are **not a popup**: while the box holds text they
  replace the filters below it — `#sidebar.searching` hides the facets,
  the count and the chips, the list sits in the flow and scrolls with the
  sidebar, 25 appellations and 6 of each other group — because the
  dropdown that sat half over the tree read as a layout error to the
  2026-10-18 testers; an empty box shows the filters again, there are no
  seeds for an empty query, and Esc or the × clears the text and the tree
  filter with it, an empty box letting the key reach the drawer / panel) →
  the count → active-filter chips → **Wine style** (the taxonomy tree,
  depth-0 rows in `FACET_BUCKET_ORDER`, sub-styles behind a chevron; a row
  without children ends in a `.tree-toggle-spacer` of the chevron's width —
  28 px, 44 px on phones — and every row is the chevron's height, so the
  counts sit in one column at every breakpoint; on phones no facet scrolls
  inside a box of its own — the drawer is the one scroll surface; the
  section starts collapsed, like Classification and Appellation type — only
  the appellation tree is open by default, and `revealCheckedTreeRows`
  opens a section whose tree holds a tick, 2026-10-18) →
  Classification (collapsed; the Appellation type tree is withheld from the
  sidebar since 2026-10-18 — Boris: drop it for now, it may come back when
  AVAs etc. are introduced; its markup is the only thing removed, the
  builder, data tokens and chip handling stay dormant behind null-guards) →
  the country → region → appellation tree → footer (the disclaimer + the
  two links), which also
  holds the server-rendered `#config-menu` (language + theme) that app.js
  lifts into the ⚙ control — a no-JS visitor keeps the language links there.
  The theme switch is one row beside its heading: three icon-only buttons
  (sun / monitor / moon — the convention; the half-circle read as nothing),
  each with the word as `aria-label` and `title`, the pressed one filled
  with the accent (2026-10-19: the words had made the cells cramped).
  The sidebar is a flex column: on desktop the open appellation `<details>`
  takes every pixel left (`flex:1 1 auto`, at least 190 px) and is its own
  scroll box with a sticky summary — its content sits in the element's
  shadow slot, out of reach of a flex rule on the inner `.facet` — so the
  footer sits at the bottom whatever the list's length (feedback
  2026-10-18: it floated mid-sidebar under a 340 px list); on phones the
  drawer stays the one scroll surface. Countries and regions
  sort **alphabetically** in the page's language (`COUNTRY_TREE`; by size
  until 2026-10-18, the "no region" bucket still last). The legend left the
  sidebar for the map. **Sub-denominations nest under their parent's row**
  behind a chevron, their label the parent's name cut from the front
  (`childLabel`: "Aloxe-Corton premier cru Les Vercots" → "premier cru Les
  Vercots"; a name that does not start with the parent's, or carries a
  Latin bracket, stays whole; `parent_slug` is a startup field for it), and
  an appellation name **wraps** instead of truncating — fifteen Aloxe rows
  had read "Aloxe-Corton premier …". The tree filter opens a fold whose
  child matches (`data-auto-opened-q`, closed when the query clears), and a
  facet filter keeps a parent row for a reachable child (its own colour or
  roster). A tree row is a `.tree-row` / `.aoc-row` div holding the
  checkbox's `<label>` and, as **siblings**, the chevron (or an inert
  spacer) and the → open button — never a button inside a label (a button
  is a labelable element and would take the row's name as its own).
  `buildTreeFacet` folds each subtree into a hidden sibling
  `.tree-children` wrapper (`aria-controls` / `aria-expanded` on the
  chevron); `revealCheckedTreeRows` opens the branches above a ticked row. A
  facet filter with ≤ 25 matches opens the tree groups that hold them
  (`openGroupsWithMatches`, tagged `data-auto-opened-f`, closed again when
  the filter clears); above that the status line offers "show in the list".
- **Map chrome** (app.js after the landing gate; CSS "Map chrome" block):
  the **start view fits the corpus** (`bounds: corpusBounds()` — every wine
  record's bbox except the Atlantic islands west of 12° W, which would push
  the continent into a corner; the drinks, `is_wine` false and off by
  default, never count — with them the frame ran from Guadeloupe to La
  Réunion and the map opened at z3 over the Sahara, 2026-11-14: the overseas
  rum's one bbox spans both, so its east edge passes the 12° W test; a URL
  hash still wins, MapLibre applies
  `bounds` only when it is empty; until 2026-10-18 a fixed France view at
  z5.4, "too zoomed in"), and **no card is reopened** on the next visit
  (the `selected_slugs` restore reopened Penedès for whoever came after;
  the key is removed on load). MapLibre `NavigationControl` (no compass;
  accessible names from `ctrl_zoom_in` / `ctrl_zoom_out` through the Map
  `locale` option; hidden ≤ 768px) above the attribution, a metric
  `ScaleControl` bottom-left and above it the **legend pills**
  (`legendControl`): one pill per scheme — PDO, PGI, Spirits — each a
  checkbox (`#show-pdo` / `#show-igp` / `#show-spirits`; PDO on, the
  other two off by default, remembered per browser; a toggle redraws in
  place and never moves the camera — only a facet pick fits the map) and
  an ⓘ (`.scope-hint`, `data-key` pdo / pgi / spirit-gi) that opens the
  scheme definition of the card's pills — `TERMS_INFO`, the same tooltip
  element — by hover, focus or a tap (touch drives it through the click
  alone, because a tap is a burst of synthetic mouse events whose trailing
  mouseout would close what the tap opened). Filled while the scheme is
  drawn, outlined while hidden; the spirits pill takes dark ink — white
  fails AA on `#a07530`, the colour non-wine GIs paint (`is_wine` tested
  before the PGI kind in `_build_source_block`). Hiding PDOs is a third
  gate beside PGIs and spirits (`showPdo`, `isPdoRec`: filter expression,
  client matcher, landing gate, `openAppellation`). The **⚙ control**
  top-right (`settingsControl`) holds the languages by their own names and
  the light / system / dark switch as icon-only buttons (sun / monitor /
  moon, the word as accessible name + hover hint); Esc closes it first,
  a click elsewhere closes it without stealing focus. Bottom-corner
  controls stack, later ones above (`insertBefore(firstChild)`), with
  `clear:both` so they never sit side by side.
- **Hover** (pointer devices only, `(hover: hover) and (pointer: fine)`):
  `hitSlugsAt(point)` — the click's 4 px box over both fill layers, deduped,
  a `parent-appellation` / `sibling-dgc` inheritor dropped only while its
  donor is in the hit set too (a sub-denomination painted alone — ticked by
  itself, or kept by a filter its parent fails — is hovered and opened like
  any record; before 2026-10-22 Romagna Oriolo under `?grape=nebbiolo` could
  be neither), sorted by `localityRank` — serves hover and click alike; the polygon under the
  cursor takes feature-state `hover` (brighter fill, +0.8 px outline, always
  under the selection override) on both sources and a pointer-tracking
  label (`maplibregl.Popup.trackPointer`, `aria-hidden`) names it with "+N"
  for the rest of the stack a click would open. Hovering a stack row lights
  its polygon without the label.
- **Card** (`renderAocCard`, mirrored by `render_content_block`): name →
  meta → cancelled / promoted lines → "sub-denomination of" → stub line →
  styles → grapes → terroir facts XOR summary → dűlők / menzioni → note →
  **boundary notes** (`<details class="boundary-notes">`: the amber
  provenance lines and the zoom-reactive footprint line, folded; the summary
  says "· approximate area" for a shape that stands in for the delimitation
  — `isApproxGeom` / `_APPROX_GEOM_SOURCES`) → **related appellations** (a
  parent's sub-denominations under the regulator's own heading,
  `SUBDENOM_HEADINGS`, from the `children` list stage 04 writes into the
  parent's panel payload — parents only, never a startup field; 12 rows then
  "and N more"; and "All appellations in <region> · <country>", the tree's
  region / country filter — it *replaces* the appellation selection where a
  tree tick adds to it (2026-10-21: after "all of Italy" a second "all of
  Piemonte" had changed nothing) — the SSR card renders the country link as
  a real href to the browse index's `#c-<cc>` section) → provenance line →
  sources → "Report a mistake". The meta line's **unit count** ("N
  commune(s)") is printed only where the polygon is the union of the counted
  units — `COUNTED_UNION_SOURCES` in content_block.py, mirrored in app.js
  (`tests/test_content_block.py` keeps the two in step); it is an allowlist, so
  a new geometry source prints no count until it is added. Stage 04 writes
  `communes_matched` = -1 for every other source (`counted_units`), the GR LAU
  count from the units drawn (`gisco_ids`), and a Galician record adds its IET
  parishes ("1 commune(s) · 49 parish(es)"). Until 2026-10-23 a denylist let
  the zone resolvers' feature count read "1 commune(s)" on 388 zone-, NUTS-
  and geoportal-drawn cards. **The browser's Back works** (2026-10-21):
  a card opened or closed, a stack cycled and a related link followed are
  `pushState` entries (`setAocPath` / `writeHistory` in app.js), each
  carrying the view it showed — the facet filters and the open stack
  (`historyState`) — and `popstate` restores it (`restoreFilters`, the
  stack re-rendered untracked, the camera brought back by MapLibre's own
  hash listener); a filter change made in between is written onto the
  entry it was made in (`applyFilter`), so Back undoes the last navigation
  and keeps the ticks; a landing replaces its entry and seeds it. Plausible
  counts a `pushState` as a pageview (same path deduped), so card opens
  show in the Pages report since this change — see
  [docs/analytics.md](docs/analytics.md). A **stack** renders the focus card in full and the rest
  as rows (`stackRows`: name · classification · region; a click brings it to
  the front, `via: stack-pick`) under a visible hint; only the focus record's
  payload is fetched.
- **Phones (≤ 768px)**: a bar (`#mobile-bar`: brand link, ⚙, and a magnifier
  that opens the drawer with the search field focused and reads × while the
  drawer is open — the ☰ of 2026-10-17 said "menu" where the drawer is
  search-first (feedback 2026-10-21); the first screen is no longer a bare
  map) over the map; the ⚙ and its menu are
  homed into the bar by `homeSettings` (re-homed when the viewport crosses
  768 px) and the map's control is hidden there — a control floating under
  the bar looked misplaced — and the bar's search button went on 2026-10-18
  because it opened the drawer the ☰ opens, the search being the drawer's
  first row anyway; the legend pills stay on the map; the sidebar's fold
  button and rail do not exist on phones; the sidebar is a
  drawer with a scrim — its own brand block (`.brand-title` + `.subtitle`,
  the page `<h1>` on the home and fold pages) is visually hidden there, not
  removed, since the bar already names the site 50 px above it (2026-10-18) (`setDrawer` owns `#sidebar.open`, the scrim and the
  buttons' `aria-expanded`; focus moves into the drawer on open and back to
  the opener on close; Esc closes the drawer before the sheet; opening a
  record from the tree, the search or a related link closes it); a record
  opens as a **45 % sheet** with a handle (`setSheetExpanded`, 92 % when
  expanded; a scroll expands it; `closePanel` resets); `fitPadding` pads
  every camera fit for the sheet and the bar; `100dvh`,
  `env(safe-area-inset-*)`, `viewport-fit=cover`. **Tablets (769–1024px)**:
  the open panel overlays the map's right edge instead of pushing it.
  `html.booted` (two frames after start) gates the panel / drawer
  transitions, so an entity landing paints its panel open.
- **Design tokens** (`:root` at the top of the style block): one accent
  (`--c-accent`; the former `#7A1F2B` / `#7a1f3a` are gone), `--c-pgi`,
  `--c-spirit`, `--c-cream`, a neutral lightness scale `--n-0 … --n-900`,
  the dark panel pair, the amber note colours, four small text sizes
  (`--fs-2xs … --fs-md`) and the **sidebar palette by role** (`--side-bg`,
  `--side-bg-2…4`, `--side-border(-2)`, `--side-text(-2, -3)`,
  `--side-input-bg`, `--side-focus`, `--side-link`, `--side-chip-on`,
  `--side-accent-ink`): light by default and redefined under
  `html.theme-dark`, so the sidebar, the phone bar and the ⚙ menu follow
  the theme (feedback 2026-10-18: light mode had left the menu dark; write
  sidebar CSS with these, never with `--n-*`). `tests/test_map_chrome.py` keeps `--c-accent` /
  `--c-pgi` / `--c-spirit` in step with the paint and pins the hover state,
  the viewport meta and the phone chrome; `tests/test_sidebar_unified.py`
  pins the sidebar.
- **Analytics**: `Drawer Opened {via: menu | search}`, `Sheet Expanded
  {slug, via: handle | scroll}`, `Filter Applied` from a related link carries
  `via: panel-link`; since 2026-10-18 `Kind Toggled` also carries `kind:
  pdo`, and `Settings Opened`, `Sidebar Toggled {state, via}` and `Search
  Cleared {via: button | escape}` are new — see
  [docs/analytics.md](docs/analytics.md).

## Share, embed, and the view in the URL

The address bar is the share link (2026-10-22, after Reinier Broeks'
Druivenatlas copied `/nl/#5.96/49.368/12.455` from a grape search and got the
bare map: the filter lived in `history.state` only). The query string names
the view and the app writes it back on every change, so copying the URL, a
bookmark and a hand-written link all reproduce what was on screen. The
grammar lives in the shared query core
([scripts/_lib/assets/query_core.mjs](scripts/_lib/assets/query_core.mjs)
`viewFromQuery` / `queryFromView`, so the map, the node tests and later the
MCP server read it identically), the app applies it in `applyViewQuery` and
writes it in `currentUrl` (app.js):

- `grape=<slug|name>[,…]` + `main=1` (the "main grape only" chip) — a grape
  by its canonical slug, its label in any locale or a VIVC synonym
  (`grapeKeyFor`: `Sankt+Laurent`, `svatovavrinecke` and `sankt-laurent` are
  one filter); `style=<slug|label>[,…]` (`styleKeyFor`); `class=` /
  `type=` — the classification and appellation-type keys, checked against
  the app's own tables; `country=<cc>[,…]` (the whole country ticked),
  `region=<cc>:<raw key>[,…]` (or a label: `Piemonte`, `Burgundy`;
  `regionKeyFor`), `sel=<slug>[,…]` (single ticks) — the three are the
  partition `collapsedSelection` also gives the chip tray; `aocs=<slug>[,…]`
  stays the MCP server's "show these" set (stack + highlight + frame);
  `pdo=0` / `pgi=1` / `spirits=1` — the scheme gates, written only when
  they differ from the defaults; `embed=1` and `theme=dark` (embed only);
  `bbox=w,s,e,n` — an area to fit on load, in degrees: what the share
  dialog writes into an embed URL in place of the camera hash, so an
  iframe of any size shows the area that was shared (`fitBounds`, no
  padding: a little more in one direction when the ratios differ; the
  snippet also carries the map's aspect ratio, clamped to 1.2–2.4, so the
  fit is usually exact). A hash wins over a bbox when both are present;
  either suppresses the landing's own framing (`CAMERA_GIVEN`).
  Values are comma-separated and may repeat the key; unknown values are
  dropped, never guessed (`view.unknown` lists them). The camera stays in
  the hash; a filter link with no hash and no card frames its matches on
  load (`fitToFiltered(0)`).
- **A shared view is the same for everyone**: when the URL carries any of
  `grape main style class type country region sel pdo pgi spirits embed`
  (`view.shared`), the gates come from the URL, absent meaning the default,
  never from this browser's saved preference; a bare `?aocs=` keeps the
  older behaviour (its slugs turn on what they need). A hand-written
  `?grape=sankt-laurent` therefore shows the PDOs; add `&pgi=1` for the
  Landwein PGIs. `localStorage` is never written from an embed
  (`saveGate`).
- The language redirect in the head script skips an embed and carries the
  query across (`dest + search + hash`): before, a saved language choice
  dropped every shared filter on the way to its own locale.
- **Share** (the control top-right of the map above the ⚙, in the phone bar
  beside it — `shareControl` / `homeSettings`; `openShare`,
  `_build_share_dialog` in map_template.py): a native `<dialog>` with the
  subject (the open card and the rest of its stack, else the active filters
  with their match count, else "the map as shown" — `shareSubject`), the link
  (copy; the OS share sheet where `navigator.share` exists), and the embed
  code: the same view as an `<iframe>` (the link plus `embed=1`, lazy, 480 px)
  followed by a plain link under the map, the OpenStreetMap pattern, so the
  reader of the embedding page can always reach the full map. The copy
  buttons are the About dialog's (`button[data-copy]`, `data-copy-kind`
  tells the events apart). Two radios choose the embed's theme (light by
  default, which writes nothing; dark adds `theme=dark` — the snippet is
  re-rendered from `shareState`), and a `<details class="share-params">`
  behind an ⓘ lists the URL parameters for advanced users (`_SHARE_PARAMS`
  in map_template.py: the code is the grammar, the label its meaning).
- **Embed** (`?embed=1`): the map alone — `html.embed` is set pre-paint and
  the CSS hides the sidebar, the bar, the panel and the dialogs; no ⚙, no
  share control; the theme is the URL's (`theme=dark`), light otherwise; a
  brand badge top-left (`brandControl`) opens the same view on the site in a
  new tab (`siteUrl`); a click on the map opens a popup (`showEmbedPopup`,
  `.owm-embed-pop`) listing the stack under the point, each row the
  appellation's page in a new tab, the hover label as on the site; the
  legend pills still work. An embed never writes `localStorage` and never
  redirects by language. **Framing needs the CDN to allow it**: deploy.py's
  `X-Frame-Options: SAMEORIGIN` edge rule forbids every iframe — the change
  that retires it (`_RETIRED_HEADERS`, the rule deleted on the next deploy)
  is a security-header decision and is applied by hand; until then the
  snippet works on the site's own origin only.
- Analytics: `Share Opened {via, what}`, `Share Copied {kind}`, `Share
  Native`, `Embed Viewed {host, framed}`, `Embed Link Clicked {target, slug}` — see
  [docs/analytics.md](docs/analytics.md). An embed's pageview lands on the
  locale home's path (Plausible strips the query).

Not built, on purpose: a static per-grape page (`/nl/druif/sankt-laurent`,
indexable, SSR list + map) is the SEO answer to the same need and would be
where `?grape=` redirects later; a `map_url` on `filter_appellations` results
(the MCP server shares the codec) is a one-liner once the server is next
deployed.

## Structured data (JSON-LD) on entity pages

Each **indexable** per-appellation entity page (`/<lang>/<slug>`) carries a
single schema.org `@graph` — `WebSite → WebPage → Place(AdministrativeArea) →
BreadcrumbList`, with stable fragment `@id`s cross-linked via
`mainEntity` / `breadcrumb` / `isPartOf`. Built by `_build_entity_jsonld()`
in [scripts/_lib/map_template.py](scripts/_lib/map_template.py); **folded**
pages (sub-denominations, stubs, no-geometry, thin records) emit none, by
design. Honest modelling only — no `Article` markup (would need fabricated
author / editorial dates for a generated page).

- **`sameAs`** (entity reconciliation — the highest-value SEO/GEO signal):
  Wikidata QID → per-locale Wikipedia article → official regulator / producer
  body. Source PDFs and legal acts are *not* identity pages, so they go in the
  WebPage's **`isBasedOn`** instead. The eAmbrosia register is excluded — it's
  a hash-route SPA (`…/#/detail/EUGI…`), one server shell for every GI, so it's
  a poor `sameAs` target.
- **Wikidata QIDs** come from stage **02i**
  ([scripts/02i_fetch_wikidata_qids.py](scripts/02i_fetch_wikidata_qids.py)),
  a cached, incremental network stage (run between 02g and 04). Two resolution
  paths: (1) Wikidata property **P9854 "eAmbrosia ID"** joined on each record's
  `id_eambrosia` (the eAmbrosia-sourced countries), and (2) **Wikipedia
  sitelink → QID** via the MediaWiki `pageprops.wikibase_item` API, keyed on the
  02b/aocs validated article title (covers FR, which is INAO-sourced and carries
  no `id_eambrosia`, plus the P9854 gaps). Coverage is partial by design
  (~1.2 k of the corpus at v1; the rest fall back to Wikipedia/regulator
  `sameAs` or none). Pin/suppress a QID via `raw/wikidata/slug_overrides.json`.
  Stage 04 joins `qids-by-slug.json` onto each record as `wikidata_qid`.
- **BreadcrumbList**: `Open Wine Map → [parent →] appellation`. The country
  level is deliberately omitted — there is no per-country landing page, and a
  non-final `ListItem` without an `item` URL is invalid for Google's
  BreadcrumbList rich result. Every emitted crumb carries an `item`.
- `description` follows the panel's facts-XOR-summary rule (`_entity_lead`):
  the first two terroir-fact bullets in the page locale, led by the first
  *natural-factors* bullet that names the appellation as a standalone word —
  "the Rioja appellation" counts, "Rioja Alavesa" is a sibling's sentence,
  and the human-factors bullets (the decree history: "The ruling of the
  Lesparre tribunal of 29 November 1926…" led 317 EN pages) never lead —
  else the first natural bullet, else the first bullet; else the summary, but
  only when it is readable in that locale (02c-translated, or written in it —
  an untranslated FR decree boilerplate "Seuls peuvent prétendre…" is not an
  English description); else the meta description. `inLanguage` is the page
  locale on the WebSite and WebPage nodes only — schema.org defines it on
  CreativeWork and Event, and on the Place the validator flagged it
  UNKNOWN_FIELD on every entity page (Ahrefs, 2026-11-06). The `<meta
  name="description">` / `og:description` are facts
  first, then the lead: `name, region, country · TERM (SCHEME). Red, white —
  Chardonnay, Pinot Noir. <lead sentence>` clamped to 160 characters (the
  simple styles and three principal grapes: those the record's own facts
  or summary name first, in the order the text names them (the regulator's
  emphasis — Pauillac leads with Cabernet-Sauvignon, not the Cot its roster
  also allows), then by the number of the country's records carrying the
  grape (`_grape_rank_by_country`: Rioja opens with Tempranillo, not the
  Chardonnay a corpus-wide count puts first), then roster order — in
  Title Case, a Cyrillic or Greek spelling yielding to the lexicon's Latin
  name; only 57 EN descriptions named a top grape before 2026-09-26; Bing
  had flagged the older grape-only template as too short and
  near-identical, 2026-09-18) — the styles in a fixed reading order (white,
  red, rosé, sparkling, sweet, oxidative, other; an alphabetical cut had
  dropped "white" on 420 pages), the grape names cleaned of the regulator's
  colour code with Romance particles lower-cased, a synonym and its
  canonical slug named once, a colour bucket only when the record carries
  that colour itself (a white primeur is not "red"), and the lead kept only
  when at least 60 characters remain for it — the styles are dropped first,
  then the lead (a stub lead misleads more than none); a summary under
  eight words (a pliego form heading) is no lead;
  a record with neither facts nor summary (the thin CH cantonal AOCs
  indexed only as parents, Oberösterreich, the Veneto IGT) names its related
  denominations instead, so the description is never the bare head line
  (Bing flagged /en/schwyz at 42 characters, 2026-09-26), and its grape
  clause grows to as many principal varieties as the budget holds, "… and N
  other grape varieties" (`provenance_grapes_more`) when cut
  (`_fill_grape_clause`, 2026-11-07: Ahrefs' 46 descriptions under 100
  characters were all of this class, 76–99 characters; a record with a lead
  keeps the three-grape clause, and Schwyz / Zürich, with no roster, keep
  the denominations tail alone — never template text).
- The interprofession link (`sources.syndicate`, also a JSON-LD `sameAs`)
  resolves in [scripts/_lib/appellation_urls.py](scripts/_lib/appellation_urls.py):
  by slug, by parent slug, by the FR wine region (`by_bassin` is keyed on
  the region buckets — BORDEAUX → CIVB, ROUSSILLON → CIVR, CORSE → CIV
  Corse, ALSACE → CIVA …; a non-wine record takes a region body only when
  it is a spirit body, COGNAC / ARMAGNAC), then by the raw INAO comité, and
  only for a product comité that is not itself a region key (the cider
  comité → IDAC; the COGNAC comité had handed Whisky breton to the BNIC). A
  wrong body is worse than none: a region with no interprofession
  (LORRAINE, ILE-DE-FRANCE) has no entry, the Centre-Loire AOCs carry the
  BIVC by slug, and the Auvergne / Forez / Roannaise / Saint-Pourçain AOCs
  an explicit `null`.
- `<title>` (`_entity_title`, mirrored by `docTitleFor` in app.js) is kept
  within 65 characters — Bing's "Title too long" (7 of the crawled pages;
  491 of 1,659 EN index titles were over) — by progressive shortening, and
  always carries a map word (2026-09-26: 29 % of EN titles had dropped the
  brand and with it the only "map"; no FR / ES / NL title said carte / mapa
  / kaart). On the EN page the brand is that word: `name — TERM (SCHEME) ·
  region, country · Open Wine Map`; the other locales open with the map
  phrase of the `title_with_map` msgid in place of the brand ("Mercurey,
  carte du vignoble — AOC (AOP) · Bourgogne, France"; "mapa de viñedos";
  "kaart van het wijngebied" — bare "carte" / "wijnkaart" is a restaurant
  wine list; a spirit or cider GI, `is_wine` false, carries no vineyard
  phrase). Then the same with the scheme stripped ("AOC (PDO)" → "AOC"),
  brand kept; then the map phrase without the brand, with and without the
  scheme; then without the term, then country only, then the map phrase
  alone, then the bare name; a long "Latin (native)" Greek name tries its
  Latin form alone before losing the region; at each step the primary alias of a French "X
  ou Y" register name is tried first ("Côte de Nuits-Villages — AOC (PDO) ·
  Burgundy, France" rather than the 102-character full name). A region that
  is only the country again (`_COUNTRY_AS_REGION`: the 19 ES pliegos naming
  no comunidad, "Italia", "Österreich", "Slovensko", "Malta") is dropped
  from title, description and JSON-LD `containedInPlace` — never "España,
  Spain"; so is a region that merely repeats the appellation's name ("Mosel,
  Mosel, Germany", 86 pages — the test runs on the name, its Latin form, the
  French primary alias and the slug, against the label and the raw value,
  so "Alsace ou Vin d'Alsace" and Κρήτη count), a country that does (the
  Malta PDO) and the product comité RHUM ("Rum, France"). A region outlives
  the country on the ladder, and the bare name takes the brand before it
  stands alone. The `<h1>` keeps the full name.
- Contract: the builder returns a pre-serialised opaque string filling the
  `{jsonld_html}` `str.format` slot — its JSON braces are data, not format
  fields, so it must not be double-braced or `esc()`-ed.

## Internal linking & crawlability (browse index, cross-links, llms.txt, 404)

The map homepage is a JS app shell with no crawlable `<a>` links to entity
pages (the sidebar list is client-rendered), so the per-appellation pages were
link-graph orphans discoverable only via the sitemap. Stage 04 now emits a
static link layer (all in [scripts/_lib/map_template.py](scripts/_lib/map_template.py)
+ [scripts/04_build_maps.py](scripts/04_build_maps.py)):

- **Browse-index pages** — `wiki/<locale>/appellations/index.html` per locale,
  a self-contained page (`_render_browse_page` + `_BROWSE_TEMPLATE`, NOT the
  map shell) listing every **index**-classified appellation as a real `<a>`,
  grouped by country and sorted by localized name. The static crawl hub.
  A namespace `assert "appellations" not in aocs` guards the path collision.
  It carries the shell's social-card block (`og:image` 1200×630 +
  `twitter:*`) since 2026-11-07 — the four hubs were the only pages without
  it (Ahrefs, `tests/test_browse_page.py`).
  Since 2026-10-21 it reads like the About dialog: the map's design tokens,
  sliced from the shell's style block (`_design_tokens_css` /
  `_static_page_css`, shared with the 404 page — both had kept the
  pre-October accent in a CSS of their own and followed the OS scheme, not
  the ⚙ choice), the accent-underlined title, uppercase accent country
  headings, the ruled credit line, the sidebar's brand block and the locale
  names of the ⚙ menu, and the theme the ⚙ chose (`_THEME_PREPAINT_JS`, the
  map's pre-paint rule; the OS scheme is the no-JS fallback) — on the
  page-wide multi-column list it always had, since a 520 px column would
  not hold 1,600 links. The DOM is unchanged — one `<h1>`, an `<h2>` per
  country, plain `<ul>` of real links, the CollectionPage JSON-LD, no app
  bundle — which is what crawlers read; `tests/test_browse_page.py` pins it.
- **Inbound links** to the browse hub: the sidebar footer (`{browse_path}`
  slot, on the homepage AND every entity page) + a paragraph in the About
  dialog (`about_browse_html`).
- **Entity cross-link nav** (`_entity_nav_html` → `<nav class="entity-nav">`):
  browse link + parent (when `parent_slug` resolves) + children (from
  `children_by_parent`, built once in `emit_html`, passed as `children_map`).
  Emitted into `ssr_content` for index AND fold pages, hidden under `html.js`
  alongside `#ssr-content` (no-JS / crawler only). Because folds now carry a
  non-empty `ssr`, the brand-`<h1>` invariant is tracked by an explicit
  `has_card` flag, not `ssr` truthiness.
- **The `js` class is a promise the app must keep or withdraw.** The head
  script adds `html.js` before paint (so JS users never see the card flash),
  and app.js removes the card only once the live panel has rendered the
  record. Every path on which that cannot happen drops the class again:
  inside app.js (`showSsrFallback`) when the data bundle did not load
  (Google documents a 2 MB per-resource cap; the blob is ~4 MB raw but
  375 KB Brotli, and the 2026-09-26 live test parsed it, so the cap is on
  transferred bytes), when MapLibre threw in its constructor (Google's
  JavaScript guide says Googlebot has no WebGL; the Inspection Tool's
  renderer did have one on 2026-09-26 — the fallback covers both) or when
  the page's slug is not in the bundle; and, independently of app.js, in the head script's `load`
  listener, which reveals the card whenever `#ssr-content` is still in the
  DOM once the page has loaded — the case where app.js itself never ran
  (Search Console's live test reported app.js as "Other error" on
  2026-09-26; scripts are synchronous, so on the happy path the card is
  gone before `load`). Before 2026-09-26 the card was `display:none` in
  Googlebot's rendered DOM on every entity page (blank screenshot, ~500
  characters of chrome). The headless check is Playwright against
  `scripts/serve.py` under four conditions — WebGL on; `getContext('webgl*')`
  returning null; the blob route aborted; the app.js route aborted —
  asserting `#ssr-content` visible and `h1.offsetParent` non-null in the
  three failure cases and the live panel rendered in the first. Deployed
  2026-09-26 13:50; the Search Console live test then rendered the full
  panel (h1, styles, grapes, terroir) with 29 of 32 resources loaded — the
  three misses are robots-blocked by design: the Plausible tracker and the
  two pmtiles under `/map-data/` (the console's "Bad response code: 499"
  from pmtiles is Google's code for a robots-blocked fetch; polygons are
  not indexable anyway, so `/map-data/` stays disallowed).
- **`wiki/llms.txt`** (`_write_llms_txt`) — llmstxt.org markdown index: the EN
  meta description as the blockquote, the site links, then every index slug as
  an EN deep-link grouped by country. No build date inside (byte-stable for the
  deploy SHA256 diff).
- **Stale entity directories are pruned** at build time: a slug that left the
  corpus (renamed, cancelled) has its `wiki/<lang>/<slug>/` removed next to
  the panel-JSON prune, so the deploy diff deletes it on the CDN (four
  indexable `/valtenesi` pages from 2026-09-20 had survived two renames).
- **`wiki/404.html`** (`_write_404_page`) — self-contained noindex branded
  error page; Bunny serves it via `Custom404FilePath`.
- **Root-level verification files** — a search console's ownership file
  (Naver's `navera60fce37d9e94743bbf6483eed322080.html` and Seznam's
  `seznam-wmt-BrZt5ppWxq6mCwzBgnu0wNQXQ8USZoY4.txt`, both 2026-11-06; Seznam
  names the apex host, which 301s to www) is
  checked in under `scripts/_lib/site_root/` and copied into `wiki/` by stage
  04 beside the other root files (`copy_site_root_files` in
  [scripts/_lib/site_root_files.py](scripts/_lib/site_root_files.py); the
  directory is a shell path, so `--shell-only` re-emits it). deploy.py's
  `public_url` is None for a root-level `.html` other than `index.html`, so
  such a file is uploaded but never fingerprinted or submitted to IndexNow.
  The IndexNow key file is the exception: it stays in `.env` (see
  `write_seo_files`).
- **Data-updated date** — only the 5 homepages carry it (`about_updated_html`
  in the About dialog). `about_dialog_html` is built per-`_fill` (date for the
  homepage, dateless for entities) instead of living in `page_shell`, so a
  rebuild churns 5 files, not all ~11.6k entity pages.
- **Sitemap** grows to 4 home + 4 browse + (index slugs × 4 locales).
- **Language switcher keeps the appellation.** On an entity page the four
  static locale links point at `/<lang>/<slug>` (`_lang_switcher(slug=)` —
  passed per page through `_fill`, which merges per-page slots over
  `page_shell`), not at the locale roots: that is the crawlable cross-locale
  link the hreflang cluster asserts, and a no-JS visitor keeps their place.
  app.js still rewrites the destination on click (camera hash preserved).
- **Deploy** ([scripts/deploy.py](scripts/deploy.py)) gained two idempotent,
  warn-don't-fail Bunny config steps called from `main()`: `ensure_force_ssl`
  (POST `/pullzone/<id>/setForceSSL` per hostname whose `ForceSSL` is off — was
  serving `http://www.openwinemap.com/` as 200) and `ensure_custom_404`
  (resolve storage zone by name, set `Custom404FilePath=/404.html`). Apex→www
  301 stays a manual dashboard rule (smoke-checked by `check_apex_redirect`).
  IndexNow receives only pages whose *content* changed: every page is
  fingerprinted on its content — title, description / robots / Open Graph
  metas, canonical and hreflang links, JSON-LD, the server-rendered card and
  the entity nav, hashed asset references normalised; never the sidebar,
  the panel skeleton, the viewport meta or the scripts (2026-10-19, `page_content`
  in deploy.py) — and compared with the previous deploy's set in
  `tmp/deploy/indexnow-fingerprints-<env>.json`, so an asset-hash rebuild or
  a UI release no longer pings all ~11.6k pages (Bing's "IndexNow batch mode"
  warning; `--indexnow-baseline SITE_DIR` re-records the set from a snapshot
  after a change to the scope, `--no-indexnow` skips the submission once);
  and only under the page's own canonical URL
  (`public_url`: `/` for the EN home, `/<lang>/` and `/<lang>/appellations/`
  with the slash, `/<lang>/<slug>` without), never a `noindex` fold page
  (`indexnow_urls` reads the head) — before 2026-09-26 the deploy had pushed
  11,821 trailing-slash URLs and 5,180 fold pages Bing had never seen in
  the sitemap; see [docs/deploy.md](docs/deploy.md).

## Deploy environments

`scripts/deploy.sh` publishes `wiki/` to production; `scripts/deploy.sh --env
beta` publishes the *same build* to https://beta.openwinemap.com/ (own Bunny
pull + storage zone, `_BETA`-suffixed credentials in `.env`, robots.txt
overridden to `Disallow: /`, no IndexNow). The script reads the pull zone back
and refuses to run unless it serves the environment's hostname from the
expected storage zone. Full runbook, the .env layout and the reason beta is
blocked at robots.txt rather than with a noindex header (it would leak into
production through the cross-host canonical): [docs/deploy.md](docs/deploy.md).

## WebMCP tools and the MCP server

The map answers agents through two surfaces built on **one query core**,
[scripts/_lib/assets/query_core.mjs](scripts/_lib/assets/query_core.mjs): a
dependency-free ES module (search normalisation and scoring, grape / style /
region / scheme resolution, `search`, `filter`, `full`, `facets`, and the shared
`TOOL_DEFS` schemas). Stage 04 inlines it into app.js at the `__OWM_query_core__`
token (`export ` stripped; `_load_query_core_inline` refuses imports or build
tokens), and the app's omnisearch, tree filter and label helpers (`grapeName`,
`regionLabel`, `countryLabel`, `expandGrapeSet`, …) are aliases of the `QC`
instance — change search semantics in the core, never in app.js.

- **WebMCP** (end of app.js): `search_appellations`, `filter_appellations`,
  `get_appellation`, `list_facets` (adapters over `QC`) plus `show_appellation`
  (opens the panel), registered through `document.modelContext` only where the
  browser exposes it. Chrome ships it as an origin trial (Chrome 149–162, ends
  2027-03-30): the token lives in the repo-root `.env` as
  `WEBMCP_ORIGIN_TRIAL_TOKEN` (registered for https://openwinemap.com with
  subdomain matching, so www and beta share it) and stage 04 emits it as
  `<meta http-equiv="origin-trial">` straight after `<meta charset>` on every
  map page (`_origin_trial_meta`). Chrome reissues the token on renewal — swap
  the `.env` value and rebuild. Counted as the `WebMCP Tool` Plausible event.
- **Remote MCP server** ([mcp/](mcp/), https://mcp.openwinemap.com/mcp): a
  Bunny standalone Edge Script built on `@modelcontextprotocol/server`
  (`createMcpHandler`, stateless; serves protocol 2026-07-28 natively and
  2025-era clients through the SDK's stateless fallback). Same four read tools
  plus a `locale` argument (en / fr / es / nl). Data: stage 04 writes
  `wiki/data/mcp/<locale>.json` — the startup records plus the core's lookup
  tables (`QUERY_CONTEXT_KEYS` / `QUERY_CONTEXT_FORMAT` in map_template.py,
  pinned against `mcp/src/context.js` by `tests/test_mcp_query_context.py`);
  the script caches it per isolate and revalidates by ETag every 5 min, and
  `get_appellation` fetches the panel JSON `/data/d/<locale>/<slug>.json`.
  Counted server-side as the `MCP Tool` and `MCP Connect` Plausible events,
  in a Plausible site of their own, `mcp.openwinemap.com` (since 2026-10-28,
  the script's `PLAUSIBLE_DOMAIN`; until then the website's site, where every
  call from a rotating vendor IP counted as a visitor — 51 of the 200
  visitors of 2026-10-27; read the website's 2026-10-04 → 10-28 numbers with
  `hostname is not mcp.openwinemap.com`)
  (2026-10-26: the declaring client's name — every 2026-07-28 request carries
  it, a 2025-era client only in `initialize` —, the protocol era, the
  User-Agent's product token, result counts and errors; never a search's
  text). The calls arrive from the chat vendors' datacenters, so their country
  is the vendor's; the people are counted through the links: every site link
  the tools return carries `?utm_medium=mcp` (`LINK_TAG`, the query core's
  `linkQuery`), plus `utm_content=map` from the map view, and by the view's
  own `MCP Map Viewed` event, sent from the reader's browser once the map has
  drawn (`trackViewed` in mcp/view/view.js; configured, and its Plausible host
  added to the view's CSP, only for a counted request — `viewAnalytics` in
  server.js). `MCP Connect` counts conversations that loaded the connector
  (claude.ai and Claude Code list the tools at every start), not uses; a
  claude.ai connector used from Claude Code is proxied through Anthropic's
  cloud too (`ua` = `claude-user`, a US datacenter), so the owner's own
  sessions are indistinguishable from anyone's. Build / deploy:
  `.venv/bin/python scripts/deploy_mcp.py deploy` (esbuild bundle → Bunny
  compute API → publish with the git SHA → smoke test in all three protocol
  modes); the site deploy (`deploy.sh`) must go first when the context format
  changes. Tests: `npm test` in mcp/ (core anchors, protocol conformance per
  mode, context store), `.venv/bin/python mcp/test/parity_webmcp.py` (the page's
  WebMCP tools and the server answer the same calls identically, headless
  Chromium). Plan, decisions and spike results:
  [docs/plan-mcp-server.md](docs/plan-mcp-server.md).
- **The map inside the chat** (MCP Apps): a fifth tool, `show_on_map`
  {slugs}, carries `_meta.ui.resourceUri` → `ui://open-wine-map/map`, a
  self-contained MapLibre view ([mcp/view/](mcp/view/), built into
  `dist/view.html` by `npm run build:view`) that draws the requested
  appellations straight from the site's pmtiles (`TILE_ORIGIN`, default the
  site; Bunny already answers them cross-origin, `Range` preflight included)
  over the CARTO basemap (`CARTO_KEY` script variable). The tile URLs carry the
  site's own `?v=` content fingerprint, handed over in the query context's
  `tiles` key and the tool result — the files are browser-cached for 30 days,
  so a deploy must change the URL. With ≤ 10
  appellations each has its own colour and a legend list: hover a row or a
  polygon to light it, click a row to zoom to it (the site button then opens
  its page), the colour square hides it. Its text result and the view's site
  button link the set as **`/?aocs=a,b,c`** (any locale home, ≤ 200 slugs):
  app.js opens that stack in the panel, highlights all of it and frames the
  map on it; the query stays in the URL until the reader opens something else.
  Host check: `.venv/bin/python mcp/test/apps_host_check.py [--shots DIR]
  [--live MCP_URL]`. Plan and phases: [docs/plan-mcp-apps.md](docs/plan-mcp-apps.md).

## Analytics

Self-hosted Plausible, one site per environment (`openwinemap.com`,
`beta.openwinemap.com`, …) and one for the MCP server's events
(`mcp.openwinemap.com`, set by the Edge Script, never the website's): the tracker script pins the site, so the snippet
in `_TEMPLATE` picks it by hostname at runtime from `plausible_sites()`
([scripts/_lib/env.py](scripts/_lib/env.py); prod is the code default, other
environments via `PLAUSIBLE_SITES` in `.env`) — one build serves every
environment, an unknown host loads no tracker. Custom events go through
`track()` in [scripts/_lib/assets/app.js](scripts/_lib/assets/app.js). The
event/prop reference, the goal-configuration recipe (events are stored but
invisible until configured as goals — retroactively), and the known reading
artefacts (replaceState opens are not pageviews; page-load opens are not
tracked; `Appellation Viewed.slug` is the stack focus, split by `via`; app.js
rewrites the address while the page parses, so the head snippet notes the
landing's `utm_*` / `ref` / `source` parameters and hands them back to the
first pageview through the tracker's `transformRequest` — campaign tags were
lost 2026-10-22 → 10-26 without it) live in
[docs/analytics.md](docs/analytics.md). Keep that table in sync when adding
or renaming a `track()` call, and never commit an API key.

**Visitor feedback lives in Plausible, not GitHub.** Every appellation card
ends with a "Report a mistake" section (`renderFeedback` in app.js — a
titled card section, same style as Sources; a top-of-card pill was tried and
dropped 2026-09-16 as redundant): one tap on an aspect
chip (boundary / grapes / facts / name / sources / other) fires
`Feedback Flagged {slug, aspect, geom_source, …}` (a second tap un-flags it:
`Feedback Retracted`), and an optional note goes out as `Feedback Note {slug,
aspect, note, credit}` — `note` (≤ 500 chars) and `credit` (≤ 60) are the two
props that carry visitor text (self-hosted). **Credit (2026-10-31):** the box
a chip opens also offers "Your name or pseudonym (optional)" under a hint that
says it is public; Send carries it as `credit` (a name with no note still goes
out — it credits that card's flags), never a chip tap; the browser remembers it
(`owm_feedback_credit`, cleared by sending an empty field). A name reaches the
site only through the checked-in [scripts/_lib/contributors.json](scripts/_lib/contributors.json)
(`_lib/contributors.py`), added at triage for a report that was acted on —
never an offensive name, an impersonation, contact details or a link; removed
on request. The About dialog shows a "Thanks" section once the table has a
name, and its privacy paragraph states the exception (kept to thank you,
removed by e-mail). A blocked tracker — localhost included — falls back to the
prefilled e-mail link (chip shown pressed, nothing persisted), and `track()` echoes events
to the console; a dev site keyed on `localhost` in `PLAUSIBLE_SITES` makes
local testing land in a dashboard. The stub card's "help us find it" opens the same row on
`sources`. The sidebar's GitHub-issue link is gone (clicks, no issues). The
curation view is [scripts/feedback_report.py](scripts/feedback_report.py)
(`PLAUSIBLE_API_KEY` in the repo-root `.env`): net flags per
appellation × aspect against panel opens, every note verbatim with its credit,
and the names offered for credit, marked when contributors.json lists them.

## Validators (detectors over the build, never editors)

Five skills, built 2026-10-23 from [docs/plan-validators.md](docs/plan-validators.md),
check the *built site* against its sources from outside the pipeline. None
writes under `wiki/` or `raw/` (apart from a one-day probe cache under
`raw/cache/`): a finding carries a public-source quote, a failure-mode tag
and its routing — a parser, an override file with a cited source, a feedback
sidecar, a `--only` re-run — and the "isolated or broader" sweep is part of
reporting it. Reports land under `tmp/validation/` (JSON + Markdown); a full
review is copied to a dated `docs/review-*.md`.

- **`/validate-cards`** — [scripts/audit_cards_llm.py](scripts/audit_cards_llm.py)
  over the packet of [scripts/_lib/card_packet.py](scripts/_lib/card_packet.py):
  the card as the reader sees it in one locale (the SSR card rendered through
  `render_content_block` and reduced to text, plus structured fields — the
  summary only when the card renders it, facts XOR summary) next to every
  source document behind it (the extracted record section by section, the
  national-spec and EU-register sidecars, for CZ the Vyhláška 88/2017 roster
  every card follows, the Wikipedia page; a document the packet lacks shows
  up as confident false findings — Moravské drew four against the 2011 fiche
  alone on the first run). The judge
  is the `audit` stage default (Opus; the extractor is Sonnet) and never sees
  the pipeline's quotes or prompts. Per card section it returns error /
  omission / unsupported / stale findings with a severity, a tag, the card's
  claim, a verbatim quote and a fix; every quote is re-grounded with the
  terroir-coverage matcher (`verified`). Scope by `--sample` (stratified by
  country × geometry source), `--top-viewed` (Plausible), `--only`,
  `--country`, `--slugs-file` (the `--slugs-out` of `diff_records.py`);
  `--locale`, `--section grapes`, `--second-opinion MODEL`, `--batch`,
  `--max-usd` (≈ $0.10 a card at the Opus batch rate; the script refuses
  above the ceiling without `--yes`), `--emit-feedback DIR` (the
  review-evidence shape `build_terroir_feedback.py` reads),
  `--emit-curator-md`, `--compare A B`. First run (3 cards, synchronous):
  Rioja Alta "do-not-trust" with the Alavesa sibling leak, a Malvasía identity
  pin and a missing sweet style, all quoted; Pauillac "trust".
- **`/validate-sources`** — [scripts/audit_source_freshness.py](scripts/audit_source_freshness.py)
  over [scripts/_lib/freshness/](scripts/_lib/freshness/): one probe module per
  upstream family (eAmbrosia list diffed per country; INAO's datasets on
  data.gouv.fr and, with `--inao`, the product page's dated act; GOV.UK content
  API; GISCO / swisstopo release listings; Bétard = SNAPSHOT; every document
  URL a card cites by HEAD, `--deep` re-fetching and comparing sha256; trade
  bodies liveness only; `--reference` Wikipedia revisions). Verdicts CURRENT /
  NEWER-UPSTREAM / RELINKED / GONE / UNREACHABLE / IN-OPPOSITION / SNAPSHOT /
  COVERED (EUR-Lex, through eAmbrosia) / UNVERIFIABLE, each with the re-fetch
  recipe. Per-host politeness delay, a circuit breaker after three failures
  (BO Agri is French-IP only), a request budget, a one-day cache. `--counts`
  reconciles each country's held file numbers against the live register (FR
  through `raw/inao/register/resolved.json`). First run 2026-10-23: 62 GIs
  modified or republished since their fetch, Nivegy-völgy (PDO-HU-02816)
  registered and not indexed, the INAO parcellaire release of 2026-10-19
  newer than the 2026-09-28 one built, Priorat's INCAVI pliego and
  Znojemská's Sbírka file gone (404). A register publication counts as held
  when its OJ reference is the document the oj-pages manifest fetched (the
  ELI "C/2026/3572" and EUR-Lex's "OJ:C_202603572" are one key,
  `eambrosia.oj_keys`): the country index can predate a newest-OJ-C fetch,
  and Belokranjec and Metliška črnina had read NEWER-UPSTREAM for the
  document already in the build (2026-10-25).
- **`/validate-geometry`** — [scripts/audit_geometry_vs_text.py](scripts/audit_geometry_vs_text.py),
  the one polygon-vs-**text** check: the units the delimitation names (FR:
  INAO aires CSV + cahier section IV; CH: BFS communes; RO / BG / HU / GR / CY:
  the record's parsed `geo_communes`; IT / AT: `parse_geo_area`; GR / PT: the
  stage-04 disclosure fields; `--llm`: an independent model reading, cached
  per text sha) against the units the resolved polygon covers whole (≥ 95 %)
  or in part (> 5 %), reverse-geocoded on GISCO LAU, IGN communes,
  swissBOUNDARIES, CAOP or ONS. An FR aire token with a partial-commune
  qualifier — "Mercurol-Veaunes pour le seul territoire de la commune déléguée
  de Mercurol" — resolves to the commune (`fr_token`) and is not `missing` when
  its parcels fall under the drawn-in-part threshold (`partial_undrawn`;
  2026-10-30, 340 such tokens in 142 FR records had read as unresolved).
  Homonyms are settled by the text's own header
  where the list has one — the oblast for BG (`geo_communes_scoped`, the
  GISCO id's EKATTE prefix), the județ for RO (each unit's NUTS-3 county),
  with the resolver's village rule (`geo_communes_villages`) — else by
  distance (a same-named unit farther than 25 km from the polygon is the
  layer's, not the text's; 2026-10-24: the 25 km rule had bound RO villages
  to same-named communes of the next county and filed five RO IGPs SUSPECT);
  a national-spec stub is read from its sidecar's list, as stage 04 draws
  it. The `--llm` read reports each unit's county / oblast (`parent`), keeps
  villages apart (`village` level) and gets an answer budget that grows with
  the text (a truncated answer is not cached). Administrative prefixes are
  folded ("Oraş Babadag"), county-level names set
  aside (ABOVE-COMMUNE). Read through `geom_source`: a commune-union record's
  MISSING / EXTRA units are a parser defect, a zone / Bétard / parcellaire
  record's whole EXTRA units a vintage or attribution question. Also the
  child-inside-parent containment no other audit checks (parents drawn from a
  règlement scan excluded). Buckets OK / SUSPECT / REVIEWED
  ([scripts/_lib/geometry_text_overrides.json](scripts/_lib/geometry_text_overrides.json),
  pinned `missing` / `extra` so an entry re-fires on drift) / NO-TEXT /
  NO-UNITS / ABOVE-COMMUNE; `--strict`. First run: the BG PGI Дунавска равнина
  is drawn as the union of its 21 member PDOs while its text names 114
  obshtini (40 drawn) — the region-pdo-union fallback under-draws a PGI whose
  text is a commune list; Bétard's padding shows as EXTRA whole communes on
  the Romanian PDOs. Its French sibling,
  [scripts/audit_aires_vs_cahier.py](scripts/audit_aires_vs_cahier.py)
  (2026-11-13), compares the cahier's own commune list with INAO's rows —
  the cahier wins; see "INAO aires-communes supplements".
- **`/validate-release`** — [scripts/validate_release.py](scripts/validate_release.py)
  runs the registry of `--strict` audits, the translation detectors, pytest,
  the About-page date and the stage-04 snapshot staleness as one table
  (`--quick` skips the geometry audits; `--list`); exit 1 on a failed gate.
  [scripts/diff_records.py](scripts/diff_records.py) `snapshot` / `diff`
  reduces a build to one JSON per record (roster, styles, region, geometry
  source, area, facts sha, sources) and lists what a rebuild changed, with
  `--slugs-out` feeding the card validator.
- **`/triage-feedback`** — the recurring flag-triage session as a procedure:
  `feedback_report.py` → the validators on the flagged slugs → the failure
  mode and its sweep → the dated triage doc and the CURATOR_TODO rows.

`tests/test_card_packet.py`, `test_cards_llm.py`, `test_freshness.py`,
`test_geometry_vs_text.py`, `test_diff_records.py` pin the guards on canned
data (no network, no model); `tests/test_validator_skills.py` lints that every
script a skill names exists, that every release-registry command points at a
script with a `--strict` flag, and that this section names the scripts.

## Code style

- Python 3.12, ruff line length 100.
- Single-purpose scripts; share helpers via `scripts/_lib/`.
- **Stage 04 module layout.** `04_build_maps.py` orchestrates; the bulk of its
  logic lives in `scripts/_lib/`. The per-country national-spec augmenters are
  in `_lib/augment/<cc>.py` (their shared slug-keyed provenance caches +
  sidecar dirs in `_lib/augment/_shared.py` — imported by both the augmenter
  that writes them and `_sources_for()`/the panel-blob phase that reads them,
  so the dict objects stay identical across the split). Grape/style lexicon
  loading is in `_lib/lexicon_loading.py`; the commune-index + DGC/ES geometry
  resolution chain (incl. the `DGCGeomResult` dataclass) is in
  `_lib/geom_chain.py`. These were move-only extractions verified by the
  golden comparator (see below); when moving more out of `04_build_maps.py`,
  use the `stage04-extraction` skill — stage-04 failures are silent (a country
  or feature just vanishes from the map), so a full-build golden diff, not
  "it didn't crash", is the proof.
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
