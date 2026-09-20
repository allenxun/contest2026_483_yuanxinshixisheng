"""One bounded observation of the real, weight-free ggml graph on K7."""
import json
import re
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/graph-core-20260910'
assert not (E / 'runtime.json').exists(), 'Preserve the first run'
assert 'PASS: REAL K7 NSH' in (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert json.loads((E / 'affinity-boot.json').read_text())['passed']
sys.path.insert(0, str(R.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial

s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
s.rts = False
s.dtr = False
s.port = 'COM8'
raw = bytearray()
prompt = False
error = None
start = time.monotonic()
try:
    with s:
        s.write(b'k7graph both\r')
        s.flush()
        end = start + 20
        while time.monotonic() < end:
            raw.extend(s.read(16384))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
                prompt = True
                break
except Exception as exc:
    error = type(exc).__name__ + ': ' + str(exc)
finally:
    (E / 'runtime.bin').write_bytes(raw)

rows = []
for line in raw.decode('ascii', errors='replace').splitlines():
    if 'threads_configured=' in line:
        rows.append({k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)(?:\s|$)', line)})
checks = []
for threads, mask in [(2, 2), (4, 14)]:
    found = [r for r in rows if r.get('threads_configured') == threads]
    expected = dict(result=0, operation=0, cleanup=0, compute=0, checked=4096,
                    mismatches=0, checksum=-10, worker_mask=mask,
                    starts=threads-1, exits=threads-1, pool_bytes=0, handles=0,
                    running=0, mutexes=0, conds=0, attrs=0,
                    retained_pool=0, retained_context=0, weights=0,
                    physical_cpu_observed=0)
    checks.append(len(found) == 1 and all(found[0].get(k) == v for k, v in expected.items()))
passed = prompt and error is None and len(rows) == 2 and all(checks)
report = dict(passed=passed, elapsed_seconds=time.monotonic()-start,
              prompt_returned=prompt, error=error, rows=rows,
              scope='Real ggml F32 multiply, no weights; software worker participation only, no physical CPU observation',
              on_timeout='Observation ends only; no task kill, free, cleanup retry or success inference')
(E / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
if not passed:
    raise RuntimeError('Graph runtime did not meet the exact acceptance gate')
