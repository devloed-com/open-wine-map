"""Netherlands-specific pipeline helpers (country #17).

Siblings of `scripts/_lib/sk/` — the Dutch pipeline clones the Slovak
template structurally (EU-OJ single-document HTML, Latin script,
Bétard PDO geometry where present, PGI = province-wide territory). The
single delta from SK is that all 12 NL PGIs are coextensive with a
single Dutch province (Limburg, Gelderland, Zeeland, Noord-Brabant,
Zuid-Holland, Noord-Holland, Utrecht, Overijssel, Flevoland, Drenthe,
Groningen, Friesland) and resolve via a **GISCO LAU 2024 province-
union** (mirrors the AT Bundesland-union pattern); 4 newer PDOs that
post-date Bétard 2022 resolve via a commune-list union on the same
GISCO layer.

`source_lang` is `"nl"` for every record — this is the first single-
source-lang NL pipeline in the corpus. Belgium (`be`) introduced
per-record `source_lang` with `"nl"` for Flemish wines; the NL pipeline
shares all the Dutch downstream infrastructure (02b Wikipedia cache,
02e translation glossary, locale catalog) that BE put in place.
"""
