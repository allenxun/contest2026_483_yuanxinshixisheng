"""Freeze input revision; create independent filter build and loader tools."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
old = json.loads((R/'private/audio-input-original-hashes.json').read_text())
for rel in list(old):
    p = R/rel
    if p.is_file():
        old[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*')) + [R/'tools/build_audio_input.sh', R/'tools/sync_sdk.py']:
    if p.is_file():
        old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
target = R/'private/audio-filter-original-hashes.json'
assert not target.exists()
target.write_text(json.dumps(old))
for name in ['build_audio_input_vm.py', 'build_audio_input.sh',
             'verify_audio_input_image.py', 'reboot_audio_input_ram.py',
             'uart_load_audio_input.py', 'check_audio_input_affinity.py',
             'start_audio_input_radio.py']:
    s = (R/'tools'/name).read_text().replace('audio-input', 'audio-filter').replace('audio_input', 'audio_filter')
    if name == 'build_audio_input_vm.py':
        marker = "paths.append('evidence/build/audio-gain-20260910/verification.json')"
        assert marker in s
        s = s.replace(marker, marker + "\npaths.append('evidence/build/audio-input-20260910/verification.json')")
    if name == 'uart_load_audio_input.py':
        s = s.replace('audio-gain-20260910', 'audio-input-20260910')
    dest = R/'tools'/name.replace('audio_input', 'audio_filter')
    assert not dest.exists()
    dest.write_text(s, encoding='utf-8', newline='\n')
print('Independent audio-filter tools prepared')
