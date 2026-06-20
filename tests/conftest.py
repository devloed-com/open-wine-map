"""Shared pytest fixtures.

`fixture_text` loads a redacted regulator-document excerpt from
tests/fixtures/ — see tests/fixtures/README.md for the conventions.

`_grape_vocab_snapshot` (autouse, session) feeds the grape matcher a
committed vocabulary snapshot when the gitignored `raw/vivc/by-slug`
corpus is absent (CI). Without it the matcher's `exact_index` loses every
VIVC prime/synonym surface, so dozens of grape surfaces fall through to
fuzzy matching and pick the wrong slug (`Weißer Riesling` -> raeuschling),
failing the Phase-5 parser fixture tests on CI while they pass locally.
Locally (raw/ present) it is a no-op — the live vocabulary is used.
Regenerate the snapshot with tests/fixtures/gen_grape_vocab_snapshot.py.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture
def fixture_text():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(autouse=True, scope="session")
def _grape_vocab_snapshot():
    from _lib import grape_entity

    if grape_entity._VIVC_DIR.exists():
        # Live VIVC corpus present (local / full pipeline) — use it as-is.
        yield
        return

    snapshot_path = FIXTURES / "grape_vocab_snapshot.json.gz"
    if not snapshot_path.exists():
        pytest.fail(
            f"{snapshot_path} is missing and raw/vivc/by-slug is absent — "
            "regenerate it with tests/fixtures/gen_grape_vocab_snapshot.py "
            "from a checkout with a populated raw/.",
        )

    exact = json.loads(gzip.decompress(snapshot_path.read_bytes()).decode("utf-8"))
    vocab = grape_entity.Vocabulary(exact_index=exact, names=tuple(exact.keys()))

    original = grape_entity._load_vocabulary
    grape_entity._load_vocabulary = lambda: vocab
    try:
        yield
    finally:
        grape_entity._load_vocabulary = original
