"""Record the first real codec/SAI attempt without claiming acoustic success."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/audio-sound-20260910'
samples={}
for command in ('probe','tone','capture'):
    paths=list(E.glob('k7sound-'+command+'-*.json'))
    assert len(paths)==1
    item=json.loads(paths[0].read_text())
    raw=(E/item['raw']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item['raw_sha256'] and item['prompt']
    samples[command]=item
report=dict(revision='audio-sound-20260910',firmware_sha256=samples['probe']['image']['sha256'],
            codec_prepare_passed=True,platform_prepare_passed=True,sai_version='23073576',
            capture_passed=False,playback_passed=False,acoustic_validation=False,
            failure='FIFO accounting EPROTO (-71); TX prefill low field 4, RX one zero frame',
            cleanup_passed=True,observations=samples)
with (E/'first-attempt.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
p=R/'project-manifest.json'; m=json.loads(p.read_text(encoding='utf-8-sig'))
m['updated_at']=datetime.now(timezone.utc).isoformat()
m['current_device']=dict(running_revision=report['revision'],boot='RAM',firmware_sha256=report['firmware_sha256'],
 smp_cpus=8,audio_i2c_codec_read_passed=True,audio_codec_prepare_passed=True,
 audio_recording_tested=True,audio_playback_tested=True,audio_recording_passed=False,
 audio_playback_passed=False,wifi_connected=False,ble_connected=False,ble_service_running=False,
 wireless_verification='Radio not started after this RAM boot; previous audio-io-b Windows BLE DeviceNotFound preserved',
 emmc_written=False,serial_observer_running=False,evidence='evidence/audio-sound-20260910/first-attempt.json')
m['pending_firmware']=dict(revision='audio-fifo-20260910',state='FIFO four-field accounting fix under review')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text();start=s.index('**音频控制总线');end=s.index('\n\n',start)
s=s[:start]+'**音频电源、时钟与 codec 初始化已实板通过，录放音在 FIFO 计数检查处失败。** `audio-sound-20260910` 已 RAM 启动；真实 SAI 版本23073576，codec prepare/stop与平台恢复均返回0。首次播放与采集返回-71，正在按官方四字段求和方式修正；还没有完整录音或听感验收。当前无线服务未启动；上一镜像 Windows BLE 两次DeviceNotFound保留。见 `evidence/audio-sound-20260910/first-attempt.json`。'+s[end:]
p.write_text(s,encoding='utf-8')
for rel in ['docs/板载音频接入状态_20260910.md','docs/代码日志对应表.md']:
    with (R/rel).open('a',encoding='utf-8') as f:
        f.write('\n\n2026-09-10 18:42真实音频首轮：audio-sound镜像SHA256 '+report['firmware_sha256']+'已RAM启动，SAI23073576、codec初始化及停止/恢复成功。tone预填充和capture首帧后均返回-71，未取得完整录放音；四字段FIFO求和修正在独立audio-fifo版本准备。原始结果见evidence/audio-sound-20260910/first-attempt.json，失败未覆盖。\n')
print('Recorded actual failure and passed control-path portions separately')
