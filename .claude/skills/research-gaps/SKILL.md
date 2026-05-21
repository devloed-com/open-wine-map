---
name: research-gaps
description: >-
  Fill gaps in open-wine-map curation data — missing Wikipedia tooltip cards,
  unresolved VIVC slugs, wines or AOCs with no source document — by detecting
  the gap, generating a self-contained web-research prompt, dispatching it to
  research agents (WebSearch + WebFetch) inside Claude Code, and staging the
  findings for review before they land in an overrides file. A Claude
  browser-extension prompt is emitted only for the subset of sources an agent
  cannot reach (WAF-blocked EUR-Lex, JavaScript-only search UIs). Use when an
  audit reports `missing` / `error` records, `vivc_id: null` entries, stub
  wines, or AOC cahier stubs — or when the user asks to research, look up, or
  fill missing curation data.
---

# research-gaps

Find missing open-wine-map curation data and recover it through a four-stage
round trip: **detect → generate prompt → dispatch → stage for review**.

Most research runs inside Claude Code via `general-purpose` agents that have
`WebSearch` + `WebFetch` — no copy-paste. A Claude browser-extension prompt is
written *only* for the residual items an agent cannot reach (WAF challenges,
JS-only search UIs). Findings are always **staged for review**; the skill
never writes an overrides file without explicit confirmation.

## Invocation

- `/research-gaps <gap-type>` — research a known gap. Gap types are listed in
  [reference/gap-types.md](reference/gap-types.md).
- `/research-gaps` — no argument: run the detect command for each gap type,
  print open counts, ask the user which to research.
- `/research-gaps --import <results-file>` — resume after a browser run:
  parse the pasted browser-extension results and continue at stage 4.
- `/research-gaps <free-form description>` — a gap not in the registry:
  define a new gap-type entry with the user, then proceed.

If a `tmp/<gap>-research-prompt.md` already exists from a previous run, offer
to dispatch it as-is instead of regenerating.

## Hard rules

- **Public, licence-clear sources only.** This is the project's first
  invariant (see CLAUDE.md). Accept only public sources — Wikipedia, VIVC
  (vivc.de), INAO / JORF / BO Agri, EUR-Lex, eAmbrosia, IVV, MASAF, national
  and regional gazettes, consejo / consorzio regulador sites. Reject
  paywalled material, scraped third-party narrative wikis, and proprietary
  teaching content. If a finding cannot point at a public source, drop it.
- **Never auto-write overrides.** Always stage results and get explicit
  confirmation first (project preference: stage for review).
- **Never invent a plausible title or URL.** A confident `NONE` is a valid,
  useful result — it tells the curator to stop retrying the fetch. Research
  that cannot ground a finding in a real page returns `NONE`.
- **Check identity.** A found page must be about the *same* variety / wine /
  AOC the gap means — cross-check grapes against VIVC, wines against the GI
  file number, AOCs against the appellation name. A homonym place or person
  does not count.
- **Triage before generating.** A raw `missing`/`error` scan over-counts
  badly (e.g. ~744 ES grape records, but only ~39 are actionable — the rest
  are non-Iberian varieties with genuinely no Spanish article). Filter to
  the items that are actually cited in the relevant corpus before building a
  prompt, and confirm the final count with the user.

## Procedure

### 1 — Detect the gap

Look the gap type up in [reference/gap-types.md](reference/gap-types.md) and
run its **detect** command. Then **triage**:

- Drop items that are out of scope (e.g. grapes not cited in that country's
  pliegos — cross-reference the gap type's audit script).
- If the actionable count is still large (> 60), show the count and confirm
  scope with the user before generating — research agents cost tokens.

### 2 — Generate the research prompt

Write `tmp/<gap-type>-research-prompt.md` using the template in
[reference/prompt-template.md](reference/prompt-template.md). It must be
**fully self-contained** — context, the public-source rule, search-priority
order, the item list, and the output format — because a research agent (and
the browser Claude) has no repo context.

### 3 — Dispatch (hybrid)

**Default — research agents:**

- Chunk the item list into groups of ~10.
- Spawn one `general-purpose` agent per chunk, **all in one message** so they
  run in parallel. Give each agent its slice of the prompt; tell it to use
  `WebSearch` + `WebFetch` and return rows in the exact output format.
- Instruct every agent: if a candidate source answers with a WAF / CAPTCHA /
  JavaScript challenge or a login wall it cannot get past, mark that item
  `UNREACHABLE` with the blocked URL — do not guess.
- Each agent's final message returns to you directly. No copy-paste.

**Browser fallback — residual only:**

- Collect every item agents marked `UNREACHABLE`. Also route here any gap
  type flagged `WAF risk: high` in the registry (e.g. BO Agri's SPA search) —
  agents will likely fail those, so they can go straight to the browser.
- If the residual is **non-empty**, write `tmp/<gap-type>-browser-prompt.md`
  scoped to just those items, then tell the user:

  > Run `tmp/<gap-type>-browser-prompt.md` in the Claude browser extension,
  > paste the reply into `tmp/<gap-type>-browser-results.md`, then re-invoke
  > `/research-gaps --import tmp/<gap-type>-browser-results.md`.

- If the residual is **empty**, skip the browser entirely.

### 4 — Stage results for review

- Write every finding (agent results + any imported browser results) to
  `tmp/<gap-type>-research-results.md`, verbatim.
- Build a review table: `item | FOUND / NONE | proposed value | identity note`.
- For `FOUND` rows show the exact overrides-file edit you propose; for `NONE`
  rows show the `CURATOR_TODO.md` line you propose.
- Present the table. **Stop and ask the user to confirm.** Do not write any
  repository file yet.

### 5 — Apply on confirmation

Only after the user confirms:

- `FOUND` rows → merge into the gap type's **overrides target** file. Add
  keys only; preserve existing ordering / sorting and schema.
- `NONE` rows → append a dated line under the matching country / mechanism
  section of `CURATOR_TODO.md` (no prose — see the project's curator-file
  convention) so the fetch is not retried blindly.
- Report what changed and the re-run command the gap type's `reference/`
  entry names (usually the consuming stage, then `04_build_maps.py`).
- Leave the `tmp/` prompt and results files in place — they are the
  provenance trail. Mention their paths.

## Notes

- The `tmp/` directory is a working directory and already holds prior
  research prompts (`tmp/es-grape-wikipedia-research-prompt.md`, etc.) —
  match that naming.
- This skill stages data; it does not run the pipeline. After the user
  confirms an apply, hand back the re-run command rather than running it
  unprompted.
