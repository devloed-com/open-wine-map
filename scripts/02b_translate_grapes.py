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


def _enumerate_jobs(
    slugs: list[str], target_locales: tuple[str, ...], *, skip_cached: bool = True,
) -> list[dict]:
    """Per (target_lang, slug) where the target has no usable native entry,
    some other locale supplies one, and the cache is stale or absent."""
    dominant = load_dominant_lang()
    jobs: list[dict] = []
    for slug in slugs:
        for tgt in target_locales:
            if native_extract_for(tgt, slug) is not None:
                continue
            source = pick_source(slug, tgt, dominant.get(slug))
            if source is None:
                continue
            if skip_cached:
                existing = _existing_cache(tgt, slug)
                if (
                    existing
                    and existing.get("extract")
                    and existing.get("source_sha") == extract_sha(source["extract"])
                    and existing.get("source_lang") == source["lang"]
                ):
                    continue
            jobs.append({"slug": slug, "lang": tgt, "source": source})
    return jobs


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


def import_translations_file(
    in_path: Path, *, target_locales: tuple[str, ...],
    translator_id: str, translator_kind: str,
) -> int:
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1
    blocks = _normalise_todo_payload(payload, target_locales)
    if not blocks:
        print("error: file has neither single-locale nor multi-locale shape.", file=sys.stderr)
        return 1
    dominant = load_dominant_lang()

    wrote: dict[str, int] = {}
    skipped_empty = skipped_sha = 0
    for lang, items in blocks:
        wrote.setdefault(lang, 0)
        for it in items:
            slug = it.get("slug") or ""
            extract = (it.get("extract") or "").strip()
            if not extract:
                skipped_empty += 1
                continue
            source = {
                "lang": it.get("source_lang") or "",
                "extract": it.get("source_extract") or "",
                "page_url": it.get("source_page_url") or "",
                "revision_id": it.get("source_revision_id"),
                "wikipedia_title": it.get("source_wikipedia_title") or "",
            }
            if not source["extract"]:
                skipped_empty += 1
                continue
            current = pick_source(slug, lang, dominant.get(slug))
            if current and current["lang"] == source["lang"]:
                cur_sha = extract_sha(current["extract"])
                if it.get("source_sha") and it["source_sha"] != cur_sha:
                    print(
                        f"  skip {lang}/{slug}: source SHA mismatch — re-run --emit-todo",
                        file=sys.stderr,
                    )
                    skipped_sha += 1
                    continue
            _write_cache(
                lang=lang, slug=slug, extract=extract, source=source,
                translator=translator_id, translator_kind=translator_kind,
            )
            wrote[lang] += 1
    total = sum(wrote.values())
    counts = ", ".join(f"{lang}={n}" for lang, n in wrote.items())
    print(
        f"[02b-grape-tx] wrote {total} ({counts}); "
        f"skipped empty={skipped_empty}, sha_mismatch={skipped_sha}",
        file=sys.stderr,
    )
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
