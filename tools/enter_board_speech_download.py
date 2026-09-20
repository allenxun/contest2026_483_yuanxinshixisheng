from cloud_radio_stage_audit import remote,ROOT
import subprocess
code=r'''
import serial,time,re
with serial.Serial('/dev/ttyUSB0',1500000,timeout=.02,write_timeout=2) as s:
 s.dtr=False;s.rts=False
 for c in b'reboot\r':s.write(bytes([c]));s.flush();time.sleep(.004)
 b=bytearray();end=time.monotonic()+35
 while time.monotonic()<end:
  b.extend(s.read(8192))
  if b'U-Boot' in b:s.write(b'\x03');s.flush();time.sleep(.03)
  if re.search(rb'(?:^|\n)=>\s*$',b):break
 else:raise RuntimeError('U-Boot not intercepted')
 print(b.decode(errors='replace'),flush=True)
 s.write(b'fastboot usb 1\r');s.flush();end=time.monotonic()+3;b=bytearray()
 while time.monotonic()<end:b.extend(s.read(8192))
 print(b.decode(errors='replace'),flush=True)
 if b'Enter fastboot...OK' not in b:raise RuntimeError('gadget not ready')
'''
try:result=remote(code)
except subprocess.CalledProcessError as e:result=e.output
(ROOT/'evidence/board-speech-bridge-20260914/enter-download.log').write_bytes(result)
print(result.decode(errors='replace'))
