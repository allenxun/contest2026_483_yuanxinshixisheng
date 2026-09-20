"""Record the exact bounded filter experiment, not an audio-quality acceptance."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R/'evidence/audio-filter-20260910'
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
image = hashlib.sha256((R/'artifacts/audio-filter-20260910/nuttx.bin').read_bytes()).hexdigest()
assert image == '8c8f46b4a354be34e6ff8d3d430cb81f70d583a8a0f929aeed0047ae5f1585fc'
rows = []
for name in ['k7sound-capture-pga24-20260910-205820',
             'k7sound-replay-ma4-max-20260910-205830',
             'k7sound-dump-20260910-205840']:
    d = json.loads((E/(name+'.json')).read_text())
    raw = (E/d['raw']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == d['raw_sha256']
    assert d['image']['sha256'] == image and d['prompt']
    if 'dump' not in name:
        assert b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0 amp_low=1' in raw
        assert b'frames=3200' in raw
    if 'replay-ma4' in name:
        assert b'SOUND filter=1 result=0 frames=3200 saturations=0' in raw
    rows.append(d)
report = dict(revision='audio-filter-20260910', sha256=image, operations=rows,
              bounded_capture_and_ma4_playback_passed=True, duration_seconds=0.2,
              hp80_board_tested=False, raw_capture_dump_saved=True,
              repeated_loud_playback=False, human_listening_performed=False,
              microphone_audio_passed=False, voice_playback_passed=False,
              periodic_zero_samples_unresolved=True,
              host_asr_result='All three PGA24 inputs produce differing text; no reliable wake/provisioning recognition acceptance',
              host_asr_evidence='pga24-host-asr/recognized.json')
(E/'runtime-results.json').write_text(json.dumps(report, indent=2))
p = R/'project-manifest.json'
d = json.loads(p.read_text(encoding='utf-8'))
d['updated_at'] = datetime.now(timezone.utc).isoformat()
d['current_device'] = dict(firmware='audio-filter-20260910', sha256=image,
                           console='NSH', audio_stopped=True, amp_low=True,
                           wireless_state='restoration in progress, not yet confirmed online')
d['pending_firmware'] = None
d['latest_audio_checkpoint'] = dict(revision=report['revision'], firmware_sha256=image,
    report='evidence/audio-filter-20260910/runtime-results.json',
    finding='MA4 short board path passed; prior user feedback louder voice but obvious noise; no clean-quality acceptance',
    microphone_audio_passed=False, voice_playback_passed=False)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print('Recorded bounded audio-filter evidence; wireless verification pending')
