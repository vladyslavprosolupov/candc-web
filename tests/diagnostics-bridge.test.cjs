const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = 'engine/build/emscripten/GeneralsMD/GeneralsXZH.js';

test('compiled Emscripten telemetry bridge copies all fields and contains collector errors', {skip: !fs.existsSync(path)}, () => {
  const generated = fs.readFileSync(path, 'utf8');
  const marker = generated.indexOf('window.gxDiagnostics.engine({');
  const manifest = JSON.parse(fs.readFileSync('engine/build/emscripten/web-diagnostics-build.json', 'utf8'));
  if (!manifest.enabled) {
    assert.equal(marker, -1, 'compiled-off engine has no telemetry bridge');
    assert.ok(!generated.includes('sdl.error.worker'));
    return;
  }
  assert.ok(marker > 0, 'enabled build contains the telemetry bridge');
  const prefix = generated.slice(0, marker);
  const starts = [...prefix.matchAll(/^  \d+: (\([^\n]*\) => \{)/gm)];
  const last = starts.at(-1);
  assert.ok(last, 'generated ASM_CONST function boundary');
  const start = last.index + last[0].indexOf(last[1]);
  const end = generated.indexOf('\n  },', marker) + '\n  }'.length;
  const source = generated.slice(start, end);
  const heap = new Uint32Array(64);
  for (let i = 0; i < 48; i++) heap[i + 1] = i + 100;
  let snapshot, errors = 0;
  const context = {HEAPU32: heap, growMemViews() {}, UTF8ToString: () => 'Maps/USA04/USA04.map',
    window: {gxDiagnostics: {enabled: true, log() {}, engine: value => { snapshot = value; }}}, console: {error: () => errors++}};
  const bridge = vm.runInNewContext('(' + source + ')', context);
  assert.doesNotThrow(() => bridge(4, 0, 0, 0));
  assert.equal(snapshot.logicFrame, 113);
  assert.equal(snapshot.focusWindow, 119);
  assert.equal(snapshot.sdlButtons, 122);
  assert.equal(snapshot.map, 'Maps/USA04/USA04.map');
  assert.equal(snapshot.pollCalls, 124);
  assert.equal(snapshot.wasmHeapBytes, 129 * 65536);
  assert.equal(snapshot.sdlInternal.enqueueFailed, 136);
  assert.equal(snapshot.sampleSequence, 143);
  assert.equal(snapshot.sdlInternal.queueCount, 145);
  assert.equal(snapshot.sdlInternal.hasHead, true);
  assert.equal(errors, 0);
  heap[30] = 65536; // wasm32's 4GiB limit must not wrap to zero.
  bridge(4, 0, 0, 0);
  assert.equal(snapshot.wasmHeapBytes, 4294967296);
  context.window.gxDiagnostics.engine = () => { throw new Error('collector failure'); };
  assert.doesNotThrow(() => bridge(4, 0, 0, 0));
  assert.equal(errors, 1);
});
