"""Record actual native scan acceptance and source-only ORT compile gates."""
import hashlib,json,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/voice-owner-20260910'
run=sorted(E.glob('native-start-*'))[-1];life=sorted(E.glob('lifetime-*'))[-1]
assert all(x['passed'] for x in json.loads((run/'result.json').read_text())['stages'])
rows=json.loads((life/'result.json').read_text())['results'];assert all(x['passed'] for x in rows)
build=json.loads((R/'evidence/build/voice-owner-20260910/verification.json').read_text())
state=dict(revision='voice-owner-20260910',sha256=build['artifacts']['nuttx.bin']['sha256'],
 ram_boot=True,radio_fault=False,shared_service_ready=True,persistent_task_observed=True,
 wifi_online=False,ble_service_started=True,ble_client_tested=False,
 native_scans_passed=3,scans=[x for x in rows if x['stage'].startswith('scan')],
 asr_integrated=False,tts_integrated=False,speech_provisioning_accepted=False,
 evidence=[str(run.relative_to(R)),str(life.relative_to(R))])
(E/'device-state.json').write_text(json.dumps(state,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
m['current_device']=state;m['pending_firmware']=None
m['voice_network_backend']=dict(revision=state['revision'],compiled=True,hardware_tested=True,
 scan_passed=True,connection_on_this_revision_tested=False,speech_tested=False)
base=R/'evidence/native-ort-common-compile1-20260911'
fix=R/'evidence/native-ort-common-compile2-20260911'
first=json.loads((base/'result.json').read_text())['results']
second={x['index']:x for x in json.loads((fix/'result.json').read_text())['results']}
objects=[]
for index,row in enumerate(first):
 if 'skipped' in row:
  file=R/'evidence/native-ort-env-compile3-20260911/env-gate.o'
 else:
  final=second.get(index,row);assert final['exit_code']==0
  file=(fix if index in second else base)/(str(index)+'.o')
 data=file.read_bytes();assert data[:5]==b'\x7fELF\x02' and struct.unpack_from('<HH',data,16)==(1,183)
 objects.append(dict(source=row['source'],object=str(file.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
assert len(objects)==21
report=dict(source_count=21,all_translation_units_compiled=True,objects=objects,
 static_dependencies_built=False,linked=False,model_loaded=False,hardware_inference_tested=False)
(fix/'combined-source-gate.json').write_text(json.dumps(report,indent=2)+'\n')
m['native_asr_runtime']=dict(common_translation_units=21,all_common_sources_compiled=True,
 common_linked=False,asr_model_run=False,tts_model_run=False,evidence=str(fix.relative_to(R)))
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n2026-09-11 voice-owner：BIN '+state['sha256']+' RAM启动通过，独立k7_wifi_svc持久任务在命令退出后仍存在，三次真实VoiceLink接口扫描通过；后两次2.922/2.938秒，各64项含Lansee，host fault=0，Wi-Fi未连接，BLE仅服务启动未测客户端。ASR/TTS未集成。ORT common共21个源全部实际编译成AArch64对象，组合证据记录每个对象哈希；静态依赖链接和模型运行未完成。\n')
