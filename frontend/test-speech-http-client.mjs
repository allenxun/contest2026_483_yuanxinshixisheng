import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SpeechHttpClient, SpeechHttpError, inspectPcm16MonoWav } from './speech-http-client.mjs';
import { createWholeDeviceClient } from './整机BLE与云端语音拼接示例.mjs';

function wav16k(samples = 160) {
  const bytes = new Uint8Array(44 + samples * 2); const v = new DataView(bytes.buffer);
  for (const [offset, text] of [[0, 'RIFF'], [8, 'WAVE'], [12, 'fmt '], [36, 'data']])
    for (let i = 0; i < text.length; i++) bytes[offset + i] = text.charCodeAt(i);
  v.setUint32(4, bytes.length - 8, true); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 16000, true);
  v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  v.setUint32(40, samples * 2, true); return bytes;
}
const jsonResponse = body => ({ ok: true, status: 200, json: async () => body });
const wavResponse = bytes => ({ ok: true, status: 200, arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) });

test('health, ASR and TTS use the bridge contract without an authorization header', async () => {
  const calls = []; const output = wav16k();
  const fetchImpl = async (url, init) => {
    calls.push({ url, ...init });
    if (url.endsWith('/health')) return jsonResponse({ ready: true, asr: true, tts: true });
    if (url.endsWith('/v1/asr')) return jsonResponse({ text: '你好联网' });
    if (url.endsWith('/v1/tts')) return wavResponse(output);
    throw new Error('unexpected');
  };
  const client = new SpeechHttpClient('http://127.0.0.1:18086', { fetchImpl });
  assert.deepEqual(await client.health(), { ready: true, asr: true, tts: true });
  assert.deepEqual(await client.asr(wav16k()), { text: '你好联网' });
  assert.deepEqual(await client.tts('联网成功', { voice: '白桦' }), output);
  assert.deepEqual(calls.map(x => [x.url, x.method]), [
    ['http://127.0.0.1:18086/health', 'GET'],
    ['http://127.0.0.1:18086/v1/asr', 'POST'],
    ['http://127.0.0.1:18086/v1/tts', 'POST']
  ]);
  for (const call of calls) {
    const headers = Object.fromEntries(Object.entries(call.headers).map(([k, v]) => [k.toLowerCase(), v]));
    assert.equal(headers.authorization, undefined);
  }
  assert.equal(calls[1].headers['Content-Type'], 'audio/wav');
  assert.deepEqual(JSON.parse(calls[2].body), {
    text: '联网成功', format: 'wav', sample_rate: 16000, channels: 1, voice: '白桦'
  });
});

test('audio format, response schema and HTTP errors are stable', async () => {
  assert.deepEqual(inspectPcm16MonoWav(wav16k()), {
    encoding: 1, channels: 1, sampleRate: 16000, bitsPerSample: 16, dataBytes: 320
  });
  const wav24k = wav16k(); new DataView(wav24k.buffer).setUint32(24, 24000, true);
  assert.throws(() => inspectPcm16MonoWav(wav24k), e => e.code === 'unsupported_audio_format');
  const badHealth = new SpeechHttpClient('http://localhost:1', { fetchImpl: async () => jsonResponse({ ready: true }) });
  await assert.rejects(badHealth.health(), e => e.code === 'invalid_response');
  const unavailable = new SpeechHttpClient('http://localhost:1', { fetchImpl: async () => ({ ok: false, status: 503 }) });
  await assert.rejects(unavailable.health(), e => e.code === 'http_error' && e.status === 503 && e.retryable === true);
});

test('request timeout aborts the fetch and does not expose response content', async () => {
  const client = new SpeechHttpClient('http://localhost:1', {
    timeoutMs: 5,
    fetchImpl: (_url, { signal }) => new Promise((_resolve, reject) =>
      signal.addEventListener('abort', () => reject(new DOMException('secret backend body', 'AbortError')), { once: true }))
  });
  await assert.rejects(client.health(), error => {
    assert.ok(error instanceof SpeechHttpError);
    assert.equal(error.code, 'request_timeout');
    assert.equal(error.message, 'request_timeout');
    assert.equal(error.retryable, true);
    return true;
  });
});

test('whole-device example requires K7 internet evidence before bridge health', async () => {
  let healthCalls = 0;
  const fetchImpl = async url => {
    if (url.endsWith('/health')) { healthCalls++; return jsonResponse({ ready: true, asr: true, tts: true }); }
    throw new Error('unexpected');
  };
  const client = createWholeDeviceClient({}, {
    speechBaseUrl: 'http://10.3.3.170:18086', render: () => {},
    reportDeviceOnline: async () => {}, probeDeviceInternet: async () => true, fetchImpl,
    provision: { dispose: async () => {} }
  });
  client.state = { ...client.state, wifi_connected: true, ip: '10.3.0.214' };
  const state = await client.refreshConnectivity();
  assert.equal(state.internet_ready, true);
  assert.equal(state.online_reported, true);
  assert.equal(state.cloud_ready, true);
  assert.equal(healthCalls, 1);
});


test('App bridge availability alone never proves K7 internet connectivity', async () => {
  let calls = 0;
  const client = createWholeDeviceClient({}, {
    speechBaseUrl: 'http://10.3.3.170:18086', render: () => {},
    fetchImpl: async () => { calls++; return jsonResponse({ ready: true, asr: true, tts: true }); },
    provision: { dispose: async () => {} }
  });
  client.state = { ...client.state, wifi_connected: true, ip: '10.3.0.214' };
  const state = await client.refreshConnectivity();
  assert.equal(state.internet_ready, false);
  assert.equal(state.cloud_ready, false);
  assert.equal(calls, 0);
});
