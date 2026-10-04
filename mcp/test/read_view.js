// Prints the live MCP Apps view resource of an endpoint as JSON
// ({text, csp}) — used by apps_host_check.py --live.
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const client = new Client({ name: 'owm-view-check', version: '0' }, { versionNegotiation: { mode: { pin: '2026-07-28' } } });
await client.connect(new StreamableHTTPClientTransport(new URL(process.argv[2]), { requestInit: { headers: { 'X-OWM-Smoke': '1' } } }));
const res = await client.readResource({ uri: 'ui://open-wine-map/map' });
const c = res.contents[0];
process.stdout.write(JSON.stringify({ text: c.text, csp: c._meta.ui.csp }));
await client.close();
