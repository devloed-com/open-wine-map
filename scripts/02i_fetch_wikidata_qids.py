"""Resolve appellation slugs to Wikidata QIDs (stage 02i).

The appellation-level analogue of the VIVC grape resolver (02g). For every
distinct appellation slug across the corpus, resolve a Wikidata QID by two
paths and cache a slug-keyed map that stage 04 joins into each record's
JSON-LD `sameAs` (a Wikidata QID is the single highest-value entity-
reconciliation target for Google's Knowledge Graph and the AI answer engines).

Resolution paths
  1. **P9854 "eAmbrosia ID"** — one SPARQL query yields the whole
     `{EUGI… → QID}` table; we join on each record's `id_eambrosia`
     (present for the eAmbrosia-sourced countries; FR/CH/LU lack it).
  2. **Wikipedia sitelink** — for slugs with a validated Wikipedia article
     (from the 02b/aocs cache, never `missing`) but no P9854 hit, resolve the
     article title → QID via the MediaWiki `pageprops.wikibase_item` API.

Reads:  raw/*/*-extracted/*.json            (slug + id_eambrosia)
        raw/wikipedia/aocs/<lang>/*.json    (validated article titles)
        raw/wikidata/slug_overrides.json    (optional: slug → {qid} / {suppress})
Writes: raw/wikidata/qids-by-slug.json      ({slug: {qid, via, eambrosia_id,
                                              wiki_title, wiki_lang}})
        raw/wikidata/p9854.json             (cached SPARQL table)
        raw/wikidata/manifest.json
        raw/wikidata/slug_overrides.example.json

Re-runnable + incremental: a slug already resolved (QID or recorded-empty) is
kept untouched unless `--refresh` (re-resolve all) or `--only SLUG` (re-resolve
just those). Network failures degrade to "no QID" — the map still renders,
`sameAs` just omits Wikidata.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.wikidata import (  # noqa: E402
    fetch_p9854_table,
    fetch_titles_qids,
    normalize_qid,
    title_from_page,
)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
WIKI_AOCS = RAW / "wikipedia" / "aocs"
OUT_DIR = RAW / "wikidata"
QIDS_BY_SLUG = OUT_DIR / "qids-by-slug.json"
P9854_CACHE = OUT_DIR / "p9854.json"
MANIFEST = OUT_DIR / "manifest.json"
OVERRIDES = OUT_DIR / "slug_overrides.json"
OVERRIDES_TEMPLATE = OUT_DIR / "slug_overrides.example.json"

# Languages whose article we'd rather resolve first (any one resolves the same
# QID; this only orders which API call carries a given slug). EN/FR/ES first
# because their AOC-article coverage is densest.
_LANG_PREF = ["en", "fr", "es", "de", "it", "pt", "nl"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def collect_corpus() -> dict[str, dict]:
    """`{slug: {"id_eambrosia": str, "name": str, "country": str}}` over every
    `raw/*/*-extracted/` directory (glob-discovered, so a new country pipeline
    is picked up automatically). First non-empty `id_eambrosia` per slug wins."""
    out: dict[str, dict] = {}
    for jp in sorted(RAW.glob("*/*-extracted/*.json")):
        if jp.name.startswith("_") or jp.name == "manifest.json":
            continue
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(rec, dict):
            continue
        slug = rec.get("slug")
        if not slug:
            continue
        eid = (rec.get("id_eambrosia") or "").strip()
        entry = out.setdefault(
            slug,
            {"id_eambrosia": "", "name": rec.get("name") or slug,
             "country": rec.get("country") or ""},
        )
        if eid and not entry["id_eambrosia"]:
            entry["id_eambrosia"] = eid
    return out


def collect_wiki_titles() -> dict[str, list[tuple[str, str]]]:
    """`{slug: [(lang, title), …]}` for every validated (non-`missing`)
    Wikipedia article in the 02b/aocs cache, ordered by `_LANG_PREF`."""
    out: dict[str, dict[str, str]] = {}
    if not WIKI_AOCS.exists():
        return {}
    for lang_dir in WIKI_AOCS.iterdir():
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        for jp in lang_dir.glob("*.json"):
            if jp.name == "manifest.json":
                continue
            try:
                rec = json.loads(jp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if rec.get("missing"):
                continue
            title = title_from_page(rec.get("page_title"), rec.get("page_url"))
            slug = rec.get("slug")
            if slug and title:
                out.setdefault(slug, {})[lang] = title
    ordered: dict[str, list[tuple[str, str]]] = {}
    for slug, by_lang in out.items():
        langs = [lg for lg in _LANG_PREF if lg in by_lang]
        langs += [lg for lg in sorted(by_lang) if lg not in _LANG_PREF]
        ordered[slug] = [(lg, by_lang[lg]) for lg in langs]
    return ordered


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def resolve_via_sitelink(
    session, candidates: dict[str, list[tuple[str, str]]]
) -> dict[str, dict]:
    """Resolve `{slug: [(lang, title), …]}` to `{slug: {qid, wiki_lang,
    wiki_title}}` via batched MediaWiki pageprops lookups. Tries each slug's
    preferred title first; unresolved slugs fall through to their next-language
    title on subsequent rounds."""
    resolved: dict[str, dict] = {}
    pending = {s: list(c) for s, c in candidates.items() if c}
    round_no = 0
    while pending:
        round_no += 1
        # one (lang, title) per still-pending slug this round
        by_lang: dict[str, list[tuple[str, str]]] = {}
        for slug, cand in pending.items():
            lang, title = cand[0]
            by_lang.setdefault(lang, []).append((slug, title))
        next_pending: dict[str, list] = {}
        for lang, pairs in by_lang.items():
            for i in range(0, len(pairs), 50):
                chunk = pairs[i:i + 50]
                titles = [t for _, t in chunk]
                try:
                    title_qid = fetch_titles_qids(session, lang, titles)
                except requests.RequestException as e:
                    log(f"  [sitelink] {lang} batch failed: {e}")
                    title_qid = {}
                for slug, title in chunk:
                    qid = title_qid.get(title, "")
                    if qid:
                        resolved[slug] = {"qid": qid, "wiki_lang": lang, "wiki_title": title}
                    elif len(pending[slug]) > 1:
                        next_pending[slug] = pending[slug][1:]  # try next language
        if next_pending == pending:  # no progress
            break
        pending = next_pending
        if round_no > 8:  # safety bound; corpora carry ≤ a few languages
            break
    return resolved


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve appellation slugs to Wikidata QIDs")
    ap.add_argument("--refresh", action="store_true",
                    help="re-resolve every slug (and re-fetch the P9854 table)")
    ap.add_argument("--only", action="append", default=[],
                    help="re-resolve just this slug (repeatable)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_json(QIDS_BY_SLUG, {})
    overrides = load_json(OVERRIDES, {})
    only = set(args.only)

    corpus = collect_corpus()
    wiki = collect_wiki_titles()
    slugs = sorted(set(corpus) | set(wiki))
    log(f"[02i] corpus slugs={len(corpus)} wiki-articles={len(wiki)} union={len(slugs)}")

    def needs_resolution(slug: str) -> bool:
        if args.refresh:
            return True
        if only:
            return slug in only
        return slug not in existing

    todo = [s for s in slugs if needs_resolution(s)]
    log(f"[02i] resolving {len(todo)} slug(s) ({len(slugs) - len(todo)} cached)")

    session = requests.Session()

    # Path 1: P9854 table (cached; one SPARQL query).
    p9854 = load_json(P9854_CACHE, {})
    if args.refresh or not p9854:
        try:
            p9854 = fetch_p9854_table(session)
            P9854_CACHE.write_text(json.dumps(p9854, ensure_ascii=False, indent=2), "utf-8")
            log(f"[02i] P9854 table: {len(p9854)} rows")
        except requests.RequestException as e:
            log(f"[02i] P9854 SPARQL failed ({e}); using cached table ({len(p9854)} rows)")

    # Path 1 join on id_eambrosia; collect the sitelink candidates for the rest.
    results: dict[str, dict] = {}
    sitelink_candidates: dict[str, list[tuple[str, str]]] = {}
    for slug in todo:
        eid = (corpus.get(slug) or {}).get("id_eambrosia", "")
        qid = p9854.get(eid, "") if eid else ""
        if qid:
            results[slug] = {"qid": qid, "via": "p9854", "eambrosia_id": eid,
                             "wiki_title": "", "wiki_lang": ""}
        elif wiki.get(slug):
            sitelink_candidates[slug] = wiki[slug]
        else:
            results[slug] = {"qid": "", "via": "none", "eambrosia_id": eid,
                             "wiki_title": "", "wiki_lang": ""}

    # Path 2: Wikipedia sitelink for the P9854 misses that have an article.
    if sitelink_candidates:
        log(f"[02i] sitelink lookup for {len(sitelink_candidates)} slug(s)…")
        sl = resolve_via_sitelink(session, sitelink_candidates)
        for slug in sitelink_candidates:
            eid = (corpus.get(slug) or {}).get("id_eambrosia", "")
            hit = sl.get(slug)
            if hit:
                results[slug] = {"qid": hit["qid"], "via": "sitelink", "eambrosia_id": eid,
                                 "wiki_title": hit["wiki_title"], "wiki_lang": hit["wiki_lang"]}
            else:
                results[slug] = {"qid": "", "via": "none", "eambrosia_id": eid,
                                 "wiki_title": "", "wiki_lang": ""}

    # Merge resolved entries over the retained cache.
    merged = dict(existing)
    merged.update(results)

    # Curator overrides win last: {slug: {"qid": "Q…"}} pins, {"suppress": true} blanks.
    for slug, ov in (overrides or {}).items():
        if not isinstance(ov, dict):
            continue
        if ov.get("suppress"):
            merged[slug] = {"qid": "", "via": "override-suppress", "eambrosia_id": "",
                            "wiki_title": "", "wiki_lang": ""}
        else:
            qid = normalize_qid(ov.get("qid"))
            if qid:
                merged[slug] = {"qid": qid, "via": "override", "eambrosia_id": "",
                                "wiki_title": "", "wiki_lang": ""}

    merged = {s: merged[s] for s in sorted(merged)}
    QIDS_BY_SLUG.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")

    counts = {"total": len(merged), "with_qid": sum(1 for v in merged.values() if v.get("qid"))}
    for via in ("p9854", "sitelink", "override", "override-suppress", "none"):
        counts[via] = sum(1 for v in merged.values() if v.get("via") == via)
    MANIFEST.write_text(json.dumps({
        "generated_by": "scripts/02i_fetch_wikidata_qids.py",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "p9854_rows": len(p9854),
        "counts": counts,
    }, ensure_ascii=False, indent=2), "utf-8")

    if not OVERRIDES_TEMPLATE.exists():
        OVERRIDES_TEMPLATE.write_text(json.dumps({
            "_help": "Curator pins: slug -> {qid:'Q123', note:'…'} forces a QID; "
                     "slug -> {suppress:true, note:'…'} blanks a wrong auto-match. "
                     "Copy to slug_overrides.json (gitignored) to take effect.",
            "example-slug": {"qid": "Q123456", "note": "why pinned"},
        }, ensure_ascii=False, indent=2), "utf-8")

    log(f"[02i] wrote {QIDS_BY_SLUG.relative_to(ROOT)}: "
        f"{counts['with_qid']}/{counts['total']} with QID "
        f"(p9854={counts['p9854']} sitelink={counts['sitelink']} "
        f"override={counts['override']} none={counts['none']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
