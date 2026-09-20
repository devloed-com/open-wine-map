# Analytics — Plausible events, goals and how to read the numbers

The map ships a self-hosted [Plausible](https://plausible.io/) snippet
(`analytics.dev.devloed.com`, injected by `_TEMPLATE` in
[scripts/_lib/map_template.py](../scripts/_lib/map_template.py)); the site id
is **`openwinemap.com`** (Plausible strips the `www.`). Custom events are sent
through the `track(name, props)` helper in
[scripts/_lib/assets/app.js](../scripts/_lib/assets/app.js). Every prop is a
bounded slug vocabulary — never raw user text — so breakdowns stay useful and
nothing personal can leak. The one deliberate exception is the `note` prop of
`Feedback Note` (short visitor text, see below).

## Environments — one build, one tracker per hostname

Plausible's v2 tracker (`/js/pa-<id>.js`) pins the site domain *inside* the
script (`init({domain})` cannot override it), so every environment is its own
Plausible site with its own script id. The page snippet picks the script by
`location.hostname` at runtime from a small map baked in by stage 04 —
`plausible_sites()` in [scripts/_lib/env.py](../scripts/_lib/env.py): the
production entry is the code default; further environments come from `.env`:

    PLAUSIBLE_SITES=openwinemap.com=pa-QAprx84urDZKvC3I6r6bc,beta.openwinemap.com=pa-<id>
    PLAUSIBLE_HOST=https://analytics.dev.devloed.com        # optional

`www.` is stripped before the lookup; a hostname with no entry (localhost, a
preview) loads no tracker at all. One build therefore serves prod and beta
byte-identically, and beta traffic never lands in the prod site. Adding an
environment: create the site in Plausible, copy the id from its snippet, add
the `.env` entry, rebuild (stage 04), deploy. **Goals are per site** — the
goal list below has to be configured again on a new site.

Because the inline snippet always defines a `window.plausible` queue stub,
`track()` cannot tell a blocked tracker from a loaded one; `trackerLoaded()`
(checks `plausible.l`, set by the tracker's init) is what the feedback row
uses to fall back to e-mail when nothing would be recorded — the tapped chip
still shows the choice for the open card, but nothing is stored anywhere.

**Testing on localhost.** No tracker loads there by default, so the feedback
row shows the e-mail fallback and every `track()` call is echoed to the
browser console as `[track] <event> {props}` — enough to check the flow. To
see events land in a dashboard, create a throw-away Plausible site (its
domain can be anything, e.g. `dev.openwinemap.com`), key its script id on
`localhost` in `.env` and rebuild:

    PLAUSIBLE_SITES=localhost=pa-<dev id>

The snippet passes `captureOnLocalhost: true` to the tracker for exactly this
case (the tracker otherwise drops localhost events); on any real host the
option is inert, and a build with no `localhost` entry loads nothing there.

## Events sent by app.js

| Event | Props | Fired when |
|---|---|---|
| `Appellation Viewed` | `slug`, `country`, `kind`, `region`, `stacked`, `stack_size`, `via`, `locale` | the detail panel opens or the stack focus changes. `via` ∈ `map` (click on the map), `cycle` (re-click cycling a stack), `facet`, `omnisearch`, `panel-link` (parent/child link inside a card). **Not** fired for the page-load open of a `/<lang>/<slug>` landing (the pageview already records it) nor for the localStorage restore. |
| `Appellation Opened` | `slug`, `via` (`facet` / `omnisearch`), `locale` | an explicit pick — the cleanest interest signal |
| `Filter Applied` | `facet`, `value`, `locale` | a facet checkbox / chip / country / region / appellation filter changes |
| `Filters Reset` | `locale` | the reset button |
| `Kind Toggled` | `kind` (`igp` / `spirits`), `enabled`, `via` (`reveal-hint`, optional), `locale` | the IGP / spirits switches |
| `View Mode Switched` | `mode` (`simple` / `advanced`), `locale` | the mode toggle |
| `Grape Scope Toggled` | `scope` (`main` / `all`), `locale` | principal-only vs all grapes |
| `Omnisearch Used` | `result_count`, `had_match`, `groups` (a/g/r/s), `query_len`, `locale` | 1 s after typing stops in the omnisearch |
| `Omnisearch Result Picked` | `type` (`grape` / `region` / `style` / `classification`), `locale` | a non-appellation suggestion is picked (appellation picks fire `Appellation Opened`) |
| `Search Used` | `result_count`, `had_match`, `query_len`, `locale` | the legacy sidebar search (superseded by the omnisearch in June 2026) |
| `Theme Changed` | `theme`, `locale` | light / dark toggle |
| `Feedback Flagged` | `slug`, `aspect` (`boundary` / `grapes` / `facts` / `name` / `sources` / `other`), `country`, `kind`, `geom_source`, `via` (`card` / `stub-help`), `locale` | one tap on an aspect chip in the **"Report a mistake" section at the bottom of every appellation card** (2026-09). No account, no form. Pressed chips are remembered per browser (localStorage) so a revisit does not re-fire. A `slug × aspect` breakdown is the curator queue; flags ÷ `Appellation Viewed` is a per-record trust score. |
| `Feedback Retracted` | `slug`, `aspect`, `locale` | a second tap on a pressed chip un-flags it (a misclick, or a change of mind). A flag cannot be recalled from Plausible, so net the two: flags − retractions per `slug × aspect`. |
| `Feedback Note` | `slug`, `aspect`, `note`, `locale` | the optional free-text note sent after a flag. `aspect` is every chip pressed on the card at send time, joined with `+` (`boundary+grapes`). **`note` is visitor text** — whitespace-collapsed, capped at 500 characters client-side (Plausible accepts up to 2,000), with an inline "no personal details" hint. Self-hosted, no visitor identity attached; `scripts/feedback_report.py` lists every note with its slug and date. |
| `Feedback Clicked` | `channel` (`email`), `locale` | the e-mail link in the sidebar disclaimer. The GitHub-issue link was removed 2026-09: months of clicks produced zero issues (a login wall + blank form). GitHub stays reachable from the About dialog for PRs. |
| `Outbound Link: Click` | `url` | Plausible's own outbound-link tracking (source PDFs, Wikipedia, interprofessions, GitHub) |

## Goals — what the dashboard and the Stats API can see

Plausible stores every custom event but only **shows** the ones configured as
a goal (Site settings → Goals → *Add goal* → *Custom event*, exact name).
Adding a goal is retroactive — history appears immediately. Configured on
2026-09-11: `Appellation Viewed`, `Filter Applied`, `Outbound Link: Click`,
`View Mode Switched`, `Kind Toggled`, `Filters Reset`, `Search Used`; on
2026-09-16: `Appellation Opened`, `Omnisearch Used`, `Omnisearch Result
Picked`, `Theme Changed`, `Grape Scope Toggled`.

**Still to add on production** (stored, invisible until then):

- `Feedback Clicked` (sent since the 2026-09-11 build)
- `Feedback Flagged`, `Feedback Retracted` and `Feedback Note` — the card
  feedback row (2026-09-16 build). Read them with
  `scripts/feedback_report.py` (below), not the dashboard.

`beta.openwinemap.com` carries `Appellation Viewed`, `Outbound Link: Click`
and the four `Feedback *` goals (2026-09-16); the interaction goals are not
configured there. To list a site's goals without the dashboard, filter the
Stats API on `event:goal` — an unconfigured name answers HTTP 400 "is not
configured for this site" (the Sites API is not enabled on this instance).

## Reading the numbers — artefacts to keep in mind

- **Pageviews on entity paths are entries only.** Opening an appellation
  rewrites the URL with `history.replaceState`, which Plausible does not count
  as a pageview (by design — panel opens are not page loads). `/en/bourgogne`
  showing 85 visitors and 10 pageviews means 10 landings and 85 people whose
  panel was on Bourgogne at some point. Use the `Appellation Viewed` slug
  breakdown, not the Pages report, for what people look at.
- **Bounce on entity landings was ~0 by construction until 2026-09-11**: the
  page-load open fired `Appellation Viewed`, and any second event ends a
  bounce. From this build on, a landing that only reads the SSR page counts
  as a bounce again, so expect the organic bounce rate to rise from ~8 % to
  something honest.
- **Empty entry page + 0 pageviews** (≈ 7 % of visits) are map tabs resumed
  after the 30-minute session timeout; they show as *Direct*. Real, engaged
  sessions — not a bug.
- **`Appellation Viewed.slug` is the stack focus**, i.e. the smallest
  bounding box under the click, so an umbrella appellation whose aire equals
  a famous one gets the credit (Coteaux Champenois ≡ Champagne). Filter on
  `via` = `facet` / `omnisearch` — or use `Appellation Opened` — for intent.
- A wrongly-huge simple-mode polygon shows up in this breakdown before it
  shows up anywhere else (Pouilly-Loché, 2026-09: a 0.4 km² AOC drawn
  across all of Burgundy by a stage-02 aire parse miss). Stage 04's
  `[villages-guard]` log line now flags the pattern; the analytics is the
  second line of defence.

## Querying

The Stats API v2 (`POST /api/v2/query`, `Authorization: Bearer <key>`) covers
aggregates, time series and breakdowns by any prop or visit dimension; no DB
tunnel is needed for insights. Keys are created per session in Plausible's
settings and revoked afterwards — never commit or store one. A ClickHouse
tunnel (port 8123) is only worth it for session-sequence questions
("searched, then opened?") that the API cannot express.

**Reading the feedback.** The dashboard shows one property at a time and
cannot net a flag against its retraction, so the curation view is
[scripts/feedback_report.py](../scripts/feedback_report.py): it cross-tabs the
three `Feedback *` goals through the Stats API and prints a Markdown report —
the queue (net flags per appellation × aspect, `Appellation Viewed` over the
same range as a trust ratio, geometry source) and every note verbatim with
its date. The key comes from the environment, never a file:

    export PLAUSIBLE_API_KEY=<per-session Stats API key>
    .venv/bin/python scripts/feedback_report.py                       # production, all time
    .venv/bin/python scripts/feedback_report.py --site beta.openwinemap.com --range 30d
    .venv/bin/python scripts/feedback_report.py --range 2026-09-01,2026-09-30 --json /tmp/fb.json
    .venv/bin/python scripts/feedback_report.py --csv feedback.csv   # one row per flag / retraction / note

`--csv` is the spreadsheet form: one row per event, with `date` and `datetime`
(hour resolution — the finest the Stats API exposes — in the site's timezone; `event` =
`flagged` / `retracted` / `note`) with slug, aspect, country, kind,
`geom_source`, `via`, locale, the note text and the slug's panel opens;
`--csv -` prints it instead of the report. Notes are whitespace-collapsed
before they are sent, and the `csv` module quotes the rest.

A goal missing on the site is reported and counted as zero. The trust ratio's
denominator is the slug as **stack focus**: a card flagged from inside a
stack (one click on Sardinia opens five overlapping DOCs, and only the focus
fires `Appellation Viewed`) shows fewer opens than it had readers — "—" means
no focus open in the range, not no readers. A flag that recurs on one
appellation × aspect is a data defect to fix upstream (the stage, the
override file), never a reason to hide the chip.
