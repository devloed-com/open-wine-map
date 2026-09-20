"""Batch usage accounting and pricing (scripts/_lib/batch.py)."""
from __future__ import annotations

import json

from _lib import batch


def test_batch_cost_is_half_list_price_with_cache_rates():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert batch.batch_cost_usd(usage, "claude-sonnet-5") == round((2.0 + 1.0) * 0.5, 4)
    assert batch.batch_cost_usd(usage, "claude-opus-5") == round((5.0 + 2.5) * 0.5, 4)
    cached = {**usage, "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}
    assert batch.batch_cost_usd(cached, "claude-sonnet-4-6") == round((3.0 + 1.5 + 0.3 + 3.75) * 0.5, 4)
    assert batch.batch_cost_usd(usage, "some-unknown-model") is None


def test_usage_summary_sums_only_results_with_usage():
    results = {
        "a": {"text": "x", "usage": {"input_tokens": 10, "output_tokens": 5}},
        "b": {"text": "y", "usage": {"input_tokens": 20, "output_tokens": 1, "cache_read_input_tokens": 7}},
        "c": {"error": "errored"},
    }
    s = batch.usage_summary(results, "claude-sonnet-5")
    assert (s["n_results"], s["n_with_usage"]) == (3, 2)
    assert (s["input_tokens"], s["output_tokens"], s["cache_read_input_tokens"]) == (30, 6, 7)
    assert s["cost_usd"] == batch.batch_cost_usd(s, "claude-sonnet-5")


def test_cost_ledger_row(tmp_path, monkeypatch):
    ledger = tmp_path / "costs.jsonl"
    monkeypatch.setattr(batch, "COSTS_LEDGER", ledger)
    monkeypatch.setenv("OWM_TERROIR_RUN", "r-test")
    summary = batch.usage_summary({"a": {"text": "", "usage": {"input_tokens": 1, "output_tokens": 1}}}, "claude-opus-5")
    batch._record_cost(provider="anthropic", model="claude-opus-5", batch_id="msgbatch_1",
                       sidecar=tmp_path / "02d-it.json", thinking="adaptive", summary=summary)
    row = json.loads(ledger.read_text().splitlines()[0])
    assert row["stage"] == "02d-it" and row["run"] == "r-test" and row["batch_id"] == "msgbatch_1"
    assert row["cost_usd"] == summary["cost_usd"] and row["thinking"] == "adaptive"
