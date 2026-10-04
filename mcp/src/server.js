// Open Wine Map MCP server: a stateless, web-standard request handler.
// Runtime-agnostic (Bunny Edge Scripting in production, Node in tests): the
// entry point supplies `dataOrigin` and, optionally, a `fetch` and an
// `onToolCall` hook (analytics). The tools are the query core's TOOL_DEFS —
// the same definitions and code the map page registers as WebMCP tools.
import { McpServer, createMcpHandler, fromJsonSchema } from '@modelcontextprotocol/server';
import { CfWorkerJsonSchemaValidator } from '@modelcontextprotocol/server/validators/cf-worker';
import { TOOL_DEFS, QueryError } from '../../scripts/_lib/assets/query_core.mjs';
import { LOCALES, createContextStore } from './context.js';

export const SERVER_INFO = {
  name: 'open-wine-map',
  title: 'Open Wine Map',
  version: '1.0.0',
  websiteUrl: 'https://www.openwinemap.com/',
};

const INSTRUCTIONS = [
  'Open Wine Map covers the protected wine appellations of 19 European countries (EU PDO/PGI and the UK and Swiss schemes),',
  'built from the regulators\' own specifications. Use search_appellations to find an appellation by name,',
  'filter_appellations for structured questions (country, region, style, grape, scheme) — list_facets gives the accepted',
  'values — and get_appellation for one appellation\'s grapes, styles, terroir facts and sources.',
  'When quoting terroir facts, cite the specification URL, and Wikipedia (CC BY-SA 4.0) where a fact says so.',
  'Every result carries the appellation\'s page on www.openwinemap.com.',
].join(' ');

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

function buildServer(tools, onToolCall) {
  const server = new McpServer(SERVER_INFO, {
    jsonSchemaValidator: validator,
    capabilities: { tools: { listChanged: false } },
    instructions: INSTRUCTIONS,
  });
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
export function createHandler({ dataOrigin, fetchImpl = fetch, onToolCallFor, store }) {
  const tools = createTools({ dataOrigin, fetchImpl, store });
  const hook = ctx => (onToolCallFor && ctx && ctx.requestInfo ? onToolCallFor(ctx.requestInfo) : undefined);
  return createMcpHandler(ctx => buildServer(tools, hook(ctx)), {
    legacy: 'stateless',
    responseMode: 'json',
    maxRequestBodySize: 64 * 1024,
  });
}
