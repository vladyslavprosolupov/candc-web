#!/usr/bin/env python3
"""Bind temporary diagnostics compile mode to an exact successful WASM binary."""
import hashlib
import json
from pathlib import Path
import sys


def cmake_enabled(value):
    value = value.upper()
    return value not in {'', '0', 'OFF', 'NO', 'FALSE', 'N', 'IGNORE', 'NOTFOUND'} and not value.endswith('-NOTFOUND')


def write_manifest(build):
    cache = (build / 'CMakeCache.txt').read_text()
    value = next(line.split('=', 1)[1] for line in cache.splitlines() if line.startswith('GX_WEB_INPUT_DIAGNOSTICS:BOOL='))
    wasm = build / 'GeneralsMD/GeneralsXZH.wasm'
    manifest = {'enabled': cmake_enabled(value), 'wasmSha256': hashlib.sha256(wasm.read_bytes()).hexdigest()}
    (build / 'web-diagnostics-build.json').write_text(json.dumps(manifest) + '\n')
    return manifest


if __name__ == '__main__':
    write_manifest(Path(sys.argv[1]))
