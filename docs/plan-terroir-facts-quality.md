# Terroir-fact quality fixes — implementation handoff (2026-09-11)

> **2026-09-12 — full-corpus review:** every EN bullet was graded and the
> high-severity findings verified; see
> [review-terroir-facts-2026-09-12.md](review-terroir-facts-2026-09-12.md)
> for the measured state after the fixes below and the next ranked work items
> (R1–R10). Its headline: ≈ 7 % of bullets still mislead, three quarters from
> extraction, and 83 % of the corpus predates the style block.

Self-contained plan for a fresh session. Everything below was established by
reading a stratified sample of 1,000 English terroir-fact bullets (plus an
earlier 100) against their source quotes, and by a set of corpus-wide checks.
Evidence, sampler output and per-bullet tags are preserved under
`tmp/terroir-facts-review/` (gitignored, see "Evidence" at the end).

Nothing in this plan changes the public-source rules in `CLAUDE.md`: every fix
is either a pipeline-code change, a prompt change, or a curator re-source
through the existing `manual_overrides.json` mechanism.

## TL;DR

| finding | scale | root cause | work item |
|---|---|---|---|
| Source-language common nouns and non-Latin script left in EN bullets | 16 % of all bullets; 37–51 % for GR/BG/HU/CZ/HR/LU; 12 % IT | the per-country 02e "Preserve … verbatim" prompt lists contain common nouns (soils, climates, harvest categories, scheme abbreviations) | **W1** |
| Alsace grand-cru pages carry Zotzenberg's geology, slope, Sylvaner rule and 1992 date | 51 records, ~250 of 430 bullets wrong | 02d slicer keys spans by section number over the one shared 339 KB cahier → last chapter wins | **W2a** |
| Pierrevert carries Saint-Pourçain's lien; L'Étoile and Grands-Echezeaux carry Bourgogne Passe-tout-grains' lien | 3 records, 15 bullets, all wrong | stage 01 fetched the wrong BO Agri PDF (L'Étoile and Grands-Echezeaux share one manifest filename) | **W2b** |
| Same fact repeated inside one record | 10 % of bullets (435 identical-quote repeats in 340 records, plus paraphrases) | the four sub-section calls re-extract the same sentence; no dedupe | **W3** |
| "wiki" provenance on facts that are grounded in the cahier | 626 of 982 wiki-labelled facts | quotes containing "[…]" fail the longest-contiguous-match coverage test | **W4** |
| Arrows, INAO colour codes (Pinot Noir N), unexpanded VT/SGN, missing terminal period, meta text ("confirmed by Wikipedia") | 4.3 % + 8 % punctuation | no style rules in the 02d prompt; codes are cahier vocabulary | **W5** |
| Bullets with no information ("uniqueness stems from soil, climate and varieties") | 3.4 % overall, 18 % GR | boilerplate sentence shared by many GR/CY specs | **W6** |
| Hedge dropped: "repose essentiellement sur pinot noir" → "exclusively Pinot Noir" | 14 FR bullets corpus-wide | no "keep hedges" rule | **W5** |
| Fact filed under the wrong sub-section | 1.7 % | sub-section is the slice the call came from, not a per-fact judgement | **W7** |
| Audit covers only fr/es/gb and none of the above checks | — | — | **W8** |

What is **not** broken: numeric hallucination. Of 1,275 numbers that appear in
a bullet but not in its grounding quote, at most 5 are unsupported by the
source text once number formats are normalised (`13°5`, `22, 5`, `un
centinaio`, `anno mille`). Extraction fidelity is high; the defects are
mechanical and prompt-level.

Baseline rates (n = 1,000, Wilson 95 % CI) to beat after the fixes:

| category | rate |
|---|---|
| content error / over-claim / mistranslation | 3.4 % (2.4–4.7) — 1.6 % once W2 is fixed |
| untranslated common noun or non-Latin script | 16.1 % (14.0–18.5) |
| near-duplicate within record | 10.1 % (8.4–12.1) |
| provenance mislabelled as wiki | 5.4 % (4.2–7.0) |
| style (arrow / colour code / abbreviation / meta) | 4.3 % (3.2–5.7) |
| no information | 3.4 % (2.4–4.7) |
| misfiled sub-section | 1.7 % (1.1–2.7) |
| no terminal punctuation | 8.1 % (6.6–10.0) |
| fully clean | 58.1 % |

## Landed 2026-09-11 — W3 + W4 as cache post-passes (no LLM call)

- **W4** — `scripts/_lib/terroir_coverage.py` is now the one grounding
  function (ellipsis-aware: a multi-span quote is graded span by span, and the
  grade is the better of whole-quote and weakest-span, so nothing already
  passing is demoted); all 21 `02d` scripts and `audit_terroir_facts.py`
  import it. `scripts/recompute_terroir_provenance.py` re-graded the caches
  through each country's own 02d source resolver: 467 caches rewritten,
  provenance changed on **204 facts (174 wiki→both, 30 cahier→both)**, 481
  translation caches synced; 26 stale records skipped (22 Wikipedia-revision
  drift, 3 CH cahier-context drift, `collioure` no longer a 02d target) —
  those want a 02d re-run, not a post-pass. The "~600" estimate above counted
  every wiki-labelled fact with a cahier quote; only 226 of those quotes carry
  an ellipsis, and 174 ground on every span. The residual ~400 are light
  paraphrases / typography (coverage 0.4–0.59, no ellipsis) — a normalisation
  question for W5/W8, not a coverage-rule bug. Report:
  `tmp/terroir-facts-review/provenance-recompute.json`.
- **W3** — `scripts/_lib/terroir_dedupe.py` + `scripts/dedupe_terroir_facts.py`.
  The rule as landed, calibrated against the 1,000-bullet review: bullets
  near-identical (`token_set_ratio ≥ 85`), or same / contained source quote
  (≥ 30 chars) **and** bullet similarity ≥ 60; never when the bullets carry
  different number sets; never when they lead with different sub-denomination
  names (the roster stage 04's sibling filter uses — commit 24bd059d — so no
  sub-zone page loses the bullet about it); transitive. The plan's bare
  "identical quote" rule was rejected on evidence: 183 of the 552
  identical-quote pairs are two distinct facts from one source sentence
  (alluvial soils / river water supply). Recall against the review's `dup`
  tags: 78 %. Applied: **798 of 12,114 facts dropped (6.6 %)** — 698
  same-quote, 100 similar-bullet — in 560 records. FR is nearly untouched (3)
  because FR 02d slices the lien into disjoint sub-sections, while every other
  country re-reads the whole lien per sub-section call (IT 296, ES 136, BG 69,
  GR 50). The 2,132 index-aligned 02e caches were pruned in step and their
  `source_facts_sha` updated, so no translation was lost or redone; the sibling
  guard never had to fire on the current corpus. Report:
  `tmp/terroir-facts-review/dedupe.json`.
- **W2b** — no BO Agri lookup was needed: the eAmbrosia register serves each
  of the three appellations' own cahier. Pinned `prefer_cahier: true` in the
  checked-in `scripts/_lib/fr/register_overrides.json`; stage 01 gained the
  prefer-register path (bypasses its has-usable-cahier guard for a pin), the
  three were re-bound and re-extracted (Pierrevert 5.2 KB lien naming
  Pierrevert, L'Étoile 9.4 KB / 14 mentions, Grands-Echezeaux 8.6 KB / 17
  mentions; Saint-Pourçain and Passe-tout-grains 0). Name guard → W8 audit.
- **W2a** — `scripts/_lib/terroir_chapters.py` finds the `« Alsace grand cru
  X »` chapter headings; FR 02d's `_job_from_record` windows a shared cahier to
  the record's own chapter (51 / 51 resolve, 5.9–8.9 KB each, four slices) and
  skips a record with no own chapter instead of falling back. The 51 caches
  are stale by sha and are in the scoped re-extraction list.
- **W3b** — every 02d script now calls `dedupe_facts` after its sub-section
  loop (`n_deduped` in the cache) and carries the shared style block
  (`scripts/_lib/terroir_prompts.STYLE_RULES`, spliced before the JSON-only
  paragraph of all 21 prompts: full sentences, no arrows / labels / colour
  codes, expand VT-SGN-TBA, never mention the document, keep hedges, do not
  restate, skip tautologies).
- **W5** — `scripts/_lib/terroir_normalize.py` (colour codes stripped only
  after a name the grape matcher's vocabulary recognises — "l'ugni blanc B" →
  "l'ugni blanc", "orizzonte B" / "Weinbauzone B" untouched; VT / SGN
  expanded; terminal period; and, for the four target locales only, residual
  Greek / Cyrillic script Latinised — homoglyphs inside a Latin word mapped
  ("Thermoheliоhydric"), whole non-Latin gloss tokens transliterated with
  unidecode ("(ξερολιθιές)" → "(xerolithies)"), a Greek-letter chemical
  prefix ("α-terpineol") and a predominantly non-Latin bullet left alone).
  Applied at stage-04 render after the overlay and sibling filter, and as
  `scripts/normalize_terroir_facts.py` over the caches: **1,261 source bullets in 365 records and 4,037 translated bullets
  in 1,015 caches** normalised, translation caches re-keyed, nothing
  re-translated. Arrows / meta text / dropped hedges go through the scoped
  re-extraction (169 arrow records, 9 meta, 5 hedge).
- **W6** — `scripts/_lib/terroir_boilerplate.py` + `filter_terroir_boilerplate.py`.
  Grouping by exact quote failed (the sentence embeds the appellation name
  and the model quotes spans of varying length), so records are grouped per
  (country, tautology pattern): a pattern quoted by ≥ 3 records of one
  country is boilerplate for all of them; never a record's only fact, never a
  bullet carrying a number. Dry run: 137 facts in 116 records (GR 84, FR 44 —
  the Zotzenberg-contaminated Alsace ones, IT 6, DE 3). Applied after the
  Alsace re-extraction.

- **W8** — `scripts/audit_terroir_facts.py` rewritten over
  `scripts/_lib/terroir_sources.py` (each country's own 02d resolver, so all
  21 countries are audited, not fr/es/gb). New checks, each counted in
  `summary.checks` with its rows in the report: non-Latin script in the four
  translation locales (S), colour code (S), missing terminal punctuation (S),
  arrow / label prefix / meta text (R), intra-record duplicates via
  `duplicate_reason` (S), cross-record shared quotes (R), the FR name guard
  (S, whitelist `saone-et-loire`), the shared-cahier own-chapter checks (S),
  wiki-provenance-with-cahier-quote (R). `--country`, `--strict` (exit 1 on
  any strict finding), 31 unit tests, ~2 min on the corpus. Baseline before
  the re-runs: non-Latin 3,167, arrows 819 (216 source), intra-record
  duplicates 27, quote-outside-own-chapter 198 (the Alsace crus), colour codes
  0 and missing periods 0 (normaliser already applied).
- **W1** — `translation_rules()` / `translation_system_prompt()` in
  `scripts/_lib/terroir_prompts.py`: two buckets (keep names verbatim /
  translate the common nouns, with the plan's per-language examples), the
  one-time-gloss allowance, the hard Latin-script rule for el/bg, the two W5
  02e rules and keep-hedges; every 02e script now passes its proper-noun
  roster (common nouns dropped per country — see the agent report in the
  session) through it and appends the EN/NL glossary (previously FR-only).
  `_EN_GLOSSARY` +8 calques. `--only SLUG` on all 21 scripts.
  `scripts/detect_untranslated_terroir_facts.py` (non-Latin + the LEAK regex,
  minus tokens that are correct target-language words: NL leem / zandleem /
  mergel / lege, FR marne + the proper noun Marne) flagged **5,091 bullets =
  1,984 (slug, locale) pairs in 596 slugs** (gr 2,069, bg 1,000, it 974).
- **W1 follow-up (Boris, live check of `/nl/alsace-bergheim`: "Vosges" must be
  "Vogezen")** — the keep-verbatim rule was too broad: "region names" kept
  mountain ranges, rivers, seas and regions-as-places in the source form.
  `translation_rules` now has a geography rule (established target exonym
  where one exists — Vogezen / Rijn / Apennijnen / Tuscany / Piedmont /
  Burgundy-as-region — while appellation names stay exactly as registered even
  when they coincide with a region, and grape or institution names built on a
  place stay verbatim). `scripts/_lib/exonyms.py` carries the table and the
  detector flags residual source forms (`exonym:` reason; GI-homonym forms
  only in place-like context): **418 bullets in 313 (slug, locale) pairs**
  (Piemonte 51, Sardegna 44, Tejo 42, Sicilia 33, "Danube Plain" 27, Wien
  25, Toscana 21, Massif Central 20 …), re-translated on Anthropic batch in
  two passes. Result: **418 → 120 bullets (75 pairs)**; the second pass
  changed nothing, because the model's output is deterministic for an
  unchanged prompt — the residue is its settled judgement: Wien / Mosel /
  Tejo / Piemonte kept as region names in ES, NL and FR ("la región
  vitivinícola de Wien"), named ranges kept as names (Appennino Dauno, Alpi
  Apuane), Kärnten as the g.U. English "Mosel" and "Tejo" were removed from
  the table — English wine writing uses them for the regions. Vogezen / Rijn
  / Apennijnen / Tuscany / Piedmont / Sicily / Sardinia are now in place.
  Clearing the last 120 needs either a stronger, example-heavy nudge for
  those exact forms or a curated deterministic replacement for the non-GI
  ones (Bayern → Bavaria, Appennino → Apennines) — left open; the audit
  stays at 0 strict findings.
- **Re-runs (all `--batch --provider anthropic`)**: 02d `--refresh` on 262
  records (51 Alsace, 3 re-sourced, 169 arrow, 9 meta, 5 hedge, 25 stale;
  17 country batches, 1,016 requests, all concurrent) — every record
  re-extracted, 0 arrows / 0 meta left in them, Rangen volcanic /
  Gloeckelberg granitic / Kitterlé sandstone, no cru mentions Zotzenberg;
  then dedupe (26 more) and boilerplate (92 facts: GR 83, IT 6, DE 3);
  then 02e `--refresh --only` over the union of flagged and re-extracted
  slugs (797 slugs, 19 country batches). Gotcha met on the way: a stale
  `raw/.batch/02e-at.json` from May resumed an expired batch — delete
  old sidecars before a `--batch` run.

## Acceptance (2026-09-11, after all of the above)

200-bullet re-sample (seed 2027, ≥ 5 per country, rest proportional;
`tmp/terroir-facts-review/sample200*.{json,txt}`), tagged with the same
rubric, against the 1,000-bullet baseline:

| category | baseline (n = 1,000) | after (n = 200) | target |
|---|---|---|---|
| content error / over-claim / mistranslation | 3.4 % | 0.5 % (one inverted "<" sign carried from the source bullet) | < 1.5 % ✓ |
| untranslated common noun or non-Latin script | 16.1 % | 2.0 % (andezity/ryolity, climă temperat-continentală, kontinentális klíma, Kalk/Schiefer) | < 2 % ✓ |
| near-duplicate within record | 10.1 % | 0 % | < 2 % ✓ |
| provenance mislabelled as wiki | 5.4 % | 0 % | ≈ 0 ✓ |
| style (arrow / colour code / abbreviation / meta) | 4.3 % | 0 % | < 1 % ✓ |
| "Label:" prefix (not in the baseline definition; report-only in the audit) | — | 4.5 % | — |
| no information | 3.4 % | 3.5 % (residual: quotes under the 60-char W6 floor, phrasing variants outside the pattern gate) | — |
| no terminal punctuation | 8.1 % | 0 % | — |
| fully clean | 58.1 % | 94 % (89.5 % counting label prefixes) | — |

Corpus-wide, the extended audit (`audit_terroir_facts.py --strict`,
`tmp/terroir-facts-review/audit-after.json`; the "before" is `audit-w8.json`):

| check | before | after |
|---|---:|---:|
| non-Latin script in the four translation locales | 3,167 | 0 (45 after the batch re-run; 38 pairs re-translated → 21 residual glosses / homoglyphs, then Latinised deterministically by the normaliser) |
| colour codes / missing terminal period (source + translations) | 0 / 0 (normaliser) | 0 / 0 |
| arrows (source / translated) | 216 / 603 | 0 / 2 |
| meta text (source / translated) | 14 / 48 | 0 / 10 |
| intra-record duplicate pairs | 27 | 0 |
| FR name guard / no own chapter | 0 / 0 | 0 / 0 |
| cahier-grounded quote outside the own Alsace chapter | 198 | 0 (44 Wikipedia-grounded paraphrases were being counted; check narrowed) |
| eroded bullets / cahier drift / wiki drift | 198 / 57 / 22 | 1 (Collioure) / 0 / 0 |
| facts (source) | 11,316 | 11,260 |
| `--strict` exit | 1 (3,392 strict findings) | **0** (`audit-final.json`) |

~~Still open: **W7** (sub-section per fact), the "Label:" lead prefixes, and
the residual no-information bullets whose quote is shorter than the W6 floor.~~
**Closed 2026-09-13** by the follow-up programme in
[review-terroir-facts-2026-09-12.md](review-terroir-facts-2026-09-12.md)
("Implemented" / "Results"): W7 is the claim-support gate's `subsection`
verdict (`scripts/02d_verify_terroir_facts.py`), the label prefixes went
with the re-extraction of the whole pre-style-block corpus (1,365 records)
under the 120–220-character rule, and the tautological / no-information
bullets are the gate's `drop` verdict.

## Recommended order

1. **W2a** (slicer) and **W3/W4 post-pass scripts** — code only, no LLM cost,
   fix the only outright-wrong content.
2. **W2b** curator re-source (three PDFs) — needs a human on the BO Agri UI.
3. **W5** normaliser (deterministic) + **W8** audit — gives the acceptance
   checks before any re-run.
4. **W1** prompt split + **W5/W6** prompt rules — then the targeted LLM
   re-runs (see "Re-run plan").
5. **W7** last; lowest impact.

Follow the memory rule "only fetch what's missing": never re-run 02d/02e
unfiltered across the corpus; every re-run below is scoped to the records a
detector script names.

---

## W1 — Split the 02e "preserve verbatim" lists

**Files.** `scripts/02e_translate_terroir_facts.py` (`build_system_prompt`, the
FR/ES base — line ~68) and all 20 country scripts
`scripts/<cc>/02e_translate_terroir_facts.py` (at, be, bg, ch, cy, cz, de, es,
gb, gr, hr, hu, it, lu, mt, nl, pt, ro, si, sk). Each has one long
`- Preserve <Language> proper nouns verbatim: …` line (bg:42, gr:42–43, hu:42,
hr:42, it:51, es:47, …). The target-locale glossary lives in
`scripts/_lib/translation_glossary.py` (`_EN_GLOSSARY`, `_NL_GLOSSARY`).

**Change.** Split every list into two buckets and rewrite the rule text:

- *Keep verbatim* (proper nouns and registered terms): appellation, region,
  commune and vineyard-site **names**; grape **names** (transliterated when the
  source script is not Latin); **named** formations and named winds (Marnes à
  exogyra virgula, Flysch di Cormons, llicorella, albariza, tuffeau,
  Muschelkalk, Rotliegend, Mistral, Bora, Meltemi); registered traditional
  terms and Prädikat tiers (Aszú, Szamorodni, Vinsanto, Nychteri, tokajský
  výber, Trockenbeerenauslese, Vendanges Tardives, Sélection de Grains Nobles).
- *Translate* (common nouns — this is what currently leaks): generic soil and
  rock words (IT argille / calcare / marne / arenaria / scisti / calcareniti /
  argilliti; HU lösz / mészkő / homokkő / agyagpala / barna erdőtalaj /
  csernozjom / vulkáni talaj; BG льос / чернозем / канелена горска почва /
  смолница; HR-SI vapnenac / crvenica / fliš / apnenec / ilovica / laporovec /
  lapor; PT xisto; DE Lehm / Quarzit / Gneis / Granit / Urgestein /
  Vulkangestein / Steillage / Lagenwein; NL leem / klei / zandleem / mergel;
  LU-FR gypse / marnes keupériennes / calcaire conchylien); climate phrases
  (умереноконтинентален климат, μεσογειακό κλίμα, ηπειρωτικό κλίμα,
  kontinentalna klima, kontinentální podnebí, pannonisches Klima); generic
  harvest and wine-law categories (kasna berba, desertno vino, predikatno vino,
  pozna trgatev, ledeno vino, suhi jagodni izbor, pozdní sběr, slámové víno,
  αφρώδεις οίνοι, λιαστοί οίνοι, pezsgő, gyöngyözőbor, vendemmia, fruttaia);
  site words (lege, dűlő, viniční trať, podgorie, borvidék, vinorodni okoliš,
  ribera, páramo, gromače, emparrado); scheme abbreviations (ΠΓΕ / ΠΟΠ / ЗНП /
  ЗГУ / OEM / OFJ / CHOP / CHZO / ZOI → PGI / PDO).
- Allow a **one-time gloss** of a genuinely technical local term the way
  Drenthe's bullet already does: "boulder clay (keileem)", "dry-stone walls
  (prizidi)". Never the reverse ("Continental (ηπειρωτικό κλίμα)").
- Add a **hard script rule** for GR/BG/CY: "The output must be entirely in
  Latin script. Transliterate Greek and Cyrillic proper nouns using the
  EU-official Latin form (Ξινόμαυρο → Xinomavro, Στара планина → Stara
  Planina, Гъмза → Gamza)." The eAmbrosia `transcriptions[0]` field and the
  grape lexicon's Latin slugs are the reference spellings.
- Extend `_EN_GLOSSARY` with the calques the sample caught: "minerality NOT
  mineralité"; "wine-grape varieties NOT must varieties" (CZ moštové odrůdy);
  "style / version NOT typology" (IT tipologia); "actual alcohol NOT developed
  alcohol" (IT gradi svolti); "carbonate / calcareous soils NOT carbonated
  soils" (FR carbonatés); "vineyard sites NOT lege / dűlők"; "para-barros is a
  Portuguese soil class, never invent proto-barros"; Beaujolais "grillage /
  pigeage / remontage" = submerged-cap / punch-down / pump-over.
- Optional but recommended: move the two-bucket rule into a shared helper
  (`scripts/_lib/terroir_prompts.py`, `preserve_rules(source_lang)`) so 21
  scripts stop drifting. Move-only; keep each country's proper-noun roster.

**Cache invalidation.** 02e caches key on `source_facts_sha`; a prompt change
does *not* trigger re-translation. Country 02e scripts have `--refresh` but no
`--only` (the 02d scripts have `--only`; FR 02d has `--slug`). Add `--only SLUG`
(repeatable) to every 02e script (mirror the 02d flag), then re-translate only
the slugs a detector names. Detector: scan `raw/translations/terroir-facts/
<lang>/*.json` for non-Latin script (`[Ѐ-ӿͰ-Ͽ]`) and for the leak regex below;
check **all four target locales**, not only EN. Run with `--batch --provider
anthropic --refresh --only …` (the batch path loads `.env`).

```python
LEAK = re.compile(r"(?i)\b(lösz|mészkő|homokkő|argille|argilliti|arenari[ae]|calcar[ei]|marn[ae]|scisti|"
                  r"podgori\w*|mineralité|kasna berba|desertn\w+ vin\w*|predikatn\w+|pozna trgatev|"
                  r"ledeno vino|okoliš|vapnen\w+|crvenic\w+|fliš|apnen\w+|xisto\w*|leem|zandleem|mergel|"
                  r"viničn\w+|dűlő\w*|lege\b|Steillage\w*|Lagenwein\w*|Urgestein|typology|must varieties)\b")
```

**Acceptance.** Non-Latin characters in Latin-target caches = 0 outside quoted
local words that carry a gloss; leak-regex hits < 20 corpus-wide; a fresh
50-bullet GR/BG/HU/CZ/HR sample reads as English.

## W2 — Wrong chapter / wrong cahier

### W2a Shared-cahier slicer (Alsace grand cru, 51 records)

`scripts/02d_extract_terroir_facts.py`: `_spans_by_top` (line ~183) builds
`out[m.group(1)] = (start, end)` over every `1°- / 2°- / 3°-` anchor in the
lien, so with 51 cru chapters in one 339 KB `lien_au_terroir` the **last**
chapter (Zotzenberg, alphabetically last) wins for every cru. Only the
`produit` slice (generic to all crus) is currently correct.

Fix in `slice_section_x`: when the lien contains more than one `1°` anchor,
first locate the record's own chapter — the heading `« Alsace grand cru
<Cru> »` (compare accent-folded; the record's `name` is the cru name) — and
restrict the lien to the window from that heading to the next `« Alsace grand
cru` heading before slicing. If no own chapter is found, log loudly and skip the
record rather than fall back. Add a unit test on a synthetic three-chapter lien.

Then re-run for the 51 slugs only: `02d … --slug alsace-grand-cru-… --refresh`
(FR 02d uses `--slug`), which changes `source_facts_sha` and re-queues 02e for
those records automatically. Expect the new facts to describe each cru's own
geology (Gloeckelberg is granitic sand, Rangen volcanic, Kitterlé sandstone,
etc. — the chapter texts say so).

The longer-term home for this is stage 02 (CLAUDE.md notes sub-sections of a
shared cahier are not parsed in v1); the 02d fix is sufficient for the terroir
layer.

### W2b Wrong PDF bound to the record (3 parents) — curator + guard

| id | slug | lien actually belongs to | evidence |
|---:|---|---|---|
| 290 | `pierrevert` | Saint-Pourçain | lien mentions Saint-Pourçain 6×, Pierrevert 0×; manifest PDF `e2a5794e…` |
| 187 | `l-etoile` | Bourgogne Passe-tout-grains (Mâcon / Jura regional text) | lien byte-identical to `bourgogne-passe-tout-grains`; manifest PDF `49acff22…`, shared with Grands-Echezeaux |
| 184 | `grands-echezeaux` | same as above | same PDF `49acff22…` |

Route: a curator finds the right cahier on the BO Agri search UI and pins it in
`raw/inao/cahiers/manual_overrides.json` (mechanism in CLAUDE.md, "Manual
override mechanism"), then stage 01 → `02 --only` → `02d --slug` → 02e → 04.
The corresponding entry is in `CURATOR_TODO.md` (France).

Guard (stage 02 or `audit_terroir_facts.py`): for every FR parent with a lien
≥ 800 chars, tokenise the appellation name (drop stop words such as côtes, de,
saint, grand, cru, village, coteaux) and require at least one token to occur in
the lien; otherwise emit a warning and, in `--strict`, fail. The check that
found these three is in `tmp/terroir-facts-review/` (see Evidence).

## W3 — Dedupe within a record

Two layers:

- **Post-pass now** (no LLM cost): `scripts/dedupe_terroir_facts.py` rewriting
  `raw/terroir-facts/*.json` in place. Drop a fact when (a) its normalised
  `cahier_quote` or `wiki_quote` (≥ 30 chars) equals an earlier fact's, or
  (b) `rapidfuzz.fuzz.token_set_ratio(bullet_a, bullet_b) ≥ 85`. Keep the
  earlier fact unless the later one has provenance `both` or a longer quote.
  Rewriting changes `source_facts_sha`, so 02e re-translates the ~340 touched
  records automatically (`--batch`).
- **In 02d** for future runs: the same routine after the four sub-section calls
  (FR: the loop around line ~436 that does `facts.append(classified)`; every
  country 02d has the same `f["subsection"] = sub["key"]` pattern, e.g.
  `scripts/it/02d_extract_terroir_facts.py:362`). Put it in
  `scripts/_lib/terroir_dedupe.py` and call it from all 21 scripts. Add one
  prompt line: "Do not restate a fact already covered by another sub-section."

Sample cases to test against: `skalicky-rubin` facts 3/10,
`moselle-luxembourgeoise` facts 1/2/3/6/7/8/10 (42 km, 129–142 m and the two
cantons appear three times each), `vulkanland-steiermark` 5/7, `sobes` 3/7,
`hrvatsko-podunavlje` 3/6, `colline-lucchesi` 2/7, `halkidiki` 3/7.

## W4 — Coverage check with ellipses

`fuzzy_coverage` (FR 02d line ~171; the same function is duplicated in the
country 02d scripts and in `scripts/audit_terroir_facts.py`) uses one
longest-contiguous match. The model legitimately joins two spans with "[…]",
"[...]" or "…", which caps coverage well below 0.6 and flips provenance to
`wiki` (626 cases) or drops the fact.

Fix: split the quote on `\[…\]|\[\.\.\.\]|…|\.\.\.`, compute coverage per span,
and take the minimum (spans shorter than ~15 chars ignored). Move the function
to `scripts/_lib/terroir_coverage.py` and import it everywhere. Then a post-pass
(`audit_terroir_facts.py --rewrite-provenance`, or a small script) recomputes
`cahier_coverage` / `wiki_coverage` / `provenance` on the existing caches
without an LLM call. Expect roughly 600 facts to move from `wiki` to `cahier`
or `both`; the panel attribution ("via Wikipedia · CC BY-SA 4.0") changes
accordingly at the next stage-04 build.

## W5 — Style rules and a deterministic normaliser

**Prompt (02d `EXTRACT_SYSTEM`, FR line ~132, and the country equivalents):**

- Full sentences ending with a period; no "→"; no label prefixes ("Colour:",
  "Climate:", "Soils:").
- Grape names without INAO colour codes (N / B / G / Rs / Rg).
- Expand VT / SGN / TBA on first use.
- Never refer to "the document", "the cahier", "the disciplinare" or
  "Wikipedia" inside the bullet (two bullets leaked "confirmed by Wikipedia" /
  "according to the document").
- Keep the source's hedges: essentiellement, principalement, parfois, souvent,
  généralement, "repose sur". Do not strengthen to "exclusively", "100 %",
  "only", "always".
- Skip statements that would be true of any appellation.

**02e:** add "drop INAO colour-code suffixes" and "end every bullet with a
period" to the base rules.

**Normaliser (`scripts/_lib/terroir_normalize.py`, applied at stage-04 render
and available as a cache post-pass):** append a terminal period when missing;
strip ` (N|B|G|Rs|Rg)` after a token that resolves in the grape lexicon; expand
`VT` / `SGN` in FR/EN/ES/NL. Leave arrows and meta text to a targeted re-run:
the ~150 arrow bullets and the "exclusively / 100 %" bullets are re-extracted
with `--slug … --refresh` once the prompt rules are in.

## W6 — Boilerplate filter (conservative)

Detect a `cahier_quote` (normalised, ≥ 60 chars) shared by ≥ 3 records of the
same country **and** matching a tautology pattern (`uniqueness … attributed
to`, `directly linked to the character`, `no uniform description`, `defined by
their typicity`, `favourable soil and climatic conditions`). Drop such facts
unless they are the record's only fact. Do **not** filter on shared quotes
alone — several cahiers are legitimately shared (Anjou family, the Calabrian
IGT text, the RO caiete, the Alsace `produit` slice). Add the pattern list to
the 02d prompt as things to skip.

## W7 — Sub-section per fact (low priority)

Either ask the model to return `"subsection"` per fact and use it when it
disagrees with the slice, or add a keyword reclassifier in the post-pass
(yield / density / pruning / vinification / AOC dates → facteurs_humains; soil
/ climate / relief → facteurs_naturels; colour / aroma / palate → produit).
Sample cases: `haspengouwse-wijn` 4/10 (yield cap under naturels), `la-tache`
1/9, `moselle-luxembourgeoise` 6/10, `tarquinia` 5/5 (climate under humains),
`castelli-romani` 3/5, `vin-santo-del-chianti` 8/8.

**Deferred (Boris, 2026-09-11).** No re-extraction is needed: `subsection` is
a per-fact field in the source cache, copied by index into the four 02e
caches and not part of the translation hash. Preferred routes when picked
up: a keyword reclassifier over the EN rendering (one table, not 21) or a
classification-only LLM pass (one batch request per record, bullets
untouched) — either as a post-pass that rewrites `subsection` and syncs the
translation caches (`_lib/terroir_cache.py` pattern), then one stage-04
rebuild. Move a fact only on a clear contradiction and never into
`interactions`.

## W8 — Audit extension

`scripts/audit_terroir_facts.py` only knows fr / es / gb
(`EXTRACTED_BY_COUNTRY`, line ~45). Extend it to every country by reusing each
country 02d's lien resolver (`_resolve_lien_and_source`, which already handles
the national-spec sidecars), and add checks, each with a count and `--strict`
failure:

- non-Latin script in Latin-target translation caches;
- INAO colour codes, arrows, label prefixes, missing terminal period;
- intra-record identical quotes and bullet similarity ≥ 85;
- cross-record identical quotes (report only, with the whitelist of shared
  cahiers);
- FR parent whose lien never names the appellation (W2b guard);
- shared-cahier records whose quotes are not found in their own chapter (W2a);
- provenance `wiki` with a non-empty `cahier_quote` after W4.

## Re-run plan and cost

1. Land W2a, W3 post-pass, W4 post-pass, W5 normaliser, W8 checks. Run the
   audit to get the "before" counts.
2. Curator supplies the three PDFs (W2b); run stage 01 → 02 `--only` for them.
3. Land W1 + W5/W6 prompt rules (+ `--only` on the 02e scripts).
4. LLM re-runs, all `--batch --provider anthropic`, all scoped:
   - 02d `--refresh`: the 51 Alsace slugs, the 3 re-sourced slugs, the ~150
     arrow records, the 14 "exclusively" records, the GR/AT boilerplate
     records — roughly 250 records.
   - 02e `--refresh --only …`: every record whose `source_facts_sha` changed
     (automatic) plus the W1 detector list in all four target locales — on the
     order of 2,000 record-locale pairs. Anthropic batch pricing makes this
     cheap; do not use Ollama with `--workers > 1` (memory rule).
5. `scripts/04_build_maps.py`, then the audit in `--strict`.
6. Re-sample 200 bullets (seed 2027) with the sampler below, tag with the same
   rubric, and compare against the baseline table. Target: untranslated < 2 %,
   duplicates < 2 %, content errors < 1.5 %, style < 1 %, provenance mislabel
   ≈ 0.

## Evidence (`tmp/terroir-facts-review/`, gitignored)

- `sample1000-review.md` — every flagged bullet of the 1,000 sample with EN,
  source bullet, quotes and tags. Rubric: ERR (content error / over-claim), MT
  (mistranslation), UNT (untranslated common noun), LOW, SUB, STY, DUP, META;
  automatic tags NONLATIN, ARROW, CODE, NOPUNCT, PROVMIS, DUPQ, ALSACE.
- `sample1000_tagged.json` — the same sample as data (`issues` per bullet).
- `tags.txt` — the raw manual tags by sample index.
- `sample.json` — the earlier 100-bullet sample.
- `numcheck.log`, `numcheck_notfound.json` — the corpus-wide beyond-quote
  number check.

Sampler (reproduces `sample1000.json`; seed 2026, ≥ 10 per country, rest
proportional):

```python
import json, glob, os, random, collections
rows = []
for p in sorted(glob.glob("raw/terroir-facts/*.json")):
    slug = os.path.basename(p)[:-5]
    if slug.startswith("manifest"): continue
    src = json.load(open(p)); c = src.get("country", "fr")
    enp = f"raw/translations/terroir-facts/en/{slug}.json"
    en = json.load(open(enp))["facts"] if os.path.exists(enp) else (src["facts"] if c in ("mt", "gb") else None)
    if en is None: continue
    for i, f in enumerate(src["facts"]):
        if i < len(en):
            rows.append(dict(slug=slug, country=c, i=i, en=en[i]["bullet"], src=f["bullet"],
                             cq=f.get("cahier_quote", ""), wq=f.get("wiki_quote", ""),
                             prov=f.get("provenance"), sub=f.get("subsection")))
random.seed(2026)
byc = collections.defaultdict(list)
for r in rows: byc[r["country"]].append(r)
sample = [r for c, l in byc.items() for r in random.sample(l, min(10, len(l)))]
rest = [r for r in rows if r not in sample]
sample += random.sample(rest, 1000 - len(sample)); random.shuffle(sample)
```

Corpus-wide detectors used in the review (rewrite as audit checks in W8):
non-Latin `re.compile(r"[Ѐ-ӿͰ-Ͽ]")` over EN bullets → 791 hits (GR 503 / 1,170,
BG 264 / 544); INAO code `[a-zé]\s(N|B|G|Rs|Rg)(?=[\s,;:.)]|$)` → 160 FR bullets;
arrows → 152; identical `cahier_quote` within a record → 435; `provenance ==
"wiki" and cahier_quote` → 626; lien-never-names-appellation → 4 FR parents
(the 3 above plus `saone-et-loire`, which is fine).
