# Test fixtures

Short, redacted excerpts of **public, licence-clear** regulator documents used
to pin parser behaviour. These are extracts of INAO cahiers des charges, EU-OJ
single documents (documento único), and national product specifications —
already public sources under the project's licence rules.

Rules:
- Keep each fixture SHORT (< ~200 lines): the minimal section the parser routes
  on, not the whole document.
- Name as `<cc>_<template-or-variant>_<slug-ish>.txt` (pdftotext output) or
  `.html` (OJ pages). E.g. `fr_section10_chablis.txt`, `es_jccm_mentrida.txt`.
- Redact anything not needed for the assertion.
- A purely synthetic fixture (no source document available) must carry a
  `# synthetic` header comment on its first line.
- Never commit whole documents or anything copied straight out of `raw/`.

Consumed by `tests/test_<cc>_parser.py` via the `fixture_text` fixture in
`tests/conftest.py`.
