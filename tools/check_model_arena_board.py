"""Bounded checks for the explicitly enabled K7 model arena; no raw memory commands."""
import json,re,sys,time
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1];E=R/'evidence/model-arena-20260910'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
records=[]
s=serial.Serial(port=None,baudrate=1500000,timeout=.03,write_timeout=2);s.rts=False;s.dtr=False;s.port='COM8'
try:
 with s:
  for cmd,timeout in [('k7mem status',5),('free',5),('k7mem test',60),('k7mem status',5),('free',5)]:
   s.write(cmd.encode()+b'\r');s.flush();buf=bytearray();end=time.monotonic()+timeout
   while time.monotonic()<end:
    buf.extend(s.read(8192))
    if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):break
   else:raise RuntimeError('Timeout: '+cmd)
   clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',buf.decode(errors='replace'))
   records.append(dict(time=datetime.now(timezone.utc).isoformat(),command=cmd,output=clean));print(clean,flush=True)
   if cmd=='k7mem test':
    m=re.search(r'sparse_test=PASS allocation=(\d+) page_samples=(\d+) passes=2 free_before=(\d+) free_after=(\d+)',clean)
    assert m and int(m[1])==384*1024*1024 and int(m[2])==98304 and int(m[3])==int(m[4]), 'DDR test failed'
finally:
 with (E/'ddr-test.json').open('x',encoding='utf-8') as f:json.dump(dict(records=records,scope='384MiB allocation; 98304 sparse pages, two patterns, cache clean/invalidate and free recovery; not all-byte 1GiB coverage'),f,indent=2)
