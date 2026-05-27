"""Luxembourg-specific pipeline helpers (country #15).

LU is the project's first country whose canonical source is a single
national-spec PDF (the IVV 2020 *Cahier des charges AOP Moselle
luxembourgeoise*). It has no fetchable EU-OJ Document Unique — the
eAmbrosia entry's only publication is the Ares numeric reference
`58323`. Structurally the closest sibling is the CZ pipeline (national
spec → records, no EU-OJ document), but the LU cahier is one document
with section-letter anchors (a-j) rather than CZ's multi-decree fold.

This package carries only the Luxembourg tables: the cahier section-
keyword routing, the wine-region facet (a single region, Moselle
Luxembourgeoise), the commune-name index, and the polygon index.
"""
