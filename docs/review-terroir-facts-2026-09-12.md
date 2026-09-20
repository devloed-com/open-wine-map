# Terroir-fact quality review — full EN corpus (2026-09-12)

Follow-up to [plan-terroir-facts-quality.md](plan-terroir-facts-quality.md)
(W1–W6, W8 landed 2026-09-11; W7 open). That plan was built on a 1,000-bullet
sample; this review graded **every** English terroir fact — 11,260 bullets in
1,634 records across 21 countries — against the source-language bullet, the
grounding quotes and the exact regulator text stage 02d graded against
(`_lib/terroir_sources.py`), then adversarially verified every high-severity
finding plus a stratified sample of the rest. Evidence is under
`tmp/terroir-facts-review/full-review-2026-09-12/` (gitignored; see
"Evidence" at the end).

## TL;DR

| finding | scale | root cause | fix |
|---|---|---|---|
| Bullets that would **misinform a reader** (wrong entity, unsupported causal link, invented detail, dropped hedge, wrong number/direction) | ≈ 780 bullets, **6.9 %** (95 % range 5.6–8.5 %); 384 verified one by one, in 346 records | 3 of 4 originate in the **source-language extraction** (02d), not in translation; the pre-2026-09-11 prompt produced them at twice the rate of the current one | R1 broad 02d re-run + R2 claim-support gate |
| `interactions` sub-section asserts terroir → wine causation the source never makes | 73 of the 106 verified "unsupported causal link" bullets; 29 % of all interactions bullets flagged as duplicates, 33 % as content errors | the 4th sub-section call re-reads the whole lien and is asked for a causal link; it manufactures one when the source only lists factors | R2 (gate) + R3 (redesign the call) |
| Records still bound to the **wrong source text** | Bourgogne Passe-tout-grains (Beaujolais cahier); ≥ 15 IT records whose MASAF sidecar carries a sottozona annex (Abruzzo, Montepulciano d'Abruzzo, Trentino, Romagna, Terre di Cosenza, Colli Tortonesi, Riviera Ligure di Ponente, Friuli Colli Orientali, …); 4 GR specs with sections copied from another PGI; 2 FR records sharing one PDF; 2 wrong Wikipedia bindings | name guard defeated by common tokens; MASAF `extract_articles` keeps the *last* occurrence of each article number; ΥΠΑΑΤ files literally paste sections across PGIs | R4 (data fixes + guards) |
| Telegraphic "Label:" bullets | 1,291 EN bullets (11 %) in 730 records — **729 of them extracted before the style block** | never re-extracted; every country prompt still caps bullets at 140 characters, which forces the compression that produces both labels and errors ("sin. Tanaro" → "syn. Tanaro") | R1 (re-run) + R5 (drop the char cap) |
| Translation-stage defects | 225 of the 590 non-refuted verified findings involve 02e: calques (Lehm → clay, generoso → generous, tirage → disgorgement, Burgundian *climat* → climate), a numeric slip (250–290 m → 250–490 m), name back-formation ("Caiata" from *caiatino*), hedges upgraded ("weakly" → "moderately") | no back-check of EN against SRC; glossary and exonym gaps (Bayern, Rodopi/Rhodopes) | R6 |
| Untranslated / source-form words | ≈ 510 bullets (4.5 %, precision-corrected) | residue of W1; German compounds and BG/HU geography dominate | R6 |
| Misfiled sub-section (W7) | ≈ 610 bullets (5.4 %); reviewers supplied `suggested_subsection` for 690 | slice ≠ per-fact judgement | R7 |
| Intra-record restatement after the W3 dedupe | ≈ 540 bullets (4.8 %); 45 % of `interactions` bullets in two-lens batches | dedupe is lexical; the restatements are paraphrases with a causal wrapper | R3 |

What is **not** broken: numbers. Of 3,875 bullets carrying a number, 42 had a
number found in neither quote nor source after normalisation; all 42 were
refuted by the verifier (decade / century idioms, "ultra-cinquantennale",
"anno mille"). Numeric hallucination stays at ≈ 0. Translation-only numeric
errors exist but are rare (La Grande Rue 490 m, Sithonia 1960s).

## Method

1. **Sheets.** One sheet per ~10 records (192 sheets, later re-cut to 151
   single-Read sheets): per fact EN / SRC / cahier quote / wiki quote /
   sub-section / provenance, plus the record's full source text and the
   per-sub-section Wikipedia hints. Rubric in `REVIEW_GUIDE.md` (14 tags:
   ERR HALL MT UNT GRAM STY LOW LEN DUP SUB SIB NAME PROV MISSING).
2. **Review.** 41 sheets by two independent lenses (fidelity, language);
   the remaining 151 by one combined lens after the quota made two lenses
   unaffordable. Hard-tag rates are stable across the two methods (31 % vs
   33 % of facts); soft-tag rates are not (GRAM 32 % vs 8 %), so every rate
   below is either verified or precision-corrected.
3. **Verification.** Every one of the 440 high-severity findings, a
   stratified sample of 215 of the 3,238 other hard-tag findings, and the 42
   number residuals were re-judged by an adversarial verifier holding the
   record's full source (573 record-level agents, 703 verdicts). A second
   judge re-graded 278 soft-tag findings for precision.
4. **Classification.** Each of the 384 verified-misleading bullets was
   assigned a failure mode.

Cost note for the next run: a default subagent carries a 176 k-token base
context (the 300 KB project `CLAUDE.md`); the Explore agent type carries
14 k and produced equivalent findings (28/31 and 30/32 overlap on the same
sheets). The whole verified review ran on ≈ 40 M subagent tokens once
switched.

## Headline numbers

| measure | value | basis |
|---|---|---|
| facts reviewed | 11,260 in 1,634 records (100 %) | — |
| facts with any reviewer flag | 6,805 (60 %) | raw; method-sensitive |
| facts with a hard tag (ERR / HALL / MT / SIB / NAME / PROV) | 3,678 (33 %) | raw |
| high-severity findings | 440 | 416 confirmed or partially confirmed on verification (95 %), **355 reader-misleading (81 %)** |
| other hard-tag findings | 3,238 | sample of 215: 78 % confirmed or partial, **13 % reader-misleading** (9–18 %) |
| **misleading bullets, corpus-wide** | **≈ 777 (6.9 %)**, range 634–959 | 355 + 13 % × 3,238 |
| bullets with a verified content-level defect of any weight | ≈ 2,950 (26 %) | 95 % × 440 + 78 % × 3,238; most are "partially confirmed": a dropped qualifier, a narrowed attribution |
| stage of origin (590 non-refuted verdicts) | extraction 365 · translation 127 · both 98 | 79 % involve 02d |
| UNT (precision 94 %) | ≈ 510 (4.5 %) | 543 raw |
| STY (82 %) — "Label:" prefixes, mixed units, stray quotes | ≈ 1,360 (12 %) | 1,646 raw; 1,291 are label prefixes |
| SUB (88 %) | ≈ 610 (5.4 %) | 690 raw |
| DUP (67 %) | ≈ 540 (4.8 %) | 815 raw |
| LEN (40 %) | ≈ 410 (3.6 %) | 1,028 raw |
| GRAM (26 %) | ≈ 390 (3.5 %) | 1,484 raw; the language lens tagged label fragments as GRAM |
| LOW (77 %) | ≈ 300 (2.7 %) | 393 raw |
| records where the source prominently describes something no bullet captures (MISSING) | 1,089 of 1,634 | reviewer notes; not verified |

The 2026-09-11 acceptance sample reported 0.5 % content errors and 94 %
clean. It was right about the categories it measured (arrows, codes,
punctuation, non-Latin script, duplicates are indeed ≈ 0) and wrong about
content: that sample was graded bullet-by-bullet against the quotes, while
the misleading bullets found here mostly need the *whole source* to be seen
— the quote is genuine, the claim built on it is not.

## Failure modes (384 verified-misleading bullets)

| mode | n | share | stage | typical case |
|---|---:|---:|---|---|
| unsupported causal link | 106 | 28 % | extraction 94 | *Taurasi*: "volcanic pyroclastic material … imparts great minerality, structure and an austere character" — the source only records the material's presence |
| mistranslation | 55 | 14 % | translation 40 · both 15 | *Rueda*: "Generous wines" for *vinos generosos* (fortified); *Crémant d'Alsace*: "from the date of disgorgement" for *à compter du tirage* |
| wrong entity | 55 | 14 % | extraction 44 | *Campo de Cartagena*: the Mar Menor "acts as a climatic buffer" — the source credits the open Mediterranean; *Tacoronte-Acentejo*: "volcanic origin distinct from the rest of the Canaries" — the source says the origin is common, the evolution differs |
| invented detail | 54 | 14 % | extraction 37 | *Grignolino d'Asti*: "pale colour typical of thin-skinned red varieties" — nowhere in the sources |
| wrong number / unit | 21 | 5 % | mixed | *La Grande Rue* 250–**490** m (source 290; translation-only); *Barolo* "the Langhe began forming almost 70 million years ago" (the Cenozoic did) |
| wrong direction / sign | 21 | 5 % | mixed | *Volnay*: "shelter afforded by the Morvan to the east" (the Côte lies east of the Morvan); *Nagy-Somló*: varieties "withdrawn" that the source says were brought back |
| wrong grape / name | 17 | 4 % | translation 15 | *Balaton*: Hungarian *Pintes* rendered "Pinot"; *Terre del Volturno*: "the Caiata area" back-formed from *caiatino* (Caiazzo) |
| hedge dropped | 17 | 4 % | extraction 14 | *Canelli*: "pruning exclusively to Guyot" (source: *tipicamente*); *Boliarovo*: "moderately expressed" for *слабо изразено* (weakly) |
| sibling / sub-zone confusion | 11 | 3 % | extraction | *Pouilly-sur-Loire*: the soil → style links belong to Pouilly-Fumé; *Salice Salentino*: the Basso Salento contrast presented as the DOC's soils |
| narrowed attribution | 10 | 3 % | extraction | *Vratsa*: soils "contribute to the softness and long finish" — the source credits climate + relief + soils + human factor en bloc |
| wrong source text | 5 | 1 % | extraction | see below; 5 bullets in the verified set, many more in the affected records |
| added qualifier | 5 | 1 % | extraction | *Dolinata na Struma*: "traditional local varieties" on a bare enumeration |
| other | 7 | 2 % | | |

By sub-section: `interactions` carries 73 of the 106 unsupported causal
links although it holds only 10 % of the bullets; `facteurs_naturels`
carries the wrong-entity and wrong-direction cases; `facteurs_humains` the
hedge drops and wrong names. By country the profile is uniform except that
Italy contributes 63 of the 106 causal-link cases (the IT prompt re-reads
the whole disciplinare for every sub-section) and Spain / Hungary lean to
mistranslation.

### Prompt vintage matters more than country

| records extracted | records | facts | high-severity | verified misleading | label prefix | DUP flag |
|---|---:|---:|---:|---:|---:|---:|
| before the 2026-09-11 style block | 1,365 | 9,090 | 4.4 % | 3.5 % | 14.2 % | 8.1 % |
| after (the scoped W-re-runs) | 269 | 2,170 | 2.0 % | 1.7 % | 0.0 % | 3.6 % |

The current prompt halves the misleading rate and removes the label
fragments. 83 % of the corpus has never been extracted under it.

## Systematic source defects (fix the data, not the prompt)

- **Bourgogne Passe-tout-grains** (`id_appellation` 144) — `raw/inao/cahier-extracted/bourgogne-passe-tout-grains.json`
  is bound to PDF `49acff22…` (BO Agri `e89b7ce3…`); the extracted lien is the
  **AOC Beaujolais** cahier (23 mentions of Beaujolais, 0 of Passe-tout-grains,
  0 of Bourgogne). All 6 terroir facts describe the Beaujolais; the map blob
  carries `styles: ["primeur"]` and no grapes for it. W2b re-bound L'Étoile
  and Grands-Echezeaux off this same PDF but left the record it was
  attributed to. The `name_guard` passes because "tout" and "grains" (≥ 4
  letters, not stop words) occur in any French cahier.
- **Hautes-Alpes / Haute-Vienne** — both manifest entries point at BO Agri
  `22caf075…` and PDF `1106c71b…`; the two extracted liens differ and each
  matches its record, so one record's `boagri_url` (and the public PDF link)
  is misattributed.
- **IT MASAF sidecars with sottozona annexes** — `scripts/_lib/it/masaf.py`
  `extract_articles` keeps the **last** occurrence of each article number
  (meant for TOC + body). In a consolidated disciplinare whose sottozona
  annexes restart at *Art. 1*, every article — summary, grapes, geo area,
  Art. 9 lien — comes from the last annex. 24 PDFs repeat *Art. 1* / *Art.
  9* (`masaf_multi_annex.json`); confirmed wrong on the map or in the
  terroir source: `montepulciano-d-abruzzo` (San Martino sulla Marrucina
  annex: 1 grape, single-commune area, annex lien), `abruzzo` (Colline
  Teramane annex), `trentino` (Valle di Cembra: 4 grapes), `romagna`
  (Verucchio summary), `terre-di-cosenza` (Verbicaro), `colli-tortonesi`
  (Terre di Libarna: 1 grape), `riviera-ligure-di-ponente` (Taggia),
  `friuli-colli-orientali` (Savorgnano), plus `colli-bolognesi`,
  `colli-orientali-del-friuli-picolit`, `langhe`, `portofino`,
  `sambuca-di-sicilia`, `veneto`, `bardolino`, `riviera-del-garda-classico`
  to check. Stubs take the whole sidecar; non-stubs are gap-filled from it.
  Fix: per article number keep the first occurrence with a non-trivial
  body (or the longest), and treat the annexes as the sottozona records'
  own text (the Alsace W2a pattern).
- **GR ΥΠΑΑΤ specs pasted across PGIs** — `fthiotida` (geographic section
  names ΠΓΕ Παρνασσός and its municipalities), `peloponnisos` (describes
  Αχαΐα / Πλαγιές Αιγιαλείας / Αρκαδία), `retsina-evias` (human-factors
  section is Retsina Attikis), `ipiros` (sparkling section from Ioannina).
  A source defect at the regulator, but the pipeline should refuse to
  ground on it: a foreign-appellation guard (see R4).
- **Wrong Wikipedia binding** — `tirol` → de.wikipedia *Toro
  (Weinbaugebiet)* (the Spanish DO); `montecastelli` → the village article
  (its one wiki-only bullet describes the village hill). Pin both `missing`
  in `raw/wikipedia/aoc_overrides.json`.
- **Šobes** — fact #1 (Mikulov bioregion, Pavlov Hills limestone) is the
  Mikulovská podoblast 50 km away; Šobes sits on Bohemian Massif
  crystalline rock — a consequence of grounding every CZ record on the
  region-wide CHZO text with the podoblast article as hint.
- **Montana (BG)** — the IAVV spec has the Danube "to the south" and Stara
  Planina "to the north"; the bullet silently corrects it. Curator note.
- **Collioure** — no source text resolves today and the record carries one
  bullet (a 2009 planting grandfather clause). Already in CURATOR_TODO.

## Country profile

Hard-flag share is 24–37 % everywhere (SK 11 %); the verified column is
the count of high-severity findings confirmed as misleading, all verified.

| cc | records | facts | high-severity | verified misleading | UNT | label prefix | wiki-only provenance |
|---|---:|---:|---:|---:|---:|---:|---:|
| fr | 460 | 3,238 | 95 (2.9 %) | 76 | 107 | 385 | 411 |
| it | 519 | 3,045 | 181 (5.9 %) | 139 | 159 | 337 | 296 |
| es | 142 | 1,070 | 27 (2.5 %) | 22 | 58 | 107 | 87 |
| gr | 147 | 1,032 | 35 (3.4 %) | 28 | 9 | 73 | 2 |
| bg | 54 | 456 | 26 (5.7 %) | 22 | 30 | 72 | 0 |
| hu | 41 | 395 | 13 (3.3 %) | 13 | 26 | 47 | 5 |
| ro | 46 | 366 | 12 (3.3 %) | 12 | 20 | 51 | 0 |
| pt | 44 | 345 | 7 (2.0 %) | 6 | 11 | 34 | 12 |
| de | 39 | 288 | 8 (2.8 %) | 6 | 33 | 39 | 9 |
| hr | 18 | 196 | 7 (3.6 %) | 6 | 12 | 27 | 4 |
| at | 29 | 194 | 6 (3.1 %) | 5 | 21 | 21 | 6 |
| nl | 21 | 161 | 2 (1.2 %) | 1 | 28 | 38 | 5 |
| si | 17 | 123 | 3 (2.4 %) | 3 | 2 | 15 | 5 |
| sk | 10 | 85 | 3 (3.5 %) | 3 | 12 | 15 | 1 |
| cz | 13 | 72 | 3 (4.2 %) | 3 | 4 | 22 | 12 |
| cy | 11 | 71 | 3 (4.2 %) | 2 | 1 | 5 | 0 |
| be | 10 | 56 | 1 | 1 | 7 | 2 | 2 |
| gb | 6 | 46 | 5 | 4 | 0 | 1 | 2 |
| ch / lu / mt | 7 | 21 | 3 | 3 | 3 | 0 | 15 |

Italy's rate is the corpus's worst for a structural reason (whole-document
re-reads per sub-section, 140-character cap, annex mis-slicing); Bulgaria's
comes from the telegraphic IAVV extractions (five of eight bullets in
Vratsa, Lozitsa and Pazardzhik are verbless fragments) and the specs' habit
of crediting all factors en bloc, which the extraction then narrows.

## Recommended improvements, ranked by verified impact

**R1 — Re-extract the pre-style-block corpus (02d `--refresh`, batch).**
1,365 records (83 %) predate the current prompt; the post-block cohort has
half the misleading rate, no label fragments and half the duplicates.
Scope first the union of: the 730 label-prefix records, the 346 records
with a verified misleading bullet (`rerun-slugs*.txt`), and the wrong-source
records after R4; then the rest per country as batch budget allows. A full
02d re-run of the corpus is one Anthropic batch per country (the plan's
262-record re-run cost a few dollars); 02e re-translates automatically on
`source_facts_sha` change. This is the single largest lever and needs no
new code.

**R2 — Add a claim-support gate after extraction (new `02d-verify` step,
batch, one request per bullet).** The coverage test only checks that the
*quote* exists in the source; it never checks that the *bullet's claim* is
what the quote says. Every failure mode above except mistranslation passes
the coverage test. A verifier prompt of the shape used here ("does the
source support each assertion of this bullet; which words go beyond it;
rewrite or drop") confirmed 95 % of the reviewer's high-severity flags and
refuted the number residuals, so it is precise enough to gate on: drop a
bullet whose main claim is unsupported, rewrite one whose qualifier or
causal wrapper is. Run it in 02d after dedupe and before the cache write;
record `support: {verdict, note}` per fact so the audit can count it.

**R3 — Redesign the `interactions` call.** It produces 10 % of the bullets
and 69 % of the unsupported causal links, and 45 % of its output restates
the naturels / produit bullets. Options, in order of preference: (a) fold
it into the other three calls — ask each sub-section call to mark a bullet
`causal: true` only when the source sentence itself contains a causal
connective, and cap `interactions` at what those yield; (b) keep the call
but require the quote to contain the causal verb and reject otherwise (the
R2 gate does this); (c) for non-FR countries, slice the lien into
sub-section windows as FR does instead of re-reading the whole text four
times (FR has 0.8 % DUP flags, IT 8.5 %).

**R4 — Fix the source bindings and harden the guards.**
- Re-bind `bourgogne-passe-tout-grains` (register `prefer_cahier` pin or
  BO Agri lookup), resolve the Hautes-Alpes / Haute-Vienne shared PDF, pin
  `tirol` and `montecastelli` Wikipedia to `missing`.
- `name_guard`: require the *whole* folded name minus stop words (or its
  longest token ≥ 6 letters) rather than any ≥ 4-letter token; extend it to
  every country through `terroir_sources.py`, and add a **foreign-name
  guard**: a source text that names another appellation of the same
  country ≥ 3 times and its own 0 times is refused (catches the GR pastes,
  the MASAF annexes, Šobes).
- `masaf.extract_articles`: choose the occurrence with the longest body per
  article number, then emit the annexes as per-sottozona chapters (the
  Alsace `terroir_chapters.py` pattern) so the synthesized sottozona records
  get their own text instead of inheriting the parent's. Re-run 02f for the
  24 PDFs in `masaf_multi_annex.json`, then 02d for the affected slugs.

**R5 — Remove the 140-character cap and the telegraphic register from the
02d prompts.** All 21 prompts still say "≤ 140 caractères chacune" (or its
translation);
the audit already ignores its own soft cap (3,437 bullets over it). The cap
is what produced "Roero (sin. Tanaro)", "Klima: Ø 9,8 °C", the "Label:"
fragments and most hedge drops. Ask for one full sentence of up to ~220
characters; let the normaliser handle length outliers.

**R6 — Translation back-check and glossary.** 225 verified defects involve
02e. Add: (a) a cheap batch back-check that compares each EN bullet with
its SRC bullet and flags changed numbers, dropped or upgraded hedges, and
terms in a watch-list (climat, tirage, generoso, Lehm, Spritzigkeit,
capa, tipologia, Urgestein); (b) glossary entries for those terms; (c)
exonyms `Bayern → Bavaria`, `Родопи → Rhodopes`, and a policy for `Stara
Planina` (Balkan Mountains); (d) `Немски ризлинг → Riesling` (rendered
"Welschriesling" in ruse / shumen while the lexicon folds it to Riesling).

**R7 — W7 sub-section reclassifier.** 690 findings carry a
`suggested_subsection` (precision 88 %): use them as the validation set for
the keyword reclassifier the plan sketched, or run a classification-only
batch pass. Move only on a clear contradiction; the `interactions` label
should be *earned* by a causal sentence (R3), not assigned by slice.

**R8 — Semantic dedupe.** The lexical W3 rule leaves ≈ 540 restatements,
almost all "naturels fact + produit fact rewritten as a causal sentence".
After R3 most disappear; for the rest, an embedding or LLM pairwise pass
over each record's ≤ 15 bullets is cheap.

**R9 — Audit additions (`audit_terroir_facts.py`).** Make `label_prefix`
strict once R1 lands; add `multi_sentence` (100 bullets), `en_equals_src`
(2), `cross_record_identical_en` (26 bullets in 55 records — the Alsace
produit slice and the GR retsina cluster), the foreign-name guard, the
MASAF repeated-article detector, and a Wikipedia-binding sanity check
(article title must share a token with the record name). Keep the LLM
review harness (`workflows/` in the evidence directory) as a repeatable
`audit_terroir_facts_llm.py --sample N` for regression: with Explore-type
agents a 60-fact sheet costs ≈ 60 k tokens.

**R10 — Coverage (lower priority).** Reviewers noted a prominent
uncaptured element in 1,089 records (lakes as climate regulators, named
winds, headline hectares, defining practices). The 5 / 2 / 2 / 2 caps are
tight for long liens; consider scaling the naturels cap with lien length,
and asking for named entities first.

## Implemented after the review (2026-09-13): per-record feedback layer

The review's verified findings now live as constraints the next
extraction reads: `raw/terroir-facts-feedback/<slug>.json` (1,238 records:
384 do-not-claim entries in 346 records, 1,133 capture hints, 96
cautions), built by `scripts/build_terroir_feedback.py` from the evidence
directory and read by every 02d script through
`_lib/terroir_feedback.with_feedback` (live call and `--emit-todo`).
The prompt block lists each misleading claim as "do not assert … unless
the source states it explicitly" with the verifier's source-quoting
reason, the uncaptured elements as "if the text describes it, capture",
and the record cautions; it never carries the corrected English text, and
only `extraction` / `both` entries reach 02d. `audit_terroir_facts.py`
gained `feedback_recurrence` (report-only): known-bad claims still
matching a current bullet — the regression measure for R1. Baseline
before any re-run: **311 known-bad claims in 285 records** (the 384
misleading bullets minus the 73 translation-only ones, all still present
by construction); the number to watch is that count after the re-run.

## Implemented (2026-09-13): R1–R10 landed — see "Results" below

Everything runs as one rollback unit (`scripts/rerun_terroir_facts.py`,
run id `r1-2026-09-13`; undo with
`scripts/rollback_terroir_facts.py --run r1-2026-09-13`):

| rec. | what landed | where |
|---|---|---|
| backup | every 02d / gate / 02e / back-check / post-pass write snapshots the slug's source + 4 translation caches per run; per-slug entry files; rollback restores overwritten files and deletes created ones | `_lib/terroir_backup.py`, `_lib/terroir_cache.write_*_cache`, `rollback_terroir_facts.py`, wiring lint `tests/test_terroir_backup.py` |
| R1 | 918 records re-extracted (the union: 730 label-prefix + 346 verified-misleading + 23 wrong-source, all countries) under the new prompt, with the feedback sidecars in the prompt; the remaining 486 pre-block records are `tmp/terroir-facts-review/r1-scope-rest.json` | `rerun_terroir_facts.py --scope …` |
| R2 | claim-support gate, one request per record against the exact 02d source + hints + feedback; supported / rewrite (guarded) / drop; `support` per fact, `gate` block, feedback `history` | `02d_verify_terroir_facts.py`, `_lib/terroir_gate.py` |
| R3 | `interactions` earned: the shared prompt block admits a causal bullet only on an explicit connective in the source sentence; the gate rewrites or drops the rest | `_lib/terroir_prompts.STYLE_RULES`, gate prompt |
| R4 | Bourgogne Passe-tout-grains re-bound to its register cahier (`prefer_cahier` pin); Hautes-Alpes / Haute-Vienne verified as a genuine 20-cahier bundle (no change); `tirol` / `montecastelli` Wikipedia pinned `missing` (02b gained `--only`); MASAF `extract_article_runs` (annexes as chapters, 20 parents corrected, 77 sottozone detected vs 38); name guard on whole name / long-token stem, all countries (strict FR, report elsewhere); foreign-name guard; Wikipedia-binding check | `register_overrides.json`, `aoc_overrides.json`, `_lib/it/masaf.py`, `audit_terroir_facts.py` |
| R5 | the 140-character cap replaced in all 21 prompts by "one full sentence of ~120–220 characters, never a telegraphic fragment"; audit soft cap 240 | 21 × `02d_extract_terroir_facts.py` |
| R6 | translation back-check per (record, locale) with fixes under guards; glossary entries (climat, tirage, generoso, Lehm, Spritzigkeit, capa, Urgestein, Pintes, Немски ризлинг, caiatino); exonyms (Rodopi → Rhodopes, Bayern → Bavaria, Carpathians, Danube forms, Peloponnese, Crete, …) | `02e_verify_terroir_facts.py`, `_lib/terroir_backcheck.py`, `_lib/translation_glossary.py`, `_lib/exonyms.py` |
| R7 | the gate returns `subsection` on a clear contradiction only; `support.moved_from` records the move; translations re-synced by index | gate |
| R8 | the gate's `restates` + the lexical dedupe after rewrites | gate |
| R9 | audit: `multi_sentence`, `en_equals_src`, `cross_record_identical_en`, `foreign_name`, `wiki_binding`, `masaf_sidecar_stale`, `gate_pending`, `rewrite_rejected`, `name_guard_other`, `--strict-labels`; the LLM audit as a script with an independent grader (`claude-opus-5`) and a paired before / after | `audit_terroir_facts.py`, `audit_terroir_facts_llm.py` |
| R10 | named entities and figures first; up to two extra bullets on a long text | `STYLE_RULES` |

## Results (2026-09-13, runs `r1-2026-09-13` + `r1b-2026-09-13`)

Everything below is undoable: `scripts/rollback_terroir_facts.py --run
r1c-2026-09-13`, then `--run r1b-2026-09-13`, then `--run r1-2026-09-13`
(newest first; 2,153 + 28 snapshot entries).

**What ran.** 1,403 of 1,634 records re-extracted under the new prompt
(the 918-record union first, then the 486 remaining pre-block records;
the 231 untouched records are the post-block cohort of 2026-09-11 that
the review already measured as clean), every record through the gate,
every changed record re-translated, every translation cache
back-checked, then the deterministic post-passes (normalise, dedupe) and
the strict audit.

| step | scale | outcome |
|---|---:|---|
| 02d re-extraction | 1,403 records, 21 countries | 0 records without facts; median bullet 195 chars (was ≤ 140); **0 label-prefix bullets** (was 1,291) |
| gate, pass 1 (corpus) | 1,633 records, 11,202 bullets | 27 % rewritten, 1.5 % dropped, 498 moved sub-section, 283 rewrites refused by the guards |
| gate, re-gate of refused | 251 records | cap raised 320 → 420 chars; 52 still refused |
| gate, pass 2 (rest scope) | 492 records, 2,978 bullets | 28 % rewritten, 1.6 % dropped |
| 02e re-translation | ≈ 6,900 (record, locale) caches | 5,891 / 5,891 aligned at the end |
| back-check | 7,731 caches, 50,555 translated bullets | **4,483 fixed (8.9 %)**, 802 fixes refused by the guards |
| strict audit | 1,638 caches, 11,140 bullets, 39,997 translated | **0 strict findings**, with `label_prefix` promoted to strict |
| `feedback_recurrence` | 311 known-bad claims before | **6** after the runs (5 of them fuzzy matches on bullets the gate had already corrected; 1 real — the Rosé d'Anjou sibling text); 19 after merging the new audit findings below |

**Validation — paired, same records, same independent grader
(`claude-opus-5`, a different model from the sonnet-4-6 extractor / gate),
grading the EN bullets a reader sees against the full source
(`scripts/audit_terroir_facts_llm.py`).**

| sample | state | bullets | misleading | share (95 % CI) | records with ≥ 1 |
|---|---|---:|---:|---|---:|
| 120 records, whole corpus, seed 0 | before the programme (backup `r1`) | 804 | 111 | **13.8 %** (11.6–16.4) | 76 |
| same 120 | after `r1` (re-extraction + gate + 02e + back-check) | 793 | 25 | **3.2 %** (2.1–4.6) | 21 |
| 60 records, rest scope, seed 7 | after the gate, before their re-extraction (backup `r1b`) | 349 | 13 | 3.7 % (2.2–6.3) | 12 |
| same 60 | after `r1b` | 348 | 5 | **1.4 %** (0.6–3.3) | 5 |

Paired: 64 of 120 records improved, 6 worse, 50 unchanged (first sample);
10 / 3 / 47 (second). The six "worse" records are re-extracted records
whose new bullets carry a small residual defect (a dropped *plutôt*, a
soil subtype in a parenthesis the source lists elsewhere) — none is a
gate rewrite that went wrong. The independent grader is stricter than
the review's verifier (it put the pre-programme state at 13.8 %, the
review at 6.9 %), so the absolute target of < 1.5 % is met on the second
sample and missed on the first (3.2 %); relative to its own baseline the
programme removes **77 %** of the misleading bullets on the first sample
and 62 % of what the gate alone had left on the second. Residual failure
modes after: narrowed attribution 8, unsupported causal link 7, hedge 6,
wrong entity 6, invented detail 5 — the same family as before, at a
fifth of the rate; 16 of the 25 are extraction, 5 translation, 4 both.
The 30 residual bullets were merged into the feedback sidecars
(`llm-audit-2026-09-13-after-r1` / `-r1b`), so the next re-run of those
records reads them as constraints.

**Run `r1c` — the grounding filter.** Montepulciano d'Abruzzo came out
of `r1` with 1 fact: 8 verbatim quotes had been dropped because the
MASAF text carries pdftotext artefacts ("gradi- giorno") and one wrong
character halves a single-longest-contiguous-match coverage. The
coverage test in `_lib/terroir_coverage.py` is now also graded by
verbatim blocks (≥ 12 chars, summed; threshold unchanged at 0.6 —
scattered phrases and foreign text still score < 0.3). The 28 records
that had lost ≥ 4 facts to grounding were re-run through the chain (91 →
207 facts; Montepulciano 1 → 9, Montefalco 6 → 13) and every cache
re-graded (`recompute_terroir_provenance.py`): wiki-only provenance fell
from 830 to 394 bullets and `wiki_with_cahier_quote` from 446 to 5 — the
cahier quote *was* there; the old measure could not see past one
artefact. Final corpus: 1,638 records, **11,255 bullets**, strict audit
0 findings (labels strict).

**Experiment (2026-09-14, run `exp-sonnet5`, rolled back): Sonnet 5 as
extractor.** The 120-record sample was re-extracted with
`claude-sonnet-5` (thinking off, `OWM_BATCH_THINKING=disabled`), then
gated / translated / back-checked by the unchanged Sonnet 4.6 stages,
and graded paired by the Opus-5 verifier against its pre-experiment
state. Per bullet, reader-misleading extraction defects were the same —
1.8 % (15 / 812) on 4.6 vs 1.7 % (18 / 1,064) on Sonnet 5 — with
overlapping intervals; the gate rewrote 20 % of Sonnet 5's bullets vs
27 % of 4.6's, and Sonnet 5 produced 31 % more bullets per record (8.9
vs 6.8), every quote grounding (0 grounding drops vs 73). Translation-
origin defects rose with the volume (4 → 10). Conclusion: the extractor
model is not the lever for the misleading rate; Sonnet 5 buys coverage
and a third off the extraction price at equal per-bullet reliability. A
switch is a coverage / cost decision, not a quality one; the run was
rolled back so the corpus stays on one extractor.

**Configuration decided 2026-09-14** (Boris): Sonnet 5 as the extractor
(coverage + cost), Opus 5 with adaptive thinking as the gate; the code
defaults are set (`providers.STAGE_DEFAULTS`), the corpus is not yet
migrated. The hand-off with the remaining recommendations is
[handoff-terroir-facts-2026-09-14.md](handoff-terroir-facts-2026-09-14.md).

**Side effects worth knowing.** The MASAF annex fix corrected 20 IT
parents' sidecars (Trentino 4 → 28 grapes, Colli Tortonesi 1 → 24,
Langhe 1 → 14, Romagna 1 → 15) and the sottozona detector now finds 77
sottozone in 17 parents (was 38 in 10) — visible on the map after stage
04. The gate's `moved` verdicts (≈ 5 % of bullets) closed W7 without a
separate reclassifier. Cost: the whole programme ran as Anthropic
batches (≈ 12,000 extraction, 2,400 gate, 7,000 translation, 7,700
back-check, 360 opus-5 grading requests) in about two hours of
wall-clock.

**Still open.** `rewrite_rejected` 97 (an empty or over-long rewrite; the
original bullet stays, flagged), `wiki_binding` 23 and `foreign_name` 3
for a curator (see CURATOR_TODO "Cross-country"), `collioure` (no
source), and the 231 post-block records of 2026-09-11: gated like every
record, but not re-extracted (their prompt already carried the style
block); they are the cleanest cohort and can wait for the next scoped
run.

## Re-run scope

`tmp/terroir-facts-review/full-review-2026-09-12/`:

- `rerun-slugs.txt` — 346 records with a verified misleading bullet
  (`rerun-slugs-<cc>.txt` per country; IT 146 records, FR 81, GR 34, ES 26,
  BG 23, HU 16, RO 12, …).
- `confirmed-misleading.json` — the 384 bullets with mode, stage,
  verifier reason and a corrected English rendering (for spot-checking the
  re-run, not for hand-editing caches).
- `masaf_multi_annex.json` — the 24 MASAF PDFs to re-slice.
- `det_checks.json` → `rows.label_prefix` — the 1,291 label bullets / 730
  records.

Suggested order: R4 data fixes → R5 prompt edit + R2/R3 code → 02d
`--refresh` on the union above (then the rest of the pre-block corpus) →
02e → 04 → `audit_terroir_facts.py --strict` → re-sample 200 with the
verifier prompt, target misleading < 1.5 %.

## Evidence

`tmp/terroir-facts-review/full-review-2026-09-12/` (15 MB, gitignored):

- `REVIEW_GUIDE.md` — rubric and pipeline context given to every reviewer.
- `findings/` — per-sheet reviewer output (`<sheet>-fidelity|language|explore.json`).
- `merged.json` — per-fact merged findings + summary; `record_notes` holds
  the 1,263 MISSING / 96 OTHER / 10 WRONG_SOURCE / 4 SIB record notes.
- `verdicts/`, `verdicts_merged.json` — 703 adversarial verdicts
  (`verdict`, `reader_misled`, `where`, `confirmed_tags`, `reason`,
  `corrected_en`).
- `precision/` — 278 soft-tag second opinions; `modes/`, `modes_merged.json`
  — failure mode per misleading bullet.
- `det_checks.json`, `numcheck_notfound.json` — deterministic checks.
- `report_data.json` — every number in this document.
- `workflows/` + `*.py` — the sheet builders, merge, harvest and the
  Workflow scripts (review, verify, precision, modes) to re-run.
