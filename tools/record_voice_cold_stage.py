"""Record observed cold-service startup and missing persistent workers."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/voice-cold-20260910'
run=sorted(E.glob('native-start-*'))[-1];status=sorted(E.glob('service-status-*'))[-1]
assert b'WIFI shared start ret=0' in (run/'shared.bin').read_bytes()
assert b'VOICE scan timeout' in (run/'scan.bin').read_bytes()
assert b'host_mode=1 fault=0' in (status/'host.bin').read_bytes()
build=json.loads((R/'evidence/build/voice-cold-20260910/verification.json').read_text())
state=dict(revision='voice-cold-20260910',sha256=build['artifacts']['nuttx.bin']['sha256'],
 ram_boot=True,radio_fault=False,wifi_online=False,shared_ready_pointer=True,
 shared_workers_present=False,native_scan_passed=False,asr_integrated=False,tts_integrated=False,
 evidence=str(run.relative_to(R)),task_evidence=str(status.relative_to(R)),
 detail='scan accepted then 35-second timeout; task snapshot lacks service pthreads after launcher task exit')
(E/'device-state.json').write_text(json.dumps(state,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
m['last_runtime_checkpoint']=state
m['current_device']=dict(state='U-Boot RAM loading',pending_revision='voice-owner-20260910',wifi_online=False)
m['pending_firmware']=dict(revision='voice-owner-20260910',status='RAM_LOADING',hardware_tested=False)
m['native_asr_runtime']=dict(env_translation_unit_compiled=True,common_linked=False,model_run=False,
 evidence='evidence/native-ort-env-compile3-20260911',object_sha256='bd96c2a71d5b291064ed95bc0e005f0ffb2bde5d684376c1b7c255b05baa8b2e')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n2026-09-11 voice-cold：冷态服务启动和probe通过，scan接受后35秒超时；真实ps无后台pthread，host fault=0，Wi-Fi离线。独立voice-owner将pthread移入持久任务组，编译首轮仅缩进Werror失败，保存完整日志及hash后修复；现RAM加载中。原生ORT Env v2实际ARM64单源编译通过，common仍有3个源编译缺口，不能称运行库链接或ASR成功。\n')
