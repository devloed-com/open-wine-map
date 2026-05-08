#!/usr/bin/env bash
set -euo pipefail

# Publishes wiki/ to the Bunny.net storage zone and purges the CDN cache.
# Requires:
#   - rclone configured with remote `open-wine-map` (FTP, explicit TLS)
#   - env BUNNY_API_KEY (account API key, NOT the storage zone FTP password)
#   - env BUNNY_PULLZONE_ID (numeric, from dash.bunny.net/cdn/<id>)

: "${BUNNY_API_KEY:?set BUNNY_API_KEY (account API key from dashboard → account → API)}"
: "${BUNNY_PULLZONE_ID:?set BUNNY_PULLZONE_ID (numeric, from dash.bunny.net/cdn/<id>)}"

cd "$(dirname "$0")/.."

rclone sync wiki/ open-wine-map: \
  --exclude 'map-data/*.geojson' \
  --exclude '_index.json' \
  --transfers 4 --checkers 4 \
  --timeout 60s --contimeout 30s --retries 5 --low-level-retries 10 \
  --inplace \
  --progress

curl -fsS -X POST \
  "https://api.bunny.net/pullzone/${BUNNY_PULLZONE_ID}/purgeCache" \
  -H "AccessKey: ${BUNNY_API_KEY}"

echo
echo "deployed. https://www.openwinemap.com/"
