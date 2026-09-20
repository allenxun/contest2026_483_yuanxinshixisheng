import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
EVIDENCE = PROJECT / 'evidence/speaker-csr-fix-20260913'
ARTIFACTS = PROJECT / 'artifacts/speaker-csr-fix-20260913'
build = json.loads((EVIDENCE / 'result.json').read_text())
assert build['build_exit'] == 0 and build['sync_audit_exit'] == 0
assert all(t['exit_code'] == (0 if t['variant'] == 'fixed' else -6) for t in build['tests'])
assert json.loads((EVIDENCE / 'unwind.json').read_text())['passed']
for name, info in build['artifacts'].items():
    raw = (ARTIFACTS / name).read_bytes()
    assert len(raw) == info['bytes'] and hashlib.sha256(raw).hexdigest() == info['sha256']
tone = (EVIDENCE / 'audio-crosscheck-tone-20260913-173359.log').read_bytes()
assert b'TXCR=00400fff' in tone and b'SOUND result=0' in tone and b'nsh>' in tone
boot = (EVIDENCE / 'ram-final-20260913-173248.log').read_bytes()
for crc in (b'12d5ac66', b'b20f998f', b'2af64aa7', b'9f4af07d'):
    assert crc in boot
record = {
    'revision': 'speaker-csr-fix-20260913',
    'firmware_sha256': build['artifacts']['nuttx.bin']['sha256'],
    'host_regression_passed': True, 'arm64_build_passed': True,
    'ram_crc_verified': True, 'nsh_verified_by_followup': True,
    'initial_boot_script_timed_out': True,
    'playback_register_verified': True,
    'audible_tone_confirmed_by_user': True,
    'speech_replay_clear_confirmed_by_user': True,
    'repeated_phrase_user_confirmed_spoken_multiple_times': True,
    'wake_recognition_passed': False, 'voice_wifi_provisioning_passed': False,
    'flash_written': False, 'gimbal_started': False,
    'next_request': 'User now selects hello-prefix wake plus start-network phrase; separate firmware in progress',
    'limitations': ['No long-term audio reliability claim',
                    'Serial output has dropped fragments; timeout retained as failed script result',
                    'No phone BLE connection or Wi-Fi connection validation in this run'],
}
(EVIDENCE / 'acceptance.json').write_text(json.dumps(record, indent=2) + '\n')
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in EVIDENCE.iterdir() if p.is_file() and p.name != 'sha256.json'}
(EVIDENCE / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('PASS speaker component acceptance; voice provisioning remains unverified')
