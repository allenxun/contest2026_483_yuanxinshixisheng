"""Bounded read-only console snapshot before the ORT diagnostic RAM load."""
import sys,time,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
O=R/'evidence/voice-ort-add-20260911';O.mkdir(exist_ok=True)
out=O/('preload-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
records=[]
with s:
 for cmd in ('uname -a','free','k7radio host-status','k7radio wifi-status'):
  s.write(cmd.encode()+b'\r');s.flush();raw=bytearray();end=time.monotonic()+5
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):break
  records.append(dict(command=cmd,output=raw.decode(errors='replace')))
  if not re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):break
out.write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
