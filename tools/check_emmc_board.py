"""Bounded status or fixed LBA0/LBA1 read diagnostic; no raw storage output."""
import argparse,json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
p=argparse.ArgumentParser();p.add_argument('--probe',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
assert not a.out.exists(), 'Use a new evidence filename'
E=R/'evidence/emmc-readonly-20260910'
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
if a.probe:
    previous=json.loads((E/'status.json').read_text(encoding='utf-8'))
    assert previous['prompt_returned'] and any('EMMC status' in x for x in previous['lines'])
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.rts=False;s.dtr=False;s.port='COM8'
buf=bytearray();returned=False;cmd='k7emmc '+('probe' if a.probe else 'status')
try:
    with s:
        s.write(cmd.encode('ascii')+b'\r');s.flush();end=time.monotonic()+12
        while time.monotonic()<end:
            buf.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf): returned=True;break
finally:
    lines=[]
    for line in buf.decode('ascii',errors='replace').splitlines():
        line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
        if line.startswith('EMMC '):lines.append(line)
    result=dict(command=cmd,prompt_returned=returned,lines=lines,storage_writes=False)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
if not returned:raise RuntimeError('Console did not return; do not blindly retry')
