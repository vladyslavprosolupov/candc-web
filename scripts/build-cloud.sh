#!/usr/bin/env bash
# Asset-free build from a clean checkout on Linux or macOS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/bootstrap.py
export PATH="$ROOT/.tools/build-tools/bin:$PATH"
source .tools/emsdk/emsdk_env.sh
export BUILD_JOBS="${BUILD_JOBS:-2}"
npm ci --ignore-scripts
bash scripts/build.sh
npm test
EXPORT_ARGS=()
if python3 -c 'import json; raise SystemExit(0 if json.load(open("engine/build/emscripten/web-diagnostics-build.json"))["enabled"] else 1)'; then
  EXPORT_ARGS+=(--diagnostics)
fi
python3 scripts/export-site.py "${EXPORT_ARGS[@]}"
# Pages consumes this ephemeral config after the source bundle captured OFF defaults.
python3 scripts/diagnostics-deployment-config.py --cloud-runtime
