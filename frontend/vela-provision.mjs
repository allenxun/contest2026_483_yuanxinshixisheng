// SPDX-License-Identifier: Apache-2.0
// VelaVision BLE protocol v1. No Wi-Fi credentials are logged or persisted.
export const UUID = Object.freeze({
  service: '6b7a0001-78c3-4f2e-9c2f-3ecbc2d74680',
  write: '6b7a0002-78c3-4f2e-9c2f-3ecbc2d74680',
  notify: '6b7a0003-78c3-4f2e-9c2f-3ecbc2d74680',
  status: '6b7a0004-78c3-4f2e-9c2f-3ecbc2d74680'
});
export function encodeUtf8(text) {
  const encoded = encodeURIComponent(text), bytes = [];
  for (let i = 0; i < encoded.length; i++) {
    if (encoded[i] === '%') { bytes.push(parseInt(encoded.slice(i + 1, i + 3), 16)); i += 2; }
    else bytes.push(encoded.charCodeAt(i));
  }
  return Uint8Array.from(bytes);
}
export function decodeUtf8(bytes) {
  return decodeURIComponent(Array.from(bytes, b => '%' + b.toString(16).padStart(2, '0')).join(''));
}
export class LineDecoder {
  constructor(onMessage) { this.bytes = []; this.onMessage = onMessage; }
  reset() { this.bytes.fill(0); this.bytes = []; }
  feed(value) {
    for (const byte of new Uint8Array(value)) {
      if (this.bytes.length >= 4096) { this.reset(); throw new Error('notification_overflow'); }
      if (byte === 10) {
        const line = this.bytes; this.bytes = [];
        const message = JSON.parse(decodeUtf8(line)); line.fill(0);
        if (message.v !== 1) throw new Error('unsupported_protocol');
        this.onMessage(message);
      } else this.bytes.push(byte);
    }
  }
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
export class VelaProvision {
  constructor(uniApi, { onConnection = () => {}, onAccessPoint = () => {}, onWifiState = () => {} } = {}) {
    this.uni = uniApi; this.onConnection = onConnection; this.onAccessPoint = onAccessPoint;
    this.onWifiState = onWifiState;
    this.deviceId = null; this.connected = false; this.pending = null; this.pendingRead = null; this.nextId = 100; this.capabilities = null;
    this.decoder = new LineDecoder(message => this._message(message));
    this.valueHandler = event => {
      if (event.deviceId !== this.deviceId) return;
      if (event.characteristicId.toLowerCase() === UUID.status) {
        const request = this.pendingRead;
        if (!request) return;
        this.pendingRead = null; clearTimeout(request.timer);
        try {
          const state = JSON.parse(decodeUtf8(new Uint8Array(event.value)));
          if (state.v !== 1 || typeof state.encrypted !== 'boolean') throw new Error('invalid_capabilities');
          this.capabilities = state; request.resolve(state);
        } catch (error) { request.reject(error); }
        return;
      }
      if (event.characteristicId.toLowerCase() !== UUID.notify) return;
      try { this.decoder.feed(event.value); } catch (error) { this._reject(error); }
    };
    this.connectionHandler = event => {
      if (event.deviceId !== this.deviceId) return;
      if (!event.connected) { this.connected = false; this.decoder.reset(); this.capabilities = null; this._reject(new Error('disconnected')); this._rejectRead(new Error('disconnected')); }
      // A raw OS "connected" event is earlier than encrypted GATT readiness.
      // Only connect() reports true after service discovery and capabilities.
      if (!event.connected) this.onConnection(false);
    };
    this.uni.onBLECharacteristicValueChange(this.valueHandler);
    this.uni.onBLEConnectionStateChange(this.connectionHandler);
  }
  _call(method, options = {}) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(method + '_timeout')), 16000);
      try {
        this.uni[method]({ ...options,
          success: value => { clearTimeout(timer); resolve(value); },
          fail: error => { clearTimeout(timer); reject(error); }
        });
      } catch (error) { clearTimeout(timer); reject(error); }
    });
  }
  _rejectRead(error) {
    if (!this.pendingRead) return;
    const request = this.pendingRead; this.pendingRead = null; clearTimeout(request.timer); request.reject(error);
  }
  readCapabilities() {
    if (!this.connected) return Promise.reject(new Error('not_connected'));
    if (this.pendingRead || this.pending) return Promise.reject(new Error('busy'));
    return new Promise((resolve, reject) => {
      const request = { resolve, reject, timer: setTimeout(() => this._rejectRead(new Error('capability_timeout')), 5000) };
      this.pendingRead = request;
      this._call('readBLECharacteristicValue', { deviceId: this.deviceId, serviceId: UUID.service, characteristicId: UUID.status })
        .catch(error => { if (this.pendingRead === request) this._rejectRead(error); });
    });
  }
  _reject(error) {
    if (!this.pending) return;
    const pending = this.pending; this.pending = null; clearTimeout(pending.timer); pending.reject(error);
  }
  _message(message) {
    const pending = this.pending;
    if (!pending) return;
    if (pending.id === null && message.event === 'scan_started') pending.id = message.id;
    if (message.id !== pending.id) return;
    if (pending.session !== null && message.session !== pending.session) return;
    if (message.event === 'ap') { pending.rows.push(message); this.onAccessPoint(message); return; }
    if (message.event === 'scan_started') return;
    if (message.event === 'wifi_connecting') { this.onWifiState(message); return; }
    if (message.event === 'error') { this._reject(Object.assign(new Error(message.code), { code: message.code, detail: message.detail, id: message.id, session: message.session })); return; }
    if (pending.scan && message.event !== 'scan_done') return;
    if (!pending.scan && message.event !== pending.expected) return;
    if (pending.expected === 'wifi_connected' &&
        (message.wifi_connected !== true || typeof message.ip !== 'string' ||
         !/^(?:\d{1,3}\.){3}\d{1,3}$/.test(message.ip) ||
         message.ip.split('.').some(x => Number(x) > 255) ||
         message.ip === '0.0.0.0' || message.ip === '255.255.255.255')) {
      this._reject(new Error('invalid_network_result')); return;
    }
    if (pending.expected === 'credentials_received' &&
        (message.validated !== true || message.stored !== false || message.wifi_connected !== false || message.ip !== null)) {
      this._reject(new Error('invalid_receipt')); return;
    }
    if (pending.scan && message.count !== pending.rows.length) { this._reject(new Error('scan_count_mismatch')); return; }
    this.pending = null; clearTimeout(pending.timer);
    pending.resolve(pending.scan ? { ...message, networks: pending.rows } : message);
  }
  async connect(deviceId) {
    if (this.pending) throw new Error('busy');
    if (this.deviceId) await this.disconnect();
    this.deviceId = deviceId; this.decoder.reset();
    await this._call('openBluetoothAdapter');
    try {
      await this._call('createBLEConnection', { deviceId, timeout: 15000 });
      const result = await this._call('getBLEDeviceServices', { deviceId });
      if (!result.services.some(s => s.uuid.toLowerCase() === UUID.service)) throw new Error('service_not_found');
      const { characteristics } = await this._call('getBLEDeviceCharacteristics', { deviceId, serviceId: UUID.service });
      if (!characteristics.some(c => c.uuid.toLowerCase() === UUID.write && c.properties.write) ||
          !characteristics.some(c => c.uuid.toLowerCase() === UUID.notify && c.properties.notify)) throw new Error('characteristic_not_found');
      await this._call('notifyBLECharacteristicValueChange', { deviceId, serviceId: UUID.service, characteristicId: UUID.notify, state: true });
      this.connected = true;
      // Wait for the board's actual encryption state, including any OS pairing
      // prompt. Link creation alone is not provisioning readiness.
      const deadline = Date.now() + 30000;
      while (!(await this.readCapabilities()).encrypted) {
        if (Date.now() >= deadline) throw new Error('encryption_timeout');
        await sleep(500);
      }
      this.onConnection(true);
      return this.capabilities;
    } catch (error) { await this.disconnect(); throw error; }
  }
  async _write(bytes, request) {
    try {
      for (let pos = 0; pos < bytes.length; pos += 20) {
        if (!this.connected || this.pending !== request) throw new Error('request_cancelled');
        await this._call('writeBLECharacteristicValue', {
          deviceId: this.deviceId, serviceId: UUID.service, characteristicId: UUID.write,
          value: bytes.slice(pos, pos + 20).buffer, writeType: 'write'
        });
      }
    } finally { bytes.fill(0); }
  }
  _request(payload, { id, scan = false, timeout = 60000, expected = 'status', session = null }) {
    if (!this.deviceId || !this.connected) return Promise.reject(new Error('not_connected'));
    if (this.pending || this.pendingRead) return Promise.reject(new Error('busy'));
    const bytes = encodeUtf8(payload);
    if (bytes.length > 512) { bytes.fill(0); return Promise.reject(new Error('command_too_large')); }
    return new Promise((resolve, reject) => {
      this.pending = { id, scan, expected, session, rows: [], resolve, reject, timer: setTimeout(() => this._reject(new Error('timeout')), timeout) };
      const request = this.pending;
      this._write(bytes, request).catch(error => { if (this.pending === request) this._reject(error); });
    });
  }
  async scan() {
    // The current native scan opens/closes the WLAN interface. Query first so
    // a refresh cannot imply scanning an already connected interface.
    const state = await this.status();
    if (state.wifi_connected === true)
      throw Object.assign(new Error('online_scan_unavailable'), { code: 'online_scan_unavailable', ip: state.ip });
    return this._request('X', { id: null, scan: true });
  }
  status() {
    const id = this.nextId = this.nextId % 65535 + 1;
    return this._request(JSON.stringify({ v: 1, id, cmd: 'status' }) + '\n',
      { id, timeout: 15000, session: Number.isInteger(this.capabilities?.session) ? this.capabilities.session : null });
  }
  connectWifi(details = {}) { return this._credentialsRequest(details, true); }
  submitCredentials(details = {}) { return this._credentialsRequest(details, false); }
  _credentialsRequest({ ssid_b64, password }, connect) {
    if (!this.connected || this.capabilities?.[connect ? 'connect' : 'receive_credentials'] !== true || !Number.isInteger(this.capabilities.session))
      return Promise.reject(Object.assign(new Error('not_ready'), { code: 'not_ready' }));
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    const valid64 = typeof ssid_b64 === 'string' && /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(ssid_b64);
    const pad = valid64 ? (ssid_b64.endsWith('==') ? 2 : (ssid_b64.endsWith('=') ? 1 : 0)) : 0;
    const length = valid64 ? ssid_b64.length / 4 * 3 - pad : 0;
    if (!valid64 || length < 1 || length > 32 || (pad && (alphabet.indexOf(ssid_b64[ssid_b64.length-pad-1]) & (pad === 2 ? 15 : 3))))
      return Promise.reject(Object.assign(new Error('invalid_ssid'), { code: 'invalid_ssid' }));
    if (typeof password !== 'string' || !/^[\x20-\x7e]{8,63}$/.test(password))
      return Promise.reject(Object.assign(new Error('invalid_password'), { code: 'invalid_password' }));
    const id = this.nextId = this.nextId % 65535 + 1;
    return this._request(JSON.stringify({ v: 1, id, cmd: connect ? 'connect' : 'submit_credentials', ssid_b64, password }) + '\n',
      { id, expected: connect ? 'wifi_connected' : 'credentials_received', session: this.capabilities.session, timeout: connect ? 120000 : 15000 });
  }
  async disconnect() {
    this.connected = false; this._reject(new Error('disconnected')); this._rejectRead(new Error('disconnected')); this.decoder.reset(); this.capabilities = null;
    const deviceId = this.deviceId; this.deviceId = null;
    if (deviceId) await this._call('closeBLEConnection', { deviceId }).catch(() => {});
    this.onConnection(false);
  }
  async reconnect(deviceId, attempts = 3) {
    await this.disconnect(); let failure;
    for (let i = 0; i < attempts; i++) {
      try { await this.connect(deviceId); return; } catch (error) { failure = error; }
      if (i + 1 < attempts) await sleep(Math.min(1000 * 2 ** i, 4000));
    }
    throw failure;
  }
  async dispose() {
    await this.disconnect();
    this.uni.offBLECharacteristicValueChange?.(this.valueHandler);
    this.uni.offBLEConnectionStateChange?.(this.connectionHandler);
  }
}
