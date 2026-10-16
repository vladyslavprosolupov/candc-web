const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function shell(stored = null, search = '', legacy = null) {
  const context = {window: {}, localStorage: {getItem: key => key === 'gx-render-fps' ? stored : legacy}, location: {search}, URLSearchParams};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('engine/web/shell/game.js', 'utf8'), context);
  return context;
}

test('fresh installation renders up to 120 without overriding the game-speed flag', () => {
  const s = shell();
  assert.equal(s.gxRenderFpsLimit(), 120);
  assert.deepEqual(Array.from(s.gxGameArguments()), []);
});

test('explicit lower render preferences survive relaunch', () => {
  for (const fps of [30, 60, 90, 120]) {
    const s = shell(String(fps));
    assert.equal(s.gxRenderFpsLimit(), fps);
    assert.deepEqual(Array.from(s.gxGameArguments()), []);
  }
});

test('invalid or legacy over-limit render settings fall back to 120', () => {
  for (const value of ['', '0', '-30', 'garbage', '60oops', '144', '480', 'Infinity']) {
    assert.equal(shell(value).gxRenderFpsLimit(), 120, value);
  }
});

test('explicit diagnostic engine arguments are preserved', () => {
  assert.deepEqual(Array.from(shell(null, '?args=-noshellmap+-fps+30').gxGameArguments()),
    ['-noshellmap', '-fps', '30']);
});

test('existing installations migrate the old 30 FPS default and preserve other lower limits', () => {
  assert.equal(shell(null, '', '30').gxRenderFpsLimit(), 120);
  for (const fps of [60, 90, 120]) {
    assert.equal(shell(null, '', String(fps)).gxRenderFpsLimit(), fps);
  }
  assert.equal(shell('30', '', '120').gxRenderFpsLimit(), 30);
});
