---
name: ruff-zero
description: >-
  Drive open-wine-map's ruff error count to zero WITHOUT changing behaviour.
  Use when executing Phase 1 of the improvements plan, or whenever
  `uv run ruff check scripts/ tests/` reports errors. Covers the safe
  procedure for each rule class present in this repo (F401, F541, F601,
  E741, E702, E731, F841, E402), with a mandatory special procedure for
  F601 duplicate keys in scripts/_lib/grape_lexicon.py — those are DATA,
  not style, and blind deletion can silently change grape-synonym folding.
---

# ruff-zero

Goal state: `uv run ruff check scripts/ tests/` → `All checks passed!` and
`uv run python -m pytest -q` → all pass, after EVERY commit.

## Order of operations

1. `uv run ruff check scripts/ tests/ --fix` (auto-fixes F401 unused
   imports, F541 empty f-strings). Run pytest. Commit:
   `fix: ruff auto-fixes (unused imports, empty f-strings)`
2. F601 in `scripts/_lib/grape_lexicon.py` — see special procedure below.
   Own commit.
3. Remaining classes, ONE RULE CLASS PER COMMIT, pytest between each:
   - **E741** (`l`, `I`, `O` as names): rename to something contextual
     (`l` → `line`, `lst`, `layer`, `lon`…). Rename ONLY within the
     function scope shown by ruff; use exact-match find within that
     function, never file-wide sed.
   - **E702** (semicolon-joined statements): split onto separate lines,
     same indentation.
   - **E731** (lambda assignment): convert to a `def` with the same name.
   - **F841** (unused variable): if the right-hand side has side effects
     (function call), keep the call and drop the assignment; if pure,
     delete the line.
   - **E402** (import not at top): only move the import if nothing between
     file top and the import mutates `sys.path` or env that the import
     needs. In this repo several scripts do
     `sys.path.insert(0, …/scripts)` BEFORE importing `_lib` — those
     imports must stay put; silence with `# noqa: E402` instead.

## F601 special procedure (grape_lexicon.py)

Each finding = the same dict key literal appears twice. Python keeps the
LAST one. This file maps grape-name slugs to canonical slugs — a wrong
deletion changes which VIVC identity a grape folds into.

Per finding:

1. Find BOTH occurrences: `grep -n '"<key>"' scripts/_lib/grape_lexicon.py`
2. Compare the two VALUES.
   - **Identical values** → delete the LATER occurrence (the one ruff
     points at). If the later line carries a more informative comment
     (e.g. a VIVC number), move that comment to the surviving line.
   - **Different values** → DO NOT TOUCH. Append the key + both
     line numbers + both values to a report list and continue. These are
     real data conflicts requiring VIVC research (hand off to the
     `grape-colour-researcher` agent or a human).
3. After all findings:
   ```
   uv run ruff check scripts/_lib/grape_lexicon.py --select F601
   uv run python -m pytest -q        # tests/test_no_duplicate_keys.py guards semantics
   ```
4. Commit: `fix: dedupe repeated grape_lexicon keys (identical-value F601s)`
   — include the skipped-conflict report (if any) in the commit body.

## Freezing at zero

After all classes are clean, add to `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "W"]
```

Run the check again — adding `W` may surface new findings; fix them the
same way (one class per commit). Do NOT add rule families beyond E/F/W
without being asked.

## Pitfalls

- Never run file-wide search-replace for renames; ruff gives exact
  line/col — edit surgically.
- `scripts/04_build_maps.py` and `scripts/_lib/map_template.py` are
  5.9k/4k lines; load only the relevant region (read_file with offset),
  not the whole file.
- If pytest fails after a change, `git checkout -- <file>` and redo that
  single finding; do not stack fixes on a broken tree.
- `done2.json` / `todo.json` in the worktree are translation round-trip
  artifacts — never commit them.
