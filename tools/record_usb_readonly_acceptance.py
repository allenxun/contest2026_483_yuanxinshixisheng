"""Bind finite native block reads and wireless recovery to the loaded image."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from verify_usb_readonly_image import verify

R = Path(__file__).resolve().parents[1]
E = R/'evidence/usb-readonly-20260910'
image = verify(R/'artifacts/usb-readonly-20260910')
load = (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert 'PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED' in load
assert 'PASS: REAL K7 NSH' in load and image['sha256'] in load
enum = json.loads((E/'enumeration.json').read_text())
assert enum['passed'] and enum['before'] == [] and enum['new_nodes'] == ['/dev/sda']
raw = (E/'read.bin').read_bytes()
assert b'USB_STORAGE command=read result=0 mount_attempted=0' in raw
assert re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw)
match = re.search(rb'USB_STORAGE read node=/dev/sda sector_size=(\d+) sectors=(\d+) readonly=1 lba=0 reads=2 crc32=([0-9a-f]{8}) repeated=1', raw)
assert match
ble = [json.loads(s) for s in (E/'ble-wireless.jsonl').read_text().splitlines()]
assert any(x['event'] == 'PASS' and x['ip'] == '10.3.0.214' for x in ble)
assert any(x['event'] == 'hold_pass' and x['seconds'] == 30 for x in ble)
assert ble[-1]['event'] == 'test_client_disconnected'
gateway = json.loads((E/'gateway.json').read_text())
lines = [s for x in gateway['records'] for s in x['lines']]
assert any('5 packets transmitted, 5 received, 0% packet loss' in s for s in lines)
rejects = [int(re.search(r'rejected=(\d+)', s)[1]) for s in lines if 'WIFI AMSDU' in s]
assert rejects == [1, 1]
state = dict(running_revision=E.name, boot='RAM', firmware_sha256=image['sha256'],
    smp_cpus=8, usb_storage_enabled=True, usb_new_node='/dev/sda',
    usb_first_sector_read_passed=True, usb_sector_size=int(match[1]), usb_sectors=int(match[2]),
    usb_repeated_crc32=match[3].decode(), usb_media_written=False, filesystem_mounted=False,
    usb_vid_pid_recorded=False, full_identity_bound_acceptance=False,
    wifi_connected=True, ip='10.3.0.214', gateway_ping='5/5', wireless_hold_seconds=30,
    ble_service_running=True, ble_connected=False, ble_disconnect='Test client intentionally disconnected',
    receive_rejects_before=1, receive_rejects_after=1, serial_observer_running=False,
    model_loaded=False, agent_deployed=False, audio_hardware_tested=False,
    microphone_connection='User explicitly confirmed MIC connector',
    emmc_written=False, evidence_directory=E.relative_to(R).as_posix(),
    limits=['Finite LBA0 two-read/close test; no filesystem or model load',
            'VID/PID absent from enumeration output; strict identity parser acceptance not claimed',
            'Wireless recovery with USB host idle, not concurrent USB bulk load stress',
            'One cumulative RX reject retained; cause not diagnosed, no zero-reject acceptance',
            'C++ concurrent cold exceptions and full audio integration unresolved'])
proof = dict(state=state, recorded_utc=datetime.now(timezone.utc).isoformat(),
    hashes={n:hashlib.sha256((E/n).read_bytes()).hexdigest() for n in
        ('ramload-progress.txt','affinity-boot.json','before.bin','start.bin','enumeration-wait.bin',
         'after.bin','read.bin','ble-wireless.jsonl','gateway.json')})
with (E/'runtime-acceptance.json').open('x') as f: json.dump(proof, f, indent=2)
p = R/'project-manifest.json'
m = json.loads(p.read_text(encoding='utf-8'))
m['current_device'] = state
m['last_verified_device'] = state.copy()
m['pending_firmware'] = None
m['updated_at'] = proof['recorded_utc']
p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'README.md'
s = p.read_text(encoding='utf-8')
a = s.index('**当前已验收')
b = s.index('\n\n', a)
s = s[:a] + '**当前运行 `usb-readonly-20260910`（RAM）。** 新USB块节点 `/dev/sda` 枚举、两次首扇区读取一致及关闭通过；未挂载文件系统或加载模型。无线恢复后真实配网/IP、30秒保持、网关5/5通过，USB控制器保持空闲；测试BLE客户端主动断开。接收拒绝累计1→1仍保留，VID/PID未记录，不宣称完整USB身份验收或长稳。此前模型池ggml缓冲区已真机通过，音频接线经用户确认，录放音驱动仍在开发。最新证据 `evidence/usb-readonly-20260910/runtime-acceptance.json`。' + s[b:]
p.write_text(s, encoding='utf-8')
note = '\n\n本轮真实结果：USB新节点/dev/sda，512字节扇区、60555264扇区，两次LBA0 CRC32=b1241e76且关闭成功；未挂载/未写盘。无线恢复30秒及网关5/5，拒绝1→1保留。VID/PID未输出，严格身份绑定验收尚未满足。见evidence/usb-readonly-20260910/runtime-acceptance.json；当前无持续串口进程。\n'
for name in ('docs/USB只读模型存储接入_20260910.md', 'docs/代码日志对应表.md'):
    with (R/name).open('a', encoding='utf-8') as f: f.write(note)
print('Finite USB read and wireless recovery recorded; identity/stability limits retained')
