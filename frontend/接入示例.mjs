// SPDX-License-Identifier: Apache-2.0
import { VelaProvision, UUID, decodeUtf8 } from './vela-provision.mjs';

// deviceId 必须来自当前手机的 BLE 扫描结果。iOS 不使用固定 MAC 地址。
// App 负责系统蓝牙权限、设备选择页面；调用前停止自身的 BLE 扫描。
export async function openVelaWifiList(uni, deviceId, updateUi) {
  updateUi({ bluetoothReady: false, canScan: false, canConnectWifi: false,
    passwordEnabled: false, canSubmitCredentials: false, scanComplete: false });
  const ble = new VelaProvision(uni, {
    onConnection: ready => updateUi(ready ? { bluetoothReady: true } : {
      bluetoothReady: false, canScan: false, canConnectWifi: false,
      passwordEnabled: false, canSubmitCredentials: false, scanComplete: false
    }),
    onAccessPoint: ap => {
      let label;
      try {
        label = decodeUtf8(new Uint8Array(uni.base64ToArrayBuffer(ap.ssid_b64)));
        if (!label) label = '隐藏网络';
      } catch { label = '非 UTF-8 网络 (' + ap.ssid_b64 + ')'; }
      // label 只用作文本显示；保留 ssid_b64 原样，禁止重新编码显示名作为 SSID。
      updateUi({ accessPoint: { ...ap, label } });
    }
  });
  try {
    const capabilities = await ble.connect(deviceId);
    // 接收配网信息与真正联网是两个能力；旧 id36 不会开放提交。
    updateUi({ canScan: capabilities.scan === true, canConnectWifi: false,
      passwordEnabled: capabilities.receive_credentials === true,
      canSubmitCredentials: capabilities.receive_credentials === true });
    if (capabilities.scan !== true) throw new Error('scan_not_supported');
    const result = await ble.scan();
    updateUi({ scanComplete: true, count: result.count, truncated: result.truncated });
    // 保留 ble 供页面刷新列表和状态查询；离开页面时 await ble.dispose()。
    return ble;
  } catch (error) {
    if (error.code === 'online_scan_unavailable') {
      updateUi({ bluetoothReady: true, canScan: false, scanComplete: false,
        wifiConnected: true, ip: error.ip, error: error.code });
      return ble; // Keep BLE open so status and network changes remain usable.
    }
    await ble.dispose();
    updateUi({ bluetoothReady: false, error: error.code || error.message || 'ble_error' });
    throw error;
  }
}

// 扫描页面可用此服务 UUID 筛选候选设备；名称可能在后续广播包才到达。
export const discoveryService = UUID.service;

// 按钮文案“发送给设备”，成功文案“设备已收到，尚未联网”。
// 页面不得持久化或日志记录 password；调用结束后清空输入框。
export async function submitWifiDetails(ble, ssid_b64, password, updateUi) {
  updateUi({ credentialsReceived: false, submittingCredentials: true, error: null });
  try {
    const receipt = await ble.submitCredentials({ ssid_b64, password });
    updateUi({ credentialsReceived: true, wifiConnected: false, ip: null });
    return receipt;
  } catch (error) {
    updateUi({ credentialsReceived: false, error: error.code || error.message || 'receipt_unconfirmed' });
    throw error;
  } finally {
    updateUi({ clearPassword: true, submittingCredentials: false });
  }
}
