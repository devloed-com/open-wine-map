"""Translate SK per-AOC terroir-fact bullets (SK → en/fr/es/nl).

SK analog of `scripts/si/02e_translate_terroir_facts.py`. Same bounded-
narrative-layer rules — cache per source SHA, attribution preserved,
round-trip flow for forks without API access — but the source language
is Slovak (the JEDNOTNÝ DOKUMENT is canonical for SK wines), so the
locale set is en/fr/es/nl.

Reads:  raw/terroir-facts/<slug>.json  (where country == "sk")
Writes: raw/translations/terroir-facts/<lang>/<slug>.json
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, llm_json, providers, roundtrip  # noqa: E402

TERROIR_FACTS = ROOT / "raw" / "terroir-facts"
CACHE_ROOT = ROOT / "raw" / "translations" / "terroir-facts"

TARGET_LOCALES = ("en", "fr", "es", "nl")
LOCALE_NAME = {"en": "English", "fr": "French", "es": "Spanish", "nl": "Dutch"}


SYSTEM_PROMPT = """You translate short Slovak bullets describing a Slovak wine appellation's terroir, history, and wine character into {lang_name}. The bullets come from the EU "jednotný dokument" / špecifikácia výrobku and are aimed at sommelier students and wine enthusiasts.

Rules:
- Output a JSON array of strings, one translated bullet per input bullet, in the SAME order. The array length must equal the input list length.
- Preserve Slovak proper nouns verbatim: appellation names ("Vinohradnícka oblasť Tokaj", "Tokajské víno", "Malokarpatská", "Južnoslovenská", "Stredoslovenská", "Východoslovenská", "Nitrianska", "Karpatská perla", "Skalický rubín", "Slovenská"), wine-region names ("Malokarpatská", "Južnoslovenská", "Nitrianska", "Stredoslovenská", "Východoslovenská", "Tokaj"), commune, vinohradnícky rajón and vineyard-site names, grape variety names ("Frankovka modrá", "Veltlínske zelené", "Devín", "Dunaj", "Hron", "Rimava", "Váh", "Nitria", "Furmint", "Lipovina", "Muškát žltý", "Svätovavrinecké", "Modrý Portugal", "Rizling vlašský", "Rizling rýnsky", "Tramín červený", "Pesecká leánka", "Müller Thurgau", "Cabernet Sauvignon"), named geological formations and soil types ("spraš", "černozem", "ílovica", "vápenec", "dolomit", "andezit", "ryolit", "vulkanická pôda", "hlina"), named climatic features ("panónske podnebie", "kontinentálne podnebie", "vplyv Karpát"), and Slovak wine-law / Tokaj-predikát terms ("vinohradnícka oblasť", "vinohradnícky rajón", "neskorý zber", "výber z hrozna", "bobuľový výber", "hrozienkový výber", "ľadové víno", "slamové víno", "tokajský výber", "tokajská esencia", "samorodné", "CHOP", "CHZO").
- Geological era labels: translate to the standard {lang_name} form when one exists. When unsure, keep the Slovak form.
- Translate descriptive vocabulary naturally for a wine-literate reader.
- Match each source bullet's length and register; do not add commentary, footnotes, or explanations.
- Output ONLY the JSON array, no preface, no markdown fences."""


# ─────────────────────────────────────────────────────────────── helpers ──


def facts_sha(facts: list[dict]) -> str:
    """SHA over the source bullet texts joined; used for cache invalidation."""
    blob = "\n".join((f.get("bullet") or "") for f in facts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def parse_array(raw: str, expected_len: int) -> list[str] | None:
    arr, _err = llm_json.parse_str_array(raw, expected_len)
    return arr


# ────────────────────────────────────────────────────────── cache + jobs ──


def cache_path(lang: str, slug: str) -> Path:
    return CACHE_ROOT / lang / f"{slug}.json"


def load_existing(lang: str, slug: str) -> dict | None:
    return cache.read_json_or_none(cache_path(lang, slug))


def write_cache(
    *,
    lang: str,
    slug: str,
    src_facts: list[dict],
    translated_bullets: list[str],
    src_data: dict,
    translator: str,
    translator_kind: str,
) -> None:
    facts_out = [
        {
            "bullet": translated_bullets[i],
            "subsection": src_facts[i].get("subsection", "facteurs_naturels"),
            "provenance": src_facts[i].get("provenance", "cahier"),
        }
        for i in range(len(src_facts))
    ]
    payload = {
        "country": "sk",
        "source_lang": "sk",
        "slug": slug,
        "lang": lang,
        "facts": facts_out,
        "source_facts_sha": facts_sha(src_facts),
        "wiki_source_url": src_data.get("wiki_source_url") or "",
        "cahier_source_pdf_url": src_data.get("cahier_source_pdf_url") or "",
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


def _load_si_source(path: Path) -> dict | None:
    """Return SI terroir-facts payload for `path` if it has facts; else None."""
    d = cache.read_json_or_none(path)
    if not d or not d.get("facts"):
        return None
    if d.get("country") != "sk":
        return None
    return d


def enumerate_jobs(
    languages: tuple[str, ...], *, skip_cached: bool = True
) -> list[dict]:
    jobs: list[dict] = []
    for f in sorted(TERROIR_FACTS.glob("*.json")):
        if f.name.startswith("_") or f.name.startswith("manifest"):
            continue
        src = _load_si_source(f)
        if src is None:
            continue
        src_facts = src["facts"]
        sha = facts_sha(src_facts)
        for lang in languages:
            if skip_cached and _is_fresh_cache(load_existing(lang, src["slug"]), sha, len(src_facts)):
                continue
            jobs.append({
                "slug": src["slug"],
                "lang": lang,
                "src_facts": src_facts,
                "src_data": src,
                "sha": sha,
            })
    return jobs


# ──────────────────────────────────────────────────────────── extraction ──


def build_user_prompt(src_facts: list[dict]) -> str:
    lines = [f"{i + 1}. {f.get('bullet', '')}" for i, f in enumerate(src_facts)]
    return "Translate the following bullets:\n\n" + "\n".join(lines)


def translate_one(provider, job: dict) -> tuple[list[str] | None, str | None]:
    system = SYSTEM_PROMPT.format(lang_name=LOCALE_NAME[job["lang"]])
    user = build_user_prompt(job["src_facts"])
    try:
        raw = provider.chat(system=system, user=user, max_tokens=2000, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return None, f"call: {e}"
    parsed = parse_array(raw, len(job["src_facts"]))
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
            "source_lang": "sk",
            "source_facts_sha": j["sha"],
            "source_bullets": [f.get("bullet", "") for f in j["src_facts"]],
            "translated_bullets": [],
        }
        for j in jobs
    ]
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lang": "sk",
        "languages": list(languages),
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    counts = {loc: sum(1 for j in jobs if j["lang"] == loc) for loc in languages}
    pretty = ", ".join(f"{loc}={n}" for loc, n in counts.items())
    print(f"[02e/sk] wrote {out_path} ({len(items)} items: {pretty})", file=sys.stderr)
    return 0


def _import_one(it: dict, src_index: dict, *, translator_id: str, translator_kind: str) -> str:
    slug = it.get("slug") or ""
    lang = it.get("lang") or ""
    if lang not in TARGET_LOCALES:
        return "skipped_unknown_lang"
    src = src_index.get(slug)
    if src is None:
        return "skipped_unknown_slug"
    src_facts = src.get("facts") or []
    if not src_facts:
        return "skipped_unknown_slug"
    if it.get("source_facts_sha") and it["source_facts_sha"] != facts_sha(src_facts):
        print(
            f"  skip {lang}/{slug}: source SHA mismatch — re-run --emit-todo to refresh",
            file=sys.stderr,
        )
        return "skipped_sha"
    translated = it.get("translated_bullets") or []
    if len(translated) != len(src_facts) or any(not (s or "").strip() for s in translated):
        return "skipped_empty"
    write_cache(
        lang=lang,
        slug=slug,
        src_facts=src_facts,
        translated_bullets=[s.strip() for s in translated],
        src_data=src,
        translator=translator_id,
        translator_kind=translator_kind,
    )
    return "wrote"


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1
    src_index: dict[str, dict] = {}
    for f in TERROIR_FACTS.glob("*.json"):
        if f.name.startswith("_") or f.name.startswith("manifest"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if d.get("country") == "sk":
            src_index[d["slug"]] = d
    counts = {"wrote": 0, "skipped_sha": 0, "skipped_empty": 0,
              "skipped_unknown_slug": 0, "skipped_unknown_lang": 0}
    for it in payload.get("items") or []:
        outcome = _import_one(
            it, src_index, translator_id=translator_id, translator_kind=translator_kind,
        )
        counts[outcome] += 1
    pretty = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    print(f"[02e/sk] {pretty}", file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────  main ──


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama", choices=("anthropic", "mistral", "ollama", "manual"),
        help="translation backend (default ollama)",
    )
    ap.add_argument(
        "--model", default=None,
        help=(
            "model id (default per provider: "
            f"anthropic={providers.DEFAULT_ANTHROPIC_MODEL}, "
            f"mistral={providers.DEFAULT_MISTRAL_MODEL}, "
            f"ollama={providers.DEFAULT_OLLAMA_MODEL})"
        ),
    )
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument(
        "--lang", action="append", choices=TARGET_LOCALES, default=None,
        help="restrict to a specific locale (repeatable); default: all 4",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap on jobs (0 = all)")
    ap.add_argument(
        "--workers", type=int, default=1,
        help="concurrent (lang, slug) pairs (default 1, keep 1 for Ollama)",
    )
    ap.add_argument("--refresh", action="store_true", help="re-translate even if cached")
    ap.add_argument(
        "--batch", action="store_true",
        help="submit all work to the provider Batch API (--provider anthropic|"
             "mistral; ~50%% cheaper); resumes an in-flight batch on re-run",
    )
    roundtrip.add_arguments(ap)
    return ap


def _check_inputs() -> int:
    if not TERROIR_FACTS.exists():
        print(
            "error: raw/terroir-facts is missing — run "
            "scripts/sk/02d_extract_terroir_facts.py first",
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


def _process_one_job(provider, model_id: str, job: dict) -> tuple[bool, str | None]:
    translated, err = translate_one(provider, job)
    if err or translated is None:
        return False, err or "unknown"
    write_cache(
        lang=job["lang"],
        slug=job["slug"],
        src_facts=job["src_facts"],
        translated_bullets=translated,
        src_data=job["src_data"],
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
        for job in tqdm(jobs, desc="translate-sk", leave=False):
            ok, err = _process_one_job(provider, model_id, job)
            if ok:
                done += 1
            else:
                skipped.append((job["lang"], job["slug"], err or "unknown"))
            time.sleep(0.05)
        return done, skipped

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_one_job, provider, model_id, j): j for j in jobs}
        for fut in tqdm(as_completed(futures), total=len(jobs), desc="translate-sk", leave=False):
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


def _run_batch(args, languages: tuple[str, ...]) -> int:
    if not batch.supports(args.provider):
        print("error: --batch requires --provider anthropic|mistral", file=sys.stderr)
        return 1
    model_id = args.model or batch.default_model(args.provider)
    jobs = enumerate_jobs(languages, skip_cached=not args.refresh)
    if args.limit:
        jobs = jobs[: args.limit]
    if not jobs:
        print("[02e/sk] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02e/sk] batch: {len(jobs)} translations (provider={args.provider}, "
          f"model={model_id}, locales={','.join(languages)})", file=sys.stderr)
    batch.run_two_pass(
        provider=args.provider, model=model_id,
        sidecar=ROOT / "raw" / ".batch" / "02e-sk.json",
        run_loop=lambda prov: _run_translation_loop(prov, model_id, jobs, workers=1),
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    rc = _check_inputs()
    if rc:
        return rc

    languages = tuple(args.lang) if args.lang else TARGET_LOCALES

    sub_rc = _dispatch_emit_or_import(args, languages)
    if sub_rc is not None:
        return sub_rc

    if args.batch:
        return _run_batch(args, languages)

    jobs = enumerate_jobs(languages, skip_cached=not args.refresh)
    if args.limit:
        jobs = jobs[: args.limit]

    if not jobs:
        print("[02e/sk] nothing to do — all caches up to date.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        for j in jobs:
            print(f"  missing: {j['lang']}/{j['slug']}.json", file=sys.stderr)
        print(
            f"[02e/sk] manual provider: {len(jobs)} entries need translation. "
            f"Use --emit-todo PATH, fill in translated_bullets, then --import "
            f"PATH --translator-id <id> to write cache files.",
            file=sys.stderr,
        )
        return 1

    workers = max(1, args.workers)
    print(
        f"[02e/sk] {len(jobs)} translations to fetch "
        f"(provider={args.provider}, model={model_id}, "
        f"locales={','.join(languages)}, workers={workers})",
        file=sys.stderr,
    )
    done, skipped = _run_translation_loop(provider, model_id, jobs, workers=workers)
    print(f"[02e/sk] translated: {done}, skipped: {len(skipped)}", file=sys.stderr)
    if skipped:
        for lang, slug, err in skipped[:20]:
            print(f"  skip {lang}/{slug}: {err[:160]}", file=sys.stderr)
        print("[02e/sk] rerun this stage to retry the skipped entries.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
