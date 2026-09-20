"""Freeze preceding formal version before integrating input-only experiments."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-gain-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_gain.sh',R/'tools/sync_sdk.py']:
 if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
target=R/'private/audio-input-original-hashes.json';assert not target.exists()
target.write_text(json.dumps(old))
for name in ['build_audio_gain_vm.py','build_audio_gain.sh','verify_audio_gain_image.py','reboot_audio_gain_ram.py','uart_load_audio_gain.py','check_audio_gain_affinity.py','start_audio_gain_radio.py']:
 s=(R/'tools'/name).read_text().replace('audio-gain','audio-input').replace('audio_gain','audio_input')
 if name=='build_audio_gain_vm.py':s=s.replace("paths.append('evidence/build/audio-reset-20260910/verification.json')", "paths.append('evidence/build/audio-reset-20260910/verification.json')\npaths.append('evidence/build/audio-gain-20260910/verification.json')")
 if name=='uart_load_audio_gain.py':s=s.replace('audio-reset-20260910','audio-gain-20260910')
 dest=R/'tools'/name.replace('audio_gain','audio_input');assert not dest.exists()
 dest.write_text(s,encoding='utf-8',newline='\n')
print('Independent audio-input tools prepared')
