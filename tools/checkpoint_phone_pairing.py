"""Record actual RAM boot/service evidence separately from phone acceptance."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REV='phone-pairing-20260909';E=ROOT/'evidence'/REV
def read(name):return (E/name).read_text(encoding='utf-8',errors='replace')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
report=json.loads((ROOT/'evidence/build'/REV/'verification.json').read_text())
assert report['build_exit_code']==0 and all(t['exit_code']==0 for t in report['pool_tests'])
for name,digest in report['sources'].items():assert sha(ROOT/name)==digest,name
assert 'NuttShell (NSH)' in read('ramload.bin')
assert 'boot_ret=0 cp_ready=1 wifi_ready=1 bt_ready=1' in read('radio-start.bin')
# The short initial console capture ended before initialization finished.
# Use subsequent live status, not an invented missing startup log line.
assert 'host_mode=1 fault=0' in read('host-status.bin')
assert 'registered=1 connected=0 subscribed=0 busy=0' in read('provision-status.bin')
result=dict(revision=REV,recorded_at=datetime.now(timezone.utc).isoformat(),
    firmware_sha256=report['artifacts']['nuttx.bin']['sha256'],ram_booted=True,
    emmc_flashed=False,gimbal_started=False,hardware_joint_validation=False,
    bluetooth_name='VelaVision K7',serial_port='COM8',service_started=True,
    paired_record_capacity=8,recycle_idle_records=True,max_simultaneous_connections=1,
    receive_credentials=True,wifi_connect=False,wifi_connection_attempted=False,
    phone_pairing_passed=False,phone_long_connection_passed=False,
    scope='New image RAM boot and radio/provision startup only; phone retest pending',
    evidence={name:sha(E/name) for name in ('ramload.bin','radio-start.bin','bt-host.bin','host-status.bin','provision-status.bin','ble-status.bin')})
if (E/'phone-live-ble.bin').exists():
    assert 'connections=1 disconnections=0' in read('phone-live-ble.bin')
    assert 'encrypt_status=0 encrypted=1' in read('phone-live-ble.bin')
    assert 'registered=1 connected=1 subscribed=0 busy=0' in read('phone-live-provision.bin')
    rows=[json.loads(line) for line in read('phone-observation-01.jsonl').splitlines()]
    start=next(datetime.fromisoformat(row['time']) for row in rows if row.get('line','').startswith('RADIO BLE connection status=0'))
    observed=datetime.fromtimestamp((E/'phone-live-ble.bin').stat().st_mtime,timezone.utc)
    result.update(phone_pairing_passed=True,user_confirmed_phone_connected=True,
                  connected_at_observation=True,encrypted_at_observation=True,
                  observed_connection_seconds=int((observed-start).total_seconds()),
                  connections=1,disconnections=0,notify_subscribed=False,
                  scope='User-confirmed phone pairing and encrypted initial hold; longer soak/reconnect/data exchange pending')
    for name in ('phone-live-ble.bin','phone-live-provision.bin','phone-observation-01.jsonl'):
        result['evidence'][name]=sha(E/name)
(E/'device-state.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=ROOT/'project-manifest.json';manifest=json.loads(p.read_text(encoding='utf-8'))
manifest['current_device']=result
manifest['latest_development']=dict(revision=REV,hardware_tested=True,
    hardware_scope=result['scope'],hardware_evidence=f'evidence/{REV}/device-state.json',
    snapshot=f'evidence/build/{REV}/verification.json',
    note='Earlier acceptance snapshots remain historical; no Android long-connection pass claimed')
p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
