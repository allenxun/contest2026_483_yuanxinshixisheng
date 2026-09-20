"""One-shot bounded two-A53 check after verified diagnostic RAM boot."""
import json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/smp-diag-20260910'
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert not (E/'diagnostic.json').exists()
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.rts=False;s.dtr=False;s.port='COM8'
buf=bytearray();returned=False
with s:
    s.write(b'k7smp\r');s.flush();start=time.monotonic()
    while time.monotonic()-start<6:
        buf.extend(s.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):returned=True;break
(E/'diagnostic.bin').write_bytes(buf)
lines=[re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',x).strip() for x in buf.decode('ascii',errors='replace').splitlines()]
passed=returned and any(x=='SMP result=PASS shared_counter=20000 expected=20000' for x in lines)
for cpu in (0,1):
    passed=passed and any(x.startswith(f'SMP cpu={cpu} observed={cpu} samples=10000 mismatch=0 sleep_errors=0 ') for x in lines)
result=dict(passed=passed,prompt_returned=returned,lines=lines,storage_writes=False,
            scope='two A53 pinned workers, shared atomic counter and timed sleeps; not eight-core or peripheral SMP acceptance')
(E/'diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
if not passed:raise RuntimeError('Two-core diagnostic not passed; preserve evidence before recovery')
