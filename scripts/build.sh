#!/usr/bin/env bash
# Compile the real Zero Hour engine and assemble its browser shell.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -d .tools/build-tools/bin ]]; then
  export PATH="$ROOT/.tools/build-tools/bin:$PATH"
fi
if [[ ! -f .tools/emsdk/emsdk_env.sh ]]; then
  echo "Missing local Emscripten SDK. See README.md." >&2
  exit 1
fi
source .tools/emsdk/emsdk_env.sh
export EMSCRIPTEN_ROOT="$ROOT/.tools/emsdk/upstream/emscripten"
FFMPEG_DIR="$(python3 -c 'import hashlib, pathlib, tempfile; p=str(pathlib.Path.cwd()); print(pathlib.Path(tempfile.gettempdir()) / ("generals-ffmpeg-" + hashlib.sha256(p.encode()).hexdigest()[:12]))')"
cmake --preset emscripten -S engine -DGX_WEB_INPUT_DIAGNOSTICS="${GX_WEB_DIAGNOSTICS:-OFF}" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DFFMPEG_EM_PREFIX="$FFMPEG_DIR" -DFFMPEG_BUILD_JOBS="${BUILD_JOBS:-8}"
cmake --build engine/build/emscripten --target z_generals -j "${BUILD_JOBS:-8}"
# Record the successful binary mode and hash; failed builds cannot masquerade as ready.
python3 scripts/write-build-manifest.py engine/build/emscripten
# A clean source build has no private installation or prepacked asset index.
mkdir -p engine/web/dist/assets
if [[ ! -f engine/web/dist/assets/builds.json ]]; then
  printf '[]\n' > engine/web/dist/assets/builds.json
fi
engine/scripts/web/make-dist.sh --skip-assets
