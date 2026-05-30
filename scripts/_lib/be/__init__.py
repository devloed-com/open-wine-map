"""Belgium-specific pipeline helpers (country #16).

Siblings of `scripts/_lib/sk/` — the Belgian pipeline clones the Slovak /
Slovenian one structurally (EU-OJ single-document HTML, Latin script,
Bétard PDO geometry, PGI = region-union). The wrinkle is **per-record
source_lang**: the 5 Flemish PDOs + the cross-border Maasvallei wine
use `nl`; the 4 Walloon PDOs use `fr`. This is the second country in
the corpus to use per-record source_lang (Switzerland was first); see
`scripts/_lib/ch/` for the precedent.

This package carries the Belgian tables: the ENIG DOCUMENT (NL) +
DOCUMENT UNIQUE (FR) keyword routing, the Vlaanderen/Wallonie region
facet, and the polygon index.
"""
