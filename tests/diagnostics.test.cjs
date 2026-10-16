const {test} = require('node:test');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const {createRecorder, clean, MAX_BYTES} = require('../engine/web/shell/diagnostics.js');
const options = send => ({uuid: randomUUID, send});

test('chunks and backlog stay bounded during long offline sessions', async () => {
  let saved, sent;
  const r = createRecorder({...options(async c => { sent = c; throw Error('offline'); }), persist: q => { saved = JSON.parse(JSON.stringify(q)); }});
  for (let i = 0; i < 500; i++) r.record('test', '🔥'.repeat(1000));
  for (let i = 0; i < 30; i++) r.enqueue('periodic', {});
  assert.equal(saved.length, 16);
  assert.ok(saved.every(c => Buffer.byteLength(JSON.stringify(c)) <= MAX_BYTES));
  assert.ok(saved[0].dropped > 0);
  await assert.rejects(r.flush());
  assert.equal(r.status().pending, 16);
  const retry = createRecorder({...options(async c => ({ok: true, id: c.id, session: c.session})), restored: saved});
  await retry.flush();
  assert.equal(retry.status().pending, 0);
});

test('a false acknowledgement retains the exact chunk for retry', async () => {
  const attempts = []; let valid = false;
  const r = createRecorder(options(async c => { attempts.push(c.id); return {ok: true, id: valid ? c.id : 'wrong', session: c.session}; }));
  const id = r.enqueue('manual', {});
  await assert.rejects(r.flush()); assert.ok(r.has(id));
  valid = true; await r.flush(); assert.ok(!r.has(id));
  assert.deepEqual(attempts, [id, id]);
});

test('concurrent flushes do not duplicate in-flight requests', async () => {
  let resolve, requests = 0;
  const r = createRecorder(options(c => { requests++; return new Promise(r => { resolve = () => r({ok: true, id: c.id, session: c.session}); }); }));
  r.enqueue('manual', {});
  const a = r.flush(), b = r.flush();
  assert.equal(requests, 1); resolve(); await Promise.all([a, b]);
  assert.equal(r.status().pending, 0);
});

test('console storms are limited and secrets/query strings redacted', () => {
  let saved;
  const r = createRecorder({...options(async () => {}), persist: q => { saved = q; }});
  for (let i = 0; i < 1000; i++) r.log('warn', 'token=abc email@example.com https://host/path?secret=abc#hash');
  r.interval({}); r.enqueue('periodic', {});
  assert.equal(saved[0].events.filter(e => e.type === 'warn').length, 40);
  assert.equal(saved[0].events.find(e => e.type === 'suppressed').data.count, 960);
  assert.ok(!JSON.stringify(saved).includes('abc'));
  assert.equal(clean('password=hello'), 'password=[redacted]');
});

test('real authentication fails closed without a JWT or audience', async () => {
  const {authenticate} = await import('../functions/api/diagnostics.js');
  assert.equal(await authenticate(new Request('https://game.test'), {}), null);
  assert.equal(await authenticate(new Request('https://game.test', {headers: {'Cf-Access-Jwt-Assertion': 'invalid'}}), {ACCESS_AUD: 'test'}), null);
});

function request(body, origin = 'https://game.test') {
  return new Request('https://game.test/api/diagnostics', {method: 'POST', headers: {'Content-Type': 'application/json', Origin: origin}, body: JSON.stringify(body)});
}
const chunk = () => ({version: 1, session: randomUUID(), id: randomUUID(), sequence: 0, reason: 'manual', events: [{at: Date.now(), type: 'manual-report', data: {}}]});
const owner = async () => 'vladyslavprosolupov@gmail.com';

test('server awaits writes, enforces identity, and retries the same object key', async () => {
  const {handle} = await import('../functions/api/diagnostics.js');
  const writes = new Map(), body = {...chunk(), player: 'spoofed'};
  const env = {DIAGNOSTICS_ENABLED: 'true', DIAGNOSTICS: {put: async (k, v) => { writes.set(k, JSON.parse(v)); }}};
  const result = await handle(request(body), env, owner);
  assert.equal(result.status, 200); assert.equal((await result.json()).id, body.id);
  assert.equal(writes.size, 2); assert.equal([...writes.values()][0].player, await owner());
  await handle(request(body), env, owner); assert.equal(writes.size, 2);
  const failure = await handle(request(body), {DIAGNOSTICS_ENABLED: 'true', DIAGNOSTICS: {put: async () => { throw Error('storage'); }}}, owner);
  assert.equal(failure.status, 503);
});

test('rejects oversized bodies, invalid schema, foreign origins and unauthorized reads', async () => {
  const {handle} = await import('../functions/api/diagnostics.js');
  const env = {DIAGNOSTICS_ENABLED: 'true', DIAGNOSTICS: {put: async () => assert.fail('must not write')}};
  assert.equal((await handle(request(chunk()), env, async () => null)).status, 401);
  assert.equal((await handle(request(chunk(), 'https://evil.test'), env, owner)).status, 403);
  assert.equal((await handle(request({...chunk(), session: '../escape'}), env, owner)).status, 400);
  assert.equal((await handle(request({...chunk(), large: 'x'.repeat(70000)}), env, owner)).status, 413);
  assert.equal((await handle(new Request('https://game.test/api/diagnostics'), env, async () => 'romamitch@icloud.com')).status, 403);
});


test('engine log noise cannot consume the exception logging budget', () => {
  let saved;
  const r = createRecorder({...options(async () => {}), persist: q => { saved = q; }});
  for (let i = 0; i < 1000; i++) r.log('engine.filtered', 'frame noise');
  r.log('error', 'critical failure'); r.enqueue('manual', {});
  assert.ok(saved[0].events.some(e => e.type === 'error' && e.data === 'critical failure'));
});


test('server write gate defaults off and rejects before authorization or storage access', async () => {
  const {handle} = await import('../functions/api/diagnostics.js');
  for (const enabled of [undefined, false, true, 'false', 'TRUE', '1']) {
    const env = {DIAGNOSTICS_ENABLED: enabled, get DIAGNOSTICS() { assert.fail('disabled endpoint must not access storage'); }};
    const response = await handle(request(chunk()), env, () => assert.fail('disabled endpoint must not authorize'));
    assert.equal(response.status, 410);
  }
});

test('config status requires authentication, works without storage, and reports exact gate', async () => {
  const {handle} = await import('../functions/api/diagnostics.js');
  const req = () => new Request('https://game.test/api/diagnostics?config=1');
  assert.equal((await handle(req(), {}, async () => null)).status, 401);
  for (const enabled of [undefined, 'false', 'true']) {
    const response = await handle(req(), {DIAGNOSTICS_ENABLED: enabled}, async () => 'romamitch@icloud.com');
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {enabled: enabled === 'true'});
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
  }
});
