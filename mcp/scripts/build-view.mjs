// Builds the MCP Apps view (view/view.html + view/view.js) into one
// self-contained HTML document, dist/view.html: MCP Apps resources are a
// single HTML string (no sibling files), so the bundle and MapLibre's CSS are
// inlined. The edge bundle imports the result as text (esbuild --loader).
import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = await build({
  entryPoints: [path.join(root, 'view', 'view.js')],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
  minify: true,
  legalComments: 'none',
  write: false,
});
const js = out.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const css = (await readFile(path.join(root, 'node_modules', 'maplibre-gl', 'dist', 'maplibre-gl.css'), 'utf8'))
  .replace(/<\/style/gi, '<\\/style');
const template = await readFile(path.join(root, 'view', 'view.html'), 'utf8');
for (const token of ['/*__OWM_MAPLIBRE_CSS__*/', '/*__OWM_VIEW_JS__*/', '__OWM_VIEW_CONFIG__']) {
  if (template.split(token).length !== 2) throw new Error(`view.html: expected one ${token}`);
}
// Function replacers: the bundle contains `$&`-style sequences a string
// replacement would interpret.
const html = template
  .replace('/*__OWM_MAPLIBRE_CSS__*/', () => css)
  .replace('/*__OWM_VIEW_JS__*/', () => js);
await mkdir(path.join(root, 'dist'), { recursive: true });
await writeFile(path.join(root, 'dist', 'view.html'), html);
console.log(`dist/view.html  ${(Buffer.byteLength(html) / 1024).toFixed(1)}kb`);
