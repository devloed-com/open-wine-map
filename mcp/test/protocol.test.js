import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, haveBuild } from './local.js';
import { smoke, MODES, SMOKE_CALLS } from './smoke.js';

const skip = haveBuild() ? false : 'no wiki/ build (run scripts/04_build_maps.py)';
let srv;
before(async () => { if (!skip) srv = await startServer(); });
after(async () => { if (srv) await srv.close(); });

const TOOLS = ['filter_appellations', 'get_appellation', 'list_facets', 'search_appellations'];

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
    assert.match(get.url, /\/fr\/priorat$/);
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

test('GET is 405 and other paths are 404, with CORS', { skip }, async () => {
  const get = await fetch(srv.url, { headers: { Accept: 'text/event-stream' } });
  assert.equal(get.status, 405);
  assert.equal(get.headers.get('access-control-allow-origin'), '*');
  const other = await fetch(srv.url.replace('/mcp', '/'));
  assert.equal(other.status, 404);
  const pre = await fetch(srv.url, { method: 'OPTIONS' });
  assert.equal(pre.status, 204);
});
