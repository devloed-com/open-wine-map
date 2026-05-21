"""Resolve grape slugs to VIVC variety numbers and snapshot passport pages.

Pipeline stage 02g — a *spike* track. VIVC (Vitis International Variety
Catalogue, https://www.vivc.de/, Julius Kühn-Institut Geilweilerhof) is
the most thorough public grapevine-cultivar reference; the goal here is
to produce, per distinct grape slug in the FR / ES / PT corpora, a
record of the form

    {slug, name, query, vivc_id, prime_name, color, country,
     species, parent1, parent2, synonyms[{name, official_in}],
     resolved_via, fetched_at, source_url}

and a `manifest.json` summarising coverage (exact-match / ambiguous /
miss buckets). Ambiguous slugs are appended to a starter overrides
template at `raw/vivc/slug_overrides.example.json` so the curator can
pin them by VIVC ID manually.

Per CLAUDE.md the licence question is **not yet settled**: VIVC's
disclaimer is silent on data redistribution, so this spike snapshots
HTML under `raw/vivc/` for local audit only — downstream consumers
should ship VIVC IDs + locally-keyed synonym strings until JKI grants
explicit CC-BY-SA permission.

Reads:  raw/inao/cahier-extracted/*.json + raw/es/pliegos-extracted/*.json
        + raw/pt/cadernos-extracted/*.json   (distinct grape slugs)
        raw/vivc/slug_overrides.json         (optional: slug → vivc_id pins)
Writes: raw/vivc/search/<slug>.html          (cached search response)
        raw/vivc/passport/<vivc_id>.html     (cached passport page)
        raw/vivc/by-slug/<slug>.json         (resolved record)
        raw/vivc/manifest.json
        raw/vivc/slug_overrides.example.json (ambiguous-slug curator queue)

Re-runnable: cached HTML + by-slug JSON skipped unless --refresh.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.vivc import (  # noqa: E402
    PASSPORT_URL,
    SEARCH_URL,
    fetch_passport,
    parse_passport,
    parse_search_results,
    pick_best,
    search_cultivarname,
)

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
ES_EXTRACTED = ROOT / "raw" / "es" / "pliegos-extracted"
PT_EXTRACTED = ROOT / "raw" / "pt" / "cadernos-extracted"
IT_EXTRACTED = ROOT / "raw" / "it" / "disciplinari-extracted"
IT_MASAF_EXTRACTED = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"

OUT_DIR = ROOT / "raw" / "vivc"
SEARCH_DIR = OUT_DIR / "search"
PASSPORT_DIR = OUT_DIR / "passport"
BY_SLUG_DIR = OUT_DIR / "by-slug"
MANIFEST = OUT_DIR / "manifest.json"
OVERRIDES = OUT_DIR / "slug_overrides.json"
OVERRIDES_TEMPLATE = OUT_DIR / "slug_overrides.example.json"

UA = (
    "open-wine-map/0.0.1 (+https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)


def _record_files() -> list[Path]:
    out: list[Path] = []
    for d in (EXTRACTED, ES_EXTRACTED, PT_EXTRACTED, IT_EXTRACTED, IT_MASAF_EXTRACTED):
        if not d.exists():
            continue
        out.extend(jp for jp in d.glob("*.json") if not jp.name.startswith("_"))
    return out


def collect_grape_slugs() -> dict[str, str]:
    """Walk FR / ES / PT / IT extracted records, return {slug: display_name}."""
    slugs: dict[str, str] = {}
    for jp in _record_files():
        rec = json.loads(jp.read_text())
        for d in (rec.get("grapes") or {}).get("details") or []:
            s = d.get("slug")
            if s:
                slugs.setdefault(s, d.get("name", s))
    return slugs


_APOSTROPHE_REJOIN_RE = re.compile(r"\b([dlnsDLNS])\s+(\w)", re.UNICODE)
# Trailing 1-2 letter colour markers (B. / N. / G. / Rs. / Rg. / R.) — IT
# disciplinari and ES pliegos pass the colour code through to the `name`
# field. VIVC's cultivarname search rejects them. Anchored at end so we
# don't strip mid-word matches.
_COLOUR_SUFFIX_RE = re.compile(r"\s+(B|N|G|Rs|Rg|R)\.?\s*$", re.IGNORECASE)


def slug_to_query(name: str) -> str:
    """The search query we send to VIVC. Strip parenthesised qualifiers
    ('Alfrocheiro (Tinta-Bastardinha)' → 'Alfrocheiro'), drop dash-suffix
    synonyms ('Cabernet franc N. - Cabernet' → 'Cabernet franc N.'),
    peel off trailing colour-letter markers ('Sangiovese N.' →
    'Sangiovese'), normalise hyphens to spaces (some corpus records
    store the kebab-case slug as the name, e.g. 'cabernet-sauvignon' →
    'cabernet sauvignon'), then re-attach single-letter elision
    particles with an apostrophe so French/Italian apostrophed names
    match their VIVC primes:

        nero-d-avola      → "nero d avola"      → "nero d'avola"
        len-de-l-el       → "len de l el"       → "len de l'el"
        pineau-d-aunis    → "pineau d aunis"    → "pineau d'aunis"
    """
    q = name.split("(")[0].strip()
    # Strip leading country/region prefix ("Italia - X", "Italie - X", etc.)
    # — geographic qualifier in IT disciplinari, not a synonym.
    q = re.sub(r"^(Italia|Italie|Italy)\s+[-–—]\s+", "", q, flags=re.IGNORECASE)
    # Dash with spaces on either side = synonym separator (drop tail);
    # bare hyphen = slug component (kept, normalised to space below).
    q = re.split(r"\s+[-–—]\s+", q, maxsplit=1)[0].strip()
    q = _COLOUR_SUFFIX_RE.sub("", q).strip()
    q = q.replace("-", " ").replace("_", " ")
    q = " ".join(q.split())
    q = _APOSTROPHE_REJOIN_RE.sub(r"\1'\2", q)
    return q or name


def _passport_record(
    slug: str,
    name: str,
    query: str,
    vivc_id: int,
    resolved_via: str,
    passport_html: str,
) -> dict:
    p = parse_passport(passport_html)
    return {
        "slug": slug,
        "name": name,
        "query": query,
        "resolved_via": resolved_via,
        "vivc_id": vivc_id,
        "prime_name": p.prime_name,
        "color": p.color,
        "country": p.country,
        "species": p.species,
        "parent1": p.parent1,
        "parent2": p.parent2,
        "pedigree_confirmed": p.pedigree_confirmed,
        "synonyms": [dataclasses.asdict(s) for s in p.synonyms],
        "source_url": PASSPORT_URL.format(vid=vivc_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_note": (
            "VIVC publishes no explicit data licence; redistribute the IDs "
            "but seek JKI permission before republishing verbatim synonym "
            "strings. Cite: Röckel et al., Vitis International Variety "
            "Catalogue – www.vivc.de"
        ),
    }


def _cached_passport(session: requests.Session, vivc_id: int, refresh: bool) -> str:
    path = PASSPORT_DIR / f"{vivc_id}.html"
    if path.exists() and not refresh:
        return path.read_text()
    html = fetch_passport(session, vivc_id)
    path.write_text(html)
    return html


def _cached_search(
    session: requests.Session, slug: str, query: str, refresh: bool
) -> str:
    path = SEARCH_DIR / f"{slug}.html"
    if path.exists() and not refresh:
        return path.read_text()
    html = search_cultivarname(session, query)
    path.write_text(html)
    return html


def _resolve_one(
    session: requests.Session,
    slug: str,
    name: str,
    overrides: dict[str, int],
    refresh: bool,
    throttle: float,
) -> tuple[dict, str]:
    """Returns (record, bucket) where bucket ∈ {"override","exact-cultivar",
    "exact-prime","ambiguous-cultivar","ambiguous-prime","miss"}."""
    out_path = BY_SLUG_DIR / f"{slug}.json"

    if slug in overrides:
        vivc_id = int(overrides[slug])
        passport_html = _cached_passport(session, vivc_id, refresh)
        rec = _passport_record(slug, name, name, vivc_id, "override", passport_html)
        out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
        time.sleep(throttle)
        return rec, "override"

    query = slug_to_query(name)
    search_html = _cached_search(session, slug, query, refresh)
    rows = parse_search_results(search_html)
    row, status = pick_best(rows, query)
    if row is None:
        # Persist a miss record so audit_grape_coverage can see it.
        rec = {
            "slug": slug,
            "name": name,
            "query": query,
            "resolved_via": status,
            "vivc_id": None,
            "candidates": [
                {
                    "cultivar_name": r.cultivar_name,
                    "prime_name": r.prime_name,
                    "vivc_id": r.vivc_id,
                    "color": r.color,
                    "country": r.country,
                }
                for r in rows
            ],
            "source_url": SEARCH_URL.format(q=query),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
        time.sleep(throttle)
        return rec, status

    passport_html = _cached_passport(session, row.vivc_id, refresh)
    rec = _passport_record(slug, name, query, row.vivc_id, status, passport_html)
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    time.sleep(throttle)
    return rec, status


def _emit_overrides_template(ambiguous: list[dict]) -> None:
    """Write a starter overrides template listing every ambiguous slug + the
    candidate VIVC IDs the curator can choose from. Hand-edit, then save as
    `slug_overrides.json` (which 02g reads on re-run)."""
    payload = {
        "_doc": (
            "Pin ambiguous slugs to a specific VIVC variety number. Copy to "
            "slug_overrides.json (without _example) and edit. Each value is "
            "the integer VIVC ID. Re-run scripts/02g_fetch_vivc.py to apply."
        ),
        "entries": {
            rec["slug"]: {
                "_query": rec["query"],
                "_resolved_via": rec["resolved_via"],
                "_candidates": rec.get("candidates", []),
                "vivc_id": None,
            }
            for rec in sorted(ambiguous, key=lambda r: r["slug"])
        },
    }
    OVERRIDES_TEMPLATE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh", action="store_true", help="re-fetch HTML even if cached"
    )
    ap.add_argument(
        "--throttle",
        type=float,
        default=0.5,
        help="seconds between requests (be polite to JKI: default 0.5s)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="process only the first N slugs (sorted) — useful for smoke tests",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="process only these slugs (overrides --limit)",
    )
    return ap


def _load_overrides() -> tuple[dict[str, int], set[str]]:
    """Returns `(pins, skips)`. A `vivc_id` of `false` pins the slug as
    deliberately absent from VIVC — a curator decision to keep a variety
    distinct that VIVC folds into another prime (e.g. bianchello, which
    VIVC catalogues as a Trebbiano Toscano synonym). Skipped slugs are
    never resolved and any stale by-slug record is removed."""
    if not OVERRIDES.exists():
        return {}, set()
    data = json.loads(OVERRIDES.read_text())
    entries = data.get("entries") if isinstance(data, dict) else None
    out: dict[str, int] = {}
    skip: set[str] = set()
    for slug, v in (entries or {}).items():
        vid = v.get("vivc_id") if isinstance(v, dict) else v
        if vid is False:
            skip.add(slug)
        elif isinstance(vid, int):
            out[slug] = vid
    print(f"[02g] loaded {len(out)} curator pin(s), {len(skip)} skip(s)", file=sys.stderr)
    return out, skip


def _select_slugs(args: argparse.Namespace) -> dict[str, str]:
    slugs = collect_grape_slugs()
    if args.only:
        return {s: slugs.get(s, s) for s in args.only}
    if args.limit:
        return dict(sorted(slugs.items())[: args.limit])
    return slugs


def _run_loop(
    session: requests.Session,
    slugs: dict[str, str],
    overrides: dict[str, int],
    args: argparse.Namespace,
) -> tuple[dict[str, int], list[dict]]:
    buckets: dict[str, int] = {}
    ambiguous: list[dict] = []
    for slug, name in tqdm(sorted(slugs.items()), desc="vivc", leave=False):
        rec: dict = {}
        try:
            rec, bucket = _resolve_one(
                session, slug, name, overrides, args.refresh, args.throttle
            )
        except requests.RequestException as exc:
            print(f"[02g] {slug}: HTTP error {exc!r}", file=sys.stderr)
            bucket = "http-error"
        buckets[bucket] = buckets.get(bucket, 0) + 1
        if bucket in ("ambiguous-cultivar", "ambiguous-prime"):
            ambiguous.append(rec)
    return buckets, ambiguous


def main() -> int:
    args = _build_parser().parse_args()
    if not EXTRACTED.exists():
        print(
            f"error: {EXTRACTED} missing — run scripts/02_extract_cahiers.py first",
            file=sys.stderr,
        )
        return 1

    overrides, skips = _load_overrides()
    slugs = _select_slugs(args)

    for d in (SEARCH_DIR, PASSPORT_DIR, BY_SLUG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    for s in skips & set(slugs):
        slugs.pop(s, None)
        stale = BY_SLUG_DIR / f"{s}.json"
        if stale.exists():
            stale.unlink()
    print(
        f"[02g] {len(slugs)} unique grape slugs to resolve "
        f"({len(skips)} curator-skipped — kept distinct, no VIVC)",
        file=sys.stderr,
    )

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    buckets, ambiguous = _run_loop(session, slugs, overrides, args)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_slugs": len(slugs),
        "source": "https://www.vivc.de/ (Vitis International Variety Catalogue)",
        "maintainer": "Julius Kühn-Institut, Geilweilerhof (JKI)",
        "citation": "Röckel et al. (year): Vitis International Variety Catalogue – www.vivc.de",
        "buckets": dict(sorted(buckets.items())),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[02g] manifest: {MANIFEST.relative_to(ROOT)} buckets={manifest['buckets']}",
        file=sys.stderr,
    )

    if ambiguous:
        _emit_overrides_template(ambiguous)
        print(
            f"[02g] {len(ambiguous)} ambiguous slug(s) — "
            f"curator queue at {OVERRIDES_TEMPLATE.relative_to(ROOT)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
