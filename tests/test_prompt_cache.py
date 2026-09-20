"""Prompt-cache block shapes (scripts/_lib/prompt_cache.py) and the batch hash."""
from __future__ import annotations

from _lib import batch
from _lib import prompt_cache as pc


def test_cached_system_puts_the_shared_block_first(monkeypatch):
    monkeypatch.delenv(pc.TTL_ENV, raising=False)
    out = pc.cached_system("THE LIEN", "the instructions")
    assert out == [
        {"type": "text", "text": "THE LIEN", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "the instructions"},
    ]
    assert pc.system_text(out) == "THE LIEN\n\nthe instructions"
    assert pc.cached_system("", "the instructions") == "the instructions"


def test_ttl_switches(monkeypatch):
    monkeypatch.setenv(pc.TTL_ENV, "1h")
    assert pc.cache_control() == {"type": "ephemeral", "ttl": "1h"}
    assert pc.mark_cached("S")[0]["cache_control"]["ttl"] == "1h"
    monkeypatch.setenv(pc.TTL_ENV, "off")
    assert pc.cache_control() is None
    assert pc.cached_system("A", "B") == "A\n\nB"
    assert pc.mark_cached("S") == "S"


def test_split_user_lead_formats_both_halves():
    ask, doc = pc.split_user_lead("Sub-section: {label}\n\nText of the spec:\n\n{lien}", label="Soils", lien="Clay.")
    assert (ask, doc) == ("Sub-section: Soils", "Text of the spec:\n\nClay.")


def test_batch_request_id_is_stable_for_block_systems_and_distinct_from_flat_text():
    blocks = pc.cached_system("A", "B")
    assert batch._request_id(blocks, "u") == batch._request_id(list(blocks), "u")
    assert batch._request_id(blocks, "u") != batch._request_id("A\n\nB", "u")
    p = batch._anthropic_params("claude-sonnet-5", {"system": blocks, "user": "u", "max_tokens": 10}, "disabled")
    assert p["system"] is blocks and p["messages"] == [{"role": "user", "content": "u"}]


def test_phase_groups_keep_first_appearance_order_and_untagged_requests():
    reqs = [{"custom_id": "a", "phase": "n"}, {"custom_id": "b", "phase": "h"}, {"custom_id": "c", "phase": "n"},
            {"custom_id": "d", "phase": None}]
    groups = batch._phase_groups(reqs)
    assert [(ph, [r["custom_id"] for r in rs]) for ph, rs in groups] == [("n", ["a", "c"]), ("h", ["b"]), (None, ["d"])]


def test_run_phased_submits_one_batch_per_phase_in_order(monkeypatch, tmp_path):
    calls = []

    def fake_run_batch(provider, model, reqs, *, sidecar, poll_interval=0, thinking=None):
        calls.append((sidecar.name, [r["custom_id"] for r in reqs]))
        return {r["custom_id"]: {"text": "ok"} for r in reqs}

    monkeypatch.setattr(batch, "run_batch", fake_run_batch)
    reqs = [{"custom_id": "a", "phase": "n"}, {"custom_id": "b", "phase": "h"}, {"custom_id": "c", "phase": "n"}]
    out = batch.run_phased("anthropic", "m", reqs, sidecar=tmp_path / "02d-it.json")
    assert calls == [("02d-it.p0.json", ["a", "c"]), ("02d-it.p1.json", ["b"])]
    assert set(out) == {"a", "b", "c"}
    # a single phase falls through to one batch with the plain sidecar
    calls.clear()
    batch.run_phased("anthropic", "m", [{"custom_id": "x", "phase": None}], sidecar=tmp_path / "02d-it.json")
    assert calls == [("02d-it.json", ["x"])]


def test_collecting_provider_records_the_phase_and_phased_lien_ttl(monkeypatch):
    c = batch.CollectingProvider()
    c.chat(system="s", user="u", cache_phase="facteurs_naturels")
    assert c.requests[0]["phase"] == "facteurs_naturels"
    monkeypatch.delenv(pc.TTL_ENV, raising=False)
    monkeypatch.setenv(batch.PHASED_ENV, "1")
    assert pc.cached_system("L", "R", phased=True)[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert pc.cached_system("L", "R")[0]["cache_control"] == {"type": "ephemeral"}
    monkeypatch.setenv(batch.PHASED_ENV, "0")
    assert not batch.phased()
    assert pc.cached_system("L", "R", phased=True)[0]["cache_control"] == {"type": "ephemeral"}
