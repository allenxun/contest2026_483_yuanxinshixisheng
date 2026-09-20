"""Record measured integration failure separately from source/build progress."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/voice-native-20260910'
run=sorted(E.glob('native-start-*'))[-1]
assert b'BSPASSERT:port.c-237' in (run/'shared.bin').read_bytes()
assert b'VOICE native_network=0' in (run/'probe.bin').read_bytes()
build=json.loads((R/'evidence/build/voice-native-20260910/verification.json').read_text())
state=dict(revision='voice-native-20260910',sha256=build['artifacts']['nuttx.bin']['sha256'],
    ram_boot=True,eight_idle_tasks=True,wifi_online=False,ble_operational=False,
    radio_fault=True,shared_service_ready=False,asr_integrated=False,tts_integrated=False,
    speech_provisioning_accepted=False,evidence=str(run.relative_to(R)).replace('\\','/'),
    failure='STOP before first OPEN caused firmware BSPASSERT port.c-237; commands 6 and 4 timed out')
(E/'device-state.json').write_text(json.dumps(state,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
m['current_device']=state
m['pending_firmware']=dict(revision='voice-cold-20260910',status='building',hardware_tested=False)
m['voice_network_backend'].update(adapter_compiled=True,adapter_revision='voice-native-20260910',
    hardware_tested=True,hardware_passed=False,detail='service startup assertion; no successful native scan')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'docs/代码日志对应表.md'
with p.open('a',encoding='utf-8') as f:
    f.write('\n2026-09-11 voice-native：真实原生编译、应用注册、ELF及RAM启动通过；BIN '+state['sha256']+
      '。wifi-service-start在首次OPEN之前发送STOP，模组BSPASSERT port.c-237，VoiceLink probe native_network=0，未执行扫描。失败原始输出保留于 '+state['evidence']+
      '。voice-cold独立修复冷态初始化，后续操作清理栅栏保留，尚未验收。官方日志本轮13文件/19740事件通过，仅覆盖该次采集。\n')
