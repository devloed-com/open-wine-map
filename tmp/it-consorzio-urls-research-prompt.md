# Research task — official websites for the consorzi di tutela / DO organisations of Italian wine appellations

## Context

I maintain open-wine-map, a wine-appellation reference built **only** from
public, licence-clear regulator data. The map's detail panel ("card") for
each appellation shows a link to the official site of the body that
administers that denominazione — for France an *interprofession* /
*syndicat*, for Spain a *consejo regulador*. The Italian equivalent is the
**Consorzio di tutela** (the protection-and-promotion consortium for a DOP /
DOCG / IGT).

France and Spain already have this link curated. **Italy has none.** This
task collects the official-website URL for the organisation behind each of
the 531 Italian wine appellations, so the Italian cards reach parity.

There are two kinds of item below:

- **CONSORZIO items** — the EU register (eAmbrosia) names a consorzio for
  the appellation. The consorzio name is given; find that consorzio's
  official website. One website covers every appellation that consorzio
  administers.
- **WINE items** — eAmbrosia names no consorzio. Find the consorzio di
  tutela responsible for that specific appellation, or confirm none exists.

## What I need from you

For each item below, search the sources listed and return one of:

1. **FOUND** — the official website of the consorzio di tutela (or, where a
   consorzio genuinely does not exist, the official DOP/IGT body — a
   regional *istituto*, *camera di commercio* protection office, or the
   regulating regional authority). Give the exact organisation name and the
   full homepage URL.
2. **NONE** — no public consorzio / DO-organisation website exists for this
   appellation. Say so, and note any close-but-wrong page you found instead
   (a single winery, a wine-shop, a generic tourism page — those do **not**
   count).

Search in priority order:

1. **The consorzio's own website** — Italian consorzi di tutela almost all
   run a public site (often `consorzio<nome>.it`, `vini<nome>.it`,
   `<nome>wine.it`, or similar). A web search for the exact consorzio name
   usually lands it directly.
2. **Federdoc** (`federdoc.com`) — the national federation of Italian wine
   consorzi di tutela; its members directory lists consorzi with links.
3. **The MASAF** (Italian Ministry of Agriculture, `masaf.gov.it`) list of
   *consorzi di tutela riconosciuti* (recognised consortia) — authoritative
   for which consorzio is *erga omnes* recognised for a given DOP/IGT.
4. **The regional authority** (Regione, or bodies such as the Istituto
   Marchigiano di Tutela Vini, INCAVI-equivalent regional institutes) — for
   appellations administered by a regional institute rather than a
   stand-alone consorzio.

**Identity check:** the site must be the body that *administers / protects*
the named appellation(s) — its homepage or "chi siamo" page should name the
denominazione(s), or it must be listed against that DOP/IGT by Federdoc or
MASAF. A producer's commercial site, a wine e-commerce site, a regional
tourism portal, or a Wikipedia article does **not** count. For CONSORZIO
items, confirm the site matches the consorzio name given (allow for the
consorzio having modernised or shortened its name).

A confident **NONE is a useful answer.** Many small IGTs and older DOPs have
no consorzio at all. Do not invent a plausible-looking URL — only return
FOUND when you have opened the page and confirmed its identity.

If a candidate source blocks you with a JavaScript / CAPTCHA / WAF challenge
or a login wall you cannot get past, return that item as **UNREACHABLE**
with the URL you were blocked on — do not guess.

## Output format

One row per item, pipe-delimited. Group FOUND rows first, then NONE, then
UNREACHABLE. The `ITEM_ID` is the value in the **ID** column of the item
list (a `C###` code for CONSORZIO items, the wine `slug` for WINE items).

    ITEM_ID | FOUND       | <official organisation name> | <homepage URL> | <one-line identity note: how you confirmed it>
    ITEM_ID | NONE        | —                            | —              | <what you found instead, if anything>
    ITEM_ID | UNREACHABLE | —                            | <blocked URL>  | <challenge type>

The `<official organisation name>` becomes the link label shown on the card,
so give the consorzio's normal public name (e.g. `Consorzio Tutela Vini
d'Abruzzo`), not a slogan.

## Item list

The full list is below for reference. Each dispatched research agent is
given only its own slice. CONSORZIO items list the appellations the
consorzio covers (for your identity check); WINE items list the single
appellation, its DOP/IGT kind, and its region where known.

_(items injected per-agent — see the dispatched slices)_
