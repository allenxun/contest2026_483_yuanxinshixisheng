"""Create a separately traceable audio FIFO revision; no SDK or board access."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
oldrev, newrev = 'audio-sound-20260910', 'audio-fifo-20260910'
old = json.loads((R/'private/audio-sound-original-hashes.json').read_text())
for rel in list(old):
    p = R/rel
    if p.is_file():
        old[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in (R/'app/k7sound').rglob('*'):
    if p.is_file(): old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
(R/'private/audio-fifo-original-hashes.json').write_text(json.dumps(old), encoding='utf-8')
for name in ['build_audio_sound_vm.py','build_audio_sound.sh','verify_audio_sound_image.py',
             'reboot_audio_sound_ram.py','uart_load_audio_sound.py','check_audio_sound_affinity.py',
             'start_audio_sound_radio.py']:
    s = (R/'tools'/name).read_text()
    s = s.replace(oldrev, newrev).replace('audio-sound-stage','audio-fifo-stage')
    s = s.replace('audio-sound-original-hashes','audio-fifo-original-hashes')
    s = s.replace('build_audio_sound.sh','build_audio_fifo.sh').replace('verify_audio_sound_image','verify_audio_fifo_image')
    # Reuse only the already accepted build cache; keep immutable outputs separate.
    if name == 'build_audio_sound_vm.py':
        s = s.replace("paths.append('evidence/build/audio-io-20260910/verification.json')",
                      "paths.append('evidence/build/audio-io-20260910/verification.json')\npaths.append('evidence/build/audio-sound-20260910/verification.json')")
    if name == 'uart_load_audio_sound.py':
        s = s.replace('audio-io-b-20260910', oldrev)
    dest = R/'tools'/name.replace('audio_sound','audio_fifo')
    if dest.exists(): raise RuntimeError('Refuse to replace '+str(dest))
    dest.write_text(s, encoding='utf-8', newline='\n')
print('Prepared separate audio-fifo revision, build cache remains audio_sound')
