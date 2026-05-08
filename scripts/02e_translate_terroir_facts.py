"""Translate per-AOC terroir-fact bullets (FR → en/es/nl).

Pipeline stage 02e. Sister stage to 02c (summary translation) and 02d
(bullet extraction). Same bounded-narrative-layer rules: cache per-source
SHA, attribution preserved, round-trip flow for forks without API access.

Reads:  raw/terroir-facts/*.json
Writes: raw/translations/terroir-facts/<lang>/<slug>.json

Per locale cache shape:
  - slug, lang
  - facts: list of {bullet, subsection, provenance} mirroring the FR
    structure but with bullet text in `lang`. Index/order matches the FR
    cache so render-time overlay is positional.
  - source_facts_sha: sha256 of the FR bullets joined with "\n"
  - wiki_source_url, cahier_source_pdf_url: copied from the FR cache so
    the per-locale UI can render the same attribution links without
    re-reading the FR file
  - translator, translator_kind, fetched_at

Providers:
  anthropic  Anthropic Messages API (recommended for production).
             Default model: claude-haiku-4-5.
  ollama     Local Ollama HTTP API. Default model: mistral-small3.2.
  manual     No network calls. With --emit-todo dumps every untreated
             (lang, slug) pair into one JSON for offline / external
             processing. With --import reads back filled-in translations
             and writes per-locale cache entries.

Re-translates only entries whose source_facts_sha changed (or are
missing). Pass --refresh to force re-translate everything.
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

TERROIR_FACTS = ROOT / "raw" / "terroir-facts"
CACHE_ROOT = ROOT / "raw" / "translations" / "terroir-facts"

TARGET_LOCALES = ("en", "es", "nl")
LOCALE_NAME = {"en": "English", "es": "Spanish", "nl": "Dutch"}


SYSTEM_PROMPT = """You translate short French bullets describing a French wine appellation's terroir, history, and wine character into {lang_name}. The bullets come from an INAO cahier des charges and are aimed at sommelier students and wine enthusiasts.

Rules:
- Output a JSON array of strings, one translated bullet per input bullet, in the SAME order. The array length must equal the input list length.
- Preserve French proper nouns verbatim: appellation names, region names, commune names, grape variety names, named geological formations (e.g. "Marnes à exogyra virgula", "Calcaire du Barrois", "Poudingue de Jurançon", "tuffeau"), named winds (e.g. "Mistral", "Bise", "Tramontane", "foehn"), local soil/landscape names ("caillottes", "chailloux", "restanques", "chaillées").
- Geological era labels: translate to the standard {lang_name} form if it exists (e.g. Kimméridgien → Kimmeridgian in EN, Kimmeridgiense in ES). When unsure, keep the French form.
- Translate descriptive vocabulary naturally for a wine-literate reader.
- Match each source bullet's length and register; do not add commentary, footnotes, or explanations.
- Output ONLY the JSON array, no preface, no markdown fences."""


# ─────────────────────────────────────────────────────────────── helpers ──


def facts_sha(facts: list[dict]) -> str:
    """SHA over the FR bullet texts joined; used for cache invalidation."""
    blob = "\n".join((f.get("bullet") or "") for f in facts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def parse_array(raw: str, expected_len: int) -> list[str] | None:
    """Strip ```json fences, parse, validate length. None on failure."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        arr = json.loads(cleaned)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(arr, list) or len(arr) != expected_len:
        return None
    return [str(x).strip() for x in arr]


# ────────────────────────────────────────────────────────── cache + jobs ──


def cache_path(lang: str, slug: str) -> Path:
    return CACHE_ROOT / lang / f"{slug}.json"


def load_existing(lang: str, slug: str) -> dict | None:
    return cache.read_json_or_none(cache_path(lang, slug))


def write_cache(
    *,
    lang: str,
    slug: str,
    fr_facts: list[dict],
    translated_bullets: list[str],
    fr_data: dict,
    translator: str,
    translator_kind: str,
) -> None:
    facts_out = [
        {
            "bullet": translated_bullets[i],
            "subsection": fr_facts[i].get("subsection", "facteurs_naturels"),
            "provenance": fr_facts[i].get("provenance", "cahier"),
        }
        for i in range(len(fr_facts))
    ]
    payload = {
        "slug": slug,
        "lang": lang,
        "facts": facts_out,
        "source_facts_sha": facts_sha(fr_facts),
        "wiki_source_url": fr_data.get("wiki_source_url") or "",
        "cahier_source_pdf_url": fr_data.get("cahier_source_pdf_url") or "",
        "translator": translator,
        "translator_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cache.write_json(cache_path(lang, slug), payload)


def _is_fresh_cache(existing: dict | None, sha: str, expected_len: int) -> bool:
    return bool(
        existing
        and existing.get("source_facts_sha") == sha
        and len(existing.get("facts") or []) == expected_len
    )


def _load_fr_cache(path: Path) -> dict | None:
    d = cache.read_json_or_none(path)
    return d if d and d.get("facts") else None


def enumerate_jobs(
    languages: tuple[str, ...], *, skip_cached: bool = True
) -> list[dict]:
    """Per-(lang, slug) jobs needing translation. A job is included when the
    target cache is missing or its source_facts_sha doesn't match the FR
    cache's current bullets."""
    jobs: list[dict] = []
    for f in sorted(TERROIR_FACTS.glob("*.json")):
        if f.name.startswith("_") or f.name == "manifest.json":
            continue
        fr = _load_fr_cache(f)
        if fr is None:
            continue
        fr_facts = fr["facts"]
        sha = facts_sha(fr_facts)
        for lang in languages:
            if skip_cached and _is_fresh_cache(load_existing(lang, fr["slug"]), sha, len(fr_facts)):
                continue
            jobs.append({
                "slug": fr["slug"],
                "lang": lang,
                "fr_facts": fr_facts,
                "fr_data": fr,
                "sha": sha,
            })
    return jobs


# ──────────────────────────────────────────────────────────── extraction ──


def build_user_prompt(fr_facts: list[dict]) -> str:
    """Numbered list of FR bullets — order is the contract with the model."""
    lines = [f"{i + 1}. {f.get('bullet', '')}" for i, f in enumerate(fr_facts)]
    return "Translate the following bullets:\n\n" + "\n".join(lines)


def translate_one(provider, job: dict) -> tuple[list[str] | None, str | None]:
    system = SYSTEM_PROMPT.format(lang_name=LOCALE_NAME[job["lang"]])
    user = build_user_prompt(job["fr_facts"])
    try:
        raw = provider.chat(system=system, user=user, max_tokens=2000, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return None, f"call: {e}"
    parsed = parse_array(raw, len(job["fr_facts"]))
    if parsed is None:
        return None, f"parse_or_length_mismatch: {raw[:200]!r}"
    return parsed, None


# ─────────────────────────────────────────────────── round-trip (manual) ──


def emit_todo(out_path: Path, *, languages: tuple[str, ...], skip_cached: bool) -> int:
    jobs = enumerate_jobs(languages, skip_cached=skip_cached)
    items = [
        {
            "slug": j["slug"],
            "lang": j["lang"],
            "source_facts_sha": j["sha"],
            "source_bullets": [f.get("bullet", "") for f in j["fr_facts"]],
            "translated_bullets": [],
        }
        for j in jobs
    ]
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "languages": list(languages),
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    counts = {l: sum(1 for j in jobs if j["lang"] == l) for l in languages}
    pretty = ", ".join(f"{l}={n}" for l, n in counts.items())
    print(f"[02e] wrote {out_path} ({len(items)} items: {pretty})", file=sys.stderr)
    return 0


def _import_one(it: dict, fr_index: dict, *, translator_id: str, translator_kind: str) -> str:
    slug = it.get("slug") or ""
    lang = it.get("lang") or ""
    if lang not in TARGET_LOCALES:
        return "skipped_unknown_lang"
    fr = fr_index.get(slug)
    if fr is None:
        return "skipped_unknown_slug"
    fr_facts = fr.get("facts") or []
    if not fr_facts:
        return "skipped_unknown_slug"
    if it.get("source_facts_sha") and it["source_facts_sha"] != facts_sha(fr_facts):
        print(
            f"  skip {lang}/{slug}: source SHA mismatch — re-run --emit-todo to refresh",
            file=sys.stderr,
        )
        return "skipped_sha"
    translated = it.get("translated_bullets") or []
    if len(translated) != len(fr_facts) or any(not (s or "").strip() for s in translated):
        return "skipped_empty"
    write_cache(
        lang=lang,
        slug=slug,
        fr_facts=fr_facts,
        translated_bullets=[s.strip() for s in translated],
        fr_data=fr,
        translator=translator_id,
        translator_kind=translator_kind,
    )
    return "wrote"


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1
    fr_index: dict[str, dict] = {}
    for f in TERROIR_FACTS.glob("*.json"):
        if f.name.startswith("_") or f.name == "manifest.json":
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        fr_index[d["slug"]] = d
    counts = {"wrote": 0, "skipped_sha": 0, "skipped_empty": 0,
              "skipped_unknown_slug": 0, "skipped_unknown_lang": 0}
    for it in payload.get("items") or []:
        outcome = _import_one(
            it, fr_index, translator_id=translator_id, translator_kind=translator_kind,
        )
        counts[outcome] += 1
    pretty = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    print(f"[02e] {pretty}", file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────  main ──


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="anthropic", choices=("anthropic", "ollama", "manual"),
        help="translation backend (default: anthropic)",
    )
    ap.add_argument(
        "--model", default=None,
        help=(
            "model id (default per provider: "
            f"anthropic={providers.DEFAULT_ANTHROPIC_MODEL}, ollama={providers.DEFAULT_OLLAMA_MODEL})"
        ),
    )
    ap.add_argument(
        "--ollama-url", default=providers.DEFAULT_OLLAMA_URL,
        help="Ollama chat endpoint (default: localhost:11434)",
    )
    ap.add_argument(
        "--lang", action="append", choices=TARGET_LOCALES, default=None,
        help="restrict to a specific locale (repeatable); default: all 3",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap on jobs (0 = all)")
    ap.add_argument(
        "--workers", type=int, default=1,
        help=(
            "concurrent (lang, slug) pairs to translate (default 1). For "
            "Ollama, the server must be started with OLLAMA_NUM_PARALLEL >= "
            "workers (current default is 4) or extra requests just queue. "
            "For Anthropic, respect your account's RPM/concurrency limits."
        ),
    )
    ap.add_argument("--refresh", action="store_true", help="re-translate even if cached")
    roundtrip.add_arguments(ap)
    return ap


def _check_inputs() -> int:
    if not TERROIR_FACTS.exists():
        print(
            "error: raw/terroir-facts is missing — run scripts/02d_extract_terroir_facts.py first",
            file=sys.stderr,
        )
        return 1
    return 0


def _dispatch_emit_or_import(args, languages: tuple[str, ...]) -> int | None:
    rc = roundtrip.validate_emit_import(args)
    if rc is not None:
        return rc
    if args.emit_todo:
        return emit_todo(Path(args.emit_todo), languages=languages, skip_cached=not args.all)
    if args.import_path:
        return import_todo(
            Path(args.import_path),
            translator_id=args.translator_id,
            translator_kind=args.translator_kind,
        )
    return None


def _make_provider(args) -> tuple[object | None, str]:
    return providers.make_provider(args.provider, model=args.model, ollama_url=args.ollama_url)


def _print_manual_listing(jobs: list[dict]) -> int:
    for j in jobs:
        print(f"  missing: {j['lang']}/{j['slug']}.json", file=sys.stderr)
    print(
        f"[02e] manual provider: {len(jobs)} entries need translation. "
        f"Use --emit-todo PATH, fill in translated_bullets, then --import PATH "
        f"--translator-id <id> to write cache files.",
        file=sys.stderr,
    )
    return 1


def _process_one_job(provider, model_id: str, job: dict) -> tuple[bool, str | None]:
    """Translate one (lang, slug) job + write cache. Returns (success, error_message)."""
    translated, err = translate_one(provider, job)
    if err or translated is None:
        return False, err or "unknown"
    write_cache(
        lang=job["lang"],
        slug=job["slug"],
        fr_facts=job["fr_facts"],
        translated_bullets=translated,
        fr_data=job["fr_data"],
        translator=model_id,
        translator_kind=provider.kind,
    )
    return True, None


def _run_translation_loop(
    provider, model_id: str, jobs: list[dict], workers: int = 1,
) -> tuple[int, list[tuple[str, str, str]]]:
    done = 0
    skipped: list[tuple[str, str, str]] = []
    if workers <= 1:
        for job in tqdm(jobs, desc="translate", leave=False):
            ok, err = _process_one_job(provider, model_id, job)
            if ok:
                done += 1
            else:
                skipped.append((job["lang"], job["slug"], err or "unknown"))
            time.sleep(0.05)
        return done, skipped

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_one_job, provider, model_id, j): j for j in jobs}
        for fut in tqdm(as_completed(futures), total=len(jobs), desc="translate", leave=False):
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


def main() -> int:
    args = _build_argparser().parse_args()
    rc = _check_inputs()
    if rc:
        return rc

    languages = tuple(args.lang) if args.lang else TARGET_LOCALES

    sub_rc = _dispatch_emit_or_import(args, languages)
    if sub_rc is not None:
        return sub_rc

    jobs = enumerate_jobs(languages, skip_cached=not args.refresh)
    if args.limit:
        jobs = jobs[: args.limit]

    if not jobs:
        print("[02e] nothing to do — all caches up to date.", file=sys.stderr)
        return 0

    provider, model_id = _make_provider(args)
    if provider is None:
        return _print_manual_listing(jobs)

    workers = max(1, args.workers)
    print(
        f"[02e] {len(jobs)} translations to fetch "
        f"(provider={args.provider}, model={model_id}, "
        f"locales={','.join(languages)}, workers={workers})",
        file=sys.stderr,
    )
    done, skipped = _run_translation_loop(provider, model_id, jobs, workers=workers)
    print(f"[02e] translated: {done}, skipped: {len(skipped)}", file=sys.stderr)
    if skipped:
        for lang, slug, err in skipped[:20]:
            print(f"  skip {lang}/{slug}: {err[:160]}", file=sys.stderr)
        if len(skipped) > 20:
            print(f"  … and {len(skipped) - 20} more", file=sys.stderr)
        print("[02e] rerun this stage to retry the skipped entries.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
