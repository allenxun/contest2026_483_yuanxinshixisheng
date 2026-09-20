import assert from 'node:assert/strict';
import { test } from 'node:test';
import { GimbalCloudClient, GimbalCloudError } from './gimbal-cloud-client.mjs';

const ID = '55555555-5555-4555-8555-555555555555';
const TASK = '7f3c2b1a-9d4e-4c5f-8a6b-1d2e3f4a5b6c';
const REPORT = '11111111-1111-4111-8111-111111111111';
const MEDIA = '22222222-2222-4222-8222-222222222222';
const success = (data, status = 200, id = 'req-1') => new Response(JSON.stringify({
  requestId: id, data, meta: { replayed: false, serverTime: '2026-09-14T00:00:00Z' }
}), { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': id } });

function mock(responder) {
  const calls = [];
  const client = new GimbalCloudClient({ baseUrl: 'http://10.3.3.170:18085/', fetchImpl: async (url, init) => {
    calls.push({ url, init }); return responder(url, init, calls.length);
  }});
  return { client, calls };
}

test('device session is public and remembered only in memory', async () => {
  const { client, calls } = mock(() => success({ gimbalId: ID, sessionToken: 'device-token', expiresAt: '2026-09-15T00:00:00Z', serverTime: '2026-09-14T00:00:00Z' }));
  const session = await client.createGimbalSession({ credential: 'credential', credentialVersion: '1', proof: 'proof' });
  assert.equal(session.data.gimbalId, ID); assert.equal(session.requestId, 'req-1'); assert.equal(client.token, 'device-token');
  assert.equal(calls[0].init.headers.has('authorization'), false);
  assert.deepEqual(JSON.parse(calls[0].init.body), { credential: 'credential', credentialVersion: '1', proof: 'proof' });
});

test('heartbeat and status add device bearer and preserve bigint strings', async () => {
  const { client, calls } = mock((url) => success(url.endsWith('/heartbeats') ? { accepted: true } : { connectionStatus: 'online' }));
  client.setToken('short-lived-token');
  const heartbeat = await client.heartbeat(ID, { observationEpoch: 'boot-1', observationSeq: '2', observedAt: '2026-09-14T00:00:00Z', powerState: 'awake' });
  await client.getGimbalStatus(ID); assert.equal(heartbeat.data.accepted, true);
  assert.equal(calls[0].init.headers.get('authorization'), 'Bearer short-lived-token');
  assert.equal(JSON.parse(calls[0].init.body).observationSeq, '2');
  assert.ok(calls[1].url.endsWith(`/api/v1/gimbals/${ID}/status`));
});

test('binding sends pairing proof and idempotency headers', async () => {
  const { client, calls } = mock(() => success({ bindingStatus: 'self' })); client.setToken('app-token');
  await client.getBindingStatus(ID, 'pair-proof');
  await client.bindGimbal(ID, { expectedBindingRevision: '0', pairingProof: 'pair-proof' }, { key: 'bind-1' });
  await client.unbindGimbal(ID, { key: 'unbind-1', ifMatch: '"binding-1"' });
  assert.equal(calls[0].init.headers.get('x-pairing-proof'), 'pair-proof');
  assert.equal(calls[1].init.headers.get('idempotency-key'), 'bind-1');
  assert.equal(calls[2].init.headers.get('if-match'), '"binding-1"');
});

test('assessment create and retake enforce exact image sets', async () => {
  const { client, calls } = mock(() => success({ taskId: TASK, status: 'queued', photoVersion: '1' }, 202)); client.setToken('device-token');
  const image = new Blob(['image'], { type: 'image/jpeg' });
  await client.createAssessment({ metadata: { photoVersion: '1', captureSessionId: 'capture', consentEvidenceRef: 'consent' }, front: image, left: image, right: image }, { key: 'create-1' });
  assert.deepEqual([...calls[0].init.body.keys()], ['metadata', 'front', 'left', 'right']);
  await client.retakeAssessment(TASK, '2', { metadata: { expectedPhotoVersion: '1', replacedViews: ['left'] }, images: { left: image } }, { key: 'retake-1' });
  assert.deepEqual([...calls[1].init.body.keys()], ['metadata', 'left']);
  assert.throws(() => client.retakeAssessment(TASK, '2', { metadata: { expectedPhotoVersion: '1', replacedViews: ['left'] }, images: { right: image } }, { key: 'bad' }), /image_set_mismatch/);
});

test('task, report, current assessment and media use frozen paths', async () => {
  const { client, calls } = mock((url, init, n) => n === 4
    ? new Response(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'image/jpeg', 'X-Request-Id': 'media-1' } })
    : success({ ok: true }));
  client.setToken('device-token');
  await client.getCurrentAssessment(ID); await client.getAssessment(TASK); await client.getReport(REPORT, { view: 'brief' });
  const media = await client.getMedia(MEDIA);
  assert.ok(calls[0].url.endsWith(`/gimbals/${ID}/current-assessment`));
  assert.ok(calls[1].url.endsWith(`/skin-assessment-tasks/${TASK}`));
  assert.ok(calls[2].url.endsWith(`/skin-reports/${REPORT}?view=brief`));
  assert.deepEqual([...new Uint8Array(media.body)], [1, 2, 3]); assert.equal(media.contentType, 'image/jpeg');
});

test('structured backend errors are exposed without leaking authorization', async () => {
  const { client, calls } = mock(() => new Response(JSON.stringify({ requestId: 'req-e', error: {
    code: 'REQUEST_IN_PROGRESS', message: 'pending', retryable: true, details: { phase: 'create' }
  }}), { status: 409, headers: { 'Retry-After': '2', 'X-Request-Id': 'req-e' } }));
  client.setToken('secret-token');
  await assert.rejects(client.getGimbalStatus(ID), error => error instanceof GimbalCloudError &&
    error.code === 'REQUEST_IN_PROGRESS' && error.retryable && error.retryAfter === '2' && error.requestId === 'req-e');
  assert.equal(calls[0].init.headers.get('authorization'), 'Bearer secret-token');
});

test('input and response guards reject unsafe or ambiguous values', async () => {
  const { client } = mock(() => new Response(JSON.stringify({ data: {} }), { status: 200 }));
  assert.throws(() => client.setToken('bad\ntoken'), /token_invalid/);
  await assert.rejects(client.createGimbalSession({ credential: 'x', credentialVersion: 1, proof: 'p' }), /credential_version_invalid/);
  client.setToken('token');
  await assert.rejects(client.getGimbalStatus(ID), error => error.code === 'INVALID_RESPONSE');
  assert.throws(() => client.getReport(REPORT, { view: 'admin' }), /report_view_invalid/);
});
