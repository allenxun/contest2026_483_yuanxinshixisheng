"""One held camera session after user confirmed MCU reset and clear space."""
import subprocess
from cloud_radio_stage_audit import ROOT,remote
code=r'''
import serial,time
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for cmd,marker in [('k7host start',b'K7 host start result=0'),
                    ('k7host camera',b'camera connected=1'),
                    ('k7host probe',b'committed=1'),
                    ('k7host voicecam 1800 &',b'VOICE SESSION ready mode=0')]:
  for c in cmd.encode()+bytes([13]):s.write(bytes([c]));s.flush();time.sleep(.004)
  raw=bytearray();end=time.monotonic()+20
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if marker in raw:break
  print(raw.decode(errors='replace'),flush=True)
  if marker not in raw:raise RuntimeError('camera preparation failed: '+cmd)
  time.sleep(1)
'''
try:raw=remote(code);ok=True
except subprocess.CalledProcessError as e:raw=e.output or b'';ok=False
(ROOT/'evidence/device-intent-20260915/voicecam-start.log').write_bytes(raw)
print(raw.decode(errors='replace'))
if not ok:raise SystemExit(1)
