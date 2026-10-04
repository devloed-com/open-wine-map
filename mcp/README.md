# Open Wine Map — remote MCP server

A stateless MCP server for the Open Wine Map corpus, deployed as a Bunny
standalone Edge Script at **https://mcp.openwinemap.com/mcp** (Streamable HTTP,
no authentication).

Tools — the same definitions and code the map page registers as WebMCP tools
(`scripts/_lib/assets/query_core.mjs`), plus a `locale` argument (en / fr / es / nl):

| tool | does |
|---|---|
| `search_appellations` | find appellations by name (romanised Greek / Bulgarian forms included) |
| `filter_appellations` | country, region, style, grape (VIVC synonyms), scheme / traditional term |
| `get_appellation` | grapes, styles, terroir facts with provenance, sources, attribution |
| `list_facets` | the values `filter_appellations` accepts, with counts |

## Layout

- `src/server.js` — tools + `createMcpHandler` (protocol 2026-07-28 and the
  2025-era stateless fallback)
- `src/context.js` — loads `/data/mcp/<locale>.json` from the site (written by
  stage 04), caches it per isolate, revalidates by ETag
- `src/http.js` — routing (`POST /mcp`), CORS, `no-store`
- `src/edge.js` — Bunny entry point; optional `MCP Tool` Plausible event

## Develop

```sh
npm ci
npm test                      # needs a stage-04 build in ../wiki for most tests
npm run build                 # → dist/edge.js (single file, uploaded as is)
node test/smoke.js https://mcp.openwinemap.com/mcp   # all three protocol modes
../.venv/bin/python test/parity_webmcp.py            # page WebMCP tools == server
```

Deploy: `.venv/bin/python scripts/deploy_mcp.py deploy` from the repo root
(see that script's docstring; `BUNNY_API_KEY`, `BUNNY_MCP_SCRIPT_ID` in `.env`).
Script variables: `DATA_ORIGIN` (default https://www.openwinemap.com),
`PLAUSIBLE_HOST`, `PLAUSIBLE_DOMAIN`.

Add it to a client: Le Chat → Connectors → Custom MCP Connector → server URL
`https://mcp.openwinemap.com/mcp`; Claude → Settings → Connectors → Add custom
connector, same URL.
