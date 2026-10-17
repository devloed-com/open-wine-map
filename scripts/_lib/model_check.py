"""Is the configured default the newest model of its family?

Every LLM stage resolves its Anthropic model through `providers.STAGE_DEFAULTS`
(via `batch.default_model` on the Batch path, `providers.make_provider` on the
synchronous one). Those ids are hard-coded, so a release goes unnoticed until
somebody looks: Sonnet 4.6 kept writing translations after Sonnet 5 shipped,
and wrote 40 of the 42 Dutch de/het errors of 2026-10-09. The rule (Boris,
2026-10-09) is the newest version of a family unless a run names another.

`ensure_latest(model)` lists the account's models through the Models API
(`GET /v1/models`), cached in `raw/cache/anthropic-models.json` for a day,
and stops the run — before anything is submitted — when the same family
(sonnet / opus / haiku / fable) has a model created after the configured one.
It does not switch on its own: a new model can change the request surface
(Sonnet 5.5 answers the `disabled` thinking Sonnet 5 took with a 400), so a
bump is a code change — STAGE_DEFAULTS, the price table, the thinking mapping,
tests/test_stage_defaults.py. An explicit `--model` is never checked, so a
deliberate older model (or resuming an in-flight batch) still works.

When the check cannot run — no API key, the API unreachable and no cache —
it warns and lets the run go on; a stale cache is used with a warning.
`OWM_SKIP_MODEL_CHECK=1` disables it (the test suite sets it).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _lib.env import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "raw" / "cache" / "anthropic-models.json"
MAX_AGE = timedelta(days=1)

_FAMILY_RE = re.compile(r"^claude-(opus|sonnet|haiku|fable|mythos)-\d")

Fetcher = Callable[[], list[dict]]


def family(model_id: str) -> str | None:
    m = _FAMILY_RE.match(model_id or "")
    return m.group(1) if m else None


def _fetch_from_api() -> list[dict]:
    import anthropic  # type: ignore

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is unset")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return [
        {"id": m.id, "display_name": getattr(m, "display_name", ""),
         "created_at": m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at)}
        for m in client.models.list()
    ]


def _read_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_models(*, cache: Path = CACHE, fetch: Fetcher = _fetch_from_api,
                now: datetime | None = None) -> tuple[list[dict] | None, str]:
    """(models, how) — `how` is "cache", "api" or "stale-cache: <error>";
    (None, "<error>") when there is neither a fresh answer nor a cache."""
    now = now or datetime.now(timezone.utc)
    cached = _read_cache(cache)
    if cached:
        try:
            age = now - datetime.fromisoformat(cached["fetched_at"])
        except (KeyError, ValueError):
            age = MAX_AGE
        if age < MAX_AGE:
            return cached.get("models") or [], "cache"
    try:
        models = fetch()
    except Exception as e:  # noqa: BLE001 — any failure falls back to the cache
        if cached:
            return cached.get("models") or [], f"stale-cache: {e}"
        return None, str(e)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": now.isoformat(timespec="seconds"), "models": models},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return models, "api"


def newer_models(model_id: str, models: list[dict]) -> list[dict] | None:
    """Same-family models created after `model_id`, newest first; None when
    `model_id` is not in the list (unknown to the account, or retired)."""
    fam = family(model_id)
    by_id = {m["id"]: m for m in models}
    if model_id not in by_id:
        return None
    mine = by_id[model_id]["created_at"]
    out = [m for m in models if family(m["id"]) == fam and m["id"] != model_id and m["created_at"] > mine]
    return sorted(out, key=lambda m: m["created_at"], reverse=True)


def ensure_latest(model_id: str, *, stage: str | None = None, cache: Path = CACHE,
                  fetch: Fetcher = _fetch_from_api, now: datetime | None = None) -> None:
    """SystemExit when a newer model of `model_id`'s family exists; a
    warning on stderr when that cannot be established."""
    if os.environ.get("OWM_SKIP_MODEL_CHECK") or not family(model_id):
        return
    models, how = list_models(cache=cache, fetch=fetch, now=now)
    where = f" (stage {stage})" if stage else ""
    if models is None:
        print(f"[model-check] warning: could not list models ({how}); running {model_id}{where} unchecked",
              file=sys.stderr)
        return
    if how.startswith("stale-cache"):
        print(f"[model-check] warning: models list older than a day ({how})", file=sys.stderr)
    newer = newer_models(model_id, models)
    if newer is None:
        print(f"[model-check] warning: {model_id} is not in the account's model list", file=sys.stderr)
        return
    if newer:
        top = newer[0]
        raise SystemExit(
            f"error: the default model{where} is {model_id}, but {top['id']} "
            f"({top.get('display_name') or top['id']}, released {top['created_at'][:10]}) is newer in the "
            f"same family.\n"
            f"  Bump scripts/_lib/providers.py STAGE_DEFAULTS (+ batch.BATCH_PRICES_USD_PER_M, "
            f"providers.effective_thinking for the new model's thinking options, tests/test_stage_defaults.py),\n"
            f"  or pass --model {model_id} to run on it deliberately (e.g. to resume an in-flight batch)."
        )
