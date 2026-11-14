---
name: validate-geometry
description: >-
  Check that an appellation's polygon matches the delimitation the regulator
  wrote: the administrative units the text names versus the units the drawn
  polygon covers (reverse-geocoded against GISCO LAU, IGN communes,
  swissBOUNDARIES, CAOP, ONS), with an optional independent LLM reading of
  the text, plus the child-inside-parent containment no other audit checks.
  Use after a geometry change, on a visitor boundary flag, for "does the
  Monterrei / Cévennes / Côtes du Lot polygon match its text" questions, and
  as the geometry gate before a deploy. Runs scripts/audit_geometry_vs_text.py
  (plus the six polygon-vs-polygon audits it complements); reports
  OK / SUSPECT / REVIEWED, never redraws anything.
---

# validate-geometry

The geographic validator of [docs/plan-validators.md](../../../docs/plan-validators.md) § 3.
`scripts/audit_geometry_vs_text.py` complements the polygon-vs-polygon audits
(`audit_geometry_outliers`, `_overlaps`, `_betard_delta`, `audit_parcellaire_gaps`,
`audit_vineyard_envelopes`, `audit_climats`, `audit_it_regions`) with the one
independent check: **polygon vs text**.

## Hard rules

- **Detector only.** The audit redraws nothing. A real mismatch is fixed
  upstream — the country's delimitation reader, an `aires_supplements.json` /
  `parcellaire_gap_fills.json` pin with the cahier quoted, a commune-list
  parser — never by editing a polygon.
- **Reviewed mismatches carry evidence.** A SUSPECT that is the regulator's
  own statement goes in `scripts/_lib/geometry_text_overrides.json` with the
  reason, the public source, the date and the pinned `missing` / `extra`
  units; the entry re-fires (`override_stale`) when the sets change.
- **External maps are QA only.** A screenshot or a third-party map may tell
  you where to look; nothing is ever copied from it (memory
  `feedback_external_maps_for_qa_only`).
- **Read through `geom_source`.** A commune-union record with MISSING / EXTRA
  units has a parser defect; a zone / Bétard / parcellaire record is expected
  to draw parts of its named units, and only EXTRA whole units are the signal.

## Procedure

1. **Scope and run** (streams the 300 MB GeoJSON once; loads the layers of
   the countries in scope):
   `.venv/bin/python scripts/audit_geometry_vs_text.py --country ro --country bg`
   `… --country fr --only cevennes --only cotes-du-lot`
   `… --strict` (the release gate: exit 1 on an unreviewed SUSPECT).
2. **Deterministic named units** exist for FR (INAO aires CSV + cahier
   section IV), CH (BFS communes), RO / BG / HU (`parse_commune_list`), IT and
   AT (`parse_geo_area`), and the GR / PT disclosure fields. Other countries
   report NO-UNITS until `--llm` reads the text (`--batch`-less, cached per
   text sha under `raw/cache/geometry-text-llm/`): the model lists members,
   exclusions and holders with a quote each, and only names the layer carries
   count.
3. **Read the Markdown**: SUSPECT rows with the missing / extra unit names,
   the unresolved names (a spelling the layer does not carry — the usual
   cause, fix the reader or pin the name), and `child-outside-parent` shares.
4. **Triage each SUSPECT** against the text: parser miss → fix the reader and
   re-run stage 04 for the record; regulator's own statement → override entry
   with the quote; a layer vintage question → `/validate-sources` geometry
   tier.
5. **Re-run** after a fix with the same scope; the record moves to OK or the
   override to REVIEWED.
   A spirit, aromatised wine or cider drawn from a curator pin or from the
   register's NUTS rows (`drinks-area-pin`, `gisco-nuts-union`) reports
   **PINNED** when the only difference is whole units beyond the parser's
   reading — the country parsers were written for wine texts — and SUSPECT
   when a unit the parser read is not drawn. Scope a drinks run with one
   `--only` per slug; a full-corpus run takes hours.
   For a French record drawn from INAO's commune rows, the cahier is the
   delimitation and wins over the rows (Boris, 2026-11-13). First check the
   build holds the newest published cahier — BO Agri's title search,
   `https://info.agriculture.gouv.fr/boagri/recherche/resultat_recherche_rapide?titre=<name>`,
   answers when INAO's product site does not; pin a newer one in
   `raw/inao/cahiers/manual_overrides.json` and re-extract. Then
   `.venv/bin/python scripts/audit_aires_vs_cahier.py --only <slug>` lists
   the communes the cahier names that the rows lack (whole / partial /
   unclear, with the sentence), the rows the zone text does not name and the
   neighbouring codes (Gignac for Gigondas); `--bare --emit-pins PATH` stages
   a pin for `scripts/_lib/aires_supplements.json` (`communes`, `remove`,
   `not_drawn`, `whole_departements`). Read the text around every `whole`
   commune before pinning: Armagnac lists five communes and excludes them
   from the vineyard in the next sentence.
   A pre-merger commune code in the rows is drawn by the former commune's own
   outline where one exists (`scripts/_lib/fr/former_communes.py`); the ones
   with no outline are named on the card, not a defect. A code whose commune
   left its département before 2009 (Chassieu under 38088, Frettes under
   52210) is INAO's table at fault where the cahier says "le département de
   …": not drawn, listed by the audit (`--all`). The mirror case — a row
   whose code is today a commune nouvelle larger than the commune the cahier
   names — is drawn as the seat's former outline where the cahier names the
   old commune or restricts the new one (`scripts/_lib/fr/seat_communes.py`;
   stage 04 lists them, "[geo] seats of communes nouvelles …"); the audit
   reads such a commune as named in part. A merger never moves an aire: a
   commune of today drawn whole for a row that names its seat is a finding.
6. The polygon-vs-polygon audits still run on every geometry change
   (`scripts/validate_release.py` without `--quick` runs them all).

## Reference QA

For a visitor flag with a reference map, open the record on the site at the
flagged zoom (`scripts/serve.py` + Playwright, memory
`feedback_headless_map_check`) next to the reference. Note what differs, then
find the public source that settles it. The reference is never the source.
