"""Link same-image radio recovery to bounded audio evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[1]
E = R/'evidence/audio-filter-20260910'
auth = [json.loads(x) for x in (E/'wifi-auth-private.jsonl').read_text().splitlines()]
assert any('WIFI DHCP acquired ip=10.3.0.214' in x['line'] for x in auth)
for name in ('wifi-gateway.json', 'wifi-after-short-capture.json'):
    d = json.loads((E/name).read_text())
    lines = [line for record in d['records'] for line in record['lines']]
    assert any('5 packets transmitted, 5 received, 0% packet loss' in x for x in lines)
    assert any('WIFI status active=1 wifi_connected=1' in x for x in lines)
failures = []
for name in ('ble-wifi-connect.jsonl', 'ble-wifi-connect-fresh-bond.jsonl'):
    events = [json.loads(x) for x in (E/name).read_text().splitlines()]
    assert any(x.get('event') == 'FAIL' for x in events)
    failures.append(dict(file=name, errors=[x.get('error_type') for x in events if x.get('event')=='FAIL']))
report = dict(wpa2_dhcp_passed=True, submission='private echo-off serial console, not BLE',
    ip='10.3.0.214', gateway_initial='5/5', gateway_after_short_audio_capture='5/5',
    ble_connect_passed=False, ble_failures=failures, phone_tested=False,
    audio_scope='one 200ms capture while Wi-Fi online; gateway probe after capture',
    concurrent_ping_during_capture=False, long_stability_tested=False,
    voice_network_flow_tested=False)
(E/'wireless-recovery.json').write_text(json.dumps(report,indent=2))
p = R/'project-manifest.json'
d = json.loads(p.read_text(encoding='utf-8'))
assert d['current_device']['firmware']=='audio-filter-20260910'
d['updated_at'] = datetime.now(timezone.utc).isoformat()
d['current_device'].update(wireless_state='Wi-Fi online 10.3.0.214; BLE registered but no client connected',
    radio_started=True, wifi_connected=True, ble_connected=False, serial_observer_running=False)
d['latest_audio_checkpoint']['wireless_report']='evidence/audio-filter-20260910/wireless-recovery.json'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print('Same-image Wi-Fi verified; BLE failure preserved')
