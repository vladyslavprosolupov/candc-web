#!/usr/bin/env python3
"""Run permanent public-API SDL event queue regressions against the actual archive.

The default runs one SDL_CreateThread batch and 524288 raw-pthread events.
Use --threadless-baseline --raw-pthread-only to independently rebuild the
old SDL_PTHREADS=OFF configuration and reproduce missing queue delivery.
The baseline is intentionally expected to fail; no game build is modified.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdl-build', type=Path, default=ROOT / 'engine/build/emscripten/_deps/sdl3-build')
    parser.add_argument('--sdl-source', type=Path, default=ROOT / 'engine/build/emscripten/_deps/sdl3-src')
    parser.add_argument('--library', type=Path, help='Exercise a preserved SDL archive directly')
    parser.add_argument('--threadless-baseline', action='store_true', help='Build an isolated SDL_PTHREADS=OFF baseline (expected failure)')
    parser.add_argument('--raw-pthread-only', action='store_true', help='Run callback/worker queue stress without SDL thread creation')
    args = parser.parse_args()
    if args.threadless_baseline:
        if args.library:
            parser.error('--library and --threadless-baseline are mutually exclusive')
        args.sdl_build = ROOT / '.local/sdl-public-threadless-build'
        toolchain = ROOT / '.tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'
        subprocess.run(['cmake', '-S', str(args.sdl_source.resolve()), '-B', str(args.sdl_build), '-G', 'Ninja',
                        '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_C_FLAGS=-pthread -fwasm-exceptions',
                        '-DSDL_PTHREADS=OFF', '-DSDL_STATIC=ON', '-DSDL_SHARED=OFF',
                        '-DSDL_TEST_LIBRARY=OFF', '-DSDL_TESTS=OFF', '-DSDL_EXAMPLES=OFF',
                        '-DSDL_VIDEO=OFF', '-DSDL_AUDIO=OFF', '-DSDL_CAMERA=OFF',
                        '-DSDL_JOYSTICK=OFF', '-DSDL_HAPTIC=OFF', '-DSDL_SENSOR=OFF'], check=True, cwd=ROOT)
        subprocess.run(['cmake', '--build', str(args.sdl_build), '--target', 'SDL3-static', '-j', '8'], check=True, cwd=ROOT)
    library = args.library.resolve() if args.library else args.sdl_build.resolve() / 'libSDL3.a'
    if not library.is_file():
        parser.error(f'SDL archive not found: {library}')
    node = shutil.which('node')
    if not node:
        parser.error('Node.js is required to run the fixture')
    out = ROOT / '.local/sdl-event-queue-regression'
    out.mkdir(parents=True, exist_ok=True)
    emcc = ROOT / '.tools/emsdk/upstream/emscripten/emcc'
    defines = ['-DGX_QUEUE_RAW_ONLY'] if args.raw_pthread_only else []
    subprocess.run([str(emcc), *defines, '-O1', '-g', '-pthread', '-fwasm-exceptions',
                    '-I' + str(args.sdl_source.resolve() / 'include'),
                    str(ROOT / 'tests/sdl-event-queue.c'), str(library),
                    '-sENVIRONMENT=node', '-sEXIT_RUNTIME=1', '-sPTHREAD_POOL_SIZE=2',
                    '-sINITIAL_MEMORY=67108864', '-o', str(out / 'test.js')], check=True, cwd=ROOT)
    print(f'Running public SDL queue regression: {library}', flush=True)
    subprocess.run([node, str(out / 'test.js')], check=True, cwd=ROOT, timeout=45)


if __name__ == '__main__':
    main()
