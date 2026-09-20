"""Freeze filter firmware and stage an isolated silent digital-loopback build."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
old = json.loads((R/'private/audio-route-original-hashes.json').read_text())
for rel in list(old):
    p = R/rel
    if p.is_file(): old[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*')) + [R/'tools/build_audio_route.sh', R/'tools/sync_sdk.py']:
    if p.is_file(): old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
dest = R/'private/audio-marker-original-hashes.json'
assert not dest.exists()
dest.write_text(json.dumps(old))
for name in ['build_audio_route_vm.py','build_audio_route.sh','verify_audio_route_image.py',
             'reboot_audio_route_ram.py','uart_load_audio_route.py',
             'check_audio_route_affinity.py','start_audio_route_radio.py']:
    s = (R/'tools'/name).read_text().replace('audio-route','audio-marker').replace('audio_route','audio_marker')
    if name == 'build_audio_route_vm.py':
        marker = "paths.append('evidence/build/audio-loopback-20260910/verification.json')"
        assert marker in s
        s = s.replace(marker, marker+"\npaths.append('evidence/build/audio-route-20260910/verification.json')")
    if name == 'uart_load_audio_route.py':
        s = s.replace('audio-loopback-20260910','audio-route-20260910')
    target = R/'tools'/name.replace('audio_route','audio_marker')
    assert not target.exists()
    target.write_text(s,encoding='utf-8',newline='\n')
print('Independent audio-marker tools prepared')
