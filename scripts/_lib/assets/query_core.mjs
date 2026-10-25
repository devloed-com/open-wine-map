// Open Wine Map query core: appellation search, filtering and record shaping,
// shared by the map app and the remote MCP server so the two answer every
// query identically.
//
// - app.js: stage 04 inlines this file at the query_core build token
//   (map_template._render_app_js, with every `export ` removed), and the app
//   calls createQueryCore() with its build-injected tables.
// - mcp/: bundled by esbuild; the server calls createQueryCore() with the same
//   tables, read from wiki/data/mcp/<locale>.json.
//
// Keep it dependency-free and free of window / document: it runs in browsers,
// Deno (Bunny Edge Scripting) and Node (tests).

export class QueryError extends Error {}

// Both sides of every search comparison go through this: diacritics
// stripped, lower-cased, and every run of punctuation or whitespace folded
// to one space, so "aloxe corton" finds Aloxe-Corton and "d alba" finds
// d'Alba (727 records were unfindable by their own full name before the
// fold, 2026-09-25).
export function searchNormalize(s) {
  return (s || '').normalize('NFD').replace(/\p{Diacritic}/gu, '')
    .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

// Title-case the first letter of each word (after start, whitespace,
// hyphen, or apostrophe). Wikipedia grape titles aren't uniformly
// cased (FR uses "Cabernet sauvignon" sentence case while EN uses
// "Cabernet Sauvignon" title case), and the slug fallback is pure
// lowercase — normalising here makes pills and filter entries
// consistent regardless of source.
export function toTitleCase(s) {
  return s.replace(/(?:^|[\s\-'(])\p{L}/gu, c => c.toUpperCase());
}

// A scheme / traditional term as typed ("DOCa", "Vino de Pago", "it:docg")
// → the form class_key segments use ("doca", "vino-de-pago", "it:docg").
export function schemeKey(s) {
  return (s || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
    .replace(/[^\p{L}\p{N}:]+/gu, ' ').trim().replace(/ /g, '-');
}

export function setIntersects(set, arr) {
  if (!arr) return false;
  for (const x of arr) if (set.has(x)) return true;
  return false;
}

const SLUG_PATTERN = '^[a-z0-9-]{1,120}$';
const READ_ONLY = { readOnlyHint: true, idempotentHint: true, openWorldHint: false };

// The tool definitions both surfaces register (WebMCP in the page, MCP on
// the edge). The MCP server adds a `locale` property; the page answers in
// its own locale.
export const TOOL_DEFS = {
  search_appellations: {
    description: 'Find European wine appellations (PDO/PGI, AOC, DOC, DO, …) by name, including romanised forms of Greek and Bulgarian names. Returns slug, official name, country, region, classification and the page URL.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', minLength: 1, maxLength: 200, description: 'Appellation name or part of it, e.g. "Priorat", "Chablis", "naoussa".' },
        country: { type: 'string', pattern: '^[a-z]{2}$', description: 'Optional ISO 3166-1 alpha-2 code, lower-case (fr, es, it, pt, de, at, gr, gb, …).' },
        limit: { type: 'integer', minimum: 1, maximum: 100, description: 'Maximum results (default 20).' },
      },
      required: ['query'],
    },
    annotations: READ_ONLY,
  },
  filter_appellations: {
    description: 'List wine appellations matching structured criteria: country, region, wine style, grape variety, legal scheme or traditional term. All criteria are optional and combined with AND. list_facets returns the accepted values.',
    inputSchema: {
      type: 'object',
      properties: {
        country: { type: 'string', pattern: '^[a-z]{2}$', description: 'ISO 3166-1 alpha-2 code, lower-case.' },
        region: { type: 'string', maxLength: 100, description: 'Wine region as shown on the map, e.g. "Bourgogne", "Catalunya", "Mosel".' },
        style: { type: 'string', maxLength: 100, description: 'Wine style slug or label, e.g. "red", "white", "rose", "sparkling", "sweet", "fortified", "vin-jaune".' },
        grape: { type: 'string', maxLength: 100, description: 'Grape variety name or slug, e.g. "Garnacha", "pinot-noir". Synonyms of the same VIVC variety are included.' },
        main_grape_only: { type: 'boolean', description: 'Only match the grape among the principal varieties (default false).' },
        scheme: { type: 'string', maxLength: 50, description: 'Legal scheme (pdo, pgi, spirit-gi, uk-pdo, uk-pgi, none) or traditional term (aoc, docg, doc, igt, doca, doq, dac, …; "it:doc" to name one country\'s).' },
        include_sub_denominations: { type: 'boolean', description: 'Include sub-denominations (DGCs, subzonas, sottozone, crus); default false.' },
        include_spirits: { type: 'boolean', description: 'Include spirit-drink and cider GIs; default false.' },
        limit: { type: 'integer', minimum: 1, maximum: 200, description: 'Maximum results (default 50).' },
      },
    },
    annotations: READ_ONLY,
  },
  get_appellation: {
    description: 'Full record of one wine appellation by slug: grape varieties (principal / accessory), wine styles, terroir facts with their provenance, source documents and the attribution to give when quoting it.',
    inputSchema: {
      type: 'object',
      properties: { slug: { type: 'string', pattern: SLUG_PATTERN, description: 'Appellation slug, as returned by search_appellations.' } },
      required: ['slug'],
    },
    annotations: READ_ONLY,
  },
  list_facets: {
    description: 'The values filter_appellations accepts, with appellation counts: countries, wine regions, wine styles, and legal schemes / traditional terms. Counts cover wine appellations, not sub-denominations or spirits.',
    inputSchema: { type: 'object', properties: {} },
    annotations: READ_ONLY,
  },
};

const capInt = (v, dflt, max) => Math.max(1, Math.min(max, parseInt(v, 10) || dflt));

// ctx: { locale, siteOrigin, slugBase, aocs, grapesInfo, grapeSearchIndex,
//        vivcSiblings, styleDescendants, styleLabels, simpleStyleLabels,
//        simpleStyleBuckets, regionLabels, regionSearchTerms, countryLabels,
//        termLabels, labels }
export function createQueryCore(ctx) {
  const aocs = ctx.aocs;
  const labels = ctx.labels || {};
  const collator = new Intl.Collator(ctx.locale);
  const byName = (x, y) => collator.compare(aocs[x].name || x, aocs[y].name || y);

  // The forms a record can be found by: the regulator's own name, the EU /
  // official Latin transcription (`name_latin`, the bracket on screen) and
  // the search-only `search_forms` stage 04 derives from the name (ELOT 743
  // and unidecode for Greek, unidecode for Bulgarian — _lib/romanise.py).
  // Derived forms are never displayed: what is on screen stays the
  // regulator's string; they only make "agio oros" or "targovishte" match.
  // Each form is matched on its own, so a query never spans two forms.
  function searchForms(rec) {
    if (!rec) return [];
    if (!rec._sf) {
      const raw = [rec.name || '', rec.name_latin || ''].concat(rec.search_forms || []);
      const seen = new Set();
      rec._sf = [];
      for (const f of raw.map(searchNormalize)) {
        if (f && !seen.has(f)) { seen.add(f); rec._sf.push(f); }
      }
    }
    return rec._sf;
  }

  // Best match of a normalised query against a record's forms: prefix 100,
  // substring 80, no match -1.
  function searchScore(rec, nq) {
    let best = -1;
    for (const f of searchForms(rec)) {
      const s = f.startsWith(nq) ? 100 : (f.includes(nq) ? 80 : -1);
      if (s > best) best = s;
    }
    return best;
  }

  // The tree row's data-name: the forms joined by a newline, which no
  // normalised query contains, so a substring test on it is a per-form test.
  function searchableText(rec) {
    return searchForms(rec).join('\n');
  }

  function regionSearchForms(region) {
    const t = (ctx.regionSearchTerms || {})[region];
    return t ? t.forms : [];
  }

  // A grape set → itself plus every slug sharing its VIVC variety.
  function expandGrapeSet(set) {
    if (!set || !set.size) return set;
    const out = new Set(set);
    for (const slug of set) {
      const sibs = (ctx.vivcSiblings || {})[slug];
      if (sibs) for (const s of sibs) out.add(s);
    }
    return out;
  }

  function grapeName(slug) {
    const info = (ctx.grapesInfo || {})[slug];
    const raw = (info && info.name) ? info.name : slug.replace(/-/g, ' ');
    return toTitleCase(raw);
  }

  // Every region a record is listed under: its own and, for one spanning
  // several (Garda, Cava, the umbrella PGIs), its `region_aliases`.
  function regionsOf(r) {
    return [r.region, ...(r.region_aliases || [])].filter(Boolean);
  }

  function regionLabel(region) {
    if (!region) return labels.meta_no_region;
    return (ctx.regionLabels || {})[region] || region;
  }

  function countryLabel(cc) {
    return (ctx.countryLabels || {})[cc] || cc || '';
  }

  const factsSubLabels = {
    facteurs_naturels: labels.facts_sub_facteurs_naturels,
    facteurs_humains: labels.facts_sub_facteurs_humains,
    produit: labels.facts_sub_produit,
    interactions: labels.facts_sub_interactions,
  };

  const grapeIndexNorm = (ctx.grapeSearchIndex || []).map(entry => ({
    entry,
    labelN: searchNormalize(entry.label),
    aliasesN: (entry.aliases || []).map(a => searchNormalize(a)),
  }));

  function pageUrl(slug) {
    return ctx.siteOrigin + ctx.slugBase + encodeURIComponent(slug);
  }

  function brief(slug) {
    const r = aocs[slug];
    const out = {
      slug,
      name: r.name,
      country: r.country || 'fr',
      country_name: countryLabel(r.country || 'fr'),
      region: r.region ? regionLabel(r.region) : null,
      classification: r.class_label || r.kind || null,
      url: pageUrl(slug),
    };
    if (r.name_latin) out.name_latin = r.name_latin;
    if (r.is_sub_denomination) out.is_sub_denomination = true;
    if (r.is_wine === false) out.is_wine = false;
    if (r.cancelled) out.cancelled = r.cancelled;
    if (r.promoted) out.promoted = r.promoted;
    return out;
  }

  // A grape given by name or slug → every slug of its VIVC variety.
  function grapeSlugsFor(q) {
    const nq = searchNormalize(q);
    if (!nq) return null;
    const hits = new Set();
    for (const e of grapeIndexNorm) {
      if (searchNormalize(e.entry.slug) === nq || e.labelN === nq || e.aliasesN.includes(nq)) hits.add(e.entry.slug);
    }
    if (!hits.size) for (const slug in (ctx.grapesInfo || {})) {
      const info = ctx.grapesInfo[slug] || {};
      if (searchNormalize(slug) === nq || searchNormalize(info.name) === nq) hits.add(slug);
    }
    if (!hits.size) for (const k in aocs) {
      for (const s of aocs[k].grapes_all || []) if (searchNormalize(s) === nq) hits.add(s);
    }
    return hits.size ? expandGrapeSet(hits) : new Set();
  }

  // A style given by slug or by its label in this locale → the style and
  // every style under it in the taxonomy.
  function styleSlugsFor(q) {
    const nq = searchNormalize(q);
    if (!nq) return null;
    const desc = ctx.styleDescendants || {};
    const lab = ctx.styleLabels || {};
    const simpleLab = ctx.simpleStyleLabels || {};
    const buckets = ctx.simpleStyleBuckets || {};
    const keys = new Set(Object.keys(desc).concat(Object.keys(lab), Object.keys(buckets)));
    for (const s of keys) {
      if (searchNormalize(s) === nq || searchNormalize(lab[s]) === nq || searchNormalize(simpleLab[s]) === nq) {
        return new Set([s].concat(desc[s] || [], buckets[s] || []));
      }
    }
    return new Set();
  }

  function inCountry(r, cc) {
    return (r.country || 'fr') === cc || (r.country_aliases || []).includes(cc);
  }

  // A grape given by name or slug → the canonical search-index slug the map's
  // grape filter keys on (expandGrapeSet widens it to the VIVC siblings at
  // predicate time), or null. Exact matches only, label before alias.
  function grapeKeyFor(q) {
    const nq = searchNormalize(q);
    if (!nq) return null;
    for (const e of grapeIndexNorm) {
      if (searchNormalize(e.entry.slug) === nq || e.labelN === nq) return e.entry.slug;
    }
    for (const e of grapeIndexNorm) if (e.aliasesN.includes(nq)) return e.entry.slug;
    for (const slug in (ctx.grapesInfo || {})) {
      const info = ctx.grapesInfo[slug] || {};
      if (searchNormalize(slug) === nq || searchNormalize(info.name) === nq) return slug;
    }
    return null;
  }

  // A style given by slug or by its label in this locale → the taxonomy node
  // the style filter keys on, or null.
  function styleKeyFor(q) {
    const nq = searchNormalize(q);
    if (!nq) return null;
    const desc = ctx.styleDescendants || {};
    const lab = ctx.styleLabels || {};
    const simpleLab = ctx.simpleStyleLabels || {};
    const buckets = ctx.simpleStyleBuckets || {};
    const keys = new Set(Object.keys(desc).concat(Object.keys(lab), Object.keys(buckets)));
    for (const s of keys) if (searchNormalize(s) === nq) return s;
    for (const s of keys) if (searchNormalize(lab[s]) === nq || searchNormalize(simpleLab[s]) === nq) return s;
    return null;
  }

  // A region given by its raw key, its label in this locale or a search form
  // → every (country, raw region) pair carrying it; `cc` narrows to one
  // country (a cross-border record answers to each country it spans).
  function regionKeyFor(q, cc) {
    const nq = searchNormalize(q);
    if (!nq) return [];
    const seen = new Set();
    const out = [];
    for (const slug in aocs) {
      const r = aocs[slug];
      const region = r.region || '';
      if (!region) continue;
      if (cc && !inCountry(r, cc)) continue;
      const country = cc || r.country || 'fr';
      const key = country + ':' + region;
      if (seen.has(key)) continue;
      seen.add(key);
      if (searchNormalize(region) === nq || searchNormalize(regionLabel(region)) === nq
          || regionSearchForms(region).some(f => searchNormalize(f) === nq)) out.push({ country, region });
    }
    return out;
  }

  // ---- The view in the URL -------------------------------------------------
  // A map view is shareable because the address bar carries it: the query
  // string names the filters (grape / main / style / class / type), the tree
  // selection (country / region / sel), a shared set (aocs — the MCP server's
  // show_on_map links one), the scheme gates when they differ from the
  // defaults (pdo=0 / pgi=1 / spirits=1), and the embed flags (embed=1,
  // theme=dark), and the area to frame on load (bbox=w,s,e,n in degrees —
  // what the share dialog writes into an embed URL in place of the camera
  // hash, so an iframe of another size fits the same area). Values are
  // comma-separated and may repeat the key; a grape or style may be given by
  // name ("Sankt Laurent") or slug, a region as "<cc>:<raw key>" or by its
  // label. The camera itself stays in the hash.
  // viewFromQuery reads one (unknown values are listed, never guessed);
  // queryFromView writes one, omitting every default so a plain view has no
  // query at all.
  const VIEW_KEYS = ['grape', 'main', 'style', 'class', 'type', 'country', 'region', 'sel', 'aocs', 'pdo', 'pgi', 'spirits', 'embed', 'theme', 'bbox'];
  const SHARE_KEYS = ['grape', 'main', 'style', 'class', 'type', 'country', 'region', 'sel', 'pdo', 'pgi', 'spirits', 'embed'];

  function viewFromQuery(search) {
    const raw = typeof search === 'string' ? search.replace(/^\?/, '') : '';
    const params = new URLSearchParams(raw);
    const list = key => {
      const out = [];
      for (const v of params.getAll(key)) for (const piece of v.split(',')) {
        const t = piece.trim();
        if (t && !out.includes(t)) out.push(t);
      }
      return out;
    };
    const flag = key => {
      if (!params.has(key)) return null;
      const v = (params.get(key) || '').trim().toLowerCase();
      return v === '1' || v === 'true' || v === 'on' || v === 'yes';
    };
    const push = (arr, v) => { if (v && !arr.includes(v)) arr.push(v); };
    const view = {
      grapes: [], mainGrapeOnly: false, styles: [], classifications: [], types: [],
      countries: [], regions: [], appellations: [], set: [],
      gates: { pdo: null, pgi: null, spirits: null }, embed: false, theme: null, bbox: null,
      unknown: [], shared: false,
    };
    for (const g of list('grape')) { const k = grapeKeyFor(g); if (k) push(view.grapes, k); else view.unknown.push('grape:' + g); }
    view.mainGrapeOnly = flag('main') === true && view.grapes.length > 0;
    for (const s of list('style')) { const k = styleKeyFor(s); if (k) push(view.styles, k); else view.unknown.push('style:' + s); }
    // Classification and appellation-type keys are the map's own facet
    // tables, which the context does not carry: passed through as given, the
    // app drops what its tables do not know.
    for (const c of list('class')) push(view.classifications, c);
    for (const t of list('type')) push(view.types, t);
    for (const c of list('country')) {
      const cc = c.toLowerCase();
      if ((ctx.countryLabels || {})[cc]) push(view.countries, cc); else view.unknown.push('country:' + c);
    }
    for (const r of list('region')) {
      const m = /^([a-z]{2}):(.+)$/i.exec(r);
      const hits = regionKeyFor(m ? m[2] : r, m ? m[1].toLowerCase() : '');
      if (!hits.length) view.unknown.push('region:' + r);
      for (const h of hits) if (!view.regions.some(x => x.country === h.country && x.region === h.region)) view.regions.push(h);
    }
    for (const s of list('sel')) { if (aocs[s]) push(view.appellations, s); else view.unknown.push('sel:' + s); }
    for (const s of list('aocs')) { if (aocs[s]) push(view.set, s); else view.unknown.push('aocs:' + s); }
    view.set = view.set.slice(0, 200);
    view.gates.pdo = flag('pdo');
    view.gates.pgi = flag('pgi');
    view.gates.spirits = flag('spirits');
    view.embed = flag('embed') === true;
    const theme = (params.get('theme') || '').trim().toLowerCase();
    view.theme = (theme === 'dark' || theme === 'light') ? theme : null;
    if (params.has('bbox')) {
      const b = (params.get('bbox') || '').split(',').map(Number);
      const ok = b.length === 4 && b.every(Number.isFinite)
        && b[0] >= -180 && b[2] <= 180 && b[1] >= -90 && b[3] <= 90 && b[0] < b[2] && b[1] < b[3];
      if (ok) view.bbox = b; else view.unknown.push('bbox:' + params.get('bbox'));
    }
    // A URL that carries a view is the same for everyone: the app then reads
    // the gates from it (absent = the default) instead of this browser's
    // saved preference. A plain ?aocs= set keeps the pre-existing behaviour.
    view.shared = SHARE_KEYS.some(k => params.has(k));
    return view;
  }

  function queryFromView(view) {
    const v = view || {};
    const enc = x => encodeURIComponent(String(x)).replace(/%3A/gi, ':').replace(/%20/g, '+');
    const parts = [];
    const add = (key, values) => {
      const vals = (values || []).filter(x => x !== null && x !== undefined && String(x) !== '');
      if (vals.length) parts.push(key + '=' + vals.map(enc).join(','));
    };
    add('grape', v.grapes);
    if (v.mainGrapeOnly && v.grapes && v.grapes.length) parts.push('main=1');
    add('style', v.styles);
    add('class', v.classifications);
    add('type', v.types);
    add('country', v.countries);
    add('region', (v.regions || []).map(r => r.country + ':' + r.region));
    add('sel', v.appellations);
    add('aocs', v.set);
    const g = v.gates || {};
    if (g.pdo === false) parts.push('pdo=0');
    if (g.pgi === true) parts.push('pgi=1');
    if (g.spirits === true) parts.push('spirits=1');
    if (v.embed) parts.push('embed=1');
    if (v.embed && v.theme === 'dark') parts.push('theme=dark');
    if (v.bbox && v.bbox.length === 4) parts.push('bbox=' + v.bbox.map(x => Number(x).toFixed(4)).join(','));
    return parts.join('&');
  }

  function search({ query, country, limit } = {}) {
    const nq = searchNormalize(query);
    if (!nq) throw new QueryError('query is empty');
    const cc = (country || '').toLowerCase();
    const hits = [];
    for (const slug in aocs) {
      const r = aocs[slug];
      if (cc && !inCountry(r, cc)) continue;
      const score = searchScore(r, nq);
      if (score < 0) continue;
      hits.push({ slug, score, sub: r.is_sub_denomination ? 1 : 0, name: r.name || slug });
    }
    hits.sort((a, b) => b.score - a.score || a.sub - b.sub || collator.compare(a.name, b.name));
    const n = capInt(limit, 20, 100);
    return { total: hits.length, results: hits.slice(0, n).map(h => brief(h.slug)) };
  }

  function filter(a = {}) {
    const cc = (a.country || '').toLowerCase();
    // A criterion that was given but normalises to nothing ("!!") is an
    // error, never silently dropped from the AND.
    const nRegion = searchNormalize(a.region);
    if (a.region && !nRegion) throw new QueryError('unknown region: ' + a.region);
    const styles = a.style ? styleSlugsFor(a.style) : null;
    if (a.style && !(styles && styles.size)) throw new QueryError('unknown style: ' + a.style);
    const grapes = a.grape ? grapeSlugsFor(a.grape) : null;
    if (a.grape && !(grapes && grapes.size)) throw new QueryError('unknown grape: ' + a.grape);
    // class_key segments are 'pdo' or '<cc>:<term>' ('it:docg',
    // 'es:vino-de-pago'): fold case, accents and spaces, keep the ':'.
    const term = schemeKey(a.scheme);
    if (a.scheme && !term) throw new QueryError('unknown scheme: ' + a.scheme);
    const out = [];
    for (const slug in aocs) {
      const r = aocs[slug];
      if (!a.include_sub_denominations && r.is_sub_denomination) continue;
      if (!a.include_spirits && r.is_wine === false) continue;
      if (cc && !inCountry(r, cc)) continue;
      if (nRegion && !regionsOf(r).some(reg => searchNormalize(reg) === nRegion
          || searchNormalize(regionLabel(reg)) === nRegion
          || regionSearchForms(reg).some(f => searchNormalize(f) === nRegion))) continue;
      if (styles && !setIntersects(styles, r.styles || [])) continue;
      if (grapes && !setIntersects(grapes, (a.main_grape_only ? r.grapes_principal : r.grapes_all) || [])) continue;
      if (term) {
        const segs = (r.class_key || '').split(';').filter(Boolean);
        if (!segs.some(s => s === term || s.split(':').pop() === term)) continue;
      }
      out.push(slug);
    }
    out.sort(byName);
    const n = capInt(a.limit, 50, 200);
    return { total: out.length, results: out.slice(0, n).map(brief) };
  }

  // The full record. `rec` is the startup record merged with its panel
  // payload (the app hydrates AOCS in place; the server merges a copy);
  // `complete` is false when the panel payload could not be loaded.
  function full(slug, rec = aocs[slug], complete = true) {
    if (!aocs[slug]) throw new QueryError('unknown appellation slug: ' + slug);
    const r = rec;
    const out = brief(slug);
    if (!complete) {
      out.detail_unavailable = 'The detail data (terroir facts, sources, attribution) could not be loaded; '
        + 'this record is partial. Call get_appellation again to retry.';
    }
    if (r.parent_slug && aocs[r.parent_slug]) out.parent = brief(r.parent_slug);
    out.styles = (r.styles || []).map(s => (ctx.styleLabels || {})[s] || s);
    out.grapes = {
      principal: (r.grapes_principal || []).map(grapeName),
      accessory: (r.grapes_accessory || []).map(grapeName),
    };
    const tf = r.terroir_facts;
    if (tf && tf.facts && tf.facts.length) {
      out.terroir_facts = tf.facts.map(f => ({
        text: f.bullet,
        section: factsSubLabels[f.subsection] || f.subsection,
        source: f.provenance === 'wiki' ? 'wikipedia' : 'specification',
      }));
      out.terroir_facts_attribution = {
        specification_url: tf.cahier_source_pdf_url || null,
        wikipedia_url: tf.wiki_source_url || null,
        wikipedia_licence: tf.facts.some(f => f.provenance === 'wiki') ? 'CC BY-SA 4.0' : null,
        note: 'Extracted from the regulator specification (and Wikipedia where marked), machine-translated outside the source language.',
      };
    } else if (r.summary) {
      out.summary = r.summary;
      if (r.summary_translation) out.summary_note = 'Machine translated from the regulator specification.';
    }
    const src = {};
    for (const [k, v] of Object.entries(r.sources || {})) {
      if (typeof v === 'string' && /^https?:\/\//.test(v)) src[k] = v;
    }
    if ((r.sources || {}).file_number) out.eu_file_number = r.sources.file_number;
    out.sources = src;
    if (r.note) out.note = r.note;
    out.geometry_source = r.geom_source || null;
    return out;
  }

  // The values filter() accepts, counted over wine appellations (no
  // sub-denominations, no spirits), each list sorted by count then label.
  function facets() {
    const countries = new Map();
    const regions = new Map();
    const styles = new Map();
    const schemes = new Map();
    const bump = (m, key, init) => {
      const e = m.get(key) || Object.assign({ count: 0 }, init());
      e.count += 1;
      m.set(key, e);
    };
    for (const slug in aocs) {
      const r = aocs[slug];
      if (r.is_sub_denomination || r.is_wine === false) continue;
      const cc = r.country || 'fr';
      bump(countries, cc, () => ({ code: cc, name: countryLabel(cc) }));
      for (const reg of regionsOf(r)) bump(regions, reg, () => ({ value: regionLabel(reg), country: cc }));
      for (const s of r.styles || []) bump(styles, s, () => ({ value: s, label: (ctx.styleLabels || {})[s] || s }));
      for (const seg of (r.class_key || '').split(';').filter(Boolean)) {
        bump(schemes, seg, () => ({ value: seg, label: (ctx.termLabels || {})[seg] || seg }));
      }
    }
    const order = (key) => (x, y) => y.count - x.count || collator.compare(x[key], y[key]);
    return {
      countries: [...countries.values()].sort(order('name')),
      regions: [...regions.values()].sort(order('value')),
      styles: [...styles.values()].sort(order('label')),
      schemes: [...schemes.values()].sort(order('label')),
    };
  }

  return {
    searchForms, searchScore, searchableText, regionSearchForms, expandGrapeSet,
    grapeName, regionLabel, countryLabel, brief, search, filter, full, facets,
    grapeKeyFor, styleKeyFor, regionKeyFor, viewFromQuery, queryFromView, VIEW_KEYS,
  };
}
