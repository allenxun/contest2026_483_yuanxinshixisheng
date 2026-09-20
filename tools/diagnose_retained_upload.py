from cloud_radio_stage_audit import remote,ROOT
code=r'''
from pathlib import Path
import json,os,signal,time,serial,re
root=Path('/home/swl/openvela/work/velavision-project')
out=root/'evidence/photo-retry-20260916'
state=json.loads((root/'evidence/integration-panel-20260916/state.json').read_text())
assert state['done']==7 and state['held'] and not state['busy'],state
assert b'/host/whole_device/integration_panel.py' in Path('/proc/28435/cmdline').read_bytes()
(out/'pre-direct-retry-state.json').write_text(json.dumps(state))
os.kill(28435,signal.SIGTERM);time.sleep(1)
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
log=(out/'direct-native-retry.log').open('xb',buffering=0)
buf=bytearray()
try:
 for byte in b'k7cloud photo-retry 10.3.1.125 &\r':s.write(bytes([byte]));s.flush();time.sleep(.004)
 end=time.monotonic()+55
 while time.monotonic()<end:
  raw=s.read(8192);log.write(raw);buf.extend(raw)
  if b'K7CLOUD photo_retry result=' in buf:break
finally:s.close();log.close()
print('\n'.join(x for x in buf.decode(errors='replace').splitlines() if any(k in x for k in ('photo_','error','Error'))))
'''
result=remote(code)
(ROOT/'evidence/photo-retry-20260916/direct-native-retry-result.txt').write_bytes(result)
print(result.decode())

