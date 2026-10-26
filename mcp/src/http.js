// HTTP shell around the MCP handler: routing, CORS, no-store. Shared by the
// Bunny entry point and the tests.
import { createHandler, clientProps, CLIENT_INFO_KEY, PROTOCOL_VERSION_KEY } from './server.js';
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

// A client's opening request — `initialize` (2025-era) or `server/discover`
// (2026-07-28) — as `MCP Connect` props: the client it names, the protocol it
// asks for, its User-Agent token. A 2025-era client names itself nowhere else:
// this server is stateless and sees each later request alone. null for any
// other request, or one too large to read twice (the SDK caps bodies at 64 KB).
const PEEK_MAX = 64 * 1024;
export async function connectProps(request) {
  if (request.method !== 'POST') return null;
  const length = Number(request.headers.get('Content-Length'));
  if (!length || length > PEEK_MAX) return null;
  let msg;
  try {
    msg = await request.clone().json();
  } catch {
    return null;
  }
  if (Array.isArray(msg)) msg = msg[0];
  const params = (msg && msg.params) || {};
  let info;
  let protocol;
  let era;
  if (msg && msg.method === 'initialize') {
    [info, protocol, era] = [params.clientInfo, params.protocolVersion, 'legacy'];
  } else if (msg && msg.method === 'server/discover') {
    const meta = params._meta || {};
    [info, protocol, era] = [meta[CLIENT_INFO_KEY], meta[PROTOCOL_VERSION_KEY], 'modern'];
  } else {
    return null;
  }
  const out = clientProps(info, era, request);
  if (typeof protocol === 'string' && protocol) out.protocol = protocol.slice(0, 20);
  return out;
}

// opts: { dataOrigin, fetchImpl?, track?(request) → ((event, props) => void) | undefined,
//         view?: { html, tileOrigin, cartoKey }, tileProxy?: boolean }
export function createApp(opts) {
  const fetchImpl = opts.fetchImpl || fetch;
  // One context store per isolate, shared by every request's handler.
  const store = createContextStore({ dataOrigin: opts.dataOrigin, fetchImpl });
  const mcp = createHandler({ dataOrigin: opts.dataOrigin, fetchImpl, store, track: opts.track, view: opts.view });
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
    const send = opts.track ? opts.track(request) : undefined;
    if (send) {
      const props = await connectProps(request);
      if (props) send('MCP Connect', props);
    }
    const resp = await mcp.fetch(request);
    return withHeaders(resp, { ...CORS, 'Cache-Control': 'no-store' });
  };
}
