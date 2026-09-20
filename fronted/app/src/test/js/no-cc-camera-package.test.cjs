const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const project = path.resolve(__dirname, '../../../..');
const main = path.join(project, 'app/src/main');
const read = relative => fs.readFileSync(path.join(project, relative), 'utf8');

test('养肤页只展示三张仍受支持的设备卡片', () => {
  const layout = read('app/src/main/res/layout/fragment_skincare.xml');
  const cardIds = [...layout.matchAll(/android:id="@\+id\/(cardDevice[123]|cardCamera)"/g)]
    .map(match => match[1]);
  assert.deepEqual(cardIds, ['cardDevice1', 'cardDevice2', 'cardDevice3']);
});

test('安装清单保留 K7，且不注册已移除的 CC-C 页面', () => {
  const manifest = read('app/src/main/AndroidManifest.xml');
  assert.match(manifest, /\.ui\.device\.OpenVelaConnectActivity/);
  assert.doesNotMatch(manifest, /\.ui\.device\.DeviceSkinTestActivity/);
});

test('BLE 配网不再要求已移除摄像头使用的系统 Wi-Fi 权限', () => {
  const manifest = read('app/src/main/AndroidManifest.xml');
  assert.match(manifest, /android\.permission\.BLUETOOTH_SCAN/);
  for (const permission of ['ACCESS_WIFI_STATE', 'CHANGE_WIFI_STATE', 'NEARBY_WIFI_DEVICES']) {
    assert.doesNotMatch(manifest, new RegExp('android\\.permission\\.' + permission));
  }
});

test('打包输入不包含 CC-C 与 FFmpeg 原生库', () => {
  assert.equal(fs.existsSync(path.join(project, 'libs')), false);
  assert.equal(fs.existsSync(path.join(main, 'jniLibs')), false);
  assert.equal(fs.existsSync(path.join(main, 'java/com/sdk/wifivideo/WifiCamera.kt')), false);
  assert.equal(fs.existsSync(path.join(main, 'java/com/example/aisia/ui/device/DeviceSkinTestActivity.kt')), false);
  assert.equal(fs.existsSync(path.join(main, 'java/com/example/aisia/ui/device/CameraWifiManager.kt')), false);
  const gradle = read('app/build.gradle.kts');
  assert.match(gradle, /filament-extract\/jni/);
  assert.doesNotMatch(gradle, /src\/main\/jniLibs/);
});
