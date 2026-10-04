// HTTP shell around the MCP handler: routing, CORS, no-store. Shared by the
// Bunny entry point and the tests.
import { createHandler } from './server.js';
import { createContextStore } from './context.js';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
  'Access-Control-Allow-Headers':
    'Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id, Mcp-Method, Mcp-Name, Last-Event-ID',
  'Access-Control-Expose-Headers': 'MCP-Protocol-Version, Mcp-Session-Id',
  'Access-Control-Max-Age': '86400',
};

function withHeaders(resp, extra) {
  const headers = new Headers(resp.headers);
  for (const [k, v] of Object.entries(extra)) headers.set(k, v);
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
}

// opts: { dataOrigin, fetchImpl?, onToolCallFor?(request) → (tool, locale) => void }
export function createApp(opts) {
  const fetchImpl = opts.fetchImpl || fetch;
  // One context store per isolate, shared by every request's handler.
  const store = createContextStore({ dataOrigin: opts.dataOrigin, fetchImpl });
  const mcp = createHandler({ dataOrigin: opts.dataOrigin, fetchImpl, store, onToolCallFor: opts.onToolCallFor });
  return async function handle(request) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (url.pathname !== '/mcp') {
      return Response.json(
        { error: 'not found', mcp_endpoint: `${url.origin}/mcp`, site: opts.dataOrigin },
        { status: 404, headers: { ...CORS, 'Cache-Control': 'no-store' } },
      );
    }
    const resp = await mcp.fetch(request);
    return withHeaders(resp, { ...CORS, 'Cache-Control': 'no-store' });
  };
}
