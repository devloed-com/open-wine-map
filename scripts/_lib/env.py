"""Repo-root `.env` loading, shared by the stages that need a credential.

The LLM stages read provider keys straight from the environment; stage 04
needs the basemap key at *render* time (it is baked into the emitted app.js),
so it goes through the same `.env` that `scripts/deploy.sh` sources.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_WARNED = False


def load_dotenv() -> None:
    """Populate os.environ from a repo-root .env (KEY=VALUE lines); existing
    environment variables win."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def carto_basemap_key() -> str:
    """CARTO Basemaps key for the raster tile URLs — the default for every host
    without an entry in `carto_basemap_keys()`.

    Client-side by necessity — the browser issues the tile request, so the key
    is public once the map ships; it lives in `.env` (gitignored) rather than
    in the source so it is rotatable and stays out of git history.

    Empty when unset: the map still builds and every polygon still renders, but
    CARTO stamps "API KEY REQUIRED" across every basemap tile, so warn loudly —
    a silent watermark is exactly the failure this indirection can reintroduce.
    """
    global _WARNED
    load_dotenv()
    key = os.environ.get("CARTO_BASEMAP_KEY", "").strip()
    if not key and not _WARNED:
        _WARNED = True
        print(
            "WARNING: CARTO_BASEMAP_KEY is unset — the basemap will render with "
            "CARTO's 'API KEY REQUIRED' watermark. Set it in the repo-root .env.",
            file=sys.stderr,
        )
    return key


def carto_basemap_keys() -> dict[str, str]:
    """hostname → CARTO key, for hosts that must not share the default key
    (a per-environment quota, or a key referrer-locked to one host):

        CARTO_BASEMAP_KEYS=beta.openwinemap.com=cb1_…

    Like `plausible_sites()`, app.js picks the entry by `location.hostname`
    (leading `www.` stripped) at runtime and falls back to `carto_basemap_key()`,
    so one build serves every environment. Empty when unset."""
    return _host_map("CARTO_BASEMAP_KEYS")


def _host_map(var: str) -> dict[str, str]:
    """Parse a `host=value,host=value` .env variable into {host: value}; hosts
    are lower-cased with a leading `www.` stripped, malformed entries are
    warned about and skipped."""
    load_dotenv()
    out: dict[str, str] = {}
    raw = os.environ.get(var, "").strip()
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        if "=" not in entry:
            print(f"WARNING: {var} entry without '=': {entry!r} — ignored", file=sys.stderr)
            continue
        host, value = (p.strip() for p in entry.split("=", 1))
        host = host.lower().removeprefix("www.")
        if host and value:
            out[host] = value
    return out


PLAUSIBLE_HOST_DEFAULT = "https://analytics.dev.devloed.com"

# The production site's tracker script id. Public by nature (it is in every
# served page), so it lives here as the default rather than only in .env: a
# fresh checkout builds the same analytics wiring as the deployed site.
_PLAUSIBLE_SITES_DEFAULT = {"openwinemap.com": "pa-QAprx84urDZKvC3I6r6bc"}


def plausible_host() -> str:
    load_dotenv()
    return os.environ.get("PLAUSIBLE_HOST", PLAUSIBLE_HOST_DEFAULT).strip().rstrip("/")


def plausible_sites() -> dict[str, str]:
    """hostname → tracker-script id, one entry per deploy environment.

    Plausible's v2 tracker (`/js/pa-<id>.js`) pins the site domain inside the
    script — `init({domain})` cannot override it — so each environment has its
    own script and the page picks one by `location.hostname` at runtime. One
    build therefore serves every environment byte-identically; a host with no
    entry (localhost, a preview) loads no tracker at all.

    `PLAUSIBLE_SITES` in .env extends / overrides the default:
        PLAUSIBLE_SITES=openwinemap.com=pa-QAprx84urDZKvC3I6r6bc,beta.openwinemap.com=pa-xxxx
    Keys are matched with a leading `www.` stripped.
    """
    return {**_PLAUSIBLE_SITES_DEFAULT, **_host_map("PLAUSIBLE_SITES")}
