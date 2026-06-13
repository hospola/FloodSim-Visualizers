#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$DIR"

# Open browser once the server is ready
(sleep 2 && xdg-open http://localhost:5027 2>/dev/null || true) &

echo "Starting DanaSim Viewer at http://localhost:5027 ..."
./DanaSim.Viewer.Web "$@"
