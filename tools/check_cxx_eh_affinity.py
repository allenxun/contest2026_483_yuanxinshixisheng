"""Bounded actual task-affinity snapshot for the experimental service build."""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from smp_console_config import console_baud

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/cxx-eh-20260910'
p = argparse.ArgumentParser()
p.add_argument('--radio', action='store_true')
a = p.parse_args()
name = 'affinity-radio' if a.radio else 'affinity-boot'
assert not (E / (name + '.json')).exists()
assert 'PASS: REAL K7 NSH' in (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
sys.path.insert(0, str(R.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial
s = serial.Serial(port=None, baudrate=console_baud(R, E.name), timeout=.02, write_timeout=2)
s.rts = False
s.dtr = False
s.port = 'COM8'
raw = bytearray()
prompt = False
try:
    with s:
        s.write(b'ps\r')
        s.flush()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            raw.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
                prompt = True
                break
finally:
    (E / (name + '.bin')).write_bytes(raw)
lines = raw.decode('ascii', errors='replace').splitlines()
tasks = [line for line in lines if re.match(r'\s*\d+\s+\d+\s+(?:\d+|---)\(0x', line)]
idle = [line for line in tasks if re.search(r'CPU[0-7] IDLE', line)]
services = [line for line in tasks if line not in idle]
passed = prompt and len(idle) == 8 and bool(services)
passed = passed and all('(0x00000001)' in line for line in services)
if a.radio:
    passed = passed and all(any(n in line for line in services) for n in ['skw_bt_tx', 'skw_radio_rx', 'skw_wifi_ip'])
report = dict(passed=passed, idle_count=len(idle), service_tasks=services,
              scope='Task affinity snapshot only; not IRQ affinity or migration stress', storage_writes=False)
(E / (name + '.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
if not passed:
    raise RuntimeError('Actual task affinity did not meet service-profile gate')
