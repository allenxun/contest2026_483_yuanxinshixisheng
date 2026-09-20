"""Record raw internal-loopback evidence without claiming correct audio data."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/audio-loopback-20260910'
raw_path = E / 'k7sound-loopback-20260910-212123.bin'
raw = raw_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '0d7708fb92553cef9403a10c1d7860f1d31344da86567f202760a6d93adb017f'
assert b'frames=128 tx_queued=270 polls=4428 stop=0 restore=0 amp=0 held=0' in raw
assert b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0 amp_low=1' in raw
assert 'PASS: REAL K7 NSH' in (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
sha = hashlib.sha256((R / 'artifacts/audio-loopback-20260910/nuttx.bin').read_bytes()).hexdigest()
assert sha == '63735a3140e3992ed11ff7f8bfbae62c61d5cee50b4107ad4f6358348b1dc913'
report = dict(revision='audio-loopback-20260910', firmware_sha256=sha,
              raw_file=raw_path.name, raw_sha256=hashlib.sha256(raw).hexdigest(),
              frames=128, elapsed_us=8063, transport_completed=True,
              stop_restore_passed=True, amplifier_enabled=False,
              correct_marker_stream=False, periodic_zero_samples_unresolved=True,
              finding='Internal silent loopback reproduces periodic zero pairs; microphone/codec capture is not required for reproduction. Exact cause unresolved.',
              human_listening_performed=False, clean_audio_accepted=False)
(E / 'runtime-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
p = R / 'project-manifest.json'
d = json.loads(p.read_text(encoding='utf-8'))
d['updated_at'] = datetime.now(timezone.utc).isoformat()
d['current_device'] = dict(firmware=report['revision'], sha256=sha, console='NSH',
                           audio_stopped=True, amp_low=True, radio_started=False,
                           wifi_connected=False, ble_connected=False,
                           serial_observer_running=False)
d['pending_firmware'] = None
d['latest_audio_checkpoint'] = dict(revision=report['revision'], firmware_sha256=sha,
    report='evidence/audio-loopback-20260910/runtime-results.json',
    finding=report['finding'], clean_audio_accepted=False)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print('Recorded internal-loopback reproduction; no correct-audio acceptance')
