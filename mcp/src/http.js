// HTTP shell around the MCP handler: routing, CORS, no-store. Shared by the
// Bunny entry point and the tests.
import { createHandler } from './server.js';
import { createContextStore } from './context.js';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
  'Access-Control-Allow-Headers':
    'Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id, Mcp-Method, Mcp-Name, Last-Event-ID, X-OWM-Smoke, Range, If-Match, If-None-Match',
  'Access-Control-Expose-Headers': 'MCP-Protocol-Version, Mcp-Session-Id, Content-Range, Content-Length, ETag, Accept-Ranges',
  'Access-Control-Max-Age': '86400',
};

function withHeaders(resp, extra) {
  const headers = new Headers(resp.headers);
  for (const [k, v] of Object.entries(extra)) headers.set(k, v);
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
}

// The site's vector tiles, re-served with CORS so the MCP Apps view can read
// them from its sandbox origin. Only for a deployment whose TILE_ORIGIN is
// this script (the spike); production serves CORS from the site's own CDN.
async function proxyTiles(request, url, opts, fetchImpl) {
  if (!/^\/map-data\/[a-z0-9-]+\.pmtiles$/.test(url.pathname) || !['GET', 'HEAD'].includes(request.method)) {
    return new Response('not found', { status: 404, headers: CORS });
  }
  const headers = {};
  for (const h of ['Range', 'If-Match', 'If-None-Match']) {
    if (request.headers.get(h)) headers[h] = request.headers.get(h);
  }
  const upstream = await fetchImpl(`${opts.dataOrigin}${url.pathname}`, { method: request.method, headers });
  // no-store: a standalone script runs only on a cache miss, and a cached
  // 206 would be served to requests for other ranges of the same file.
  return withHeaders(upstream, { ...CORS, 'Cache-Control': 'no-store' });
}

// opts: { dataOrigin, fetchImpl?, onToolCallFor?(request) → (tool, locale) => void,
//         view?: { html, tileOrigin, cartoKey }, tileProxy?: boolean }
export function createApp(opts) {
  const fetchImpl = opts.fetchImpl || fetch;
  // One context store per isolate, shared by every request's handler.
  const store = createContextStore({ dataOrigin: opts.dataOrigin, fetchImpl });
  const mcp = createHandler({ dataOrigin: opts.dataOrigin, fetchImpl, store, onToolCallFor: opts.onToolCallFor, view: opts.view });
  return async function handle(request) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (opts.tileProxy && url.pathname.startsWith('/map-data/')) return proxyTiles(request, url, opts, fetchImpl);
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
