"""Fetch Wikipedia pages for appellations in the corpus, for use as a salience
hint in stage 02d (terroir-fact extraction).

Sister stage to 02b_fetch_grape_lexicon.py. Same Wikipedia + CC-BY-SA-4.0
attribution model. Per CLAUDE.md the cahier/pliego text remains the
regulator-only canonical source; Wikipedia is admitted as a bounded
secondary source for grape-variety descriptions and per-appellation pages,
each cached entry records `revision`, `fetched_at`, `page_url`, `license`
so downstream stages and the UI can attribute correctly.

Per-language driver: pass `--lang` to switch the source records dir, the
Wikipedia host, the disambiguator chain, and the wine-keyword filter.
Defaults to `fr` (the FR pipeline's existing call shape stays byte-identical).

Reads:  raw/<source>/  (collects non-DGC appellations from extracted JSONs)
Writes: raw/wikipedia/aocs/<lang>/<slug>.json
        raw/wikipedia/aocs/manifest.json

Per cache file:
  - On hit: lead_extract (REST summary), sections (Action API parse),
    full_text (TextExtracts plaintext), revision, fetched_at, page_url,
    license, page_title.
  - On miss: {missing: true, fetched_at, attempted_titles}.
  - On disambiguation / wrong-topic: {error: "...", rejected_title,
    fetched_at}.

DGCs / subzonas are skipped — they inherit the parent appellation's
Wikipedia page in stage 02d. (Most do not have their own Wikipedia entry.)

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

# Per-language config. `disambiguators_for_kind` returns the suffix priority
# order for the candidate-title cascade (highest priority first); each suffix
# is later combined with sentence-case variants. `aoc_keywords` is the
# substring filter applied to the REST summary description+extract to reject
# wrong-topic page hits (a town named Bandol vs the Bandol appellation).
LANG_CONFIG: dict[str, dict] = {
    "fr": {
        "aoc_keywords": (
            "appellation", "vin", "vignoble", "viticole", "cépage", "cépages",
            "aoc", "aop", "igp", "vendange", "vendanges", "raisin",
        ),
        "default_source": "raw/inao/cahier-extracted",
        # FR: kind drives primary; both AOC and IGP are tried before bare title.
        "disambiguators_for_kind": lambda kind: (
            ("IGP", "AOC") if kind == "IGP" else ("AOC", "IGP")
        ),
    },
    "es": {
        "aoc_keywords": (
            "denominación", "denominacion", "vino", "vinos", "viñedo", "vinedo",
            "vinícola", "vinicola", "uva", "uvas", "vendimia", "viticultura",
            "do", "dop", "doca", "doc",
        ),
        "default_source": "raw/es/pliegos-extracted",
        # ES: most wine pages disambiguate as `(vino)`. `DOP` and the long form
        # `denominación de origen` are alternative suffixes some pages use.
        # Kind is informational — the cascade order is the same.
        "disambiguators_for_kind": lambda kind: (
            "vino", "DOP", "denominación de origen", "DO",
        ),
    },
}

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)


def rest_url(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{{title}}"


def action_url(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def looks_like_aoc(data: dict, keywords: tuple[str, ...]) -> bool:
    blob = ((data.get("description") or "") + " " + (data.get("extract") or "")).lower()
    return any(k in blob for k in keywords)


def slug_to_title(slug: str, name: str) -> str:
    """Prefer the cahier/pliego display name (preserves diacritics +
    capitalisation that the slug strips)."""
    return name or " ".join(p.capitalize() for p in slug.split("-"))


def _resolve_kind(rec: dict) -> str:
    """AOC / AOP / IGP / DOP / "" — drives the Wikipedia disambiguation suffix.
    Falls back to SIQO sign columns when `kind` is not set."""
    kind = (rec.get("kind") or "").upper()
    if kind:
        return kind
    sigs = (rec.get("signe_fr") or "") + " " + (rec.get("signe_ue") or "")
    if "IGP" in sigs:
        return "IGP"
    if "AOC" in sigs or "AOP" in sigs:
        return "AOC"
    return ""


def collect_targets(source_dir: Path) -> list[tuple[str, str, str]]:
    """Scan extracted records, return [(slug, name, kind)] for non-DGC entries."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for jp in sorted(source_dir.glob("*.json")):
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


def fetch_summary(session: requests.Session, lang: str, title: str) -> tuple[dict | None, int]:
    url = rest_url(lang).format(title=title.replace(" ", "_"))
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


def fetch_sections(session: requests.Session, lang: str, title: str) -> list[str]:
    try:
        r = session.get(
            action_url(lang),
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


def fetch_full_text(session: requests.Session, lang: str, title: str) -> str:
    try:
        r = session.get(
            action_url(lang),
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
    Wikipedia uses sentence case for compound page titles
    (e.g. `Alpes-de-haute-provence (IGP)`, not `Alpes-de-Haute-Provence`)."""
    parts = s.split("-")
    if len(parts) <= 1:
        return s
    return parts[0] + "-" + "-".join(p.lower() for p in parts[1:])


def _candidate_titles(base: str, disambiguators: tuple[str, ...]) -> list[str]:
    """Wikipedia disambiguates wine pages with parenthetical suffixes that
    vary by wiki (FR: `(AOC)` / `(IGP)`; ES: `(vino)` / `(DOP)` / ...).
    Try sentence-case variants too — REST does not follow case redirects on
    multi-segment compound titles. Bare title is the last fallback."""
    sc = _sentence_case(base)
    cands: list[str] = []
    for d in disambiguators:
        cands.append(f"{base} ({d})")
        cands.append(f"{sc} ({d})")
    cands.append(base)
    cands.append(sc)
    seen: set[str] = set()
    return [t for t in cands if not (t in seen or seen.add(t))]


def opensearch_title(
    session: requests.Session, lang: str, base: str, disambiguator: str
) -> str | None:
    """Fall-through: ask Wikipedia's opensearch for matching titles, return
    the first result that contains a wine-style disambiguation suffix or
    falls back to the first hit."""
    suffix_low = f"({disambiguator.lower()})"
    try:
        r = session.get(
            action_url(lang),
            params={
                "action": "opensearch",
                "search": f"{base} {disambiguator}",
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
        if suffix_low in t.lower():
            return t
    return titles[0] if titles else None


def _record_from(
    slug: str, lang: str, title: str, data: dict, session: requests.Session
) -> dict:
    sections = fetch_sections(session, lang, title)
    full_text = fetch_full_text(session, lang, title)
    return {
        "slug": slug,
        "lang": lang,
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
    session: requests.Session,
    lang: str,
    keywords: tuple[str, ...],
    slug: str,
    titles: list[str],
) -> tuple[dict | None, str | None]:
    """Probe each title via the REST summary; on the first wine-topic hit
    enrich and return the record. Otherwise return (None, last_rejected_title)."""
    last_rejected: str | None = None
    for title in titles:
        data, _ = fetch_summary(session, lang, title)
        if data is None:
            continue
        if looks_like_aoc(data, keywords):
            return _record_from(slug, lang, title, data, session), None
        last_rejected = data.get("title") or title
    return None, last_rejected


def fetch_aoc(
    session: requests.Session,
    cfg: dict,
    lang: str,
    slug: str,
    name: str,
    kind: str,
) -> dict:
    """Try the kind-appropriate disambig suffixes (with sentence-case variants)
    first, then fall back to opensearch. Reject results whose description+
    extract doesn't mention wine vocabulary."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = slug_to_title(slug, name)
    disambiguators = cfg["disambiguators_for_kind"](kind)
    keywords = cfg["aoc_keywords"]
    candidates = _candidate_titles(base, disambiguators)

    record, rejected = _try_candidates(session, lang, keywords, slug, candidates)
    if record:
        return record

    fallback = opensearch_title(session, lang, base, disambiguators[0])
    if fallback and fallback not in candidates:
        extra_record, extra_rejected = _try_candidates(
            session, lang, keywords, slug, [fallback]
        )
        if extra_record:
            return extra_record
        rejected = rejected or extra_rejected

    if rejected is not None:
        return {
            "slug": slug,
            "lang": lang,
            "error": "not_aoc_topic",
            "rejected_title": rejected,
            "fetched_at": now,
        }
    return {
        "slug": slug,
        "lang": lang,
        "missing": True,
        "attempted_titles": candidates + ([fallback] if fallback else []),
        "fetched_at": now,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lang", default="fr", choices=sorted(LANG_CONFIG),
                    help="Wikipedia language + per-country config (default: fr)")
    ap.add_argument("--source", default=None,
                    help="extracted-records dir (default: per-lang)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--throttle", type=float, default=0.2, help="seconds between API calls")
    ap.add_argument("--limit", type=int, default=0, help="cap on entries to process (0 = all)")
    args = ap.parse_args()

    cfg = LANG_CONFIG[args.lang]
    source_dir = Path(args.source) if args.source else ROOT / cfg["default_source"]
    out_dir = ROOT / "raw" / "wikipedia" / "aocs" / args.lang
    manifest_path = ROOT / "raw" / "wikipedia" / "aocs" / "manifest.json"

    if not source_dir.exists():
        print(
            f"error: {source_dir} missing — run the prior extraction stage first",
            file=sys.stderr,
        )
        return 1

    targets = collect_targets(source_dir)
    if args.limit:
        targets = targets[: args.limit]
    print(
        f"[02b/aocs/{args.lang}] {len(targets)} non-DGC entries to consider",
        file=sys.stderr,
    )

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    out_dir.mkdir(parents=True, exist_ok=True)
    ok = miss = err = cached = 0
    for slug, name, kind in tqdm(targets, desc=f"wikipedia/aocs/{args.lang}", leave=False):
        cache = out_dir / f"{slug}.json"
        if cache.exists() and not args.refresh:
            cached += 1
            continue
        result = fetch_aoc(session, cfg, args.lang, slug, name, kind)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        if result.get("missing"):
            miss += 1
        elif result.get("error"):
            err += 1
        else:
            ok += 1
        time.sleep(args.throttle)

    # Per-language sub-section in the shared manifest. Loading prior content
    # avoids clobbering sibling-lang manifests when multiple languages live
    # in the same `aocs/` tree.
    manifest_root: dict = {}
    if manifest_path.exists():
        try:
            manifest_root = json.loads(manifest_path.read_text())
        except Exception:  # noqa: BLE001
            manifest_root = {}
    if "by_lang" not in manifest_root or not isinstance(manifest_root.get("by_lang"), dict):
        manifest_root = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": "CC-BY-SA-4.0",
            "by_lang": {},
        }
    manifest_root["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest_root["by_lang"][args.lang] = {
        "n_entries": len(targets),
        "source": f"{args.lang}.wikipedia.org REST summary + Action API + TextExtracts",
        "scope": f"non-DGC entries from {source_dir.relative_to(ROOT)}",
        "counts": {"ok": ok, "miss": miss, "err": err, "cached": cached},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest_root, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"[02b/aocs/{args.lang}] new ok={ok} miss={miss} err={err} cached={cached} "
        f"manifest: {manifest_path.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
