// A local HTTP server around the app for tests: Node's http module adapted to
// the web-standard handler, with data served from the built wiki/ directory
// instead of the live site.
import http from 'node:http';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from '../src/http.js';

export const WIKI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../wiki');
const DATA_ORIGIN = 'https://data.test';

export function haveBuild() {
  return existsSync(path.join(WIKI, 'data', 'mcp', 'en.json'));
}

export async function wikiFetch(url) {
  const u = new URL(url);
  if (u.origin !== DATA_ORIGIN) throw new Error(`unexpected fetch ${url}`);
  try {
    const body = await readFile(path.join(WIKI, decodeURIComponent(u.pathname)));
    return new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch {
    return new Response('not found', { status: 404 });
  }
}

const VIEW = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist/view.html');

export async function startServer() {
  const view = existsSync(VIEW)
    ? { html: await readFile(VIEW, 'utf8'), tileOrigin: DATA_ORIGIN, cartoKey: 'test-key' }
    : undefined;
  const app = createApp({ dataOrigin: DATA_ORIGIN, fetchImpl: wikiFetch, view });
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = chunks.length ? Buffer.concat(chunks) : undefined;
    const request = new Request(`http://${req.headers.host}${req.url}`, {
      method: req.method,
      headers: req.headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : body,
    });
    const resp = await app(request);
    res.writeHead(resp.status, Object.fromEntries(resp.headers));
    res.end(Buffer.from(await resp.arrayBuffer()));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  return { url: `http://127.0.0.1:${port}/mcp`, close: () => new Promise(r => server.close(r)) };
}
