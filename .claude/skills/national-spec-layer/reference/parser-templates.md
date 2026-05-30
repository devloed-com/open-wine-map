# Sibling-template selection

Pick the closest existing country by the **source document's shape**, then
read that country's three files (`scripts/<sib>/01c_*.py`,
`scripts/_lib/<sib>/specifikacija.py`, `scripts/<sib>/02f_*.py`) as the live
template. The 01c fetch + 02f extract are ~95% reusable across all of them;
the parser's **section-slicing strategy + keyword tables** are what differ.

| `source_format` | Sibling | Parser strategy | Notes |
|---|---|---|---|
| `pdf-numbered` | **bg** (`iavv-specifikacija-v1`) | line-anchored `^N.` numbered sections, monotonic-progression guard; grapes colour-split (`за бели/червени`) | cleanest copy target; all-PDF, `pdftotext -layout` |
| `pdf-numbered` + commune list | **ro** (`onvpv-caiet-de-sarcini-v1`) | Roman-numeral outline; **also merges `geo_communes`** so IGPs resolve via GISCO commune-union | use when the spec enumerates the commune list and the country has IGPs needing geometry |
| `doc-lettered` | **hr** (`mps-specifikacija-v1`) | `^[a-j])` lettered slicer + a keyword-section fallback for docx; `.doc` via the shared `owm-antiword` Docker image | multi-format (.doc/.docx/.pdf); note HR/SI use the `specifikacija_url` provenance key, not `national_spec_url` |
| `pdf-lettered` (name/synonym table) | **sk** (`upv-sr-specifikacia-v1`) | HR's `^[a-i])` lettered slicer (over a PDF, not .doc) + BG's PDF/01c/02f mechanics; the §f variety section is a **two-column `Odroda \| Synonymum` table** under `MUŠTOVÉ BIELE`/`MODRÉ` colour-bucket labels — take ONLY the left (canonical) column: strip the glued bucket prefix, split on the ≥2-space column gutter, keep Title-Case + comma-free + ≤4-word tokens. This drops synonym-continuation lines, ALL-CAPS bucket labels, and intro prose without polluting the unknowns queue, AND sidesteps synonym-identity confusion (SK Pesecká leánka ↔ Feteasca regala) by never feeding the synonym column to the matcher | use when the regulator ships a lettered PDF whose variety list is a name/synonym table rather than a flat colour-split list |
| `mixed` (pdf+doc+docx+html) | **gr** (`gr-national-{pdf,doc,docx}`) | role-keyword section splitter reused across formats + a capitalised-token grape scan for prose `.doc` | when the regulator ships heterogeneous formats |
| `national-tables` (no per-wine spec) | **cz** | parses 1–2 national decrees (variety table + per-region commune table) applied to all wines | use only when no per-wine spec exists; terroir is usually absent (CZ produced 0 bullets) — flag to the user, it may fail the terroir bar |

## Format-conversion helpers (reused verbatim from any 02f sibling)

- `.pdf` → `pdftotext -layout -enc UTF-8`
- `.doc` → `owm-antiword` Docker image
  (`docker build -t owm-antiword:latest -f scripts/si/Dockerfile.doc-converter scripts/si/`)
- `.docx` → stdlib `zipfile` → `word/document.xml` strip (drop `<w:pPr>` first)
- `.html` → read text / strip tags

## Parser skeleton — what to keep vs. replace

Keep (mechanical): the section slicer, `match_variety` grape resolution, the
colour-marker → grape-list loop, `_parse_styles`, `derive_summary`, and the
output dict shape (`summary` / `grapes` / `geo_area_brief` / `link_to_terroir`
/ `section_roles` / `section_titles` / `styles` / `n_sections` /
`parser_template`).

Replace (per-country, the TODO): the `_ROLE_KEYWORDS` / section-title tables
(the regulator's own language), the colour-marker regex (the local "white /
red / rosé" phrasing), and any style markers. Tune these against 1–2 sample
specs before sweeping `--all`.

## Script + non-Latin gotchas

- Cyrillic / Greek: comparisons via `.casefold()`, never NFKD-ASCII (which
  erases the script). For grape aliases, `ъ`/`ь` romanise to an apostrophe
  under `unidecode` (`Гъмза`→`g'mza`) so the alias key must carry the
  apostrophe, not the slugify-hyphen form. See `[[project_cyrillic_handling]]`.
- Unknown varieties flow to `raw/<cc>/extraction-unknowns-specifikacije.json`;
  feed them to the `grape-colour-researcher` agent, then fold into
  `scripts/_lib/grape_lexicon.py` (GRAPE_ALIAS + DEFAULT_COLOUR) before the
  final 02f re-run.
