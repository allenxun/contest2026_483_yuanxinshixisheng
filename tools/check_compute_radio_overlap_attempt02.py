"""One bounded compute experiment with concurrent gateway traffic.
Only whitelisted diagnostic lines are persisted; no radio payloads/credentials.
"""
import json
import re
import sys
import time
from pathlib import Path
from smp_console_config import console_baud
R = Path(__file__).resolve().parents[1]
E = R / 'evidence/smp-load-20260910'
assert not (E / 'compute-radio-attempt02.json').exists()
assert json.loads((E / 'affinity-boot.json').read_text())['passed']
ble = [json.loads(x) for x in (E / 'ble-overlap-attempt02.jsonl').read_text().splitlines()]
assert any(x['event'] == 'hold_started' for x in ble)
assert not any(x['event'] in ['FAIL', 'test_client_disconnected'] for x in ble)
sys.path.insert(0, str(R.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial
s = serial.Serial(port=None, baudrate=console_baud(R, E.name), timeout=.02, write_timeout=2)
s.dtr = False
s.rts = False
s.port = 'COM8'
records = []
partial = bytearray()
allowed = re.compile(r'^(LOAD |56 bytes from 10\.3\.0\.1:|45 packets transmitted,|rtt min/avg/max/mdev|ERROR:)')

def receive(data):
    partial.extend(data)
    while b'\n' in partial:
        raw, _, tail = partial.partition(b'\n')
        partial[:] = tail
        line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', raw.decode('ascii', errors='replace')).strip()
        if allowed.match(line):
            row = dict(wall_time=time.time(), line=line)
            records.append(row)
            if line.startswith('LOAD '): print(json.dumps(row), flush=True)
    if len(partial) > 8192:
        raise RuntimeError('Unexpected unbounded console line')

passed = False
prompt = False
start = time.time()
try:
    with s:
        # Discard old asynchronous radio messages; never persist their payloads.
        until = time.monotonic() + .3
        while time.monotonic() < until: s.read(8192)
        s.write(b'ping -c 45 -I wlan0 10.3.0.1 &\r')
        s.flush()
        buf = bytearray()
        until = time.monotonic() + 3
        while time.monotonic() < until:
            data = s.read(8192)
            buf.extend(data)
            receive(data)
            if re.search(rb'nsh>\s*(?:\x1b\[K)?', buf): break
        else: raise RuntimeError('Background ping did not return NSH prompt')
        partial.clear()
        s.write(b'k7load\r')
        s.flush()
        end = time.monotonic() + 66
        buf.clear()
        while time.monotonic() < end:
            data = s.read(8192)
            buf.extend(data)
            receive(data)
            if b'LOAD result=' in buf and re.search(rb'nsh>\s*(?:\x1b\[K)?$', buf):
                prompt = True
                break
        rows = [r['line'] for r in records]
        passed = prompt and any(x.startswith('LOAD result=PASS ') for x in rows)
        passed = passed and any('45 packets transmitted, 45 received, 0% packet loss' in x for x in rows)
        for cpu in range(4, 8):
            passed = passed and any(re.match(rf'LOAD cpu={cpu} batches=\d+ mismatch=0 bad_result=0 sleep_errors=0 clock_errors=0 ', x) for x in rows)
finally:
    (E / 'compute-radio-attempt02.json').write_text(json.dumps(dict(passed=passed, prompt_returned=prompt,
        start_wall_time=start, end_wall_time=time.time(), records=records,
        scope='60-second four-A72 synthetic compute plus gateway ping; BLE overlap verified separately',
        raw_radio_payloads_saved=False, storage_writes=False), indent=2) + '\n')
if not passed:
    raise RuntimeError('Compute/radio gate did not pass; preserve evidence, no rerun')
print('PASS bounded compute and 45 gateway replies', flush=True)
