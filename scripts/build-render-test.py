#!/usr/bin/env python3
"""Build a tiny browser GPU regression fixture against the production renderer."""
import json, shlex, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
commands=json.loads((root/'engine/build/emscripten/compile_commands.json').read_text())
entry=next(e for e in commands if e['file'].endswith('/d3d8webgl.cpp'))
args=shlex.split(entry['command'])
flags=[v for v in args[1:] if v.startswith(('-I','-D','-std='))]
out=root/'engine/web/dist/render-test';out.mkdir(exist_ok=True)
(out/'index.html').write_text('''<!doctype html><title>Renderer regression</title><canvas id="canvas"></canvas><pre id="output"></pre>
<script>var Module={canvas:document.querySelector('#canvas'),print:t=>document.querySelector('#output').textContent+=t+'\\n',printErr:console.error};</script><script src="test.js"></script>''')
subprocess.run([args[0],*flags,'-O1','-sUSE_WEBGL2=1','-sFULL_ES3=1','-sALLOW_MEMORY_GROWTH=1',str(root/'tests/renderer.cpp'),entry['file'],'-o',str(out/'test.js')],check=True,cwd=root)
print('Open http://localhost:8080/render-test/')
