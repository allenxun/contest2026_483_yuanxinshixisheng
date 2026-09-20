"""One bounded serial invocation of the C++ runtime probe, with raw evidence."""
import json
import re
import sys
import time
from pathlib import Path
from smp_console_config import console_baud
R = Path(__file__).resolve().parents[1]
E = R/'evidence/cxx-unwind-20260910'
assert not (E/'runtime.json').exists(), 'Do not overwrite a completed attempt'
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
sys.path.insert(0, str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s = serial.Serial(port=None, baudrate=console_baud(R,E.name), timeout=.02, write_timeout=2)
s.rts = False
s.dtr = False
s.port = 'COM8'
raw = bytearray()
prompt = False
started = time.monotonic()
try:
    with s:
        s.write(b'k7cxx\r')
        s.flush()
        while time.monotonic()-started < 10:
            raw.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):
                prompt = True
                break
finally:
    (E/'runtime.bin').write_bytes(raw)
match = re.search(rb'CXX result=(PASS|FAIL) code=(\d+) off_t_bits=(\d+) pointer_bits=(\d+) model_tested=0',raw)
report = dict(passed=bool(prompt and match and match[1]==b'PASS'),
              prompt=prompt, duration_seconds=time.monotonic()-started,
              model_tested=False, file_io_tested=False, storage_written=False)
if match:
    report.update(code=int(match[2]),off_t_bits=int(match[3]),pointer_bits=int(match[4]))
(E/'runtime.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if not report['passed']: raise SystemExit(1)
