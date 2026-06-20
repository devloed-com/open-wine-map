# Reconciliation log

Dated history of corpus-reconciliation passes — what landed, what was verified,
what regressed. Split out of `CURATOR_TODO.md` (which now keeps only the
`Last reconciled:` pointer + open items) so the actionable queue stays readable.

Newest first.

---

## 2026-05-14

Rully + Maranges CAVB cahiers landed via Type 1C OCR fallback — 35 new slugs
(24 Rully premier-crus + 9 Maranges climats), section X 8050/9349 chars, 02d
ran fine on both, 02e produced 7 EN/ES/NL translations.

Stale audit confirmed three "code follow-ups" already shipped:
- AOC Wikipedia override consumption live in
  `scripts/02b_fetch_aoc_lexicon.py:64-66,322-373,388-390` (cache carries
  `override_source=curator`).
- ES grape lexicon already iterates `raw/es/pliegos-extracted/` via
  `collect_grape_slugs` in `scripts/02b_fetch_grape_lexicon.py:76-95`.
- DOCUMENTO ÚNICO anchor regex matches both Toro + Ribera del Guadiana (RDG's
  "0 grapes principal" was role-routing, not anchor).

Earlier same day:
- Wikipedia AOC override merge — fr 44→101, es 0→29.
- ES national-pliego URL research merged 12 entries into
  `raw/es/national-pliegos/manual_overrides.json` + stage 02f override-priority
  read wired in `scripts/es/02f_extract_national_pliegos.py` + parser tightened
  in `scripts/_lib/es/national_pliego.py` → 138 new variety-DOP additions, zero
  regressions.
- 6 stale research prompts under `scripts/_lib/` deleted after their batches
  closed.
- ES consejo regulador URL merge — 56 new entries to `appellation_urls.json`,
  `by_slug` now 205.
