"""Translate per-AOC cahier summaries (FR → en/es/nl) for the map UI.

Pipeline stage 02c.

Reads `raw/inao/cahier-extracted/*.json`, derives the same FR summary that
stage 04 will render (`derive_summary` in `_lib/summaries.py`), and writes
one machine-translated cache file per AOC per locale to
`raw/translations/summaries/<lang>/<slug>.json`. The cache file records the
SHA of the FR input so reruns are idempotent — entries are re-translated
only when the FR summary actually changed.

CLAUDE.md authorises this as a bounded translation layer: each cache file
carries `source_pdf_url`, `source_pdf_filename`, `source_summary`,
`source_summary_sha`, `translator`, `translator_kind`, and `fetched_at`,
and the UI renders an attribution line linking to the cahier des charges.

Providers
---------

`anthropic` — calls the Anthropic Messages API. Requires
`ANTHROPIC_API_KEY` in the environment. Default model: claude-haiku-4-5
(fast and accurate for short paragraphs at low cost).

`manual` — non-network mode. Lists every (slug, lang) pair with no cache
entry and exits non-zero. Use when running the pipeline in a fork that
prefers hand-translated text or a different translation tool: drop
matching JSON files into `raw/translations/summaries/<lang>/` (with at
least the `slug`, `lang`, `summary`, `source_summary_sha` fields) and
rerun stage 02c with `--provider=manual` to verify completeness.

Failures on individual AOCs are logged and skipped — the script exits 0
but reports a per-locale skip count so a CI loop can decide whether to
retry. Rerun stage 02c (any provider) to translate just the missing
entries.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.summaries import derive_summary, summary_sha  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
CACHE_ROOT = ROOT / "raw" / "translations" / "summaries"
TARGET_LOCALES = ("en", "es", "nl")
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_BATCH = 10

LOCALE_NAME = {
    "en": "English",
    "es": "Spanish",
    "nl": "Dutch",
}


SYSTEM_PROMPT = """You translate short French paragraphs from INAO cahier des charges (French wine appellation specifications) into the target language.

Style:
- Plain prose. No markdown, no list formatting, no quotes around the output.
- Preserve appellation names, region names, and grape variety names exactly as in the source (do not translate proper nouns; "Pinot noir" stays "Pinot noir", "Côtes du Rhône" stays "Côtes du Rhône").
- Translate vinification and stylistic vocabulary naturally for a wine-literate reader (sommelier students and enthusiasts).
- Match the source paragraph's register and length — do not add extra context, footnotes, or explanations.
- If the source mentions a colour ("rouge", "blanc", "rosé", "tranquille", "mousseux"), translate it.

Output ONLY the translated paragraph. No preface, no closing remarks, no JSON wrapper."""


# ---------------------------------------------------------------- providers --


class AnthropicProvider:
    kind = "anthropic-api"

    def __init__(self, model: str):
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise SystemExit(
                "error: anthropic SDK missing. add it with `uv add anthropic` "
                "(or use --provider=manual for non-network mode)."
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise SystemExit("error: ANTHROPIC_API_KEY environment variable is unset.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def translate(self, *, text: str, lang: str) -> str:
        target_name = LOCALE_NAME[lang]
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Translate this French paragraph into {target_name}.\n\n"
                        f"---\n{text}\n---"
                    ),
                }
            ],
        )
        # Concatenate all text blocks (Messages API returns a list).
        out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return out.strip()


class ManualProvider:
    kind = "manual"

    def __init__(self):
        pass

    def translate(self, *, text: str, lang: str) -> str:  # pragma: no cover
        raise RuntimeError(
            "manual provider does not perform translation; drop in pre-translated "
            "JSON files under raw/translations/summaries/<lang>/ and rerun."
        )


# -------------------------------------------------------------------- core --


def _cache_path(lang: str, slug: str) -> Path:
    return CACHE_ROOT / lang / f"{slug}.json"


def _load_existing(lang: str, slug: str) -> dict | None:
    p = _cache_path(lang, slug)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _write_cache(*, lang: str, slug: str, summary: str, source_text: str,
                 source_pdf_filename: str, source_pdf_url: str,
                 translator: str, translator_kind: str) -> None:
    p = _cache_path(lang, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "lang": lang,
        "summary": summary,
        "source_summary": source_text,
        "source_summary_sha": summary_sha(source_text),
        "source_pdf_filename": source_pdf_filename,
        "source_pdf_url": source_pdf_url,
        "translator": translator,
        "translator_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _enumerate_jobs(
    extracted_files: list[Path],
    languages: tuple[str, ...],
    *,
    skip_cached: bool = True,
) -> list[dict]:
    """Build the work list: every (lang, slug) whose cache is missing or stale.
    With `skip_cached=False`, every (lang, slug) pair is included regardless
    of cache state — used by `--emit-todo --all`."""
    jobs: list[dict] = []
    for f in sorted(extracted_files):
        if f.name == "_index.json":
            continue
        rec = json.loads(f.read_text())
        slug = rec["slug"]
        text = derive_summary(rec)
        if not text:
            continue
        sha = summary_sha(text)
        src = rec.get("source") or {}
        pdf_filename = src.get("filename") or ""
        pdf_url = src.get("boagri_url") or ""
        for lang in languages:
            if skip_cached:
                existing = _load_existing(lang, slug)
                if existing and existing.get("source_summary_sha") == sha and existing.get("summary"):
                    continue
            jobs.append(
                {
                    "slug": slug,
                    "lang": lang,
                    "source_text": text,
                    "source_pdf_filename": pdf_filename,
                    "source_pdf_url": pdf_url,
                }
            )
    return jobs


def _job_to_todo_item(j: dict) -> dict:
    return {
        "slug": j["slug"],
        "source_summary": j["source_text"],
        "source_summary_sha": summary_sha(j["source_text"]),
        "source_pdf_filename": j["source_pdf_filename"],
        "source_pdf_url": j["source_pdf_url"],
        "summary": "",
    }


def emit_todo_file(
    out_path: Path,
    *,
    languages: tuple[str, ...],
    skip_cached: bool,
    single_lang: bool,
) -> int:
    """Write a translation-todo JSON file. Single-locale shape when
    `single_lang=True`, otherwise dict-keyed-by-locale."""
    files = list(EXTRACTED.glob("*.json"))
    jobs = _enumerate_jobs(files, languages, skip_cached=skip_cached)
    by_lang: dict[str, list[dict]] = {l: [] for l in languages}
    for j in jobs:
        by_lang[j["lang"]].append(_job_to_todo_item(j))
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if single_lang:
        lang = languages[0]
        payload = {"lang": lang, "exported_at": timestamp, "items": by_lang[lang]}
        total = len(payload["items"])
    else:
        payload = {"exported_at": timestamp}
        total = 0
        for lang in languages:
            payload[lang] = {"items": by_lang[lang]}
            total += len(by_lang[lang])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    counts = ", ".join(f"{lang}={len(by_lang[lang])}" for lang in languages)
    print(f"[02c] wrote {out_path} ({total} items: {counts})", file=sys.stderr)
    return 0


def _normalise_todo_payload(payload: dict) -> list[tuple[str, list[dict]]]:
    """Yield (lang, items) pairs from either single-locale or multi-locale shape.
    `fr` is accepted on import (so a round-trip can carry hand-rewritten FR
    summaries that fix cahier-extraction quirks); it is never produced by
    `--emit-todo` or by the network-translation path."""
    if "items" in payload and "lang" in payload:
        return [(payload["lang"], payload.get("items") or [])]
    out: list[tuple[str, list[dict]]] = []
    for lang in (*TARGET_LOCALES, "fr"):
        block = payload.get(lang)
        if isinstance(block, dict) and isinstance(block.get("items"), list):
            out.append((lang, block["items"]))
    return out


def import_translations_file(
    in_path: Path,
    *,
    translator_id: str,
    translator_kind: str,
) -> int:
    """Read a translated TODO JSON and write per-AOC cache files. Returns the
    process exit code (0 on success, 1 on read error)."""
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1

    blocks = _normalise_todo_payload(payload)
    if not blocks:
        print(
            "error: file has neither a single-locale shape "
            "({lang, items}) nor a multi-locale shape ({en|es|nl: {items}}).",
            file=sys.stderr,
        )
        return 1

    # Build a per-slug map of the *current* FR derivation so we can verify
    # that the import file's source_summary_sha is still valid.
    current_sha: dict[str, str] = {}
    for f in EXTRACTED.glob("*.json"):
        if f.name == "_index.json":
            continue
        rec = json.loads(f.read_text())
        text = derive_summary(rec)
        if text:
            current_sha[rec["slug"]] = summary_sha(text)

    wrote: dict[str, int] = {}
    skipped_empty = skipped_sha = skipped_unknown = 0
    for lang, items in blocks:
        wrote.setdefault(lang, 0)
        for it in items:
            slug = it.get("slug") or ""
            summary = (it.get("summary") or "").strip()
            if not summary:
                skipped_empty += 1
                continue
            cur_sha = current_sha.get(slug)
            if cur_sha is None:
                print(f"  skip {lang}/{slug}: unknown slug (no extracted record)", file=sys.stderr)
                skipped_unknown += 1
                continue
            if it.get("source_summary_sha") and it["source_summary_sha"] != cur_sha:
                print(
                    f"  skip {lang}/{slug}: source SHA mismatch — re-run --emit-todo to refresh",
                    file=sys.stderr,
                )
                skipped_sha += 1
                continue
            _write_cache(
                lang=lang,
                slug=slug,
                summary=summary,
                source_text=it.get("source_summary") or "",
                source_pdf_filename=it.get("source_pdf_filename") or "",
                source_pdf_url=it.get("source_pdf_url") or "",
                translator=translator_id,
                translator_kind=translator_kind,
            )
            wrote[lang] += 1

    total_written = sum(wrote.values())
    counts = ", ".join(f"{lang}={n}" for lang, n in wrote.items())
    print(
        f"[02c] wrote {total_written} ({counts}); "
        f"skipped empty={skipped_empty}, sha_mismatch={skipped_sha}, unknown_slug={skipped_unknown}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="anthropic", choices=("anthropic", "manual"),
        help="translation backend (default: anthropic; set ANTHROPIC_API_KEY)",
    )
    ap.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"anthropic model id (default: {DEFAULT_MODEL})",
    )
    ap.add_argument(
        "--lang", action="append", choices=TARGET_LOCALES, default=None,
        help="restrict to a specific locale (repeatable); default: all 3",
    )
    ap.add_argument(
        "--limit", type=int, default=0,
        help="translate at most N (slug, lang) pairs (0 = all). Useful for partial runs.",
    )
    ap.add_argument(
        "--retry", action="store_true",
        help="alias for default behaviour: skips entries already cached, translates everything else",
    )
    ap.add_argument(
        "--emit-todo", metavar="PATH", default=None,
        help="write a translation-todo JSON file (no API calls) and exit. "
             "All locales by default; --lang restricts to one (single-locale shape).",
    )
    ap.add_argument(
        "--all", action="store_true",
        help="with --emit-todo: include entries that already have a cache hit "
             "(default is to export only missing entries).",
    )
    ap.add_argument(
        "--import", dest="import_path", metavar="PATH", default=None,
        help="read a filled-in todo JSON and write per-AOC cache files. "
             "Requires --translator-id.",
    )
    ap.add_argument(
        "--translator-id", default=None,
        help="identifier recorded as `translator` in cache files when using --import "
             "(e.g. \"claude.ai · 2026-05-01\" or \"deepl-v2\").",
    )
    ap.add_argument(
        "--translator-kind", default="manual",
        help="value recorded as `translator_kind` in cache files when using --import "
             "(default: manual; e.g. deepl-api).",
    )
    args = ap.parse_args()

    if not EXTRACTED.exists():
        print("error: raw/inao/cahier-extracted is missing — run 02_extract_cahiers.py first", file=sys.stderr)
        return 1

    if args.emit_todo and args.import_path:
        print("error: --emit-todo and --import are mutually exclusive.", file=sys.stderr)
        return 1

    # --- emit-todo path ---
    if args.emit_todo:
        single_lang = bool(args.lang) and len(args.lang) == 1
        languages = tuple(args.lang) if args.lang else TARGET_LOCALES
        return emit_todo_file(
            Path(args.emit_todo),
            languages=languages,
            skip_cached=not args.all,
            single_lang=single_lang,
        )

    # --- import path ---
    if args.import_path:
        if not args.translator_id:
            print(
                "error: --import requires --translator-id (e.g. "
                "--translator-id 'claude.ai · 2026-05-01').",
                file=sys.stderr,
            )
            return 1
        return import_translations_file(
            Path(args.import_path),
            translator_id=args.translator_id,
            translator_kind=args.translator_kind,
        )

    # --- network / manual-list paths (existing behaviour) ---
    languages = tuple(args.lang) if args.lang else TARGET_LOCALES
    files = list(EXTRACTED.glob("*.json"))
    jobs = _enumerate_jobs(files, languages)
    if args.limit:
        jobs = jobs[: args.limit]

    if not jobs:
        print("[02c] nothing to do — all caches up to date.", file=sys.stderr)
        return 0

    print(
        f"[02c] {len(jobs)} translations to fetch "
        f"(provider={args.provider}, model={args.model if args.provider == 'anthropic' else '-'}, "
        f"locales={','.join(languages)})",
        file=sys.stderr,
    )

    if args.provider == "manual":
        for j in jobs:
            print(f"  missing: {j['lang']}/{j['slug']}.json", file=sys.stderr)
        print(
            f"[02c] manual provider: {len(jobs)} entries need a hand-translation drop-in. "
            f"Use --emit-todo PATH to dump them as a single JSON for round-trip translation, "
            f"then --import PATH --translator-id <id> to write the cache files.",
            file=sys.stderr,
        )
        return 1

    provider = AnthropicProvider(args.model)
    translator_id = args.model

    skipped: list[tuple[str, str, str]] = []
    done = 0
    for j in tqdm(jobs, desc="translate", leave=False):
        try:
            translated = provider.translate(text=j["source_text"], lang=j["lang"])
        except Exception as e:  # noqa: BLE001
            skipped.append((j["lang"], j["slug"], str(e)))
            continue
        if not translated:
            skipped.append((j["lang"], j["slug"], "empty response"))
            continue
        _write_cache(
            lang=j["lang"],
            slug=j["slug"],
            summary=translated,
            source_text=j["source_text"],
            source_pdf_filename=j["source_pdf_filename"],
            source_pdf_url=j["source_pdf_url"],
            translator=translator_id,
            translator_kind=provider.kind,
        )
        done += 1
        # Tiny pacing buffer; the API rate-limit is generous but free-tier
        # spikes can throttle. 50ms keeps things polite without slowing
        # the wall-clock perceptibly.
        time.sleep(0.05)

    print(f"[02c] translated: {done}, skipped: {len(skipped)}", file=sys.stderr)
    if skipped:
        for lang, slug, err in skipped[:20]:
            print(f"  skip {lang}/{slug}: {err[:120]}", file=sys.stderr)
        if len(skipped) > 20:
            print(f"  … and {len(skipped) - 20} more", file=sys.stderr)
        print("[02c] rerun this stage to retry the skipped entries.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
