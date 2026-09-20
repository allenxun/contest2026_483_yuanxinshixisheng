"""Prepare independent microphone pad/MCLK/reference diagnostics."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-normal-original-hashes.json').read_text())
for rel in list(old):
    p=R/rel
    if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_normal.sh']:
    if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'private/audio-mic-original-hashes.json').write_text(json.dumps(old))
for name in ['build_audio_normal_vm.py','build_audio_normal.sh','verify_audio_normal_image.py',
             'reboot_audio_normal_ram.py','uart_load_audio_normal.py','check_audio_normal_affinity.py',
             'start_audio_normal_radio.py']:
    s=(R/'tools'/name).read_text().replace('audio-normal','audio-mic').replace('audio_normal','audio_mic')
    if name=='build_audio_normal_vm.py':
        s=s.replace("paths.append('evidence/build/audio-fifo-20260910/verification.json')", "paths.append('evidence/build/audio-fifo-20260910/verification.json')\npaths.append('evidence/build/audio-normal-20260910/verification.json')")
    if name=='uart_load_audio_normal.py':s=s.replace('audio-fifo-20260910','audio-normal-20260910')
    dest=R/'tools'/name.replace('audio_normal','audio_mic');assert not dest.exists()
    dest.write_text(s,encoding='utf-8',newline='\n')
print('Prepared audio-mic revision')
