#!/usr/bin/env bash
set -euo pipefail

# Trampoline to scripts/deploy.py — publishes wiki/ to Bunny Storage via
# the HTTP API and purges the CDN cache. See deploy.py for env vars.
#
# The .env sourced below also carries CARTO_BASEMAP_KEY, which is a *build*-time
# variable: stage 04 bakes it into the emitted app.js tile URLs. It is listed
# here because .env is the one place credentials live; deploy.py itself never
# reads it. Rebuild (04_build_maps.py) after rotating it, then deploy.

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec .venv/bin/python scripts/deploy.py "$@"
