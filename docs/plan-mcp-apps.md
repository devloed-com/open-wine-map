# Plan — the map inside the chat (MCP Apps)

Status: proposed, 2026-10-04. Builds on the live MCP server
(docs/plan-mcp-server.md). Nothing implemented.

## Goal

When an assistant answers from the Open Wine Map MCP server, it can show the
appellations **on a live map inside the conversation** — the real polygons,
framed, highlighted — instead of only a link. Hosts that do not support it keep
today's text results (plus the map link).

Target hosts: those that implement MCP Apps — Claude (web, desktop), ChatGPT,
VS Code, Goose. Le Chat is not listed and is out of scope (text fallback).

## What the spec allows (verified 2026-10-04)

MCP Apps is the official MCP extension for interactive UIs (SEP-1865; stable
spec `2026-01-26`, extension framework locked in protocol `2026-07-28`). The
spec and SDK are in `github.com/modelcontextprotocol/ext-apps`; the SDK is
`@modelcontextprotocol/ext-apps` 2.0.3 (peers: our `@modelcontextprotocol/server` v2).

- A tool declares `_meta.ui.resourceUri: "ui://…"`; the server serves that
  resource via `resources/read` as one HTML5 document,
  `mimeType: "text/html;profile=mcp-app"`. The host renders it in a sandboxed
  iframe (web hosts: through a sandbox proxy on a separate origin — Claude:
  a hash of the server URL under `claudemcpcontent.com`; ChatGPT:
  `*.web-sandbox.oaiusercontent.com`).
- The server negotiates: the host advertises the extension
  `io.modelcontextprotocol/ui` with `mimeTypes`; the server SHOULD attach UI
  only then, and every UI tool MUST still return meaningful text content.
- Data reaches the view by `postMessage` JSON-RPC: `ui/notifications/tool-input`
  and `ui/notifications/tool-result` (SDK: `app.ontoolinput` / `app.ontoolresult`);
  the view can call server tools (`app.callServerTool`), open links
  (`app.openLink`), ask for fullscreen (`app.requestDisplayMode`). Tools can be
  app-only (`_meta.ui.visibility: ["app"]`).
- **Allowed domains** — `_meta.ui.csp` on the resource, enforced by the host,
  never loosened:

  | field | CSP directive(s) | default when omitted |
  |---|---|---|
  | `connectDomains` | `connect-src` (fetch / XHR / WebSocket) | none (`'self'` only) |
  | `resourceDomains` | `script-src`, `style-src`, `img-src`, `font-src`, `media-src` | none |
  | `frameDomains` | `frame-src` (nested iframes) | `'none'` |
  | `baseUriDomains` | `base-uri` | `'self'` |

  The reference CSP is `default-src 'none'` and **has no `worker-src`**, so by
  the letter of the spec a `blob:` worker falls back to `script-src` and is
  blocked. In practice Claude's sandbox sends `worker-src 'self'
  https://www.claudeusercontent.com blob:`, and TomTom's maps MCP server runs
  MapLibre in MCP Apps on Claude, ChatGPT and VS Code with the worker inlined
  as a `blob:` URL (PR tomtom-international/tomtom-maps-mcp#255, MapLibre 6,
  +~460 KB per app). Hosts MAY restrict further and SHOULD warn users about
  declared external domains.
- ChatGPT: apps declaring `frame_domains` (nested iframes) "are subject to
  stricter review and are likely to be rejected for broad distribution unless
  iframe content is core to the use case".

## The two options

### A. Embedded view — a nested iframe of our own map

The view is a thin HTML shell that frames
`https://www.openwinemap.com/embed/<locale>/<slug(s)>`.

- csp: `frameDomains: ["https://www.openwinemap.com"]`; nothing else.
- Site work: an embed mode in app.js (no sidebar / chrome, accept a slug list,
  highlight + fit); `/embed/*` must be frameable — today every page sends
  `X-Frame-Options: SAMEORIGIN` (deploy.py security headers), so an edge-rule
  exception for `/embed/*` with `Content-Security-Policy: frame-ancestors`
  listing the host sandbox origins (an open-ended, host-specific list) or `*`.
- \+ Full fidelity for free: the real map, styles, LOD, panel, our own CSP and
  workers (the inner frame is our origin, so no worker or CORS question).
- − Depends on each host honouring `frameDomains`; ChatGPT reviews it strictly;
  three frames deep (host → sandbox → view → our page); relaxing framing on our
  origin; the host's theme / size signals stop at the shell.

### B. MapLibre widget — the map rendered in the view itself

The view is one self-contained HTML file: MapLibre GL + pmtiles + the MCP Apps
SDK + a small renderer, with MapLibre's worker inlined as a `blob:` URL (the
TomTom pattern). It draws our existing vector tiles over the basemap.

- csp: `connectDomains` and `resourceDomains`: `https://www.openwinemap.com`
  (the two `.pmtiles`, fetched with HTTP Range) and the basemap host(s).
- Site work: CORS on `/map-data/*.pmtiles` (Bunny edge rule:
  `Access-Control-Allow-Origin: *`, `Access-Control-Expose-Headers:
  Content-Range, Content-Length, ETag`, OPTIONS answered) — the tiles are
  public, read-only, already served to every visitor. No framing change.
- Basemap: CARTO raster is keyed per host (`CARTO_BASEMAP_KEYS`) and a key may
  be restricted to our domains — the sandbox origin is not ours. Either a CARTO
  key allowed from any origin, or the staged key-free OpenFreeMap vector style
  (scripts/_lib/vendor/openfreemap-*.json; needs its tile/glyph/sprite hosts in
  the csp). Our style draws no text labels, so the appellation layers need no
  glyphs.
- \+ One frame; no reliance on `frameDomains` (no ChatGPT review penalty); the
  view gets host theme (light / dark) and size natively; proven in production
  by TomTom on the same hosts.
- − A second, small renderer to keep in step with the map's styling (paint
  colours by kind, outlines, the overview / detail crossfade); depends on hosts
  allowing `blob:` workers (Claude, ChatGPT, VS Code do; the spec does not
  promise it); ~1.3 MB inlined HTML (MapLibre ~0.8 MB + worker ~0.46 MB) inside
  the edge bundle — fine against the 10 MB limit, to be measured against the
  500 ms startup.

### Recommendation: B, the widget

It works on the hosts that matter without asking them to allow a nested frame
of a third-party origin, needs no framing exception on the site, and has a
production precedent on exactly those hosts. A's real advantage — full
fidelity — matters less in a chat-sized view, where the job is "these
appellations, here, highlighted"; the full map stays one click away
(`app.openLink`). Keep A as the fallback if a host turns out to block `blob:`
workers.

## Design (option B)

- **Tool**: a new `show_on_map` {`slugs`: up to 200, `locale`?} with
  `_meta.ui.resourceUri: "ui://open-wine-map/map"`. The data tools stay
  text-only, so a map appears when the model decides to show one, not on every
  search. Its text result is the map link(s) — the fallback for hosts without
  MCP Apps, and for Le Chat. The result's `structuredContent` carries what the
  view needs: per slug name, kind, country, bbox, page URL, plus the union bbox.
- **View**: fit the union bbox; draw the overview and detail layers from the
  live pmtiles, filtered to the requested slugs (others faint or hidden);
  click a polygon → name + "Open on Open Wine Map" (`app.openLink`); a
  fullscreen button (`requestDisplayMode`); host theme → light / dark paint.
- **Styling in step**: the paint expressions (fill colours by kind, outline
  ramps) move from `map_template.py` / `app.js` into a shared module consumed
  by both the map and the widget build, so a colour change cannot drift.
- **Build**: `mcp/view/` → one HTML file (esbuild + inlined worker, the TomTom
  `setWorkerUrl(blob)` pattern) → embedded as a string in the edge bundle.
- **Server**: `registerAppResource` / `registerAppTool` from
  `@modelcontextprotocol/ext-apps/server`, gated by `getUiCapability` — hosts
  without the extension get `show_on_map` as a plain text tool.
- **Analytics**: `MCP Tool` already counts `show_on_map` calls; a view-loaded
  ping is not possible without a `connectDomains` entry for Plausible — skip.

## Phases

| # | work | exit criterion |
|---|---|---|
| 0 | spike on the throw-away `owm-mcp-spike` script: `show_on_map` + a minimal view (MapLibre, inlined worker, one pmtiles source proxied with CORS by the spike script itself, so the production site is untouched) | renders Priorat on Claude (Boris's account) and in the ext-apps reference host; worker and tiles load under the host CSP; bundle size and cold start measured |
| 1 | CORS on `/map-data/*` (deploy.py, idempotent edge rule); basemap decision | pmtiles load from a foreign origin with Range; no change for the site |
| 2 | shared paint module; the view proper (both LOD sources, highlight, click, fullscreen, theme) | headless test of the view with a stubbed host (`postMessage`) |
| 3 | server: app resource + `show_on_map`, capability-gated; text fallback | protocol tests: UI host gets `_meta.ui`, plain host gets text |
| 4 | deploy, docs (CLAUDE.md, mcp/README, About / llms.txt mention), live checks on Claude and ChatGPT | the map shows in both; Le Chat still gets the link |

## Open decisions

1. Basemap in the widget: CARTO with an unrestricted key, or switch the widget
   (only) to the key-free OpenFreeMap vector style?
2. `show_on_map` as its own tool (recommended) or a UI on `get_appellation` /
   `filter_appellations`?
3. ChatGPT: personal use via developer mode only, or aim for the app directory
   (review, which the widget option keeps open)?

## Sources

- MCP Apps spec (stable): https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx
- MCP Apps overview: https://blog.modelcontextprotocol.io/tags/apps/
- TomTom MapLibre-in-MCP-Apps (inlined blob worker, Claude CSP): https://github.com/tomtom-international/tomtom-maps-mcp/pull/255
- ChatGPT Apps SDK, custom UX / frame domains: https://developers.openai.com/apps-sdk/build/custom-ux
- MCP App resource metadata (CSP fields, ChatGPT widget fields): https://sunpeak.ai/blogs/mcp-app-resource-metadata
- MCP App CSP explained: https://dev.to/cptrodgers/mcp-app-csp-explained-why-your-widget-wont-render-9n1
