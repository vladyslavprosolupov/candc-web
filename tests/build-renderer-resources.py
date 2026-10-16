#!/usr/bin/env python3
"""Build the production WebGL wrapper resource regression fixture."""
import json
import argparse
import shlex
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', nargs='?', choices=('resources', 'programs'), default='resources')
parser.add_argument('--renderer-ref', help='Compile a historical engine Git ref to verify that the fixture detects regressions')
options = parser.parse_args()
fixture = options.fixture
commands = json.loads((root / 'engine/build/emscripten/compile_commands.json').read_text())
entry = next(item for item in commands if item['file'].endswith('/d3d8webgl.cpp'))
args = shlex.split(entry['command'])
flags = [value for value in args[1:] if value.startswith(('-I', '-D', '-std='))]
suffix = 'baseline' if options.renderer_ref else 'test'
out = root / f'engine/web/dist/render-{fixture}-{suffix}'
out.mkdir(exist_ok=True)
(out / 'index.html').write_text('''<!doctype html><title>Renderer resources regression</title>
<canvas id="canvas"></canvas><pre id="output"></pre>
<script>var Module={canvas:document.querySelector('#canvas'),print:t=>document.querySelector('#output').textContent+=t+'\\n',printErr:console.error};</script>
<script src="test.js"></script>''')
with tempfile.TemporaryDirectory(prefix='renderer-regression-') as temporary:
    renderer = entry['file']
    if options.renderer_ref:
        directory = Path(temporary)
        for name in ('d3d8webgl.cpp', 'webgl_pipeline.cpp', 'webgl_pipeline.h'):
            source = subprocess.check_output(['git', 'show', options.renderer_ref +
                ':Core/Libraries/Source/d3d8webgl/src/' + name], cwd=root / 'engine')
            (directory / name).write_bytes(source)
        renderer = str(directory / 'd3d8webgl.cpp')
    subprocess.run([args[0], *flags, '-O1', '-sUSE_WEBGL2=1', '-sFULL_ES3=1',
                    '-sALLOW_MEMORY_GROWTH=1', str(root / f'tests/renderer-{fixture}.cpp'),
                    renderer, '-o', str(out / 'test.js')], check=True, cwd=root)
print(f'Open /render-{fixture}-{suffix}/ on the local asset server.')
