"""Retry the retained set through the existing native stage worker; no reboot."""
from cloud_radio_stage_audit import remote,ROOT
assert 'ASSESSMENT_READY' in (ROOT/'evidence/hello-keyword-20260916/gateway-upload-diag.log').read_text()
code=r'''
from pathlib import Path
import json,os,signal,time,serial,re
root=Path('/home/swl/openvela/work/velavision-project')
out=root/'evidence/hello-keyword-20260916'
state=json.loads((root/'evidence/integration-panel-20260916/state.json').read_text())
assert state['done']==7 and state['held'] and not state['busy'],state
assert b'/host/whole_device/integration_panel.py' in Path('/proc/11934/cmdline').read_bytes()
os.kill(11934,signal.SIGTERM);time.sleep(1)
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
def send(cmd):
 for byte in (cmd+'\r').encode():s.write(bytes([byte]));s.flush();time.sleep(.004)
buf=bytearray();result={'upload_observed':False}
log=(out/'retained-upload-retry.log').open('xb',buffering=0)
try:
 send('k7cloud device-loop 10.3.1.125 60 &')
 end=time.monotonic()+150
 while time.monotonic()<end:
  raw=s.read(8192);log.write(raw);buf.extend(raw)
  m=re.search(rb'K7CLOUD photo_upload epoch=(\d+) result=(-?\d+) accepted=(\d+) task=([^\r\n]*)',buf)
  if m:
   result={'upload_observed':True,'epoch':int(m[1]),'result':int(m[2]),'accepted':m[3]==b'1','task':m[4].decode(errors='replace')};break
  if b'K7CLOUD device loop_done=' in buf:break
finally:
 send('k7cloud device-stop');time.sleep(.3);send('k7host halt')
 end=time.monotonic()+8
 while time.monotonic()<end:log.write(s.read(8192))
 s.close();log.close()
 (out/'retained-upload-retry.json').write_text(json.dumps(result))
print(json.dumps(result))
'''
result=remote(code)
(ROOT/'evidence/hello-keyword-20260916/retained-upload-retry.json').write_bytes(result)
print(result.decode())
