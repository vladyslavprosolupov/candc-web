import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'engine/build/emscripten/_deps/sdl3-src/src/events/SDL_events.c'
PATCH = ROOT / 'engine/Patches/sdl3-input-diagnostics.patch'
spec = importlib.util.spec_from_file_location('sdl_patch', ROOT / 'engine/scripts/web/apply-sdl-diagnostics.py')
sdl_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdl_patch)


class SdlPatchTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE.is_file(), 'configure SDL dependency first')
    def test_pinned_patch_is_reproducible_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            target = source / 'src/events/SDL_events.c'
            target.parent.mkdir(parents=True)
            target.write_bytes(SOURCE.read_bytes())
            if hashlib.sha256(target.read_bytes()).hexdigest() == sdl_patch.PATCHED:
                subprocess.run(['patch', '--batch', '-R', '-p1', '-i', str(PATCH)], cwd=source,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), sdl_patch.PRISTINE)
            sdl_patch.apply(source, PATCH)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), sdl_patch.PATCHED)
            modified = target.stat().st_mtime_ns
            sdl_patch.apply(source, PATCH)
            self.assertEqual(target.stat().st_mtime_ns, modified)
            target.write_text('source drift')
            with self.assertRaises(SystemExit):
                sdl_patch.apply(source, PATCH)
