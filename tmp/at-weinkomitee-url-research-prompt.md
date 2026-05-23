# Research task — official organisation websites for 32 Austrian wine appellations

## Context

I maintain open-wine-map, a wine-appellation reference map built **only** from
public, licence-clear regulator data. The map detail panel for each appellation
shows a row linking the **organisation that administers the denomination** — the
French *interprofession*, the Spanish *consejo regulador*, the Italian
*consorzio di tutela*. France, Spain, Portugal and Italy are curated; Austria
has zero coverage and I need to fill it.

For Austria the administering body for a DAC (Districtus Austriae Controllatus)
wine region is its **Regionales Weinkomitee** (regional wine committee). In
practice the public-facing web presence of a DAC region is the **regional wine
board / marketing association** — e.g. "Wein Burgenland", "Wein Steiermark",
"Niederösterreich Wein" — and many individual DAC regions run a dedicated site,
often on a `.wine` top-level domain (e.g. the Kamptal or Weinviertel region
site). The national body is **Österreich Wein Marketing GmbH (ÖWM)** at
oesterreichwein.at / austrianwine.com.

The corpus has two kinds of appellation:
- **Regional/Bundesland-level PDOs** (Burgenland, Niederösterreich, Steiermark,
  Wien, Kärnten, Salzburg, Tirol, Vorarlberg, Oberösterreich) — the generic
  catch-all denomination for a federal state.
- **DAC PDOs** — a specific controlled appellation inside one Bundesland (e.g.
  Kamptal DAC inside Niederösterreich).
- **Landwein IGPs** (Bergland, Weinland, Steirerland) — broad geographic
  indications spanning several Bundesländer.

## What I need from you

For each appellation below, search the sources listed and return one of:

1. **FOUND** — the real, current official website of the organisation that
   administers or markets this appellation (its Regionales Weinkomitee, its
   regional wine board, or — for the generic regional/IGP entries that have no
   dedicated body — the Bundesland wine board or ÖWM). Give the exact
   organisation name and the full homepage URL.
2. **NONE** — no public official organisation website exists for this
   appellation. Say so, and note any close-but-wrong page you found instead.

Search in priority order:

1. The **Regionales Weinkomitee** / regional wine-region official site (often a
   `.wine` or `.at` domain named after the region).
2. The **Bundesland wine board** (e.g. weinburgenland.at, wein-steiermark.at,
   niederoesterreich.wine / niederoesterreichwein) for regional-level PDOs and
   DACs that have no separate site.
3. **Österreich Wein Marketing (ÖWM)** — oesterreichwein.at (German) /
   austrianwine.com (English) — the national fallback, and the authoritative
   directory of Austrian wine regions; use it to confirm which region a DAC
   belongs to and to discover the regional site.

**Identity check:** the page must be the official organisation / wine-board
site for *this* appellation — confirm the region name matches and that it is
the administering/marketing body, not a single winery, a wine shop, a tourism
portal, a hotel, or a third-party narrative wiki. A homonym place does not
count. Austrian regional wine sites typically describe the DAC rules, the
member growers, and the region — that is the signal you have the right page.

A confident **NONE is a useful answer.** Do not invent a plausible-looking URL
or organisation name — only return FOUND when you have opened the page and
confirmed its identity. Prefer the most specific correct organisation: if a DAC
has its own regional site, return that rather than the Bundesland-wide board.

If a candidate source blocks you with a JavaScript / CAPTCHA / WAF challenge or
a login wall you cannot get past, return that item as **UNREACHABLE** with the
URL you were blocked on — do not guess.

## The items

(Each agent receives its assigned slice below.)

| slug | name | kind | Bundesland / scope |
|---|---|---|---|
| niederosterreich | Niederösterreich | DOP | Niederösterreich (regional PDO) |
| weinviertel | Weinviertel | DOP | Niederösterreich (DAC) |
| kamptal | Kamptal | DOP | Niederösterreich (DAC) |
| kremstal | Kremstal | DOP | Niederösterreich (DAC) |
| traisental | Traisental | DOP | Niederösterreich (DAC) |
| wagram | Wagram | DOP | Niederösterreich (DAC) |
| wachau | Wachau | DOP | Niederösterreich (DAC) |
| carnuntum | Carnuntum | DOP | Niederösterreich (DAC) |
| thermenregion | Thermenregion | DOP | Niederösterreich (DAC) |
| wien | Wien | DOP | Wien (regional PDO) |
| wiener-gemischter-satz | Wiener Gemischter Satz | DOP | Wien (DAC) |
| burgenland | Burgenland | DOP | Burgenland (regional PDO) |
| neusiedlersee | Neusiedlersee | DOP | Burgenland (DAC) |
| neusiedlersee-hugelland | Neusiedlersee-Hügelland | DOP | Burgenland (older PDO, superseded by Leithaberg) |
| leithaberg | Leithaberg | DOP | Burgenland (DAC) |
| rosalia | Rosalia | DOP | Burgenland (DAC) |
| mittelburgenland | Mittelburgenland | DOP | Burgenland (DAC) |
| eisenberg | Eisenberg | DOP | Burgenland (DAC) |
| sudburgenland | Südburgenland | DOP | Burgenland (older PDO) |
| ruster-ausbruch | Ruster Ausbruch | DOP | Burgenland (DAC, town of Rust) |
| karnten | Kärnten | DOP | Kärnten (regional PDO) |
| tirol | Tirol | DOP | Tirol (regional PDO) |
| steiermark | Steiermark | DOP | Steiermark (regional PDO) |
| sudsteiermark | Südsteiermark | DOP | Steiermark (DAC) |
| weststeiermark | Weststeiermark | DOP | Steiermark (DAC) |
| vulkanland-steiermark | Vulkanland Steiermark | DOP | Steiermark (DAC) |
| steirerland | Steirerland | IGP | Steiermark (Landwein IGP) |
| salzburg | Salzburg | DOP | Salzburg (regional PDO) |
| vorarlberg | Vorarlberg | DOP | Vorarlberg (regional PDO) |
| oberosterreich | Oberösterreich | DOP | Oberösterreich (regional PDO) |
| bergland | Bergland | IGP | multi-state Landwein IGP |
| weinland | Weinland | IGP | multi-state Landwein IGP |

## Output format

One line per appellation, pipe-delimited. Group FOUND rows first, NONE rows
after, UNREACHABLE last:

    slug | FOUND       | <organisation name> | <full homepage URL> | <identity note: what the site is, region match>
    slug | NONE        | —                   | —                   | <what was found instead, or why no org exists>
    slug | UNREACHABLE | —                   | <blocked URL>       | <challenge type>

The `<organisation name>` is shown verbatim in the UI as the link label, so
give the proper German name of the body (e.g. "Weinkomitee Kamptal",
"Wein Burgenland", "Niederösterreich Wein", "Österreich Wein Marketing").
