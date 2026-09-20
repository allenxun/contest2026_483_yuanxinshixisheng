"""Prepare a new audio I/O build without replacing the accepted preflight."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
REV = 'audio-io-20260910'
previous = json.loads((R/'evidence/build/audio-preflight-20260910/verification.json').read_text())
assert previous['build_exit_code'] == 0
for name, item in previous['artifacts'].items():
    p = R/'artifacts/audio-preflight-20260910'/name
    assert hashlib.sha256(p.read_bytes()).hexdigest() == item['sha256']
baseline = json.loads((R/'private/usb-readonly-original-hashes.json').read_text(encoding='utf-8-sig'))
baseline.update(previous['sources'])
for rel in ['tools/sync_sdk.py']:
    baseline[rel] = hashlib.sha256((R/rel).read_bytes()).hexdigest()
(R/'private/audio-io-original-hashes.json').write_text(json.dumps(baseline, indent=2))
profile = R/'board/kickpi_k7/configs/velavision_audio_io_local/defconfig'
profile.parent.mkdir(parents=True, exist_ok=True)
profile.write_text((R/'board/kickpi_k7/configs/velavision_audio_preflight_local/defconfig').read_text()+'\nCONFIG_EXAMPLES_K7AUDIOHW=y\n')
for name in ['build_audio_preflight.sh', 'build_audio_preflight_vm.py']:
    s = (R/'tools'/name).read_text()
    s = s.replace('audio-preflight', 'audio-io').replace('audio_preflight', 'audio_io')
    if name.endswith('.py'):
        s = s.replace('private/usb-readonly-original-hashes.json', 'private/audio-io-original-hashes.json')
        needle = "paths=list(dict.fromkeys(p.replace('\\\\','/') for p in paths))"
        assert needle in s
        s = s.replace(needle, "paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7audiohw').iterdir()) if p.is_file()]\n" + needle)
        s = s.replace("['CONFIG_EXAMPLES_K7AUDIO=y',", "['CONFIG_EXAMPLES_K7AUDIOHW=y','CONFIG_EXAMPLES_K7AUDIO=y',")
    dest = R/'tools'/name.replace('audio_preflight', 'audio_io')
    if dest.exists():
        assert dest.read_text() == s
    else:
        dest.write_text(s, newline='\n')
for name in ['verify_audio_preflight_image.py', 'reboot_audio_preflight_ram.py',
             'uart_load_audio_preflight.py', 'check_audio_preflight_affinity.py',
             'start_audio_preflight_radio.py']:
    s = (R/'tools'/name).read_text().replace('audio-preflight', 'audio-io').replace('audio_preflight', 'audio_io')
    if name.startswith('uart_load'):
        s = s.replace('usb-readonly-20260910', 'audio-preflight-20260910')
    if name.startswith('verify'):
        s = s.replace("['CONFIG_EXAMPLES_K7AUDIO=y',", "['CONFIG_EXAMPLES_K7AUDIOHW=y','CONFIG_EXAMPLES_K7AUDIO=y',")
    dest = R/'tools'/name.replace('audio_preflight', 'audio_io')
    if dest.exists():
        assert dest.read_text() == s
    else:
        dest.write_text(s, newline='\n')
print('Audio I/O profile and RAM helpers prepared; no device operation')
