const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = 'engine/build/emscripten/GeneralsMD/GeneralsXZH.js';

test('compiled Emscripten telemetry bridge copies all fields and contains collector errors', {skip: !fs.existsSync(path)}, () => {
  const generated = fs.readFileSync(path, 'utf8');
  const marker = generated.indexOf('window.gxDiagnostics.engine({');
  assert.ok(marker > 0, 'build the instrumented engine before running this regression');
  const prefix = generated.slice(0, marker);
  const starts = [...prefix.matchAll(/^  \d+: (\([^\n]*\) => \{)/gm)];
  const last = starts.at(-1);
  assert.ok(last, 'generated ASM_CONST function boundary');
  const start = last.index + last[0].indexOf(last[1]);
  const end = generated.indexOf('\n  },', marker) + '\n  }'.length;
  const source = generated.slice(start, end);
  const heap = new Uint32Array(32);
  for (let i = 0; i < 24; i++) heap[i + 1] = i + 100;
  let snapshot, errors = 0;
  const context = {HEAPU32: heap, growMemViews() {}, UTF8ToString: () => 'Maps/USA04/USA04.map',
    window: {gxDiagnostics: {engine: value => { snapshot = value; }}}, console: {error: () => errors++}};
  const bridge = vm.runInNewContext('(' + source + ')', context);
  assert.doesNotThrow(() => bridge(4, 0));
  assert.equal(snapshot.logicFrame, 113);
  assert.equal(snapshot.focusWindow, 119);
  assert.equal(snapshot.sdlButtons, 122);
  assert.equal(snapshot.map, 'Maps/USA04/USA04.map');
  assert.equal(errors, 0);
  context.window.gxDiagnostics.engine = () => { throw new Error('collector failure'); };
  assert.doesNotThrow(() => bridge(4, 0));
  assert.equal(errors, 1);
});
