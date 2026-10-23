# Where a finding goes

| card section | owner | fix lands in |
|---|---|---|
| name, classification | catalogue + `scripts/_lib/gi_terms.py`, `traditional_terms.json`, `siqo_supplements.json` | a cited pin or a table row |
| region | `scripts/_lib/<cc>/region.py`, `scripts/_lib/fr_wine_region.py` | the region table |
| styles | the country's `parse_styles`, `scripts/_lib/style_taxonomy.py`, the stage-04 style floor | parser / taxonomy; `audit_styles.py --strict` after |
| grapes | the country's variety parser, `scripts/_lib/grape_lexicon.py`, `grape_entity.py` guards, `raw/vivc/slug_overrides.json`, `grape_display_overrides.json` | re-extract with a snapshot and a per-record grape diff (`scripts/diff_records.py`); `audit_grape_identity.py`, `audit_vivc_coverage.py --strict` |
| area | the delimitation reader, `aires_supplements.json`, `parcellaire_gap_fills.json`, the geometry overrides | `audit_geometry_vs_text.py`, the geometry audits |
| terroir_facts | the feedback sidecar (`build_terroir_feedback.py`), then `rerun_terroir_facts.py` for the scope | never the cache by hand |
| summary | stage 02's summary pick / 02c translation | parser; 02c `--only` |
| sub_denomination | `dgc_rules.py`, `shared_cahier.py`, `sottozona_rules`, the inherited-facts sibling filter | parser / stage 04 |
| sources | `_sources_for()` in 04, the country's manifest | stage 01 / 01c re-fetch |

Every row of the curator Markdown the script emits carries the failure-mode
tag and a "sweep" cell: fill it ("isolated" / "N more: …") before the row
enters CURATOR_TODO.md.
