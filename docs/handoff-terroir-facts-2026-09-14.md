# Terroir facts — hand-off (2026-09-14)

Where the terroir-fact quality programme stands after the 2026-09-13 runs,
the configuration decided on 2026-09-14, and the remaining work in priority
order, each item with its evidence, the files involved, the acceptance test
and the cost. Written for whoever picks this up next (human or agent); read
[review-terroir-facts-2026-09-12.md](review-terroir-facts-2026-09-12.md)
("Implemented" / "Results") first for what already landed, and the
"Hard rules" bullets on the gate, the back-check and the per-run backups in
[../CLAUDE.md](../CLAUDE.md) for the invariants.

## 0a. Progress log (2026-09-14, afternoon)

Landed on `gi-terms-and-analytics` after the hand-off was written — each
a commit, tests green (632), `ruff` clean:

| item | commit | what changed |
|---|---|---|
| §0 commit | `a1e4920` … `5724847` | the whole programme committed in the four suggested slices |
| 3.1 MASAF cap | `2cfab2e` | 02f emits `link_to_terroir_full` (v3 sidecars, regenerated: 469 of 522 longer, +3.66 M chars); IT 02d / gate / audits read it; panel text byte-identical |
| 3.2 grounding typography | `5fe8c45` | `normalize()` folds quotes / apostrophes / dashes, NFKC, soft hyphens, hyphen-breaks, guillemet spaces. Measured on every kept r1 quote: FR 1,628 / 3,165 higher (1,387 → contiguous), others 484 / 5,679; 0 threshold regressions |
| 3.3 extractor does the gate's job | `0b72dba` | claim-support rule first in `STYLE_RULES`; gate-v2: empty rewrite → supported + `rewrite_missing`, cosmetic rewrite (ratio ≥ 95 **and** no differing word of 4+ letters) → supported + `cosmetic_rewrite`; audit lists `rewrite_missing` |
| 3.4 earned `interactions` | `0b72dba` | `_lib/terroir_interactions.py` (15-language connective table); 02d drops an interactions fact whose *quote* has no connective (cap 2), the gate demotes it. Measured on r1: 69 % of interactions quotes carry one, 8 % bullet-only, 23 % none. The fourth call stays (FR X.3 / EU 8.4 are the earned ones); no promotion (1,388 candidates would triple the share) |
| 3.7 mechanics | `146a6ef` | `needs_gate` shared by 02d_verify + audit: pending = a fact without a verdict, or source / GATE_VERSION changed — no exact sha, so post-passes no longer re-fire the gate; 02d normalises at write time; `feedback_recurrence` resolves on a meaningful `support.original_bullet` rewrite |
| 3.10 cost logging | `86c3af0` | per-result usage from both providers, Batch-API pricing, `raw/.batch/costs.jsonl` ledger, `batch` block in gate / back-check reports, per-stage spend logged by the orchestrator |
| orchestrator | `3133802` | `--scoped-02d` (IT: every record is stale after 3.1 — a scoped run would otherwise re-extract all of Italy) and `--scoped-gate` (gate-v2 made every record ungated — a smoke would otherwise re-gate the corpus) |

Not done, deliberately: 3.7 `--only-file` across the 42 scripts (the
stale-marking works; `--scoped-02d` covers the case that hurt), the
`multi_sentence` splitter and the Alsace `produit` decision; 3.5, 3.6,
3.8, 3.9 untouched.

Later the same afternoon: `ff14659` back-check keeps the translation when
a fix comes back empty (`fix_missing`, backcheck-v2 — 3.8's 512);
`f2e5f4d` + `1023576` the audit pinned the MASAF template at v2 (every
regenerated sidecar would have reported stale) and `META_RE` was
English-only — source-language citations ("secondo il disciplinare",
"selon le cahier des charges", "laut Produktspezifikation", "according to
the production specification") are now caught, and the normaliser drops
such a clause when it trails the sentence; `9e0f8f3` FR 02d records
`n_dropped` / `n_deduped` / `n_unearned_interactions`; `43d2d5e`
orchestrator `--scoped-backcheck` (see the smoke).

**Sequencing.** Items 3.1–3.4 all change what the extractor produces, so
they were landed *before* the corpus migration (2.1) rather than after —
one full pass, not two. GATE_VERSION is `gate-v2` and BACKCHECK_VERSION
`backcheck-v2`, so the migration's corpus-wide gate and back-check steps
redo everything by construction.

### Smoke of the new chain — `smoke-cfg-2026-09-14` (6 records, $1.12)

`rerun_terroir_facts.py --scope {barolo, chablis, rioja, mosel, dingac,
santorini} --scoped-02d --scoped-gate` (+ the back-check scoped by hand,
see below), then `normalize_terroir_facts.py --only …`, then the audit:

| stage | result |
|---|---|
| 02d Sonnet 5 (thinking off) | 58 facts (9.7 / record; the same six had 52 under Sonnet 4.6), 0 grounding drops, 5 unearned `interactions` dropped → 2 kept = **3.4 % share** (was 10.8 %) |
| gate Opus 5 adaptive | 4 / 58 rewritten (**6.9 %**, was 20–27 %), 0 dropped, 1 moved, 0 cosmetic, 0 empty. All four rewrites read as true source-grounded corrections (Rioja Alavesa / Sierra de Cantabria north–south, "von Hand", "milenaria", the Santorini hedge grading) |
| 02e Sonnet 4.6 → back-check | 19 / 210 translated bullets fixed (9.0 %), 2 empty fixes kept as `fix_missing`, 0 rejected |
| audit | strict checks 0; `gate_pending` 1,629 = the rest of the corpus (v2 bump), `feedback_recurrence` 23 — 17 are the do-not-claim entries merged from the two post-r1 LLM audits, still in their (un-re-extracted) records; none in the six |
| ledger | 02d $0.34 · gate $0.37 · 02e $0.26 · back-check $0.14 |

Two things the smoke taught: (1) after a version bump the corpus-wide
gate / back-check steps are the whole corpus — the back-check submitted
5,895 requests before I cancelled it at $0.00 processed; hence
`--scoped-backcheck`, and the rule *a smoke passes all three `--scoped-*`
flags, a migration passes none*. (2) Sonnet 5 still cites the document
once in six records ("secondo il disciplinare") — the normaliser strips a
trailing citation and the audit now flags the source-language forms.

**Cost projection for 2.1**, from the ledger: $1.12 for the six → ≈ $300
for 1,640 records as an upper bound (the six include three long sources —
Barolo's now-uncapped Art. 9 alone is 119 K input tokens); the hand-off's
$210 is the lower bound. Expect $210–300.

## 0. State you inherit

- **Corpus**: 1,638 records / 11,255 source bullets / 5,895 translation
  caches; strict audit 0 findings (`label_prefix` strict); 1,403 records
  extracted 2026-09-13 with Sonnet 4.6 under the current prompt, every
  record gated (Sonnet 4.6, `gate-v1`), every translation back-checked.
  Measured with the Opus-5 verifier: 3.2 % reader-misleading bullets on a
  120-record sample (from 13.8 % before), 1.4 % on a 60-record sample of
  the second run.
- **Runs on disk** (`scripts/rollback_terroir_facts.py --list`):
  `r1-2026-09-13` (union scope, 1,634 slugs), `r1b-2026-09-13` (rest
  scope, 519), `r1c-2026-09-13` (grounding fix + provenance re-grade,
  1,203), `exp-sonnet5` (rolled back), two `smoke-*`. Roll back newest
  first; rebuild stage 04 afterwards.
- **Not committed.** Everything since commit `a857790` on branch
  `gi-terms-and-analytics` is uncommitted: the whole review programme
  (`_lib/terroir_*`, the 21 × 02d/02e edits, the gate, the back-check, the
  orchestrator, the rollback, the audit changes, docs, tests). First act
  of the hand-off: commit it — `git status` is the list; a sensible split
  is (1) backup + rollback + orchestrator, (2) gate + back-check + prompts
  + audit, (3) MASAF slicer + BPTG pin + Wikipedia pins, (4) docs. Raw
  caches, backups and feedback sidecars are gitignored and live only on
  this machine.
- **Map**: `wiki/` was rebuilt from the final caches (77 IT sottozone,
  Montepulciano d'Abruzzo 9 facts); not deployed.

## 1. Decided configuration (2026-09-14) — already the code default

| stage | model | thinking | why |
|---|---|---|---|
| 02d extraction (21 scripts) | `claude-sonnet-5` | off | paired test on 120 records: same per-bullet reliability as Sonnet 4.6 (1.7 % vs 1.8 % extraction-origin misleading), **31 % more grounded facts**, 0 grounding drops, 20 % gate-rewrite rate vs 27 %, $2 / $10 per M vs $3 / $15 |
| gate `02d_verify` | `claude-opus-5` | adaptive | the Opus-5 verifier caught residuals a Sonnet gate had passed; `MAX_TOKENS` raised to 8,000 for thinking + reply |
| LLM audit | `claude-opus-5` | adaptive | unchanged |
| 02e translation, back-check | `claude-sonnet-4-6` | — | not re-tested; the back-check already fixes 9 % of translated bullets |

Where it lives: `providers.STAGE_DEFAULTS` + `stage_default()`,
`batch.default_model(provider, stage)` / `default_thinking()`, the
`thinking` argument threaded through `batch.run_two_pass` →
`_submit_anthropic` and `AnthropicProvider`; every 02d script passes
`stage="02d"`, the gate / back-check / audit their own stage; `--model` and
`--thinking` override per run; `OWM_BATCH_THINKING` overrides for an
experiment. `tests/test_stage_defaults.py` pins it. The orchestrator's
`--model` now applies to 02d only.

**The corpus is NOT yet on this configuration** — it was extracted and
gated with Sonnet 4.6. Step 2.1 below is the migration.

**Costs** (measured token usage × Batch-API rates): a full corpus pass is
≈ **$210** in this configuration (02d $47, gate ≈ $79 with adaptive
thinking, 02e $50, back-check $34) vs $157 all-Sonnet-4.6; a 120-record
Opus-5 audit pass is ≈ $6; a scoped re-run costs proportionally. Token
usage per batch is retrievable for 29 days with
`client.messages.batches.results(id)` — there is no cost logging in the
pipeline yet (item 3.10).

## 2. Runbook

```
# one scoped run = one rollback unit; logs under /tmp/owm-<run>/
.venv/bin/python scripts/rerun_terroir_facts.py --scope SLUGS.json --run <id> [--parallel 7]
#   = mark stale → 02d --batch per country → 02d_verify --batch (corpus-wide, ungated)
#     → 02e --batch (all countries, stale only) → 02e_verify --batch → audit
.venv/bin/python scripts/normalize_terroir_facts.py && .venv/bin/python scripts/dedupe_terroir_facts.py
.venv/bin/python scripts/audit_terroir_facts.py --strict --strict-labels --quiet --report tmp/terroir-facts-review/audit-<id>.json

# acceptance: paired, same grader, same records
.venv/bin/python scripts/audit_terroir_facts_llm.py --sample 120 --batch --from-backup <id> --report before.json
.venv/bin/python scripts/audit_terroir_facts_llm.py --slugs-file <the sample> --batch --report after.json
.venv/bin/python scripts/audit_terroir_facts_llm.py --compare before.json after.json
#   feed the residue back:  --emit-feedback DIR  →  scripts/build_terroir_feedback.py --evidence DIR --review-id <id>

# undo
.venv/bin/python scripts/rollback_terroir_facts.py --list
.venv/bin/python scripts/rollback_terroir_facts.py --run <id> [--only slug] [--dry-run]
.venv/bin/python scripts/04_build_maps.py
```

Gotchas learned the hard way: the 21 scripts spell their record filter
three ways (`--slug` exact for FR, `--only` *name* substring for stage 02,
`--only` slug substring for the other 02d scripts) — that is why the
orchestrator marks caches stale instead of passing slugs; never run two
chains on overlapping records at once (the gate and 02e both write the
translation caches); a post-pass that changes bullets makes `gate_pending`
fire again (it keys on an exact sha) — re-run `02d_verify` after
normalise / dedupe; the audit's `feedback_recurrence` is lexical and
fuzzy-matches corrected bullets (5 of its 6 residual hits were fixed
bullets), so read its rows before believing the count.

### 2.1 Migrate the corpus to the decided configuration

Re-extract everything with Sonnet 5 and re-gate with Opus 5:

```
python3 -c "import json,glob; json.dump({'slugs':[p.split('/')[-1][:-5] for p in glob.glob('raw/terroir-facts/*.json') if 'manifest' not in p]}, open('tmp/terroir-facts-review/scope-all.json','w'))"
.venv/bin/python scripts/rerun_terroir_facts.py --scope tmp/terroir-facts-review/scope-all.json --run cfg-2026-xx-xx --parallel 7
```

≈ $210–300 (see the smoke), ≈ 45–60 min wall-clock. Then the acceptance pair above; expect the
misleading share at or below 3 % on the 120-record frame, more facts per
record (≈ 8.9 vs 6.8), and check that the Opus gate's rewrite / drop
shares are in the 4.6 gate's range (20–28 % / 1.5–2 %) — a much higher
drop rate means the adaptive-thinking gate is stricter than the prompt
intends and the prompt's "supported" definition needs loosening, not the
model. The 231 records extracted 2026-09-11 (never re-extracted since)
come along in this pass.

## 3. Remaining recommendations, ranked

Each item: **evidence** (measured in this programme) → **do** → **accept**.

### 3.1 Lift the 4,000-character cap on the MASAF terroir text (Italy)
- Evidence: `derive_terroir(body, max_chars=4000)` in
  `scripts/_lib/it/masaf.py` truncates the sidecar's `link_to_terroir`;
  312 of 519 IT sidecars have an Art. 9 longer than that — ≈ 2.85 M
  characters of regulator terroir text that 02d, the gate and the audit
  never see. Italy is the largest and worst-scoring country.
- Do: keep the panel's short text as `link_to_terroir_brief` (stage 04
  reads the short one) and give 02d the full Art. 9 body (or raise the cap
  for the 02d path only). Re-run `it/02f_extract_masaf.py --all
  --include-nonstub`, then the IT records through the chain (their sha
  changes, so the orchestrator picks them up without a scope).
- Accept: IT facts per record up; paired audit on 60 IT records not worse
  than before; `audit_it_coverage.py` unchanged.
- Cost: IT-only pass ≈ $70.

### 3.2 Grounding filter: normalise typography before matching
- Evidence: even after the block-aware coverage (`_lib/terroir_coverage`),
  965 extracted facts were discarded against 11,255 kept (7.9 %); 114
  records lost ≥ 3. The quotes are verbatim; they fail on curly vs straight
  apostrophes, hyphen-space artefacts ("gradi- giorno"), soft hyphens,
  ligatures. (Sonnet 5 had 0 drops on the 120-record sample, so 2.1 may
  make this moot — measure after it.)
- Do: fold apostrophe / quote / dash variants and remove soft hyphens and
  hyphen-newline joins in `normalize()` on both sides; keep the 0.6
  threshold; add cases to `tests/test_terroir_audit_checks.py`
  (`test_coverage_is_block_aware…`). Then re-run the records with
  `n_dropped ≥ 3` (the r1c pattern: `r1c-scope-grounding.json` was built
  from that query).
- Accept: `n_dropped` sum < 2 % of kept; no new `eroded_bullets`; the
  scattered-phrase and foreign-text probes still score < 0.3.

### 3.3 Make the extractor do the gate's job
- Evidence: the gate rewrote 27–28 % of Sonnet 4.6 bullets (20 % of
  Sonnet 5's); 44 % of rewrites were light edits and 9 % near-cosmetic
  (`fuzz.ratio ≥ 95`); 124 rewrites came back empty.
- Do: (a) move the gate's claim-support rules ("assert only what the
  quoted sentence states; never turn presence into cause; never narrow an
  en-bloc attribution") into `STYLE_RULES` — a first version is there;
  make it explicit and first; (b) in `_lib/terroir_gate.apply_verdicts`,
  treat a rewrite with `fuzz.ratio(original, rewrite) ≥ 95` as
  `supported` (keep the original) so the rewritten cohort is meaning
  changes only; (c) in the gate prompt require a non-empty `rewrite` for
  the `rewrite` verdict, else downgrade to `supported` with the note.
- Accept: gate rewrite share falls; a 100-rewrite sample graded by the
  Opus verifier shows ≥ 90 % meaning-changing.

### 3.4 Finish R3 — earn the `interactions` sub-section
- Evidence: the `interactions` share is unchanged at 10.8 % of bullets;
  the gate rewrites causal wrappers but rarely moves the bullet out of
  `interactions`; 7 of the 25 residual misleading bullets on the sample
  are still unsupported causal links.
- Do: the review's first option — drop the fourth sub-section call in the
  21 scripts, ask the three remaining calls to mark `causal: true` only
  when the source sentence carries an explicit connective, and file those
  under `interactions` (cap 1–2). `SUBSECTIONS` is per script; stage 04
  and `terroir_sources` key on the four sub-section names, so keep the
  key, change how it is filled. Alternatively a deterministic
  connective check per source language in `apply_verdicts` (a bullet
  under `interactions` whose quote has no connective → move to
  `facteurs_naturels` / `produit` by the verdict's `subsection`).
- Accept: `interactions` share ≈ 3–5 %; `unsupported-causal-link` tags in
  the paired audit at or near 0.

### 3.5 Calibrate the measurement
- Evidence: the Opus-5 grader put the pre-programme baseline at 13.8 %
  where the review's Sonnet verifier said 6.9 %; nobody has checked the
  grader's precision, nor sampled the 3,899 gate rewrites or the 4,483
  back-check fixes for correctness.
- Do: second-opinion 50 of the grader's "misleading" verdicts (a
  different model, or a human on the sheet the audit can emit); grade a
  100-rewrite and a 100-fix sample; publish the precision numbers in the
  review doc and restate the target on the Opus scale.
- Accept: a precision figure per instrument; the acceptance target
  restated ("< X % on the Opus-5 grader").

### 3.6 Source-binding residue the new audit checks surfaced
- `wiki_binding` 23: 7 HR records bound to the umbrella *Vinogradarska
  područja Republike Hrvatske*, `frusinate` → the province, `lisboa` → a
  list article, `lesvos` → "white wine", `regensburger-landwein` →
  *Baierwein*, `starkenburger-landwein` → *Hessische Bergstraße*; pin in
  `raw/wikipedia/aoc_overrides.json`, refresh with
  `02b_fetch_aoc_lexicon.py --lang <l> --source <dir> --only <slug>
  --refresh` (a changed revision re-triggers 02d). Full list in
  CURATOR_TODO "Cross-country".
- `foreign_name` 3: `terre-del-colleoni` names Bergamasca 8×, `pompeiano`
  two provinces 5× — check the MASAF binding.
- CZ register fiche: the `morava` / `slovacka` "terroir" text (31 k
  chars) is a per-wine-type description that never names the wine
  (`name_guard_other`); check `_lib/register_fiche` slicing of §7.
- MASAF annexes: the sidecars now carry `annexes[].title`; feed those to
  `extract_it_sottozone` (Montepulciano d'Abruzzo 9, Abruzzo 4, Trentino
  5 are still undetected) and ground each synthesized sottozona on its
  own annex Art. 9 instead of the parent's bullets; fix the detector's
  merge of «Schioppettino di Prepotto» + «Savorgnano».
- `rewrite_rejected` 97: originals kept, flagged in `support`; re-gate
  after 3.3 or hand-check.

### 3.7 Smaller mechanics
- `feedback_recurrence`: compare the claim with `support.original_bullet`
  too, and count a fact as resolved when its current bullet differs
  meaningfully from the matched original.
- Key the gate on a normalised sha so normalise / dedupe do not re-fire
  `gate_pending`.
- One `--only-file` across the 21 × 02d and 02e scripts (then the
  orchestrator can pass slugs instead of marking caches stale).
- `multi_sentence` 95 source bullets despite the one-sentence rule —
  minor; the normaliser could split on the first terminator + capital.
- `cross_record_identical_en` 16: the Alsace grand cru `produit` slice is
  one shared paragraph for 51 crus; decide whether to keep it once per
  cru or drop it from the sub-record view.

### 3.8 Translation side
- The back-check fixes 8.9 % of translated bullets; the r1b pass (after
  the glossary additions) fixed 8.4 % — the glossary is not the lever,
  the back-check is. Consider Sonnet 5 for 02e + back-check (untested;
  one paired 60-record run answers it, ≈ $10).
- 512 back-check fixes came back empty (same fix as 3.3c).

### 3.9 Curator items outside the pipeline
- `collioure`: no source text resolves; the only record the gate and the
  audit skip.
- Hautes-Alpes / Haute-Vienne: verified a genuine 20-cahier bundle, no
  change needed (closed in CURATOR_TODO).

### 3.10 Cost logging
- `batch._fetch_anthropic` sees `usage` per result; sum input / output
  tokens into the stage manifests and the gate / back-check reports so a
  run reports its own cost. Today the numbers in this document came from
  re-reading the batches via the API.

## 4. Things that are settled — do not reopen

- The coverage threshold stays 0.6; the block-aware measure is the fix
  for artefacts, not a lower threshold.
- The name guard is strict for FR only; the other countries' texts often
  never name the wine by design (CZ region-wide, Landwein).
- Sonnet 5 as extractor is a coverage / cost choice, not a quality one
  (paired test, `exp-sonnet5`); do not expect it to move the misleading
  rate — 3.3 / 3.4 / 3.5 are what move it.
- The label-prefix regex was tightened to 1–2-word labels after it
  flagged enumerating colons ("Three soil types coexist:"); keep
  `label_prefix` strict.
