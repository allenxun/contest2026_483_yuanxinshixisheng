"""Record actual indexed A-MSDU hardware results and immutable source hashes."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REV='wifi-amsdu-index-20260909';E=ROOT/'evidence'/REV
def text(name):return (E/name).read_text(encoding='utf-8',errors='replace')
report=json.loads((ROOT/'evidence/build'/REV/'verification.json').read_text())
assert report['build_exit_code']==0
for test in ('handshake_tests','wifi_data_tests','amsdu_tests'):assert report[test]['exit_code']==0
for name,digest in report['sources'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
assert 'DHCP acquired ip=10.3.0.214 gateway=10.3.0.1 wifi_connected=1' in text('lansee-01.jsonl')
ping=re.search(r'(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss',text('ping-first-40.bin'));assert ping
stats=re.search(r'WIFI AMSDU complete=(\d+) subframes=(\d+) rejected=(\d+)',text('wifi-status.bin'));assert stats
ble=re.search(r'connected=(\d+).*handle=(\d+)',text('ble-status.bin'));assert ble
encrypt=re.search(r'encrypted=(\d+)',text('ble-status.bin'));assert encrypt
v=dict(updated_at=datetime.now(timezone.utc).isoformat(),running_revision=REV,boot='RAM',firmware_sha256=report['artifacts']['nuttx.bin']['sha256'],wpa2_hardware_passed=True,dhcp_hardware_passed=True,test_ssid='Lansee',tested_ip='10.3.0.214',tested_gateway='10.3.0.1',gateway_ping=dict(sent=int(ping[1]),received=int(ping[2]),loss_percent=float(ping[3])),amsdu=dict(complete=int(stats[1]),subframes=int(stats[2]),rejected=int(stats[3])),ble_connected_at_snapshot=bool(int(ble[1])),ble_encrypted_at_snapshot=bool(int(encrypt[1])),frontend_connect=False,long_duration_acceptance=False,emmc_written=False,stm32_written=False,gimbal_started=False)
v['amsdu_hardware_passed']=int(stats[1])>0 and int(ping[1])==int(ping[2])
v['historical_wifi_auth_negative_test']='evidence/wifi-ip-rx-20260909/wrong-password-01.jsonl'
if (E/'ble-after-coexist.bin').exists():
    after=text('ble-after-coexist.bin');before=text('ble-status.bin');run=text('phone-coexist-50.bin')
    assert '50 packets transmitted, 50 received, 0% packet loss' in run
    assert 'RADIO BLE disconnected' not in run
    for pattern in (r'connected=1 handle=17',r'connections=2 disconnections=1',r'encrypt_status=0 encrypted=1'):
        assert re.search(pattern,before) and re.search(pattern,after),pattern
    assert 'wifi_connected=1 ip=10.3.0.214' in text('wifi-after-coexist.bin')
    v['ble_wifi_short_coexistence']=dict(passed=True,duration_ms=50050,ping_sent=50,ping_received=50,new_ble_disconnections=0,encrypted_before_and_after=True,scope='phone BLE connection held during Wi-Fi gateway traffic; not simultaneous BLE application throughput or long-duration acceptance')
    v['current_device_scope']='Lansee connected; phone BLE encrypted at snapshot; no persistent UART observer'
v['evidence']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(E.iterdir()) if p.is_file() and p.name!='device-state.json'}
(E/'device-state.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=ROOT/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'));m['latest_wireless_checkpoint']=v;p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v[k] for k in ('running_revision','gateway_ping','amsdu','amsdu_hardware_passed','ble_connected_at_snapshot','ble_encrypted_at_snapshot')},ensure_ascii=False))
