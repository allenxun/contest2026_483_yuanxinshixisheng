import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-rxtrace-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_rxtrace.sh']:
 if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'private/audio-reset-original-hashes.json').write_text(json.dumps(old))
for name in ['build_audio_rxtrace_vm.py','build_audio_rxtrace.sh','verify_audio_rxtrace_image.py','reboot_audio_rxtrace_ram.py','uart_load_audio_rxtrace.py','check_audio_rxtrace_affinity.py','start_audio_rxtrace_radio.py']:
 s=(R/'tools'/name).read_text().replace('audio-rxtrace','audio-reset').replace('audio_rxtrace','audio_reset')
 if name=='build_audio_rxtrace_vm.py':s=s.replace("paths.append('evidence/build/audio-mic-20260910/verification.json')", "paths.append('evidence/build/audio-mic-20260910/verification.json')\npaths.append('evidence/build/audio-rxtrace-20260910/verification.json')")
 if name=='uart_load_audio_rxtrace.py':s=s.replace('audio-mic-20260910','audio-rxtrace-20260910')
 dest=R/'tools'/name.replace('audio_rxtrace','audio_reset');assert not dest.exists()
 dest.write_text(s,encoding='utf-8',newline='\n')
print('Prepared independent audio-reset revision')
