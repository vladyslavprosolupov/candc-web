const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {randomUUID} = require('node:crypto');
const {createRecorder} = require('../engine/web/shell/diagnostics.js');
const source = fs.readFileSync('engine/web/shell/diagnostics.js', 'utf8');

function browser(enabled, fetchImpl, restored = null) {
  const calls = {read: 0, write: 0, remove: 0, observer: 0, disconnected: 0};
  const listeners = new Map(), intervals = new Map(), timeouts = new Map(), frames = new Map();
  let next = 0;
  const target = () => ({addEventListener(type, fn) { listeners.set(fn, {type, target: this}); }, removeEventListener(type, fn) { listeners.delete(fn); }});
  const document = {...target(), getElementById: () => null, hasFocus: () => true, visibilityState: 'visible'};
  class Worker { constructor() { Object.assign(this, target()); } }
  const originals = {log() {}, info() {}, warn() {}, error() {}};
  const window = {...target(), document, Worker, Module: {gxDiagnosticsEnabled: true}};
  if (enabled !== undefined) window.gxDiagnosticsConfig = {enabled};
  const sandbox = {window, document, console: {...originals}, TextEncoder, crypto: {randomUUID}, AbortController,
    localStorage: {getItem() { calls.read++; return restored; }, setItem() { calls.write++; }, removeItem() { calls.remove++; }},
    navigator: {userAgent: 'test', onLine: true}, innerWidth: 100, innerHeight: 100, devicePixelRatio: 1,
    crossOriginIsolated: true, performance: {now: () => 100}, fetch: fetchImpl,
    setInterval(fn, ms) { const id = ++next; intervals.set(id, {fn, ms}); return id; }, clearInterval(id) { intervals.delete(id); },
    setTimeout(fn) { const id = ++next; timeouts.set(id, fn); return id; }, clearTimeout(id) { timeouts.delete(id); },
    requestAnimationFrame(fn) { const id = ++next; frames.set(id, fn); return id; }, cancelAnimationFrame(id) { frames.delete(id); },
    PerformanceObserver: class { constructor() { calls.observer++; } observe() {} disconnect() { calls.disconnected++; } },
  };
  vm.runInNewContext(source, sandbox);
  return {window, sandbox, originals, calls, listeners, intervals, timeouts, frames, Worker};
}
const settle = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

test('missing or false config performs absolutely no browser collection', () => {
  for (const config of [undefined, false]) {
    const b = browser(config, () => assert.fail('no fetch while off'));
    assert.equal(b.window.gxDiagnostics.enabled, false);
    b.window.gxDiagnostics.start(); b.window.gxDiagnostics.engine({}); b.window.gxDiagnostics.report();
    assert.deepEqual(b.calls, {read: 0, write: 0, remove: 0, observer: 0, disconnected: 0});
    for (const queue of [b.listeners, b.intervals, b.timeouts, b.frames]) assert.equal(queue.size, 0);
    for (const key of Object.keys(b.originals)) assert.equal(b.sandbox.console[key], b.originals[key]);
    assert.equal(b.window.Worker, b.Worker);
  }
});

test('disable restores hooks, removes worker/listener hooks, cancels work and aborts requests', async () => {
  const requests = [];
  const b = browser(true, async (url, options) => {
    requests.push({url, options});
    if (url.includes('config')) return {ok: true, json: async () => ({enabled: true})};
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(Error('aborted'))));
  });
  await settle();
  const api = b.window.gxDiagnostics;
  const worker = new b.window.Worker('engine.js');
  assert.ok([...b.listeners.values()].some(l => l.target === worker));
  api.engine({logicFrame: 30});
  const uploading = [...b.intervals.values()].find(i => i.ms === 30000).fn();
  await settle();
  const post = requests.find(r => r.options.method === 'POST');
  assert.ok(post);
  api.disable();
  await uploading;
  assert.equal(post.options.signal.aborted, true);
  assert.equal(b.window.gxDiagnostics.enabled, false);
  assert.equal(b.window.Module.gxDiagnosticsEnabled, false);
  assert.equal(b.window.Worker, b.Worker);
  for (const key of Object.keys(b.originals)) assert.equal(b.sandbox.console[key], b.originals[key]);
  for (const queue of [b.listeners, b.intervals, b.timeouts, b.frames]) assert.equal(queue.size, 0);
  assert.equal(b.calls.disconnected, 1); assert.equal(b.calls.remove, 1);
  const count = requests.length;
  api.engine({}); api.start(); api.report();
  await settle(); assert.equal(requests.length, count);
});

test('server kill switch discards restored chunks without resending', async () => {
  const restored = JSON.stringify([{version: 1, session: randomUUID(), id: randomUUID(), events: []}]);
  for (const status of [200, 410]) {
    const urls = [];
    const b = browser(true, async url => { urls.push(url); return {ok: status === 200, status, json: async () => ({enabled: false})}; }, restored);
    await settle();
    assert.equal(b.window.gxDiagnostics.enabled, false);
    assert.deepEqual(urls, ['/api/diagnostics?config=1']);
    assert.equal(b.calls.remove, 1);
  }
});

test('disabled recorder cannot resend restored or in-flight chunks', async () => {
  let resolve, sends = 0, persisted;
  const r = createRecorder({uuid: randomUUID, restored: [{id: 'old', session: 'old'}],
    persist: q => { persisted = q.slice(); }, send: c => { sends++; return new Promise(r => { resolve = () => r({ok: true, id: c.id, session: c.session}); }); }});
  const flushing = r.flush();
  r.disable(); resolve(); await flushing;
  r.record('ignored', {}); r.enqueue('manual', {}); await r.flush();
  assert.equal(sends, 1); assert.deepEqual(persisted, []); assert.equal(r.status().pending, 0);
});

test('enabled main and worker errors reach bounded chunks without serializing worker messages', async () => {
  const chunks = [];
  const b = browser(true, async (url, options) => {
    if (url.includes('config')) return {ok: true, json: async () => ({enabled: true})};
    const chunk = JSON.parse(options.body); chunks.push(chunk);
    return {ok: true, json: async () => ({ok: true, id: chunk.id, session: chunk.session})};
  });
  await settle();
  const api = b.window.gxDiagnostics;
  const worker = new b.window.Worker('engine.js');
  for (const [fn, listener] of b.listeners) {
    if (listener.type === 'error' && listener.target === worker) fn({message: 'worker failed token=private'});
    if (listener.type === 'error' && listener.target === b.window) fn({message: 'main failed'});
  }
  api.start(); await [...b.intervals.values()].find(i => i.ms === 30000).fn();
  assert.ok(chunks[0].events.some(e => e.type === 'error' && e.data.includes('worker: worker failed token=[redacted]')));
  assert.ok(chunks[0].events.some(e => e.type === 'error' && e.data === 'main failed'));
  api.disable(); assert.equal(api.enabled, false);
});
