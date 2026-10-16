const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('first static-host visit reloads even after clients.claim; failure cannot loop', async () => {
  const source = fs.readFileSync('engine/web/shell/coi-serviceworker.js', 'utf8');
  const values = new Map();
  let reloads = 0;
  const context = {
    window: { crossOriginIsolated: false, isSecureContext: true,
      location: { pathname: '/game/', reload() { reloads++; } } },
    document: { currentScript: { src: 'https://example.test/game/coi-serviceworker.js' } },
    navigator: { serviceWorker: { controller: {}, ready: Promise.resolve(),
      register: async () => ({ scope: '/game/', update: async () => {} }) } },
    sessionStorage: { getItem: k => values.get(k), setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) },
    console: { log() {}, warn() {}, error() {} }
  };
  async function visit() {
    vm.runInNewContext(source, context);
    await new Promise(resolve => setImmediate(resolve));
  }
  await visit();
  assert.equal(reloads, 1);
  await visit();
  assert.equal(reloads, 1);
  assert.equal(context.window.gxCoiPending, false);
  context.window.crossOriginIsolated = true;
  await visit();
  assert.equal(values.size, 0);
});
