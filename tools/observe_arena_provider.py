"""Bounded, one-shot observation of the actual K7 model-pool tensor diagnostic."""
import json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/arena-provider-20260910'
assert not (E/'runtime.json').exists()
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert json.loads((E/'affinity-boot.json').read_text())['passed']
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';raw=bytearray();prompt=False;error=None
start=time.monotonic()
try:
 with s:
  s.write(b'k7arena\r');s.flush()
  end=start+15
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
except Exception as exc:error=type(exc).__name__+': '+str(exc)
finally:(E/'runtime.bin').write_bytes(raw)
rows=[]
for line in raw.decode('ascii',errors='replace').splitlines():
 if line.startswith('arena_provider result='):
  rows.append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
expected=dict(result=0,init_raw=0,peak=32768,checked=8192,mismatches=0,
 allocations=1,releases=1,live=0,errors=0,quarantine=0,range=1,returned=1,limit=1048576,weights=0)
passed=prompt and error is None and len(rows)==1
if passed:
 row=rows[0];passed=all(row.get(k)==v for k,v in expected.items()) and row.get('before')==row.get('after') and row.get('before',0)>1048576
r=dict(passed=passed,prompt_returned=prompt,elapsed_seconds=time.monotonic()-start,error=error,rows=rows,
 scope='Real K7 arena plus ggml set/get only; 32KiB normal payload, no graph computation/model/OOM/full-DDR test',
 on_timeout='Observer stops reading; no forced task deletion or speculative resource cleanup')
(E/'runtime.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if not passed:raise RuntimeError('Actual arena diagnostic failed exact gate')
