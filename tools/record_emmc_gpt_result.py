"""Record verified native GPT results, preserving prior image evidence."""
import json,hashlib
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/emmc-gpt-20260910'
gpt=json.loads((E/'gpt-01.json').read_text());parts=json.loads((E/'partition-summary.json').read_text())
assert gpt['prompt_returned'] and any('primary_backup_crc=PASS' in x for x in gpt['lines'])
events=[json.loads(x) for x in (E/'ble-connect.jsonl').read_text().splitlines()]
assert any(x['event']=='hold_pass' and x['seconds']==30 for x in events)
assert events[-1]['event']=='test_client_disconnected'
gateway=json.loads((E/'gateway.json').read_text())
assert any('5 packets transmitted, 5 received' in line for x in gateway['records'] for line in x['lines'])
report=json.loads((R/'evidence/build/emmc-gpt-20260910/verification.json').read_text())
digest=report['artifacts']['nuttx.bin']['sha256']
assert hashlib.sha256((R/'artifacts/emmc-gpt-20260910/nuttx.bin').read_bytes()).hexdigest()==digest
state=dict(updated_at=datetime.now(timezone.utc).isoformat(),running_revision='emmc-gpt-20260910',
    firmware_sha256=digest,boot='RAM',liveness_verified=True,wifi_connected=True,test_ip='10.3.0.214',
    ble_service_running=True,ble_connected=False,test_client_intentionally_disconnected=True,
    real_ble_to_wifi_passed=True,test_client='Windows Bleak',gateway_ping=dict(sent=5,received=5),
    ble_wifi_hold_seconds=30,emmc=dict(sectors=parts['device_sectors'],sector_bytes=512,mode='400kHz 1-bit PIO',
        initialization_passed=True,gpt_primary_backup_and_entries_crc_passed=True,partitions=len(parts['partitions']),
        inter_partition_gaps=len(parts['inter_partition_gaps']),block_device_registered=False,filesystem_mounted=False),
    model_arena=dict(mapped_bytes=1073741824,retested_this_build=False),smp_cpus=1,emmc_written=False,
    production_stability_passed=False,wireless_note='One A-MSDU rejected counter observed; not a zero-error stress test',
    evidence_directory=str(E.relative_to(R)))
(E/'device-state.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
m=json.loads((R/'project-manifest.json').read_text(encoding='utf-8'));m['current_device']=state
m['pending_firmware']={'revision':'emmc-block-20260910','state':'building; not loaded'}
(R/'project-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Recorded GPT CRC verification and radio recovery; block-device candidate pending')
