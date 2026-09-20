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
