"""Freeze predecessor and create independent cold-service fix build tools."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/voice-native-original-hashes.json').read_text())
for rel in list(old):
    p=R/rel
    if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for folder in ('app/k7radio','app/voicelink'):
    for p in (R/folder).rglob('*'):
        if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
p=R/'private/voice-cold-original-hashes.json'
assert not p.exists()
p.write_text(json.dumps(old))
for name in ['build_voice_native_vm.py','build_voice_native.sh','verify_voice_native_image.py','reboot_voice_native_ram.py','uart_load_voice_native.py','check_voice_native_affinity.py','start_voice_native_radio.py']:
    s=(R/'tools'/name).read_text().replace('voice-native','voice-cold').replace('voice_native','voice_cold')
    if name=='build_voice_native_vm.py':
        mark="paths.append('evidence/build/voice-shared-20260910/verification.json')"
        s=s.replace(mark,mark+"\npaths.append('evidence/build/voice-native-20260910/verification.json')")
    if name=='uart_load_voice_native.py':s=s.replace('audio-guard-20260910','voice-native-20260910')
    if name=='reboot_voice_native_ram.py':
        s=s.replace("s.write(b'k7radio wifi-disconnect\\r');s.flush()", "# Shared predecessor is faulted/offline: verify status before reboot; no legacy RF command.\n s.write(b'k7radio host-status\\r');s.flush()")
    if name=='start_voice_native_radio.py':s=s.replace("('shared', 'k7radio wifi-service-start', 15, b'nsh>')", "('shared', 'k7radio wifi-service-start', 15, b'WIFI shared start ret=0')")
    target=R/'tools'/name.replace('voice_native','voice_cold')
    assert not target.exists()
    target.write_text(s,encoding='utf-8',newline='\n')
