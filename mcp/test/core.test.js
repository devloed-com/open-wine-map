// The shared query core against the built query context (wiki/data/mcp/).
// These anchors are the same answers the map page's WebMCP tools give.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { WIKI, haveBuild } from './local.js';
import { coreFromContext, createContextStore } from '../src/context.js';
import { QueryError } from '../../scripts/_lib/assets/query_core.mjs';

const skip = haveBuild() ? false : 'no wiki/ build (run scripts/04_build_maps.py)';
const load = locale => JSON.parse(readFileSync(path.join(WIKI, 'data', 'mcp', `${locale}.json`), 'utf8'));
const cores = {};
const core = locale => (cores[locale] ||= coreFromContext(load(locale), 'https://www.openwinemap.com'));
const slugs = res => res.results.map(r => r.slug);

test('search: exact names rank first, sub-denominations after parents', { skip }, () => {
  assert.equal(core('en').search({ query: 'Priorat' }).results[0].slug, 'priorat');
  assert.equal(core('en').search({ query: 'montsant' }).results[0].slug, 'montsant');
  const rioja = core('en').search({ query: 'rioja', limit: 10 }).results;
  assert.equal(rioja[0].slug, 'rioja');
  assert.ok(rioja.findIndex(r => r.is_sub_denomination) > 0);
});

test('search: punctuation folds and romanised Greek / Bulgarian names match', { skip }, () => {
  assert.equal(core('en').search({ query: 'aloxe corton' }).results[0].slug, 'aloxe-corton');
  const naoussa = core('en').search({ query: 'naoussa' }).results[0];
  assert.equal(naoussa.country, 'gr');
  assert.ok(core('en').search({ query: 'agio oros' }).total >= 1);
});

test('search: country narrows; an empty query is a QueryError', { skip }, () => {
  assert.ok(slugs(core('en').search({ query: 'champagne', country: 'es' })).every(s => s !== 'champagne'));
  assert.throws(() => core('en').search({ query: ' - ' }), QueryError);
});

test('filter: grape synonyms, region labels, styles and schemes', { skip }, () => {
  const garnacha = slugs(core('en').filter({ country: 'es', grape: 'Garnacha', limit: 200 }));
  assert.ok(garnacha.includes('priorat') && garnacha.includes('montsant'));
  assert.ok(slugs(core('en').filter({ grape: 'malbec', limit: 200 })).includes('cahors'));
  assert.ok(slugs(core('en').filter({ region: 'Cataluña', limit: 200 })).includes('priorat'));
  assert.ok(slugs(core('en').filter({ region: 'catalonia', limit: 200 })).includes('priorat'));
  assert.equal(core('en').filter({ scheme: 'Vino de Pago', limit: 1 }).total,
    core('en').filter({ scheme: 'es:vino-de-pago', limit: 1 }).total);
  assert.ok(slugs(core('en').filter({ country: 'fr', style: 'sparkling', limit: 200 })).includes('champagne'));
  const docg = core('en').filter({ scheme: 'docg', limit: 200 });
  assert.ok(docg.total >= 70 && docg.results.every(r => r.country === 'it'));
  assert.equal(core('en').filter({ scheme: 'it:docg', limit: 200 }).total, docg.total);
  assert.throws(() => core('en').filter({ grape: 'not-a-grape-at-all' }), QueryError);
  assert.throws(() => core('en').filter({ region: '!!' }), QueryError);
});

test('filter: sub-denominations and spirits only on request', { skip }, () => {
  const base = core('en').filter({ country: 'fr', limit: 1 }).total;
  assert.ok(core('en').filter({ country: 'fr', include_sub_denominations: true, limit: 1 }).total > base);
  assert.ok(core('en').filter({ country: 'fr', include_spirits: true, limit: 1 }).total > base);
});

test('full: panel merge, attribution, locale labels', { skip }, () => {
  const panel = JSON.parse(readFileSync(path.join(WIKI, 'data', 'd', 'fr', 'priorat.json'), 'utf8'));
  const ctx = load('fr');
  const r = core('fr').full('priorat', { ...ctx.aocs.priorat, ...panel }, true);
  assert.equal(r.url, 'https://www.openwinemap.com/fr/priorat');
  assert.ok(r.grapes.principal.length > 0);
  assert.ok(r.terroir_facts.length > 0 && r.terroir_facts_attribution);
  assert.ok(Object.values(r.sources).every(u => /^https?:\/\//.test(u)));
  const partial = core('fr').full('priorat', ctx.aocs.priorat, false);
  assert.ok(partial.detail_unavailable);
  assert.throws(() => core('fr').full('no-such-slug'), QueryError);
});

test('facets: values round-trip into filter', { skip }, () => {
  const f = core('en').facets();
  assert.ok(f.countries.length >= 19);
  const region = f.regions.find(r => r.country === 'es');
  assert.equal(core('en').filter({ region: region.value, limit: 1 }).total >= 1, true);
  const scheme = f.schemes.find(s => s.value.includes(':'));
  assert.equal(core('en').filter({ scheme: scheme.value, limit: 1 }).total, scheme.count);
  const style = f.styles[0];
  assert.ok(core('en').filter({ style: style.value, limit: 1 }).total >= style.count);
});

test('context store: ETag revalidation, stale copy on failure, one cold load', async () => {
  let t = 0;
  const calls = [];
  let mode = 'ok';
  const ctx = { format_version: 1, locale: 'en', aocs: { a: { name: 'A' } }, labels: {} };
  const fetchImpl = async (url, init) => {
    calls.push(init && init.headers['If-None-Match']);
    if (mode === 'down') return new Response('x', { status: 503 });
    if (init && init.headers['If-None-Match'] === '"v1"') return new Response(null, { status: 304 });
    return new Response(JSON.stringify(ctx), { status: 200, headers: { ETag: '"v1"' } });
  };
  const store = createContextStore({ dataOrigin: 'https://x', fetchImpl, ttlMs: 1000, now: () => t });
  const [a, b] = await Promise.all([store.get('en'), store.get('en')]);
  assert.equal(calls.length, 1, 'concurrent cold loads share one fetch');
  assert.equal(a.core.search({ query: 'a' }).results[0].slug, 'a');
  assert.equal(a, b);
  await store.get('en');
  assert.equal(calls.length, 1, 'fresh copy within the TTL');
  t = 2000;
  await store.get('en');
  assert.equal(calls[1], '"v1"', 'revalidates with the ETag');
  t = 4000;
  mode = 'down';
  const stale = await store.get('en');
  assert.equal(stale.core.search({ query: 'a' }).total, 1, 'keeps serving the copy it has');
  await assert.rejects(store.get('de'));
});
