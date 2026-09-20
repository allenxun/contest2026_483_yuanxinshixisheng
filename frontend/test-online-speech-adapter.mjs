import assert from 'node:assert/strict';
import { test } from 'node:test';
import { VelaOnlineSpeechAdapter } from './整机联网语音适配器.mjs';

class FakeProvision {
  constructor() {
    this.rows = [{ ssid_b64: 'TGFuc2Vl', rssi: -40, security: 'rsn' }];
    this.connectedDetails = null;
  }
  async connect() { return { v: 1, encrypted: true, scan: true, connect: true, session: 7 }; }
  async scan() { return { count: this.rows.length, truncated: false, networks: this.rows }; }
  async connectWifi(details) { this.connectedDetails = details; return { wifi_connected: true, ip: '10.3.0.214' }; }
  async dispose() { this.disposed = true; }
}

test('reuses BLE scan/connect and reports layered readiness without retaining password', async () => {
  const provision = new FakeProvision();
  const states = []; const reports = []; const speechCalls = [];
  const adapter = new VelaOnlineSpeechAdapter(null, {
    provision,
    onState: state => states.push(state),
    internetProbe: async ({ ip }) => ({ ready: ip === '10.3.0.214' }),
    reportOnline: async state => reports.push(state),
    cloudProbe: async () => true,
    speechClient: {
      asr: async (audio, options) => { speechCalls.push(['asr', audio, options]); return { text: '你好' }; },
      tts: async (text, options) => { speechCalls.push(['tts', text, options]); return new Uint8Array([1, 2]); }
    }
  });
  await adapter.open('k7');
  await adapter.scan();
  adapter.selectNetwork('TGFuc2Vl');
  let cleared = false;
  const password = 'SECRET_TEST_123';
  const result = await adapter.connectSelected(password, () => { cleared = true; });

  assert.equal(provision.connectedDetails.ssid_b64, 'TGFuc2Vl');
  assert.equal(provision.connectedDetails.password, password);
  assert.equal(cleared, true);
  assert.equal(result.wifi_connected, true);
  assert.equal(result.ip, '10.3.0.214');
  assert.equal(result.internet_ready, true);
  assert.equal(result.online_reported, true);
  assert.equal(result.cloud_ready, true);
  assert.deepEqual(reports, [{ wifi_connected: true, ip: '10.3.0.214', internet_ready: true }]);
  assert.ok(states.some(state => state.wifi_connected && !state.internet_ready));
  assert.ok(states.some(state => state.internet_ready && !state.cloud_ready));
  assert.ok(!JSON.stringify(states).includes(password));
  assert.ok(!JSON.stringify(reports).includes(password));

  assert.deepEqual(await adapter.asr(new Uint8Array([3]), { sampleRate: 16000 }), { text: '你好' });
  assert.deepEqual(await adapter.tts('联网成功'), new Uint8Array([1, 2]));
  assert.equal(speechCalls.length, 2);
});

test('DHCP success remains visible when internet probe fails and cloud calls stay disabled', async () => {
  const provision = new FakeProvision(); let cloudProbes = 0; let cleared = false;
  const adapter = new VelaOnlineSpeechAdapter(null, {
    provision,
    internetProbe: async () => false,
    cloudProbe: async () => { cloudProbes++; return true; },
    speechClient: { asr: async () => ({ text: 'wrong' }), tts: async () => new Uint8Array() }
  });
  await adapter.open('k7'); await adapter.scan(); adapter.selectNetwork('TGFuc2Vl');
  const state = await adapter.connectSelected('SECRET_TEST_123', () => { cleared = true; });
  assert.equal(cleared, true);
  assert.equal(state.wifi_connected, true);
  assert.equal(state.internet_ready, false);
  assert.equal(state.cloud_ready, false);
  assert.equal(state.error, 'internet_unavailable');
  assert.equal(cloudProbes, 0);
  await assert.rejects(adapter.asr(new Uint8Array()), /cloud_not_ready/);
  await assert.rejects(adapter.tts('test'), /cloud_not_ready/);
});

test('only a network from the current scan can be selected', async () => {
  const adapter = new VelaOnlineSpeechAdapter(null, { provision: new FakeProvision() });
  await adapter.open('k7'); await adapter.scan();
  assert.throws(() => adapter.selectNetwork('VW5rbm93bg=='), /network_not_in_scan/);
  await assert.rejects(adapter.connectSelected('SECRET_TEST_123'), /network_not_selected/);
  assert.ok(!Object.hasOwn(adapter.snapshot(), 'password'));
});

const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
async function prepared(options = {}) {
  const provision = options.provision || new FakeProvision();
  const adapter = new VelaOnlineSpeechAdapter(null, { provision, ...options });
  await adapter.open('k7'); await adapter.scan(); adapter.selectNetwork('TGFuc2Vl');
  return { adapter, provision };
}

test('disconnect while internet probe is pending cannot resurrect readiness or report online', async () => {
  const wait = deferred(); let reports = 0;
  const { adapter, provision } = await prepared({
    internetProbe: () => wait.promise, reportOnline: async () => { reports++; }, cloudProbe: async () => true
  });
  const pending = adapter.connectSelected('SECRET_TEST_123');
  await new Promise(resolve => setImmediate(resolve));
  provision.onConnection(false); wait.resolve(true); await pending;
  assert.equal(adapter.snapshot().cloud_ready, false);
  assert.equal(adapter.snapshot().wifi_connected, false);
  assert.equal(reports, 0);
});

test('dispose while cloud probe is pending immediately closes gates and ignores late success', async () => {
  const wait = deferred();
  const { adapter } = await prepared({ internetProbe: async () => true, cloudProbe: () => wait.promise });
  const pending = adapter.connectSelected('SECRET_TEST_123');
  await new Promise(resolve => setImmediate(resolve));
  await adapter.dispose(); wait.resolve(true); await pending;
  assert.equal(adapter.snapshot().cloud_ready, false);
  assert.equal(adapter.snapshot().wifi_connected, false);
});

test('late older probe cannot override newer failed connectivity check', async () => {
  const wait = deferred(); let count = 0;
  const { adapter } = await prepared({ internetProbe: () => ++count === 1 ? wait.promise : false,
    cloudProbe: async () => true });
  const pending = adapter.connectSelected('SECRET_TEST_123');
  await new Promise(resolve => setImmediate(resolve));
  await adapter.refreshConnectivity(); wait.resolve(true); await pending;
  assert.equal(adapter.snapshot().cloud_ready, false);
  assert.equal(adapter.snapshot().internet_ready, false);
});

test('board status loss revokes previously ready cloud state', async () => {
  const { adapter, provision } = await prepared({ internetProbe: async () => true, cloudProbe: async () => true });
  await adapter.connectSelected('SECRET_TEST_123');
  assert.equal(adapter.snapshot().cloud_ready, true);
  provision.status = async () => ({ wifi_connected: false, ip: null });
  await adapter.refreshConnectivity();
  assert.equal(adapter.snapshot().wifi_connected, false);
  assert.equal(adapter.snapshot().cloud_ready, false);
  assert.equal(adapter.snapshot().error, 'wifi_status_unconfirmed');
});

test('late report success after BLE disconnect cannot mark online or call cloud probe', async () => {
  const wait = deferred(); let cloudCalls = 0;
  const { adapter, provision } = await prepared({ internetProbe: async () => true,
    reportOnline: () => wait.promise, cloudProbe: async () => { cloudCalls++; return true; } });
  const pending = adapter.connectSelected('SECRET_TEST_123');
  await new Promise(resolve => setImmediate(resolve));
  provision.onConnection(false); wait.resolve(); await pending;
  assert.equal(adapter.snapshot().online_reported, false);
  assert.equal(cloudCalls, 0);
});
