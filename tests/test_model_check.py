"""The newest-model-of-its-family guard (scripts/_lib/model_check.py)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from _lib import model_check as mc

NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
MODELS = [
    {"id": "claude-sonnet-5", "display_name": "Claude Sonnet 5", "created_at": "2026-05-01T00:00:00+00:00"},
    {"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5", "created_at": "2026-09-01T00:00:00+00:00"},
    {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "created_at": "2026-08-01T00:00:00+00:00"},
    {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5", "created_at": "2025-10-01T00:00:00+00:00"},
]


@pytest.fixture(autouse=True)
def _check_on(monkeypatch):
    monkeypatch.delenv("OWM_SKIP_MODEL_CHECK", raising=False)


def _fetch(calls):
    def f():
        calls.append(1)
        return MODELS
    return f


def test_family_reads_the_model_line():
    assert mc.family("claude-sonnet-5-5") == "sonnet"
    assert mc.family("claude-opus-5") == "opus"
    assert mc.family("mistral-medium-latest") is None


def test_an_older_default_stops_the_run_before_anything_is_submitted(tmp_path):
    with pytest.raises(SystemExit) as e:
        mc.ensure_latest("claude-sonnet-5", stage="02e", cache=tmp_path / "m.json", fetch=_fetch([]), now=NOW)
    assert "claude-sonnet-5-5" in str(e.value) and "--model claude-sonnet-5" in str(e.value)


def test_the_newest_passes_and_other_families_do_not_count(tmp_path):
    calls = []
    for model in ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-4-5"):
        mc.ensure_latest(model, cache=tmp_path / "m.json", fetch=_fetch(calls), now=NOW)
    assert calls == [1]                                     # one API call, then the cache


def test_the_list_is_cached_for_a_day(tmp_path):
    cache, calls = tmp_path / "m.json", []
    mc.list_models(cache=cache, fetch=_fetch(calls), now=NOW)
    assert mc.list_models(cache=cache, fetch=_fetch(calls), now=NOW + timedelta(hours=23))[1] == "cache"
    assert mc.list_models(cache=cache, fetch=_fetch(calls), now=NOW + timedelta(hours=25))[1] == "api"
    assert len(calls) == 2
    assert json.loads(cache.read_text())["models"] == MODELS


def test_a_failed_refresh_falls_back_to_the_stale_cache_then_warns(tmp_path, capsys):
    cache = tmp_path / "m.json"
    mc.list_models(cache=cache, fetch=_fetch([]), now=NOW)

    def boom():
        raise RuntimeError("offline")
    models, how = mc.list_models(cache=cache, fetch=boom, now=NOW + timedelta(days=3))
    assert models == MODELS and how.startswith("stale-cache")
    mc.ensure_latest("claude-sonnet-5-5", cache=tmp_path / "none.json", fetch=boom, now=NOW)
    assert "unchecked" in capsys.readouterr().err           # no list at all: warn, do not block


def test_a_model_missing_from_the_list_warns(tmp_path, capsys):
    mc.ensure_latest("claude-sonnet-9", cache=tmp_path / "m.json", fetch=_fetch([]), now=NOW)
    assert "not in the account's model list" in capsys.readouterr().err


def test_the_skip_switch_and_non_claude_models_never_call_the_api(tmp_path, monkeypatch):
    calls = []
    mc.ensure_latest("mistral-medium-latest", cache=tmp_path / "m.json", fetch=_fetch(calls), now=NOW)
    monkeypatch.setenv("OWM_SKIP_MODEL_CHECK", "1")
    mc.ensure_latest("claude-sonnet-5", cache=tmp_path / "m.json", fetch=_fetch(calls), now=NOW)
    assert calls == []


def test_an_explicit_model_is_never_checked(monkeypatch):
    from _lib import providers
    seen = []
    monkeypatch.setattr(providers, "ensure_latest", lambda m, **kw: seen.append(m))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    providers.make_provider("anthropic", model="claude-sonnet-4-6", stage="02e")
    providers.make_provider("anthropic", model=None, stage="02e")
    assert seen == [providers.stage_default("02e")[0]]
