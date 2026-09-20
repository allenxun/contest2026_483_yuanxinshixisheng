"""Record version-specific observations; transport completion is not acoustic success."""
import hashlib, json, re
from pathlib import Path
R = Path(__file__).resolve().parents[1]
E = R/'evidence/audio-reset-20260910'
def evidence(stem):
    j = json.loads((E/(stem+'.json')).read_text())
    raw = (E/j['raw']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == j['raw_sha256']
    assert j['image']['sha256'] == '4b4ee06366ff7cb9d3959ec6f16dc206bf7474cf4466e596f891547261aa925b'
    return dict(report=stem+'.json', raw_sha256=j['raw_sha256'], prompt=j['prompt'],
                result_lines=re.findall(r'SOUND (?:result|pio|reset result|start_clear result|experiment)[^\r\n]*', raw.decode(errors='replace')))
report = dict(revision='audio-reset-20260910', firmware_sha256='4b4ee06366ff7cb9d3959ec6f16dc206bf7474cf4466e596f891547261aa925b',
    clear=evidence('k7sound-capture-clear-20260910-195958'),
    reset=evidence('k7sound-capture-reset-20260910-200121'),
    clockwait=evidence('k7sound-capture-clockwait-20260910-200129'),
    capture=evidence('k7sound-capture-48000-20260910-200557'),
    replay=evidence('k7sound-replay-20260910-200608'),
    dump=evidence('k7sound-dump-20260910-200625'),
    tones=[evidence('k7sound-tone-20260910-'+stamp) for stamp in ['200719','200721','200722']],
    human_feedback=dict(voice_replay='没有听到声音', tone='三声都听到了', source='Actual user replies in current primary task'),
    extraction='voice-replay-first/extraction.json',
    findings=['CLK/FS-off start clear timed out; held fault recovered by verified same-image RAM reboot.',
              'H/M reset and 20us clock wait completed but did not remove periodic zero samples.',
              '48000-pair capture and raw board-speaker replay completed; user heard no voice.',
              'Three same-image short tones completed and user heard all three.'],
    microphone_audio_passed=False, voice_playback_passed=False,
    current_device=dict(firmware='audio-reset-20260910', console='NSH', audio_stopped=True, amp_low=True,
                        wireless_started=False, serial_observer_running=False))
(E/'runtime-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'project-manifest.json'
m = json.loads(p.read_text(encoding='utf-8'))
m['latest_audio_checkpoint'] = {k: report[k] for k in ['revision','firmware_sha256','microphone_audio_passed','voice_playback_passed']}
m['latest_audio_checkpoint']['report'] = 'evidence/audio-reset-20260910/runtime-results.json'
m['latest_audio_checkpoint']['finding'] = 'Board raw replay completed but user heard no voice; same-image three tones audible; periodic zeros unresolved'
m['current_device'] = report['current_device']
m['pending_firmware'] = dict(revision='audio-gain-20260910', status='preparing bounded playback gain only; not built or loaded')
p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
text = '\n\n2026-09-10 20:07实际：audio-reset已RAM启动。CLK/FS关闭时start-clear超时并锁住；同镜像RAM重载恢复。H/M复位与20us时钟等待均执行成功但每4帧3零未消失。MIC采集48000对后由板载喇叭原样回放，两端传输/停止返回0，用户明确没有听到声音；随后同版本三次短音用户全部听到。不能验收语音回放。原始PCM及实听结果见evidence/audio-reset-20260910/runtime-results.json；无线未启动，无eMMC写入。下一版仅准备可控DAC音量档位，默认与原始PCM保持不变。\n'
for rel in ['docs/板载音频接入状态_20260910.md','docs/代码日志对应表.md']:
    with (R/rel).open('a', encoding='utf-8') as f: f.write(text)
p=R/'README.md';s=p.read_text(encoding='utf-8')
start=s.index('**喇叭短音已获用户实听确认')
end=s.index('\n\n', start)
s=s[:start]+'**板载短音可听，麦克风已有变化数据，但录音回放未通过。** `audio-reset-20260910` 真机3秒采集与原始回放均完成，用户没有听到回放语音；随后三声短音全部可听。录音每4帧仍有3帧为零，复位与时钟等待对照未修复。原始数据与实听结果见 `evidence/audio-reset-20260910/runtime-results.json`；下一版仅准备可控播放音量档位。'+s[end:]
p.write_text(s, encoding='utf-8')
print('Actual record/replay failure and audible-tone control saved')
