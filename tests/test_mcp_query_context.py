"""The MCP server's query context (/data/mcp/<locale>.json) is the contract
between stage 04 and the edge script (mcp/src/context.js): a key stage 04 stops
writing, or one the script starts reading, fails silently at runtime (a filter
that matches nothing). Pin both sides."""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import map_template as mt  # noqa: E402

CONTEXT_JS = ROOT / "mcp" / "src" / "context.js"
WIKI = ROOT / "wiki"


def test_context_js_reads_exactly_the_written_keys():
    src = CONTEXT_JS.read_text(encoding="utf-8")
    read = set(re.findall(r"\bctx\.([a-z_]+)\b", src))
    assert read == set(mt.QUERY_CONTEXT_KEYS), read ^ set(mt.QUERY_CONTEXT_KEYS)


def test_supported_format_matches():
    src = CONTEXT_JS.read_text(encoding="utf-8")
    formats = json.loads(re.search(r"SUPPORTED_FORMATS = (\[[^\]]*\])", src).group(1))
    assert mt.QUERY_CONTEXT_FORMAT in formats


def test_query_core_inlines_as_a_classic_script():
    inline = mt._QUERY_CORE_INLINE
    assert not re.search(r"^\s*(?:import|export)\b", inline, flags=re.M)
    assert "function createQueryCore" in inline and "TOOL_DEFS" in inline


def test_app_js_carries_the_query_core_token():
    assert mt._APP_JS_SOURCE.count("__OWM_query_core__") == 1


@pytest.mark.skipif(not (WIKI / "data" / "mcp" / "en.json").exists(), reason="no wiki/ build")
@pytest.mark.parametrize("locale", ["en", "fr", "es", "nl"])
def test_built_context(locale):
    ctx = json.loads((WIKI / "data" / "mcp" / f"{locale}.json").read_text(encoding="utf-8"))
    assert set(ctx) == set(mt.QUERY_CONTEXT_KEYS)
    assert ctx["format_version"] == mt.QUERY_CONTEXT_FORMAT
    assert ctx["locale"] == locale
    assert set(ctx["labels"]) == set(mt.QUERY_CONTEXT_LABELS)
    # Same records as the page's startup bundle, same fields.
    blob = glob.glob(str(WIKI / "data" / f"aocs.{locale}.*.js"))[0]
    text = Path(blob).read_text(encoding="utf-8")
    startup = json.loads(text[text.index("{"):text.rindex("}") + 1])["aocs"]
    assert ctx["aocs"] == startup
    assert all(set(v) == {"name"} for v in ctx["grapes_info"].values())
