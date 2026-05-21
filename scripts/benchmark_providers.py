"""Compare LLM providers/models on the extraction + translation stages.

This is a benchmark harness, not a pipeline stage. It runs the *real*
stage-02d (terroir-fact extraction), stage-02c (summary translation), and
stage-02e (terroir-bullet translation) prompt logic — imported verbatim
from the pipeline scripts — against a fixed cross-language sample of
appellations, once per candidate, and records per-call latency and token
usage. Stage-02e translates each candidate's *own* extracted bullets, so
the facts-translation column is the same model end to end.

A candidate names a (provider, model) pair plus a *mode* for each task:

  live           call the model now, instrumented (latency + tokens).
  cache          read the pipeline's already-computed output from disk
                 (raw/terroir-facts/ for extraction, raw/translations/
                 summaries/ for translation). No LLM call, no cost.
  cache-or-live  read the cache; fall back to a live call on a miss.
  skip           don't run this task for this candidate.

This lets the slow local-Ollama extraction reuse the pipeline's existing
mistral-small3.2 output instead of a multi-hour re-run, and surfaces the
human 02c round-trip translations as a reference row.

It NEVER writes to the real pipeline caches. The live extraction path
calls the pure primitives (`extract_one_aoc` for FR, `_process_subsection`
for ES/PT/IT) and skips the country scripts' `_process_record`, which
would persist a cache file. All output lands under `raw/benchmark/`:

  raw/benchmark/results.json   structured results (machine-readable)
  raw/benchmark/REPORT.md      side-by-side comparison (human review)

Usage
-----
  python scripts/benchmark_providers.py --list
  python scripts/benchmark_providers.py --candidate ollama/mistral-small3.2
  python scripts/benchmark_providers.py --candidate anthropic --candidate mistral
  python scripts/benchmark_providers.py --report-only

API keys are read from the environment, or from a `.env` file in the
repo root (KEY=VALUE lines) if present. Runs are incremental: each
candidate is merged into results.json as it finishes.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import providers  # noqa: E402
from _lib.summaries import derive_summary  # noqa: E402

# ─────────────────────────────────────────────────────────── configuration ──

# The sample: ~10 sources spanning all four source languages, Chablis
# included. Each entry is (country, slug). Verified at startup.
SAMPLE: list[tuple[str, str]] = [
    ("fr", "chablis"),
    ("fr", "chateauneuf-du-pape"),
    ("fr", "sancerre"),
    ("es", "priorat"),
    ("es", "montsant"),
    ("es", "rioja"),
    ("pt", "douro"),
    ("pt", "vinho-verde"),
    ("it", "chianti"),
    ("it", "prosecco"),
]

# Translation target languages (en + nl are valid 02c targets for fr/es/pt/it).
TARGET_LANGS: tuple[str, ...] = ("en", "nl")

# The candidate matrix. Each value: provider, model, and a per-task mode
# (live / cache / cache-or-live / skip — see the module docstring).
#
#   ollama/mistral-small3.2 — extraction reuses the pipeline's existing
#     stage-02d output (raw/terroir-facts/, mistral-small3.2); translation
#     is run live (fast, no cached Ollama translations exist).
#   manual/human-roundtrip  — the human 02c round-trip translations cached
#     in raw/translations/summaries/. A reference row; only the slugs that
#     have been hand-translated show a value.
#   gpt-oss:20b / llama3.1:8b are omitted — no cached extraction, and a
#     live extraction sweep takes ~hours on this machine. Add them back
#     with extraction="live" if you want to pay that cost.
CANDIDATES: dict[str, dict] = {
    "ollama/mistral-small3.2": {
        "provider": "ollama", "model": "mistral-small3.2",
        "extraction": "cache", "translation": "live", "facts": "cache",
    },
    "anthropic/haiku-4-5": {
        "provider": "anthropic", "model": "claude-haiku-4-5",
        "extraction": "live", "translation": "live", "facts": "live",
    },
    "anthropic/sonnet-4-6": {
        "provider": "anthropic", "model": "claude-sonnet-4-6",
        "extraction": "live", "translation": "live", "facts": "live",
    },
    "anthropic/opus-4-7": {
        "provider": "anthropic", "model": "claude-opus-4-7",
        "extraction": "live", "translation": "live", "facts": "live",
    },
    "mistral/large": {
        "provider": "mistral", "model": "mistral-large-latest",
        "extraction": "live", "translation": "live", "facts": "live",
    },
    "mistral/medium-3.5": {
        "provider": "mistral", "model": "mistral-medium-latest",
        "extraction": "live", "translation": "live", "facts": "live",
    },
    "manual/human-roundtrip": {
        "provider": "cache", "model": "human (02c round-trip)",
        "extraction": "skip", "translation": "cache", "facts": "skip",
    },
}

# USD per 1M tokens, (input, output). APPROXIMATE — verify against the
# providers' current pricing pages before trusting the cost column.
# Models with no entry (Ollama / cache) are reported as free.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    "mistral-large-latest": (2.00, 6.00),
    "mistral-medium-latest": (0.40, 2.00),
}

OUT_DIR = ROOT / "raw" / "benchmark"
TERROIR_FACTS_DIR = ROOT / "raw" / "terroir-facts"
SUMMARIES_DIR = ROOT / "raw" / "translations" / "summaries"

# ───────────────────────────────────────────────────────────────── .env ──


def load_dotenv() -> None:
    """Populate os.environ from a repo-root .env (KEY=VALUE lines). Existing
    environment variables win."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# ─────────────────────────────────────────── pipeline modules (importlib) ──

# Stage scripts are named `02c_*.py` / `02d_*.py` — not importable as normal
# modules (leading digit). Load by path so the benchmark runs the exact
# pipeline prompt logic.


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


EXTRACT_MODS = {
    "fr": _load("bench_02d_fr", "scripts/02d_extract_terroir_facts.py"),
    "es": _load("bench_02d_es", "scripts/es/02d_extract_terroir_facts.py"),
    "pt": _load("bench_02d_pt", "scripts/pt/02d_extract_terroir_facts.py"),
    "it": _load("bench_02d_it", "scripts/it/02d_extract_terroir_facts.py"),
}
C02 = _load("bench_02c", "scripts/02c_translate_summaries.py")
E02_MODS = {
    "fr": _load("bench_02e_fr", "scripts/02e_translate_terroir_facts.py"),
    "es": _load("bench_02e_es", "scripts/es/02e_translate_terroir_facts.py"),
    "pt": _load("bench_02e_pt", "scripts/pt/02e_translate_terroir_facts.py"),
    "it": _load("bench_02e_it", "scripts/it/02e_translate_terroir_facts.py"),
}

# ────────────────────────────────────── instrumented provider subclasses ──

RETRY_ATTEMPTS = 4
RETRY_BACKOFF_S = 8


def _retry(fn):
    """Call fn(); on any exception retry up to RETRY_ATTEMPTS times with
    linear backoff. Transient API overload (HTTP 429 / 529) is the common
    case on a long benchmark run."""
    last: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_BACKOFF_S * attempt
                print(f"    retry {attempt}/{RETRY_ATTEMPTS - 1} after "
                      f"{type(e).__name__}: {str(e)[:100]} — sleeping {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise last  # type: ignore[misc]


# Subclass the pipeline providers and override chat() to time the call and
# capture token usage (the production chat() discards both). Each call
# appends a {latency_s, input_tokens, output_tokens} record to .calls.
# Retry/backoff is the benchmark's own (SDK auto-retry is disabled below)
# so a "successful" call's recorded latency is one clean attempt.


class InstrAnthropic(providers.AnthropicProvider):
    def __init__(self, model: str):
        super().__init__(model)
        self.client = self.client.with_options(max_retries=0)
        self.calls: list[dict] = []

    def reset(self) -> None:
        self.calls = []

    def chat(self, *, system: str, user: str, max_tokens: int = 1024, **_: object) -> str:
        def _once():
            t0 = time.perf_counter()
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg, time.perf_counter() - t0

        msg, dt = _retry(_once)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        self.calls.append({
            "latency_s": round(dt, 3),
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        })
        return text


class InstrMistral(providers.MistralProvider):
    def __init__(self, model: str, url: str = providers.DEFAULT_MISTRAL_URL):
        super().__init__(model, url=url)
        self.calls: list[dict] = []

    def reset(self) -> None:
        self.calls = []

    def chat(self, *, system: str, user: str, max_tokens: int = 1024, **_: object) -> str:
        def _once():
            t0 = time.perf_counter()
            r = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=providers.MISTRAL_TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json(), time.perf_counter() - t0

        body, dt = _retry(_once)
        usage = body.get("usage") or {}
        self.calls.append({
            "latency_s": round(dt, 3),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        })
        return body["choices"][0]["message"]["content"].strip()


class InstrOllama(providers.OllamaProvider):
    def __init__(self, model: str, url: str = providers.DEFAULT_OLLAMA_URL):
        super().__init__(model, url=url)
        self.calls: list[dict] = []

    def reset(self) -> None:
        self.calls = []

    def chat(self, *, system: str, user: str, num_ctx: int = 4096, **_: object) -> str:
        def _once():
            t0 = time.perf_counter()
            r = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_ctx": num_ctx},
                },
                timeout=providers.OLLAMA_TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json(), time.perf_counter() - t0

        body, dt = _retry(_once)
        self.calls.append({
            "latency_s": round(dt, 3),
            "input_tokens": body.get("prompt_eval_count", 0),
            "output_tokens": body.get("eval_count", 0),
        })
        return body["message"]["content"].strip()


def make_instrumented(provider: str, model: str, *, ollama_url: str, mistral_url: str):
    if provider == "anthropic":
        return InstrAnthropic(model)
    if provider == "mistral":
        return InstrMistral(model, url=mistral_url)
    if provider == "ollama":
        return InstrOllama(model, url=ollama_url)
    raise ValueError(f"unknown provider: {provider}")


# ─────────────────────────────────────────────────────── live task runs ──

_targets_cache: dict[str, dict] = {}


def _country_records(country: str) -> dict:
    """Slug -> record index for one country's 02d collect_targets(). Memoised."""
    if country not in _targets_cache:
        mod = EXTRACT_MODS[country]
        _targets_cache[country] = {r["slug"]: r for r in mod.collect_targets()}
    return _targets_cache[country]


def run_extraction(provider, model_id: str, country: str, slug: str) -> dict:
    """Run the real 02d extraction live. FR uses the pure `extract_one_aoc`;
    ES/PT/IT loop the pure `_process_subsection` (the countries'
    `_process_record` writes a cache file — deliberately skipped)."""
    provider.reset()
    t0 = time.perf_counter()
    if country == "fr":
        mod = EXTRACT_MODS["fr"]
        rec = json.loads((mod.EXTRACTED / f"{slug}.json").read_text())
        job = mod._job_from_record(rec)
        if job is None:
            return {"error": f"FR record {slug} not extractable (DGC or section too short)"}
        facts, errors = mod.extract_one_aoc(provider, job)
    else:
        mod = EXTRACT_MODS[country]
        rec = _country_records(country).get(slug)
        if rec is None:
            return {"error": f"{country}/{slug} absent from collect_targets()"}
        wiki_path = mod.WIKI_AOCS / f"{slug}.json"
        wiki_record = json.loads(wiki_path.read_text()) if wiki_path.exists() else {}
        facts, errors = [], []
        for sub in mod.SUBSECTIONS:
            kept, _dropped, err = mod._process_subsection(provider, model_id, rec, sub, wiki_record)
            if err:
                errors.append(f"{sub['key']}: {err}")
            for f in kept:
                f = dict(f)
                f["subsection"] = sub["key"]
                facts.append(f)
    wall = time.perf_counter() - t0
    calls = list(provider.calls)
    return {
        "source": "live",
        "facts": facts,
        "errors": errors,
        "calls": calls,
        "n_facts": len(facts),
        "n_calls": len(calls),
        "wall_s": round(wall, 2),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
    }


def run_translation(provider, country: str, slug: str) -> dict:
    """Run the real 02c summary translation live into TARGET_LANGS."""
    cfg = C02.SOURCE_CONFIG[country]
    rec = json.loads((cfg["source_dir"] / f"{slug}.json").read_text())
    text = derive_summary(rec)
    if not text:
        return {"error": f"{country}/{slug}: derive_summary() returned nothing"}
    out: dict = {"source": "live", "source_text": text, "langs": {}}
    for lang in TARGET_LANGS:
        provider.reset()
        t0 = time.perf_counter()
        try:
            translated = C02.translate_summary(
                provider, text=text, source_lang=country, target_lang=lang,
                source_document=cfg["source_document"],
            )
        except Exception as e:  # noqa: BLE001
            out["langs"][lang] = {"error": str(e)}
            continue
        wall = time.perf_counter() - t0
        call = provider.calls[-1] if provider.calls else {}
        out["langs"][lang] = {
            "text": translated,
            "wall_s": round(wall, 2),
            "input_tokens": call.get("input_tokens", 0),
            "output_tokens": call.get("output_tokens", 0),
        }
    return out


def run_facts_translation(provider, country: str, bullets: list[dict]) -> dict:
    """Translate one candidate's own extracted terroir bullets into
    TARGET_LANGS, live, via stage 02e's prompt for `country`. The whole
    bullet list is one call per language (02e's contract)."""
    if not bullets:
        return {"error": "no extracted bullets to translate"}
    mod = E02_MODS[country]
    out: dict = {"source": "live", "langs": {}}
    for lang in TARGET_LANGS:
        provider.reset()
        if country == "fr":
            job = {"fr_data": {"source_lang": "fr"}, "lang": lang, "fr_facts": bullets}
        else:
            job = {"lang": lang, "src_facts": bullets}
        t0 = time.perf_counter()
        try:
            translated, err = mod.translate_one(provider, job)
        except Exception as e:  # noqa: BLE001
            out["langs"][lang] = {"error": str(e)}
            continue
        wall = time.perf_counter() - t0
        if err or translated is None:
            out["langs"][lang] = {"error": err or "translate_one returned None"}
            continue
        call = provider.calls[-1] if provider.calls else {}
        out["langs"][lang] = {
            "bullets": [{"source": bullets[i].get("bullet", ""), "text": translated[i]}
                        for i in range(len(bullets))],
            "wall_s": round(wall, 2),
            "input_tokens": call.get("input_tokens", 0),
            "output_tokens": call.get("output_tokens", 0),
        }
    return out


# ─────────────────────────────────────────────────── cached task reads ──


def ingest_extraction_cache(slug: str) -> dict | None:
    """Read the pipeline's stage-02d output for `slug` from raw/terroir-facts/.
    Returns an extraction block (same shape as a live run, zero cost / no
    latency), or None when the slug has no cache file."""
    p = TERROIR_FACTS_DIR / f"{slug}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except (ValueError, OSError):
        return None
    facts = d.get("facts")
    if facts is None:
        return None
    return {
        "source": "cache",
        "cache_file": str(p.relative_to(ROOT)),
        "cache_translator": d.get("translator") or d.get("model"),
        "cache_translator_kind": d.get("translator_kind") or d.get("model_kind"),
        "facts": facts,
        "errors": [],
        "calls": [],
        "n_facts": len(facts),
        "n_calls": 0,
        "wall_s": None,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def ingest_translation_cache(slug: str) -> dict | None:
    """Read the pipeline's stage-02c output for `slug` from
    raw/translations/summaries/<lang>/. Returns a translation block, or None
    when no target language is cached for the slug."""
    langs: dict = {}
    source_text = ""
    for lang in TARGET_LANGS:
        p = SUMMARIES_DIR / lang / f"{slug}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        source_text = source_text or d.get("source_summary") or ""
        langs[lang] = {
            "text": d.get("summary") or "",
            "wall_s": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_translator": d.get("translator"),
            "cache_translator_kind": d.get("translator_kind"),
        }
    if not langs:
        return None
    return {"source": "cache", "source_text": source_text, "langs": langs}


def ingest_facts_translation_cache(slug: str) -> dict | None:
    """Read the pipeline's stage-02e output for `slug` from
    raw/translations/terroir-facts/<lang>/. Each translated bullet is paired
    with its source bullet from raw/terroir-facts/ (same order — 02e's
    contract). Returns None when nothing is cached."""
    src_p = TERROIR_FACTS_DIR / f"{slug}.json"
    if not src_p.exists():
        return None
    try:
        src_facts = json.loads(src_p.read_text()).get("facts")
    except (ValueError, OSError):
        return None
    if not src_facts:
        return None
    out: dict = {"source": "cache", "langs": {}}
    for lang in TARGET_LANGS:
        p = ROOT / "raw" / "translations" / "terroir-facts" / lang / f"{slug}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        tfacts = d.get("facts")
        if not tfacts:
            continue
        n = min(len(src_facts), len(tfacts))
        out["langs"][lang] = {
            "bullets": [{"source": src_facts[i].get("bullet", ""),
                         "text": tfacts[i].get("bullet", "")} for i in range(n)],
            "wall_s": None, "input_tokens": 0, "output_tokens": 0,
            "cache_translator": d.get("translator"),
            "cache_translator_kind": d.get("translator_kind"),
        }
    return out if out["langs"] else None


# ──────────────────────────────────────────────────────────────── costing ──


def cost_usd(model_id: str, in_tok: int, out_tok: int) -> float | None:
    price = PRICING.get(model_id)
    if not price:
        return None
    return in_tok / 1e6 * price[0] + out_tok / 1e6 * price[1]


# ──────────────────────────────────────────────────────────── run one cand ──


def _do_extraction(provider, model: str, country: str, slug: str, mode: str) -> dict:
    """Resolve one source's extraction per `mode` (cache / cache-or-live / live)."""
    if mode in ("cache", "cache-or-live"):
        cached = ingest_extraction_cache(slug)
        if cached is not None:
            return cached
        if mode == "cache-or-live":
            return run_extraction(provider, model, country, slug)
        return {"error": "not in raw/terroir-facts/ cache"}
    return run_extraction(provider, model, country, slug)


def _do_facts(provider, country: str, slug: str, bullets: list, mode: str) -> dict:
    """Resolve one source's bullet-translation per `mode`."""
    if mode in ("cache", "cache-or-live"):
        cached = ingest_facts_translation_cache(slug)
        if cached is not None:
            return cached
        if mode == "cache-or-live":
            return run_facts_translation(provider, country, bullets)
        return {"error": "not in raw/translations/terroir-facts/ cache"}
    return run_facts_translation(provider, country, bullets)


def run_candidate(label: str, *, tasks: tuple[str, ...], sample: list[tuple[str, str]],
                  prior: dict | None, ollama_url: str, mistral_url: str) -> dict:
    """Run the requested tasks for one candidate per its per-task mode. Tasks
    not in `tasks` are carried forward from `prior`, so a `--task facts` run
    keeps the existing extraction / summary-translation results."""
    spec = CANDIDATES[label]
    prov_name, model = spec["provider"], spec["model"]
    ext_mode = spec.get("extraction", "live")
    tr_mode = spec.get("translation", "live")
    facts_mode = spec.get("facts", "live")
    block: dict = {
        "provider": prov_name, "model": model,
        "modes": {"extraction": ext_mode, "translation": tr_mode, "facts": facts_mode},
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    prior_sources = (prior or {}).get("sources") or {}

    modes = [m for task, m in (("extraction", ext_mode), ("translation", tr_mode),
                               ("facts", facts_mode)) if task in tasks]
    needs_provider = prov_name != "cache" and any(m in ("live", "cache-or-live") for m in modes)

    provider = None
    if needs_provider:
        try:
            provider = make_instrumented(prov_name, model,
                                         ollama_url=ollama_url, mistral_url=mistral_url)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            block["error"] = str(e)
            print(f"  [{label}] SKIPPED: {e}", file=sys.stderr)
            return block

    sources: dict = {}
    for country, slug in sample:
        key = f"{country}/{slug}"
        entry: dict = dict(prior_sources.get(key) or {})  # carry forward untouched tasks

        if "extraction" in tasks and ext_mode != "skip":
            print(f"  [{label}] {key} extraction ({ext_mode})…", file=sys.stderr)
            try:
                entry["extraction"] = _do_extraction(provider, model, country, slug, ext_mode)
            except Exception as e:  # noqa: BLE001
                entry["extraction"] = {"error": f"{type(e).__name__}: {e}"}

        if "translation" in tasks and tr_mode != "skip":
            print(f"  [{label}] {key} translation ({tr_mode})…", file=sys.stderr)
            try:
                if tr_mode == "cache":
                    entry["translation"] = (ingest_translation_cache(slug)
                                            or {"error": "not in 02c translation cache"})
                else:
                    entry["translation"] = run_translation(provider, country, slug)
            except Exception as e:  # noqa: BLE001
                entry["translation"] = {"error": f"{type(e).__name__}: {e}"}

        if "facts" in tasks and facts_mode != "skip":
            print(f"  [{label}] {key} facts-translation ({facts_mode})…", file=sys.stderr)
            try:
                bullets = (entry.get("extraction") or {}).get("facts") or []
                entry["facts_translation"] = _do_facts(provider, country, slug, bullets, facts_mode)
            except Exception as e:  # noqa: BLE001
                entry["facts_translation"] = {"error": f"{type(e).__name__}: {e}"}

        sources[key] = entry
    block["sources"] = sources
    return block


# ────────────────────────────────────────────────────────── results.json ──


def load_results(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    return {"sample": [list(s) for s in SAMPLE], "target_langs": list(TARGET_LANGS),
            "results": {}}


def save_results(path: Path, data: dict) -> None:
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ───────────────────────────────────────────────────────── report builder ──


def _nums(xs: list) -> list[float]:
    return [x for x in xs if isinstance(x, (int, float))]


def _median(xs: list) -> float | None:
    vals = _nums(xs)
    return round(statistics.median(vals), 1) if vals else None


def _accumulate_langs(t: dict, prefix: str, task: dict) -> None:
    """Fold a translation-style task's per-language blocks into totals."""
    for lb in (task.get("langs") or {}).values():
        if "error" in lb:
            continue
        t[f"{prefix}_calls"] += 1
        t[f"{prefix}_in"] += lb.get("input_tokens", 0)
        t[f"{prefix}_out"] += lb.get("output_tokens", 0)
        t[f"{prefix}_lat"].append(lb.get("wall_s"))


def _candidate_totals(block: dict) -> dict:
    t = {"ext_calls": 0, "ext_in": 0, "ext_out": 0, "ext_lat": [], "ext_facts": 0,
         "tr_calls": 0, "tr_in": 0, "tr_out": 0, "tr_lat": [],
         "ft_calls": 0, "ft_in": 0, "ft_out": 0, "ft_lat": []}
    for entry in (block.get("sources") or {}).values():
        ext = entry.get("extraction") or {}
        if "error" not in ext:
            t["ext_calls"] += ext.get("n_calls", 0)
            t["ext_in"] += ext.get("input_tokens", 0)
            t["ext_out"] += ext.get("output_tokens", 0)
            t["ext_facts"] += ext.get("n_facts", 0)
            t["ext_lat"] += [c["latency_s"] for c in ext.get("calls", [])]
        _accumulate_langs(t, "tr", entry.get("translation") or {})
        _accumulate_langs(t, "ft", entry.get("facts_translation") or {})
    return t


def _cost_label(model: str, provider: str, in_tok: int, out_tok: int) -> str:
    if provider == "cache":
        return "n/a (human)"
    c = cost_usd(model, in_tok, out_tok)
    return "local (free)" if c is None else f"${c:.4f}"


def _speed_cell(median: float | None, mode: str) -> str:
    if median is not None:
        return str(median)
    return "cached" if mode in ("cache", "cache-or-live") else "—"


def _facts_block(lbl: str, ft: dict) -> list[str]:
    """Render one candidate's terroir-bullet translation for one source."""
    if "error" in ft:
        return [f"**{lbl}** — {ft['error']}", ""]
    langs = ft.get("langs") or {}
    en = langs.get("en") or {}
    nl = langs.get("nl") or {}
    tag = "pipeline cache" if ft.get("source") == "cache" else "live"
    o = [f"**{lbl}** ({tag})"]
    for lg, lb in (("en", en), ("nl", nl)):
        if "error" in lb:
            o.append(f"- _{lg}: error — {lb['error']}_")
    en_b = en.get("bullets") or []
    nl_b = nl.get("bullets") or []
    for i in range(max(len(en_b), len(nl_b))):
        o.append(f"- _src:_ {en_b[i]['source'] if i < len(en_b) else nl_b[i]['source']}")
        if i < len(en_b):
            o.append(f"  - **en** {en_b[i]['text']}")
        if i < len(nl_b):
            o.append(f"  - **nl** {nl_b[i]['text']}")
    o.append("")
    return o


def _render_facts_section(results: dict, sample: list, ran: list) -> list[str]:
    o = ["\n## 5. Terroir-bullet translations — review quality here\n",
         "_Each candidate's own extracted bullets, translated by the same "
         "candidate (stage-02e prompt). Per bullet: source, then en / nl._\n"]
    for country, slug in sample:
        key = f"{country}/{slug}"
        o.append(f"\n### {key}\n")
        blocks: list[str] = []
        for lbl in ran:
            ft = ((results[lbl].get("sources") or {}).get(key) or {}).get("facts_translation")
            if ft is not None:
                blocks += _facts_block(lbl, ft)
        o += blocks or ["_(no bullet translation for this source)_\n"]
    return o


def build_report(data: dict) -> str:
    results: dict = data.get("results") or {}
    sample = [tuple(s) for s in data.get("sample") or []]
    langs = data.get("target_langs") or list(TARGET_LANGS)
    order = [lbl for lbl in CANDIDATES if lbl in results] + \
            [lbl for lbl in results if lbl not in CANDIDATES]
    ran = [lbl for lbl in order if "error" not in results[lbl]]
    skipped = {lbl: results[lbl]["error"] for lbl in order if "error" in results[lbl]}
    not_run = [lbl for lbl in CANDIDATES if lbl not in results]

    o: list[str] = []
    o.append("# Provider comparison benchmark\n")
    o.append(f"Generated: {data.get('generated_at', '?')}  ")
    o.append(f"Sample: {len(sample)} sources — {', '.join('/'.join(s) for s in sample)}  ")
    o.append(f"Translation targets: {', '.join(langs)}\n")
    o.append("Quality is for the reviewer to judge — sections 3 and 4 stack the "
             "candidates per source. The harness measures only speed and cost.\n")
    o.append("> A candidate's task is **live** (model called now, instrumented), "
             "**cached** (the pipeline's existing output, read from disk — no cost, "
             "no latency), or **skipped**. The per-task mode is shown below.\n")
    o.append("> Cost uses the approximate `PRICING` table in "
             "`scripts/benchmark_providers.py` — verify against current provider "
             "pricing before quoting. Ollama is local (no token cost).\n")
    o.append(f"\nCandidates with results: {', '.join(ran) or '(none)'}  ")
    if skipped:
        o.append("Skipped (init failed): "
                 + "; ".join(f"{k} — {v}" for k, v in skipped.items()) + "  ")
    if not_run:
        o.append(f"Not yet run: {', '.join(not_run)}  ")

    # ── modes table ──
    o.append("\n## 0. Candidate matrix\n")
    o.append("| Candidate | Model | Extraction | Summary-tr | Facts-tr |")
    o.append("|---|---|---|---|---|")
    for lbl in ran:
        b = results[lbl]
        m = b.get("modes") or {}
        o.append(f"| {lbl} | `{b['model']}` | {m.get('extraction', '?')} | "
                 f"{m.get('translation', '?')} | {m.get('facts', '?')} |")

    # ── Section 1: speed & cost ──
    o.append("\n## 1. Speed & cost (over the sample)\n")
    o.append("| Candidate | Extr. calls | Extr. s/call | Summary-tr calls | "
             "Summary-tr s/call | Facts-tr calls | Facts-tr s/call | "
             "Input tok | Output tok | Est. cost |")
    o.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for lbl in ran:
        b = results[lbl]
        m = b.get("modes") or {}
        t = _candidate_totals(b)
        in_tok = t["ext_in"] + t["tr_in"] + t["ft_in"]
        out_tok = t["ext_out"] + t["tr_out"] + t["ft_out"]
        o.append(
            f"| {lbl} | {t['ext_calls']} | "
            f"{_speed_cell(_median(t['ext_lat']), m.get('extraction', 'live'))} | "
            f"{t['tr_calls']} | "
            f"{_speed_cell(_median(t['tr_lat']), m.get('translation', 'live'))} | "
            f"{t['ft_calls']} | "
            f"{_speed_cell(_median(t['ft_lat']), m.get('facts', 'live'))} | "
            f"{in_tok:,} | {out_tok:,} | "
            f"{_cost_label(b['model'], b['provider'], in_tok, out_tok)} |"
        )
    o.append("\n_s/call is wall-clock per LLM call (network for API candidates, "
             "local compute for Ollama). `cached` = task read from the pipeline's "
             "existing output, no call made. Cost sums all three tasks._\n")

    # ── Section 2: extraction yield ──
    o.append("\n## 2. Extraction yield (grounded bullets kept per source)\n")
    o.append("_A signal, not a quality score. Read section 3 for the actual facts._\n")
    o.append("| Source | " + " | ".join(ran) + " |")
    o.append("|" + "---|" * (len(ran) + 1))
    for country, slug in sample:
        key = f"{country}/{slug}"
        cells = []
        for lbl in ran:
            ext = ((results[lbl].get("sources") or {}).get(key) or {}).get("extraction")
            if ext is None:
                cells.append("—")
            elif "error" in ext:
                cells.append("err")
            else:
                cells.append(str(ext.get("n_facts", 0)))
        o.append(f"| {key} | " + " | ".join(cells) + " |")

    # ── Section 3: extraction output ──
    o.append("\n## 3. Extraction output — review quality here\n")
    for country, slug in sample:
        key = f"{country}/{slug}"
        o.append(f"\n### {key}\n")
        any_ext = False
        for lbl in ran:
            ext = ((results[lbl].get("sources") or {}).get(key) or {}).get("extraction")
            if ext is None:
                continue
            any_ext = True
            if "error" in ext:
                o.append(f"**{lbl}** — error: {ext['error']}\n")
                continue
            if ext.get("source") == "cache":
                head = (f"**{lbl}** — {ext.get('n_facts', 0)} facts · from "
                        f"`{ext.get('cache_file', '?')}` "
                        f"(pipeline cache, {ext.get('cache_translator_kind', '?')}/"
                        f"{ext.get('cache_translator', '?')})")
            else:
                head = (f"**{lbl}** — {ext.get('n_facts', 0)} facts, "
                        f"{ext.get('n_calls', 0)} calls, {ext.get('wall_s', 0)}s")
                if ext.get("errors"):
                    head += f", {len(ext['errors'])} subsection error(s)"
            o.append(head)
            for f in ext.get("facts") or []:
                o.append(f"- {f.get('bullet', '')}  \n"
                         f"  _[{f.get('subsection', '?')} · {f.get('provenance', '?')} · "
                         f"cahier_cov={f.get('cahier_coverage', 0)} "
                         f"wiki_cov={f.get('wiki_coverage', 0)}]_")
            if not (ext.get("facts")):
                o.append("- _(no grounded facts)_")
            for e in ext.get("errors") or []:
                o.append(f"  - ⚠ {e}")
            o.append("")
        if not any_ext:
            o.append("_(no extraction run for this source)_\n")

    # ── Section 4: translation output ──
    o.append("\n## 4. Translation output — review quality here\n")
    for country, slug in sample:
        key = f"{country}/{slug}"
        o.append(f"\n### {key}\n")
        src_text = ""
        for lbl in ran:
            tr = ((results[lbl].get("sources") or {}).get(key) or {}).get("translation") or {}
            if tr.get("source_text"):
                src_text = tr["source_text"]
                break
        o.append(f"**Source summary ({country}):** {src_text or '_(none)_'}\n")
        for lang in langs:
            o.append(f"**→ {lang}**\n")
            for lbl in ran:
                tr = ((results[lbl].get("sources") or {}).get(key) or {}).get("translation")
                if tr is None:
                    continue
                if "error" in tr:
                    o.append(f"- _{lbl}_: — ({tr['error']})")
                    continue
                lb = (tr.get("langs") or {}).get(lang)
                if lb is None:
                    o.append(f"- _{lbl}_: —")
                elif "error" in lb:
                    o.append(f"- _{lbl}_: error — {lb['error']}")
                else:
                    tag = "cached" if lb.get("wall_s") is None else f"{lb['wall_s']}s"
                    o.append(f"- _{lbl}_ ({tag}): {lb.get('text', '')}")
            o.append("")

    o += _render_facts_section(results, sample, ran)
    return "\n".join(o) + "\n"


# ─────────────────────────────────────────────────────────────────  main ──


def _cand_key(label: str) -> str:
    """CSS-safe slug of a candidate label."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _h(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


_HTML_CSS = """
*{box-sizing:border-box}
body{margin:0;font:13px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 color:#18181b;background:#f4f4f5}
header{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid #d4d4d8;padding:10px 18px}
header h1{margin:0;font-size:15px}
header .meta{color:#71717a;font-size:11px;margin:2px 0 8px}
.controls{display:flex;flex-wrap:wrap;gap:10px}
fieldset{border:1px solid #d4d4d8;border-radius:6px;margin:0;padding:2px 9px 5px;
 display:flex;gap:9px;flex-wrap:wrap;align-items:center}
legend{font-size:10px;color:#71717a;text-transform:uppercase;letter-spacing:.04em;padding:0 4px}
label.tg{display:inline-flex;gap:4px;align-items:center;cursor:pointer;white-space:nowrap;font-size:12px}
main{padding:14px 18px 80px}
h2{font-size:14px;margin:28px 0 2px}
h2 .sub{font-weight:400;color:#71717a;font-size:11px}
.src{margin:12px 0}
.src>h3{display:inline-block;margin:0 0 6px;font:600 12px/1 ui-monospace,Menlo,monospace;
 background:#27272a;color:#fafafa;padding:5px 9px;border-radius:4px}
.cols{display:flex;gap:10px;overflow-x:auto;align-items:flex-start;padding-bottom:8px}
.col{flex:1 1 250px;min-width:250px;background:#fff;border:1px solid #d4d4d8;border-radius:7px}
.col-head{font-weight:600;font-size:12px;padding:6px 9px;border-bottom:1px solid #e4e4e7;
 background:#fafafa;border-radius:7px 7px 0 0}
.col-head .sub{display:block;font-weight:400;color:#71717a;font-size:10.5px}
.col-body{padding:4px 9px 8px}
.blt{padding:5px 0;border-bottom:1px solid #f1f1f3}
.blt:last-child{border-bottom:0}
.tag{font-size:10px;color:#a1a1aa}
.prov-cahier{color:#a16207}.prov-wiki{color:#1d4ed8}.prov-both{color:#15803d}
.src-txt{color:#71717a}
.loc{margin-top:3px;display:flex;gap:5px}
.lbl{flex:0 0 auto;height:15px;padding:0 4px;font:600 9.5px/15px sans-serif;color:#fff;
 background:#a1a1aa;border-radius:3px;text-transform:uppercase}
.loc-en .lbl{background:#2563eb}.loc-nl .lbl{background:#ea580c}
.err{color:#b91c1c}
.muted{color:#a1a1aa}
"""

_HTML_JS = """
document.querySelectorAll('input[data-toggle]').forEach(function(cb){
  cb.addEventListener('change', function(){
    document.body.classList.toggle(cb.dataset.toggle, !cb.checked);
  });
});
"""


def _html_ext_col(lbl: str, ext: dict | None) -> str:
    """One provider column for the extraction section."""
    p = [f"<div class='col col-cand-{_cand_key(lbl)}'>"]
    if ext is None:
        return "".join(p + [f"<div class='col-head'>{_h(lbl)}<span class='sub'>no extraction"
                            "</span></div><div class='col-body muted'>—</div></div>"])
    if "error" in ext:
        return "".join(p + [f"<div class='col-head'>{_h(lbl)}<span class='sub'>error</span>"
                            f"</div><div class='col-body err'>{_h(ext['error'])}</div></div>"])
    srctag = "pipeline cache" if ext.get("source") == "cache" else "live"
    p.append(f"<div class='col-head'>{_h(lbl)}<span class='sub'>{ext.get('n_facts', 0)} "
             f"facts · {srctag}</span></div><div class='col-body'>")
    facts = ext.get("facts") or []
    for f in facts:
        prov = f.get("provenance", "?")
        p.append(f"<div class='blt'>{_h(f.get('bullet', ''))} <span class='tag "
                 f"prov-{_h(prov)}'>[{_h(f.get('subsection', '?'))} · {_h(prov)}]</span></div>")
    if not facts:
        p.append("<div class='muted'>(no grounded facts)</div>")
    return "".join(p + ["</div></div>"])


def _html_facts_col(lbl: str, ft: dict | None) -> str:
    """One provider column for the bullet-translation section."""
    p = [f"<div class='col col-cand-{_cand_key(lbl)}'>"]
    if ft is None:
        return "".join(p + [f"<div class='col-head'>{_h(lbl)}<span class='sub'>no translation"
                            "</span></div><div class='col-body muted'>—</div></div>"])
    if "error" in ft:
        return "".join(p + [f"<div class='col-head'>{_h(lbl)}<span class='sub'>error</span>"
                            f"</div><div class='col-body err'>{_h(ft['error'])}</div></div>"])
    srctag = "pipeline cache" if ft.get("source") == "cache" else "live"
    langs = ft.get("langs") or {}
    en, nl = langs.get("en") or {}, langs.get("nl") or {}
    p.append(f"<div class='col-head'>{_h(lbl)}<span class='sub'>{srctag}</span></div>"
             "<div class='col-body'>")
    en_b, nl_b = en.get("bullets") or [], nl.get("bullets") or []
    for lg, lb in (("en", en), ("nl", nl)):
        if "error" in lb:
            p.append(f"<div class='loc loc-{lg}'><span class='lbl'>{lg}</span>"
                     f"<span class='err'>{_h(lb['error'])}</span></div>")
    for i in range(max(len(en_b), len(nl_b))):
        src = en_b[i]["source"] if i < len(en_b) else nl_b[i]["source"]
        p.append(f"<div class='blt'><div class='src-txt'>{_h(src)}</div>")
        if i < len(en_b):
            p.append(f"<div class='loc loc-en'><span class='lbl'>en</span>"
                     f"<span>{_h(en_b[i]['text'])}</span></div>")
        if i < len(nl_b):
            p.append(f"<div class='loc loc-nl'><span class='lbl'>nl</span>"
                     f"<span>{_h(nl_b[i]['text'])}</span></div>")
        p.append("</div>")
    if not en_b and not nl_b and "error" not in en and "error" not in nl:
        p.append("<div class='muted'>(no bullets)</div>")
    return "".join(p + ["</div></div>"])


def _html_section(title: str, sub: str, sample: list, shown: list,
                   results: dict, task: str, col_fn) -> list[str]:
    o = [f"<h2>{title} <span class='sub'>— {sub}</span></h2>"]
    for country, slug in sample:
        key = f"{country}/{slug}"
        o.append(f"<div class='src'><h3>{_h(key)}</h3><div class='cols'>")
        for lbl in shown:
            o.append(col_fn(lbl, ((results[lbl].get("sources") or {}).get(key) or {}).get(task)))
        o.append("</div></div>")
    return o


def build_html(data: dict) -> str:
    """Render the side-by-side comparison page (sections 3 + 5) with
    locale and provider toggles. Self-contained — no external assets."""
    results = data.get("results") or {}
    sample = [tuple(s) for s in data.get("sample") or []]
    langs = list(data.get("target_langs") or TARGET_LANGS)
    order = ([l for l in CANDIDATES if l in results]
             + [l for l in results if l not in CANDIDATES])
    shown = [l for l in order if "error" not in results[l]
             and any("extraction" in e or "facts_translation" in e
                     for e in (results[l].get("sources") or {}).values())]

    rules = [f"body.hide-loc-{lg} .loc-{lg}{{display:none}}" for lg in langs]
    rules += [f"body.hide-cand-{_cand_key(l)} .col-cand-{_cand_key(l)}{{display:none}}"
              for l in shown]

    o = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<title>Provider comparison — extraction &amp; bullet translation</title>",
         "<style>", _HTML_CSS, "\n".join(rules), "</style></head><body>",
         "<header><h1>Provider comparison — extraction &amp; bullet translation</h1>",
         f"<div class='meta'>Generated {_h(data.get('generated_at', '?'))} · "
         f"{len(sample)} sources · {len(shown)} providers · "
         "sections 3 (extraction) &amp; 5 (terroir-bullet translations)</div>",
         "<div class='controls'>",
         "<fieldset><legend>Locales (translations)</legend>"]
    for lg in langs:
        o.append(f"<label class='tg'><input type='checkbox' checked "
                 f"data-toggle='hide-loc-{_h(lg)}'> {_h(lg)}</label>")
    o.append("</fieldset><fieldset><legend>Providers</legend>")
    for lbl in shown:
        o.append(f"<label class='tg'><input type='checkbox' checked "
                 f"data-toggle='hide-cand-{_cand_key(lbl)}'> {_h(lbl)}</label>")
    o.append("</fieldset></div></header><main>")

    o += _html_section("3. Extraction", "terroir bullets, source language",
                        sample, shown, results, "extraction", _html_ext_col)
    o += _html_section("5. Terroir-bullet translations",
                        "each model translates its own extracted bullets",
                        sample, shown, results, "facts_translation", _html_facts_col)

    o += ["</main><script>", _HTML_JS, "</script></body></html>"]
    return "".join(o)


def _verify_sample() -> list[str]:
    problems = []
    dirs = {
        "fr": ROOT / "raw" / "inao" / "cahier-extracted",
        "es": ROOT / "raw" / "es" / "pliegos-extracted",
        "pt": ROOT / "raw" / "pt" / "cadernos-extracted",
        "it": ROOT / "raw" / "it" / "disciplinari-extracted",
    }
    for country, slug in SAMPLE:
        if country not in dirs:
            problems.append(f"{country}/{slug}: unknown country")
        elif not (dirs[country] / f"{slug}.json").exists():
            problems.append(f"{country}/{slug}: extracted record not found")
    return problems


def _resolve_candidates(selectors: list[str] | None) -> list[str]:
    if not selectors:
        return list(CANDIDATES)
    chosen: list[str] = []
    for sel in selectors:
        if sel in CANDIDATES:
            chosen.append(sel)
            continue
        matched = [lbl for lbl, spec in CANDIDATES.items() if spec["provider"] == sel]
        if matched:
            chosen += matched
        else:
            print(f"warning: --candidate '{sel}' matched nothing", file=sys.stderr)
    seen: set[str] = set()
    return [c for c in chosen if not (c in seen or seen.add(c))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", action="append", default=None,
                    help="candidate label or bare provider name (repeatable; "
                         "default: all)")
    ap.add_argument("--task", choices=("extraction", "translation", "facts", "all"),
                    default="all",
                    help="task(s) to run (default: all three). Run one task to add "
                         "it; the others are kept from results.json.")
    ap.add_argument("--limit", type=int, default=0,
                    help="run only the first N sample sources (0 = all)")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild REPORT.md from results.json, run nothing")
    ap.add_argument("--list", action="store_true",
                    help="print the sample + candidate matrix and exit")
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    results_path = out_dir / "results.json"
    report_path = out_dir / "REPORT.md"
    html_path = out_dir / "report.html"

    if args.list:
        print("Sample:")
        for i, (c, s) in enumerate(SAMPLE, 1):
            print(f"  {i:2}. {c}/{s}")
        print(f"\nTranslation targets: {', '.join(TARGET_LANGS)}\n\nCandidates:")
        for lbl, spec in CANDIDATES.items():
            print(f"  {lbl:24} {spec['provider']:9} {spec['model']:24} "
                  f"ext={spec['extraction']:13} sum-tr={spec['translation']:6} "
                  f"facts-tr={spec.get('facts', 'live')}")
        return 0

    if args.report_only:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        d = load_results(results_path)
        report_path.write_text(build_report(d))
        html_path.write_text(build_html(d))
        print(f"[bench] wrote {report_path} and {html_path}", file=sys.stderr)
        return 0

    load_dotenv()

    problems = _verify_sample()
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1

    sample = SAMPLE[: args.limit] if args.limit else list(SAMPLE)
    tasks = (("extraction", "translation", "facts") if args.task == "all"
             else (args.task,))
    candidates = _resolve_candidates(args.candidate)
    if not candidates:
        print("error: no candidates selected", file=sys.stderr)
        return 1

    print(f"[bench] {len(candidates)} candidate(s): {', '.join(candidates)}", file=sys.stderr)
    print(f"[bench] {len(sample)} source(s), tasks={'+'.join(tasks)}", file=sys.stderr)

    data = load_results(results_path)
    data["sample"] = [list(s) for s in sample]
    data["target_langs"] = list(TARGET_LANGS)
    data.setdefault("results", {})

    for lbl in candidates:
        print(f"\n[bench] === {lbl} ===", file=sys.stderr)
        t0 = time.time()
        block = run_candidate(lbl, tasks=tasks, sample=sample,
                              prior=data["results"].get(lbl),
                              ollama_url=args.ollama_url, mistral_url=args.mistral_url)
        block["wall_total_s"] = round(time.time() - t0, 1)
        data["results"][lbl] = block
        save_results(results_path, data)  # incremental — survives a later crash
        report_path.write_text(build_report(data))
        html_path.write_text(build_html(data))
        print(f"[bench] {lbl} done in {block['wall_total_s']}s", file=sys.stderr)

    print(f"\n[bench] results: {results_path}\n[bench] report:  {report_path}"
          f"\n[bench] html:    {html_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
