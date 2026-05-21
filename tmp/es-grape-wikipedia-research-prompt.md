# Research task — Spanish-Wikipedia titles for 39 Iberian grape varieties

## Context

I maintain a wine-appellation reference (open-wine-map). The map's grape
"pills" carry a short tooltip extract fetched from Wikipedia. For the
Spanish-language map (`es.wikipedia.org`) the fetcher derives a title
from the grape's internal slug and queries that page.

**39 grape varieties cited in Spanish wine pliegos got no usable
`es.wikipedia.org` card.** Two failure modes:

- **`missing`** — no page resolved at the slug-derived title. Either
  the variety's es.wikipedia article lives at a different title (a
  disambiguator, an accent, a regional spelling) or there is genuinely
  no article.
- **`not_grape_topic`** — a page resolved but it was about something
  else (a place, a surname, a generic word) — a disambiguation
  collision. These almost always need a `(uva)` / `(vino)` style
  disambiguated title.

These are mostly Canary-Islands, Galician, Catalan and Balearic
varieties — genuinely obscure, so for several the honest answer will be
"no article exists". The point of this task is to separate **wrong
title** (recoverable — give me the real URL) from **no article**.

## What I need from you

For each of the 39 slugs below, search `es.wikipedia.org` and return
one of:

1. **A real article** about *this grape variety* → give the exact page
   title and full URL. The article must clearly be about the wine
   grape, not a homonym place/person.
2. **No article** → say so. If a closely-related article exists (e.g.
   the variety is only covered as a redirect target or inside a parent
   variety's article), note that and give its URL.

Watch for: regional-name vs canonical-name (the pliego often uses a
local synonym); accent/spelling drift (`ñ`, `ç`, Catalan vs Castilian
forms); and the `(uva)` disambiguator es.wikipedia uses for grapes that
share a name with a town. Cross-check identity against the **Vitis
International Variety Catalogue** (`vivc.de`) when a slug is ambiguous,
so the article you pick is the same DNA variety the pliego means.

## The 39 varieties

`missing` (no page resolved):

```
albarin-tinto · albillo-criollo · alfrocheiro · bastardillo-chico ·
caino-longo · corropio · escursac · espero-de-gall · estaladina ·
gajo-arroba · giro-negre · giro-ros · gorgollassa · izkiriota ·
marselan · petit-courbu · pirene · rabigato · ratino-gallega ·
tinto-fragoso · tinto-jeromo · valenci-tinto · vidadillo · vinyater ·
xarello-rosado
```

`not_grape_topic` (resolved to a non-grape page — needs a disambiguated title):

```
castanal · cenicienta · doradilla · garro · gonfaus ·
malvasia-volcanica · molinera · morisca · oneca · tinto-velasco ·
tortosi · verdello · verdil · vijariego-negro
```

## Output format

For each slug return one line:

```
slug | FOUND  | <exact es.wikipedia title> | <full URL>        | <one-line identity note + VIVC # if checked>
slug | NONE   | —                          | —                 | <what you found instead, if anything>
```

Group the `FOUND` rows first (those are the actionable ones — they
become per-locale title overrides) and the `NONE` rows after.

A confident `NONE` is a useful result — it tells me to register the
variety's canonical slug without a tooltip rather than keep retrying
the fetch. Do not invent a plausible-looking title.

---

_Note for the curator: regenerate this list against the post-fetch
state — it was built before the synonym-aware 02b grape re-fetch
finished, which may recover some `missing` entries automatically.
`scripts/audit_es_grape_aliases.py` plus the `missing`/`error` records
under `raw/wikipedia/grapes/es/` give the current set._
