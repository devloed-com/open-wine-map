# Ahrefs Site Audit — 2026-11-06

Trigger: Boris pasted the Ahrefs "Issues Overview" for openwinemap.com
(project 10663135, crawl 2026-11-06T12:04:30Z, 13 issue types, ~4,992 of the
6,640 indexable entity pages crawled) and ten per-issue CSV exports. No
Ahrefs API key is configured, so the triage ran against the local build
(same vintage as the live site: "Data updated on 2026-10-31", deployed
2026-11-06 10:32 CET, before the crawl), the live CDN, the schema.org
validator and the CSVs. Verdicts: **real** (a defect in the build),
**decision** (correct but improvable), **noise** (the auditor's
classification or a measurement artefact).

| Ahrefs issue | pages | verdict | what it was |
|---|---:|---|---|
| Structured data validation error | 4,992 | **real — fixed** | `inLanguage` on the JSON-LD `AdministrativeArea` node; schema.org defines the property on CreativeWork and Event, the validator reports `UNKNOWN_FIELD` (severity WARNING) on every entity page |
| Open Graph tags incomplete | 4 | **real — fixed** | the four browse hubs `/<lang>/appellations/` had og:type / title / description / url and no `og:image`; `_BROWSE_TEMPLATE` lacked the social-card block the map shell carries |
| X (Twitter) card missing | 4 | **real — fixed** | same four pages, no `twitter:*` |
| Meta description too short (< 100) | 46 | **decision — changed** | all lead-less records (Swiss cantonal AOCs, Oberösterreich, the Veneto IGT: no terroir facts, no summary readable in the locale), 74–99 characters |
| Slow page (TTFB > 1.5 s?) | 31 | noise | post-deploy cache purge — see below |
| Slow server response for AI crawlers | 12 | noise | same; TTFB 1.9–8.4 s in the CSV (en/manchuela 8.4 s, en/malokarpatska 8.1 s, en/chambertin-clos-de-bèze 5.6 s) |
| 3XX redirect | 5 | noise | apex → www, http → https, robots.txt: single hops by design |
| HTTP → HTTPS redirect | 3 | noise | same |
| Product page missing Product schema | 11 | noise | Ahrefs' page-type guess on entity pages; no Product markup is correct |
| Article page missing Article schema | 1 | noise | es/cidre-de-normandie; no Article markup by design (a generated page has no author or editorial dates to declare) |
| Category page missing ItemList schema | 1 | noise | en/colares, a page-type guess |
| Organization schema missing or incomplete | 4 | notice | the homepages' WebSite publisher is name + url; logo and sameAs are optional enrichment |
| Page and SERP titles do not match | 25 | notice | Google drops the " · Open Wine Map" suffix; a few SERP titles are still the pre-2026-09-26 format (fr/brouilly "BEAUJOLAIS") — the recrawl closes it |

## The slow pages are the cache purge, not the origin

The deploy of 10:32 CET purged Bunny's edge cache; the crawl started 2.5
hours later and pulled ~5,000 cold pages in parallel from the storage origin
(UK). Measured on 2026-11-07, the pages the CSV lists at 1.9–8.4 s answer in
0.3–0.7 s, `cdn-cache: HIT` and `MISS` alike, and the same under the GPTBot,
ClaudeBot and PerplexityBot user agents (no UA-dependent path). Options if
the finding should not recur on the next audit: Bunny Perma-Cache / origin
shield, or a post-deploy warm-up pass over the sitemap URLs. Not a code
defect; nothing changed.

## Fixes (2026-11-07, `scripts/_lib/map_template.py`)

- **Place `inLanguage` dropped** in `_build_entity_jsonld`; WebSite and
  WebPage keep theirs. After the rebuild: 0 of 6,640 indexable entity pages
  carry it on the Place, 13,280 WebSite + WebPage nodes still do; the
  schema.org validator returns 0 errors / 0 warnings on en/pauillac,
  fr/basel-stadt and en/appellations (`tests/test_entity_jsonld.py`).
- **Social card on the browse hubs**: `og:image` (1200 × 630, alt = the page
  title) and `twitter:card / title / description / image` added to
  `_BROWSE_TEMPLATE`, the shell's own block (`tests/test_browse_page.py`).
- **Lead-less descriptions fill with the roster** (`_fill_grape_clause`): a
  record with no lead sentence grows its grape clause to as many principal
  varieties as the 160 characters hold, the rest counted through the
  existing `provenance_grapes_more` msgid ("{names} and {n} other grape
  varieties" / "et {n} autres cépages" / "y otras {n} variedades de uva" /
  "en {n} andere druivenrassen"); the whole roster when it fits; the
  related-denominations tail keeps its room; a record with a lead keeps the
  three-grape clause. Basel-Stadt EN went from 95 to 144 characters
  ("… Blauburgunder, Chardonnay, Divico, Johanniter, Regent and 66 other
  grape varieties."), Oberösterreich 95 → 155, Veneto 98 → 155.

Indexable descriptions under 100 characters: 46 → 16, under 110: 532 → 475.
The 16 are four records × four locales whose content is exhausted — Schwyz
and Zürich (no roster of their own; the related-denominations tail is all
there is, 74–76 chars), Graubünden / Grigioni (one variety, 74–79) and
Obwalden (its whole roster of four, 94–97). Not padded: the 2026-09-26 rule
stands, no template text in a description.

## Left as is

- **The lead cliff at 100–102 characters.** ~60 records per locale with a
  lead have their head + three grapes at exactly 100–102 characters, so the
  lead has 58–59 characters of room, under `_LEAD_MIN_ROOM` (60), and is
  dropped whole ("Alsace grand cru Bruderthal, Alsace, France · AOC (PDO).
  Gewurztraminer, Muscat Ottonel, Pinot Gris." — 100). Ahrefs does not flag
  them (its floor is < 100). The 2026-09-26 decision ("a stub lead misleads
  more than none") holds; lowering the floor or clamping the lead is a
  separate call.
- **Organization enrichment** (logo, sameAs on the publisher node) and the
  Bunny cache options above.
- **IndexNow on the next deploy**: every indexable page's JSON-LD changed,
  so the content fingerprints differ on all ~6,644 canonical URLs and the
  deploy submits the full set (as on 2026-09-26); `--no-indexnow` skips it.
