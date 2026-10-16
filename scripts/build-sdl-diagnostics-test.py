#!/usr/bin/env python3
"""Build/run a real patched SDL queue regression; requires a diagnostics-enabled SDL build.

Use --threadless-baseline to build an isolated SDL_PTHREADS=OFF baseline:
the real SDL_CreateThread check must fail there. Add --raw-pthread-stress
to reproduce the callback/worker queue race without SDL thread creation.
The default library uses the current engine build, which must pass every check.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdl-build', type=Path, default=ROOT / 'engine/build/emscripten/_deps/sdl3-build', help='Directory containing the real libSDL3.a to exercise')
    parser.add_argument('--sdl-source', type=Path, default=ROOT / 'engine/build/emscripten/_deps/sdl3-src')
    parser.add_argument('--off-library', type=Path, help='Additionally verify an independently built default-OFF SDL archive has no custom symbols')
    parser.add_argument('--threadless-baseline', action='store_true', help='Build isolated SDL_PTHREADS=OFF baseline in .local (expected fixture failure)')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--raw-pthread-stress', action='store_true', help='Explicitly simulate browser callbacks vs worker polling with real pthreads (including intentionally threadless SDL baseline)')
    args = parser.parse_args()
    if args.threadless_baseline:
        args.sdl_build = ROOT / '.local/sdl-threadless-build'
        toolchain = ROOT / '.tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'
        subprocess.run(['cmake', '-S', str(args.sdl_source.resolve()), '-B', str(args.sdl_build), '-G', 'Ninja',
                        '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_C_FLAGS=-pthread -fwasm-exceptions -DGX_WEB_INPUT_DIAGNOSTICS',
                        '-DSDL_PTHREADS=OFF', '-DSDL_STATIC=ON', '-DSDL_SHARED=OFF',
                        '-DSDL_TEST_LIBRARY=OFF', '-DSDL_TESTS=OFF', '-DSDL_EXAMPLES=OFF',
                        '-DSDL_VIDEO=OFF', '-DSDL_AUDIO=OFF', '-DSDL_CAMERA=OFF',
                        '-DSDL_JOYSTICK=OFF', '-DSDL_HAPTIC=OFF', '-DSDL_SENSOR=OFF'], check=True, cwd=ROOT)
        subprocess.run(['cmake', '--build', str(args.sdl_build), '--target', 'SDL3-static', '-j', '8'], check=True, cwd=ROOT)
    library = args.sdl_build.resolve() / 'libSDL3.a'
    if not library.is_file():
        parser.error(f'SDL archive not found: {library}')
    nm = ROOT / '.tools/emsdk/upstream/bin/llvm-nm'
    symbols = subprocess.check_output([str(nm), '--defined-only', '--quiet', str(library)], text=True)
    helpers = ('SDL_GXSetInputDiagnosticsEnabled', 'SDL_GXGetInputDiagnostics')
    if not all(name in symbols for name in helpers):
        parser.error('SDL lacks diagnostics helpers; build with GX_WEB_DIAGNOSTICS=1 first')
    if args.off_library:
        off_symbols = subprocess.check_output([str(nm), '--defined-only', '--quiet', str(args.off_library.resolve())], text=True)
        if any(name in off_symbols for name in helpers):
            parser.error('Default-OFF SDL library unexpectedly contains diagnostics helpers')
        print('PASS default-OFF SDL archive omits diagnostics helpers', flush=True)
    out = ROOT / '.local/sdl-diagnostics-regression'
    out.mkdir(parents=True, exist_ok=True)
    emcc = ROOT / '.tools/emsdk/upstream/emscripten/emcc'
    defines = ['-DGX_TEST_RAW_PTHREAD_STRESS'] if args.raw_pthread_stress else []
    subprocess.run([str(emcc), *defines, '-O1', '-g', '-pthread', '-fwasm-exceptions',
                    '-I' + str(args.sdl_source.resolve() / 'include'),
                    str(ROOT / 'tests/sdl-diagnostics.c'), str(library),
                    '-sENVIRONMENT=node', '-sEXIT_RUNTIME=1', '-sPTHREAD_POOL_SIZE=2',
                    '-sINITIAL_MEMORY=67108864',
                    '-o', str(out / 'test.js')], check=True, cwd=ROOT)
    print(f'Built {out / "test.js"}', flush=True)
    if not args.build_only:
        node = shutil.which('node')
        if not node:
            parser.error('Node.js is required to run the fixture')
        subprocess.run([node, str(out / 'test.js')], check=True, cwd=ROOT, timeout=60)


if __name__ == '__main__':
    main()
