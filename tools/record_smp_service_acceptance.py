"""Record bounded integrated hardware results, retaining narrower scope."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/smp-service-20260910'
assert 'PASS: REAL K7 NSH' in (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
for n in ['diagnostic', 'affinity-boot', 'affinity-radio']:
    assert json.loads((E / (n + '.json')).read_text())['passed']
ble = [json.loads(x) for x in (E / 'ble-connect.jsonl').read_text().splitlines()]
assert any(x['event'] == 'hold_pass' and x['seconds'] == 60 for x in ble)
assert any(x['event'] == 'test_client_disconnected' for x in ble)
gateway = json.loads((E / 'gateway-during-ble.json').read_text())
lines = [line for row in gateway['records'] for line in row['lines']]
assert any('5 packets transmitted, 5 received, 0% packet loss' in line for line in lines)
assert any('connected=1' in line and line.startswith('RADIO BLE name=') for line in lines)
assert any('encrypted=1' in line for line in lines)
assert any('rejected=0' in line for line in lines)
state = dict(running_revision=E.name, boot='RAM', smp_cpus=8,
             firmware_sha256=hashlib.sha256((R / 'artifacts' / E.name / 'nuttx.bin').read_bytes()).hexdigest(),
             wifi_connected=True, ip='10.3.0.214', gateway_ping='5/5 during encrypted BLE connection',
             ble_service_running=True, ble_connected=False, ble_disconnect='test client intentionally disconnected after successful 60-second hold',
             default_service_affinity='0x1; actual radio and network tasks verified on CPU0',
             diagnostic_shared_counter=80000, diagnostic_cpu_mismatches=0,
             hold_seconds=60, amsdu_rejected=0, emmc_written=False,
             emmc_reregistered_this_boot=False, evidence_directory=E.relative_to(R).as_posix(),
             provisioning_stack_peak=dict(used=6688, allocated=8112, percent=82.4),
             limits=['No sustained compute load concurrent with radio', 'No Android/iOS or internet acceptance in this round',
                     'Not long-term acceptance', 'USB, NPU, audio, eMMC and model arena not retested in this SMP boot',
                     'Provisioning stack headroom needs review before adding shared voice service'])
out = E / 'acceptance.json'
assert not out.exists()
out.write_text(json.dumps(state, indent=2) + '\n')
p = R / 'project-manifest.json'
m = json.loads(p.read_text())
m['updated_at'] = datetime.now(timezone.utc).isoformat()
m['current_device'] = state
m['last_verified_device'] = state.copy()
m['pending_firmware'] = None
m['cpu_plan'].update(current_configured_cpus=8, smp_verified=True,
                     peripheral_smp_verified='bounded radio regression only, services pinned to CPU0')
m['smp_diagnostics']['service_integration'] = 'evidence/smp-service-20260910/acceptance.json'
p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
p = R / 'README.md'
s = p.read_text()
start = s.index('**当前板端')
end = s.index('\n\n', start)
s = s[:start] + '**当前板端运行八核无线集成候选 `smp-service-20260910`（RAM启动）。** 四颗A53与四颗A72诊断通过，普通服务默认CPU0且实际无线线程亲和性已核对。BLE真实WPA2/DHCP配网、60秒保持、加密BLE连接期间网关5/5通过，本轮A-MSDU拒收0；测试客户端随后主动断开，Wi-Fi在线。见 `evidence/smp-service-20260910/acceptance.json`。尚未验证持续计算负载与外设并发、全机长稳、板端语音或Agent。' + s[end:]
p.write_text(s, encoding='utf-8')
for name in ['八核CPU接入与任务分配_20260910.md', '八核无线集成候选审查_20260910.md', '代码日志对应表.md']:
    with (R / 'docs' / name).open('a', encoding='utf-8') as f:
        f.write('\n\n2026-09-10后续实测：smp-service-20260910 已RAM上板。8核诊断通过，系统/无线线程亲和性0x1已核对；BLE真实配网及60秒保持、BLE加密连接期间Wi-Fi网关5/5、本轮拒收0。当前保留此候选运行，测试客户端主动断开。不是持续计算并发、外设全量或长稳验收；k7_provision栈峰值6688/8112字节，后续共享语音服务接入前应复核余量。见 evidence/smp-service-20260910/acceptance.json。\n')
print('Recorded bounded eight-core radio hardware acceptance')
