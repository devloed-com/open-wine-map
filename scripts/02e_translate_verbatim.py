"""Translate verbatim-mode terroir-facts into the panel target locales.

Sibling of the per-country 02e bullet-translation scripts. Picks up
records emitted by `_lib/terroir_verbatim.py` (mode="verbatim") from
the shared `raw/terroir-facts/` cache and translates the verbatim
text into en / fr / es / nl, excluding each record's own
`source_lang`. Per-country 02e scripts already skip verbatim records
(they require `facts` to translate), so this stage is the
single source of verbatim translations regardless of country.

Cache key: sha256 of `verbatim_text` (carried as `cahier_source_sha`
in the source). Re-running 02d that lengthens the lien past
MIN_LIEN_CHARS invalidates both 02d cache (re-routed to bullet
extraction) and downstream 02e (the bullet path picks up the new
record).

Providers: anthropic / mistral / ollama / manual (mirrors the
per-country 02e pattern). The manual round-trip flow uses
`--emit-todo PATH` to dump untranslated items as a single JSON and
`--import PATH --translator-id <id>` to write the cache files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache, providers  # noqa: E402

TERROIR_FACTS = ROOT / "raw" / "terroir-facts"
CACHE_ROOT = ROOT / "raw" / "translations" / "terroir-facts"

ALL_LOCALES = ("en", "fr", "es", "nl")
LOCALE_NAME = {
    "en": "English", "fr": "French", "es": "Spanish", "nl": "Dutch",
}
SOURCE_LANG_NAME = {
    "bg": "Bulgarian", "cs": "Czech", "de": "German", "el": "Greek",
    "en": "English", "es": "Spanish", "fr": "French", "hr": "Croatian",
    "hu": "Hungarian", "it": "Italian", "nl": "Dutch", "pt": "Portuguese",
    "ro": "Romanian", "sk": "Slovak", "sl": "Slovenian",
}

SYSTEM_PROMPT = (
    "You translate a short verbatim paragraph from a wine appellation's "
    "regulatory specification ({source_lang_name}) into {target_lang_name}. "
    "The paragraph describes terroir, history, or wine character and is "
    "aimed at sommelier students and wine enthusiasts.\n\n"
    "Translate faithfully. Preserve regulator-specific terminology, place "
    "names, and wine-style traditional terms verbatim. Do not paraphrase, "
    "summarise, or add commentary. Do not silently correct typos in the "
    "source — keep them as published (they are part of the public record). "
    "Return ONLY the translated paragraph, no preamble, no closing remark."
)


def cache_path(lang: str, slug: str) -> Path:
    return CACHE_ROOT / lang / f"{slug}.json"


def _iter_verbatim_records() -> list[dict]:
    out = []
    if not TERROIR_FACTS.exists():
        return out
    for jp in sorted(TERROIR_FACTS.glob("*.json")):
        if jp.name.startswith(("_", "manifest")):
            continue
        rec = cache.read_json_or_none(jp)
        if not rec or rec.get("mode") != "verbatim":
            continue
        if not rec.get("verbatim_text"):
            continue
        out.append(rec)
    return out


def _target_locales_for(src: dict) -> tuple[str, ...]:
    src_lang = src.get("source_lang") or ""
    return tuple(l for l in ALL_LOCALES if l != src_lang)


def _is_fresh_cache(existing: dict | None, src_sha: str) -> bool:
    return bool(
        existing
        and existing.get("mode") == "verbatim"
        and existing.get("source_text_sha") == src_sha
    )


def load_existing(lang: str, slug: str) -> dict | None:
    return cache.read_json_or_none(cache_path(lang, slug))


def enumerate_jobs(skip_cached: bool = True) -> list[dict]:
    jobs: list[dict] = []
    for src in _iter_verbatim_records():
        sha = src.get("cahier_source_sha") or ""
        for lang in _target_locales_for(src):
            if skip_cached and _is_fresh_cache(load_existing(lang, src["slug"]), sha):
                continue
            jobs.append({
                "slug": src["slug"],
                "lang": lang,
                "src": src,
                "sha": sha,
            })
    return jobs


def write_translation(
    *, slug: str, lang: str, src: dict, translated_text: str,
    translator: str, translator_kind: str,
) -> None:
    payload = {
        "country": src.get("country"),
        "source_lang": src.get("source_lang"),
        "slug": slug,
        "lang": lang,
        "mode": "verbatim",
        "verbatim_text": translated_text,
        "verbatim_chars": len(translated_text),
        "validation_flag": src.get("validation_flag", ""),
        "source_text_sha": src.get("cahier_source_sha") or "",
        "cahier_source_pdf_url": src.get("cahier_source_pdf_url") or "",
        "translator": translator,
        "translator_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cache.write_json(cache_path(lang, slug), payload)


def translate_one(provider, job: dict) -> tuple[str | None, str | None]:
    src = job["src"]
    src_lang = src.get("source_lang") or ""
    system = SYSTEM_PROMPT.format(
        source_lang_name=SOURCE_LANG_NAME.get(src_lang, src_lang or "the source language"),
        target_lang_name=LOCALE_NAME[job["lang"]],
    )
    user = f"Translate the following paragraph:\n\n{src['verbatim_text']}"
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1200, num_ctx=4096)
    except Exception as e:  # noqa: BLE001
        return None, f"call: {e}"
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return None, "empty response"
    return text, None


def emit_todo(out_path: Path, *, skip_cached: bool) -> int:
    jobs = enumerate_jobs(skip_cached=skip_cached)
    items = [
        {
            "slug": j["slug"],
            "lang": j["lang"],
            "source_lang": j["src"].get("source_lang"),
            "source_text_sha": j["sha"],
            "source_text": j["src"]["verbatim_text"],
            "translated_text": "",
        }
        for j in jobs
    ]
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "verbatim",
        "languages": list(ALL_LOCALES),
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    print(f"[02e/verbatim] wrote {out_path} ({len(items)} items)", file=sys.stderr)
    return 0


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    wrote = 0
    skipped = 0
    src_by_slug = {r["slug"]: r for r in _iter_verbatim_records()}
    for item in items:
        slug = item.get("slug")
        lang = item.get("lang")
        txt = (item.get("translated_text") or "").strip()
        if not (slug and lang and txt):
            skipped += 1
            continue
        src = src_by_slug.get(slug)
        if not src:
            print(f"  skip {slug}/{lang}: source record not found", file=sys.stderr)
            skipped += 1
            continue
        if src.get("cahier_source_sha") != item.get("source_text_sha"):
            print(f"  skip {slug}/{lang}: sha mismatch (source changed since export)",
                  file=sys.stderr)
            skipped += 1
            continue
        write_translation(
            slug=slug, lang=lang, src=src, translated_text=txt,
            translator=translator_id, translator_kind=translator_kind,
        )
        wrote += 1
    print(f"[02e/verbatim] imported {wrote} translation(s), skipped {skipped}",
          file=sys.stderr)
    return 0 if wrote else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="manual",
        choices=("anthropic", "mistral", "ollama", "manual"),
    )
    ap.add_argument("--model", default=None)
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--emit-todo", metavar="PATH",
                    help="dump untranslated jobs to PATH and exit")
    ap.add_argument("--import", dest="import_path", metavar="PATH",
                    help="import translations from PATH (round-trip)")
    ap.add_argument("--translator-id", default="",
                    help="required with --import; identifies the translator")
    ap.add_argument("--translator-kind", default="manual",
                    help="optional with --import; e.g. 'deepl-api', 'human'")
    args = ap.parse_args()

    if args.emit_todo:
        return emit_todo(Path(args.emit_todo), skip_cached=not args.refresh)
    if args.import_path:
        if not args.translator_id:
            print("error: --translator-id required with --import", file=sys.stderr)
            return 2
        return import_todo(
            Path(args.import_path),
            translator_id=args.translator_id,
            translator_kind=args.translator_kind,
        )

    jobs = enumerate_jobs(skip_cached=not args.refresh)
    if args.only:
        needles = [s.lower() for s in args.only]
        jobs = [j for j in jobs if any(n in j["slug"].lower() for n in needles)]
    if args.limit:
        jobs = jobs[: args.limit]

    if not jobs:
        print("[02e/verbatim] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(
            f"[02e/verbatim] manual provider: {len(jobs)} jobs need translation. "
            f"Use --emit-todo PATH, fill the file offline, then "
            f"--import PATH --translator-id <id> to write the cache.",
            file=sys.stderr,
        )
        return 1

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[02e/verbatim] {len(jobs)} jobs (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)
    for job in jobs:
        translated, err = translate_one(provider, job)
        if translated is None:
            print(f"  skip {job['slug']}/{job['lang']}: {err}", file=sys.stderr)
            continue
        write_translation(
            slug=job["slug"], lang=job["lang"], src=job["src"],
            translated_text=translated, translator=model_id,
            translator_kind=getattr(provider, "kind", args.provider),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
