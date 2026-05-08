"""Static HTTP server for wiki/ with Range request support.

PMTiles fetches tile bytes via HTTP Range. Python's built-in http.server
ignores Range and returns the full file on every request, which makes
pmtiles.js error out (or, on some maplibre versions, silently render no
tiles). We wrap SimpleHTTPRequestHandler to honour Range and return 206.

Run:
    uv run python scripts/serve.py
    # then open http://127.0.0.1:8765/map/
"""
from __future__ import annotations

import http.server
import os
import re
import socketserver
import sys
from pathlib import Path

PORT = int(os.environ.get("PORT", "8765"))
WIKI_ROOT = Path(__file__).resolve().parent.parent / "wiki"
os.chdir(WIKI_ROOT)


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()

        m = re.match(r"bytes=(\d+)-(\d*)", rng)
        if not m:
            return super().send_head()

        size = os.path.getsize(path)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        if start >= size or end >= size or start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        f = open(path, "rb")
        f.seek(start)
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        self._range_remaining = length
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        chunk = 64 * 1024
        while remaining > 0:
            buf = source.read(min(chunk, remaining))
            if not buf:
                break
            outputfile.write(buf)
            remaining -= len(buf)

    def guess_type(self, path):
        if path.endswith(".pmtiles"):
            return "application/octet-stream"
        return super().guess_type(path)


class ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReusableServer(("127.0.0.1", PORT), RangeHandler) as httpd:
        print(f"Serving {WIKI_ROOT} at http://127.0.0.1:{PORT}/", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nbye")
            sys.exit(0)
