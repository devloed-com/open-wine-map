"""Stage 02b/grapes: a throttled or failing Wikipedia answer is retried and
never read as "no such article" (2026-10-22: a throttled run cached 1,108 of
1,113 (slug, locale) pairs as `missing`)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fetch_02b", ROOT / "scripts" / "02b_fetch_grape_lexicon.py")
fetch_02b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_02b)


class _Resp:
    def __init__(self, status: int, payload: dict | None = None, retry_after: str | None = None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = {"retry-after": retry_after} if retry_after else {}

    def json(self) -> dict:
        return self._payload


class _Session:
    def __init__(self, answers: list[_Resp]):
        self.answers = list(answers)
        self.calls = 0

    def get(self, url: str, timeout: float = 0) -> _Resp:
        self.calls += 1
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(fetch_02b.time, "sleep", lambda s: None)


def test_a_throttled_answer_is_retried():
    s = _Session([_Resp(429, retry_after="1"), _Resp(200, {"type": "standard", "title": "Timorasso"})])
    assert fetch_02b._try_one(s, "it", "Timorasso")["title"] == "Timorasso"
    assert s.calls == 2


def test_a_lasting_throttle_raises_instead_of_reading_as_missing():
    s = _Session([_Resp(429)])
    with pytest.raises(fetch_02b.TransientFetchError):
        fetch_02b._try_one(s, "it", "Timorasso")


def test_an_absent_article_is_none():
    assert fetch_02b._try_one(_Session([_Resp(404)]), "it", "Nessuna_pagina") is None


def test_a_lasting_throttle_stops_the_locale_after_three_slugs(tmp_path, monkeypatch):
    calls = []

    def _raise(session, lang, slug, donors, throttle):
        calls.append(slug)
        raise fetch_02b.TransientFetchError("429")

    monkeypatch.setattr(fetch_02b, "OUT_DIR", tmp_path)
    monkeypatch.setattr(fetch_02b, "_resolve_one", _raise)
    counts = fetch_02b._fetch_locale(None, "it", ["a", "b", "c", "d", "e"], refresh=False, throttle=0.0)
    assert calls == ["a", "b", "c"]
    assert counts["err"] == 3 and counts["ok"] == 0
    assert not list(tmp_path.glob("it/*.json"))
