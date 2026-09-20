"""Batch-API execution for the LLM stages (02c / 02d / 02e).

The pipeline stages call `provider.chat()` one request at a time. The
Anthropic and Mistral Batch APIs are asynchronous and ~50% cheaper, so
this module runs a stage's normal processing loop as a batch via two
passes over that exact loop:

  pass 1 (collect) — a `CollectingProvider` records every distinct
    `chat()` the stage issues and returns "" so nothing is parsed/cached.
  pass 2 (replay)  — a `ReplayProvider` feeds the batched answers back,
    matched by prompt hash, so the stage parses + writes caches as usual.

Between the passes the collected prompts are submitted to the provider's
Batch API, polled to completion, and the answers collected. The batch id
is written to a sidecar file: an interrupted run, re-run, resumes the
in-flight batch instead of resubmitting (and re-paying).

Each request's `custom_id` is a hash of its prompt, so pass 2 matches
answers by content rather than call order. A batch run is therefore
incremental — it enumerates only stale / missing entries, never
resubmitting an already-processed one — and an interrupted run resumes
the in-flight batch (via the sidecar) even after a partial pass 2. Runs
are single-threaded.

Every fetched result carries the provider's `usage` (input / output /
cache tokens); `run_batch` sums them, prices them at the Batch-API rate
(`BATCH_PRICES_USD_PER_M`, 50 % of the list price), prints the line and
appends it to `raw/.batch/costs.jsonl` — one row per batch, keyed by the
stage sidecar — so a run reports its own cost instead of the numbers
being re-read from the API afterwards. `run_two_pass` returns the same
summary in its stats dict for the stage's report.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from _lib.env import load_dotenv
from _lib.prompt_cache import system_text
from _lib.providers import effective_thinking, stage_default


def _load_dotenv() -> None:
    """Populate os.environ from a repo-root .env (KEY=VALUE lines); existing
    environment variables win. Lets `--batch` pick up API keys without a
    manual export."""
    load_dotenv()


POLL_INTERVAL_S = 20
MISTRAL_BASE = "https://api.mistral.ai/v1"
_KIND = {"anthropic": "anthropic-api", "mistral": "mistral-api"}
_DEFAULT_MODEL = {"anthropic": "claude-sonnet-4-6", "mistral": "mistral-medium-latest"}


def default_model(provider: str, stage: str | None = None) -> str:
    """The batch-default model id for a provider (overridable with --model);
    for anthropic the per-stage default from `providers.STAGE_DEFAULTS`."""
    if provider == "anthropic":
        return stage_default(stage)[0]
    return _DEFAULT_MODEL.get(provider, "")


def default_thinking(provider: str, stage: str | None = None) -> str | None:
    """The stage's thinking mode for anthropic (None / "disabled" / "adaptive")."""
    return stage_default(stage)[1] if provider == "anthropic" else None


def supports(provider: str) -> bool:
    return provider in _KIND


# Substrings that mark a *permanent* failure — never worth retrying.
_PERMANENT = ("credit balance", "invalid_request_error", "authentication_error",
              "permission_error", "Unauthorized", "Forbidden")


def _retry(fn, *, what: str, attempts: int = 5):
    """Call fn(); retry transient failures (connection drop, 5xx, overload)
    with linear backoff. Permanent errors (credit exhausted, bad key, 400)
    raise immediately — no point retrying those."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(s in msg for s in _PERMANENT):
                raise
            last = e
            if attempt < attempts:
                wait = 20 * attempt
                print(f"[batch] {what} failed ({type(e).__name__}: {msg[:140]}) — "
                      f"retry {attempt}/{attempts - 1} in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise last  # type: ignore[misc]


# ───────────────────────────────────────────── collecting / replay providers ──


def _request_id(system, user: str) -> str:
    """Stable content hash of a prompt — the batch `custom_id`. Replay keys
    on this, so it is order-independent: an interrupted run resumes
    correctly even when entries were cached (and thus dropped from the job
    list) in between."""
    sys_key = system if isinstance(system, str) else json.dumps(system, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{sys_key}\x00{user}".encode()).hexdigest()[:32]


class CollectingProvider:
    """Pass 1. Records every *distinct* `chat()` the stage would issue and
    returns "" (so the stage parses nothing and writes no cache). Requests
    are de-duplicated by prompt hash — identical prompts cost one batch
    request."""

    kind = "collecting"

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._seen: set[str] = set()

    def chat(self, *, system, user: str, max_tokens: int = 1024, cache_phase=None, **_: object) -> str:
        cid = _request_id(system, user)
        if cid not in self._seen:
            self._seen.add(cid)
            self.requests.append({
                "custom_id": cid,
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "phase": cache_phase,
            })
        return ""


class ReplayProvider:
    """Pass 2. Returns each batched answer matched by prompt hash — order-
    independent, so it is robust to the job list shrinking between an
    interrupted run and its resume. Raises on an errored or missing request
    so the stage's existing per-job error handling skips it cleanly."""

    def __init__(self, results: dict, kind: str) -> None:
        self.results = results
        self.kind = kind

    def chat(self, *, system, user: str, **_: object) -> str:
        cid = _request_id(system, user)
        r = self.results.get(cid)
        if r is None:
            raise RuntimeError(
                f"batch replay: no result for request {cid} — its prompt "
                "changed since the batch was submitted."
            )
        if r.get("error"):
            raise RuntimeError(f"batch request {cid} errored: {r['error']}")
        return r["text"]


# ─────────────────────────────────────────────────────────────────── usage ──

# List price, USD per million tokens (input, output); the Batch API bills
# BATCH_DISCOUNT of it. Cache reads bill at 10 % of input, cache writes at
# 125 %. Unknown model → tokens are still summed, cost is None.
BATCH_PRICES_USD_PER_M: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
BATCH_DISCOUNT = 0.5
COSTS_LEDGER = Path(__file__).resolve().parents[2] / "raw" / ".batch" / "costs.jsonl"
_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _usage_from_anthropic(usage) -> dict:
    return {k: int(getattr(usage, k, 0) or 0) for k in _USAGE_KEYS}


def _usage_from_mistral(usage: dict | None) -> dict:
    u = usage or {}
    return {"input_tokens": int(u.get("prompt_tokens") or 0), "output_tokens": int(u.get("completion_tokens") or 0),
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def batch_cost_usd(usage: dict, model: str) -> float | None:
    """The Batch-API price of `usage` for `model`, or None for an unpriced model."""
    prices = BATCH_PRICES_USD_PER_M.get(model)
    if not prices:
        return None
    inp, out = prices
    per_m = (
        usage.get("input_tokens", 0) * inp
        + usage.get("output_tokens", 0) * out
        + usage.get("cache_read_input_tokens", 0) * inp * 0.1
        + usage.get("cache_creation_input_tokens", 0) * inp * 1.25
    )
    return round(per_m / 1_000_000 * BATCH_DISCOUNT, 4)


def usage_summary(results: dict, model: str) -> dict:
    """Sum the per-result `usage` dicts and price them: {n_results,
    n_with_usage, input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens, cost_usd}."""
    tot = {k: 0 for k in _USAGE_KEYS}
    n = 0
    for r in results.values():
        u = r.get("usage") if isinstance(r, dict) else None
        if not u:
            continue
        n += 1
        for k in _USAGE_KEYS:
            tot[k] += int(u.get(k) or 0)
    return {"n_results": len(results), "n_with_usage": n, **tot, "cost_usd": batch_cost_usd(tot, model)}


def _record_cost(*, provider: str, model: str, batch_id: str, sidecar: Path, thinking: str | None,
                 summary: dict) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": sidecar.stem, "provider": provider, "model": model, "thinking": thinking,
        "batch_id": batch_id, "run": os.environ.get("OWM_TERROIR_RUN") or None, **summary,
    }
    try:
        COSTS_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with COSTS_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:  # the ledger is bookkeeping, never a reason to fail a run
        print(f"[batch] could not append to {COSTS_LEDGER.name}: {e}", file=sys.stderr)


def _cost_line(summary: dict) -> str:
    cost = summary.get("cost_usd")
    return (f"in={summary['input_tokens']:,} out={summary['output_tokens']:,}"
            + (f" cache_read={summary['cache_read_input_tokens']:,}" if summary.get("cache_read_input_tokens") else "")
            + (f" ≈ ${cost:,.2f}" if cost is not None else " (unpriced model)"))


# ─────────────────────────────────────────────────────────── anthropic batch ──


def _anthropic_client():
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise SystemExit("error: anthropic SDK missing — `uv add anthropic`.") from e
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("error: ANTHROPIC_API_KEY environment variable is unset.")
    return anthropic.Anthropic(api_key=key)


def _anthropic_params(model: str, r: dict, thinking: str | None) -> dict:
    params = {
        "model": model,
        "max_tokens": r["max_tokens"],
        "system": r["system"],
        "messages": [{"role": "user", "content": r["user"]}],
    }
    # The Claude 5 family runs adaptive thinking when `thinking` is omitted,
    # and the extraction stages' 1,500–2,000-token `max_tokens` budgets were
    # sized for text only: each stage passes its `STAGE_DEFAULTS` mode
    # ("disabled" for 02d, "adaptive" for the gate); `OWM_BATCH_THINKING`
    # overrides for an experiment.
    mode = effective_thinking(model, os.environ.get("OWM_BATCH_THINKING") or thinking)
    if mode:
        params["thinking"] = {"type": mode}
    return params


def _submit_anthropic(model: str, reqs: list[dict], thinking: str | None = None) -> str:
    client = _anthropic_client()
    batch = client.messages.batches.create(requests=[
        {"custom_id": r["custom_id"], "params": _anthropic_params(model, r, thinking)} for r in reqs
    ])
    return batch.id


def _fetch_anthropic(batch_id: str, poll_interval: int) -> dict:
    client = _anthropic_client()
    while True:
        b = _retry(lambda: client.messages.batches.retrieve(batch_id),
                   what="anthropic batch poll")
        if b.processing_status == "ended":
            break
        rc = b.request_counts
        print(f"[batch] anthropic {batch_id}: {b.processing_status} — "
              f"processing={rc.processing} succeeded={rc.succeeded} "
              f"errored={rc.errored}", file=sys.stderr)
        time.sleep(poll_interval)
    out: dict = {}
    entries = _retry(lambda: list(client.messages.batches.results(batch_id)),
                     what="anthropic batch results")
    for entry in entries:
        res = entry.result
        if res.type == "succeeded":
            text = "".join(blk.text for blk in res.message.content
                            if getattr(blk, "type", "") == "text").strip()
            out[entry.custom_id] = {"text": text, "usage": _usage_from_anthropic(res.message.usage)}
        else:
            out[entry.custom_id] = {"error": res.type}
    return out


# ───────────────────────────── mistral batch (raw HTTP — no mistralai SDK) ──

_MISTRAL_DONE = {"SUCCESS", "FAILED", "TIMEOUT_EXCEEDED", "CANCELLED",
                 "CANCELLATION_REQUESTED"}


def _mistral_key() -> str:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise SystemExit("error: MISTRAL_API_KEY environment variable is unset.")
    return key


def _submit_mistral(model: str, reqs: list[dict]) -> str:
    key = _mistral_key()
    lines = [
        json.dumps({
            "custom_id": r["custom_id"],
            "body": {
                "max_tokens": r["max_tokens"],
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_text(r["system"])},
                    {"role": "user", "content": r["user"]},
                ],
            },
        }, ensure_ascii=False)
        for r in reqs
    ]
    jsonl = ("\n".join(lines)).encode("utf-8")
    up = requests.post(
        f"{MISTRAL_BASE}/files",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("batch.jsonl", jsonl, "application/jsonl")},
        data={"purpose": "batch"},
        timeout=300,
    )
    up.raise_for_status()
    file_id = up.json()["id"]
    job = requests.post(
        f"{MISTRAL_BASE}/batch/jobs",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"input_files": [file_id], "model": model,
              "endpoint": "/v1/chat/completions"},
        timeout=120,
    )
    job.raise_for_status()
    return job.json()["id"]


def _mistral_line_text(d: dict) -> tuple[str | None, str | None]:
    """Tolerant extraction of one Mistral batch output line → (text, error).
    Handles both the `response.body` and `result.data` output shapes."""
    resp = d.get("response")
    if isinstance(resp, dict):
        sc = resp.get("status_code")
        if sc and sc != 200:
            return None, f"http {sc}"
        choices = (resp.get("body") or {}).get("choices")
        if choices:
            return choices[0]["message"]["content"].strip(), None
    result = d.get("result")
    if isinstance(result, dict):
        if result.get("type") == "error":
            return None, str(result.get("error") or "error")
        choices = (result.get("data") or {}).get("choices")
        if choices:
            return choices[0]["message"]["content"].strip(), None
    return None, "unrecognised mistral batch output line"


def _fetch_mistral(job_id: str, poll_interval: int) -> dict:
    key = _mistral_key()
    h = {"Authorization": f"Bearer {key}"}
    status = "?"
    j: dict = {}
    while True:
        r = requests.get(f"{MISTRAL_BASE}/batch/jobs/{job_id}", headers=h, timeout=60)
        r.raise_for_status()
        j = r.json()
        status = j.get("status", "?")
        if status in _MISTRAL_DONE:
            break
        print(f"[batch] mistral {job_id}: {status} — "
              f"{j.get('succeeded_requests', '?')}/{j.get('total_requests', '?')}",
              file=sys.stderr)
        time.sleep(poll_interval)
    if status != "SUCCESS":
        raise RuntimeError(f"mistral batch {job_id} ended with status {status}")
    out_file = j.get("output_file")
    if not out_file:
        raise RuntimeError(f"mistral batch {job_id}: completed job has no output_file")
    content = requests.get(f"{MISTRAL_BASE}/files/{out_file}/content", headers=h, timeout=300)
    content.raise_for_status()
    out: dict = {}
    for line in content.text.splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        text, err = _mistral_line_text(d)
        if err is None:
            resp = d.get("response")
            body = (resp.get("body") or {}) if isinstance(resp, dict) else {}
            out[d.get("custom_id")] = {"text": text, "usage": _usage_from_mistral(body.get("usage"))}
        else:
            out[d.get("custom_id")] = {"error": err}
    return out


# ───────────────────────────────────────────────────────────── orchestration ──


def _submit(provider: str, model: str, reqs: list[dict], thinking: str | None = None) -> str:
    if provider == "anthropic":
        return _submit_anthropic(model, reqs, thinking)
    if provider == "mistral":
        return _submit_mistral(model, reqs)
    raise ValueError(f"batch unsupported for provider {provider!r}")


def _fetch(provider: str, batch_id: str, poll_interval: int) -> dict:
    if provider == "anthropic":
        return _fetch_anthropic(batch_id, poll_interval)
    return _fetch_mistral(batch_id, poll_interval)


def run_batch(provider: str, model: str, reqs: list[dict], *, sidecar: Path,
              poll_interval: int = POLL_INTERVAL_S, thinking: str | None = None) -> dict:
    """Submit `reqs` to `provider`'s Batch API, poll to completion, return
    {custom_id: {"text": ...} | {"error": ...}}. If `sidecar` already holds
    an in-flight batch id for this provider, resume that batch (no resubmit,
    no re-pay)."""
    _load_dotenv()
    state = None
    if sidecar.exists():
        try:
            state = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            state = None
    if state and state.get("batch_id") and state.get("provider") == provider:
        batch_id = state["batch_id"]
        print(f"[batch] resuming in-flight {provider} batch {batch_id} "
              f"(submitted {state.get('submitted_at', '?')}, "
              f"{state.get('n_requests', '?')} requests) — not resubmitting",
              file=sys.stderr)
    else:
        if not reqs:
            return {}
        print(f"[batch] submitting {len(reqs)} requests to the {provider} batch "
              f"API (model={model}, ~50% cheaper than synchronous)", file=sys.stderr)
        batch_id = _retry(lambda: _submit(provider, model, reqs, thinking),
                          what=f"{provider} batch submit")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "provider": provider, "model": model, "batch_id": batch_id,
            "thinking": thinking, "n_requests": len(reqs),
            "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2), encoding="utf-8")
        print(f"[batch] {provider} batch {batch_id} submitted — id saved to "
              f"{sidecar.name} (re-run this command to resume if interrupted)",
              file=sys.stderr)
    results = _fetch(provider, batch_id, poll_interval)
    summary = usage_summary(results, model)
    print(f"[batch] {provider} batch {batch_id} complete — {len(results)} results; "
          f"{_cost_line(summary)}", file=sys.stderr)
    _record_cost(provider=provider, model=model, batch_id=batch_id, sidecar=sidecar,
                 thinking=thinking, summary=summary)
    return results


PHASED_ENV = "OWM_BATCH_PHASED"


def phased() -> bool:
    """Whether requests tagged with a `cache_phase` are submitted as one
    batch per phase, in order (default on; OWM_BATCH_PHASED=0 disables)."""
    return (os.environ.get(PHASED_ENV) or "1").strip().lower() not in ("0", "off", "false", "no")


def _phase_groups(reqs: list[dict]) -> list[tuple[object, list[dict]]]:
    """Requests grouped by their `phase`, in order of first appearance;
    untagged requests form one group."""
    order: list[object] = []
    groups: dict[object, list[dict]] = {}
    for r in reqs:
        ph = r.get("phase")
        if ph not in groups:
            order.append(ph)
            groups[ph] = []
        groups[ph].append(r)
    return [(ph, groups[ph]) for ph in order]


def run_phased(provider: str, model: str, reqs: list[dict], *, sidecar: Path,
               poll_interval: int = POLL_INTERVAL_S, thinking: str | None = None) -> dict:
    """The requests of a record that share a cached prefix (a 02d record's
    four sub-section calls) are processed concurrently inside one batch,
    so most of them write the prefix instead of reading it (13–47 % hits
    on the cfg-2026-09-14 run). Submitting one batch per `cache_phase`,
    each after the previous has ended, makes the first phase write and
    the later phases read — the prefix block carries the 1-hour TTL for
    this (a read refreshes the timer, so each phase only has to finish
    within an hour). Each phase has its own sidecar and resumes on its
    own; the merged results feed one replay."""
    groups = _phase_groups(reqs)
    if len(groups) < 2:
        return run_batch(provider, model, reqs, sidecar=sidecar, poll_interval=poll_interval, thinking=thinking)
    results: dict = {}
    for i, (ph, group) in enumerate(groups):
        side = sidecar.with_name(f"{sidecar.stem}.p{i}{sidecar.suffix}")
        print(f"[batch] phase {i + 1}/{len(groups)} ({ph}): {len(group)} requests", file=sys.stderr)
        results.update(run_batch(provider, model, group, sidecar=side, poll_interval=poll_interval,
                                 thinking=thinking))
        side.unlink(missing_ok=True)
    return results


def run_two_pass(*, provider: str, model: str, sidecar: Path, run_loop,
                 poll_interval: int = POLL_INTERVAL_S, thinking: str | None = None) -> dict:
    """Run a stage's processing loop as a batch. `run_loop(provider)` runs the
    stage loop once, single-threaded; it is called twice (collect, replay).
    The stage should enumerate only stale / missing entries — replay matches
    answers by prompt hash, so dropping already-done entries is safe and the
    run is incremental. Returns a small stats dict."""
    if not supports(provider):
        raise SystemExit(f"error: --batch supports anthropic / mistral, not {provider!r}")
    collector = CollectingProvider()
    with contextlib.redirect_stderr(io.StringIO()):
        run_loop(collector)  # pass 1 — collect prompts (stderr muted: "" noise)
    reqs = collector.requests
    in_flight = sidecar.exists() or any(sidecar.parent.glob(f"{sidecar.stem}.p*{sidecar.suffix}"))
    if not reqs and not in_flight:
        print("[batch] nothing to do — all entries already processed.", file=sys.stderr)
        return {"n_requests": 0, "n_results": 0, "n_errored": 0}
    print(f"[batch] collected {len(reqs)} distinct model requests", file=sys.stderr)
    use_phases = phased() and any(r.get("phase") is not None for r in reqs)
    runner = run_phased if use_phases else run_batch
    results = runner(provider, model, reqs, sidecar=sidecar,
                     poll_interval=poll_interval, thinking=thinking)
    usage = usage_summary(results, model)
    run_loop(ReplayProvider(results, kind=_KIND[provider]))  # pass 2 — write caches
    sidecar.unlink(missing_ok=True)  # batch fully consumed — clear resume state
    n_err = sum(1 for r in results.values() if r.get("error"))
    if n_err:
        print(f"[batch] {n_err} of {len(results)} requests errored — re-run to "
              "retry just those (already-done entries are skipped)", file=sys.stderr)
    return {"n_requests": len(reqs), "n_results": len(results), "n_errored": n_err,
            "model": model, "usage": usage}
