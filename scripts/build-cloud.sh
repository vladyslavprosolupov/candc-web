#!/usr/bin/env bash
# Asset-free build from a clean checkout on Linux or macOS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/diagnostics-deployment-config.py --verify-runtime --requested-mode "${GX_WEB_DIAGNOSTICS:-OFF}"
python3 scripts/bootstrap.py
export PATH="$ROOT/.tools/build-tools/bin:$PATH"
source .tools/emsdk/emsdk_env.sh
export BUILD_JOBS="${BUILD_JOBS:-2}"
printf 'Requested temporary diagnostics: %s; build jobs: %s\n' "${GX_WEB_DIAGNOSTICS:-OFF}" "$BUILD_JOBS"
python3 --version
node --version
cmake --version
.tools/emsdk/upstream/emscripten/emcc --version
npm ci --ignore-scripts
python3 scripts/ci-build.py --log .local/engine-build.log -- bash scripts/build.sh
npm test
EXPORT_ARGS=()
if python3 -c 'import json; raise SystemExit(0 if json.load(open("engine/build/emscripten/web-diagnostics-build.json"))["enabled"] else 1)'; then
  EXPORT_ARGS+=(--diagnostics)
fi
python3 scripts/export-site.py "${EXPORT_ARGS[@]}"
python3 scripts/diagnostics-deployment-config.py --verify-runtime
python3 -c 'import json; print("Exported build:", json.load(open("release/build.json")))'
