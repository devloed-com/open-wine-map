"""Translate grape-variety Wikipedia extracts into target locales where the
native Wikipedia page is missing.

Pipeline stage 02b/grapes-translate — sister stage to 02b_fetch_grape_lexicon
and to the cahier translators (02c / 02e) and the styles translator (02b
/styles-translate). For every grape slug whose target-locale Wikipedia
entry is missing or 404, picks the best available source-locale extract
via the chain `dominant-cahier-lang(slug) → fr → en → any-other`,
translates it into the target locale, and caches the result under
`raw/translations/grapes/<lang>/<slug>.json` with full source
attribution.

Stage 04 merges the translated cache on top of the native fetch cache,
producing a unified per-locale grape lexicon. The UI renders translated
entries with "translated from <source-locale> Wikipedia · CC BY-SA 4.0"
attribution instead of the legacy `(français)` fallback marker.

Providers (matching 02c / 02e / 02b-translate-styles):
  anthropic — Anthropic Messages API (requires ANTHROPIC_API_KEY).
  mistral   — Mistral Chat API (requires MISTRAL_API_KEY).
  ollama    — Local Ollama HTTP API (default model: mistral-small3.2).
  manual    — No-op; use with --emit-todo / --import for hand translation.

Cache invalidation: per (slug, target_lang) the cache stores `source_sha`
(sha256 of the source extract). When the upstream Wikipedia extract
changes, the cache is invalidated automatically.

Reads:
  raw/wikipedia/grapes/<lang>/<slug>.json (native fetches; some `missing`)
  raw/inao/cahier-extracted/, raw/es/pliegos-extracted/,
  raw/pt/cadernos-extracted/                   (slug corpus + dominant-lang)

Writes:
  raw/translations/grapes/<lang>/<slug>.json
  raw/translations/grapes/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache, providers, roundtrip  # noqa: E402
from _lib.grape_corpus import collect_grape_slugs, per_slug_dominant_lang  # noqa: E402

NATIVE_DIR = ROOT / "raw" / "wikipedia" / "grapes"
CACHE_ROOT = ROOT / "raw" / "translations" / "grapes"
MANIFEST = CACHE_ROOT / "manifest.json"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"

# Target locales the UI renders. PT is *not* a target (no /pt/ page yet)
# but PT is fetched as a source language for translation (some grapes
# only have authoritative pages on pt.wikipedia).
LOCALES = ("fr", "en", "es", "nl")
SOURCE_LOCALES = ("fr", "en", "es", "nl", "pt")

LOCALE_NAME = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "nl": "Dutch",
    "pt": "Portuguese",
}


SYSTEM_PROMPT = """You translate short Wikipedia paragraphs about grape varieties into the target language.

Style:
- Plain prose. No markdown, no list formatting, no quotes around the output, no trailing brackets like [...].
- Preserve proper nouns exactly as in the source: appellation names, region names, grape-variety names (Tempranillo, Garnacha Tinta, Touriga Nacional, Mourvèdre, Monastrell, Cabernet Sauvignon, Chardonnay, etc.) — including their per-country regulatory spellings (Aragonez vs Tinta Roriz vs Tempranillo).
- Translate ampelographic and vinification vocabulary naturally for a wine-literate reader (sommelier students and enthusiasts).
- Match the source paragraph's register and length — do not add extra context, footnotes, or explanations.
- If the source paragraph ends with "[…]" that is a truncation marker; preserve it at the end of your translation as "[…]".

Output ONLY the translated paragraph. No preface, no closing remarks, no JSON wrapper."""


def extract_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_VIVC_CACHE: dict[str, dict | None] = {}


def _load_vivc(slug: str) -> dict | None:
    if slug in _VIVC_CACHE:
        return _VIVC_CACHE[slug]
    path = VIVC_BY_SLUG / f"{slug}.json"
    if not path.exists():
        _VIVC_CACHE[slug] = None
        return None
    _VIVC_CACHE[slug] = json.loads(path.read_text())
    return _VIVC_CACHE[slug]


def _vivc_id_for(slug: str) -> int | None:
    rec = _load_vivc(slug)
    return rec.get("vivc_id") if rec else None


def _build_translation_donor_index(target_lang: str) -> dict[int, dict]:
    """Per target-lang `vivc_id → existing-translation` index. Two cahier
    slugs that share a VIVC id source from the same Wikipedia paragraph
    and therefore translate to the same target text — once one is in cache
    for a locale, every sibling slug can reuse the result instead of
    paying for another translation."""
    lang_dir = CACHE_ROOT / target_lang
    if not lang_dir.exists():
        return {}
    out: dict[int, dict] = {}
    for f in lang_dir.glob("*.json"):
        try:
            rec = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not (rec.get("extract") or "").strip():
            continue
        vid = _vivc_id_for(f.stem)
        if vid is None:
            continue
        out.setdefault(vid, rec)
    return out


def _share_from_donor(
    *, slug: str, target_lang: str, source: dict, donor: dict
) -> dict | None:
    """Reuse a sibling's translation when the source content + locale match
    exactly. A mismatch on either field means the donor was made from a
    different paragraph (different dominant-cahier-lang chain) — skip and
    let the candidate go through a real translation pass."""
    current_sha = extract_sha(source["extract"])
    if donor.get("source_sha") != current_sha:
        return None
    if donor.get("source_lang") != source["lang"]:
        return None
    vid = _vivc_id_for(slug)
    return {
        "slug": slug,
        "lang": target_lang,
        "extract": donor["extract"],
        "source_lang": source["lang"],
        "source_extract": source["extract"],
        "source_sha": current_sha,
        "source_page_url": source["page_url"],
        "source_revision_id": source.get("revision_id"),
        "source_wikipedia_title": source.get("wikipedia_title") or "",
        "translator": donor.get("translator", ""),
        "translator_kind": donor.get("translator_kind", ""),
        "shared_from_slug": donor.get("slug"),
        "shared_via": f"shared-vivc:{vid}:{donor.get('slug')}",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def load_corpus_slugs() -> list[str]:
    """`sorted([slug, …])` from FR + ES + PT extracted corpora."""
    return sorted(collect_grape_slugs().keys())


def load_dominant_lang() -> dict[str, str]:
    return per_slug_dominant_lang()


def load_native_entry(lang: str, slug: str) -> dict | None:
    return cache.read_json_or_none(NATIVE_DIR / lang / f"{slug}.json")


def native_extract_for(lang: str, slug: str) -> dict | None:
    entry = load_native_entry(lang, slug)
    if not entry or entry.get("missing") or entry.get("error"):
        return None
    if not (entry.get("extract") or "").strip():
        return None
    return entry


def source_chain(slug: str, target_lang: str, dominant: str | None) -> tuple[str, ...]:
    """`(src, …)` to walk in order: dominant cahier-lang → fr → en → other.
    `target_lang` is excluded — translating into yourself is a no-op."""
    seen = {target_lang}
    out: list[str] = []
    if dominant and dominant not in seen:
        out.append(dominant)
        seen.add(dominant)
    for fallback in ("fr", "en"):
        if fallback not in seen:
            out.append(fallback)
            seen.add(fallback)
    for other in SOURCE_LOCALES:
        if other not in seen:
            out.append(other)
            seen.add(other)
    return tuple(out)


def pick_source(slug: str, target_lang: str, dominant: str | None) -> dict | None:
    """Best source-locale entry for translating `slug` into `target_lang`."""
    for src in source_chain(slug, target_lang, dominant):
        entry = native_extract_for(src, slug)
        if entry is not None:
            return {
                "lang": src,
                "extract": entry["extract"],
                "page_url": entry.get("page_url") or "",
                "revision_id": entry.get("revision_id"),
                "wikipedia_title": entry.get("wikipedia_title") or "",
            }
    return None


def _cache_path(lang: str, slug: str) -> Path:
    return CACHE_ROOT / lang / f"{slug}.json"


def _existing_cache(lang: str, slug: str) -> dict | None:
    return cache.read_json_or_none(_cache_path(lang, slug))


def _write_cache(*, lang: str, slug: str, extract: str, source: dict,
                 translator: str, translator_kind: str) -> None:
    payload = {
        "slug": slug,
        "lang": lang,
        "extract": extract,
        "source_lang": source["lang"],
        "source_extract": source["extract"],
        "source_sha": extract_sha(source["extract"]),
        "source_page_url": source["page_url"],
        "source_revision_id": source.get("revision_id"),
        "source_wikipedia_title": source.get("wikipedia_title") or "",
        "translator": translator,
        "translator_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cache.write_json(_cache_path(lang, slug), payload)


def _cache_hit(existing: dict | None, source: dict) -> bool:
    return bool(
        existing
        and existing.get("extract")
        and existing.get("source_sha") == extract_sha(source["extract"])
        and existing.get("source_lang") == source["lang"]
    )


def _try_donor_share(
    slug: str, tgt: str, source: dict, donor_indexes: dict[str, dict[int, dict]]
) -> dict | None:
    """If a sibling-vivc slug already has a cached translation in `tgt`
    with the same source content, write a shared cache entry and return
    it. Caller treats the return as a non-job (dedup short-circuit)."""
    vid = _vivc_id_for(slug)
    if vid is None:
        return None
    donor = donor_indexes[tgt].get(vid)
    if donor is None:
        return None
    shared = _share_from_donor(slug=slug, target_lang=tgt, source=source, donor=donor)
    if shared is None:
        return None
    cache.write_json(_cache_path(tgt, slug), shared)
    donor_indexes[tgt].setdefault(vid, shared)
    return shared


def _resolve_pair(
    slug: str, tgt: str, source: dict, donor_indexes: dict[str, dict[int, dict]],
    *, skip_cached: bool,
) -> tuple[str, dict | None]:
    """Classify a (slug, tgt) pair: `('cached', None)` already satisfied,
    `('shared', record)` resolved via donor short-circuit (side effect:
    cache written), `('queue', job)` needs a real translation pass."""
    if skip_cached:
        if _cache_hit(_existing_cache(tgt, slug), source):
            return "cached", None
        shared = _try_donor_share(slug, tgt, source, donor_indexes)
        if shared is not None:
            return "shared", shared
    return "queue", {"slug": slug, "lang": tgt, "source": source}


def _group_by_source(raw_jobs: list[dict]) -> list[dict]:
    """Collapse jobs that share `(target_lang, source_sha)` to one anchor
    with `_siblings` attached; the translator processes anchors and
    `_replicate_to_siblings` copies the result."""
    anchors: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    for job in raw_jobs:
        key = (job["lang"], extract_sha(job["source"]["extract"]))
        anchor = by_key.get(key)
        if anchor is None:
            by_key[key] = job
            job["_siblings"] = []
            anchors.append(job)
        else:
            anchor["_siblings"].append(job)
    return anchors


def _enumerate_jobs(
    slugs: list[str], target_locales: tuple[str, ...], *, skip_cached: bool = True,
) -> list[dict]:
    """Per (target_lang, slug) where the target has no usable native entry,
    some other locale supplies one, and the cache is stale or absent.
    Applies two-stage dedup (donor short-circuit + intra-run grouping) so
    the returned jobs are unique by source content."""
    dominant = load_dominant_lang()
    donor_indexes = {lang: _build_translation_donor_index(lang) for lang in target_locales}
    raw_jobs: list[dict] = []
    shared_writes = 0
    for slug in slugs:
        for tgt in target_locales:
            if native_extract_for(tgt, slug) is not None:
                continue
            source = pick_source(slug, tgt, dominant.get(slug))
            if source is None:
                continue
            kind, payload = _resolve_pair(
                slug, tgt, source, donor_indexes, skip_cached=skip_cached,
            )
            if kind == "shared":
                shared_writes += 1
            elif kind == "queue":
                raw_jobs.append(payload)

    anchors = _group_by_source(raw_jobs)
    n_siblings = sum(len(a["_siblings"]) for a in anchors)
    if shared_writes or n_siblings:
        print(
            f"[02b-grape-tx] dedup: reused {shared_writes} from prior runs; "
            f"grouped {n_siblings} siblings under {len(anchors)} anchors",
            file=sys.stderr,
        )
    return anchors


def _replicate_to_siblings(anchor_job: dict, translated: str, *,
                           translator: str, translator_kind: str) -> None:
    """Anchor → siblings: every sibling job has the same (target_lang,
    source_sha) as the anchor, so the translated text applies verbatim.
    Recorded with `shared_via: shared-vivc-source:<anchor-slug>` so the
    audit can attribute reuse to the dedup pass (vs. a prior-run donor)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for sib in anchor_job.get("_siblings") or []:
        sib_src = sib["source"]
        payload = {
            "slug": sib["slug"],
            "lang": sib["lang"],
            "extract": translated,
            "source_lang": sib_src["lang"],
            "source_extract": sib_src["extract"],
            "source_sha": extract_sha(sib_src["extract"]),
            "source_page_url": sib_src["page_url"],
            "source_revision_id": sib_src.get("revision_id"),
            "source_wikipedia_title": sib_src.get("wikipedia_title") or "",
            "translator": translator,
            "translator_kind": translator_kind,
            "shared_from_slug": anchor_job["slug"],
            "shared_via": f"shared-vivc-source:{anchor_job['slug']}",
            "fetched_at": now,
        }
        cache.write_json(_cache_path(sib["lang"], sib["slug"]), payload)


def _translate_one(provider, *, source_extract: str, source_lang: str, target_lang: str) -> str:
    user = (
        f"Translate this {LOCALE_NAME[source_lang]} Wikipedia paragraph about a grape variety "
        f"into {LOCALE_NAME[target_lang]}.\n\n---\n{source_extract}\n---"
    )
    return provider.chat(system=SYSTEM_PROMPT, user=user, max_tokens=600, num_ctx=4096)


def _process_one_job(provider, model_id: str, job: dict) -> tuple[bool, str | None]:
    src = job["source"]
    try:
        translated = _translate_one(
            provider,
            source_extract=src["extract"],
            source_lang=src["lang"],
            target_lang=job["lang"],
        )
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    translated = (translated or "").strip()
    if not translated:
        return False, "empty response"
    _write_cache(
        lang=job["lang"], slug=job["slug"], extract=translated, source=src,
        translator=model_id, translator_kind=provider.kind,
    )
    _replicate_to_siblings(
        job, translated, translator=model_id, translator_kind=provider.kind,
    )
    return True, None


def _run_translation_loop(provider, model_id: str, jobs: list[dict], workers: int):
    done = 0
    skipped: list[tuple[str, str, str]] = []
    if workers <= 1:
        for job in tqdm(jobs, desc="translate-grapes", leave=False):
            ok, err = _process_one_job(provider, model_id, job)
            if ok:
                done += 1
            else:
                skipped.append((job["lang"], job["slug"], err or "unknown"))
            time.sleep(0.05)
        return done, skipped

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_one_job, provider, model_id, j): j for j in jobs}
        for fut in tqdm(as_completed(futures), total=len(jobs), desc="translate-grapes", leave=False):
            job = futures[fut]
            try:
                ok, err = fut.result()
            except Exception as e:  # noqa: BLE001
                skipped.append((job["lang"], job["slug"], f"worker exception: {e}"))
                continue
            if ok:
                done += 1
            else:
                skipped.append((job["lang"], job["slug"], err or "unknown"))
    return done, skipped


# ----------------------------- emit / import (manual round-trip) ----


def _job_to_todo_item(j: dict) -> dict:
    src = j["source"]
    return {
        "slug": j["slug"],
        "lang": j["lang"],
        "source_lang": src["lang"],
        "source_extract": src["extract"],
        "source_sha": extract_sha(src["extract"]),
        "source_page_url": src["page_url"],
        "source_revision_id": src.get("revision_id"),
        "source_wikipedia_title": src.get("wikipedia_title") or "",
        "extract": "",
    }


def emit_todo_file(
    out_path: Path, *, slugs: list[str], target_locales: tuple[str, ...],
    skip_cached: bool, single_lang: bool,
) -> int:
    jobs = _enumerate_jobs(slugs, target_locales, skip_cached=skip_cached)
    by_lang: dict[str, list[dict]] = {l: [] for l in target_locales}
    for j in jobs:
        by_lang[j["lang"]].append(_job_to_todo_item(j))
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if single_lang:
        lang = target_locales[0]
        payload = {"lang": lang, "exported_at": timestamp, "items": by_lang[lang]}
        total = len(payload["items"])
    else:
        payload = {"exported_at": timestamp}
        for lang in target_locales:
            payload[lang] = {"items": by_lang[lang]}
        total = sum(len(by_lang[l]) for l in target_locales)
    cache.write_json(out_path, payload)
    counts = ", ".join(f"{lang}={len(by_lang[lang])}" for lang in target_locales)
    print(f"[02b-grape-tx] wrote {out_path} ({total} items: {counts})", file=sys.stderr)
    return 0


def _normalise_todo_payload(
    payload: dict, target_locales: tuple[str, ...],
) -> list[tuple[str, list[dict]]]:
    if "items" in payload and "lang" in payload:
        return [(payload["lang"], payload.get("items") or [])]
    out: list[tuple[str, list[dict]]] = []
    for lang in target_locales:
        block = payload.get(lang)
        if isinstance(block, dict) and isinstance(block.get("items"), list):
            out.append((lang, block["items"]))
    return out


def _import_one_item(
    it: dict, lang: str, dominant: dict[str, str], *,
    translator_id: str, translator_kind: str,
) -> str:
    """Returns `'wrote'`, `'empty'`, or `'sha_mismatch'`. Side effect on
    `'wrote'`: writes the translation cache for (slug, lang)."""
    slug = it.get("slug") or ""
    extract = (it.get("extract") or "").strip()
    if not extract:
        return "empty"
    source = {
        "lang": it.get("source_lang") or "",
        "extract": it.get("source_extract") or "",
        "page_url": it.get("source_page_url") or "",
        "revision_id": it.get("source_revision_id"),
        "wikipedia_title": it.get("source_wikipedia_title") or "",
    }
    if not source["extract"]:
        return "empty"
    current = pick_source(slug, lang, dominant.get(slug))
    if current and current["lang"] == source["lang"]:
        cur_sha = extract_sha(current["extract"])
        if it.get("source_sha") and it["source_sha"] != cur_sha:
            print(
                f"  skip {lang}/{slug}: source SHA mismatch — re-run --emit-todo",
                file=sys.stderr,
            )
            return "sha_mismatch"
    _write_cache(
        lang=lang, slug=slug, extract=extract, source=source,
        translator=translator_id, translator_kind=translator_kind,
    )
    return "wrote"


def _load_import_payload(in_path: Path, target_locales: tuple[str, ...]):
    """Parse + normalise the import file. Returns the block list or None
    on any error (with the error already printed to stderr)."""
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return None
    try:
        payload = json.loads(in_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return None
    blocks = _normalise_todo_payload(payload, target_locales)
    if not blocks:
        print("error: file has neither single-locale nor multi-locale shape.", file=sys.stderr)
        return None
    return blocks


def import_translations_file(
    in_path: Path, *, target_locales: tuple[str, ...],
    translator_id: str, translator_kind: str,
) -> int:
    blocks = _load_import_payload(in_path, target_locales)
    if blocks is None:
        return 1
    dominant = load_dominant_lang()

    wrote: dict[str, int] = {}
    skipped_empty = skipped_sha = 0
    for lang, items in blocks:
        wrote.setdefault(lang, 0)
        for it in items:
            status = _import_one_item(
                it, lang, dominant,
                translator_id=translator_id, translator_kind=translator_kind,
            )
            if status == "wrote":
                wrote[lang] += 1
            elif status == "empty":
                skipped_empty += 1
            elif status == "sha_mismatch":
                skipped_sha += 1
    total = sum(wrote.values())
    counts = ", ".join(f"{lang}={n}" for lang, n in wrote.items())
    print(
        f"[02b-grape-tx] wrote {total} ({counts}); "
        f"skipped empty={skipped_empty}, sha_mismatch={skipped_sha}",
        file=sys.stderr,
    )
    if total > 0:
        _enumerate_jobs(load_corpus_slugs(), target_locales, skip_cached=True)
    return 0


def _write_manifest(provider_kind: str, model_id: str,
                    done_by_lang: dict[str, int], skipped: list[tuple[str, str, str]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "translator_kind": provider_kind,
        "translator": model_id,
        "translated_by_lang": done_by_lang,
        "skipped": [{"lang": l, "slug": s, "reason": r} for (l, s, r) in skipped],
    }
    cache.write_json(MANIFEST, payload, sort_keys=True)


# --------------------------------------------------------------------- main --


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama", choices=("anthropic", "mistral", "ollama", "manual"),
        help="translation backend (default: ollama).",
    )
    ap.add_argument("--model", default=None,
        help=f"model id (defaults: anthropic={providers.DEFAULT_ANTHROPIC_MODEL}, "
             f"mistral={providers.DEFAULT_MISTRAL_MODEL}, "
             f"ollama={providers.DEFAULT_OLLAMA_MODEL})")
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL,
        help=f"Ollama chat endpoint (default: {providers.DEFAULT_OLLAMA_URL})")
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL,
        help=f"Mistral chat endpoint (default: {providers.DEFAULT_MISTRAL_URL})")
    ap.add_argument("--lang", action="append", default=None,
        help="restrict to a specific target locale (repeatable); default: all 4")
    ap.add_argument("--limit", type=int, default=0,
        help="translate at most N (slug, lang) pairs (0 = all)")
    ap.add_argument("--workers", type=int, default=1,
        help="concurrent (slug, lang) pairs to translate (default 1)")
    ap.add_argument("--refresh", action="store_true",
        help="ignore cached translations and re-translate everything (still honours SHA-match no-op).")
    roundtrip.add_arguments(ap)
    return ap


def _handle_manual(slugs: list[str], target_locales: tuple[str, ...], refresh: bool) -> int:
    jobs = _enumerate_jobs(slugs, target_locales, skip_cached=not refresh)
    if not jobs:
        print("[02b-grape-tx] nothing to translate (cache satisfies all needs).", file=sys.stderr)
        return 0
    print(f"[02b-grape-tx] {len(jobs)} (slug, lang) pairs need translation:", file=sys.stderr)
    for j in jobs[:30]:
        src = j["source"]
        print(f"  {j['lang']}/{j['slug']} ← {src['lang']} (\"{src['wikipedia_title']}\")",
              file=sys.stderr)
    if len(jobs) > 30:
        print(f"  … and {len(jobs)-30} more.", file=sys.stderr)
    print(
        "Use --emit-todo PATH to dump them for hand translation, or switch "
        "--provider to ollama / anthropic / mistral.",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    args = _build_parser().parse_args()
    rv = roundtrip.validate_emit_import(args)
    if rv is not None:
        return rv

    target_locales = tuple(args.lang) if args.lang else LOCALES
    slugs = load_corpus_slugs()
    if not slugs:
        print("error: corpus is empty — run scripts/02_extract_cahiers.py first.", file=sys.stderr)
        return 1

    if args.emit_todo:
        return emit_todo_file(
            Path(args.emit_todo), slugs=slugs, target_locales=target_locales,
            skip_cached=not args.all, single_lang=bool(args.lang and len(args.lang) == 1),
        )
    if args.import_path:
        return import_translations_file(
            Path(args.import_path), target_locales=target_locales,
            translator_id=args.translator_id, translator_kind=args.translator_kind,
        )
    if args.provider == "manual":
        return _handle_manual(slugs, target_locales, args.refresh)

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    jobs = _enumerate_jobs(slugs, target_locales, skip_cached=not args.refresh)
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
    if not jobs:
        print("[02b-grape-tx] nothing to translate (cache satisfies all needs).", file=sys.stderr)
        _write_manifest(provider.kind, model_id, {}, [])
        return 0

    print(f"[02b-grape-tx] translating {len(jobs)} (slug, lang) pairs with {provider.kind} "
          f"({model_id}), workers={args.workers}", file=sys.stderr)
    done, skipped = _run_translation_loop(provider, model_id, jobs, args.workers)

    done_by_lang = dict.fromkeys(target_locales, 0)
    for slug in slugs:
        for l in target_locales:
            entry = _existing_cache(l, slug)
            if entry and entry.get("extract"):
                done_by_lang[l] += 1

    print(f"[02b-grape-tx] done={done}, skipped={len(skipped)}", file=sys.stderr)
    for lang, slug, err in skipped[:20]:
        print(f"  skip {lang}/{slug}: {err}", file=sys.stderr)
    if len(skipped) > 20:
        print(f"  … and {len(skipped)-20} more.", file=sys.stderr)
    _write_manifest(provider.kind, model_id, done_by_lang, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
