"""Bounded external observation of fresh-boot cold/warm exceptions."""
import argparse,hashlib,json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/cxx-eh-20260910'
p=argparse.ArgumentParser();p.add_argument('mode',choices=['cold','warm']);a=p.parse_args()
out=E/a.mode;out.mkdir(exist_ok=True)
assert not (out/'runtime.json').exists()
bootlog=out/'ramload-progress.txt'
assert 'PASS: REAL K7 NSH' in bootlog.read_text(encoding='utf-8-sig')
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.rts=False;s.dtr=False;s.port='COM8';raw=bytearray();prompt=False
started=time.monotonic()
try:
    with s:
        s.write(('k7eh '+a.mode+'\r').encode());s.flush()
        while time.monotonic()-started<15:
            raw.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
finally:
    (out/'runtime.bin').write_bytes(raw)
pattern=rb'K7EH worker=(\d+) caught=(\d+) cleaned=(\d+) errors=(\d+) cpu=(\d+) cpu_mismatch=(\d+) first_begin=(\d+) first_end=(\d+)'
keys=['worker','caught','cleaned','errors','cpu','cpu_mismatch','first_begin','first_end']
workers=[dict(zip(keys,map(int,m))) for m in re.findall(pattern,raw)]
rounds=1 if a.mode=='cold' else 64
passed=prompt and len(workers)==2 and ('K7EH result=PASS code=0 created=2 joined=2 mode='+a.mode).encode() in raw
passed=passed and all(w['worker']==i and w['cpu']==4+i and w['caught']==rounds and w['cleaned']==3*rounds and w['errors']==w['cpu_mismatch']==0 for i,w in enumerate(workers))
overlap=False
if len(workers)==2:
    overlap=max(w['first_begin'] for w in workers)<min(w['first_end'] for w in workers)
report=dict(passed=passed,mode=a.mode,prompt=prompt,workers=workers,
 duration_seconds=time.monotonic()-started,first_call_intervals_overlap=overlap,
 global_unwinder_cold_proven=False,libgcc_thread_safety_proven=False,
 boot_log_sha256=hashlib.sha256(bootlog.read_bytes()).hexdigest(),
 scope='Finite target exception/RAII and joined-thread check; not proof of shared unwinder synchronization')
(out/'runtime.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if not passed:raise SystemExit(1)
