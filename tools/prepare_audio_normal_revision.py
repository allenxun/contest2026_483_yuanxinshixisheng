"""Prepare an independent codec normal-power experiment, with prior hashes."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-fifo-original-hashes.json').read_text())
for rel in list(old):
    p=R/rel
    if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_fifo.sh']:
    if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'private/audio-normal-original-hashes.json').write_text(json.dumps(old))
for name in ['build_audio_fifo_vm.py','build_audio_fifo.sh','verify_audio_fifo_image.py',
             'reboot_audio_fifo_ram.py','uart_load_audio_fifo.py','check_audio_fifo_affinity.py',
             'start_audio_fifo_radio.py']:
    s=(R/'tools'/name).read_text().replace('audio-fifo','audio-normal').replace('audio_fifo','audio_normal')
    if name=='build_audio_fifo_vm.py':
        s=s.replace("paths.append('evidence/build/audio-sound-20260910/verification.json')", "paths.append('evidence/build/audio-sound-20260910/verification.json')\npaths.append('evidence/build/audio-fifo-20260910/verification.json')")
    if name=='uart_load_audio_fifo.py':s=s.replace('audio-sound-20260910','audio-fifo-20260910')
    dest=R/'tools'/name.replace('audio_fifo','audio_normal')
    assert not dest.exists()
    dest.write_text(s,encoding='utf-8',newline='\n')
print('New normal-power experiment prepared, immutable prior outputs retained')
