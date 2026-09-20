"""Run the one-shot short SIMD context probe; never launch actuators."""
import json,re,sys,time
from pathlib import Path
from smp_console_config import console_baud
R=Path(__file__).resolve().parents[1];E=R/'evidence/neon-file64-20260910'
assert json.loads((E/'runtime.json').read_text())['passed']
assert not (E/'neon.json').exists()
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=console_baud(R,E.name),timeout=.02,write_timeout=2)
s.rts=False;s.dtr=False;s.port='COM8';raw=bytearray();prompt=False
started=time.monotonic()
try:
    with s:
        s.write(b'k7neon\r');s.flush()
        while time.monotonic()-started<13:
            raw.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
finally:
    (E/'neon.bin').write_bytes(raw)
rows=[dict(zip(['id','cpu','batches','peer_progress','errors'],map(int,m))) for m in re.findall(rb'NEON id=(\d+) cpu=(\d+) batches=(\d+) peer_progress=(\d+) errors=(\d+)',raw)]
passed=prompt and len(rows)==4 and b'NEON result=PASS scope=d8-d15-low64 cpus=4,5' in raw
passed=passed and [r['cpu'] for r in rows]==[4,4,5,5] and [r['id'] for r in rows]==[0,1,2,3]
passed=passed and all(r['batches']>0 and r['peer_progress']>0 and r['errors']==0 for r in rows)
report=dict(passed=passed,duration_seconds=time.monotonic()-started,workers=rows,
 scope='CPU4/5 D8-D15 low64 across yielded peer progress, not all SIMD state or LLM',model_tested=False)
(E/'neon.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if not passed:raise SystemExit(1)
