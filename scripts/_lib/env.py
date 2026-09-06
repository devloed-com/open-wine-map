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
    """CARTO Basemaps key for the raster tile URLs.

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
