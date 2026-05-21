# Research task — find the correct pt.wikipedia.org article for 27 Portuguese wine appellations

## Context

I maintain open-wine-map, a wine-appellation reference built **only** from
public, licence-clear regulator data. For each Portuguese wine appellation
(DOP / IGP) the map shows a tooltip card sourced from the appellation's
**pt.wikipedia.org** article. An automated title-cascade tried to resolve
each appellation slug to a Portuguese Wikipedia page and failed for 27 of
the 44 PT appellations. Two distinct failure modes:

- **`missing`** — the cascade found no page at all under the titles it tried.
- **`not_aoc_topic`** — the cascade resolved to a page that is *not* about
  the wine appellation (a homonym town, island, river, or — in one case — an
  unrelated person). The wrong page it landed on is given below as `rejected`.

I need the **correct Portuguese Wikipedia article** about the **wine
appellation / wine region / wine** itself.

## What I need from you

For each appellation below, search and return one of:

1. **FOUND** — a real pt.wikipedia.org article unambiguously about *this*
   wine appellation, wine region, or the wine itself. Give the exact page
   title and the full URL.
2. **NONE** — no public pt.wikipedia.org article exists about this
   appellation as a wine topic. Say so, and note the closest wrong page.

Search in priority order:

1. **pt.wikipedia.org** — try the bare appellation name, then disambiguated
   forms: `<name> (vinho)`, `<name> (DOP)`, `<name> (IGP)`,
   `<name> (região vinícola)`, `<name> (sub-região)`, and the descriptive
   forms `Vinho de <name>`, `Vinho do <name>`, `Vinho da <name>`,
   `Região vinícola do <name>`, `Região Demarcada do <name>`. Also follow
   Wikipedia redirects and check the disambiguation page if the bare name
   is taken by a town/island/river.
2. If pt.wikipedia.org genuinely has no wine article, that is a **NONE** —
   do not substitute an article from another language Wikipedia.

**Identity check:** the article must be about the wine appellation / wine
region / the wine — its lead should mention *vinho*, *DOP* / *IGP* /
*Denominação de Origem* / *Indicação Geográfica*, *região vitivinícola*,
*castas*, or *vinho regional*. An article about the homonym municipality,
island, civil parish (freguesia), river, or historical province does **not**
count — those are exactly the wrong matches the cascade already made. If the
town article has a substantial "Vinho" / "Vitivinicultura" section but there
is no dedicated wine article, treat that as NONE (a section is not a page).

A confident **NONE is a useful answer.** Do not invent a plausible-looking
title or URL — only return FOUND when you have opened the page and confirmed
it is about the wine.

If a source blocks you with a JavaScript / CAPTCHA / WAF challenge or a login
wall you cannot get past, return that item as **UNREACHABLE** with the URL
you were blocked on — do not guess.

## The 27 appellations

| slug | appellation | kind | region | failure | rejected page |
|---|---|---|---|---|---|
| alenquer | Alenquer | DOP | Lisboa | missing | — |
| alentejano | Alentejano | IGP | Alentejo | missing | — |
| beira-interior | Beira Interior | DOP | Beira Interior | missing | — |
| bucelas | Bucelas | DOP | Lisboa | not_aoc_topic | Bucelas (the freguesia / town) |
| carcavelos | Carcavelos | DOP | Lisboa | not_aoc_topic | Carcavelos (the freguesia / town) |
| colares | Colares | DOP | Lisboa | missing | — |
| dao | Dão | DOP | Dão | not_aoc_topic | Dallin H. Oaks (unrelated person) |
| do-tejo | Do Tejo | DOP | Tejo | missing | — |
| duriense | Duriense | IGP | Douro/Porto | missing | — |
| encostas-d-aire | Encostas d'Aire | DOP | Lisboa | missing | — |
| graciosa | Graciosa | DOP | Açores | not_aoc_topic | Graciosa (the island) |
| lagoa | Lagoa | DOP | Algarve | not_aoc_topic | Lagoa (the municipality) |
| lagos | Lagos | DOP | Algarve | not_aoc_topic | Lago Svínavatn (unrelated lake) |
| madeira | Madeira | DOP | Madeira | not_aoc_topic | Madeira (the island/archipelago) |
| madeirense | Madeirense | DOP | Madeira | missing | — |
| minho | Minho | IGP | Minho | missing | — |
| pico | Pico | DOP | Açores | not_aoc_topic | Pico Pinheiro (unrelated peak) |
| setubal | Setúbal | DOP | Setúbal | not_aoc_topic | Setúbal (the city) |
| tavora-varosa | Távora-Varosa | DOP | Dão | missing | — |
| tejo | Tejo | IGP | Tejo | not_aoc_topic | Rio Tejo (the river) |
| terras-da-beira | Terras da Beira | IGP | Beira Interior | missing | — |
| terras-de-cister | Terras de Cister | IGP | Beira Interior | missing | — |
| terras-do-dao | Terras do Dão | IGP | Dão | missing | — |
| terras-madeirenses | Terras Madeirenses | IGP | Madeira | missing | — |
| torres-vedras | Torres Vedras | DOP | Lisboa | not_aoc_topic | Torres Vedras (the municipality) |
| transmontano | Transmontano | IGP | Trás-os-Montes | missing | — |
| tras-os-montes | Trás-os-Montes | DOP | Trás-os-Montes | not_aoc_topic | Trás-os-Montes e Alto Douro (historical province) |

Hints (do not treat as answers — verify each):
- `madeira`, `setubal` are famous fortified wines — there is very likely a
  dedicated wine article (e.g. *Vinho da Madeira*, *Moscatel de Setúbal*).
- `dao`, `bucelas`, `carcavelos`, `colares` are classic Portuguese wine
  regions — look for `Vinho do Dão` / `Vinho de Bucelas` etc.
- `alentejano`, `minho`, `duriense`, `transmontano`, `terras-*` are IGP
  "Vinho Regional" categories — the article, if any, may be titled
  `Vinho Regional <name>` or be a section of the broader region's wine page.
- `do-tejo` is the DOP "Do Tejo" (formerly "Ribatejo"); a `Vinho do Ribatejo`
  or `Tejo (vinho)` article may exist.

## Output format

One line per appellation, pipe-delimited. Group FOUND rows first, then NONE,
then UNREACHABLE:

    slug | FOUND       | <exact pt.wikipedia.org page title> | <full URL> | <one sentence from the lead proving it is the wine appellation>
    slug | NONE        | —                                   | —          | <closest wrong page you found / why no wine article exists>
    slug | UNREACHABLE | —                                   | <blocked URL> | <challenge type>
