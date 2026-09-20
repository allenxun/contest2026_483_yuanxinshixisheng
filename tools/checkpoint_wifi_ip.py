"""Checkpoint verified native WLAN results, without claiming BLE coexistence."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
r=Path(__file__).resolve().parents[1];rev='wifi-ip-rx-20260909';base=r/'evidence'/rev
def read(n):return (base/n).read_text(encoding='utf-8',errors='replace')
assert 'DHCP acquired ip=10.3.0.214 gateway=10.3.0.1 wifi_connected=1' in read('lansee-ip-01.jsonl')
assert 'DHCP acquired ip=10.3.0.214 gateway=10.3.0.1 wifi_connected=1' in read('lansee-reconnect-02.jsonl')
assert '30 packets transmitted, 30 received, 0% packet loss' in read('ping-coexist-01.bin')
assert 'completed=0 ret=-110 installed=00 IP_acquired=0' in read('wrong-password-01.jsonl')
assert 'link cleanup keys=0 unjoin=0 close=0' in read('disconnect-01.bin')
v=dict(updated_at=datetime.now(timezone.utc).isoformat(),running_revision=rev,boot='RAM',firmware_sha256=hashlib.sha256((r/'artifacts'/rev/'nuttx.bin').read_bytes()).hexdigest(),wpa2_hardware_passed=True,dhcp_hardware_passed=True,test_ssid='Lansee',tested_ip='10.3.0.214',tested_gateway='10.3.0.1',gateway_ping=dict(sent=30,received=30,loss_percent=0),wrong_password=dict(authenticated=False,keys_installed=False,ip_acquired=False,cleanup_passed=True),correct_password_retry_passed=True,ble_wifi_coexistence_passed=False,frontend_connect=False,current_device_scope='Rebooted same RAM image for user-requested phone BLE retry; Wi-Fi not yet reconnected after that reboot',emmc_written=False,stm32_written=False,gimbal_started=False)
v['evidence']={n:hashlib.sha256((base/n).read_bytes()).hexdigest() for n in ('lansee-ip-01.jsonl','lansee-reconnect-02.jsonl','ping-gateway.bin','ping-coexist-01.bin','wrong-password-01.jsonl','disconnect-01.bin')}
(base/'device-state.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'));m['latest_wireless_checkpoint']=v;p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
intro='**最新真机结果：原生 Wi-Fi 已完成 WPA2、DHCP 和网关通信。** `wifi-ip-rx-20260909` 取得 Lansee 的 `10.3.0.214`，网关 `10.3.0.1` 连续 30 次 Ping 全部成功；错误密码拒绝、主动断开清理及正确密码重新联网通过。Windows BLE 服务发现测试未通过，手机重试正在记录；前端仍 `connect:false`。用户要求重测蓝牙后，同一 RAM 镜像已重启，暂未恢复 Wi-Fi 连接。见 [真实认证与 IP 记录](docs/WiFi认证与IP接入_20260909.md) 和 `evidence/wifi-ip-rx-20260909/device-state.json`。\n\n'
p=r/'README.md';s=p.read_text(encoding='utf-8');s=s.replace('## 当前统一版本\n\n','## 当前统一版本\n\n'+intro,1);p.write_text(s,encoding='utf-8')
p=r/'docs/代码日志对应表.md';s=p.read_text(encoding='utf-8');s=s.replace('# 代码、日志与验证对应表\n\n','# 代码、日志与验证对应表\n\n最新 `wifi-ip-rx-20260909`：WPA2、DHCP、网关 30/30、错误密码拒绝及恢复联网有真机证据，位于 `evidence/wifi-ip-rx-20260909/`；对应源码/构建在 `evidence/build/wifi-ip-rx-20260909/verification.json`。蓝牙并发、正式前端 connect 接口仍未验收，不混写为已交付。下方保留历史。\n\n',1);p.write_text(s,encoding='utf-8')
print('Verified Wi-Fi hardware evidence checkpoint saved')
