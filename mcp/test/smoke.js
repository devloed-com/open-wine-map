// Connects the official MCP client to `url` once per protocol mode (2025-era
// legacy handshake, 2026-07-28 pinned, auto-negotiated) and exercises the
// server. Used by the tests against a local server and, as a CLI, against a
// deployed endpoint:  node test/smoke.js https://mcp.openwinemap.com/mcp
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

export const MODES = {
  legacy: undefined,
  modern: { mode: { pin: '2026-07-28' } },
  auto: { mode: 'auto' },
};

export async function smoke(url, mode, calls) {
  const opts = MODES[mode] ? { versionNegotiation: MODES[mode] } : {};
  const client = new Client({ name: 'owm-smoke', version: '0' }, opts);
  // X-OWM-Smoke: the edge script does not count test traffic as `MCP Tool` events.
  const transport = new StreamableHTTPClientTransport(new URL(url), { requestInit: { headers: { 'X-OWM-Smoke': '1' } } });
  const t0 = performance.now();
  await client.connect(transport);
  const connectMs = performance.now() - t0;
  try {
    const tools = (await client.listTools()).tools.map(t => t.name);
    const results = [];
    for (const [name, args] of calls) results.push(await client.callTool({ name, arguments: args }));
    return {
      mode,
      era: client.getProtocolEra(),
      version: client.getNegotiatedProtocolVersion(),
      server: client.getServerVersion(),
      instructions: client.getInstructions ? client.getInstructions() : undefined,
      connectMs: Math.round(connectMs),
      tools,
      results,
    };
  } finally {
    await client.close();
  }
}

export const SMOKE_CALLS = [
  ['search_appellations', { query: 'priorat', limit: 3 }],
  ['get_appellation', { slug: 'priorat', locale: 'fr' }],
  ['filter_appellations', { country: 'es', grape: 'Garnacha', style: 'red', limit: 200 }],
  ['list_facets', {}],
];

// Poll until the endpoint reports `version` (a just-published release can
// take a moment to replace the isolates still serving the previous one).
export async function waitForVersion(url, version, timeoutMs = 120000) {
  const until = Date.now() + timeoutMs;
  let seen;
  while (Date.now() < until) {
    try {
      const r = await smoke(url, 'modern', []);
      seen = r.server && r.server.version;
      if (seen === version) return seen;
    } catch (e) {
      seen = String((e && e.message) || e);
    }
    await new Promise(res => setTimeout(res, 3000));
  }
  throw new Error(`${url} still reports ${seen}, expected ${version}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [url, expect] = [process.argv[2], process.argv.indexOf('--expect-version')];
  if (!url) throw new Error('usage: node test/smoke.js <mcp-url> [--expect-version V]');
  if (expect > 0) console.log(JSON.stringify({ version: await waitForVersion(url, process.argv[expect + 1]) }));
  for (const mode of Object.keys(MODES)) {
    try {
      const r = await smoke(url, mode, SMOKE_CALLS);
      const [search, get, filter, facets] = r.results.map(x => x.structuredContent || x.content);
      console.log(JSON.stringify({
        mode, era: r.era, version: r.version, connectMs: r.connectMs, tools: r.tools,
        search_top: search.results && search.results.map(x => x.slug),
        get: get.name && { name: get.name, region: get.region, grapes: get.grapes.principal.length, facts: (get.terroir_facts || []).length },
        filter_total: filter.total,
        facets: facets.countries && { countries: facets.countries.length, regions: facets.regions.length },
      }));
    } catch (e) {
      console.log(JSON.stringify({ mode, error: String((e && e.message) || e) }));
      process.exitCode = 1;
    }
  }
}
