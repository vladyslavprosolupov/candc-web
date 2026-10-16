#!/usr/bin/env python3
"""Compile the actual production audio cache against real Emscripten OpenAL."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('Core/GameEngineDevice/Source/OpenALAudioDevice')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accounting', action='store_true', help='Also verify decoded PCM and WebAudio float32 resident accounting')
    parser.add_argument('--engine-ref', help='Compile historical cache source/header instead of the working tree')
    args = parser.parse_args()
    print('Audio cache source: ' + (args.engine_ref or 'working tree'), flush=True)
    out = ROOT / '.local/audio-cache-regression'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='actual-audio-cache-') as temp:
        sources = Path(temp)
        # Preserve both production files byte-for-byte; only external dependencies
        # use fixture headers. Quoted local includes therefore use the real header.
        for name in ('OpenALAudioCache.cpp', 'OpenALAudioCache.h'):
            if args.engine_ref:
                data = subprocess.check_output(['git', '-C', str(ROOT / 'engine'), 'show', args.engine_ref + ':' + str(CACHE / name)])
            else:
                data = (ROOT / 'engine' / CACHE / name).read_bytes()
            (sources / name).write_bytes(data)
        shutil.copy2(ROOT / 'engine' / CACHE / 'OpenALBufferLease.h', sources / 'OpenALBufferLease.h')
        emcc = ROOT / '.tools/emsdk/upstream/emscripten/em++'
        defines = ['-DGX_TEST_CACHE_ACCOUNTING'] if args.accounting else []
        subprocess.run([str(emcc), *defines, '-std=c++20', '-O1', '-g', '-fwasm-exceptions',
                        '-I' + str(sources), '-I' + str(ROOT / 'tests/audio-cache-fixtures'),
                        str(ROOT / 'tests/audio-cache.cpp'), str(sources / 'OpenALAudioCache.cpp'),
                        '-lopenal', '-sENVIRONMENT=node', '-sEXIT_RUNTIME=1', '-sINITIAL_MEMORY=33554432',
                        '--pre-js', str(ROOT / 'tests/audio-cache-fixtures/audio-context.js'),
                        '-o', str(out / 'test.js')], check=True, cwd=ROOT)
    node = shutil.which('node')
    if not node:
        parser.error('Node.js is required')
    subprocess.run([node, str(out / 'test.js')], check=True, cwd=ROOT, timeout=30)


if __name__ == '__main__':
    main()
