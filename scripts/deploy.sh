#!/usr/bin/env bash
set -euo pipefail

# Trampoline to scripts/deploy.py — publishes wiki/ to Bunny Storage via
# the HTTP API and purges the CDN cache. See deploy.py for env vars.

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec .venv/bin/python scripts/deploy.py "$@"
