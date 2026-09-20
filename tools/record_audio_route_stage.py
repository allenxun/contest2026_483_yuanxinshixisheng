"""Record a route counterexample and accurate current device state."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[1]
E = R/'evidence/audio-route-20260910'
rows = [json.loads((E/n).read_text()) for n in ('rxall-analysis.json','default-analysis.json')]
for d in rows:
    raw = Path(d['raw']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == d['sha256']
    assert all(d[x] == 0 for x in ('result','stop','restore','amp','held'))
    assert b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0 amp_low=1' in raw
assert rows[0]['path_active']=='000400e4' and rows[1]['path_active']=='0004e4e4'
assert all(x['path_restored']=='0000e4e4' for x in rows)
assert rows[0]['eight_word_groups']==rows[1]['eight_word_groups']
sha=hashlib.sha256((R/'artifacts/audio-route-20260910/nuttx.bin').read_bytes()).hexdigest()
assert sha=='d84275e8e7576941b70fdd2bb9bd427eee8716435565c6acc40ebfd0634acee3'
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
report=dict(revision='audio-route-20260910',firmware_sha256=sha,
    experiment='RX all paths select SDI0; same-image default control',
    operations=rows,route_written_and_restored=True,periodic_zero_samples_unresolved=True,
    finding='Changing RX routes did not change observed raw marker/zero distribution.',
    clean_audio_accepted=False,human_listening_performed=False)
(E/'runtime-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
p=R/'project-manifest.json'; d=json.loads(p.read_text(encoding='utf-8'))
d['updated_at']=datetime.now(timezone.utc).isoformat()
d['current_device']=dict(firmware=report['revision'],sha256=sha,console='NSH',audio_stopped=True,
    amp_low=True,radio_started=False,wifi_connected=False,ble_connected=False,serial_observer_running=False)
d['pending_firmware']=None
d['latest_audio_checkpoint']=dict(revision=report['revision'],firmware_sha256=sha,
    report='evidence/audio-route-20260910/runtime-results.json',finding=report['finding'],clean_audio_accepted=False)
p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print('Route experiment recorded: controlled variable confirmed, periodic zeros unchanged')
