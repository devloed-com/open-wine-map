
  const AOCS = (window.__OWM_DATA && window.__OWM_DATA.aocs) || {};
  if (!window.__OWM_DATA) {
    console.error('Open Wine Map: data bundle failed to load — appellation details unavailable. Try reloading.');
  }
  // Snapshot the URL camera hash (#zoom/lat/lon) NOW, before the map is
  // constructed: maplibre's `hash: true` writes the default camera into
  // location.hash synchronously during `new Map()`, so a later
  // `!window.location.hash` check can't tell a user-shared camera from the
  // map's own auto-written default. Only a hash present at page entry is
  // genuinely user-supplied.
  const INITIAL_CAMERA_HASH = window.location.hash || '';
  const FACET_STYLES_TREE = __OWM_styles_tree_json__;
  const STYLE_DESCENDANTS = __OWM_style_descendants_json__;
  const FACET_STYLES_SIMPLE = __OWM_styles_simple_json__;
  const FACET_PRINCIPAL = __OWM_principal_json__;
  const FACET_ACCESSORY = __OWM_accessory_json__;
  const FACET_GRAPES_ALL = __OWM_grapes_all_json__;
  const FACET_REGIONS = __OWM_regions_json__;
  const STYLE_LABELS = __OWM_style_labels_json__;
  const SIMPLE_STYLE_LABELS = __OWM_simple_style_labels_json__;
  const SIMPLE_STYLE_BUCKETS = __OWM_simple_style_buckets_json__;
  // {canonical style slug -> [searchable synonym terms]} — wine-style analogue
  // of GRAPE_SYNONYMS; makes a style findable by a local name in the omnisearch
  // (typing "fondillon" surfaces the rancio style → its appellations).
  const STYLE_SEARCH_TERMS = __OWM_style_search_terms_json__;
  // Classification facet (aging / Prädikat / selection tiers) — a facet parallel
  // to styles; same tree/descendants/labels/synonym shape.
  const FACET_CLASS_TREE = __OWM_class_tree_json__;
  const CLASS_DESCENDANTS = __OWM_class_descendants_json__;
  const CLASS_LABELS = __OWM_class_labels_json__;
  const CLASS_SEARCH_TERMS = __OWM_class_search_terms_json__;
  const LABELS = __OWM_labels_json__;
  // Default document title (the locale homepage title). The tab title tracks
  // the open appellation so it doesn't get stuck on whichever entity page the
  // user landed on / first opened; reset to this when the panel closes.
  const DEFAULT_TITLE = LABELS.page_title;
  const GITHUB_NEW_ISSUE_URL = "__OWM_github_new_issue_url__";
  // Per-jurisdiction regulator-published specification document name,
  // in the regulator's own language. Used by the stub-message block
  // when no source document has been located for an appellation yet.
  const STUB_DOC_NAMES = {
    fr: 'cahier des charges',
    es: 'pliego de condiciones',
    pt: 'caderno de especificações',
    it: 'disciplinare di produzione',
    at: 'Produktspezifikation',
    si: 'specifikacija proizvoda',
    hr: 'specifikacija proizvoda',
    ro: 'caiet de sarcini',
  };
  const GRAPES_INFO = (window.__OWM_DATA && window.__OWM_DATA.grapes_info) || {};
  // Slug -> siblings sharing the same VIVC variety id. Used to make the
  // grape filter synonym-aware: toggling Cot also matches AOCs that
  // list Malbec / Auxerrois / any other regulatory spelling of vivc_id
  // 2889. The facet list keeps each spelling as its own row (so the user
  // sees the regulator's terminology) — the expansion happens only in
  // the filter predicate.
  const VIVC_SIBLINGS = __OWM_vivc_siblings_json__;
  // Per-locale canonical row label: each member of a VIVC group maps to
  // the single canonical slug under which the facet renders. Cross-narrow
  // counts roll up via this map so a record using "malbec" increments the
  // canonical "cot" row.
  const SLUG_TO_CANONICAL = __OWM_slug_to_canonical_json__;
  // Synonyms shown inline on each canonical row (e.g. Côt → [malbec,
  // auxerrois]). Sorted by global usage; the row's `.name` span includes
  // every synonym so the per-facet search input matches any spelling.
  const GRAPE_SYNONYMS = __OWM_grape_synonyms_json__;
  function expandGrapeSet(set) {
    if (!set || !set.size) return set;
    const out = new Set(set);
    for (const slug of set) {
      const sibs = VIVC_SIBLINGS[slug];
      if (sibs) for (const s of sibs) out.add(s);
    }
    return out;
  }
  function grapeSynonymsHtml(canonSlug) {
    const syns = GRAPE_SYNONYMS[canonSlug];
    if (!syns || !syns.length) return '';
    const labels = syns.map(s => grapeName(s)).join(', ');
    return ` <span class="syns">(${labels})</span>`;
  }

  // -------------------------- grape chip filter --------------------------
  //
  // Replaces the long-list checkbox facet for grapes with a typeahead +
  // selected-chip UX. The index ships pre-built (one entry per canonical
  // slug with cahier label + VIVC prime + full alias vocabulary + per-role
  // counts). Match logic: substring against the label and any alias, with
  // a score (prefix > substring, label > alias) so "garna" surfaces
  // Grenache (Garnacha) and "shiraz" surfaces Syrah.
  const GRAPE_SEARCH_INDEX = __OWM_grape_search_index_json__;
  const _GRAPE_INDEX_NORM = GRAPE_SEARCH_INDEX.map(entry => ({
    entry,
    labelN: searchNormalize(entry.label),
    aliasesN: (entry.aliases || []).map(a => searchNormalize(a)),
  }));

  function rankGrapeSuggestions(query, role, limit) {
    const countKey = role === 'principal' ? 'count_principal'
                   : role === 'accessory' ? 'count_accessory' : 'count';
    const nq = searchNormalize(query || '');
    if (!nq) {
      return _GRAPE_INDEX_NORM
        .filter(e => e.entry[countKey] > 0)
        .slice(0, limit)
        .map(e => ({ entry: e.entry, matched: null, score: 0 }));
    }
    const out = [];
    for (const e of _GRAPE_INDEX_NORM) {
      if (e.entry[countKey] === 0) continue;
      let score = -1;
      let matched = null;  // The alias string that matched, if any.
      if (e.labelN.startsWith(nq)) score = 100;
      else if (e.labelN.includes(nq)) score = 80;
      else {
        // Walk aliases; remember which one matched best so the suggestion
        // can promote that spelling to the primary slot ("Ull de Llebre
        // (Tempranillo)" instead of plain "Tempranillo" when the user
        // typed "ull").
        let bestAliasScore = -1;
        let bestAliasIdx = -1;
        for (let i = 0; i < e.aliasesN.length; i++) {
          const a = e.aliasesN[i];
          let s = -1;
          if (a.startsWith(nq)) s = 60;
          else if (a.includes(nq)) s = 40;
          if (s > bestAliasScore) { bestAliasScore = s; bestAliasIdx = i; }
        }
        if (bestAliasScore >= 0) {
          score = bestAliasScore;
          matched = e.entry.aliases[bestAliasIdx];
        }
      }
      if (score >= 0) out.push({ entry: e.entry, matched, score });
    }
    out.sort((a, b) => b.score - a.score || b.entry[countKey] - a.entry[countKey]);
    return out.slice(0, limit).map(o => ({ entry: o.entry, matched: o.matched, score: o.score }));
  }

  function _findGrapeEntry(slug) {
    for (const e of _GRAPE_INDEX_NORM) if (e.entry.slug === slug) return e.entry;
    return null;
  }

  function _grapeChipHtml(entry) {
    const canon = entry.canonical && !canonicalEqualsCahier(entry.canonical, entry.label)
      ? ` <span class="canon">(${escapeHtml(entry.canonical)})</span>` : '';
    return (
      `<span class="chip" data-slug="${escapeAttr(entry.slug)}">` +
        `<span class="name">${escapeHtml(toTitleCase(entry.label))}</span>${canon}` +
        `<button class="chip-x" type="button" aria-label="Remove ${escapeAttr(entry.label)}">×</button>` +
      `</span>`
    );
  }

  function _grapeSuggestionHtml(entry, matched, role, active) {
    // When the query matched on an alias (e.g. "ull de llebre" → Tempranillo
    // via the GRAPE_ALIAS reverse-key "ull-de-llebre"), promote the
    // matched alias to the primary slot so the suggestion reads in the
    // user's terminology — "Ull de Llebre (Tempranillo)" — instead of
    // burying the match in the canonical row label.
    const primary = matched || entry.label;
    const secondary = matched && matched.toLowerCase() !== entry.label.toLowerCase()
      ? entry.label
      : (entry.canonical && !canonicalEqualsCahier(entry.canonical, entry.label) ? entry.canonical : '');
    const secondaryHtml = secondary
      ? ` <span class="canon">${escapeHtml(toTitleCase(secondary))}</span>` : '';
    const countKey = role === 'principal' ? 'count_principal'
                   : role === 'accessory' ? 'count_accessory' : 'count';
    const cls = ['suggestion'];
    if (active) cls.push('active');
    return (
      `<div class="${cls.join(' ')}" role="option" data-slug="${escapeAttr(entry.slug)}">` +
        `<span class="name">${escapeHtml(toTitleCase(primary))}</span>${secondaryHtml}` +
        `<span class="count">${entry[countKey]}</span>` +
      `</div>`
    );
  }

  function buildGrapeChipFilter(container, role, filterSet) {
    container.innerHTML =
      `<div class="chip-tray" aria-live="polite"></div>` +
      `<div class="grape-search-wrap">` +
        `<input type="text" class="grape-search" name="grape-search-${escapeAttr(role)}" placeholder="${escapeAttr(LABELS.search_grape_placeholder)}" autocomplete="off" role="combobox" aria-expanded="false" aria-autocomplete="list">` +
        `<div class="grape-suggestions" role="listbox" hidden></div>` +
      `</div>`;
    const tray = container.querySelector('.chip-tray');
    const input = container.querySelector('.grape-search');
    const drop  = container.querySelector('.grape-suggestions');
    let activeIdx = 0;
    let currentSuggestions = [];

    function renderChips() {
      const chips = [];
      for (const slug of filterSet) {
        const e = _findGrapeEntry(slug);
        if (e) chips.push(_grapeChipHtml(e));
      }
      tray.innerHTML = chips.join('');
    }

    function renderSuggestions(q) {
      currentSuggestions = rankGrapeSuggestions(q, role, 12)
        .filter(s => !filterSet.has(s.entry.slug));
      activeIdx = 0;
      if (!currentSuggestions.length) {
        drop.innerHTML = '';
        drop.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        return;
      }
      drop.innerHTML = currentSuggestions
        .map((s, i) => _grapeSuggestionHtml(s.entry, s.matched, role, i === activeIdx)).join('');
      drop.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function highlight(i) {
      const items = drop.querySelectorAll('.suggestion');
      if (!items.length) return;
      items.forEach((el, k) => el.classList.toggle('active', k === i));
      activeIdx = i;
      const cur = items[i];
      if (cur) cur.scrollIntoView({ block: 'nearest' });
    }

    function pick(slug) {
      filterSet.add(slug);
      input.value = '';
      renderChips();
      renderSuggestions('');
      applyFilter();
      input.focus();
    }

    function remove(slug) {
      filterSet.delete(slug);
      renderChips();
      renderSuggestions(input.value);
      applyFilter();
    }

    tray.addEventListener('click', (e) => {
      const btn = e.target.closest('.chip-x');
      if (!btn) return;
      const chip = btn.closest('.chip');
      if (chip) remove(chip.dataset.slug);
    });

    drop.addEventListener('mousedown', (e) => {
      const s = e.target.closest('.suggestion');
      if (!s) return;
      e.preventDefault();  // keep focus on input
      pick(s.dataset.slug);
    });

    drop.addEventListener('mousemove', (e) => {
      const s = e.target.closest('.suggestion');
      if (!s) return;
      const items = Array.from(drop.querySelectorAll('.suggestion'));
      highlight(items.indexOf(s));
    });

    input.addEventListener('input', () => renderSuggestions(input.value));
    input.addEventListener('focus', () => renderSuggestions(input.value));
    input.addEventListener('blur', () => {
      // Delay so the mousedown handler runs before we hide.
      setTimeout(() => { drop.hidden = true; input.setAttribute('aria-expanded', 'false'); }, 120);
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (drop.hidden) renderSuggestions(input.value);
        else highlight((activeIdx + 1) % currentSuggestions.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!drop.hidden) highlight((activeIdx - 1 + currentSuggestions.length) % currentSuggestions.length);
      } else if (e.key === 'Enter') {
        if (!drop.hidden && currentSuggestions[activeIdx]) {
          e.preventDefault();
          pick(currentSuggestions[activeIdx].entry.slug);
        }
      } else if (e.key === 'Escape') {
        drop.hidden = true;
        input.setAttribute('aria-expanded', 'false');
      } else if (e.key === 'Backspace' && !input.value && filterSet.size) {
        // Remove the most-recently-added chip.
        const last = [...filterSet].pop();
        remove(last);
      }
    });

    renderChips();
    container._refresh = () => { renderChips(); if (!drop.hidden) renderSuggestions(input.value); };
  }

  function refreshAllGrapeChipFilters() {
    document.querySelectorAll('.grape-chip-filter').forEach(c => c._refresh && c._refresh());
  }
  const STYLES_INFO = __OWM_styles_info_json__;
  const REGION_LABELS = __OWM_region_labels_json__;
  const COUNTRY_LABELS = __OWM_country_labels_json__;
  const COUNTRY_FLAG_EMOJI = __OWM_country_flag_emoji_json__;
  const LANG = "__OWM_lang_attr__";
  const SOURCE_TYPE = "__OWM_source_type__";

  // Plausible custom-event helper. No-ops gracefully if the analytics
  // script failed to load (ad-blocker, offline preview, dev build).
  // All props use bounded slug vocabularies — never raw user text — so
  // the breakdown UI stays useful and no PII can leak.
  function track(name, props) {
    try {
      if (typeof window.plausible !== 'function') return;
      window.plausible(name, props ? { props: props } : undefined);
    } catch (e) {}
  }

  // Title-case the first letter of each word (after start, whitespace,
  // hyphen, or apostrophe). Wikipedia grape titles aren't uniformly
  // cased (FR uses "Cabernet sauvignon" sentence case while EN uses
  // "Cabernet Sauvignon" title case), and the slug fallback is pure
  // lowercase — normalising here makes pills and filter entries
  // consistent regardless of source.
  function toTitleCase(s) {
    return s.replace(/(?:^|[\s\-'(])\p{L}/gu, c => c.toUpperCase());
  }

  function grapeName(slug) {
    const info = GRAPES_INFO[slug];
    const raw = (info && info.name) ? info.name : slug.replace(/-/g, ' ');
    return toTitleCase(raw);
  }

  function regionLabel(region) {
    if (!region) return LABELS.meta_no_region;
    return REGION_LABELS[region] || region;
  }

  function oneCountryChip(countryCode) {
    const flag = COUNTRY_FLAG_EMOJI[countryCode] || '';
    const name = COUNTRY_LABELS[countryCode] || '';
    if (!flag && !name) return '';
    const flagSpan = flag ? `<span class="country-flag" aria-hidden="true">${flag}</span>` : '';
    const nameSpan = name ? `<span class="country-name">${escapeHtml(name)}</span>` : '';
    return `<span class="meta-country">${flagSpan}${nameSpan}</span>`;
  }

  // Cross-border PDOs (e.g. Maasvallei Limburg BE+NL) get a chip per
  // country, joined with " · ". Single-country records render one chip.
  function countryChipHtml(countryCode, aliases) {
    if (!countryCode) return '';
    const codes = [countryCode].concat(aliases || []);
    return codes.map(oneCountryChip).filter(Boolean).join(' · ');
  }

  function grapeUrl(slug) {
    const info = GRAPES_INFO[slug];
    if (info && info.page_url) return info.page_url;
    const title = slug.replace(/-/g, '_').replace(/^./, c => c.toUpperCase());
    return `https://${LANG}.wikipedia.org/wiki/${title}`;
  }

  // True when the per-AOC cahier spelling and the VIVC prime name refer
  // to the same variety after a light normalisation (strip diacritics,
  // the INAO trailing colour letter, and the VIVC trailing color word).
  // When equal, we suppress the canonical bracket to avoid pills like
  // "Touriga Nacional (Touriga Nacional)".
  const CANON_COLOR_WORD_RE = /\b(tinto|tinta|blanco|blanca|noir|blanc|gris|rouge|ros[eé])\b/gi;
  const CANON_COLOR_LETTER_RE = /\s+(b|n|g|rs|rg)$/i;
  function canonicalEqualsCahier(canon, cahier) {
    const norm = s => s
      .normalize('NFKD')
      .replace(/\p{Diacritic}/gu, '')
      .replace(CANON_COLOR_LETTER_RE, '')
      .replace(CANON_COLOR_WORD_RE, '')
      .replace(/[^a-z0-9]/gi, '')
      .toLowerCase();
    return norm(canon) === norm(cahier);
  }

  function searchNormalize(s) {
    return (s || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  }

  // BG / GR appellations carry both a native-script name (Cyrillic /
  // Greek) and an informational Latin transliteration (`name_latin`).
  // Search has to match either form so a user typing "Mavrud" finds
  // "Мавруд".
  function searchableText(rec) {
    return searchNormalize(((rec && rec.name) || '') + ' ' + ((rec && rec.name_latin) || ''));
  }

  function nameWithLatin(rec) {
    const native = escapeHtml((rec && rec.name) || '');
    const latin = (rec && rec.name_latin) || '';
    if (!latin || latin === rec.name) return native;
    return native + ' <span class="latin">(' + escapeHtml(latin) + ')</span>';
  }

  const proto = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', proto.tile);

  // Basemap: CARTO Voyager (light) + dark_all (dark). BOTH rasters are added up
  // front and switched by layer visibility, so the theme toggle is live — no
  // source remove/re-add (which would reorder layers above the appellation
  // polygons and drop their selection feature-state). Same CARTO / OSM credit.
  function cartoTiles(style) {
    return ['a', 'b', 'c'].map(function (s) {
      return 'https://' + s + '.basemaps.cartocdn.com/' + style + '/{z}/{x}/{y}.png';
    });
  }
  function effectiveTheme() {
    var t = null;
    try { t = localStorage.getItem('theme'); } catch (e) {}
    if (t === 'light' || t === 'dark') return t;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  const basemapAttribution = '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
  const initialDark = effectiveTheme() === 'dark';
  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        'basemap-light': { type: 'raster', tileSize: 256, tiles: cartoTiles('rastertiles/voyager'), attribution: basemapAttribution },
        'basemap-dark': { type: 'raster', tileSize: 256, tiles: cartoTiles('dark_all'), attribution: basemapAttribution }
      },
      layers: [
        { id: 'basemap-light', type: 'raster', source: 'basemap-light', layout: { visibility: initialDark ? 'none' : 'visible' } },
        { id: 'basemap-dark', type: 'raster', source: 'basemap-dark', layout: { visibility: initialDark ? 'visible' : 'none' } }
      ]
    },
    // minZoom 3 keeps the camera inside the tileset's lowest level (tiles
    // start at z3) so zooming out to a continental overview never drops into
    // an empty, polygon-less void. maxZoom 14 is defensive (tiles max at z12;
    // MapLibre overzooms cleanly above that).
    center: [2.6, 46.5], zoom: 5.4, minZoom: 3, maxZoom: 14, hash: true
  });

  // ----- theme switch (light / dark / system) -----
  function applyBasemap() {
    const dark = effectiveTheme() === 'dark';
    if (map.getLayer('basemap-dark')) map.setLayoutProperty('basemap-dark', 'visibility', dark ? 'visible' : 'none');
    if (map.getLayer('basemap-light')) map.setLayoutProperty('basemap-light', 'visibility', dark ? 'none' : 'visible');
  }
  function updateThemeButtons(mode) {
    document.querySelectorAll('#theme-toggle .theme-btn').forEach(function (b) {
      const on = b.dataset.themeMode === mode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function setTheme(mode) {
    try { if (mode === 'system') localStorage.removeItem('theme'); else localStorage.setItem('theme', mode); } catch (e) {}
    document.documentElement.classList.toggle('theme-dark', effectiveTheme() === 'dark');
    applyBasemap();
    updateThemeButtons(mode);
    track('Theme Changed', { theme: mode, locale: LANG });
  }
  (function () {
    let saved = 'system';
    try { const t = localStorage.getItem('theme'); if (t === 'light' || t === 'dark') saved = t; } catch (e) {}
    updateThemeButtons(saved);
    document.querySelectorAll('#theme-toggle .theme-btn').forEach(function (b) {
      b.addEventListener('click', function () { setTheme(b.dataset.themeMode); });
    });
    // In system mode, follow live OS theme changes (CSS re-evaluates the class;
    // the basemap needs the explicit nudge).
    if (window.matchMedia) {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const onChange = function () {
        let cur = null;
        try { cur = localStorage.getItem('theme'); } catch (e) {}
        if (cur === 'light' || cur === 'dark') return;
        document.documentElement.classList.toggle('theme-dark', mq.matches);
        applyBasemap();
      };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  })();

  // Preserve the camera hash AND the open-appellation path segment when
  // switching locale (/<lang>/<slug>), and remember the manual choice.
  document.querySelectorAll('#lang-switcher a').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      try { localStorage.setItem('lang_choice', a.dataset.lang); } catch (err) {}
      const slug = slugFromPath();
      const code = a.dataset.lang;
      const dest = (slug && AOCS[slug]) ? ('/' + code + '/' + encodeURIComponent(slug)) : a.dataset.href;
      window.location.href = dest + window.location.hash;
    });
  });

  // Skip-to-map link: focus the map canvas (keyboard-pannable) rather than
  // letting the "#map" fragment overwrite the maplibre position hash.
  const skipLink = document.querySelector('.skip-link');
  if (skipLink) {
    skipLink.addEventListener('click', e => {
      e.preventDefault();
      const canvas = map.getCanvas();
      if (!canvas.hasAttribute('tabindex')) canvas.setAttribute('tabindex', '0');
      canvas.focus();
    });
  }

  // Mobile sidebar toggle.
  const sidebarEl = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebar-toggle');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => sidebarEl.classList.toggle('open'));
  }

  // About dialog. Native <dialog>; backdrop click closes.
  const aboutDialog = document.getElementById('about-dialog');
  const aboutLink = document.getElementById('about-link');
  if (aboutDialog && aboutLink) {
    aboutLink.addEventListener('click', e => {
      e.preventDefault();
      if (typeof aboutDialog.showModal === 'function') aboutDialog.showModal();
      else aboutDialog.setAttribute('open', '');
    });
    aboutDialog.querySelector('.close').addEventListener('click', () => aboutDialog.close());
    aboutDialog.addEventListener('click', e => {
      const r = aboutDialog.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right
                  && e.clientY >= r.top  && e.clientY <= r.bottom;
      if (!inside) aboutDialog.close();
    });
  }

  // Defeat naive scrapers: the address never appears as a contiguous
  // string in rendered HTML. We arm the anchor's href on first
  // interaction (mousedown/focus/touchstart, all of which fire before
  // the click that actually navigates), so the browser handles the
  // mailto: protocol natively. We also copy the address to the
  // clipboard on click so the link still works for users without a
  // configured mailto handler (Firefox silently drops navigation in
  // that case).
  document.querySelectorAll('a.feedback-mail').forEach(a => {
    const address = () => a.dataset.u + '@' + a.dataset.d;
    const arm = () => {
      if (a.dataset.u && a.dataset.d) {
        a.href = 'mailto:' + address() + '?subject=open%20wine%20map';
      }
    };
    a.addEventListener('mousedown', arm);
    a.addEventListener('focus', arm);
    a.addEventListener('touchstart', arm, { passive: true });
    a.addEventListener('click', () => {
      const addr = address();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(addr).catch(() => {});
      }
      const toast = document.createElement('span');
      toast.className = 'feedback-copied';
      toast.textContent = LABELS.feedback_copied_label;
      a.insertAdjacentElement('afterend', toast);
      requestAnimationFrame(() => toast.classList.add('visible'));
      setTimeout(() => {
        toast.classList.remove('visible');
        toast.addEventListener('transitionend', () => toast.remove(), { once: true });
      }, 1800);
    });
  });

  let viewMode = 'simple';
  try { viewMode = localStorage.getItem('view_mode') || 'simple'; } catch (e) {}
  if (viewMode !== 'advanced') viewMode = 'simple';

  let showIgp = false;
  try { showIgp = localStorage.getItem('show_igp') === '1'; } catch (e) {}

  let showSpirits = false;
  try { showSpirits = localStorage.getItem('show_spirits') === '1'; } catch (e) {}

  // Spirits toggle is Advanced-only; in Simple mode spirits are always
  // hidden regardless of the persisted preference.
  function spiritsVisible() { return viewMode === 'advanced' && showSpirits; }

  const filters = {
    q: '',
    styles: new Set(),
    stylesSimple: new Set(),
    classifications: new Set(),
    principal: new Set(),
    accessory: new Set(),
    grapesAll: new Set(),
    appellations: new Set(),
    // When true, the grape filter matches grapes_principal instead of grapes_all
    // (the "main grape only" toggle inside the Grapes facet).
    mainGrapeOnly: false,
  };
  try { filters.mainGrapeOnly = localStorage.getItem('main_grape_only') === '1'; } catch (e) {}

  function debounce(fn, ms) {
    let t = null;
    return function () {
      const args = arguments;
      if (t) clearTimeout(t);
      t = setTimeout(() => { t = null; fn.apply(null, args); }, ms);
    };
  }
  // The map filter + status update stay synchronous so the map reacts instantly;
  // only the heavy facet-availability recompute (iterates the whole ~3.3k-record
  // corpus and rebuilds facet DOM) is coalesced across rapid filter toggles.
  const refreshFacetAvailabilityDebounced = debounce(() => refreshFacetAvailability(), 140);

  function applyFilter(opts) {
    const expr = buildFilterExpr();
    for (const id of ['appellations-fill', 'appellations-outline',
                       'appellations-fill-villages', 'appellations-outline-villages']) {
      if (map.getLayer(id)) map.setFilter(id, expr);
    }
    updateStatus();
    refreshFacetBadges();
    refreshFacetAvailabilityDebounced();
    renderActiveFilters();
    if (opts && opts.fit) fitToFiltered();
  }

  document.getElementById('active-filters-chips').addEventListener('click', e => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const chip = btn.closest('.filter-chip');
    if (!chip) return;
    const kind = chip.dataset.kind;
    const key = chip.dataset.key;
    if (kind === 'styleSimple') filters.stylesSimple.delete(key);
    else if (kind === 'style') filters.styles.delete(key);
    else if (kind === 'classification') filters.classifications.delete(key);
    else if (kind === 'grapeAll') filters.grapesAll.delete(key);
    else if (kind === 'principal') filters.principal.delete(key);
    else if (kind === 'accessory') filters.accessory.delete(key);
    else if (kind === 'appellation') filters.appellations.delete(key);
    else if (kind === 'region') setRegionSelection(key, false);
    else if (kind === 'mainGrapeOnly') {
      filters.mainGrapeOnly = false;
      const m = document.getElementById('main-grape-only'); if (m) m.checked = false;
      try { localStorage.setItem('main_grape_only', '0'); } catch (e) {}
    }
    // Sync the underlying checkboxes for the cleared filter.
    document.querySelectorAll('#sidebar .facet input[type=checkbox]').forEach(inp => {
      const k = inp.dataset.key;
      const isApp = inp.closest('#facet-appellations');
      if (isApp && k) {
        inp.checked = filters.appellations.has(k);
      }
    });
    refreshSidebarCheckedState();
    refreshRegionTriStates();
    applyFilter();
  });

  function refreshSidebarCheckedState() {
    // Re-sync facet checkboxes (styles only — grapes are chip filters
    // and re-render their chip tray via `refreshAllGrapeChipFilters`).
    const sets = {
      'facet-styles': filters.styles,
      'facet-styles-simple': filters.stylesSimple,
      'facet-classification': filters.classifications,
    };
    for (const [id, set] of Object.entries(sets)) {
      const el = document.getElementById(id);
      if (!el) continue;
      el.querySelectorAll('input[type=checkbox]').forEach(inp => {
        inp.checked = set.has(inp.dataset.key);
      });
    }
    refreshAllGrapeChipFilters();
  }

  function fitToFiltered() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let any = false;
    for (const slug in AOCS) {
      const rec = AOCS[slug];
      const b = (viewMode === 'simple' && rec.bbox_villages) ? rec.bbox_villages : rec.bbox;
      if (!b) continue;
      if (!matchesClient(rec, slug)) continue;
      if (b[0] < minX) minX = b[0];
      if (b[1] < minY) minY = b[1];
      if (b[2] > maxX) maxX = b[2];
      if (b[3] > maxY) maxY = b[3];
      any = true;
    }
    if (!any) return;
    if (minX >= maxX || minY >= maxY) return;
    map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 40, maxZoom: 10, duration: 500 });
  }

  function fmt(tpl, vars) {
    return tpl.replace(/\{(\w+)\}/g, (_, k) => vars[k] != null ? vars[k] : '');
  }

  function updateStatus() {
    const el = document.getElementById('status');
    const total = Object.keys(AOCS).length;
    const expr = buildFilterExpr();
    if (!expr) { el.textContent = fmt(LABELS.count_total, { n: total }); return; }
    let n = 0;
    for (const slug in AOCS) if (matchesClient(AOCS[slug], slug)) n++;
    // When the filter excludes every visible record but matches one or
    // more hidden IGPs, surface a one-click reveal so the user understands
    // *why* the camera didn't move. Same idea for hidden spirits.
    if (n === 0) {
      let nHiddenIgp = 0;
      if (!showIgp) {
        for (const slug in AOCS) {
          const rec = AOCS[slug];
          if ((rec.kind || 'AOC') !== 'IGP') continue;
          if (matchesClient(rec, slug, { ignoreIgpGate: true })) nHiddenIgp++;
        }
      }
      if (nHiddenIgp > 0) {
        const prefix = fmt(LABELS.count_filtered, { n: 0, total: total });
        el.textContent = prefix + ' · ';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hint-action';
        btn.textContent = fmt(LABELS.count_hidden_igp_hint, { n: nHiddenIgp });
        btn.addEventListener('click', () => {
          showIgp = true;
          const igpEl = document.getElementById('show-igp');
          if (igpEl) igpEl.checked = true;
          try { localStorage.setItem('show_igp', '1'); } catch (err) {}
          track('Kind Toggled', { kind: 'igp', enabled: 'true', locale: LANG, via: 'reveal-hint' });
          applyFilter({ fit: true });
        });
        el.appendChild(btn);
        return;
      }
    }
    el.textContent = fmt(LABELS.count_filtered, { n: n, total: total });
  }

  function setIntersects(set, arr) {
    if (!arr) return false;
    for (const v of arr) if (set.has(v)) return true;
    return false;
  }

  function buildFacet(containerId, items, store, format, extraFormat) {
    const el = document.getElementById(containerId);
    const html = items.map(([key, count]) => {
      const safeKey = String(key).replace(/"/g, '&quot;');
      const label = format ? format(key) : key;
      const extra = extraFormat ? extraFormat(key) : '';
      return `<label><input type="checkbox" data-key="${safeKey}"><span class="name">${label}${extra}</span><span class="count">${count}</span></label>`;
    }).join('');
    el.innerHTML = html;
    el.addEventListener('change', e => {
      if (e.target.tagName !== 'INPUT') return;
      const k = e.target.dataset.key;
      if (e.target.checked) store.add(k); else store.delete(k);
      if (e.target.checked) {
        track('Filter Applied', { facet: containerId.replace(/^facet-/, ''), value: k, locale: LANG });
      }
      applyFilter({ fit: true });
    });
  }

  function buildTreeFacet(containerId, tree, store, labels, descendants, facetName) {
    const el = document.getElementById(containerId);
    if (!el) return;  // defensive null-guard
    const html = tree.map(node => {
      const safeKey = String(node.slug).replace(/"/g, '&quot;');
      const label = labels[node.slug] || node.slug;
      const hasChildren = (descendants[node.slug] || []).length > 1;
      const cls = `tree-row${ hasChildren ? ' tree-row-parent' : '' }`;
      return `<label class="${cls}" data-depth="${node.depth}"><input type="checkbox" data-key="${safeKey}"><span class="name">${label}</span><span class="count">${node.count}</span></label>`;
    }).join('');
    el.innerHTML = html;
    el.addEventListener('change', e => {
      if (e.target.tagName !== 'INPUT') return;
      const k = e.target.dataset.key;
      if (e.target.checked) store.add(k); else store.delete(k);
      if (e.target.checked) {
        track('Filter Applied', { facet: facetName, value: k, locale: LANG });
      }
      applyFilter({ fit: true });
    });
  }

  // Expand a set of taxonomy slugs to the leaf slugs records actually carry,
  // so a click on a parent (e.g. "sweet" / "aging") catches every descendant.
  function expandTree(set, descendants) {
    if (!set.size) return null;
    const out = new Set();
    for (const s of set) {
      const ds = descendants[s];
      if (ds && ds.length) for (const d of ds) out.add(d);
      else out.add(s);
    }
    return out;
  }
  const expandStyles = set => expandTree(set, STYLE_DESCENDANTS);
  const expandClass = set => expandTree(set, CLASS_DESCENDANTS);

  buildTreeFacet('facet-styles', FACET_STYLES_TREE, filters.styles, STYLE_LABELS, STYLE_DESCENDANTS, 'styles');
  buildTreeFacet('facet-classification', FACET_CLASS_TREE, filters.classifications, CLASS_LABELS, CLASS_DESCENDANTS, 'classification');
  buildFacet('facet-styles-simple', FACET_STYLES_SIMPLE, filters.stylesSimple, k => SIMPLE_STYLE_LABELS[k] || k);
  document.querySelectorAll('.grape-chip-filter').forEach(container => {
    const role = container.dataset.role || 'all';
    const set = role === 'principal' ? filters.principal
              : role === 'accessory' ? filters.accessory
              : filters.grapesAll;
    buildGrapeChipFilter(container, role, set);
  });

  // Map of region → list of slugs, computed once. The appellation tree
  // re-renders on spirits-toggle (entries appear/disappear), but the
  // per-region grouping itself is stable across rebuilds.
  const REGION_SLUGS = (() => {
    const m = new Map();
    const order = FACET_REGIONS.map(([r]) => r);
    for (const r of order) m.set(r, []);
    m.set('', []);
    for (const slug in AOCS) {
      const r = AOCS[slug].region || '';
      if (!m.has(r)) m.set(r, []);
      m.get(r).push(slug);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => AOCS[a].name.localeCompare(AOCS[b].name, 'fr'));
    }
    return m;
  })();

  function visibleSlugsInRegion(region) {
    const all = REGION_SLUGS.get(region) || [];
    if (spiritsVisible()) return all;
    return all.filter(s => AOCS[s].is_wine !== false);
  }

  function setRegionSelection(region, on) {
    const slugs = visibleSlugsInRegion(region);
    for (const s of slugs) {
      if (on) filters.appellations.add(s);
      else filters.appellations.delete(s);
    }
  }

  function regionTriState(region) {
    const slugs = visibleSlugsInRegion(region);
    if (!slugs.length) return 'empty';
    let n = 0;
    for (const s of slugs) if (filters.appellations.has(s)) n++;
    if (n === 0) return 'unchecked';
    if (n === slugs.length) return 'checked';
    return 'indeterminate';
  }

  function buildAppellationFacet() {
    const el = document.getElementById('facet-appellations');
    if (!el) return;  // defensive null-guard
    const html = [];
    for (const [region, allSlugs] of REGION_SLUGS) {
      const slugs = spiritsVisible() ? allSlugs : allSlugs.filter(s => AOCS[s].is_wine !== false);
      if (!slugs.length) continue;
      const label = region ? regionLabel(region) : LABELS.meta_no_region;
      const items = slugs.map(slug => {
        const safeSlug = escapeAttr(slug);
        const rec = AOCS[slug];
        const nameHtml = nameWithLatin(rec);
        const checked = filters.appellations.has(slug) ? ' checked' : '';
        const openLbl = escapeAttr(fmt(LABELS.open_appellation_aria, { name: rec.name || slug }));
        return `<label data-slug="${safeSlug}" data-name="${escapeAttr(searchableText(rec))}"><input type="checkbox" data-key="${safeSlug}"${checked}><span class="name">${nameHtml}</span><button type="button" class="open-aoc" data-slug="${safeSlug}" aria-label="${openLbl}" title="${escapeAttr(LABELS.open_appellation_title)}">→</button></label>`;
      }).join('');
      const safeRegion = escapeAttr(region);
      // Checkbox lives outside `<summary>` (sibling of `<details>`,
      // not a descendant) so the nested-interactive-in-summary
      // accessibility warning doesn't fire. Visual layout is restored
      // via `.region-group-wrap`'s flex rule — checkbox + disclosure
      // sit in the same row.
      html.push(`<div class="region-group-wrap" data-region="${safeRegion}"><input type="checkbox" class="region-select" data-region="${safeRegion}" aria-label="${escapeAttr(LABELS.select_all_aria)}"><details class="region-group" data-region="${safeRegion}"><summary><span class="name">${escapeHtml(label)}</span><span class="count">${slugs.length}</span></summary><div class="region-items">${items}</div></details></div>`);
    }
    el.innerHTML = html.join('');
    // Reapply current search visibility (so a tree rebuild during a typed
    // query keeps the filtered view).
    refreshFacetVisibility('facet-appellations', filters.q);
    refreshRegionTriStates();
  }

  // Single delegated listener — buildAppellationFacet may run multiple
  // times (mode swap, spirits toggle), so the handler stays on the
  // container instead of being re-attached each time.
  document.getElementById('facet-appellations')?.addEventListener('change', e => {
    const el = document.getElementById('facet-appellations');
    if (e.target.tagName !== 'INPUT') return;
    if (e.target.classList.contains('region-select')) {
      const region = e.target.dataset.region;
      setRegionSelection(region, e.target.checked);
      for (const inp of el.querySelectorAll(
        `.region-group[data-region="${CSS.escape(region)}"] .region-items input[type=checkbox]`
      )) {
        inp.checked = filters.appellations.has(inp.dataset.key);
      }
      if (e.target.checked) {
        track('Filter Applied', { facet: 'region', value: region || '(none)', locale: LANG });
      }
    } else {
      const k = e.target.dataset.key;
      if (e.target.checked) filters.appellations.add(k); else filters.appellations.delete(k);
      if (e.target.checked) {
        track('Filter Applied', { facet: 'appellation', value: k, locale: LANG });
      }
    }
    refreshRegionTriStates();
    applyFilter({ fit: true });
  });

  // Keyboard/SR path to open an appellation's detail panel — the WebGL polygons
  // aren't DOM-reachable, so the facet "open" button is the only non-mouse way
  // in. preventDefault/stopPropagation stop the click from toggling the
  // enclosing label's filter checkbox.
  document.getElementById('facet-appellations')?.addEventListener('click', e => {
    const btn = e.target.closest('.open-aoc');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const slug = btn.dataset.slug;
    if (!AOCS[slug]) return;
    lastPanelTrigger = btn;
    lastStackKey = slug;
    stackFocusIndex = 0;
    renderPanelStack([slug], 0);
    track('Appellation Opened', { slug: slug, via: 'facet', locale: LANG });
    const b = (viewMode === 'simple' && AOCS[slug].bbox_villages) ? AOCS[slug].bbox_villages : AOCS[slug].bbox;
    if (b && typeof map.fitBounds === 'function') {
      map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, maxZoom: 11, duration: 500 });
    }
  });

  function refreshRegionTriStates() {
    const el = document.getElementById('facet-appellations');
    if (!el) return;
    el.querySelectorAll('.region-group').forEach(group => {
      const region = group.dataset.region;
      // `.region-select` is a sibling of `.region-group` inside the
      // `.region-group-wrap`, not a descendant. Reach via the parent.
      const cb = (group.parentElement || group).querySelector('.region-select');
      if (!cb) return;
      const state = regionTriState(region);
      cb.checked = state === 'checked';
      cb.indeterminate = state === 'indeterminate';
    });
  }

  function refreshFacetVisibility(containerId, q) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const nq = searchNormalize(q);
    // Appellation tree: groups + labels with data-name dataset.
    const groups = el.querySelectorAll('.region-group');
    if (groups.length) {
      groups.forEach(group => {
        let visible = 0;
        group.querySelectorAll('label').forEach(lbl => {
          const match = !nq || lbl.dataset.name.includes(nq);
          lbl.style.display = match ? '' : 'none';
          if (match) visible++;
        });
        const wrap = group.parentElement;
        if (wrap && wrap.classList.contains('region-group-wrap')) {
          wrap.style.display = visible ? '' : 'none';
        } else {
          group.style.display = visible ? '' : 'none';
        }
        // Auto-expand matching groups while searching, but re-collapse them
        // when the query is cleared — tracking which groups WE opened so a
        // group the user expanded by hand stays open. (Was: open-on-search
        // with no matching collapse, leaving every group expanded after clear.)
        if (nq) {
          if (visible && !group.open) { group.open = true; group.dataset.autoOpened = '1'; }
        } else if (group.dataset.autoOpened) {
          group.open = false;
          delete group.dataset.autoOpened;
        }
      });
      return;
    }
    // Flat facet (grapes etc.) — match against the .name span text.
    el.querySelectorAll('label').forEach(lbl => {
      const span = lbl.querySelector('.name');
      const text = searchNormalize(span ? span.textContent : '');
      lbl.style.display = (!nq || text.includes(nq)) ? '' : 'none';
    });
  }

  buildAppellationFacet();

  function applyMode() {
    document.documentElement.classList.toggle('mode-simple', viewMode === 'simple');
    document.documentElement.classList.toggle('mode-advanced', viewMode === 'advanced');
    document.querySelectorAll('#mode-toggle .mode-btn').forEach(b => {
      const on = b.dataset.mode === viewMode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    document.querySelectorAll('#sidebar [data-modes]').forEach(el => {
      const modes = el.dataset.modes.split(/\s+/);
      el.classList.toggle('mode-hidden', !modes.includes(viewMode));
    });
    swapMapLayers();
    // The appellation tree's contents depend on spiritsVisible(), which
    // depends on viewMode — rebuild on every mode switch (optional-chain the
    // children check defensively).
    if (document.getElementById('facet-appellations')?.children.length) {
      buildAppellationFacet();
    }
  }

  function swapMapLayers() {
    const advLayers = ['appellations-fill', 'appellations-outline'];
    const vilLayers = ['appellations-fill-villages', 'appellations-outline-villages'];
    const showAdv = viewMode === 'advanced';
    for (const id of advLayers) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', showAdv ? 'visible' : 'none');
    }
    for (const id of vilLayers) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', showAdv ? 'none' : 'visible');
    }
  }

  document.querySelectorAll('#mode-toggle .mode-btn').forEach(b => {
    b.addEventListener('click', () => {
      const next = b.dataset.mode;
      if (next === viewMode) return;
      viewMode = next;
      try { localStorage.setItem('view_mode', viewMode); } catch (e) {}
      track('View Mode Switched', { mode: viewMode, locale: LANG });
      applyMode();
      // Don't re-fit on a mode switch — preserve the current camera. (Was
      // `{fit:true}`: simple fits tight bbox_villages, advanced fits wider full
      // bbox, so toggling with a filter active jarringly zoomed the map out.)
      applyFilter();
    });
  });

  const igpEl = document.getElementById('show-igp');
  igpEl.checked = showIgp;
  igpEl.addEventListener('change', e => {
    showIgp = e.target.checked;
    try { localStorage.setItem('show_igp', showIgp ? '1' : '0'); } catch (err) {}
    track('Kind Toggled', { kind: 'igp', enabled: showIgp ? 'true' : 'false', locale: LANG });
    applyFilter({ fit: true });
  });

  const spiritsEl = document.getElementById('show-spirits');
  spiritsEl.checked = showSpirits;
  spiritsEl.addEventListener('change', e => {
    showSpirits = e.target.checked;
    try { localStorage.setItem('show_spirits', showSpirits ? '1' : '0'); } catch (err) {}
    track('Kind Toggled', { kind: 'spirits', enabled: showSpirits ? 'true' : 'false', locale: LANG });
    // Spirit AOCs join/leave the appellation tree; rebuild + reapply.
    buildAppellationFacet();
    applyFilter({ fit: true });
  });

  // The merged Appellation facet hosts the appellation search; typing in
  // it auto-expands the section if collapsed, since otherwise the tree
  // updates would be invisible to the user.
  const qInput = document.getElementById('q');
  // Debounced search analytics: fire once after the user stops typing.
  // We send result_count / had_match / query_len only — never the raw
  // string, since search boxes attract typos, names, and assorted junk.
  let searchTrackTimer = null;
  if (qInput) qInput.addEventListener('input', e => {
    filters.q = e.target.value.trim();
    refreshFacetVisibility('facet-appellations', filters.q);
    const det = qInput.closest('details');
    if (filters.q && det && !det.open) det.open = true;
    if (searchTrackTimer) clearTimeout(searchTrackTimer);
    if (filters.q) {
      searchTrackTimer = setTimeout(() => {
        const nq = searchNormalize(filters.q);
        let n = 0;
        for (const slug in AOCS) {
          if (searchableText(AOCS[slug]).includes(nq)) n++;
        }
        track('Search Used', {
          result_count: String(n),
          had_match: n > 0 ? 'true' : 'false',
          query_len: String(filters.q.length),
          locale: LANG,
        });
      }, 1000);
    }
  });

  // Per-facet search inputs (cépages). They filter only the visible
  // checkboxes in their target facet; they do not affect the map filter.
  document.querySelectorAll('.facet-search[data-facet]').forEach(input => {
    input.addEventListener('input', e => {
      refreshFacetVisibility(input.dataset.facet, e.target.value.trim());
    });
  });

  document.getElementById('reset').addEventListener('click', () => {
    track('Filters Reset', { locale: LANG });
    filters.q = '';
    filters.styles.clear(); filters.stylesSimple.clear();
    filters.classifications.clear();
    filters.principal.clear(); filters.accessory.clear(); filters.grapesAll.clear();
    filters.appellations.clear();
    filters.mainGrapeOnly = false;
    try { localStorage.setItem('main_grape_only', '0'); } catch (e) {}
    const _mgo = document.getElementById('main-grape-only'); if (_mgo) _mgo.checked = false;
    const _omni = document.getElementById('omni');
    if (_omni) {
      _omni.value = '';
      _omni.setAttribute('aria-expanded', 'false');
      _omni.removeAttribute('aria-activedescendant');
      const _od = document.getElementById('omni-suggestions'); if (_od) { _od.hidden = true; _od.innerHTML = ''; }
      const _ol = document.getElementById('omni-live'); if (_ol) _ol.textContent = '';
    }
    document.querySelectorAll('#sidebar .facet input[type=checkbox]').forEach(c => {
      c.checked = false;
      c.indeterminate = false;
    });
    document.querySelectorAll('.facet-search').forEach(i => { i.value = ''; });
    refreshFacetVisibility('facet-appellations', '');
    refreshFacetVisibility('facet-grapes-all', '');
    refreshFacetVisibility('facet-principal', '');
    refreshFacetVisibility('facet-accessory', '');
    applyFilter();
  });

  // ===================== search + browse rail (the sidebar) =====================
  // The production search/filter behaviour. A single merged grape model
  // (filters.grapesAll + filters.mainGrapeOnly), a unified omnisearch bar over
  // appellations + grapes + regions + styles that also live-filters the
  // appellation tree, and the filter functions below.

  function activeGrapeField() {
    return filters.mainGrapeOnly ? 'grapes_principal' : 'grapes_all';
  }
  // Union of the quick-chip buckets (stylesSimple, expanded to fine slugs) and
  // any advanced-tree picks (filters.styles), so style filtering is identical
  // regardless of view mode (simple chips + advanced-tree picks combined).
  function activeStyleFineSet() {
    const out = new Set();
    for (const b of filters.stylesSimple) for (const s of (SIMPLE_STYLE_BUCKETS[b] || [])) out.add(s);
    const fine = expandStyles(filters.styles);
    if (fine) for (const s of fine) out.add(s);
    return out;
  }

  function buildFilterExpr() {
    const parts = ['all'];
    if (!showIgp) parts.push(['!=', ['get', 'kind'], 'IGP']);
    if (!spiritsVisible()) parts.push(['==', ['get', 'is_wine'], '1']);
    function inField(field, set) {
      if (!set || !set.size) return null;
      const tests = [];
      for (const v of set) tests.push(['in', ';' + v + ';', ['get', field]]);
      return tests.length === 1 ? tests[0] : ['any', ...tests];
    }
    const sExpr = inField('styles', activeStyleFineSet());
    if (sExpr) parts.push(sExpr);
    const cExpr = inField('classifications', expandClass(filters.classifications));
    if (cExpr) parts.push(cExpr);
    const gExpr = inField(activeGrapeField(), expandGrapeSet(filters.grapesAll));
    if (gExpr) parts.push(gExpr);
    if (filters.appellations.size) {
      const tests = [];
      for (const s of filters.appellations) tests.push(['==', ['get', 'slug'], s]);
      parts.push(tests.length === 1 ? tests[0] : ['any', ...tests]);
    }
    return parts.length === 1 ? null : parts;
  }

  function matchesClient(rec, slug, opts) {
    if (!(opts && opts.ignoreIgpGate) && !showIgp && (rec.kind || 'AOC') === 'IGP') return false;
    if (!spiritsVisible() && rec.is_wine === false) return false;
    const styleSet = activeStyleFineSet();
    if (styleSet.size && !setIntersects(styleSet, rec.styles || [])) return false;
    const classSet = expandClass(filters.classifications);
    if (classSet && classSet.size && !setIntersects(classSet, rec.classifications || [])) return false;
    if (filters.grapesAll.size && !setIntersects(expandGrapeSet(filters.grapesAll), rec[activeGrapeField()] || [])) return false;
    if (filters.appellations.size && !filters.appellations.has(slug)) return false;
    return true;
  }

  function matchesExceptFacets(rec, slug, except) {
    if (!showIgp && (rec.kind || 'AOC') === 'IGP') return false;
    if (!spiritsVisible() && rec.is_wine === false) return false;
    if (!except.has('styles') && !except.has('stylesSimple')) {
      const styleSet = activeStyleFineSet();
      if (styleSet.size && !setIntersects(styleSet, rec.styles || [])) return false;
    }
    if (!except.has('classifications')) {
      const classSet = expandClass(filters.classifications);
      if (classSet && classSet.size && !setIntersects(classSet, rec.classifications || [])) return false;
    }
    if (!except.has('grapesAll') && filters.grapesAll.size && !setIntersects(expandGrapeSet(filters.grapesAll), rec[activeGrapeField()] || [])) return false;
    if (!except.has('appellations') && filters.appellations.size && !filters.appellations.has(slug)) return false;
    return true;
  }

  function renderActiveFilters() {
    const el = document.getElementById('active-filters-chips');
    if (!el) return;
    const chips = [];
    for (const k of filters.stylesSimple) chips.push({ kind: 'styleSimple', key: k, label: SIMPLE_STYLE_LABELS[k] || k });
    for (const k of filters.styles) chips.push({ kind: 'style', key: k, label: STYLE_LABELS[k] || k });
    for (const k of filters.classifications) chips.push({ kind: 'classification', key: k, label: CLASS_LABELS[k] || k });
    for (const k of filters.grapesAll) chips.push({ kind: 'grapeAll', key: k, label: grapeName(k) });
    if (filters.mainGrapeOnly) chips.push({ kind: 'mainGrapeOnly', key: '1', label: LABELS.main_grape_only_label });
    const collapsed = new Set();
    for (const [region] of REGION_SLUGS) {
      const slugs = visibleSlugsInRegion(region);
      if (!slugs.length) continue;
      if (slugs.every(s => filters.appellations.has(s))) {
        chips.push({ kind: 'region', key: region, label: region ? regionLabel(region) : LABELS.meta_no_region });
        for (const s of slugs) collapsed.add(s);
      }
    }
    for (const slug of filters.appellations) {
      if (collapsed.has(slug)) continue;
      const rec = AOCS[slug];
      if (rec) chips.push({ kind: 'appellation', key: slug, label: rec.name });
    }
    el.innerHTML = chips.map(c => {
      const cls = c.kind === 'region' ? 'filter-chip region-chip' : 'filter-chip';
      const removeAria = fmt(LABELS.remove_filter_aria, { label: c.label });
      return `<span class="${cls}" data-kind="${escapeAttr(c.kind)}" data-key="${escapeAttr(c.key)}"><span>${escapeHtml(c.label)}</span><button type="button" aria-label="${escapeAttr(removeAria)}">×</button></span>`;
    }).join('');
  }

  function regionsSelectedCount() {
    let n = 0;
    for (const [region] of REGION_SLUGS) {
      const st = regionTriState(region);
      if (st === 'checked' || st === 'indeterminate') n++;
    }
    return n;
  }

  function refreshFacetBadges() {
    const map_ = {
      styles: filters.stylesSimple.size + filters.styles.size,
      classification: filters.classifications.size,
      grapes: filters.grapesAll.size,
      appellations: filters.appellations.size,
      regions: regionsSelectedCount(),
    };
    document.querySelectorAll('#sidebar > details[data-facet]').forEach(det => {
      const badge = det.querySelector(':scope > summary .facet-badge');
      if (!badge) return;
      const n = map_[det.dataset.facet] || 0;
      badge.textContent = n > 0 ? String(n) : '';
    });
  }

  function refreshFacetAvailability() {
    const sEl = document.getElementById('facet-styles-simple');
    if (sEl) {
      const except = new Set(['stylesSimple']);
      const counts = new Map();
      for (const slug in AOCS) {
        const rec = AOCS[slug];
        if (!matchesExceptFacets(rec, slug, except)) continue;
        for (const v of (rec.styles_simple || [])) counts.set(v, (counts.get(v) || 0) + 1);
      }
      sEl.querySelectorAll('label').forEach(lbl => {
        const inp = lbl.querySelector('input[type=checkbox]'); if (!inp) return;
        const n = counts.get(inp.dataset.key) || 0;
        const c = lbl.querySelector('.count'); if (c) c.textContent = String(n);
        lbl.classList.toggle('facet-unavailable', n === 0 && !inp.checked);
      });
    }
    const treeEl = document.getElementById('facet-styles');
    if (treeEl) {
      const except = new Set(['styles']);
      const treeCounts = new Map();
      for (const slug in AOCS) {
        const rec = AOCS[slug];
        if (!matchesExceptFacets(rec, slug, except)) continue;
        const recStyleSet = new Set(rec.styles || []);
        if (!recStyleSet.size) continue;
        for (const node in STYLE_DESCENDANTS) {
          const ds = STYLE_DESCENDANTS[node];
          for (let i = 0; i < ds.length; i++) { if (recStyleSet.has(ds[i])) { treeCounts.set(node, (treeCounts.get(node) || 0) + 1); break; } }
        }
      }
      treeEl.querySelectorAll('label').forEach(lbl => {
        const inp = lbl.querySelector('input[type=checkbox]'); if (!inp) return;
        const n = treeCounts.get(inp.dataset.key) || 0;
        const c = lbl.querySelector('.count'); if (c) c.textContent = String(n);
        lbl.classList.toggle('facet-unavailable', n === 0 && !inp.checked);
      });
    }
    const classEl = document.getElementById('facet-classification');
    if (classEl) {
      const except = new Set(['classifications']);
      const classCounts = new Map();
      for (const slug in AOCS) {
        const rec = AOCS[slug];
        if (!matchesExceptFacets(rec, slug, except)) continue;
        const recClassSet = new Set(rec.classifications || []);
        if (!recClassSet.size) continue;
        for (const node in CLASS_DESCENDANTS) {
          const ds = CLASS_DESCENDANTS[node];
          for (let i = 0; i < ds.length; i++) { if (recClassSet.has(ds[i])) { classCounts.set(node, (classCounts.get(node) || 0) + 1); break; } }
        }
      }
      classEl.querySelectorAll('label').forEach(lbl => {
        const inp = lbl.querySelector('input[type=checkbox]'); if (!inp) return;
        const n = classCounts.get(inp.dataset.key) || 0;
        const c = lbl.querySelector('.count'); if (c) c.textContent = String(n);
        lbl.classList.toggle('facet-unavailable', n === 0 && !inp.checked);
      });
    }
    const appEl = document.getElementById('facet-appellations');
    if (appEl) {
      const except = new Set(['appellations']);
      appEl.querySelectorAll('.region-group').forEach(group => {
        let visible = 0;
        group.querySelectorAll('label').forEach(lbl => {
          const inp = lbl.querySelector('input[type=checkbox]'); if (!inp) return;
          const slug = inp.dataset.key; const rec = AOCS[slug];
          const reachable = rec ? matchesExceptFacets(rec, slug, except) : false;
          const hide = !reachable && !inp.checked;
          lbl.classList.toggle('facet-unavailable', hide);
          if (!hide) visible++;
        });
        (group.parentElement || group).classList.toggle('facet-unavailable', visible === 0);
        const cs = group.querySelector(':scope > summary > .count');
        if (cs) cs.textContent = String(visible);
      });
    }
  }

  // ---- omnisearch ----
  const _REGION_INDEX = FACET_REGIONS.map(([region, count]) => ({
    region, count, label: regionLabel(region), labelN: searchNormalize(regionLabel(region)),
  }));
  // Index the FULL style taxonomy (the 6 buckets + interior groups + distinctive
  // leaves like rancio / vin jaune / fino / oloroso), not just the 6 simple
  // buckets, so detailed styles are findable in the omnisearch. Depth-0 tree
  // nodes ARE the simple buckets (same slugs); deeper nodes are the details.
  const _SIMPLE_STYLE_KEYS = new Set(FACET_STYLES_SIMPLE.map(([b]) => b));
  const _STYLE_INDEX = FACET_STYLES_TREE.map(node => ({
    key: node.slug, count: node.count,
    label: STYLE_LABELS[node.slug] || node.slug,
    labelN: searchNormalize(STYLE_LABELS[node.slug] || node.slug),
    aliasesN: (STYLE_SEARCH_TERMS[node.slug] || []).map(searchNormalize),
  }));
  const _CLASS_INDEX = FACET_CLASS_TREE.map(node => ({
    key: node.slug, count: node.count,
    label: CLASS_LABELS[node.slug] || node.slug,
    labelN: searchNormalize(CLASS_LABELS[node.slug] || node.slug),
    aliasesN: (CLASS_SEARCH_TERMS[node.slug] || []).map(searchNormalize),
  }));

  function rankAllSuggestions(query, perGroup) {
    const nq = searchNormalize(query || '');
    if (!nq) return { appellations: [], grapes: [], regions: [], styles: [], classifications: [] };
    // Search/count grapes against the active scope: when "main grape only" is
    // on, the map filters grapes_principal, so the dropdown surfaces principal-
    // relevant grapes and shows their principal count (was always total count).
    const grapeRole = filters.mainGrapeOnly ? 'principal' : 'all';
    const grapes = rankGrapeSuggestions(query, grapeRole, perGroup).map(s => ({
      type: 'grape', key: s.entry.slug,
      name: toTitleCase(s.matched || s.entry.label),
      sub: (s.matched && s.matched.toLowerCase() !== s.entry.label.toLowerCase()) ? toTitleCase(s.entry.label) : '',
      count: filters.mainGrapeOnly ? (s.entry.count_principal || 0) : s.entry.count,
      score: s.score,
    }));
    const scoreLabel = labelN => labelN.startsWith(nq) ? 100 : (labelN.includes(nq) ? 80 : -1);
    const regions = _REGION_INDEX
      .map(r => ({ r, score: scoreLabel(r.labelN) })).filter(x => x.score >= 0)
      .sort((a, b) => b.score - a.score || b.r.count - a.r.count).slice(0, perGroup)
      .map(x => ({ type: 'region', key: x.r.region, name: x.r.label, sub: '', count: x.r.count, score: x.score }));
    const styles = _STYLE_INDEX
      .map(s => {
        // Best score across the localized label and any synonym (fondillón,
        // eiswein, vinsanto…); record which synonym matched for the sub-label.
        let score = scoreLabel(s.labelN);
        let matched = '';
        for (const a of s.aliasesN) {
          const sc = scoreLabel(a);
          if (sc > score) { score = sc; matched = a; }
        }
        return { s, score, matched };
      }).filter(x => x.score >= 0)
      .sort((a, b) => b.score - a.score || b.s.count - a.s.count).slice(0, perGroup)
      .map(x => ({
        type: 'style', key: x.s.key,
        name: x.matched ? toTitleCase(x.matched) : x.s.label,
        sub: x.matched ? x.s.label : '',
        count: x.s.count, score: x.score,
      }));
    const classifications = _CLASS_INDEX
      .map(s => {
        let score = scoreLabel(s.labelN);
        let matched = '';
        for (const a of s.aliasesN) {
          const sc = scoreLabel(a);
          if (sc > score) { score = sc; matched = a; }
        }
        return { s, score, matched };
      }).filter(x => x.score >= 0)
      .sort((a, b) => b.score - a.score || b.s.count - a.s.count).slice(0, perGroup)
      .map(x => ({
        type: 'classification', key: x.s.key,
        name: x.matched ? toTitleCase(x.matched) : x.s.label,
        sub: x.matched ? x.s.label : '',
        count: x.s.count, score: x.score,
      }));
    const apps = [];
    for (const slug in AOCS) {
      const rec = AOCS[slug];
      if (!showIgp && (rec.kind || 'AOC') === 'IGP') continue;
      if (!spiritsVisible() && rec.is_wine === false) continue;
      const t = searchableText(rec);
      const score = t.startsWith(nq) ? 100 : (t.includes(nq) ? 80 : -1);
      if (score >= 0) apps.push({ slug, rec, score });
    }
    apps.sort((a, b) => b.score - a.score || (a.rec.name || '').localeCompare(b.rec.name || '', 'fr'));
    const appellations = apps.slice(0, perGroup).map(a => ({
      type: 'appellation', key: a.slug, name: a.rec.name,
      sub: a.rec.region ? regionLabel(a.rec.region) : '', count: null, score: a.score,
    }));
    return { appellations, grapes, regions, styles, classifications };
  }

  function pickOmni(type, key) {
    if (type === 'grape') {
      filters.grapesAll.add(key);
      track('Omnisearch Result Picked', { type: 'grape', locale: LANG });
      refreshAllGrapeChipFilters();
      applyFilter({ fit: true });
    } else if (type === 'region') {
      setRegionSelection(key, true);
      // Reflect the new selection in the appellation-tree checkboxes.
      const appEl = document.getElementById('facet-appellations');
      if (appEl) appEl.querySelectorAll('input[type=checkbox]').forEach(inp => {
        if (inp.dataset.key) inp.checked = filters.appellations.has(inp.dataset.key);
      });
      refreshRegionTriStates();
      track('Omnisearch Result Picked', { type: 'region', locale: LANG });
      applyFilter({ fit: true });
    } else if (type === 'style') {
      // Route to the matching surface: the 6 coarse buckets drive the simple
      // chips; detailed taxonomy nodes (rancio, vin jaune, …) drive the advanced
      // style tree. Both render as removable active-filter chips either way.
      if (_SIMPLE_STYLE_KEYS.has(key)) filters.stylesSimple.add(key);
      else filters.styles.add(key);
      refreshSidebarCheckedState();
      track('Omnisearch Result Picked', { type: 'style', locale: LANG });
      applyFilter({ fit: true });
    } else if (type === 'classification') {
      filters.classifications.add(key);
      refreshSidebarCheckedState();
      track('Omnisearch Result Picked', { type: 'classification', locale: LANG });
      applyFilter({ fit: true });
    } else if (type === 'appellation') {
      if (!AOCS[key]) return;
      lastPanelTrigger = document.getElementById('omni');
      lastStackKey = key;
      stackFocusIndex = 0;
      renderPanelStack([key], 0);
      track('Appellation Opened', { slug: key, via: 'omnisearch', locale: LANG });
      const b = (viewMode === 'simple' && AOCS[key].bbox_villages) ? AOCS[key].bbox_villages : AOCS[key].bbox;
      if (b && typeof map.fitBounds === 'function') map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, maxZoom: 11, duration: 500 });
    }
  }

  function buildOmnisearch() {
    const input = document.getElementById('omni');
    const drop = document.getElementById('omni-suggestions');
    if (!input || !drop) return;
    const GROUP_LABELS = {
      appellations: LABELS.facet_appellations_h, grapes: LABELS.facet_grapes_h,
      regions: LABELS.facet_regions_h, styles: LABELS.facet_styles_h,
      classifications: LABELS.facet_classification_h,
    };
    const live = document.getElementById('omni-live');
    // The omnisearch ALSO live-filters the appellation tree below (in addition
    // to the open-panel dropdown), reusing the tree filter + auto-collapse.
    function syncTreeFilter(q) {
      filters.q = q;  // persist across mode/spirits rebuilds (buildAppellationFacet reads it)
      refreshFacetVisibility('facet-appellations', q);
      if (q) {
        const treeEl = document.getElementById('facet-appellations');
        const par = treeEl && treeEl.closest('details');
        if (par && !par.open) par.open = true;
      }
    }
    let items = [];
    let activeIdx = -1;
    let trackTimer = null;

    function setLive(msg) { if (live) live.textContent = msg || ''; }
    function clearActiveDescendant() { input.removeAttribute('aria-activedescendant'); }

    function suggestionHtml(it, idx) {
      const sub = it.sub ? ` <span class="sub">${escapeHtml(it.sub)}</span>` : '';
      const count = (it.count != null) ? `<span class="count">${it.count}</span>` : '';
      return `<div class="suggestion" id="omni-opt-${idx}" role="option" aria-selected="false" data-idx="${idx}" data-type="${escapeAttr(it.type)}" data-key="${escapeAttr(it.key)}"><span class="name">${escapeHtml(it.name)}</span>${sub}${count}</div>`;
    }
    // Build the grouped markup for the given {group: items} map; group headers
    // keep a fixed visual order. Resets `items` to the flattened, index-aligned
    // list the keyboard/mouse handlers walk.
    function paintGroups(groups, order) {
      items = [];
      let html = '';
      for (const g of order) {
        const list = groups[g];
        if (!list || !list.length) continue;
        html += `<div class="omni-group-header">${escapeHtml(GROUP_LABELS[g] || g)}</div>`;
        for (const it of list) { const idx = items.length; items.push(it); html += suggestionHtml(it, idx); }
      }
      return html;
    }
    function showDrop(html) { drop.innerHTML = html; drop.hidden = false; input.setAttribute('aria-expanded', 'true'); }
    function hideDrop() {
      drop.hidden = true; drop.innerHTML = ''; items = []; activeIdx = -1;
      input.setAttribute('aria-expanded', 'false'); clearActiveDescendant();
    }

    // Empty-query state: seed the dropdown with popular grapes / styles /
    // regions so a user can discover the taxonomy without knowing a name
    // (appellations are excluded — there is no meaningful "popular" few).
    function renderSeeds() {
      const role = filters.mainGrapeOnly ? 'principal' : 'all';
      const ck = filters.mainGrapeOnly ? 'count_principal' : 'count';
      // Over-fetch then sort by the active scope's count so "popular grapes"
      // reflects principal usage when "main grape only" is on (the shared index
      // is ordered by total count; re-sorting here keeps the canonical facet,
      // which also uses the empty-query branch, untouched).
      const grapes = rankGrapeSuggestions('', role, 30)
        .sort((a, b) => (b.entry[ck] || 0) - (a.entry[ck] || 0))
        .slice(0, 5)
        .map(s => ({
          type: 'grape', key: s.entry.slug, name: toTitleCase(s.entry.label), sub: '',
          count: s.entry[ck] || 0,
        }));
      const styles = _STYLE_INDEX.slice().sort((a, b) => b.count - a.count).slice(0, 5)
        .map(s => ({ type: 'style', key: s.key, name: s.label, sub: '', count: s.count }));
      const regions = _REGION_INDEX.slice().sort((a, b) => b.count - a.count).slice(0, 5)
        .map(r => ({ type: 'region', key: r.region, name: r.label, sub: '', count: r.count }));
      const html = paintGroups({ grapes, styles, regions }, ['grapes', 'styles', 'regions']);
      if (!items.length) { hideDrop(); return; }
      showDrop(html);
      activeIdx = -1;  // passive: Enter on an empty box does nothing
      clearActiveDescendant();
      setLive('');
    }
    function renderNoResults(q) {
      items = []; activeIdx = -1;
      const msg = fmt(LABELS.omni_no_results, { q });
      showDrop(`<div class="omni-empty">${escapeHtml(msg)}</div>`);
      clearActiveDescendant();
      setLive(msg);
    }
    function renderDrop(q) {
      if (!q) { renderSeeds(); return; }
      const res = rankAllSuggestions(q, 5);
      const html = paintGroups(res, ['appellations', 'grapes', 'regions', 'styles', 'classifications']);
      if (!items.length) { renderNoResults(q); return; }
      showDrop(html);
      // Pre-arm the single highest-scoring row across ALL groups (not always the
      // first appellation), so a stray Enter lands on the best match. Ties keep
      // the earliest, preserving the fixed group order.
      let best = 0;
      for (let i = 1; i < items.length; i++) {
        if ((items[i].score || 0) > (items[best].score || 0)) best = i;
      }
      highlight(best);
      setLive('');
    }
    function highlight(i) {
      const els = drop.querySelectorAll('.suggestion');
      els.forEach((el, k) => {
        const on = k === i;
        el.classList.toggle('active', on);
        el.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      activeIdx = i;
      if (els[i]) { els[i].scrollIntoView({ block: 'nearest' }); input.setAttribute('aria-activedescendant', els[i].id); }
      else clearActiveDescendant();
    }
    function choose(i) {
      const it = items[i];
      if (!it) return;
      const wasAppellation = it.type === 'appellation';
      pickOmni(it.type, it.key);
      input.value = '';
      syncTreeFilter('');  // emptying the box clears the tree filter
      // On mobile, an appellation pick flies the map but the drawer would stay
      // open covering it — close it so the result is visible.
      if (wasAppellation && window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
        const sb = document.getElementById('sidebar'); if (sb) sb.classList.remove('open');
      }
      hideDrop();
      if (!wasAppellation) input.focus();
    }
    drop.addEventListener('mousedown', e => {
      const s = e.target.closest('.suggestion');
      if (!s) return;
      e.preventDefault();
      choose(parseInt(s.dataset.idx, 10));
    });
    drop.addEventListener('mousemove', e => {
      const s = e.target.closest('.suggestion');
      if (s) highlight(parseInt(s.dataset.idx, 10));
    });
    input.addEventListener('input', () => {
      const q = input.value.trim();
      renderDrop(q);
      syncTreeFilter(q);
      if (trackTimer) clearTimeout(trackTimer);
      if (q) trackTimer = setTimeout(() => {
        const r = rankAllSuggestions(q, 5);
        const total = r.appellations.length + r.grapes.length + r.regions.length + r.styles.length;
        track('Omnisearch Used', {
          result_count: String(total),
          had_match: total > 0 ? 'true' : 'false',
          groups: [r.appellations.length && 'a', r.grapes.length && 'g', r.regions.length && 'r', r.styles.length && 's'].filter(Boolean).join(''),
          query_len: String(q.length),
          locale: LANG,
        });
      }, 1000);
    });
    input.addEventListener('focus', () => renderDrop(input.value.trim()));
    input.addEventListener('blur', () => setTimeout(hideDrop, 120));
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (drop.hidden) renderDrop(input.value.trim());
        else if (items.length) highlight((activeIdx + 1) % items.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!drop.hidden && items.length) highlight((activeIdx - 1 + items.length) % items.length);
      } else if (e.key === 'Enter') {
        if (!drop.hidden && activeIdx >= 0) { e.preventDefault(); choose(activeIdx); }
      } else if (e.key === 'Escape') {
        hideDrop();
      }
    });
  }

  buildOmnisearch();
  // Rescope the Grapes facet typeahead/counts to the active grape field so
  // "main grape only" surfaces principal-relevant grapes with principal counts
  // (picks still land in filters.grapesAll).
  function rescopeGrapeFacet() {
    const gc = document.querySelector('.grape-chip-filter[data-role="all"]');
    if (gc) buildGrapeChipFilter(gc, filters.mainGrapeOnly ? 'principal' : 'all', filters.grapesAll);
  }
  const mgoEl = document.getElementById('main-grape-only');
  if (mgoEl) {
    mgoEl.checked = filters.mainGrapeOnly;
    if (filters.mainGrapeOnly) rescopeGrapeFacet();  // reflect a restored toggle on first paint
    mgoEl.addEventListener('change', e => {
      filters.mainGrapeOnly = e.target.checked;
      try { localStorage.setItem('main_grape_only', filters.mainGrapeOnly ? '1' : '0'); } catch (err) {}
      track('Grape Scope Toggled', { scope: filters.mainGrapeOnly ? 'main' : 'all', locale: LANG });
      rescopeGrapeFacet();
      applyFilter({ fit: true });
    });
  }

  // ----- detail panel -----
  const panel = document.getElementById('panel');
  const panelBody = document.getElementById('panel-body');

  function renderSources(slug, sources) {
    if (!sources) sources = {};
    const links = [];
    if (sources.boagri) {
      const homo = sources.homologation_date ? ' — ' + LABELS.src_homologated + ' ' + escapeHtml(sources.homologation_date) : '';
      const jorf = sources.jorf_date ? ', ' + LABELS.src_jorf + ' ' + escapeHtml(sources.jorf_date) : '';
      links.push(`<li><a href="${escapeAttr(sources.boagri)}" target="_blank" rel="noopener">${LABELS.src_cahier}</a>${homo}${jorf}</li>`);
    }
    if (sources.show_texte) {
      links.push(`<li><a href="${escapeAttr(sources.show_texte)}" target="_blank" rel="noopener">${LABELS.src_show_texte}</a></li>`);
    }
    if (sources.product) {
      links.push(`<li><a href="${escapeAttr(sources.product)}" target="_blank" rel="noopener">${LABELS.src_product}</a></li>`);
    }
    if (sources.eur_lex_url) {
      links.push(`<li><a href="${escapeAttr(sources.eur_lex_url)}" target="_blank" rel="noopener">${LABELS.src_eur_lex}</a></li>`);
    }
    if (sources.national_pliego_url) {
      const added = (sources.national_pliego_added_slugs || []).length;
      const note = added ? ' — +' + added + ' ' + LABELS.src_national_pliego_added : '';
      links.push(`<li><a href="${escapeAttr(sources.national_pliego_url)}" target="_blank" rel="noopener">${LABELS.src_national_pliego}</a>${note}</li>`);
    }
    if (sources.national_spec_url) {
      const org = sources.national_spec_source_org ? ' — ' + escapeHtml(sources.national_spec_source_org) : '';
      links.push(`<li><a href="${escapeAttr(sources.national_spec_url)}" target="_blank" rel="noopener">${LABELS.src_national_spec}</a>${org}</li>`);
    }
    if (sources.chzo_spec_url) {
      const reg = sources.chzo_spec_region ? ' — ' + escapeHtml(sources.chzo_spec_region) : '';
      const org = sources.chzo_spec_source_org ? ' (' + escapeHtml(sources.chzo_spec_source_org.toUpperCase()) + ')' : '';
      links.push(`<li><a href="${escapeAttr(sources.chzo_spec_url)}" target="_blank" rel="noopener">${LABELS.src_chzo_spec}</a>${reg}${org}</li>`);
    }
    if (sources.regional_register_url) {
      const reg = sources.regional_register_region ? ' — ' + escapeHtml(sources.regional_register_region) : '';
      links.push(`<li><a href="${escapeAttr(sources.regional_register_url)}" target="_blank" rel="noopener">${LABELS.src_regional_register}</a>${reg}</li>`);
    }
    if (sources.id_eambrosia) {
      const eambrosiaUrl = `https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/${encodeURIComponent(sources.id_eambrosia)}`;
      const fileNum = sources.file_number ? ' — ' + LABELS.src_eambrosia_id + ' ' + escapeHtml(sources.file_number) : '';
      links.push(`<li><a href="${escapeAttr(eambrosiaUrl)}" target="_blank" rel="noopener">${LABELS.src_eambrosia}</a>${fileNum}</li>`);
    }
    if (sources.cantonal_reglement_url) {
      const lab = sources.cantonal_reglement_label ? ' — ' + escapeHtml(sources.cantonal_reglement_label) : '';
      links.push(`<li><a href="${escapeAttr(sources.cantonal_reglement_url)}" target="_blank" rel="noopener">${LABELS.src_cantonal_reglement}</a>${lab}</li>`);
    }
    if (sources.ofag_repertoire_url) {
      links.push(`<li><a href="${escapeAttr(sources.ofag_repertoire_url)}" target="_blank" rel="noopener">${LABELS.src_ofag_repertoire}</a></li>`);
    }
    if (sources.syndicate && sources.syndicate.url) {
      const syLabel = sources.syndicate.label ? ' — ' + escapeHtml(sources.syndicate.label) : '';
      links.push(`<li><a href="${escapeAttr(sources.syndicate.url)}" target="_blank" rel="noopener">${LABELS.src_syndicate}</a>${syLabel}</li>`);
    }
    return '<h2>' + LABELS.panel_sources_h + '</h2><ul class="sources">' + links.join('') + '</ul>';
  }

  function escapeAttr(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function frMarker() {
    return LANG === 'fr'
      ? ''
      : ` <span class="fr-marker" title="${escapeAttr(LABELS.fr_marker_aria)}">${escapeHtml(LABELS.fr_marker)}</span>`;
  }

  function srcMarker(country) {
    const sourceLang = (country === 'es' || country === 'pt') ? country : 'fr';
    if (LANG === sourceLang) return '';
    const text = country === 'es' ? LABELS.es_marker
      : country === 'pt' ? (LABELS.pt_marker || LABELS.fr_marker)
      : LABELS.fr_marker;
    const aria = country === 'es' ? LABELS.es_marker_aria
      : country === 'pt' ? (LABELS.pt_marker_aria || LABELS.fr_marker_aria)
      : LABELS.fr_marker_aria;
    return ` <span class="fr-marker" title="${escapeAttr(aria)}">${escapeHtml(text)}</span>`;
  }

  function translationAttribution(t, country) {
    if (!t) return '';
    const labelText = country === 'es'
      ? LABELS.translation_source_label_es
      : country === 'pt'
      ? (LABELS.translation_source_label_pt || LABELS.translation_source_label)
      : LABELS.translation_source_label;
    const url = t.source_pdf_url;
    const sourceHtml = url
      ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(labelText)}</a>`
      : escapeHtml(labelText);
    const tpl = LABELS.translation_attribution;
    const placeholder = '{source}';
    const idx = tpl.indexOf(placeholder);
    const pre = idx >= 0 ? tpl.slice(0, idx) : (tpl + ' ');
    const post = idx >= 0 ? tpl.slice(idx + placeholder.length) : '';
    return `<p class="translation-attr">${escapeHtml(pre)}${sourceHtml}${escapeHtml(post)}</p>`;
  }

  const FACTS_SUB_ORDER = ['facteurs_naturels', 'facteurs_humains', 'produit', 'interactions'];
  const FACTS_SUB_LABELS = {
    facteurs_naturels: LABELS.facts_sub_facteurs_naturels,
    facteurs_humains: LABELS.facts_sub_facteurs_humains,
    produit: LABELS.facts_sub_produit,
    interactions: LABELS.facts_sub_interactions,
  };

  function buildFactsSourceLabel(country) {
    if (country === 'es') return LABELS.facts_attribution_source_label_es;
    if (country === 'pt') return LABELS.facts_attribution_source_label_pt;
    return LABELS.facts_attribution_source_label;
  }

  function buildFactsAttribution(tplKey, country, cahierUrl) {
    const labelText = buildFactsSourceLabel(country);
    const sourceHtml = cahierUrl
      ? `<a href="${escapeAttr(cahierUrl)}" target="_blank" rel="noopener">${escapeHtml(labelText)}</a>`
      : escapeHtml(labelText);
    const tpl = LABELS[tplKey];
    const placeholder = '{source}';
    const idx = tpl.indexOf(placeholder);
    const pre = idx >= 0 ? tpl.slice(0, idx) : (tpl + ' ');
    const post = idx >= 0 ? tpl.slice(idx + placeholder.length) : '';
    return `<p class="translation-attr">${escapeHtml(pre)}${sourceHtml}${escapeHtml(post)}</p>`;
  }

  function renderVerbatimFacts(r, tf) {
    const text = tf.verbatim_text || '';
    if (!text) return '';
    const cahierUrl = tf.cahier_source_pdf_url || '';
    const flag = tf.validation_flag || '';
    const badge = flag
      ? `<span class="verbatim-badge" title="${escapeAttr(flag)}">${escapeHtml(LABELS.facts_verbatim_to_verify)}</span>`
      : '';
    const body = `<blockquote class="facts-verbatim">${escapeHtml(text)}</blockquote>`;
    const attribution = buildFactsAttribution('facts_verbatim_attribution', r.country, cahierUrl);
    return `<h2>${LABELS.panel_facts_h}${badge ? ' ' + badge : ''}</h2>${body}${attribution}`;
  }

  function renderTerroirFacts(r) {
    const tf = r.terroir_facts;
    if (!tf) return '';
    if (tf.mode === 'verbatim') return renderVerbatimFacts(r, tf);
    if (!tf.facts || !tf.facts.length) return '';
    const wikiUrl = tf.wiki_source_url || '';
    const wikiAttr = wikiUrl
      ? ` <span class="wiki-attr">(<a href="${escapeAttr(wikiUrl)}" target="_blank" rel="noopener">${escapeHtml(LABELS.facts_wiki_marker)}</a>)</span>`
      : ` <span class="wiki-attr">(${escapeHtml(LABELS.facts_wiki_marker)})</span>`;
    const grouped = {};
    for (const f of tf.facts) {
      const k = f.subsection || 'facteurs_naturels';
      (grouped[k] = grouped[k] || []).push(f);
    }
    const blocks = FACTS_SUB_ORDER.flatMap(k => {
      const facts = grouped[k];
      if (!facts || !facts.length) return [];
      const items = facts.map(f => {
        const marker = f.provenance === 'wiki' ? wikiAttr : '';
        return `<li>${escapeHtml(f.bullet)}${marker}</li>`;
      }).join('');
      return [`<div class="facts-sub-h">${escapeHtml(FACTS_SUB_LABELS[k] || k)}</div><ul class="facts">${items}</ul>`];
    });
    if (!blocks.length) return '';
    const attribution = buildFactsAttribution(
      'facts_attribution', r.country, tf.cahier_source_pdf_url || ''
    );
    return `<h2>${LABELS.panel_facts_h}</h2>${blocks.join('')}${attribution}`;
  }

  function renderDulok(r) {
    // HU named single-vineyards (dűlők), grouped by település, in a
    // collapsible block. Names are verbatim regulator data (not
    // translated); the termékleírás source is attributed in Sources.
    const dulok = r.dulok || [];
    if (!dulok.length) return '';
    const groups = {};
    const order = [];
    for (const d of dulok) {
      const tel = d.telepules || '';
      let name = d.dulo || '';
      if (d.aldulok && d.aldulok.length) name += ' (' + d.aldulok.join(', ') + ')';
      if (!(tel in groups)) { groups[tel] = []; order.push(tel); }
      groups[tel].push(name);
    }
    const rows = order.map(tel =>
      `<div class="dulo-row"><span class="dulo-tel">${escapeHtml(tel)}</span> ${
        groups[tel].map(n => escapeHtml(n)).join(', ')}</div>`).join('');
    return `<details class="dulok"><summary>${
      fmt(LABELS.panel_dulok_h, { n: dulok.length })}</summary>${rows}</details>`;
  }

  function renderMenzioni(r) {
    // IT menzioni geografiche aggiuntive (MGA/UGA crus) — a flat,
    // collapsible name-chip list on the parent panel. Verbatim regulator
    // data (not translated); the disciplinare is attributed in Sources.
    // No per-cru polygons: no licence-clear public GIS layer exists.
    const mz = r.menzioni || [];
    if (!mz.length) return '';
    const chips = mz.map(n =>
      `<span class="pill menzione">${escapeHtml(toTitleCase(n))}</span>`).join('');
    return `<details class="dulok menzioni"><summary>${
      fmt(LABELS.panel_menzioni_h, { n: mz.length })}</summary>` +
      `<div class="menzioni-chips">${chips}</div></details>`;
  }

  function renderAocCard(slug, isPrimary) {
    const r = AOCS[slug];
    if (!r) return '';
    const styleChips = (r.styles || []).map(s => {
      const safe = escapeAttr(s);
      const info = STYLES_INFO[s];
      const has = !!(info && info.extract);
      const cls = ['pill', 'style', `style--${safe}`, has ? 'has-info' : ''].filter(Boolean).join(' ');
      const label = toTitleCase(STYLE_LABELS[s] || s);
      if (has && info.page_url) {
        return `<a class="${cls}" data-slug="${safe}" href="${escapeAttr(info.page_url)}" target="_blank" rel="noopener">${label}</a>`;
      }
      // has-info spans (extract but no Wikipedia URL) aren't links, so make
      // them keyboard-focusable to surface the tooltip without a mouse.
      const tab = has ? ' tabindex="0"' : '';
      return `<span class="${cls}" data-slug="${safe}"${tab}>${label}</span>`;
    }).join('');
    const grapePill = (g, cls) => {
      const info = GRAPES_INFO[g];
      const has = !!(info && (info.extract || (info.vivc_id && info.vivc_url) || info.note));
      const cls2 = ['pill', 'grape', cls, has ? 'has-info' : ''].filter(Boolean).join(' ');
      // Title-case both the cahier spelling and the canonical bracket so
      // pills stay consistent regardless of source casing ("mourvèdre" /
      // "MOURVEDRE" → "Mourvèdre").
      const cahierName = toTitleCase((r.grape_names && r.grape_names[g]) || grapeName(g));
      // Prefer VIVC's prime name when resolved; fall back to a Latin
      // transliteration of the cahier spelling for non-Latin scripts
      // (Cyrillic / Greek native varieties that VIVC hasn't catalogued)
      // so pills still surface a readable Latin form alongside the
      // native one. Per-record `grape_names_latin` covers slugs that
      // never make it into GRAPES_INFO (no Wikipedia + no VIVC).
      const canon = (info && info.canonical_name)
        || (info && info.name_latin)
        || (r.grape_names_latin && r.grape_names_latin[g])
        || '';
      const labelInner = canon && !canonicalEqualsCahier(canon, cahierName)
        ? `${escapeHtml(cahierName)} <span class="canon">(${escapeHtml(canon)})</span>`
        : escapeHtml(cahierName);
      return `<a class="${cls2}" data-slug="${escapeAttr(g)}" href="${escapeAttr(grapeUrl(g))}" target="_blank" rel="noopener">${labelInner}</a>`;
    };
    const principal = (r.grapes_principal || []).map(g => grapePill(g, '')).join('');
    const accessory = (r.grapes_accessory || []).map(g => grapePill(g, 'accessory')).join('');
    const observation = (r.grapes_observation || []).map(g => grapePill(g, 'observation')).join('');
    // PT cadernos enumerate every authorised casta as `principal` because
    // the IVV documento-único format doesn't carry a role split (see
    // CLAUDE.md "PT grape role classification — not published by the
    // regulator"). Surface that limitation inline under the principal
    // pills so the rendering is honest about what the regulator publishes.
    const ptRoleDisclaimer = (r.country === 'pt' && principal)
      ? `<div class="role-disclaimer">${escapeHtml(LABELS.pt_role_disclaimer)}</div>`
      : '';
    const klass = isPrimary ? 'aoc-card' : 'aoc-card subordinate';
    let metaTail = '';
    if (r.geom_source === 'aires-csv' || r.geom_source === 'dgc-village-override') {
      metaTail = ' · ' + fmt(LABELS.meta_communes_inao, { n: r.communes_matched || 0 });
    } else if (
      r.geom_source !== 'parcellaire' && r.geom_source !== 'parcellaire-dgc' &&
      r.geom_source !== 'aires-csv-dgc' && r.geom_source !== 'cadastre-lieu-dit-dgc' &&
      r.geom_source !== 'sibling-dgc' && r.geom_source !== 'parent-appellation' &&
      r.communes_matched > 0
    ) {
      metaTail = ' · ' + fmt(LABELS.meta_communes, { n: r.communes_matched });
    }
    const region = r.region ? regionLabel(r.region) : '';
    const regionSeg = region ? ` · ${escapeHtml(region)}` : '';
    const countryChip = countryChipHtml(r.country, r.country_aliases);
    const countrySeg = countryChip ? `${countryChip} · ` : '';
    const dgcLine = r.is_sub_denomination && r.parent_slug
      ? `<div class="dgc-line">${escapeHtml(LABELS.dgc_of)} <a class="parent-link" data-slug="${escapeAttr(r.parent_slug)}" href="#">${escapeHtml(r.parent_name || r.parent_slug)}</a></div>`
      : '';
    let approxLine = '';
    if (r.geom_source === 'sibling-dgc' && r.geom_fallback_slug) {
      const u = `<a class="parent-link" data-slug="${escapeAttr(r.geom_fallback_slug)}" href="#">${escapeHtml(r.geom_fallback_name || r.geom_fallback_slug)}</a>`;
      approxLine = `<div class="approx-line">${fmt(LABELS.geom_approx_within, { umbrella: u })}</div>`;
    } else if (r.geom_source === 'parent-appellation') {
      approxLine = `<div class="approx-line">${escapeHtml(LABELS.geom_approx_parent)}</div>`;
    } else if (r.geom_source === 'aires-csv-dgc') {
      approxLine = `<div class="approx-line">${escapeHtml(LABELS.geom_approx_aires)}</div>`;
    } else if (r.geom_source === 'cadastre-lieu-dit-dgc' && r.cadastre_lieu_dit) {
      const src = `<a href="https://cadastre.data.gouv.fr/" target="_blank" rel="noopener">${escapeHtml(LABELS.geom_approx_cadastre_source_label)}</a>`;
      approxLine = `<div class="approx-line">${fmt(LABELS.geom_approx_cadastre, { lieu_dit: escapeHtml(r.cadastre_lieu_dit), commune: escapeHtml(r.cadastre_commune || ''), source: src })}</div>`;
    }
    const stubLine = r.is_stub
      ? `<div class="approx-line">${fmt(LABELS.stub_message, { doc: '<em>' + escapeHtml(STUB_DOC_NAMES[r.country] || STUB_DOC_NAMES.fr) + '</em>' })} <a class="stub-help" href="${escapeAttr(GITHUB_NEW_ISSUE_URL)}" target="_blank" rel="noopener">${escapeHtml(LABELS.stub_help_label)}</a></div>`
      : '';
    const dulokBlock = renderDulok(r);
    const menzioniBlock = renderMenzioni(r);
    const factsBlock = renderTerroirFacts(r);
    const isTranslated = !!r.summary_translation;
    const summaryMarker = isTranslated ? '' : srcMarker(r.country);
    const summary = (!factsBlock && r.summary)
      ? `<p>${escapeHtml(r.summary)}${summaryMarker}</p>${translationAttribution(r.summary_translation, r.country)}`
      : '';
    // Curated, source-cited cross-border note (e.g. Teran SI/HR). Only a
    // handful of appellations carry one — see _lib/appellation_notes.json.
    const noteBlock = (r.note && r.note.text)
      ? `<div class="appellation-note"><div class="note-text">ⓘ ${escapeHtml(r.note.text)}</div>${
          (r.note.sources && r.note.sources.length)
            ? '<div class="note-srcs">' + r.note.sources.map(s =>
                `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.label)}</a>`).join('') + '</div>'
            : ''
        }</div>`
      : '';
    return `
      <div class="${klass}">
        <h1>${nameWithLatin(r)}</h1>
        <div class="meta">${countrySeg}${r.kind}${regionSeg}${metaTail}</div>
        ${dgcLine}
        ${approxLine}
        ${stubLine}
        ${styleChips ? '<h2>' + LABELS.panel_styles_h + '</h2><div class="pills">' + styleChips + '</div>' : ''}
        ${principal ? '<h2>' + LABELS.facet_principal_h + '</h2><div class="pills">' + principal + '</div>' : ''}
        ${ptRoleDisclaimer}
        ${accessory ? '<h2>' + LABELS.facet_accessory_h + '</h2><div class="pills">' + accessory + '</div>' : ''}
        ${observation ? '<h2>' + LABELS.panel_observation_h + '</h2><div class="pills">' + observation + '</div>' : ''}
        ${factsBlock || summary}
        ${dulokBlock}
        ${menzioniBlock}
        ${noteBlock}
        ${renderSources(slug, r.sources)}
      </div>
    `;
  }

  function bboxArea(b) {
    if (!b || b.length < 4) return Infinity;
    const w = b[2] - b[0], h = b[3] - b[1];
    return w > 0 && h > 0 ? w * h : Infinity;
  }

  function localityRank(slug) {
    // Sort key: bounding-box area of the rendered geometry, mode-aware.
    // Bbox area penalises spread-out multipolygons (parent cuvée
    // covering every premier-cru fragment in a region) so a localised
    // climat outranks a scattered parent even when the parent's total
    // polygon area is smaller.
    const r = AOCS[slug];
    if (!r) return Infinity;
    const primary = viewMode === 'advanced' ? r.bbox : r.bbox_villages;
    const fallback = viewMode === 'advanced' ? r.bbox_villages : r.bbox;
    const a = bboxArea(primary);
    return Number.isFinite(a) ? a : bboxArea(fallback);
  }

  // Tab title for an open appellation — mirrors the server-rendered entity
  // <title> (see _build_entity_meta) so navigating within the SPA and landing
  // on a pre-rendered /<locale>/<slug> page show the same title.
  function docTitleFor(slug) {
    const r = AOCS[slug];
    if (!r) return DEFAULT_TITLE;
    const region = r.region ? regionLabel(r.region) : '';
    const country = COUNTRY_LABELS[r.country] || '';
    const geo = [region, country].filter(Boolean).join(', ');
    const head = [r.kind, geo].filter(Boolean).join(' · ');
    return r.name + (head ? ' — ' + head : '') + ' · Open Wine Map';
  }

  // ---- lazy panel-detail hydration (Phase 3 data-bundle diet) -------------
  // The startup bundle ships only STARTUP_AOCS_FIELDS (see map_template.py);
  // the heavy per-appellation detail (summary, terroir facts, sources, grape
  // display-names, dűlők, menzioni, notes …) loads on first open from
  // /data/d/<locale>/<slug>.json and is merged into AOCS[slug]. A fetch is
  // issued at most once per slug (deduped while in flight); repeat opens are
  // instant. A failed fetch degrades to the startup fields rather than hanging.
  const PANEL_DATA_BASE = '/data/d/' + LANG + '/';
  const _panelFetches = {};
  let panelGen = 0;
  function hydratePanel(slug) {
    const r = AOCS[slug];
    if (!r) return Promise.resolve();
    if (r._hydrated) return Promise.resolve();
    if (_panelFetches[slug]) return _panelFetches[slug];
    const p = fetch(PANEL_DATA_BASE + encodeURIComponent(slug) + '.json')
      .then(resp => resp.ok ? resp.json() : null)
      .then(data => { if (data) Object.assign(r, data); r._hydrated = true; })
      .catch(() => { r._hydrated = true; })
      .then(() => { delete _panelFetches[slug]; });
    _panelFetches[slug] = p;
    return p;
  }
  function ensurePanelData(slugs) { return Promise.all(slugs.map(hydratePanel)); }

  // Skeleton shown for the brief first-open fetch: the real title comes from
  // startup fields (instant), the body shimmers until the detail JSON lands.
  function skeletonCard(slug, isPrimary) {
    const r = AOCS[slug] || {};
    const klass = isPrimary ? 'aoc-card' : 'aoc-card subordinate';
    return `<div class="${klass} aoc-skeleton" aria-busy="true">`
      + `<h1>${nameWithLatin(r)}</h1>`
      + `<div class="meta"><span class="skel skel-meta"></span></div>`
      + `<div class="skel skel-h"></div>`
      + `<div class="skel skel-line"></div><div class="skel skel-line"></div>`
      + `<div class="skel skel-line short"></div>`
      + `</div>`;
  }

  function renderPanelStack(slugs, focusIndex, doTrack) {
    if (!slugs.length) return;
    const sorted = slugs
      .filter(s => AOCS[s])
      .sort((a, b) => localityRank(a) - localityRank(b));
    if (!sorted.length) return;
    const focus = ((((focusIndex | 0) % sorted.length) + sorted.length) % sorted.length);
    const ordered = focus === 0
      ? sorted
      : [sorted[focus], ...sorted.filter((_, i) => i !== focus)];
    let header = '';
    if (sorted.length > 1) {
      const pos = `<span class="stack-pos" title="${escapeAttr(LABELS.stack_cycle_hint)}">${focus + 1} / ${sorted.length}</span>`;
      header = `<div class="stack-header"><span>${fmt(LABELS.stack_header, { n: sorted.length })}</span>${pos}</div>`;
    }
    // A generation token cancels a stale fetch's render when the user opens or
    // cycles to a different stack before this one's detail arrives.
    const myGen = ++panelGen;
    const renderFull = () => {
      panelBody.innerHTML = header + ordered.map((s, i) => renderAocCard(s, i === 0)).join('');
    };
    panel.classList.add('open');
    document.title = docTitleFor(ordered[0]);
    setSelection(ordered.slice(0, 1));
    // Fresh opens only (doTrack !== false): move keyboard focus into the panel
    // (WCAG 2.4.3) and reflect the appellation in the URL so it is shareable.
    // The localStorage restore passes doTrack === false so it neither steals
    // focus nor rewrites the URL on every reload / language switch.
    if (doTrack !== false) {
      setAocPath(ordered[0]);
      if (typeof panel.focus === 'function') panel.focus({ preventScroll: true });
    }
    // Popularity signal: the appellation brought to the front of the stack.
    // doTrack is suppressed for the localStorage restore (fires on every
    // reload / language switch — not a fresh view).
    if (doTrack !== false) {
      const focusSlug = ordered[0];
      const fr = AOCS[focusSlug];
      if (fr) {
        track('Appellation Viewed', {
          slug: focusSlug,
          country: fr.country || '(none)',
          kind: fr.kind || '(none)',
          region: fr.region || '(none)',
          stacked: sorted.length > 1 ? 'true' : 'false',
          locale: LANG,
        });
      }
    }
    // Cached opens render synchronously (no skeleton flash); first opens show
    // the skeleton, fetch the stack's detail, then swap in the full cards.
    if (ordered.every(s => AOCS[s] && AOCS[s]._hydrated)) {
      renderFull();
      return;
    }
    panelBody.innerHTML = header + ordered.map((s, i) => skeletonCard(s, i === 0)).join('');
    ensurePanelData(ordered).then(() => { if (myGen === panelGen) renderFull(); });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // ----- selection highlight + persistence (across reload / language switch) -----
  // Selection is mirrored into both `appellations` (advanced/parcellaire) and
  // `appellations-villages` (simple/commune) sources so the highlight follows
  // the user across mode toggles. setFeatureState calls before map.on('load')
  // throw because the source isn't registered yet — we swallow and re-apply
  // at the end of map.on('load').
  let selectedSlugs = [];
  // The element that opened the panel (a facet "open" button), so focus can
  // return there on close (WCAG 2.4.3). Null for map clicks / in-panel
  // cross-links, which have no sensible DOM element to return focus to.
  let lastPanelTrigger = null;

  // Cycling: clicking on the same overlap rotates focus through the stack.
  // Key is the deduped slug set (order-independent) so the user can wobble
  // a few pixels and still cycle; moving to a different overlap resets.
  let lastStackKey = '';
  let stackFocusIndex = 0;

  function setSelectedState(slug, selected) {
    for (const source of ['appellations', 'appellations-villages']) {
      const opts = { source: source, id: slug };
      if (SOURCE_TYPE === 'pmtiles') opts.sourceLayer = 'appellations';
      try { map.setFeatureState(opts, { selected: selected }); } catch (e) {}
    }
  }

  function setSelection(slugs) {
    for (const s of selectedSlugs) setSelectedState(s, false);
    selectedSlugs = slugs.slice();
    for (const s of selectedSlugs) setSelectedState(s, true);
    try {
      if (selectedSlugs.length) localStorage.setItem('selected_slugs', JSON.stringify(selectedSlugs));
      else localStorage.removeItem('selected_slugs');
    } catch (e) {}
  }

  // Deep-link an appellation as a real path segment: /<lang>/<slug> for every
  // locale, EN included (/en/<slug>) — so one CDN rewrite covers all four. EN's
  // *home* stays at / (HOME_BASE); only its deep-links live under /en/. The slug
  // rides the path; the camera stays in MapLibre's hash, so the two never
  // collide. replaceState keeps it out of the back-button history.
  // Static-host caveat: in-session navigation is pure client-side (no reload),
  // but a fresh load / shared link of /<lang>/<slug> needs the server to serve
  // the locale index for that path — scripts/serve.py locally, a CDN rewrite in
  // prod. A legacy ?aoc= query is still read on load (and upgraded to a path).
  const SLUG_BASE = '/' + LANG + '/';
  const HOME_BASE = (LANG === 'en') ? '/' : SLUG_BASE;
  function slugFromPath() {
    let p = window.location.pathname || '/';
    p = (p.indexOf(SLUG_BASE) === 0) ? p.slice(SLUG_BASE.length) : p.replace(/^\//, '');
    p = p.replace(/\/+$/, '').split('/')[0];
    try { p = decodeURIComponent(p); } catch (e) {}
    return p || null;
  }
  function setAocPath(slug) {
    try {
      const path = slug ? SLUG_BASE + encodeURIComponent(slug) : HOME_BASE;
      history.replaceState(history.state, '', path + window.location.hash);
    } catch (e) {}
  }

  // Single close path: clears selection + stack state + URL param, and returns
  // focus to the panel's trigger when asked (WCAG 2.4.3). Map clicks pass
  // returnFocus=false — the user's intent already moved to the map.
  function closePanel(returnFocus) {
    const wasOpen = panel.classList.contains('open');
    // Bump the generation so an in-flight panel-detail fetch doesn't repaint
    // the body after the panel has been closed.
    panelGen++;
    panel.classList.remove('open');
    document.title = DEFAULT_TITLE;
    setSelection([]);
    lastStackKey = '';
    stackFocusIndex = 0;
    setAocPath(null);
    if (returnFocus && wasOpen) {
      const target = (lastPanelTrigger && document.contains(lastPanelTrigger))
        ? lastPanelTrigger : document.getElementById('q');
      if (target) { try { target.focus(); } catch (e) {} }
    }
    lastPanelTrigger = null;
  }

  // Restore an open detail panel: a shared /<lang>/<slug> path (or a legacy
  // ?aoc= query) wins over the localStorage restore; otherwise reopen whatever
  // was last open. Both run before map.on('load') — the setFeatureState
  // highlight throws are swallowed and re-applied at the end of map.on('load').
  (function () {
    // JS is live, so drop the no-JS / crawler SSR fallback article — the
    // interactive panel below supersedes it. No-op on the homepage (no article).
    var _ssr = document.getElementById('ssr-content');
    if (_ssr) _ssr.remove();
    let urlSlug = slugFromPath();
    if (!(urlSlug && AOCS[urlSlug])) {
      try { const q = new URLSearchParams(window.location.search).get('aoc'); if (q && AOCS[q]) urlSlug = q; } catch (e) {}
    }
    if (urlSlug && AOCS[urlSlug]) {
      lastStackKey = urlSlug;
      stackFocusIndex = 0;
      renderPanelStack([urlSlug], 0);
      // Frame the shared appellation, but only when the link carries no
      // explicit camera hash (respect a co-shared #zoom/lat/lon). Use the
      // page-entry snapshot, not the live hash — maplibre has already written
      // the default camera into location.hash by now.
      if (!INITIAL_CAMERA_HASH) {
        // Mode-aware like fitToFiltered / the facet-open handler: simple mode
        // renders the villages geometry, so frame that extent, not parcellaire.
        const b = (viewMode === 'simple' && AOCS[urlSlug].bbox_villages) ? AOCS[urlSlug].bbox_villages : AOCS[urlSlug].bbox;
        if (b) map.once('load', () => map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 60, maxZoom: 11, duration: 0 }));
      }
      return;
    }
    let saved = null;
    try { saved = localStorage.getItem('selected_slugs'); } catch (e) {}
    if (!saved) return;
    let slugs;
    try { slugs = JSON.parse(saved); } catch (e) { return; }
    if (!Array.isArray(slugs) || !slugs.length) return;
    const valid = slugs.filter(s => AOCS[s]);
    if (!valid.length) return;
    renderPanelStack(valid, 0, false);
  })();

  document.querySelector('#panel .close').addEventListener('click', () => closePanel(true));

  // Esc closes the detail panel and returns focus to its trigger (WCAG 2.1.2).
  // The native About <dialog> owns Esc while open, so defer to it.
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (aboutDialog && aboutDialog.open) return;
    if (panel.classList.contains('open')) { e.stopPropagation(); closePanel(true); }
  });

  // ----- pill tooltip (Wikipedia, CC BY-SA 4.0) — grapes + styles -----
  const grapeTip = document.createElement('div');
  grapeTip.id = 'grape-tooltip';
  grapeTip.setAttribute('role', 'tooltip');
  document.body.appendChild(grapeTip);
  let grapeTipCloseTimer = null;
  // The pill the tooltip currently describes, so a screen reader announces
  // the extract / VIVC id / attribution when a keyboard user focuses a pill.
  let describedPill = null;
  const cancelGrapeTipClose = () => {
    if (grapeTipCloseTimer) { clearTimeout(grapeTipCloseTimer); grapeTipCloseTimer = null; }
  };
  const hideGrapeTip = () => {
    grapeTip.style.display = 'none';
    if (describedPill) { describedPill.removeAttribute('aria-describedby'); describedPill = null; }
  };
  const scheduleGrapeTipClose = () => {
    cancelGrapeTipClose();
    grapeTipCloseTimer = setTimeout(() => { hideGrapeTip(); grapeTipCloseTimer = null; }, 150);
  };
  grapeTip.addEventListener('mouseenter', cancelGrapeTipClose);
  grapeTip.addEventListener('mouseleave', scheduleGrapeTipClose);

  function positionGrapeTip(el) {
    const r = el.getBoundingClientRect();
    const top = (r.bottom + 220 > window.innerHeight) ? (r.top - grapeTip.offsetHeight - 6) : (r.bottom + 6);
    const left = Math.min(Math.max(8, r.left), window.innerWidth - grapeTip.offsetWidth - 8);
    grapeTip.style.top = Math.max(8, top) + 'px';
    grapeTip.style.left = left + 'px';
  }

  function resolvePillInfo(el) {
    if (el.matches('a.pill.grape.has-info')) {
      const info = GRAPES_INFO[el.dataset.slug];
      if (!info) return null;
      if (!info.extract && !(info.vivc_id && info.vivc_url) && !info.note) return null;
      return { info, url: info.page_url || grapeUrl(el.dataset.slug) };
    }
    if (el.matches('.pill.style.has-info')) {
      const info = STYLES_INFO[el.dataset.slug];
      if (!info || !info.extract) return null;
      return { info, url: info.page_url || '' };
    }
    return null;
  }

  const showPillTip = (e) => {
    const el = e.target.closest('a.pill.grape.has-info, .pill.style.has-info');
    if (!el) return;
    const resolved = resolvePillInfo(el);
    if (!resolved) return;
    const { info, url } = resolved;
    const safeUrl = escapeAttr(url);
    const hasExtract = !!info.extract;
    const thumb = (hasExtract && info.thumbnail)
      ? `<img class="thumb" src="${escapeAttr(info.thumbnail)}" alt="" loading="lazy" decoding="async">` : '';
    // Two translation paths now feed the source-block:
    //   1. info.translation — legacy styles path (raw/translations/styles/)
    //   2. info.is_translated — grapes path (raw/translations/grapes/),
    //      with source_lang on the entry itself.
    const tx = info.translation;
    const grapeTranslated = !tx && info.is_translated && info.source_lang;
    let srcBlock = '';
    if (hasExtract) {
      if (tx || grapeTranslated) {
        const srcLang = tx ? tx.source_lang : info.source_lang;
        const srcUrl = (tx ? tx.source_page_url : info.page_url) || url;
        const wikiLabel = LABELS['wiki_lang_' + srcLang]
          || ('Wikipedia ' + (srcLang || '').toUpperCase());
        const wikiLink = srcUrl
          ? `<a href="${escapeAttr(srcUrl)}" target="_blank" rel="noopener">${escapeHtml(wikiLabel)}</a>`
          : escapeHtml(wikiLabel);
        srcBlock = LABELS.tooltip_translated_from.replace('{wiki}', wikiLink);
      } else {
        const srcLink = url
          ? `<a href="${safeUrl}" target="_blank" rel="noopener">Wikipedia</a>`
          : 'Wikipedia';
        srcBlock = `via ${srcLink} · CC BY-SA 4.0${info.thumbnail ? ' · image: Wikimedia Commons' : ''}`;
      }
    }
    if (info.vivc_id && info.vivc_url) {
      const vivcLabel = LABELS.vivc_link_label.replace('{id}', info.vivc_id);
      const vivcLink = `<a href="${escapeAttr(info.vivc_url)}" target="_blank" rel="noopener" title="${escapeAttr(LABELS.vivc_link_title)}">${escapeHtml(vivcLabel)}</a>`;
      srcBlock += srcBlock ? ` · ${vivcLink}` : vivcLink;
    }
    const extPara = hasExtract ? `<p class="ext">${escapeHtml(info.extract)}</p>` : '';
    const notePara = info.note ? `<p class="note">${escapeHtml(info.note)}</p>` : '';
    const srcDiv = srcBlock ? `<div class="src">${srcBlock}</div>` : '';
    grapeTip.innerHTML = thumb + extPara + notePara + srcDiv;
    cancelGrapeTipClose();
    grapeTip.style.display = 'block';
    if (describedPill && describedPill !== el) describedPill.removeAttribute('aria-describedby');
    describedPill = el;
    el.setAttribute('aria-describedby', 'grape-tooltip');
    positionGrapeTip(el);
  };

  const hidePillTip = (e) => {
    if (e.target.closest('a.pill.grape.has-info, .pill.style.has-info')) scheduleGrapeTipClose();
  };
  // Show on hover (mouseover) and on keyboard focus (focusin); hide on the
  // matching mouseout/focusout; Escape dismisses immediately.
  panel.addEventListener('mouseover', showPillTip);
  panel.addEventListener('focusin', showPillTip);
  panel.addEventListener('mouseout', hidePillTip);
  panel.addEventListener('focusout', hidePillTip);
  panel.addEventListener('keydown', e => {
    if (e.key === 'Escape' && grapeTip.style.display === 'block') {
      // Esc dismisses the innermost layer first: kill the tooltip and stop the
      // event so the document-level handler doesn't also close the panel.
      e.stopPropagation();
      cancelGrapeTipClose(); hideGrapeTip();
    }
  });

  panel.addEventListener('click', e => {
    const a = e.target.closest('a.parent-link');
    if (!a) return;
    e.preventDefault();
    const slug = a.dataset.slug;
    if (slug && AOCS[slug]) {
      lastPanelTrigger = null;
      lastStackKey = '';
      stackFocusIndex = 0;
      renderPanelStack([slug]);
    }
  });

  // ----- map interactions -----
  let hoveredSlug = null;

  map.on('load', () => {
__OWM_source_block__
    for (const id of ['appellations-fill', 'appellations-outline',
                      'appellations-fill-villages', 'appellations-outline-villages']) {
      map.on('mousemove', id, e => {
        if (!e.features.length) return;
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features[0];
        const slug = f.properties.slug;
        if (slug !== hoveredSlug) hoveredSlug = slug;
      });
      map.on('mouseleave', id, () => {
        map.getCanvas().style.cursor = '';
        hoveredSlug = null;
      });
    }

    // Single map-level click handler. Per-layer click handlers fired multiple
    // times at boundaries (fill + outline), and the last handler's
    // setSelection won — making the same spot select different things. Hit-
    // testing once at the click point gives one deterministic feature set,
    // and an empty hit becomes "click outside → deselect".
    map.on('click', e => {
      // 4-pixel bbox around the click — vineyard polygons (grand-cru
      // climats, narrow premier-cru slivers) are often sub-pixel thin at
      // typical zoom; a point-only hit-test misses them.
      const r = 4;
      const bbox = [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
      const features = map.queryRenderedFeatures(bbox, {
        layers: ['appellations-fill', 'appellations-fill-villages'],
      });
      if (!features.length) { closePanel(false); return; }
      // Dedupe by slug, and drop DGCs that share another AOC's polygon
      // (geom_source = parent-appellation / sibling-dgc). They're returned
      // because the underlying geometry was inherited, but they have no
      // distinct shape to click on — selecting one gold-outlines the whole
      // parent and clutters the panel stack with siblings nobody pointed at.
      const seen = new Set();
      const slugs = [];
      for (const f of features) {
        const s = f.properties.slug;
        if (!s || seen.has(s)) continue;
        seen.add(s);
        const rec = AOCS[s];
        const src = rec && rec.geom_source;
        if (src === 'parent-appellation' || src === 'sibling-dgc') continue;
        slugs.push(s);
      }
      if (!slugs.length) { closePanel(false); return; }
      const key = slugs.slice().sort().join('|');
      if (key === lastStackKey && slugs.length > 1) {
        stackFocusIndex = (stackFocusIndex + 1) % slugs.length;
      } else {
        lastStackKey = key;
        stackFocusIndex = 0;
      }
      lastPanelTrigger = null;
      renderPanelStack(slugs, stackFocusIndex);
    });

    // Re-apply feature-state for any selection restored from localStorage
    // before sources existed. Safe no-op when nothing is selected.
    for (const s of selectedSlugs) setSelectedState(s, true);

    applyMode();
    applyFilter();
    updateStatus();
  });
