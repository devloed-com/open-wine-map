"""Fetch Wikipedia FR pages for AOCs in the corpus, for use as a salience
hint in stage 02d (terroir-fact extraction).

Sister stage to 02b_fetch_grape_lexicon.py. Same Wikipedia + CC-BY-SA-4.0
attribution model. Per CLAUDE.md the cahier text remains INAO/JORF-only;
Wikipedia is admitted as a bounded secondary source for grape-variety
descriptions (existing) and now AOC pages (this stage), each cached entry
records `revision`, `fetched_at`, `page_url`, `license` so downstream
stages and the UI can attribute correctly.

Reads:  raw/inao/cahier-extracted/*.json  (collects non-DGC AOCs)
Writes: raw/wikipedia/aocs/fr/<slug>.json
        raw/wikipedia/aocs/manifest.json

Per cache file:
  - On hit: lead_extract (REST summary), sections (Action API parse),
    full_text (TextExtracts plaintext), revision, fetched_at, page_url,
    license, page_title.
  - On miss: {missing: true, fetched_at, attempted_titles}.
  - On disambiguation / wrong-topic: {error: "...", rejected_title,
    fetched_at}.

DGCs are skipped — they inherit the parent appellation's Wikipedia page
in stage 02d. (Most DGCs do not have their own Wikipedia entry.)

Re-runnable: cached entries are kept; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
OUT_DIR = ROOT / "raw" / "wikipedia" / "aocs" / "fr"
MANIFEST = ROOT / "raw" / "wikipedia" / "aocs" / "manifest.json"
LANG = "fr"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)
REST_URL = "https://fr.wikipedia.org/api/rest_v1/page/summary/{title}"
ACTION_URL = "https://fr.wikipedia.org/w/api.php"

AOC_KEYWORDS = (
    "appellation", "vin", "vignoble", "viticole", "cépage", "cépages",
    "aoc", "aop", "igp", "vendange", "vendanges", "raisin",
)


def looks_like_aoc(data: dict) -> bool:
    blob = ((data.get("description") or "") + " " + (data.get("extract") or "")).lower()
    return any(k in blob for k in AOC_KEYWORDS)


def slug_to_title(slug: str, name: str) -> str:
    """Prefer the cahier's display name (preserves diacritics + capitalisation
    that the slug strips)."""
    return name or " ".join(p.capitalize() for p in slug.split("-"))


def _resolve_kind(rec: dict) -> str:
    """AOC / AOP / IGP / "" — drives the Wikipedia disambiguation suffix."""
    kind = (rec.get("kind") or "").upper()
    if kind:
        return kind
    sigs = (rec.get("signe_fr") or "") + " " + (rec.get("signe_ue") or "")
    if "IGP" in sigs:
        return "IGP"
    if "AOC" in sigs or "AOP" in sigs:
        return "AOC"
    return ""


def collect_aoc_targets() -> list[tuple[str, str, str]]:
    """Scan extracted cahiers, return [(slug, name, kind)] for non-DGC
    appellations."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_") or not jp.is_file():
            continue
        rec = json.loads(jp.read_text())
        if rec.get("is_dgc"):
            continue
        slug = rec.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append((slug, rec.get("name") or slug, _resolve_kind(rec)))
    return out


def fetch_summary(session: requests.Session, title: str) -> tuple[dict | None, int]:
    url = REST_URL.format(title=title.replace(" ", "_"))
    try:
        r = session.get(url, timeout=30)
    except requests.RequestException:
        return None, 0
    if r.status_code == 200:
        try:
            data = r.json()
        except ValueError:
            return None, r.status_code
        if data.get("type") not in ("disambiguation", "no-extract"):
            return data, r.status_code
        return None, r.status_code
    return None, r.status_code


def fetch_sections(session: requests.Session, title: str) -> list[str]:
    try:
        r = session.get(
            ACTION_URL,
            params={
                "action": "parse",
                "page": title,
                "prop": "sections",
                "format": "json",
                "redirects": 1,
            },
            timeout=30,
        )
        r.raise_for_status()
    except requests.RequestException:
        return []
    data = r.json()
    return [s["line"] for s in (data.get("parse") or {}).get("sections", [])]


def fetch_full_text(session: requests.Session, title: str) -> str:
    try:
        r = session.get(
            ACTION_URL,
            params={
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exsectionformat": "plain",
                "titles": title,
                "format": "json",
                "redirects": 1,
            },
            timeout=30,
        )
        r.raise_for_status()
    except requests.RequestException:
        return ""
    pages = r.json().get("query", {}).get("pages", {})
    if not pages:
        return ""
    return next(iter(pages.values()), {}).get("extract", "") or ""


def _sentence_case(s: str) -> str:
    """Lower-case everything after the first hyphen segment.
    Wikipedia FR uses sentence case for compound wine page titles
    (e.g. `Alpes-de-haute-provence (IGP)`, not `Alpes-de-Haute-Provence`)."""
    parts = s.split("-")
    if len(parts) <= 1:
        return s
    return parts[0] + "-" + "-".join(p.lower() for p in parts[1:])


def _candidate_titles(base: str, kind: str) -> list[str]:
    """Wikipedia disambiguates wine appellations as `(AOC)` or `(IGP)`.
    Try sentence-case variants too — REST does not follow case redirects on
    multi-segment compound titles. Bare title is the last fallback."""
    primary = "IGP" if kind == "IGP" else "AOC"
    secondary = "AOC" if primary == "IGP" else "IGP"
    sc = _sentence_case(base)
    cands = [
        f"{base} ({primary})",
        f"{sc} ({primary})",
        f"{base} ({secondary})",
        f"{sc} ({secondary})",
        base,
        sc,
    ]
    seen: set[str] = set()
    return [t for t in cands if not (t in seen or seen.add(t))]


def opensearch_aoc_title(session: requests.Session, base: str, kind: str) -> str | None:
    """Fall-through: ask Wikipedia FR's opensearch for matching titles, return
    the first result that contains an AOC/IGP-style suffix or wine vocabulary."""
    suffix = "IGP" if kind == "IGP" else "AOC"
    try:
        r = session.get(
            ACTION_URL,
            params={
                "action": "opensearch",
                "search": f"{base} {suffix}",
                "limit": 5,
                "format": "json",
                "namespace": 0,
            },
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException:
        return None
    titles = r.json()[1] if isinstance(r.json(), list) and len(r.json()) >= 2 else []
    for t in titles:
        low = t.lower()
        if "(aoc)" in low or "(igp)" in low or "(aop)" in low:
            return t
    return titles[0] if titles else None


def _record_from(slug: str, title: str, data: dict, session: requests.Session) -> dict:
    sections = fetch_sections(session, title)
    full_text = fetch_full_text(session, title)
    return {
        "slug": slug,
        "lang": LANG,
        "page_title": data.get("title") or title,
        "page_url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
        "revision": data.get("revision"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": "CC-BY-SA-4.0",
        "lead_extract": data.get("extract", ""),
        "description": data.get("description", ""),
        "sections": sections,
        "full_text": full_text,
    }


def _try_candidates(
    session: requests.Session, slug: str, titles: list[str]
) -> tuple[dict | None, str | None]:
    """Probe each title via the REST summary; on the first wine-topic hit
    enrich and return the record. Otherwise return (None, last_rejected_title)."""
    last_rejected: str | None = None
    for title in titles:
        data, _ = fetch_summary(session, title)
        if data is None:
            continue
        if looks_like_aoc(data):
            return _record_from(slug, title, data, session), None
        last_rejected = data.get("title") or title
    return None, last_rejected


def fetch_aoc(session: requests.Session, slug: str, name: str, kind: str) -> dict:
    """Try the kind-appropriate disambig suffixes (with sentence-case variants)
    first, then fall back to opensearch. Reject results whose description+
    extract doesn't mention wine vocabulary."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = slug_to_title(slug, name)
    candidates = _candidate_titles(base, kind)

    record, rejected = _try_candidates(session, slug, candidates)
    if record:
        return record

    fallback = opensearch_aoc_title(session, base, kind)
    if fallback and fallback not in candidates:
        extra_record, extra_rejected = _try_candidates(session, slug, [fallback])
        if extra_record:
            return extra_record
        rejected = rejected or extra_rejected

    if rejected is not None:
        return {
            "slug": slug,
            "lang": LANG,
            "error": "not_aoc_topic",
            "rejected_title": rejected,
            "fetched_at": now,
        }
    return {
        "slug": slug,
        "lang": LANG,
        "missing": True,
        "attempted_titles": candidates + ([fallback] if fallback else []),
        "fetched_at": now,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.2, help="seconds between API calls")
    ap.add_argument("--limit", type=int, default=0, help="cap on AOCs to process (0 = all)")
    args = ap.parse_args()

    if not EXTRACTED.exists():
        print(
            f"error: {EXTRACTED} missing — run scripts/02_extract_cahiers.py first",
            file=sys.stderr,
        )
        return 1

    targets = collect_aoc_targets()
    if args.limit:
        targets = targets[: args.limit]
    print(f"[02b/aocs] {len(targets)} non-DGC AOCs to consider", file=sys.stderr)

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = miss = err = cached = 0
    for slug, name, kind in tqdm(targets, desc="wikipedia/aocs/fr", leave=False):
        cache = OUT_DIR / f"{slug}.json"
        if cache.exists() and not args.refresh:
            cached += 1
            continue
        result = fetch_aoc(session, slug, name, kind)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        if result.get("missing"):
            miss += 1
        elif result.get("error"):
            err += 1
        else:
            ok += 1
        time.sleep(args.throttle)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_aocs": len(targets),
        "license": "CC-BY-SA-4.0",
        "source": "fr.wikipedia.org REST summary + Action API + TextExtracts",
        "lang": LANG,
        "scope": "non-DGC AOCs from raw/inao/cahier-extracted/",
        "counts": {"ok": ok, "miss": miss, "err": err, "cached": cached},
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(
        f"[02b/aocs] new ok={ok} miss={miss} err={err} cached={cached} "
        f"manifest: {MANIFEST.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
