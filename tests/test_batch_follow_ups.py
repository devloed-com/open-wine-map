"""The batch follow-up round (scripts/_lib/batch.py `run_two_pass(..., follow_ups=True)`):
a stage that asks a second question on reading an answer gets one more batch, writes
only after it, and resumes without resubmitting the main batch."""
from __future__ import annotations

import json

import pytest
from _lib import batch

EMPTY = '{"facts": []}'
FULL = '{"facts": [{"bullet": "Deep red."}]}'


def _stage(writes):
    """A one-record stage loop: a main call and, when the answer is the empty
    list, a follow-up; the 'write' is recorded with the provider kind, the way
    the 02d scripts route a `collecting` provider's writes to a scratch dir."""
    def run_loop(prov):
        raw = prov.chat(system="S", user="ask", max_tokens=10, cache_phase="produit")
        if raw == EMPTY:
            raw = prov.chat(system="S", user="ask again", max_tokens=10, cache_phase="produit",
                            follow_up=True)
        writes.append((prov.kind, raw))
    return run_loop


MAIN = batch._request_id("S", "ask")
AGAIN = batch._request_id("S", "ask again")


def _fake_run_batch(calls, answers, *, fail_on=None):
    def run_batch(provider, model, reqs, *, sidecar, poll_interval=0, thinking=None):
        calls.append((sidecar.name, [r["custom_id"] for r in reqs]))
        if fail_on and sidecar.name == fail_on:
            raise RuntimeError("interrupted")
        return {r["custom_id"]: {"text": answers[r["custom_id"]], "usage": {"input_tokens": 1, "output_tokens": 1}}
                for r in reqs}
    return run_batch


def test_follow_up_round_submits_one_more_batch_and_writes_once(monkeypatch, tmp_path):
    calls, writes = [], []
    monkeypatch.setattr(batch, "run_batch", _fake_run_batch(calls, {MAIN: EMPTY, AGAIN: FULL}))
    monkeypatch.setenv(batch.PHASED_ENV, "0")
    stats = batch.run_two_pass(provider="anthropic", model="m", sidecar=tmp_path / "02d-gr.json",
                               run_loop=_stage(writes), follow_ups=True)
    assert calls == [("02d-gr.json", [MAIN]), ("02d-gr.r1.json", [AGAIN])]
    # pass 1 collects (""), the probe reads the empty answer and collects the follow-up (""),
    # the final replay writes the second reading
    assert writes == [("collecting", ""), ("collecting", ""), ("anthropic-api", FULL)]
    assert stats["n_results"] == 2 and stats["usage"]["n_with_usage"] == 2
    assert not list(tmp_path.iterdir()), "no sidecar or stored answers left behind"


def test_without_follow_ups_the_behaviour_is_unchanged(monkeypatch, tmp_path):
    calls, writes = [], []
    monkeypatch.setattr(batch, "run_batch", _fake_run_batch(calls, {MAIN: EMPTY, AGAIN: FULL}))
    monkeypatch.setenv(batch.PHASED_ENV, "0")
    batch.run_two_pass(provider="anthropic", model="m", sidecar=tmp_path / "02e-gr.json",
                       run_loop=_stage(writes))
    assert calls == [("02e-gr.json", [MAIN])]
    # the stage's follow-up has no answer: "" and the first answer stands — never an exception
    assert writes == [("collecting", ""), ("anthropic-api", "")]


def test_no_follow_up_when_the_first_answer_is_not_empty(monkeypatch, tmp_path):
    calls, writes = [], []
    monkeypatch.setattr(batch, "run_batch", _fake_run_batch(calls, {MAIN: FULL}))
    monkeypatch.setenv(batch.PHASED_ENV, "0")
    batch.run_two_pass(provider="anthropic", model="m", sidecar=tmp_path / "02d-gr.json",
                       run_loop=_stage(writes), follow_ups=True)
    assert calls == [("02d-gr.json", [MAIN])]
    assert writes == [("collecting", ""), ("collecting", FULL), ("anthropic-api", FULL)]


def test_an_interrupted_follow_up_batch_resumes_without_resubmitting_the_main_one(monkeypatch, tmp_path):
    calls, writes = [], []
    sidecar = tmp_path / "02d-gr.json"
    monkeypatch.setenv(batch.PHASED_ENV, "0")
    monkeypatch.setattr(batch, "run_batch",
                        _fake_run_batch(calls, {MAIN: EMPTY, AGAIN: FULL}, fail_on="02d-gr.r1.json"))
    with pytest.raises(RuntimeError):
        batch.run_two_pass(provider="anthropic", model="m", sidecar=sidecar,
                           run_loop=_stage(writes), follow_ups=True)
    stored = tmp_path / "02d-gr.results.json"
    assert json.loads(stored.read_text())[MAIN]["text"] == EMPTY
    assert writes == [("collecting", ""), ("collecting", "")], "nothing written before the round ends"
    calls.clear()
    writes.clear()
    monkeypatch.setattr(batch, "run_batch", _fake_run_batch(calls, {MAIN: EMPTY, AGAIN: FULL}))
    batch.run_two_pass(provider="anthropic", model="m", sidecar=sidecar,
                       run_loop=_stage(writes), follow_ups=True)
    assert calls == [("02d-gr.r1.json", [AGAIN])], "the main batch is not resubmitted"
    assert writes[-1] == ("anthropic-api", FULL)
    assert not stored.exists()


def test_replay_provider_collects_follow_ups_once_and_still_raises_for_a_changed_prompt():
    rp = batch.ReplayProvider({MAIN: {"text": EMPTY}}, kind="anthropic-api")
    assert rp.chat(system="S", user="ask") == EMPTY
    assert rp.chat(system="S", user="ask again", follow_up=True, cache_phase="produit") == ""
    assert rp.chat(system="S", user="ask again", follow_up=True) == ""
    assert [r["custom_id"] for r in rp.follow_ups] == [AGAIN]
    assert rp.follow_ups[0]["phase"] == "produit"
    with pytest.raises(RuntimeError, match="no result"):
        rp.chat(system="S", user="something else")
