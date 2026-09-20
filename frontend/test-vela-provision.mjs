import assert from 'node:assert/strict';
import { test } from 'node:test';
import { VelaProvision, UUID, LineDecoder, encodeUtf8, decodeUtf8 } from './vela-provision.mjs';
import { openVelaWifiList, submitWifiDetails } from './接入示例.mjs';

class MockUni {
  constructor() { this.writes = []; this.buffer = ''; this.commandId = 1; this.holdWrite = null; this.interruptWrite = false; }
  onBLECharacteristicValueChange(fn) { this.value = fn; }
  offBLECharacteristicValueChange(fn) { assert.equal(fn, this.value); this.value = null; }
  onBLEConnectionStateChange(fn) { this.connection = fn; }
  offBLEConnectionStateChange(fn) { assert.equal(fn, this.connection); this.connection = null; }
  openBluetoothAdapter(o) { o.success({}); }
  createBLEConnection(o) { this.deviceId = o.deviceId; this.connection({ deviceId: o.deviceId, connected: true }); o.success({}); }
  closeBLEConnection(o) { this.buffer = ''; o.success({}); }
  getBLEDeviceServices(o) { o.success({ services: [{ uuid: UUID.service.toUpperCase() }] }); }
  getBLEDeviceCharacteristics(o) { o.success({ characteristics: [
    { uuid: UUID.write, properties: { write: true } }, { uuid: UUID.notify, properties: { notify: true } }
  ] }); }
  notifyBLECharacteristicValueChange(o) { assert.equal(o.state, true); o.success({}); }
  readBLECharacteristicValue(o) {
    o.success({});
    this.value({ deviceId: this.deviceId, characteristicId: UUID.status, value: encodeUtf8(JSON.stringify({ v: 1, encrypted: true, scan: true, session: 1, receive_credentials: this.acceptCredentials === true, connect: this.advertisedConnect === true })).buffer });
  }
  emit(messages, width = 7) {
    const bytes = encodeUtf8(messages.map(m => JSON.stringify(m) + '\n').join(''));
    for (let i = 0; i < bytes.length; i += width) this.value({ deviceId: this.deviceId, characteristicId: UUID.notify.toUpperCase(), value: bytes.slice(i, i + width).buffer });
  }
  writeBLECharacteristicValue(o) {
    assert.equal(o.writeType, 'write'); assert.ok(o.value.byteLength <= 20);
    this.writes.push(new Uint8Array(o.value).slice());
    if (this.interruptWrite) { this.interruptWrite = false; this.holdWrite = o; this.connection({ deviceId: this.deviceId, connected: false }); return; }
    const part = decodeUtf8(new Uint8Array(o.value)); this.buffer += part;
    if (this.buffer === 'X') {
      this.buffer = ''; const id = this.commandId++;
      this.emit([{ v: 1, id, event: 'scan_started' }, { v: 1, id, event: 'ap', ssid_b64: 'TGFuc2Vl', rssi: -45, security: 'rsn', band: '2.4G', channel: 1 }, { v: 1, id, event: 'scan_done', count: this.wrongCount ? 2 : 1, truncated: false }]);
    } else if (this.buffer.endsWith('\n')) {
      const request = JSON.parse(this.buffer); this.buffer = '';
      if (request.cmd === 'connect') {
        this.lastSubmission = request;
        this.emit([{ v: 1, id: request.id, session: 99, event: 'wifi_connected', wifi_connected: true, ip: '10.0.0.99' },
          { v: 1, id: request.id, session: 1, event: 'wifi_connecting' }]);
        if (this.networkFailure) this.emit([{ v: 1, id: request.id, session: 1, event: 'error', code: 'connection_timeout', detail: -110 }]);
        else this.emit([{ v: 1, id: request.id, session: 1, event: 'wifi_connected', wifi_connected: true, ip: this.invalidIP ? '0.0.0.0' : '10.3.0.214', stored: false }]);
      } else if (request.cmd === 'submit_credentials') {
        this.lastSubmission = request;
        this.emit([{ v: 1, id: request.id, session: 99, event: 'credentials_received', validated: true, stored: false, wifi_connected: false, ip: null }]);
        this.emit([{ v: 1, id: request.id, session: 1, event: 'credentials_received', validated: true, stored: false, wifi_connected: this.falseSuccess === true, ip: null }]);
      } else
      this.emit([{ v: 1, id: request.id, event: 'status', wifi_connected: this.networkConnected === true, ip: this.networkConnected ? '10.3.0.214' : null, session: 1 }]);
    }
    o.success({});
  }
}

test('UTF-8 JSONL handles every fragment width and combined messages', () => {
  const expected = [{ v: 1, text: '中文😀\\"\nSSID' }, { v: 1, text: 'next' }];
  const bytes = encodeUtf8(expected.map(m => JSON.stringify(m) + '\n').join(''));
  for (let width = 1; width <= 20; width++) {
    const actual = []; const decoder = new LineDecoder(m => actual.push(m));
    for (let i = 0; i < bytes.length; i += width) decoder.feed(bytes.slice(i, i + width));
    assert.deepEqual(actual, expected);
  }
});
test('decoder reset removes disconnected partial frame and bounds malformed input', () => {
  const actual = []; const decoder = new LineDecoder(m => actual.push(m));
  decoder.feed(encodeUtf8('{"v":')); decoder.reset(); decoder.feed(encodeUtf8('{"v":1}\n')); assert.deepEqual(actual, [{ v: 1 }]);
  assert.throws(() => decoder.feed(new Uint8Array(4097).fill(65)), /overflow/);
  assert.throws(() => decoder.feed(encodeUtf8('{"v":2}\n')), /unsupported_protocol/);
});
test('uni adapter discovers, subscribes, reads encryption, scans, and bounds writes', async () => {
  const api = new MockUni(); const readiness = []; const app = new VelaProvision(api, { onConnection: value => readiness.push(value) });
  const capabilities = await app.connect('ios-device-uuid'); assert.equal(capabilities.encrypted, true);
  assert.deepEqual(readiness, [true], 'Raw OS connection must not report readiness before GATT/encryption');
  const scan = await app.scan(); assert.equal(scan.count, 1); assert.equal(scan.networks[0].ssid_b64, 'TGFuc2Vl');
  assert.equal((await app.status()).wifi_connected, false);
  app.nextId = 65535; await app.status(); assert.equal(app.nextId, 1);
  const before = api.writes.length; await assert.rejects(app.connectWifi(), /not_ready/); assert.equal(api.writes.length, before);
  await app.dispose(); assert.equal(api.value, null); assert.equal(api.connection, null);
});
test('disconnection cancels partial command; late old error cannot reject new request', async () => {
  const api = new MockUni(); const app = new VelaProvision(api); await app.connect('k7');
  api.interruptWrite = true; await assert.rejects(app.status(), /disconnected/);
  assert.equal(api.writes.length, 1); await assert.rejects(app.scan(), /not_connected/);
  await app.reconnect('k7'); const next = app.status(); api.holdWrite.fail(new Error('late_old_error'));
  assert.equal((await next).event, 'status'); await app.dispose();
});
test('incomplete scan response is not presented as success', async () => {
  const api = new MockUni(); api.wrongCount = true; const app = new VelaProvision(api); await app.connect('k7');
  await assert.rejects(app.scan(), /scan_count_mismatch/); await app.dispose();
});

for (const advertisedConnect of [false, true]) test(`scan page keeps passwords disabled with advertised connect=${advertisedConnect}`, async () => {
  const api = new MockUni(); const state = {};
  api.advertisedConnect = advertisedConnect;
  api.base64ToArrayBuffer = text => Uint8Array.from(Buffer.from(text, 'base64')).buffer;
  const app = await openVelaWifiList(api, 'k7', update => Object.assign(state, update));
  assert.equal(state.accessPoint.label, 'Lansee');
  assert.equal(state.scanComplete, true); assert.equal(state.canScan, true);
  assert.equal(state.passwordEnabled, false); assert.equal(state.canConnectWifi, false);
  const count = api.writes.length;
  if (!advertisedConnect) {
    await assert.rejects(app.connectWifi({ ssid_b64: 'TGFuc2Vl', password: 'TEST_ONLY_123' }), /not_ready/);
    assert.equal(api.writes.length, count, 'Disabled submission must not transmit credentials');
  }
  api.connection({ deviceId: 'k7', connected: false });
  assert.equal(state.bluetoothReady, false); assert.equal(state.canScan, false);
  assert.equal(state.passwordEnabled, false); assert.equal(state.scanComplete, false);
  await app.dispose();
});

test('connect capability submits fragmented credentials, ignores stale session and resolves only real IP', async () => {
  const api = new MockUni(); api.advertisedConnect = true;
  const progress = []; const app = new VelaProvision(api, { onWifiState: m => progress.push(m.event) });
  await app.connect('k7');
  const result = await app.connectWifi({ ssid_b64: 'TGFuc2Vl', password: 'TEST_ONLY_123' });
  assert.equal(api.lastSubmission.cmd, 'connect'); assert.equal(result.ip, '10.3.0.214');
  assert.deepEqual(progress, ['wifi_connecting']); assert.equal(result.session, 1);
  api.networkFailure = true;
  await assert.rejects(app.connectWifi({ ssid_b64: 'TGFuc2Vl', password: 'TEST_ONLY_123' }), e => e.code === 'connection_timeout' && e.detail === -110);
  api.networkFailure = false; api.invalidIP = true;
  await assert.rejects(app.connectWifi({ ssid_b64: 'TGFuc2Vl', password: 'TEST_ONLY_123' }), /invalid_network_result/);
  const before = api.writes.length;
  await assert.rejects(app.connectWifi({ ssid_b64: 'TGFuc2Vl', password: 'short' }), /invalid_password/);
  assert.equal(api.writes.length, before); await app.dispose();
});

test('online scan is rejected before X and the list page retains the BLE connection', async () => {
  const api = new MockUni();api.networkConnected = true;const ui = {};
  const app = await openVelaWifiList(api, 'k7', x => Object.assign(ui, x));
  assert.equal(app.connected, true);assert.equal(ui.wifiConnected, true);
  assert.equal(ui.ip, '10.3.0.214');assert.equal(ui.error, 'online_scan_unavailable');
  assert.equal(ui.canScan, false);
  assert.ok(!api.writes.some(b => b.length === 1 && b[0] === 88));
  await app.dispose();
});

test('credential receipt uses explicit capability, preserves password and does not imply connection', async () => {
  const api = new MockUni(); const app = new VelaProvision(api);
  await app.connect('k7');let before = api.writes.length;
  await assert.rejects(app.submitCredentials({ ssid_b64: 'TGFuc2Vl', password: 'EXAMPLE_123' }), /not_ready/);
  assert.equal(api.writes.length, before);await app.disconnect();
  api.acceptCredentials = true;await app.connect('k7');
  const receipt = await app.submitCredentials({ ssid_b64: 'TGFuc2Vl', password: ' space\\quote" ' });
  assert.equal(receipt.session, 1);assert.equal(receipt.wifi_connected, false);assert.equal(receipt.stored, false);
  assert.equal(api.lastSubmission.password, ' space\\quote" ');before = api.writes.length;
  for (const [ssid_b64, password, error] of [['YR==', '12345678', 'invalid_ssid'], ['TGFuc2Vl', '1234567', 'invalid_password'], ['TGFuc2Vl', '1234567中', 'invalid_password']])
    await assert.rejects(app.submitCredentials({ ssid_b64, password }), new RegExp(error));
  assert.equal(api.writes.length, before);
  api.falseSuccess = true;
  await assert.rejects(app.submitCredentials({ ssid_b64: 'TGFuc2Vl', password: 'EXAMPLE_123' }), /invalid_receipt/);
  await app.dispose();
});

test('receipt-capable device enables send-details UI but never enables connectWifi', async () => {
  const api = new MockUni();api.acceptCredentials = true;
  api.base64ToArrayBuffer = text => Uint8Array.from(Buffer.from(text, 'base64')).buffer;
  const state = {};const app = await openVelaWifiList(api, 'k7', update => Object.assign(state, update));
  assert.equal(state.passwordEnabled, true);assert.equal(state.canSubmitCredentials, true);
  assert.equal(state.canConnectWifi, false);await app.dispose();
  assert.equal(state.passwordEnabled, false);assert.equal(state.canSubmitCredentials, false);
});

test('submit example clears password input and stale receipt state after failure', async () => {
  const state = { credentialsReceived: true };
  const ble = { submitCredentials: async () => { throw Object.assign(new Error('invalid_password'), { code: 'invalid_password' }); } };
  await assert.rejects(submitWifiDetails(ble, 'TGFuc2Vl', 'short', update => Object.assign(state, update)), /invalid_password/);
  assert.equal(state.credentialsReceived, false);assert.equal(state.clearPassword, true);
  assert.equal(state.submittingCredentials, false);assert.equal(state.error, 'invalid_password');
});
