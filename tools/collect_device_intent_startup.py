import json
from datetime import datetime,timezone
from cloud_radio_stage_audit import remote,ROOT
raw=remote("import pathlib;print(pathlib.Path('/home/swl/openvela/work/velavision-project/evidence/device-intent-20260915/result.json').read_text())")
result=json.loads(raw)
assert result['ram_boot'] and result['firmware_sha256']=='c3b862d2c62ced7504e1c7a4babfe317fb0c18aeee285c1c3b7f133939c5e137'
result.update(wifi_connected_at_startup=False,ble_service_ready=True,
              bridge_pid=54580,bridge_echo_test=False,motion_tested=False,
              updated_at=datetime.now(timezone.utc).isoformat())
(ROOT/'evidence/device-intent-20260915/device-state.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
