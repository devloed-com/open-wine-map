"""The FR roster reader keeps the apostrophe of an elided article in the name
it stores ("muscat d'Alexandrie B" → "muscat d'alexandrie", not "muscat d
alexandrie"), while the words it matches stay space-joined, so no binding
moves (2026-10-30: 233 pills on 93 + 49 + 43 + 25 + 12 + 11 records)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.grape_lexicon import _tokenise_role_chunk, _with_source_apostrophes  # noqa: E402


def test_the_stored_name_keeps_the_source_apostrophe():
    toks = _tokenise_role_chunk("muscat d'Alexandrie B, pineau d’aunis N, len de l'El B, "
                                "rayon d'or B et grenache N")
    assert [(t["slug"], t["name"]) for t in toks] == [
        ("muscat-d-alexandrie", "muscat d'alexandrie"),
        ("pineau-d-aunis", "pineau d'aunis"),
        ("len-de-l-el", "len de l'el"),
        ("rayon-d-or", "rayon d'or"),
        ("grenache", "grenache"),
    ]


def test_a_space_in_the_source_stays_a_space():
    assert _with_source_apostrophes("muscat d alexandrie", "cépages : muscat d alexandrie") == \
        "muscat d alexandrie"
    assert _with_source_apostrophes("grenache", "grenache") == "grenache"
    assert _with_source_apostrophes("muscat d alexandrie", "no match here") == "muscat d alexandrie"
