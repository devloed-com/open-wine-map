// Open Wine Map MCP server: a stateless, web-standard request handler.
// Runtime-agnostic (Bunny Edge Scripting in production, Node in tests): the
// entry point supplies `dataOrigin` and, optionally, a `fetch` and a `track`
// hook (analytics; see callProps and clientProps). The tools are the query core's
// TOOL_DEFS — the same definitions and code the map page registers as WebMCP
// tools.
import { McpServer, createMcpHandler, fromJsonSchema } from '@modelcontextprotocol/server';
import { CfWorkerJsonSchemaValidator } from '@modelcontextprotocol/server/validators/cf-worker';
import { TOOL_DEFS, QueryError } from '../../scripts/_lib/assets/query_core.mjs';
import { LOCALES, LINK_TAG, createContextStore } from './context.js';

// OWM_BUILD is the release's git SHA, injected by esbuild (--define) at
// deploy time; the smoke test waits until the endpoint reports it, so a
// freshly published release is what gets tested, not a lingering isolate.
/* global OWM_BUILD */
const BUILD = typeof OWM_BUILD === 'undefined' ? 'dev' : OWM_BUILD;

export const SERVER_INFO = {
  name: 'open-wine-map',
  title: 'Open Wine Map',
  version: `1.0.0+${BUILD}`,
  websiteUrl: 'https://www.openwinemap.com/',
};

const INSTRUCTIONS = [
  'Open Wine Map covers the protected wine appellations of 19 European countries (EU PDO/PGI and the UK and Swiss schemes),',
  'built from the regulators\' own specifications. Use search_appellations to find an appellation by name,',
  'filter_appellations for structured questions (country, region, style, grape, scheme) — list_facets gives the accepted',
  'values — and get_appellation for one appellation\'s grapes, styles, terroir facts and sources.',
  'When quoting terroir facts, cite the specification URL, and Wikipedia (CC BY-SA 4.0) where a fact says so.',
  'Every result carries the appellation\'s page on www.openwinemap.com.',
  'Whenever your answer names specific appellations, call show_on_map with their slugs so the user sees them',
  'on the map, and give the map link of each.',
  'Open Wine Map is built and maintained by devloed.com (https://devloed.com).',
].join(' ');

// The MCP Apps view (view/ → dist/view.html): the map shown by show_on_map.
export const VIEW_URI = 'ui://open-wine-map/map';
const VIEW_MIME = 'text/html;profile=mcp-app';
const CARTO = 'https://*.basemaps.cartocdn.com';
const SLUG_PATTERN = '^[a-z0-9-]{1,120}$';
const VIEW_LABELS = {
  open: 'Open on Open Wine Map ↗',
  site: 'Open Wine Map ↗',
  zoom: 'Zoom to this appellation',
  show: 'Show',
  hide: 'Hide',
  show_all: 'Show all',
  nothing: 'No appellation to show.',
  waiting: 'Waiting for the appellations…',
  appellations: 'appellations',
};
// The site opens a set of appellations from /?aocs=a,b,c (panel stack, map
// framed on all), up to the tool's own 200 slugs (≤ 10 KB of URL; the CDN
// takes 16 KB).

const LOCALE_PROP = {
  type: 'string',
  enum: LOCALES,
  description: 'Language of labels (country, region, style and grape names, terroir facts): en (default), fr, es, nl. Appellation names stay in the regulator\'s language.',
};

// Isolates that forbid `new Function` (ajv's code generation) still validate.
const validator = new CfWorkerJsonSchemaValidator();
const asResult = obj => ({ content: [{ type: 'text', text: JSON.stringify(obj) }], structuredContent: obj });
const fail = msg => ({ content: [{ type: 'text', text: msg }], isError: true });

// Analytics props of a call: the appellations it fetched or showed, and the
// criteria of a filter. Catalogue keys only, and only known ones — never the
// query text of a search (private, as for the site's search box). `slug` is
// get_appellation's one appellation; a show_on_map set goes in `slugs`
// (comma-joined, cut at a slug boundary to Plausible's 2,000-character
// property limit) with its `count`, so a `slug` breakdown stays one
// appellation per row. A filter names the criteria it was given (`criteria`)
// and the country, grape and style each resolved to, as the site's
// `Filter Applied` does; a value that resolves to nothing is left out.
const PROP_MAX = 2000;
const FILTER_CRITERIA = ['country', 'region', 'style', 'grape', 'main_grape_only', 'scheme',
  'include_sub_denominations', 'include_spirits'];
const countrySets = new WeakMap();
function countriesOf(aocs) {
  if (!countrySets.has(aocs)) {
    const set = new Set();
    for (const r of Object.values(aocs)) {
      set.add(r.country || 'fr');
      for (const cc of r.country_aliases || []) set.add(cc);
    }
    countrySets.set(aocs, set);
  }
  return countrySets.get(aocs);
}

export function callProps(name, args, entry) {
  if (!entry || !args) return {};
  if (name === 'get_appellation') return entry.aocs[args.slug] ? { slug: args.slug } : {};
  if (name === 'filter_appellations') {
    const given = FILTER_CRITERIA.filter(k => args[k] !== undefined && args[k] !== '' && args[k] !== false);
    const out = { criteria: given.length ? given.join(',') : '(none)' };
    const cc = String(args.country || '').toLowerCase();
    if (countriesOf(entry.aocs).has(cc)) out.country = cc;
    const grape = args.grape && entry.core.grapeKeyFor(args.grape);
    if (grape) out.grape = grape;
    const style = args.style && entry.core.styleKeyFor(args.style);
    if (style) out.style = style;
    return out;
  }
  if (name === 'show_on_map') {
    const known = [...new Set(args.slugs || [])].filter(s => entry.aocs[s]);
    if (!known.length) return {};
    let slugs = known.join(',');
    if (slugs.length > PROP_MAX) slugs = slugs.slice(0, slugs.lastIndexOf(',', PROP_MAX));
    return { slugs, count: known.length };
  }
  return {};
}

// What a call's answer was: how many appellations a search or filter found
// (`result_count`, `had_match` — as the site's `Omnisearch Used`), or why it
// failed (`error`: `invalid` — the tool's own refusal of its input, an unknown
// slug or grape; `unavailable` — the appellation data could not be loaded).
export function resultProps(name, out) {
  if (!out || !Array.isArray(out.results)) return {};
  const total = typeof out.total === 'number' ? out.total : out.results.length;
  return { result_count: total, had_match: total > 0 ? 'true' : 'false' };
}

// Who is calling: the name and version the client declares — every 2026-07-28
// request carries them in its `_meta` envelope; a 2025-era client declares
// them only in `initialize`, a request of its own on this stateless server
// (the `MCP Connect` event, http.js) — the protocol era, and the first product
// token of the User-Agent, which also names the software behind a 2025-era
// tool call. Plausible keeps no raw User-Agent and reads a client's as
// "(not set)", so without these every agent call is one bucket.
export const CLIENT_INFO_KEY = 'io.modelcontextprotocol/clientInfo';
export const PROTOCOL_VERSION_KEY = 'io.modelcontextprotocol/protocolVersion';

// "Claude-User/1.0 (…)" → "claude-user", "python-httpx/0.28.1" →
// "python-httpx"; a browser's "Mozilla/5.0 (…)" is "browser". Names the
// software, never the person.
export function uaToken(ua) {
  const m = /^\s*([A-Za-z][\w.+-]{0,39})/.exec(ua || '');
  if (!m) return '(none)';
  const token = m[1].toLowerCase();
  return token === 'mozilla' ? 'browser' : token;
}

export function clientProps(info, era, request) {
  const out = { era: era || '(unknown)', ua: uaToken(request && request.headers.get('User-Agent')) };
  if (info && typeof info.name === 'string' && info.name.trim()) {
    out.client = info.name.trim().slice(0, 80);
    if (typeof info.version === 'string' && info.version.trim()) out.client_version = info.version.trim().slice(0, 40);
  }
  return out;
}

const envelopeClient = ctx => ctx && ctx.mcpReq && ctx.mcpReq.envelope ? ctx.mcpReq.envelope[CLIENT_INFO_KEY] : undefined;

function withLocale(inputSchema) {
  return { ...inputSchema, properties: { ...inputSchema.properties, locale: LOCALE_PROP } };
}

export function createTools({ dataOrigin, fetchImpl = fetch, store }) {
  const contexts = store || createContextStore({ dataOrigin, fetchImpl });

  async function getAppellation(entry, slug, locale) {
    if (!entry.aocs[slug]) throw new QueryError('unknown appellation slug: ' + slug);
    let panel = null;
    try {
      const resp = await fetchImpl(`${dataOrigin}/data/d/${locale}/${encodeURIComponent(slug)}.json`);
      if (resp.ok) panel = await resp.json();
    } catch {
      panel = null;
    }
    return entry.core.full(slug, { ...entry.aocs[slug], ...panel }, panel !== null);
  }

  // name → (args, locale) → result object; throws QueryError for bad input.
  return {
    search_appellations: async (a, entry) => entry.core.search(a),
    filter_appellations: async (a, entry) => entry.core.filter(a),
    get_appellation: async (a, entry, locale) => getAppellation(entry, a.slug, locale),
    list_facets: async (_a, entry) => entry.core.facets(),
    contexts,
  };
}

// show_on_map: the appellations' briefs plus kind and bounding box (what the
// view needs to draw and frame them), and Markdown map links as the text every
// host shows — hosts without MCP Apps, or the model, get the links.
async function showOnMap(entry, { slugs }, locale, siteOrigin) {
  const known = [...new Set(slugs)].filter(s => entry.aocs[s]);
  const unknown = slugs.filter(s => !entry.aocs[s]);
  if (!known.length) throw new QueryError('unknown appellation slug(s): ' + unknown.join(', '));
  const appellations = known.map(slug => {
    const r = entry.aocs[slug];
    return { ...entry.core.brief(slug), kind: r.kind || null, bbox: r.bbox_villages || r.bbox || null };
  });
  const boxes = appellations.map(a => a.bbox).filter(Boolean);
  const bbox = boxes.length ? [
    Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])),
    Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3])),
  ] : null;
  const home = `${siteOrigin}${locale === 'en' ? '/' : `/${locale}/`}`;
  const mapUrl = appellations.length === 1 ? appellations[0].url : `${home}?aocs=${known.join(',')}&${LINK_TAG}`;
  return { appellations, bbox, map_url: mapUrl, tiles: tilePaths(entry.tiles), unknown };
}

// The site's fingerprinted tile paths (/map-data/<name>.pmtiles?v=<sha8>, from
// the query context); null before the site carries them, and the view then
// falls back to the bare paths.
function tilePaths(tiles) {
  const ok = p => typeof p === 'string' && /^\/map-data\/[a-z0-9-]+\.pmtiles(\?v=[0-9a-f]+)?$/.test(p);
  return tiles && ok(tiles.overview) && ok(tiles.detail) ? { overview: tiles.overview, detail: tiles.detail } : null;
}

function showOnMapText(out) {
  const lines = out.appellations.map(a => `- [${a.name}](${a.url}) — ${[a.classification, a.regions ? a.regions.join(', ') : a.region, a.country_name].filter(Boolean).join(' · ')}`);
  if (out.appellations.length > 1) lines.push(`\nAll of them on the map: ${out.map_url}`);
  if (out.unknown.length) lines.push(`(not found: ${out.unknown.join(', ')})`);
  return `Shown on the map (Open Wine Map):\n${lines.join('\n')}`;
}

// analytics: { endpoint, domain, url } for the view's `MCP Map Viewed` event,
// or null; its origin joins the CSP's connect list only when it is set.
function viewResource(view, analytics) {
  const config = { tileOrigin: view.tileOrigin, cartoKey: view.cartoKey || '', labels: VIEW_LABELS };
  if (analytics) config.analytics = analytics;
  const html = view.html.replace('__OWM_VIEW_CONFIG__', () => JSON.stringify(config).replace(/</g, '\\u003c'));
  const domains = [view.tileOrigin, CARTO];
  const connect = analytics ? [...domains, new URL(analytics.endpoint).origin] : domains;
  return {
    uri: VIEW_URI,
    mimeType: VIEW_MIME,
    text: html,
    _meta: { ui: { csp: { connectDomains: connect, resourceDomains: domains }, prefersBorder: true } },
  };
}

// The view counts itself only when this request is counted (call.send is
// absent for a smoke test or without PLAUSIBLE_HOST); the event's page is
// /map on the MCP server's own host, beside the tool events' /mcp.
function viewAnalytics(view, call) {
  if (!view.analytics || !call.send || !call.request) return null;
  return {
    endpoint: `${view.analytics.host}/api/event`,
    domain: view.analytics.domain,
    url: `${new URL(call.request.url).origin}/map`,
  };
}

// call: { send?(event, props), era, request } — the analytics of this
// request (send is absent when nothing is counted).
function buildServer(tools, call, view, siteOrigin) {
  const report = (tool, locale, ctx, props) => {
    if (call.send) call.send('MCP Tool', { tool, locale, ...props, ...clientProps(envelopeClient(ctx), call.era, call.request) });
  };
  const server = new McpServer(SERVER_INFO, {
    jsonSchemaValidator: validator,
    capabilities: { tools: { listChanged: false }, resources: { listChanged: false } },
    instructions: INSTRUCTIONS,
  });
  if (view && view.html) {
    server.registerResource('map', VIEW_URI, {
      title: 'Open Wine Map',
      description: 'Interactive map of wine appellations (shown by show_on_map).',
      mimeType: VIEW_MIME,
    }, async () => ({ contents: [viewResource(view, viewAnalytics(view, call))] }));
    server.registerTool('show_on_map', {
      title: 'Show on the map',
      description: 'Show wine appellations on an interactive map in the conversation — their real boundaries, framed and highlighted. '
        + 'Call it whenever your answer names specific appellations (after search_appellations, filter_appellations or get_appellation), '
        + 'with their slugs; up to 200 at once.',
      inputSchema: fromJsonSchema({
        type: 'object',
        properties: {
          slugs: { type: 'array', items: { type: 'string', pattern: SLUG_PATTERN }, minItems: 1, maxItems: 200, description: 'Appellation slugs from the other tools\' results.' },
          locale: LOCALE_PROP,
        },
        required: ['slugs'],
      }, validator),
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
      _meta: { ui: { resourceUri: VIEW_URI } },
    }, async (args, ctx) => {
      const { locale = 'en', slugs } = args || {};
      const entry = await tools.contexts.get(locale).catch(() => null);
      const props = callProps('show_on_map', { slugs }, entry);
      if (!entry) {
        report('show_on_map', locale, ctx, { ...props, error: 'unavailable' });
        return fail('The appellation data is temporarily unavailable; try again shortly.');
      }
      try {
        const out = await showOnMap(entry, { slugs }, locale, siteOrigin);
        report('show_on_map', locale, ctx, props);
        return { content: [{ type: 'text', text: showOnMapText(out) }], structuredContent: out };
      } catch (e) {
        report('show_on_map', locale, ctx, { ...props, error: e instanceof QueryError ? 'invalid' : 'internal' });
        if (e instanceof QueryError) return fail(e.message);
        throw e;
      }
    });
  }
  for (const [name, def] of Object.entries(TOOL_DEFS)) {
    server.registerTool(name, {
      description: def.description,
      inputSchema: fromJsonSchema(withLocale(def.inputSchema), validator),
      annotations: def.annotations,
    }, async (args, ctx) => {
      const { locale = 'en', ...rest } = args || {};
      const entry = await tools.contexts.get(locale).catch(() => null);
      const props = callProps(name, rest, entry);
      if (!entry) {
        report(name, locale, ctx, { ...props, error: 'unavailable' });
        return fail('The appellation data is temporarily unavailable; try again shortly.');
      }
      try {
        const out = await tools[name](rest, entry, locale);
        report(name, locale, ctx, { ...props, ...resultProps(name, out) });
        return asResult(out);
      } catch (e) {
        report(name, locale, ctx, { ...props, error: e instanceof QueryError ? 'invalid' : 'internal' });
        if (e instanceof QueryError) return fail(e.message);
        throw e;
      }
    });
  }
  return server;
}

// track(request) → ((event, props) => void) | undefined: the analytics hook,
// built from the HTTP request the SDK hands each per-request server (undefined:
// nothing is counted for this request — no analytics configured, or a smoke
// test). view: { html, tileOrigin, cartoKey } — the MCP Apps map; omitted → no
// show_on_map tool (the data tools are unaffected).
export function createHandler({ dataOrigin, fetchImpl = fetch, track, store, view }) {
  const tools = createTools({ dataOrigin, fetchImpl, store });
  const callOf = (ctx = {}) => ({
    send: track && ctx.requestInfo ? track(ctx.requestInfo) : undefined,
    era: ctx.era,
    request: ctx.requestInfo,
  });
  return createMcpHandler(ctx => buildServer(tools, callOf(ctx), view, dataOrigin), {
    legacy: 'stateless',
    responseMode: 'json',
    maxRequestBodySize: 64 * 1024,
  });
}
