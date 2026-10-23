#!/usr/bin/env python3
"""Source freshness — is every source a card cites still the newest the
publisher has? The `/validate-sources` validator (docs/plan-validators.md § 1).

Reads the built site (the EN startup bundle and every panel payload's
`sources` block — exactly what the card cites, no stage-04 import) and
probes each source by tier (`scripts/_lib/freshness/`):

  eu         the eAmbrosia register, diffed per country (new / gone /
             modified / new publication / amendment in progress); EUR-Lex
             URLs are COVERED by it (WAF)
  national   INAO's datasets on data.gouv.fr; INAO's product pages (`--inao`,
             ~1 s per record, scope it); GOV.UK; every national-spec
             document by HEAD (`--deep`: re-fetch and compare sha256)
  regional   regional registers, cantonal règlements, Galician parishes,
             Italian geoportal overrides — HEAD / sha like the national tier
  trade      the interprofession / consorzio sites: liveness only, never read
  geometry   GISCO LAU / NUTS, swisstopo releases; Bétard is a SNAPSHOT;
             layers with no release listing are UNVERIFIABLE (named)
  reference  Wikipedia revisions of the cached appellation pages (`--reference`)

`--counts` is the VERIFICATION.md reconciliation made repeatable: our
record count and file-number set per country against the live register
(and GOV.UK for the UK).

Output: `tmp/validation/sources-<stamp>.{json,md}` with every probe and its
recipe; `--curator-md PATH` writes the NEWER-UPSTREAM / GONE rows as
CURATOR_TODO rows grouped by country. Probe answers are cached for a day
under raw/cache/freshness/ (`--refresh` ignores the cache). Read-only.

    .venv/bin/python scripts/audit_source_freshness.py                       # corpus-level + per-record HEADs (eu, national, geometry)
    .venv/bin/python scripts/audit_source_freshness.py --country fr --inao --only pauillac --only margaux
    .venv/bin/python scripts/audit_source_freshness.py --tiers eu,geometry --counts
    .venv/bin/python scripts/audit_source_freshness.py --country gr --deep --max-requests 400
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import card_packet  # noqa: E402
from _lib.freshness import (  # noqa: E402  # noqa: E402
    COVERED,
    CURRENT,
    GONE,
    IN_OPPOSITION,
    NEWER,
    RELINKED,
    UNREACHABLE,
    UNVERIFIABLE,
    VERDICTS,
    Cache,
    Http,
    Probe,
    datagouv,
    eambrosia,
    generic,
    govuk,
    inao,
    layers,
    log,
    wikipedia,
)

REPORT_DIR = ROOT / "tmp" / "validation"
ALL_TIERS = ("eu", "national", "regional", "trade", "geometry", "reference")
DEFAULT_TIERS = ("eu", "national", "geometry")

# A card's source key → (tier, held-sha key, held-bytes key). Keys not listed
# (filename, sha, dates, counts, lists) are not URLs and are skipped.
SOURCE_KEYS: dict[str, tuple[str, str, str]] = {
    "boagri": ("national", "pdf_sha256", ""), "show_texte": ("national", "", ""), "product": ("national", "", ""),
    "eu_register_cahier": ("eu", "", ""), "eur_lex_url": ("eu", "", ""), "eu_oj_publication_url": ("eu", "", ""),
    "national_pliego_url": ("national", "national_pliego_sha256", ""),
    "national_spec_url": ("national", "national_spec_sha256", "national_spec_bytes"),
    "national_spec_fetch_url": ("national", "", ""),
    "specifikacija_url": ("national", "specifikacija_sha256", ""), "specifikacija_final_url": ("national", "specifikacija_sha256", ""),
    "ble_produktspezifikation_url": ("national", "ble_produktspezifikation_sha256", ""),
    "masaf_override_url": ("national", "masaf_sha256", ""), "regional_register_url": ("regional", "", ""),
    "register_fiche_url": ("eu", "", ""), "chzo_spec_url": ("national", "chzo_spec_sha256", ""),
    "ivv_caderno_url": ("national", "pdf_sha256", ""), "area_act_url": ("national", "area_act_sha256", ""),
    "cahier_url": ("national", "pdf_sha256", ""), "gov_uk_register_url": ("national", "", ""),
    "gov_uk_spec_url": ("national", "pdf_sha256", ""),
    "ofag_repertoire_url": ("national", "ofag_repertoire_sha256", ""), "cantonal_reglement_url": ("regional", "cantonal_reglement_sha256", ""),
    "cantonal_roster_url": ("regional", "", ""), "parroquias_url": ("regional", "", ""), "parroquias_licence_url": ("regional", "", ""),
    "syndicate": ("trade", "", ""),
}
# Corpus-level probes answer these per-record keys (INAO walks product pages
# only with --inao; GOV.UK's content API answers the two UK keys).
CORPUS_COVERED = {"show_texte", "product", "gov_uk_register_url", "gov_uk_spec_url"}


def _url(v) -> str:
    if isinstance(v, str) and v.startswith("http"):
        return v
    if isinstance(v, dict) and isinstance(v.get("url"), str) and v["url"].startswith("http"):
        return v["url"]
    return ""


def record_sources(locale: str, slug: str) -> dict:
    payload = card_packet.load_payload(locale, slug) or {}
    return payload.get("sources") or {}


def select(aocs: dict, *, countries, only, sample, seed, parents_only: bool) -> list[str]:
    slugs = [s for s, r in aocs.items()
             if (not countries or r.get("country") in set(countries))
             and (not only or s in set(only))
             and (not parents_only or not r.get("is_sub_denomination"))]
    if sample and len(slugs) > sample:
        random.Random(seed).shuffle(slugs)
        slugs = sorted(slugs[:sample])
    return sorted(slugs)


def per_record_probes(http: Http, aocs: dict, slugs: list[str], *, tiers: set[str], deep: bool,
                      walk_inao: bool, locale: str) -> dict[str, list[Probe]]:
    out: dict[str, list[Probe]] = defaultdict(list)
    seen_urls: dict[str, Probe] = {}
    for slug in slugs:
        rec = aocs[slug]
        cc = rec.get("country") or ""
        srcs = record_sources(locale, slug)
        fetched_at = srcs.get("fetched_at") or ""
        for key, v in srcs.items():
            spec = SOURCE_KEYS.get(key)
            url = _url(v)
            if not spec or not url:
                continue
            tier, sha_key, bytes_key = spec
            if tier not in tiers:
                continue
            if key in CORPUS_COVERED and not (key in ("show_texte", "product") and walk_inao):
                continue
            if key == "product" and walk_inao:
                continue
            if key == "show_texte" and walk_inao:
                p = inao.probe_record(http, product_url=_url(srcs.get("product")), show_texte_url=url,
                                      held_date_text=srcs.get("homologation_date") or srcs.get("jorf_date") or "",
                                      id_appellation=str(srcs.get("id_appellation") or ""), name=rec.get("name") or slug)
                out[slug].append(p)
                continue
            if url in seen_urls:
                p = Probe(**{**seen_urls[url].as_dict()})
                out[slug].append(p)
                continue
            if key in ("eur_lex_url", "eu_oj_publication_url") and "ec.europa.eu/geographical-indications-register" not in url:
                p = eambrosia.eurlex_covered(url, cc, slug)
            else:
                fa = srcs.get(f"{key.replace('_url', '')}_fetched_at") or fetched_at
                p = generic.probe_url(http, tier=tier, source_key=key, url=url, country=cc, slug=slug,
                                      fetched_at=fa, held_sha256=str(srcs.get(sha_key) or "") if sha_key else "",
                                      held_bytes=str(srcs.get(bytes_key) or "") if bytes_key else "", deep=deep)
            seen_urls[url] = p
            out[slug].append(p)
    return out


def _held_file_numbers(cc: str, aocs: dict) -> tuple[set[str], dict[str, str]]:
    """The EU file numbers the corpus holds for a country, and name per number:
    the eAmbrosia index, or for France the register binding of stage 01d and
    for the UK the GOV.UK index."""
    names: dict[str, str] = {}
    if cc == "fr":
        p = ROOT / "raw" / "inao" / "register" / "resolved.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for v in (d.values() if isinstance(d, dict) else d):
                if isinstance(v, dict) and v.get("file_number"):
                    names[v["file_number"]] = v.get("register_name") or v.get("name") or ""
        return set(names), names
    if cc == "gb":
        p = ROOT / "raw" / "gb" / "gov-uk" / "index.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for r in (d.get("wines") if isinstance(d, dict) else d) or []:
                if r.get("file_number"):
                    names[r["file_number"]] = r.get("name") or ""
        return set(names), names
    idx, _ = eambrosia.country_index(cc)
    for r in idx:
        names[r["fileNumber"]] = r.get("name") or ""
    return set(names), names


def counts_table(http: Http, aocs: dict) -> list[dict]:
    rows = eambrosia.live_rows(http)
    if isinstance(rows, str):
        return [{"country": "*", "error": rows}]
    live = eambrosia.wine_rows_by_country(rows)
    cancelled: dict[str, str] = {}
    cp = ROOT / "scripts" / "_lib" / "cancelled_gis.json"
    if cp.exists():
        for slug, e in json.loads(cp.read_text(encoding="utf-8")).items():
            if isinstance(e, dict) and e.get("file_number"):
                cancelled[e["file_number"]] = slug
    out = []
    n_parents: Counter = Counter()
    n_all: Counter = Counter()
    for slug, r in aocs.items():
        n_all[r["country"]] += 1
        if not r.get("is_sub_denomination") and r.get("is_wine") is not False:
            n_parents[r["country"]] += 1
    for cc in sorted(n_all):
        fns, names = _held_file_numbers(cc, aocs)
        held_names = {eambrosia._norm(n) for n in names.values() if n} | {eambrosia._norm(r.get("name") or "") for r in aocs.values() if r["country"] == cc}
        lv = {fn: row for fn, row in live.get(eambrosia.CC_TO_LIVE.get(cc, cc.upper()), {}).items()
              if (row.get("status") or "").lower() == "registered" and not row.get("removedFlag")}
        missing = []
        for fn in sorted(set(lv) - fns):
            row = lv[fn]
            if eambrosia.CROSS_BORDER_OWNER.get(fn, cc) != cc:
                continue
            if any(eambrosia._norm(n) in held_names for n in row.get("protectedNames") or []):
                continue
            missing.append(f"{fn} {', '.join(row.get('protectedNames') or [])}")
        gone = [f"{fn}{' (cancelled: ' + cancelled[fn] + ')' if fn in cancelled else ''}" for fn in sorted(fns - set(lv))]
        out.append({"country": cc, "records": n_all[cc], "records_parents": n_parents[cc], "index_file_numbers": len(fns),
                    "live_registered_wine_gis": len(lv), "live_not_in_index": missing[:12], "index_not_live": gone[:12],
                    "note": {"fr": "spine INAO; file numbers from raw/inao/register/resolved.json", "ch": "outside the EU scheme",
                             "gb": "spine GOV.UK; file numbers from the UK index"}.get(cc, "")})
    return out


def summarize(corpus: list[Probe], per_record: dict[str, list[Probe]]) -> dict:
    by_verdict: Counter = Counter()
    by_tier_verdict: dict[str, Counter] = defaultdict(Counter)
    for p in corpus:
        by_verdict[p.verdict] += 1
        by_tier_verdict[p.tier][p.verdict] += 1
    rec_verdicts: Counter = Counter()
    for slug, ps in per_record.items():
        for p in ps:
            by_verdict[p.verdict] += 1
            by_tier_verdict[p.tier][p.verdict] += 1
        worst = next((v for v in (GONE, NEWER, IN_OPPOSITION, RELINKED, UNREACHABLE, UNVERIFIABLE, COVERED, CURRENT)
                      if any(p.verdict == v for p in ps)), "NONE")
        rec_verdicts[worst] += 1
    return {"probes": sum(by_verdict.values()), "by_verdict": dict(by_verdict),
            "by_tier": {t: dict(c) for t, c in sorted(by_tier_verdict.items())},
            "records": len(per_record), "records_by_worst_verdict": dict(rec_verdicts)}


def markdown(summary: dict, corpus: list[Probe], per_record: dict[str, list[Probe]], aocs: dict,
             counts: list[dict] | None, *, title: str) -> str:
    cell = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
    out = [f"# {title}", "", f"Probes: {summary['probes']} · records: {summary['records']}", "",
           "| verdict | probes |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in sorted(summary["by_verdict"].items(), key=lambda kv: -kv[1])]
    out += ["", "## Corpus-level (registers and layers)", "",
            "| tier | source | verdict | held | upstream | reason |", "|---|---|---|---|---|---|"]
    for p in sorted(corpus, key=lambda p: (p.tier, VERDICTS.index(p.verdict) if p.verdict in VERDICTS else 9)):
        if p.verdict == CURRENT and p.source_key.startswith("eambrosia"):
            continue
        out.append(f"| {p.tier} | {cell(p.source_key)} | **{p.verdict}** | {cell(p.held)} | {cell(p.upstream)} | {cell(p.reason)} |")
    eam = [p for p in corpus if p.source_key.startswith("eambrosia")]
    if eam:
        c = Counter(p.verdict for p in eam)
        out += ["", f"eAmbrosia per-GI rows: {dict(c)} (CURRENT rows omitted above)."]
    actionable = [(s, p) for s, ps in per_record.items() for p in ps if p.verdict in (NEWER, GONE, IN_OPPOSITION, RELINKED)]
    out += ["", f"## Per-record findings ({len(actionable)})", "",
            "| slug | country | tier | source | verdict | held | upstream | reason | recipe |", "|---|---|---|---|---|---|---|---|---|"]
    for s, p in sorted(actionable, key=lambda sp: (aocs[sp[0]].get("country"), sp[0])):
        out.append(f"| `{s}` | {aocs[s].get('country')} | {p.tier} | {cell(p.source_key)} | **{p.verdict}** | {cell(p.held)} | {cell(p.upstream)} | {cell(p.reason)} | {cell(p.recipe)} |")
    unreachable = Counter((p.source_key, p.reason) for ps in per_record.values() for p in ps if p.verdict == UNREACHABLE)
    if unreachable:
        out += ["", "## Unreachable (per source key)", ""] + [f"- {k}: {v} × — {r}" for (k, r), v in unreachable.most_common(20)]
    if counts:
        out += ["", "## Counts against the live register", "",
                "| country | records (parents) | held file numbers | live registered wine GIs | live not held | held not live | note |",
                "|---|---:|---:|---:|---|---|---|"]
        for c in counts:
            if c.get("error"):
                out.append(f"| * | | | | {cell(c['error'])} | | |")
                continue
            out.append(f"| {c['country']} | {c['records']} ({c['records_parents']}) | {c['index_file_numbers']} | {c['live_registered_wine_gis']} | "
                       f"{cell(', '.join(c['live_not_in_index']))} | {cell(', '.join(c['index_not_live']))} | {cell(c['note'])} |")
    return "\n".join(out) + "\n"


def curator_rows(corpus: list[Probe], per_record: dict[str, list[Probe]], aocs: dict) -> str:
    cell = lambda s: str(s or "").replace("|", "\\|")  # noqa: E731
    by_cc: dict[str, list[str]] = defaultdict(list)
    for p in corpus:
        if p.verdict in (NEWER, GONE):
            by_cc["corpus"].append(f"| ❌ | {cell(p.source_key)} | {p.verdict} | {cell(p.held)} → {cell(p.upstream)} | {cell(p.reason)} | {cell(p.recipe)} |")
    for s, ps in per_record.items():
        for p in ps:
            if p.verdict in (NEWER, GONE, IN_OPPOSITION):
                by_cc[aocs[s].get("country") or "?"].append(
                    f"| ❌ | `{s}` · {cell(p.source_key)} | {p.verdict} | {cell(p.held)} → {cell(p.upstream)} | {cell(p.reason)} | {cell(p.recipe)} |")
    out = []
    for cc in sorted(by_cc):
        out += [f"### {cc.upper()} — validate-sources findings ({datetime.now(timezone.utc).date()})", "",
                "| | source | verdict | held → upstream | reason | recipe |", "|---|---|---|---|---|---|"] + by_cc[cc] + [""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiers", default=",".join(DEFAULT_TIERS), help=f"comma list of {', '.join(ALL_TIERS)}")
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--sample", type=int, default=0, help="probe a random sample of records (0 = all in scope)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--parents-only", action="store_true", default=True)
    ap.add_argument("--with-children", action="store_false", dest="parents_only")
    ap.add_argument("--deep", action="store_true", help="re-fetch documents and compare sha256 with the held one")
    ap.add_argument("--inao", action="store_true", help="walk INAO product pages for the FR scope (~1 s per record)")
    ap.add_argument("--reference", action="store_true", help="also probe Wikipedia revisions for the scope")
    ap.add_argument("--counts", action="store_true", help="append the per-country reconciliation against the live register")
    ap.add_argument("--no-record-probes", action="store_true", help="corpus-level probes only")
    ap.add_argument("--max-requests", type=int, default=1500)
    ap.add_argument("--refresh", action="store_true", help="ignore the one-day probe cache")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--report", default=None)
    ap.add_argument("--md", default=None)
    ap.add_argument("--curator-md", default=None)
    ap.add_argument("--strict", action="store_true", help="exit 1 when a GONE or NEWER-UPSTREAM verdict is found")
    args = ap.parse_args()

    tiers = {t.strip() for t in args.tiers.split(",") if t.strip()}
    bad = tiers - set(ALL_TIERS)
    if bad:
        sys.exit(f"unknown tier(s): {sorted(bad)}")
    if args.reference:
        tiers.add("reference")
    aocs, _ = card_packet.load_startup(args.locale)
    if not aocs:
        sys.exit("no built site — run scripts/04_build_maps.py first")
    http = Http(Cache(refresh=args.refresh), max_requests=args.max_requests)
    slugs = select(aocs, countries=args.country, only=args.only, sample=args.sample, seed=args.seed,
                   parents_only=args.parents_only)
    countries = sorted({aocs[s]["country"] for s in slugs})
    log(f"scope: {len(slugs)} records, countries {countries}, tiers {sorted(tiers)}")

    corpus: list[Probe] = []
    live_by_cc = None
    if "eu" in tiers:
        rows = eambrosia.live_rows(http)
        if isinstance(rows, str):
            corpus.append(eambrosia.unreachable(rows))
        else:
            live_by_cc = eambrosia.wine_rows_by_country(rows)
            for cc in countries:
                corpus.extend(eambrosia.probe_country(cc, live_by_cc))
            log(f"eAmbrosia: {Counter(p.verdict for p in corpus if p.source_key.startswith('eambrosia'))}")
    if "national" in tiers:
        if "fr" in countries:
            corpus += datagouv.probe(http)
        if "gb" in countries:
            corpus += govuk.probe(http)
    if "geometry" in tiers:
        corpus += layers.probe(http)

    per_record: dict[str, list[Probe]] = {}
    if not args.no_record_probes:
        per_record = per_record_probes(http, aocs, slugs, tiers=tiers, deep=args.deep,
                                       walk_inao=args.inao, locale=args.locale)
    if "reference" in tiers:
        by_lang: dict[str, set[str]] = defaultdict(set)
        for s in slugs:
            payload = card_packet.load_payload(args.locale, s) or {}
            lang = payload.get("source_lang") or card_packet.WIKI_LANG_BY_COUNTRY.get(aocs[s]["country"]) or aocs[s]["country"]
            by_lang[lang].add(s)
        for lang, ss in sorted(by_lang.items()):
            for p in wikipedia.probe(http, kind="aocs", lang=lang, slugs=ss):
                slug = next((s for s in ss if p.url.endswith("/" + s) or s in p.recipe.split("--only ")[-1]), None)
                per_record.setdefault(slug or f"wikipedia/{lang}", []).append(p)

    counts = counts_table(http, aocs) if args.counts else None
    summary = summarize(corpus, per_record)
    summary.update({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tiers": sorted(tiers),
                    "countries": countries, "requests": http.n_requests, "dead_hosts": http.dead, "deep": args.deep, "inao": args.inao})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    report = Path(args.report) if args.report else REPORT_DIR / f"sources-{stamp}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "corpus": [p.as_dict() for p in corpus],
                                  "records": {s: [p.as_dict() for p in ps] for s, ps in per_record.items()},
                                  "counts": counts}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = Path(args.md) if args.md else report.with_suffix(".md")
    md.write_text(markdown(summary, corpus, per_record, aocs, counts, title=f"validate-sources — {stamp}"), encoding="utf-8")
    if args.curator_md:
        Path(args.curator_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.curator_md).write_text(curator_rows(corpus, per_record, aocs), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    log(f"report → {report}\nmarkdown → {md}")
    if args.strict and (summary["by_verdict"].get(NEWER) or summary["by_verdict"].get(GONE)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
