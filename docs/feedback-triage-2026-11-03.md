# Visitor feedback triage — 2026-11-03

Queue: `scripts/feedback_report.py --range 30d`. New since the 2026-10-30
triage: one flag, retracted within the hour, no note, no name offered for
credit. The one e-mail-link click of the period is of 2026-10-09 04:00 (the
sidebar link, es locale, no card) and was inside the 2026-10-11 window.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Vouvray, 2026-11-01 13:00, retracted | boundary | fr · footprint z8.6 | no defect found |

## Vouvray — boundary, footprint band

A retracted flag is not proof of no defect, so the surface was checked in the
flag's locale and zoom band:

- `audit_geometry_vs_text.py --only vouvray`: OK — the polygon covers the
  eight communes of the cahier's aire (Chançay, Noizay, Parçay-Meslay, Reugny,
  Rochecorbon, Tours, Vernou-sur-Brenne, Vouvray), nothing missing, nothing
  extra. `geom_source` is `parcellaire`: the INAO delimitation itself.
- `audit_parcellaire_gaps.py --only vouvray`: every aire commune carries a
  parcel row in the 2026-10-19 release; no gap, no pin needed.
- `audit_vineyard_envelopes.py --only vouvray`: the z8.6 view is the
  generalised footprint (r = 250 m). Parcels 32.2 km², footprint 47.5 km²
  (1.48×, median for the corpus), contained within tolerance, bridging onto
  a neighbour's parcels 0.0 % — the shape leaks neither onto Montlouis across
  the Loire nor onto Touraine around it.
- Headless Chromium on the local build, `/fr/?aocs=vouvray#8.6/47.454/0.818`:
  the footprint draws on the north bank of the Loire east of Tours and up the
  Brenne valley, the card opens with the Chenin / Orbois roster the cahier
  states and its terroir facts. The live panel payload
  (`/data/d/fr/vouvray.json`) is byte-identical to the local one.

Failure mode: none identified. Isolated: the flag names no detail and was
withdrawn by the visitor; the three detectors and the rendered view agree
with the cahier.

## Changes

None. No CURATOR_TODO row, no contributor added.
