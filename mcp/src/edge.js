// Bunny Edge Scripting entry point (standalone script).
//
// Script environment variables (all optional):
//   DATA_ORIGIN       the site the data is read from (https://www.openwinemap.com)
//   PLAUSIBLE_HOST    self-hosted Plausible; unset → no analytics
//   PLAUSIBLE_DOMAIN  the Plausible site the `MCP Tool` event is counted under
//   TILE_ORIGIN       where the map view loads /map-data/*.pmtiles (needs CORS)
//   TILE_PROXY        "1": this script re-serves the site's tiles with CORS
//   CARTO_KEY         CARTO basemap key for the map view (public, as on the site)
import * as BunnySDK from '@bunny.net/edgescript-sdk';
import process from 'node:process';
import { createApp } from './http.js';
import VIEW_HTML from '../dist/view.html';

const env = name => (process.env[name] || '').trim().replace(/\/$/, '');
const dataOrigin = env('DATA_ORIGIN') || 'https://www.openwinemap.com';
const plausibleHost = env('PLAUSIBLE_HOST');
const plausibleDomain = env('PLAUSIBLE_DOMAIN') || 'openwinemap.com';

// `MCP Tool` {tool, locale}: tool arguments are never sent (the same rule as
// the page's `WebMCP Tool` event). Sent after the response, without blocking.
function trackToolCall(request) {
  if (!plausibleHost || request.headers.get('X-OWM-Smoke')) return undefined;
  return (tool, locale) => {
    const send = fetch(`${plausibleHost}/api/event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': request.headers.get('User-Agent') || 'mcp-client',
        'X-Forwarded-For': request.headers.get('X-Forwarded-For') || '',
      },
      body: JSON.stringify({
        name: 'MCP Tool',
        url: new URL(request.url).origin + '/mcp',
        domain: plausibleDomain,
        props: { tool, locale },
      }),
    }).catch(() => {});
    try { Bunny.v1.waitUntil(send); } catch { /* not on Bunny */ }
  };
}

const app = createApp({
  dataOrigin,
  onToolCallFor: trackToolCall,
  view: { html: VIEW_HTML, tileOrigin: env('TILE_ORIGIN') || dataOrigin, cartoKey: env('CARTO_KEY') },
  tileProxy: env('TILE_PROXY') === '1',
});

BunnySDK.net.http.serve(app);
