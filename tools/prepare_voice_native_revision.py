"""Register native VoiceLink network integration, without simulated ASR/TTS."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((R/'private/voice-shared-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=sha(p)
for folder in ('app/k7sound','app/k7radio','app/voicelink'):
 for p in (R/folder).rglob('*'):
  if p.is_file():old[p.relative_to(R).as_posix()]=sha(p)
for rel in ('tools/build_voice_shared.sh','tools/sync_sdk.py'):old[rel]=sha(R/rel)
p=R/'private/voice-native-original-hashes.json';assert not p.exists();p.write_text(json.dumps(old))
for name in ['build_voice_shared_vm.py','build_voice_shared.sh','verify_voice_shared_image.py','reboot_voice_shared_ram.py','uart_load_voice_shared.py','check_voice_shared_affinity.py']:
 s=(R/'tools'/name).read_text().replace('voice-shared','voice-native').replace('voice_shared','voice_native')
 if name=='build_voice_shared_vm.py':
  a=s.index('# Exact prior failed staging');b=s.index("(STAGE/'staging.json')",a);s=s[:a]+s[b:]
  mark="paths.append('evidence/build/audio-guard-20260910/verification.json')";assert mark in s
  s=s.replace(mark,mark+"\npaths.append('evidence/build/voice-shared-20260910/verification.json')")
  s=s.replace('evidence/sync/voice-native-attempt2.json','evidence/sync/voice-shared-attempt2.json')
  mark="paths=list(dict.fromkeys(p.replace('\\\\','/') for p in paths))";assert mark in s
  s=s.replace(mark,"paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/voicelink').rglob('*')) if p.is_file()]\n"+mark)
  s=s.replace("for x in ['CONFIG_EXAMPLES_K7RADIO_SHARED=y'","for x in ['CONFIG_EXAMPLES_K7VOICE=y','CONFIG_EXAMPLES_K7RADIO_SHARED=y'")
 if name=='verify_voice_shared_image.py':s=s.replace("for line in ['CONFIG_EXAMPLES_K7RADIO_SHARED=y'","for line in ['CONFIG_EXAMPLES_K7VOICE=y','CONFIG_EXAMPLES_K7RADIO_SHARED=y'")
 if name=='uart_load_voice_shared.py':s=s.replace('audio-guard-20260910','audio-guard-20260910') # current loaded predecessor
 target=R/'tools'/name.replace('voice_shared','voice_native');assert not target.exists();target.write_text(s,encoding='utf-8',newline='\n')
C=R/'work-in-progress/parallel-model-reader-medium/voice-native-adapter-v1'
want='dfc153b4fada22bfc84df2a8d7264f4d566844d3657ff7183da2f63f08fe5dbc'
assert sha(C/'outputs.json')==want
for row in json.loads((C/'outputs.json').read_text()):assert sha(C/row.get('path',row.get('name')))==row['sha256']
for row in json.loads((C/'after-inputs.json').read_text()):assert sha(R/row['path'])==row['sha256'],row['path']
for name in ('voice_wifi_adapter.cpp','voice_wifi_adapter.hpp'):(R/'app/voicelink/src'/name).write_bytes((C/'candidate'/name).read_bytes())
p=R/'board/kickpi_k7/configs/velavision_audio_sound_local/defconfig';s=p.read_text();assert 'CONFIG_EXAMPLES_K7VOICE=y' not in s;p.write_text(s+'\nCONFIG_EXAMPLES_K7VOICE=y\n',newline='\n')
E=R/'evidence/voice-native-20260910';E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(adapter_manifest_sha256=want,asr_tts_integrated=False,hardware_tested=False),indent=2))
print('Native adapter integrated; application registration required')
