"""Parity: the map page's WebMCP tools and the MCP server must answer alike.

Serves wiki/ locally, loads each locale's homepage in headless Chromium with a
stub `document.modelContext` that captures the tools app.js registers, calls
them, then asks the MCP server (mcp/test/mcp_calls.js, same wiki/ data) the
same questions and diffs the answers (page origin normalised). Needs a stage-04
build, Playwright and `npm ci` in mcp/.

    .venv/bin/python mcp/test/parity_webmcp.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]

CALLS = {
    "en": [
        ["search_appellations", {"query": "priorat"}],
        ["search_appellations", {"query": "naoussa"}],
        ["search_appellations", {"query": "agio oros"}],
        ["search_appellations", {"query": "saint", "country": "fr", "limit": 30}],
        ["filter_appellations", {"country": "es", "grape": "Garnacha", "limit": 200}],
        ["filter_appellations", {"scheme": "docg", "style": "red", "limit": 200}],
        ["filter_appellations", {"region": "Bourgogne", "include_sub_denominations": True, "limit": 200}],
        ["filter_appellations", {"grape": "malbec", "main_grape_only": True, "limit": 200}],
        ["filter_appellations", {"scheme": "es:vino-de-pago", "limit": 200}],
        ["filter_appellations", {"scheme": "Vino de Pago", "limit": 200}],
        ["filter_appellations", {"style": "!!"}],
        ["get_appellation", {"slug": "montsant"}],
        ["get_appellation", {"slug": "champagne"}],
        ["get_appellation", {"slug": "no-such-slug"}],
        ["list_facets", {}],
    ],
    "fr": [
        ["get_appellation", {"slug": "priorat"}],
        ["filter_appellations", {"region": "Catalunya", "limit": 200}],
        ["list_facets", {}],
    ],
    "nl": [["get_appellation", {"slug": "mosel"}], ["search_appellations", {"query": "mosel"}]],
}

STUB = """
window.__owmTools = {};
Object.defineProperty(document, 'modelContext', { value: {
  registerTool(t) { window.__owmTools[t.name] = t; },
}});
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def normalise(obj, origin: str):
    return json.loads(json.dumps(obj).replace(origin, "ORIGIN"))


def page_answers(page, base: str, locale: str, calls):
    page.goto(f"{base}/" if locale == "en" else f"{base}/{locale}/", wait_until="networkidle")
    page.wait_for_function("Object.keys(window.__owmTools).length >= 5", timeout=30000)
    out = []
    for name, args in calls:
        res = page.evaluate(
            "async ([n, a]) => window.__owmTools[n].execute(a)", [name, args]
        )
        out.append({"isError": True, "text": res["content"][0]["text"]} if res.get("isError")
                   else res["structuredContent"])
    return out


def mcp_answers(locale: str, calls):
    with_locale = [[n, {**a, "locale": locale}] for n, a in calls]
    proc = subprocess.run(["node", "test/mcp_calls.js"], cwd=ROOT / "mcp", input=json.dumps(with_locale),
                          capture_output=True, text=True, check=True)
    payload = json.loads(proc.stdout)
    return normalise(payload["results"], payload["origin"])


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "scripts/serve.py"], cwd=ROOT,
                              env={**os.environ, "PORT": str(port)},
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    failures = 0
    try:
        time.sleep(1.0)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-gl=swiftshader"])
            page = browser.new_page()
            page.add_init_script(STUB)
            for locale, calls in CALLS.items():
                web = normalise(page_answers(page, base, locale, calls), base)
                srv = mcp_answers(locale, calls)
                for (name, args), w, m in zip(calls, web, srv):
                    ok = w == m
                    failures += not ok
                    print(f"{'ok ' if ok else 'DIFF'} {locale} {name} {json.dumps(args, ensure_ascii=False)}")
                    if not ok:
                        print("   page:", json.dumps(w, ensure_ascii=False)[:600])
                        print("   mcp: ", json.dumps(m, ensure_ascii=False)[:600])
            browser.close()
    finally:
        server.terminate()
    print(f"{failures} difference(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
