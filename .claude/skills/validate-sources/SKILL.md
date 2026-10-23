---
name: validate-sources
description: >-
  Check that every source a card cites is still the newest the publisher has,
  across tiers — the EU register (eAmbrosia, with EUR-Lex covered through it),
  national regulators (INAO + data.gouv.fr, GOV.UK, the national-spec PDFs),
  regional sources (geoportals, cantonal règlements, parish layers), trade
  bodies (liveness only), geometry layers (GISCO, swisstopo; Bétard is a
  snapshot) and Wikipedia revisions — and reconcile per-country counts against
  the live register. Use for "did any cahier / single document change", "is
  the parcellaire release current", "which sources are link-rotten", the
  monthly drift check, or before a deploy. Runs
  scripts/audit_source_freshness.py (network; cached for a day); never
  ingests anything.
---

# validate-sources

The freshness validator of [docs/plan-validators.md](../../../docs/plan-validators.md) § 1:
`scripts/audit_source_freshness.py` over the probe package
`scripts/_lib/freshness/` (one module per upstream family, verdicts
CURRENT / NEWER-UPSTREAM / RELINKED / GONE / UNREACHABLE / IN-OPPOSITION /
SNAPSHOT / COVERED / UNVERIFIABLE). It is the register-drift recipe of
[docs/register-drift-2026-09-20.md](../../../docs/register-drift-2026-09-20.md)
made repeatable.

## Hard rules

- **Detector only.** Reports what is newer, where, and the stage to re-run;
  it fetches nothing into `raw/`. Re-fetching is the recipe's job, run by you
  after reading the finding.
- **Trade bodies are a signal, never a source.** Their sites are probed for
  liveness so a dead link leaves the card; nothing is ever read from them.
- **Fenced hosts are named, not hammered.** BO Agri answers French IPs only
  (use a French exit node), minagric wants the four-w host, EUR-Lex is a WAF
  (COVERED through eAmbrosia). The per-host circuit breaker marks a host
  unreachable after three failures; respect the verdict's reason.
- **A CURRENT on the EU tier is necessary, not sufficient, for France**: the
  register lags the national arrêté (3 of 22 on 2026-09-20). `--inao` walks
  the INAO product pages for the FR scope (~1 s per record).

## Procedure

1. **Corpus-level, cheap (≈ 10 requests):**
   `.venv/bin/python scripts/audit_source_freshness.py --no-record-probes --tiers eu,national,geometry --counts`
   Read the Markdown under `tmp/validation/sources-<stamp>.md`: the eAmbrosia
   NEWER / GONE / IN-OPPOSITION rows per GI, the data.gouv.fr release check,
   GOV.UK, GISCO / swisstopo, the counts table.
2. **Per-record documents** for a scope (HEADs, cached a day):
   `--country gr --tiers national,regional` ; add `--deep` to re-fetch and
   compare sha256 when a HEAD says "newer" (a server re-stamp is not a new
   document); `--sample 60` for a spot check; `--max-requests` caps the run.
3. **France:** `--country fr --inao --only <slug> …` for the records the EU
   tier or a visitor flagged; a full FR walk is ~466 pages — run it in the
   background with a log.
4. **Wikipedia** (`--reference`): informational; a newer revision changes a
   tooltip or a salience hint, never a regulator fact.
5. **Route** the NEWER / GONE rows (`--curator-md PATH` writes them grouped by
   country, with the recipe): a new document → the country's stage 01 / 01c
   `--only … --refresh` → 02 / 02f → 04 (recipes in
   [reference/recipes.md](reference/recipes.md)); a GONE register row → confirm the
   cancellation regulation on EUR-Lex, then `scripts/_lib/cancelled_gis.json`;
   a NEW GI → stage 00 + region / geometry entries; a GONE document URL →
   `manual_overrides.json` of that layer. Append the counts table to
   VERIFICATION.md when you ran `--counts` as a reconciliation.
6. **Cadence:** on demand before a deploy and after a visitor flag; a monthly
   corpus-level run is the drift check (the `schedule` skill can run it).

## What stays manual

- Confirming a cancellation or a new registration on EUR-Lex before any
  registry changes.
- Fetching behind a geo-fence (VPN) and pinning a curator URL.
- Deciding whether a "modified, no new publication" register row is worth a
  re-fetch (often a register attachment only).
