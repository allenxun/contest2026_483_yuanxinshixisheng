// SPDX-License-Identifier: Apache-2.0
// VelaVision business-backend client. Tokens and device credentials stay in memory.

const BIGINT_TEXT = /^(0|[1-9][0-9]*)$/;
const UUID_TEXT = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class GimbalCloudError extends Error {
  constructor(message, { status = 0, code = 'TRANSPORT_ERROR', retryable = false,
    details, requestId, retryAfter } = {}) {
    super(message);
    this.name = 'GimbalCloudError';
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.details = details;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

function requiredText(value, name, maxLength) {
  if (typeof value !== 'string' || value.length === 0 || value.length > maxLength)
    throw new TypeError(`${name}_invalid`);
  return value;
}

function bigintText(value, name) {
  if (typeof value !== 'string' || !BIGINT_TEXT.test(value)) throw new TypeError(`${name}_invalid`);
  return value;
}

function uuid(value, name) {
  if (typeof value !== 'string' || !UUID_TEXT.test(value)) throw new TypeError(`${name}_invalid`);
  return value;
}

function bearer(value) {
  if (typeof value !== 'string' || value.trim() !== value || value.length === 0 || /[\r\n]/.test(value))
    throw new TypeError('token_invalid');
  return value;
}

function idempotencyKey(value) { return requiredText(value, 'idempotency_key', 128); }

function jsonPart(value) {
  return new Blob([JSON.stringify(value)], { type: 'application/json' });
}

function imagePart(value, name) {
  if (!(value instanceof Blob) || value.size === 0) throw new TypeError(`${name}_image_invalid`);
  return value;
}

export class GimbalCloudClient {
  constructor({ baseUrl, fetchImpl = globalThis.fetch, token = null } = {}) {
    if (typeof fetchImpl !== 'function') throw new TypeError('fetch_required');
    const parsed = new URL(requiredText(baseUrl, 'base_url', 2048));
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new TypeError('base_url_invalid');
    parsed.pathname = parsed.pathname.replace(/\/$/, '');
    parsed.search = ''; parsed.hash = '';
    this.baseUrl = parsed.toString().replace(/\/$/, '');
    this.fetchImpl = fetchImpl;
    this.token = token === null ? null : bearer(token);
  }

  setToken(token) { this.token = bearer(token); }
  clearToken() { this.token = null; }

  async createGimbalSession({ credential, credentialVersion, proof }, { rememberToken = true, signal } = {}) {
    const envelope = await this._request('/api/v1/gimbal-sessions', {
      method: 'POST', auth: false, signal,
      json: {
        credential: requiredText(credential, 'credential', 256),
        credentialVersion: bigintText(credentialVersion, 'credential_version'),
        proof: requiredText(proof, 'proof', 512)
      }
    });
    const data = envelope.data;
    uuid(data?.gimbalId, 'gimbal_id');
    bearer(data?.sessionToken);
    if (rememberToken) this.token = data.sessionToken;
    return envelope;
  }

  heartbeat(gimbalId, body, options = {}) {
    requiredText(body?.observationEpoch, 'observation_epoch', 128);
    bigintText(body?.observationSeq, 'observation_seq');
    if (!['awake', 'asleep'].includes(body?.powerState)) throw new TypeError('power_state_invalid');
    return this._data(`/api/v1/gimbals/${uuid(gimbalId, 'gimbal_id')}/heartbeats`, {
      method: 'POST', json: body, signal: options.signal
    });
  }

  getGimbalStatus(gimbalId, options = {}) {
    return this._data(`/api/v1/gimbals/${uuid(gimbalId, 'gimbal_id')}/status`, { signal: options.signal });
  }

  getBindingStatus(gimbalId, pairingProof, options = {}) {
    return this._data(`/api/v1/gimbals/${uuid(gimbalId, 'gimbal_id')}/binding-status`, {
      signal: options.signal, headers: { 'X-Pairing-Proof': requiredText(pairingProof, 'pairing_proof', 8192) }
    });
  }

  bindGimbal(gimbalId, { expectedBindingRevision, pairingProof }, { key, signal } = {}) {
    return this._data(`/api/v1/me/gimbal-bindings/${uuid(gimbalId, 'gimbal_id')}`, {
      method: 'PUT', signal, idempotencyKey: key,
      json: {
        expectedBindingRevision: bigintText(expectedBindingRevision, 'binding_revision'),
        pairingProof: requiredText(pairingProof, 'pairing_proof', 8192)
      }
    });
  }

  async unbindGimbal(gimbalId, { key, ifMatch, signal } = {}) {
    const headers = {};
    if (ifMatch !== undefined) headers['If-Match'] = requiredText(ifMatch, 'if_match', 256);
    await this._request(`/api/v1/me/gimbal-bindings/${uuid(gimbalId, 'gimbal_id')}`, {
      method: 'DELETE', signal, idempotencyKey: key, headers, expectNoContent: true
    });
  }

  getCurrentAssessment(gimbalId, options = {}) {
    return this._data(`/api/v1/gimbals/${uuid(gimbalId, 'gimbal_id')}/current-assessment`, { signal: options.signal });
  }

  createAssessment({ metadata, front, left, right }, { key, signal } = {}) {
    if (!metadata || typeof metadata !== 'object') throw new TypeError('metadata_invalid');
    if (bigintText(metadata.photoVersion, 'photo_version') !== '1') throw new TypeError('photo_version_invalid');
    requiredText(metadata.captureSessionId, 'capture_session_id', 128);
    requiredText(metadata.consentEvidenceRef, 'consent_evidence_ref', 128);
    const form = new FormData();
    form.append('metadata', jsonPart(metadata));
    form.append('front', imagePart(front, 'front'), 'front');
    form.append('left', imagePart(left, 'left'), 'left');
    form.append('right', imagePart(right, 'right'), 'right');
    return this._data('/api/v1/skin-assessment-tasks', {
      method: 'POST', body: form, idempotencyKey: key, signal
    });
  }

  retakeAssessment(taskId, photoVersion, { metadata, images }, { key, signal } = {}) {
    uuid(taskId, 'task_id'); bigintText(photoVersion, 'photo_version');
    if (!metadata || typeof metadata !== 'object' || !Array.isArray(metadata.replacedViews) || metadata.replacedViews.length === 0)
      throw new TypeError('metadata_invalid');
    bigintText(metadata.expectedPhotoVersion, 'expected_photo_version');
    if (BigInt(photoVersion) !== BigInt(metadata.expectedPhotoVersion) + 1n) throw new TypeError('photo_version_invalid');
    const views = metadata.replacedViews;
    if (new Set(views).size !== views.length || views.some(view => !['front', 'left', 'right'].includes(view)))
      throw new TypeError('replaced_views_invalid');
    if (!images || Object.keys(images).length !== views.length || Object.keys(images).some(view => !views.includes(view)))
      throw new TypeError('image_set_mismatch');
    const form = new FormData(); form.append('metadata', jsonPart(metadata));
    for (const view of views) form.append(view, imagePart(images[view], view), view);
    return this._data(`/api/v1/skin-assessment-tasks/${taskId}/photo-versions/${photoVersion}`, {
      method: 'PUT', body: form, idempotencyKey: key, signal
    });
  }

  getAssessment(taskId, options = {}) {
    return this._data(`/api/v1/skin-assessment-tasks/${uuid(taskId, 'task_id')}`, { signal: options.signal });
  }

  getReport(reportId, { view = 'full', signal } = {}) {
    if (!['full', 'brief'].includes(view)) throw new TypeError('report_view_invalid');
    return this._data(`/api/v1/skin-reports/${uuid(reportId, 'report_id')}?view=${view}`, { signal });
  }

  async getMedia(mediaId, options = {}) {
    const response = await this._raw(`/api/v1/media/${uuid(mediaId, 'media_id')}/content`, { signal: options.signal });
    if (!response.ok) throw await this._error(response);
    return {
      body: await response.arrayBuffer(),
      contentType: response.headers.get('content-type') || 'application/octet-stream',
      requestId: response.headers.get('x-request-id')
    };
  }

  async _data(path, options) { return this._request(path, options); }

  async _raw(path, { method = 'GET', auth = true, json, body, headers = {}, idempotencyKey: key, signal } = {}) {
    const requestHeaders = new Headers(headers);
    if (auth) {
      if (!this.token) throw new GimbalCloudError('session token required', { code: 'AUTH_REQUIRED' });
      requestHeaders.set('Authorization', `Bearer ${this.token}`);
    }
    if (key !== undefined) requestHeaders.set('Idempotency-Key', idempotencyKey(key));
    if (json !== undefined) { requestHeaders.set('Content-Type', 'application/json'); body = JSON.stringify(json); }
    try { return await this.fetchImpl(this.baseUrl + path, { method, headers: requestHeaders, body, signal }); }
    catch (error) {
      if (error instanceof GimbalCloudError) throw error;
      throw new GimbalCloudError(error?.message || 'network request failed', { code: error?.name === 'AbortError' ? 'ABORTED' : 'TRANSPORT_ERROR' });
    }
  }

  async _request(path, options = {}) {
    const response = await this._raw(path, options);
    if (!response.ok) throw await this._error(response);
    if (options.expectNoContent || response.status === 204) return null;
    let envelope;
    try { envelope = await response.json(); } catch { throw new GimbalCloudError('invalid JSON response', { status: response.status, code: 'INVALID_RESPONSE' }); }
    if (!envelope || typeof envelope.requestId !== 'string' || !Object.hasOwn(envelope, 'data') ||
        !envelope.meta || typeof envelope.meta.replayed !== 'boolean' || typeof envelope.meta.serverTime !== 'string')
      throw new GimbalCloudError('invalid success envelope', { status: response.status, code: 'INVALID_RESPONSE' });
    const headerId = response.headers.get('x-request-id');
    if (headerId && headerId !== envelope.requestId)
      throw new GimbalCloudError('request ID mismatch', { status: response.status, code: 'INVALID_RESPONSE', requestId: headerId });
    return envelope;
  }

  async _error(response) {
    let envelope = null;
    try { envelope = await response.json(); } catch {}
    const body = envelope?.error;
    return new GimbalCloudError(typeof body?.message === 'string' ? body.message : `HTTP ${response.status}`, {
      status: response.status,
      code: typeof body?.code === 'string' ? body.code : 'HTTP_ERROR',
      retryable: body?.retryable === true,
      details: body?.details,
      requestId: envelope?.requestId || response.headers.get('x-request-id'),
      retryAfter: response.headers.get('retry-after')
    });
  }
}
