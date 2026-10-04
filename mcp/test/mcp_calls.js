// Reads [[tool, args], …] as JSON on stdin, answers each through the MCP
// server (local, data from wiki/) with the official client, and prints
// [structuredContent | {isError, text}, …] as JSON. Used by parity_webmcp.py.
import { startServer } from './local.js';
import { smoke } from './smoke.js';

const input = await new Promise(resolve => {
  let buf = '';
  process.stdin.on('data', c => { buf += c; });
  process.stdin.on('end', () => resolve(buf));
});
const calls = JSON.parse(input);
const srv = await startServer();
try {
  const r = await smoke(srv.url, 'modern', calls);
  const out = r.results.map(x => (x.isError ? { isError: true, text: x.content[0].text } : x.structuredContent));
  process.stdout.write(JSON.stringify({ origin: 'https://data.test', results: out }));
} finally {
  await srv.close();
}
