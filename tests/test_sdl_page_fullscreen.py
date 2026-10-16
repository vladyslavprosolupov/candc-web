import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = Path('src/video/emscripten/SDL_emscriptenvideo.c')
SOURCE = ROOT / 'engine/build/emscripten/_deps/sdl3-src' / DRIVER
PATCH = ROOT / 'engine/Patches/sdl3-page-fullscreen.patch'
spec = importlib.util.spec_from_file_location(
    'fullscreen_patch', ROOT / 'engine/scripts/web/apply-sdl-page-fullscreen.py')
fullscreen_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fullscreen_patch)

# Compile the actual pinned driver function against a small browser/SDL fixture.
# MAIN_THREAD_EM_ASM_INT models the DOM ownership query (foreign vs SDL canvas).
STUBS = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef int SDL_FullscreenResult;
typedef int SDL_FullscreenOp;
enum { SDL_FULLSCREEN_FAILED=-1, SDL_FULLSCREEN_SUCCEEDED=0, SDL_FULLSCREEN_PENDING=1,
       SDL_FULLSCREEN_OP_LEAVE=0, SDL_FULLSCREEN_OP_ENTER=1,
       EMSCRIPTEN_RESULT_SUCCESS=0, EMSCRIPTEN_RESULT_DEFERRED=1,
       EMSCRIPTEN_FULLSCREEN_SCALE_STRETCH=0, EMSCRIPTEN_FULLSCREEN_SCALE_ASPECT=1,
       EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_NONE=0, EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_HIDEF=1,
       EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_STDDEF=2, EMSCRIPTEN_FULLSCREEN_FILTERING_DEFAULT=0,
       SDL_WINDOW_FULLSCREEN=1, SDL_WINDOW_HIGH_PIXEL_DENSITY=2 };
typedef struct { int unused; } SDL_VideoDevice, SDL_VideoDisplay;
typedef struct { bool fullscreen_change_in_progress; const char *canvas_id;
                 int fullscreen_mode_flags; bool fullscreen_resize; } SDL_WindowData;
typedef struct { SDL_WindowData *internal; bool fullscreen_exclusive; int flags; } SDL_Window;
typedef struct { bool isFullscreen; } EmscriptenFullscreenChangeEvent;
typedef struct { int scaleMode,canvasResolutionScaleMode,filteringMode;
                 void (*canvasResizedCallback)(void); void *canvasResizedCallbackUserData; } EmscriptenFullscreenStrategy;
static bool browser_fullscreen, foreign_fullscreen;
static int exits, entries;
#define MAIN_THREAD_EM_ASM_INT(...) foreign_fullscreen
#define SDL_zero(x) memset(&(x),0,sizeof(x))
static void Emscripten_HandleCanvasResize(void) {}
static int emscripten_get_fullscreen_status(EmscriptenFullscreenChangeEvent *event) {
    event->isFullscreen=browser_fullscreen; return EMSCRIPTEN_RESULT_SUCCESS;
}
static int emscripten_exit_fullscreen(void) { ++exits; browser_fullscreen=false; return EMSCRIPTEN_RESULT_SUCCESS; }
static int emscripten_request_fullscreen_strategy(const char *canvas,int defer,EmscriptenFullscreenStrategy *strategy) {
    ++entries; browser_fullscreen=true; return EMSCRIPTEN_RESULT_SUCCESS;
}
'''
CASES = r'''
int main(void) {
    SDL_WindowData data={0}; data.canvas_id="#canvas";
    SDL_Window window={.internal=&data};
    // SDL_OnWindowShown applies non-fullscreen pending flags during game boot.
    browser_fullscreen=true; foreign_fullscreen=true;
    if (Emscripten_SetWindowFullscreen(NULL,&window,NULL,SDL_FULLSCREEN_OP_LEAVE)!=SDL_FULLSCREEN_SUCCEEDED || exits || !browser_fullscreen) {
        fputs("SDL boot exited page-owned fullscreen\n",stderr); return 1;
    }
    // SDL is still allowed to leave fullscreen when its own canvas owns it.
    data.fullscreen_change_in_progress=false; foreign_fullscreen=false;
    if (Emscripten_SetWindowFullscreen(NULL,&window,NULL,SDL_FULLSCREEN_OP_LEAVE)!=SDL_FULLSCREEN_SUCCEEDED || exits!=1 || browser_fullscreen) return 2;
    // Applying normal flags in a normal page never asks the browser to exit.
    data.fullscreen_change_in_progress=false;
    if (Emscripten_SetWindowFullscreen(NULL,&window,NULL,SDL_FULLSCREEN_OP_LEAVE)!=SDL_FULLSCREEN_SUCCEEDED || exits!=1) return 3;
    // Native SDL canvas fullscreen entry remains available.
    data.fullscreen_change_in_progress=false;
    if (Emscripten_SetWindowFullscreen(NULL,&window,NULL,SDL_FULLSCREEN_OP_ENTER)!=SDL_FULLSCREEN_SUCCEEDED || entries!=1) return 4;
    return 0;
}
'''


@unittest.skipUnless(SOURCE.is_file(), 'configure SDL dependency first')
class SdlPageFullscreenTests(unittest.TestCase):
    def pristine(self, source):
        target = source / DRIVER
        target.parent.mkdir(parents=True)
        target.write_bytes(SOURCE.read_bytes())
        if hashlib.sha256(target.read_bytes()).hexdigest() == fullscreen_patch.PATCHED:
            subprocess.run(['patch', '--batch', '-R', '-p1', '-i', str(PATCH)], cwd=source,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), fullscreen_patch.PRISTINE)
        return target

    def run_driver(self, target, directory):
        source = target.read_text()
        # Skip the prototype; take the function definition nearest the end.
        start = source.rindex('static SDL_FullscreenResult Emscripten_SetWindowFullscreen(')
        end = source.index('\nstatic ', start + 1)
        fixture = directory / 'driver.c'
        fixture.write_text(STUBS + source[start:end] + CASES)
        executable = directory / 'driver'
        subprocess.run(['cc', '-std=c99', str(fixture), '-o', str(executable)], check=True,
                       capture_output=True, text=True)
        return subprocess.run([str(executable)], capture_output=True, text=True)

    @unittest.skipUnless(shutil.which('cc'), 'C compiler required')
    def test_actual_driver_preserves_page_fullscreen_but_releases_own_canvas(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            target = self.pristine(directory)
            old = self.run_driver(target, directory)
            self.assertEqual(old.returncode, 1)
            self.assertIn('SDL boot exited page-owned fullscreen', old.stderr)
            fullscreen_patch.apply(directory)
            fixed = self.run_driver(target, directory)
            self.assertEqual(fixed.returncode, 0, fixed.stderr)

    def test_patch_is_reproducible_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            target = self.pristine(directory)
            fullscreen_patch.apply(directory)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), fullscreen_patch.PATCHED)
            modified = target.stat().st_mtime_ns
            fullscreen_patch.apply(directory)
            self.assertEqual(target.stat().st_mtime_ns, modified)
            target.write_text('source drift')
            with self.assertRaises(SystemExit):
                fullscreen_patch.apply(directory)


if __name__ == '__main__':
    unittest.main()
