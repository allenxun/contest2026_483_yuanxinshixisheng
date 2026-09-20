"""Record observed board state separately from build-only and old id36 proof."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];E=ROOT/'evidence/credentials-20260909'
def text(name):return (E/name).read_text(encoding='utf-8',errors='replace')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rows=[json.loads(line) for line in text('ble-reception-03.jsonl').splitlines()]
    events={r['event']:r for r in rows}
    assert 'PASS' in events and events['capabilities']['state']['receive_credentials'] is True
    assert events['capabilities']['state']['encrypted'] and not events['capabilities']['state']['connect']
    assert events['real_scan_pass']['lansee_present']
    assert events['synthetic_credentials_receipt']['response']['event']=='credentials_received'
    assert 'NuttShell (NSH)' in text('ramload.bin')
    assert 'boot_ret=0 cp_ready=1 wifi_ready=1 bt_ready=1' in text('radio-start.bin')
    assert 'receive_credentials=1 connect=0 advertise=0' in text('bt-host.bin')
    assert 'registered=1 connected=0 subscribed=0 busy=0' in text('final-provision.bin')
    assert 'input_bytes=0' in text('final-provision.bin') and 'host_mode=1 fault=0' in text('final-host.bin')
    result=dict(revision='credentials-20260909',recorded_at=datetime.now(timezone.utc).isoformat(),
      firmware_sha256=sha(ROOT/'artifacts/credentials-20260909/nuttx.bin'),
      ram_booted=True,emmc_flashed=False,gimbal_started=False,hardware_joint_validation=False,
      bluetooth_name='VelaVision K7',serial_port='COM8',service_started=True,
      test_client_connected=False,receive_credentials=True,wifi_connect=False,wifi_connection_attempted=False,
      scope='Windows BLE real scan and synthetic credential receipt; not Android/iOS or WPA/DHCP validation',
      scan_count=events['real_scan_pass']['count'],lansee_present=True,
      credentials_receipt=events['synthetic_credentials_receipt']['response'],
      password_stored=False,invalid_password_rejected=True,
      initial_test_failures='First restricted Windows requester unavailable; second stale Windows bond caused GATT unreachable. Removed only owned K7 Windows bond; third test passed.',
      evidence={p.name:sha(p) for p in sorted(E.iterdir()) if p.is_file() and p.name!='device-state.json'})
    (E/'device-state.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest=json.loads((ROOT/'project-manifest.json').read_text(encoding='utf-8'))
    manifest['current_device']=result
    manifest['latest_development']['hardware_tested']=True
    manifest['latest_development']['hardware_scope']=result['scope']
    manifest['latest_development']['hardware_evidence']='evidence/credentials-20260909/device-state.json'
    (ROOT/'project-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(result='PASS',device=result['bluetooth_name'],scan_count=result['scan_count'],receive_credentials=True,connect=False)))
if __name__=='__main__':main()
