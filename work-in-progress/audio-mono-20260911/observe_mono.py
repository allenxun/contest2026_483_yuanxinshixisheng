"""Run a bounded true-board receive-mono timing and restore check."""
import json
import re
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent
STAMP = time.strftime('%Y%m%d-%H%M%S')
LOG_PATH = ROOT / ('mono-smoke-' + STAMP + '.log')
RESULT_PATH = ROOT / ('mono-smoke-' + STAMP + '.json')
port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()


def read_prompt(seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
            break
    LOG_PATH.write_bytes(LOG_PATH.read_bytes() + data if LOG_PATH.exists() else data)
    print(data.decode(errors='replace'), flush=True)
    return bytes(data)


try:
    port.write(b'\r')
    boot = read_prompt(20)
    assert b'nsh>' in boot, 'Missing NSH prompt'
    port.write(b'k7sound capture-pga24-mono 3200\r')
    data = read_prompt(20)
finally:
    port.close()

pio = re.search(rb'SOUND pio=(-?\d+) frames=(\d+).*?stop=(-?\d+) held=(\d+)', data)
trace = re.search(rb'SOUND trace start=(\d+) end=(\d+)', data)
mono = re.search(rb'SOUND mono active=([0-9a-fA-F]{8}) restore=(-?\d+)', data)
pcm = re.search(rb'left_min=(-?\d+) left_max=(-?\d+) left_nonzero=(\d+) '
                rb'right_min=(-?\d+) right_max=(-?\d+) right_nonzero=(\d+)', data)
elapsed = int(trace.group(2)) - int(trace.group(1)) if trace else None
result = {
    'revision': 'audio-mono-20260911',
    'command': 'k7sound capture-pga24-mono 3200',
    'requested_frames': 3200,
    'pio_result': int(pio.group(1)) if pio else None,
    'captured_frames': int(pio.group(2)) if pio else None,
    'stop_result': int(pio.group(3)) if pio else None,
    'held': int(pio.group(4)) if pio else None,
    'elapsed_us': elapsed,
    'mono_active': mono.group(1).decode().lower() if mono else None,
    'mono_restore_result': int(mono.group(2)) if mono else None,
    'left_min': int(pcm.group(1)) if pcm else None,
    'left_max': int(pcm.group(2)) if pcm else None,
    'left_nonzero': int(pcm.group(3)) if pcm else None,
    'right_matches_left_stats': bool(pcm and pcm.group(1) == pcm.group(4) and
                                     pcm.group(2) == pcm.group(5) and
                                     pcm.group(3) == pcm.group(6)),
    'terminal_result_ok': b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in data,
    'timing_near_200ms': elapsed is not None and 180000 <= elapsed <= 220000,
    'hardware_tested': True,
    'raw_log': LOG_PATH.name,
}
RESULT_PATH.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result), flush=True)
