"""Record native clock snapshots and the same-image finite wireless recovery."""
import datetime
import hashlib
import json
from pathlib import Path
import re
from verify_audio_preflight_image import verify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/audio-preflight-20260910'


def main():
    image = verify(ROOT / 'artifacts/audio-preflight-20260910')
    load = (OUT / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
    assert image['sha256'] in load and 'PASS: REAL K7 NSH' in load
    assert 'PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED' in load
    preflight = json.loads((OUT / 'preflight.json').read_text())
    assert preflight['passed'] and preflight['image']['sha256'] == image['sha256']
    assert preflight['raw_sha256'] == hashlib.sha256((OUT / 'preflight.bin').read_bytes()).hexdigest()
    assert json.loads((OUT / 'affinity-boot.json').read_text())['passed']
    assert json.loads((OUT / 'affinity-radio.json').read_text())['passed']
    ble = [json.loads(s) for s in (OUT / 'ble-wireless.jsonl').read_text().splitlines()]
    passed = [r for r in ble if r['event'] == 'PASS']
    assert len(passed) == 1
    ip = passed[0]['ip']
    assert any(r['event'] == 'hold_pass' and r['seconds'] == 30 and r['ip'] == ip for r in ble)
    assert ble[-1]['event'] == 'test_client_disconnected'
    gateway = json.loads((OUT / 'gateway.json').read_text())
    lines = [s for r in gateway['records'] for s in r['lines']]
    assert any('5 packets transmitted, 5 received, 0% packet loss' in s for s in lines)
    assert any('wifi_connected=1 ip=' + ip in s for s in lines)
    rejects = [int(re.search(r'rejected=(\d+)', s)[1]) for s in lines if 'WIFI AMSDU' in s]
    assert len(rejects) == 2
    state = dict(running_revision=OUT.name, boot='RAM', firmware_sha256=image['sha256'],
                 smp_cpus=8, audio_preflight_passed=True, audio_actual_rate_known=False,
                 audio_recording_tested=False, audio_playback_tested=False,
                 i2c_transactions=0, wifi_connected=True, ip=ip, gateway_ping='5/5',
                 wireless_hold_seconds=30, ble_service_running=True, ble_connected=False,
                 ble_disconnect='Test client intentionally disconnected',
                 receive_rejects_before=rejects[0], receive_rejects_after=rejects[1],
                 serial_observer_running=False, model_loaded=False, agent_deployed=False,
                 usb_host_started_this_boot=False, filesystem_mounted=False,
                 microphone_connection='User explicitly confirmed MIC connector',
                 emmc_written=False, evidence_directory=OUT.relative_to(ROOT).as_posix(),
                 limits=['Clock/IOC reads only; no codec access, frequency proof, record or playback',
                         'Finite wireless recovery only, not long stability or internet acceptance',
                         'USB storage previous-version results retained, not repeated in this boot',
                         'Cold concurrent C++ exception behavior remains unresolved'])
    filenames = ['ramload-progress.txt', 'preflight.bin', 'preflight.json', 'affinity-boot.json',
                 'affinity-radio.json', 'ble-wireless.jsonl', 'gateway.json']
    proof = dict(state=state, preflight=preflight,
                 recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 hashes={n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() for n in filenames})
    with (OUT / 'runtime-acceptance.json').open('x', encoding='utf-8') as file:
        json.dump(proof, file, ensure_ascii=False, indent=2)
    path = ROOT / 'project-manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    manifest['current_device'] = state
    manifest['last_verified_device'] = state.copy()
    manifest['pending_firmware'] = None
    manifest['updated_at'] = proof['recorded_utc']
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path = ROOT / 'README.md'
    text = path.read_text(encoding='utf-8')
    start = text.index('**当前运行 `usb-readonly-20260910`')
    end = text.index('\n\n', start)
    summary = ('**当前运行 `audio-preflight-20260910`（RAM）。** 音频CRU/IOC的8地址两份只读快照完成，'
               '没有I2C事务、codec初始化或录放音。真实Wi-Fi配网/IP、30秒保持与网关5/5通过，'
               f'本轮接收拒绝计数{rejects[0]}→{rejects[1]}；测试BLE客户端主动断开。'
               '本次未启动USB存储，旧版本只读结果保留。'
               '最新证据 `evidence/audio-preflight-20260910/runtime-acceptance.json`。')
    path.write_text(text[:start] + summary + text[end:], encoding='utf-8')
    note = ('\n\n2026-09-10：audio-preflight独立构建及实际ARM64编译单元/ELF/raw校验通过，'
            'RAM上板完成8个固定CRU/IOC地址两份快照，无寄存器写、I2C事务或录放音。'
            f'无线同镜像真实IP、BLE30秒/网关5/5，接收拒绝{rejects[0]}→{rejects[1]}。'
            '证据evidence/audio-preflight-20260910/runtime-acceptance.json；'
            'app/k7audio和配套tools归属本主会话，日志按最新manifest/官方校验为准。\n')
    for name in ['docs/代码日志对应表.md', 'docs/板载音频接入状态_20260910.md']:
        with (ROOT / name).open('a', encoding='utf-8') as file:
            file.write(note)
    print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    main()
