"""Integrate reviewed native shared radio backend, without ASR success claims."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
S=R/'private/radio-reviewed-stage-20260910'
m=json.loads((S/'assembly.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for rel,d in m['inputs'].items():assert sha(R/'app/k7radio'/rel)==d,rel
for rel,d in m['files'].items():assert sha(S/rel)==d,rel
for version,d in m['candidate_manifests'].items():
 p=R/'work-in-progress/parallel-model-reader-medium'/version
 assert sha(p/'outputs.json')==d
 for row in json.loads((p/'outputs.json').read_text()):assert sha(p/row.get('path',row.get('name')))==row['sha256']
old=json.loads((R/'private/audio-guard-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=sha(p)
for folder in ('app/k7sound','app/k7radio'):
 for p in (R/folder).rglob('*'):
  if p.is_file():old[p.relative_to(R).as_posix()]=sha(p)
for rel in ('tools/build_audio_guard.sh','tools/sync_sdk.py'):old[rel]=sha(R/rel)
dest=R/'private/voice-shared-original-hashes.json';assert not dest.exists();dest.write_text(json.dumps(old))
for name in ['build_audio_guard_vm.py','build_audio_guard.sh','verify_audio_guard_image.py','reboot_audio_guard_ram.py','uart_load_audio_guard.py','check_audio_guard_affinity.py','start_audio_guard_radio.py']:
 s=(R/'tools'/name).read_text().replace('audio-guard','voice-shared').replace('audio_guard','voice_shared')
 if name=='build_audio_guard_vm.py':
  mark="paths.append('evidence/build/audio-rx2-20260910/verification.json')";assert mark in s
  s=s.replace(mark,mark+"\npaths.append('evidence/build/audio-guard-20260910/verification.json')")
 if name=='uart_load_audio_guard.py':s=s.replace('audio-rx2-20260910','audio-guard-20260910')
 if name=='verify_audio_guard_image.py':s=s.replace("for line in ['CONFIG_EXAMPLES_K7SOUND=y'","for line in ['CONFIG_EXAMPLES_K7RADIO_SHARED=y','CONFIG_EXAMPLES_K7SOUND=y'")
 target=R/'tools'/name.replace('audio_guard','voice_shared');assert not target.exists();target.write_text(s,encoding='utf-8',newline='\n')
for rel,d in m['files'].items():
 assert rel.startswith('app/k7radio/')
 target=R/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((S/rel).read_bytes())
p=R/'board/kickpi_k7/configs/velavision_audio_sound_local/defconfig';s=p.read_text();assert 'CONFIG_EXAMPLES_K7RADIO_SHARED=y' not in s
p.write_text(s+'\nCONFIG_EXAMPLES_K7RADIO_SHARED=y\n',newline='\n')
p=R/'tools/sync_sdk.py';s=p.read_text();mark="'audio-rx2-20260910')";assert mark in s
p.write_text(s.replace(mark,"'audio-rx2-20260910', 'audio-guard-20260910')"),newline='\n')
E=R/'evidence/voice-shared-20260910';E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(assembly_sha256=sha(S/'assembly.json'),candidate_manifests=m['candidate_manifests'],asr_tts_integrated=False,hardware_tested=False,change='Shared native BLE/voice scan-connect ownership backend; legacy mutating radio CLI gated'),indent=2))
print('Shared radio backend integrated; not a completed voice firmware')
