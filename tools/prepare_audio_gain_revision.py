"""Freeze current input hashes and create independent playback gain build tools."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
old = json.loads((R/'private/audio-reset-original-hashes.json').read_text())
for rel in list(old):
    p = R/rel
    if p.is_file(): old[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*')) + [R/'tools/build_audio_reset.sh', R/'tools/sync_sdk.py']:
    if p.is_file(): old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
target = R/'private/audio-gain-original-hashes.json'
assert not target.exists()
target.write_text(json.dumps(old))
for name in ['build_audio_reset_vm.py','build_audio_reset.sh','verify_audio_reset_image.py','reboot_audio_reset_ram.py','uart_load_audio_reset.py','check_audio_reset_affinity.py','start_audio_reset_radio.py']:
    s = (R/'tools'/name).read_text().replace('audio-reset','audio-gain').replace('audio_reset','audio_gain')
    if name == 'build_audio_reset_vm.py':
        s = s.replace("paths.append('evidence/build/audio-rxtrace-20260910/verification.json')", "paths.append('evidence/build/audio-rxtrace-20260910/verification.json')\npaths.append('evidence/build/audio-reset-20260910/verification.json')")
    if name == 'uart_load_audio_reset.py': s = s.replace('audio-rxtrace-20260910','audio-reset-20260910')
    dest = R/'tools'/name.replace('audio_reset','audio_gain')
    assert not dest.exists()
    dest.write_text(s, encoding='utf-8', newline='\n')
print('Independent audio-gain tools prepared; firmware not built or loaded')
