import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, haveBuild } from './local.js';
import { smoke, MODES, SMOKE_CALLS } from './smoke.js';
import { callProps, clientProps, resultProps, uaToken } from '../src/server.js';
import { connectProps } from '../src/http.js';

const skip = haveBuild() ? false : 'no wiki/ build (run scripts/04_build_maps.py)';
let srv;
before(async () => { if (!skip) srv = await startServer(); });
after(async () => { if (srv) await srv.close(); });

const TOOLS = ['filter_appellations', 'get_appellation', 'list_facets', 'search_appellations', 'show_on_map'];

for (const mode of Object.keys(MODES)) {
  test(`connects and answers every tool (${mode})`, { skip }, async () => {
    const r = await smoke(srv.url, mode, SMOKE_CALLS);
    assert.equal(r.era, mode === 'legacy' ? 'legacy' : 'modern');
    assert.deepEqual([...r.tools].sort(), TOOLS);
    const [search, get, filter, facets] = r.results.map(x => x.structuredContent);
    assert.equal(search.results[0].slug, 'priorat');
    assert.equal(get.slug, 'priorat');
    assert.ok(get.grapes.principal.length > 0);
    assert.ok(get.terroir_facts.length > 0, 'priorat carries terroir facts');
    assert.equal(get.detail_unavailable, undefined);
    assert.match(get.url, /\/fr\/priorat\?utm_medium=mcp$/);
    assert.ok(filter.results.some(x => x.slug === 'priorat'));
    assert.ok(facets.countries.length >= 19);
  });
}

test('tool errors are results, not protocol errors', { skip }, async () => {
  const r = await smoke(srv.url, 'modern', [
    ['get_appellation', { slug: 'no-such-slug' }],
    ['filter_appellations', { grape: 'not-a-grape-at-all' }],
    ['filter_appellations', { style: '!!' }],
    ['search_appellations', { query: '  ' }],
  ]);
  for (const res of r.results) assert.equal(res.isError, true);
  assert.match(r.results[0].content[0].text, /unknown appellation slug/);
});

test('arguments outside the schema are rejected', { skip }, async () => {
  const r = await smoke(srv.url, 'modern', [
    ['get_appellation', { slug: '../../etc/passwd' }],
    ['search_appellations', { query: 'x', limit: 500 }],
    ['search_appellations', { query: 'x', locale: 'de' }],
  ]);
  for (const res of r.results) assert.equal(res.isError, true);
});

test('analytics: what a call fetched, found and who called, never query text', { skip }, async () => {
  const events = [];
  const local = await startServer({ track: () => (event, props) => events.push({ event, ...props }) });
  const who = { era: 'modern', ua: 'node', client: 'owm-smoke', client_version: '0' };
  try {
    const r = await smoke(local.url, 'modern', [
      ['search_appellations', { query: 'priorat' }],
      ['get_appellation', { slug: 'priorat', locale: 'fr' }],
      ['get_appellation', { slug: 'no-such-slug' }],
      ['filter_appellations', { country: 'es', grape: 'Garnacha', style: 'tinto-no-such' }],
      ['filter_appellations', { country: 'es', grape: 'Garnacha', limit: 1 }],
    ]);
    assert.equal(r.results.length, 5);
    const [connect, ...tools] = events;
    assert.deepEqual(connect, { event: 'MCP Connect', ...who, protocol: '2026-07-28' });
    const garnacha = tools[4];
    assert.ok(garnacha.result_count > 1, 'the count is the total, not the page');
    assert.deepEqual(tools, [
      { event: 'MCP Tool', tool: 'search_appellations', locale: 'en', result_count: 1, had_match: 'true', ...who },
      { event: 'MCP Tool', tool: 'get_appellation', locale: 'fr', slug: 'priorat', ...who },
      { event: 'MCP Tool', tool: 'get_appellation', locale: 'en', error: 'invalid', ...who },
      { event: 'MCP Tool', tool: 'filter_appellations', locale: 'en', criteria: 'country,style,grape', country: 'es', grape: 'grenache', error: 'invalid', ...who },
      { event: 'MCP Tool', tool: 'filter_appellations', locale: 'en', criteria: 'country,grape', country: 'es', grape: 'grenache', result_count: garnacha.result_count, had_match: 'true', ...who },
    ]);
    assert.ok(!Object.values(tools[0]).includes('priorat'), 'a search\'s query text is never sent');
    events.length = 0;
    await smoke(local.url, 'legacy', [['list_facets', {}]]);
    assert.deepEqual(events, [
      { event: 'MCP Connect', era: 'legacy', ua: 'node', client: 'owm-smoke', client_version: '0', protocol: events[0].protocol },
      { event: 'MCP Tool', tool: 'list_facets', locale: 'en', era: 'legacy', ua: 'node' },
    ]);
    assert.match(events[0].protocol, /^2025-/);
    events.length = 0;
    const { Client, StreamableHTTPClientTransport } = await import('@modelcontextprotocol/client');
    const client = new Client({ name: 't', version: '1' }, { versionNegotiation: { mode: { pin: '2026-07-28' } } });
    await client.connect(new StreamableHTTPClientTransport(new URL(local.url)));
    try {
      events.length = 0;
      const res = await client.callTool({ name: 'show_on_map', arguments: { slugs: ['priorat', 'montsant', 'nope', 'priorat'] } });
      assert.deepEqual(events, [{ event: 'MCP Tool', tool: 'show_on_map', locale: 'en', slugs: 'priorat,montsant', count: 2, era: 'modern', ua: 'node', client: 't', client_version: '1' }]);
      assert.match(res.structuredContent.map_url, /\/\?aocs=priorat,montsant&utm_medium=mcp$/);
    } finally {
      await client.close();
    }
  } finally {
    await local.close();
  }
});

test('analytics: client props name the software, never more', () => {
  const req = ua => new Request('https://mcp.test/mcp', { headers: ua ? { 'User-Agent': ua } : {} });
  assert.equal(uaToken('Claude-User/1.0 (+https://claude.ai)'), 'claude-user');
  assert.equal(uaToken('python-httpx/0.28.1'), 'python-httpx');
  assert.equal(uaToken('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141'), 'browser');
  assert.equal(uaToken(''), '(none)');
  assert.deepEqual(clientProps({ name: ' claude-ai ', version: '0.1.0' }, 'legacy', req('node')),
    { era: 'legacy', ua: 'node', client: 'claude-ai', client_version: '0.1.0' });
  assert.deepEqual(clientProps({ name: '' }, undefined, req()), { era: '(unknown)', ua: '(none)' });
  assert.deepEqual(resultProps('list_facets', { countries: [] }), {});
  assert.deepEqual(resultProps('search_appellations', { results: [] }), { result_count: 0, had_match: 'false' });
});

test('analytics: MCP Connect reads the opening request only', async () => {
  const post = (body, extra = {}) => {
    const text = JSON.stringify(body);
    return new Request('https://mcp.test/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': String(text.length), 'User-Agent': 'openai-mcp/1.0.0', ...extra },
      body: text,
    });
  };
  const init = { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', clientInfo: { name: 'openai-mcp', version: '1.0.0' }, capabilities: {} } };
  const request = post(init);
  assert.deepEqual(await connectProps(request),
    { era: 'legacy', ua: 'openai-mcp', client: 'openai-mcp', client_version: '1.0.0', protocol: '2025-06-18' });
  assert.deepEqual(await request.json(), init, 'the body is still there for the SDK');
  assert.equal(await connectProps(post({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'x' } })), null);
  assert.equal(await connectProps(post(init, { 'Content-Length': String(70 * 1024) })), null);
  assert.equal(await connectProps(new Request('https://mcp.test/mcp')), null);
});

test('analytics: a large show_on_map set is cut at a slug boundary', () => {
  const slugs = Array.from({ length: 200 }, (_, i) => `appellation-number-${String(i).padStart(3, '0')}`);
  const entry = { aocs: Object.fromEntries(slugs.map(s => [s, {}])) };
  const p = callProps('show_on_map', { slugs }, entry);
  assert.equal(p.count, 200);
  assert.ok(p.slugs.length <= 2000);
  assert.ok(p.slugs.split(',').every(s => entry.aocs[s]));
  assert.deepEqual(callProps('get_appellation', { slug: 'x' }, null), {});
});

test('GET is 405 and other paths are 404, with CORS', { skip }, async () => {
  const get = await fetch(srv.url, { headers: { Accept: 'text/event-stream' } });
  assert.equal(get.status, 405);
  assert.equal(get.headers.get('access-control-allow-origin'), '*');
  const other = await fetch(srv.url.replace('/mcp', '/'));
  assert.equal(other.status, 404);
  const pre = await fetch(srv.url, { method: 'OPTIONS' });
  assert.equal(pre.status, 204);
});

test('show_on_map: briefs with bbox, union bbox, map links, UI resource', { skip }, async () => {
  const { Client, StreamableHTTPClientTransport } = await import('@modelcontextprotocol/client');
  const client = new Client({ name: 't', version: '0' }, { versionNegotiation: { mode: { pin: '2026-07-28' } } });
  await client.connect(new StreamableHTTPClientTransport(new URL(srv.url)));
  try {
    const tool = (await client.listTools()).tools.find(t => t.name === 'show_on_map');
    assert.equal(tool._meta.ui.resourceUri, 'ui://open-wine-map/map');
    const res = await client.callTool({ name: 'show_on_map', arguments: { slugs: ['priorat', 'montsant', 'nope'] } });
    const out = res.structuredContent;
    assert.deepEqual(out.appellations.map(a => a.slug), ['priorat', 'montsant']);
    assert.deepEqual(out.unknown, ['nope']);
    assert.equal(out.bbox.length, 4);
    assert.ok(out.appellations.every(a => a.bbox && a.kind && a.url));
    assert.match(res.content[0].text, /\[Priorat\]\(https:\/\/data\.test\/en\/priorat\?utm_medium=mcp\)/);
    assert.equal(out.map_url, 'https://data.test/?aocs=priorat,montsant&utm_medium=mcp');
    assert.match(out.tiles.overview, /^\/map-data\/appellations-overview\.pmtiles\?v=[0-9a-f]{8}$/);
    assert.match(out.tiles.detail, /^\/map-data\/appellations\.pmtiles\?v=[0-9a-f]{8}$/);
    assert.ok(res.content[0].text.includes('All of them on the map: https://data.test/?aocs=priorat,montsant&utm_medium=mcp'));
    // A set over 50 (the 51 Alsace grands crus) still links the set, not the homepage.
    const crus = (await client.callTool({ name: 'search_appellations', arguments: { query: 'Alsace grand cru', limit: 60 } }))
      .structuredContent.results.map(r => r.slug).filter(s => s.startsWith('alsace-grand-cru-'));
    assert.ok(crus.length > 50, `only ${crus.length} grands crus found`);
    const many = await client.callTool({ name: 'show_on_map', arguments: { slugs: crus } });
    assert.equal(many.structuredContent.map_url, `https://data.test/?aocs=${crus.join(',')}&utm_medium=mcp`);
    const one = await client.callTool({ name: 'show_on_map', arguments: { slugs: ['priorat'], locale: 'fr' } });
    assert.equal(one.structuredContent.map_url, 'https://data.test/fr/priorat?utm_medium=mcp');
    assert.ok(!one.content[0].text.includes('All of them'));
    const read = await client.readResource({ uri: 'ui://open-wine-map/map' });
    const c = read.contents[0];
    assert.equal(c.mimeType, 'text/html;profile=mcp-app');
    assert.deepEqual(c._meta.ui.csp.connectDomains, ['https://data.test', 'https://*.basemaps.cartocdn.com']);
    assert.ok(c.text.includes('"tileOrigin":"https://data.test"') && !c.text.includes('__OWM_VIEW_CONFIG__'));
    const bad = await client.callTool({ name: 'show_on_map', arguments: { slugs: ['nope'] } });
    assert.equal(bad.isError, true);
  } finally {
    await client.close();
  }
});

test('map view: its MCP Map Viewed event is configured only for a counted request', { skip }, async () => {
  const { Client, StreamableHTTPClientTransport } = await import('@modelcontextprotocol/client');
  const viewAnalytics = { host: 'https://plausible.test', domain: 'owm.test' };
  const readView = async opts => {
    const local = await startServer({ ...opts, viewAnalytics });
    const client = new Client({ name: 't', version: '0' }, { versionNegotiation: { mode: { pin: '2026-07-28' } } });
    await client.connect(new StreamableHTTPClientTransport(new URL(local.url)));
    try {
      return { origin: new URL(local.url).origin, c: (await client.readResource({ uri: 'ui://open-wine-map/map' })).contents[0] };
    } finally {
      await client.close();
      await local.close();
    }
  };
  const base = ['https://data.test', 'https://*.basemaps.cartocdn.com'];
  const counted = await readView({ track: () => () => {} });
  assert.deepEqual(counted.c._meta.ui.csp.connectDomains, [...base, 'https://plausible.test']);
  assert.deepEqual(counted.c._meta.ui.csp.resourceDomains, base);
  assert.ok(counted.c.text.includes(
    `"analytics":{"endpoint":"https://plausible.test/api/event","domain":"owm.test","url":"${counted.origin}/map"}`));
  // Not counted (a smoke test, no PLAUSIBLE_HOST): the view sends nothing and the CSP stays as it was.
  const quiet = await readView({});
  assert.deepEqual(quiet.c._meta.ui.csp.connectDomains, base);
  assert.ok(!quiet.c.text.includes('"analytics"'));
});
