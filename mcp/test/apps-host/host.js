// A minimal MCP Apps host for tests: frames the view (served from another
// origin under the CSP the spec prescribes) and drives it with the SDK's own
// AppBridge — initialize, host context, then the show_on_map tool result.
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';

const result = JSON.parse(document.getElementById('tool-result').textContent);
const iframe = document.getElementById('view');
window.__hostLog = [];
const log = (...a) => { window.__hostLog.push(a.map(String).join(' ')); };

// Bridge first, then navigate: the view sends ui/initialize as soon as its
// script runs, before the iframe's load event (real hosts work the same way).
(async () => {
  const bridge = new AppBridge(
    null,
    { name: 'owm-test-host', version: '0' },
    { openLinks: {}, logging: {} },
    { hostContext: { theme: document.body.dataset.theme || 'light', displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'], containerDimensions: { maxHeight: 600 } } },
  );
  bridge.oninitialized = async () => {
    log('initialized');
    await bridge.sendToolInput({ arguments: { slugs: result.appellations.map(a => a.slug) } });
    await bridge.sendToolResult({ content: [{ type: 'text', text: 'shown' }], structuredContent: result });
    log('tool-result sent');
  };
  bridge.onopenlink = async ({ url }) => { log('openLink', url); return {}; };
  bridge.onsizechange = ({ height }) => { if (height) iframe.style.height = `${height}px`; };
  await bridge.connect(new PostMessageTransport(iframe.contentWindow, iframe.contentWindow));
  log('bridge connected');
  iframe.src = iframe.dataset.src;
})();
