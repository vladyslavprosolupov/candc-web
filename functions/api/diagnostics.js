// GeneralsX @feature Codex 16/10/2026 Private, acknowledged diagnostic chunks.
import {createRemoteJWKSet, jwtVerify} from 'jose';

const issuer = 'https://proud-sunset-7e91.cloudflareaccess.com';
const keys = createRemoteJWKSet(new URL(issuer + '/cdn-cgi/access/certs'));
const players = new Set(['vladyslavprosolupov@gmail.com', 'romamitch@icloud.com', 'cr.tracker12@proton.me']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const json = (value, status = 200) => Response.json(value, {status, headers: {
  'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
  'Cross-Origin-Resource-Policy': 'same-origin',
}});

export async function authenticate(request, env) {
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token || !env.ACCESS_AUD) return null;
  try {
    const {payload} = await jwtVerify(token, keys, {issuer, audience: env.ACCESS_AUD, algorithms: ['RS256']});
    return players.has(payload.email) ? payload.email : null;
  } catch { return null; }
}

async function readBounded(request) {
  if (Number(request.headers.get('Content-Length')) > 65536) throw new Error('size');
  const reader = request.body?.getReader();
  if (!reader) throw new Error('body');
  const chunks = []; let size = 0;
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > 65536) { await reader.cancel(); throw new Error('size'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder().decode(bytes));
}

// Authentication is injectable only for unit tests, never via HTTP or configuration.
export async function handle(request, env, authorize = authenticate) {
  // TEMPORARY diagnostics kill switch: reject writes before authentication or storage.
  if (request.method === 'POST' && env.DIAGNOSTICS_ENABLED !== 'true')
    return json({error: 'diagnostics disabled'}, 410);
  const email = await authorize(request, env);
  if (!email) return json({error: 'unauthorized'}, 401);
  const url = new URL(request.url);
  if (request.method === 'GET' && url.searchParams.get('config') === '1')
    return json({enabled: env.DIAGNOSTICS_ENABLED === 'true'});
  if (!env.DIAGNOSTICS) return json({error: 'storage unavailable'}, 503);
  if (request.method === 'POST') {
    if (request.headers.get('Origin') !== url.origin ||
        !request.headers.get('Content-Type')?.startsWith('application/json')) return json({error: 'origin or type'}, 403);
    let body;
    try { body = await readBounded(request); }
    catch (e) { return json({error: 'invalid chunk'}, e.message === 'size' ? 413 : 400); }
    if (body?.version !== 1 || !uuid.test(body.session) || !uuid.test(body.id) ||
        !['periodic', 'manual', 'pagehide'].includes(body.reason) ||
        !Number.isSafeInteger(body.sequence) || body.sequence < 0 ||
        !Array.isArray(body.events) || body.events.length > 256 ||
        !body.events.every(e => e && Number.isFinite(e.at) && typeof e.type === 'string' && e.type.length <= 80))
      return json({error: 'invalid schema'}, 400);
    const date = new Date().toISOString().slice(0, 10);
    const key = `sessions/${date}/${body.session}/${body.id}.json`;
    const stored = JSON.stringify({...body, receivedAt: new Date().toISOString(), player: email});
    // Await durable storage before acknowledging. Retries reuse the UUID/key.
    try {
      await env.DIAGNOSTICS.put(key, stored, {httpMetadata: {contentType: 'application/json'}});
      if (body.reason === 'manual') await env.DIAGNOSTICS.put(`reports/${date}/${body.id}.json`, stored,
        {httpMetadata: {contentType: 'application/json'}});
    } catch { return json({error: 'storage failed'}, 503); }
    return json({ok: true, id: body.id, session: body.session});
  }
  if (request.method !== 'GET') return json({error: 'method'}, 405);
  if (email !== 'vladyslavprosolupov@gmail.com') return json({error: 'forbidden'}, 403);
  const key = url.searchParams.get('key');
  if (key) {
    if (!/^(sessions\/\d{4}-\d{2}-\d{2}\/[0-9a-f-]{36}|reports\/\d{4}-\d{2}-\d{2})\/[0-9a-f-]{36}\.json$/.test(key)) return json({error: 'key'}, 400);
    const object = await env.DIAGNOSTICS.get(key);
    return object ? new Response(object.body, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}}) : json({error: 'not found'}, 404);
  }
  const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10);
  const session = url.searchParams.get('session');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || (session && !uuid.test(session))) return json({error: 'filter'}, 400);
  const prefix = url.searchParams.has('reports') ? `reports/${date}/` : `sessions/${date}/${session ? session + '/' : ''}`;
  const result = await env.DIAGNOSTICS.list({prefix, limit: 100, cursor: url.searchParams.get('cursor') || undefined});
  return json({objects: result.objects.map(o => ({key: o.key, size: o.size, uploaded: o.uploaded})), cursor: result.truncated ? result.cursor : null});
}

export async function onRequest({request, env}) {
  try { return await handle(request, env); }
  catch { return json({error: 'diagnostics unavailable'}, 503); }
}
