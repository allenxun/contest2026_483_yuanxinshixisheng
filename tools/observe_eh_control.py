"""Observe one explicit EH control on a fresh RAM boot; never force cleanup."""
import argparse,json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/eh-control-20260910'
p=argparse.ArgumentParser();p.add_argument('mode',choices=['single','warm1']);a=p.parse_args()
out=E/a.mode;out.mkdir(exist_ok=True)
assert not (out/'runtime.json').exists()
boot=E/('ramload-progress.txt' if a.mode=='single' else 'warm1-ramload-progress.txt')
assert 'PASS: REAL K7 NSH' in boot.read_text(encoding='utf-8-sig')
if a.mode=='warm1':assert (E/'single/runtime.json').exists()
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';raw=bytearray();prompt=False;error=None
start=time.monotonic()
try:
 with s:
  s.write(('k7ehcontrol '+a.mode+'\r').encode());s.flush()
  end=start+18
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
except Exception as exc:error=type(exc).__name__+': '+str(exc)
finally:(out/'runtime.bin').write_bytes(raw)
text=raw.decode('ascii',errors='replace');rows=[]
for line in text.splitlines():
 if 'K7EHCONTROL worker=' in line:rows.append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
count=1 if a.mode=='single' else 2
worker_ok=len(rows)==count
for index,row in enumerate(rows):
 cpu=5 if count==1 else 4+index
 expected=dict(worker=index,caught=1,cleaned=3,errors=0,cpu=cpu,requested_cpu=cpu,cpu_mismatch=0)
 worker_ok=worker_ok and all(row.get(k)==v for k,v in expected.items())
 worker_ok=worker_ok and row.get('first_end',0)>=row.get('first_begin',1)>0
final=f'K7EHCONTROL result=PASS code=0 created={count} joined={count} mode={a.mode} concurrency_proven=0'
preheat='K7EHCONTROL PREHEAT_PASS caught=1 cleaned=3 workers_created=0'
passed=prompt and error is None and worker_ok and final in text
if a.mode=='warm1':passed=passed and preheat in text and text.index(preheat)<text.index('K7EHCONTROL worker=')
r=dict(mode=a.mode,passed=passed,prompt_returned=prompt,elapsed_seconds=time.monotonic()-start,
 error=error,workers=rows,preheat_pass=preheat in text,joined_summary=final in text,
 scope='One fresh-boot control, not general concurrent unwinder safety or overlap proof',
 on_failure='No forced task deletion/free; preserve output and restore baseline')
(out/'runtime.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if not passed:raise RuntimeError('EH control failed exact gate; raw output preserved')
