"""Start only the radio firmware and provisioning service after verified RAM boot."""
import sys,time,re,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/emmc-block-20260910'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
with s:
 # bt-host registers and advertises the provisioning service itself.
 stages=[('sdio-boot','k7radio sdio-boot',40,b'nsh>'),('bt-host','k7radio bt-host',35,b'connect=true advertise=0')]
 for name,cmd,timeout,expected in stages:
  s.write(cmd.encode()+b'\r');s.flush();buf=bytearray();end=time.monotonic()+timeout
  while time.monotonic()<end:
   buf.extend(s.read(8192))
   if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):break
  else:raise RuntimeError('Console timeout: '+name)
  # No connection credentials are submitted by startup commands.
  (E/(name+'.bin')).write_bytes(buf)
  assert expected in buf,'Startup gate failed: '+name
  print(json.dumps(dict(stage=name,expected_marker=True)),flush=True)
