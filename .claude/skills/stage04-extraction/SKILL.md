---
name: stage04-extraction
description: >-
  Move-only refactor procedure for carving functions out of
  scripts/04_build_maps.py into scripts/_lib/ modules without changing any
  build output. Use when executing Phase 6 of the improvements plan
  ("extract augmenters", "modularize stage 04") or any time a function
  must move out of 04_build_maps.py / map_template.py. The danger this
  skill defends against: stage 04 failures are often SILENT (a country or
  feature just disappears from the map), so verification relies on the
  golden-output comparator, not on "it didn't crash".
---

# stage04-extraction

## Iron rules

1. **Move, never edit.** The function body is copied verbatim. No renames,
   no cleanups, no type-hint additions, no f-string fixes — those are
   separate commits OUTSIDE this skill.
2. **One module per commit.**
3. **The build output is the test.** A move is proven correct only by
   `scripts/compare_build_output.py` reporting `identical` after a full
   stage-04 rebuild (Task "final proof" below). py_compile + pytest are
   intermediate gates only.

## Prerequisite

A golden snapshot must exist (plan Phase 0):
`tmp/golden-before/` populated from the CURRENT `wiki/` output, and
`scripts/compare_build_output.py` present. If missing, create them first —
never extract without a golden snapshot.

## Procedure (per module)

1. **Map the block.** Identify the function(s) to move and EVERYTHING they
   reference: module-level constants, helper functions, imports. Use:
   ```
   grep -n "<name>" scripts/04_build_maps.py
   ```
   for every symbol used inside the body. A symbol used by BOTH the moved
   block and remaining code stays in a shared location (move it to the new
   module and import it back, or leave it and import it into the new
   module — prefer whichever produces fewer cross-imports).
2. **Create the module** under `scripts/_lib/` (e.g.
   `scripts/_lib/augment/es.py`). Top of file: only the imports the moved
   code actually needs. Note: `_lib` modules use relative imports
   (`from .grape_lexicon import …`) — follow the pattern of existing
   `_lib` files; check one (e.g. `scripts/_lib/lieu_dit.py`) first.
3. **Replace in 04_build_maps.py** the moved block with an import near the
   other `_lib` imports:
   ```python
   from _lib.augment.es import augment_es_records_with_national_pliegos
   ```
   (Match how 04_build_maps.py already imports from `_lib` — copy an
   existing import line's style exactly.)
4. **Intermediate gates:**
   ```
   uv run python -m py_compile scripts/04_build_maps.py scripts/_lib/augment/*.py
   uv run python -m pytest -q
   uv run ruff check scripts/
   ```
   All three must pass. (04_build_maps.py cannot be imported by module
   name — it starts with a digit — hence py_compile.)
5. **Smoke the entry point** without a full build:
   ```
   uv run scripts/04_build_maps.py --help 2>&1 | head -5
   ```
   If the script has no argparse, run it for ~20 seconds and Ctrl-C after
   the record-loading phase prints; an ImportError/NameError appears
   immediately.
6. **Commit:** `refactor: extract <names> to _lib/augment/<cc>.py (no-op)`

## Final proof (once per phase, after the LAST module move)

```
uv run scripts/04_build_maps.py
uv run scripts/compare_build_output.py tmp/golden-before wiki
```

Expected: `identical`, exit 0. ANY diff = a move changed behaviour →
bisect by `git stash` / re-applying module moves one at a time. Do not
rationalize a diff away; stage 04 output is deterministic by design (the
codebase sorts set-derived structures specifically to guarantee this).

## Known coupling traps in 04_build_maps.py

- Several `augment_*` functions read module-level path constants
  (`ROOT`, `RAW`, …) defined near the top of the file — they must be
  imported or re-derived (`Path(__file__).resolve()` depth changes when
  the file moves from `scripts/` to `scripts/_lib/augment/`! Re-derive
  carefully: `parents[2]` from `scripts/_lib/augment/x.py` = repo root,
  vs `parents[1]` from `scripts/04_build_maps.py`).
- `_backfill_it_nonstub_from_masaf` is a private helper of the IT
  augmenter — moves with it.
- `synthesize_it_sottozone_records` is called between other IT steps in
  `main()`; preserve call ORDER in main() exactly.
- tqdm/print progress lines inside moved functions stay verbatim (curators
  grep build logs for them).
