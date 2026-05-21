# Research-prompt template

Fill the placeholders and write the result to
`tmp/<gap-type>-research-prompt.md`. The prompt must be **fully
self-contained** — a research agent and the browser Claude both start with
zero repo context. The browser variant (`tmp/<gap-type>-browser-prompt.md`)
is the same template scoped to the `UNREACHABLE` residual.

Keep the existing `tmp/*-research-prompt.md` files as worked examples —
`es-grape-wikipedia` (pipe-delimited output) and `it-masaf-disciplinare`
(JSON output) bracket the two output shapes.

---

```markdown
# Research task — <one line: what to find, for how many items>

## Context

I maintain open-wine-map, a wine-appellation reference built **only** from
public, licence-clear regulator data. <One short paragraph: which corpus
(FR/ES/PT/IT), what the gap is, and where the found data is used in the map.>

<If there are distinct failure modes, list them as a bullet each — e.g.
`missing` (no page resolved) vs `not_grape_topic` (resolved to a homonym).>

## What I need from you

For each <item> below, search the sources listed and return one of:

1. **FOUND** — a real <page / document> that is unambiguously about *this*
   <item>. Give the exact <title / identifier> and the full URL.
2. **NONE** — no public, licence-clear source exists. Say so, and note any
   close-but-wrong page you found instead.

Search in priority order:

1. <source 1 — most authoritative>
2. <source 2>
3. <source 3>

**Identity check:** <how to confirm it is the right item — VIVC variety
number for grapes, GI file number for wines, appellation name for AOCs>. A
page about a homonym place or person does not count.

A confident **NONE is a useful answer.** Do not invent a plausible-looking
title or URL — only return FOUND when you have opened the page and confirmed
its identity.

If a candidate source blocks you with a JavaScript / CAPTCHA / WAF challenge
or a login wall you cannot get past, return that item as **UNREACHABLE** with
the URL you were blocked on — do not guess.

## The <N> items

<A list or a table. Include every disambiguating hint you have — slug, kind,
file number, region, the rejected title a previous fetch landed on.>

## Output format

<Pick the shape that matches the gap type's overrides target.>

### Pipe-delimited (Wikipedia-title gaps)

One line per item; group FOUND rows first, NONE rows after:

    slug | FOUND       | <exact page title> | <full URL> | <identity note + VIVC # if checked>
    slug | NONE        | —                  | —          | <what was found instead>
    slug | UNREACHABLE | —                  | <blocked URL> | <challenge type>

### JSON (source-document gaps)

A JSON object ready to merge into the overrides file, keyed by slug:

    {
      "<slug>": {
        "pdf_url": "https://...",
        "source_org": "<masaf|boe|regione|consorzio|gazzetta>",
        "verification_note": "What the document is, its date / decree number, and a short quote proving it names the GI and carries the production rules."
      }
    }

For a genuine NONE, emit the slug with `"pdf_url": null` and a note on what
you found instead. An honest null beats a guess.
```
