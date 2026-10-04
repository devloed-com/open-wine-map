"""Build and publish the MCP server (mcp/) as a Bunny Edge Script.

The server is a standalone Edge Script with its own linked pull zone; its code
is uploaded as one bundled file (`npm run build` in mcp/ → mcp/dist/edge.js),
then published as a release whose note is the git commit. See
docs/plan-mcp-server.md.

Usage:
  .venv/bin/python scripts/deploy_mcp.py create NAME   one-time: create the
        script + linked pull zone, print its id and hostname
  .venv/bin/python scripts/deploy_mcp.py deploy [--script-id ID] [--no-build]
        build, upload, publish, then smoke-test the default hostname
  .venv/bin/python scripts/deploy_mcp.py info [--script-id ID]
  .venv/bin/python scripts/deploy_mcp.py delete --script-id ID

Env (repo-root .env):
  BUNNY_API_KEY          account API key (shared with deploy.py)
  BUNNY_MCP_SCRIPT_ID    the production script id (deploy / info default)
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.env import load_dotenv  # noqa: E402

MCP_DIR = ROOT / "mcp"
BUNDLE = MCP_DIR / "dist" / "edge.js"
API = "https://api.bunny.net"
SCRIPT_TYPE_STANDALONE = 1  # EdgeScriptTypes: 0 DNS, 1 CDN (standalone), 2 Middleware


def api(method: str, path: str, key: str, **kw) -> requests.Response:
    r = requests.request(method, f"{API}{path}", headers={"AccessKey": key}, timeout=60, **kw)
    if r.status_code >= 400:
        sys.exit(f"{method} {path} → {r.status_code} {r.text[:300]}")
    return r


def build() -> None:
    if not (MCP_DIR / "node_modules").exists():
        subprocess.run(["npm", "ci"], cwd=MCP_DIR, check=True)
    (MCP_DIR / "dist").mkdir(exist_ok=True)
    subprocess.run(["npm", "run", "build"], cwd=MCP_DIR, check=True)


def git_note() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "mcp", "scripts/_lib/assets"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return f"{sha}{'+dirty' if dirty else ''}"


def script_info(key: str, script_id: str) -> dict:
    return api("GET", f"/compute/script/{script_id}", key).json()


def hostnames(info: dict) -> list[str]:
    names = [info.get("DefaultHostname"), info.get("SystemHostname")]
    return [n.removeprefix("https://").removeprefix("http://").rstrip("/") for n in names if n]


def cmd_create(key: str, name: str) -> None:
    build()
    body = {
        "Name": name,
        "Code": BUNDLE.read_text(encoding="utf-8"),
        "ScriptType": SCRIPT_TYPE_STANDALONE,
        "CreateLinkedPullZone": True,
        "LinkedPullZoneName": name,
    }
    info = api("POST", "/compute/script", key, json=body).json()
    script_id = info["Id"]
    api("POST", f"/compute/script/{script_id}/publish", key, json={"Note": git_note()})
    info = script_info(key, script_id)
    print(json.dumps({"Id": script_id, "Hostnames": hostnames(info),
                      "LinkedPullZones": info.get("LinkedPullZones")}, indent=1))


def cmd_deploy(key: str, script_id: str, no_build: bool) -> None:
    if not no_build:
        build()
    code = BUNDLE.read_text(encoding="utf-8")
    api("POST", f"/compute/script/{script_id}/code", key, json={"Code": code})
    note = git_note()
    api("POST", f"/compute/script/{script_id}/publish", key, json={"Note": note})
    info = script_info(key, script_id)
    hosts = hostnames(info)
    print(f"published {len(code.encode()):,} bytes as release '{note}' → {hosts}", file=sys.stderr)
    if hosts:
        subprocess.run(["node", "test/smoke.js", f"https://{hosts[0]}/mcp"], cwd=MCP_DIR, check=False)


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("name")
    for name in ("deploy", "info", "delete"):
        p = sub.add_parser(name)
        p.add_argument("--script-id", default=os.environ.get("BUNNY_MCP_SCRIPT_ID"))
        if name == "deploy":
            p.add_argument("--no-build", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("BUNNY_API_KEY")
    if not key:
        sys.exit("set BUNNY_API_KEY in .env")
    if args.cmd == "create":
        cmd_create(key, args.name)
        return 0
    if not args.script_id:
        sys.exit("pass --script-id or set BUNNY_MCP_SCRIPT_ID")
    if args.cmd == "deploy":
        cmd_deploy(key, args.script_id, args.no_build)
    elif args.cmd == "info":
        info = script_info(key, args.script_id)
        info.pop("DeploymentKey", None)
        print(json.dumps(info, indent=1))
    elif args.cmd == "delete":
        api("DELETE", f"/compute/script/{args.script_id}", key)
        print(f"deleted script {args.script_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
