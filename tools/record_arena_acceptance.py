"""Record the finite arena test and its matching wireless regression."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/arena-provider-20260910'
runtime = json.loads((E / 'runtime.json').read_text())
assert runtime['passed'] and runtime['prompt_returned']
row, = runtime['rows']
assert row['result'] == 0 and row['checked'] == 8192
assert row['before'] == row['after'] and row['peak'] == 32768
assert all(row[k] == 0 for k in ('mismatches', 'live', 'errors', 'quarantine', 'weights'))
assert row['allocations'] == row['releases'] == row['returned'] == row['range'] == 1
progress = (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert 'PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED' in progress
assert 'PASS: REAL K7 NSH' in progress
assert json.loads((E / 'affinity-boot.json').read_text())['passed']
ble = [json.loads(s) for s in (E / 'ble-wireless.jsonl').read_text().splitlines()]
assert any(r['event'] == 'PASS' and r['ip'] == '10.3.0.214' for r in ble)
assert any(r['event'] == 'hold_pass' and r['seconds'] == 30 for r in ble)
assert ble[-1]['event'] == 'test_client_disconnected'
lines = [s for r in json.loads((E / 'gateway.json').read_text())['records'] for s in r['lines']]
assert any('5 packets transmitted, 5 received, 0% packet loss' in s for s in lines)
state = dict(running_revision=E.name, boot='RAM', smp_cpus=8,
    firmware_sha256='b240f9448c682ce4017fbcf3405681c421b31ddb8afc7491a15535d0a8457b46',
    arena_ggml_buffer_passed=True, arena_checked_values=8192, arena_payload_bytes=32768,
    model_loaded=False, agent_deployed=False, concurrent_cxx_cold_passed=False,
    wifi_connected=True, ip='10.3.0.214', gateway_ping='5/5',
    ble_service_running=True, ble_connected=False, wireless_hold_seconds=30,
    ble_disconnect='Test client intentionally disconnected', receive_rejects_before=0,
    receive_rejects_after=0, emmc_written=False, usb_storage_enabled=False,
    evidence_directory=E.relative_to(R).as_posix(),
    limits=['32KiB buffer set/get only, no graph or weights in this test',
            'Not OOM, full DDR, model inference, long-term wireless or internet acceptance',
            'Concurrent cold C++ exception failure remains unresolved'])
proof = dict(state=state, recorded_utc=datetime.now(timezone.utc).isoformat(),
    hashes={n: hashlib.sha256((E/n).read_bytes()).hexdigest() for n in
            ('ramload-progress.txt', 'runtime.json', 'affinity-boot.json', 'ble-wireless.jsonl', 'gateway.json', 'integration.json')})
with (E/'acceptance.json').open('x', encoding='utf-8') as f:
    json.dump(proof, f, indent=2)
p = R/'project-manifest.json'
m = json.loads(p.read_text(encoding='utf-8'))
m['current_device'] = state
m['last_verified_device'] = state.copy()
m['pending_firmware'] = dict(revision='usb-readonly-20260910', compiled=False,
    hardware_tested=False, next='Checked MSC and bounded block read; FAT remains disabled')
m['updated_at'] = proof['recorded_utc']
p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'README.md'
s = p.read_text(encoding='utf-8')
a = s.index('**当前已验收')
b = s.index('\n\n', a)
s = s[:a] + '**当前已验收 `arena-provider-20260910`（RAM）的模型池 ggml 缓冲区接入。** 两个张量共32KiB、8192项数据检查及释放归还通过；同镜像BLE真实配网/IP、30秒保持和网关5/5通过，客户端主动断开。未加载模型，USB文件存储正在接入。历史2/4线程图计算已通过；冷并发C++异常问题仍未解决，单线程和完整预热对照通过不代表通用修复。见 `evidence/arena-provider-20260910/acceptance.json`。' + s[b:]
p.write_text(s, encoding='utf-8')
note = '\n\n2026-09-10：app/k7arena经独立构建、实际TU宏/ELF检查和RAM真机通过32KiB/8192项set-get及释放；配套无线30秒、网关5/5通过。证据evidence/arena-provider-20260910/acceptance.json。USB只读MSC、FAT与模型同句柄读取仍是候选，不宣称已枚举U盘或加载权重。来源为当前主会话及候选交接哈希；官方日志须刷新后核对。\n'
with (R/'docs/代码日志对应表.md').open('a', encoding='utf-8') as f:
    f.write(note)
print('Arena finite acceptance and current device state recorded')
