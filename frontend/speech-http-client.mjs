// SPDX-License-Identifier: Apache-2.0
// HTTP client for the team's speech bridge. MiMo credentials stay on that
// bridge; this client deliberately has no API-key or Authorization option.

export class SpeechHttpError extends Error {
  constructor(code, { status = null, retryable = false, cause = null } = {}) {
    super(code, cause ? { cause } : undefined);
    this.name = 'SpeechHttpError';
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

const ascii = (bytes, offset, length) =>
  String.fromCharCode(...bytes.subarray(offset, offset + length));

export function inspectPcm16MonoWav(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  if (bytes.byteLength < 44 || ascii(bytes, 0, 4) !== 'RIFF' || ascii(bytes, 8, 4) !== 'WAVE')
    throw new SpeechHttpError('invalid_wav');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 12; let format = null; let dataBytes = null;
  while (offset + 8 <= bytes.byteLength) {
    const name = ascii(bytes, offset, 4);
    const size = view.getUint32(offset + 4, true);
    const body = offset + 8;
    if (body + size > bytes.byteLength) throw new SpeechHttpError('invalid_wav');
    if (name === 'fmt ') {
      if (size < 16) throw new SpeechHttpError('invalid_wav');
      format = {
        encoding: view.getUint16(body, true),
        channels: view.getUint16(body + 2, true),
        sampleRate: view.getUint32(body + 4, true),
        bitsPerSample: view.getUint16(body + 14, true)
      };
    } else if (name === 'data') dataBytes = size;
    offset = body + size + (size & 1);
  }
  if (!format || dataBytes === null || format.encoding !== 1 || format.channels !== 1 ||
      format.sampleRate !== 16000 || format.bitsPerSample !== 16)
    throw new SpeechHttpError('unsupported_audio_format');
  return Object.freeze({ ...format, dataBytes });
}

async function audioBytes(audio) {
  if (audio instanceof Uint8Array) return audio;
  if (audio instanceof ArrayBuffer) return new Uint8Array(audio);
  if (ArrayBuffer.isView(audio)) return new Uint8Array(audio.buffer, audio.byteOffset, audio.byteLength);
  if (typeof Blob !== 'undefined' && audio instanceof Blob) return new Uint8Array(await audio.arrayBuffer());
  throw new SpeechHttpError('invalid_audio');
}

export class SpeechHttpClient {
  constructor(baseUrl, { fetchImpl = globalThis.fetch, timeoutMs = 15000 } = {}) {
    if (typeof fetchImpl !== 'function') throw new TypeError('fetch_required');
    const parsed = new URL(baseUrl);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash)
      throw new TypeError('invalid_base_url');
    parsed.pathname = parsed.pathname.replace(/\/+$/, '') + '/';
    this.baseUrl = parsed;
    this.fetch = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  _url(path) { return new URL(path.replace(/^\/+/, ''), this.baseUrl).toString(); }

  async _request(path, init, { timeoutMs = this.timeoutMs, signal = null } = {}) {
    const controller = new AbortController(); let timedOut = false;
    const abort = () => controller.abort(signal?.reason);
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    let response;
    try {
      response = await this.fetch(this._url(path), { ...init, signal: controller.signal });
    } catch (error) {
      if (timedOut) throw new SpeechHttpError('request_timeout', { retryable: true, cause: error });
      if (signal?.aborted) throw new SpeechHttpError('request_aborted', { cause: error });
      throw new SpeechHttpError('network_error', { retryable: true, cause: error });
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
    if (!response?.ok) {
      const status = Number.isInteger(response?.status) ? response.status : null;
      throw new SpeechHttpError('http_error', {
        status,
        retryable: status === null || status === 408 || status === 429 || status >= 500
      });
    }
    return response;
  }

  async health(options = {}) {
    const response = await this._request('/health', {
      method: 'GET', headers: { Accept: 'application/json' }
    }, options);
    let result;
    try { result = await response.json(); }
    catch (error) { throw new SpeechHttpError('invalid_response', { cause: error }); }
    if (typeof result?.ready !== 'boolean' || typeof result?.asr !== 'boolean' || typeof result?.tts !== 'boolean')
      throw new SpeechHttpError('invalid_response');
    return Object.freeze({ ready: result.ready, asr: result.asr, tts: result.tts });
  }

  async asr(audio, { signal = null, timeoutMs = 30000 } = {}) {
    const bytes = await audioBytes(audio);
    inspectPcm16MonoWav(bytes);
    const response = await this._request('/v1/asr', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'audio/wav' },
      body: bytes
    }, { signal, timeoutMs });
    let result;
    try { result = await response.json(); }
    catch (error) { throw new SpeechHttpError('invalid_response', { cause: error }); }
    if (typeof result?.text !== 'string') throw new SpeechHttpError('invalid_response');
    return Object.freeze({ ...result, text: result.text });
  }

  async tts(text, { voice = null, signal = null, timeoutMs = 30000 } = {}) {
    if (typeof text !== 'string' || !text.trim() || text.length > 2000)
      throw new SpeechHttpError('invalid_text');
    if (voice !== null && (typeof voice !== 'string' || !voice || voice.length > 64))
      throw new SpeechHttpError('invalid_voice');
    const request = { text, format: 'wav', sample_rate: 16000, channels: 1 };
    if (voice !== null) request.voice = voice;
    const response = await this._request('/v1/tts', {
      method: 'POST',
      headers: { Accept: 'audio/wav', 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    }, { signal, timeoutMs });
    let bytes;
    try { bytes = new Uint8Array(await response.arrayBuffer()); }
    catch (error) { throw new SpeechHttpError('invalid_response', { cause: error }); }
    inspectPcm16MonoWav(bytes);
    return bytes;
  }
}

