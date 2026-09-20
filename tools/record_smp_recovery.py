"""Join actual recovery observations without erasing historical failures."""
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/smp-eight-20260910'
assert 'PASS: REAL K7 NSH' in (E / 'recovery-progress.txt').read_text(encoding='utf-8-sig')
ble = [json.loads(x) for x in (E / 'recovery-ble.jsonl').read_text().splitlines()]
assert any(x['event'] == 'PASS' for x in ble)
assert any(x['event'] == 'hold_pass' and x['seconds'] == 30 for x in ble)
gateway = json.loads((E / 'recovery-gateway.json').read_text())
assert any('5 packets transmitted, 5 received, 0% packet loss' in line for r in gateway['records'] for line in r['lines'])
state = dict(running_revision='emmc-vfs-20260910', boot='RAM', smp_cpus=1,
             firmware_sha256='06320f4b86326ea91d682fb6192dad5c64f7893279f9d73ed57490f80b9fe10b',
             wifi_connected=True, ip='10.3.0.214', gateway_ping='5/5',
             ble_service_running=True, ble_connected=False, ble_disconnect='test client intentionally disconnected',
             hold_seconds=30, amsdu_rejected=0, emmc_written=False,
             emmc_reregistered_this_boot=False, evidence_directory=E.relative_to(R).as_posix(),
             limits='Recovery observation only; not long-term, Android/iOS, internet, or peripheral-SMP acceptance')
p = E / 'recovery-acceptance.json'
assert not p.exists()
p.write_text(json.dumps(state, indent=2) + '\n')
p = R / 'project-manifest.json'
m = json.loads(p.read_text())
m['updated_at'] = datetime.now(timezone.utc).isoformat()
m['current_device'] = state
m['last_verified_device'] = state.copy()
m['pending_firmware'] = dict(revision='smp-service-20260910', state='building, not loaded', default_cpuset='0x1', peripheral_smp_tested=False)
p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
p = R / 'README.md'
s = p.read_text()
s = s.replace('**当前板端正在恢复单核无线/eMMC镜像。**', '**当前板端已恢复单核无线/eMMC镜像，Wi-Fi在线、BLE服务运行。**')
s = s.replace('当前恢复镜像期间无线暂停', '最新恢复验证见 `evidence/smp-eight-20260910/recovery-acceptance.json`：真实WPA2/DHCP、30秒保持、网关5/5，本轮A-MSDU拒收0；历史异常仍保留')
s = s.replace('次会话继续语音流收尾与内存测量。', '语音编排、板载音频资料和codec候选共358份交付文件哈希已核对；完整codec录音配置仍待核实。')
p.write_text(s, encoding='utf-8')
print('Recorded actual recovery, preserved all failed attempts')
