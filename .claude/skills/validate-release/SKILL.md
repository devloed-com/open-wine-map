---
name: validate-release
description: >-
  Pre-deploy gate: run every deterministic audit the repo has (the --strict
  audits, the translation detectors, the test suite), the About-page date and
  the stage-04 snapshot staleness check as one command with one table, then
  the LLM card validator on the records the build changed. Use before
  deploy.sh, after a full stage-04 build, or when asked "is this build fit to
  ship". Runs scripts/validate_release.py (+ diff_records.py and
  audit_cards_llm.py for the changed records); fails the release on any
  failed check.
---

# validate-release

The umbrella of [docs/plan-validators.md](../../../docs/plan-validators.md) § 4.
`scripts/validate_release.py` runs the registry of gates (`--list` prints it)
and writes `tmp/validation/release-<stamp>.md`.

## Procedure

1. **Snapshot before the build** (once per release cycle):
   `.venv/bin/python scripts/diff_records.py snapshot --out tmp/validation/records-before.json`
   If the snapshot was not taken, use the deployed site's snapshot under
   `snapshots/` or the previous `tmp/validation/records-*.json`.
2. **Build**, then snapshot again and diff:
   `.venv/bin/python scripts/diff_records.py snapshot --out tmp/validation/records-after.json`
   `.venv/bin/python scripts/diff_records.py diff tmp/validation/records-before.json tmp/validation/records-after.json --md tmp/validation/records-diff.md --slugs-out tmp/validation/changed.json`
   Read the diff: every changed roster, style, region, geometry source or
   area must be explained by the release's changes; an unexplained change is
   a regression.
3. **Gates:** `.venv/bin/python scripts/validate_release.py --quick` (the
   geometry audits take minutes each; run the full set after any geometry
   change: no `--quick`). A failed check is a failed release — fix it or
   justify it in the deploy note; never deploy over a red gate.
4. **Changed cards** through the LLM validator (state the estimate first):
   `.venv/bin/python scripts/audit_cards_llm.py --slugs-file tmp/validation/changed.json --batch --emit-curator-md tmp/validation/cards-rows.md`
   With more than ~150 changed records, `--sample` within them.
5. **About-page date**: the table's `about-date` row must say today (memory
   `feedback_about_page_date`: rebuild on deploy day).
6. Hand the release table and the diff summary to the user with the deploy
   command; the deploy itself needs their OK.

## What stays manual

- The deploy (`scripts/deploy.sh`) and any registry edit.
- Judging an unexplained record diff.
