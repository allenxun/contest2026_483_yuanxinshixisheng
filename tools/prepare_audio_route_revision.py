"""Freeze filter firmware and stage an isolated silent digital-loopback build."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
old = json.loads((R/'private/audio-loopback-original-hashes.json').read_text())
for rel in list(old):
    p = R/rel
    if p.is_file(): old[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*')) + [R/'tools/build_audio_loopback.sh', R/'tools/sync_sdk.py']:
    if p.is_file(): old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
dest = R/'private/audio-route-original-hashes.json'
assert not dest.exists()
dest.write_text(json.dumps(old))
for name in ['build_audio_loopback_vm.py','build_audio_loopback.sh','verify_audio_loopback_image.py',
             'reboot_audio_loopback_ram.py','uart_load_audio_loopback.py',
             'check_audio_loopback_affinity.py','start_audio_loopback_radio.py']:
    s = (R/'tools'/name).read_text().replace('audio-loopback','audio-route').replace('audio_loopback','audio_route')
    if name == 'build_audio_loopback_vm.py':
        marker = "paths.append('evidence/build/audio-filter-20260910/verification.json')"
        assert marker in s
        s = s.replace(marker, marker+"\npaths.append('evidence/build/audio-loopback-20260910/verification.json')")
    if name == 'uart_load_audio_loopback.py':
        s = s.replace('audio-filter-20260910','audio-loopback-20260910')
    target = R/'tools'/name.replace('audio_loopback','audio_route')
    assert not target.exists()
    target.write_text(s,encoding='utf-8',newline='\n')
print('Independent audio-route tools prepared')
