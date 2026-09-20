"""Bounded board smoke test for the explicit S16 microphone path."""
import json
import re
import time
from pathlib import Path

import serial

root = Path(__file__).resolve().parent
stamp = time.strftime('%Y%m%d-%H%M%S')
log_path = root / ('s16-smoke-' + stamp + '.log')
result_path = root / ('s16-smoke-' + stamp + '.json')

port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()

def read_until_prompt(seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
            break
    with log_path.open('ab') as output:
        output.write(data)
    print(data.decode(errors='replace'), flush=True)
    return bytes(data)

try:
    port.write(b'\r')
    boot = read_until_prompt(15)
    assert b'nsh>' in boot, 'Missing NSH prompt after boot'
    port.write(b'k7sound capture-pga24-16 3200\r')
    data = read_until_prompt(15)
finally:
    port.close()

match = re.search(
    rb'SOUND pcm left_min=(-?\d+) left_max=(-?\d+) left_nonzero=(\d+) '
    rb'right_min=(-?\d+) right_max=(-?\d+) right_nonzero=(\d+)', data)
assert match, 'Missing PCM statistics'
values = [int(value) for value in match.groups()]
registers = re.search(
    rb'RXCR=([0-9a-fA-F]{8}) FSCR=([0-9a-fA-F]{8}) CKR=([0-9a-fA-F]{8})', data)
assert registers, 'Missing SAI registers'
result = {
    'frames': 3200,
    'left_min': values[0], 'left_max': values[1], 'left_nonzero': values[2],
    'right_min': values[3], 'right_max': values[4], 'right_nonzero': values[5],
    'rxcr': registers.group(1).decode().lower(),
    'fscr': registers.group(2).decode().lower(),
    'ckr': registers.group(3).decode().lower(),
    'command_passed': b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in data,
    'hardware_tested': True,
}
assert result['rxcr'] == '00400def'
assert result['fscr'] == '0100f01f'
assert result['ckr'] == '00000038'
assert result['command_passed']
result_path.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
