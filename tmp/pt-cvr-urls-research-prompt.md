# Research task — official websites for the DO organisations of Portuguese wine appellations

## Context

I maintain open-wine-map, a wine-appellation reference built **only** from
public, licence-clear regulator data. The map's detail panel ("card") for
each appellation shows a link to the official site of the body that
administers that denominação — for France an *interprofession*, for Italy a
*consorzio di tutela*, for Spain a *consejo regulador*. The Portuguese
equivalent is the **Comissão Vitivinícola Regional (CVR)** — the regional
wine commission that certifies and protects a region's DOP/IGP wines — or,
for a few regions, a dedicated institute (e.g. the **IVDP** for Douro/Porto,
the **IVBAM** for Madeira and the Azores).

France, Italy and Spain already have this link curated. **Portugal has
none.** This task collects the official-website URL for the organisation
behind each of the 44 Portuguese wine appellations.

Portugal administers all its denominations through a *small fixed set* of
regional commissions and institutes — typically one organisation covers
several appellations (its region's DOP plus the matching IGP, and often
several sub-area DOPs). Examples:

- **IVDP — Instituto dos Vinhos do Douro e do Porto** → Douro, Porto, Duriense
- **CVRVV — Comissão de Viticultura da Região dos Vinhos Verdes** → Vinho Verde, Minho
- **CVR Alentejana** → Alentejo, Alentejano
- **IVBAM — Instituto do Vinho, do Bordado e do Artesanato da Madeira** → Madeira, Madeirense, and the Azores DOPs
- **CVR Lisboa** → Lisboa plus the Lisbon-area DOPs (Alenquer, Arruda, Bucelas, Colares, Carcavelos, Óbidos, Torres Vedras, Encostas d'Aire, Lourinhã)

## What I need from you

For each appellation below, search the sources listed and return one of:

1. **FOUND** — the official website of the CVR / institute that administers
   that appellation. Give the exact organisation name and the full homepage
   URL.
2. **NONE** — no public official website exists. Say so, and note any
   close-but-wrong page you found instead (a single winery, a wine-shop, a
   tourism portal — those do **not** count).

Search in priority order:

1. **The CVR's / institute's own website** (often `cvr<region>.pt`,
   `ivdp.pt`, `vinhoverde.pt`, `vinhosdoalentejo.pt`, etc.).
2. **The IVV — Instituto da Vinha e do Vinho** (`ivv.gov.pt`) — the national
   authority; its site lists the regional entidades certificadoras with
   links.
3. **The regional commission's listing** for the matching DOP/IGP, where one
   CVR covers several denominations.

**Identity check:** the site must be the body that *certifies / protects*
the named appellation — its homepage should name the região or the
denominação, or it must be the IVV-listed entidade certificadora for that
DOP/IGP. A producer's commercial site, a wine e-commerce site, a tourism
portal, or a Wikipedia article does **not** count.

A confident **NONE is a useful answer.** Do not invent a plausible-looking
URL — only return FOUND when you have opened the page and confirmed its
identity. If a candidate source blocks you with a JavaScript / CAPTCHA / WAF
challenge or a login wall you cannot get past, return that item as
**UNREACHABLE** with the URL you were blocked on — do not guess.

## Output format

One row per item, pipe-delimited. Group FOUND rows first, then NONE, then
UNREACHABLE. The `ITEM_ID` is the wine `slug` from the item list.

    slug | FOUND       | <official organisation name> | <homepage URL> | <one-line identity note: how you confirmed it covers this appellation>
    slug | NONE        | —                            | —              | <what you found instead, if anything>
    slug | UNREACHABLE | —                            | <blocked URL>  | <challenge type>

The `<official organisation name>` becomes the link label shown on the card
— give the organisation's normal public name (e.g. `Comissão Vitivinícola
Regional Alentejana` or its common acronym).

## Item list

_(injected per-agent — see the dispatched slices)_
