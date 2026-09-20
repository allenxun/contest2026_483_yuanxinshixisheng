from cloud_radio_stage_audit import SSH,ROOT
import subprocess
code=r"""
import serial,time,re
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 def readfor(seconds):
  b=bytearray();end=time.monotonic()+seconds
  while time.monotonic()<end:b.extend(s.read(8192))
  return b
 readfor(1);s.write(bytes([13]));s.flush();b=readfor(1)
 assert b'nsh>' in b,'NSH handshake missing; no reboot sent'
 s.write(b'reboot'+bytes([13]));s.flush()
 b=bytearray();end=time.monotonic()+35
 while time.monotonic()<end:
  chunk=s.read(8192);b.extend(chunk)
  if b'U-Boot' in b:s.write(bytes([3]));s.flush();time.sleep(.02)
  if re.search(rb'(?:^|\n)=>\s*$',b):break
 print(b.decode(errors='replace'),flush=True)
 assert re.search(rb'(?:^|\n)=>\s*$',b),'U-Boot not intercepted'
 s.write(b'fastboot usb 1'+bytes([13]));s.flush();b=readfor(3)
 print(b.decode(errors='replace'),flush=True)
 assert b'Enter fastboot...OK' in b,'Fastboot not ready'
"""
r=subprocess.run(SSH[:-1]+['-o','ConnectTimeout=8',SSH[-1],'python3 -'],input=code.encode(),capture_output=True,timeout=50)
out=r.stdout+r.stderr
(ROOT/'evidence/resume-20260916/enter-download.log').write_bytes(out)
print(out.decode(errors='replace'))
raise SystemExit(r.returncode)
