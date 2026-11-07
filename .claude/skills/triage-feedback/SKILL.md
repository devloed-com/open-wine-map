---
name: triage-feedback
description: >-
  Triage the visitor feedback stored in Plausible (Feedback Flagged / Note on
  the appellation cards): pull the queue, run the deterministic checks and the
  LLM card validator on each flagged card, establish whether each defect is
  isolated or one instance of a broader failure mode (sweep the siblings),
  and write the dated triage doc plus the CURATOR_TODO rows. Use when asked to
  "triage the flags", "what did visitors report", or after a flag arrives.
  Runs scripts/feedback_report.py then the validate-cards / validate-geometry /
  validate-sources scripts on the flagged slugs; fixes go upstream, never into
  the build.
---

# triage-feedback

The recurring triage session of 2026-09-22 → 2026-10-22 as a skill
([docs/plan-validators.md](../../../docs/plan-validators.md) § 4).

## Hard rules

- **A retracted flag is not proof of no defect** (memory
  `feedback_retracted_flag_not_proof`): check the surface in the flag's locale
  and zoom band (`lod`, `zoom` props).
- **Isolated or broader, always** (memory `feedback_isolated_or_broader`):
  name the failure mode in one line, sweep the country's other records / the
  same parser template / the unknowns queues, report "isolated" or "N more
  records, fixed / queued".
- **Fix upstream.** Parser, lexicon, override with a cited source; never the
  build, never the cache by hand.

## Procedure

1. **Queue:** `.venv/bin/python scripts/feedback_report.py --range 30d`
   (`PLAUSIBLE_API_KEY` in `.env`): net flags per appellation × aspect, the
   notes verbatim.
2. **Per flagged slug, by aspect:**
   - boundary → `scripts/audit_geometry_vs_text.py --only <slug>` (+ the
     parent), the geometry audits for that record, a headless look at the
     flagged zoom (memory `feedback_headless_map_check`);
   - grapes / facts / name / sources → `scripts/audit_cards_llm.py --only <slug>`
     (synchronous, a few cents), then read the source yourself;
   - sources / "outdated" → `scripts/audit_source_freshness.py --only <slug>
     --tiers eu,national,regional --deep` (FR: add `--inao`).
3. **Name the failure mode** and **sweep**: the same tag across the country
   (`audit_cards_llm.py --country cc --section <section>` on a sample when the
   mode is a parser rule), the extraction-unknowns queues for a lexicon gap, a
   corpus-wide count for a rendering rule.
4. **Fix upstream**, re-extract with a snapshot and a per-record diff
   (`scripts/diff_records.py`), rebuild, re-run the validator on the slug.
5. **Credit** (the report's "Credits offered" section): for each name whose
   report was acted on (fixed, or confirmed and queued), append
   `{name, added, via, slugs, report}` to `scripts/_lib/contributors.json`,
   the name exactly as given. Skip an offensive name, an impersonation, contact
   details or a link; remove a name on request. The About dialog's thanks list
   follows on the next build (`04_build_maps.py --shell-only` is enough).
6. **Write** `docs/feedback-triage-<date>.md` (what was flagged, what was
   wrong, isolated or broader, what changed, who is credited) and the
   CURATOR_TODO rows for what is queued; save the memory note
   (`project_feedback_triage_<date>`).
