"""Romania-specific pipeline helpers (country #9).

Siblings of `scripts/_lib/hr/` and `scripts/_lib/hu/` — the Romanian
pipeline clones the Croatian template (EU-OJ single-document HTML in
the national language, Latin script with diacritics, Bétard PDO
geometry). Differences from HR: 13 IGPs (HR had zero), 3 newer PDOs
missing from Bétard 2022 — both resolved by the new `gisco-commune-list`
fallback (ES pattern) against the shared Eurostat GISCO LAU. The EU-OJ
template anchor is "DOCUMENT UNIC". This package carries the Romanian
keyword tables, the 8-borrégió-equivalent wine-region facet, the
commune-precise polygon index, and the Romanian commune-list parser.
"""
