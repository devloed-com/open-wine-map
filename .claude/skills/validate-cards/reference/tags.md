# Failure-mode tags (`audit_cards_llm.TAGS`)

Bullet-level (shared with `audit_terroir_facts_llm.py`): wrong-entity,
unsupported-causal-link, invented-detail, wrong-number-or-unit, wrong-direction,
hedge-dropped-or-changed, sibling-or-subzone-confusion, narrowed-attribution,
added-qualifier, mistranslation, untranslated-term, label-fragment, duplicate,
misfiled-subsection, tautology.

Header / roster / style / area:

| tag | usually means |
|---|---|
| wrong-role | the regulator's principal / accessory split was not read (ES national pliego, IT annex `clause_roles`, DE BLE § 3.2) |
| missing-grape | a lexicon gap (`raw/<cc>/extraction-unknowns*.json`), a wrapped name in a table, a section the parser did not route |
| extra-grape | a fuzzy look-alike, a restated appellation name, an excluded variety read as a member, a sibling's roster |
| wrong-grape-identity | a VIVC pin on the wrong passport (`raw/vivc/slug_overrides.json`), a synonym folded to the wrong canonical slug |
| missing-style / extra-style | the style floor or a category the parser did not map (`scripts/_lib/style_taxonomy.py`, the country's `parse_styles`) |
| wrong-region | the region table of the country (`scripts/_lib/<cc>/region.py`, `fr_wine_region.py`) |
| wrong-scheme / wrong-name | `gi_terms.py`, the catalogue row (SIQO supplements, eAmbrosia index) |
| area-mismatch | the delimitation reader; cross-check with `audit_geometry_vs_text.py` |
| sibling-leak | a sub-denomination card shows a sibling's statement (stage 04 sibling filter, `terroir_chapters.py`) |
| stub-shown-as-content | a catalogue entry rendered as if it were content |
| source-not-cited / source-vintage | `_sources_for()`; a document the card used but does not link, or two documents of different vintages (→ `/validate-sources`) |
