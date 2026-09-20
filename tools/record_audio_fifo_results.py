"""Record actual FIFO progress and explicit user speaker confirmation."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]; E=R/'evidence/audio-fifo-20260910'
observations=[]
for p in sorted(E.glob('k7sound-*.json')):
    item=json.loads(p.read_text());raw=(E/item['raw']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item['raw_sha256'] and item['prompt']
    observations.append(item)
result=dict(revision='audio-fifo-20260910',firmware_sha256='741c9b2f8b23f6f247da865201061343cbe36b924404457f82f1d6630ce14020',
 fifo_sum4_hardware_passed=True,tx_prefill_raw='00104104',tx_prefill_words=16,
 tone_transfer_passed=True,speaker_confirmation=dict(source='User reply in current conversation',
 reply='听到了三声',scope='Three low-level 200ms test tones; not intelligible recorded voice playback'),
 capture_transfer_passed=True,capture_frames=48000,capture_seconds=3,
 microphone_audio_passed=False,capture_all_zero=True,
 zero_capture='evidence/audio-fifo-20260910/zero-capture/extraction.json',
 observations=observations,emmc_written=False)
with (E/'runtime-results.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
p=R/'project-manifest.json';m=json.loads(p.read_text())
m['updated_at']=datetime.now(timezone.utc).isoformat()
m['latest_audio_checkpoint']=result|{'observations':'evidence/audio-fifo-20260910/runtime-results.json'}
m['current_device']=dict(state='U-Boot RAM loading',running_revision=None,
 last_loaded_revision='audio-fifo-20260910',wifi_connected=False,ble_connected=False,
 serial_observer_running=True,serial_owner='uart_load_audio_normal.py',emmc_written=False)
m['pending_firmware']=dict(revision='audio-normal-20260910',state='Compiled and ELF verified, RAM load in progress',
 sha256='e625c8aee64b166f2e192485d4a50060a4f4d4f28aa85e650a57cc9fa816eeaf')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text();start=s.index('**音频电源');end=s.index('\n\n',start)
s=s[:start]+'**喇叭短音已获用户实听确认，麦克风仍在排查全零样本。** `audio-fifo-20260910` 修正官方四字段FIFO汇总后，3200帧播放和48000帧/3秒采集均返回0；用户确认三声短音可听到。但麦克风全部样本为零，不能验收录音。原始零样本WAV已保存；正常功耗对照版 `audio-normal-20260910` 已编译通过，正在RAM加载。见 `evidence/audio-fifo-20260910/runtime-results.json`。'+s[end:]
p.write_text(s,encoding='utf-8')
for rel in ['docs/板载音频接入状态_20260910.md','docs/代码日志对应表.md']:
    with (R/rel).open('a',encoding='utf-8') as f:
        f.write('\n\n2026-09-10 18:54：audio-fifo镜像 '+result['firmware_sha256']+' 真机FIFO首读00104104，四字段总16，3200帧短音传输0，用户确认三声可听到；48000帧/3秒采集也返回0但全部为零，录音未通过。数据和用户确认分别保存在evidence/audio-fifo-20260910/runtime-results.json，零样本原始WAV在zero-capture/。下一audio-normal对照只改codec正常功耗并加启动前诊断；可选原始PCM缓冲回放只由显式replay启用，未实测。\n')
print('Speaker confirmation recorded; zero capture explicitly remains failed')
