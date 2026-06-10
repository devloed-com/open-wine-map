"""Shared pytest fixtures.

`fixture_text` loads a redacted regulator-document excerpt from
tests/fixtures/ — see tests/fixtures/README.md for the conventions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_text():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load
