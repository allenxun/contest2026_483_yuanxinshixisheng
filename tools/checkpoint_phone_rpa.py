"""Record new image startup without inheriting the previous phone pass."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REV='phone-rpa-20260909';E=ROOT/'evidence'/REV
def read(n):return (E/n).read_text(encoding='utf-8',errors='replace')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((ROOT/'evidence/build'/REV/'verification.json').read_text())
assert report['build_exit_code']==0 and report['address_tests']['exit_code']==0
for name,digest in report['sources'].items():assert sha(ROOT/name)==digest,name
assert 'NuttShell (NSH)' in read('ramload.bin')
assert 'boot_ret=0 cp_ready=1 wifi_ready=1 bt_ready=1' in read('radio-start.bin')
assert 'receive_credentials=1 connect=0 advertise=0' in read('bt-host.bin')
assert 'RADIO bt-host ret=0' in read('bt-host.bin')
result=dict(revision=REV,recorded_at=datetime.now(timezone.utc).isoformat(),
    firmware_sha256=report['artifacts']['nuttx.bin']['sha256'],ram_booted=True,
    emmc_flashed=False,gimbal_started=False,hardware_joint_validation=False,
    bluetooth_name='VelaVision K7',serial_port='COM8',service_started=True,
    paired_record_capacity=8,recycle_idle_records=True,max_simultaneous_connections=1,
    receive_credentials=True,wifi_connect=False,wifi_connection_attempted=False,
    phone_repair_validation='pending',phone_data_exchange='pending',phone_long_connection_passed=False,
    scope='RPA address correction: RAM boot and service startup passed; phone re-pairing and X test pending',
    evidence={name:sha(E/name) for name in ('ramload.bin','radio-start.bin','bt-host.bin')})
(E/'device-state.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=ROOT/'project-manifest.json';manifest=json.loads(p.read_text(encoding='utf-8'))
manifest['current_device']=result
manifest['latest_development']=dict(revision=REV,hardware_tested=True,hardware_scope=result['scope'],hardware_evidence=f'evidence/{REV}/device-state.json',snapshot=f'evidence/build/{REV}/verification.json',note='Earlier phone initial-hold pass did not prove re-pairing stability')
p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
