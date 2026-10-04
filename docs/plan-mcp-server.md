# Plan — a remote MCP server for Open Wine Map

Status (2026-10-04): live. Branch `feat/mcp-server` (from `origin/main` a619b99).

| phase | state |
|---|---|
| 0 spike | done — see "SDK findings" |
| 1 shared query core | done — `scripts/_lib/assets/query_core.mjs`, inlined into app.js; WebMCP is an adapter; `list_facets` added; schemas hardened; country-qualified schemes (`it:docg`) now match (they never did) |
| 2 query context | done — `wiki/data/mcp/<locale>.json`, 3.7 MB each; contract test |
| 3 server + tests | done — `mcp/`; 14 node tests, parity 0 differences (page WebMCP vs server, 3 locales), headless UI check clean, full pytest green |
| 4 deploy | done — site deployed (snapshot `snapshots/openwinemap-deployed-20261004T134415Z`); script `owm-mcp` (id 94571, `BUNNY_MCP_SCRIPT_ID`) at https://mcp.openwinemap.com/mcp — CNAME in the Bunny DNS zone, free certificate, Force SSL; variables DATA_ORIGIN / PLAUSIBLE_HOST / PLAUSIBLE_DOMAIN. Smoke (all three modes) green against the live data. The deploy smoke waits for the release's SHA (`1.0.0+<sha>`): right after a publish, isolates of the previous release still answer |
| 5 discovery | About dialog sentence (4 locales) + `llms.txt` "For AI agents" section + docs live; open: `MCP Tool` goal in Plausible (the 48 events of 2026-10-04 are all deploy-window test traffic), Le Chat live test, MCP Registry entry, delete spike `owm-mcp-spike` (id 94565) |

## Why

The map registers four WebMCP tools in the page (`search_appellations`,
`filter_appellations`, `get_appellation`, `show_appellation`; end of
`scripts/_lib/assets/app.js`), with the origin-trial token live since the
2026-10-04 deploy. WebMCP only reaches an agent that runs *inside* Chrome on
the page. Chat assistants that only fetch URLs (Le Chat, Claude, ChatGPT)
cannot see those tools — a Le Chat session on 2026-10-04 probed
`/.well-known/*` paths, found nothing and fell back to page scraping.

Their path today is `llms.txt` + the server-rendered entity pages: enough to
look up one appellation, useless for structured questions ("every DOCG with
Nebbiolo in Piemonte") because filtering exists only in the JS app. A remote
MCP server gives those clients the same search / filter / lookup tools. Le Chat
takes a remote Streamable HTTP server as a Custom MCP Connector (paste the URL;
no auth needed).

Expect modest use: nothing discovers an MCP server automatically yet (the
`.well-known/mcp/server-cards.json` proposal, SEP-2127, is still open), so a
user adds the URL by hand.

## Facts the design rests on (verified 2026-10-04)

- **MCP protocol**: the current revision is **2026-07-28**, and it is
  stateless by design — no `initialize` / `notifications/initialized`
  handshake, protocol version and client capabilities in every request's
  `_meta` (and the `MCP-Protocol-Version` header), a mandatory
  `server/discover` RPC, `resultType` on every result, `ttlMs` / `cacheScope`
  on `tools/list`, required `Mcp-Method` / `Mcp-Name` request headers, no
  sessions, no `ping`. Clients in the field may still speak **2025-11-25** /
  2025-06-18 (with the handshake), so the server must answer both.
- **Bunny Edge Scripting** (standalone script = its own origin, gets a linked
  pull zone): Deno/V8 runtime; 30 s CPU / request, 128 MB active memory,
  50 subrequests, 10 MB script, 500 ms startup; $0.20 per million requests +
  $0.02 per 1,000 s CPU. Code is uploaded as **one string** (`POST
  /compute/script/{id}/code {Code}`, then `POST /compute/script/{id}/publish
  {Note}`; `AccessKey` header) → the script must be a single bundled file.
  A standalone script runs only on cache miss unless "run script before cache"
  is on.
- **Data already published** per locale: the startup blob
  `data/aocs.<locale>.<hash>.js` (en: 2,955 records; `aocs` 3.4 MB +
  `grapes_info` 0.7 MB raw) and one panel JSON per slug
  `data/d/<locale>/<slug>.json` (median 5 KB, max 33 KB).

## Architecture

```
MCP client ──POST /mcp──▶ mcp.openwinemap.com  (Bunny standalone Edge Script)
                             │  official MCP TS SDK, stateless,
                             │  WebStandardStreamableHTTPServerTransport
                             │  query core (shared with app.js)
                             ├─ GET www.openwinemap.com/data/mcp/<locale>.json   (once per isolate, revalidated)
                             └─ GET www.openwinemap.com/data/d/<locale>/<slug>.json  (get_appellation)
```

### 1. One query core, two adapters

The search and filter logic must not exist twice. Extract it from app.js into
`scripts/_lib/assets/query_core.mjs`, a dependency-free ES module of pure
functions over a data context:

- `searchNormalize`, record search forms, `searchScore` (prefix 100 /
  substring 80, per form) — exactly today's semantics.
- grape resolution (name / alias / slug → VIVC sibling set), style resolution
  (slug / label → descendants), region matching (key, label, region search
  forms), scheme / traditional-term matching on `class_key`.
- `search(ctx, args)`, `filter(ctx, args)`, `brief(ctx, slug)`,
  `full(ctx, slug, panel)` — the bodies of today's WebMCP tools.

app.js gets the module inlined at build time (`_render_app_js` replaces a
`__OWM_query_core__` token with the file, `export ` stripped, asserted
single-occurrence); the UI's omnisearch and tree filter keep calling the same
functions. The edge bundle imports the same file. WebMCP and MCP tools become
thin adapters, so their outputs are identical by construction.

### 2. Data context emitted by stage 04

`wiki/data/mcp/<locale>.json`, stable path (not content-hashed — the script
must find it), with a `format_version`:

- per record: slug, name, name_latin, search_forms, country, country_aliases,
  region, kind, class_key, class_label, styles, grapes_principal, grapes_all,
  is_sub_denomination, parent_slug, is_wine, cancelled, promoted;
- the lookup tables the core needs: grape search index, VIVC siblings, style
  descendants / labels / simple buckets, region labels + region search terms,
  country labels, terroir sub-section labels.

A contract test pins the field list (the STARTUP_AOCS_FIELDS lesson: a missing
field fails silently). The script caches the parsed context per isolate and
revalidates with `If-None-Match` at most every few minutes; a deploy purges the
CDN, so new data reaches the script within that window.

### 3. Protocol: the official SDK, bundled

Use the official TypeScript SDK's web-standard Streamable HTTP server
transport in stateless mode, bundled with esbuild into one file. With two live
protocol revisions (2026-07-28 and the handshake-based 2025-11-25) the SDK's
version negotiation is the part not worth hand-writing. **Gate:** phase 0
proves the bundle fits Bunny (size, 500 ms startup, cold-start latency) and
that Le Chat and the MCP Inspector both connect. Fallback if it does not fit: a
hand-written dual-version JSON-RPC handler (initialize + server/discover,
tools/list, tools/call), tested against the SDK client.

### 4. Tools

| tool | inputs | notes |
|---|---|---|
| `search_appellations` | query, country?, limit?, locale? | as WebMCP |
| `filter_appellations` | country?, region?, style?, grape?, main_grape_only?, scheme?, include_sub_denominations?, include_spirits?, limit?, locale? | as WebMCP |
| `get_appellation` | slug, locale? | as WebMCP; fetches the panel JSON |
| `list_facets` *(proposed)* | locale? | countries, regions, styles, schemes with counts, so an agent knows valid filter values; added to WebMCP too |

`show_appellation` has no server meaning; every result already carries the
map URL. Schema hardening, applied to the WebMCP definitions in the same
change: `limit` with `minimum` / `maximum`, `locale` as an enum
(en / fr / es / nl), `country` with a two-letter pattern, string `maxLength`;
annotations `readOnlyHint`, `idempotentHint`, `openWorldHint: false`; an
`outputSchema` + `structuredContent` beside the text content. Results keep the
attribution fields the panel shows (specification URL, Wikipedia URL +
CC BY-SA 4.0 where a fact is wiki-sourced, machine-translation note).

### 5. HTTP behaviour

POST `/mcp` only (GET → 405; no server-to-client stream); `Cache-Control:
no-store` on every response; permissive CORS (public read-only data, browser
clients such as the Inspector); request body and query-length caps; result
caps as in WebMCP (100 / 200). No authentication.

## Repository layout

```
mcp/
  package.json        pinned SDK + esbuild (dev); scripts: build, test
  src/server.js       createHandler({fetchData}) → (Request) => Response
  src/edge.js         Bunny entry: BunnySDK.net.http.serve(handler)
  test/*.test.js      node --test (Node 20; no Deno locally)
  dist/edge.js        build output, gitignored
scripts/_lib/assets/query_core.mjs   shared with app.js
scripts/deploy_mcp.py               build → set code → publish
```

## Deploy

- One-time setup (needs Boris; outward-facing): create the standalone script
  with a linked pull zone (dashboard, or `POST /compute/script` with
  `CreateLinkedPullZone`), add hostname `mcp.openwinemap.com` to that pull
  zone, DNS CNAME, free SSL; script env var `DATA_ORIGIN=https://www.openwinemap.com`.
  New `.env` key `BUNNY_MCP_SCRIPT_ID`; the existing `BUNNY_API_KEY` covers
  the API calls.
- `scripts/deploy_mcp.py`: `npm run build` in `mcp/`, upload the bundle, publish
  with the git SHA as release note, smoke-test (`server/discover`, a legacy
  `initialize`, `tools/list`, one `tools/call`). Rollback = republish an
  earlier release (`POST /compute/script/{id}/publish/{uuid}`).
- Order: the data deploy (`deploy.sh`) goes first; the script tolerates an
  older `format_version` for one release.

## Discovery, docs, analytics

- `llms.txt`: an "MCP server" line with the URL; About dialog: one sentence
  (four locales via gettext); a short docs page with connector steps for
  Le Chat, Claude and ChatGPT; CLAUDE.md section.
- Optional: an entry in the official MCP Registry. Skip `.well-known` server
  cards until SEP-2127 lands.
- Optional: server-side Plausible event `MCP Tool` {tool, locale,
  protocol_version}, sent with `waitUntil`; arguments never sent (same rule as
  `WebMCP Tool`); documented in docs/analytics.md.

## Verification

- `node --test`: query core against the built `wiki/` data (Montsant and
  Priorat among the anchors; a Greek romanised query; a grape synonym; a
  scheme term); protocol conformance with the SDK client over a local HTTP
  wrapper, once per protocol revision.
- Parity: Playwright on `scripts/serve.py` with an init script that captures
  `document.modelContext.registerTool`, then the same queries through the
  WebMCP tools and the MCP handler must return identical JSON.
- No UI regression from the extraction: omnisearch and tree filter checked
  headlessly; the golden comparator shows only the app bundles changing.
- pytest contract test for `data/mcp/<locale>.json`.
- Live: MCP Inspector against the deployed URL, then a Le Chat custom
  connector session repeating the Priorat question.

## Phases

| # | work | exit criterion |
|---|---|---|
| 0 | spike: bundle the SDK server, deploy to a throw-away Bunny script | cold start and size within limits; Le Chat + Inspector connect on both protocol revisions — else switch to the hand-written handler |
| 1 | extract `query_core.mjs`; WebMCP becomes an adapter; schema hardening | omnisearch / WebMCP behaviour unchanged (headless); tests green |
| 2 | stage 04 emits `data/mcp/<locale>.json` | contract test; sizes logged |
| 3 | `mcp/` server + tests | conformance + parity green locally |
| 4 | `deploy_mcp.py`, one-time Bunny setup | smoke test passes on `mcp.openwinemap.com` |
| 5 | llms.txt / About / docs / optional analytics + registry | live Le Chat session answers from the tools |

## Risks

- **Spec churn**: two revisions in the field; the SDK carries the
  negotiation. Pin the SDK version, test both revisions in CI.
- **Bundle vs Bunny limits**: unproven — hence phase 0 first.
- **app.js regression** from the extraction: the live search depends on it;
  covered by the headless checks.
- **Abuse**: read-only, cheap per call; caps on inputs and results; Bunny
  pull-zone rate limiting available if needed.

## Decisions (Boris, 2026-10-04)

1. Hostname `mcp.openwinemap.com`; DNS is on Bunny (delegated from Hover), so
   the record can be added through the Bunny API with the script setup.
2. Shared query core.
3. `list_facets`: yes, in both WebMCP and MCP.
4. Server-side `MCP Tool` analytics event: yes, tool + locale only.
5. Phase 0's throw-away script: created through the Bunny API.

## SDK findings (phase 0)

`@modelcontextprotocol/server` 2.3.0 (2026-10-02) ships `createMcpHandler(
factory, {legacy: 'stateless', responseMode: 'json'})`, a web-standard
`{fetch(Request)}` handler that serves 2026-07-28 requests natively and
2025-era requests through a per-request stateless fallback (GET / DELETE →
405). `fromJsonSchema()` takes a plain JSON Schema, so the WebMCP schemas are
reused verbatim; the `validators/cf-worker` provider avoids `new Function`
code generation in isolates that forbid it.

Spike result (2026-10-04, script `owm-mcp-spike`, id 94565,
https://owm-mcp-spike.bunny.run/mcp — throw-away, delete after phase 4):

- bundle 319 KB minified (zod 852 KB + SDK 568 KB unminified inputs) — far
  under the 10 MB limit; startup fine.
- official client, all three modes against the live edge: legacy handshake
  → 2025-11-25; pinned → 2026-07-28; auto → 2026-07-28. First connect
  1.2 s (cold isolate + TLS), warm 55–75 ms. The panel subrequest to
  www.openwinemap.com works from the edge.
- MCP Inspector CLI (independent client) lists the tools.
- POST responses are not served from the CDN cache (two `tools/call` with
  different arguments → different results). Bunny rewrites the response
  `Cache-Control` to `no-cache` and adds `cdn-cachedat`; harmless.
- The legacy (2025) path answers as an SSE stream (the SDK's stateless
  fallback ignores `responseMode`); valid for 2025 clients.
- Open: a Le Chat custom-connector session against the spike URL (needs
  Boris's account).

## Sources

- MCP versioning / current revision 2026-07-28: https://modelcontextprotocol.io/docs/learn/versioning
- MCP 2026-07-28 changelog: https://modelcontextprotocol.io/specification/latest/changelog
- SDK web-standard transport: https://ts.sdk.modelcontextprotocol.io/v2/classes/_modelcontextprotocol_server.server_streamableHttp.WebStandardStreamableHTTPServerTransport.html
- Le Chat MCP connectors: https://docs.mistral.ai/le-chat/knowledge-integrations/connectors/mcp-connectors
- Bunny Edge Scripting limits: https://bunny.net/docs/scripting/limits
- Bunny Edge Scripting pricing: https://bunny.net/docs/scripting/pricing
- Bunny standalone scripts: https://bunny.net/docs/scripting/standalone/overview
- Bunny compute API (OpenAPI): https://core-api-public-docs.b-cdn.net/docs/v3/compute.json
- MCP server cards proposal (SEP-2127): https://mcpplaygroundonline.com/blog/mcp-server-cards-well-known-discovery
- WebMCP explainer (rejects static manifests): https://github.com/webmachinelearning/webmcp
