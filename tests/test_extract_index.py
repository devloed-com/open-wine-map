"""A partial stage-02 run (`--only` / `--limit`) must merge into `_index.json`,
never replace it (the Italian run of 2026-10-22 left 7 of 524 records)."""
from __future__ import annotations

import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.extract_index import is_partial, wiki_index_kept, write_index  # noqa: E402


def test_full_run_replaces_and_partial_run_merges(tmp_path):
    idx = tmp_path / "_index.json"
    write_index(idx, {"a": {"n": 1}, "b": {"n": 1}}, partial=False)
    out = write_index(idx, {"b": {"n": 2}}, partial=True)
    assert out == {"a": {"n": 1}, "b": {"n": 2}}
    assert json.loads(idx.read_text(encoding="utf-8")) == out
    assert write_index(idx, {"c": {"n": 3}}, partial=False) == {"c": {"n": 3}}


def test_partial_run_over_a_corrupt_or_missing_index(tmp_path):
    idx = tmp_path / "_index.json"
    assert write_index(idx, {"a": {}}, partial=True) == {"a": {}}
    idx.write_text("[1, 2]", encoding="utf-8")
    assert write_index(idx, {"a": {}}, partial=True) == {"a": {}}
    idx.write_text("{not json", encoding="utf-8")
    assert write_index(idx, {"a": {}}, partial=True) == {"a": {}}


@pytest.mark.parametrize(
    "args,partial",
    [
        (Namespace(only=[], limit=0), False),
        (Namespace(only=["piemonte"], limit=0), True),
        (Namespace(only=[], limit=5), True),
        (Namespace(only=["x"]), True),
        (Namespace(), False),
    ],
)
def test_is_partial(args, partial):
    assert is_partial(args) is partial


def test_every_stage_02_with_a_record_filter_writes_through_the_helper():
    """Wiring lint: a stage 02 that can run partially must not write its index
    directly (the French extractor has its own drop-guarded merge)."""
    offenders = []
    for script in sorted((ROOT / "scripts").glob("*/02_extract_*.py")):
        src = script.read_text(encoding="utf-8")
        if '"--only"' not in src and '"--limit"' not in src:
            continue
        if "write_index(" not in src or re.search(r"INDEX_OUT(_PATH)?\.write_text\(", src):
            offenders.append(script.relative_to(ROOT).as_posix())
    assert not offenders, offenders


def test_wiki_index_kept_full_and_partial():
    """A full stage-03 run replaces its country's entries; a `--only` run
    replaces only the records it selected (2026-10-24: `03 --only collioure`
    had left one French entry in wiki/_index.json)."""
    existing = {"a": {"country": "fr"}, "b": {"country": "fr"}, "c": {"country": "es"}}
    assert wiki_index_kept(existing, "fr", partial=False) == {"c": {"country": "es"}}
    kept = wiki_index_kept(existing, "fr", partial=True)
    assert kept == existing and kept is not existing
    assert {**kept, "b": {"country": "fr", "n": 2}}["a"] == {"country": "fr"}


def test_every_stage_03_merges_through_the_helper():
    """Wiring lint: every stage-03 generator takes `--only` and must merge
    wiki/_index.json through `wiki_index_kept`, never by dropping its
    country's entries itself."""
    scripts = [ROOT / "scripts" / "03_generate_wiki.py",
               *sorted((ROOT / "scripts").glob("*/03_generate_wiki.py"))]
    offenders = []
    for script in scripts:
        src = script.read_text(encoding="utf-8")
        if '"--only"' not in src:
            continue
        if ("wiki_index_kept(" not in src or "partial=bool(args.only)" not in src
                or re.search(r'if v\.get\("country"\) != "[a-z]{2}"\}', src)):
            offenders.append(script.relative_to(ROOT).as_posix())
    assert len(scripts) >= 21
    assert not offenders, offenders
