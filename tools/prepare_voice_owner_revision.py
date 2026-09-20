"""Create independent persistent-owner revision from the measured cold build."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/voice-cold-original-hashes.json').read_text())
for rel in list(old):
    p=R/rel
    if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for folder in ('app/k7radio','app/voicelink'):
    for p in (R/folder).rglob('*'):
        if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
p=R/'private/voice-owner-original-hashes.json';assert not p.exists();p.write_text(json.dumps(old))
for name in ['build_voice_cold_vm.py','build_voice_cold.sh','verify_voice_cold_image.py','reboot_voice_cold_ram.py','uart_load_voice_cold.py','check_voice_cold_affinity.py','start_voice_cold_radio.py']:
    s=(R/'tools'/name).read_text().replace('voice-cold','voice-owner').replace('voice_cold','voice_owner')
    if name=='build_voice_cold_vm.py':
        mark="paths.append('evidence/build/voice-native-20260910/verification.json')"
        s=s.replace(mark,mark+"\npaths.append('evidence/build/voice-cold-20260910/verification.json')")
    if name=='uart_load_voice_cold.py':s=s.replace('voice-native-20260910','voice-cold-20260910')
    target=R/'tools'/name.replace('voice_cold','voice_owner');assert not target.exists()
    target.write_text(s,encoding='utf-8',newline='\n')
