// SPDX-License-Identifier: Apache-2.0
// App-level orchestration over the existing VelaVision BLE protocol.
// Wi-Fi credentials are passed directly to VelaProvision and are never stored
// in this adapter's state or included in callbacks.
import { VelaProvision } from './vela-provision.mjs';

const emptyState = () => ({
  bluetooth_ready: false,
  scan_done: false,
  networks: [],
  wifi_connecting: false,
  wifi_connected: false,
  ip: null,
  internet_ready: false,
  online_reported: false,
  cloud_ready: false,
  error: null
});

const ready = value => value === true || value?.ready === true;
const safeCode = (error, fallback) => {
  const code = error?.code;
  return typeof code === 'string' && /^[a-z0-9_]{1,64}$/i.test(code) ? code : fallback;
};

export class VelaOnlineSpeechAdapter {
  constructor(uniApi, {
    onState = () => {},
    internetProbe = async () => false,
    reportOnline = null,
    cloudProbe = async () => false,
    speechClient = null,
    provision = null
  } = {}) {
    this.onState = onState;
    this.internetProbe = internetProbe;
    this.reportOnline = reportOnline;
    this.cloudProbe = cloudProbe;
    this.speechClient = speechClient;
    this.state = emptyState();
    this.selected = null;
    this.generation = 0;
    this.probeGeneration = 0;
    this.provision = provision || new VelaProvision(uniApi);
    const previousConnection = this.provision.onConnection;
    const previousWifiState = this.provision.onWifiState;
    this.provision.onConnection = value => {
      if (!value) {
        this.generation++;
        this.probeGeneration++;
        this.selected = null;
        this._set({ ...emptyState(), capabilities: null, error: 'ble_disconnected' });
      } else this._set({ bluetooth_ready: true });
      previousConnection?.(value);
    };
    this.provision.onWifiState = event => {
      if (event.event === 'wifi_connecting') {
        this.probeGeneration++;
        this._set({ wifi_connecting: true, wifi_connected: false, ip: null,
          internet_ready: false, online_reported: false, cloud_ready: false, error: null });
      }
      previousWifiState?.(event);
    };
  }

  snapshot() {
    return Object.freeze({ ...this.state, networks: this.state.networks.map(row => ({ ...row })) });
  }

  _set(update) {
    this.state = { ...this.state, ...update };
    this.onState(this.snapshot());
  }

  async open(deviceId) {
    const capabilities = await this.provision.connect(deviceId);
    if (capabilities.connect !== true)
      throw Object.assign(new Error('firmware_not_ready'), { code: 'firmware_not_ready' });
    this._set({ bluetooth_ready: true, capabilities: { ...capabilities }, error: null });
    return this.snapshot();
  }

  async scan() {
    const generation = this.generation;
    this.selected = null;
    this._set({ scan_done: false, networks: [], error: null });
    try {
      const result = await this.provision.scan();
      if (generation !== this.generation) return this.snapshot();
      this._set({ scan_done: true, networks: result.networks.map(row => ({ ...row })) });
      return this.snapshot();
    } catch (error) {
      if (generation === this.generation) this._set({ error: safeCode(error, 'scan_failed') });
      throw error;
    }
  }

  selectNetwork(ssid_b64) {
    const selected = this.state.networks.find(row => row.ssid_b64 === ssid_b64);
    if (!selected) throw Object.assign(new Error('network_not_in_scan'), { code: 'network_not_in_scan' });
    this.selected = { ...selected };
    return { ...selected };
  }

  async connectSelected(password, clearPassword = () => {}) {
    if (!this.selected)
      throw Object.assign(new Error('network_not_selected'), { code: 'network_not_selected' });
    const ssid_b64 = this.selected.ssid_b64;
    const generation = ++this.generation;
    this.probeGeneration++;
    this._set({
      wifi_connecting: true, wifi_connected: false, ip: null,
      internet_ready: false, online_reported: false, cloud_ready: false, error: null
    });
    try {
      const result = await this.provision.connectWifi({ ssid_b64, password });
      if (generation !== this.generation) return this.snapshot();
      this._set({ wifi_connecting: false, wifi_connected: true, ip: result.ip });
      await this.refreshConnectivity();
      return this.snapshot();
    } catch (error) {
      if (generation === this.generation)
        this._set({ wifi_connecting: false, error: safeCode(error, 'wifi_connect_failed') });
      throw error;
    } finally {
      password = '';
      clearPassword();
    }
  }

  async refreshConnectivity() {
    if (!this.state.wifi_connected || !this.state.ip)
      throw Object.assign(new Error('wifi_not_connected'), { code: 'wifi_not_connected' });

    const generation = this.generation;
    const probe = ++this.probeGeneration;
    const ip = this.state.ip;
    const current = () => generation === this.generation && probe === this.probeGeneration;
    this._set({ internet_ready: false, online_reported: false, cloud_ready: false });
    // Re-read the real board state when supported. A phone's own network route
    // is not proof that the K7 retained its DHCP lease.
    if (typeof this.provision.status === 'function') {
      let status;
      try { status = await this.provision.status(); } catch { status = null; }
      if (!current()) return this.snapshot();
      if (status?.wifi_connected !== true || status.ip !== ip) {
        this.generation++;
        this._set({ wifi_connected: false, wifi_connecting: false, ip: null,
          error: 'wifi_status_unconfirmed' });
        return this.snapshot();
      }
    }
    let internetReady = false;
    try {
      internetReady = ready(await this.internetProbe({ ip }));
    } catch {
      internetReady = false;
    }
    if (!current()) return this.snapshot();
    this._set({
      internet_ready: internetReady,
      online_reported: false,
      cloud_ready: false,
      error: internetReady ? null : 'internet_unavailable'
    });
    if (!internetReady) return this.snapshot();

    if (typeof this.reportOnline === 'function') {
      try {
        await this.reportOnline({
          wifi_connected: true,
          ip,
          internet_ready: true
        });
        if (!current()) return this.snapshot();
        this._set({ online_reported: true });
      } catch (error) {
        if (!current()) return this.snapshot();
        this._set({ error: safeCode(error, 'online_report_failed') });
        return this.snapshot();
      }
    }

    let cloudReady = false;
    try {
      cloudReady = ready(await this.cloudProbe());
    } catch {
      cloudReady = false;
    }
    if (!current()) return this.snapshot();
    this._set({ cloud_ready: cloudReady, error: cloudReady ? null : 'cloud_unavailable' });
    return this.snapshot();
  }

  async asr(audio, options = {}) {
    if (!this.state.cloud_ready || typeof this.speechClient?.asr !== 'function')
      throw Object.assign(new Error('cloud_not_ready'), { code: 'cloud_not_ready' });
    return this.speechClient.asr(audio, options);
  }

  async tts(text, options = {}) {
    if (!this.state.cloud_ready || typeof this.speechClient?.tts !== 'function')
      throw Object.assign(new Error('cloud_not_ready'), { code: 'cloud_not_ready' });
    return this.speechClient.tts(text, options);
  }

  async dispose() {
    this.generation++;
    this.probeGeneration++;
    this.selected = null;
    this._set({ ...emptyState(), capabilities: null });
    await this.provision.dispose();
  }
}
