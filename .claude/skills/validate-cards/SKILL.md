---
name: validate-cards
description: >-
  Independent LLM reading of whole appellation cards against their sources —
  name, classification, region, styles, grape roster and roles, area, terroir
  facts, summary, sub-denomination relation, sources — by a judge from a
  different model family than the extractor that sees only the rendered card
  and the source documents. Use to measure a build's card quality
  ("validate 200 cards", "grade the top-viewed cards", "check the cards a
  parser change touched", "second opinion on these slugs"), to turn the
  findings into feedback-sidecar constraints and CURATOR_TODO rows, and for
  the paired before / after of a fix. Runs scripts/audit_cards_llm.py; costs
  money (≈ $0.10 per card at the Opus batch rate) and says so before running.
---

# validate-cards

The whole-card validator of [docs/plan-validators.md](../../../docs/plan-validators.md) § 2.
`scripts/audit_cards_llm.py` builds, per record, the **packet**
(`scripts/_lib/card_packet.py`): the card as the reader sees it in one
locale (the server-rendered card as text + structured fields) and every
source document behind it (the regulator record section by section, the
national-spec and EU-register sidecars, the Wikipedia page). The judge never
sees the pipeline's grounding quotes, prompts or gate verdicts. Every quote it
returns is re-grounded against the documents (`verified`).

## Hard rules

- **Detector, never editor.** The script writes a report; nothing under
  `wiki/` or `raw/` changes. A finding is routed, never applied.
- **Independence.** Judge = `providers.STAGE_DEFAULTS["audit"]` (Opus) against
  the Sonnet extractor. Do not grade with the extractor's model. `--second-opinion
  MODEL` re-grades the records with a verified misleading finding.
- **Spend is stated first.** The script prints the estimate and refuses above
  `--max-usd` (default 25) without `--yes`. Say the estimate to the user before
  a run over ~$5; a corpus sweep is ≈ $300 — sample and stratify instead.
- **Isolated or broader.** Every verified misleading finding names a failure
  mode (`tag`); before reporting a fix, sweep the same tag across the country
  / parser template and say "isolated" or "N more" (memory
  `feedback_isolated_or_broader`).
- **Wine only by default** (`--all-products` for spirits and ciders); stubs with
  no grapes and no facts are left out (`--include-stubs`).

## Procedure

1. **Scope.** One of:
   - `--sample N` (stratified by country × geometry source; `--seed`),
   - `--top-viewed N` (Plausible `Appellation Viewed`; needs `PLAUSIBLE_API_KEY`),
   - `--only slug …` / `--country cc …`,
   - `--slugs-file changed.json` — the `--slugs-out` of
     `scripts/diff_records.py diff` after a rebuild (the cards a change touched).
   `--locale fr|es|nl` grades another locale's rendering (EN by default, the
   locale readers see most). `--section grapes` grades one section only.
2. **Dry run** to see the packets and the estimate:
   `.venv/bin/python scripts/audit_cards_llm.py <scope> --dry-run`
3. **Run.** `--batch` for anything above a handful (Batch API, 50 % price,
   resumable through `raw/.batch/cards-llm-*.json`); synchronous for a few
   records. Add `--emit-curator-md tmp/validation/cards-rows.md` and, when
   terroir facts are in scope, `--emit-feedback tmp/validation/cards-feedback`.
4. **Read the Markdown** (next to the JSON under `tmp/validation/`): the
   share of cards with a verified misleading finding (Wilson 95 %), by
   section / tag / country, then every record's findings with the quote. An
   `unverified` finding (quote not found in the documents) is a judge claim,
   not evidence — do not act on it without reading the source.
5. **Route.**
   - terroir-fact findings → `scripts/build_terroir_feedback.py --evidence
     tmp/validation/cards-feedback --review-id cards-<stamp>` (do-not-claim
     constraints), then a scoped re-run through `scripts/rerun_terroir_facts.py`;
   - header / roster / style / area findings → the parser, lexicon or override
     file that owns them (see [reference/routing.md](reference/routing.md));
     the curator rows go into CURATOR_TODO.md under the country, with the sweep
     result in the last column;
   - a finding that is the house convention (a verbatim spelling, a disclosure
     line, an inherited roster) is a prompt gap: fix the `SYSTEM` rules in the
     script, never the card.
6. **Verify a fix** with the same scope: `--report after.json`, then
   `--compare before.json after.json` prints the paired change (records
   improved / worse / same).
7. **Full review** (≥ 200 records): copy the Markdown to
   `docs/review-cards-<date>.md` with a headline table, and append the
   session's memory note.

## What stays manual

- Reading the source for every finding you act on. The judge quotes; it does
  not decide.
- Writing override / supplement entries (they need a cited public source).
- Choosing the sweep breadth for a failure mode.

## Reference

- [reference/tags.md](reference/tags.md) — the failure-mode tags and what each
  usually means upstream.
- [reference/routing.md](reference/routing.md) — section → owner table.
