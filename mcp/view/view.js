// The MCP Apps view of `show_on_map`: a MapLibre map of the requested
// appellations, drawn from the site's own vector tiles over the CARTO basemap.
// Runs in the host's sandboxed iframe; everything it loads is declared in the
// resource's `_meta.ui.csp` (server.js). MapLibre 4's UMD build starts its
// worker from a blob: URL, which the MCP Apps hosts allow.
//
// Interaction: the title opens a legend list — one colour per appellation (up
// to PALETTE.length of them), hover a row or a polygon to highlight the
// other, click a row to zoom to it (and point "Open ↗" at its page), the
// colour square toggles it, "Show all" resets.
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { App } from '@modelcontextprotocol/ext-apps';

const CONFIG = JSON.parse(document.getElementById('owm-config').textContent);
const KIND_COLOUR = { IGP: '#6e7546', other: '#934050' };
// Tableau 10: distinct, readable on both basemaps.
const PALETTE = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];
const OVERVIEW_MAX_ZOOM = 11.9; // the site's LOD: footprints below, parcels from z11
const DETAIL_MIN_ZOOM = 11;
const FILLS = ['fill-overview', 'fill-detail'];
const LINES = ['line-overview', 'line-detail'];

const $ = id => document.getElementById(id);
const status = msg => { $('status').textContent = msg || ''; $('status').hidden = !msg; };

let map = null;
let theme = 'light';
let data = null;          // the tool result: { appellations, bbox, map_url }
let colours = {};         // slug → fill colour
const hidden = new Set(); // slugs toggled off in the list
let pinned = null;        // slug the user zoomed to (row or polygon click)
let hovered = null;       // slug under the pointer (row or polygon)

function cartoTiles(style) {
  const auth = CONFIG.cartoKey ? `?key=${encodeURIComponent(CONFIG.cartoKey)}` : '';
  return ['a', 'b', 'c'].map(s => `https://${s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png${auth}`);
}

const lineColour = () => (theme === 'dark' ? '#f2e6d0' : '#2a1014');

function applyTheme(t) {
  theme = t === 'dark' ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', theme === 'dark');
  if (!map || !map.getLayer('basemap-light')) return;
  map.setLayoutProperty('basemap-light', 'visibility', theme === 'dark' ? 'none' : 'visible');
  map.setLayoutProperty('basemap-dark', 'visibility', theme === 'dark' ? 'visible' : 'none');
  for (const id of LINES) if (map.getLayer(id)) map.setPaintProperty(id, 'line-color', lineColour());
}

function setFeatureFlag(slug, key, on) {
  if (!map || !slug) return;
  for (const source of ['overview', 'detail']) {
    try { map.setFeatureState({ source, sourceLayer: 'appellations', id: slug }, { [key]: on }); } catch { /* not loaded yet */ }
  }
}

function buildMap() {
  // The site's versioned paths (the files are browser-cached for 30 days, so
  // a deploy must change the URL); bare paths until the server has them.
  const tiles = (data && data.tiles) || { overview: '/map-data/appellations-overview.pmtiles', detail: '/map-data/appellations.pmtiles' };
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  const attribution = '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · <a href="https://www.openwinemap.com/">Open Wine Map</a>';
  map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        'basemap-light': { type: 'raster', tileSize: 256, tiles: cartoTiles('rastertiles/voyager'), attribution },
        'basemap-dark': { type: 'raster', tileSize: 256, tiles: cartoTiles('dark_all'), attribution },
        overview: { type: 'vector', url: `pmtiles://${CONFIG.tileOrigin}${tiles.overview}`, promoteId: 'slug' },
        detail: { type: 'vector', url: `pmtiles://${CONFIG.tileOrigin}${tiles.detail}`, promoteId: 'slug' },
      },
      layers: [
        { id: 'basemap-light', type: 'raster', source: 'basemap-light' },
        { id: 'basemap-dark', type: 'raster', source: 'basemap-dark', layout: { visibility: 'none' } },
      ],
    },
    attributionControl: { compact: true },
    dragRotate: false,
    pitchWithRotate: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  map.on('error', e => console.warn('map error', e && e.error));
  const fills = () => FILLS.filter(id => map.getLayer(id));
  map.on('click', e => {
    const f = data ? map.queryRenderedFeatures(e.point, { layers: fills() })[0] : null;
    if (!f) return;
    focus(f.properties.slug, { fly: false });
    showPopup(f.properties.slug, e.lngLat);
  });
  map.on('mousemove', e => {
    const f = map.queryRenderedFeatures(e.point, { layers: fills() })[0];
    map.getCanvas().style.cursor = f ? 'pointer' : '';
    hover(f ? f.properties.slug : null);
  });
  map.getCanvas().addEventListener('mouseleave', () => hover(null));
  return new Promise(resolve => map.on('load', resolve));
}

// Black or white check mark, whichever reads on the swatch colour.
function inkOn(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? '#222' : '#fff';
}

function colourFor(a, i, n) {
  if (n <= PALETTE.length) return PALETTE[i];
  return a.kind === 'IGP' ? KIND_COLOUR.IGP : KIND_COLOUR.other;
}

function addAppellationLayers() {
  for (const id of [...FILLS, ...LINES]) if (map.getLayer(id)) map.removeLayer(id);
  const slugs = data.appellations.map(a => a.slug);
  const matchColour = ['match', ['get', 'slug'], ...slugs.flatMap(s => [s, colours[s]]), KIND_COLOUR.other];
  const visible = ['in', ['get', 'slug'], ['literal', slugs.filter(s => !hidden.has(s))]];
  const over = { 'source-layer': 'appellations', maxzoom: OVERVIEW_MAX_ZOOM, filter: visible };
  const detail = { 'source-layer': 'appellations', minzoom: DETAIL_MIN_ZOOM, filter: visible };
  const lit = ['boolean', ['feature-state', 'lit'], false];
  // One lit: it stands out, the others fade back; none lit: all at 0.55.
  const fill = {
    'fill-color': matchColour,
    'fill-opacity': ['case', lit, 0.8, ['boolean', ['feature-state', 'dim'], false], 0.18, 0.55],
  };
  const line = { 'line-color': lineColour(), 'line-width': ['case', lit, 3, 1.1] };
  const sort = { 'fill-sort-key': ['-', 0, ['get', 'area']] };
  map.addLayer({ id: 'fill-overview', type: 'fill', source: 'overview', ...over, layout: sort, paint: fill });
  map.addLayer({ id: 'fill-detail', type: 'fill', source: 'detail', ...detail, layout: sort, paint: fill });
  map.addLayer({ id: 'line-overview', type: 'line', source: 'overview', ...over, paint: line });
  map.addLayer({ id: 'line-detail', type: 'line', source: 'detail', ...detail, paint: line });
  repaintState();
}

// Feature state from (hovered || pinned): that one lit, the others dimmed —
// unless it is hidden, which must not dim what is still shown.
function repaintState() {
  const shown = s => (s && !hidden.has(s) ? s : null);
  const lit = shown(hovered) || shown(pinned);
  for (const a of data.appellations) {
    setFeatureFlag(a.slug, 'lit', a.slug === lit);
    setFeatureFlag(a.slug, 'dim', !!lit && a.slug !== lit);
  }
  for (const row of document.querySelectorAll('#rows .row')) {
    row.classList.toggle('lit', row.dataset.slug === lit);
    row.classList.toggle('pinned', row.dataset.slug === pinned);
  }
  const target = pinned && data.appellations.find(a => a.slug === pinned);
  $('open-site').textContent = target ? `${target.name} ↗` : CONFIG.labels.site;
}

function hover(slug) {
  if (slug === hovered) return;
  hovered = slug;
  repaintState();
}

function fitTo(bbox, maxZoom) {
  if (bbox) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, maxZoom, duration: 400 });
}

function focus(slug, { fly = true } = {}) {
  const a = data.appellations.find(x => x.slug === slug);
  if (!a) return;
  pinned = slug;
  if (hidden.delete(slug)) { addAppellationLayers(); renderList(); }
  if (fly) fitTo(a.bbox, 12);
  repaintState();
  const row = document.querySelector(`#rows .row[data-slug="${CSS.escape(slug)}"]`);
  if (row) row.scrollIntoView({ block: 'nearest' });
}

function showAll() {
  pinned = null;
  hidden.clear();
  addAppellationLayers();
  renderList();
  fitTo(data.bbox, data.appellations.length === 1 ? 12 : 10);
}

function showPopup(slug, lngLat) {
  const a = data.appellations.find(x => x.slug === slug);
  if (!a) return;
  const box = document.createElement('div');
  const name = document.createElement('div');
  name.className = 'popup-name';
  name.textContent = a.name;
  const meta = document.createElement('div');
  meta.className = 'popup-meta';
  meta.textContent = [a.classification, a.region, a.country_name].filter(Boolean).join(' · ');
  const open = document.createElement('button');
  open.className = 'popup-open';
  open.type = 'button';
  open.textContent = CONFIG.labels.open;
  open.addEventListener('click', () => app.openLink({ url: a.url }));
  box.append(name, meta, open);
  new maplibregl.Popup({ closeButton: true, maxWidth: '260px' }).setLngLat(lngLat).setDOMContent(box).addTo(map);
}

function toggleHidden(slug) {
  if (!hidden.delete(slug)) hidden.add(slug);
  if (pinned === slug && hidden.has(slug)) pinned = null;
  addAppellationLayers();
  renderList();
}

function renderList() {
  const list = $('rows');
  list.replaceChildren();
  for (const a of data.appellations) {
    const off = hidden.has(a.slug);
    const row = document.createElement('div');
    row.className = 'row' + (off ? ' off' : '');
    row.dataset.slug = a.slug;
    // The colour square is the toggle: filled with a check = shown, hollow = hidden.
    const sw = document.createElement('button');
    sw.type = 'button';
    sw.className = 'swatch';
    sw.style.setProperty('--c', colours[a.slug]);
    sw.style.color = inkOn(colours[a.slug]);
    sw.textContent = off ? '' : '✓';
    sw.title = off ? CONFIG.labels.show : CONFIG.labels.hide;
    sw.setAttribute('aria-label', `${off ? CONFIG.labels.show : CONFIG.labels.hide}: ${a.name}`);
    sw.setAttribute('aria-pressed', String(!off));
    sw.addEventListener('click', () => toggleHidden(a.slug));
    const text = document.createElement('button');
    text.type = 'button';
    text.className = 'row-text';
    text.title = CONFIG.labels.zoom;
    const nm = document.createElement('span');
    nm.className = 'row-name';
    nm.textContent = a.name;
    const meta = document.createElement('span');
    meta.className = 'row-meta';
    meta.textContent = [a.classification, a.region].filter(Boolean).join(' · ');
    text.append(nm, meta);
    text.addEventListener('click', () => focus(a.slug));
    row.addEventListener('mouseenter', () => hover(a.slug));
    row.addEventListener('mouseleave', () => hover(null));
    row.append(sw, text);
    list.append(row);
  }
  repaintState();
}

function toggleList(open) {
  const show = open === undefined ? $('list').hidden : open;
  $('list').hidden = !show;
  $('title').setAttribute('aria-expanded', String(show));
}

async function render(result) {
  data = result;
  if (!data || !Array.isArray(data.appellations) || !data.appellations.length) {
    status(CONFIG.labels.nothing);
    return;
  }
  const n = data.appellations.length;
  colours = Object.fromEntries(data.appellations.map((a, i) => [a.slug, colourFor(a, i, n)]));
  hidden.clear();
  pinned = null;
  if (!map) await buildMap();
  applyTheme(theme);
  addAppellationLayers();
  renderList();
  fitTo(data.bbox, n === 1 ? 12 : 10);
  status('');
  // Test hook (apps_host_check.py): how many requested appellations are drawn.
  window.__owmView = {
    features: () => map.queryRenderedFeatures({ layers: FILLS.filter(id => map.getLayer(id)) }).length,
  };
  $('title').textContent = n === 1 ? `${data.appellations[0].name} ▾` : `${n} ${CONFIG.labels.appellations} ▾`;
  $('title').hidden = false;
  $('show-all').textContent = CONFIG.labels.show_all;
  $('open-site').hidden = false;
  // A multi-appellation answer opens the list, so the colours are explained.
  toggleList(n > 1);
}

const app = new App(
  { name: 'open-wine-map-view', version: '1.0.0' },
  { availableDisplayModes: ['inline', 'fullscreen'] },
  { autoResize: true },
);

app.ontoolresult = params => {
  render(params && params.structuredContent).catch(e => status(String((e && e.message) || e)));
};
app.onhostcontextchanged = ctx => {
  if (ctx && ctx.theme) applyTheme(ctx.theme);
  if (ctx && ctx.displayMode) {
    document.documentElement.classList.toggle('fullscreen', ctx.displayMode === 'fullscreen');
    if (map) setTimeout(() => map.resize(), 0);
  }
};

$('title').addEventListener('click', () => toggleList());
$('show-all').addEventListener('click', () => showAll());
// The site link follows the view: the appellation zoomed to, else the ones
// still shown (the server's ?aocs= link, minus what the reader hid).
function siteUrl() {
  const target = pinned && data.appellations.find(a => a.slug === pinned);
  if (target) return target.url;
  const shown = data.appellations.filter(a => !hidden.has(a.slug));
  if (shown.length === 1) return shown[0].url;
  if (hidden.size && shown.length && data.map_url) {
    try {
      const u = new URL(data.map_url);
      if (u.searchParams.has('aocs')) {
        u.searchParams.set('aocs', shown.map(a => a.slug).join(','));
        return u.toString().replace(/%2C/g, ',');
      }
    } catch (e) { /* fall back to the server's link */ }
  }
  return data.map_url || data.appellations[0].url;
}

$('open-site').addEventListener('click', () => {
  if (data) app.openLink({ url: siteUrl() });
});

async function main() {
  await app.connect();
  const ctx = app.getHostContext && app.getHostContext();
  if (ctx && ctx.theme) applyTheme(ctx.theme);
  const modes = (ctx && ctx.availableDisplayModes) || [];
  if (modes.includes('fullscreen')) {
    $('fullscreen').hidden = false;
    $('fullscreen').onclick = async () => {
      const isFull = document.documentElement.classList.contains('fullscreen');
      await app.requestDisplayMode({ mode: isFull ? 'inline' : 'fullscreen' });
    };
  }
  if (!data) status(CONFIG.labels.waiting);
}

main().catch(e => status(String((e && e.message) || e)));
