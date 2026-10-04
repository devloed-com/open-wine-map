// The MCP Apps view of `show_on_map`: a MapLibre map of the requested
// appellations, drawn from the site's own vector tiles over the CARTO basemap.
// Runs in the host's sandboxed iframe; everything it loads is declared in the
// resource's `_meta.ui.csp` (server.js). MapLibre 4's UMD build starts its
// worker from a blob: URL, which the MCP Apps hosts allow.
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { App } from '@modelcontextprotocol/ext-apps';

const CONFIG = JSON.parse(document.getElementById('owm-config').textContent);
const KIND_COLOUR = ['case', ['==', ['get', 'kind'], 'IGP'], '#6e7546', '#934050'];
const OVERVIEW_MAX_ZOOM = 11.9; // the site's LOD: footprints below, parcels from z11
const DETAIL_MIN_ZOOM = 11;

const $ = id => document.getElementById(id);
const status = msg => { $('status').textContent = msg || ''; $('status').hidden = !msg; };

function cartoTiles(style) {
  const auth = CONFIG.cartoKey ? `?key=${encodeURIComponent(CONFIG.cartoKey)}` : '';
  return ['a', 'b', 'c'].map(s => `https://${s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png${auth}`);
}

let map = null;
let current = null;
let theme = 'light';

function applyTheme(t) {
  theme = t === 'dark' ? 'dark' : 'light';
  document.documentElement.classList.toggle('dark', theme === 'dark');
  if (map && map.getLayer('basemap-light')) {
    map.setLayoutProperty('basemap-light', 'visibility', theme === 'dark' ? 'none' : 'visible');
    map.setLayoutProperty('basemap-dark', 'visibility', theme === 'dark' ? 'visible' : 'none');
  }
}

function buildMap() {
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
        overview: { type: 'vector', url: `pmtiles://${CONFIG.tileOrigin}/map-data/appellations-overview.pmtiles`, promoteId: 'slug' },
        detail: { type: 'vector', url: `pmtiles://${CONFIG.tileOrigin}/map-data/appellations.pmtiles`, promoteId: 'slug' },
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
  const fills = () => ['fill-overview', 'fill-detail'].filter(id => map.getLayer(id));
  map.on('click', e => {
    const feats = current ? map.queryRenderedFeatures(e.point, { layers: fills() }) : [];
    if (feats.length) showPopup(feats[0], e.lngLat);
  });
  map.on('mousemove', e => {
    map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: fills() }).length ? 'pointer' : '';
  });
  return new Promise(resolve => map.on('load', resolve));
}

function addAppellationLayers(slugs) {
  for (const id of ['fill-overview', 'fill-detail', 'line-overview', 'line-detail']) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  const inSet = ['in', ['get', 'slug'], ['literal', slugs]];
  const over = { 'source-layer': 'appellations', maxzoom: OVERVIEW_MAX_ZOOM, filter: inSet };
  const detail = { 'source-layer': 'appellations', minzoom: DETAIL_MIN_ZOOM, filter: inSet };
  const sort = { 'fill-sort-key': ['-', 0, ['get', 'area']] };
  map.addLayer({ id: 'fill-overview', type: 'fill', source: 'overview', ...over, layout: sort,
    paint: { 'fill-color': KIND_COLOUR, 'fill-opacity': 0.5 } });
  map.addLayer({ id: 'fill-detail', type: 'fill', source: 'detail', ...detail, layout: sort,
    paint: { 'fill-color': KIND_COLOUR, 'fill-opacity': 0.5 } });
  const line = { 'line-color': theme === 'dark' ? '#f2e6d0' : '#2a1014', 'line-width': 1.2 };
  map.addLayer({ id: 'line-overview', type: 'line', source: 'overview', ...over, paint: line });
  map.addLayer({ id: 'line-detail', type: 'line', source: 'detail', ...detail, paint: line });
}

function fit(bbox, single) {
  if (!bbox) return;
  map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 36, maxZoom: single ? 12 : 10, duration: 0 });
}

function showPopup(feature, lngLat) {
  const a = (current.appellations || []).find(x => x.slug === feature.properties.slug);
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

async function render(data) {
  current = data;
  if (!data || !Array.isArray(data.appellations) || !data.appellations.length) {
    status(CONFIG.labels.nothing);
    return;
  }
  if (!map) await buildMap();
  applyTheme(theme);
  addAppellationLayers(data.appellations.map(a => a.slug));
  fit(data.bbox, data.appellations.length === 1);
  status('');
  // Test hook (apps_host_check.py): how many requested appellations are drawn.
  window.__owmView = {
    features: () => map.queryRenderedFeatures({ layers: ['fill-overview', 'fill-detail'].filter(id => map.getLayer(id)) }).length,
  };
  const title = data.appellations.length === 1
    ? data.appellations[0].name
    : `${data.appellations.length} ${CONFIG.labels.appellations}`;
  $('title').textContent = title;
  $('title').hidden = false;
  $('open-site').hidden = false;
  $('open-site').onclick = () => app.openLink({ url: data.map_url || data.appellations[0].url });
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
  if (!current) status(CONFIG.labels.waiting);
}

main().catch(e => status(String((e && e.message) || e)));
