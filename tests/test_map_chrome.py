"""The map chrome's shared contracts: the CSS design tokens (one accent, kept
in step with the paint), and — as the UX pass adds them — the hover paint
state and the viewport meta."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import map_template as mt  # noqa: E402

CSS = mt._STYLE_CSS


def _token(name: str) -> str:
    m = re.search(name + r":(#[0-9a-fA-F]{3,6})", CSS)
    assert m, f"token {name} missing from :root"
    return m.group(1).lower()


def test_root_tokens_exist_and_are_used() -> None:
    assert ":root {" in CSS
    for name in ("--c-accent", "--c-pgi", "--c-spirit", "--c-cream", "--n-0", "--n-900",
                 "--n-dark-panel", "--note-bg"):
        _token(name)
        assert f"var({name})" in CSS, name
    assert CSS.count("var(--") > 100


def test_one_accent_colour() -> None:
    # The three former burgundies are one token; the browse page keeps its own CSS.
    body = CSS[CSS.index("}", CSS.index(":root {")) :]
    for old in ("#7a1f3a", "#7A1F2B", "#7a1f2b"):
        assert old not in body, old
    assert _token("--c-accent") == "#934050"


def test_tokens_match_the_paint_colours() -> None:
    src = inspect.getsource(mt._build_source_block).lower()
    assert _token("--c-accent") in src
    assert _token("--c-pgi") in src
