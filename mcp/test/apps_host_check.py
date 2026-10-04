"""Renders the MCP Apps view (dist/view.html) the way an MCP Apps host does
and checks the map draws: the view on its own origin under the CSP the spec
prescribes (ext-apps SEP-1865 "CSP Construction from Metadata"), driven by the
SDK's AppBridge, tiles from a local Range + CORS server over wiki/map-data.

Two policies: `spec` is the spec's reference CSP verbatim (it has no
worker-src, so blob: workers fall back to script-src and are refused);
`claude` adds `worker-src 'self' blob:` as Claude's sandbox does. MapLibre
needs a blob: worker, so `claude` must draw and `spec` is expected not to.

    (cd mcp && npm run build:view)
    .venv/bin/python mcp/test/apps_host_check.py [--shots DIR]
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "mcp"
sys.path.insert(0, str(ROOT / "scripts"))
import serve  # noqa: E402  — the Range-capable static handler
from _lib.env import load_dotenv  # noqa: E402

load_dotenv()
CARTO = "https://*.basemaps.cartocdn.com"


def reference_csp(connect: list[str], resource: list[str], worker_blob: bool) -> str:
    r, c = " ".join(resource), " ".join(connect)
    csp = (f"default-src 'none'; script-src 'self' 'unsafe-inline' {r}; style-src 'self' 'unsafe-inline' {r}; "
           f"connect-src 'self' {c}; img-src 'self' data: {r}; font-src 'self' {r}; media-src 'self' data: {r}; "
           "frame-src 'none'; object-src 'none'; base-uri 'self'")
    return csp + ("; worker-src 'self' blob:" if worker_blob else "")


def serve_dir(handler, port: int):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TileHandler(serve.RangeHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, ETag, Accept-Ranges")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Match, If-None-Match")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def tool_result(slugs: list[str], site: str) -> dict:
    ctx = json.loads((ROOT / "wiki/data/mcp/en.json").read_text(encoding="utf-8"))
    out = []
    for s in slugs:
        r = ctx["aocs"][s]
        out.append({"slug": s, "name": r["name"], "kind": r.get("kind"), "classification": r.get("class_label"),
                    "region": r.get("region"), "country_name": r.get("country"), "url": f"{site}/en/{s}",
                    "bbox": r.get("bbox_villages") or r.get("bbox")})
    bb = [b["bbox"] for b in out]
    union = [min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb)]
    return {"appellations": out, "bbox": union, "map_url": out[0]["url"], "unknown": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=Path, default=None)
    ap.add_argument("--live", metavar="MCP_URL", default=None,
                    help="render the view resource as served by this endpoint (its own tiles + CSP)")
    args = ap.parse_args()
    host_js = subprocess.run(
        ["npx", "esbuild", "test/apps-host/host.js", "--bundle", "--format=iife", "--platform=browser"],
        cwd=MCP, capture_output=True, text=True, check=True).stdout

    tiles = serve_dir(functools.partial(TileHandler, directory=str(ROOT / "wiki")), 0)
    tile_origin = f"http://127.0.0.1:{tiles.server_address[1]}"
    view_tpl = (MCP / "dist/view.html").read_text(encoding="utf-8")
    config = {"tileOrigin": tile_origin, "cartoKey": os.environ.get("CARTO_BASEMAP_KEY", ""),
              "labels": {"open": "Open ↗", "nothing": "none", "waiting": "waiting", "appellations": "appellations"}}
    view_html = view_tpl.replace("__OWM_VIEW_CONFIG__", json.dumps(config))
    domains = [tile_origin, CARTO]
    if args.live:
        live = json.loads(subprocess.run(["node", "test/read_view.js", args.live], cwd=MCP,
                                         capture_output=True, text=True, check=True).stdout)
        view_html = live["text"]
        tile_origin = live["csp"]["connectDomains"][0]
        domains = live["csp"]["connectDomains"]
    csps = {"spec": reference_csp(domains, domains, False), "claude": reference_csp(domains, domains, True)}

    class ViewHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            policy = "claude" if "claude" in self.path else "spec"
            body = view_html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", csps[policy])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    view_srv = serve_dir(ViewHandler, 0)
    # A different hostname from the host page → a different origin.
    view_origin = f"http://localhost:{view_srv.server_address[1]}"
    result = tool_result(["priorat", "montsant"], "https://www.openwinemap.com")

    def host_page(policy: str, theme: str) -> str:
        return (f"<!doctype html><meta charset=utf-8><body style='margin:0' data-theme='{theme}'>"
                f"<script id=tool-result type=application/json>{json.dumps(result)}</script>"
                f"<iframe id=view data-src='{view_origin}/view?{policy}' sandbox='allow-scripts allow-same-origin' "
                f"style='width:720px;height:420px;border:0'></iframe><script>{host_js}</script>")

    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-gl=swiftshader"])
        for policy, expect_map in (("claude", True), ("spec", False)):
            for theme in (("light", "dark") if expect_map else ("light",)):
                page = browser.new_page(viewport={"width": 760, "height": 640})
                msgs: list[str] = []
                page.on("console", lambda m: msgs.append(f"{m.type}: {m.text}"))
                tile_hits = []
                page.on("request", lambda r: tile_hits.append(r.url) if r.url.startswith(tile_origin) else None)
                page.set_content(host_page(policy, theme), wait_until="load")
                page.wait_for_timeout(9000)
                frame = next(f for f in page.frames if f.url.startswith(view_origin))
                title = frame.evaluate("document.getElementById('title').textContent")
                status = frame.evaluate("document.getElementById('status').textContent")
                painted = frame.evaluate("""() => { const c = document.querySelector('#map canvas');
                    if (!c) return 0; const g = c.getContext('webgl2') || c.getContext('webgl');
                    return c.width * c.height; }""")
                csp_errors = [m for m in msgs if "Content Security Policy" in m or "Refused" in m]
                features = frame.evaluate("window.__owmView ? window.__owmView.features() : -1")
                drew = features > 0 and title.startswith("2 ") and not status
                print(f"{policy:6} {theme:5} title={title!r} status={status!r} canvas={painted} "
                      f"features={features} tile_requests={len(tile_hits)} csp_errors={len(csp_errors)} host={page.evaluate('window.__hostLog')}")
                for m in (csp_errors[:3] if drew == expect_map else msgs[:12]):
                    print("    ", m[:300])
                if args.shots:
                    args.shots.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(args.shots / f"view-{policy}-{theme}.png"))
                if drew != expect_map:
                    ok = False
                    print(f"    UNEXPECTED: drew={drew}, expected {expect_map}")
                page.close()
        browser.close()
    tiles.shutdown()
    view_srv.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
