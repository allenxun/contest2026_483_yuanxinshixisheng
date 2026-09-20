import { VelaProvision } from './vela-provision.mjs';

// Call from the App's device page; UI collects the password only when enabled.
export async function openWifiProvisioning(uni, deviceId, render) {
  const ble = new VelaProvision(uni, {
    onConnection: ready => render(ready ? { bluetoothReady: true } : { bluetoothReady: false, canConnectWifi: false }),
    onWifiState: event => render({ phase: event.event, requestId: event.id })
  });
  try {
    const capability = await ble.connect(deviceId);
    if (capability.connect !== true) throw new Error('firmware_not_ready');
    render({ canConnectWifi: true });
    return ble;
  } catch (error) { await ble.dispose(); throw error; }
}

export async function connectSelectedWifi(ble, accessPoint, password, render, clearPassword) {
  render({ phase: 'submitting', ip: null });
  try {
    const result = await ble.connectWifi({ ssid_b64: accessPoint.ssid_b64, password });
    // DHCP success means local network joined, not internet reachability.
    render({ phase: 'local_network_connected', ip: result.ip, requestId: result.id });
    return result;
  } catch (error) {
    render({ phase: 'failed', code: error.code || error.message, requestId: error.id, ip: null });
    throw error;
  } finally { password = ''; clearPassword(); }
}
