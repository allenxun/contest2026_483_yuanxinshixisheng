from cloud_radio_stage_audit import ROOT,remote
code=r'''
import serial,time
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for c in b'k7host camera'+bytes([13]):s.write(bytes([c]));s.flush();time.sleep(.004)
 raw=bytearray();end=time.monotonic()+5
 while time.monotonic()<end:
  raw.extend(s.read(8192))
  if b'nsh>' in raw:break
 print(raw.decode(errors='replace'))
'''
raw=remote(code)
(ROOT/'evidence/device-intent-20260915/camera-readonly-after-wait.log').write_bytes(raw)
print(raw.decode(errors='replace'))
