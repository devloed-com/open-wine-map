# Analytics — Plausible events, goals and how to read the numbers

The map ships a self-hosted [Plausible](https://plausible.io/) snippet
(`analytics.dev.devloed.com`, injected by `_TEMPLATE` in
[scripts/_lib/map_template.py](../scripts/_lib/map_template.py)); the site id
is **`openwinemap.com`** (Plausible strips the `www.`). Custom events are sent
through the `track(name, props)` helper in
[scripts/_lib/assets/app.js](../scripts/_lib/assets/app.js), which no-ops
when the script is blocked. Every prop is a bounded slug vocabulary — never
raw user text — so breakdowns stay useful and nothing personal can leak.

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
| `Feedback Clicked` | `channel` (`github` / `email`), `locale` | a link tagged `data-feedback` in the sidebar disclaimer or the About dialog |
| `Outbound Link: Click` | `url` | Plausible's own outbound-link tracking (source PDFs, Wikipedia, interprofessions, GitHub) |

## Goals — what the dashboard and the Stats API can see

Plausible stores every custom event but only **shows** the ones configured as
a goal (Site settings → Goals → *Add goal* → *Custom event*, exact name).
Adding a goal is retroactive — history appears immediately. Configured on
2026-09-11: `Appellation Viewed`, `Filter Applied`, `Outbound Link: Click`,
`View Mode Switched`, `Kind Toggled`, `Filters Reset`, `Search Used`.

**Still to add** (sent since June 2026 but invisible until then):

- `Appellation Opened`
- `Omnisearch Used`
- `Omnisearch Result Picked`
- `Theme Changed`
- `Grape Scope Toggled`
- `Feedback Clicked` (new, 2026-09)

Until `Omnisearch Used` is a goal, search usage is unmeasured — `Search Used`
went to zero when the omnisearch replaced the sidebar search on 2026-06-19.

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
