// Open Wine Map MCP server: a stateless, web-standard request handler.
// Runtime-agnostic (Bunny Edge Scripting in production, Node in tests): the
// entry point supplies `dataOrigin` and, optionally, a `fetch` and an
// `onToolCall` hook (analytics). The tools are the query core's TOOL_DEFS —
// the same definitions and code the map page registers as WebMCP tools.
import { McpServer, createMcpHandler, fromJsonSchema } from '@modelcontextprotocol/server';
import { CfWorkerJsonSchemaValidator } from '@modelcontextprotocol/server/validators/cf-worker';
import { TOOL_DEFS, QueryError } from '../../scripts/_lib/assets/query_core.mjs';
import { LOCALES, createContextStore } from './context.js';

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
  const mapUrl = appellations.length === 1 ? appellations[0].url : `${home}?aocs=${known.join(',')}`;
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
  const lines = out.appellations.map(a => `- [${a.name}](${a.url}) — ${[a.classification, a.region, a.country_name].filter(Boolean).join(' · ')}`);
  if (out.appellations.length > 1) lines.push(`\nAll of them on the map: ${out.map_url}`);
  if (out.unknown.length) lines.push(`(not found: ${out.unknown.join(', ')})`);
  return `Shown on the map (Open Wine Map):\n${lines.join('\n')}`;
}

function viewResource(view) {
  const config = { tileOrigin: view.tileOrigin, cartoKey: view.cartoKey || '', labels: VIEW_LABELS };
  const html = view.html.replace('__OWM_VIEW_CONFIG__', () => JSON.stringify(config).replace(/</g, '\\u003c'));
  const domains = [view.tileOrigin, CARTO];
  return {
    uri: VIEW_URI,
    mimeType: VIEW_MIME,
    text: html,
    _meta: { ui: { csp: { connectDomains: domains, resourceDomains: domains }, prefersBorder: true } },
  };
}

function buildServer(tools, onToolCall, view, siteOrigin) {
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
    }, async () => ({ contents: [viewResource(view)] }));
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
    }, async (args) => {
      const { locale = 'en', slugs } = args || {};
      if (onToolCall) onToolCall('show_on_map', locale);
      let entry;
      try {
        entry = await tools.contexts.get(locale);
      } catch {
        return fail('The appellation data is temporarily unavailable; try again shortly.');
      }
      try {
        const out = await showOnMap(entry, { slugs }, locale, siteOrigin);
        return { content: [{ type: 'text', text: showOnMapText(out) }], structuredContent: out };
      } catch (e) {
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
    }, async (args) => {
      const { locale = 'en', ...rest } = args || {};
      if (onToolCall) onToolCall(name, locale);
      let entry;
      try {
        entry = await tools.contexts.get(locale);
      } catch {
        return fail('The appellation data is temporarily unavailable; try again shortly.');
      }
      try {
        return asResult(await tools[name](rest, entry, locale));
      } catch (e) {
        if (e instanceof QueryError) return fail(e.message);
        throw e;
      }
    });
  }
  return server;
}

// onToolCallFor(request) → (tool, locale) => void | undefined: the analytics
// hook, built from the HTTP request the SDK hands each per-request server.
// view: { html, tileOrigin, cartoKey } — the MCP Apps map; omitted → no
// show_on_map tool (the data tools are unaffected).
export function createHandler({ dataOrigin, fetchImpl = fetch, onToolCallFor, store, view }) {
  const tools = createTools({ dataOrigin, fetchImpl, store });
  const hook = ctx => (onToolCallFor && ctx && ctx.requestInfo ? onToolCallFor(ctx.requestInfo) : undefined);
  return createMcpHandler(ctx => buildServer(tools, hook(ctx), view, dataOrigin), {
    legacy: 'stateless',
    responseMode: 'json',
    maxRequestBodySize: 64 * 1024,
  });
}
