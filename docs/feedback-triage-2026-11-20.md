# Visitor feedback triage — 2026-11-20

Queue: `scripts/feedback_report.py --range 2026-11-17,2026-11-20`. New since
the 2026-11-17 triage: one flag, retracted within the hour, no note, no name
offered for credit, no e-mail-link click.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Saint-Joseph, 2026-11-17 22:00, retracted | boundary | en · footprint z9.9 | no defect found |

## Saint-Joseph — boundary, footprint band

A retracted flag is not proof of no defect, so the surface was checked in the
flag's locale and zoom band:

- `audit_geometry_vs_text.py --only saint-joseph`: OK. `geom_source` is
  `parcellaire`, which is INAO's own delimitation.
- `audit_parcellaire_gaps.py --only saint-joseph`: every commune of the aire
  has a parcel row in the 2026-10-19 release, so there is nothing to fill.
- `audit_vineyard_envelopes.py --only saint-joseph --water`: at z9.9 the map
  draws the generalised footprint. Parcels 33.4 km² (781 parts), footprint
  51.8 km² (1.55×), contained within tolerance. It bridges 0.08 km² onto
  Condrieu's parcels (0.2 % of the footprint) and holds 0.03 km² of BD TOPO
  water. It does not cross the Rhône.
- Headless Chromium on production, `/en/saint-joseph` and `#9.9/…` at the
  northern, middle and southern ends, plus `#12/45.36/4.77`. The footprint
  follows the right-bank strip from Chavanay / Malleval / Saint-Pierre-de-Bœuf
  down to Tournon and Guilherand-Granges. The lobe beside it at Condrieu /
  Ampuis belongs to Condrieu / Côte-Rôtie (it lies outside Saint-Joseph's
  bbox, which ends at 45.439° N). At z12 the parcels draw as expected. The
  card shows the Syrah / Marsanne / Roussanne roster and the terroir facts.

Failure mode: none identified. The flag names no detail and the visitor
withdrew it. The three detectors and the rendered view all agree with INAO's
delimitation, so it is isolated.

## Changes

None. No CURATOR_TODO row, no contributor added.
