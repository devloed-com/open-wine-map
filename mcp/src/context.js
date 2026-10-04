// Per-locale query context: /data/mcp/<locale>.json from the site (written
// by stage 04), turned into a query core. Cached per isolate and revalidated
// with its ETag at most every `ttlMs`; a failed refresh keeps serving the copy
// it has, so a CDN hiccup never takes the tools down once they have loaded.
import { createQueryCore } from '../../scripts/_lib/assets/query_core.mjs';

export const LOCALES = ['en', 'fr', 'es', 'nl'];
export const SUPPORTED_FORMATS = [1];

export function coreFromContext(ctx, siteOrigin) {
  if (!SUPPORTED_FORMATS.includes(ctx.format_version)) {
    throw new Error(`unsupported query context format ${ctx.format_version}`);
  }
  return createQueryCore({
    locale: ctx.locale,
    siteOrigin,
    slugBase: `/${ctx.locale}/`,
    aocs: ctx.aocs,
    grapesInfo: ctx.grapes_info,
    grapeSearchIndex: ctx.grape_search_index,
    vivcSiblings: ctx.vivc_siblings,
    styleDescendants: ctx.style_descendants,
    styleLabels: ctx.style_labels,
    simpleStyleLabels: ctx.simple_style_labels,
    simpleStyleBuckets: ctx.simple_style_buckets,
    regionLabels: ctx.region_labels,
    regionSearchTerms: ctx.region_search_terms,
    countryLabels: ctx.country_labels,
    termLabels: ctx.term_labels,
    labels: ctx.labels,
  });
}

export function createContextStore({ dataOrigin, fetchImpl = fetch, ttlMs = 5 * 60 * 1000, now = Date.now }) {
  const entries = new Map(); // locale → { core, aocs, etag, checkedAt, pending }

  async function refresh(locale, entry) {
    const headers = entry?.etag ? { 'If-None-Match': entry.etag } : {};
    const resp = await fetchImpl(`${dataOrigin}/data/mcp/${locale}.json`, { headers });
    if (resp.status === 304 && entry) {
      entry.checkedAt = now();
      return entry;
    }
    if (!resp.ok) throw new Error(`query context ${locale}: HTTP ${resp.status}`);
    const ctx = await resp.json();
    const fresh = { core: coreFromContext(ctx, dataOrigin), aocs: ctx.aocs, etag: resp.headers.get('ETag'), checkedAt: now() };
    entries.set(locale, fresh);
    return fresh;
  }

  // The query core for `locale` (and the raw records, for merging panels).
  async function get(locale) {
    if (!LOCALES.includes(locale)) throw new Error(`unsupported locale ${locale}`);
    const entry = entries.get(locale);
    if (entry && now() - entry.checkedAt < ttlMs) return entry;
    if (entry?.pending) return entry.pending;
    if (!entry) {
      // Deduplicate concurrent cold loads of the same locale.
      const placeholder = { pending: refresh(locale, null) };
      entries.set(locale, placeholder);
      try {
        return await placeholder.pending;
      } catch (e) {
        entries.delete(locale);
        throw e;
      }
    }
    entry.pending = refresh(locale, entry)
      .catch(() => { entry.checkedAt = now(); return entry; })
      .finally(() => { entry.pending = null; });
    return entry.pending;
  }

  return { get };
}
